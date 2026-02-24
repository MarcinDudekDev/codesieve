"""TypeHints sieve — measures type annotation coverage."""

from __future__ import annotations

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile, FunctionInfo
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MIN, SCORE_RANGE
from codesieve.sieves.base import BaseSieve

# Python param types
PY_SKIP_NAMES = ("self", "cls")
PY_TYPED_PARAM_TYPES = ("typed_parameter", "typed_default_parameter")
PY_UNTYPED_PARAM_TYPES = ("identifier", "default_parameter")
PY_SPLAT_TYPES = ("list_splat_pattern", "dictionary_splat_pattern")

# PHP param types
PHP_PARAM_TYPES = ("simple_parameter", "variadic_parameter")

# PHP strict_types penalty — PSR-12 §2.1 recommends declare(strict_types=1)
STRICT_TYPES_PENALTY = 1.5

# TS param types
TS_PARAM_TYPES = ("required_parameter", "optional_parameter")


def _get_param_name_python(child, source: bytes) -> str | None:
    """Extract Python parameter name, returning None for self/cls."""
    if child.type == "identifier":
        name = ast_utils.get_node_text(child, source)
        return None if name in PY_SKIP_NAMES else name

    if child.type in PY_SPLAT_TYPES:
        for sub in child.children:
            if sub.type == "identifier":
                name = ast_utils.get_node_text(sub, source)
                return None if name in PY_SKIP_NAMES else name
        return None

    name_child = child.child_by_field_name("name") or (child.children[0] if child.children else None)
    if name_child:
        name = ast_utils.get_node_text(name_child, source)
        return None if name in PY_SKIP_NAMES else name
    return "<unknown>"


def _check_params_python(func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
    """Check Python parameter annotations. Returns (total, annotated, findings)."""
    params_node = func.node.child_by_field_name("parameters")
    if params_node is None:
        return 0, 0, []

    total = 0
    annotated = 0
    findings: list[Finding] = []

    for child in params_node.children:
        if child.type in PY_TYPED_PARAM_TYPES:
            name = _get_param_name_python(child, source)
            if name is None:
                continue
            total += 1
            annotated += 1
        elif child.type in PY_UNTYPED_PARAM_TYPES:
            name = _get_param_name_python(child, source)
            if name is None:
                continue
            total += 1
            findings.append(Finding(
                message=f"parameter '{name}' in {func.name}() missing type hint",
                line=func.start_line, function=func.name, severity="info",
            ))
        elif child.type in PY_SPLAT_TYPES:
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


def _get_param_name_php(child, source: bytes) -> str | None:
    """Extract PHP parameter name from simple_parameter/variadic_parameter."""
    name_node = child.child_by_field_name("name")
    if name_node:
        for sub in name_node.children:
            if sub.type == "name":
                return ast_utils.get_node_text(sub, source)
    return None


def _check_params_php(func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
    """Check PHP parameter type declarations. Returns (total, annotated, findings)."""
    params_node = func.node.child_by_field_name("parameters")
    if params_node is None:
        return 0, 0, []

    total = 0
    annotated = 0
    findings: list[Finding] = []

    for child in params_node.children:
        if child.type not in PHP_PARAM_TYPES:
            continue
        name = _get_param_name_php(child, source)
        if name is None:
            continue
        total += 1
        # PHP param has type if it has a "type" field child
        if child.child_by_field_name("type"):
            annotated += 1
        else:
            prefix = "..." if child.type == "variadic_parameter" else ""
            findings.append(Finding(
                message=f"parameter '${prefix}{name}' in {func.name}() missing type declaration",
                line=func.start_line, function=func.name, severity="info",
            ))

    return total, annotated, findings


def _get_param_name_ts(child, source: bytes) -> str | None:
    """Extract TS parameter name from required_parameter/optional_parameter."""
    for sub in child.children:
        if sub.type == "identifier":
            return ast_utils.get_node_text(sub, source)
        if sub.type == "rest_pattern":
            for subsub in sub.children:
                if subsub.type == "identifier":
                    return ast_utils.get_node_text(subsub, source)
    return None


def _check_params_ts(func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
    """Check TypeScript parameter type annotations. Returns (total, annotated, findings)."""
    params_node = func.node.child_by_field_name("parameters")
    if params_node is None:
        return 0, 0, []

    total = 0
    annotated = 0
    findings: list[Finding] = []

    for child in params_node.children:
        if child.type not in TS_PARAM_TYPES:
            continue
        name = _get_param_name_ts(child, source)
        if name is None:
            continue
        total += 1
        if child.child_by_field_name("type"):
            annotated += 1
        else:
            prefix = "..." if any(sub.type == "rest_pattern" for sub in child.children) else ""
            findings.append(Finding(
                message=f"parameter '{prefix}{name}' in {func.name}() missing type annotation",
                line=func.start_line, function=func.name, severity="info",
            ))

    return total, annotated, findings


def _has_strict_types(parsed: ParsedFile) -> bool:
    """Check if a PHP file has declare(strict_types=1) at the top."""
    for child in parsed.root.children:
        if child.type == "declare_statement":
            for sub in child.children:
                if sub.type == "declare_directive":
                    has_strict = False
                    has_one = False
                    for part in sub.children:
                        if part.type == "strict_types":
                            has_strict = True
                        if part.type == "integer" and ast_utils.get_node_text(part, parsed.source) == "1":
                            has_one = True
                    if has_strict and has_one:
                        return True
    return False


class TypeHintsSieve(BaseSieve):
    name = "TypeHints"
    description = "Measures type annotation coverage on function parameters and return types"
    default_weight = 0.08

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        # JS has no native type system — skip
        if parsed.language == "javascript":
            return self.perfect("TypeHints not applicable for JavaScript")

        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        findings: list[Finding] = []
        total_params = 0
        annotated_params = 0
        annotated_returns = 0

        if parsed.language == "php":
            check_params = _check_params_php
        elif parsed.language == "typescript":
            check_params = _check_params_ts
        else:
            check_params = _check_params_python

        for func in functions:
            if func.node.child_by_field_name("return_type"):
                annotated_returns += 1
            else:
                findings.append(Finding(
                    message=f"{func.name}() missing return type annotation",
                    line=func.start_line, function=func.name, severity="info",
                ))

            params_total, params_ann, params_findings = check_params(func, parsed.source)
            total_params += params_total
            annotated_params += params_ann
            findings.extend(params_findings)

        total_functions = len(functions)
        denominator = total_params + total_functions
        coverage = (annotated_params + annotated_returns) / denominator if denominator else 1.0

        score = SCORE_MIN + SCORE_RANGE * coverage

        # PHP: penalize missing declare(strict_types=1) — PSR-12 §2.1
        strict_note = ""
        if parsed.language == "php" and not _has_strict_types(parsed):
            score -= STRICT_TYPES_PENALTY
            strict_note = ", missing strict_types"
            findings.insert(0, Finding(
                message="missing declare(strict_types=1) — PSR-12 §2.1",
                line=1, severity="warning",
            ))

        summary = f"{coverage:.0%} type coverage ({annotated_params}/{total_params} params, {annotated_returns}/{total_functions} returns){strict_note}"

        return self.result(score, summary, findings)
