"""Naming sieve — deterministic naming convention analysis."""

from __future__ import annotations

import re

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile, FunctionInfo
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

# Shared naming patterns
SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
DUNDER = re.compile(r"^__[a-z][a-z0-9_]*__$")

ALLOWED_SHORT = {"i", "j", "k", "n", "x", "y", "z", "e", "f", "fd", "fn", "db", "id", "ip", "ok", "os", "re", "io", "_"}
VIOLATION_SCALE = 18.0
SHORT_NAME_LIMIT = 2

# Python-specific
PY_SKIP_NAMES = ("self", "cls")
PY_PARAM_NODE_TYPES = ("identifier", "default_parameter", "typed_parameter",
                       "typed_default_parameter", "list_splat_pattern", "dictionary_splat_pattern")

# PHP-specific — magic methods like __construct, __destruct, __get, __set, etc.
PHP_MAGIC_METHODS = re.compile(r"^__[a-zA-Z]+$")
PHP_PARAM_NODE_TYPES = ("simple_parameter", "variadic_parameter")

# JS/TS-specific
JS_PARAM_NODE_TYPES = ("identifier", "assignment_pattern", "rest_pattern",
                       "object_pattern", "array_pattern")
TS_PARAM_NODE_TYPES = ("required_parameter", "optional_parameter")


# ---- Naming validators ----

def _is_valid_python_name(name: str, context: str) -> tuple[bool, str]:
    """Check if a name follows Python conventions. Returns (valid, reason)."""
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


def _is_valid_php_name(name: str, context: str) -> tuple[bool, str]:
    """Check if a name follows PHP/PSR-1/PSR-12 conventions. Returns (valid, reason).

    PSR-1 §4.1: Class constants MUST be UPPER_SNAKE_CASE
    PSR-1 §3:   Class names MUST be PascalCase (StudlyCaps)
    PSR-1 §4.3: Method names MUST be camelCase
    Standalone functions: camelCase or snake_case (PSR does not cover these)
    """
    if PHP_MAGIC_METHODS.match(name):
        return True, ""
    if context == "class":
        if PASCAL_CASE.match(name):
            return True, ""
        return False, f"class '{name}' should be PascalCase (PSR-1)"
    if context == "constant":
        if UPPER_SNAKE.match(name):
            return True, ""
        return False, f"constant '{name}' should be UPPER_SNAKE_CASE (PSR-1)"
    if context == "method":
        # PSR-1 §4.3: Method names MUST be declared in camelCase
        if CAMEL_CASE.match(name):
            return True, ""
        return False, f"method '{name}' should be camelCase (PSR-1)"
    # Standalone functions: PSR does not mandate, accept camelCase or snake_case
    if CAMEL_CASE.match(name) or SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
        return True, ""
    return False, f"'{name}' should be camelCase or snake_case"


def _is_valid_js_name(name: str, context: str) -> tuple[bool, str]:
    """Check if a name follows JS/TS conventions. Returns (valid, reason).

    Standard conventions:
    - Classes: PascalCase
    - Functions/methods: camelCase
    - Constants: UPPER_SNAKE_CASE or camelCase (both accepted)
    - Variables: camelCase or UPPER_SNAKE_CASE
    """
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
    # Functions and variables: camelCase or UPPER_SNAKE
    if CAMEL_CASE.match(name) or SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
        return True, ""
    return False, f"'{name}' should be camelCase or snake_case"


def _validate_name(name: str, context: str, language: str) -> tuple[bool, str]:
    """Dispatch to language-specific validator."""
    if language == "php":
        return _is_valid_php_name(name, context)
    if language in ("javascript", "typescript"):
        return _is_valid_js_name(name, context)
    return _is_valid_python_name(name, context)


# ---- Definition name checks ----

def _php_func_context(func_node) -> str:
    """Determine if a PHP function node is a method or standalone function."""
    if func_node.type == "method_declaration":
        return "method"
    return "function"


def _js_func_context(func_node) -> str:
    """Determine if a JS/TS function node is a method or standalone function."""
    if func_node.type == "method_definition":
        return "method"
    return "function"


def _check_definition_names(parsed: ParsedFile) -> tuple[int, int, list[Finding]]:
    """Check function and class definition names. Returns (total, violations, findings)."""
    total = 0
    violations = 0
    findings: list[Finding] = []

    for func in parsed.get_functions():
        if func.name == "<anonymous>":
            continue
        total += 1
        if parsed.language == "php":
            context = _php_func_context(func.node)
        elif parsed.language in ("javascript", "typescript"):
            context = _js_func_context(func.node)
        else:
            context = "function"
        valid, reason = _validate_name(func.name, context, parsed.language)
        if not valid:
            violations += 1
            findings.append(Finding(message=reason, line=func.start_line, function=func.name, severity="warning"))

    for cls in parsed.get_classes():
        total += 1
        valid, reason = _validate_name(cls.name, "class", parsed.language)
        if not valid:
            violations += 1
            findings.append(Finding(message=reason, line=cls.start_line, severity="warning"))

    return total, violations, findings


# ---- Parameter name extraction ----

def _extract_param_name_python(child, source: bytes) -> str | None:
    """Extract the actual parameter name from a Python parameter node."""
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


def _extract_param_name_php(child, source: bytes) -> str | None:
    """Extract parameter name from a PHP simple_parameter/variadic_parameter node."""
    name_node = child.child_by_field_name("name")
    if name_node:
        # variable_name node contains $ + name children
        for sub in name_node.children:
            if sub.type == "name":
                return ast_utils.get_node_text(sub, source)
    return None


def _extract_param_name_js(child, source: bytes) -> str | None:
    """Extract parameter name from a JS parameter node."""
    if child.type == "identifier":
        return ast_utils.get_node_text(child, source)
    if child.type == "assignment_pattern":
        # Default param: first child is the identifier
        for sub in child.children:
            if sub.type == "identifier":
                return ast_utils.get_node_text(sub, source)
    if child.type == "rest_pattern":
        for sub in child.children:
            if sub.type == "identifier":
                return ast_utils.get_node_text(sub, source)
    # object_pattern / array_pattern: destructured — skip name check
    return None


def _extract_param_name_ts(child, source: bytes) -> str | None:
    """Extract parameter name from a TS required_parameter/optional_parameter."""
    for sub in child.children:
        if sub.type == "identifier":
            return ast_utils.get_node_text(sub, source)
        if sub.type == "rest_pattern":
            for subsub in sub.children:
                if subsub.type == "identifier":
                    return ast_utils.get_node_text(subsub, source)
    return None


# ---- Parameter name checks ----

def _check_param_names(func: FunctionInfo, source: bytes, seen: set[str], language: str) -> tuple[int, int, list[Finding]]:
    """Check parameter names for abbreviations. Returns (total, violations, findings)."""
    params_node = func.node.child_by_field_name("parameters")
    if not params_node:
        return 0, 0, []

    if language == "php":
        param_types = PHP_PARAM_NODE_TYPES
        extractor = _extract_param_name_php
        skip = set()
    elif language == "javascript":
        param_types = JS_PARAM_NODE_TYPES
        extractor = _extract_param_name_js
        skip = set()
    elif language == "typescript":
        param_types = TS_PARAM_NODE_TYPES
        extractor = _extract_param_name_ts
        skip = set()
    else:
        param_types = PY_PARAM_NODE_TYPES
        extractor = _extract_param_name_python
        skip = set(PY_SKIP_NAMES)

    total = 0
    violations = 0
    findings: list[Finding] = []

    for child in params_node.children:
        if child.type not in param_types:
            continue
        name = extractor(child, source)
        if not name or name in skip or name in seen:
            continue
        seen.add(name)
        total += 1
        if len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
            violations += 1
            findings.append(Finding(
                message=f"abbreviated parameter '{name}' in {func.name}()",
                line=func.start_line, function=func.name, severity="info",
            ))

    return total, violations, findings


# ---- Variable name checks ----

def _check_variable_names_python(func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
    """Check Python variable assignment names."""
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

        valid, reason = _is_valid_python_name(name, "variable")
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


def _check_variable_names_php(func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
    """Check PHP variable assignment names."""
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
        # Extract the name from variable_name (skip $)
        name = None
        for sub in left.children:
            if sub.type == "name":
                name = ast_utils.get_node_text(sub, source)
                break
        if not name or name in seen:
            continue
        # Skip $this
        if name == "this":
            continue
        seen.add(name)
        total += 1
        line = node.start_point[0] + 1

        if len(name) <= SHORT_NAME_LIMIT and name not in ALLOWED_SHORT:
            violations += 1
            findings.append(Finding(
                message=f"abbreviated variable '${name}' in {func.name}()",
                line=line, function=func.name, severity="info",
            ))

    return total, violations, findings


def _check_variable_names_js(func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
    """Check JS/TS variable names (assignments and declarations within function body)."""
    body = func.node.child_by_field_name("body")
    if not body:
        return 0, 0, []

    total = 0
    violations = 0
    findings: list[Finding] = []

    for node in ast_utils.walk_within_scope(body):
        # assignment_expression: foo = bar
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
        # variable_declarator: let/const/var x = ...
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


class NamingSieve(BaseSieve):
    name = "Naming"
    description = "Checks naming convention compliance and abbreviation usage"
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        total_names, violations, findings = _check_definition_names(parsed)

        for func in parsed.get_functions():
            seen_in_func: set[str] = set()

            count, viols, new_findings = _check_param_names(func, parsed.source, seen_in_func, parsed.language)
            total_names += count
            violations += viols
            findings.extend(new_findings)

            if parsed.language == "php":
                var_checker = _check_variable_names_php
            elif parsed.language in ("javascript", "typescript"):
                var_checker = _check_variable_names_js
            else:
                var_checker = _check_variable_names_python
            count, viols, new_findings = var_checker(func, parsed.source, seen_in_func)
            total_names += count
            violations += viols
            findings.extend(new_findings)

        if total_names == 0:
            return self.perfect("No names to check")

        violation_ratio = violations / total_names
        score = SCORE_MAX - violation_ratio * VIOLATION_SCALE
        summary = f"{violations} violations in {total_names} names ({violation_ratio:.0%})"

        return self.result(score, summary, findings)
