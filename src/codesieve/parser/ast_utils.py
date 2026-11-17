"""Shared AST walking helpers for tree-sitter nodes."""

from __future__ import annotations

from typing import Iterator

import tree_sitter

FUNCTION_BOUNDARY_TYPES = (
    "function_definition", "class_definition",
    # PHP-specific
    "method_declaration", "anonymous_function", "arrow_function", "class_declaration",
    # JS/TS-specific
    "function_declaration", "method_definition", "generator_function_declaration",
    "function_expression",
)


def walk_tree(node: tree_sitter.Node) -> Iterator[tree_sitter.Node]:
    """Yield all nodes in the tree via depth-first traversal."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def walk_within_scope(root: tree_sitter.Node) -> Iterator[tree_sitter.Node]:
    """Walk tree but stop at nested function boundaries.

    Yields all descendants of root except those inside nested function_definition nodes.
    The root itself is always yielded even if it is a function_definition.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        yield current
        for child in reversed(current.children):
            if child.type in FUNCTION_BOUNDARY_TYPES:
                continue
            stack.append(child)


def find_nodes(root: tree_sitter.Node, types: tuple[str, ...]) -> list[tree_sitter.Node]:
    """Find all nodes of given types in the tree."""
    return [n for n in walk_tree(root) if n.type in types]


def _decode_slice(source: bytes, start: int, end: int) -> str:
    """Decode a source slice, folding CRLF to LF so compared or printed text reads like the LF twin.

    A leaf can end at the CR of its line with the LF sitting just past the cut
    (Python and Go comment nodes do this), leaving a ``\\r`` with no ``\\n``
    inside the slice to fold into. The LF twin's leaf ends before the break, so
    a trailing ``\\r`` whose next source byte is ``\\n`` is dropped with the
    slice, not folded.
    """
    if source[end - 1:end] == b"\r" and source[end:end + 1] == b"\n":
        end -= 1
    return source[start:end].decode("utf-8", errors="replace").replace("\r\n", "\n")


def _is_crlf_only_leaf(node: tree_sitter.Node) -> bool:
    """True for a leaf the grammar emits only because a line break is CRLF.

    The JS/TSX grammar tokenises a whitespace-only ``jsx_text`` run into a leaf
    unless the run starts with ``\\n``. A run starting with CR — necessarily the
    CR of a CRLF pair, since a lone CR never reaches the tree — therefore yields
    a leaf the LF twin does not have. Runs starting with space or tab exist on
    both sides, and any run containing real text is kept for its content, so
    only break-led pure-whitespace ``jsx_text`` leaves are skipped.
    """
    if node.type != "jsx_text":  # type first: node.text copies bytes and this runs per node
        return False
    text = node.text or b""
    return text[:1] in (b"\r", b"\n") and not text.strip()


def get_node_text(node: tree_sitter.Node, source: bytes) -> str:
    """Extract source text for a node."""
    return _decode_slice(source, node.start_byte, node.end_byte)


def node_line_count(node: tree_sitter.Node) -> int:
    """Count the number of lines a node spans."""
    return node.end_point[0] - node.start_point[0] + 1


def get_child_by_field(node: tree_sitter.Node, field_name: str) -> tree_sitter.Node | None:
    """Get a child node by field name."""
    return node.child_by_field_name(field_name)


def nesting_depth(node: tree_sitter.Node, nesting_types: tuple[str, ...], stop_at: tree_sitter.Node | None = None) -> int:
    """Calculate the nesting depth of a node by counting nesting ancestors.

    Stops at stop_at node if provided (to avoid counting ancestors above the function root).
    """
    depth = 0
    current = node.parent
    while current is not None and current is not stop_at:
        if current.type in nesting_types:
            depth += 1
        current = current.parent
    return depth


def max_nesting_in_subtree(root: tree_sitter.Node, nesting_types: tuple[str, ...]) -> int:
    """Find the maximum nesting depth within a subtree, not crossing into nested functions."""
    max_depth = 0
    for node in walk_within_scope(root):
        if node.type in nesting_types:
            depth = nesting_depth(node, nesting_types, stop_at=root) + 1
            max_depth = max(max_depth, depth)
    return max_depth


def named_descendant_count(node: tree_sitter.Node) -> int:
    """Count named nodes in a subtree (including the node itself).

    Used as a complexity floor so trivial expressions (e.g. `i + 1`) are ignored.
    Leaves that exist only because of a CRLF break are skipped — the LF twin
    does not have them.
    """
    return sum(1 for n in walk_tree(node) if n.is_named and not _is_crlf_only_leaf(n))


def normalize_subtree(
    node: tree_sitter.Node,
    source: bytes,
    identifier_types: tuple[str, ...] = (),
    call_types: tuple[str, ...] = (),
    blank_identifiers: bool = True,
) -> str:
    """Serialize a subtree into a canonical, structure-preserving string.

    Literal values (numbers, strings) and operators are kept verbatim so that
    `1024 * 1024` stays distinct from `1024 / 1024`. When ``blank_identifiers`` is
    set, variable-reference nodes (``identifier_types``) are replaced with a single
    placeholder — except callee names, which sit in the ``function`` field of a
    ``call_types`` node and are preserved so `round(...)` never collides with `floor(...)`.
    Two expressions that differ only in their variable names normalize to the same string.
    """
    def serialize(n: tree_sitter.Node, protected: bool) -> str:
        """Render one node as its normalized form, recursing into children.

        ``protected`` propagates down a call's callee, so the function *being*
        called keeps its name while its arguments are still blanked — otherwise
        `foo(a)` and `bar(a)` would normalize alike and read as a repetition.
        """
        if _is_crlf_only_leaf(n):
            return ""
        if blank_identifiers and not protected and n.type in identifier_types:
            return "§ID§"
        if not n.children:
            return _decode_slice(source, n.start_byte, n.end_byte)
        callee = n.child_by_field_name("function") if n.type in call_types else None
        callee_id = callee.id if callee is not None else None
        inner = "".join(
            serialize(child, protected or child.id == callee_id) for child in n.children
        )
        return f"({n.type}{inner})"

    return serialize(node, protected=False)
