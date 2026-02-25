"""Protocol definitions for language-specific sieve rules."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from codesieve.models import Finding
from codesieve.parser.treesitter import FunctionInfo, ParsedFile


@runtime_checkable
class NamingRules(Protocol):
    """Language-specific naming convention rules."""
    skip_param_names: frozenset[str]
    param_node_types: tuple[str, ...]

    def validate_name(self, name: str, context: str) -> tuple[bool, str]: ...
    def func_context(self, node) -> str: ...
    def extract_param_name(self, node, source: bytes) -> str | None: ...
    def check_variable_names(self, func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]: ...


@runtime_checkable
class ErrorHandlingRules(Protocol):
    """Language-specific error handling rules."""
    handler_node_type: str
    broad_exception_types: frozenset[str]
    raise_types: tuple[str, ...]
    raise_skip_types: tuple[str, ...]

    def is_bare_handler(self, node) -> bool: ...
    def is_empty_body(self, node) -> bool: ...
    def get_handler_body(self, node): ...
    def get_caught_type_text(self, node, source: bytes) -> str | None: ...
    def has_broad_catch_concept(self) -> bool: ...


@runtime_checkable
class TypeHintRules(Protocol):
    """Language-specific type hint checking rules."""
    supported: bool
    skip_reason: str

    def check_params(self, func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]: ...
    def check_extras(self, parsed: ParsedFile) -> tuple[float, str, list[Finding]]: ...


@runtime_checkable
class MagicNumberRules(Protocol):
    """Language-specific magic number detection rules."""
    def is_default_param(self, node) -> bool: ...
    def is_constant_assignment(self, node, source: bytes) -> bool: ...
    def is_negated(self, node) -> bool: ...


@runtime_checkable
class GuardClauseRules(Protocol):
    """Language-specific guard clause detection rules."""
    docstring_types: tuple[str, ...]

    def has_elif_or_else(self, if_node) -> bool: ...


@runtime_checkable
class DeprecatedAPIRules(Protocol):
    """Language-specific deprecated API detection rules."""
    supported: bool
    skip_reason: str
    call_node_type: str
    deprecated_db: dict[str, tuple[str, str, str]]

    def extract_call_name(self, node, source: bytes) -> str | None: ...
