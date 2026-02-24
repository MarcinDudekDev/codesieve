"""ErrorHandling sieve — measures error handling quality."""

from __future__ import annotations

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

BARE_EXCEPT_PENALTY = 1.5
EMPTY_BODY_PENALTY = 1.0
BROAD_CATCH_PENALTY = 0.5

# Broad exception types per language
BROAD_EXCEPTIONS = {
    "python": {"Exception"},
    "php": {"Exception", "\\Exception", "Throwable", "\\Throwable"},
}


# ---- Python-specific helpers ----

def _get_block(except_node):
    """Extract the block child from a Python except clause."""
    for child in except_node.children:
        if child.type == "block":
            return child
    return None


EXCEPT_TYPE_INDICATORS = ("identifier", "attribute", "tuple")


def _is_bare_except_python(except_node) -> bool:
    """Check if Python except clause has no exception type specified."""
    return not any(child.type in EXCEPT_TYPE_INDICATORS for child in except_node.children)


def _is_empty_body_python(except_node) -> bool:
    """Check if Python except body contains only pass or ellipsis."""
    block = _get_block(except_node)
    if block is None:
        return False

    significant = [c for c in block.children if c.type not in ("comment", "newline")]
    if len(significant) != 1:
        return False

    stmt = significant[0]
    if stmt.type == "pass_statement":
        return True
    if stmt.type == "expression_statement":
        return any(child.type == "ellipsis" for child in stmt.children)
    return False


# ---- PHP-specific helpers ----

def _get_catch_body(catch_node):
    """Extract the compound_statement body from a PHP catch clause."""
    return catch_node.child_by_field_name("body")


def _is_empty_body_php(catch_node) -> bool:
    """Check if PHP catch body is empty (only braces, whitespace, comments)."""
    body = _get_catch_body(catch_node)
    if body is None:
        return False
    significant = [c for c in body.children if c.type not in ("comment", "{", "}", "php_tag")]
    return len(significant) == 0


def _get_catch_type_text(catch_node, source: bytes) -> str | None:
    """Extract the exception type text from a PHP catch clause."""
    type_node = catch_node.child_by_field_name("type")
    if type_node:
        return ast_utils.get_node_text(type_node, source)
    return None


# ---- JS/TS-specific helpers ----

def _get_catch_body_js(catch_node):
    """Extract the statement_block body from a JS/TS catch clause."""
    return catch_node.child_by_field_name("body")


def _is_empty_body_js(catch_node) -> bool:
    """Check if JS/TS catch body is empty (only braces, whitespace, comments)."""
    body = _get_catch_body_js(catch_node)
    if body is None:
        return False
    significant = [c for c in body.children if c.type not in ("comment", "{", "}")]
    return len(significant) == 0


# ---- Shared helpers ----

_RAISE_SKIP_TYPES_PYTHON = ("function_definition", "except_clause")
_RAISE_SKIP_TYPES_PHP = ("function_definition", "method_declaration", "anonymous_function",
                         "arrow_function", "catch_clause")
_RAISE_SKIP_TYPES_JS = ("function_declaration", "method_definition", "arrow_function",
                        "generator_function_declaration", "function_expression", "catch_clause")


def _has_raise_in_scope(block, language: str) -> bool:
    """Check if block contains a raise/throw, not crossing into nested handlers or functions."""
    if language in ("javascript", "typescript"):
        raise_type = "throw_statement"
        skip_types = _RAISE_SKIP_TYPES_JS
    elif language == "php":
        raise_type = "throw_expression"
        skip_types = _RAISE_SKIP_TYPES_PHP
    else:
        raise_type = "raise_statement"
        skip_types = _RAISE_SKIP_TYPES_PYTHON

    stack = list(reversed(block.children))
    while stack:
        node = stack.pop()
        if node.type == raise_type:
            return True
        # PHP: throw can also be in a throw_statement
        if language == "php" and node.type == "throw_statement":
            return True
        if node.type in skip_types:
            continue
        stack.extend(reversed(node.children))
    return False


def _is_broad_catch(handler_node, source: bytes, language: str) -> bool:
    """Check if handler catches broad exception without re-raising."""
    # JS/TS catches are untyped by design — no broad catch concept
    if language in ("javascript", "typescript"):
        return False
    broad_types = BROAD_EXCEPTIONS.get(language, set())

    if language == "php":
        type_text = _get_catch_type_text(handler_node, source)
        if type_text is None or type_text not in broad_types:
            return False
        body = _get_catch_body(handler_node)
    else:
        # Python
        catches_exception = any(
            child.type == "identifier" and ast_utils.get_node_text(child, source) == "Exception"
            for child in handler_node.children
        )
        if not catches_exception:
            return False
        body = _get_block(handler_node)

    if body is None:
        return False
    return not _has_raise_in_scope(body, language)


def _check_handler(handler_node, source: bytes, language: str) -> list[tuple[str, float, str]]:
    """Check a single exception handler for issues. Returns list of (message, penalty, severity)."""
    issues = []

    if language == "python":
        if _is_bare_except_python(handler_node):
            issues.append(("bare except: clause (no exception type)", BARE_EXCEPT_PENALTY, "error"))
        if _is_empty_body_python(handler_node):
            issues.append(("empty except body (pass/...)", EMPTY_BODY_PENALTY, "warning"))
    elif language in ("javascript", "typescript"):
        if _is_empty_body_js(handler_node):
            issues.append(("empty catch body", EMPTY_BODY_PENALTY, "warning"))
    else:
        # PHP catch clauses always require a type — no "bare catch" possible
        if _is_empty_body_php(handler_node):
            issues.append(("empty catch body", EMPTY_BODY_PENALTY, "warning"))

    if _is_broad_catch(handler_node, source, language):
        broad_name = "Exception" if language == "python" else "\\Exception"
        issues.append((f"broad 'catch {broad_name}' without re-throw", BROAD_CATCH_PENALTY, "warning"))

    return issues


class ErrorHandlingSieve(BaseSieve):
    name = "ErrorHandling"
    description = "Measures error handling quality: bare excepts, empty handlers, broad catches"
    default_weight = 0.10

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        try_nodes = ast_utils.find_nodes(parsed.root, ("try_statement",))

        if not try_nodes:
            count = len(parsed.get_functions())
            msg = f"No try blocks in {count} functions" if count else "No functions or try blocks found"
            return self.perfect(msg)

        if parsed.language == "python":
            handler_type = "except_clause"
        else:
            handler_type = "catch_clause"  # PHP, JS, TS all use catch_clause

        findings: list[Finding] = []
        score = SCORE_MAX
        counts = {"bare": 0, "empty": 0, "broad": 0}
        count_keys = {"bare except": "bare", "empty": "empty", "broad": "broad"}

        for try_node in try_nodes:
            for child in try_node.children:
                if child.type != handler_type:
                    continue
                line = child.start_point[0] + 1
                for message, penalty, severity in _check_handler(child, parsed.source, parsed.language):
                    score -= penalty
                    findings.append(Finding(message=message, line=line, severity=severity))
                    for prefix, key in count_keys.items():
                        if prefix in message:
                            counts[key] += 1
                            break

        summary = self._build_summary(counts, len(try_nodes))
        return self.result(score, summary, findings)

    def _build_summary(self, counts: dict[str, int], try_count: int) -> str:
        parts = []
        if counts["bare"]:
            parts.append(f"{counts['bare']} bare except(s)")
        if counts["empty"]:
            parts.append(f"{counts['empty']} empty handler(s)")
        if counts["broad"]:
            parts.append(f"{counts['broad']} broad catch(es)")
        return ", ".join(parts) if parts else f"{try_count} try blocks, all good"
