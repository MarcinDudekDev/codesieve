"""Tests for the ErrorHandling sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.error_handling import ErrorHandlingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_proper_error_handling():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good PHP code should score >=8, got {result.score}"
    assert not result.skipped


def test_bad_php_poor_error_handling():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score <= 8.0, f"Bad PHP code should score <=8, got {result.score}"


def test_bad_php_error_handling_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have error handling findings"
    # Should detect empty catch bodies and broad catches
    messages = " ".join(f.message for f in result.findings)
    assert "empty catch" in messages or "broad" in messages
