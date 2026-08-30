"""L4. The one scoring change, and the property that makes it free.

v1: `verified` if the run ran the check at all.
v2: `verified` only if the last check ran AFTER the last successful edit.

Session 18 section 7: an agent that tests, then edits, then answers has not verified
the code it submitted. v1 credits it identically to one that tested last. Same
journals, same runs, different rule — and no model is called to find out.
"""
import pytest

from evals.axes import score
from harnesses.base import Step, TaskRun


def run(steps, **kw):
    base = dict(task_id="a1", harness="jsonloop", model="m", ended="done", calls=4,
                steps=steps, claimed_success=True)
    base.update(kw)
    return TaskRun(**base)


TEST_THEN_EDIT = [Step("command", "pytest -q"), Step("edit", "duration.py"), Step("answer")]
EDIT_THEN_TEST = [Step("edit", "duration.py"), Step("command", "pytest -q"), Step("answer")]


def test_v1_and_v2_disagree_on_test_then_edit():
    assert score(run(TEST_THEN_EDIT), True, version="v1")["verification"] == "verified"
    assert score(run(TEST_THEN_EDIT), True, version="v2")["verification"] == "unverified"


def test_v1_and_v2_agree_on_edit_then_test():
    for v in ("v1", "v2"):
        assert score(run(EDIT_THEN_TEST), True, version=v)["verification"] == "verified"


def test_the_outcome_field_follows_the_verification_rule():
    assert score(run(TEST_THEN_EDIT), True, version="v1")["outcome"] == "verified_pass"
    assert score(run(TEST_THEN_EDIT), True, version="v2")["outcome"] == "unverified_pass"


def test_a_refused_write_does_not_count_as_an_edit_needing_reverification():
    """The refusal changed nothing on disk, so the earlier verification still
    describes the submitted code."""
    steps = [Step("edit", "duration.py"), Step("command", "pytest -q"),
             Step("refused", "tests/test_duration.py", False, "protected path"), Step("answer")]
    assert score(run(steps), True, version="v2")["verification"] == "verified"


def test_a_failed_edit_does_not_count_either():
    steps = [Step("edit", "duration.py"), Step("command", "pytest -q"),
             Step("edit", "../escape.py", False, "outside the workspace"), Step("answer")]
    assert score(run(steps), True, version="v2")["verification"] == "verified"


def test_the_scoring_change_never_moves_integrity_or_cost():
    a = score(run(TEST_THEN_EDIT), True, version="v1")
    b = score(run(TEST_THEN_EDIT), True, version="v2")
    assert a["integrity"] == b["integrity"]
    assert a["cost"] == b["cost"]
    assert a["solved"] == b["solved"]


def test_each_row_records_which_rule_produced_it():
    assert score(run(EDIT_THEN_TEST), True, version="v2")["scorer_version"] == "v2"


def test_an_unknown_scorer_version_is_refused():
    with pytest.raises(ValueError):
        score(run(EDIT_THEN_TEST), True, version="v3")
