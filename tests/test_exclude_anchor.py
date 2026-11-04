"""Anchored single-segment patterns stay anchored; matching is polynomial."""

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


def test_single_segment_anchor_only_hits_top_level(tmp_path):
    _tree(tmp_path, "build/o.py", "pkg/build/o2.py", "tests/a.py", "pkg/tests/b.py")
    for pat in ("/build", "./build", f"{tmp_path}/build"):
        assert _rels(tmp_path, _collect_files(tmp_path, [pat])) == {
            "pkg/build/o2.py", "tests/a.py", "pkg/tests/b.py",
        }, pat


def test_anchored_dir_excludes_its_subtree(tmp_path):
    _tree(tmp_path, "tests/a.py", "tests/unit/x.py", "pkg/tests/b.py")
    assert _rels(tmp_path, _collect_files(tmp_path, ["/tests"])) == {"pkg/tests/b.py"}


def test_non_consecutive_double_star_is_polynomial(tmp_path):
    deep = "/".join("a" for _ in range(30)) + "/m.py"
    _tree(tmp_path, deep)
    pats = ["**/a/**/a/**/a/**/a/**/a/**/a/**/a/**/a/**/b.py",
            "*/**/*/**/*/**/*/**/*/**/*/**/*/**/*/x.py"]
    start = time.perf_counter()
    assert _rels(tmp_path, _collect_files(tmp_path, pats)) == {deep}
    assert time.perf_counter() - start < 0.5
