"""A file tree-sitter cannot parse is a tool error, never a passing grade.

tree-sitter always returns a tree: what it cannot understand becomes ERROR (or a
zero-width MISSING) node. Graded anyway, a file of pure garbage reads as a file
with no functions — the best score Comments, TypeHints and Naming can give — so
broken code passed the gate the tool exists to be.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codesieve.cli import main
from codesieve.config import Config
from codesieve.engine import scan, scan_file
from codesieve.parser.treesitter import ParsedFile, SourceParseError

GARBAGE = "def broken(:\n    pass\n"
CLEAN = (
    "def price(amount: float) -> float:\n"
    '    """Return the price."""\n'
    "    return amount\n"
)


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text)
    return path


def _output(result) -> str:
    """stdout and stderr together, whichever way this Click version splits them."""
    return result.output + (result.stderr or "")


def test_unparseable_python_file_raises(tmp_path):
    path = _write(tmp_path, "garbage.py", GARBAGE)
    with pytest.raises(SourceParseError) as excinfo:
        ParsedFile(str(path))
    assert "line 1" in str(excinfo.value)
    assert "does not parse" in str(excinfo.value)


@pytest.mark.parametrize("name,text", [
    ("truncated.py", "class Case(:\n    def method(self):\n"),
    ("truncated.php", "<?php\nfunction f(int $a) {\n    return $a\n"),
    ("truncated.js", "function f(a) {\n    return a;\n"),
    ("truncated.go", "package main\n\nfunc f(a int) int {\n\treturn a\n"),
])
def test_every_language_refuses_to_grade_a_broken_file(tmp_path, name, text):
    with pytest.raises(SourceParseError):
        ParsedFile(str(_write(tmp_path, name, text)))


def test_scan_file_does_not_grade_a_broken_file(tmp_path):
    with pytest.raises(SourceParseError):
        scan_file(_write(tmp_path, "garbage.py", GARBAGE), Config())


def test_scan_grades_the_survivors_and_records_the_parse_error(tmp_path):
    _write(tmp_path, "garbage.py", GARBAGE)
    _write(tmp_path, "clean.py", CLEAN)
    report = scan(tmp_path, Config())
    assert [fr.filename for fr in report.file_reports] == ["clean.py"]
    assert len(report.errors) == 1
    path, message = report.errors[0]
    assert path.endswith("garbage.py")
    assert "does not parse" in message


def test_cli_exits_2_on_a_syntax_error_and_names_the_file(tmp_path):
    _write(tmp_path, "garbage.py", GARBAGE)
    result = CliRunner().invoke(main, ["scan", str(tmp_path)])
    assert result.exit_code == 2
    assert "garbage.py" in _output(result)
    assert "does not parse" in _output(result)
    assert "Traceback" not in _output(result)


def test_syntax_error_is_never_reported_as_a_pass(tmp_path):
    """The regression: this file used to score 8.5 / grade A and exit 0."""
    _write(tmp_path, "garbage.py", GARBAGE)
    result = CliRunner().invoke(main, ["scan", str(tmp_path), "--format", "json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["files"] == []
