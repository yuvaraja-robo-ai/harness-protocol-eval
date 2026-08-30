"""L0. The shapes, and the one field that must not exist.

`actually_passed` lives on the journal, not on TaskRun. The agent's claim and the
grader's verdict are two observations, and their disagreement is the false_success
axis. A single object holding both invites code that conflates them.
"""
import dataclasses
import json

import pytest

from harnesses.base import Step, TaskRun


def test_taskrun_has_no_verdict_field():
    names = {f.name for f in dataclasses.fields(TaskRun)}
    assert "actually_passed" not in names
    assert "solved" not in names
    assert "passed" not in names


def test_taskrun_separates_claim_from_everything_else():
    run = TaskRun(task_id="t", harness="h", model="m", claimed_success=True, ended="done")
    assert run.claimed_success is True


def test_step_defaults_are_a_successful_action():
    s = Step(kind="read", target="calc.py")
    assert s.ok is True
    assert s.detail == ""


def test_taskrun_round_trips_through_json_without_loss():
    run = TaskRun(
        task_id="a1", harness="jsonloop", model="qwen3.8:latest",
        steps=[Step("read", "calc.py"), Step("refused", "tests/t.py", False, "protected path")],
        claimed_success=False, ended="max_steps", seconds=12.5, calls=3,
        unusable_replies=1, input_tokens=100, output_tokens=20, usd=0.0,
    )
    blob = json.dumps(dataclasses.asdict(run))
    back = json.loads(blob)
    back["steps"] = [Step(**s) for s in back["steps"]]
    assert TaskRun(**back) == run


def test_cost_fields_are_real_counts_not_a_char_proxy():
    """A char/4 proxy is not a token count and must never be published as one."""
    names = {f.name for f in dataclasses.fields(TaskRun)}
    assert {"input_tokens", "output_tokens", "usd", "seconds", "calls"} <= names
    assert "tokens" not in names, "ambiguous single 'tokens' field invites the proxy bug"
