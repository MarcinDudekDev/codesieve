"""Language packs — plug-and-play language-specific rules for sieves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codesieve import standards

if TYPE_CHECKING:
    from codesieve.langs.protocols import (
        CommentRules,
        DeprecatedAPIRules,
        ErrorHandlingRules,
        GuardClauseRules,
        MagicNumberRules,
        NamingRules,
        TypeHintRules,
    )


@dataclass(frozen=True)
class LanguagePack:
    naming: NamingRules
    error_handling: ErrorHandlingRules
    magic_numbers: MagicNumberRules
    guard_clauses: GuardClauseRules
    type_hints: TypeHintRules | None = None
    deprecated_api: DeprecatedAPIRules | None = None
    comments: CommentRules | None = None


_REGISTRY: dict[tuple[str, str], LanguagePack] = {}


def register_lang_pack(language: str, pack: LanguagePack, standard: str = standards.FALLBACK) -> None:
    """Register a language pack, optionally as the variant for a coding standard."""
    _REGISTRY[(language, standard)] = pack


def get_lang_pack(language: str, standard: str = standards.FALLBACK) -> LanguagePack | None:
    """Look up the pack for a language under a coding standard.

    Falls back to the language's default pack when it has no variant for the
    requested standard — most languages have exactly one convention set.
    """
    return _REGISTRY.get((language, standard)) or _REGISTRY.get((language, standards.FALLBACK))


# Auto-import language modules to trigger registration
from codesieve.langs import python, php, php_wordpress, javascript, typescript, go  # noqa: E402, F401
