"""Scan orchestrator — parse files, run sieves, aggregate results."""

from __future__ import annotations

import os
from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path

from codesieve import standards
from codesieve.config import Config
from codesieve.models import FileReport, ScanReport, SieveType
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
from codesieve.sieves.comments import CommentsSieve
from codesieve.sieves.dry import DrySieve
from codesieve.suppression import apply_suppressions

SIEVE_REGISTRY: dict[str, type[BaseSieve]] = {
    "KISS": KissSieve,
    "Nesting": NestingSieve,
    "Naming": NamingSieve,
    "ErrorHandling": ErrorHandlingSieve,
    "TypeHints": TypeHintsSieve,
    "MagicNumbers": MagicNumbersSieve,
    "GuardClauses": GuardClausesSieve,
    "DeprecatedAPI": DeprecatedAPISieve,
    "Comments": CommentsSieve,
    "DRY": DrySieve,
}


_SUPPORTED_GLOBS = ("*.py", "*.php", "*.js", "*.jsx", "*.ts", "*.tsx", "*.go")


def _matches_prefix(parts: tuple[str, ...], pat: tuple[str, ...]) -> bool:
    """True if `pat` consumes some leading run of `parts`, `**` spanning any number of segments.

    Prefix semantics is what makes an excluded directory exclude its contents.
    Tracks the set of reachable positions, so it is O(len(parts) * len(pat))
    however many `**` the pattern holds.
    """
    positions = {0}
    for seg in pat:
        if seg == "**":
            positions = set(range(min(positions), len(parts) + 1))
        else:
            positions = {i + 1 for i in positions if i < len(parts) and fnmatchcase(parts[i], seg)}
        if not positions:
            return False
    return True


def _compile_excludes(root: Path, exclude: list[str]) -> list[tuple[str, ...]]:
    """Turn exclude patterns into root-relative segment tuples, gitignore-style.

    A leading `/` or `./`, or an absolute path under the root, anchors the
    pattern to the scan root. Anything else floats: it gets a leading `**`, so a
    bare name (`.venv`) or `tests/*` matches at any depth. `.` segments and runs
    of `**` are dropped.
    """
    root_prefixes = {p.as_posix().rstrip("/") + "/" for p in (root.absolute(), root.resolve())}
    compiled = []
    for pat in exclude:
        for prefix in root_prefixes:
            if pat.startswith(prefix):
                pat = "/" + pat[len(prefix):]
                break
        anchored = pat.startswith(("/", "./"))
        segments: list[str] = []
        for s in pat.split("/"):
            if s in ("", ".") or (s == "**" and segments[-1:] == ["**"]):
                continue
            segments.append(s)
        if not segments:
            continue
        if not anchored and segments[0] != "**":
            segments.insert(0, "**")
        compiled.append(tuple(segments))
    return compiled


def _is_excluded(rel_parts: tuple[str, ...], patterns: list[tuple[str, ...]]) -> bool:
    """True if a path (segments relative to the scan root) falls under any compiled pattern."""
    return any(_matches_prefix(rel_parts, segments) for segments in patterns)


def _collect_files(path: Path, exclude: list[str]) -> list[Path]:
    """Collect all supported files from a path, respecting exclusions."""
    if path.is_file():
        lang = detect_language(str(path))
        return [path] if lang else []

    patterns = _compile_excludes(path, exclude)
    files = []
    for dirpath, dirnames, filenames in os.walk(path):
        base = Path(dirpath)
        rel = base.relative_to(path).parts
        dirnames[:] = sorted(d for d in dirnames if not _is_excluded(rel + (d,), patterns))
        for name in filenames:
            if not any(fnmatchcase(name, g) for g in _SUPPORTED_GLOBS):
                continue
            if _is_excluded(rel + (name,), patterns):
                continue
            if detect_language(str(base / name)):
                files.append(base / name)
    return sorted(files)


def scan_file(filepath: str | Path, config: Config) -> FileReport:
    """Scan a single file through configured sieves."""
    filepath = Path(filepath)
    parsed = ParsedFile(str(filepath), standard=config.standard)

    sieves_to_run = [
        SIEVE_REGISTRY[name]()
        for name in config.sieves
        if name in SIEVE_REGISTRY
    ]

    if config.deterministic:
        sieves_to_run = [s for s in sieves_to_run if s.sieve_type == SieveType.DETERMINISTIC]

    results = [sieve.analyze(parsed) for sieve in sieves_to_run]
    results = apply_suppressions(results, parsed)

    agg = weighted_average(results, config.weights)
    grade = score_to_grade(agg)

    return FileReport(
        path=str(filepath),
        language=parsed.language,
        standard=parsed.standard,
        line_count=parsed.line_count,
        sieve_results=results,
        aggregate_score=agg,
        grade=grade,
    )


def _collect_diff_files(path: Path, ref: str) -> set[Path] | None:
    """Collect files changed since ref using git diff; None when git cannot answer.

    An empty set means "nothing changed" and None means "no diff available"
    (not a repo, bad ref, no git), so callers can tell the two apart.
    """
    import shutil
    import subprocess
    git = shutil.which("git") or "git"
    try:
        # Fixed git argv, no shell; ref is a git revision, not shell input.
        root = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "--show-toplevel"],
            cwd=str(path if path.is_dir() else path.parent),
            text=True,
        ).strip()
        diff_output = subprocess.check_output(  # noqa: S603
            [git, "diff", "--name-only", "--diff-filter=ACM", ref],
            cwd=root,
            text=True,
        ).strip()
        if not diff_output:
            return set()
        return {Path(root) / line for line in diff_output.splitlines()}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _resolve_corpus_standard(files: list[Path], config: Config) -> str:
    """Resolve an ``auto`` standard once, from the whole set of PHP files.

    Deciding per file would grade siblings against different standards in a
    codebase with mixed naming; the standard is a property of the codebase.
    """
    sources: list[tuple[str, str, list[str]]] = []
    for f in files:
        if detect_language(str(f)) != "php":
            continue
        try:
            # Parsed, not read: the vote counts declarations from the tree, so a
            # `function foo(` inside a comment, string or heredoc cannot vote.
            parsed = ParsedFile(str(f))
        except (OSError, ValueError):
            continue
        sources.append((str(f), parsed.source_text, parsed.callable_names()))
    return standards.resolve_for_corpus(config.standard, sources)


def scan(path: str | Path, config: Config, diff_ref: str | None = None) -> ScanReport:
    """Scan a file or directory."""
    path = Path(path)
    files = _collect_files(path, config.exclude)

    if diff_ref:
        changed = _collect_diff_files(path, diff_ref)
        if changed is None:
            import sys
            print(f"codesieve: --diff {diff_ref}: git diff unavailable here; scanning all files",
                  file=sys.stderr)
        else:
            wanted = {c.resolve() for c in changed}
            files = [f for f in files if f.resolve() in wanted]

    if not files:
        return ScanReport()

    if config.standard == standards.AUTO:
        config = replace(config, standard=_resolve_corpus_standard(files, config))

    reports = []
    for f in files:
        try:
            reports.append(scan_file(f, config))
        except Exception as e:  # codesieve: ignore[ErrorHandling]  — intentional per-file resilience: one bad file must not abort the whole scan
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
