"""Tests for the engine with TypeScript files."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file, scan
from codesieve.models import Grade

FIXTURES = Path(__file__).parent / "fixtures" / "typescript"


def test_scan_ts_file_good():
    config = Config()
    report = scan_file(FIXTURES / "good.ts", config)
    assert report.aggregate_score >= 7.0
    assert report.grade in (Grade.A, Grade.B)
    assert len(report.sieve_results) == 9
    assert report.language == "typescript"


def test_scan_ts_file_bad():
    config = Config()
    report = scan_file(FIXTURES / "bad.ts", config)
    assert report.aggregate_score <= 8.0
    assert report.grade in (Grade.B, Grade.C, Grade.D, Grade.F)


def test_scan_ts_directory():
    config = Config()
    report = scan(FIXTURES, config)
    assert len(report.file_reports) == 2
    assert report.aggregate_score > 0
    assert all(r.language == "typescript" for r in report.file_reports)
