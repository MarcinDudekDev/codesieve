"""Go language pack — rules for all sieves."""

from __future__ import annotations

import re

import tree_sitter

from codesieve.langs import LanguagePack, register_lang_pack
from codesieve.langs._patterns import PASCAL_CASE, CAMEL_CASE, ALLOWED_SHORT, SHORT_NAME_LIMIT
from codesieve.models import Finding
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import FunctionInfo, ParsedFile

_GO_ALLOWED_SHORT = frozenset("abcdefghijklmnopqrstuvwxyz") | ALLOWED_SHORT | {
    "c0", "c1", "c2", "rc", "as", "ch", "mu", "wg", "sb", "fn", "ts",
    "err", "ctx", "req", "res", "buf", "msg", "key", "val",
}
_GO_SHORT_LIMIT = 3

_HAS_UNDERSCORE_MIDDLE = re.compile(r".+_.+")


class GoGuardClauseRules:
    docstring_types: tuple[str, ...] = ()

    def has_elif_or_else(self, if_node: tree_sitter.Node) -> bool:
        return any(child.type == "else" for child in if_node.children)

    def is_docstring_node(self, node: tree_sitter.Node) -> bool:
        return False


class GoMagicNumberRules:
    def is_default_param(self, node: tree_sitter.Node) -> bool:
        return False  # Go has no default params

    def is_constant_assignment(self, node: tree_sitter.Node, source: bytes) -> bool:
        parent = node.parent
        if parent and parent.type == "unary_expression":
            parent = parent.parent
        if not parent:
            return False
        # Walk up through expression_list to const_spec
        if parent.type == "expression_list":
            parent = parent.parent
        return parent is not None and parent.type == "const_spec"

    def is_negated(self, node: tree_sitter.Node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "unary_expression"
            and any(c.type == "-" for c in parent.children)
        )


class GoErrorHandlingRules:
    supported = False
    skip_reason = "Go uses err != nil pattern — no try/catch to analyze"
    handler_node_type = ""
    broad_exception_types: frozenset[str] = frozenset()
    raise_types: tuple[str, ...] = ()
    raise_skip_types: tuple[str, ...] = ()

    def is_bare_handler(self, node: tree_sitter.Node) -> bool:
        return False

    def is_empty_body(self, node: tree_sitter.Node) -> bool:
        return False

    def get_handler_body(self, node: tree_sitter.Node) -> tree_sitter.Node | None:
        return None

    def get_caught_type_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        return None

    def has_broad_catch_concept(self) -> bool:
        return False


class GoTypeHintRules:
    supported = False
    skip_reason = "Go is statically typed — all parameters require explicit types"

    def check_params(self, func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
        return 0, 0, []

    def check_extras(self, parsed: ParsedFile) -> tuple[float, str, list[Finding]]:
        return 0.0, "", []


class GoDeprecatedAPIRules:
    supported = False
    skip_reason = "No deprecated API database for Go"
    call_node_type = "call_expression"
    deprecated_db: dict[str, tuple[str, str, str]] = {}

    def extract_call_name(self, node: tree_sitter.Node, source: bytes) -> str | None:
        return None


_GO_PARAM_NODE_TYPES = ("parameter_declaration", "variadic_parameter_declaration")


def _extract_param_name_go(child: tree_sitter.Node, source: bytes) -> str | None:
    for sub in child.children:
        if sub.type == "identifier":
            return ast_utils.get_node_text(sub, source)
    return None


def _validate_go_name(name: str) -> tuple[bool, str]:
    if not name or name == "_":
        return True, ""
    if _HAS_UNDERSCORE_MIDDLE.match(name):
        return False, f"'{name}' should be camelCase or PascalCase (no underscores)"
    if PASCAL_CASE.match(name) or CAMEL_CASE.match(name):
        return True, ""
    return False, f"'{name}' should be camelCase or PascalCase"


_GO_ALLOWED_PARAMS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
) | {"c0", "c1", "c2", "rc", "as", "ch", "mu", "wg", "sb", "ts", "ss", "bs", "rs",
     "err", "ctx", "req", "res", "buf", "msg", "key", "val", "fn", "ok", "id", "ip",
     "n1", "n2", "i0", "i1", "b0", "b1", "s0", "s1", "s2"}


class GoNamingRules:
    skip_param_names: frozenset[str] = frozenset({"_"})
    param_node_types = _GO_PARAM_NODE_TYPES
    allowed_short_names = _GO_ALLOWED_PARAMS

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        return _validate_go_name(name)

    def func_context(self, node: tree_sitter.Node) -> str:
        return "method" if node.type == "method_declaration" else "function"

    def extract_param_name(self, node: tree_sitter.Node, source: bytes) -> str | None:
        return _extract_param_name_go(node, source)

    def check_variable_names(self, func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
        body = func.node.child_by_field_name("body")
        if not body:
            return 0, 0, []

        total = 0
        violations = 0
        findings: list[Finding] = []

        for node in ast_utils.walk_within_scope(body):
            if node.type != "short_var_declaration":
                continue
            lhs = node.child_by_field_name("left")
            if not lhs:
                continue
            for child in lhs.children:
                if child.type != "identifier":
                    continue
                name = ast_utils.get_node_text(child, source)
                if not name or name in seen or name == "_":
                    continue
                seen.add(name)
                total += 1
                if len(name) <= _GO_SHORT_LIMIT and name in _GO_ALLOWED_SHORT:
                    continue
                valid, reason = _validate_go_name(name)
                if not valid:
                    violations += 1
                    findings.append(Finding(
                        message=reason,
                        line=node.start_point[0] + 1,
                        function=func.name,
                        severity="warning",
                    ))
                elif len(name) <= SHORT_NAME_LIMIT and name not in _GO_ALLOWED_SHORT:
                    violations += 1
                    findings.append(Finding(
                        message=f"abbreviated variable '{name}' in {func.name}()",
                        line=node.start_point[0] + 1,
                        function=func.name,
                        severity="info",
                    ))

        return total, violations, findings


class GoCommentRules:
    supported = True
    skip_reason = ""

    def has_docstring(self, func_node: tree_sitter.Node, source: bytes) -> bool:
        prev = func_node.prev_named_sibling
        return prev is not None and prev.type == "comment"


_pack = LanguagePack(
    guard_clauses=GoGuardClauseRules(),
    magic_numbers=GoMagicNumberRules(),
    error_handling=GoErrorHandlingRules(),
    type_hints=GoTypeHintRules(),
    naming=GoNamingRules(),
    deprecated_api=GoDeprecatedAPIRules(),
    comments=GoCommentRules(),
)

register_lang_pack("go", _pack)
