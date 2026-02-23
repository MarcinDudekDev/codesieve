"""Base class for all sieves."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesieve.models import SieveResult, SieveType
from codesieve.parser.treesitter import ParsedFile
from codesieve.scoring import SCORE_MAX, normalize_score


class BaseSieve(ABC):
    """Abstract base class for code quality sieves."""

    name: str = ""
    description: str = ""
    sieve_type: SieveType = SieveType.DETERMINISTIC
    default_weight: float = 0.0

    @abstractmethod
    def analyze(self, parsed: ParsedFile) -> SieveResult:
        """Analyze a parsed file and return a SieveResult."""
        ...

    def perfect(self, summary: str) -> SieveResult:
        """Return a perfect-score result (e.g. when nothing to analyze)."""
        return SieveResult(name=self.name, score=SCORE_MAX, sieve_type=self.sieve_type, summary=summary)

    def result(self, score: float, summary: str, findings: list | None = None) -> SieveResult:
        """Return a normalized result."""
        return SieveResult(
            name=self.name, score=normalize_score(score), sieve_type=self.sieve_type,
            summary=summary, findings=findings or [],
        )

    def skip(self, reason: str) -> SieveResult:
        """Return a skipped result."""
        return SieveResult(
            name=self.name, score=0.0, sieve_type=self.sieve_type,
            summary=reason, skipped=True, skip_reason=reason,
        )
