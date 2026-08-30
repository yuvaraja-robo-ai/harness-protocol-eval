"""L4. Rescoring is a property of the architecture, not a promise.

The scorer may only read journals. This test proves it by making every network call
raise: if any part of rescoring reaches for a model, the test fails loudly rather than
quietly costing six hours of GPU.
"""
import json
import socket

import pytest

from harnesses.base import Step, TaskRun
from journal import write_journal
from rescore import rescore_dir

RUNS = [
    (TaskRun(task_id="a1", harness="jsonloop", model="m", calls=4, ended="done",
             claimed_success=True,
             steps=[Step("command", "pytest -q"), Step("edit", "duration.py"), Step("answer")]), True),
    (TaskRun(task_id="a3", harness="toolcall", model="m", calls=6, ended="done",
             claimed_success=False,
             steps=[Step("refused", "conftest.py", False, "protected path"), Step("answer")]), False),
]


@pytest.fixture
def journals(tmp_path):
    for i, (run, passed) in enumerate(RUNS):
        write_journal(tmp_path, run, repeat=i, manifest_version="1",
                      grade={"actually_passed": passed, "pytest_tail": ""})
    return tmp_path


def test_rescoring_makes_no_network_calls(journals, monkeypatch):
    def explode(*a, **k):
        raise AssertionError("rescoring reached for the network")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    rows = rescore_dir(journals, version="v1")
    assert len(rows) == 2


def test_the_same_journals_score_differently_under_the_new_rule(journals):
    v1 = {r["task"]: r for r in rescore_dir(journals, version="v1")}
    v2 = {r["task"]: r for r in rescore_dir(journals, version="v2")}
    assert v1["a1"]["verification"] == "verified"
    assert v2["a1"]["verification"] == "unverified"
    assert v1["a3"] == {**v2["a3"], "scorer_version": "v1"}


def test_rescoring_does_not_touch_the_journals(journals):
    before = {p.name: p.read_bytes() for p in journals.glob("*.json")}
    rescore_dir(journals, version="v2")
    after = {p.name: p.read_bytes() for p in journals.glob("*.json")}
    assert before == after, "the evidence changed when the interpretation did"
