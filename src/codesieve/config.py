"""Configuration loader for .codesieve.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULTS = {
    "sieves": ["KISS", "Nesting", "Naming", "ErrorHandling", "TypeHints", "MagicNumbers", "GuardClauses"],
    "weights": {
        "KISS": 0.20,
        "Nesting": 0.15,
        "Naming": 0.15,
        "ErrorHandling": 0.10,
        "TypeHints": 0.08,
        "MagicNumbers": 0.05,
        "GuardClauses": 0.05,
        "DRY": 0.15,
        "SRP": 0.15,
        "Complexity": 0.10,
        "Comments": 0.10,
    },
    "fail_under": 0.0,
    "deterministic": False,
    "format": "terminal",
    "exclude": ["**/node_modules/**", "**/.venv/**", "**/venv/**", "**/__pycache__/**"],
}


@dataclass
class Config:
    sieves: list[str] = field(default_factory=lambda: list(DEFAULTS["sieves"]))
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULTS["weights"]))
    fail_under: float = 0.0
    deterministic: bool = False
    format: str = "terminal"
    exclude: list[str] = field(default_factory=lambda: list(DEFAULTS["exclude"]))

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        """Load config from .codesieve.yml, falling back to defaults."""
        if config_path is None:
            config_path = Path.cwd() / ".codesieve.yml"
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
  # - DRY        # Phase 2
  # - SRP        # Phase 3 (requires LLM)
  # - Complexity  # Phase 3 (requires LLM)
  # - Comments   # Phase 2

weights:
  KISS: 0.20
  Nesting: 0.15
  Naming: 0.15
  ErrorHandling: 0.10
  TypeHints: 0.08
  MagicNumbers: 0.05
  GuardClauses: 0.05
  DRY: 0.15
  SRP: 0.15
  Complexity: 0.10
  Comments: 0.10

# Minimum aggregate score (0 = disabled)
fail_under: 0

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
