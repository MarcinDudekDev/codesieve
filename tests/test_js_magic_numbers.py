"""Tests for the MagicNumbers sieve on JavaScript code."""

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.magic_numbers import MagicNumbersSieve

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_good_js_no_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "good.js"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score >= 9.0, f"Good JS should have few magic numbers, got {result.score}"


def test_bad_js_has_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "bad.js"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score <= 3.0, f"Bad JS with magic numbers should score low, got {result.score}"
    assert len(result.findings) > 5, "Should find many magic numbers"


def test_js_const_upper_snake_not_magic():
    """UPPER_SNAKE const declarations should not be flagged as magic numbers."""
    code = '''function test() {
    const MAX_SIZE = 500;
    return MAX_SIZE;
}
'''
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = MagicNumbersSieve().analyze(parsed)
        assert result.score == 10.0, f"UPPER_SNAKE consts should not be magic, got {result.score}"
    finally:
        os.unlink(path)


def test_js_default_param_not_magic():
    """Default parameter values should not be flagged."""
    code = '''function retry(attempts = 5) {
    return attempts;
}
'''
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = MagicNumbersSieve().analyze(parsed)
        assert result.score == 10.0, f"Default params should not be magic, got {result.score}"
    finally:
        os.unlink(path)
