"""Click CLI for CodeSieve."""

from __future__ import annotations

import sys

import click
from rich.console import Console

from codesieve import __version__
from codesieve.config import Config, generate_default_config
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
@click.option("--fail-under", type=float, default=None, help="Fail if aggregate score is below this threshold")
@click.option("--sieves", type=str, default=None, help="Comma-separated list of sieves to run")
@click.option("--config", "config_path", type=click.Path(), default=None, help="Path to .codesieve.yml")
@click.option("--exclude", "exclude_patterns", type=str, default=None, help="Comma-separated glob patterns to exclude")
@click.option("--diff", "diff_ref", type=str, default=None, is_flag=False, flag_value="HEAD", help="Only scan files changed since REF (default: HEAD)")
def scan_cmd(path: str, fmt: str | None, deterministic: bool, fail_under: float | None,
             sieves: str | None, config_path: str | None, exclude_patterns: str | None,
             diff_ref: str | None):
    """Scan a file or directory for code quality."""
    config = Config.load(config_path)

    # CLI overrides
    if fmt:
        config.format = fmt
    if deterministic:
        config.deterministic = True
    if fail_under is not None:
        config.fail_under = fail_under
    if sieves:
        config.sieves = [s.strip() for s in sieves.split(",")]
    if exclude_patterns:
        config.exclude.extend([p.strip() for p in exclude_patterns.split(",")])

    # Validate sieve names
    for name in config.sieves:
        if name not in SIEVE_REGISTRY:
            click.echo(f"Unknown sieve: {name}. Available: {', '.join(SIEVE_REGISTRY.keys())}", err=True)
            sys.exit(2)

    report = scan(path, config, diff_ref=diff_ref)

    if not report.file_reports:
        click.echo("No supported files found.", err=True)
        sys.exit(2)

    if config.format == "json":
        click.echo(report_to_json(report))
    elif config.format == "sarif":
        click.echo(report_to_sarif(report))
    else:
        console = Console()
        render_scan_report(report, console)

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
