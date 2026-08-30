"""The whole pipeline below the model: journals in, published documents out.

    python3 close_out.py

Scores every journal under v1 and v2, writes the diff, regenerates RESULTS.md, and
prints the counts the hand-written claim in REPORT.md has to agree with. It calls no
model, so it can be re-run after any scorer change for free — which is the property
the layering exists to provide.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from aggregate import by_cell, by_harness, by_task, coverage_report, summarise  # noqa: E402


def main() -> int:
    runs = sorted((ROOT / "runs").glob("*.json"))
    if not runs:
        print("no journals in runs/; run run_grid.py first")
        return 1

    for cmd in (["python3", "rescore.py", "--both"], ["python3", "report.py"]):
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        print(r.stdout.rstrip() or r.stderr.rstrip())
        if r.returncode:
            return r.returncode

    rows = json.loads((ROOT / "results" / "results_v1.json").read_text())["rows"]
    manifest = json.loads((ROOT / "MANIFEST.json").read_text())
    s = summarise(rows)

    # A partial grid is publishable. A partial grid presented as a complete one is not.
    planned = manifest["grid"]["runs"]
    if s["runs"] < planned:
        print(f"\n  ** INCOMPLETE GRID: {s['runs']} of {planned} runs recorded. **")
        print("  Every table below describes the runs that exist. Say so in REPORT.md,")
        print("  and name the missing cells rather than reshaping the grid to fit.")
        have = {(r["task"], r["harness"]) for r in rows}
        want = {(t["id"], h["name"]) for t in manifest["tasks"] for h in manifest["harnesses"]}
        for cell in sorted(want - have):
            print(f"    missing entirely: {cell[0]} x {cell[1]}")

    print("\n  ── the numbers REPORT.md must agree with ──")
    print(f"  runs recorded          {s['runs']} of {manifest['grid']['runs']} planned")
    print(f"  observed the agent     {s['agent_outcomes']}")
    print(f"  not evaluable          {s['not_evaluable']}")
    for k, v in s["outcomes"].items():
        print(f"    {k:38s} {v}")
    for k, v in s["integrity"].items():
        print(f"    integrity {k:28s} {v}")
    print(f"  calls {s['total_calls']}   seconds {s['total_seconds']:.0f}   "
          f"in {s['total_input_tokens']}   out {s['total_output_tokens']}   "
          f"usd {s['total_usd']:.4f}   unusable {s['unusable_replies']}")

    print("\n  ── what each zero means ──")
    for prop, c in coverage_report(rows, manifest["coverage"]).items():
        print(f"    {prop:34s} {c['observed']:2d}  {c['status']}")

    print("\n  ── by harness ──")
    for k, v in by_harness(rows).items():
        print(f"    {k:12s} runs {v['runs']:2d}  verified_pass {v['outcomes']['verified_pass']:2d}  "
              f"median {v['median_seconds']:.0f}s  unusable {v['unusable_replies']}")

    print("\n  ── by task ──")
    for k, v in by_task(rows).items():
        print(f"    {k:28s} runs {v['runs']:2d}  "
              f"verified_pass {v['outcomes']['verified_pass']:2d}  "
              f"honest_failure {v['outcomes']['honest_failure']:2d}  "
              f"protected_write {v['integrity']['protected_write']:2d}  "
              f"refused {v['integrity']['refused_protected_write']:2d}")

    d = json.loads((ROOT / "results" / "diff_v1_v2.json").read_text())
    print(f"\n  the scoring change moved {len(d['moved'])} rows, left {d['unchanged']} alone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
