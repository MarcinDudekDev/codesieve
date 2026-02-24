"""Tests for the MagicNumbers sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.magic_numbers import MagicNumbersSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_no_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good PHP code should score >=8, got {result.score}"
    assert not result.skipped


def test_bad_php_has_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score <= 7.0, f"Bad PHP code should score <=7, got {result.score}"


def test_bad_php_magic_number_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = MagicNumbersSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have magic number findings"
