"""Tests for the Nesting sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.nesting import NestingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_low_nesting():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = NestingSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good PHP code should score >=7, got {result.score}"
    assert not result.skipped


def test_bad_php_deep_nesting():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = NestingSieve().analyze(parsed)
    assert result.score <= 6.0, f"Bad PHP code should score <=6, got {result.score}"


def test_bad_php_nesting_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = NestingSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have nesting findings"
