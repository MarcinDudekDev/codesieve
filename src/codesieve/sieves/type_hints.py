"""TypeHints sieve — measures type annotation coverage."""

from __future__ import annotations

from codesieve.langs import get_lang_pack
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import SCORE_MIN, SCORE_RANGE
from codesieve.sieves.base import BaseSieve


class TypeHintsSieve(BaseSieve):
    name = "TypeHints"
    description = "Measures type annotation coverage on function parameters and return types"
    default_weight = 0.08

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        pack = get_lang_pack(parsed.language)
        rules = pack.type_hints if pack else None

        if rules is None or not rules.supported:
            reason = rules.skip_reason if rules else f"TypeHints not applicable for {parsed.language.title()}"
            return self.skip(reason)

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

            params_total, params_ann, params_findings = rules.check_params(func, parsed.source)
            total_params += params_total
            annotated_params += params_ann
            findings.extend(params_findings)

        total_functions = len(functions)
        denominator = total_params + total_functions
        coverage = (annotated_params + annotated_returns) / denominator if denominator else 1.0

        score = SCORE_MIN + SCORE_RANGE * coverage

        # Language-specific extras (e.g. PHP strict_types penalty)
        extra_penalty, extra_note, extra_findings = rules.check_extras(parsed)
        if extra_penalty:
            score -= extra_penalty
            findings[:0] = extra_findings  # prepend

        summary = f"{coverage:.0%} type coverage ({annotated_params}/{total_params} params, {annotated_returns}/{total_functions} returns){extra_note}"

        return self.result(score, summary, findings)
