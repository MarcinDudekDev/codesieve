"""TypeScript language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs.javascript import JSGuardClauseRules, JSMagicNumberRules

_js_magic = JSMagicNumberRules()


class TSMagicNumberRules:
    """TS default params differ from JS; const/negation reuse JS logic."""

    def is_default_param(self, node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in ("required_parameter", "optional_parameter"):
                return True
            if parent.type in ("function_declaration", "method_definition",
                               "arrow_function", "generator_function_declaration",
                               "class_declaration"):
                break
            parent = parent.parent
        return False

    def is_constant_assignment(self, node, source: bytes) -> bool:
        return _js_magic.is_constant_assignment(node, source)

    def is_negated(self, node) -> bool:
        return _js_magic.is_negated(node)


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
    magic_numbers=TSMagicNumberRules(),
)

register_lang_pack("typescript", _pack)
