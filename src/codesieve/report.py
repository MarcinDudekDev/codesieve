"""Output formatting for CodeSieve reports."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table
from rich.text import Text

from codesieve.models import FileReport, ScanReport, SieveType


def _type_label(sieve_type: SieveType) -> str:
    return {"deterministic": "determ.", "llm": "LLM", "hybrid": "hybrid"}[sieve_type.value]


def _score_color(score: float) -> str:
    if score >= 8.0:
        return "green"
    if score >= 6.0:
        return "yellow"
    if score >= 4.0:
        return "dark_orange"
    return "red"


def render_file_report(report: FileReport, console: Console | None = None) -> None:
    """Render a file report as a Rich table."""
    console = console or Console()

    title = f"CodeSieve Report — {report.path} ({report.line_count} lines, {report.language.title()})"
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("Sieve", style="bold", width=14)
    table.add_column("Score", justify="center", width=7)
    table.add_column("Type", width=10)
    table.add_column("Summary")

    for result in report.sieve_results:
        if result.skipped:
            score_text = Text("skip", style="dim")
            table.add_row(result.name, score_text, _type_label(result.sieve_type), result.skip_reason or "")
        else:
            color = _score_color(result.score)
            score_text = Text(f"{result.score:.1f}", style=color)
            table.add_row(result.name, score_text, _type_label(result.sieve_type), result.summary)

    # Aggregate row
    table.add_section()
    agg_color = _score_color(report.aggregate_score)
    agg_text = Text(f"{report.aggregate_score:.1f}", style=f"bold {agg_color}")
    table.add_row("AGGREGATE", agg_text, "", f"Grade: {report.grade.value}")

    console.print(table)
    console.print()


def render_scan_report(report: ScanReport, console: Console | None = None) -> None:
    """Render a full scan report."""
    console = console or Console()
    for fr in report.file_reports:
        render_file_report(fr, console)

    if len(report.file_reports) > 1:
        agg_color = _score_color(report.aggregate_score)
        console.print(
            f"[bold]Overall:[/bold] [{agg_color}]{report.aggregate_score:.1f}[/{agg_color}] "
            f"(Grade: [bold]{report.grade.value}[/bold]) across {len(report.file_reports)} files"
        )


def report_to_json(report: ScanReport) -> str:
    """Serialize a scan report to JSON."""
    data = {
        "aggregate_score": report.aggregate_score,
        "grade": report.grade.value,
        "files": [],
    }
    for fr in report.file_reports:
        file_data = {
            "path": fr.path,
            "language": fr.language,
            "line_count": fr.line_count,
            "aggregate_score": fr.aggregate_score,
            "grade": fr.grade.value,
            "sieves": [],
        }
        for sr in fr.sieve_results:
            sieve_data = {
                "name": sr.name,
                "score": sr.score,
                "type": sr.sieve_type.value,
                "summary": sr.summary,
                "skipped": sr.skipped,
                "findings": [
                    {"message": f.message, "line": f.line, "function": f.function, "severity": f.severity}
                    for f in sr.findings
                ],
            }
            file_data["sieves"].append(sieve_data)
        data["files"].append(file_data)
    return json.dumps(data, indent=2)
