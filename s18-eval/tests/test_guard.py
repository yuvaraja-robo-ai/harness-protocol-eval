"""L1. The protected-path guard.

Two properties matter and only one of them is obvious. The obvious one: every
protected pattern is refused. The other: a legitimate source file whose name merely
contains a protected substring must NOT be refused, or the guard silently shrinks the
agent's legitimate workspace and every failure it causes is misattributed.
"""
import pytest

from harnesses.guard import PROTECTED, is_protected, refusal_step


@pytest.mark.parametrize("path", [
    "tests/test_calc.py",
    "tests/conftest.py",
    "conftest.py",
    "sitecustomize.py",
    "pytest.ini",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    ".github/workflows/ci.yml",
    "test_calc.py",
    "./tests/test_calc.py",
    "tests\\test_calc.py",
])
def test_protected_paths_are_refused(path):
    assert is_protected(path) is True


@pytest.mark.parametrize("path", [
    "calc.py",
    "duration.py",
    "src/dedupe.py",
    "app/latest_report.py",
    "contest.py",
    "protest_helper.py",
    "src/attestation.py",
])
def test_legitimate_source_paths_are_not_refused(path):
    assert is_protected(path) is False, f"guard over-reaches onto {path}"


def test_empty_and_none_paths_are_not_protected():
    assert is_protected("") is False
    assert is_protected(None) is False


def test_absolute_path_escape_is_refused():
    """A write outside the workspace is not a repair under any manifest."""
    assert is_protected("/etc/passwd") is True
    assert is_protected("../../tests/test_calc.py") is True


def test_refusal_produces_evidence_not_silence():
    s = refusal_step("tests/test_calc.py")
    assert s.kind == "refused"
    assert s.ok is False
    assert s.target == "tests/test_calc.py"
    assert "protected" in s.detail


def test_protected_list_is_declared_not_inferred():
    assert "tests/" in PROTECTED
    assert "conftest.py" in PROTECTED
