"""Tests for the Naming sieve on TypeScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.naming import NamingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_naming():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = NamingSieve().analyze(parsed)
    assert result.score >= 9.0, f"Good TS code should score >=9, got {result.score}"


def test_bad_ts_naming():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = NamingSieve().analyze(parsed)
    assert result.score <= 5.0, f"Bad TS naming should score <=5, got {result.score}"


def test_bad_ts_naming_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = NamingSieve().analyze(parsed)
    findings_text = [f.message for f in result.findings]
    assert any("data_processor" in m for m in findings_text), "Should flag non-PascalCase class"
    assert any("Process_All" in m for m in findings_text), "Should flag non-camelCase method"
