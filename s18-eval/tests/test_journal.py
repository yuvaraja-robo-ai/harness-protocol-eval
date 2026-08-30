"""L3. The evidence layer.

Two properties. The journal is written before the grade is known, and the journal is
sufficient on its own — the scorer must be able to score it with the workspace
deleted. If a field can only be recovered by going back to the workspace, then a
scorer change costs a rerun, which is the thing this layer exists to prevent.
"""
import json
import pathlib
import shutil

import pytest

from evals.axes import score
from harnesses.base import JOURNAL_SCHEMA, Step, TaskRun
from journal import load_journal, write_journal

RUN = TaskRun(
    task_id="a1", harness="jsonloop", model="qwen3.8:latest",
    steps=[Step("read", "calc.py"), Step("edit", "calc.py"), Step("command", "pytest -q"),
           Step("answer", detail="fixed")],
    claimed_success=True, ended="done", seconds=42.0, calls=4,
    input_tokens=900, output_tokens=210, usd=0.0,
)


def test_journal_is_written_before_the_grade_is_attached(tmp_path):
    p = write_journal(tmp_path, RUN, repeat=0, manifest_version="1")
    d = json.loads(p.read_text())
    assert d["schema"] == JOURNAL_SCHEMA
    assert "actually_passed" not in d, "the grade was attached before the run was persisted"


def test_the_grade_is_appended_and_the_run_record_is_unchanged(tmp_path):
    p = write_journal(tmp_path, RUN, repeat=0, manifest_version="1")
    before = json.loads(p.read_text())
    write_journal(tmp_path, RUN, repeat=0, manifest_version="1",
                  grade={"actually_passed": True, "pytest_tail": "1 passed"},
                  final_files={"calc.py": "x"})
    after = json.loads(p.read_text())
    assert after["actually_passed"] is True
    for k in ("steps", "calls", "claimed_success", "ended", "input_tokens"):
        assert after[k] == before[k], f"{k} changed when the grade was attached"


def test_a_journal_scores_with_the_workspace_deleted(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "calc.py").write_text("x = 1\n")
    p = write_journal(tmp_path / "runs", RUN, repeat=0, manifest_version="1",
                      grade={"actually_passed": True, "pytest_tail": ""},
                      final_files={"calc.py": (ws / "calc.py").read_text()})
    shutil.rmtree(ws)
    run, passed = load_journal(p)
    assert score(run, actually_passed=passed)["outcome"] == "verified_pass"


def test_run_id_encodes_task_harness_and_repeat(tmp_path):
    p = write_journal(tmp_path, RUN, repeat=2, manifest_version="1")
    assert p.name == "a1__jsonloop__r2.json"
    assert json.loads(p.read_text())["run_id"] == "a1__jsonloop__r2"


def test_an_unknown_schema_is_refused_rather_than_misread(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"schema": "s18-journal/99", "task_id": "a1"}))
    with pytest.raises(ValueError, match="schema"):
        load_journal(p)


def test_round_trip_preserves_every_step(tmp_path):
    p = write_journal(tmp_path, RUN, repeat=0, manifest_version="1",
                      grade={"actually_passed": False, "pytest_tail": ""})
    run, passed = load_journal(p)
    assert run == RUN
    assert passed is False
