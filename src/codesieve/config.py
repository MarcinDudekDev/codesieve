"""Configuration loader for .codesieve.yml."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from codesieve import standards


CONFIG_FILENAME = ".codesieve.yml"


class ConfigError(Exception):
    """A .codesieve.yml exists but cannot be parsed or holds wrongly typed values."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that turns a duplicate mapping key into a YAML error.

    ``yaml.safe_load`` lets ``fail_under: 9`` followed by ``fail_under: 0``
    through with the last value winning silently — the same silent gate
    removal an unknown key was. Checking the raw node keys before
    ``construct_mapping`` flattens merge keys means an explicit key may still
    legitimately override a ``<<`` merged one; two literal occurrences of the
    same key cannot.
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        seen: set[str] = set()
        for key_node, _ in node.value:
            if not isinstance(key_node, yaml.ScalarNode):
                continue  # a complex key is rejected later for being unhashable
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue  # `<<` merge entries are not literal duplicates
            if key_node.value in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"found duplicate key {key_node.value!r}", key_node.start_mark)
            seen.add(key_node.value)
        return super().construct_mapping(node, deep=deep)


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


def _is_number(value: object) -> bool:
    """True for int/float, never for bool — ``fail_under: yes`` is not a threshold."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_nonnegative(value: object) -> bool:
    """True for a finite int/float >= 0.

    NaN and the infinities pass ``isinstance`` but poison the math downstream:
    a NaN weight makes ``min(10, nan)`` return 10 (a fabricated grade A pass),
    and a NaN ``fail_under`` is never exceeded, so the gate silently disables
    itself.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value >= 0


def _validate_types(data: dict, config_path: Path) -> None:
    """Raise ConfigError on any wrongly typed value in a parsed config mapping.

    Only keys present in the file are checked — absent keys take defaults.
    ``standard`` and ``exclude`` stay lenient: an unknown standard warns and
    falls back, and exclude keeps its coercion in ``_normalized_exclude``.
    """
    def bad(key: str, want: str) -> ConfigError:
        return ConfigError(f"{config_path}: `{key}` must be {want}, got {data[key]!r}")

    if "sieves" in data:
        sieves = data["sieves"]
        if (not isinstance(sieves, list) or not sieves
                or not all(isinstance(s, str) for s in sieves)):
            raise bad("sieves", "a non-empty list of strings")
    if "weights" in data:
        weights = data["weights"]
        if (not isinstance(weights, dict)
                or not all(isinstance(k, str) for k in weights)
                or not all(_is_finite_nonnegative(v) for v in weights.values())):
            raise bad("weights", "a mapping of sieve name to a finite number >= 0")
    if "fail_under" in data and not _is_finite_nonnegative(data["fail_under"]):
        raise bad("fail_under", "a finite number >= 0")
    if "deterministic" in data and not isinstance(data["deterministic"], bool):
        raise bad("deterministic", "a boolean")
    if "format" in data and data["format"] not in ("terminal", "json", "sarif"):
        raise bad("format", "one of terminal/json/sarif")


def _validate_keys(data: dict, config_path: Path) -> None:
    """Raise ConfigError on keys outside the config schema.

    An unknown key used to be dropped silently — a ``fail-under`` typo read
    as "no gate at all", and a ``weights`` typo reweighted nothing while
    looking like a tweak. Names are case-sensitive: ``Fail_Under`` is an
    unknown key, not a typo to forgive.
    """
    unknown = sorted(str(k) for k in data if k not in DEFAULTS)
    if unknown:
        raise ConfigError(
            f"{config_path}: unknown key(s) {', '.join(unknown)}; "
            f"valid keys: {', '.join(DEFAULTS)}")
    weights = data.get("weights")
    if isinstance(weights, dict):
        bad_weights = sorted(str(k) for k in weights if k not in DEFAULTS["weights"])
        if bad_weights:
            raise ConfigError(
                f"{config_path}: unknown `weights` name(s) {', '.join(bad_weights)}; "
                f"valid names: {', '.join(DEFAULTS['weights'])}")


def _normalized_exclude(value: object) -> list[str]:
    """Coerce a YAML ``exclude`` value into a list of pattern strings.

    An empty ``exclude:`` key loads as None and crashed the scan; a bare string
    was iterated character by character, so ``exclude: tests`` excluded nothing.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


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
    # The file this config was loaded from; None for plain defaults. The
    # config lock needs it to spot a --config under a non-standard name.
    source_path: Path | None = None

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
        if not config_path.is_file():
            # A FIFO or device would block on open(); a directory fails anyway.
            # stat() never blocks, so check before touching the file.
            raise ConfigError(f"{config_path}: not a regular file")

        try:
            with open(config_path) as f:
                data = yaml.load(f, Loader=_UniqueKeyLoader)
        except yaml.YAMLError as e:
            raise ConfigError(f"{config_path}: invalid YAML: {e}") from e
        except (UnicodeDecodeError, RecursionError) as e:
            # Not-UTF-8 bytes and absurdly deep nesting are parse failures
            # too; they must not escape as tracebacks.
            raise ConfigError(f"{config_path}: cannot parse config: {e}") from e
        except OSError as e:
            raise ConfigError(f"{config_path}: cannot read config: {e}") from e

        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError(
                f"{config_path}: expected a mapping of settings, got {type(data).__name__}")
        _validate_keys(data, config_path)
        _validate_types(data, config_path)

        return cls(
            sieves=data.get("sieves", DEFAULTS["sieves"]),
            weights={**DEFAULTS["weights"], **data.get("weights", {})},
            fail_under=data.get("fail_under", 0.0),
            standard=_validated_standard(data.get("standard", DEFAULTS["standard"]), config_path),
            deterministic=data.get("deterministic", False),
            format=data.get("format", "terminal"),
            exclude=_normalized_exclude(data.get("exclude", DEFAULTS["exclude"])),
            source_path=config_path,
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

# Output format: terminal, json, sarif
format: terminal

# File patterns to exclude
exclude:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/__pycache__/**"
"""
