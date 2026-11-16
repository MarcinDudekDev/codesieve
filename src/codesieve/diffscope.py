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
from pathlib import Path, PurePosixPath

from codesieve.config import CONFIG_FILENAME


class DiffScopeError(Exception):
    """Raised when the diff scope for ``--diff`` / ``--new-only`` cannot be computed."""


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


def _changed_paths(root: Path, base: str, ref: str) -> list[tuple[str, list[str]]]:
    """Tracked changes vs ``base`` as ``(post-image name, diff pathspecs)`` pairs.

    ``git diff --name-status -z -M`` compares the working tree (index
    included) against the base commit; ``-z`` keeps odd filenames intact.
    Renames and copies appear as ``R<score>``/``C<score>`` followed by the
    pre- and post-image names — the added-line diff needs both names in its
    pathspec or rename detection cannot pair them and the post-image looks
    like a new file with every line added. ``T`` (a file swapped for a
    symlink or back) is a change like any other and must stay in scope.
    """
    out = _run(root, ["diff", "--name-status", "-z", "-M", "--diff-filter=ACMRT", base],
               f"--new-only: git diff against merge-base of {ref!r} failed")
    fields = _split_nul(out)
    changes: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        i += 1
        if status[0] in "RC":
            old, new = fields[i], fields[i + 1]
            i += 2
            changes.append((new, [old, new]))
        else:
            changes.append((fields[i], [fields[i]]))
            i += 1
    return changes


def _untracked_paths(root: Path, ref: str, mode: str = "--new-only") -> list[str]:
    """Untracked, non-ignored files in the repo (``git ls-files --others``)."""
    out = _run(root, ["ls-files", "--others", "--exclude-standard", "-z"],
               f"{mode}: listing untracked files for --diff {ref!r} failed")
    return _split_nul(out)


def _added_lines(root: Path, base: str, names: list[str], ref: str) -> set[int]:
    """Line numbers added to ``names[-1]`` since ``base``, per ``git diff -U0``.

    A ``@@ -a,b +c,d @@`` header contributes lines ``c .. c+d-1``; a missing
    count means 1 line, and a count of 0 (pure deletions) adds nothing.
    ``--no-ext-diff`` and ``--no-textconv`` keep user-configured diff drivers
    from reshaping the output the hunk parser relies on.
    """
    out = _run(root, ["diff", "-U0", "-M", "--no-color", "--no-ext-diff", "--no-textconv",
                      base, "--", *names],
               f"--new-only: git diff -U0 failed for {names[-1]!r} against {ref!r}")
    added: set[int] = set()
    for line in out.splitlines():
        match = _HUNK_HEADER.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) is not None else 1
        added.update(range(start, start + count))
    return added


def resolve_scope(path: Path, ref: str) -> tuple[str, dict[Path, set[int] | None]]:
    """Return ``(merge-base sha, {file: added line numbers})`` for ``--new-only``.

    ``path`` is the scan target; the scope covers the whole repo it lives in,
    so a subdirectory scan still sees changes relative to the merge-base.
    A ``None`` line set marks an untracked file, where every line counts as
    added; untracked files are never read here — the engine expands the
    marker to lines ``1..line_count`` only for files it actually scans.
    Raises :class:`DiffScopeError` naming ``ref`` on any failure — there is no
    silent fallback in this mode.
    """
    if ref.startswith("-"):
        raise DiffScopeError(f"--new-only: --diff ref {ref!r} looks like a git option")
    root = _repo_root(path, ref)
    base = _merge_base(root, ref)
    scope: dict[Path, set[int] | None] = {}
    for name, spec in _changed_paths(root, base, ref):
        scope[root / name] = _added_lines(root, base, spec, ref)
    for name in _untracked_paths(root, ref):
        scope[root / name] = None
    return base, scope


def _lock_listing(root: Path, base: str, ref: str) -> list[str]:
    """Repo-relative paths differing from ``base`` in any way, plus untracked files.

    Unlike the scan scope there is no ``--diff-filter``: a deleted or
    renamed-away ``.codesieve.yml`` loosens the gate exactly like an edit
    does, so every status counts and a rename or copy contributes both of
    its names — the old one matters when a config was renamed away, the new
    one when something was renamed to it.
    """
    out = _run(root, ["diff", "--name-status", "-z", "-M",
                      "--end-of-options", base, "--"],
               f"config lock: git diff --name-status against the diff base of {ref!r} failed")
    fields = _split_nul(out)
    changed: list[str] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        i += 1
        if status[0] in "RC":
            changed.extend((fields[i], fields[i + 1]))
            i += 2
        else:
            changed.append(fields[i])
            i += 1
    changed.extend(_untracked_paths(root, ref, mode="config lock"))
    return changed


def locked_config_paths(changed: list[str], config_path: Path | None,
                        root: Path) -> list[str]:
    """Which of ``changed`` are CodeSieve configs: the lock's decision.

    ``changed`` holds repo-relative POSIX paths. A path locks the run when
    its basename is ``.codesieve.yml`` at any depth, or when it is
    ``config_path`` — the config file this run loaded — inside the
    repository: a ``--config ci.yml`` is a config even under another name.
    Returns the locked repo-relative paths, POSIX separators, sorted.
    """
    names = set(changed)
    locked = {rel for rel in names if PurePosixPath(rel).name == CONFIG_FILENAME}
    if config_path is None:
        return sorted(locked)
    try:
        loaded = config_path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return sorted(locked)  # the loaded config lives outside this repository
    if loaded in names:
        locked.add(loaded)
    return sorted(locked)


def config_lock(path: Path, ref: str, base: str | None,
                config_path: Path | None) -> list[str]:
    """Repo-relative paths of CodeSieve configs changed in this diff (sorted).

    ``base`` is the merge-base sha for ``--new-only``; pass None to diff
    against ``ref`` itself for a plain ``--diff``. The check covers the
    whole repository holding ``path``, however narrow the scan target is.
    Raises :class:`DiffScopeError` on any git failure — a lock that cannot
    be evaluated is a tool error.
    """
    root = _repo_root(path, ref)
    changed = _lock_listing(root, base if base is not None else ref, ref)
    return locked_config_paths(changed, config_path, root)
