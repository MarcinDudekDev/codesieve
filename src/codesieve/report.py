"""Output formatting for CodeSieve reports."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from rich.console import Console
from rich.table import Table
from rich.text import Text

from codesieve import standards
from codesieve.models import FileReport, ScanReport, SieveType


def _type_label(sieve_type: SieveType) -> str:
    """Short column label for a sieve type, abbreviated to keep the table narrow."""
    return {"deterministic": "determ.", "llm": "LLM", "hybrid": "hybrid"}[sieve_type.value]


def _score_color(score: float) -> str:
    """Rich colour name for a score, green through red as it falls."""
    if score >= 8.0:
        return "green"
    if score >= 6.0:
        return "yellow"
    if score >= 4.0:
        return "dark_orange"
    return "red"


_SEVERITY_COLORS = {"error": "red", "warning": "yellow", "info": "dim"}

CONFIG_LOCK_RULE = "config-lock"
CONFIG_LOCK_MESSAGE = ("config changed in this diff; "
                       "set CODESIEVE_ALLOW_CONFIG_CHANGE=1 to allow it")


def _sarif_uri(path: str) -> str:
    """Render a filesystem path as a SARIF ``artifactLocation.uri``.

    SARIF resolves ``uri`` as a URI reference, so a raw absolute path is wrong
    twice over: an unencoded space breaks the reference, and a path outside the
    repository root cannot be matched to a file at all. The path is made relative
    to the working directory when it lives under it, spelled with POSIX
    separators, and percent-encoded.
    """
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(Path.cwd().resolve())
    except (OSError, ValueError):
        return quote(candidate.as_posix(), safe="/")
    return quote(relative.as_posix(), safe="/")


def render_file_report(report: FileReport, console: Console | None = None) -> None:
    """Render a file report as a Rich table with findings."""
    console = console or Console()

    descriptor = f"{report.line_count} lines, {report.language.title()}"
    if report.standard != standards.DEFAULT:
        descriptor += f", {report.standard} standard"
    title = f"CodeSieve Report — {report.path} ({descriptor})"
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

    # Findings section — in new-only mode only findings on added lines list.
    if report.added_lines is not None:
        all_findings = report.new_findings()
    else:
        all_findings = []
        for result in report.sieve_results:
            if result.skipped:
                continue
            for finding in result.findings:
                all_findings.append((result.name, finding))

    if all_findings:
        all_findings.sort(key=lambda x: x[1].line or 0)
        heading = "New findings" if report.added_lines is not None else "Findings"
        console.print(f"\n  [bold]{heading} ({len(all_findings)}):[/bold]")
        for sieve_name, finding in all_findings:
            color = _SEVERITY_COLORS.get(finding.severity, "dim")
            line_str = f"L{finding.line}" if finding.line else "L?"
            console.print(f"  [{color}]{line_str:>6}  {finding.message}  ({sieve_name})[/{color}]")

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

    if report.new_only:
        short_base = (report.base or "")[:7]
        console.print(f"[bold]New findings: {report.new_finding_count}[/bold] (base {short_base})")

    for locked in report.config_lock or []:
        console.print(f"{locked} [{CONFIG_LOCK_RULE}] {CONFIG_LOCK_MESSAGE}",
                      markup=False, style="red")


def report_to_json(report: ScanReport) -> str:
    """Serialize a scan report to JSON.

    In new-only mode the report gains ``new_only``, ``base`` and
    ``new_finding_count`` at the top level, and a ``new_findings`` list per
    file — while the full ``sieves[].findings`` lists stay unchanged.
    """
    data: dict = {
        "aggregate_score": report.aggregate_score,
        "grade": report.grade.value,
    }
    if report.new_only:
        data["new_only"] = True
        data["base"] = report.base
        data["new_finding_count"] = report.new_finding_count
    if report.config_lock is not None:
        data["config_lock"] = [
            {"path": locked, "rule": CONFIG_LOCK_RULE, "message": CONFIG_LOCK_MESSAGE}
            for locked in report.config_lock
        ]
    data["files"] = []
    for fr in report.file_reports:
        file_data: dict = {
            "path": fr.path,
            "language": fr.language,
            "standard": fr.standard,
            "line_count": fr.line_count,
            "aggregate_score": fr.aggregate_score,
            "grade": fr.grade.value,
            "sieves": [],
        }
        if report.new_only:
            file_data["new_findings"] = [
                {"sieve": name, "message": f.message, "line": f.line,
                 "function": f.function, "severity": f.severity}
                for name, f in fr.new_findings()
            ]
        for sr in fr.sieve_results:
            sieve_data = {
                "name": sr.name,
                "score": None if sr.skipped else sr.score,
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


def report_to_sarif(report: ScanReport) -> str:
    """Serialize a scan report to SARIF 2.1.0 format."""
    from codesieve import __version__

    # Build rules from all sieves seen across files
    rules_seen: dict[str, dict] = {}
    results_list: list[dict] = []

    for fr in report.file_reports:
        new_pairs = fr.new_findings() if report.new_only else None
        for sr in fr.sieve_results:
            if sr.name not in rules_seen:
                rules_seen[sr.name] = {
                    "id": sr.name,
                    "shortDescription": {"text": sr.name},
                    "defaultConfiguration": {"level": "warning"},
                }
            if new_pairs is None:
                findings = sr.findings
            else:
                findings = [f for name, f in new_pairs if name == sr.name]
            for finding in findings:
                severity_map = {"error": "error", "warning": "warning", "info": "note"}
                result_entry: dict = {
                    "ruleId": sr.name,
                    "level": severity_map.get(finding.severity, "note"),
                    "message": {"text": finding.message},
                }
                if finding.line:
                    result_entry["locations"] = [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": _sarif_uri(fr.path)},
                            "region": {"startLine": finding.line},
                        }
                    }]
                results_list.append(result_entry)

    if report.config_lock:
        rules_seen[CONFIG_LOCK_RULE] = {
            "id": CONFIG_LOCK_RULE,
            "shortDescription": {"text": "CodeSieve config changed in this diff"},
            "defaultConfiguration": {"level": "error"},
        }
        for locked in report.config_lock:
            results_list.append({
                "ruleId": CONFIG_LOCK_RULE,
                "level": "error",
                "message": {"text": CONFIG_LOCK_MESSAGE},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": _sarif_uri(locked)}}}],
            })

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "CodeSieve",
                    "version": __version__,
                    "rules": list(rules_seen.values()),
                }
            },
            "results": results_list,
        }],
    }
    return json.dumps(sarif, indent=2)
