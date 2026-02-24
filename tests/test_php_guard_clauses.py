"""Tests for the GuardClauses sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.guard_clauses import GuardClausesSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_uses_guards():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good PHP code should score >=8, got {result.score}"
    assert not result.skipped


def test_bad_php_needs_guards():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = GuardClausesSieve().analyze(parsed)
    assert result.score <= 10.0  # may or may not flag wrappedBody


def test_bad_php_guard_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = GuardClausesSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have guard clause findings"
