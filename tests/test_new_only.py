"""Acceptance tests for ``codesieve scan --diff REF --new-only``.

New-only mode reports, and fails on, only the findings that sit on lines added
since the merge-base of REF and HEAD (working tree and untracked files
included). The whole-file score is still computed and shown, but it does not
decide the exit code in this mode.

Everything goes through the CLI with ``--format json`` against a real temp git
repo, so the tests pin behaviour and the JSON contract, not internals.

Exit codes in new-only mode: 0 = no new findings, 1 = new findings,
2 = the diff scope could not be computed (never a silent full scan).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codesieve.cli import main

CLEAN_FN = (
    "def price(amount: float) -> float:\n"
    '    """Return the price."""\n'
    "    return amount\n"
)
# MagicNumbers flags the literal on the `return` line of each of these.
OLD_FN = (
    "\n\n"
    "def old_fee(amount: float) -> float:\n"
    '    """Return the fee."""\n'
    "    return amount * 4217\n"
)
NEW_FN = (
    "\n\n"
    "def new_fee(amount: float) -> float:\n"
    '    """Return the fee."""\n'
    "    return amount * 9931\n"
)
HARMLESS_FN = (
    "\n\n"
    "def label(name: str) -> str:\n"
    '    """Return the label."""\n'
    "    return name\n"
)
OLD_LINE = 8   # `return amount * 4217` in CLEAN_FN + OLD_FN
NEW_LINE = 13  # `return amount * 9931` in CLEAN_FN + OLD_FN + NEW_FN


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo on branch ``main`` with one commit: legacy.py (one old finding) and other.py (clean)."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "legacy.py").write_text(CLEAN_FN + OLD_FN)
    (root / "other.py").write_text(CLEAN_FN)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _run(root: Path, *extra: str):
    return CliRunner().invoke(main, ["scan", str(root), "--format", "json", *extra])


def _json(result) -> dict:
    return json.loads(getattr(result, "stdout", result.output))


def _new(data: dict) -> list[tuple[str, int, str]]:
    """(file name, line, sieve) for every new finding in a JSON report."""
    return sorted(
        (Path(f["path"]).name, nf["line"], nf["sieve"])
        for f in data["files"]
        for nf in f["new_findings"]
    )


def test_sanity_fixture_has_the_old_finding(repo: Path):
    """Guard for every test below: a plain scan does flag the old literal on OLD_LINE."""
    data = _json(_run(repo))
    legacy = next(f for f in data["files"] if f["path"].endswith("legacy.py"))
    lines = [x["line"] for s in legacy["sieves"] if s["name"] == "MagicNumbers" for x in s["findings"]]
    assert lines == [OLD_LINE]


def test_old_finding_on_untouched_line_does_not_fail(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + HARMLESS_FN)
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 0, result.output
    data = _json(result)
    assert data["new_only"] is True
    assert data["new_finding_count"] == 0
    assert _new(data) == []
    assert [Path(f["path"]).name for f in data["files"]] == ["legacy.py"]


def test_new_finding_on_added_line_fails_with_exit_1(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    data = _json(result)
    assert data["new_finding_count"] == 1
    assert _new(data) == [("legacy.py", NEW_LINE, "MagicNumbers")]
    message = data["files"][0]["new_findings"][0]["message"]
    assert "9931" in message and "4217" not in message


def test_whole_file_score_is_kept_and_all_findings_still_listed(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    plain = _json(_run(repo / "legacy.py"))["files"][0]
    scoped = _json(_run(repo, "--diff", "HEAD", "--new-only"))["files"][0]
    assert scoped["aggregate_score"] == plain["aggregate_score"]
    assert scoped["grade"] == plain["grade"]
    assert scoped["sieves"] == plain["sieves"]  # old finding is still in the full list


def test_untracked_file_is_in_scope_and_every_line_counts_as_added(repo: Path):
    (repo / "fresh.py").write_text(CLEAN_FN + NEW_FN)  # never `git add`ed
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert _new(_json(result)) == [("fresh.py", 8, "MagicNumbers")]


def test_gitignored_untracked_file_is_not_in_scope(repo: Path):
    (repo / ".gitignore").write_text("generated.py\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "ignore")
    (repo / "generated.py").write_text(CLEAN_FN + NEW_FN)
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 0, result.output


def test_staged_and_committed_additions_count(repo: Path):
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    _git(repo, "commit", "-q", "-am", "add new_fee")
    result = _run(repo, "--diff", "main", "--new-only")
    assert result.exit_code == 1, result.output
    assert _new(_json(result)) == [("legacy.py", NEW_LINE, "MagicNumbers")]


def test_scope_is_the_merge_base_not_the_tip_of_ref(repo: Path):
    """Work that landed on main after the branch point is not this branch's change."""
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + HARMLESS_FN)
    _git(repo, "commit", "-q", "-am", "harmless change")
    _git(repo, "checkout", "-q", "main")
    (repo / "other.py").write_text(CLEAN_FN + NEW_FN)  # someone else's finding, on main only
    _git(repo, "commit", "-q", "-am", "main moves on")
    merge_base = _git(repo, "merge-base", "main", "feature")
    _git(repo, "checkout", "-q", "feature")

    result = _run(repo, "--diff", "main", "--new-only")
    assert result.exit_code == 0, result.output
    data = _json(result)
    assert [Path(f["path"]).name for f in data["files"]] == ["legacy.py"]
    assert data["base"] == merge_base


def test_removing_lines_adds_nothing(repo: Path):
    (repo / "legacy.py").write_text(OLD_FN.lstrip("\n"))  # dropped price(); the old literal moved up
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 0, result.output
    assert _json(result)["new_finding_count"] == 0


def test_editing_the_flagged_line_itself_makes_it_new(repo: Path):
    (repo / "legacy.py").write_text((CLEAN_FN + OLD_FN).replace("4217", "4218"))
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert _new(_json(result)) == [("legacy.py", OLD_LINE, "MagicNumbers")]


def test_fail_under_does_not_decide_the_exit_code_in_new_only_mode(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + HARMLESS_FN)
    result = _run(repo, "--diff", "HEAD", "--new-only", "--fail-under", "10.1")
    assert result.exit_code == 0, result.output


def test_clean_tree_exits_zero(repo: Path):
    result = CliRunner().invoke(main, ["scan", str(repo), "--diff", "HEAD", "--new-only"])
    assert result.exit_code == 0, result.output
    assert "No changed files" in result.output


def test_excluded_changed_file_stays_excluded(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = _run(repo, "--diff", "HEAD", "--new-only", "--exclude", "legacy.py")
    assert result.exit_code == 0, result.output


# --- the diff scope cannot be computed: exit 2, never a silent full scan ---------------------

def test_unknown_ref_is_exit_2(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = _run(repo, "--diff", "no-such-ref", "--new-only")
    assert result.exit_code == 2, result.output
    assert "No such option" not in result.output
    assert "no-such-ref" in result.output


def test_ref_that_looks_like_an_option_is_exit_2_and_runs_nothing(repo: Path):
    marker = repo / "pwned"
    result = _run(repo, f"--diff=--output={marker}", "--new-only")
    assert result.exit_code == 2, result.output  # Click or diffscope may reject it; both are fine
    assert not marker.exists()


def test_outside_a_git_repo_is_exit_2(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "m.py").write_text(CLEAN_FN + NEW_FN)
    result = _run(plain, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 2, result.output
    assert "No such option" not in result.output


def test_new_only_without_diff_is_exit_2(repo: Path):
    result = _run(repo, "--new-only")
    assert result.exit_code == 2, result.output
    assert "No such option" not in result.output


# --- other output formats and the unchanged default --------------------------------------------

def test_terminal_output_names_the_new_finding_count(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = CliRunner().invoke(main, ["scan", str(repo), "--diff", "HEAD", "--new-only"])
    assert result.exit_code == 1, result.output
    assert "New findings: 1" in result.output
    assert "9931" in result.output


def test_sarif_lists_only_new_findings(repo: Path):
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = CliRunner().invoke(main, ["scan", str(repo), "--format", "sarif", "--diff", "HEAD", "--new-only"])
    assert result.exit_code == 1, result.output
    results = json.loads(getattr(result, "stdout", result.output))["runs"][0]["results"]
    lines = [r["locations"][0]["physicalLocation"]["region"]["startLine"] for r in results]
    assert lines == [NEW_LINE]


def test_plain_diff_without_new_only_is_unchanged(repo: Path):
    """--diff alone keeps grading whole files: no new_* keys, exit code from --fail-under only."""
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = _run(repo, "--diff", "HEAD")
    assert result.exit_code == 0, result.output
    data = _json(result)
    assert "new_only" not in data and "new_finding_count" not in data
    assert "new_findings" not in data["files"][0]


# --- regressions found by independent verification (round 1) ----------------------------------

def test_pure_rename_adds_no_lines(repo: Path):
    _git(repo, "mv", "legacy.py", "renamed.py")  # byte-identical content, staged rename
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 0, result.output
    assert _json(result)["new_finding_count"] == 0


def test_rename_plus_edit_counts_only_the_added_lines(repo: Path):
    _git(repo, "mv", "legacy.py", "renamed.py")
    (repo / "renamed.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    result = _run(repo, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert _new(_json(result)) == [("renamed.py", NEW_LINE, "MagicNumbers")]


def test_committed_rename_on_a_branch_adds_no_lines(repo: Path):
    _git(repo, "checkout", "-q", "-b", "feature")
    _git(repo, "mv", "legacy.py", "renamed.py")
    _git(repo, "commit", "-q", "-m", "rename")
    result = _run(repo, "--diff", "main", "--new-only")
    assert result.exit_code == 0, result.output


def test_unreadable_untracked_files_do_not_abort_the_scan(repo: Path):
    """Junk that will never be scanned must not decide the exit code."""
    junk = repo / "junk.dat"
    junk.write_text("x")
    junk.chmod(0o000)
    (repo / "dangling.dat").symlink_to(repo / "does-not-exist")
    (repo / "legacy.py").write_text(CLEAN_FN + OLD_FN + NEW_FN)
    try:
        result = _run(repo, "--diff", "HEAD", "--new-only")
    finally:
        junk.chmod(0o644)
    assert result.exit_code == 1, result.output
    assert _new(_json(result)) == [("legacy.py", NEW_LINE, "MagicNumbers")]


@pytest.mark.parametrize("target", ["other.py", "."])
def test_empty_scope_is_still_a_valid_json_report(repo: Path, target: str):
    """Nothing in scope (unchanged file, or a clean tree) is a clean report, not plain text."""
    result = _run(repo / target, "--diff", "HEAD", "--new-only")
    assert result.exit_code == 0, result.output
    data = _json(result)
    assert data["new_only"] is True
    assert data["new_finding_count"] == 0
    assert data["files"] == []
    assert data["base"] == _git(repo, "rev-parse", "HEAD")


def test_empty_scope_is_still_valid_sarif(repo: Path):
    result = CliRunner().invoke(
        main, ["scan", str(repo), "--format", "sarif", "--diff", "HEAD", "--new-only"])
    assert result.exit_code == 0, result.output
    assert json.loads(getattr(result, "stdout", result.output))["runs"][0]["results"] == []


def test_empty_scope_terminal_output_states_zero_new_findings(repo: Path):
    result = CliRunner().invoke(main, ["scan", str(repo), "--diff", "HEAD", "--new-only"])
    assert result.exit_code == 0, result.output
    assert "No changed files" in result.output
    assert "New findings: 0" in result.output
