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


# --- PHP 8 promoted params and file-level strict_types (warden cycle, 2026-11-19) ---------

def _analyze_php(tmp_path, source: str):
    target = tmp_path / "Sample.php"
    target.write_text(source)
    return TypeHintsSieve().analyze(ParsedFile(str(target)))


def test_promoted_constructor_params_are_counted_and_typed(tmp_path):
    """`public readonly int $x` is a parameter: typing and naming must see it."""
    source = (
        "<?php\ndeclare(strict_types=1);\n"
        "class Point {\n"
        "    public function __construct(public readonly int $x, public $y) {}\n"
        "}\n"
    )
    result = _analyze_php(tmp_path, source)
    assert "(1/2 params" in result.summary, result.summary
    messages = [f.message for f in result.findings]
    assert any("$y'" in m for m in messages), messages
    assert not any("$x'" in m for m in messages), messages


def test_variadic_param_message_puts_the_ellipsis_before_the_dollar(tmp_path):
    result = _analyze_php(
        tmp_path, "<?php\ndeclare(strict_types=1);\nfunction f(...$rest) { return 1; }\n"
    )
    messages = [f.message for f in result.findings]
    assert any("'...$rest'" in m for m in messages), messages
    assert not any("$...rest" in m for m in messages), messages


def test_functions_less_file_is_charged_for_missing_strict_types(tmp_path):
    """`declare(strict_types=1)` is a file requirement, so it applies without functions."""
    result = _analyze_php(tmp_path, "<?php\n$GLOBALS['x'] = 1;\n")
    assert result.score == 8.5, result.score
    assert "strict_types" in result.summary, result.summary
    assert any("strict_types" in f.message for f in result.findings)


def test_functions_less_file_with_strict_types_is_perfect(tmp_path):
    result = _analyze_php(tmp_path, "<?php\ndeclare(strict_types=1);\n$GLOBALS['x'] = 1;\n")
    assert result.score == 10.0, result.score
