"""Tests for the engine orchestrator."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file, scan
from codesieve.models import Grade

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_scan_file_good():
    config = Config()
    report = scan_file(FIXTURES / "good.py", config)
    assert report.aggregate_score >= 7.0
    assert report.grade in (Grade.A, Grade.B)
    assert len(report.sieve_results) == 7


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
