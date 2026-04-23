"""Language packs — plug-and-play language-specific rules for sieves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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


_REGISTRY: dict[str, LanguagePack] = {}


def register_lang_pack(language: str, pack: LanguagePack) -> None:
    """Register a language pack for a given language identifier."""
    _REGISTRY[language] = pack


def get_lang_pack(language: str) -> LanguagePack | None:
    """Look up the language pack for a language. Returns None if not registered."""
    return _REGISTRY.get(language)


# Auto-import language modules to trigger registration
from codesieve.langs import python, php, javascript, typescript  # noqa: E402, F401
