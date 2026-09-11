"""Tests for inline per-finding suppression (`# codesieve: ignore`)."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file
from codesieve.models import Finding, SieveResult, SieveType
from codesieve.parser.treesitter import ParsedFile
from codesieve.suppression import apply_suppressions, parse_suppressions


# ---- source fixtures (written to tmp_path so they escape the recursive scan) -------------

# Line 4 broad catch is suppressed; line 8 bare-except+empty stays flagged.
_EH_SOURCE = """\
def process(x):
    try:
        risky()
    except Exception as e:  # codesieve: ignore[ErrorHandling]
        print(e)
    try:
        other()
    except:
        pass
"""

# Same file, but the ignore comment removed — used to prove the score/grade moved.
_EH_SOURCE_NO_IGNORE = _EH_SOURCE.replace("  # codesieve: ignore[ErrorHandling]", "")


def _write(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.write_text(source)
    return p


def _parsed(tmp_path: Path, source: str, name: str = "s.py") -> ParsedFile:
    return ParsedFile(str(_write(tmp_path, name, source)))


def _sieve(report, name: str) -> SieveResult:
    return next(r for r in report.sieve_results if r.name == name)


def _by(results, name):
    return next(r for r in results if r.name == name)


def _result(name, score, findings):
    return SieveResult(name=name, score=score, sieve_type=SieveType.DETERMINISTIC,
                       summary="", findings=findings)


# ---- unit: comment parsing (real comment nodes only, names lowercased) -------------------

def test_parse_bare_ignore_means_all(tmp_path):
    supp = parse_suppressions(_parsed(tmp_path, "x = 1  # codesieve: ignore\n"))
    assert supp == {1: None}


def test_parse_named_and_comma_list(tmp_path):
    supp = parse_suppressions(_parsed(
        tmp_path,
        "a = 1  # codesieve: ignore[ErrorHandling]\n"
        "b = 2  # codesieve: ignore[ErrorHandling,Naming]\n",
    ))
    assert supp[1] == frozenset({"errorhandling"})            # lowercased
    assert supp[2] == frozenset({"errorhandling", "naming"})


def test_parse_slash_prefix_for_js(tmp_path):
    supp = parse_suppressions(_parsed(tmp_path, "foo();  // codesieve: ignore\n", "s.js"))
    assert supp == {1: None}


def test_marker_inside_string_literal_is_not_a_comment(tmp_path):
    # BUG 1 regression: the marker text sits in a STRING, not a comment -> no suppression.
    parsed = _parsed(tmp_path, 'x = "codesieve: ignore[MagicNumbers]"\n')
    assert parse_suppressions(parsed) == {}


# ---- unit: apply on synthetic results (penalty-additive + proportional paths) -----------

def test_named_ignore_drops_only_that_sieve(tmp_path):
    parsed = _parsed(tmp_path, "row = 1  # codesieve: ignore[ErrorHandling]\n")
    eh = _result("ErrorHandling", 8.5, [Finding("broad catch", line=1, penalty=1.5)])
    naming = _result("Naming", 8.5, [Finding("bad name", line=1)])
    out = apply_suppressions([eh, naming], parsed)
    assert _by(out, "ErrorHandling").findings == []      # suppressed
    assert len(_by(out, "Naming").findings) == 1          # other sieve untouched


def test_case_insensitive_sieve_name(tmp_path):
    # BUG 2 regression: lowercase name in ignore[...] must still match the sieve.
    parsed = _parsed(tmp_path, "row = 1  # codesieve: ignore[magicnumbers]\n")
    mn = _result("MagicNumbers", 9.5, [Finding("magic", line=1, penalty=0.5)])
    out = apply_suppressions([mn], parsed)
    assert _by(out, "MagicNumbers").findings == []


def test_unknown_sieve_name_warns(tmp_path, capsys):
    parsed = _parsed(tmp_path, "row = 1  # codesieve: ignore[NoSuchSieve]\n")
    mn = _result("MagicNumbers", 9.5, [Finding("magic", line=1, penalty=0.5)])
    apply_suppressions([mn], parsed)
    err = capsys.readouterr().err
    assert "unknown sieve" in err.lower() and "nosuchsieve" in err.lower()


def test_additive_score_restored_exactly(tmp_path):
    # Two EH findings (1.5 + 0.5 penalty) => raw 8.0; suppress the 0.5 one on line 1.
    parsed = _parsed(tmp_path, "a = 1  # codesieve: ignore[ErrorHandling]\nb = 2\n")
    eh = _result("ErrorHandling", 8.0, [
        Finding("broad", line=1, penalty=0.5),
        Finding("bare except", line=2, penalty=1.5),
    ])
    out = apply_suppressions([eh], parsed)[0]
    assert [f.line for f in out.findings] == [2]
    assert out.score == 8.5  # 10.0 - 1.5 kept penalty, exact


def test_all_findings_suppressed_restores_perfect(tmp_path):
    parsed = _parsed(tmp_path, "a = 1  # codesieve: ignore\n")
    eh = _result("ErrorHandling", 4.0, [Finding("broad", line=1, penalty=1.5)])
    out = apply_suppressions([eh], parsed)[0]
    assert out.score == 10.0
    # Summary must not keep describing findings that are gone.
    assert out.summary == "1 finding(s) suppressed inline"


def test_partial_suppression_never_inflates_non_additive_sieve(tmp_path):
    # No per-finding penalty (ratio/severity sieve) + only one of two dropped =>
    # score must stay put. Inflating here would let a minor finding launder a grade.
    parsed = _parsed(tmp_path, "a = 1  # codesieve: ignore[Naming]\nb = 2\n")
    naming = _result("Naming", 6.0, [Finding("x", line=1), Finding("y", line=2)])
    out = apply_suppressions([naming], parsed)[0]
    assert out.score == 6.0                       # unchanged — no inflation
    assert [f.line for f in out.findings] == [2]  # minor finding hidden from report


def test_full_suppression_of_non_additive_sieve_leaves_score_untouched(tmp_path):
    # Categorical rule: a ratio sieve's score is NOT a pure function of its
    # findings (unflagged code still bounds it), so even suppressing *all* its
    # findings must not hand out a 10.
    parsed = _parsed(tmp_path, "a = 1  # codesieve: ignore[Naming]\nb = 2  # codesieve: ignore[Naming]\n")
    naming = _result("Naming", 6.0, [Finding("x", line=1), Finding("y", line=2)])
    out = apply_suppressions([naming], parsed)[0]
    assert out.score == 6.0        # unchanged — suppression never moves a ratio score
    assert out.findings == []      # findings still hidden from the report


def test_full_suppression_of_additive_sieve_restores_perfect(tmp_path):
    # Additive sieves ARE a pure function of findings, so all-suppressed => 10.0.
    parsed = _parsed(tmp_path, "a = 1  # codesieve: ignore[ErrorHandling]\n")
    eh = _result("ErrorHandling", 4.0, [Finding("broad", line=1, penalty=1.5)])
    assert apply_suppressions([eh], parsed)[0].score == 10.0


# ---- integration: through scan_file (score + grade must reflect suppression) ------------

def test_ignore_sieve_drops_line_finding(tmp_path):
    report = scan_file(_write(tmp_path, "eh.py", _EH_SOURCE), Config())
    eh = _sieve(report, "ErrorHandling")
    lines = [f.line for f in eh.findings]
    assert 4 not in lines, "line-4 broad catch should be suppressed"
    assert any(line in (8, 9) for line in lines), "line-8 bare/empty except must still fire"


def test_other_sieves_still_fire(tmp_path):
    report = scan_file(_write(tmp_path, "eh.py", _EH_SOURCE), Config())
    assert not _sieve(report, "ErrorHandling").skipped


def test_bare_ignore_drops_all_on_line(tmp_path):
    source = _EH_SOURCE.replace("ignore[ErrorHandling]", "ignore")
    report = scan_file(_write(tmp_path, "eh.py", source), Config())
    lines = [f.line for f in _sieve(report, "ErrorHandling").findings]
    assert 4 not in lines


def test_string_literal_marker_does_not_game_magicnumbers(tmp_path):
    # BUG 1 end-to-end: 9999 shares a line with a string that contains the marker.
    source = 'def f():\n    return 9999 + len("codesieve: ignore[MagicNumbers]")\n'
    report = scan_file(_write(tmp_path, "g.py", source), Config())
    mn = _sieve(report, "MagicNumbers")
    assert any(f.line == 2 for f in mn.findings), "9999 must still be flagged"
    assert mn.score < 10.0, "string-embedded marker must not inflate the score"


def test_suppressing_minor_finding_does_not_launder_ratio_grade(tmp_path):
    # Auditor repro (TypeHints): two untyped functions; ignore one. The other is
    # still untyped, so the ratio score must NOT rise vs. no suppression at all.
    src = (
        "def a(x, y):\n"
        "    return x + y\n"
        "def b(x, y):  # codesieve: ignore[TypeHints]\n"
        "    return x - y\n"
    )
    plain_src = src.replace("  # codesieve: ignore[TypeHints]", "")
    ignored = scan_file(_write(tmp_path, "ti.py", src), Config())
    plain = scan_file(_write(tmp_path, "ti_plain.py", plain_src), Config())
    th_ignored = _sieve(ignored, "TypeHints").score
    th_plain = _sieve(plain, "TypeHints").score
    assert th_ignored == th_plain, "partial suppression must not inflate TypeHints"


def test_suppressing_shallow_nesting_keeps_deep_violation_score(tmp_path):
    # Auditor repro (Nesting): a deep function and a shallow one; ignore only the
    # shallow one. The deep violation dominates the score, which must not move.
    deep = (
        "def deep():\n"
        + "".join("    " * i + f"if x{i}:\n" for i in range(1, 8))
        + "    " * 8 + "pass\n"
    )
    shallow = (
        "def shallow():  # codesieve: ignore[Nesting]\n"
        "    if a:\n"
        "        if b:\n"
        "            pass\n"
    )
    src = deep + shallow
    plain_src = src.replace("  # codesieve: ignore[Nesting]", "")
    ignored = scan_file(_write(tmp_path, "ns.py", src), Config())
    plain = scan_file(_write(tmp_path, "ns_plain.py", plain_src), Config())
    assert _sieve(ignored, "Nesting").score == _sieve(plain, "Nesting").score


def test_full_suppression_of_ratio_sieve_findings_never_reaches_ten(tmp_path):
    # Auditor repro (KISS): a flagged complex function carries the ONLY KISS
    # finding; an unflagged-but-moderate function still caps KISS below 10.
    # Suppressing every KISS finding must NOT hand out a perfect score.
    moderate = (
        "def moderate(x):\n"
        + "".join(f"    if x == {i}:\n        pass\n" for i in range(1, 5))  # CC 5, unflagged
    )
    complex_fn = (
        "def complex_fn(x):  # codesieve: ignore[KISS]\n"
        + "".join(f"    if x == {i}:\n        pass\n" for i in range(1, 12))  # CC 12, flagged
    )
    src = moderate + complex_fn
    plain_src = src.replace("  # codesieve: ignore[KISS]", "")
    ignored = scan_file(_write(tmp_path, "kiss.py", src), Config())
    plain = scan_file(_write(tmp_path, "kiss_plain.py", plain_src), Config())

    kiss_ignored = _sieve(ignored, "KISS")
    assert kiss_ignored.findings == [], "the complex fn's KISS finding is suppressed"
    assert kiss_ignored.score < 10.0, "unflagged moderate code must still bound KISS"
    assert kiss_ignored.score == _sieve(plain, "KISS").score, "score must not move at all"


def test_aggregate_score_and_grade_reflect_suppression(tmp_path):
    ignored = scan_file(_write(tmp_path, "on.py", _EH_SOURCE), Config())
    plain = scan_file(_write(tmp_path, "off.py", _EH_SOURCE_NO_IGNORE), Config())

    eh_ignored = _sieve(ignored, "ErrorHandling").score
    eh_plain = _sieve(plain, "ErrorHandling").score
    assert eh_ignored > eh_plain, "suppressing the broad catch must lift the EH score"
    assert ignored.aggregate_score >= plain.aggregate_score, "aggregate must not regress"


def test_engine_self_annotation_suppresses_its_own_broad_catch():
    # engine.py annotates its scan-loop catch-all with `# codesieve: ignore[ErrorHandling]`.
    engine_path = Path(__file__).parent.parent / "src" / "codesieve" / "engine.py"
    report = scan_file(engine_path, Config())
    eh = _sieve(report, "ErrorHandling")
    assert all("broad" not in f.message.lower() for f in eh.findings), \
        "engine.py's intentional broad catch should be suppressed"
