"""KISS sieve — measures cyclomatic complexity, method length, and parameter count."""

from __future__ import annotations

from codesieve.models import Finding
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MIN, SCORE_MAX, normalize_score
from codesieve.sieves.base import BaseSieve

# Score thresholds: (upper_bound, score)
CC_THRESHOLDS = [(3, SCORE_MAX), (6, 8.0), (10, 6.0), (15, 4.0), (25, 2.0)]
LENGTH_THRESHOLDS = [(10, SCORE_MAX), (20, 8.0), (35, 6.0), (50, 4.0), (75, 2.0)]
PARAM_THRESHOLDS = [(2, SCORE_MAX), (3, 8.0), (4, 6.0), (5, 4.0), (7, 2.0)]

# Weights within KISS: 50% CC, 30% length, 20% params
CC_WEIGHT = 0.50
LENGTH_WEIGHT = 0.30
PARAM_WEIGHT = 0.20


def _score_from_thresholds(value: float, thresholds: list[tuple[int, float]]) -> float:
    """Map a value to a score using threshold table."""
    for upper, score in thresholds:
        if value <= upper:
            return score
    return SCORE_MIN


def cyclomatic_complexity(func_node, lang_map) -> int:
    """Calculate cyclomatic complexity for a function node."""
    cc = 1
    for node in ast_utils.walk_tree(func_node):
        if node.type in lang_map.branch_types:
            cc += 1
    return cc


class KissSieve(BaseSieve):
    name = "KISS"
    description = "Measures simplicity via cyclomatic complexity, method length, and parameter count"
    default_weight = 0.20

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        functions = parsed.get_functions()
        if not functions:
            return self.perfect("No functions found")

        findings: list[Finding] = []
        func_scores = []

        for func in functions:
            cc = cyclomatic_complexity(func.node, parsed.lang_map)
            cc_s = _score_from_thresholds(cc, CC_THRESHOLDS)
            len_s = _score_from_thresholds(func.line_count, LENGTH_THRESHOLDS)
            param_s = _score_from_thresholds(func.param_count, PARAM_THRESHOLDS)
            func_scores.append(cc_s * CC_WEIGHT + len_s * LENGTH_WEIGHT + param_s * PARAM_WEIGHT)

            if cc > 10:
                findings.append(Finding(message=f"{func.name}() has CC={cc}", line=func.start_line, function=func.name, severity="warning"))
            if func.line_count > 35:
                findings.append(Finding(message=f"{func.name}() is {func.line_count} lines long", line=func.start_line, function=func.name, severity="warning"))
            if func.param_count > 5:
                findings.append(Finding(message=f"{func.name}() has {func.param_count} parameters", line=func.start_line, function=func.name, severity="warning"))

        worst = min(func_scores)
        avg = sum(func_scores) / len(func_scores)
        score = worst * 0.4 + avg * 0.6

        raw_ccs = [cyclomatic_complexity(f.node, parsed.lang_map) for f in functions]
        avg_raw_cc = sum(raw_ccs) / len(raw_ccs)
        max_len = max(f.line_count for f in functions)
        summary = f"avg CC={avg_raw_cc:.1f}, max fn length={max_len}, {len(functions)} functions"

        return self.result(score, summary, findings)
