"""Acceptance tests for the ``codesieve scan`` exit-code contract.

    0  the scan ran and passed
    1  the scan ran and the code failed the gate (aggregate below --fail-under,
       or new findings in --new-only mode)
    2  the tool could not do what it was asked: bad config, unknown sieve,
       git diff unavailable when --diff was requested, a file that crashed
       during the scan

A tool error is never reported as a pass and never as a code failure, and it
never surfaces as a Python traceback.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codesieve.cli import main

CLEAN = (
    "def price(amount: float) -> float:\n"
    '    """Return the price."""\n'
    "    return amount\n"
)
# Scores well below 10: bare excepts with empty bodies, no hints, no docstrings.
POOR = "".join(
    f"def f{i}(a, b):\n    try:\n        return a / b\n    except:\n        pass\n\n\n"
    for i in range(6)
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A plain directory (not a git repo) with one clean file; cwd is moved there."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "clean.py").write_text(CLEAN)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def repo(project: Path) -> Path:
    """The same directory as a git repo with one commit and one modified file."""
    _git(project, "init", "-q", "-b", "main")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "Test")
    _git(project, "config", "commit.gpgsign", "false")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    (project / "clean.py").write_text(CLEAN + "\n\nLIMIT = 3\n")
    return project


def _scan(*args: str):
    return CliRunner().invoke(main, ["scan", *args])


def _assert_tool_error(result, *needles: str) -> None:
    """Exit 2, a readable message naming the cause, and no traceback."""
    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "Traceback" not in result.output
    for needle in needles:
        assert needle in result.output, result.output


# --- 0 and 1: the scan ran --------------------------------------------------------------------

def test_passing_scan_exits_0(project: Path):
    result = _scan(str(project), "--fail-under", "5")
    assert result.exit_code == 0, result.output


def test_score_below_fail_under_exits_1(project: Path):
    (project / "poor.py").write_text(POOR)
    result = _scan(str(project / "poor.py"), "--fail-under", "9.9")
    assert result.exit_code == 1, result.output


def test_low_score_without_fail_under_exits_0(project: Path):
    (project / "poor.py").write_text(POOR)
    result = _scan(str(project / "poor.py"))
    assert result.exit_code == 0, result.output


# --- 2: unknown sieve -------------------------------------------------------------------------

def test_unknown_sieve_on_command_line_exits_2(project: Path):
    _assert_tool_error(_scan(str(project), "--sieves", "KISS,NoSuchSieve"), "NoSuchSieve")


def test_unknown_sieve_in_config_exits_2(project: Path):
    (project / ".codesieve.yml").write_text("sieves:\n  - KISS\n  - NoSuchSieve\n")
    _assert_tool_error(_scan(str(project)), "NoSuchSieve")


# --- 2: bad config ----------------------------------------------------------------------------

def test_explicit_config_path_that_does_not_exist_exits_2(project: Path):
    _assert_tool_error(_scan(str(project), "--config", str(project / "missing.yml")), "missing.yml")


def test_config_with_invalid_yaml_exits_2(project: Path):
    (project / ".codesieve.yml").write_text("sieves: [KISS\nfail_under: : 3\n")
    _assert_tool_error(_scan(str(project)), ".codesieve.yml")


def test_config_that_is_not_a_mapping_exits_2(project: Path):
    (project / ".codesieve.yml").write_text("- KISS\n- Naming\n")
    _assert_tool_error(_scan(str(project)), ".codesieve.yml")


@pytest.mark.parametrize("body", [
    "fail_under: high\n",
    "sieves: KISS\n",
    "weights: [1, 2]\n",
    "weights:\n  KISS: heavy\n",
    "deterministic: maybe\n",
    "format: xml\n",
])
def test_config_with_a_wrongly_typed_value_exits_2(project: Path, body: str):
    (project / ".codesieve.yml").write_text(body)
    _assert_tool_error(_scan(str(project)), ".codesieve.yml")


def test_bad_config_found_via_config_from_target_exits_2(project: Path, tmp_path: Path, monkeypatch):
    (project / ".codesieve.yml").write_text("- not a mapping\n")
    monkeypatch.chdir(tmp_path)  # config is discovered from the target, not from cwd
    _assert_tool_error(_scan(str(project), "--config-from-target"), ".codesieve.yml")


def test_valid_config_still_loads(project: Path):
    (project / ".codesieve.yml").write_text(
        "sieves:\n  - KISS\n  - Naming\nweights:\n  KISS: 0.5\nfail_under: 5\n"
        "standard: psr\ndeterministic: true\nformat: json\nexclude:\n  - skipme\n"
    )
    result = _scan(str(project))
    assert result.exit_code == 0, result.output
    data = json.loads(getattr(result, "stdout", result.output))
    assert [s["name"] for s in data["files"][0]["sieves"]] == ["KISS", "Naming"]


def test_missing_default_config_is_not_an_error(project: Path):
    """No .codesieve.yml and no --config: plain defaults, as before."""
    assert not (project / ".codesieve.yml").exists()
    assert _scan(str(project)).exit_code == 0


# --- 2: git diff unavailable when --diff was requested ---------------------------------------

def test_diff_outside_a_git_repo_exits_2_and_scans_nothing(project: Path):
    result = _scan(str(project), "--diff", "HEAD", "--format", "json")
    _assert_tool_error(result, "--diff")
    assert "aggregate_score" not in result.output  # no silent full scan


def test_diff_against_unknown_ref_exits_2_and_scans_nothing(repo: Path):
    result = _scan(str(repo), "--diff", "no-such-ref", "--format", "json")
    _assert_tool_error(result, "no-such-ref")
    assert "aggregate_score" not in result.output


def test_diff_that_works_still_exits_0(repo: Path):
    result = _scan(str(repo), "--diff", "HEAD", "--format", "json")
    assert result.exit_code == 0, result.output
    data = json.loads(getattr(result, "stdout", result.output))
    assert [Path(f["path"]).name for f in data["files"]] == ["clean.py"]


# --- 2: a file crashed during the scan -------------------------------------------------------

@pytest.fixture
def crashing_scan(monkeypatch: pytest.MonkeyPatch):
    """Make the engine blow up on any file named boom.py, as an internal sieve bug would."""
    import codesieve.engine as engine

    real_scan_file = engine.scan_file

    def scan_file(filepath, config):
        if Path(filepath).name == "boom.py":
            raise RuntimeError("sieve exploded")
        return real_scan_file(filepath, config)

    monkeypatch.setattr(engine, "scan_file", scan_file)


def test_crashed_file_exits_2_and_is_named(project: Path, crashing_scan):
    (project / "boom.py").write_text(CLEAN)
    _assert_tool_error(_scan(str(project)), "boom.py", "sieve exploded")


def test_crashed_file_does_not_hide_the_other_files(project: Path, crashing_scan):
    (project / "boom.py").write_text(CLEAN)
    result = _scan(str(project))
    assert result.exit_code == 2, result.output
    assert "clean.py" in result.output  # the rest of the report is still printed


def test_crash_beats_a_low_score(project: Path, crashing_scan):
    """A broken run is exit 2 even when the files that did scan would have failed the gate."""
    (project / "boom.py").write_text(CLEAN)
    (project / "poor.py").write_text(POOR)
    result = _scan(str(project), "--fail-under", "9.9")
    assert result.exit_code == 2, result.output


def test_crash_beats_a_passing_score(project: Path, crashing_scan):
    (project / "boom.py").write_text(CLEAN)
    result = _scan(str(project), "--fail-under", "1")
    assert result.exit_code == 2, result.output


def test_only_file_crashing_exits_2(project: Path, crashing_scan):
    (project / "clean.py").unlink()
    (project / "boom.py").write_text(CLEAN)
    _assert_tool_error(_scan(str(project)), "boom.py")


def test_crash_in_json_mode_keeps_stdout_valid_json(project: Path, crashing_scan):
    (project / "boom.py").write_text(CLEAN)
    result = _scan(str(project), "--format", "json")
    assert result.exit_code == 2, result.output
    data = json.loads(result.stdout)  # the error line goes to stderr, not into the JSON
    assert [Path(f["path"]).name for f in data["files"]] == ["clean.py"]
    assert "boom.py" in result.stderr


# --- regressions found by independent verification (round 1) ----------------------------------

import os  # noqa: E402
import sys  # noqa: E402

HANG_LIMIT_S = 30


def _scan_subprocess(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run the real CLI in a child process: captures git's own stderr and bounds a hang."""
    return subprocess.run(
        [sys.executable, "-m", "codesieve", "scan", *args],
        cwd=cwd, capture_output=True, text=True, timeout=HANG_LIMIT_S,
    )


def test_config_that_is_not_utf8_exits_2(project: Path):
    (project / ".codesieve.yml").write_bytes(b"\xff\xfe\x00\x01x")
    _assert_tool_error(_scan(str(project)), ".codesieve.yml")


def test_config_nested_beyond_the_parser_limit_exits_2(project: Path):
    depth = 2500
    (project / ".codesieve.yml").write_text("x: " + "[" * depth + "1" + "]" * depth + "\n")
    _assert_tool_error(_scan(str(project)), ".codesieve.yml")


@pytest.mark.parametrize("body", [
    "weights:\n  KISS: .nan\n",
    "weights:\n  KISS: .inf\n",
    "weights:\n  KISS: -1\n",
    "fail_under: .nan\n",
    "fail_under: .inf\n",
    "fail_under: -5\n",
    "sieves: []\n",
])
def test_config_with_a_nonsense_number_or_empty_sieve_list_exits_2(project: Path, body: str):
    """A NaN weight used to print a fabricated 10.0 A and pass --fail-under."""
    (project / "poor.py").write_text(POOR)
    (project / ".codesieve.yml").write_text(body)
    _assert_tool_error(_scan(str(project), "--fail-under", "5"), ".codesieve.yml")


@pytest.mark.parametrize("value", ["nan", "inf", "-1"])
def test_nonsense_fail_under_on_the_command_line_exits_2(project: Path, value: str):
    (project / "poor.py").write_text(POOR)
    result = _scan(str(project), f"--fail-under={value}")
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output


def test_empty_sieves_option_exits_2(project: Path):
    result = _scan(str(project), "--sieves", "")
    assert result.exit_code == 2, result.output


@pytest.mark.parametrize("fmt", ["json", "sarif"])
def test_plain_diff_with_no_changes_keeps_stdout_machine_readable(repo: Path, fmt: str):
    (repo / "clean.py").write_text(CLEAN)  # back to the committed content: nothing changed
    result = _scan(str(repo), "--diff", "HEAD", "--format", fmt)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["files"] == [] if fmt == "json" else data["runs"][0]["results"] == []


def test_plain_diff_sees_a_changed_file_with_a_non_ascii_name(repo: Path):
    name = "weirdÿ.py"
    (repo / name).write_text(CLEAN)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add weird file")  # also commits the fixture's clean.py edit
    (repo / name).write_text(CLEAN + "\n\nLIMIT = 3\n")
    result = _scan(str(repo), "--diff", "HEAD", "--format", "json")
    assert result.exit_code == 0, result.output
    assert [Path(f["path"]).name for f in json.loads(result.stdout)["files"]] == [name]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX FIFOs")
def test_fifo_with_a_source_extension_does_not_hang_the_scan(project: Path):
    os.mkfifo(project / "pipe.py")
    done = _scan_subprocess(str(project), "--format", "json", cwd=project)
    assert done.returncode == 0, done.stderr
    assert [Path(f["path"]).name for f in json.loads(done.stdout)["files"]] == ["clean.py"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX FIFOs")
def test_fifo_as_config_is_a_tool_error_not_a_hang(project: Path):
    os.mkfifo(project / ".codesieve.yml")
    done = _scan_subprocess(str(project), cwd=project)
    assert done.returncode == 2, done.stderr
    assert ".codesieve.yml" in done.stderr
    assert "Traceback" not in done.stderr


def test_crashed_file_is_reported_exactly_once(project: Path, crashing_scan):
    (project / "boom.py").write_text(CLEAN)
    result = _scan(str(project), "--format", "json")
    assert result.stderr.count("sieve exploded") == 1, result.stderr


def test_failed_diff_prints_one_line_without_gits_own_noise(repo: Path):
    done = _scan_subprocess(str(repo), "--diff", "no-such-ref", cwd=repo)
    assert done.returncode == 2, done.stderr
    assert "fatal:" not in done.stderr
    assert len(done.stderr.strip().splitlines()) == 1, done.stderr
    assert done.stdout == ""


# --- regressions found by independent verification (round 2) ----------------------------------

def test_plain_diff_sees_renamed_files(repo: Path):
    """A rename is a change: git reports it as R, which the old ACM filter dropped."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    _git(repo, "mv", "clean.py", "tidy.py")
    result = _scan(str(repo), "--diff", "HEAD", "--format", "json")
    assert result.exit_code == 0, result.output
    assert [Path(f["path"]).name for f in json.loads(result.stdout)["files"]] == ["tidy.py"]


def test_plain_diff_sees_a_committed_rename_with_edits(repo: Path):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    _git(repo, "mv", "clean.py", "tidy.py")
    (repo / "tidy.py").write_text(CLEAN + "\n\nLIMIT = 3\nOTHER = LIMIT\n")
    _git(repo, "commit", "-q", "-am", "rename and edit")
    result = _scan(str(repo), "--diff", "HEAD~1", "--format", "json")
    assert result.exit_code == 0, result.output
    assert [Path(f["path"]).name for f in json.loads(result.stdout)["files"]] == ["tidy.py"]


def test_plain_diff_and_new_only_agree_on_which_tracked_files_changed(repo: Path):
    """The invariant behind three separate bugs: both modes must scope the same tracked files."""
    for name in ("keep.py", "edit.py", "move.py", "move_edit.py", "na\u00efve.py", "gone.py"):
        (repo / name).write_text(CLEAN)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    (repo / "edit.py").write_text(CLEAN + "\n\nLIMIT = 3\n")
    (repo / "na\u00efve.py").write_text(CLEAN + "\n\nLIMIT = 3\n")
    _git(repo, "mv", "move.py", "moved.py")
    _git(repo, "mv", "move_edit.py", "moved_edit.py")
    (repo / "moved_edit.py").write_text(CLEAN + "\n\nLIMIT = 3\n")
    _git(repo, "rm", "-q", "gone.py")
    (repo / "added.py").write_text(CLEAN)
    _git(repo, "add", "added.py")

    def scoped(*mode: str) -> list[str]:
        result = _scan(str(repo), "--format", "json", *mode)
        assert result.exit_code in (0, 1), result.output
        return sorted(Path(f["path"]).name for f in json.loads(result.stdout)["files"])

    expected = ["added.py", "edit.py", "moved.py", "moved_edit.py", "na\u00efve.py"]
    assert scoped("--diff", "HEAD") == expected
    assert scoped("--diff", "HEAD", "--new-only") == expected


@pytest.mark.parametrize("extra", [(), ("--new-only",)])
def test_empty_diff_ref_is_a_tool_error_not_a_full_scan(repo: Path, extra: tuple[str, ...]):
    result = _scan(str(repo), "--diff=", "--format", "json", *extra)
    assert result.exit_code == 2, result.output
    assert "aggregate_score" not in result.output
