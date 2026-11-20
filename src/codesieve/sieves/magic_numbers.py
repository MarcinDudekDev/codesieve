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

ALLOWED_NUMBERS = {0, 1, -1, 2, 100, 1000}
PENALTY_PER_MAGIC = 0.5
NUMERIC_TYPES = ("integer", "float", "number", "int_literal", "float_literal")


def _parse_int(text: str) -> int:
    """Read an integer literal, including the forms ``int(x, 0)`` refuses.

    ``int("0755", 0)`` raises because Python 3 has no leading-zero literal, yet
    Go and PHP still lex ``0755`` / ``017`` that way, and JavaScript spells a
    BigInt ``123456n``. Those literals used to parse to ``None`` and vanish from
    the sieve silently, so a whole file could score 10.0 on them.
    """
    clean = text.replace("_", "")
    try:
        return int(clean, 0)
    except ValueError:
        digits = clean[:-1] if clean[-1:] in ("n", "j") else clean
        if not digits.isdigit():
            raise
        if len(digits) > 1 and digits[0] == "0" and set(digits) <= set("01234567"):
            return int(digits, 8)  # legacy octal: Go `0755`, PHP `017`
        return int(digits, 10)


def _parse_numeric(node: tree_sitter.Node, source: bytes,
                   is_negated_fn: Callable[[tree_sitter.Node], bool]) -> float | None:
    """Parse a numeric node to its value, accounting for unary minus parent."""
    text = ast_utils.get_node_text(node, source)
    try:
        clean = text.replace("_", "")
        if node.type in ("integer", "int_literal"):
            value = _parse_int(clean)
        elif node.type in ("number", "float_literal"):
            # JS and TS lex hex, octal and binary literals as `number`, which
            # float() rejects; _parse_int reads the prefix. Legacy `052` survives
            # float() as 52, so this fallback only ever sees a prefixed or
            # suffixed form.
            try:
                value = float(clean)
            except ValueError:
                value = _parse_int(clean)
        else:
            value = float(clean)
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
        """Count unexplained numeric literals inside function bodies and charge a flat cost each.

        Literals that already carry a name — parameter defaults, constant
        assignments — and the universally harmless values are not counted.
        """
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        pack = get_lang_pack(parsed.language, parsed.standard)
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
                penalty=PENALTY_PER_MAGIC,
            ))
        return results
