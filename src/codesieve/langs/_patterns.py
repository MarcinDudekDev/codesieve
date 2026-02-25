"""Shared naming-convention regex patterns used by language packs."""

from __future__ import annotations

import re

SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
UPPER_SNAKE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PASCAL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
DUNDER = re.compile(r"^__[a-z][a-z0-9_]*__$")

ALLOWED_SHORT = {"i", "j", "k", "n", "x", "y", "z", "e", "f", "fd", "fn", "db", "id", "ip", "ok", "os", "re", "io", "_"}
SHORT_NAME_LIMIT = 2
