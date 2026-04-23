"""DeprecatedAPI sieve — detects calls to deprecated or removed functions."""

from __future__ import annotations

from codesieve.langs import get_lang_pack
from codesieve.langs.protocols import ExtendedDeprecatedAPIRules
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

REMOVED_PENALTY = 1.0
DEPRECATED_PENALTY = 0.5


def _make_finding(func_name: str, entry: tuple[str, str, str], line: int) -> tuple[Finding, float]:
    """Build a Finding and its penalty from a deprecated DB entry."""
    replacement, severity, version = entry
    if severity == "removed":
        msg = f"{func_name}() removed in {version} — use {replacement}"
        return Finding(message=msg, line=line, severity="error"), REMOVED_PENALTY
    msg = f"{func_name}() deprecated since {version} — use {replacement}"
    return Finding(message=msg, line=line, severity="warning"), DEPRECATED_PENALTY


def _build_summary(findings: list[Finding]) -> str:
    """Summarise deprecated API findings."""
    removed = sum(1 for f in findings if f.severity == "error")
    deprecated = sum(1 for f in findings if f.severity == "warning")
    parts = []
    if removed:
        parts.append(f"{removed} removed")
    if deprecated:
        parts.append(f"{deprecated} deprecated")
    return f"{' + '.join(parts)} pattern(s) found"


class DeprecatedAPISieve(BaseSieve):
    name = "DeprecatedAPI"
    description = "Detects calls to deprecated or removed functions"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        pack = get_lang_pack(parsed.language)
        rules = pack.deprecated_api if pack else None

        if rules is None or not rules.supported:
            return self.skip(f"No deprecated-API rules for {parsed.language}")

        findings: list[Finding] = []
        score = SCORE_MAX

        for node in ast_utils.walk_tree(parsed.root):
            if node.type != rules.call_node_type:
                continue
            func_name = rules.extract_call_name(node, parsed.source)
            if func_name is None or func_name not in rules.deprecated_db:
                continue
            finding, penalty = _make_finding(func_name, rules.deprecated_db[func_name], node.start_point[0] + 1)
            score -= penalty
            findings.append(finding)

        if isinstance(rules, ExtendedDeprecatedAPIRules):
            for finding, penalty in rules.check_extra_patterns(parsed):
                score -= penalty
                findings.append(finding)

        if not findings:
            return self.perfect("No deprecated API calls found")

        return self.result(score, _build_summary(findings), findings)
