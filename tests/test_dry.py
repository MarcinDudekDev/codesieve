"""Tests for the DRY sieve."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.dry import DrySieve

PY_FIXTURES = Path(__file__).parent / "fixtures" / "python"
JS_FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def _py_file(code: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False)
    f.write(code)
    f.close()
    return f.name


def _js_file(code: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False)
    f.write(code)
    f.close()
    return f.name


def test_good_py_no_duplicates():
    parsed = ParsedFile(str(PY_FIXTURES / "good.py"))
    result = DrySieve().analyze(parsed)
    assert result.score == 10.0, f"Good Python should have no duplicates, got {result.score}"
    assert len(result.findings) == 0


def test_good_js_no_duplicates():
    parsed = ParsedFile(str(JS_FIXTURES / "good.js"))
    result = DrySieve().analyze(parsed)
    assert result.score == 10.0, f"Good JS should have no duplicates, got {result.score}"
    assert len(result.findings) == 0


def test_duplicate_python_functions():
    code = """\
def save_user(db, record):
    db.connect()
    db.execute("INSERT INTO records VALUES (?)", record)
    db.commit()
    db.close()

def save_product(db, record):
    db.connect()
    db.execute("INSERT INTO records VALUES (?)", record)
    db.commit()
    db.close()
"""
    path = _py_file(code)
    try:
        result = DrySieve().analyze(ParsedFile(path))
        assert result.score < 10.0, f"Duplicate functions should score below 10, got {result.score}"
        assert len(result.findings) == 1
        assert "duplicates" in result.findings[0].message
    finally:
        os.unlink(path)


def test_three_way_duplicate():
    code = """\
def alpha(x, y):
    total = x + y
    result = total * 2
    return result

def beta(x, y):
    total = x + y
    result = total * 2
    return result

def gamma(x, y):
    total = x + y
    result = total * 2
    return result
"""
    path = _py_file(code)
    try:
        result = DrySieve().analyze(ParsedFile(path))
        assert len(result.findings) == 2, f"Expected 2 dup findings (beta + gamma), got {len(result.findings)}"
        assert result.score < 10.0
    finally:
        os.unlink(path)


def test_trivial_bodies_not_flagged():
    """Single-line or two-line bodies should not count as duplicates."""
    code = """\
def get_x(obj):
    return obj.x

def get_y(obj):
    return obj.x
"""
    path = _py_file(code)
    try:
        result = DrySieve().analyze(ParsedFile(path))
        assert result.score == 10.0, f"Trivial bodies should not be flagged, got {result.score}"
    finally:
        os.unlink(path)


def test_similar_but_not_identical_not_flagged():
    """Functions that differ by one line must not be reported."""
    code = """\
def process_csv(data):
    cleaned = data.strip()
    parts = cleaned.split(",")
    return [p.strip() for p in parts]

def process_tsv(data):
    cleaned = data.strip()
    parts = cleaned.split("\\t")
    return [p.strip() for p in parts]
"""
    path = _py_file(code)
    try:
        result = DrySieve().analyze(ParsedFile(path))
        assert result.score == 10.0, f"Different functions should not be flagged, got {result.score}"
        assert len(result.findings) == 0
    finally:
        os.unlink(path)


def test_no_functions_returns_perfect():
    code = "x = 1\ny = 2\n"
    path = _py_file(code)
    try:
        result = DrySieve().analyze(ParsedFile(path))
        assert result.score == 10.0
        assert result.skipped is False
    finally:
        os.unlink(path)


def test_duplicate_js_functions():
    code = """\
function saveUser(db, record) {
    db.connect();
    db.execute("INSERT INTO records VALUES (?)", record);
    db.commit();
    db.close();
}

function saveProduct(db, record) {
    db.connect();
    db.execute("INSERT INTO records VALUES (?)", record);
    db.commit();
    db.close();
}
"""
    path = _js_file(code)
    try:
        result = DrySieve().analyze(ParsedFile(path))
        assert result.score < 10.0, f"Duplicate JS functions should score below 10, got {result.score}"
        assert len(result.findings) >= 1
    finally:
        os.unlink(path)
