"""Line-ending definitions shared by the parser and diff-scope mapping.

A parser row breaks on ``\\n`` or on a lone ``\\r`` — a ``\\r`` not followed
by ``\\n`` (see ``_normalize_lone_cr`` in ``treesitter.py``). git only counts
``\\n``, so any numbering that must agree between the two is defined here,
where both sides can import it without pulling in tree-sitter.
"""

import re

_LONE_CR = re.compile(rb"\r(?!\n)")
