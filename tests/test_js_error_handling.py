"""Tests for the ErrorHandling sieve on JavaScript code."""

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.error_handling import ErrorHandlingSieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_error_handling():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score >= 9.0, f"Good JS error handling should score >=9, got {result.score}"


def test_bad_js_empty_catch():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = ErrorHandlingSieve().analyze(parsed)
    assert result.score < 10.0, f"JS with empty catch should lose points, got {result.score}"
    assert any("empty catch" in f.message for f in result.findings), "Should flag empty catch body"


def test_js_no_try_blocks():
    """JS code without try blocks should get perfect score."""
    code = 'function add(a, b) { return a + b; }\n'
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = ErrorHandlingSieve().analyze(parsed)
        assert result.score == 10.0
    finally:
        os.unlink(path)


def test_js_catch_with_rethrow():
    """Catch that re-throws should not be penalized."""
    code = '''function risky() {
    try { doSomething(); }
    catch (e) { console.log(e); throw e; }
}
'''
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = ErrorHandlingSieve().analyze(parsed)
        assert result.score == 10.0, f"Catch with rethrow should be perfect, got {result.score}"
    finally:
        os.unlink(path)
