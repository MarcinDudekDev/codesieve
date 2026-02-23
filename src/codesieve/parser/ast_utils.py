"""Shared AST walking helpers for tree-sitter nodes."""

from __future__ import annotations

from typing import Iterator

import tree_sitter


def walk_tree(node: tree_sitter.Node) -> Iterator[tree_sitter.Node]:
    """Yield all nodes in the tree via depth-first traversal."""
    yield node
    for child in node.children:
        yield from walk_tree(child)


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


def nesting_depth(node: tree_sitter.Node, nesting_types: tuple[str, ...]) -> int:
    """Calculate the nesting depth of a node by counting nesting ancestors."""
    depth = 0
    current = node.parent
    while current is not None:
        if current.type in nesting_types:
            depth += 1
        current = current.parent
    return depth


def max_nesting_in_subtree(root: tree_sitter.Node, nesting_types: tuple[str, ...]) -> int:
    """Find the maximum nesting depth within a subtree."""
    max_depth = 0
    for node in walk_tree(root):
        if node.type in nesting_types:
            depth = nesting_depth(node, nesting_types) + 1  # +1 for this node itself
            max_depth = max(max_depth, depth)
    return max_depth
