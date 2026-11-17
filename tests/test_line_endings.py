"""A file's line-ending style must not change what codesieve reports.

tree-sitter only counts ``\\n`` as a line break. A file saved with CR-only
(classic Mac) endings therefore parsed as one long line: handlers, functions
and whole sieves went missing and a failing file graded A. The LF twin of a
file is the reference; CRLF, CR-only and mixed endings must match it.
"""

from pathlib import Path

import pytest

from codesieve.config import Config
from codesieve.engine import scan_file
from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.error_handling import BARE_EXCEPT_PENALTY, ErrorHandlingSieve

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(
    str(p.relative_to(FIXTURES))
    for p in FIXTURES.glob("*/*")
    if p.stem in ("good", "bad") and p.is_file()
)

_BARE = "def f():\n    try:\n        g()\n    except:\n        print(1)\n\n\ndef h(a, b):\n    return a + b\n"


def _alternate(data: bytes) -> bytes:
    """Mixed endings: LF, CR and CRLF in rotation."""
    endings = (b"\n", b"\r", b"\r\n")
    parts = data.split(b"\n")
    out = bytearray()
    for i, part in enumerate(parts[:-1]):
        out += part + endings[i % 3]
    return bytes(out + parts[-1])


_STYLES = {
    "crlf": lambda data: data.replace(b"\n", b"\r\n"),
    "cr": lambda data: data.replace(b"\n", b"\r"),
    "mixed": _alternate,
}


def _write(tmp_path: Path, style: str, name: str, data: bytes) -> Path:
    target = tmp_path / style / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _signature(path: Path):
    report = scan_file(path, Config())
    per_sieve = {
        r.name: (r.skipped, r.score, sorted((f.line, f.message, f.severity) for f in r.findings))
        for r in report.sieve_results
    }
    return report.aggregate_score, report.grade, per_sieve


def test_fixture_list_is_not_empty():
    assert len(FIXTURE_FILES) >= 10, FIXTURE_FILES


@pytest.mark.parametrize("style", sorted(_STYLES))
@pytest.mark.parametrize("fixture", FIXTURE_FILES)
def test_scan_is_identical_to_the_lf_twin(tmp_path, fixture, style):
    data = (FIXTURES / fixture).read_bytes()
    assert b"\r" not in data, "fixtures are expected to be LF"
    reference = _signature(_write(tmp_path, "lf", fixture, data))
    actual = _signature(_write(tmp_path, style, fixture, _STYLES[style](data)))
    assert actual == reference


# --- the reported case ------------------------------------------------------

@pytest.mark.parametrize("style", ["cr", "crlf", "mixed"])
def test_bare_except_is_found_on_its_line(tmp_path, style):
    path = _write(tmp_path, style, "case.py", _STYLES[style](_BARE.encode()))
    result = ErrorHandlingSieve().analyze(ParsedFile(str(path)))
    assert [(f.line, f.penalty) for f in result.findings] == [(4, BARE_EXCEPT_PENALTY)]
    assert result.score == 10.0 - BARE_EXCEPT_PENALTY


def test_cr_only_file_parses_without_errors(tmp_path):
    cr = ParsedFile(str(_write(tmp_path, "cr", "case.py", _BARE.replace("\n", "\r").encode())))
    lf = ParsedFile(str(_write(tmp_path, "lf", "case.py", _BARE.encode())))
    assert not cr.root.has_error
    assert cr.line_count == lf.line_count
    assert [(f.name, f.start_line, f.code_line_count) for f in cr.get_functions()] == \
        [(f.name, f.start_line, f.code_line_count) for f in lf.get_functions()]


def test_suppression_marker_is_honoured_on_a_cr_only_file(tmp_path):
    source = _BARE.replace("    except:\n", "    except:  # codesieve: ignore[ErrorHandling]\n")
    path = _write(tmp_path, "cr", "case.py", source.replace("\n", "\r").encode())
    plain = _write(tmp_path, "cr-plain", "case.py", _BARE.replace("\n", "\r").encode())

    def eh_score(target: Path) -> float:
        report = scan_file(target, Config())
        return next(r for r in report.sieve_results if r.name == "ErrorHandling").score

    assert eh_score(plain) == 10.0 - BARE_EXCEPT_PENALTY, "the unsuppressed twin must be penalised"
    assert eh_score(path) == 10.0


# --- byte offsets and untouched files ---------------------------------------

def test_lf_and_crlf_bytes_are_left_alone(tmp_path):
    for style, data in (("lf", _BARE.encode()), ("crlf", _BARE.replace("\n", "\r\n").encode())):
        parsed = ParsedFile(str(_write(tmp_path, style, "case.py", data)))
        assert parsed.source == data


def test_cr_only_source_keeps_its_byte_length(tmp_path):
    data = _BARE.replace("\n", "\r").encode()
    parsed = ParsedFile(str(_write(tmp_path, "cr", "case.py", data)))
    assert len(parsed.source) == len(data), "byte offsets must stay valid"
    assert parsed.source.replace(b"\r", b"\n") == data.replace(b"\r", b"\n")


def test_non_ascii_text_survives(tmp_path):
    source = 'def f():\r    return "zażółć ☃"\r'
    parsed = ParsedFile(str(_write(tmp_path, "cr", "case.py", source.encode("utf-8"))))
    assert "zażółć ☃" in parsed.source_text
    assert not parsed.root.has_error


# --- edges ------------------------------------------------------------------

@pytest.mark.parametrize("data", [
    b"",
    b"\r",
    b"\r\r\r",
    b"\r\n\r",
    b"x = 1\r",
    b"x = 1\r\r\ny = 2\r",
    b"x = 1",
    b"\xff\xfe\r\rx = 1\r",
])
def test_edge_files_scan_without_crashing(tmp_path, data):
    path = _write(tmp_path, "edge", "case.py", data)
    report = scan_file(path, Config())
    assert report.sieve_results
    assert ParsedFile(str(path)).line_count == len(data.decode("utf-8", errors="replace").splitlines())


def test_blank_lines_keep_later_findings_on_their_line(tmp_path):
    source = "\r\r\r" + _BARE.replace("\n", "\r")
    path = _write(tmp_path, "cr", "case.py", source.encode())
    result = ErrorHandlingSieve().analyze(ParsedFile(str(path)))
    assert [f.line for f in result.findings] == [7]


# --- CRLF inside compared and printed text ----------------------------------
# ParsedFile keeps CRLF bytes as they are, so any text cut out of the source
# still carries "\r\n". Where that text is compared (DRY) or printed (finding
# messages) it must read the same as in the LF twin.

_REPEATED = "repeated 3×"
_NEWLINE = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}


def _repeat_source(spellings: tuple[str, ...], template: str = "'''x{nl}y'''") -> bytes:
    """Three functions returning the same call; only the newline inside the literal varies."""
    literals = [template.format(nl=_NEWLINE[s]) for s in spellings]
    return "".join(
        f"def {name}():\n    return g({literal}, 1, 2)\n\n\n" for name, literal in zip("abc", literals)
    ).encode()


def _dry_messages(path: Path) -> list[str]:
    report = scan_file(path, Config())
    return [f.message for r in report.sieve_results if r.name == "DRY" for f in r.findings]


def test_lf_reference_reports_the_repeated_expression(tmp_path):
    messages = _dry_messages(_write(tmp_path, "lf", "rep.py", _repeat_source(("lf", "lf", "lf"))))
    assert any(_REPEATED in m for m in messages), messages


@pytest.mark.parametrize("spellings", [
    ("cr", "lf", "crlf"),
    ("lf", "lf", "crlf"),
    ("crlf", "crlf", "crlf"),
    ("crlf", "lf", "cr"),
    ("lf", "crlf", "lf"),
])
def test_repeated_expression_survives_newline_spelling_in_a_literal(tmp_path, spellings):
    reference = _signature(_write(tmp_path, "lf", "rep.py", _repeat_source(("lf", "lf", "lf"))))
    actual = _signature(_write(tmp_path, "-".join(spellings), "rep.py", _repeat_source(spellings)))
    assert actual == reference


@pytest.mark.parametrize("style", sorted(_STYLES))
def test_repeated_multiline_literal_file_matches_its_lf_twin(tmp_path, style):
    data = _repeat_source(("lf", "lf", "lf"))
    reference = _signature(_write(tmp_path, "lf", "rep.py", data))
    actual = _signature(_write(tmp_path, style, "rep.py", _STYLES[style](data)))
    assert actual == reference


def test_escaped_newline_spellings_stay_distinct(tmp_path):
    # Backslash-r backslash-n typed as four characters is a different literal
    # from backslash-n: only real line-ending bytes may be folded together.
    same = _repeat_source(("lf", "lf", "lf"), template="'x\\n{nl}y'".replace("{nl}", ""))
    differs = same.replace(b"'x\\ny'", b"'x\\r\\ny'", 1)
    assert differs != same
    assert any(_REPEATED in m for m in _dry_messages(_write(tmp_path, "same", "rep.py", same)))
    assert not any(_REPEATED in m for m in _dry_messages(_write(tmp_path, "differs", "rep.py", differs)))


def test_literal_with_crlf_keeps_its_bytes(tmp_path):
    data = _repeat_source(("crlf", "lf", "crlf"))
    assert b"\r\n" in data
    assert ParsedFile(str(_write(tmp_path, "crlf", "rep.py", data))).source == data


_COMPUTED_NAME = b"class A {\n  [[ 'a',\n 'b' ].join(',')]() { return 1; }\n}\n"


def _all_findings(path: Path):
    report = scan_file(path, Config())
    return [f for r in report.sieve_results for f in r.findings]


def test_lf_reference_prints_the_multiline_method_name(tmp_path):
    findings = _all_findings(_write(tmp_path, "lf", "computed.js", _COMPUTED_NAME))
    assert any("'a',\n 'b'" in f.message for f in findings), [f.message for f in findings]


@pytest.mark.parametrize("style", sorted(_STYLES))
def test_multiline_name_in_a_message_matches_the_lf_twin(tmp_path, style):
    reference = _signature(_write(tmp_path, "lf", "computed.js", _COMPUTED_NAME))
    path = _write(tmp_path, style, "computed.js", _STYLES[style](_COMPUTED_NAME))
    assert _signature(path) == reference
    for finding in _all_findings(path):
        assert "\r" not in finding.message, finding.message
        assert "\r" not in (finding.function or ""), finding.function
    assert all("\r" not in f.name for f in ParsedFile(str(path)).get_functions())
