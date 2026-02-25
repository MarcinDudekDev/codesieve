"""Naming sieve — deterministic naming convention analysis."""

from __future__ import annotations

from codesieve.langs import get_lang_pack
from codesieve.langs._patterns import ALLOWED_SHORT, SHORT_NAME_LIMIT
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile, FunctionInfo
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

VIOLATION_SCALE = 18.0


def _check_definition_names(parsed: ParsedFile, rules) -> tuple[int, int, list[Finding]]:
    """Check function and class definition names."""
    total = 0
    violations = 0
    findings: list[Finding] = []

    for func in parsed.get_functions():
        if func.name == "<anonymous>":
            continue
        total += 1
        context = rules.func_context(func.node)
        valid, reason = rules.validate_name(func.name, context)
        if not valid:
            violations += 1
            findings.append(Finding(message=reason, line=func.start_line, function=func.name, severity="warning"))

    for cls in parsed.get_classes():
        total += 1
        valid, reason = rules.validate_name(cls.name, "class")
        if not valid:
            violations += 1
            findings.append(Finding(message=reason, line=cls.start_line, severity="warning"))

    return total, violations, findings


def _check_param_names(func: FunctionInfo, source: bytes, seen: set[str], rules) -> tuple[int, int, list[Finding]]:
    """Check parameter names for abbreviations."""
    params_node = func.node.child_by_field_name("parameters")
    if not params_node:
        return 0, 0, []

    total = 0
    violations = 0
    findings: list[Finding] = []

    for child in params_node.children:
        if child.type not in rules.param_node_types:
            continue
        name = rules.extract_param_name(child, source)
        if not name or name in rules.skip_param_names or name in seen:
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


class NamingSieve(BaseSieve):
    name = "Naming"
    description = "Checks naming convention compliance and abbreviation usage"
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        pack = get_lang_pack(parsed.language)
        rules = pack.naming if pack else None
        if rules is None:
            return self.skip("No naming rules for this language")

        total_names, violations, findings = _check_definition_names(parsed, rules)

        for func in parsed.get_functions():
            seen_in_func: set[str] = set()

            count, viols, new_findings = _check_param_names(func, parsed.source, seen_in_func, rules)
            total_names += count
            violations += viols
            findings.extend(new_findings)

            count, viols, new_findings = rules.check_variable_names(func, parsed.source, seen_in_func)
            total_names += count
            violations += viols
            findings.extend(new_findings)

        if total_names == 0:
            return self.perfect("No names to check")

        violation_ratio = violations / total_names
        score = SCORE_MAX - violation_ratio * VIOLATION_SCALE
        summary = f"{violations} violations in {total_names} names ({violation_ratio:.0%})"

        return self.result(score, summary, findings)
