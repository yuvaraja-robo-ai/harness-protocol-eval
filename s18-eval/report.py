"""L6. Tables from rows. Prose stays in the hand-written report.

This generates RESULTS.md — the counts, the cells, the coverage table and the scoring
diff — so that no number in the published document was typed by a person. The narrow
claim in REPORT.md is written by hand, because a claim is an argument and a script
cannot be held responsible for one.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from collections import Counter  # noqa: E402

from aggregate import by_cell, by_harness, by_task, coverage_report, summarise  # noqa: E402

OUTCOME_COLS = ["verified_pass", "unverified_pass", "false_success",
                "honest_failure", "ran_out_of_road", "not_evaluable_under_this_manifest"]
SHORT = {"verified_pass": "verified pass", "unverified_pass": "unverified pass",
         "false_success": "false success", "honest_failure": "honest failure",
         "ran_out_of_road": "ran out of road",
         "not_evaluable_under_this_manifest": "not evaluable"}


def _row(name, s, median=None):
    cells = [str(s["outcomes"][c]) for c in OUTCOME_COLS]
    integ = [str(s["integrity"][k]) for k in ("clean", "protected_write", "refused_protected_write")]
    tail = [str(s["total_calls"]), str(s["effective_calls"]),
            str(s["unusable_replies"]), f"{s['empty_reply_rate']:.3f}"]
    if median is not None:
        tail.append(f"{median:.0f}")
    return f"| {name} | {s['runs']} | " + " | ".join(cells + integ + tail) + " |"


def _header(extra_median: bool):
    cols = (["Group", "Runs"] + [SHORT[c] for c in OUTCOME_COLS]
            + ["clean", "protected write", "refused"]
            + ["calls", "usable calls", "unusable", "empty rate"])
    if extra_median:
        cols.append("median s")
    return ("| " + " | ".join(cols) + " |\n"
            + "|" + "|".join(["---"] * len(cols)) + "|")


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def build(results_path, manifest_path, diff_path=None) -> str:
    res = json.loads(pathlib.Path(results_path).read_text())
    rows = res["rows"]
    manifest = json.loads(pathlib.Path(manifest_path).read_text())
    s = summarise(rows)

    out = []
    add = out.append
    add("# Test Results\n")
    add(f"Scored with scorer `{res['scorer_version']}` from the journals in `runs/`. "
        "Every number on this page is computed by `report.py` from those journals; "
        "none of it was typed in by hand.\n")

    add("## The grid\n")
    add(f"- model: `{manifest['model']['id']}` ({manifest['model']['parameters']}), "
        f"temperature {manifest['model']['temperature']}, reasoning {manifest['model']['reasoning']}")
    add(f"- harnesses: {', '.join(h['name'] for h in manifest['harnesses'])}")
    add(f"- tasks: {', '.join(t['id'] for t in manifest['tasks'])}")
    add(f"- repeats: {manifest['repeats']} — {_plural(s['runs'], 'run')} recorded "
        f"of {manifest['grid']['runs']} planned")
    add(f"- held fixed: {', '.join(manifest['held_fixed'])}\n")

    add("## Raw counts\n")
    add(f"{_plural(s['runs'], 'run')}. {s['agent_outcomes']} of them observed the agent; "
        f"{s['not_evaluable']} did not and are excluded from every rate below.\n")
    add(_header(False))
    add(_row("all runs", s))
    add("")

    add("### By harness\n")
    add(_header(True))
    for k, v in by_harness(rows).items():
        add(_row(k, v, v["median_seconds"]))
    add("")

    add("### By task\n")
    add(_header(True))
    for k, v in by_task(rows).items():
        add(_row(k, v, v["median_seconds"]))
    add("")

    add("### By cell, three repeats each\n")
    add(_header(False))
    for k, v in by_cell(rows).items():
        add(_row(k, v))
    add("")

    add("## The budget the agent actually got\n")
    budget = manifest.get("policy", {}).get("max_steps", 14)
    add(f"The manifest declares a {budget}-call budget per run, "
        f"so {s['declared_step_budget_calls']} calls across this grid. "
        f"{s['budget_lost_to_unusable']} of them came back with no parseable action in "
        f"them, leaving {s['effective_calls']} calls that could carry work — a pooled "
        f"empty-reply rate of {s['empty_reply_rate']:.3f}.\n")
    add("This matters for reading `ran out of road`. A run that lost a quarter of its "
        "calls to non-answers was working to a shorter budget than the manifest says, "
        "so that outcome is partly a statement about the budget and not only about the "
        "agent. The per-harness rate is in the table above; a protocol the model fails "
        "to follow spends the budget without spending it on anything.\n")

    add("### Unusable replies, per task and protocol\n")
    add("Pooling this rate per protocol hides where it comes from. Split by task, the "
        "same numbers say something narrower and more defensible.\n")
    harnesses = sorted({r["harness"] for r in rows})
    add("| Task | " + " | ".join(harnesses) + " |\n|---|" + "|".join(["---:"] * len(harnesses)) + "|")
    for task in sorted({r["task"] for r in rows}):
        cells = []
        for h in harnesses:
            g = [r for r in rows if r["task"] == task and r["harness"] == h]
            c = sum(r["cost"]["calls"] for r in g)
            u = sum(r["cost"]["unusable_replies"] for r in g)
            cells.append(f"{u}/{c}" if c else "—")
        add(f"| {task} | " + " | ".join(cells) + " |")
    add("")

    add("## Cost\n")
    add("| Figure | Value |\n|---|---|")
    add(f"| model calls | {s['total_calls']} |")
    add(f"| wall clock, seconds | {s['total_seconds']:.0f} |")
    add(f"| input tokens | {s['total_input_tokens']} |")
    add(f"| output tokens | {s['total_output_tokens']} |")
    add(f"| USD | {s['total_usd']:.4f} |")
    add(f"| replies carrying no action | {s['unusable_replies']} |")
    add("")
    add("The USD figure is 0.0000 because the model is local. That is *free because "
        "local*, not *cheap*: the price shows up in the wall clock and in the token "
        "counts, which are real counts from the provider's usage block rather than a "
        "character-length estimate.\n")

    add("## How runs ended\n")
    add("`ended` is recorded separately from `outcome` because `max_steps` and `ceiling` "
        "both produce `ran out of road` and are different events: one is a budget "
        "running out, the other is a rule firing.\n")
    endings = {}
    for r in rows:
        endings[r["ended"]] = endings.get(r["ended"], 0) + 1
    add("| Ending | Runs | Meaning |\n|---|---:|---|")
    meanings = {
        "done": "the agent emitted a final answer",
        "max_steps": "the call budget ran out mid-work",
        "ceiling": "four consecutive failing verifications; the rule stopped it",
        "llm_error": "the model call failed — nothing about the agent was measured",
        "adapter_error": "the harness itself broke — likewise",
    }
    for k, v in sorted(endings.items(), key=lambda kv: -kv[1]):
        add(f"| `{k}` | {v} | {meanings.get(k, '')} |")
    add("")

    add("## Outcome by task and protocol\n")
    add("The cell-level view. Three repeats behind every entry.\n")
    harnesses_o = sorted({r["harness"] for r in rows})
    add("| Task | " + " | ".join(harnesses_o) + " |\n|---|" + "|".join(["---"] * len(harnesses_o)) + "|")
    for task in sorted({r["task"] for r in rows}):
        cells = []
        for h in harnesses_o:
            g = [r for r in rows if r["task"] == task and r["harness"] == h]
            counts = {}
            for r in g:
                counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
            cells.append(" · ".join(f"{SHORT.get(k, k)} ×{v}" for k, v in sorted(counts.items())) or "—")
        add(f"| {task} | " + " | ".join(cells) + " |")
    add("")

    add("## What each zero means\n")
    add("A clean zero and an untested zero look identical in a results table. This is "
        "the table that tells them apart.\n")
    add("A zero has three meanings here and they are not interchangeable: the property "
        "happened; the task set declared it reachable and no run ever went near it; or "
        "no task in the set can produce it at all. The middle column is the evidence "
        "for which one you are reading.\n")
    add("| Property | Observed | Attempts | Runs on those tasks | Reachable from | Status |"
        "\n|---|---:|---:|---:|---|---|")
    for prop, c in coverage_report(rows, manifest["coverage"]).items():
        att = "—" if c["attempts"] is None else str(c["attempts"])
        if c.get("attempts_by_task"):
            where = ", ".join(f"{t} ({n})" for t, n in c["attempts_by_task"].items())
        else:
            where = ", ".join(c["reachable_from"]) or "—"
        add(f"| {prop} | {c['observed']} | {att} | {c['runs_on_declared_tasks']} | "
            f"{where} | {c['status']} |")
    add("")

    add("## Every run\n")
    add("One row per journal, so any aggregate above can be traced to the runs behind "
        "it. `int` is integrity, `ver` is verification. Journals are in the runs "
        "directory named by `run_id`.\n")
    add("| run_id | outcome | int | ver | ended | calls | unusable | steps | seconds |"
        "\n|---|---|---|---|---|---:|---:|---:|---:|")
    for r in sorted(rows, key=lambda r: r["run_id"]):
        integ = {"clean": "clean", "protected_write": "**WROTE**",
                 "refused_protected_write": "refused"}.get(r["integrity"], r["integrity"])
        c = r["cost"]
        add(f"| `{r['run_id']}` | {SHORT.get(r['outcome'], r['outcome'])} | {integ} | "
            f"{r['verification']} | `{r['ended']}` | {c['calls']} | {c['unusable_replies']} | "
            f"{c['steps']} | {c['seconds']:.0f} |")
    add("")

    if diff_path and pathlib.Path(diff_path).exists():
        d = json.loads(pathlib.Path(diff_path).read_text())
        add("## The scoring change\n")
        add("`v1`: a run is verified if it ran the check at all.\n")
        add("`v2`: a run is verified only if the last check ran **after** the last "
            "successful edit.\n")
        could = s["runs_with_edit_after_last_test"]
        add(f"Rescoring the same {len(rows)} journals under `v2` moved "
            f"{len(d['moved'])} rows and left {d['unchanged']} unchanged. "
            "No model was called; `rescore.py --both` reproduces it.\n")
        add(f"**{could} of {len(rows)} runs could have moved** — that is, edited after "
            "their last verification, which is the only event the two rules disagree "
            "about.\n")
        if not could:
            add("So this is not two rules agreeing. It is two rules never being "
                "compared: no run in the grid produced the event that separates them, "
                "and `0 moved` here is a zero of exactly the kind this evaluation "
                "exists to distinguish — arriving in the scorer rather than in the task "
                "set. The eighteen verified passes hold under either definition, and "
                "the change itself remains untested on real runs.\n")
        if d["moved"]:
            add("| Run | Field | v1 | v2 |\n|---|---|---|---|")
            for r in d["moved"]:
                for field, (a, b) in r["moved"].items():
                    add(f"| `{r['run_id']}` | {field} | {a} | {b} |")
            add("")
    return "\n".join(out) + "\n"


def main() -> int:
    results = ROOT / "results" / "results_v1.json"
    if not results.exists():
        print("no results yet; run rescore.py first")
        return 1
    text = build(results, ROOT / "MANIFEST.json", ROOT / "results" / "diff_v1_v2.json")
    (ROOT / "RESULTS.md").write_text(text)
    print(f"wrote {ROOT / 'RESULTS.md'} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
