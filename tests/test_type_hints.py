"""Tests for the TypeHints sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.type_hints import TypeHintsSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_has_type_hints():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.score >= 5.0, f"Good code (with type hints) should score >=5, got {result.score}"


def test_bad_code_lacks_type_hints():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.score <= 3.0, f"Bad code (no type hints) should score <=3, got {result.score}"


def test_bad_code_type_hint_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = TypeHintsSieve().analyze(parsed)
    assert len(result.findings) > 0, "Missing type hints should produce findings"


def test_type_hints_name():
    sieve = TypeHintsSieve()
    assert sieve.name == "TypeHints"
    assert sieve.default_weight == 0.08
