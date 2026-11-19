"""Weighted average scoring and grade mapping."""

from __future__ import annotations

from codesieve.models import SieveResult, Grade

# Score bounds — all sieves normalize to this range
SCORE_MIN = 1.0
SCORE_MAX = 10.0
SCORE_RANGE = SCORE_MAX - SCORE_MIN  # 9.0


def normalize_score(raw: float) -> float:
    """Clamp and round a raw score to the valid range."""
    return round(max(SCORE_MIN, min(SCORE_MAX, raw)), 1)


# Default sieve weights
DEFAULT_WEIGHTS: dict[str, float] = {
    "KISS": 0.20,
    "Nesting": 0.15,
    "Naming": 0.15,
    "ErrorHandling": 0.10,
    "TypeHints": 0.08,
    "MagicNumbers": 0.05,
    "GuardClauses": 0.05,
    "DeprecatedAPI": 0.05,
    "DRY": 0.15,
    "Comments": 0.10,
    "NoSilencing": 0.05,
}


def score_to_grade(score: float) -> Grade:
    """Convert a numeric score (1-10) to a letter grade."""
    if score >= 8.0:
        return Grade.A
    if score >= 6.0:
        return Grade.B
    if score >= 4.0:
        return Grade.C
    if score >= 2.0:
        return Grade.D
    return Grade.F


def weighted_average(results: list[SieveResult], weights: dict[str, float] | None = None) -> float:
    """Calculate weighted average score, redistributing skipped sieve weights."""
    if not results:
        return 0.0

    w = weights or DEFAULT_WEIGHTS
    # A weight of 0 means "not graded" (README: weight-0 sieves are skipped), so
    # such a result stays out of the average entirely. Letting it in through the
    # equal-weights fallback scored a file 10.0/A when every selected sieve —
    # empty code, no findings — happened to weigh 0.
    active_results = [r for r in results if not r.skipped and w.get(r.name, 0.0) > 0]
    if not active_results:
        return 0.0

    # Redistribute skipped weights proportionally
    total_active_weight = sum(w[r.name] for r in active_results)
    score = sum(r.score * (w[r.name] / total_active_weight) for r in active_results)
    return normalize_score(score)
