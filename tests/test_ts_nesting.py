"""Tests for the Nesting sieve on TypeScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.nesting import NestingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_nesting():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = NestingSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good TS code should score >=7, got {result.score}"


def test_bad_ts_deep_nesting():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = NestingSieve().analyze(parsed)
    assert result.score <= 5.0, f"Deeply nested TS should score <=5, got {result.score}"
    assert len(result.findings) > 0, "Should flag deeply nested functions"
