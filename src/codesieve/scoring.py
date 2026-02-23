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
    "DRY": 0.15,
    "SRP": 0.15,
    "Complexity": 0.10,
    "Comments": 0.10,
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
    active_results = [r for r in results if not r.skipped]
    if not active_results:
        return 0.0

    # Redistribute skipped weights proportionally
    total_active_weight = sum(w.get(r.name, 0.0) for r in active_results)
    if total_active_weight == 0:
        # Equal weights fallback
        return round(sum(r.score for r in active_results) / len(active_results), 1)

    score = sum(r.score * (w.get(r.name, 0.0) / total_active_weight) for r in active_results)
    return normalize_score(score)
