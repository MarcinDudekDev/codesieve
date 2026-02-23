"""Language-specific tree-sitter node type mappings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageMap:
    """Maps abstract concepts to tree-sitter node types for a language."""
    function_types: tuple[str, ...]
    class_types: tuple[str, ...]
    parameter_types: tuple[str, ...]
    branch_types: tuple[str, ...]  # nodes that increase cyclomatic complexity
    nesting_types: tuple[str, ...]  # nodes that increase nesting depth
    comment_types: tuple[str, ...]
    string_types: tuple[str, ...]
    name_field: str  # field name for identifiers
    file_extension: str


PYTHON = LanguageMap(
    function_types=("function_definition",),
    class_types=("class_definition",),
    parameter_types=("identifier",),  # within parameters node
    branch_types=(
        "if_statement", "elif_clause", "for_statement", "while_statement",
        "except_clause", "with_statement", "assert_statement",
        "boolean_operator",  # `and` / `or` add branch paths
        "conditional_expression",  # ternary
        "list_comprehension", "set_comprehension", "dictionary_comprehension",
        "generator_expression",
    ),
    nesting_types=(
        "if_statement", "for_statement", "while_statement",
        "with_statement", "try_statement", "except_clause",
    ),
    comment_types=("comment",),
    string_types=("string", "concatenated_string"),
    name_field="name",
    file_extension=".py",
)

LANGUAGE_REGISTRY: dict[str, LanguageMap] = {
    "python": PYTHON,
}


def detect_language(filepath: str) -> str | None:
    """Detect language from file extension."""
    ext_map = {".py": "python", ".js": "javascript", ".php": "php"}
    from pathlib import Path
    ext = Path(filepath).suffix
    return ext_map.get(ext)
