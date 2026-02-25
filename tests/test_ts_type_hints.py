"""Tests for the TypeHints sieve on TypeScript code."""

import os
import tempfile
from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.type_hints import TypeHintsSieve

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_good_ts_type_hints():
    parsed = ParsedFile(str(FIXTURES / "good.ts"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good TS code should score >=7 for types, got {result.score}"
    assert not result.skipped


def test_bad_ts_type_hints():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.score < 10.0, f"Bad TS code should have type issues, got {result.score}"


def test_bad_ts_missing_annotations():
    parsed = ParsedFile(str(FIXTURES / "bad.ts"))
    result = TypeHintsSieve().analyze(parsed)
    findings_text = [f.message for f in result.findings]
    # Should flag missing type annotations
    assert any("missing" in m for m in findings_text), "Should flag missing type annotations"


def test_js_type_hints_skipped():
    """TypeHints sieve should skip for JavaScript files (no type system)."""
    js_fixtures = Path(__file__).parent / "fixtures" / "javascript"
    parsed = ParsedFile(str(js_fixtures / "good.js"))
    result = TypeHintsSieve().analyze(parsed)
    assert result.skipped is True
    assert "not applicable" in result.skip_reason.lower()


def test_fully_typed_ts():
    """Fully typed TS code should score high."""
    code = '''function greet(name: string): string {
    return 'Hello ' + name;
}

function add(a: number, b: number): number {
    return a + b;
}
'''
    with tempfile.NamedTemporaryFile(suffix='.ts', mode='w', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        parsed = ParsedFile(path)
        result = TypeHintsSieve().analyze(parsed)
        assert result.score >= 9.0, f"Fully typed TS should score >=9, got {result.score}"
    finally:
        os.unlink(path)
