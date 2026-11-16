"""Scan orchestrator — parse files, run sieves, aggregate results."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path

from codesieve import standards
from codesieve.config import Config
from codesieve.diffscope import DiffScopeError, config_lock, resolve_scope
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


def _collect_files(path: Path, exclude: list[str],
                   errors: list[tuple[str, str]] | None = None) -> list[Path]:
    """Collect all supported files from a path, respecting exclusions.

    Only regular files are scan candidates (``is_file()`` follows symlinks
    and is False for FIFOs, sockets and devices) — anything else that merely
    carries a source extension would block or crash the parser.

    When ``errors`` is given, each directory os.walk cannot list is appended
    to it as ``(dir, message)`` — otherwise an unreadable directory would
    swallow every file under it with no signal. Excluded directories are
    pruned before descent, so they never reach the walker and never report.
    """
    if path.is_file():
        lang = detect_language(str(path))
        return [path] if lang else []

    def on_walk_error(exc: OSError) -> None:
        """Record the directory ``exc.filename`` that could not be listed."""
        if errors is not None:
            errors.append((str(exc.filename or path), exc.strerror or str(exc)))

    patterns = _compile_excludes(path, exclude)
    files = []
    for dirpath, dirnames, filenames in os.walk(path, onerror=on_walk_error):
        base = Path(dirpath)
        rel = base.relative_to(path).parts
        dirnames[:] = sorted(d for d in dirnames if not _is_excluded(rel + (d,), patterns))
        for name in filenames:
            if not any(fnmatchcase(name, g) for g in _SUPPORTED_GLOBS):
                continue
            if _is_excluded(rel + (name,), patterns):
                continue
            candidate = base / name
            if not candidate.is_file():
                continue
            if detect_language(str(candidate)):
                files.append(candidate)
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


def _disk_key(path: Path) -> tuple[int, int] | None:
    """(st_dev, st_ino) identifying the directory entry itself; None when absent.

    Diff scope is matched by file identity, not name spelling: git's index and
    the directory can disagree on case or unicode normalization for the same
    file. ``lstat``, not ``stat`` or a last-component ``resolve`` — a symlink
    must key as the link, not its target: a file swapped for a symlink
    (status T) is in scope as the link, while the unchanged target is not.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def _collect_diff_files(path: Path, ref: str) -> set[Path] | None:
    """Collect files changed since ref using git diff; None when git cannot answer.

    An empty set means "nothing changed" and None means "no diff available"
    (not a repo, bad ref, no git), so callers can tell the two apart. The
    ref is first required to name a commit: an existing file or directory
    that is not a revision would otherwise be read by ``git diff`` as a
    pathspec and silently narrow the diff to that path. The trailing ``--``
    then pins the boundary so the ref can never be taken as a path.

    ``-z`` output is NUL-separated and unquoted — without it git C-quotes
    non-ASCII names (``"weird\\303\\277.py"``) and the changed file silently
    drops out of the scan. ``surrogateescape`` keeps undecodable names from
    crashing the decode. Git's own stderr goes to DEVNULL so the CLI's error
    line stays the only message the user sees.
    """
    import shutil
    import subprocess
    git = shutil.which("git") or "git"
    try:
        # Fixed git argv, no shell; ref is a git revision, not shell input.
        root = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "--show-toplevel"],
            cwd=str(path if path.is_dir() else path.parent),
            text=True, errors="surrogateescape",
            stderr=subprocess.DEVNULL,
        ).strip()
        subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "--verify", "--quiet", "--end-of-options",
             f"{ref}^{{commit}}"],
            cwd=root,
            text=True, errors="surrogateescape",
            stderr=subprocess.DEVNULL,
        )
        diff_output = subprocess.check_output(  # noqa: S603
            [git, "diff", "--name-only", "-z", "--diff-filter=ACMRT",
             "--end-of-options", ref, "--"],
            cwd=root,
            text=True, errors="surrogateescape",
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    return {Path(root) / name for name in diff_output.split("\0") if name}


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


def scan(path: str | Path, config: Config, diff_ref: str | None = None,
         new_only: bool = False) -> ScanReport:
    """Scan a file or directory.

    With ``new_only`` (requires ``diff_ref``), the scanned files are the
    normally collected ones intersected with the files changed since the
    merge-base of REF and HEAD, and each report records that file's added
    lines so renderers can tell new findings from old ones. Any scope failure
    raises DiffScopeError — for plain ``--diff`` too, there is no full-scan
    fallback: asking for a diff that git cannot produce is a tool error.

    A file that crashes mid-scan is recorded on ``ScanReport.errors`` and the
    surviving files are still reported; the CLI turns a non-empty error list
    into exit 2.
    """
    path = Path(path)
    errors: list[tuple[str, str]] = []
    files = _collect_files(path, config.exclude, errors)
    for target, message in errors:
        print(f"Error scanning {target}: {message}", file=sys.stderr)

    added_by_file: dict[tuple[int, int], set[int] | None] | None = None
    base: str | None = None
    if diff_ref and new_only:
        base, scope = resolve_scope(path, diff_ref)
        added_by_file = {key: lines for name, lines in scope.items()
                         if (key := _disk_key(name)) is not None}
        files = [f for f in files
                 if (key := _disk_key(f)) is not None and key in added_by_file]
    elif diff_ref:
        changed = _collect_diff_files(path, diff_ref)
        if changed is None:
            raise DiffScopeError(
                f"--diff {diff_ref}: git diff is unavailable here "
                "(not a git repository, unknown ref, or git missing)")
        wanted = {key for name in changed if (key := _disk_key(name)) is not None}
        files = [f for f in files
                 if (key := _disk_key(f)) is not None and key in wanted]

    # The config lock: a .codesieve.yml inside the change (or the loaded
    # --config) fails the gate even when nothing scannable changed. It is
    # evaluated only after the diff resolution above, so a bad ref still
    # raises DiffScopeError first, and it runs even when ``files`` is empty.
    lock: list[str] | None = None
    if diff_ref:
        lock = ([] if os.environ.get("CODESIEVE_ALLOW_CONFIG_CHANGE") == "1"
                else config_lock(path, diff_ref, base, config.source_path))

    if not files:
        return ScanReport(new_only=new_only, base=base, errors=errors,
                          config_lock=lock)

    if config.standard == standards.AUTO:
        config = replace(config, standard=_resolve_corpus_standard(files, config))

    reports = []
    for f in files:
        try:
            file_report = scan_file(f, config)
            if added_by_file is not None:
                key = _disk_key(f)
                added = added_by_file.get(key) if key is not None else None
                # None marks an untracked file: every parsed line was added.
                file_report.added_lines = (
                    added if added is not None
                    else set(range(1, file_report.line_count + 1))
                )
            reports.append(file_report)
        except Exception as e:  # codesieve: ignore[ErrorHandling]  — intentional per-file resilience: one bad file must not abort the whole scan
            errors.append((str(f), str(e)))
            # The single user-facing report for this crash. print(), not a
            # Rich console: Rich wraps long paths mid-string, so "one readable
            # line" would wrap into several.
            print(f"Error scanning {f}: {e}", file=sys.stderr)

    if not reports:
        return ScanReport(new_only=new_only, base=base, errors=errors,
                          config_lock=lock)

    overall = round(sum(r.aggregate_score for r in reports) / len(reports), 1)
    return ScanReport(
        file_reports=reports,
        aggregate_score=overall,
        grade=score_to_grade(overall),
        new_only=new_only,
        base=base,
        errors=errors,
        config_lock=lock,
    )
