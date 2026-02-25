"""Python language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.parser import ast_utils

from codesieve.langs._patterns import SNAKE_CASE, UPPER_SNAKE, PASCAL_CASE, DUNDER, ALLOWED_SHORT, SHORT_NAME_LIMIT


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


_EXCEPT_TYPE_INDICATORS = ("identifier", "attribute", "tuple")


class PythonErrorHandlingRules:
    handler_node_type = "except_clause"
    broad_exception_types = frozenset({"Exception"})
    raise_types = ("raise_statement",)
    raise_skip_types = ("function_definition", "except_clause")

    def is_bare_handler(self, node) -> bool:
        return not any(child.type in _EXCEPT_TYPE_INDICATORS for child in node.children)

    def is_empty_body(self, node) -> bool:
        block = self.get_handler_body(node)
        if block is None:
            return False
        significant = [c for c in block.children if c.type not in ("comment", "newline")]
        if len(significant) != 1:
            return False
        stmt = significant[0]
        if stmt.type == "pass_statement":
            return True
        if stmt.type == "expression_statement":
            return any(child.type == "ellipsis" for child in stmt.children)
        return False

    def get_handler_body(self, node):
        for child in node.children:
            if child.type == "block":
                return child
        return None

    def get_caught_type_text(self, node, source: bytes) -> str | None:
        for child in node.children:
            if child.type == "identifier" and ast_utils.get_node_text(child, source) in self.broad_exception_types:
                return ast_utils.get_node_text(child, source)
        return None

    def has_broad_catch_concept(self) -> bool:
        return True


_PY_NAMING_PARAM_NODE_TYPES = ("identifier", "default_parameter", "typed_parameter",
                               "typed_default_parameter", "list_splat_pattern", "dictionary_splat_pattern")


def _extract_param_name_python(child, source: bytes) -> str | None:
    if child.type == "identifier":
        return ast_utils.get_node_text(child, source)
    if child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
        name_child = child.child_by_field_name("name") or (child.children[0] if child.children else None)
        return ast_utils.get_node_text(name_child, source) if name_child else None
    if child.type in ("list_splat_pattern", "dictionary_splat_pattern"):
        for sub in child.children:
            if sub.type == "identifier":
                return ast_utils.get_node_text(sub, source)
    return None


class PythonNamingRules:
    skip_param_names = frozenset({"self", "cls"})
    param_node_types = _PY_NAMING_PARAM_NODE_TYPES

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        if DUNDER.match(name):
            return True, ""
        if name.startswith("_"):
            name_check = name.lstrip("_")
            if not name_check:
                return True, ""
            name = name_check
        if context == "class":
            if PASCAL_CASE.match(name):
                return True, ""
            return False, f"class '{name}' should be PascalCase"
        if context == "constant":
            return True, ""
        if SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
            return True, ""
        return False, f"'{name}' should be snake_case"

    def func_context(self, node) -> str:
        return "function"

    def extract_param_name(self, node, source: bytes) -> str | None:
        return _extract_param_name_python(node, source)

    def check_variable_names(self, func, source: bytes, seen: set[str]) -> tuple[int, int, list]:
        from codesieve.models import Finding
        body = func.node.child_by_field_name("body")
        if not body:
            return 0, 0, []

        total = 0
        violations = 0
        findings: list[Finding] = []

        for node in ast_utils.walk_within_scope(body):
            if node.type != "assignment":
                continue
            left = node.child_by_field_name("left")
            if not left or left.type != "identifier":
                continue
            name = ast_utils.get_node_text(left, source)
            if name in seen:
                continue
            seen.add(name)
            total += 1
            line = node.start_point[0] + 1

            valid, reason = self.validate_name(name, "variable")
            if not valid:
                violations += 1
                findings.append(Finding(message=reason, line=line, function=func.name, severity="warning"))
            elif len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
                violations += 1
                findings.append(Finding(
                    message=f"abbreviated variable '{name}' in {func.name}()",
                    line=line, function=func.name, severity="info",
                ))

        return total, violations, findings


_pack = LanguagePack(
    guard_clauses=PythonGuardClauseRules(),
    magic_numbers=PythonMagicNumberRules(),
    type_hints=PythonTypeHintRules(),
    error_handling=PythonErrorHandlingRules(),
    naming=PythonNamingRules(),
)

register_lang_pack("python", _pack)
