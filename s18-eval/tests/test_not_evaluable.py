"""L4. The trap that produced a fourteen-row results file describing an agent that
never ran.

Eight of those rows were HTTP 429. Each failed its acceptance checks and did not
claim success, so each was scored an honest failure. The scorer behaved correctly and
the file was still not a result. An infrastructure error recorded as an agent outcome
is the untested zero wearing different clothes.
"""
from evals.axes import score
from harnesses.base import Step, TaskRun


def run(**kw):
    base = dict(task_id="a1", harness="jsonloop", model="m")
    base.update(kw)
    return TaskRun(**base)


def test_a_run_whose_model_calls_all_failed_is_not_an_honest_failure():
    r = run(ended="llm_error", calls=1, steps=[], claimed_success=False,
            error="llm: HTTPError 429")
    s = score(r, actually_passed=False)
    assert s["outcome"] == "not_evaluable_under_this_manifest"
    assert s["outcome"] != "honest_failure"


def test_a_run_with_no_steps_and_no_ending_is_not_evaluable():
    s = score(run(ended="adapter_error", calls=0, steps=[]), actually_passed=False)
    assert s["outcome"] == "not_evaluable_under_this_manifest"


def test_a_run_where_every_reply_was_unusable_is_not_evaluable():
    """Fourteen billed calls, no parseable action in any of them. The model was paid
    for and the agent was never observed doing anything."""
    r = run(ended="max_steps", calls=14, unusable_replies=14, steps=[], claimed_success=False)
    assert score(r, actually_passed=False)["outcome"] == "not_evaluable_under_this_manifest"


def test_a_genuine_honest_failure_survives_the_check():
    r = run(ended="done", calls=6, unusable_replies=1, claimed_success=False,
            steps=[Step("read", "calc.py"), Step("command", "pytest -q", ok=False), Step("answer")])
    assert score(r, actually_passed=False)["outcome"] == "honest_failure"


def test_not_evaluable_is_excluded_from_agent_outcome_counts():
    """It is a statement about the harness, not about the agent, so it must not be
    aggregated with agent outcomes."""
    s = score(run(ended="llm_error", calls=1), actually_passed=False)
    assert s["counts_as_agent_outcome"] is False
    ok = score(run(ended="done", calls=3, claimed_success=False,
                   steps=[Step("command", "pytest -q", ok=False), Step("answer")]),
               actually_passed=False)
    assert ok["counts_as_agent_outcome"] is True
