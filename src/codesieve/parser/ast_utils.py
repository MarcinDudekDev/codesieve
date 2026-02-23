"""Shared AST walking helpers for tree-sitter nodes."""

from __future__ import annotations

from typing import Iterator

import tree_sitter

FUNCTION_BOUNDARY_TYPES = ("function_definition",)


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


def get_node_text(node: tree_sitter.Node, source: bytes) -> str:
    """Extract source text for a node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


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
