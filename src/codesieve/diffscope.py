"""Compute the diff scope for ``scan --diff REF --new-only``.

The scope of a new-only scan is the merge-base of REF and HEAD: every file
that differs from that base — tracked changes in the working tree or index,
plus untracked files that are not ignored — and, per file, the set of line
numbers that were added. A finding is only "new" when it sits on one of
those lines.

Any failure to compute the scope raises :class:`DiffScopeError`; the CLI
turns that into exit code 2. New-only mode never falls back to a full scan.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class DiffScopeError(Exception):
    """Raised when the diff scope for ``--new-only`` cannot be computed."""


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _run(cwd: Path, argv: list[str], err: str) -> str:
    """Run a fixed git ``argv`` in ``cwd`` (never a shell) or raise DiffScopeError.

    ``err`` is the caller-provided message, which names the --diff ref so the
    user can tell which argument caused the failure. ``-z`` output is decoded
    with surrogateescape so odd filenames survive the trip through ``str``.
    """
    git = shutil.which("git") or "git"
    try:
        return subprocess.check_output(  # noqa: S603
            [git, *argv], cwd=str(cwd), text=True, errors="surrogateescape",
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        raise DiffScopeError(err) from None


def _repo_root(path: Path, ref: str) -> Path:
    """Repo root containing ``path``, via ``git rev-parse --show-toplevel``."""
    cwd = path if path.is_dir() else path.parent
    out = _run(cwd, ["rev-parse", "--show-toplevel"],
               f"--new-only: --diff {ref}: {path} is not inside a git repository")
    return Path(out.strip())


def _merge_base(root: Path, ref: str) -> str:
    """Full sha of ``git merge-base REF HEAD``.

    ``--end-of-options`` plus the leading-dash rejection in resolve_scope
    keep a user-supplied ref from ever being read as a git option.
    """
    out = _run(root, ["merge-base", "--end-of-options", ref, "HEAD"],
               f"--new-only: cannot resolve --diff ref {ref!r} (unknown ref or no merge-base with HEAD)")
    base = out.strip()
    if not base:
        raise DiffScopeError(f"--new-only: no merge-base for --diff {ref!r} and HEAD")
    return base


def _split_nul(out: str) -> list[str]:
    """Split NUL-separated git output, dropping the empty trailing field."""
    return [name for name in out.split("\0") if name]


def _changed_paths(root: Path, base: str, ref: str) -> list[str]:
    """Tracked files added/copied/modified/renamed vs ``base``, worktree included.

    ``git diff <base>`` compares the working tree (index included) against the
    base commit; ``-z`` keeps odd filenames intact and renames report their
    post-image name.
    """
    out = _run(root, ["diff", "--name-only", "-z", "--diff-filter=ACMR", base],
               f"--new-only: git diff against merge-base of {ref!r} failed")
    return _split_nul(out)


def _untracked_paths(root: Path, ref: str) -> list[str]:
    """Untracked, non-ignored files in the repo (``git ls-files --others``)."""
    out = _run(root, ["ls-files", "--others", "--exclude-standard", "-z"],
               f"--new-only: listing untracked files for --diff {ref!r} failed")
    return _split_nul(out)


def _added_lines(root: Path, base: str, name: str, ref: str) -> set[int]:
    """Line numbers added to ``name`` since ``base``, per ``git diff -U0`` hunks.

    A ``@@ -a,b +c,d @@`` header contributes lines ``c .. c+d-1``; a missing
    count means 1 line, and a count of 0 (pure deletions) adds nothing.
    """
    out = _run(root, ["diff", "-U0", "--no-color", base, "--", name],
               f"--new-only: git diff -U0 failed for {name!r} against {ref!r}")
    added: set[int] = set()
    for line in out.splitlines():
        match = _HUNK_HEADER.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) is not None else 1
        added.update(range(start, start + count))
    return added


def _all_lines(path: Path, ref: str) -> set[int]:
    """Every line of an untracked file counts as added; counted in the worktree."""
    try:
        raw = path.read_bytes()
    except OSError:
        raise DiffScopeError(
            f"--new-only: --diff {ref}: cannot read untracked file {path}") from None
    line_count = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
    return set(range(1, line_count + 1))


def resolve_scope(path: Path, ref: str) -> tuple[str, dict[Path, set[int]]]:
    """Return ``(merge-base sha, {file: added line numbers})`` for ``--new-only``.

    ``path`` is the scan target; the scope covers the whole repo it lives in,
    so a subdirectory scan still sees changes relative to the merge-base.
    Raises :class:`DiffScopeError` naming ``ref`` on any failure — there is no
    silent fallback in this mode.
    """
    if ref.startswith("-"):
        raise DiffScopeError(f"--new-only: --diff ref {ref!r} looks like a git option")
    root = _repo_root(path, ref)
    base = _merge_base(root, ref)
    scope: dict[Path, set[int]] = {}
    for name in _changed_paths(root, base, ref):
        scope[root / name] = _added_lines(root, base, name, ref)
    for name in _untracked_paths(root, ref):
        scope[root / name] = _all_lines(root / name, ref)
    return base, scope
