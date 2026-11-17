"""Python ErrorHandling across every shape an ``except`` clause can take.

tree-sitter wraps ``X as y`` in an ``as_pattern`` node, so the type expression
sits one level deeper than in a plain ``except X:``. A handler must be judged
on its type expression alone: the ``as`` binding never changes the verdict.
"""

from pathlib import Path

import pytest

from codesieve.config import Config
from codesieve.engine import scan_file
from codesieve.models import Finding
from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.error_handling import (
    BARE_EXCEPT_PENALTY,
    BROAD_CATCH_PENALTY,
    EMPTY_BODY_PENALTY,
    ErrorHandlingSieve,
)

FIXTURES = Path(__file__).parent / "fixtures" / "python"

_TEMPLATE = "def f():\n    try:\n        g()\n    {clause}:\n        {body}\n"


def _analyze(tmp_path: Path, clause: str, body: str = "print(1)"):
    path = tmp_path / "case.py"
    path.write_text(_TEMPLATE.format(clause=clause, body=body))
    return ErrorHandlingSieve().analyze(ParsedFile(str(path)))


def _shape(findings: list[Finding]) -> list[tuple[str, float | None]]:
    return [(f.message, f.penalty) for f in findings]


# --- typed handlers are never bare, with or without a binding ---------------

@pytest.mark.parametrize("clause", [
    "except ValueError as e",
    "except (ValueError, KeyError) as e",
    "except os.error as e",
    "except pkg.errors.Timeout as exc",
    "except* ValueError as e",
    "except* (ValueError, KeyError) as eg",
])
def test_typed_handler_with_binding_has_no_findings(tmp_path, clause):
    result = _analyze(tmp_path, clause)
    assert result.findings == [], f"{clause!r} is a typed handler: {_shape(result.findings)}"
    assert result.score == 10.0


# Outside the identifier/attribute/tuple whitelist: any expression is a type.
@pytest.mark.parametrize("clause", [
    "except get_exc()",
    "except get_exc() as e",
    "except EXCS[0]",
    "except EXCS[0] as e",
    "except (A or B) as e",
])
def test_any_type_expression_is_not_bare(tmp_path, clause):
    result = _analyze(tmp_path, clause)
    assert not any("bare" in f.message for f in result.findings), \
        f"{clause!r} names a type: {_shape(result.findings)}"
    assert result.score == 10.0


# --- bare stays bare --------------------------------------------------------

def test_bare_except_is_still_bare(tmp_path):
    result = _analyze(tmp_path, "except")
    assert len(result.findings) == 1
    assert "bare except" in result.findings[0].message
    assert result.findings[0].penalty == BARE_EXCEPT_PENALTY
    assert result.score == 10.0 - BARE_EXCEPT_PENALTY


def test_bare_except_with_comment_between_is_still_bare(tmp_path):
    path = tmp_path / "case.py"
    path.write_text("def f():\n    try:\n        g()\n    except:  # catch all\n        # note\n        print(1)\n")
    result = ErrorHandlingSieve().analyze(ParsedFile(str(path)))
    assert [f.penalty for f in result.findings] == [BARE_EXCEPT_PENALTY]
    assert "bare except" in result.findings[0].message


# --- broad catch is reported as broad, not as bare --------------------------

@pytest.mark.parametrize("clause", [
    "except Exception",
    "except Exception as e",
    "except* Exception",
    "except* Exception as eg",
])
def test_broad_catch_is_broad_with_or_without_binding(tmp_path, clause):
    result = _analyze(tmp_path, clause)
    assert len(result.findings) == 1, f"{clause!r}: {_shape(result.findings)}"
    finding = result.findings[0]
    assert "broad" in finding.message and "bare" not in finding.message
    assert finding.penalty == BROAD_CATCH_PENALTY
    assert finding.line == 4
    assert result.score == 10.0 - BROAD_CATCH_PENALTY


@pytest.mark.parametrize("clause", ["except Exception", "except Exception as e"])
def test_broad_catch_that_reraises_is_clean(tmp_path, clause):
    result = _analyze(tmp_path, clause, body="raise")
    assert result.findings == [], f"{clause!r} re-raises: {_shape(result.findings)}"


# --- the binding never changes the verdict ----------------------------------

@pytest.mark.parametrize("type_expr", [
    "ValueError",
    "Exception",
    "BaseException",
    "(ValueError, KeyError)",
    "(ValueError, Exception)",
    "os.error",
    "builtins.Exception",
    "get_exc()",
])
@pytest.mark.parametrize("body", ["print(1)", "pass", "raise"])
def test_binding_does_not_change_findings(tmp_path, type_expr, body):
    without = _analyze(tmp_path, f"except {type_expr}", body)
    with_binding = _analyze(tmp_path, f"except {type_expr} as e", body)
    assert _shape(with_binding.findings) == _shape(without.findings)
    assert with_binding.score == without.score


# --- empty body is independent of the type ----------------------------------

def test_typed_handler_with_empty_body_reports_only_empty(tmp_path):
    result = _analyze(tmp_path, "except ValueError as e", body="pass")
    assert [f.penalty for f in result.findings] == [EMPTY_BODY_PENALTY]
    assert "empty" in result.findings[0].message


def test_summary_counts_broad_not_bare_for_bound_exception(tmp_path):
    result = _analyze(tmp_path, "except Exception as e")
    assert "broad" in result.summary and "bare" not in result.summary


# --- several handlers on one try -------------------------------------------

def test_mixed_handlers_are_judged_individually(tmp_path):
    path = tmp_path / "mixed.py"
    path.write_text(
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except ValueError as e:\n"
        "        print(e)\n"
        "    except (KeyError, IndexError) as e:\n"
        "        print(e)\n"
        "    except Exception as e:\n"
        "        print(e)\n"
        "    except:\n"
        "        print(1)\n"
    )
    result = ErrorHandlingSieve().analyze(ParsedFile(str(path)))
    assert sorted((f.line, f.penalty) for f in result.findings) == [
        (8, BROAD_CATCH_PENALTY),
        (10, BARE_EXCEPT_PENALTY),
    ]


# --- fixtures and the engine path ------------------------------------------

def test_good_fixture_has_no_bare_except_finding():
    # good.py has `except ValueError as exc:`; it must not be called bare.
    result = ErrorHandlingSieve().analyze(ParsedFile(str(FIXTURES / "good.py")))
    assert not any("bare" in f.message for f in result.findings), _shape(result.findings)


def test_bad_fixture_still_reports_two_bare_and_one_broad():
    result = ErrorHandlingSieve().analyze(ParsedFile(str(FIXTURES / "bad.py")))
    messages = [f.message for f in result.findings]
    assert sum("bare" in m for m in messages) == 2
    assert sum("broad" in m for m in messages) == 1


def test_suppressing_bound_broad_catch_lifts_score_by_broad_penalty(tmp_path):
    source = "def f():\n    try:\n        g()\n    except Exception as e:{marker}\n        print(e)\n"
    plain_path = tmp_path / "plain.py"
    plain_path.write_text(source.format(marker=""))
    ignored_path = tmp_path / "ignored.py"
    ignored_path.write_text(source.format(marker="  # codesieve: ignore[ErrorHandling]"))

    def eh_score(path: Path) -> float:
        report = scan_file(path, Config())
        return next(r for r in report.sieve_results if r.name == "ErrorHandling").score

    assert eh_score(plain_path) == 10.0 - BROAD_CATCH_PENALTY
    assert eh_score(ignored_path) == 10.0


# --- layout must not hide the type: continuations and parentheses ----------
# Found in verification round 1: a `line_continuation` node or a wrapping
# parenthesis was taken for the type expression itself.

_CONT = "\\\n        "


def test_line_continued_bare_except_is_still_bare(tmp_path):
    result = _analyze(tmp_path, f"except {_CONT}")
    assert [f.penalty for f in result.findings] == [BARE_EXCEPT_PENALTY]
    assert "bare except" in result.findings[0].message


@pytest.mark.parametrize("clause", [
    f"except {_CONT}Exception",
    f"except {_CONT}Exception as e",
    f"except Exception {_CONT}as e",
    f"except* {_CONT}Exception as eg",
    "except (Exception)",
    "except (Exception) as e",
    "except ((Exception)) as e",
    f"except {_CONT}(Exception) as e",
])
def test_broad_catch_survives_continuations_and_parentheses(tmp_path, clause):
    result = _analyze(tmp_path, clause)
    assert [f.penalty for f in result.findings] == [BROAD_CATCH_PENALTY], \
        f"{clause!r}: {_shape(result.findings)}"
    assert "broad" in result.findings[0].message


@pytest.mark.parametrize("clause", [
    f"except {_CONT}ValueError",
    f"except {_CONT}ValueError as e",
    f"except {_CONT}(ValueError, KeyError) as e",
    "except (ValueError)",
    "except (ValueError) as e",
    "except ((os.error)) as e",
])
def test_typed_handler_survives_continuations_and_parentheses(tmp_path, clause):
    result = _analyze(tmp_path, clause)
    assert result.findings == [], f"{clause!r}: {_shape(result.findings)}"


# --- broad types: BaseException, and tuples that contain a broad type -------
# A tuple catches everything its broadest member catches.

@pytest.mark.parametrize("type_expr, caught", [
    ("BaseException", "BaseException"),
    ("(BaseException)", "BaseException"),
    ("(Exception,)", "Exception"),
    ("(ValueError, Exception)", "Exception"),
    ("(Exception, ValueError)", "Exception"),
    ("(ValueError, KeyError, Exception)", "Exception"),
    ("(ValueError, BaseException)", "BaseException"),
    ("(ValueError, (Exception))", "Exception"),
    ("(ValueError, (KeyError, Exception))", "Exception"),
    ("((ValueError, Exception))", "Exception"),
    ("(ValueError,  # specific\n            Exception)", "Exception"),
    ("(os.error, Exception)", "Exception"),
])
@pytest.mark.parametrize("binding", ["", " as e"])
@pytest.mark.parametrize("star", ["", "*"])
def test_broad_member_makes_the_handler_broad(tmp_path, type_expr, caught, binding, star):
    clause = f"except{star} {type_expr}{binding}"
    result = _analyze(tmp_path, clause)
    assert [f.penalty for f in result.findings] == [BROAD_CATCH_PENALTY], \
        f"{clause!r}: {_shape(result.findings)}"
    finding = result.findings[0]
    assert finding.message == f"broad 'catch {caught}' without re-throw"
    assert finding.severity == "warning"
    assert finding.line == 4
    assert result.score == 10.0 - BROAD_CATCH_PENALTY


def test_plain_exception_message_is_unchanged(tmp_path):
    result = _analyze(tmp_path, "except Exception as e")
    assert [f.message for f in result.findings] == ["broad 'catch Exception' without re-throw"]


def test_two_broad_members_are_one_finding(tmp_path):
    result = _analyze(tmp_path, "except (Exception, BaseException) as e")
    assert [f.penalty for f in result.findings] == [BROAD_CATCH_PENALTY]


@pytest.mark.parametrize("clause", [
    "except BaseException",
    "except BaseException as e",
    "except (ValueError, Exception)",
    "except (ValueError, Exception) as e",
    "except* (ValueError, BaseException) as eg",
])
def test_broad_member_with_reraise_is_clean(tmp_path, clause):
    assert _analyze(tmp_path, clause, body="raise").findings == []


def test_raise_inside_nested_function_is_not_a_reraise(tmp_path):
    path = tmp_path / "nested.py"
    path.write_text(
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except (ValueError, Exception) as e:\n"
        "        def later():\n"
        "            raise e\n"
        "        print(later)\n"
    )
    result = ErrorHandlingSieve().analyze(ParsedFile(str(path)))
    assert [f.penalty for f in result.findings] == [BROAD_CATCH_PENALTY]


# Not broad: specific types, look-alike names, and anything that is not a bare name.
@pytest.mark.parametrize("type_expr", [
    "(ValueError, KeyError)",
    "(ValueError,)",
    "()",
    "(MyException, ExceptionGroup)",
    "(BaseExceptionGroup, exception)",
    "builtins.Exception",
    "(ValueError, builtins.Exception)",
    "(ValueError, errors.BaseException)",
    "(ValueError, Exception())",
    "(ValueError, EXCS[Exception])",
    "[ValueError, Exception]",
    "(x := Exception)",
])
@pytest.mark.parametrize("binding", ["", " as e"])
def test_only_a_bare_broad_name_in_a_tuple_is_broad(tmp_path, type_expr, binding):
    clause = f"except {type_expr}{binding}"
    result = _analyze(tmp_path, clause)
    assert result.findings == [], f"{clause!r}: {_shape(result.findings)}"


def test_broad_tuple_with_empty_body_reports_both(tmp_path):
    result = _analyze(tmp_path, "except (ValueError, Exception)", body="pass")
    assert sorted(f.penalty for f in result.findings) == [BROAD_CATCH_PENALTY, EMPTY_BODY_PENALTY]


def test_suppressing_broad_tuple_lifts_score_by_broad_penalty(tmp_path):
    source = "def f():\n    try:\n        g()\n    except (ValueError, Exception) as e:{marker}\n        print(e)\n"
    plain_path = tmp_path / "plain.py"
    plain_path.write_text(source.format(marker=""))
    ignored_path = tmp_path / "ignored.py"
    ignored_path.write_text(source.format(marker="  # codesieve: ignore[ErrorHandling]"))

    def eh_score(path: Path) -> float:
        report = scan_file(path, Config())
        return next(r for r in report.sieve_results if r.name == "ErrorHandling").score

    assert eh_score(plain_path) == 10.0 - BROAD_CATCH_PENALTY
    assert eh_score(ignored_path) == 10.0


def test_php_broad_message_is_unchanged(tmp_path):
    path = tmp_path / "case.php"
    path.write_text("<?php\nfunction f() {\n    try {\n        g();\n    } catch (\\Exception $e) {\n        log_it($e);\n    }\n}\n")
    result = ErrorHandlingSieve().analyze(ParsedFile(str(path)))
    assert [f.message for f in result.findings] == ["broad 'catch \\Exception' without re-throw"]
