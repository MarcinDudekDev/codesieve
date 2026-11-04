"""Exclude patterns must hold at any depth below the scan root.

Regression for a shipswipe report: `Path.match` is right-anchored and treats
`**` as one segment, so the default `**/.venv/**` only caught files sitting
directly inside `.venv/`, and a bare `--exclude .venv` caught nothing.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from codesieve.cli import main
from codesieve.config import Config
from codesieve.engine import _collect_files, scan
from codesieve.report import report_to_json

SRC = "def add(a: int, b: int) -> int:\n    return a + b\n"


def _tree(root: Path, *rels: str) -> None:
    for rel in rels:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(SRC)


def _rels(root: Path, files: list[Path]) -> set[str]:
    return {f.relative_to(root).as_posix() for f in files}


def test_default_excludes_deeply_nested_venv(tmp_path):
    _tree(tmp_path, "app/main.py", ".venv/lib/python3.14/site-packages/pkg/mod.py", "sub/venv/lib/x.py")
    files = _collect_files(tmp_path, Config().exclude)
    assert _rels(tmp_path, files) == {"app/main.py"}


def test_bare_name_excludes_directory_at_any_depth(tmp_path):
    _tree(tmp_path, "app/main.py", "tests/unit/test_a.py", "app/tests/test_b.py", "alembic/versions/v1.py")
    files = _collect_files(tmp_path, ["tests", "alembic"])
    assert _rels(tmp_path, files) == {"app/main.py"}


def test_slash_pattern_floats_unless_anchored(tmp_path):
    _tree(tmp_path, "tests/a.py", "pkg/tests/b.py", "pkg/c.py")
    assert _rels(tmp_path, _collect_files(tmp_path, ["tests/*"])) == {"pkg/c.py"}
    assert _rels(tmp_path, _collect_files(tmp_path, ["/tests/*"])) == {"pkg/tests/b.py", "pkg/c.py"}


def test_file_glob_still_works(tmp_path):
    _tree(tmp_path, "good.py", "deep/er/bad.py")
    assert _rels(tmp_path, _collect_files(tmp_path, ["**/bad.py"])) == {"good.py"}
    assert _rels(tmp_path, _collect_files(tmp_path, ["bad.py"])) == {"good.py"}


def test_cli_exclude_list_from_shipswipe_report(tmp_path):
    _tree(tmp_path, "server/app.py", "server/.venv/lib/site-packages/x/y.py",
          "server/tests/t.py", "server/alembic/env.py", "server/contract/c.py")
    result = CliRunner().invoke(main, [
        "scan", str(tmp_path / "server"),
        "--exclude", ".venv,tests,alembic,contract,__pycache__", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    paths = [Path(f["path"]).name for f in json.loads(result.output)["files"]]
    assert paths == ["app.py"]


def test_skipped_sieve_serializes_null_score(tmp_path):
    _tree(tmp_path, "m.py")
    data = json.loads(report_to_json(scan(tmp_path, Config())))
    sieves = data["files"][0]["sieves"]
    skipped = [s for s in sieves if s["skipped"]]
    assert skipped, "expected at least one skipped sieve for python (DeprecatedAPI)"
    assert all(s["score"] is None for s in skipped)
    assert all(isinstance(s["score"], float) for s in sieves if not s["skipped"])
