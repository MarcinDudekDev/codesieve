"""Tests for the GuardClauses sieve on TypeScript code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.guard_clauses import GuardClausesSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_guard_clauses():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score == 10.0, f"Good TS should have no guard clause issues, got {result.score}"


def test_bad_ts_guard_clauses():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad TS should flag guard clause issues, got {result.score}"
    assert len(result.findings) >= 1, "Should flag at least one function needing guard clause"
