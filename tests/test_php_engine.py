"""Tests for the engine with PHP files."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file, scan
from codesieve.models import Grade

FIXTURES = Path(__file__).parent / "fixtures" / "php"


def test_scan_php_file_good():
    config = Config()
    report = scan_file(FIXTURES / "good.php", config)
    assert report.aggregate_score >= 7.0
    assert report.grade in (Grade.A, Grade.B)
    assert len(report.sieve_results) == 8
    assert report.language == "php"


def test_scan_php_file_bad():
    config = Config()
    report = scan_file(FIXTURES / "bad.php", config)
    assert report.aggregate_score <= 5.0
    assert report.grade in (Grade.C, Grade.D, Grade.F)


def test_scan_php_directory():
    config = Config()
    report = scan(FIXTURES, config)
    assert len(report.file_reports) == 2
    assert report.aggregate_score > 0


def test_scan_mixed_directory():
    """Scanning a directory with Python, PHP, JS, and TS files."""
    config = Config()
    fixtures_root = Path(__file__).parent / "fixtures"
    report = scan(fixtures_root, config)
    languages = {r.language for r in report.file_reports}
    assert "python" in languages
    assert "php" in languages
    assert "javascript" in languages
    assert "typescript" in languages
    assert len(report.file_reports) == 8  # 2 python + 2 php + 2 js + 2 ts
