"""ParsedFile wrapper for tree-sitter parsed source code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter
import tree_sitter_python as tspython

from codesieve.parser.languages import LanguageMap, LANGUAGE_REGISTRY, detect_language
from codesieve.parser import ast_utils


PY_LANGUAGE = tree_sitter.Language(tspython.language())
_parser = tree_sitter.Parser(PY_LANGUAGE)

PARSERS: dict[str, tree_sitter.Parser] = {
    "python": _parser,
}


@dataclass
class FunctionInfo:
    """Extracted info about a function/method."""
    name: str
    node: tree_sitter.Node
    line_count: int
    param_count: int
    start_line: int


@dataclass
class ClassInfo:
    """Extracted info about a class."""
    name: str
    node: tree_sitter.Node
    method_count: int
    start_line: int


class ParsedFile:
    """Wrapper around a tree-sitter parse tree with convenience methods."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.language = detect_language(filepath)
        if self.language is None:
            raise ValueError(f"Unsupported file type: {filepath}")
        if self.language not in LANGUAGE_REGISTRY:
            raise ValueError(f"No language map for: {self.language}")
        if self.language not in PARSERS:
            raise ValueError(f"No parser for: {self.language}")

        self.lang_map: LanguageMap = LANGUAGE_REGISTRY[self.language]
        self.source: bytes = Path(filepath).read_bytes()
        self.source_text: str = self.source.decode("utf-8", errors="replace")
        self.tree: tree_sitter.Tree = PARSERS[self.language].parse(self.source)
        self.root: tree_sitter.Node = self.tree.root_node
        self.line_count: int = len(self.source_text.splitlines())

    def get_functions(self) -> list[FunctionInfo]:
        """Extract all function/method definitions."""
        nodes = ast_utils.find_nodes(self.root, self.lang_map.function_types)
        result = []
        for node in nodes:
            name_node = ast_utils.get_child_by_field(node, self.lang_map.name_field)
            name = ast_utils.get_node_text(name_node, self.source) if name_node else "<anonymous>"
            params = self._count_params(node)
            result.append(FunctionInfo(
                name=name,
                node=node,
                line_count=ast_utils.node_line_count(node),
                param_count=params,
                start_line=node.start_point[0] + 1,
            ))
        return result

    def get_classes(self) -> list[ClassInfo]:
        """Extract all class definitions."""
        nodes = ast_utils.find_nodes(self.root, self.lang_map.class_types)
        result = []
        for node in nodes:
            name_node = ast_utils.get_child_by_field(node, self.lang_map.name_field)
            name = ast_utils.get_node_text(name_node, self.source) if name_node else "<anonymous>"
            methods = ast_utils.find_nodes(node, self.lang_map.function_types)
            result.append(ClassInfo(
                name=name,
                node=node,
                method_count=len(methods),
                start_line=node.start_point[0] + 1,
            ))
        return result

    def get_comments(self) -> list[tree_sitter.Node]:
        """Find all comment nodes."""
        return ast_utils.find_nodes(self.root, self.lang_map.comment_types)

    def get_docstrings(self) -> list[tree_sitter.Node]:
        """Find docstring nodes (expression_statement containing a string as first child of function/class body)."""
        docstrings = []
        for func in ast_utils.find_nodes(self.root, self.lang_map.function_types + self.lang_map.class_types):
            body = func.child_by_field_name("body")
            if body and body.child_count > 0:
                first = body.children[0]
                if first.type == "expression_statement" and first.child_count > 0:
                    expr = first.children[0]
                    if expr.type in self.lang_map.string_types:
                        docstrings.append(expr)
        return docstrings

    def get_all_identifiers(self) -> list[tuple[str, int]]:
        """Get all identifier names and their line numbers."""
        identifiers = []
        for node in ast_utils.walk_tree(self.root):
            if node.type == "identifier":
                name = ast_utils.get_node_text(node, self.source)
                identifiers.append((name, node.start_point[0] + 1))
        return identifiers

    def _count_params(self, func_node: tree_sitter.Node) -> int:
        """Count parameters in a function definition."""
        params_node = func_node.child_by_field_name("parameters")
        if params_node is None:
            return 0
        count = 0
        for child in params_node.children:
            if child.type in ("identifier", "default_parameter", "typed_parameter",
                              "typed_default_parameter", "list_splat_pattern",
                              "dictionary_splat_pattern"):
                # Skip 'self' and 'cls' for methods
                if child.type == "identifier":
                    name = ast_utils.get_node_text(child, self.source)
                    if name in ("self", "cls"):
                        continue
                elif child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
                    name_child = child.child_by_field_name("name") or (child.children[0] if child.children else None)
                    if name_child:
                        name = ast_utils.get_node_text(name_child, self.source)
                        if name in ("self", "cls"):
                            continue
                count += 1
        return count
