"""DRY sieve — detects duplicate function bodies and repeated inline expressions."""

from __future__ import annotations

import hashlib
from collections import defaultdict

import tree_sitter

from codesieve.models import Finding, SieveResult
from codesieve.parser import ast_utils
from codesieve.parser.treesitter import FunctionInfo, ParsedFile
from codesieve.scoring import SCORE_MAX
from codesieve.sieves import dry_rules
from codesieve.sieves.base import BaseSieve

MIN_BODY_LINES = 3
PENALTY_PER_DUPLICATE = 1.5

# Part (a): repeated inline-expression detection.
MIN_OCCURRENCES = 3  # how many times an expression must repeat (within one file) to flag
MIN_EXPR_NODES = 4  # complexity floor (named-node count) so trivia like `i + 1` is ignored
BLANK_IDENTIFIERS = True  # match expressions that differ only in variable names
EXPR_PENALTY = 0.4  # score cost per extra occurrence beyond the threshold
EXPR_PENALTY_CAP = 2.0  # max cost charged for any single repeated-expression group
SNIPPET_MAX = 60  # max chars of the offending expression shown in a finding

# Part (b): stdlib/framework-helper reimplementation hints (info-level, never hard-fail).
STDLIB_PENALTY = 0.5  # light cost per reimplementation hint
STDLIB_PENALTY_CAP = 2.0  # total cost ceiling for all stdlib hints in a file


def _normalize(text: str) -> str:
    """Strip leading/trailing whitespace per line and drop blank lines."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _body_hash(func: FunctionInfo, source: bytes) -> str | None:
    """Hash a function body for exact-duplicate grouping, or None if it is too short to judge.

    Indentation and blank lines are normalized away first, so the same body at a
    different nesting level still collides. Bodies under ``MIN_BODY_LINES`` return
    None — a one-liner repeated across accessors is not duplication worth naming.
    """
    body = func.node.child_by_field_name("body")
    if body is None:
        return None
    raw = source[body.start_byte:body.end_byte].decode("utf-8", errors="replace")
    norm = _normalize(raw)
    if norm.count("\n") + 1 < MIN_BODY_LINES:
        return None
    return hashlib.md5(norm.encode()).hexdigest()  # noqa: S324


def _snippet(node: tree_sitter.Node, source: bytes) -> str:
    """One-line, whitespace-collapsed preview of an expression."""
    raw = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    flat = " ".join(raw.split())
    return flat if len(flat) <= SNIPPET_MAX else flat[:SNIPPET_MAX - 1] + "…"


class _ExprGroup:
    """A set of structurally-identical expression occurrences sharing one normalized form."""

    __slots__ = ("nodes",)

    def __init__(self) -> None:
        self.nodes: list[tree_sitter.Node] = []

    @property
    def first(self) -> tree_sitter.Node:
        """The earliest-collected occurrence — the one a finding points at and reports."""
        return self.nodes[0]


class DrySieve(BaseSieve):
    name = "DRY"
    description = "Detects duplicate function bodies and repeated inline expressions"
    default_weight = 0.15

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        """Measure repetition on three axes: duplicate bodies, repeated expressions, reinvented helpers.

        Each costs its own penalty off a perfect score, heaviest for a wholly
        duplicated function body and lightest (advisory only) for a stdlib hint.
        """
        named = [f for f in parsed.get_functions() if f.name != "<anonymous>"]

        body_findings, body_dups, dup_func_nodes = self._duplicate_bodies(named, parsed.source)
        expr_findings, expr_penalty = self._repeated_expressions(parsed, dup_func_nodes)
        stdlib_findings, stdlib_penalty = self._stdlib_reimplementations(parsed)

        findings = body_findings + expr_findings + stdlib_findings
        if not findings:
            if not named:
                return self.perfect("No functions found")
            return self.perfect("No duplicate bodies or repeated expressions found")

        score = SCORE_MAX - PENALTY_PER_DUPLICATE * body_dups - expr_penalty - stdlib_penalty
        parts = []
        if body_dups:
            parts.append(f"{body_dups} duplicate function body(ies)")
        if expr_findings:
            parts.append(f"{len(expr_findings)} repeated expression(s)")
        if stdlib_findings:
            parts.append(f"{len(stdlib_findings)} stdlib-reimplementation hint(s)")
        return self.result(score, " and ".join(parts) + " found", findings)

    # ---- Existing behaviour: duplicate function bodies ---------------------------------
    def _duplicate_bodies(
        self, named: list[FunctionInfo], source: bytes,
    ) -> tuple[list[Finding], int, set[int]]:
        """Group functions by body hash and report every member after the first as a duplicate.

        Also returns the node ids of *all* members, original included, so the
        expression pass can skip them — a duplicated body would otherwise be charged
        a second time for every expression it repeats.
        """
        groups: dict[str, list[FunctionInfo]] = defaultdict(list)
        for func in named:
            h = _body_hash(func, source)
            if h is not None:
                groups[h].append(func)

        findings: list[Finding] = []
        total_dups = 0
        dup_func_nodes: set[int] = set()
        for funcs in groups.values():
            if len(funcs) < 2:
                continue
            original = funcs[0]
            for func in funcs:
                dup_func_nodes.add(func.node.id)  # every member, incl. original, is "covered"
            for dup in funcs[1:]:
                total_dups += 1
                findings.append(Finding(
                    message=f"{dup.name}() duplicates {original.name}() — extract shared logic",
                    line=dup.start_line,
                    function=dup.name,
                    severity="warning",
                ))
        return findings, total_dups, dup_func_nodes

    # ---- Part (a): repeated inline expressions -----------------------------------------
    def _repeated_expressions(
        self, parsed: ParsedFile, dup_func_nodes: set[int],
    ) -> tuple[list[Finding], float]:
        """Report expressions repeated ``MIN_OCCURRENCES`` times or more, with their penalty.

        Occurrences are matched on structure, not text, so the same computation
        spelled with different variable names still groups. Only the largest repeated
        unit survives, and the cost per group is capped so one hot expression cannot
        sink the whole file's score.
        """
        expr_types = parsed.lang_map.dedup_expr_types
        if not expr_types:
            return [], 0.0

        candidates = self._collect_candidates(parsed, expr_types, dup_func_nodes)

        groups: dict[str, _ExprGroup] = defaultdict(_ExprGroup)
        for node in candidates:
            key = ast_utils.normalize_subtree(
                node, parsed.source,
                identifier_types=parsed.lang_map.identifier_types,
                call_types=parsed.lang_map.call_types,
                blank_identifiers=BLANK_IDENTIFIERS,
            )
            groups[key].nodes.append(node)

        qualifying = [g for g in groups.values() if len(g.nodes) >= MIN_OCCURRENCES]
        kept = self._suppress_nested(qualifying)

        findings: list[Finding] = []
        penalty = 0.0
        for group in sorted(kept, key=lambda g: g.first.start_point[0]):
            count = len(group.nodes)
            findings.append(Finding(
                message=(f"expression `{_snippet(group.first, parsed.source)}` repeated "
                         f"{count}× — extract a named helper"),
                line=group.first.start_point[0] + 1,
                severity="warning",
            ))
            penalty += min(EXPR_PENALTY_CAP, EXPR_PENALTY * (count - (MIN_OCCURRENCES - 1)))
        return findings, penalty

    # ---- Part (b): stdlib/framework-helper reimplementation hints ----------------------
    def _stdlib_reimplementations(self, parsed: ParsedFile) -> tuple[list[Finding], float]:
        rules = dry_rules.rules_for(parsed.language)
        if not rules:
            return [], 0.0

        seen: set[tuple[str, int]] = set()  # (rule id, dedup scope) — one hint per scope
        findings: list[Finding] = []
        for node in ast_utils.walk_tree(parsed.root):
            for rule in rules:
                suggestion = rule.predicate(node, parsed)
                if suggestion is None:
                    continue
                key = (suggestion.rule, suggestion.dedup_scope)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(
                    message=suggestion.message,
                    line=node.start_point[0] + 1,
                    severity="info",  # advisory only — never hard-fail
                ))
        penalty = min(STDLIB_PENALTY_CAP, STDLIB_PENALTY * len(findings))
        return findings, penalty

    def _collect_candidates(
        self, parsed: ParsedFile, expr_types: tuple[str, ...], dup_func_nodes: set[int],
    ) -> list[tree_sitter.Node]:
        """Gather non-trivial expression nodes, skipping any inside a flagged duplicate body.

        A candidate must embed inline *logic worth naming* — an operator or literal
        (``dedup_significant_types``) — so that a bare `helper(a, b)` call (the correct,
        already-extracted pattern) is never flagged just for being called repeatedly.
        """
        significant = parsed.lang_map.dedup_significant_types
        candidates: list[tree_sitter.Node] = []
        for node in ast_utils.walk_tree(parsed.root):
            if node.type not in expr_types:
                continue
            if ast_utils.named_descendant_count(node) < MIN_EXPR_NODES:
                continue
            if not self._has_significant_content(node, significant):
                continue
            if self._inside_dup_body(node, dup_func_nodes):
                continue
            candidates.append(node)
        return candidates

    @staticmethod
    def _has_significant_content(node: tree_sitter.Node, significant: tuple[str, ...]) -> bool:
        if not significant:
            return True
        return any(n.type in significant for n in ast_utils.walk_tree(node))

    @staticmethod
    def _inside_dup_body(node: tree_sitter.Node, dup_func_nodes: set[int]) -> bool:
        if not dup_func_nodes:
            return False
        current = node.parent
        while current is not None:
            if current.id in dup_func_nodes:
                return True
            current = current.parent
        return False

    @staticmethod
    def _suppress_nested(groups: list[_ExprGroup]) -> list[_ExprGroup]:
        """Keep the largest repeated unit; drop groups whose every occurrence nests inside it."""
        ordered = sorted(groups, key=lambda g: g.first.end_byte - g.first.start_byte, reverse=True)
        kept: list[_ExprGroup] = []
        claimed: list[tuple[int, int]] = []  # byte ranges already covered by kept (larger) groups
        for group in ordered:
            if all(
                any(start <= n.start_byte and n.end_byte <= end for start, end in claimed)
                for n in group.nodes
            ):
                continue
            kept.append(group)
            claimed.extend((n.start_byte, n.end_byte) for n in group.nodes)
        return kept
