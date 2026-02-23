"""Nesting sieve — measures max and average nesting depth of control flow."""

from __future__ import annotations

from codesieve.models import SieveResult, SieveType, Finding
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.sieves.base import BaseSieve

# Score thresholds: (depth, score) — 60% worst, 40% average
DEPTH_SCORES = {0: 10.0, 1: 10.0, 2: 9.0, 3: 7.0, 4: 6.0, 5: 4.0, 6: 3.0, 7: 2.0}

WORST_WEIGHT = 0.60
AVG_WEIGHT = 0.40


def _depth_to_score(depth: int) -> float:
    """Convert a nesting depth to a score."""
    if depth in DEPTH_SCORES:
        return DEPTH_SCORES[depth]
    if depth >= 8:
        return 1.0
    return 10.0


class NestingSieve(BaseSieve):
    name = "Nesting"
    description = "Measures max and average nesting depth of control flow"
    sieve_type = SieveType.DETERMINISTIC
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return SieveResult(
                name=self.name,
                score=10.0,
                sieve_type=self.sieve_type,
                summary="No functions found",
            )

        findings: list[Finding] = []
        max_depths: list[int] = []

        for func in functions:
            depth = ast_utils.max_nesting_in_subtree(func.node, parsed.lang_map.nesting_types)
            max_depths.append(depth)

            if depth >= 4:
                findings.append(Finding(
                    message=f"{func.name}() has nesting depth {depth}",
                    line=func.start_line,
                    function=func.name,
                    severity="warning" if depth < 6 else "error",
                ))

        worst_depth = max(max_depths)
        avg_depth = sum(max_depths) / len(max_depths)

        worst_score = _depth_to_score(worst_depth)
        avg_score = _depth_to_score(round(avg_depth))

        score = round(worst_score * WORST_WEIGHT + avg_score * AVG_WEIGHT, 1)
        score = max(1.0, min(10.0, score))

        # Find the function with worst nesting
        worst_func = functions[max_depths.index(worst_depth)]
        summary = f"max depth={worst_depth} in {worst_func.name}(), avg depth={avg_depth:.1f}"

        return SieveResult(
            name=self.name,
            score=score,
            sieve_type=self.sieve_type,
            summary=summary,
            findings=findings,
        )
