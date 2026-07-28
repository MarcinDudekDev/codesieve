"""Coding-standard selection — which convention set a file is graded against.

A "standard" picks between mutually incompatible convention sets for the same
language. PHP is the motivating case: PSR-1/PSR-12 wants camelCase methods and
PascalCase classes, while the WordPress Coding Standards mandate snake_case
methods and Capitalized_Words_With_Underscores classes. Grading WordPress code
against PSR produces violations for code that is correct for its ecosystem.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

PSR = "psr"
WORDPRESS = "wordpress"
AUTO = "auto"

#: The standard applied when nothing else is configured.
DEFAULT = PSR

#: Registry fallback key — the pack used when a language has no variant
#: registered for the requested standard.
FALLBACK = "default"

CHOICES = (PSR, WORDPRESS, AUTO)

#: Path segments that only occur inside a WordPress install.
_WP_PATH_MARKERS = ("wp-content", "wp-includes", "wp-admin")

#: Plugin/theme file headers and WordPress-only APIs. Any single hit is weak,
#: so detection requires a path marker or two independent source markers.
_WP_SOURCE_MARKERS = (
    re.compile(r"^\s*\*?\s*(Plugin|Theme) Name:", re.MULTILINE),
    re.compile(r"\badd_(action|filter|shortcode|meta_box)\s*\("),
    re.compile(r"\b(esc_html|esc_attr|esc_url|sanitize_text_field|wp_nonce_field)\s*\("),
    re.compile(r"\b(get_option|update_option|register_activation_hook|plugin_dir_path)\s*\("),
    re.compile(r"\bABSPATH\b"),
    re.compile(r"\b(WP_Error|WP_Query|WP_REST_Response|wpdb)\b"),
)

_MIN_SOURCE_MARKERS = 2

#: Path segments holding third-party code. Their naming conventions describe
#: their authors, not this codebase, so they are excluded from the naming vote —
#: a Composer ``vendor/`` tree is large and overwhelmingly camelCase, and would
#: otherwise outvote the plugin that depends on it.
_VENDORED_SEGMENTS = ("vendor", "node_modules")


def looks_like_wordpress(filepath: str, source_text: str) -> bool:
    """Heuristically decide whether a PHP file belongs to a WordPress codebase.

    This answers "is this the WordPress ecosystem?", NOT "does this code follow
    WPCS naming?" — the two have drifted apart, and plenty of post-2020 plugin
    code uses PSR-style method names inside WordPress-shaped files.
    """
    normalized_path = filepath.replace("\\", "/")
    if any(f"/{marker}/" in f"/{normalized_path}/" for marker in _WP_PATH_MARKERS):
        return True
    hits = sum(1 for pattern in _WP_SOURCE_MARKERS if pattern.search(source_text))
    return hits >= _MIN_SOURCE_MARKERS


def is_vendored(filepath: str) -> bool:
    """Check whether a path lies inside a third-party dependency tree."""
    normalized = f"/{filepath.replace(chr(92), '/')}/"
    return any(f"/{segment}/" in normalized for segment in _VENDORED_SEGMENTS)


def count_naming_styles(names: Iterable[str]) -> tuple[int, int]:
    """Count decisively snake_case vs decisively camelCase callable names.

    Takes names extracted from the parse tree, never from raw source. Matching
    ``function name(`` textually would count declarations written inside
    comments, string literals and heredocs — which both misgrades legitimate
    code (a WordPress plugin embedding inline JS in a heredoc) and hands
    anyone a way to steer the standard from a comment.

    Names that carry no case signal (``render``) or mix both (``get_Foo``) are
    excluded — they vote for neither standard. Magic methods are excluded too,
    since ``__construct`` is mandated by PHP, not by a style guide.
    """
    snake = 0
    camel = 0
    for name in names:
        if name.startswith("__") or name == "<anonymous>":
            continue
        stripped = name.lstrip("_")
        has_separator = "_" in stripped
        has_uppercase = any(char.isupper() for char in stripped)
        if has_separator and not has_uppercase:
            snake += 1
        elif has_uppercase and not has_separator:
            camel += 1
    return snake, camel


def follows_wpcs_naming(snake: int, camel: int) -> bool:
    """Decide whether the naming vote supports WPCS conventions.

    Ties (including no evidence at all) go to WordPress, so a file with no
    decisive names defers to the ecosystem signal that got us here.
    """
    return snake >= camel


def resolve(standard: str, language: str, filepath: str, source_text: str,
            names: Iterable[str] = ()) -> str:
    """Resolve a standard into a concrete one for one file.

    Standards describe PHP conventions, so any other language always reports the
    default — labelling a Python file "wordpress" because a PHP sibling won the
    corpus vote would be noise, and grading is unaffected either way since the
    registry has no non-PHP variants.

    Single-file resolution has only that file's names to vote with. Directory
    scans use :func:`resolve_for_corpus`, which pools the vote so every file in
    a codebase is graded against the same standard.
    """
    if language != "php":
        return DEFAULT
    if standard != AUTO:
        return standard
    if not looks_like_wordpress(filepath, source_text):
        return DEFAULT
    return WORDPRESS if follows_wpcs_naming(*count_naming_styles(names)) else DEFAULT


def resolve_for_corpus(standard: str, sources: list[tuple[str, str, list[str]]]) -> str:
    """Resolve ``auto`` once for a set of ``(filepath, source_text, names)`` PHP files.

    The path says which ecosystem the code lives in; the pooled naming vote says
    which standard it actually follows. A hybrid codebase — WPCS file and class
    names but predominantly camelCase methods — resolves to PSR, because grading
    it as WPCS would flag every one of those methods.

    Vendored trees are excluded from the vote but still count toward ecosystem
    detection: they are part of the install, they just do not speak for the
    codebase's own conventions.
    """
    if standard != AUTO:
        return standard
    if not any(looks_like_wordpress(path, text) for path, text, _ in sources):
        return DEFAULT

    total_snake = 0
    total_camel = 0
    for path, _, names in sources:
        if is_vendored(path):
            continue
        snake, camel = count_naming_styles(names)
        total_snake += snake
        total_camel += camel

    return WORDPRESS if follows_wpcs_naming(total_snake, total_camel) else DEFAULT
