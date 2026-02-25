"""JavaScript language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack


class JSGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node) -> bool:
        return any(child.type == "else_clause" for child in if_node.children)


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
)

register_lang_pack("javascript", _pack)
