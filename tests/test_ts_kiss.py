"""Tests for the KISS sieve on TypeScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.kiss import KissSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_kiss():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = KissSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good TS code should score >=8, got {result.score}"


def test_bad_ts_kiss():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = KissSieve().analyze(parsed)
    assert result.score <= 8.0, f"Bad TS code should score <=8, got {result.score}"
