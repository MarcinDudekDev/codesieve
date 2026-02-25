"""TypeScript language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs.javascript import JSGuardClauseRules


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
)

register_lang_pack("typescript", _pack)
