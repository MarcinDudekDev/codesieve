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


def _get_block(except_node):
    """Extract the block child from an except clause."""
    for child in except_node.children:
        if child.type == "block":
            return child
    return None


EXCEPT_TYPE_INDICATORS = ("identifier", "attribute", "tuple", "as_pattern")


def _is_bare_except(except_node) -> bool:
    """Check if except clause has no exception type specified (AST-based)."""
    return not any(child.type in EXCEPT_TYPE_INDICATORS for child in except_node.children)


def _is_empty_body(except_node) -> bool:
    """Check if except body contains only pass or ellipsis."""
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


def _is_broad_without_reraise(except_node, source: bytes) -> bool:
    """Check if except catches Exception broadly without re-raising."""
    catches_exception = any(
        child.type == "identifier" and ast_utils.get_node_text(child, source) == "Exception"
        for child in except_node.children
    )
    if not catches_exception:
        return False

    block = _get_block(except_node)
    if block is None:
        return False

    return not any(node.type == "raise_statement" for node in ast_utils.walk_within_scope(block))


def _check_except_clause(clause, source: bytes) -> list[tuple[str, float, str]]:
    """Check a single except clause for issues. Returns list of (message, penalty, severity)."""
    issues = []
    if _is_bare_except(clause):
        issues.append(("bare except: clause (no exception type)", BARE_EXCEPT_PENALTY, "error"))
    if _is_empty_body(clause):
        issues.append(("empty except body (pass/...)", EMPTY_BODY_PENALTY, "warning"))
    if _is_broad_without_reraise(clause, source):
        issues.append(("broad 'except Exception' without re-raise", BROAD_CATCH_PENALTY, "warning"))
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

        findings: list[Finding] = []
        score = SCORE_MAX
        counts = {"bare": 0, "empty": 0, "broad": 0}
        count_keys = {"bare except": "bare", "empty except": "empty", "broad": "broad"}

        for try_node in try_nodes:
            for child in try_node.children:
                if child.type != "except_clause":
                    continue
                line = child.start_point[0] + 1
                for message, penalty, severity in _check_except_clause(child, parsed.source):
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
