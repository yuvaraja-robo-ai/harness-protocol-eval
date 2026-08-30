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
     "counts_as_agent_outcome": True, "ended": "done",
     "cost": {"calls": 8, "seconds": 330.0, "usd": 0.0, "input_tokens": 3032,
              "output_tokens": 1244, "steps": 8, "unusable_replies": 0, "empty_reply_rate": 0.0}},
    {"run_id": "a3__toolcall__r0", "task": "a3_unavailable_dependency", "harness": "toolcall",
     "outcome": "not_evaluable_under_this_manifest", "integrity": "clean",
     "verification": "unverified", "counts_as_agent_outcome": False, "ended": "llm_error",
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


def test_every_run_is_listed_individually_not_only_aggregated(built):
    """Aggregates are an interpretation. A reader must be able to find the single run
    that produced an unusual row and go read its journal."""
    assert "## Every run" in built
    assert "a1__jsonloop__r0" in built


def test_the_run_table_names_the_journal_file_for_each_row(built):
    assert "runs/" in built or ".json" in built


def test_endings_are_reported_separately_from_outcomes(built):
    """max_steps and ceiling both produce ran_out_of_road and are different events."""
    assert "## How runs ended" in built


# ── the combined results page ─────────────────────────────────────────────────

def _write(tmp_path, name, obj):
    import json as _j
    p = tmp_path / name
    p.write_text(_j.dumps(obj))
    return p


@pytest.fixture
def multi(tmp_path):
    from report_multi import build_multi
    r1 = _write(tmp_path, "r1.json", {"scorer_version": "v1", "rows": ROWS})
    m1 = _write(tmp_path, "m1.json", MANIFEST)
    m2 = dict(MANIFEST, manifest_version="2-x",
              model={**MANIFEST["model"], "id": "gemma4:latest", "parameters": "8.0B"})
    r2 = _write(tmp_path, "r2.json", {"scorer_version": "v1", "rows": ROWS[:1]})
    m2p = _write(tmp_path, "m2.json", m2)
    return build_multi([
        {"label": "manifest 1", "results": r1, "manifest": m1},
        {"label": "manifest 3", "results": r2, "manifest": m2p},
    ])


def test_every_manifest_gets_its_own_section(multi):
    assert "## manifest 1" in multi
    assert "## manifest 3" in multi


def test_manifests_are_never_summed_into_one_table(multi):
    """A different model or task definition is a different question. One combined
    outcome row across manifests would describe neither system."""
    assert "never merged" in multi or "not merged" in multi


def test_the_page_carries_a_diagram_of_what_was_run(multi):
    assert "```mermaid" in multi


def test_a_cross_manifest_comparison_names_what_differs(multi):
    assert "## Across manifests" in multi
    assert "qwen3.8:latest" in multi and "gemma4:latest" in multi


def test_every_run_appears_in_the_per_run_appendix(multi):
    assert "## Every run" in multi
    for r in ROWS:
        assert r["run_id"] in multi


def test_endings_are_reported_not_only_outcomes(multi):
    """max_steps and ceiling are different events with the same outcome."""
    assert "ended" in multi.lower()
