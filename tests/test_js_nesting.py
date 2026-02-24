"""Tests for the Nesting sieve on JavaScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.nesting import NestingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_nesting():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = NestingSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good JS code should score >=8, got {result.score}"


def test_bad_js_deep_nesting():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = NestingSieve().analyze(parsed)
    assert result.score <= 5.0, f"Deeply nested JS should score <=5, got {result.score}"
    assert len(result.findings) > 0, "Should flag deeply nested functions"
