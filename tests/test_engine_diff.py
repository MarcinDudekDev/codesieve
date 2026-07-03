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
    result = {p.resolve() for p in _collect_diff_files(root, "HEAD")}
    assert changed.resolve() in result
    assert committed.resolve() not in result


def test_collect_diff_files_clean_tree_is_empty(git_repo):
    root, _committed, changed = git_repo
    changed.write_text("y = 1\n")  # revert the working-tree change
    assert _collect_diff_files(root, "HEAD") == set()


def test_collect_diff_files_non_git_dir_returns_empty(tmp_path: Path):
    # No git repo here -> `git rev-parse` fails -> the except branch returns set().
    assert _collect_diff_files(tmp_path, "HEAD") == set()


def test_scan_with_diff_ref_limits_to_changed_files(git_repo):
    root, committed, changed = git_repo
    report = scan(root, Config(), diff_ref="HEAD")
    scanned = {Path(r.path).resolve() for r in report.file_reports}
    assert changed.resolve() in scanned
    assert committed.resolve() not in scanned
