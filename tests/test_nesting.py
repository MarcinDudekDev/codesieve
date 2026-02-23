"""Tests for the Nesting sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.nesting import NestingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_low_nesting():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = NestingSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"


def test_bad_code_deep_nesting():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = NestingSieve().analyze(parsed)
    assert result.score <= 4.0, f"Bad code should score <=4 for nesting, got {result.score}"


def test_bad_code_nesting_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = NestingSieve().analyze(parsed)
    assert len(result.findings) > 0, "Deep nesting should produce findings"


def test_nesting_name():
    sieve = NestingSieve()
    assert sieve.name == "Nesting"
    assert sieve.default_weight == 0.15
