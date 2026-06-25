"""Tests for the DRY sieve's repeated-inline-expression detection (Part a)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.dry import MIN_OCCURRENCES, DrySieve

# Kept outside tests/fixtures/ so directory-scan tests' file counts stay fixed.
DRY_FIXTURES = Path(__file__).parent / "dry_fixtures"


def _file(code: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False)
    f.write(code)
    f.close()
    return f.name


def _analyze(code: str, suffix: str = ".py"):
    path = _file(code, suffix)
    try:
        return DrySieve().analyze(ParsedFile(path))
    finally:
        os.unlink(path)


# ---- Fixture-based: the real motivating case --------------------------------------------
def test_repeated_idiom_with_different_var_names_is_flagged():
    """The byte-math idiom repeated 3× with DIFFERENT variable names must be caught."""
    result = DrySieve().analyze(ParsedFile(str(DRY_FIXTURES / "dry_repeat_bad.py")))
    assert result.score < 10.0, f"Repeated idiom should score below 10, got {result.score}"
    assert len(result.findings) == 1
    msg = result.findings[0].message
    assert "repeated 3×" in msg
    assert "1024 * 1024" in msg


def test_extracted_helper_counter_fixture_is_perfect():
    """Once the idiom is factored into a named helper, calling it 3× must NOT be flagged."""
    result = DrySieve().analyze(ParsedFile(str(DRY_FIXTURES / "dry_repeat_good.py")))
    assert result.score == 10.0, f"Extracted-helper fixture should be perfect, got {result.score}"
    assert len(result.findings) == 0


# ---- Threshold / occurrence behaviour ---------------------------------------------------
def test_two_occurrences_below_threshold_not_flagged():
    code = """\
def f(a, b):
    x = round(a / (1024 * 1024), 2)
    y = round(b / (1024 * 1024), 2)
    return x, y
"""
    result = _analyze(code)
    assert result.score == 10.0
    assert MIN_OCCURRENCES == 3  # guards the fixture above against threshold drift


def test_var_name_blanking_can_be_inferred_from_collapse():
    """Three occurrences differing only by variable name collapse into ONE finding."""
    code = """\
def f(a, b, c):
    return (a * 60 + 30, b * 60 + 30, c * 60 + 30)
"""
    result = _analyze(code)
    assert len(result.findings) == 1
    assert "repeated 3×" in result.findings[0].message


# ---- Trivial-expression suppression -----------------------------------------------------
def test_trivial_increment_not_flagged():
    code = """\
def f(a, b, c):
    return a + 1, b + 1, c + 1
"""
    result = _analyze(code)
    assert result.score == 10.0, f"Trivial `x + 1` must not be flagged, got {result.score}"


def test_bare_helper_call_not_flagged():
    """A repeated call to a named helper (no inline logic) is the GOOD pattern."""
    code = """\
def f(a, b, c):
    return transform(a, b), transform(b, c), transform(a, c)
"""
    result = _analyze(code)
    assert result.score == 10.0


# ---- Nested sub-expression suppression --------------------------------------------------
def test_largest_repeated_unit_reported_not_nested_fragments():
    """`round(x/(1024*1024),2)` repeating should yield ONE finding, not also its inner parts."""
    code = """\
def f(a, b, c, d):
    return (
        round(a / (1024 * 1024), 2),
        round(b / (1024 * 1024), 2),
        round(c / (1024 * 1024), 2),
        round(d / (1024 * 1024), 2),
    )
"""
    result = _analyze(code)
    assert len(result.findings) == 1, f"Nested fragments must be suppressed, got {result.findings}"
    assert "repeated 4×" in result.findings[0].message


# ---- No double-count with duplicate bodies ----------------------------------------------
def test_expressions_inside_duplicate_bodies_are_skipped():
    """When whole bodies duplicate, only body findings fire — not their inner expressions."""
    code = """\
def alpha(x):
    total = x * (1024 * 1024)
    scaled = total + 512
    return scaled

def beta(x):
    total = x * (1024 * 1024)
    scaled = total + 512
    return scaled

def gamma(x):
    total = x * (1024 * 1024)
    scaled = total + 512
    return scaled
"""
    result = _analyze(code)
    # Only duplicate-body findings (beta, gamma) — no separate repeated-expression findings.
    assert all("duplicates" in f.message for f in result.findings), result.findings
    assert len(result.findings) == 2


# ---- Cross-language smoke ---------------------------------------------------------------
def test_php_byte_math_idiom_flagged():
    code = """<?php
function report($a, $b, $c) {
    $x = round($a / (1024 * 1024), 2) . ' MB';
    $y = round($b / (1024 * 1024), 2) . ' MB';
    $z = round($c / (1024 * 1024), 2) . ' MB';
    return [$x, $y, $z];
}
"""
    result = _analyze(code, suffix=".php")
    repeated = [f for f in result.findings if "repeated" in f.message]
    assert len(repeated) == 1
    assert "repeated 3×" in repeated[0].message
