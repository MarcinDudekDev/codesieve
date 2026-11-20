"""Tests for the MagicNumbers sieve."""

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.magic_numbers import MagicNumbersSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_no_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"


def test_bad_code_has_magic_numbers():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = MagicNumbersSieve().analyze(parsed)
    assert result.score <= 8.0, f"Bad code should score <=8 for magic numbers, got {result.score}"


def test_bad_code_magic_number_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = MagicNumbersSieve().analyze(parsed)
    assert len(result.findings) > 0, "Magic numbers should produce findings"


def test_magic_numbers_name():
    sieve = MagicNumbersSieve()
    assert sieve.name == "MagicNumbers"
    assert sieve.default_weight == 0.05


# --- literal forms int(x, 0) refuses (warden cycle, 2026-11-20) ---------------------------

def _scan(source: str, suffix: str):
    with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False) as f:
        f.write(source)
        path = f.name
    try:
        return MagicNumbersSieve().analyze(ParsedFile(path))
    finally:
        os.unlink(path)


def test_legacy_octal_literals_are_magic_numbers():
    """Go `0755` and PHP `017` are integers int(x, 0) raises on, so they vanished."""
    go = _scan("package main\n\nfunc f() int { return 0755 }\n", ".go")
    php = _scan("<?php\nfunction f() { return 017; }\n", ".php")
    assert [f.message for f in go.findings] == ["magic number 0755 in f()"]
    assert [f.message for f in php.findings] == ["magic number 017 in f()"]


def test_legacy_octal_is_read_as_octal_not_decimal():
    """`0100` is 64, so it must not be excused as the allowed number 100."""
    result = _scan("package main\n\nfunc f() int { return 0100 }\n", ".go")
    assert [f.message for f in result.findings] == ["magic number 0100 in f()"]


def test_js_bigint_literal_is_a_magic_number():
    result = _scan("function f() { return 123456n; }\n", ".js")
    assert [f.message for f in result.findings] == ["magic number 123456n in f()"]
