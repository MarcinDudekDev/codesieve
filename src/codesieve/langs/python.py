"""Python language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack


class PythonGuardClauseRules:
    docstring_types = ("string", "concatenated_string")

    def has_elif_or_else(self, if_node) -> bool:
        return any(child.type in ("elif_clause", "else_clause") for child in if_node.children)


_pack = LanguagePack(
    guard_clauses=PythonGuardClauseRules(),
)

register_lang_pack("python", _pack)
