"""Tests for scoring utilities."""

from codesieve.models import SieveResult, SieveType, Grade
from codesieve.scoring import normalize_score, score_to_grade, weighted_average


def test_normalize_score_clamps_low():
    assert normalize_score(-5.0) == 1.0
    assert normalize_score(0.0) == 1.0


def test_normalize_score_clamps_high():
    assert normalize_score(15.0) == 10.0
    assert normalize_score(100.0) == 10.0


def test_normalize_score_in_range():
    assert normalize_score(5.5) == 5.5
    assert normalize_score(1.0) == 1.0
    assert normalize_score(10.0) == 10.0


def test_score_to_grade_boundaries():
    assert score_to_grade(10.0) == Grade.A
    assert score_to_grade(8.0) == Grade.A
    assert score_to_grade(7.9) == Grade.B
    assert score_to_grade(6.0) == Grade.B
    assert score_to_grade(5.9) == Grade.C
    assert score_to_grade(4.0) == Grade.C
    assert score_to_grade(3.9) == Grade.D
    assert score_to_grade(2.0) == Grade.D
    assert score_to_grade(1.9) == Grade.F
    assert score_to_grade(1.0) == Grade.F


def _make_result(name: str, score: float, skipped: bool = False) -> SieveResult:
    return SieveResult(
        name=name, score=score, sieve_type=SieveType.DETERMINISTIC,
        summary="test", skipped=skipped,
    )


def test_weighted_average_basic():
    results = [_make_result("KISS", 8.0), _make_result("Nesting", 6.0)]
    avg = weighted_average(results)
    assert 1.0 <= avg <= 10.0


def test_weighted_average_skipped():
    results = [
        _make_result("KISS", 8.0),
        _make_result("DeprecatedAPI", 0.0, skipped=True),
    ]
    avg = weighted_average(results)
    # Skipped sieve should not affect the score — result should be based on KISS alone
    assert avg == 8.0


def test_weighted_average_empty():
    assert weighted_average([]) == 0.0


def test_weighted_average_all_skipped():
    results = [
        _make_result("KISS", 0.0, skipped=True),
        _make_result("Nesting", 0.0, skipped=True),
    ]
    assert weighted_average(results) == 0.0
