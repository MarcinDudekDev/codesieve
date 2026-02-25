"""JavaScript language pack — rules for all sieves."""

from __future__ import annotations

import tree_sitter

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs._patterns import SNAKE_CASE, UPPER_SNAKE, PASCAL_CASE, CAMEL_CASE, ALLOWED_SHORT, SHORT_NAME_LIMIT
from codesieve.models import Finding
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import FunctionInfo


class JSGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node: tree_sitter.Node) -> bool:
        return any(child.type == "else_clause" for child in if_node.children)


def _js_const_upper_snake(declarator: tree_sitter.Node, source: bytes) -> bool:
    """Check if a variable_declarator in a const declaration has an UPPER_SNAKE name."""
    grandparent = declarator.parent
    if not grandparent or grandparent.type != "lexical_declaration":
        return False
    if not any(c.type == "const" for c in grandparent.children):
        return False
    name_node = declarator.child_by_field_name("name")
    return (name_node is not None
            and name_node.type == "identifier"
            and bool(UPPER_SNAKE.match(ast_utils.get_node_text(name_node, source))))


class JSMagicNumberRules:
    def is_default_param(self, node: tree_sitter.Node) -> bool:
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

    def is_constant_assignment(self, node: tree_sitter.Node, source: bytes) -> bool:
        parent = node.parent
        if parent and parent.type == "unary_expression":
            parent = parent.parent
        if not parent or parent.type != "variable_declarator":
            return False
        return _js_const_upper_snake(parent, source)

    def is_negated(self, node: tree_sitter.Node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "unary_expression"
            and any(c.type == "-" for c in parent.children)
        )


class JSErrorHandlingRules:
    handler_node_type = "catch_clause"
    broad_exception_types: frozenset[str] = frozenset()
    raise_types = ("throw_statement",)
    raise_skip_types = ("function_declaration", "method_definition", "arrow_function",
                        "generator_function_declaration", "function_expression", "catch_clause")

    def is_bare_handler(self, node: tree_sitter.Node) -> bool:
        return False  # JS catch is inherently untyped

    def is_empty_body(self, node: tree_sitter.Node) -> bool:
        body = self.get_handler_body(node)
        if body is None:
            return False
        significant = [c for c in body.children if c.type not in ("comment", "{", "}")]
        return len(significant) == 0

    def get_handler_body(self, node: tree_sitter.Node) -> tree_sitter.Node | None:
        return node.child_by_field_name("body")

    def get_caught_type_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        return None  # JS/TS catches are untyped

    def has_broad_catch_concept(self) -> bool:
        return False


_JS_PARAM_NODE_TYPES = ("identifier", "assignment_pattern", "rest_pattern",
                       "object_pattern", "array_pattern")


def _extract_param_name_js(child: tree_sitter.Node, source: bytes) -> str | None:
    if child.type == "identifier":
        return ast_utils.get_node_text(child, source)
    if child.type in ("assignment_pattern", "rest_pattern"):
        for sub in child.children:
            if sub.type == "identifier":
                return ast_utils.get_node_text(sub, source)
    return None


def _check_js_abbreviated_var(name: str, line: int, func_name: str) -> Finding | None:
    """Return a Finding if name is abbreviated, else None."""
    if len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
        return Finding(
            message=f"abbreviated variable '{name}' in {func_name}()",
            line=line, function=func_name, severity="info",
        )
    return None


def _extract_assignment_name(node: tree_sitter.Node, source: bytes) -> str | None:
    """Extract identifier name from assignment_expression or variable_declarator."""
    if node.type == "assignment_expression":
        left = node.child_by_field_name("left")
        if left and left.type == "identifier":
            return ast_utils.get_node_text(left, source)
    elif node.type == "variable_declarator":
        name_node = node.child_by_field_name("name")
        if name_node and name_node.type == "identifier":
            return ast_utils.get_node_text(name_node, source)
    return None


_JS_VAR_NODE_TYPES = ("assignment_expression", "variable_declarator")


class JSNamingRules:
    skip_param_names: frozenset[str] = frozenset()
    param_node_types = _JS_PARAM_NODE_TYPES

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        if context == "class":
            return (True, "") if PASCAL_CASE.match(name) else (False, f"class '{name}' should be PascalCase")
        if context == "constant":
            return True, ""
        if context == "method":
            if CAMEL_CASE.match(name) or name == "constructor":
                return True, ""
            return False, f"method '{name}' should be camelCase"
        if CAMEL_CASE.match(name) or SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
            return True, ""
        return False, f"'{name}' should be camelCase or snake_case"

    def func_context(self, node: tree_sitter.Node) -> str:
        return "method" if node.type == "method_definition" else "function"

    def extract_param_name(self, node: tree_sitter.Node, source: bytes) -> str | None:
        return _extract_param_name_js(node, source)

    def check_variable_names(self, func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
        body = func.node.child_by_field_name("body")
        if not body:
            return 0, 0, []

        total = 0
        violations = 0
        findings: list[Finding] = []

        for node in ast_utils.walk_within_scope(body):
            if node.type not in _JS_VAR_NODE_TYPES:
                continue
            name = _extract_assignment_name(node, source)
            if not name or name in seen or name == "this":
                continue
            seen.add(name)
            total += 1
            finding = _check_js_abbreviated_var(name, node.start_point[0] + 1, func.name)
            if finding:
                violations += 1
                findings.append(finding)

        return total, violations, findings


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
    magic_numbers=JSMagicNumberRules(),
    error_handling=JSErrorHandlingRules(),
    naming=JSNamingRules(),
)

register_lang_pack("javascript", _pack)
