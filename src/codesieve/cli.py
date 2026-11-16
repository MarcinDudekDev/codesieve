"""Click CLI for CodeSieve."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import click
from rich.console import Console

from codesieve import __version__, standards
from codesieve.config import Config, ConfigError, generate_default_config
from codesieve.diffscope import DiffScopeError
from codesieve.engine import scan, SIEVE_REGISTRY
from codesieve.report import render_scan_report, report_to_json, report_to_sarif


@click.group()
@click.version_option(__version__, prog_name="codesieve")
def main():
    """CodeSieve — Grade code through principle-based sieves."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["terminal", "json", "sarif"]), default=None, help="Output format")
@click.option("--deterministic", is_flag=True, default=False, help="Only run deterministic sieves")
@click.option("--fail-under", type=float, default=None,
              help="Fail if aggregate score is below this threshold (finite number >= 0)")
@click.option("--sieves", type=str, default=None, help="Comma-separated list of sieves to run")
@click.option("--config", "config_path", type=click.Path(), default=None,
              help="Path to .codesieve.yml (exit 2 if it does not exist or is invalid)")
@click.option("--config-from-target", is_flag=True, default=False,
              help="Find .codesieve.yml by walking up from the scanned path instead of using the "
                   "current directory, stopping at the repo root. Makes a scan score the same from "
                   "anywhere. Uses plain defaults if the target tree has none; --config wins.")
@click.option("--exclude", "exclude_patterns", type=str, default=None, help="Comma-separated glob patterns to exclude")
@click.option("--standard", type=click.Choice(standards.CHOICES), default=None,
              help="Coding standard to grade against (default: psr; use wordpress for WPCS). "
                   "auto detects the WordPress ecosystem by path/API markers, then pools a "
                   "method-naming vote across the scanned files and only picks wordpress when "
                   "snake_case names are not outnumbered — hybrid codebases (WPCS file and class "
                   "names, camelCase methods) resolve to psr. Set it explicitly to be sure.")
@click.option("--diff", "diff_ref", type=str, default=None, is_flag=False, flag_value="HEAD",
              help="Only scan files changed since REF (default: HEAD); "
                   "exit 2 when git cannot produce the diff")
@click.option("--new-only", is_flag=True, default=False,
              help="With --diff REF, report and fail only on findings on lines added since "
                   "the merge-base of REF (working tree and untracked files included); the "
                   "whole-file score is still shown but --fail-under does not decide the "
                   "exit code.")
def scan_cmd(path: str, fmt: str | None, deterministic: bool,
             fail_under: float | None, sieves: str | None, config_path: str | None,
             config_from_target: bool, exclude_patterns: str | None, standard: str | None,
             diff_ref: str | None, new_only: bool):
    """Scan a file or directory for code quality."""
    if diff_ref is not None and not diff_ref.strip():
        click.echo("--diff needs a ref (or no value at all for HEAD); got an empty string.", err=True)
        sys.exit(2)
    if new_only and not diff_ref:
        click.echo("--new-only requires --diff REF.", err=True)
        sys.exit(2)
    if config_path is not None and not Path(config_path).exists():
        click.echo(f"Config file not found: {config_path}", err=True)
        sys.exit(2)
    try:
        config = (Config.discover(path, config_path) if config_from_target
                  else Config.load(config_path))
    except ConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(2)

    # CLI overrides
    if fmt:
        config.format = fmt
    if deterministic:
        config.deterministic = True
    if fail_under is not None:
        if not math.isfinite(fail_under) or fail_under < 0:
            click.echo(f"--fail-under must be a finite number >= 0, got {fail_under}", err=True)
            sys.exit(2)
        config.fail_under = fail_under
    if sieves is not None:
        if not sieves.strip():
            click.echo("--sieves names no sieves to run.", err=True)
            sys.exit(2)
        config.sieves = [s.strip() for s in sieves.split(",")]
    if standard:
        config.standard = standard
    if exclude_patterns:
        config.exclude.extend([p.strip() for p in exclude_patterns.split(",")])

    # Validate sieve names
    for name in config.sieves:
        if name not in SIEVE_REGISTRY:
            click.echo(f"Unknown sieve: {name}. Available: {', '.join(SIEVE_REGISTRY.keys())}", err=True)
            sys.exit(2)

    try:
        report = scan(path, config, diff_ref=diff_ref, new_only=new_only)
    except DiffScopeError as e:
        click.echo(str(e), err=True)
        sys.exit(2)

    if not report.file_reports and not report.errors:
        if not diff_ref:
            click.echo("No supported files found.", err=True)
            sys.exit(2)
        # An empty diff scope: terminal keeps the plain line, but for
        # --format json|sarif stdout must stay machine-readable, so it falls
        # through to the renderers with the normal empty report.
        if config.format == "terminal":
            click.echo(f"No changed files since {diff_ref}.")
            if not report.new_only:
                return

    if config.format == "json":
        click.echo(report_to_json(report))
    elif config.format == "sarif":
        click.echo(report_to_sarif(report))
    else:
        console = Console()
        render_scan_report(report, console)

    # A crashed file is a tool error: report the survivors, then fail the run.
    # The error line itself is printed once by the engine when the file fails —
    # repeating it here would report every crash twice.
    if report.errors:
        sys.exit(2)

    # In new-only mode the exit code counts new findings; --fail-under does not apply.
    if report.new_only:
        sys.exit(1 if report.new_finding_count else 0)

    # Exit code based on fail_under
    if config.fail_under > 0 and report.aggregate_score < config.fail_under:
        sys.exit(1)


@main.command(name="sieves")
def sieves_cmd():
    """List available sieves."""
    console = Console()
    console.print("[bold]Available Sieves:[/bold]\n")
    for name, cls in SIEVE_REGISTRY.items():
        sieve = cls()
        console.print(f"  [bold cyan]{name:12s}[/bold cyan] {sieve.sieve_type.value:14s} {sieve.description}")
    console.print(f"\n  Total: {len(SIEVE_REGISTRY)} sieves")


@main.command()
@click.option("--force", is_flag=True, default=False, help="Overwrite existing .codesieve.yml")
def init(force: bool):
    """Create a .codesieve.yml config file."""
    from pathlib import Path
    target = Path.cwd() / ".codesieve.yml"
    if target.exists() and not force:
        click.echo(".codesieve.yml already exists. Use --force to overwrite.", err=True)
        sys.exit(1)
    target.write_text(generate_default_config())
    click.echo(f"Created {target}")
