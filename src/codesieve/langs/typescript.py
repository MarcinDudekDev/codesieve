"""TypeScript language pack — rules for all sieves."""

from __future__ import annotations

import tree_sitter

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs.javascript import JSGuardClauseRules, JSMagicNumberRules, JSErrorHandlingRules, JSNamingRules, JSDeprecatedAPIRules, JSCommentRules
from codesieve.models import Finding
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import FunctionInfo, ParsedFile

_js_magic = JSMagicNumberRules()


class TSMagicNumberRules:
    """TS default params differ from JS; const/negation reuse JS logic."""

    def is_default_param(self, node: tree_sitter.Node) -> bool:
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

    def is_constant_assignment(self, node: tree_sitter.Node, source: bytes) -> bool:
        return _js_magic.is_constant_assignment(node, source)

    def is_negated(self, node: tree_sitter.Node) -> bool:
        return _js_magic.is_negated(node)


_TS_PARAM_TYPES = ("required_parameter", "optional_parameter")


def _get_param_name_ts(child: tree_sitter.Node, source: bytes) -> str | None:
    for sub in child.children:
        if sub.type == "identifier":
            return ast_utils.get_node_text(sub, source)
        if sub.type == "rest_pattern":
            return _first_identifier(sub, source)
    return None


def _first_identifier(node: tree_sitter.Node, source: bytes) -> str | None:
    """Return the text of the first identifier child."""
    for child in node.children:
        if child.type == "identifier":
            return ast_utils.get_node_text(child, source)
    return None


class TSTypeHintRules:
    supported = True
    skip_reason = ""

    def check_params(self, func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
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

    def check_extras(self, parsed: ParsedFile) -> tuple[float, str, list[Finding]]:
        return 0.0, "", []


_TS_NAMING_PARAM_NODE_TYPES = ("required_parameter", "optional_parameter")

_js_naming = JSNamingRules()


class TSNamingRules:
    """TS uses same validation as JS but different param node types."""
    skip_param_names: frozenset[str] = frozenset()
    param_node_types = _TS_NAMING_PARAM_NODE_TYPES

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        return _js_naming.validate_name(name, context)

    def func_context(self, node: tree_sitter.Node) -> str:
        return _js_naming.func_context(node)

    def extract_param_name(self, node: tree_sitter.Node, source: bytes) -> str | None:
        return _get_param_name_ts(node, source)

    def check_variable_names(self, func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
        return _js_naming.check_variable_names(func, source, seen)


_pack = LanguagePack(
    guard_clauses=JSGuardClauseRules(),
    magic_numbers=TSMagicNumberRules(),
    type_hints=TSTypeHintRules(),
    error_handling=JSErrorHandlingRules(),
    naming=TSNamingRules(),
    deprecated_api=JSDeprecatedAPIRules(),
    comments=JSCommentRules(),
)

register_lang_pack("typescript", _pack)
