"""Characterization tests for engine.scan / scan_file edge branches.

Pins currently-uncovered behavior: the deterministic-sieve filter and the
per-file error-resilience branch in the scan loop (the catch-all that
codesieve's ErrorHandling sieve flags — pinned here so the current contract is
documented before anyone refactors it).
"""

from pathlib import Path

from codesieve import engine
from codesieve.config import Config
from codesieve.engine import scan, scan_file
from codesieve.models import SieveType

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_scan_file_deterministic_filters_to_deterministic_sieves():
    # scan_file: `if config.deterministic` branch (line 69).
    full = scan_file(FIXTURES / "good.py", Config())
    determ = scan_file(FIXTURES / "good.py", Config(deterministic=True))
    assert 1 <= len(determ.sieve_results) <= len(full.sieve_results)
    # every sieve that ran under deterministic=True is a deterministic sieve
    for r in determ.sieve_results:
        sieve = engine.SIEVE_REGISTRY[r.name]()
        assert sieve.sieve_type == SieveType.DETERMINISTIC


def test_scan_continues_past_per_file_errors(tmp_path, monkeypatch, capsys):
    # scan loop: except branch (lines 127-129) + empty-reports short-circuit (132).
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")

    def boom(_filepath, _config):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(engine, "scan_file", boom)
    report = scan(tmp_path, Config())

    # all files raised -> nothing collected -> empty report, no crash (resilience)
    assert len(report.file_reports) == 0
    assert "Error scanning" in capsys.readouterr().err


def test_scan_survives_one_bad_file_among_good(tmp_path, monkeypatch, capsys):
    # Same branch, but proves the survivors are still scanned (the point of the catch-all).
    good = tmp_path / "good.py"
    good.write_text("def f(x):\n    return x\n")
    bad = tmp_path / "bad.py"
    bad.write_text("def g(y):\n    return y\n")

    real_scan_file = engine.scan_file

    def selective(filepath, config):
        if Path(filepath).name == "bad.py":
            raise ValueError("boom")
        return real_scan_file(filepath, config)

    monkeypatch.setattr(engine, "scan_file", selective)
    report = scan(tmp_path, Config())

    scanned = {Path(r.path).name for r in report.file_reports}
    assert scanned == {"good.py"}
    assert "Error scanning" in capsys.readouterr().err
