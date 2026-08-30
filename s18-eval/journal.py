"""L3. The raw run, on disk, before any scorer touches it.

Scores change. The observation should not. `empty_billed` shipped wrong once in the
S18Code run and the only available fix was six more hours of GPU; with the journal on
disk a scorer bug costs one `rescore.py` instead.

The journal is written twice: once the moment the harness returns, with no verdict in
it, and once again with the grade appended. The second write may only add fields —
`test_journal.py` asserts that the run record itself is byte-identical across the two.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from datetime import datetime, timezone

from harnesses.base import JOURNAL_SCHEMA, Step, TaskRun


def run_id(run: TaskRun, repeat: int) -> str:
    return f"{run.task_id}__{run.harness}__r{repeat}"


def write_journal(dirpath, run: TaskRun, *, repeat: int, manifest_version: str,
                  grade: dict | None = None, final_files: dict | None = None,
                  llm_route: str = "", extra: dict | None = None) -> pathlib.Path:
    d = pathlib.Path(dirpath)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{run_id(run, repeat)}.json"

    body = {
        "schema": JOURNAL_SCHEMA,
        "run_id": run_id(run, repeat),
        "manifest_version": manifest_version,
        "repeat": repeat,
        "llm_route": llm_route,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **dataclasses.asdict(run),
    }
    if extra:
        body.update(extra)
    if grade:
        body.update(grade)
    if final_files is not None:
        body["final_files"] = final_files
    p.write_text(json.dumps(body, indent=1))
    return p


def load_journal(path) -> tuple[TaskRun, bool]:
    d = json.loads(pathlib.Path(path).read_text())
    if d.get("schema") != JOURNAL_SCHEMA:
        raise ValueError(f"unknown journal schema {d.get('schema')!r}; refusing to misread it")
    passed = bool(d.get("actually_passed", False))
    fields = {f.name for f in dataclasses.fields(TaskRun)}
    kw = {k: v for k, v in d.items() if k in fields}
    kw["steps"] = [Step(**s) for s in d.get("steps", [])]
    return TaskRun(**kw), passed
