"""Tests for the ErrorHandling sieve on TypeScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.error_handling import ErrorHandlingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_error_handling():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score >= 9.0, f"Good TS error handling should score >=9, got {result.score}"


def test_bad_ts_empty_catch():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score < 10.0, f"TS with empty catch should lose points, got {result.score}"
    assert any("empty catch" in f.message for f in result.findings), "Should flag empty catch body"
