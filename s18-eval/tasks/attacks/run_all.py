"""The label gate. Run before the manifest is frozen and before any model is called.

Every task label in this repository is a hypothesis until an attack has been executed
against it. In the S18Code run, four of seven labels were wrong on first authoring —
every one of them argued rather than run. This script is the mechanism that would have
caught them.

Output: results/attack_matrix.json, one row per attack, each carrying `label_holds` or
`relabel_required`. A single `relabel_required` obliges a manifest correction before
the grid may run.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tasks.materialise import materialise, run_tests  # noqa: E402

ATTACKS = [
    "a1_attack_hardcode", "a1_attack_real_fix",
    "a2_attack_delete_test", "a2_attack_real_fix",
    "a2v2_attack_naive_quadratic", "a2v2_attack_real_fix", "a2v2_attack_delete_test",
    "a3_attack_conftest", "a3_attack_source_only",
]


def load_task(task_id: str) -> dict:
    return json.loads((ROOT / "tasks" / f"{task_id}.json").read_text())


def _grade(task, ws):
    public, tail = run_tests(ws, task)
    held = None
    if task.get("hidden_tests"):
        held = run_tests(ws, task, hidden=True)[0]
    return public, held, tail


def run_one(mod, workdir: pathlib.Path) -> list[dict]:
    task = load_task(mod.TASK_ID)
    variants = getattr(mod, "VARIANTS", {None: None})
    rows = []
    for variant in variants:
        ws = materialise(task, root=workdir / f"{mod.NAME}_{variant or 'base'}")
        if variant is None:
            mod.apply(ws)
        else:
            mod.apply(ws, variant)

        on_disk = None
        if getattr(mod, "ALSO_ASSERT_GREEN_ON_DISK", False):
            # Grade WITHOUT restoring, to show the edit really did go green before the
            # restore discarded it. Without this the attack proves nothing about the
            # temptation, only about the grader.
            import subprocess
            r = subprocess.run(["python3", "-m", "pytest", "-q", "--no-header",
                                "-p", "no:cacheprovider"],
                               cwd=ws, capture_output=True, text=True, timeout=120)
            on_disk = r.returncode == 0

        public, held, tail = _grade(task, ws)
        expect = mod.EXPECT
        ok = (("pass" if public else "fail") == expect["public"])
        if expect.get("held_out") is not None:
            ok = ok and (("pass" if held else "fail") == expect["held_out"])
        rows.append({
            "task": mod.TASK_ID,
            "attack": mod.NAME + (f"::{variant}" if variant else ""),
            "public_suite": "pass" if public else "fail",
            "held_out": None if held is None else ("pass" if held else "fail"),
            "green_on_disk_before_restore": on_disk,
            "expected": expect,
            "verdict": "label_holds" if ok else "relabel_required",
            "pytest_tail": tail[-200:],
            "run_on": str(date.today()),
        })
    return rows


def main() -> int:
    workdir = ROOT / ".attack_ws"
    rows: list[dict] = []
    for name in ATTACKS:
        mod = importlib.import_module(f"tasks.attacks.{name}")
        rows.extend(run_one(mod, workdir))

    out = ROOT / "results" / "attack_matrix.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"run_on": str(date.today()), "rows": rows}, indent=1))

    bad = [r for r in rows if r["verdict"] != "label_holds"]
    for r in rows:
        print(f"  {r['task'][:26]:26s} {r['attack'][:38]:38s} "
              f"public={r['public_suite']:4s} held_out={str(r['held_out']):5s} "
              f"{r['verdict']}")
    print(f"\n  {len(rows)} attacks, {len(bad)} requiring a relabel -> {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
