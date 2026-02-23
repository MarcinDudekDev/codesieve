"""Data models for CodeSieve results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
    sieve_results: list[SieveResult] = field(default_factory=list)
    aggregate_score: float = 0.0
    grade: Grade = Grade.F

    @property
    def filename(self) -> str:
        from pathlib import Path
        return Path(self.path).name


@dataclass
class ScanReport:
    """Report for an entire scan (may include multiple files)."""
    file_reports: list[FileReport] = field(default_factory=list)
    aggregate_score: float = 0.0
    grade: Grade = Grade.F
