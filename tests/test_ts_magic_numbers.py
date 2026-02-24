"""Tests for the MagicNumbers sieve on TypeScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.magic_numbers import MagicNumbersSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_no_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score >= 9.0, f"Good TS should have few magic numbers, got {result.score}"


def test_bad_ts_has_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score <= 3.0, f"Bad TS with magic numbers should score low, got {result.score}"
    assert len(result.findings) > 5, "Should find many magic numbers"
