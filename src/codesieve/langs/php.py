"""PHP language pack — rules for all sieves."""

from __future__ import annotations

import re

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.parser import ast_utils

UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class PHPGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node) -> bool:
        return any(child.type in ("else_if_clause", "else_clause") for child in if_node.children)


class PHPMagicNumberRules:
    def is_default_param(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("simple_parameter", "variadic_parameter"):
                return True
            if parent.type in ("function_definition", "method_declaration",
                               "anonymous_function", "class_declaration"):
                break
            parent = parent.parent
        return False

    def is_constant_assignment(self, node, source: bytes) -> bool:
        parent = node.parent
        if parent and parent.type == "unary_op_expression":
            parent = parent.parent
        if parent and parent.type == "const_element":
            return True
        if parent and parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            if left and left.type == "variable_name":
                for sub in left.children:
                    if sub.type == "name":
                        return bool(UPPER_SNAKE.match(ast_utils.get_node_text(sub, source)))
        return False

    def is_negated(self, node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "unary_op_expression"
            and any(
                c.type == "-" or (c.type == "operator" and ast_utils.get_node_text(c, b"-") == "-")
                for c in parent.children
            )
        )


_pack = LanguagePack(
    guard_clauses=PHPGuardClauseRules(),
    magic_numbers=PHPMagicNumberRules(),
)

register_lang_pack("php", _pack)
