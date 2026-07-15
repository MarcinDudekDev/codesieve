"""Tests for the engine orchestrator."""

import subprocess
from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file, scan, _collect_diff_files
from codesieve.models import Grade

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_scan_file_good():
    config = Config()
    report = scan_file(FIXTURES / "good.py", config)
    assert report.aggregate_score >= 7.0
    assert report.grade in (Grade.A, Grade.B)
    assert len(report.sieve_results) == 10


def test_scan_file_bad():
    config = Config()
    report = scan_file(FIXTURES / "bad.py", config)
    assert report.aggregate_score <= 5.0
    assert report.grade in (Grade.C, Grade.D, Grade.F)


def test_scan_directory():
    config = Config()
    report = scan(FIXTURES, config)
    assert len(report.file_reports) == 2
    assert report.aggregate_score > 0


def test_scan_specific_sieves():
    config = Config(sieves=["KISS"])
    report = scan_file(FIXTURES / "good.py", config)
    assert len(report.sieve_results) == 1
    assert report.sieve_results[0].name == "KISS"


def test_scan_nonexistent_returns_empty():
    config = Config()
    report = scan("/nonexistent/path/that/does/not/exist.py", config)
    assert len(report.file_reports) == 0


# --- _collect_diff_files (the `scan --diff` path) ---


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in cwd, failing the test loudly on error."""
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _init_repo(root: Path) -> None:
    """Initialise a throwaway git repo with a deterministic identity."""
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)


def test_collect_diff_files_returns_changed_file(tmp_path):
    """Normal path: a tracked file modified since a ref is collected."""
    _init_repo(tmp_path)
    src = tmp_path / "mod.py"
    src.write_text("x = 1\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)

    src.write_text("x = 2\n")  # modify since HEAD (shows as M under --diff-filter=ACM)

    changed = _collect_diff_files(tmp_path, "HEAD")
    assert src.resolve() in {c.resolve() for c in changed}


def test_collect_diff_files_empty_when_no_changes(tmp_path):
    """Edge: a clean working tree yields an empty set (no diff since ref)."""
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)

    assert _collect_diff_files(tmp_path, "HEAD") == set()


def test_collect_diff_files_non_git_dir_returns_empty(tmp_path):
    """Edge: outside a git repo, git rev-parse fails and we return an empty set."""
    assert _collect_diff_files(tmp_path, "HEAD") == set()
