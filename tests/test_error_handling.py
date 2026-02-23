"""Tests for the ErrorHandling sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.error_handling import ErrorHandlingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_proper_error_handling():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"


def test_bad_code_poor_error_handling():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score <= 5.0, f"Bad code should score <=5, got {result.score}"


def test_bad_code_error_handling_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad error handling should produce findings"
    messages = [f.message for f in result.findings]
    assert any("bare except" in m for m in messages), "Should detect bare except"


def test_error_handling_name():
    sieve = ErrorHandlingSieve()
    assert sieve.name == "ErrorHandling"
    assert sieve.default_weight == 0.10
