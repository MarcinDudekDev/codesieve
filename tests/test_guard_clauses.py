"""Tests for the GuardClauses sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.guard_clauses import GuardClausesSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_uses_guards():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"


def test_bad_code_needs_guards():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score <= 9.0, f"Bad code should score <=9 for guard clauses, got {result.score}"


def test_bad_code_guard_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = GuardClausesSieve().analyze(parsed)
    assert len(result.findings) > 0, "Wrapped function bodies should produce findings"


def test_guard_clauses_name():
    sieve = GuardClausesSieve()
    assert sieve.name == "GuardClauses"
    assert sieve.default_weight == 0.05
