"""Recompute every field from the persisted journals. No model calls, ever.

This exists because the alternative is paying for the run again to correct a
spreadsheet formula. The scorer reads journals and nothing else, so a rule can change
after the evidence is collected — which is the only way a scoring change can be
honest, since a rule chosen after seeing the runs would otherwise be unfalsifiable.

    python3 rescore.py            # v1
    python3 rescore.py --v2       # the scoring change
    python3 rescore.py --both     # both, plus the diff between them
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from evals.axes import score  # noqa: E402
from journal import load_journal  # noqa: E402


def rescore_dir(dirpath, version: str = "v1") -> list[dict]:
    rows = []
    for f in sorted(pathlib.Path(dirpath).glob("*.json")):
        run, passed = load_journal(f)
        row = score(run, actually_passed=passed, version=version)
        row["run_id"] = f.stem
        rows.append(row)
    return rows


def write_results(rows, path, version):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"scorer_version": version, "rows": rows}, indent=1))
    return p


def diff(v1: list[dict], v2: list[dict]) -> list[dict]:
    """What the rule change moved, and what it left alone.

    A scoring change that moves nothing is worth reporting as such; a scoring change
    that moves an outcome without moving its evidence is the interesting case.
    """
    by_id = {r["run_id"]: r for r in v1}
    out = []
    for b in v2:
        a = by_id.get(b["run_id"])
        if not a:
            continue
        moved = {k: (a[k], b[k]) for k in ("outcome", "verification", "integrity")
                 if a[k] != b[k]}
        if moved:
            out.append({"run_id": b["run_id"], "moved": moved})
    return out


def main() -> int:
    runs = ROOT / "runs"
    if not any(runs.glob("*.json")):
        print(f"no journals in {runs}; nothing to rescore")
        return 1

    want = sys.argv[1:] or ["--v1"]
    both = "--both" in want
    versions = ["v1", "v2"] if both else (["v2"] if "--v2" in want else ["v1"])

    scored = {}
    for v in versions:
        rows = rescore_dir(runs, version=v)
        scored[v] = rows
        out = write_results(rows, ROOT / "results" / f"results_{v}.json", v)
        print(f"rescored {len(rows)} journals under {v}, 0 model calls -> {out}")

    if both:
        d = diff(scored["v1"], scored["v2"])
        p = ROOT / "results" / "diff_v1_v2.json"
        p.write_text(json.dumps({"moved": d, "unchanged": len(scored["v1"]) - len(d)}, indent=1))
        print(f"\n  the scoring change moved {len(d)} of {len(scored['v1'])} rows -> {p}")
        for r in d:
            for field, (a, b) in r["moved"].items():
                print(f"    {r['run_id']:44s} {field}: {a} -> {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
