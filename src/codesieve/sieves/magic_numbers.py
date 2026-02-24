"""MagicNumbers sieve — detects unexplained numeric literals in function bodies."""

from __future__ import annotations

import re

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

ALLOWED_NUMBERS = {0, 1, -1, 2, 0.0, 1.0, 100, 1000}
UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PENALTY_PER_MAGIC = 0.5
NUMERIC_TYPES = ("integer", "float", "number")  # JS/TS use "number" for all numerics


def _is_default_param_python(node) -> bool:
    """Check if this numeric node is a Python default parameter value."""
    parent = node.parent
    while parent:
        if parent.type in ("default_parameter", "typed_default_parameter"):
            return True
        if parent.type in ("function_definition", "class_definition", "module"):
            break
        parent = parent.parent
    return False


def _is_default_param_php(node) -> bool:
    """Check if this numeric node is a PHP default parameter value."""
    parent = node.parent
    while parent:
        if parent.type in ("simple_parameter", "variadic_parameter"):
            return True
        if parent.type in ("function_definition", "method_declaration",
                           "anonymous_function", "class_declaration"):
            break
        parent = parent.parent
    return False


def _is_constant_assignment_python(node, source: bytes) -> bool:
    """Check if this numeric node is assigned to a Python UPPER_SNAKE variable."""
    parent = node.parent
    if parent and parent.type == "unary_operator":
        parent = parent.parent
    if parent and parent.type == "assignment":
        left = parent.child_by_field_name("left")
        if left and left.type == "identifier":
            return bool(UPPER_SNAKE.match(ast_utils.get_node_text(left, source)))
    return False


def _is_constant_assignment_php(node, source: bytes) -> bool:
    """Check if this numeric node is in a PHP const declaration or assigned to UPPER_SNAKE variable."""
    parent = node.parent
    if parent and parent.type == "unary_op_expression":
        parent = parent.parent
    # const X = 42;
    if parent and parent.type == "const_element":
        return True
    # $X = 42 where X is UPPER_SNAKE
    if parent and parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        if left and left.type == "variable_name":
            for sub in left.children:
                if sub.type == "name":
                    return bool(UPPER_SNAKE.match(ast_utils.get_node_text(sub, source)))
    return False


def _is_negated_python(node) -> bool:
    """Check if a numeric node is the operand of a Python unary minus."""
    parent = node.parent
    return (
        parent is not None
        and parent.type == "unary_operator"
        and any(c.type == "-" for c in parent.children)
    )


def _is_negated_php(node) -> bool:
    """Check if a numeric node is the operand of a PHP unary minus."""
    parent = node.parent
    return (
        parent is not None
        and parent.type == "unary_op_expression"
        and any(
            c.type == "-" or (c.type == "operator" and ast_utils.get_node_text(c, b"-") == "-")
            for c in parent.children
        )
    )


def _is_default_param_js(node) -> bool:
    """Check if this numeric node is a JS default parameter value (assignment_pattern in formal_parameters)."""
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


def _is_default_param_ts(node) -> bool:
    """Check if this numeric node is a TS default parameter value (required_parameter with value field)."""
    parent = node.parent
    while parent:
        if parent.type in ("required_parameter", "optional_parameter"):
            return True
        if parent.type in ("function_declaration", "method_definition",
                           "arrow_function", "generator_function_declaration",
                           "class_declaration"):
            break
        parent = parent.parent
    return False


def _is_constant_assignment_js(node, source: bytes) -> bool:
    """Check if this numeric node is a JS/TS const with UPPER_SNAKE name, or in a top-level const."""
    parent = node.parent
    if parent and parent.type == "unary_expression":
        parent = parent.parent
    # variable_declarator inside lexical_declaration (const)
    if parent and parent.type == "variable_declarator":
        grandparent = parent.parent
        if grandparent and grandparent.type == "lexical_declaration":
            # Check if it's a const declaration
            has_const = any(c.type == "const" for c in grandparent.children)
            if has_const:
                name_node = parent.child_by_field_name("name")
                if name_node and name_node.type == "identifier":
                    return bool(UPPER_SNAKE.match(ast_utils.get_node_text(name_node, source)))
    return False


def _is_negated_js(node) -> bool:
    """Check if a numeric node is the operand of a JS/TS unary minus."""
    parent = node.parent
    return (
        parent is not None
        and parent.type == "unary_expression"
        and any(c.type == "-" for c in parent.children)
    )


def _parse_numeric(node, source: bytes, is_negated_fn) -> float | None:
    """Parse a numeric node to its value, accounting for unary minus parent."""
    text = ast_utils.get_node_text(node, source)
    try:
        if node.type == "integer":
            value = int(text, 0)
        elif node.type == "number":
            # JS/TS "number" can be int or float
            value = float(text) if "." in text or "e" in text.lower() else int(text, 0)
        else:
            value = float(text)
    except (ValueError, OverflowError):
        return None
    if is_negated_fn(node):
        value = -value
    return value


class MagicNumbersSieve(BaseSieve):
    name = "MagicNumbers"
    description = "Detects unexplained numeric literals (magic numbers) in function bodies"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        if parsed.language == "php":
            is_default = _is_default_param_php
            is_const = _is_constant_assignment_php
            is_neg = _is_negated_php
        elif parsed.language == "javascript":
            is_default = _is_default_param_js
            is_const = _is_constant_assignment_js
            is_neg = _is_negated_js
        elif parsed.language == "typescript":
            is_default = _is_default_param_ts
            is_const = _is_constant_assignment_js  # Same const pattern for TS
            is_neg = _is_negated_js  # Same unary_expression for TS
        else:
            is_default = _is_default_param_python
            is_const = _is_constant_assignment_python
            is_neg = _is_negated_python

        findings: list[Finding] = []

        for func in functions:
            body = func.node.child_by_field_name("body")
            if not body:
                continue
            findings.extend(self._check_body(func.name, body, parsed.source, is_default, is_const, is_neg))

        magic_count = len(findings)
        score = SCORE_MAX - PENALTY_PER_MAGIC * magic_count
        summary = f"{magic_count} magic number(s) found" if magic_count else "no magic numbers"

        return self.result(score, summary, findings)

    def _check_body(self, func_name: str, body, source: bytes,
                    is_default_fn, is_const_fn, is_neg_fn) -> list[Finding]:
        """Find magic numbers in a function body."""
        results = []
        for node in ast_utils.walk_within_scope(body):
            if node.type not in NUMERIC_TYPES:
                continue
            if is_default_fn(node) or is_const_fn(node, source):
                continue
            value = _parse_numeric(node, source, is_neg_fn)
            if value is None or value in ALLOWED_NUMBERS:
                continue
            display = f"-{ast_utils.get_node_text(node, source)}" if is_neg_fn(node) else ast_utils.get_node_text(node, source)
            results.append(Finding(
                message=f"magic number {display} in {func_name}()",
                line=node.start_point[0] + 1, function=func_name, severity="info",
            ))
        return results
