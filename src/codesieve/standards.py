"""Coding-standard selection — which convention set a file is graded against.

A "standard" picks between mutually incompatible convention sets for the same
language. PHP is the motivating case: PSR-1/PSR-12 wants camelCase methods and
PascalCase classes, while the WordPress Coding Standards mandate snake_case
methods and Capitalized_Words_With_Underscores classes. Grading WordPress code
against PSR produces violations for code that is correct for its ecosystem.
"""

from __future__ import annotations

import re

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


def looks_like_wordpress(filepath: str, source_text: str) -> bool:
    """Heuristically decide whether a PHP file belongs to a WordPress codebase."""
    normalized_path = filepath.replace("\\", "/")
    if any(f"/{marker}/" in f"/{normalized_path}/" for marker in _WP_PATH_MARKERS):
        return True
    hits = sum(1 for pattern in _WP_SOURCE_MARKERS if pattern.search(source_text))
    return hits >= _MIN_SOURCE_MARKERS


def resolve(standard: str, language: str, filepath: str, source_text: str) -> str:
    """Resolve a possibly-``auto`` standard into a concrete one for this file."""
    if standard != AUTO:
        return standard
    if language == "php" and looks_like_wordpress(filepath, source_text):
        return WORDPRESS
    return DEFAULT
