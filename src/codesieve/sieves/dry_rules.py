"""Curated stdlib/framework-helper reimplementation rules for the DRY sieve (Part b).

Each rule fires on a SINGLE occurrence of a hand-rolled idiom that a well-known stdlib or
framework helper already covers. Rules are intentionally high-precision / low-recall: they
match a narrow structural signature and emit an `info` suggestion — they never hard-fail.

A rule is a callable ``predicate(node, parsed) -> Suggestion | None`` plus a ``language``
gate. The DRY sieve walks every node once and offers it to each rule for the file's language.
"""

from __future__ import annotations

from dataclasses import dataclass

import tree_sitter

from codesieve.parser.treesitter import ParsedFile

# Megabyte / gigabyte / terabyte byte counts written as a single literal.
_BYTE_LITERALS = {b"1048576", b"1073741824", b"1099511627776"}


@dataclass(frozen=True)
class Suggestion:
    """A single stdlib-reimplementation hint produced by a rule."""
    rule: str  # stable rule id, used for per-function dedup
    message: str
    dedup_scope: int  # node id the suggestion is deduped within (e.g. enclosing function)


def _unwrap(node: tree_sitter.Node) -> tree_sitter.Node:
    """Peel a single-child parenthesized expression down to its inner expression."""
    while node.type == "parenthesized_expression":
        named = [c for c in node.children if c.is_named]
        if len(named) != 1:
            break
        node = named[0]
    return node


def _is_1024_product(node: tree_sitter.Node) -> tuple[bool, int]:
    """Return (is-pure-1024-multiplication, count-of-1024-factors) for a subtree.

    Recognizes `1024`, `1024 * 1024`, `1024 * 1024 * 1024`, etc. (any parenthesization).
    """
    node = _unwrap(node)
    if node.type == "integer":
        return (node.text == b"1024", 1 if node.text == b"1024" else 0)
    if node.type == "binary_expression":
        op = node.child_by_field_name("operator")
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if op is None or op.text != b"*" or left is None or right is None:
            return (False, 0)
        lok, ln = _is_1024_product(left)
        rok, rn = _is_1024_product(right)
        return (lok and rok, ln + rn)
    return (False, 0)


def _is_byte_unit_constant(node: tree_sitter.Node) -> bool:
    """True if the node is a 2^20+/power-of-1024 byte constant (1024*1024, 1048576, …)."""
    node = _unwrap(node)
    if node.type == "integer":
        return node.text in _BYTE_LITERALS
    pure, factors = _is_1024_product(node)
    return pure and factors >= 2  # at least 1024*1024, so KB-only math isn't flagged


def _enclosing_scope(node: tree_sitter.Node, types: tuple[str, ...]) -> int:
    """Node id of the nearest enclosing scope of one of `types` (else the root's id)."""
    current = node.parent
    last = node
    while current is not None:
        if current.type in types:
            return current.id
        last = current
        current = current.parent
    return last.id


def _has_ancestor(node: tree_sitter.Node, types: tuple[str, ...]) -> bool:
    current = node.parent
    while current is not None:
        if current.type in types:
            return True
        current = current.parent
    return False


# ---- PHP / WordPress rules --------------------------------------------------------------
def _php_size_format(node: tree_sitter.Node, parsed: ParsedFile) -> Suggestion | None:
    """`$bytes / (1024 * 1024)` (or / 1048576) → WordPress `size_format()`."""
    if node.type != "binary_expression":
        return None
    op = node.child_by_field_name("operator")
    if op is None or op.text not in (b"/", b"*"):
        return None
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None:
        return None
    if not (_is_byte_unit_constant(left) or _is_byte_unit_constant(right)):
        return None
    return Suggestion(
        rule="php-size-format",
        message=("manual byte→MB/GB math (÷1024²) — WordPress `size_format()` "
                 "formats byte counts as human-readable strings"),
        dedup_scope=_enclosing_scope(node, parsed.lang_map.function_types),
    )


def _php_hr_to_bytes(node: tree_sitter.Node, parsed: ParsedFile) -> Suggestion | None:
    """A `$v *= 1024` suffix ladder (k/m/g) → WordPress `wp_convert_hr_to_bytes()`."""
    if node.type != "augmented_assignment_expression":
        return None
    op = node.child_by_field_name("operator")
    right = node.child_by_field_name("right")
    if op is None or op.text != b"*=" or right is None or right.text != b"1024":
        return None
    if not _has_ancestor(node, ("switch_statement", "if_statement")):
        return None
    return Suggestion(
        rule="php-hr-to-bytes",
        message=("hand-rolled k/m/g ini-size parser (`*= 1024` ladder) — WordPress "
                 "`wp_convert_hr_to_bytes()` parses shorthand byte values"),
        dedup_scope=_enclosing_scope(node, parsed.lang_map.function_types),
    )


@dataclass(frozen=True)
class Rule:
    name: str
    language: str
    predicate: object  # callable(node, parsed) -> Suggestion | None


RULES: tuple[Rule, ...] = (
    Rule("php-size-format", "php", _php_size_format),
    Rule("php-hr-to-bytes", "php", _php_hr_to_bytes),
)


def rules_for(language: str) -> list[Rule]:
    return [r for r in RULES if r.language == language]
