"""Tests for the Comments sieve across all supported languages."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.comments import CommentsSieve

PY_FIXTURES = Path(__file__).parent / "fixtures" / "python"
PHP_FIXTURES = Path(__file__).parent / "fixtures" / "php"
JS_FIXTURES = Path(__file__).parent / "fixtures" / "javascript"
TS_FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


# --- Python ---

def test_good_py_has_docstrings():
    parsed = ParsedFile(str(PY_FIXTURES / "good.py"))
    result = CommentsSieve().analyze(parsed)
    assert result.score == 10.0, f"Good Python should have full docstring coverage, got {result.score}"
    assert len(result.findings) == 0


def test_bad_py_missing_docstrings():
    parsed = ParsedFile(str(PY_FIXTURES / "bad.py"))
    result = CommentsSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad Python should be missing docstrings, got {result.score}"
    assert len(result.findings) > 0


def test_py_inline_documented():
    code = "def greet(name: str) -> str:\n    \"\"\"Return a greeting.\"\"\"\n    return f'Hello, {name}'\n"
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = CommentsSieve().analyze(ParsedFile(path))
        assert result.score == 10.0, f"Documented function should score 10, got {result.score}"
        assert len(result.findings) == 0
    finally:
        os.unlink(path)


def test_py_inline_undocumented():
    code = "def greet(name: str) -> str:\n    return f'Hello, {name}'\n"
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = CommentsSieve().analyze(ParsedFile(path))
        assert result.score < 10.0
        assert any("greet" in f.message for f in result.findings)
    finally:
        os.unlink(path)


# --- PHP ---

def test_good_php_has_phpdoc():
    parsed = ParsedFile(str(PHP_FIXTURES / "good.php"))
    result = CommentsSieve().analyze(parsed)
    assert result.score == 10.0, f"Good PHP should have full PHPDoc coverage, got {result.score}"


def test_bad_php_missing_phpdoc():
    parsed = ParsedFile(str(PHP_FIXTURES / "bad.php"))
    result = CommentsSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad PHP should be missing PHPDoc, got {result.score}"
    assert len(result.findings) > 0


def test_php_inline_phpdoc():
    code = "<?php\n/** @return string */\nfunction greet(string $name): string {\n    return 'Hello ' . $name;\n}\n"
    with tempfile.NamedTemporaryFile(suffix=".php", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = CommentsSieve().analyze(ParsedFile(path))
        assert result.score == 10.0, f"PHPDoc function should score 10, got {result.score}"
    finally:
        os.unlink(path)


# --- JavaScript ---

def test_good_js_has_jsdoc():
    parsed = ParsedFile(str(JS_FIXTURES / "good.js"))
    result = CommentsSieve().analyze(parsed)
    assert result.score == 10.0, f"Good JS should have full JSDoc coverage, got {result.score}"


def test_bad_js_missing_jsdoc():
    parsed = ParsedFile(str(JS_FIXTURES / "bad.js"))
    result = CommentsSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad JS should be missing JSDoc, got {result.score}"
    assert len(result.findings) > 0


def test_js_inline_jsdoc():
    code = "/** @param {string} name */\nfunction greet(name) {\n    return 'Hello ' + name;\n}\n"
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = CommentsSieve().analyze(ParsedFile(path))
        assert result.score == 10.0, f"JSDoc function should score 10, got {result.score}"
    finally:
        os.unlink(path)


def test_js_regular_comment_not_jsdoc():
    code = "// Not a JSDoc comment\nfunction greet(name) {\n    return 'Hello ' + name;\n}\n"
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = CommentsSieve().analyze(ParsedFile(path))
        assert result.score < 10.0, "// comment should not count as JSDoc"
        assert any("greet" in f.message for f in result.findings)
    finally:
        os.unlink(path)


# --- TypeScript ---

def test_good_ts_has_jsdoc():
    parsed = ParsedFile(str(TS_FIXTURES / "good.ts"))
    result = CommentsSieve().analyze(parsed)
    assert result.score == 10.0, f"Good TS should have full JSDoc coverage, got {result.score}"


def test_bad_ts_missing_jsdoc():
    parsed = ParsedFile(str(TS_FIXTURES / "bad.ts"))
    result = CommentsSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad TS should be missing JSDoc, got {result.score}"
    assert len(result.findings) > 0
