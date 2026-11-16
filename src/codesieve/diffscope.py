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

import os
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
    changed.extend(_ignored_config_names(root, ref))
    return changed


def _ignored_config_names(root: Path, ref: str) -> list[str]:
    """Untracked files named like a config at any depth, ignored ones included.

    ``git ls-files --others`` without ``--exclude-standard`` reports ignored
    files too, so a ``.codesieve.yml`` hidden by ``.gitignore``,
    ``.git/info/exclude`` or ``core.excludesFile`` still shows up. The icase
    pathspecs keep the walk cheap in repos with large ignored trees and also
    match case variants like ``.CodeSieve.yml``.
    """
    out = _run(root, ["ls-files", "--others", "-z", "--",
                      f":(icase){CONFIG_FILENAME}",
                      f":(icase,glob)**/{CONFIG_FILENAME}"],
               f"config lock: listing untracked configs for --diff {ref!r} failed")
    return _split_nul(out)


def _entry_name(directory: Path, want: os.stat_result) -> str | None:
    """On-disk name of the entry in ``directory`` holding ``want``'s inode.

    A case-insensitive filesystem answers ``lstat('ci.yml')`` for a file
    spelled ``CI.YML``, so comparing ``st_dev``/``st_ino`` against the real
    directory entries is how the stored spelling is recovered.
    """
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                st = entry.stat(follow_symlinks=False)
                if (st.st_dev, st.st_ino) == (want.st_dev, want.st_ino):
                    return entry.name
    except OSError:
        return None
    return None


def _disk_path(path: Path) -> Path:
    """``path`` with every component resolved and spelled exactly as on disk.

    ``Path.resolve()`` keeps the *spelled* case — ``CI.YML`` stays ``CI.YML``
    even when the file is ``ci.yml`` — so it cannot produce the repo-relative
    path git knows. Symlinks in the directory part are followed, then each
    component is matched by inode against the real directory entries. The
    final component is matched the same way without following it, so a
    symlinked config keeps its own repo path rather than its target's.
    """
    parent = Path(os.path.realpath(path.parent))
    cur = Path(parent.anchor)
    for part in parent.parts[1:]:
        try:
            st = os.lstat(cur / part)
        except OSError:
            return parent / path.name
        name = _entry_name(cur, st)
        cur = cur / (name if name is not None else part)
    try:
        st = os.lstat(path)
    except OSError:
        return cur / path.name
    name = _entry_name(cur, st)
    return cur / (name if name is not None else path.name)


def _base_blob(root: Path, base: str, ref: str, rel: str) -> str | None:
    """Blob id of ``rel`` at ``base``, or None when the base has no such path.

    ``--verify --quiet`` exits 1 — silently — for a missing object, which is
    an ordinary answer here (the config is untracked, ignored, new, or named
    in a different case than the committed one), not a git failure. ``base``
    itself is already proven good by the diff listing. Any other failure is
    a :class:`DiffScopeError`: the lock never fails open.
    """
    git = shutil.which("git") or "git"
    try:
        done = subprocess.run(  # noqa: S603
            [git, "rev-parse", "--verify", "--quiet", "--end-of-options",
             f"{base}:{rel}"],
            cwd=str(root), text=True, errors="surrogateescape",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        raise DiffScopeError(
            f"config lock: git rev-parse failed for --diff {ref!r}") from None
    if done.returncode == 0:
        return done.stdout.strip() or None
    if done.returncode == 1:
        return None
    raise DiffScopeError(f"config lock: git rev-parse failed for --diff {ref!r}")


def _worktree_blob(root: Path, ref: str, worktree: Path) -> str:
    """The blob id ``worktree`` would get at check-in, clean filters included.

    The path form of ``git hash-object`` applies autocrlf and eol/text
    attributes exactly like a real commit, so a repo with filters enabled
    does not lock an untouched config.
    """
    out = _run(root, ["hash-object", "--", str(worktree)],
               f"config lock: git hash-object failed for --diff {ref!r}")
    return out.strip()


def _matches_base_blob(root: Path, base: str, ref: str, rel: str,
                       worktree: Path) -> bool:
    """True when ``worktree`` hashes identically to the ``base:rel`` blob."""
    base_blob = _base_blob(root, base, ref, rel)
    if base_blob is None:
        return False
    return base_blob == _worktree_blob(root, ref, worktree)


def _symlink_matches_base(root: Path, root_real: Path, base: str, ref: str,
                          config_path: Path) -> bool:
    """True when a symlinked config's target is committed and unchanged.

    The run loads the target's bytes, so the target — inside the repository
    and identical to a base blob at its own repo path — is what must be
    proven. A target outside the repo cannot be proven, so the config locks.
    """
    spelled = _disk_path(Path(os.path.realpath(config_path)))
    try:
        rel = spelled.relative_to(root_real).as_posix()
    except ValueError:
        return False
    return _matches_base_blob(root, base, ref, rel, spelled)


def _loaded_config_lock(root: Path, base: str, ref: str,
                        config_path: Path | None) -> str | None:
    """Repo path of the loaded config unless it is provably the base version.

    The change listing cannot see a config git refuses to name — an ignored
    file, an ``update-index --assume-unchanged`` or ``--skip-worktree`` edit,
    a name spelled in another case than git tracks. The loaded file is
    therefore compared by content: its on-disk repo-relative spelling must
    exist as a blob at the diff base and hash identically, or the run locks
    and reports that on-disk spelling. A config outside this repository is
    out of the lock's reach and returns None.
    """
    if config_path is None:
        return None
    root_real = _disk_path(root)
    spelled = _disk_path(config_path)
    try:
        rel = spelled.relative_to(root_real).as_posix()
    except ValueError:
        return None  # the loaded config lives outside this repository
    if config_path.is_symlink():
        ok = _symlink_matches_base(root, root_real, base, ref, config_path)
    else:
        ok = _matches_base_blob(root, base, ref, rel, spelled)
    return None if ok else rel


def locked_config_paths(changed: list[str], config_path: Path | None,
                        root: Path) -> list[str]:
    """Which of ``changed`` are CodeSieve configs: the lock's decision.

    ``changed`` holds repo-relative POSIX paths. A path locks the run when
    its basename spells ``.codesieve.yml`` under ``str.casefold`` at any
    depth — git reports a ``.CodeSieve.yml`` under that name and a
    case-insensitive filesystem loads it as the config — or when it is
    ``config_path``, the config file this run loaded, inside the repository:
    a ``--config ci.yml`` is a config even under another name. Returns the
    locked repo-relative paths in git's spelling, POSIX separators, sorted.
    """
    names = set(changed)
    locked = {rel for rel in names
              if PurePosixPath(rel).name.casefold() == CONFIG_FILENAME}
    if config_path is None:
        return sorted(locked)
    try:
        loaded = config_path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return sorted(locked)  # the loaded config lives outside this repository
    hit = {rel.casefold(): rel for rel in names}.get(loaded.casefold())
    if hit is not None:
        locked.add(hit)
    return sorted(locked)


def config_lock(path: Path, ref: str, base: str | None,
                config_path: Path | None) -> list[str]:
    """Repo-relative paths of CodeSieve configs changed in this diff (sorted).

    ``base`` is the merge-base sha for ``--new-only``; pass None to diff
    against ``ref`` itself for a plain ``--diff``. The check covers the
    whole repository holding ``path``, however narrow the scan target is.
    It is the union of two mechanisms: every config-named path git lists as
    changed (which is what catches a deleted or renamed-away config and a
    changed ``.codesieve.yml`` that is not the one loaded), and a
    byte-identity proof that the config this run actually loads — when it
    lives inside the repository — is identical to its blob at the diff base.
    Raises :class:`DiffScopeError` on any git failure — a lock that cannot
    be evaluated is a tool error.
    """
    root = _repo_root(path, ref)
    base_ref = base if base is not None else ref
    changed = _lock_listing(root, base_ref, ref)
    locked = set(locked_config_paths(changed, config_path, root))
    loaded = _loaded_config_lock(root, base_ref, ref, config_path)
    if loaded is not None:
        locked.add(loaded)
    return sorted(locked)
