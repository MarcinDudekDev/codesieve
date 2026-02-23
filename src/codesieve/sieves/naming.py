"""Naming sieve — deterministic naming convention analysis."""

from __future__ import annotations

import re

from codesieve.models import SieveResult, SieveType, Finding
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.sieves.base import BaseSieve

# Python naming conventions
SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
DUNDER = re.compile(r"^__[a-z][a-z0-9_]*__$")

# Common abbreviations that are OK
ALLOWED_SHORT = {"i", "j", "k", "n", "x", "y", "z", "e", "f", "fd", "fn", "db", "id", "ip", "ok", "os", "re", "io", "_"}

# Single-letter names that are bad outside loops/lambdas
SINGLE_LETTER = re.compile(r"^[a-zA-Z]$")

# Common abbreviations that should be expanded
ABBREVIATED = re.compile(r"^[a-z]{1,2}\d*$")  # very short names like 'tp', 'v1'


def _is_valid_python_name(name: str, context: str) -> tuple[bool, str]:
    """Check if a name follows Python conventions. Returns (valid, reason)."""
    if DUNDER.match(name):
        return True, ""
    if name.startswith("_"):
        name_check = name.lstrip("_")
        if not name_check:
            return True, ""  # just underscores (throwaway)
        name = name_check
    if context == "class":
        if PASCAL_CASE.match(name):
            return True, ""
        return False, f"class '{name}' should be PascalCase"
    if context == "constant":
        if UPPER_SNAKE.match(name):
            return True, ""
        # Constants are hard to detect, skip for now
        return True, ""
    # functions, variables, parameters — snake_case
    if SNAKE_CASE.match(name) or UPPER_SNAKE.match(name):
        return True, ""
    return False, f"'{name}' should be snake_case"


class NamingSieve(BaseSieve):
    name = "Naming"
    description = "Checks naming convention compliance and abbreviation usage"
    sieve_type = SieveType.DETERMINISTIC
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        findings: list[Finding] = []
        total_names = 0
        violations = 0

        # Check function names
        for func in parsed.get_functions():
            total_names += 1
            valid, reason = _is_valid_python_name(func.name, "function")
            if not valid:
                violations += 1
                findings.append(Finding(
                    message=reason,
                    line=func.start_line,
                    function=func.name,
                    severity="warning",
                ))

        # Check class names
        for cls in parsed.get_classes():
            total_names += 1
            valid, reason = _is_valid_python_name(cls.name, "class")
            if not valid:
                violations += 1
                findings.append(Finding(
                    message=reason,
                    line=cls.start_line,
                    severity="warning",
                ))

        # Check for abbreviated/single-letter names in function definitions
        seen_names: set[str] = set()
        for func in parsed.get_functions():
            # Get parameter names
            params_node = func.node.child_by_field_name("parameters")
            if params_node:
                for child in ast_utils.walk_tree(params_node):
                    if child.type == "identifier":
                        name = ast_utils.get_node_text(child, parsed.source)
                        if name not in ("self", "cls") and name not in seen_names:
                            seen_names.add(name)
                            total_names += 1
                            if len(name) <= 2 and name not in ALLOWED_SHORT:
                                violations += 1
                                findings.append(Finding(
                                    message=f"abbreviated parameter '{name}' in {func.name}()",
                                    line=func.start_line,
                                    function=func.name,
                                    severity="info",
                                ))

        # Check variable assignments in function bodies
        for func in parsed.get_functions():
            body = func.node.child_by_field_name("body")
            if not body:
                continue
            for node in ast_utils.walk_tree(body):
                if node.type == "assignment":
                    left = node.child_by_field_name("left")
                    if left and left.type == "identifier":
                        name = ast_utils.get_node_text(left, parsed.source)
                        if name not in seen_names:
                            seen_names.add(name)
                            total_names += 1
                            valid, reason = _is_valid_python_name(name, "variable")
                            if not valid:
                                violations += 1
                                findings.append(Finding(
                                    message=reason,
                                    line=node.start_point[0] + 1,
                                    function=func.name,
                                    severity="warning",
                                ))
                            elif len(name) <= 2 and name not in ALLOWED_SHORT:
                                violations += 1
                                findings.append(Finding(
                                    message=f"abbreviated variable '{name}' in {func.name}()",
                                    line=node.start_point[0] + 1,
                                    function=func.name,
                                    severity="info",
                                ))

        if total_names == 0:
            return SieveResult(
                name=self.name,
                score=10.0,
                sieve_type=self.sieve_type,
                summary="No names to check",
            )

        violation_ratio = violations / total_names
        # Score: 10 at 0%, linearly decreasing to 1 at 50%+
        score = round(max(1.0, 10.0 - (violation_ratio * 18.0)), 1)
        score = max(1.0, min(10.0, score))

        summary = f"{violations} violations in {total_names} names ({violation_ratio:.0%})"
        return SieveResult(
            name=self.name,
            score=score,
            sieve_type=self.sieve_type,
            summary=summary,
            findings=findings,
        )
