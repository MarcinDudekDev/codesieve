"""Data models for CodeSieve results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from codesieve import standards


class SieveType(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HYBRID = "hybrid"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


@dataclass
class Finding:
    """A specific issue found by a sieve."""
    message: str
    line: int | None = None
    function: str | None = None
    severity: str = "info"  # info, warning, error
    penalty: float | None = None  # score cost this finding contributed (additive sieves only)


@dataclass
class SieveResult:
    """Result from a single sieve analysis."""
    name: str
    score: float  # 1.0–10.0
    sieve_type: SieveType
    summary: str
    findings: list[Finding] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class FileReport:
    """Report for a single file."""
    path: str
    language: str
    line_count: int
    standard: str = standards.DEFAULT
    sieve_results: list[SieveResult] = field(default_factory=list)
    aggregate_score: float = 0.0
    grade: Grade = Grade.F
    added_lines: set[int] | None = None  # set only in --new-only mode

    @property
    def filename(self) -> str:
        """Basename of the scanned path, for report headings that must stay narrow."""
        from pathlib import Path
        return Path(self.path).name

    def new_findings(self) -> list[tuple[str, "Finding"]]:
        """(sieve name, finding) pairs that sit on lines added since the merge-base.

        Only meaningful in new-only mode, when ``added_lines`` is populated:
        a finding is new when ``finding.line`` is in that set. Findings with
        ``line is None``, and findings of skipped sieves, are never new.
        """
        if self.added_lines is None:
            return []
        pairs = []
        for result in self.sieve_results:
            if result.skipped:
                continue
            for finding in result.findings:
                if finding.line is not None and finding.line in self.added_lines:
                    pairs.append((result.name, finding))
        return pairs


@dataclass
class ScanReport:
    """Report for an entire scan (may include multiple files)."""
    file_reports: list[FileReport] = field(default_factory=list)
    aggregate_score: float = 0.0
    grade: Grade = Grade.F
    new_only: bool = False
    base: str | None = None  # full merge-base sha, set only in --new-only mode

    @property
    def new_finding_count(self) -> int:
        """Total findings on added lines across all files (new-only mode)."""
        return sum(len(fr.new_findings()) for fr in self.file_reports)
