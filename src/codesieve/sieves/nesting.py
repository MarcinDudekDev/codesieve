"""Nesting sieve — measures max and average nesting depth of control flow."""

from __future__ import annotations

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MIN, SCORE_MAX
from codesieve.sieves.base import BaseSieve

# Score thresholds: (depth, score) — 60% worst, 40% average
DEPTH_SCORES = {0: SCORE_MAX, 1: SCORE_MAX, 2: 9.0, 3: 7.0, 4: 6.0, 5: 4.0, 6: 3.0, 7: 2.0}

WORST_WEIGHT = 0.60
AVG_WEIGHT = 0.40


def _depth_to_score(depth: int) -> float:
    """Convert a nesting depth to a score."""
    if depth in DEPTH_SCORES:
        return DEPTH_SCORES[depth]
    return SCORE_MIN if depth >= 8 else SCORE_MAX


class NestingSieve(BaseSieve):
    name = "Nesting"
    description = "Measures max and average nesting depth of control flow"
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        findings: list[Finding] = []
        max_depths: list[int] = []

        for func in functions:
            depth = ast_utils.max_nesting_in_subtree(func.node, parsed.lang_map.nesting_types)
            max_depths.append(depth)

            if depth >= 4:
                findings.append(Finding(
                    message=f"{func.name}() has nesting depth {depth}",
                    line=func.start_line, function=func.name,
                    severity="warning" if depth < 6 else "error",
                ))

        worst_depth = max(max_depths)
        avg_depth = sum(max_depths) / len(max_depths)
        score = _depth_to_score(worst_depth) * WORST_WEIGHT + _depth_to_score(round(avg_depth)) * AVG_WEIGHT

        worst_func = functions[max_depths.index(worst_depth)]
        summary = f"max depth={worst_depth} in {worst_func.name}(), avg depth={avg_depth:.1f}"

        return self.result(score, summary, findings)
