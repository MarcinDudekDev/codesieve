"""PHP language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack


class PHPGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node) -> bool:
        return any(child.type in ("else_if_clause", "else_clause") for child in if_node.children)


_pack = LanguagePack(
    guard_clauses=PHPGuardClauseRules(),
)

register_lang_pack("php", _pack)
