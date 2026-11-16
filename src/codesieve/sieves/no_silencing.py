"""NoSilencing sieve — reports comments that silence a tool instead of fixing the cause.

``# noqa``, ``# type: ignore``, ``// @ts-ignore``, ``/* eslint-disable */``,
``// phpcs:ignore``, ``//nolint`` and CodeSieve's own ``# codesieve: ignore``
all make a checker stop complaining. That is sometimes right, but it is also
the cheapest way to a better grade, so each one costs score here.

Markers are looked for only inside real comment nodes, never in raw source
lines: a marker quoted in a string or a docstring silences nothing. Findings
of this sieve cannot themselves be suppressed (see ``suppression.py``).
With ``scan --diff REF --new-only`` the sieve means "no NEW silencing".
"""

from __future__ import annotations

import re

from codesieve.models import Finding, SieveResult
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

PENALTY_PER_SUPPRESSION = 1.0

# A marker counts only where the tool itself would honour it: at the start of a
# comment, or of a `#` / `//` segment inside one. Prose that merely mentions a
# marker, or says "ignore values above this", is left alone. CodeSieve's own
# marker is the exception: suppression.py honours it anywhere in a comment, so it
# is reported anywhere too - whatever silences must be visible. One row per tool.
_SEGMENT_START = r"(?:^|#|//|/\*+|\*)\s*"
_ANYWHERE = r"\b"


def _marker(pattern: str, start: str = _SEGMENT_START, flags: int = 0) -> re.Pattern[str]:
    """Compile a marker pattern anchored at ``start``."""
    return re.compile(start + pattern, flags | re.MULTILINE)


_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("noqa", _marker(r"noqa\b", flags=re.IGNORECASE)),
    ("type: ignore", _marker(r"type:\s*ignore\b")),
    ("phpcs:ignore", _marker(r"phpcs:(?:ignore|disable)\b")),
    ("@ts-ignore", _marker(r"@ts-(?:ignore|expect-error|nocheck)\b")),
    ("eslint-disable", _marker(r"eslint-disable(?:-next-line|-line)?\b")),
    ("nolint", _marker(r"nolint\b")),
    ("codesieve: ignore", _marker(r"codesieve:\s*ignore\b", start=_ANYWHERE, flags=re.IGNORECASE)),
)


def markers_in(comment_text: str) -> list[str]:
    """Labels of the suppression markers a comment carries, in table order."""
    return [label for label, pattern in _MARKERS if pattern.search(comment_text)]


class NoSilencingSieve(BaseSieve):
    name = "NoSilencing"
    description = "Reports suppression comments (noqa, type: ignore, eslint-disable, ...) that silence a tool"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        """Charge a flat cost for every suppression marker found in a real comment."""
        findings = self._findings(parsed)
        if not findings:
            return self.perfect("no suppression comments")
        score = SCORE_MAX - PENALTY_PER_SUPPRESSION * len(findings)
        return self.result(score, f"{len(findings)} suppression comment(s) found", findings)

    def _findings(self, parsed: ParsedFile) -> list[Finding]:
        """One finding per marker, anchored on the line where its comment starts."""
        findings: list[Finding] = []
        for node in parsed.get_comments():
            text = ast_utils.get_node_text(node, parsed.source)
            for label in markers_in(text):
                findings.append(Finding(
                    message=f"suppression comment: {label}",
                    line=node.start_point[0] + 1, severity="warning",
                    penalty=PENALTY_PER_SUPPRESSION,
                ))
        return findings
