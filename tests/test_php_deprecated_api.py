"""Tests for the DeprecatedAPI sieve on PHP code."""

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.deprecated_api import DeprecatedAPISieve

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_good_php_no_deprecated():
    parsed = ParsedFile(str(FIXTURES / "good.php"))
    result = DeprecatedAPISieve().analyze(parsed)
    assert result.score == 10.0, f"Good PHP code should have no deprecated calls, got {result.score}"
    assert len(result.findings) == 0


def test_bad_php_has_deprecated():
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = DeprecatedAPISieve().analyze(parsed)
    assert result.score < 5.0, f"Bad PHP code with deprecated calls should score low, got {result.score}"
    assert len(result.findings) > 0


def test_deprecated_findings_have_replacements():
    """Each finding should suggest a modern replacement."""
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = DeprecatedAPISieve().analyze(parsed)
    for finding in result.findings:
        assert "use " in finding.message.lower() or "—" in finding.message


def test_removed_vs_deprecated_severity():
    """Removed functions should be errors, deprecated should be warnings."""
    parsed = ParsedFile(str(FIXTURES / "bad.php"))
    result = DeprecatedAPISieve().analyze(parsed)
    errors = [f for f in result.findings if f.severity == "error"]
    warnings = [f for f in result.findings if f.severity == "warning"]
    assert len(errors) > 0, "Should have error-severity findings for removed functions"
    assert len(warnings) > 0, "Should have warning-severity findings for deprecated functions"


def test_python_file_returns_perfect():
    """DeprecatedAPI sieve should skip for non-PHP files."""
    py_fixtures = Path(__file__).parent / "fixtures" / "python"
    parsed = ParsedFile(str(py_fixtures / "good.py"))
    result = DeprecatedAPISieve().analyze(parsed)
    assert result.skipped is True
    assert "non-PHP" in result.skip_reason


def test_specific_mysql_detection():
    """Should detect mysql_* function family."""
    code = '<?php\nfunction test() {\n    $conn = mysql_connect("host", "user", "pass");\n    mysql_query("SELECT 1", $conn);\n}\n'
    with tempfile.NamedTemporaryFile(suffix='.php', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = DeprecatedAPISieve().analyze(parsed)
        names = [f.message for f in result.findings]
        assert any("mysql_connect" in m for m in names)
        assert any("mysql_query" in m for m in names)
        assert all("removed" in m for m in names)
    finally:
        os.unlink(path)
