"""MagicNumbers sieve — detects unexplained numeric literals in function bodies."""

from __future__ import annotations

import re

from codesieve.models import Finding
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

ALLOWED_NUMBERS = {0, 1, -1, 2, 0.0, 1.0, 100, 1000}
UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PENALTY_PER_MAGIC = 0.5
DEFAULT_PARAM_TYPES = ("default_parameter", "typed_default_parameter")
NUMERIC_TYPES = ("integer", "float")


def _is_default_param(node) -> bool:
    """Check if this numeric node is a default parameter value."""
    parent = node.parent
    while parent:
        if parent.type in DEFAULT_PARAM_TYPES:
            return True
        if parent.type in ("function_definition", "class_definition", "module"):
            break
        parent = parent.parent
    return False


def _is_constant_assignment(node, source: bytes) -> bool:
    """Check if this numeric node is assigned to an UPPER_SNAKE variable."""
    parent = node.parent
    if parent and parent.type == "unary_operator":
        parent = parent.parent
    if parent and parent.type == "assignment":
        left = parent.child_by_field_name("left")
        if left and left.type == "identifier":
            return bool(UPPER_SNAKE.match(ast_utils.get_node_text(left, source)))
    return False


def _parse_numeric(node, source: bytes) -> float | None:
    """Parse a numeric node to its value, returning None on failure."""
    text = ast_utils.get_node_text(node, source)
    try:
        return int(text, 0) if node.type == "integer" else float(text)
    except ValueError:
        return None


class MagicNumbersSieve(BaseSieve):
    name = "MagicNumbers"
    description = "Detects unexplained numeric literals (magic numbers) in function bodies"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        findings: list[Finding] = []

        for func in functions:
            body = func.node.child_by_field_name("body")
            if not body:
                continue
            findings.extend(self._check_body(func.name, body, parsed.source))

        magic_count = len(findings)
        score = SCORE_MAX - PENALTY_PER_MAGIC * magic_count
        summary = f"{magic_count} magic number(s) found" if magic_count else "no magic numbers"

        return self.result(score, summary, findings)

    def _check_body(self, func_name: str, body, source: bytes) -> list[Finding]:
        """Find magic numbers in a function body."""
        results = []
        for node in ast_utils.walk_tree(body):
            if node.type not in NUMERIC_TYPES:
                continue
            if _is_default_param(node) or _is_constant_assignment(node, source):
                continue
            value = _parse_numeric(node, source)
            if value is None or value in ALLOWED_NUMBERS:
                continue
            results.append(Finding(
                message=f"magic number {ast_utils.get_node_text(node, source)} in {func_name}()",
                line=node.start_point[0] + 1, function=func_name, severity="info",
            ))
        return results
