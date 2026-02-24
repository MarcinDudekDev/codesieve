"""DeprecatedAPI sieve — detects calls to deprecated or removed PHP functions."""

from __future__ import annotations

from codesieve.models import Finding, SieveResult
from codesieve.parser.treesitter import ParsedFile
from codesieve.parser import ast_utils
from codesieve.scoring import SCORE_MAX
from codesieve.sieves.base import BaseSieve

# Penalty per deprecated call by severity
REMOVED_PENALTY = 1.0
DEPRECATED_PENALTY = 0.5

# PHP deprecated/removed functions: name -> (replacement, severity, PHP version)
PHP_DEPRECATED: dict[str, tuple[str, str, str]] = {
    # Removed in PHP 7 — mysql_* extension
    "mysql_connect": ("PDO or mysqli_connect()", "removed", "7.0"),
    "mysql_query": ("PDO::query() or mysqli_query()", "removed", "7.0"),
    "mysql_fetch_array": ("PDO::fetch() or mysqli_fetch_array()", "removed", "7.0"),
    "mysql_fetch_assoc": ("PDO::fetch(PDO::FETCH_ASSOC)", "removed", "7.0"),
    "mysql_fetch_row": ("PDO::fetch(PDO::FETCH_NUM)", "removed", "7.0"),
    "mysql_close": ("PDO = null or mysqli_close()", "removed", "7.0"),
    "mysql_select_db": ("PDO DSN or mysqli_select_db()", "removed", "7.0"),
    "mysql_real_escape_string": ("PDO prepared statements", "removed", "7.0"),
    "mysql_num_rows": ("PDOStatement::rowCount()", "removed", "7.0"),
    "mysql_error": ("PDO::errorInfo() or mysqli_error()", "removed", "7.0"),
    # Removed in PHP 7 — POSIX regex
    "ereg": ("preg_match()", "removed", "7.0"),
    "eregi": ("preg_match() with 'i' flag", "removed", "7.0"),
    "ereg_replace": ("preg_replace()", "removed", "7.0"),
    "eregi_replace": ("preg_replace() with 'i' flag", "removed", "7.0"),
    "split": ("preg_split() or explode()", "removed", "7.0"),
    "spliti": ("preg_split() with 'i' flag", "removed", "7.0"),
    # Removed in PHP 8.0
    "each": ("foreach loop", "removed", "8.0"),
    "create_function": ("anonymous function (closure)", "removed", "8.0"),
    "money_format": ("NumberFormatter::formatCurrency()", "removed", "8.0"),
    "restore_include_path": ("ini_restore('include_path')", "removed", "8.0"),
    # Deprecated in PHP 8.1
    "strftime": ("IntlDateFormatter::format()", "deprecated", "8.1"),
    "gmstrftime": ("IntlDateFormatter::format() with UTC", "deprecated", "8.1"),
    # Deprecated in PHP 8.2
    "utf8_encode": ("mb_convert_encoding($s, 'UTF-8', 'ISO-8859-1')", "deprecated", "8.2"),
    "utf8_decode": ("mb_convert_encoding($s, 'ISO-8859-1', 'UTF-8')", "deprecated", "8.2"),
}


class DeprecatedAPISieve(BaseSieve):
    name = "DeprecatedAPI"
    description = "Detects calls to deprecated or removed PHP functions"
    default_weight = 0.05

    def analyze(self, parsed: ParsedFile) -> SieveResult:
        if parsed.language != "php":
            return self.perfect("Not applicable (non-PHP file)")

        findings: list[Finding] = []
        score = SCORE_MAX

        for node in ast_utils.walk_tree(parsed.root):
            if node.type != "function_call_expression":
                continue
            func_name_node = node.child_by_field_name("function")
            if not func_name_node or func_name_node.type != "name":
                continue
            func_name = ast_utils.get_node_text(func_name_node, parsed.source)

            if func_name not in PHP_DEPRECATED:
                continue

            replacement, severity, version = PHP_DEPRECATED[func_name]
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
