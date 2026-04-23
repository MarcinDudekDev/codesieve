"""DRY sieve — detects duplicate function bodies (Don't Repeat Yourself)."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import FunctionInfo, ParsedFile
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

MIN_BODY_LINES = 3
PENALTY_PER_DUPLICATE = 1.5


def _normalize(text: str) -> str:
    """Strip leading/trailing whitespace per line and drop blank lines."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _body_hash(func: FunctionInfo, source: bytes) -> str | None:
    body = func.node.child_by_field_name("body")
    if body is None:
        return None
    raw = source[body.start_byte:body.end_byte].decode("utf-8", errors="replace")
    norm = _normalize(raw)
    if norm.count("\n") + 1 < MIN_BODY_LINES:
        return None
    return hashlib.md5(norm.encode()).hexdigest()  # noqa: S324


class DrySieve(BaseSieve):
    name = "DRY"
    description = "Detects duplicate function bodies (Don't Repeat Yourself)"
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        named = [f for f in parsed.get_functions() if f.name != "<anonymous>"]
        if not named:
            return self.perfect("No functions found")

        groups: dict[str, list[FunctionInfo]] = defaultdict(list)
        for func in named:
            h = _body_hash(func, parsed.source)
            if h is not None:
                groups[h].append(func)

        dup_groups = [funcs for funcs in groups.values() if len(funcs) > 1]
        if not dup_groups:
            return self.perfect("No duplicate function bodies found")

        findings: list[Finding] = []
        total_dups = 0
        for funcs in dup_groups:
            original = funcs[0]
            for dup in funcs[1:]:
                total_dups += 1
                findings.append(Finding(
                    message=f"{dup.name}() duplicates {original.name}() — extract shared logic",
                    line=dup.start_line,
                    function=dup.name,
                    severity="warning",
                ))

        score = SCORE_MAX - PENALTY_PER_DUPLICATE * total_dups
        summary = f"{total_dups} duplicate function body(ies) found"
        return self.result(score, summary, findings)
