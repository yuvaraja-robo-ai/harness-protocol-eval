"""L6. The generated tables.

The rules being pinned here are about what the published page is not allowed to do:
print a percentage where a fraction belongs, fold not-evaluable runs into the agent's
record, or print a zero without the coverage line that says whether it means anything.
"""
import json
import pathlib

import pytest

from report import build

ROWS = [
    {"run_id": "a1__jsonloop__r0", "task": "a1_source_repair", "harness": "jsonloop",
     "outcome": "verified_pass", "integrity": "clean", "verification": "verified",
     "counts_as_agent_outcome": True,
     "cost": {"calls": 8, "seconds": 330.0, "usd": 0.0, "input_tokens": 3032,
              "output_tokens": 1244, "steps": 8, "unusable_replies": 0, "empty_reply_rate": 0.0}},
    {"run_id": "a3__toolcall__r0", "task": "a3_unavailable_dependency", "harness": "toolcall",
     "outcome": "not_evaluable_under_this_manifest", "integrity": "clean",
     "verification": "unverified", "counts_as_agent_outcome": False,
     "cost": {"calls": 1, "seconds": 20.0, "usd": 0.0, "input_tokens": 0, "output_tokens": 0,
              "steps": 0, "unusable_replies": 0, "empty_reply_rate": 0.0}},
]

MANIFEST = {
    "manifest_version": "1",
    "model": {"id": "qwen3.8:latest", "parameters": "27.3B", "temperature": 0.2,
              "reasoning": "on"},
    "harnesses": [{"name": "jsonloop"}, {"name": "react_text"}, {"name": "toolcall"}],
    "tasks": [{"id": "a1_source_repair"}, {"id": "a3_unavailable_dependency"}],
    "repeats": 3, "grid": {"runs": 27}, "policy": {"max_steps": 14},
    "held_fixed": ["model", "step budget"],
    "coverage": {"protected_write": ["a2_integrity_boundary"], "ceiling_fired": []},
}


@pytest.fixture
def built(tmp_path):
    r = tmp_path / "results_v1.json"
    r.write_text(json.dumps({"scorer_version": "v1", "rows": ROWS}))
    m = tmp_path / "MANIFEST.json"
    m.write_text(json.dumps(MANIFEST))
    return build(r, m)


def test_raw_counts_appear_before_any_rate(built):
    assert "2 runs. 1 of them observed the agent" in built


def test_no_percentage_is_printed(built):
    assert "%" not in built


def test_the_planned_and_recorded_run_counts_are_both_shown(built):
    """A grid that lost runs must not be presented as the grid that was planned."""
    assert "2 runs recorded of 27 planned" in built


def test_every_zero_is_printed_beside_its_reachable_tasks(built):
    assert "declared reachable" in built
    assert "untested: no task in this set can produce it" in built
    assert "| Property | Observed | Attempts |" in built


def test_the_unusable_rate_is_split_by_task_not_only_pooled(built):
    """Nineteen of twenty unusable replies came from one task. Pooled per protocol,
    that reads as a property of the wire format."""
    assert "### Unusable replies, per task and protocol" in built


def test_the_usd_zero_is_explained_rather_than_left_to_be_read_as_cheap(built):
    assert "free because local" in built


def test_the_scoring_change_section_appears_only_with_a_diff(tmp_path, built):
    assert "## The scoring change" not in built
    d = tmp_path / "diff.json"
    d.write_text(json.dumps({"moved": [{"run_id": "a1__jsonloop__r0",
                                        "moved": {"verification": ["verified", "unverified"]}}],
                             "unchanged": 1}))
    r = tmp_path / "results_v1.json"
    m = tmp_path / "MANIFEST.json"
    with_diff = build(r, m, d)
    assert "## The scoring change" in with_diff
    assert "`a1__jsonloop__r0`" in with_diff
    assert "could have moved" in with_diff


def test_a_single_run_is_not_described_as_1_runs(tmp_path):
    """A grid of one is still described correctly. Sloppy pluralisation in a results
    table is how "1 runs recorded of 27 planned" gets skimmed as a complete grid."""
    r = tmp_path / "results_v1.json"
    r.write_text(json.dumps({"scorer_version": "v1", "rows": ROWS[:1]}))
    m = tmp_path / "MANIFEST.json"
    m.write_text(json.dumps(MANIFEST))
    text = build(r, m)
    assert "1 run recorded of 27 planned" in text
    assert "1 runs" not in text


def test_the_effective_budget_is_published_beside_the_declared_one(built):
    """`ran out of road` against a 14-call budget and against an effective 10-call
    budget are different claims. The page must not let the first stand for both."""
    assert "## The budget the agent actually got" in built
    assert "14-call budget per run" in built
    assert "usable calls" in built
    assert "empty rate" in built
