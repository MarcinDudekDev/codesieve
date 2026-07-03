"""Tests for inline per-finding suppression (`# codesieve: ignore`)."""

from pathlib import Path

from codesieve.config import Config
from codesieve.engine import scan_file
from codesieve.models import Finding, SieveResult, SieveType
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


def _sieve(report, name: str) -> SieveResult:
    return next(r for r in report.sieve_results if r.name == name)


# ---- unit: comment parsing --------------------------------------------------------------

def test_parse_bare_ignore_means_all():
    supp = parse_suppressions("x = 1  # codesieve: ignore\n")
    assert supp == {1: None}


def test_parse_named_and_comma_list():
    supp = parse_suppressions(
        "a  # codesieve: ignore[ErrorHandling]\n"
        "b  // codesieve: ignore[ErrorHandling,Naming]\n"
    )
    assert supp[1] == frozenset({"ErrorHandling"})
    assert supp[2] == frozenset({"ErrorHandling", "Naming"})


def test_parse_ignores_slash_prefix_for_js():
    assert parse_suppressions("foo();  // codesieve: ignore\n") == {1: None}


# ---- unit: apply on synthetic results (penalty-additive + proportional paths) -----------

def _result(name, score, findings):
    return SieveResult(name=name, score=score, sieve_type=SieveType.DETERMINISTIC,
                       summary="", findings=findings)


def test_named_ignore_drops_only_that_sieve():
    source = "row  # codesieve: ignore[ErrorHandling]\n"
    eh = _result("ErrorHandling", 8.5, [Finding("broad catch", line=1, penalty=1.5)])
    naming = _result("Naming", 8.5, [Finding("bad name", line=1)])
    out = apply_suppressions([eh, naming], source)
    assert _by(out, "ErrorHandling").findings == []      # suppressed
    assert len(_by(out, "Naming").findings) == 1          # other sieve untouched


def test_additive_score_restored_exactly():
    # Two EH findings (1.5 + 0.5 penalty) => raw 8.0; suppress the 0.5 one on line 1.
    source = "a  # codesieve: ignore[ErrorHandling]\nb\n"
    eh = _result("ErrorHandling", 8.0, [
        Finding("broad", line=1, penalty=0.5),
        Finding("bare except", line=2, penalty=1.5),
    ])
    out = apply_suppressions([eh], source)[0]
    assert [f.line for f in out.findings] == [2]
    assert out.score == 8.5  # 10.0 - 1.5 kept penalty, exact


def test_all_findings_suppressed_restores_perfect():
    source = "a  # codesieve: ignore\n"
    eh = _result("ErrorHandling", 4.0, [Finding("broad", line=1, penalty=1.5)])
    assert apply_suppressions([eh], source)[0].score == 10.0


def test_proportional_path_for_non_additive_sieve():
    # No penalties tagged => proportional: residual 4.0, drop 1 of 2 => residual halved.
    source = "a  # codesieve: ignore[Naming]\nb\n"
    naming = _result("Naming", 6.0, [Finding("x", line=1), Finding("y", line=2)])
    out = apply_suppressions([naming], source)[0]
    assert out.score == 8.0  # 10 - (10-6)*0.5


def _by(results, name):
    return next(r for r in results if r.name == name)


# ---- integration: through scan_file (score + grade must reflect suppression) ------------

def test_ignore_sieve_drops_line_finding(tmp_path):
    report = scan_file(_write(tmp_path, "eh.py", _EH_SOURCE), Config())
    eh = _sieve(report, "ErrorHandling")
    lines = [f.line for f in eh.findings]
    assert 4 not in lines, "line-4 broad catch should be suppressed"
    assert any(l in (8, 9) for l in lines), "line-8 bare/empty except must still fire"


def test_other_sieves_still_fire(tmp_path):
    report = scan_file(_write(tmp_path, "eh.py", _EH_SOURCE), Config())
    # Nothing suppressed KISS/Naming/etc — at least one other sieve keeps working.
    assert not _sieve(report, "ErrorHandling").skipped


def test_bare_ignore_drops_all_on_line(tmp_path):
    source = _EH_SOURCE.replace("ignore[ErrorHandling]", "ignore")
    report = scan_file(_write(tmp_path, "eh.py", source), Config())
    lines = [f.line for f in _sieve(report, "ErrorHandling").findings]
    assert 4 not in lines


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
