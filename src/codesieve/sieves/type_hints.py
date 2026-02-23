"""TypeHints sieve — measures type annotation coverage."""

from __future__ import annotations

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile, FunctionInfo
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MIN, SCORE_RANGE
from codesieve.sieves.base import BaseSieve

SKIP_NAMES = ("self", "cls")
TYPED_PARAM_TYPES = ("typed_parameter", "typed_default_parameter")
UNTYPED_PARAM_TYPES = ("identifier", "default_parameter")
SPLAT_TYPES = ("list_splat_pattern", "dictionary_splat_pattern")


def _get_param_name(child, source: bytes) -> str | None:
    """Extract parameter name, returning None for self/cls."""
    if child.type == "identifier":
        name = ast_utils.get_node_text(child, source)
        return None if name in SKIP_NAMES else name

    if child.type in SPLAT_TYPES:
        for sub in child.children:
            if sub.type == "identifier":
                name = ast_utils.get_node_text(sub, source)
                return None if name in SKIP_NAMES else name
        return None

    name_child = child.child_by_field_name("name") or (child.children[0] if child.children else None)
    if name_child:
        name = ast_utils.get_node_text(name_child, source)
        return None if name in SKIP_NAMES else name
    return "<unknown>"


def _check_params(func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
    """Check parameter annotations for a function. Returns (total, annotated, findings)."""
    params_node = func.node.child_by_field_name("parameters")
    if params_node is None:
        return 0, 0, []

    total = 0
    annotated = 0
    findings: list[Finding] = []

    for child in params_node.children:
        if child.type in TYPED_PARAM_TYPES:
            name = _get_param_name(child, source)
            if name is None:
                continue
            total += 1
            annotated += 1
        elif child.type in UNTYPED_PARAM_TYPES:
            name = _get_param_name(child, source)
            if name is None:
                continue
            total += 1
            findings.append(Finding(
                message=f"parameter '{name}' in {func.name}() missing type hint",
                line=func.start_line, function=func.name, severity="info",
            ))
        elif child.type in SPLAT_TYPES:
            name = _get_param_name(child, source)
            if name is None:
                continue
            total += 1
            prefix = "*" if child.type == "list_splat_pattern" else "**"
            findings.append(Finding(
                message=f"parameter '{prefix}{name}' in {func.name}() missing type hint",
                line=func.start_line, function=func.name, severity="info",
            ))

    return total, annotated, findings


class TypeHintsSieve(BaseSieve):
    name = "TypeHints"
    description = "Measures type annotation coverage on function parameters and return types"
    default_weight = 0.08

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        findings: list[Finding] = []
        total_params = 0
        annotated_params = 0
        annotated_returns = 0

        for func in functions:
            if func.node.child_by_field_name("return_type"):
                annotated_returns += 1
            else:
                findings.append(Finding(
                    message=f"{func.name}() missing return type annotation",
                    line=func.start_line, function=func.name, severity="info",
                ))

            params_total, params_ann, params_findings = _check_params(func, parsed.source)
            total_params += params_total
            annotated_params += params_ann
            findings.extend(params_findings)

        total_functions = len(functions)
        denominator = total_params + total_functions
        coverage = (annotated_params + annotated_returns) / denominator if denominator else 1.0

        score = SCORE_MIN + SCORE_RANGE * coverage
        summary = f"{coverage:.0%} type coverage ({annotated_params}/{total_params} params, {annotated_returns}/{total_functions} returns)"

        return self.result(score, summary, findings)
