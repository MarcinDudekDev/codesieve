"""Tests for the DeprecatedAPI sieve on JavaScript code."""

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.deprecated_api import DeprecatedAPISieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_no_deprecated():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = DeprecatedAPISieve().analyze(parsed)
    assert result.score == 10.0, f"Good JS code should have no deprecated patterns, got {result.score}"
    assert len(result.findings) == 0


def test_bad_js_has_deprecated():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = DeprecatedAPISieve().analyze(parsed)
    assert result.score < 10.0, f"Bad JS code should have deprecated findings, got {result.score}"
    assert len(result.findings) > 0


def test_js_var_detection():
    code = "var x = 1;\nvar y = 2;\nlet z = 3;\n"
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = DeprecatedAPISieve().analyze(parsed)
        var_findings = [f for f in result.findings if "var" in f.message.lower()]
        assert len(var_findings) == 2, f"Expected 2 var findings, got {len(var_findings)}"
    finally:
        os.unlink(path)


def test_js_escape_detection():
    code = "const encoded = escape('hello');\nconst decoded = unescape('%20');\n"
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = DeprecatedAPISieve().analyze(parsed)
        names = [f.message for f in result.findings]
        assert any("escape" in m for m in names), f"Should detect escape(), got {names}"
        assert any("unescape" in m for m in names), f"Should detect unescape(), got {names}"
    finally:
        os.unlink(path)


def test_js_let_const_not_flagged():
    code = "let count = 0;\nconst MAX = 10;\ncount += 1;\n"
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = DeprecatedAPISieve().analyze(parsed)
        assert result.score == 10.0, f"let/const should not be flagged, got {result.score}"
        assert len(result.findings) == 0
    finally:
        os.unlink(path)
