"""Tests for report formatting."""

import json
from io import StringIO
from pathlib import Path

from rich.console import Console

from codesieve.config import Config
from codesieve.engine import scan_file, scan
from codesieve.report import render_file_report, report_to_json, report_to_sarif

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_render_file_report_captures_table():
    config = Config()
    report = scan_file(FIXTURES / "good.py", config)
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    render_file_report(report, console)
    text = output.getvalue()
    assert "CodeSieve Report" in text
    assert "AGGREGATE" in text
    assert "KISS" in text


def test_render_file_report_findings_for_bad():
    config = Config()
    report = scan_file(FIXTURES / "bad.py", config)
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    render_file_report(report, console)
    text = output.getvalue()
    assert "Findings" in text


def test_json_roundtrip_structure():
    config = Config()
    report = scan(FIXTURES, config)
    json_str = report_to_json(report)
    data = json.loads(json_str)
    assert "aggregate_score" in data
    assert "grade" in data
    assert "files" in data
    assert len(data["files"]) == 2
    for f in data["files"]:
        assert "path" in f
        assert "sieves" in f
        assert "aggregate_score" in f


def test_sarif_output_schema():
    config = Config()
    report = scan(FIXTURES / "bad.py", config)
    sarif_str = report_to_sarif(report)
    data = json.loads(sarif_str)
    assert data["version"] == "2.1.0"
    assert "$schema" in data
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["tool"]["driver"]["name"] == "CodeSieve"
    assert len(run["tool"]["driver"]["rules"]) > 0
    assert len(run["results"]) > 0
    # Check a result has expected structure
    result = run["results"][0]
    assert "ruleId" in result
    assert "level" in result
    assert "message" in result


def test_sarif_findings_have_locations():
    config = Config()
    report = scan(FIXTURES / "bad.py", config)
    sarif_str = report_to_sarif(report)
    data = json.loads(sarif_str)
    results_with_loc = [r for r in data["runs"][0]["results"] if "locations" in r]
    assert len(results_with_loc) > 0
    loc = results_with_loc[0]["locations"][0]["physicalLocation"]
    assert "artifactLocation" in loc
    assert "region" in loc
    assert "startLine" in loc["region"]
