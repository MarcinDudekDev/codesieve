"""Tests for the KISS sieve on JavaScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.kiss import KissSieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_kiss():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = KissSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good JS code should score >=8, got {result.score}"


def test_bad_js_kiss():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = KissSieve().analyze(parsed)
    assert result.score <= 8.0, f"Bad JS code should score <=8, got {result.score}"


def test_bad_js_has_kiss_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = KissSieve().analyze(parsed)
    # Bad code has deep functions and many params
    assert len(result.findings) > 0 or result.score < 10.0
