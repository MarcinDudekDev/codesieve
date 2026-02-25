"""PHP language pack — rules for all sieves."""

from __future__ import annotations

import re

import tree_sitter

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs._patterns import SNAKE_CASE, UPPER_SNAKE, PASCAL_CASE, CAMEL_CASE, ALLOWED_SHORT, SHORT_NAME_LIMIT
from codesieve.models import Finding
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import FunctionInfo, ParsedFile

PHP_MAGIC_METHODS = re.compile(r"^__[a-zA-Z]+$")


class PHPGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node: tree_sitter.Node) -> bool:
        return any(child.type in ("else_if_clause", "else_clause") for child in if_node.children)


def _php_upper_snake_var(node: tree_sitter.Node, source: bytes) -> bool:
    """Check if a PHP variable_name node has an UPPER_SNAKE name child."""
    for sub in node.children:
        if sub.type == "name":
            return bool(UPPER_SNAKE.match(ast_utils.get_node_text(sub, source)))
    return False


class PHPMagicNumberRules:
    def is_default_param(self, node: tree_sitter.Node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("simple_parameter", "variadic_parameter"):
                return True
            if parent.type in ("function_definition", "method_declaration",
                               "anonymous_function", "class_declaration"):
                break
            parent = parent.parent
        return False

    def is_constant_assignment(self, node: tree_sitter.Node, source: bytes) -> bool:
        parent = node.parent
        if parent and parent.type == "unary_op_expression":
            parent = parent.parent
        if not parent:
            return False
        if parent.type == "const_element":
            return True
        if parent.type != "assignment_expression":
            return False
        left = parent.child_by_field_name("left")
        return left is not None and left.type == "variable_name" and _php_upper_snake_var(left, source)

    def is_negated(self, node: tree_sitter.Node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "unary_op_expression"
            and any(
                c.type == "-" or (c.type == "operator" and ast_utils.get_node_text(c, b"-") == "-")
                for c in parent.children
            )
        )


_PHP_PARAM_TYPES = ("simple_parameter", "variadic_parameter")
_STRICT_TYPES_PENALTY = 1.5


def _get_param_name_php(child: tree_sitter.Node, source: bytes) -> str | None:
    name_node = child.child_by_field_name("name")
    if name_node:
        for sub in name_node.children:
            if sub.type == "name":
                return ast_utils.get_node_text(sub, source)
    return None


def _is_strict_types_directive(directive: tree_sitter.Node, source: bytes) -> bool:
    """Check if a declare_directive is strict_types=1."""
    has_strict = False
    has_one = False
    for part in directive.children:
        if part.type == "strict_types":
            has_strict = True
        if part.type == "integer" and ast_utils.get_node_text(part, source) == "1":
            has_one = True
    return has_strict and has_one


def _has_strict_types(parsed: ParsedFile) -> bool:
    """Check if a PHP file has declare(strict_types=1) at the top."""
    for child in parsed.root.children:
        if child.type != "declare_statement":
            continue
        for sub in child.children:
            if sub.type == "declare_directive" and _is_strict_types_directive(sub, parsed.source):
                return True
    return False


class PHPTypeHintRules:
    supported = True
    skip_reason = ""

    def check_params(self, func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
        params_node = func.node.child_by_field_name("parameters")
        if params_node is None:
            return 0, 0, []

        total = 0
        annotated = 0
        findings: list[Finding] = []

        for child in params_node.children:
            if child.type not in _PHP_PARAM_TYPES:
                continue
            name = _get_param_name_php(child, source)
            if name is None:
                continue
            total += 1
            if child.child_by_field_name("type"):
                annotated += 1
            else:
                prefix = "..." if child.type == "variadic_parameter" else ""
                findings.append(Finding(
                    message=f"parameter '${prefix}{name}' in {func.name}() missing type declaration",
                    line=func.start_line, function=func.name, severity="info",
                ))

        return total, annotated, findings

    def check_extras(self, parsed: ParsedFile) -> tuple[float, str, list[Finding]]:
        if _has_strict_types(parsed):
            return 0.0, "", []
        return _STRICT_TYPES_PENALTY, ", missing strict_types", [Finding(
            message="missing declare(strict_types=1) — PSR-12 §2.1",
            line=1, severity="warning",
        )]


class PHPErrorHandlingRules:
    handler_node_type = "catch_clause"
    broad_exception_types = frozenset({"Exception", "\\Exception", "Throwable", "\\Throwable"})
    raise_types = ("throw_expression", "throw_statement")
    raise_skip_types = ("function_definition", "method_declaration", "anonymous_function",
                        "arrow_function", "catch_clause")

    def is_bare_handler(self, node: tree_sitter.Node) -> bool:
        return False  # PHP catch clauses always require a type

    def is_empty_body(self, node: tree_sitter.Node) -> bool:
        body = self.get_handler_body(node)
        if body is None:
            return False
        significant = [c for c in body.children if c.type not in ("comment", "{", "}", "php_tag")]
        return len(significant) == 0

    def get_handler_body(self, node: tree_sitter.Node) -> tree_sitter.Node | None:
        return node.child_by_field_name("body")

    def get_caught_type_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        type_node = node.child_by_field_name("type")
        if type_node:
            return ast_utils.get_node_text(type_node, source)
        return None

    def has_broad_catch_concept(self) -> bool:
        return True


class PHPDeprecatedAPIRules:
    supported = True
    skip_reason = ""
    call_node_type = "function_call_expression"
    deprecated_db: dict[str, tuple[str, str, str]] = {
        # Removed in PHP 7 — mysql_* extension
        "mysql_connect": ("PDO or mysqli_connect()", "removed", "7.0"),
        "mysql_query": ("PDO::query() or mysqli_query()", "removed", "7.0"),
        "mysql_fetch_array": ("PDO::fetch() or mysqli_fetch_array()", "removed", "7.0"),
        "mysql_fetch_assoc": ("PDO::fetch(PDO::FETCH_ASSOC)", "removed", "7.0"),
        "mysql_fetch_row": ("PDO::fetch(PDO::FETCH_NUM)", "removed", "7.0"),
        "mysql_close": ("PDO = null or mysqli_close()", "removed", "7.0"),
        "mysql_select_db": ("PDO DSN or mysqli_select_db()", "removed", "7.0"),
        "mysql_real_escape_string": ("PDO prepared statements", "removed", "7.0"),
        "mysql_num_rows": ("PDOStatement::rowCount()", "removed", "7.0"),
        "mysql_error": ("PDO::errorInfo() or mysqli_error()", "removed", "7.0"),
        # Removed in PHP 7 — POSIX regex
        "ereg": ("preg_match()", "removed", "7.0"),
        "eregi": ("preg_match() with 'i' flag", "removed", "7.0"),
        "ereg_replace": ("preg_replace()", "removed", "7.0"),
        "eregi_replace": ("preg_replace() with 'i' flag", "removed", "7.0"),
        "split": ("preg_split() or explode()", "removed", "7.0"),
        "spliti": ("preg_split() with 'i' flag", "removed", "7.0"),
        # Removed in PHP 8.0
        "each": ("foreach loop", "removed", "8.0"),
        "create_function": ("anonymous function (closure)", "removed", "8.0"),
        "money_format": ("NumberFormatter::formatCurrency()", "removed", "8.0"),
        "restore_include_path": ("ini_restore('include_path')", "removed", "8.0"),
        # Deprecated in PHP 8.1
        "strftime": ("IntlDateFormatter::format()", "deprecated", "8.1"),
        "gmstrftime": ("IntlDateFormatter::format() with UTC", "deprecated", "8.1"),
        # Deprecated in PHP 8.2
        "utf8_encode": ("mb_convert_encoding($s, 'UTF-8', 'ISO-8859-1')", "deprecated", "8.2"),
        "utf8_decode": ("mb_convert_encoding($s, 'ISO-8859-1', 'UTF-8')", "deprecated", "8.2"),
    }

    def extract_call_name(self, node: tree_sitter.Node, source: bytes) -> str | None:
        func_name_node = node.child_by_field_name("function")
        if not func_name_node or func_name_node.type != "name":
            return None
        return ast_utils.get_node_text(func_name_node, source)


_PHP_NAMING_PARAM_NODE_TYPES = ("simple_parameter", "variadic_parameter")


def _extract_php_var_name(left: tree_sitter.Node, source: bytes) -> str | None:
    """Extract the name from a PHP variable_name node (skip $)."""
    for sub in left.children:
        if sub.type == "name":
            return ast_utils.get_node_text(sub, source)
    return None


class PHPNamingRules:
    skip_param_names: frozenset[str] = frozenset()
    param_node_types = _PHP_NAMING_PARAM_NODE_TYPES

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        if PHP_MAGIC_METHODS.match(name):
            return True, ""
        if context == "class":
            return (True, "") if PASCAL_CASE.match(name) else (False, f"class '{name}' should be PascalCase (PSR-1)")
        if context == "constant":
            return (True, "") if UPPER_SNAKE.match(name) else (False, f"constant '{name}' should be UPPER_SNAKE_CASE (PSR-1)")
        if context == "method":
            return (True, "") if CAMEL_CASE.match(name) else (False, f"method '{name}' should be camelCase (PSR-1)")
        if CAMEL_CASE.match(name) or SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
            return True, ""
        return False, f"'{name}' should be camelCase or snake_case"

    def func_context(self, node: tree_sitter.Node) -> str:
        return "method" if node.type == "method_declaration" else "function"

    def extract_param_name(self, node: tree_sitter.Node, source: bytes) -> str | None:
        name_node = node.child_by_field_name("name")
        if name_node:
            for sub in name_node.children:
                if sub.type == "name":
                    return ast_utils.get_node_text(sub, source)
        return None

    def check_variable_names(self, func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
        body = func.node.child_by_field_name("body")
        if not body:
            return 0, 0, []

        total = 0
        violations = 0
        findings: list[Finding] = []

        for node in ast_utils.walk_within_scope(body):
            if node.type != "assignment_expression":
                continue
            left = node.child_by_field_name("left")
            if not left or left.type != "variable_name":
                continue
            name = _extract_php_var_name(left, source)
            if not name or name in seen or name == "this":
                continue
            seen.add(name)
            total += 1
            if len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
                violations += 1
                findings.append(Finding(
                    message=f"abbreviated variable '${name}' in {func.name}()",
                    line=node.start_point[0] + 1, function=func.name, severity="info",
                ))

        return total, violations, findings


_pack = LanguagePack(
    guard_clauses=PHPGuardClauseRules(),
    magic_numbers=PHPMagicNumberRules(),
    type_hints=PHPTypeHintRules(),
    error_handling=PHPErrorHandlingRules(),
    naming=PHPNamingRules(),
    deprecated_api=PHPDeprecatedAPIRules(),
)

register_lang_pack("php", _pack)
