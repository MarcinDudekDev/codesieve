"""Tests for the MagicNumbers sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.magic_numbers import MagicNumbersSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_no_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"


def test_bad_code_has_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score <= 7.0, f"Bad code should score <=7 for magic numbers, got {result.score}"


def test_bad_code_magic_number_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = MagicNumbersSieve().analyze(parsed)
    assert len(result.findings) > 0, "Magic numbers should produce findings"


def test_magic_numbers_name():
    sieve = MagicNumbersSieve()
    assert sieve.name == "MagicNumbers"
    assert sieve.default_weight == 0.05
