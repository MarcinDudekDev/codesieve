"""``--new-only`` on files whose line breaks git and the parser count differently.

git only counts ``\\n``. The parser also breaks rows on a lone ``\\r`` (see
test_line_endings.py), so in a file with a stray CR a finding's row is further
down than git's line number for the same code. New-only mode must translate
git's added lines into parser rows before deciding what is new; otherwise a
finding on a freshly added line is silently dropped and the gate passes.

For a CR-only file git sees a single line, so touching it makes every row new.
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
# One git line, three parser rows.
STRAY_CR = 'NOTE = """first\rsecond\rthird"""\n\n\n'
# `\r\r\n`: git counts one break per line, the parser two.
DOUBLE_CR = "ALPHA = 1\r\r\nBETA = 2\r\r\n\n\n"


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.autocrlf", "false")
    return root


def _commit(root: Path, name: str, data: bytes) -> Path:
    target = root / name
    target.write_bytes(data)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return target


def _scan(root: Path):
    result = CliRunner().invoke(
        main, ["scan", str(root), "--format", "json", "--diff", "HEAD", "--new-only"])
    return result, json.loads(getattr(result, "stdout", result.output))


def _new(data: dict) -> list[tuple[int, str]]:
    return sorted(
        (nf["line"], nf["message"])
        for f in data["files"]
        for nf in f["new_findings"]
        if nf["sieve"] == "MagicNumbers"
    )


def _row_of(text: str, needle: str) -> int:
    """1-based parser row of ``needle``: every lone CR, LF or CRLF is one break."""
    rows = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return next(i for i, row in enumerate(rows, 1) if needle in row)


@pytest.mark.parametrize("prefix", [STRAY_CR, DOUBLE_CR], ids=["stray-cr", "cr-cr-lf"])
def test_new_finding_below_a_stray_cr_is_still_new(repo: Path, prefix: str):
    before = prefix + CLEAN_FN + OLD_FN
    target = _commit(repo, "legacy.py", before.encode())
    after = before + NEW_FN
    target.write_bytes(after.encode())

    result, data = _scan(repo)
    assert result.exit_code == 1, result.output
    assert data["new_finding_count"] == 1
    new = _new(data)
    assert [line for line, _ in new] == [_row_of(after, "9931")]
    assert "9931" in new[0][1]


@pytest.mark.parametrize("prefix", [STRAY_CR, DOUBLE_CR], ids=["stray-cr", "cr-cr-lf"])
def test_old_finding_below_a_stray_cr_is_not_new(repo: Path, prefix: str):
    before = prefix + CLEAN_FN + OLD_FN
    target = _commit(repo, "legacy.py", before.encode())
    target.write_bytes((before + HARMLESS_FN).encode())

    result, data = _scan(repo)
    assert result.exit_code == 0, result.output
    assert data["new_finding_count"] == 0


def test_finding_added_above_a_stray_cr_is_new_and_the_old_one_is_not(repo: Path):
    before = CLEAN_FN + OLD_FN + "\n\n" + STRAY_CR
    target = _commit(repo, "legacy.py", before.encode())
    after = CLEAN_FN + NEW_FN + OLD_FN + "\n\n" + STRAY_CR
    target.write_bytes(after.encode())

    result, data = _scan(repo)
    assert result.exit_code == 1, result.output
    assert [line for line, _ in _new(data)] == [_row_of(after, "9931")]


def test_stray_cr_added_together_with_the_finding(repo: Path):
    before = CLEAN_FN + OLD_FN
    target = _commit(repo, "legacy.py", before.encode())
    after = before + "\n\n" + STRAY_CR.rstrip("\n") + NEW_FN
    target.write_bytes(after.encode())

    result, data = _scan(repo)
    assert result.exit_code == 1, result.output
    assert [line for line, _ in _new(data)] == [_row_of(after, "9931")]


def test_touched_cr_only_file_reports_every_finding_as_new(repo: Path):
    before = (CLEAN_FN + OLD_FN).replace("\n", "\r")
    target = _commit(repo, "legacy.py", before.encode())
    after = before + NEW_FN.replace("\n", "\r")
    target.write_bytes(after.encode())

    result, data = _scan(repo)
    assert result.exit_code == 1, result.output
    # git sees one changed line, so it cannot tell the old literal from the new one.
    assert [line for line, _ in _new(data)] == [_row_of(after, "4217"), _row_of(after, "9931")]


def test_untouched_cr_only_file_is_out_of_scope(repo: Path):
    _commit(repo, "legacy.py", (CLEAN_FN + OLD_FN).replace("\n", "\r").encode())
    (repo / "other.py").write_text(CLEAN_FN)

    result, data = _scan(repo)
    assert result.exit_code == 0, result.output
    assert [Path(f["path"]).name for f in data["files"]] == ["other.py"]


def test_untracked_cr_only_file_reports_its_findings_as_new(repo: Path):
    _commit(repo, "other.py", CLEAN_FN.encode())
    source = (CLEAN_FN + OLD_FN).replace("\n", "\r")
    (repo / "fresh.py").write_bytes(source.encode())

    result, data = _scan(repo)
    assert result.exit_code == 1, result.output
    assert [line for line, _ in _new(data)] == [_row_of(source, "4217")]


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_lf_and_crlf_files_keep_git_line_numbers(repo: Path, newline: str):
    before = (CLEAN_FN + OLD_FN).replace("\n", newline)
    target = _commit(repo, "legacy.py", before.encode())
    after = before + NEW_FN.replace("\n", newline)
    target.write_bytes(after.encode())

    result, data = _scan(repo)
    assert result.exit_code == 1, result.output
    assert [line for line, _ in _new(data)] == [13]
