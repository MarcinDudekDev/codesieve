"""Acceptance tests for the config lock and strict config keys.

Config lock: lowering ``fail_under`` or adding an ``exclude`` is the cheapest
way to turn a quality gate green. When a scan is scoped with ``--diff`` and a
``.codesieve.yml`` is itself part of the change (modified, added, untracked,
deleted or renamed since the diff base), the scan reports a ``config-lock``
finding and exits 1 - unless ``CODESIEVE_ALLOW_CONFIG_CHANGE=1`` is set.

Strict keys: an unknown key in ``.codesieve.yml`` (a typo such as
``fail-under``) used to be ignored silently, which switches the gate off. It is
now a config error: exit 2, naming the key.
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
HARMLESS = (
    "\n\n"
    "def label(name: str) -> str:\n"
    '    """Return the label."""\n'
    "    return name\n"
)
BASE_CONFIG = "fail_under: 5\n"
LOOSER_CONFIG = "fail_under: 0\n"
ALLOW = {"CODESIEVE_ALLOW_CONFIG_CHANGE": "1"}


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repo on ``main`` with a committed .codesieve.yml and one clean file; cwd is the repo."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    (root / ".codesieve.yml").write_text(BASE_CONFIG)
    (root / "app.py").write_text(CLEAN)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    monkeypatch.chdir(root)
    monkeypatch.delenv("CODESIEVE_ALLOW_CONFIG_CHANGE", raising=False)
    return root


def _scan(*args: str, env: dict[str, str] | None = None):
    return CliRunner().invoke(main, ["scan", *args], env=env)


def _json(result) -> dict:
    return json.loads(getattr(result, "stdout", result.output))


def _locked_paths(result) -> list[str]:
    return sorted(entry["path"] for entry in _json(result).get("config_lock", []))


# --- config lock: what trips it ---------------------------------------------------------------

@pytest.mark.parametrize("mode", [("--diff", "HEAD"), ("--diff", "HEAD", "--new-only")])
def test_modified_config_fails_the_scan(repo: Path, mode: tuple[str, ...]):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(repo), "--format", "json", *mode)
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]
    assert "config-lock" in json.dumps(_json(result)["config_lock"])


def test_terminal_output_names_the_rule_and_the_path(repo: Path):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(repo), "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert "[config-lock]" in result.output
    assert ".codesieve.yml" in result.output
    assert "CODESIEVE_ALLOW_CONFIG_CHANGE" in result.output  # tells a human how to allow it


def test_config_change_alone_still_fails(repo: Path):
    """No code changed at all: 'No changed files' must not be a way around the lock."""
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert "[config-lock]" in result.output


@pytest.mark.parametrize("mode", [("--diff", "HEAD"), ("--diff", "HEAD", "--new-only")])
def test_config_change_alone_is_valid_json(repo: Path, mode: tuple[str, ...]):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--format", "json", *mode)
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]
    assert _json(result)["files"] == []


def test_staged_config_change_fails(repo: Path):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    _git(repo, "add", ".codesieve.yml")
    assert _scan(str(repo), "--diff", "HEAD").exit_code == 1


def test_config_change_committed_on_a_branch_fails(repo: Path):
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    _git(repo, "commit", "-q", "-am", "loosen the gate")
    result = _scan(str(repo), "--format", "json", "--diff", "main", "--new-only")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]


def test_deleted_config_fails(repo: Path):
    (repo / ".codesieve.yml").unlink()
    result = _scan(str(repo), "--format", "json", "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]


def test_new_untracked_config_in_a_subdirectory_fails(repo: Path):
    (repo / "pkg").mkdir()
    (repo / "pkg" / ".codesieve.yml").write_text(LOOSER_CONFIG)  # never `git add`ed
    result = _scan(str(repo), "--format", "json", "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == ["pkg/.codesieve.yml"]


def test_renamed_away_config_fails(repo: Path):
    _git(repo, "mv", ".codesieve.yml", "old-config.yml")
    result = _scan(str(repo), "--format", "json", "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert ".codesieve.yml" in _locked_paths(result)


def test_explicit_config_with_another_name_is_locked_too(repo: Path):
    (repo / "ci.yml").write_text(BASE_CONFIG)
    _git(repo, "add", "ci.yml")
    _git(repo, "commit", "-q", "-m", "ci config")
    (repo / "ci.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--format", "json", "--config", str(repo / "ci.yml"), "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == ["ci.yml"]


def test_lock_trips_when_scanning_a_subdirectory(repo: Path):
    (repo / "pkg").mkdir()
    (repo / "pkg" / "mod.py").write_text(CLEAN)
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo / "pkg"), "--format", "json", "--diff", "HEAD", "--new-only")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]


# --- config lock: what does not trip it -----------------------------------------------------

@pytest.mark.parametrize("mode", [("--diff", "HEAD"), ("--diff", "HEAD", "--new-only")])
def test_unchanged_config_does_not_trip_the_lock(repo: Path, mode: tuple[str, ...]):
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(repo), "--format", "json", *mode)
    assert result.exit_code == 0, result.output
    assert _locked_paths(result) == []


def test_env_override_allows_the_change(repo: Path):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(repo), "--format", "json", "--diff", "HEAD", env=ALLOW)
    assert result.exit_code == 0, result.output
    assert _locked_paths(result) == []


@pytest.mark.parametrize("value", ["0", "", "true", "yes"])
def test_only_the_value_1_is_an_override(repo: Path, value: str):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--diff", "HEAD", env={"CODESIEVE_ALLOW_CONFIG_CHANGE": value})
    assert result.exit_code == 1, result.output


def test_without_diff_there_is_no_lock(repo: Path):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--format", "json")
    assert result.exit_code == 0, result.output
    assert "config_lock" not in _json(result)


def test_other_yaml_files_are_not_locked(repo: Path):
    (repo / "settings.yml").write_text("fail_under: 0\n")
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    assert _scan(str(repo), "--diff", "HEAD").exit_code == 0


def test_tool_error_beats_the_lock(repo: Path):
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--diff", "no-such-ref")
    assert result.exit_code == 2, result.output


# --- strict keys --------------------------------------------------------------------------------

@pytest.mark.parametrize("body, key", [
    ("fail-under: 9\n", "fail-under"),
    ("failunder: 9\n", "failunder"),
    ("sieves:\n  - KISS\nexcludes:\n  - tests\n", "excludes"),
    ("Fail_Under: 9\n", "Fail_Under"),
    ("bogus_key: 1\n", "bogus_key"),
])
def test_unknown_top_level_key_is_a_config_error(repo: Path, body: str, key: str):
    (repo / ".codesieve.yml").write_text(body)
    result = _scan(str(repo))
    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert key in result.output
    assert ".codesieve.yml" in result.output
    assert "Traceback" not in result.output


def test_unknown_key_error_lists_the_valid_keys(repo: Path):
    (repo / ".codesieve.yml").write_text("fail-under: 9\n")
    result = _scan(str(repo))
    assert "fail_under" in result.output  # the fix is one glance away


def test_unknown_sieve_name_in_weights_is_a_config_error(repo: Path):
    (repo / ".codesieve.yml").write_text("weights:\n  KISSS: 0.5\n")
    result = _scan(str(repo))
    assert result.exit_code == 2, result.output
    assert "KISSS" in result.output


def test_unknown_key_via_explicit_config_and_config_from_target(repo: Path, tmp_path: Path, monkeypatch):
    bad = tmp_path / "bad.yml"
    bad.write_text("bogus_key: 1\n")
    assert _scan(str(repo), "--config", str(bad)).exit_code == 2
    (repo / ".codesieve.yml").write_text("bogus_key: 1\n")
    monkeypatch.chdir(tmp_path)
    assert _scan(str(repo), "--config-from-target").exit_code == 2


def test_every_documented_key_is_accepted(repo: Path):
    (repo / ".codesieve.yml").write_text(
        "sieves:\n  - KISS\nweights:\n  KISS: 0.2\n  SRP: 0.15\n  Complexity: 0.1\n"
        "fail_under: 0\nstandard: psr\ndeterministic: false\nformat: terminal\nexclude:\n  - skipme\n"
    )
    assert _scan(str(repo)).exit_code == 0


def test_generated_default_config_is_accepted(repo: Path):
    """`codesieve init` must never write a config that the strict loader rejects."""
    (repo / ".codesieve.yml").unlink()
    assert CliRunner().invoke(main, ["init"]).exit_code == 0
    assert _scan(str(repo)).exit_code == 0


# --- regressions found by independent verification (round 1) ----------------------------------
# Invariant: the config a --diff run actually loads from inside the repository must be
# byte-identical to its version at the diff base, or the run is locked. Whether git happens
# to list the file as changed (ignored files, assume-unchanged, case spelling) is irrelevant.

MODES = [("--diff", "HEAD"), ("--diff", "HEAD", "--new-only")]


@pytest.fixture
def bare_repo(repo: Path) -> Path:
    """The repo fixture without a committed config: the common opt-in starting point."""
    _git(repo, "rm", "-q", ".codesieve.yml")
    _git(repo, "commit", "-q", "-m", "no config")
    return repo


@pytest.mark.parametrize("mode", MODES)
def test_gitignored_config_is_loaded_so_it_is_locked(bare_repo: Path, mode: tuple[str, ...]):
    (bare_repo / ".gitignore").write_text(".codesieve.yml\n")
    _git(bare_repo, "add", ".gitignore")
    _git(bare_repo, "commit", "-q", "-m", "ignore the config")
    (bare_repo / ".codesieve.yml").write_text("sieves: [KISS]\n")
    (bare_repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(bare_repo), "--format", "json", *mode)
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]


def test_config_hidden_through_git_info_exclude_is_locked(bare_repo: Path):
    (bare_repo / ".git" / "info").mkdir(exist_ok=True)
    (bare_repo / ".git" / "info" / "exclude").write_text(".codesieve.yml\n")
    (bare_repo / ".codesieve.yml").write_text("exclude:\n  - '**'\n")
    (bare_repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(bare_repo), "--format", "json", "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]


def test_gitignored_explicit_config_is_locked(bare_repo: Path):
    (bare_repo / ".gitignore").write_text("local.yml\n")
    _git(bare_repo, "add", ".gitignore")
    _git(bare_repo, "commit", "-q", "-m", "ignore local.yml")
    (bare_repo / "local.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(bare_repo), "--format", "json", "--config", "local.yml", "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == ["local.yml"]


def test_gitignored_config_in_a_subdirectory_is_locked_via_config_from_target(bare_repo: Path):
    (bare_repo / "pkg").mkdir()
    (bare_repo / "pkg" / "mod.py").write_text(CLEAN)
    (bare_repo / "pkg" / ".gitignore").write_text(".codesieve.yml\n")
    _git(bare_repo, "add", "-A")
    _git(bare_repo, "commit", "-q", "-m", "pkg")
    (bare_repo / "pkg" / ".codesieve.yml").write_text("sieves: [KISS]\n")
    (bare_repo / "pkg" / "mod.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(bare_repo / "pkg"), "--format", "json", "--config-from-target", "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == ["pkg/.codesieve.yml"]


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_config_edit_hidden_from_git_status_is_locked(repo: Path, flag: str):
    _git(repo, "update-index", flag, ".codesieve.yml")
    (repo / ".codesieve.yml").write_text(LOOSER_CONFIG)
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(repo), "--format", "json", "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert _locked_paths(result) == [".codesieve.yml"]


def _case_insensitive(directory: Path) -> bool:
    (directory / "CaseProbe").write_text("")
    try:
        return (directory / "caseprobe").exists()
    finally:
        (directory / "CaseProbe").unlink()


@pytest.mark.parametrize("mode", MODES)
def test_case_variant_config_name_is_locked(bare_repo: Path, tmp_path: Path, mode: tuple[str, ...]):
    """macOS/Windows load `.CodeSieve.yml` when asked for `.codesieve.yml`."""
    if not _case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    (bare_repo / ".CodeSieve.yml").write_text("sieves: [KISS]\n")
    (bare_repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(bare_repo), "--format", "json", *mode)
    assert result.exit_code == 1, result.output
    assert [p.lower() for p in _locked_paths(result)] == [".codesieve.yml"]


def test_explicit_config_spelled_in_another_case_is_locked(repo: Path, tmp_path: Path):
    if not _case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    (repo / "ci.yml").write_text(BASE_CONFIG)
    _git(repo, "add", "ci.yml")
    _git(repo, "commit", "-q", "-m", "ci config")
    (repo / "ci.yml").write_text(LOOSER_CONFIG)
    result = _scan(str(repo), "--format", "json", "--config", "CI.YML", "--diff", "HEAD")
    assert result.exit_code == 1, result.output
    assert [p.lower() for p in _locked_paths(result)] == ["ci.yml"]


@pytest.mark.parametrize("mode", MODES)
def test_committed_unchanged_config_still_passes_with_these_checks(repo: Path, mode: tuple[str, ...]):
    """The stricter check must not lock the normal case: loaded config == base version."""
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(repo), "--format", "json", *mode)
    assert result.exit_code == 0, result.output
    assert _locked_paths(result) == []


def test_unchanged_config_on_a_branch_passes_against_the_merge_base(repo: Path):
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "app.py").write_text(CLEAN + HARMLESS)
    _git(repo, "commit", "-q", "-am", "work")
    result = _scan(str(repo), "--format", "json", "--diff", "main", "--new-only")
    assert result.exit_code == 0, result.output
    assert _locked_paths(result) == []


def test_ignored_config_is_allowed_with_the_override(bare_repo: Path):
    (bare_repo / ".gitignore").write_text(".codesieve.yml\n")
    _git(bare_repo, "add", ".gitignore")
    _git(bare_repo, "commit", "-q", "-m", "ignore the config")
    (bare_repo / ".codesieve.yml").write_text(BASE_CONFIG)
    (bare_repo / "app.py").write_text(CLEAN + HARMLESS)
    result = _scan(str(bare_repo), "--format", "json", "--diff", "HEAD", env=ALLOW)
    assert result.exit_code == 0, result.output


def test_duplicate_key_in_config_is_a_config_error(repo: Path):
    """`fail_under: 9` then `fail_under: 0`: YAML keeps the last one without a word."""
    (repo / ".codesieve.yml").write_text("fail_under: 9\nfail_under: 0\n")
    result = _scan(str(repo))
    assert result.exit_code == 2, result.output
    assert "fail_under" in result.output
    assert "Traceback" not in result.output
