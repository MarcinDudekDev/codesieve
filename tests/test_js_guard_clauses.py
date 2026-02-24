"""Tests for the GuardClauses sieve on JavaScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.guard_clauses import GuardClausesSieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_guard_clauses():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score == 10.0, f"Good JS should have no guard clause issues, got {result.score}"


def test_bad_js_guard_clauses():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad JS should flag guard clause issues, got {result.score}"
    assert len(result.findings) >= 1, "Should flag at least one function needing guard clause"
