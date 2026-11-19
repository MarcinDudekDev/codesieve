"""ParsedFile wrapper for tree-sitter parsed source code."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import tree_sitter
import tree_sitter_python as tspython
import tree_sitter_php as tsphp
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import tree_sitter_go as tsgo

from codesieve import standards
from codesieve.parser.languages import LanguageMap, LANGUAGE_REGISTRY, detect_language
from codesieve.parser import _LONE_CR, ast_utils


PY_LANGUAGE = tree_sitter.Language(tspython.language())
PHP_LANGUAGE = tree_sitter.Language(tsphp.language_php())
JS_LANGUAGE = tree_sitter.Language(tsjs.language())
TS_LANGUAGE = tree_sitter.Language(tsts.language_typescript())
TSX_LANGUAGE = tree_sitter.Language(tsts.language_tsx())
GO_LANGUAGE = tree_sitter.Language(tsgo.language())

PARSERS: dict[str, tree_sitter.Parser] = {
    "python": tree_sitter.Parser(PY_LANGUAGE),
    "php": tree_sitter.Parser(PHP_LANGUAGE),
    "javascript": tree_sitter.Parser(JS_LANGUAGE),
    "typescript": tree_sitter.Parser(TS_LANGUAGE),
    "go": tree_sitter.Parser(GO_LANGUAGE),
}

TSX_PARSER = tree_sitter.Parser(TSX_LANGUAGE)


@dataclass
class FunctionInfo:
    """Extracted info about a function/method."""
    name: str
    node: tree_sitter.Node
    param_count: int
    start_line: int
    code_line_count: int
    """Lines excluding the function's own docstring.

    Deliberately has no default: KISS scores length exclusively from this, so an
    omitted value would silently read as a zero-line function and grade perfect
    on length. Better a TypeError at the construction site.

    Length is a proxy for how much a reader must hold in their head, and a
    docstring reduces that rather than adding to it. Python puts its docstring
    inside the body while PHP/JS/Go put theirs above the declaration, so counting
    raw lines charged Python — and only Python — for being documented.
    """


@dataclass
class ClassInfo:
    """Extracted info about a class."""
    name: str
    node: tree_sitter.Node
    method_count: int
    start_line: int


_HEREDOC_BODY_TYPES = ("heredoc", "heredoc_body", "nowdoc", "nowdoc_body")


class SourceParseError(ValueError):
    """Raised when tree-sitter could not parse the file.

    A tree carrying ERROR or MISSING nodes is not a smaller version of the file.
    The sieves would grade whatever fragments survived, and a file whose body
    failed to parse looks like a file with no functions at all — the best score
    Comments, TypeHints and Naming can give. Refusing to grade is the only
    honest answer, and it rides the crash path: the engine records it on
    ``ScanReport.errors`` and the CLI exits 2.
    """


def _first_error_line(root: tree_sitter.Node) -> int | None:
    """1-based line of the leftmost ERROR or MISSING node, or None if the tree is clean.

    MISSING counts as much as ERROR: tree-sitter repairs a truncated construct by
    inserting a zero-width node of the type it wanted, and that sets
    ``has_error`` on the root just the same.
    """
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            return node.start_point[0] + 1
        stack.extend(reversed(node.children))
    return None


def _normalize_lone_cr(source: bytes) -> bytes:
    """Turn classic-Mac CR line breaks into LF so tree-sitter sees the rows.

    tree-sitter only counts ``\\n`` as a row break, so a CR-only file would
    parse as one row of ERROR nodes. Swapping a lone CR for LF is a 1:1 byte
    replacement — length and every byte offset stay valid — and ``\\r\\n``
    pairs are left untouched.
    """
    if b"\r" not in source:
        return source
    return _LONE_CR.sub(b"\n", source)


class ParsedFile:
    """Wrapper around a tree-sitter parse tree with convenience methods."""

    def __init__(self, filepath: str, standard: str = standards.DEFAULT):
        """Read and parse the file, raising ValueError if its language is unsupported.

        Everything the sieves need is settled here: the language map, the raw bytes
        (sieves slice these, so the text form is only a convenience), and the
        resolved coding standard — resolution needs the parsed callables, so it
        happens last.
        """
        self.filepath = filepath
        self.language = detect_language(filepath)
        if self.language is None:
            raise ValueError(f"Unsupported file type: {filepath}")
        if self.language not in LANGUAGE_REGISTRY:
            raise ValueError(f"No language map for: {self.language}")
        if self.language not in PARSERS:
            raise ValueError(f"No parser for: {self.language}")

        self.lang_map: LanguageMap = LANGUAGE_REGISTRY[self.language]
        self.source: bytes = _normalize_lone_cr(Path(filepath).read_bytes())
        self.source_text: str = self.source.decode("utf-8", errors="replace")
        # TSX files need a separate parser
        if self.language == "typescript" and filepath.endswith(".tsx"):
            parser = TSX_PARSER
        else:
            parser = PARSERS[self.language]
        self.tree: tree_sitter.Tree = parser.parse(self.source)
        self.root: tree_sitter.Node = self.tree.root_node
        if self.root.has_error:
            line = _first_error_line(self.root)
            where = f"syntax error on line {line}" if line else "syntax error"
            raise SourceParseError(
                f"{where}: the file does not parse, so it cannot be graded"
            )
        self.line_count: int = len(self.source_text.splitlines())
        self.standard: str = standards.resolve(
            standard, self.language, filepath, self.source_text, self.callable_names(),
        )

    def callable_names(self) -> list[str]:
        """Names of every named function/method, taken from the parse tree.

        Used by the naming vote, which must never read declarations out of
        comments or string literals.
        """
        return [f.name for f in self.get_functions() if f.name != "<anonymous>"]

    def get_functions(self) -> list[FunctionInfo]:
        """Extract all function/method definitions (cached)."""
        return self._functions

    def get_classes(self) -> list[ClassInfo]:
        """Extract all class definitions (cached)."""
        return self._classes

    @cached_property
    def _functions(self) -> list[FunctionInfo]:
        """Walk the tree once for every function/method, caching the result.

        A function with no name node — a lambda or arrow function — is kept, under
        the name ``<anonymous>``; callers that only grade declarations filter it out.
        """
        nodes = ast_utils.find_nodes(self.root, self.lang_map.function_types)
        result = []
        for node in nodes:
            name_node = ast_utils.get_child_by_field(node, self.lang_map.name_field)
            name = ast_utils.get_node_text(name_node, self.source) if name_node else "<anonymous>"
            params = self._count_params(node)
            total_lines = ast_utils.node_line_count(node)
            result.append(FunctionInfo(
                name=name, node=node,
                param_count=params, start_line=node.start_point[0] + 1,
                code_line_count=total_lines - self._docstring_line_count(node),
            ))
        return result

    def docstring_statement(self, func_node: tree_sitter.Node) -> tree_sitter.Node | None:
        """Return the statement node holding the function's docstring, or None.

        The single owner of "where a docstring sits" for this parser — used by
        get_docstrings, by KISS's length count and by DRY's body hash, which
        must all agree. Only the language's in-body position counts: PHP, JS and
        Go document above the declaration, so those lines are never inside the
        node and this correctly returns None.
        """
        body = func_node.child_by_field_name("body")
        if body is None or body.child_count == 0:
            return None
        first = body.children[0]
        if first.type != "expression_statement" or first.child_count == 0:
            return None
        if first.children[0].type not in self.lang_map.string_types:
            return None
        return first

    def _docstring_line_count(self, func_node: tree_sitter.Node) -> int:
        """Return how many lines the function's own docstring occupies, 0 if it has none."""
        stmt = self.docstring_statement(func_node)
        return ast_utils.node_line_count(stmt) if stmt is not None else 0

    @cached_property
    def _classes(self) -> list[ClassInfo]:
        """Walk the tree once for every class, caching the result with its method count."""
        nodes = ast_utils.find_nodes(self.root, self.lang_map.class_types)
        result = []
        for node in nodes:
            name_node = ast_utils.get_child_by_field(node, self.lang_map.name_field)
            name = ast_utils.get_node_text(name_node, self.source) if name_node else "<anonymous>"
            methods = ast_utils.find_nodes(node, self.lang_map.function_types)
            result.append(ClassInfo(
                name=name, node=node,
                method_count=len(methods), start_line=node.start_point[0] + 1,
            ))
        return result

    def get_comments(self) -> list[tree_sitter.Node]:
        """Find all real comment nodes.

        The PHP grammar tags a `#` or `//` line inside a heredoc body as a
        ``comment`` node. That is string content, so those are dropped here
        for every caller. Only DIRECT children of a heredoc body are dropped:
        a real comment inside an interpolated expression sits deeper and is
        kept. The lookup goes top-down from the heredoc nodes because
        ``node.parent`` is linear in tree-sitter and would make a file with
        many comments quadratic.
        """
        comment_types = self.lang_map.comment_types
        heredoc_text = {
            child.id
            for body in ast_utils.find_nodes(self.root, _HEREDOC_BODY_TYPES)
            for child in body.children
            if child.type in comment_types
        }
        nodes = ast_utils.find_nodes(self.root, comment_types)
        return [node for node in nodes if node.id not in heredoc_text]

    def get_docstrings(self) -> list[tree_sitter.Node]:
        """Find docstring nodes (expression_statement containing a string as first child of function/class body)."""
        docstrings = []
        for func in ast_utils.find_nodes(self.root, self.lang_map.function_types + self.lang_map.class_types):
            stmt = self.docstring_statement(func)
            if stmt is not None:
                docstrings.append(stmt.children[0])
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
        if self.language == "php":
            return self._count_params_php(params_node)
        if self.language == "javascript":
            return self._count_params_js(params_node)
        if self.language == "typescript":
            return self._count_params_ts(params_node)
        if self.language == "go":
            return self._count_params_go(params_node)
        return self._count_params_python(params_node)

    def _count_params_python(self, params_node: tree_sitter.Node) -> int:
        count = 0
        for child in params_node.children:
            if child.type in ("identifier", "default_parameter", "typed_parameter",
                              "typed_default_parameter", "list_splat_pattern",
                              "dictionary_splat_pattern"):
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

    def _count_params_php(self, params_node: tree_sitter.Node) -> int:
        count = 0
        for child in params_node.children:
            # property_promotion_parameter is the PHP 8 `public int $x` form — a
            # parameter like any other, so it belongs in the count.
            if child.type in ("simple_parameter", "variadic_parameter",
                              "property_promotion_parameter"):
                count += 1
        return count

    def _count_params_js(self, params_node: tree_sitter.Node) -> int:
        """Count JS parameters: identifier, assignment_pattern, rest_pattern, destructuring."""
        count = 0
        for child in params_node.children:
            if child.type in ("identifier", "assignment_pattern", "rest_pattern",
                              "object_pattern", "array_pattern"):
                count += 1
        return count

    def _count_params_ts(self, params_node: tree_sitter.Node) -> int:
        """Count TS parameters: required_parameter, optional_parameter."""
        count = 0
        for child in params_node.children:
            if child.type in ("required_parameter", "optional_parameter"):
                count += 1
        return count

    def _count_params_go(self, params_node: tree_sitter.Node) -> int:
        """Count Go parameters, handling multi-name declarations like (x, y int)."""
        count = 0
        for child in params_node.children:
            if child.type == "parameter_declaration":
                names = [c for c in child.children if c.type == "identifier"]
                count += max(len(names), 1)
            elif child.type == "variadic_parameter_declaration":
                count += 1
        return count
