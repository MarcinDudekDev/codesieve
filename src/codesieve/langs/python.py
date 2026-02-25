"""Python language pack — rules for all sieves."""

from __future__ import annotations

import re

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.parser import ast_utils

UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class PythonGuardClauseRules:
    docstring_types = ("string", "concatenated_string")

    def has_elif_or_else(self, if_node) -> bool:
        return any(child.type in ("elif_clause", "else_clause") for child in if_node.children)


class PythonMagicNumberRules:
    def is_default_param(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("default_parameter", "typed_default_parameter"):
                return True
            if parent.type in ("function_definition", "class_definition", "module"):
                break
            parent = parent.parent
        return False

    def is_constant_assignment(self, node, source: bytes) -> bool:
        parent = node.parent
        if parent and parent.type == "unary_operator":
            parent = parent.parent
        if parent and parent.type == "assignment":
            left = parent.child_by_field_name("left")
            if left and left.type == "identifier":
                return bool(UPPER_SNAKE.match(ast_utils.get_node_text(left, source)))
        return False

    def is_negated(self, node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "unary_operator"
            and any(c.type == "-" for c in parent.children)
        )


_pack = LanguagePack(
    guard_clauses=PythonGuardClauseRules(),
    magic_numbers=PythonMagicNumberRules(),
)

register_lang_pack("python", _pack)
