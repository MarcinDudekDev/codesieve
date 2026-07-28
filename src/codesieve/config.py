"""Configuration loader for .codesieve.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from codesieve import standards


CONFIG_FILENAME = ".codesieve.yml"


DEFAULTS = {
    "sieves": ["KISS", "Nesting", "Naming", "ErrorHandling", "TypeHints", "MagicNumbers", "GuardClauses", "DeprecatedAPI", "Comments", "DRY"],
    "weights": {
        "KISS": 0.20,
        "Nesting": 0.15,
        "Naming": 0.15,
        "ErrorHandling": 0.10,
        "TypeHints": 0.08,
        "MagicNumbers": 0.05,
        "GuardClauses": 0.05,
        "DeprecatedAPI": 0.05,
        "DRY": 0.15,
        "SRP": 0.15,
        "Complexity": 0.10,
        "Comments": 0.10,
    },
    "fail_under": 0.0,
    "standard": standards.DEFAULT,
    "deterministic": False,
    "format": "terminal",
    "exclude": ["**/node_modules/**", "**/.venv/**", "**/venv/**", "**/__pycache__/**"],
}


def _validated_standard(value: object, config_path: Path) -> str:
    """Accept only a known standard, warning and falling back otherwise.

    The CLI gets this for free from ``click.Choice``; YAML does not, and an
    unrecognised value used to pass silently — the registry fell back to the
    default pack while the report cheerfully printed the bogus name.
    """
    if value in standards.CHOICES:
        return str(value)
    import sys
    print(f"codesieve: unknown standard {value!r} in {config_path}; "
          f"using {standards.DEFAULT!r}. Valid: {', '.join(standards.CHOICES)}", file=sys.stderr)
    return standards.DEFAULT


def find_config(target: str | Path) -> Path | None:
    """Search upward from a scan target for the nearest ``.codesieve.yml``.

    The walk stops after examining a directory that looks like a repository
    root, so a scan never silently picks up an unrelated config from a parent
    directory or from ``$HOME``.
    """
    start = Path(target)
    directory = (start if start.is_dir() else start.parent).resolve()

    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (candidate_dir / ".git").exists():
            break
    return None


@dataclass
class Config:
    sieves: list[str] = field(default_factory=lambda: list(DEFAULTS["sieves"]))
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULTS["weights"]))
    fail_under: float = 0.0
    standard: str = standards.DEFAULT
    deterministic: bool = False
    format: str = "terminal"
    exclude: list[str] = field(default_factory=lambda: list(DEFAULTS["exclude"]))

    @classmethod
    def discover(cls, target: str | Path, config_path: str | Path | None = None) -> Config:
        """Load config for a scan target, searching upward from the target itself.

        An explicit ``config_path`` always wins. Otherwise this walks up from the
        target directory looking for ``.codesieve.yml``, stopping at the first
        hit or at a repository root.

        When the search finds nothing the result is plain defaults — deliberately
        *not* the current directory's config. Falling back to the cwd would
        reintroduce the very coupling this method exists to remove: a target
        would still score differently depending on where the command was run.
        """
        if config_path is not None:
            return cls.load(config_path)
        found = find_config(target)
        return cls.load(found) if found else cls()

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        """Load config from .codesieve.yml, falling back to defaults.

        With no path, reads ``.codesieve.yml`` from the current working
        directory — note that this is independent of what is being scanned, so
        the same target can score differently from different directories. Use
        :meth:`discover` to key config off the scan target instead.
        """
        if config_path is None:
            config_path = Path.cwd() / CONFIG_FILENAME
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        return cls(
            sieves=data.get("sieves", DEFAULTS["sieves"]),
            weights={**DEFAULTS["weights"], **data.get("weights", {})},
            fail_under=data.get("fail_under", 0.0),
            standard=_validated_standard(data.get("standard", DEFAULTS["standard"]), config_path),
            deterministic=data.get("deterministic", False),
            format=data.get("format", "terminal"),
            exclude=data.get("exclude", DEFAULTS["exclude"]),
        )


def generate_default_config() -> str:
    """Generate a default .codesieve.yml content."""
    return """# CodeSieve Configuration
sieves:
  - KISS
  - Nesting
  - Naming
  - ErrorHandling
  - TypeHints
  - MagicNumbers
  - GuardClauses
  - DeprecatedAPI
  - Comments
  - DRY
  # - SRP        # Phase 3 (requires LLM)
  # - Complexity  # Phase 3 (requires LLM)

weights:
  KISS: 0.20
  Nesting: 0.15
  Naming: 0.15
  ErrorHandling: 0.10
  TypeHints: 0.08
  MagicNumbers: 0.05
  GuardClauses: 0.05
  DeprecatedAPI: 0.05
  DRY: 0.15
  SRP: 0.15
  Complexity: 0.10
  Comments: 0.10

# Minimum aggregate score (0 = disabled)
fail_under: 0

# Coding standard to grade against: psr (default) | wordpress | auto
# "wordpress" applies WPCS (snake_case functions, Capitalized_Words_With_Underscores
# classes, no declare(strict_types=1) expectation) instead of PSR-1/PSR-12.
standard: psr

# Set true to skip LLM-dependent sieves
deterministic: false

# Output format: terminal, json
format: terminal

# File patterns to exclude
exclude:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/__pycache__/**"
"""
