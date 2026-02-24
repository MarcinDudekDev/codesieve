"""Scan orchestrator — parse files, run sieves, aggregate results."""

from __future__ import annotations

from pathlib import Path

from codesieve.config import Config
from codesieve.models import FileReport, ScanReport
from codesieve.parser.languages import detect_language
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import weighted_average, score_to_grade
from codesieve.sieves.base import BaseSieve
from codesieve.sieves.kiss import KissSieve
from codesieve.sieves.nesting import NestingSieve
from codesieve.sieves.naming import NamingSieve
from codesieve.sieves.error_handling import ErrorHandlingSieve
from codesieve.sieves.type_hints import TypeHintsSieve
from codesieve.sieves.magic_numbers import MagicNumbersSieve
from codesieve.sieves.guard_clauses import GuardClausesSieve
from codesieve.sieves.deprecated_api import DeprecatedAPISieve

SIEVE_REGISTRY: dict[str, type[BaseSieve]] = {
    "KISS": KissSieve,
    "Nesting": NestingSieve,
    "Naming": NamingSieve,
    "ErrorHandling": ErrorHandlingSieve,
    "TypeHints": TypeHintsSieve,
    "MagicNumbers": MagicNumbersSieve,
    "GuardClauses": GuardClausesSieve,
    "DeprecatedAPI": DeprecatedAPISieve,
}


_SUPPORTED_GLOBS = ("*.py", "*.php")


def _collect_files(path: Path, exclude: list[str]) -> list[Path]:
    """Collect all supported files from a path, respecting exclusions."""
    if path.is_file():
        lang = detect_language(str(path))
        return [path] if lang else []

    files = []
    for pattern in _SUPPORTED_GLOBS:
        for p in sorted(path.rglob(pattern)):
            if any(p.match(pat) for pat in exclude):
                continue
            if detect_language(str(p)):
                files.append(p)
    return sorted(files)


def scan_file(filepath: str | Path, config: Config) -> FileReport:
    """Scan a single file through configured sieves."""
    filepath = Path(filepath)
    parsed = ParsedFile(str(filepath))

    sieves_to_run = [
        SIEVE_REGISTRY[name]()
        for name in config.sieves
        if name in SIEVE_REGISTRY
    ]

    results = [sieve.analyze(parsed) for sieve in sieves_to_run]

    agg = weighted_average(results, config.weights)
    grade = score_to_grade(agg)

    return FileReport(
        path=str(filepath),
        language=parsed.language,
        line_count=parsed.line_count,
        sieve_results=results,
        aggregate_score=agg,
        grade=grade,
    )


def scan(path: str | Path, config: Config) -> ScanReport:
    """Scan a file or directory."""
    path = Path(path)
    files = _collect_files(path, config.exclude)

    if not files:
        return ScanReport()

    reports = []
    for f in files:
        try:
            reports.append(scan_file(f, config))
        except Exception as e:
            from rich.console import Console
            Console(stderr=True).print(f"[red]Error scanning {f}: {e}[/red]")

    if not reports:
        return ScanReport()

    overall = round(sum(r.aggregate_score for r in reports) / len(reports), 1)
    return ScanReport(
        file_reports=reports,
        aggregate_score=overall,
        grade=score_to_grade(overall),
    )
