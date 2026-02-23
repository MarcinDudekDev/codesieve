"""GuardClauses sieve — detects functions that should use early returns."""

from __future__ import annotations

from codesieve.models import Finding
from codesieve.parser.treesitter import ParsedFile, FunctionInfo
from codesieve.scoring import SCORE_MAX, SCORE_RANGE
from codesieve.sieves.base import BaseSieve

DOCSTRING_TYPES = ("string", "concatenated_string")
SKIP_TYPES = ("comment", "newline")
MIN_IF_LINES = 3


def _get_significant_children(body) -> list:
    """Extract significant children from a function body, skipping docstrings/comments."""
    significant = []
    for child in body.children:
        if child.type in SKIP_TYPES:
            continue
        if child.type == "expression_statement" and child.child_count > 0:
            if child.children[0].type in DOCSTRING_TYPES and not significant:
                continue
        significant.append(child)
    return significant


def _needs_guard_clause(func: FunctionInfo) -> bool:
    """Check if a function wraps its entire body in a single non-trivial if block."""
    body = func.node.child_by_field_name("body")
    if not body:
        return False

    significant = _get_significant_children(body)
    if len(significant) != 1:
        return False

    stmt = significant[0]
    if stmt.type != "if_statement":
        return False

    if_lines = stmt.end_point[0] - stmt.start_point[0] + 1
    return if_lines >= MIN_IF_LINES


class GuardClausesSieve(BaseSieve):
    name = "GuardClauses"
    description = "Detects functions wrapping entire body in a single if block instead of using early returns"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        findings: list[Finding] = []
        flagged = 0

        for func in functions:
            if _needs_guard_clause(func):
                flagged += 1
                findings.append(Finding(
                    message=f"{func.name}() wraps entire body in single if — consider guard clause",
                    line=func.start_line, function=func.name, severity="info",
                ))

        total = len(functions)
        ratio = flagged / total if total else 0.0
        score = SCORE_MAX - SCORE_RANGE * ratio
        summary = f"{flagged}/{total} functions should use guard clauses" if flagged else "all functions use good return patterns"

        return self.result(score, summary, findings)
