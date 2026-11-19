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


def test_hex_binary_and_octal_literals_are_magic_numbers():
    """`int()` refused the 0x/0b/0o prefixes, so those literals were silently skipped."""
    code = (
        "function f(n) {\n"
        "  const a = n + 0xff00;\n"
        "  const b = a + 0b1010;\n"
        "  const c = b + 0o17;\n"
        "  return c + 0x1;\n"
        "}\n"
    )
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = MagicNumbersSieve().analyze(parsed)
    finally:
        os.unlink(path)
    messages = [f.message for f in result.findings]
    assert any("0xff00" in m for m in messages), messages
    assert any("0b1010" in m for m in messages), messages
    assert any("0o17" in m for m in messages), messages
    assert len(messages) == 3, messages  # 0x1 stays under the small-number threshold
