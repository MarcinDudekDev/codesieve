"""Comments sieve — measures docstring/JSDoc coverage on named functions."""

from __future__ import annotations

from codesieve.langs import get_lang_pack
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import SCORE_MIN, SCORE_RANGE
from codesieve.sieves.base import BaseSieve


class CommentsSieve(BaseSieve):
    name = "Comments"
    description = "Measures docstring/JSDoc coverage on named functions"
    default_weight = 0.10

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        pack = get_lang_pack(parsed.language)
        rules = pack.comments if pack else None

        if rules is None or not rules.supported:
            reason = rules.skip_reason if rules else f"Comments not applicable for {parsed.language.title()}"
            return self.skip(reason)

        named = [f for f in parsed.get_functions() if f.name != "<anonymous>"]
        if not named:
            return self.perfect("No named functions found")

        findings: list[Finding] = []
        documented = 0

        for func in named:
            if rules.has_docstring(func.node, parsed.source):
                documented += 1
            else:
                findings.append(Finding(
                    message=f"{func.name}() missing docstring",
                    line=func.start_line, function=func.name, severity="info",
                ))

        total = len(named)
        coverage = documented / total
        score = SCORE_MIN + SCORE_RANGE * coverage
        summary = f"{coverage:.0%} docstring coverage ({documented}/{total} functions)"
        return self.result(score, summary, findings)
