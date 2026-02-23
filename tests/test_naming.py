"""Tests for the Naming sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.naming import NamingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_good_names():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = NamingSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7 for naming, got {result.score}"


def test_bad_code_bad_names():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = NamingSieve().analyze(parsed)
    assert result.score <= 6.0, f"Bad code should score <=6 for naming, got {result.score}"


def test_bad_code_naming_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = NamingSieve().analyze(parsed)
    # Should catch PascalCase function name, abbreviated params, etc.
    assert len(result.findings) > 0, "Bad naming should produce findings"


def test_naming_name():
    sieve = NamingSieve()
    assert sieve.name == "Naming"
    assert sieve.default_weight == 0.15
