"""KISS sieve — measures cyclomatic complexity, method length, and parameter count."""

from __future__ import annotations

from codesieve.models import SieveResult, SieveType, Finding
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.sieves.base import BaseSieve

# Score thresholds: (upper_bound, score)
CC_THRESHOLDS = [(3, 10.0), (6, 8.0), (10, 6.0), (15, 4.0), (25, 2.0)]
LENGTH_THRESHOLDS = [(10, 10.0), (20, 8.0), (35, 6.0), (50, 4.0), (75, 2.0)]
PARAM_THRESHOLDS = [(2, 10.0), (3, 8.0), (4, 6.0), (5, 4.0), (7, 2.0)]

# Weights within KISS: 50% CC, 30% length, 20% params
CC_WEIGHT = 0.50
LENGTH_WEIGHT = 0.30
PARAM_WEIGHT = 0.20


def _score_from_thresholds(value: float, thresholds: list[tuple[int, float]]) -> float:
    """Map a value to a score using threshold table. Returns 1.0 for values above all thresholds."""
    for upper, score in thresholds:
        if value <= upper:
            return score
    return 1.0


def cyclomatic_complexity(func_node, lang_map) -> int:
    """Calculate cyclomatic complexity for a function node.
    CC = 1 + number of branch points within the function.
    """
    cc = 1
    for node in ast_utils.walk_tree(func_node):
        if node.type in lang_map.branch_types:
            cc += 1
    return cc


class KissSieve(BaseSieve):
    name = "KISS"
    description = "Measures simplicity via cyclomatic complexity, method length, and parameter count"
    sieve_type = SieveType.DETERMINISTIC
    default_weight = 0.20

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
        cc_scores = []
        len_scores = []
        param_scores = []

        for func in functions:
            cc = cyclomatic_complexity(func.node, parsed.lang_map)
            cc_score = _score_from_thresholds(cc, CC_THRESHOLDS)
            cc_scores.append(cc_score)

            len_score = _score_from_thresholds(func.line_count, LENGTH_THRESHOLDS)
            len_scores.append(len_score)

            param_score = _score_from_thresholds(func.param_count, PARAM_THRESHOLDS)
            param_scores.append(param_score)

            if cc > 10:
                findings.append(Finding(
                    message=f"{func.name}() has CC={cc}",
                    line=func.start_line,
                    function=func.name,
                    severity="warning",
                ))
            if func.line_count > 35:
                findings.append(Finding(
                    message=f"{func.name}() is {func.line_count} lines long",
                    line=func.start_line,
                    function=func.name,
                    severity="warning",
                ))
            if func.param_count > 5:
                findings.append(Finding(
                    message=f"{func.name}() has {func.param_count} parameters",
                    line=func.start_line,
                    function=func.name,
                    severity="warning",
                ))

        # Per-function composite scores, then blend worst (40%) with average (60%)
        func_scores = []
        for cc_s, len_s, param_s in zip(cc_scores, len_scores, param_scores):
            func_scores.append(cc_s * CC_WEIGHT + len_s * LENGTH_WEIGHT + param_s * PARAM_WEIGHT)

        worst = min(func_scores)
        avg = sum(func_scores) / len(func_scores)
        score = round(worst * 0.4 + avg * 0.6, 1)
        score = max(1.0, min(10.0, score))

        # Build summary
        raw_ccs = [cyclomatic_complexity(f.node, parsed.lang_map) for f in functions]
        avg_raw_cc = sum(raw_ccs) / len(raw_ccs)
        max_len = max(f.line_count for f in functions)
        summary = f"avg CC={avg_raw_cc:.1f}, max fn length={max_len}, {len(functions)} functions"

        return SieveResult(
            name=self.name,
            score=score,
            sieve_type=self.sieve_type,
            summary=summary,
            findings=findings,
        )
