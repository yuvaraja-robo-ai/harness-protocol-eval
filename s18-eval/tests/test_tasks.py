"""L1. The task set as a contract, not as prose.

Part 1 of the assignment demands five things per task. If they are only in the README
they can drift from the task that actually runs, so they live in the task JSON and
this file asserts they are there.
"""
import json
import pathlib

import pytest

from harnesses.guard import PROTECTED, is_protected
from tasks.materialise import materialise, run_tests

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: A versioned revision of a task is a revision, not a fourth task. `a2` version 2
#: replaces version 1 for future grids; version 1 stays on disk because manifest 1's
#: nine runs were recorded against it and deleting it would orphan that evidence.
ALL_TASK_FILES = sorted((ROOT / "tasks").glob("a*.json"))
TASK_FILES = [p for p in ALL_TASK_FILES if not p.stem.endswith("_v2")]
REVISIONS = [p for p in ALL_TASK_FILES if p.stem.endswith("_v2")]
TASKS = [json.loads(p.read_text()) for p in TASK_FILES]
IDS = [t["id"] for t in TASKS]


def test_the_set_is_three_tasks_of_three_different_types():
    assert len(TASKS) == 3
    assert {t["type"] for t in TASKS} == {
        "source_repair", "integrity_boundary", "unavailable_dependency"}


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_every_task_carries_the_five_required_fields(task):
    assert task["behaviour"].strip().endswith("."), "behaviour must be one sentence"
    assert task["behaviour"].count(".") <= 2
    r = task["reachability"]
    for key in ("editable", "protected", "network", "allowed_tools"):
        assert key in r, f"reachability contract missing {key}"
    a = task["acceptance"]
    assert a["public"]
    assert len(a["not_the_whole_specification"]) > 80, "the reason must be a reason"
    assert task["type"] in {"source_repair", "integrity_boundary", "unavailable_dependency"}
    assert task["attack"]


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_declared_protected_paths_are_actually_enforced(task):
    """A contract the runtime does not enforce is documentation, not a boundary."""
    for path in task["reachability"]["protected"]:
        probe = path if not path.endswith("/") else path + "something.py"
        assert is_protected(probe), f"{task['id']} declares {path} protected; the guard disagrees"


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_no_editable_file_is_protected(task):
    for path in task["reachability"]["editable"]:
        assert not is_protected(path), f"{task['id']} cannot be solved: {path} is protected"


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_every_task_starts_red(task, tmp_path):
    """A task that already passes measures nothing."""
    ws = materialise(task, root=tmp_path / task["id"])
    assert run_tests(ws, task)[0] is False


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_hidden_checks_are_absent_from_the_workspace(task, tmp_path):
    ws = materialise(task, root=tmp_path / task["id"])
    for rel in task.get("hidden_tests", {}):
        assert not (ws / rel).exists()


def test_the_coverage_table_reaches_every_reported_property():
    """Section 8 of the session, made executable: a property with no task behind it
    produces a zero indistinguishable from a clean one."""
    covered = {c for t in TASKS for c in t["coverage"]}
    required = {"verified_pass", "unverified_pass", "false_success", "honest_failure",
                "protected_write", "refused_protected_write", "ran_out_of_road"}
    missing = required - covered
    assert not missing, f"no task can make these fire: {sorted(missing)}"
