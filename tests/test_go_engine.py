"""Tests for the engine with Go files."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file, scan
from codesieve.models import Grade

FIXTURES = Path(__file__).parent / "fixtures" / "go"


def test_scan_go_file_good():
    config = Config()
    report = scan_file(FIXTURES / "good.go", config)
    assert report.aggregate_score >= 7.0
    assert report.grade in (Grade.A, Grade.B)
    assert len(report.sieve_results) == 10
    assert report.language == "go"


def test_scan_go_file_bad():
    config = Config()
    report = scan_file(FIXTURES / "bad.go", config)
    assert report.aggregate_score < 7.0
    assert report.grade in (Grade.B, Grade.C, Grade.D, Grade.F)


def test_scan_go_directory():
    config = Config()
    report = scan(FIXTURES, config)
    assert len(report.file_reports) == 2
    assert report.aggregate_score > 0
    assert all(r.language == "go" for r in report.file_reports)


def test_go_error_handling_skipped():
    config = Config()
    report = scan_file(FIXTURES / "good.go", config)
    eh = next(r for r in report.sieve_results if r.name == "ErrorHandling")
    assert eh.skipped
    assert "err != nil" in eh.skip_reason


def test_go_type_hints_skipped():
    config = Config()
    report = scan_file(FIXTURES / "good.go", config)
    th = next(r for r in report.sieve_results if r.name == "TypeHints")
    assert th.skipped


def test_go_deprecated_api_skipped():
    config = Config()
    report = scan_file(FIXTURES / "good.go", config)
    dep = next(r for r in report.sieve_results if r.name == "DeprecatedAPI")
    assert dep.skipped


def test_go_good_naming():
    config = Config()
    report = scan_file(FIXTURES / "good.go", config)
    naming = next(r for r in report.sieve_results if r.name == "Naming")
    assert naming.score == 10.0
    assert naming.findings == []


def test_go_magic_numbers_detected():
    config = Config()
    report = scan_file(FIXTURES / "bad.go", config)
    mn = next(r for r in report.sieve_results if r.name == "MagicNumbers")
    assert mn.score < 10.0
    assert len(mn.findings) > 0


def test_go_dry_duplicates_detected():
    config = Config()
    report = scan_file(FIXTURES / "bad.go", config)
    dry = next(r for r in report.sieve_results if r.name == "DRY")
    assert dry.score < 10.0


def test_go_comments_good_coverage():
    config = Config()
    report = scan_file(FIXTURES / "good.go", config)
    comments = next(r for r in report.sieve_results if r.name == "Comments")
    assert comments.score == 10.0


def test_scan_mixed_directory_includes_go():
    config = Config()
    fixtures_root = Path(__file__).parent / "fixtures"
    report = scan(fixtures_root, config)
    languages = {r.language for r in report.file_reports}
    assert "go" in languages
    assert "python" in languages
    assert "php" in languages
    assert "javascript" in languages
    assert "typescript" in languages
    assert len(report.file_reports) == 10  # 2 per language × 5 languages
