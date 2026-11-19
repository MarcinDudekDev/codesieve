"""Inline per-finding suppression — ruff-style ``# codesieve: ignore`` comments.

A trailing comment on a source line silences findings anchored to that line:

    risky()  # codesieve: ignore                 -> drop ALL findings on this line
    risky()  # codesieve: ignore[ErrorHandling]  -> drop only ErrorHandling findings
    risky()  # codesieve: ignore[ErrorHandling,Naming]  -> comma-separated list

The marker is honoured **only inside a real comment**, never inside a string
literal — we scan tree-sitter ``comment`` nodes (works for ``#`` in Python/PHP and
``//`` / ``/* */`` in JS/TS/Go/PHP), so a file cannot self-suppress by mentioning
the marker in a string. Sieve names are matched case-insensitively; an unknown
name is warned about rather than silently ignored.

Suppression is applied where sieve results are aggregated (``engine.scan_file``),
*before* the weighted average is taken, so a suppressed finding removes its score
penalty too — the grade improves rather than merely hiding the finding.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from codesieve.models import SieveResult
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import SCORE_MAX, normalize_score

# Matched only within comment text, so the `#`/`//` prefix is already guaranteed.
# Public because the NoSilencing sieve must report exactly what this honours: with two
# separate patterns, a comment could silence a finding here and stay invisible there.
SUPPRESS_RE = re.compile(r"codesieve:\s*ignore(?:\[([^\]]*)\])?", re.IGNORECASE)

# Sentinel value in the suppression map meaning "every sieve on this line".
_ALL = None

# Sieves whose findings an ignore comment can never drop. NoSilencing reports the
# ignore comments themselves, so its finding always sits on a line that carries one:
# if it were suppressible, every suppression would hide its own report.
UNSUPPRESSIBLE = frozenset({"NoSilencing"})


def parse_suppressions(parsed: ParsedFile) -> dict[int, frozenset[str] | None]:
    """Map 1-based line number -> lowercased sieve names, or ``None`` for all sieves.

    Only real comment nodes are inspected, so markers inside string literals are
    ignored. Names are lowercased here; callers compare case-insensitively.

    A marker inside a multi-line comment (``/* … codesieve: ignore … */``) is
    anchored on the line the marker itself sits on, the same line NoSilencing
    reports it on — an ignore comment must silence the line it names, not the
    line where the block comment happens to open.
    """
    suppressed: dict[int, frozenset[str] | None] = {}
    for node in parsed.get_comments():
        text = ast_utils.get_node_text(node, parsed.source)
        match = SUPPRESS_RE.search(text)
        if match is None:
            continue
        lineno = node.start_point[0] + 1 + text.count("\n", 0, match.start())
        raw_names = match.group(1)
        if raw_names is None or not raw_names.strip():
            suppressed[lineno] = _ALL  # bare ignore -> silence everything on this line
            continue
        names = frozenset(n.strip().lower() for n in raw_names.split(",") if n.strip())
        existing = suppressed.get(lineno, frozenset())
        suppressed[lineno] = existing if existing is _ALL else (existing | names)
    return suppressed


def _warn_unknown_names(suppressed: dict[int, frozenset[str] | None],
                        known_lower: set[str], path: str) -> None:
    """Warn on stderr about ignore comments naming a sieve that does not exist.

    A typo would otherwise silently suppress nothing, and the finding it was meant
    to hide would look like a fresh regression.
    """
    requested = {n for names in suppressed.values() if names is not _ALL for n in names}
    unknown = sorted(requested - known_lower)
    if not unknown:
        return
    from rich.console import Console
    Console(stderr=True).print(
        f"[yellow]codesieve: unknown sieve name(s) in ignore comment: "
        f"{', '.join(unknown)} ({path})[/yellow]"
    )


def _is_suppressed(line: int | None, sieve_name: str,
                   suppressed: dict[int, frozenset[str] | None]) -> bool:
    """True if this sieve's finding on this line is silenced by an ignore comment.

    A finding with no line can never be suppressed — there is no comment to anchor
    the marker to, so a file-level finding stays visible.
    """
    if line is None or line not in suppressed:
        return False
    names = suppressed[line]
    return names is _ALL or sieve_name.lower() in names


def _recompute_score(result: SieveResult, kept: list, suppressed: list) -> float:
    """Recompute a sieve's score after some findings were suppressed.

    The split is by *how the sieve scores*, and it is categorical — there is no
    approximation left to game:

    * **Additive sieves** — every finding carries its own ``penalty``
      (ErrorHandling, MagicNumbers, DeprecatedAPI). The score is a pure function
      of the findings, so it is reconstructed *exactly* as
      ``SCORE_MAX - sum(kept penalties)``. This is correct for both partial
      suppression and full suppression (all gone → ``sum == 0`` → ``SCORE_MAX``).

    * **Ratio/severity sieves** — no per-finding penalty (TypeHints, Naming,
      Nesting, KISS, GuardClauses, DRY, Comments). Their score reflects code that
      the findings do not fully represent (an *unflagged* moderate function still
      caps KISS below 10), so zero remaining findings does **not** mean a perfect
      score. Suppression therefore **never moves** these scores — partial or full.
      It only hides findings from the report. This makes it impossible to raise a
      non-additive grade by suppressing anything.
    """
    all_findings = kept + suppressed
    if all(f.penalty is not None for f in all_findings):
        return normalize_score(SCORE_MAX - sum(f.penalty for f in kept))

    return result.score  # non-additive sieve: suppression must not alter the score


def _known_sieve_names(results: list[SieveResult],
                       known_names: Iterable[str] | None) -> set[str]:
    """Lowercased sieve names a marker may legitimately use.

    That is the ones this file ran, the ones that can never be silenced, and —
    when the caller passes them — every sieve the tool knows, so a marker naming
    a sieve that simply was not selected is not mistaken for a typo.
    """
    known = {r.name.lower() for r in results} | {name.lower() for name in UNSUPPRESSIBLE}
    if known_names is not None:
        known |= {name.lower() for name in known_names}
    return known


def _suppress_result(result: SieveResult,
                     suppressed: dict[int, frozenset[str] | None]) -> SieveResult:
    """Return ``result`` with its suppressed findings dropped, or unchanged if none matched."""
    kept, dropped = [], []
    for finding in result.findings:
        (dropped if _is_suppressed(finding.line, result.name, suppressed) else kept).append(finding)

    if not dropped:
        return result

    note = f"{len(dropped)} finding(s) suppressed inline"
    summary = note if not kept else f"{result.summary} ({note})"
    return replace(result, findings=kept,
                   score=_recompute_score(result, kept, dropped), summary=summary)


def apply_suppressions(results: list[SieveResult], parsed: ParsedFile,
                       known_names: Iterable[str] | None = None) -> list[SieveResult]:
    """Drop findings matched by inline ignore comments and repair each sieve's score.

    ``known_names`` is every sieve the tool knows, not just the ones this file
    ran: with ``--sieves Naming`` a correct ``ignore[KISS]`` used to be warned
    about as a typo, because KISS was absent from this file's results.
    """
    suppressed = parse_suppressions(parsed)
    if not suppressed:
        return results

    _warn_unknown_names(suppressed, _known_sieve_names(results, known_names), parsed.filepath)

    updated: list[SieveResult] = []
    for result in results:
        if result.skipped or not result.findings or result.name in UNSUPPRESSIBLE:
            updated.append(result)
        else:
            updated.append(_suppress_result(result, suppressed))
    return updated
