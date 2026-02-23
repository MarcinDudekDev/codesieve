"""Naming sieve — deterministic naming convention analysis."""

from __future__ import annotations

import re

from codesieve.models import Finding
from codesieve.parser.treesitter import ParsedFile, FunctionInfo
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

# Python naming conventions
SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
DUNDER = re.compile(r"^__[a-z][a-z0-9_]*__$")

ALLOWED_SHORT = {"i", "j", "k", "n", "x", "y", "z", "e", "f", "fd", "fn", "db", "id", "ip", "ok", "os", "re", "io", "_"}
SKIP_NAMES = ("self", "cls")
VIOLATION_SCALE = 18.0
SHORT_NAME_LIMIT = 2


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


def _check_definition_names(parsed: ParsedFile) -> tuple[int, int, list[Finding]]:
    """Check function and class definition names. Returns (total, violations, findings)."""
    total = 0
    violations = 0
    findings: list[Finding] = []

    for func in parsed.get_functions():
        total += 1
        valid, reason = _is_valid_python_name(func.name, "function")
        if not valid:
            violations += 1
            findings.append(Finding(message=reason, line=func.start_line, function=func.name, severity="warning"))

    for cls in parsed.get_classes():
        total += 1
        valid, reason = _is_valid_python_name(cls.name, "class")
        if not valid:
            violations += 1
            findings.append(Finding(message=reason, line=cls.start_line, severity="warning"))

    return total, violations, findings


def _check_param_names(func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
    """Check parameter names for abbreviations. Returns (total, violations, findings)."""
    params_node = func.node.child_by_field_name("parameters")
    if not params_node:
        return 0, 0, []

    total = 0
    violations = 0
    findings: list[Finding] = []

    for child in ast_utils.walk_tree(params_node):
        if child.type != "identifier":
            continue
        name = ast_utils.get_node_text(child, source)
        if name in SKIP_NAMES or name in seen:
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


def _check_variable_names(func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
    """Check variable assignment names. Returns (total, violations, findings)."""
    body = func.node.child_by_field_name("body")
    if not body:
        return 0, 0, []

    total = 0
    violations = 0
    findings: list[Finding] = []

    for node in ast_utils.walk_tree(body):
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


class NamingSieve(BaseSieve):
    name = "Naming"
    description = "Checks naming convention compliance and abbreviation usage"
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        total_names, violations, findings = _check_definition_names(parsed)

        for func in parsed.get_functions():
            seen_in_func: set[str] = set()
            for checker in (_check_param_names, _check_variable_names):
                count, viols, new_findings = checker(func, parsed.source, seen_in_func)
                total_names += count
                violations += viols
                findings.extend(new_findings)

        if total_names == 0:
            return self.perfect("No names to check")

        violation_ratio = violations / total_names
        score = SCORE_MAX - violation_ratio * VIOLATION_SCALE
        summary = f"{violations} violations in {total_names} names ({violation_ratio:.0%})"

        return self.result(score, summary, findings)
