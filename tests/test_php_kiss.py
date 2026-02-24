"""Tests for the KISS sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.kiss import KissSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_scores_high():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = KissSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good PHP code should score >=7, got {result.score}"
    assert not result.skipped


def test_bad_php_scores_low():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = KissSieve().analyze(parsed)
    assert result.score <= 6.0, f"Bad PHP code should score <=6, got {result.score}"


def test_bad_php_has_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = KissSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have findings"
