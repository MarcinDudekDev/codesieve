"""Tests for the Naming sieve on PHP code."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.naming import NamingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_good_names():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = NamingSieve().analyze(parsed)
    assert result.score >= 8.0, f"Good PHP code should score >=8, got {result.score}"
    assert not result.skipped


def test_bad_php_bad_names():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = NamingSieve().analyze(parsed)
    assert result.score <= 6.0, f"Bad PHP code should score <=6, got {result.score}"


def test_bad_php_naming_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = NamingSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad PHP code should have naming findings"


def test_php_pascal_case_class():
    """Good PHP class names should be PascalCase."""
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = NamingSieve().analyze(parsed)
    # UserRepository is PascalCase — should have no class name violations
    class_violations = [f for f in result.findings if "class" in f.message]
    assert len(class_violations) == 0


def test_php_bad_class_name():
    """Bad PHP class names should be flagged with PSR-1 reference."""
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = NamingSieve().analyze(parsed)
    # 'mgr' is not PascalCase
    class_violations = [f for f in result.findings if "class" in f.message]
    assert len(class_violations) > 0
    assert "PSR-1" in class_violations[0].message


def test_php_psr1_method_camelcase():
    """PSR-1 §4.3: Method names MUST be camelCase."""
    import tempfile, os
    code = '<?php\nclass Foo {\n    public function bad_method_name() { return 1; }\n    public function goodMethodName() { return 2; }\n}\n'
    with tempfile.NamedTemporaryFile(suffix='.php', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = NamingSieve().analyze(parsed)
        method_violations = [f for f in result.findings if "method" in f.message and "camelCase" in f.message]
        assert len(method_violations) == 1, f"Expected 1 PSR-1 method violation, got {len(method_violations)}"
        assert "bad_method_name" in method_violations[0].message
        assert "PSR-1" in method_violations[0].message
    finally:
        os.unlink(path)
