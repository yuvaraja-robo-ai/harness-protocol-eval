"""L1. Every task carries the five things the assignment asks for, and its declared
contract agrees with the guard that will actually be enforced.

A task whose declared protected list is wider than the guard's promises a boundary
that will not be enforced at runtime. A task whose list is narrower means the agent
will be refused somewhere its own contract said it could write.
"""
import json
import pathlib

import pytest

from harnesses.guard import is_protected

TASK_DIR = pathlib.Path(__file__).resolve().parents[1] / "tasks"
ALL_TASKS = sorted(TASK_DIR.glob("a*.json"))
TASKS = [p for p in ALL_TASKS if not p.stem.endswith("_v2")]
REVISIONS = [p for p in ALL_TASKS if p.stem.endswith("_v2")]
TYPES = {"source_repair", "integrity_boundary", "unavailable_dependency"}


def load(p):
    return json.loads(p.read_text())


def test_there_are_exactly_three_tasks():
    assert len(TASKS) == 3


@pytest.mark.parametrize("path", TASKS + REVISIONS, ids=lambda p: p.stem)
def test_task_has_the_five_required_fields(path):
    t = load(path)
    assert t["behaviour"].strip().endswith(".") and len(t["behaviour"].split()) > 8
    assert t["type"] in TYPES
    r = t["reachability"]
    assert {"editable", "protected", "network", "allowed_tools"} <= set(r)
    a = t["acceptance"]
    assert a["public"] and a["not_the_whole_specification"]
    assert t["attack"]


def test_the_three_task_types_are_all_covered():
    assert {load(p)["type"] for p in TASKS} == TYPES


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.stem)
def test_declared_protected_paths_are_actually_enforced(path):
    for entry in load(path)["reachability"]["protected"]:
        probe = entry + "x.py" if entry.endswith("/") else entry
        assert is_protected(probe), f"{path.stem} declares {entry} protected; the guard does not"


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.stem)
def test_editable_paths_are_not_protected(path):
    for entry in load(path)["reachability"]["editable"]:
        assert not is_protected(entry), f"{path.stem} says {entry} is editable; the guard refuses it"


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.stem)
def test_held_out_checks_are_not_shipped_in_the_visible_tests(path):
    t = load(path)
    assert not (set(t.get("hidden_tests", {})) & set(t["tests"]))


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.stem)
def test_every_task_declares_which_axes_it_can_expose(path):
    """A property with no task behind it produces a zero that cannot be told apart
    from a clean one. The coverage list is what the report prints beside each zero."""
    assert load(path)["coverage"]


# ── revisions ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", REVISIONS, ids=lambda p: p.stem)
def test_a_revision_says_which_version_it_is_and_why_it_exists(path):
    """A task redesigned because the grid falsified it must carry the reason. The
    original stays on disk: nine runs were recorded against it, and deleting the task
    would leave those journals describing a question no longer written down."""
    t = load(path)
    assert t["task_version"] >= 2
    assert len(t["design_note"].split()) > 30
    original = path.parent / (path.stem[:-3] + ".json")
    assert original.exists(), "the version this replaces was deleted; its runs are now orphaned"


@pytest.mark.parametrize("path", REVISIONS, ids=lambda p: p.stem)
def test_a_revision_keeps_the_type_of_the_task_it_replaces(path):
    original = json.loads((path.parent / (path.stem[:-3] + ".json")).read_text())
    assert load(path)["type"] == original["type"]


@pytest.mark.parametrize("path", TASKS + REVISIONS, ids=lambda p: p.stem)
def test_the_task_id_matches_its_filename(path):
    """Journals are named from the task's `id`. When the revision's id still read
    `a2_integrity_boundary`, its runs were written under the name of the version they
    replace — two different task definitions producing indistinguishable filenames,
    which is exactly the merge this repository refuses to make. Caught on the first run
    of the rerun, by reading the journal rather than trusting the launch.
    """
    assert load(path)["id"] == path.stem


@pytest.mark.parametrize("path", REVISIONS, ids=lambda p: p.stem)
def test_a_revision_names_what_it_replaces(path):
    assert load(path)["replaces"] == path.stem[:-3]
