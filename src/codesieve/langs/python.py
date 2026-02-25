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


_PY_SKIP_NAMES = ("self", "cls")
_PY_TYPED_PARAM_TYPES = ("typed_parameter", "typed_default_parameter")
_PY_UNTYPED_PARAM_TYPES = ("identifier", "default_parameter")
_PY_SPLAT_TYPES = ("list_splat_pattern", "dictionary_splat_pattern")


def _get_param_name_python(child, source: bytes) -> str | None:
    if child.type == "identifier":
        name = ast_utils.get_node_text(child, source)
        return None if name in _PY_SKIP_NAMES else name
    if child.type in _PY_SPLAT_TYPES:
        for sub in child.children:
            if sub.type == "identifier":
                name = ast_utils.get_node_text(sub, source)
                return None if name in _PY_SKIP_NAMES else name
        return None
    name_child = child.child_by_field_name("name") or (child.children[0] if child.children else None)
    if name_child:
        name = ast_utils.get_node_text(name_child, source)
        return None if name in _PY_SKIP_NAMES else name
    return "<unknown>"


class PythonTypeHintRules:
    supported = True
    skip_reason = ""

    def check_params(self, func, source: bytes) -> tuple[int, int, list]:
        from codesieve.models import Finding
        params_node = func.node.child_by_field_name("parameters")
        if params_node is None:
            return 0, 0, []

        total = 0
        annotated = 0
        findings: list[Finding] = []

        for child in params_node.children:
            if child.type in _PY_TYPED_PARAM_TYPES:
                name = _get_param_name_python(child, source)
                if name is None:
                    continue
                total += 1
                annotated += 1
            elif child.type in _PY_UNTYPED_PARAM_TYPES:
                name = _get_param_name_python(child, source)
                if name is None:
                    continue
                total += 1
                findings.append(Finding(
                    message=f"parameter '{name}' in {func.name}() missing type hint",
                    line=func.start_line, function=func.name, severity="info",
                ))
            elif child.type in _PY_SPLAT_TYPES:
                name = _get_param_name_python(child, source)
                if name is None:
                    continue
                total += 1
                prefix = "*" if child.type == "list_splat_pattern" else "**"
                findings.append(Finding(
                    message=f"parameter '{prefix}{name}' in {func.name}() missing type hint",
                    line=func.start_line, function=func.name, severity="info",
                ))

        return total, annotated, findings

    def check_extras(self, parsed) -> tuple[float, str, list]:
        return 0.0, "", []


_pack = LanguagePack(
    guard_clauses=PythonGuardClauseRules(),
    magic_numbers=PythonMagicNumberRules(),
    type_hints=PythonTypeHintRules(),
)

register_lang_pack("python", _pack)
