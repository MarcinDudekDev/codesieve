"""Tests for the TypeHints sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.type_hints import TypeHintsSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_has_type_hints():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good PHP code should score >=7, got {result.score}"
    assert not result.skipped


def test_bad_php_lacks_type_hints():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.score <= 3.0, f"Bad PHP code should score <=3, got {result.score}"


def test_bad_php_type_hint_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = TypeHintsSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have type hint findings"


def test_good_php_has_strict_types():
    """Good PHP code with declare(strict_types=1) should not have strict_types finding."""
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = TypeHintsSieve().analyze(parsed)
    strict_findings = [f for f in result.findings if "strict_types" in f.message]
    assert len(strict_findings) == 0, "good.php has strict_types=1, should not be flagged"


def test_bad_php_missing_strict_types():
    """Bad PHP code without declare(strict_types=1) should be flagged."""
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = TypeHintsSieve().analyze(parsed)
    strict_findings = [f for f in result.findings if "strict_types" in f.message]
    assert len(strict_findings) == 1, "bad.php lacks strict_types, should be flagged"
    assert "PSR-12" in strict_findings[0].message
