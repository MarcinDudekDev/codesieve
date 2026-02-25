"""MagicNumbers sieve — detects unexplained numeric literals in function bodies."""

from __future__ import annotations

from typing import Callable

import tree_sitter

from codesieve.langs import get_lang_pack
from codesieve.langs.protocols import MagicNumberRules
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

ALLOWED_NUMBERS = {0, 1, -1, 2, 0.0, 1.0, 100, 1000}
PENALTY_PER_MAGIC = 0.5
NUMERIC_TYPES = ("integer", "float", "number")


def _parse_numeric(node: tree_sitter.Node, source: bytes,
                   is_negated_fn: Callable[[tree_sitter.Node], bool]) -> float | None:
    """Parse a numeric node to its value, accounting for unary minus parent."""
    text = ast_utils.get_node_text(node, source)
    try:
        if node.type == "integer":
            value = int(text, 0)
        elif node.type == "number":
            value = float(text) if "." in text or "e" in text.lower() else int(text, 0)
        else:
            value = float(text)
    except (ValueError, OverflowError):
        return None
    if is_negated_fn(node):
        value = -value
    return value


class MagicNumbersSieve(BaseSieve):
    name = "MagicNumbers"
    description = "Detects unexplained numeric literals (magic numbers) in function bodies"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        pack = get_lang_pack(parsed.language)
        rules = pack.magic_numbers if pack else None
        if rules is None:
            return self.skip("No magic number rules for this language")

        findings: list[Finding] = []

        for func in functions:
            body = func.node.child_by_field_name("body")
            if not body:
                continue
            findings.extend(self._check_body(func.name, body, parsed.source, rules))

        magic_count = len(findings)
        score = SCORE_MAX - PENALTY_PER_MAGIC * magic_count
        summary = f"{magic_count} magic number(s) found" if magic_count else "no magic numbers"

        return self.result(score, summary, findings)

    def _check_body(self, func_name: str, body: tree_sitter.Node, source: bytes,
                    rules: MagicNumberRules) -> list[Finding]:
        """Find magic numbers in a function body."""
        results: list[Finding] = []
        for node in ast_utils.walk_within_scope(body):
            if node.type not in NUMERIC_TYPES:
                continue
            if rules.is_default_param(node) or rules.is_constant_assignment(node, source):
                continue
            value = _parse_numeric(node, source, rules.is_negated)
            if value is None or value in ALLOWED_NUMBERS:
                continue
            display = f"-{ast_utils.get_node_text(node, source)}" if rules.is_negated(node) else ast_utils.get_node_text(node, source)
            results.append(Finding(
                message=f"magic number {display} in {func_name}()",
                line=node.start_point[0] + 1, function=func_name, severity="info",
            ))
        return results
