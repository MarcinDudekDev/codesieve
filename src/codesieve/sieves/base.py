"""Base class for all sieves."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesieve.models import SieveResult, SieveType
from codesieve.parser.treesitter import ParsedFile


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

    def skip(self, reason: str) -> SieveResult:
        """Return a skipped result."""
        return SieveResult(
            name=self.name,
            score=0.0,
            sieve_type=self.sieve_type,
            summary=reason,
            skipped=True,
            skip_reason=reason,
        )
