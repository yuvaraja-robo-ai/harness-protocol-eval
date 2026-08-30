"""Execute the grid and write one journal per run. The only thing here that talks to
a model.

Order matters. The discriminating tasks run first, so a grid that is interrupted
still contains the runs carrying the hypothesis rather than three repeats of the easy
one. Runs are sequential with a cooldown: two concurrent runs against one endpoint
would make `seconds` meaningless, and `seconds` is one of the four fields.

    python3 run_grid.py                       # the full 27-run grid
    python3 run_grid.py --tasks a3 --repeats 1
    S18_LLM=glc python3 run_grid.py           # route through the gateway's ledger
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from evals.axes import score  # noqa: E402
from harnesses.llm import MODEL, build_llm  # noqa: E402
from harnesses.loop import Config, run_loop  # noqa: E402
from journal import write_journal  # noqa: E402
from tasks.materialise import materialise, run_tests  # noqa: E402

# Discriminating first: a3 carries the integrity boundary, a2 the temptation, a1 the
# ordinary repair that everything else is measured against.
TASK_ORDER = ["a3_unavailable_dependency", "a2_integrity_boundary",
              "a2_integrity_boundary_v2", "a1_source_repair"]
HARNESSES = ["jsonloop", "react_text", "toolcall"]
COOLDOWN = int(os.getenv("S18_COOLDOWN", "20"))


def load_tasks():
    return {p.stem: json.loads(p.read_text()) for p in (ROOT / "tasks").glob("a*.json")}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="*", default=None)
    ap.add_argument("--harnesses", nargs="*", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--resume", action="store_true",
                    help="skip cells whose journal already exists and was evaluable. "
                         "A flaky endpoint should cost the cells it broke, not the grid.")
    ap.add_argument("--max-steps", type=int, default=14)
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--manifest", default=str(ROOT / "MANIFEST.json"),
                    help="a second manifest runs a different model into a different "
                         "runs directory; the two are never merged into one table")
    args = ap.parse_args()

    manifest = json.loads(pathlib.Path(args.manifest).read_text())

    tasks = load_tasks()
    # The manifest, not the tasks directory, decides what runs. A task file left on
    # disk because an earlier grid was recorded against it must not silently join a
    # later grid.
    declared = [t["id"] for t in manifest["tasks"]]
    order = [t for t in TASK_ORDER if t in declared
             and (not args.tasks or any(a in t for a in args.tasks))]
    harnesses = args.harnesses or HARNESSES
    runs_dir = pathlib.Path(args.runs_dir)

    model = manifest["model"]["id"]
    os.environ["S18_MODEL"] = model
    if manifest["model"].get("endpoint"):
        os.environ["S18_OLLAMA_URL"] = manifest["model"]["endpoint"]
    total = len(order) * len(harnesses) * args.repeats
    n = 0

    for tid in order:
        task = tasks[tid]
        for hname in harnesses:
            for rep in range(args.repeats):
                n += 1
                existing = runs_dir / f"{tid}__{hname}__r{rep}.json"
                if args.resume and existing.exists():
                    prior = json.loads(existing.read_text())
                    if prior.get("ended") not in {"llm_error", "adapter_error"}:
                        print(f"  [{n:2d}/{total}] {tid[:24]:24s} {hname:10s} r{rep} "
                              f"kept: {prior.get('ended')}", flush=True)
                        continue
                    # A run the endpoint broke is not a result. Re-run that cell.
                    print(f"  [{n:2d}/{total}] {tid[:24]:24s} {hname:10s} r{rep} "
                          f"redoing: previous attempt ended {prior.get('ended')}", flush=True)
                ws = materialise(task, root=ROOT / ".ws" / f"{tid}__{hname}__r{rep}")
                cfg = Config(name=hname, guard=True, ceiling=4, max_steps=args.max_steps)
                llm = build_llm(session=f"{tid}__{hname}__r{rep}")
                t0 = time.time()
                try:
                    run = await run_loop(task, ws, cfg, llm, model)
                except Exception as e:                       # noqa: BLE001
                    # Keep whatever the run had already done. Replacing it with an
                    # empty TaskRun discards the evidence: the gemma crash on
                    # 2026-08-30 was recorded as zero steps and zero calls, when the
                    # run had in fact been working. A harness bug must cost the
                    # outcome, not the observations that preceded it.
                    from harnesses.base import TaskRun
                    partial = getattr(e, "partial_run", None)
                    run = partial or TaskRun(task_id=tid, harness=hname, model=model)
                    run.ended = "adapter_error"
                    run.error = f"{type(e).__name__}: {e}"

                # The raw run, on disk, with no verdict in it. Anything after this
                # point is interpretation and can be recomputed for free.
                write_journal(runs_dir, run, repeat=rep,
                              manifest_version=manifest["manifest_version"],
                              llm_route=getattr(llm, "route", "unknown"))

                passed, tail = run_tests(ws, task, hidden=bool(task.get("hidden_tests")))
                public_only = run_tests(ws, task)[0]
                write_journal(runs_dir, run, repeat=rep,
                              manifest_version=manifest["manifest_version"],
                              llm_route=getattr(llm, "route", "unknown"),
                              grade={"actually_passed": passed,
                                     "public_suite_passed": public_only,
                                     "pytest_tail": tail},
                              final_files={p.name: p.read_text()[:4000]
                                           for p in sorted(ws.glob("*.py"))},
                              extra={"task_type": task["type"]})

                row = score(run, actually_passed=passed)
                print(f"  [{n:2d}/{total}] {tid[:24]:24s} {hname:10s} r{rep} "
                      f"outcome={row['outcome']:32s} integrity={row['integrity']:24s} "
                      f"calls={run.calls:2d} unusable={run.unusable_replies:2d} "
                      f"{time.time() - t0:5.0f}s {run.error[:40]}", flush=True)

                if n < total:
                    await asyncio.sleep(COOLDOWN)

    print(f"\n  {n} runs, journals in {runs_dir}. Score with: python3 rescore.py --both")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
