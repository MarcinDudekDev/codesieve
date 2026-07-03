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

from codesieve.models import SieveResult
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import SCORE_MAX, normalize_score

# Matched only within comment text, so the `#`/`//` prefix is already guaranteed.
_SUPPRESS_RE = re.compile(r"codesieve:\s*ignore(?:\[([^\]]*)\])?", re.IGNORECASE)

# Sentinel value in the suppression map meaning "every sieve on this line".
_ALL = None


def parse_suppressions(parsed: ParsedFile) -> dict[int, frozenset[str] | None]:
    """Map 1-based line number -> lowercased sieve names, or ``None`` for all sieves.

    Only real comment nodes are inspected, so markers inside string literals are
    ignored. Names are lowercased here; callers compare case-insensitively.
    """
    suppressed: dict[int, frozenset[str] | None] = {}
    for node in parsed.get_comments():
        text = ast_utils.get_node_text(node, parsed.source)
        match = _SUPPRESS_RE.search(text)
        if match is None:
            continue
        lineno = node.start_point[0] + 1
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
    if line is None or line not in suppressed:
        return False
    names = suppressed[line]
    return names is _ALL or sieve_name.lower() in names


def _recompute_score(result: SieveResult, kept: list, suppressed: list) -> float:
    """Recompute a sieve's score after some findings were suppressed.

    Additive sieves tag each finding with its ``penalty``; there the score is
    reconstructed exactly as ``SCORE_MAX - sum(kept penalties)`` (robust even when
    the original score was clamped). Otherwise the residual penalty is scaled down
    proportionally by how many findings remain. Either way, suppressing *all*
    findings restores a perfect score.
    """
    if not kept:
        return SCORE_MAX

    all_findings = kept + suppressed
    if all(f.penalty is not None for f in all_findings):
        return normalize_score(SCORE_MAX - sum(f.penalty for f in kept))

    residual_penalty = SCORE_MAX - result.score
    scaled = residual_penalty * (len(kept) / len(all_findings))
    return normalize_score(SCORE_MAX - scaled)


def apply_suppressions(results: list[SieveResult], parsed: ParsedFile) -> list[SieveResult]:
    """Drop findings matched by inline ignore comments and repair each sieve's score."""
    suppressed = parse_suppressions(parsed)
    if not suppressed:
        return results

    _warn_unknown_names(suppressed, {r.name.lower() for r in results}, parsed.filepath)

    updated: list[SieveResult] = []
    for result in results:
        if result.skipped or not result.findings:
            updated.append(result)
            continue

        kept, dropped = [], []
        for finding in result.findings:
            (dropped if _is_suppressed(finding.line, result.name, suppressed) else kept).append(finding)

        if not dropped:
            updated.append(result)
            continue

        new_score = _recompute_score(result, kept, dropped)
        note = f"{len(dropped)} finding(s) suppressed inline"
        summary = note if not kept else f"{result.summary} ({note})"
        updated.append(replace(result, findings=kept, score=new_score, summary=summary))
    return updated
