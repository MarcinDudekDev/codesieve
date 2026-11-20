"""Shared AST walking helpers for tree-sitter nodes."""

from __future__ import annotations

import hashlib
from typing import Iterator

import tree_sitter

FUNCTION_BOUNDARY_TYPES = (
    "function_definition", "class_definition",
    # PHP-specific
    "method_declaration", "anonymous_function", "arrow_function", "class_declaration",
    # JS/TS-specific
    "function_declaration", "method_definition", "generator_function_declaration",
    "function_expression",
    # Go-specific. A closure is a function in its own right — it is in the Go
    # language map's function_types, so the sieves grade it separately — and
    # without it here a walk of the enclosing function descends into the closure
    # too, counting every name, branch and literal inside it twice.
    "func_literal",
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


def named_descendant_counts(root: tree_sitter.Node) -> dict[int, int]:
    """Named-node count for every node under ``root``, in one bottom-up pass.

    The count is the complexity floor that ignores trivia like `i + 1`. Asking
    about every candidate expression by walking its subtree instead is quadratic
    on a long operator chain, so one pass answers them all. Leaves that exist
    only because of a CRLF break are skipped — the LF twin does not have them.
    """
    counts: dict[int, int] = {}
    pending: list[tuple[tree_sitter.Node, bool]] = [(root, False)]
    while pending:
        node, expanded = pending.pop()
        if not expanded:
            pending.append((node, True))
            pending.extend((child, False) for child in node.children)
            continue
        own = 1 if node.is_named and not _is_crlf_only_leaf(node) else 0
        counts[node.id] = own + sum(counts[child.id] for child in node.children)
    return counts


def _leaf_token(node: tree_sitter.Node, source: bytes, protected: bool,
                identifier_types: tuple[str, ...], blank_identifiers: bool) -> str | None:
    """How a leaf renders, or ``None`` when the node has children and needs a fold.

    Shared by the text form and the digest form so the blanking and CRLF rules
    cannot drift apart between them.
    """
    if _is_crlf_only_leaf(node):
        return ""
    if blank_identifiers and not protected and node.type in identifier_types:
        return "§ID§"
    if not node.children:
        return _decode_slice(source, node.start_byte, node.end_byte)
    return None


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
    rendered: dict[int, str] = {}
    # Walked with an explicit stack, exactly as if this recursed: a long chain of
    # operators (`a + b + c + …` a few thousand deep) would otherwise exhaust
    # Python's recursion limit and crash the whole scan on generated code.
    pending: list[tuple[tree_sitter.Node, bool, bool]] = [(node, False, False)]
    while pending:
        current, protected, expanded = pending.pop()
        if expanded:
            callee = current.child_by_field_name("function") if current.type in call_types else None
            callee_id = callee.id if callee is not None else None
            inner = "".join(rendered.pop(child.id) for child in current.children)
            rendered[current.id] = f"({current.type}{inner})"
            continue
        token = _leaf_token(current, source, protected, identifier_types, blank_identifiers)
        if token is not None:
            rendered[current.id] = token
            continue
        # ``protected`` propagates down a call's callee, so the function
        # *being* called keeps its name while its arguments are still
        # blanked — otherwise `foo(a)` and `bar(a)` would normalize alike and
        # read as a repetition.
        pending.append((current, protected, True))
        callee = current.child_by_field_name("function") if current.type in call_types else None
        callee_id = callee.id if callee is not None else None
        for child in reversed(current.children):
            pending.append((child, protected or child.id == callee_id, False))
    return rendered[node.id]


def _digest(kind: str, children: list[str]) -> str:
    """Fold a node's type and its rendered children into a fixed-width digest.

    Empty child digests are skipped: they are CRLF-only leaves, which the text
    form contributes nothing for, so hashing them would make a CRLF twin differ
    from its LF original.
    """
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(kind.encode())
    for child in children:
        if not child:
            continue
        hasher.update(b"\0")
        hasher.update(child.encode())
    return hasher.hexdigest()


def normalize_subtree_digests(
    root: tree_sitter.Node,
    source: bytes,
    identifier_types: tuple[str, ...] = (),
    call_types: tuple[str, ...] = (),
    blank_identifiers: bool = True,
) -> dict[int, str]:
    """Structural digest for every node under ``root``, in one bottom-up pass.

    The same walk and the same rules as `normalize_subtree`, but each node is
    folded into a fixed-width hash of its children's digests rather than a string
    containing them. That keeps a whole tree linear in memory and, because one
    pass answers every node, linear in time: asking `normalize_subtree` about
    each of the ~5000 nested expressions of a 5000-term operator chain rendered
    another copy of the chain each time and took ~50 s.

    Digests come from the tree, so a node reached through a call's callee field
    carries callee protection here even if a caller would render it as a root.
    Equal digests therefore mean equal normalized text only up to that context
    and a hash collision; a caller acting on a group must confirm the exact text.
    """
    digests: dict[int, str] = {}
    pending: list[tuple[tree_sitter.Node, bool, bool]] = [(root, False, False)]
    while pending:
        current, protected, expanded = pending.pop()
        if expanded:
            digests[current.id] = _digest(
                current.type, [digests[child.id] for child in current.children]
            )
            continue
        token = _leaf_token(current, source, protected, identifier_types, blank_identifiers)
        if token is not None:
            digests[current.id] = token
            continue
        pending.append((current, protected, True))
        callee = current.child_by_field_name("function") if current.type in call_types else None
        callee_id = callee.id if callee is not None else None
        for child in reversed(current.children):
            pending.append((child, protected or child.id == callee_id, False))
    return digests
