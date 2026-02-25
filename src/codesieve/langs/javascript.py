"""JavaScript language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.parser import ast_utils

from codesieve.langs._patterns import SNAKE_CASE, UPPER_SNAKE, PASCAL_CASE, CAMEL_CASE, ALLOWED_SHORT, SHORT_NAME_LIMIT


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


class JSErrorHandlingRules:
    handler_node_type = "catch_clause"
    broad_exception_types: frozenset[str] = frozenset()
    raise_types = ("throw_statement",)
    raise_skip_types = ("function_declaration", "method_definition", "arrow_function",
                        "generator_function_declaration", "function_expression", "catch_clause")

    def is_bare_handler(self, node) -> bool:
        return False  # JS catch is inherently untyped

    def is_empty_body(self, node) -> bool:
        body = self.get_handler_body(node)
        if body is None:
            return False
        significant = [c for c in body.children if c.type not in ("comment", "{", "}")]
        return len(significant) == 0

    def get_handler_body(self, node):
        return node.child_by_field_name("body")

    def get_caught_type_text(self, node, source: bytes) -> str | None:
        return None  # JS/TS catches are untyped

    def has_broad_catch_concept(self) -> bool:
        return False


_JS_PARAM_NODE_TYPES = ("identifier", "assignment_pattern", "rest_pattern",
                       "object_pattern", "array_pattern")


def _extract_param_name_js(child, source: bytes) -> str | None:
    if child.type == "identifier":
        return ast_utils.get_node_text(child, source)
    if child.type == "assignment_pattern":
        for sub in child.children:
            if sub.type == "identifier":
                return ast_utils.get_node_text(sub, source)
    if child.type == "rest_pattern":
        for sub in child.children:
            if sub.type == "identifier":
                return ast_utils.get_node_text(sub, source)
    return None


class JSNamingRules:
    skip_param_names: frozenset[str] = frozenset()
    param_node_types = _JS_PARAM_NODE_TYPES

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        if context == "class":
            if PASCAL_CASE.match(name):
                return True, ""
            return False, f"class '{name}' should be PascalCase"
        if context == "constant":
            return True, ""
        if context == "method":
            if CAMEL_CASE.match(name) or name == "constructor":
                return True, ""
            return False, f"method '{name}' should be camelCase"
        if CAMEL_CASE.match(name) or SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
            return True, ""
        return False, f"'{name}' should be camelCase or snake_case"

    def func_context(self, node) -> str:
        if node.type == "method_definition":
            return "method"
        return "function"

    def extract_param_name(self, node, source: bytes) -> str | None:
        return _extract_param_name_js(node, source)

    def check_variable_names(self, func, source: bytes, seen: set[str]) -> tuple[int, int, list]:
        from codesieve.models import Finding
        body = func.node.child_by_field_name("body")
        if not body:
            return 0, 0, []

        total = 0
        violations = 0
        findings: list[Finding] = []

        for node in ast_utils.walk_within_scope(body):
            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left and left.type == "identifier":
                    name = ast_utils.get_node_text(left, source)
                    if name not in seen and name != "this":
                        seen.add(name)
                        total += 1
                        line = node.start_point[0] + 1
                        if len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
                            violations += 1
                            findings.append(Finding(
                                message=f"abbreviated variable '{name}' in {func.name}()",
                                line=line, function=func.name, severity="info",
                            ))
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    name = ast_utils.get_node_text(name_node, source)
                    if name not in seen:
                        seen.add(name)
                        total += 1
                        line = node.start_point[0] + 1
                        if len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
                            violations += 1
                            findings.append(Finding(
                                message=f"abbreviated variable '{name}' in {func.name}()",
                                line=line, function=func.name, severity="info",
                            ))

        return total, violations, findings


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
    magic_numbers=JSMagicNumberRules(),
    error_handling=JSErrorHandlingRules(),
    naming=JSNamingRules(),
)

register_lang_pack("javascript", _pack)
