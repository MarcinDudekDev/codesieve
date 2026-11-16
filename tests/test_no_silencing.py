"""Acceptance tests for the NoSilencing sieve.

A suppression comment (``# noqa``, ``# type: ignore``, ``phpcs:ignore``,
``@ts-ignore``, ``eslint-disable``, ``//nolint``, and CodeSieve's own
``# codesieve: ignore``) makes a tool stop complaining without fixing the
cause. NoSilencing reports each one, found in real comment nodes only, so the
cheapest way to a better grade costs something. Together with
``--diff REF --new-only`` it becomes "no NEW silencing".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codesieve.cli import main
from codesieve.config import DEFAULTS, Config, generate_default_config
from codesieve.engine import SIEVE_REGISTRY, scan_file
from codesieve.scoring import DEFAULT_WEIGHTS, SCORE_MAX

NAME = "NoSilencing"


def _result(tmp_path: Path, filename: str, source: str, sieves: list[str] | None = None):
    path = tmp_path / filename
    path.write_text(source)
    report = scan_file(path, Config(sieves=sieves or [NAME]))
    return next(r for r in report.sieve_results if r.name == NAME)


def _lines(result) -> list[int]:
    return sorted(f.line for f in result.findings)


# --- registration -------------------------------------------------------------------------------

def test_sieve_is_registered_everywhere():
    assert NAME in SIEVE_REGISTRY
    assert NAME in Config().sieves
    assert NAME in DEFAULTS["sieves"]
    assert DEFAULT_WEIGHTS[NAME] > 0
    assert DEFAULTS["weights"][NAME] == DEFAULT_WEIGHTS[NAME]
    assert NAME in generate_default_config()


def test_sieves_command_lists_it():
    result = CliRunner().invoke(main, ["sieves"])
    assert result.exit_code == 0, result.output
    assert NAME in result.output


# --- Python -------------------------------------------------------------------------------------

PY_SOURCE = (
    "import os  # noqa\n"                                   # 1
    "import sys  # noqa: F401\n"                            # 2
    "\n"
    "\n"
    "def load(path: str) -> int:\n"                         # 5
    '    """Load a value."""\n'
    "    value: int = os.environ[path]  # type: ignore\n"   # 7
    "    other: int = sys.argv  # type: ignore[assignment]\n"  # 8
    "    return value + other  # codesieve: ignore\n"       # 9
)


def test_python_suppression_comments_are_flagged_on_their_lines(tmp_path: Path):
    result = _result(tmp_path, "mod.py", PY_SOURCE)
    assert _lines(result) == [1, 2, 7, 8, 9]


def test_messages_name_the_marker(tmp_path: Path):
    result = _result(tmp_path, "mod.py", PY_SOURCE)
    by_line = {f.line: f.message for f in result.findings}
    assert "noqa" in by_line[1]
    assert "type: ignore" in by_line[7]
    assert "codesieve: ignore" in by_line[9]


def test_clean_file_scores_perfect_with_no_findings(tmp_path: Path):
    source = 'def price(amount: float) -> float:\n    """Return the price."""\n    return amount\n'
    result = _result(tmp_path, "clean.py", source)
    assert result.findings == []
    assert result.score == SCORE_MAX
    assert not result.skipped


def test_markers_inside_strings_and_docstrings_are_not_comments(tmp_path: Path):
    source = (
        "def explain() -> str:\n"
        '    """Mentions # noqa and # type: ignore and # codesieve: ignore in prose."""\n'
        '    hint = "add # noqa to silence it, or // eslint-disable, or @ts-ignore"\n'
        "    return hint\n"
    )
    assert _result(tmp_path, "doc.py", source).findings == []


def test_ordinary_comments_are_not_flagged(tmp_path: Path):
    source = (
        "# The noqalist module ignores nothing; type hints are checked.\n"
        "LIMIT = 3  # ignore values above this\n"
        "# TODO: lint this properly\n"
    )
    assert _result(tmp_path, "plain.py", source).findings == []


def test_prose_that_only_mentions_a_marker_is_not_flagged(tmp_path: Path):
    source = (
        "# Tool tokens such as phpcs:ignore, @ts-ignore and eslint-disable are documented below.\n"
        "# We never use nolint here, and noqa is banned too.\n"
        "LIMIT = 3\n"
    )
    assert _result(tmp_path, "prose.py", source).findings == []


def test_codesieve_marker_is_reported_wherever_suppression_honours_it(tmp_path: Path):
    """suppression.py accepts the marker anywhere in a comment, so it must be visible anywhere."""
    source = (
        "def run() -> None:\n"
        '    """Run."""\n'
        "    try:\n"
        "        pass\n"
        "    except:  # intentional, see docs - codesieve: ignore[ErrorHandling]\n"
        "        raise\n"
    )
    path = tmp_path / "mod.py"
    path.write_text(source)
    report = scan_file(path, Config(sieves=["ErrorHandling", NAME]))
    by_name = {r.name: r for r in report.sieve_results}
    assert by_name["ErrorHandling"].findings == []
    assert [f.line for f in by_name[NAME].findings] == [5]


def test_each_suppression_costs_score_and_findings_carry_their_penalty(tmp_path: Path):
    one = _result(tmp_path, "one.py", "import os  # noqa\n")
    three = _result(tmp_path, "three.py", "import os  # noqa\nimport sys  # noqa\nimport re  # noqa\n")
    assert SCORE_MAX > one.score > three.score
    assert all(f.penalty is not None and f.penalty > 0 for f in three.findings)
    assert three.score == pytest.approx(SCORE_MAX - sum(f.penalty for f in three.findings))


def test_score_never_drops_below_the_scale_minimum(tmp_path: Path):
    result = _result(tmp_path, "many.py", "".join(f"import m{i}  # noqa\n" for i in range(40)))
    assert len(result.findings) == 40
    assert 1.0 <= result.score < 5.0


# --- the sieve cannot be silenced ---------------------------------------------------------------

@pytest.mark.parametrize("marker", [
    "# codesieve: ignore",
    "# codesieve: ignore[NoSilencing]",
    "# codesieve: ignore[nosilencing,ErrorHandling]",
])
def test_codesieve_ignore_cannot_suppress_no_silencing(tmp_path: Path, marker: str, capsys):
    source = f"import os  {marker}\n"
    result = _result(tmp_path, "mod.py", source, sieves=[NAME, "ErrorHandling"])
    assert _lines(result) == [1]
    assert result.score < SCORE_MAX
    assert "unknown sieve name" not in capsys.readouterr().err


def test_inline_ignore_still_suppresses_other_sieves(tmp_path: Path):
    source = (
        "def run() -> None:\n"
        '    """Run."""\n'
        "    try:\n"
        "        pass\n"
        "    except:  # codesieve: ignore[ErrorHandling]\n"
        "        raise\n"
    )
    path = tmp_path / "mod.py"
    path.write_text(source)
    report = scan_file(path, Config(sieves=["ErrorHandling", NAME]))
    by_name = {r.name: r for r in report.sieve_results}
    assert by_name["ErrorHandling"].findings == []      # still silenced, as before
    assert [f.line for f in by_name[NAME].findings] == [5]  # but the silencing itself is reported


# --- regressions found by independent verification ---------------------------------------------

BARE_EXCEPT = (
    "def run() -> None:\n"
    '    """Run."""\n'
    "    try:\n"
    "        pass\n"
    "    except:{comment}\n"
    "        raise\n"
)


@pytest.mark.parametrize("comment", [
    "  # codesieve: ignored",
    "  # xcodesieve: ignore",
    "  # codesieve: ignore_all",
    "  # codesieve: ignorefoo",
    "  # CodeSieve:   Ignore",
    "  # codesieve:ignore[ErrorHandling]",
    "  # note - codesieve: ignore",
])
def test_whatever_suppresses_a_finding_is_itself_reported(tmp_path: Path, comment: str):
    """The invariant: no comment may silence another sieve and stay invisible here."""
    plain = tmp_path / "plain.py"
    plain.write_text(BARE_EXCEPT.format(comment=""))
    silenced = tmp_path / "silenced.py"
    silenced.write_text(BARE_EXCEPT.format(comment=comment))
    config = Config(sieves=["ErrorHandling", NAME])
    before = {r.name: r for r in scan_file(plain, config).sieve_results}
    after = {r.name: r for r in scan_file(silenced, config).sieve_results}
    assert len(after["ErrorHandling"].findings) < len(before["ErrorHandling"].findings), \
        "fixture guard: this comment must really suppress the ErrorHandling finding"
    assert [f.line for f in after[NAME].findings] == [5]


def test_php_heredoc_lines_that_look_like_comments_are_not_comments(tmp_path: Path):
    source = (
        "<?php\n"
        "$x = <<<EOT\n"
        "foo\n"
        "# noqa\n"
        "// phpcs:ignore\n"
        "/* eslint-disable */\n"
        "EOT;\n"
        "// phpcs:ignore\n"          # 8: the only real comment
    )
    assert _lines(_result(tmp_path, "doc.php", source)) == [8]


def test_marker_inside_a_block_comment_is_reported_on_its_own_line(tmp_path: Path):
    source = (
        "/*\n"
        " * Notes about this module.\n"
        " * eslint-disable no-console\n"      # 3
        " */\n"
        "console.log(1);\n"
    )
    assert _lines(_result(tmp_path, "mod.js", source)) == [3]


def test_two_markers_of_the_same_kind_in_one_comment_count_twice(tmp_path: Path):
    source = "/* eslint-disable no-console */ /* eslint-disable no-alert */\nfoo();\n"
    one_comment = "/*\n * eslint-disable no-console\n * eslint-disable no-alert\n */\nfoo();\n"
    assert _lines(_result(tmp_path, "a.js", source)) == [1, 1]
    assert _lines(_result(tmp_path, "b.js", one_comment)) == [2, 3]


@pytest.mark.parametrize("filename, source", [
    ("a.py", "# ruff: noqa\nimport os\n"),
    ("b.py", "# flake8: noqa\nimport os\n"),
    ("c.php", "<?php\n// phpcs:ignoreFile\n$a = 1;\n"),
    ("d.php", "<?php\n// @phpcs:ignore Some.Rule\n$a = 1;\n"),
])
def test_file_level_and_prefixed_forms_are_reported(tmp_path: Path, filename: str, source: str):
    """They silence at least as much as the line-level forms."""
    assert len(_result(tmp_path, filename, source).findings) == 1


# --- other languages ----------------------------------------------------------------------------

def test_php_markers(tmp_path: Path):
    source = (
        "<?php\n"
        "// phpcs:ignore WordPress.Security.NonceVerification\n"   # 2
        "$a = $_POST['a'];\n"
        "# phpcs:disable\n"                                          # 4
        "$b = 1; // an ordinary comment\n"
        "/* phpcs:ignore */\n"                                       # 6
        "$c = 'phpcs:ignore is only text here';\n"
    )
    assert _lines(_result(tmp_path, "page.php", source)) == [2, 4, 6]


def test_typescript_markers(tmp_path: Path):
    source = (
        "// @ts-ignore\n"                                   # 1
        "const a: number = 'x';\n"
        "// @ts-expect-error\n"                             # 3
        "const b: number = 'y';\n"
        "/* eslint-disable no-console */\n"                 # 5
        "console.log(a, b);\n"
        "const s = '// @ts-ignore in a string';\n"
        "// @ts-nocheck\n"                                  # 8
    )
    assert _lines(_result(tmp_path, "mod.ts", source)) == [1, 3, 5, 8]


def test_javascript_markers(tmp_path: Path):
    source = (
        "// eslint-disable-next-line no-undef\n"            # 1
        "foo();\n"
        "bar(); // eslint-disable-line\n"                   # 3
        "// just a note about linting\n"
    )
    assert _lines(_result(tmp_path, "mod.js", source)) == [1, 3]


def test_go_markers(tmp_path: Path):
    source = (
        "package main\n"
        "\n"
        "func main() {\n"
        "\tdoThing() //nolint:errcheck\n"                   # 4
        "\tother() // nolint\n"                             # 5
        "\tprintln(\"//nolint in a string\")\n"
        "}\n"
    )
    assert _lines(_result(tmp_path, "main.go", source)) == [4, 5]


# --- with --new-only: no NEW silencing ----------------------------------------------------------

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "mod.py").write_text("import os  # noqa\n\nLIMIT = len(os.sep)\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _new_only(root: Path):
    return CliRunner().invoke(main, [
        "scan", str(root), "--format", "json", "--sieves", NAME, "--diff", "HEAD", "--new-only"])


def test_old_suppression_on_an_untouched_line_does_not_fail_new_only(repo: Path):
    (repo / "mod.py").write_text("import os  # noqa\n\nLIMIT = len(os.sep)\nOTHER = LIMIT\n")
    result = _new_only(repo)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["new_finding_count"] == 0


def test_newly_added_suppression_fails_new_only(repo: Path):
    (repo / "mod.py").write_text("import os  # noqa\nimport sys  # noqa\n\nLIMIT = len(os.sep)\n")
    result = _new_only(repo)
    assert result.exit_code == 1, result.output
    new = [(nf["sieve"], nf["line"]) for f in json.loads(result.stdout)["files"] for nf in f["new_findings"]]
    assert new == [(NAME, 2)]


def test_marker_added_inside_an_existing_block_comment_fails_new_only(repo: Path):
    (repo / "mod.js").write_text("/*\n * Notes.\n */\nfoo();\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "js")
    (repo / "mod.js").write_text("/*\n * Notes.\n * eslint-disable no-undef\n */\nfoo();\n")
    result = _new_only(repo)
    assert result.exit_code == 1, result.output
    new = [(nf["sieve"], nf["line"]) for f in json.loads(result.stdout)["files"] for nf in f["new_findings"]]
    assert new == [(NAME, 3)]


def test_editing_another_line_of_a_block_comment_does_not_make_its_old_marker_new(repo: Path):
    (repo / "mod.js").write_text("/*\n * Notes.\n * eslint-disable no-undef\n */\nfoo();\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "js")
    (repo / "mod.js").write_text("/* edited opening line\n * Notes.\n * eslint-disable no-undef\n */\nfoo();\n")
    result = _new_only(repo)
    assert result.exit_code == 0, result.output
