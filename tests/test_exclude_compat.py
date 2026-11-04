"""Exclude-pattern forms that worked under the old Path.match and must keep working."""

import time
from pathlib import Path

from codesieve.engine import _collect_files

SRC = "x = 1\n"


def _tree(root: Path, *rels: str) -> None:
    for rel in rels:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(SRC)


def _rels(root: Path, files: list[Path]) -> set[str]:
    return {f.relative_to(root).as_posix() for f in files}


def test_dot_slash_prefix_is_ignored(tmp_path):
    _tree(tmp_path, "src/app/m.py", "src/tests/t.py")
    assert _rels(tmp_path, _collect_files(tmp_path, ["./src/tests/*"])) == {"src/app/m.py"}


def test_absolute_pattern_under_scan_root(tmp_path):
    _tree(tmp_path, "src/app/m.py", "src/tests/t.py")
    pat = f"{tmp_path}/src/tests/*"
    assert _rels(tmp_path, _collect_files(tmp_path, [pat])) == {"src/app/m.py"}


def test_repeated_double_star_stays_fast(tmp_path):
    deep = "/".join(f"d{i}" for i in range(30)) + "/m.py"
    _tree(tmp_path, deep)
    start = time.perf_counter()
    assert _collect_files(tmp_path, ["**/**/**/**/**/**/x.py"])
    assert time.perf_counter() - start < 0.05
