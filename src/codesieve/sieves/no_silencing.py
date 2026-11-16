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
from codesieve.suppression import SUPPRESS_RE

PENALTY_PER_SUPPRESSION = 1.0

# A marker counts only where the tool itself would honour it: at the start of a
# comment, or of a `#` / `//` segment inside one. Prose that merely mentions a
# marker, or says "ignore values above this", is left alone. One row per tool;
# the named group `marker` is the token whose line gets reported.
_SEGMENT_START = r"(?:^|#|//|/\*+|\*)\s*"


def _marker(pattern: str, flags: int = 0) -> re.Pattern[str]:
    """Compile a marker pattern anchored at the start of a comment segment."""
    return re.compile(_SEGMENT_START + f"(?P<marker>{pattern})", flags | re.MULTILINE)


# CodeSieve's own marker is not in this table: it is matched with the very regex
# suppression.py uses (SUPPRESS_RE), so anything that silences a finding there is
# reported here, whatever its spelling.
_OWN_LABEL = "codesieve: ignore"
_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("noqa", _marker(r"(?:(?:ruff|flake8):\s*)?noqa\b", re.IGNORECASE)),
    ("type: ignore", _marker(r"type:\s*ignore\b")),
    ("phpcs:ignore", _marker(r"@?phpcs:(?:ignoreFile|ignore|disable)\b")),
    ("@ts-ignore", _marker(r"@ts-(?:ignore|expect-error|nocheck)\b")),
    ("eslint-disable", _marker(r"eslint-disable(?:-next-line|-line)?\b")),
    ("nolint", _marker(r"nolint\b")),
)


def markers_in(comment_text: str) -> list[tuple[str, int]]:
    """Every suppression marker in a comment as ``(label, line offset)``, in text order.

    The offset is the number of newlines before the marker token, so a marker
    on the third line of a block comment is reported on that line, not on the
    line where the comment opens.
    """
    hits: list[tuple[int, str]] = []
    for label, pattern in _MARKERS:
        hits.extend((match.start("marker"), label) for match in pattern.finditer(comment_text))
    hits.extend((match.start(), _OWN_LABEL) for match in SUPPRESS_RE.finditer(comment_text))
    return [(label, comment_text.count("\n", 0, position)) for position, label in sorted(hits)]


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
        """One finding per marker occurrence, anchored on the marker's own line."""
        findings: list[Finding] = []
        for node in parsed.get_comments():
            text = ast_utils.get_node_text(node, parsed.source)
            for label, line_offset in markers_in(text):
                findings.append(Finding(
                    message=f"suppression comment: {label}",
                    line=node.start_point[0] + 1 + line_offset, severity="warning",
                    penalty=PENALTY_PER_SUPPRESSION,
                ))
        return findings
