"""Tests for --config-from-target: config keyed off the scan target, not the cwd."""

import os
from pathlib import Path

import pytest

from codesieve.config import CONFIG_FILENAME, Config, find_config

CONFIG_YAML = "sieves:\n  - KISS\n  - Naming\nfail_under: 6.5\n"


@pytest.fixture
def project(tmp_path):
    """A repo-shaped tree: .git + config at the root, source nested below."""
    root = tmp_path / "myproject"
    (root / ".git").mkdir(parents=True)
    (root / CONFIG_FILENAME).write_text(CONFIG_YAML)
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    (nested / "app.py").write_text(
        "def add_totals(first_value: int, second_value: int) -> int:\n"
        "    return first_value + second_value\n"
    )
    return root


@pytest.fixture
def elsewhere(tmp_path, monkeypatch):
    """Run from a directory that has no config of its own."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    return other


# --- find_config ---

def test_finds_config_beside_the_target(project):
    assert find_config(project) == project / CONFIG_FILENAME


def test_walks_up_from_a_nested_directory(project):
    assert find_config(project / "src" / "deep") == project / CONFIG_FILENAME


def test_walks_up_from_a_file_not_just_a_directory(project):
    assert find_config(project / "src" / "deep" / "app.py") == project / CONFIG_FILENAME


def test_nearest_config_wins(project):
    inner = project / "src" / CONFIG_FILENAME
    inner.write_text("fail_under: 9.0\n")
    assert find_config(project / "src" / "deep") == inner


def test_stops_at_the_repo_root(tmp_path):
    """A config above the repo root must not leak into the scan."""
    (tmp_path / CONFIG_FILENAME).write_text(CONFIG_YAML)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    assert find_config(repo / "src") is None


def test_returns_none_when_nothing_is_found(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert find_config(plain) is None


# --- Config.discover ---

def test_discover_reads_the_targets_config(project, elsewhere):
    config = Config.discover(project / "src" / "deep")
    assert config.sieves == ["KISS", "Naming"]
    assert config.fail_under == 6.5


def test_discover_ignores_the_cwd_config_entirely(tmp_path, monkeypatch):
    """An unconfigured target gets defaults, NOT whatever config the cwd happens to hold.

    Falling back to the cwd would reintroduce the coupling the flag removes.
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / CONFIG_FILENAME).write_text(CONFIG_YAML)
    monkeypatch.chdir(cwd)

    target = tmp_path / "unconfigured"
    target.mkdir()
    assert Config.discover(target).sieves == Config().sieves


def test_explicit_config_path_beats_discovery(project, tmp_path):
    explicit = tmp_path / "explicit.yml"
    explicit.write_text("fail_under: 3.25\n")
    assert Config.discover(project, explicit).fail_under == 3.25


def test_discover_returns_defaults_when_there_is_no_config_anywhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = Config.discover(tmp_path)
    assert config.sieves == Config().sieves
    assert config.fail_under == 0.0


# --- The behaviour this exists to fix ---

def test_default_load_still_depends_on_cwd(project, elsewhere):
    """Unchanged legacy behaviour: load() ignores the target entirely."""
    assert Config.load().sieves == Config().sieves  # cwd has no config -> defaults


@pytest.mark.parametrize("configured", [True, False])
def test_same_target_scores_the_same_from_any_directory(tmp_path, monkeypatch, configured):
    """The whole point: the verdict must not depend on where you stand.

    Holds whether or not the target tree carries a config — a decoy config in
    one of the working directories must never leak in.
    """
    root = tmp_path / "myproject"
    (root / ".git").mkdir(parents=True)
    if configured:
        (root / CONFIG_FILENAME).write_text(CONFIG_YAML)
    target = root / "src"
    target.mkdir()

    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / CONFIG_FILENAME).write_text("sieves:\n  - Nesting\nfail_under: 1.0\n")

    monkeypatch.chdir(decoy)
    from_decoy = Config.discover(target)
    monkeypatch.chdir(root)
    from_inside = Config.discover(target)

    assert from_decoy.sieves == from_inside.sieves
    assert from_decoy.fail_under == from_inside.fail_under
    assert from_decoy.sieves == (["KISS", "Naming"] if configured else Config().sieves)


def test_cli_flag_is_opt_in(project, elsewhere):
    """Without the flag, nothing about the existing code path changes."""
    from click.testing import CliRunner

    from codesieve.cli import main

    runner = CliRunner()
    target = str(project / "src" / "deep")

    without = runner.invoke(main, ["scan", target, "--format", "json"])
    with_flag = runner.invoke(main, ["scan", target, "--format", "json", "--config-from-target"])

    assert without.exit_code == 0 and with_flag.exit_code == 0
    # The project config narrows the run to 2 sieves; the default run uses all 10.
    assert '"name": "KISS"' in without.output
    assert without.output.count('"name":') > with_flag.output.count('"name":')


def test_relative_target_resolves(project, monkeypatch):
    monkeypatch.chdir(project / "src")
    assert find_config(Path("deep")) == project / CONFIG_FILENAME


def test_discovery_survives_a_target_that_is_the_filesystem_root():
    """Walking up from / must terminate rather than loop or raise."""
    assert find_config(os.sep) is None or isinstance(find_config(os.sep), Path)
