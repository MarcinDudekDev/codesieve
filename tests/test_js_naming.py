"""Tests for the Naming sieve on JavaScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.naming import NamingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_naming():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = NamingSieve().analyze(parsed)
    assert result.score >= 9.0, f"Good JS code should score >=9, got {result.score}"


def test_bad_js_naming():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = NamingSieve().analyze(parsed)
    assert result.score <= 5.0, f"Bad JS naming should score <=5, got {result.score}"


def test_bad_js_naming_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = NamingSieve().analyze(parsed)
    findings_text = [f.message for f in result.findings]
    # Should flag snake_case class name
    assert any("data_processor" in m for m in findings_text), "Should flag non-PascalCase class"
    # Should flag PascalCase method
    assert any("Process_All" in m for m in findings_text), "Should flag non-camelCase method"


def test_anonymous_functions_not_flagged():
    """Arrow functions without names should not generate naming violations."""
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = NamingSieve().analyze(parsed)
    findings_text = [f.message for f in result.findings]
    assert not any("anonymous" in m for m in findings_text), "Anonymous functions should be skipped"
