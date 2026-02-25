"""JavaScript language pack — rules for all sieves."""

from __future__ import annotations

import re

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.parser import ast_utils

UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class JSGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node) -> bool:
        return any(child.type == "else_clause" for child in if_node.children)


class JSMagicNumberRules:
    def is_default_param(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type == "assignment_pattern" and parent.parent and parent.parent.type == "formal_parameters":
                return True
            if parent.type in ("function_declaration", "method_definition",
                               "arrow_function", "generator_function_declaration",
                               "class_declaration"):
                break
            parent = parent.parent
        return False

    def is_constant_assignment(self, node, source: bytes) -> bool:
        parent = node.parent
        if parent and parent.type == "unary_expression":
            parent = parent.parent
        if parent and parent.type == "variable_declarator":
            grandparent = parent.parent
            if grandparent and grandparent.type == "lexical_declaration":
                has_const = any(c.type == "const" for c in grandparent.children)
                if has_const:
                    name_node = parent.child_by_field_name("name")
                    if name_node and name_node.type == "identifier":
                        return bool(UPPER_SNAKE.match(ast_utils.get_node_text(name_node, source)))
        return False

    def is_negated(self, node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "unary_expression"
            and any(c.type == "-" for c in parent.children)
        )


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
    magic_numbers=JSMagicNumberRules(),
)

register_lang_pack("javascript", _pack)
