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
    allowed_short_names: frozenset[str]

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        """Return (is-valid, expected-convention) for a name in the given context.

        The second element is only consulted when the first is False — it is the
        human-readable convention quoted back in the finding ("snake_case",
        "PascalCase"), so it must name a convention, not describe the failure.
        """
        ...
    def func_context(self, node) -> str:
        """Return the context label ("function", "method", …) to validate this node's name under."""
        ...
    def extract_param_name(self, node, source: bytes) -> str | None:
        """Return the bare parameter name from a parameter node, or None if it carries none."""
        ...
    def check_variable_names(self, func: FunctionInfo, source: bytes, seen: set[str]) -> tuple[int, int, list[Finding]]:
        """Return (names checked, violations, findings) for local variables in one function.

        ``seen`` is mutated to hold the names already reported, so a variable
        reassigned throughout a function is counted and flagged only once.
        """
        ...


@runtime_checkable
class ErrorHandlingRules(Protocol):
    """Language-specific error handling rules."""
    supported: bool
    skip_reason: str
    handler_node_type: str
    broad_exception_types: frozenset[str]
    raise_types: tuple[str, ...]
    raise_skip_types: tuple[str, ...]

    def is_bare_handler(self, node) -> bool:
        """True if the handler names no exception type at all (`except:`, `catch {}`)."""
        ...
    def is_empty_body(self, node) -> bool:
        """True if the handler swallows the error — body is only `pass`/`...`/a comment."""
        ...
    def get_handler_body(self, node):
        """Return the handler's body block node, or None if the handler has none."""
        ...
    def get_caught_type_text(self, node, source: bytes) -> str | None:
        """Return the caught type's text when it is one of ``broad_exception_types``, else None.

        Returning None means "nothing to flag" — a narrow catch is never reported,
        so this doubles as the broad-catch test rather than a plain accessor.
        """
        ...
    def has_broad_catch_concept(self) -> bool:
        """True if "too broad a catch" is meaningful for this language at all.

        False disables broad-catch reporting entirely, for languages where the
        idiomatic handler necessarily catches everything.
        """
        ...


@runtime_checkable
class TypeHintRules(Protocol):
    """Language-specific type hint checking rules."""
    supported: bool
    skip_reason: str

    def check_params(self, func: FunctionInfo, source: bytes) -> tuple[int, int, list[Finding]]:
        """Return (annotatable params, annotated params, findings) for one function.

        The two counts feed the coverage ratio, so parameters that cannot carry an
        annotation (`self`, `cls`, `...`) must be left out of the total rather than
        counted as unannotated.
        """
        ...
    def check_extras(self, parsed: ParsedFile) -> tuple[float, str, list[Finding]]:
        """Return (extra penalty, summary suffix, findings) for file-level typing rules.

        Covers what per-parameter checking cannot see — e.g. a missing
        `declare(strict_types=1)`. Return `(0.0, "", [])` when there is nothing extra.
        """
        ...


@runtime_checkable
class MagicNumberRules(Protocol):
    """Language-specific magic number detection rules."""
    def is_default_param(self, node) -> bool:
        """True if the literal is a parameter default — already named by the parameter."""
        ...
    def is_constant_assignment(self, node, source: bytes) -> bool:
        """True if the literal is being bound to a named constant, so it is not magic."""
        ...
    def is_negated(self, node) -> bool:
        """True if the literal sits under a unary minus, so `-1` is judged as one value, not `1`."""
        ...


@runtime_checkable
class GuardClauseRules(Protocol):
    """Language-specific guard clause detection rules."""
    docstring_types: tuple[str, ...]

    def has_elif_or_else(self, if_node) -> bool:
        """True if the `if` has an elif/else branch, which rules it out as an invertible guard."""
        ...
    def is_docstring_node(self, node) -> bool:
        """True if the statement is a docstring, so it can be skipped when locating the real body."""
        ...


@runtime_checkable
class CommentRules(Protocol):
    """Language-specific docstring/comment coverage rules."""
    supported: bool
    skip_reason: str

    def has_docstring(self, func_node, source: bytes) -> bool:
        """True if the function carries the language's documentation form (docstring, JSDoc, …)."""
        ...
    def is_declaration_only(self, func_node, source: bytes) -> bool:
        """True if the function is a signature with no implementation.

        Such members (Protocol methods, `@overload` variants, interface and abstract
        stubs) are excluded from the coverage denominator entirely — the contract is
        documented by the enclosing class, so counting them scores a pure-protocol
        file 1.0 on nothing but one-line declarations.
        """
        ...


@runtime_checkable
class DeprecatedAPIRules(Protocol):
    """Language-specific deprecated API detection rules."""
    supported: bool
    skip_reason: str
    call_node_type: str
    deprecated_db: dict[str, tuple[str, str, str]]

    def extract_call_name(self, node, source: bytes) -> str | None:
        """Return the plain callee name to look up in ``deprecated_db``, or None to skip the node.

        Only bare calls resolve — a method or dynamic call returns None, because a
        matching *name* on some object is not the deprecated global function.
        """
        ...


@runtime_checkable
class ExtendedDeprecatedAPIRules(DeprecatedAPIRules, Protocol):
    """DeprecatedAPIRules with extra non-call-based pattern detection."""

    def check_extra_patterns(self, parsed: ParsedFile) -> list[tuple[Finding, float]]:
        """Return (finding, penalty) pairs for deprecated constructs that are not calls.

        Covers syntax the ``deprecated_db`` name lookup can never reach — `var`
        declarations, `with` blocks — each carrying its own score cost.
        """
        ...
