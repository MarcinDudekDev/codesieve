"""Tests for the CLI interface."""

import json
import os
import tempfile
from pathlib import Path

from click.testing import CliRunner

from codesieve.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_scan_terminal():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "good.py")])
    assert result.exit_code == 0
    assert "CodeSieve Report" in result.output
    assert "AGGREGATE" in result.output


def test_scan_json():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "good.py"), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "aggregate_score" in data
    assert "files" in data
    assert len(data["files"]) == 1


def test_scan_sarif():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "good.py"), "--format", "sarif"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["version"] == "2.1.0"
    assert "runs" in data
    assert data["runs"][0]["tool"]["driver"]["name"] == "CodeSieve"


def test_fail_under_pass():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "good.py"), "--fail-under", "1.0"])
    assert result.exit_code == 0


def test_fail_under_fail():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "bad.py"), "--fail-under", "9.0"])
    assert result.exit_code == 1


def test_sieves_filter():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "good.py"), "--sieves", "KISS", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    sieves = data["files"][0]["sieves"]
    assert len(sieves) == 1
    assert sieves[0]["name"] == "KISS"


def test_unknown_sieve_error():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "good.py"), "--sieves", "FakeSieve"])
    assert result.exit_code == 2
    assert "Unknown sieve" in result.output


def test_sieves_list():
    runner = CliRunner()
    result = runner.invoke(main, ["sieves"])
    assert result.exit_code == 0
    assert "KISS" in result.output
    assert "Nesting" in result.output
    assert "9 sieves" in result.output


def test_init_creates_file():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(main, ["init"], catch_exceptions=False, env={"HOME": tmpdir})
        # Use isolated filesystem
        with runner.isolated_filesystem(temp_dir=tmpdir):
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert Path(".codesieve.yml").exists()


def test_init_fails_if_exists():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".codesieve.yml").write_text("existing")
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 1
        assert "already exists" in result.output


def test_init_force_overwrites():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".codesieve.yml").write_text("old content")
        result = runner.invoke(main, ["init", "--force"])
        assert result.exit_code == 0
        content = Path(".codesieve.yml").read_text()
        assert "KISS" in content  # Should have default config now


def test_scan_nonexistent_path():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "/nonexistent/path/file.py"])
    assert result.exit_code != 0


def test_scan_with_exclude():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES), "--exclude", "**/bad.py", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    paths = [f["path"] for f in data["files"]]
    assert not any("bad.py" in p for p in paths)
