"""Tests for the engine with JavaScript files."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file, scan
from codesieve.models import Grade

FIXTURES = Path(__file__).parent / "fixtures" / "javascript"


def test_scan_js_file_good():
    config = Config()
    report = scan_file(FIXTURES / "good.js", config)
    assert report.aggregate_score >= 7.0
    assert report.grade in (Grade.A, Grade.B)
    assert len(report.sieve_results) == 10
    assert report.language == "javascript"


def test_scan_js_file_bad():
    config = Config()
    report = scan_file(FIXTURES / "bad.js", config)
    assert report.aggregate_score <= 7.0
    assert report.grade in (Grade.B, Grade.C, Grade.D, Grade.F)


def test_scan_js_directory():
    config = Config()
    report = scan(FIXTURES, config)
    assert len(report.file_reports) == 2
    assert report.aggregate_score > 0
    assert all(r.language == "javascript" for r in report.file_reports)
