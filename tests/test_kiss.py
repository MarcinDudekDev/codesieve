"""Tests for the KISS sieve."""

import os
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.kiss import KissSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_scores_high():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = KissSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"
    assert not result.skipped


def test_bad_code_scores_low():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = KissSieve().analyze(parsed)
    assert result.score <= 6.0, f"Bad code should score <=6, got {result.score}"


def test_bad_code_has_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = KissSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad code should have findings"


def test_kiss_name():
    sieve = KissSieve()
    assert sieve.name == "KISS"
    assert sieve.default_weight == 0.20
