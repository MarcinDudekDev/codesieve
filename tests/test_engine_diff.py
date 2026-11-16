"""Tests for git-diff scoped scanning: engine._collect_diff_files + scan(diff_ref=...).

These pin the behaviour of the ``codesieve scan --diff`` feature, which was
previously untested. They exercise a real temp git repo so the subprocess calls
in ``_collect_diff_files`` are covered end-to-end.
"""

import subprocess
from pathlib import Path

import pytest

from codesieve.config import Config
from codesieve.engine import _collect_diff_files, scan


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path):
    """A temp git repo with two committed .py files, one then modified (unstaged)."""
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    committed = tmp_path / "committed.py"
    committed.write_text("x = 1\n")
    changed = tmp_path / "changed.py"
    changed.write_text("y = 1\n")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-q", "-m", "init"], tmp_path)
    changed.write_text("y = 2\n")  # working-tree change vs HEAD
    return tmp_path, committed, changed


def test_collect_diff_files_returns_only_changed(git_repo):
    root, committed, changed = git_repo
    changed_files = _collect_diff_files(root, "HEAD")
    assert changed_files is not None
    result = {p.resolve() for p in changed_files}
    assert changed.resolve() in result
    assert committed.resolve() not in result


def test_collect_diff_files_clean_tree_is_empty(git_repo):
    root, _committed, changed = git_repo
    changed.write_text("y = 1\n")  # revert the working-tree change
    assert _collect_diff_files(root, "HEAD") == set()


def test_collect_diff_files_non_git_dir_returns_empty(tmp_path: Path):
    # No git repo here -> `git rev-parse` fails -> None, distinct from "nothing changed".
    assert _collect_diff_files(tmp_path, "HEAD") is None


def test_scan_with_diff_ref_limits_to_changed_files(git_repo):
    root, committed, changed = git_repo
    report = scan(root, Config(), diff_ref="HEAD")
    scanned = {Path(r.path).resolve() for r in report.file_reports}
    assert changed.resolve() in scanned
    assert committed.resolve() not in scanned


def test_scan_with_diff_ref_and_clean_tree_scans_nothing(git_repo):
    root, _committed, changed = git_repo
    changed.write_text("y = 1\n")  # no changes vs HEAD
    assert scan(root, Config(), diff_ref="HEAD").file_reports == []


def test_collect_diff_files_bad_ref_is_none_not_empty(git_repo):
    root, _committed, _changed = git_repo
    assert _collect_diff_files(root, "no-such-ref") is None


def test_scan_with_diff_outside_git_raises_instead_of_scanning_everything(tmp_path: Path):
    """--diff was asked for and git cannot answer: an error, never a silent full scan."""
    from codesieve.diffscope import DiffScopeError

    (tmp_path / "m.py").write_text("x = 1\n")
    with pytest.raises(DiffScopeError, match="--diff"):
        scan(tmp_path, Config(), diff_ref="HEAD")


def test_scan_with_unknown_diff_ref_raises(git_repo):
    from codesieve.diffscope import DiffScopeError

    root, _committed, _changed = git_repo
    with pytest.raises(DiffScopeError, match="no-such-ref"):
        scan(root, Config(), diff_ref="no-such-ref")


def test_cli_diff_with_no_changes_exits_zero(git_repo):
    from click.testing import CliRunner

    from codesieve.cli import main

    root, _committed, changed = git_repo
    changed.write_text("y = 1\n")
    result = CliRunner().invoke(main, ["scan", str(root), "--diff", "HEAD"])
    assert result.exit_code == 0, result.output
    assert "No changed files" in result.output
