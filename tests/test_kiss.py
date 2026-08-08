"""Tests for the KISS sieve."""

from pathlib import Path

from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.kiss import KissSieve

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_good_code_scores_high():
    parsed = ParsedFile(str(FIXTURES / "good.py"))
    result = KissSieve().analyze(parsed)
    assert result.score >= 7.0, f"Good code should score >=7, got {result.score}"
    assert not result.skipped


def test_bad_code_scores_low():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = KissSieve().analyze(parsed)
    assert result.score <= 6.0, f"Bad code should score <=6, got {result.score}"


def test_bad_code_has_findings():
    parsed = ParsedFile(str(FIXTURES / "bad.py"))
    result = KissSieve().analyze(parsed)
    assert len(result.findings) > 0, "Bad code should have findings"


def test_kiss_name():
    sieve = KissSieve()
    assert sieve.name == "KISS"
    assert sieve.default_weight == 0.20


# --- Documentation must not read as complexity (warden cycle, 2026-07-28) ---

def _kiss(tmp_path, name, source):
    target = tmp_path / name
    target.write_text(source)
    return KissSieve().analyze(ParsedFile(str(target)))


_BODY = "    total = 0\n    for value in values:\n        total += value\n    return total\n"
_LONG_DOC = ('    """Return the sum of values.\n\n'
             + "".join(f"    Line {i} of explanation a reader benefits from.\n" for i in range(12))
             + '    """\n')


def test_docstring_does_not_count_toward_function_length(tmp_path):
    """Documenting a function must not make it score as more complex."""
    bare = _kiss(tmp_path, "bare.py", f"def compute_total(values: list[int]) -> int:\n{_BODY}")
    documented = _kiss(tmp_path, "doc.py", f"def compute_total(values: list[int]) -> int:\n{_LONG_DOC}{_BODY}")
    assert documented.score == bare.score
    # def line + 4 body lines; the 14-line docstring between them is not counted.
    assert "max fn code lines=5" in documented.summary
    assert "max fn code lines=5" in bare.summary


def test_python_and_php_are_charged_the_same_for_being_documented(tmp_path):
    """Same code, same docs, same grade — regardless of where the language puts them.

    Python's docstring sits inside the body and PHP's docblock above the
    declaration, so raw line counting penalised Python alone.
    """
    py = _kiss(tmp_path, "same.py", f"def compute_total(values: list[int]) -> int:\n{_LONG_DOC}{_BODY}")
    php_doc = "<?php\n/**\n" + "".join(f" * Line {i} of explanation.\n" for i in range(12)) + " */\n"
    php_body = ("function compute_total(array $values): int {\n    $total = 0;\n"
                "    foreach ($values as $v) { $total += $v; }\n    return $total;\n}\n")
    php = _kiss(tmp_path, "same.php", php_doc + php_body)
    assert py.score == php.score == 10.0


def test_a_genuinely_long_function_is_still_flagged(tmp_path):
    """The exemption covers documentation only — real length must still bite."""
    body = "".join(f"    step_{i} = {i}\n" for i in range(40))
    result = _kiss(tmp_path, "long.py", f"def sprawling() -> None:\n{_LONG_DOC}{body}")
    assert any("lines long" in f.message for f in result.findings)
    assert result.score < 10.0


def test_only_the_leading_docstring_is_excluded(tmp_path):
    """A string statement mid-body is code, not documentation."""
    body = '    marker = 1\n    """not a docstring"""\n    return marker\n'
    result = _kiss(tmp_path, "mid.py", f"def thing() -> int:\n{body}")
    assert "max fn code lines=4" in result.summary
