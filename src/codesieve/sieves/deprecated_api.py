"""DeprecatedAPI sieve — detects calls to deprecated or removed functions."""

from __future__ import annotations

from codesieve.langs import get_lang_pack
from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

REMOVED_PENALTY = 1.0
DEPRECATED_PENALTY = 0.5


class DeprecatedAPISieve(BaseSieve):
    name = "DeprecatedAPI"
    description = "Detects calls to deprecated or removed functions"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        pack = get_lang_pack(parsed.language)
        rules = pack.deprecated_api if pack else None

        if rules is None or not rules.supported:
            return self.skip("Not applicable (non-PHP file)")

        findings: list[Finding] = []
        score = SCORE_MAX

        for node in ast_utils.walk_tree(parsed.root):
            if node.type != rules.call_node_type:
                continue
            func_name = rules.extract_call_name(node, parsed.source)
            if func_name is None or func_name not in rules.deprecated_db:
                continue

            replacement, severity, version = rules.deprecated_db[func_name]
            penalty = REMOVED_PENALTY if severity == "removed" else DEPRECATED_PENALTY
            score -= penalty

            if severity == "removed":
                msg = f"{func_name}() removed in PHP {version} — use {replacement}"
                sev = "error"
            else:
                msg = f"{func_name}() deprecated since PHP {version} — use {replacement}"
                sev = "warning"

            findings.append(Finding(
                message=msg,
                line=node.start_point[0] + 1,
                severity=sev,
            ))

        if not findings:
            return self.perfect("No deprecated API calls found")

        removed = sum(1 for f in findings if f.severity == "error")
        deprecated = sum(1 for f in findings if f.severity == "warning")
        parts = []
        if removed:
            parts.append(f"{removed} removed")
        if deprecated:
            parts.append(f"{deprecated} deprecated")
        summary = f"{' + '.join(parts)} function call(s) found"

        return self.result(score, summary, findings)
