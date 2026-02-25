"""ErrorHandling sieve — measures error handling quality."""

from __future__ import annotations

from codesieve.langs import get_lang_pack
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

BARE_EXCEPT_PENALTY = 1.5
EMPTY_BODY_PENALTY = 1.0
BROAD_CATCH_PENALTY = 0.5


def _has_raise_in_scope(block, rules) -> bool:
    """Check if block contains a raise/throw, not crossing into nested handlers or functions."""
    stack = list(reversed(block.children))
    while stack:
        node = stack.pop()
        if node.type in rules.raise_types:
            return True
        if node.type in rules.raise_skip_types:
            continue
        stack.extend(reversed(node.children))
    return False


def _is_broad_catch(handler_node, source: bytes, rules) -> bool:
    """Check if handler catches broad exception without re-raising."""
    if not rules.has_broad_catch_concept():
        return False

    type_text = rules.get_caught_type_text(handler_node, source)
    if type_text is None or type_text not in rules.broad_exception_types:
        return False

    body = rules.get_handler_body(handler_node)
    if body is None:
        return False
    return not _has_raise_in_scope(body, rules)


def _check_handler(handler_node, source: bytes, rules) -> list[tuple[str, float, str]]:
    """Check a single exception handler for issues."""
    issues = []

    if rules.is_bare_handler(handler_node):
        issues.append(("bare except: clause (no exception type)", BARE_EXCEPT_PENALTY, "error"))
    if rules.is_empty_body(handler_node):
        # Use language-appropriate message
        msg = "empty except body (pass/...)" if rules.handler_node_type == "except_clause" else "empty catch body"
        issues.append((msg, EMPTY_BODY_PENALTY, "warning"))

    if _is_broad_catch(handler_node, source, rules):
        broad_name = "Exception" if rules.handler_node_type == "except_clause" else "\\Exception"
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

        pack = get_lang_pack(parsed.language)
        rules = pack.error_handling if pack else None
        if rules is None:
            return self.skip("No error handling rules for this language")

        findings: list[Finding] = []
        score = SCORE_MAX
        counts = {"bare": 0, "empty": 0, "broad": 0}
        count_keys = {"bare except": "bare", "empty": "empty", "broad": "broad"}

        for try_node in try_nodes:
            for child in try_node.children:
                if child.type != rules.handler_node_type:
                    continue
                line = child.start_point[0] + 1
                for message, penalty, severity in _check_handler(child, parsed.source, rules):
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
