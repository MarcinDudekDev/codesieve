"""WordPress PHP language pack — WPCS conventions instead of PSR-1/PSR-12.

Only the rules where the WordPress Coding Standards actively contradict PSR are
overridden; everything else (error handling, magic numbers, deprecated APIs,
nesting, the type-coverage check itself) is shared with the PSR pack.
"""

from __future__ import annotations

import re
from dataclasses import replace

from codesieve import standards
from codesieve.langs import register_lang_pack
from codesieve.langs._patterns import SNAKE_CASE, UPPER_SNAKE
from codesieve.langs.php import PHP_MAGIC_METHODS, PHPNamingRules, PHPTypeHintRules
from codesieve.langs.php import _pack as _psr_pack
from codesieve.models import Finding
from codesieve.parser.treesitter import ParsedFile

#: WPCS class names: Capitalized_Words_With_Underscores, e.g. SQ_Probe, Log_Normalizer.
WP_CLASS_CASE = re.compile(r"^[A-Z][A-Za-z0-9]*(_[A-Z][A-Za-z0-9]*)*$")


class WordPressNamingRules(PHPNamingRules):
    """WPCS naming: snake_case callables, Capitalized_Words_With_Underscores classes."""

    def validate_name(self, name: str, context: str) -> tuple[bool, str]:
        if PHP_MAGIC_METHODS.match(name):
            return True, ""
        if context == "class":
            if WP_CLASS_CASE.match(name):
                return True, ""
            return False, f"class '{name}' should be Capitalized_Words_With_Underscores (WPCS)"
        if context == "constant":
            if UPPER_SNAKE.match(name):
                return True, ""
            return False, f"constant '{name}' should be UPPER_SNAKE_CASE (WPCS)"
        if SNAKE_CASE.match(name):
            return True, ""
        label = "method" if context == "method" else "function"
        return False, f"{label} '{name}' should be snake_case (WPCS)"


class WordPressTypeHintRules(PHPTypeHintRules):
    """Same type-coverage requirement as PSR, minus the strict_types expectation.

    Modern WordPress plugins can and should declare parameter and return types;
    ``declare(strict_types=1)`` is the part that is not customary, because core
    targets broad PHP compatibility.
    """

    def check_extras(self, parsed: ParsedFile) -> tuple[float, str, list[Finding]]:
        return 0.0, "", []


_pack = replace(
    _psr_pack,
    naming=WordPressNamingRules(),
    type_hints=WordPressTypeHintRules(),
)

register_lang_pack("php", _pack, standards.WORDPRESS)
