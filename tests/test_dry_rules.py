"""Tests for the DRY sieve's stdlib-reimplementation rules (Part b, dry_rules.py)."""

from __future__ import annotations

import os
import tempfile

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.dry import DrySieve


def _analyze(code: str, suffix: str):
    f = tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False)
    f.write(code)
    f.close()
    try:
        return DrySieve().analyze(ParsedFile(f.name))
    finally:
        os.unlink(f.name)


def _hints(result):
    return [f for f in result.findings if f.severity == "info"]


# ---- size_format -------------------------------------------------------------------------
def test_php_mb_math_suggests_size_format():
    code = "<?php\nfunction f($size) { return round($size / (1024 * 1024), 2) . ' MB'; }\n"
    hints = _hints(_analyze(code, ".php"))
    assert len(hints) == 1
    assert "size_format()" in hints[0].message


def test_php_literal_megabyte_divisor_suggests_size_format():
    code = "<?php\nfunction f($bytes) { return $bytes / 1048576; }\n"
    hints = _hints(_analyze(code, ".php"))
    assert len(hints) == 1
    assert "size_format()" in hints[0].message


def test_kilobyte_only_math_not_flagged():
    """`/ 1024` alone (KB) is too weak a signal — must NOT fire size_format."""
    code = "<?php\nfunction f($bytes) { return $bytes / 1024; }\n"
    assert _hints(_analyze(code, ".php")) == []


# ---- wp_convert_hr_to_bytes --------------------------------------------------------------
def test_php_ini_size_ladder_suggests_hr_to_bytes():
    code = """<?php
function to_bytes($val) {
    $last = strtolower(substr($val, -1));
    $val = (int) $val;
    switch ($last) {
        case 'g': $val *= 1024;
        case 'm': $val *= 1024;
        case 'k': $val *= 1024;
    }
    return $val;
}
"""
    hints = _hints(_analyze(code, ".php"))
    assert len(hints) == 1, f"Ladder should yield exactly one (deduped) hint, got {hints}"
    assert "wp_convert_hr_to_bytes()" in hints[0].message


def test_standalone_times_1024_not_flagged():
    """A lone `*= 1024` outside any suffix ladder is not the ini-parser signature."""
    code = "<?php\nfunction f($v) { $v *= 1024; return $v; }\n"
    assert _hints(_analyze(code, ".php")) == []


# ---- severity / scoring ------------------------------------------------------------------
def test_hints_are_info_severity_and_do_not_hard_fail():
    code = "<?php\nfunction f($bytes) { return $bytes / 1048576; }\n"
    result = _analyze(code, ".php")
    assert all(f.severity == "info" for f in _hints(result))
    assert result.score >= 9.0  # one light hint, nowhere near a hard fail


# ---- language gating ---------------------------------------------------------------------
def test_python_byte_math_not_flagged_by_php_rules():
    """PHP/WP rules are language-gated; identical Python math gets no stdlib hint."""
    code = "def f(size):\n    return round(size / (1024 * 1024), 2)\n"
    assert _hints(_analyze(code, ".py")) == []
