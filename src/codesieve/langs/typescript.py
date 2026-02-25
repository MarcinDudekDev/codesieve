"""TypeScript language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs.javascript import JSGuardClauseRules, JSMagicNumberRules, JSErrorHandlingRules
from codesieve.parser import ast_utils

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


_TS_PARAM_TYPES = ("required_parameter", "optional_parameter")


def _get_param_name_ts(child, source: bytes) -> str | None:
    for sub in child.children:
        if sub.type == "identifier":
            return ast_utils.get_node_text(sub, source)
        if sub.type == "rest_pattern":
            for subsub in sub.children:
                if subsub.type == "identifier":
                    return ast_utils.get_node_text(subsub, source)
    return None


class TSTypeHintRules:
    supported = True
    skip_reason = ""

    def check_params(self, func, source: bytes) -> tuple[int, int, list]:
        from codesieve.models import Finding
        params_node = func.node.child_by_field_name("parameters")
        if params_node is None:
            return 0, 0, []

        total = 0
        annotated = 0
        findings: list[Finding] = []

        for child in params_node.children:
            if child.type not in _TS_PARAM_TYPES:
                continue
            name = _get_param_name_ts(child, source)
            if name is None:
                continue
            total += 1
            if child.child_by_field_name("type"):
                annotated += 1
            else:
                prefix = "..." if any(sub.type == "rest_pattern" for sub in child.children) else ""
                findings.append(Finding(
                    message=f"parameter '{prefix}{name}' in {func.name}() missing type annotation",
                    line=func.start_line, function=func.name, severity="info",
                ))

        return total, annotated, findings

    def check_extras(self, parsed) -> tuple[float, str, list]:
        return 0.0, "", []


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
    magic_numbers=TSMagicNumberRules(),
    type_hints=TSTypeHintRules(),
    error_handling=JSErrorHandlingRules(),
)

register_lang_pack("typescript", _pack)
