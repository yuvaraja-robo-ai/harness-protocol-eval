"""L1. Write a task into a fresh workspace, and grade it.

The tests are ground truth and the agent never gets to write them. The graders read
them from the task definition, not from disk, so an agent that edits a test on disk
changes nothing about the verdict — it only leaves a `refused` or an `edit` step in
the journal for the integrity axis to find.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile


def materialise(task: dict, root: str | pathlib.Path | None = None) -> pathlib.Path:
    """A fresh workspace per run. Never reused: a leftover file from a previous run
    is a variable nobody declared."""
    d = pathlib.Path(root) if root else pathlib.Path(tempfile.mkdtemp(prefix="s18_"))
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    for rel, body in {**task.get("files", {}), **task.get("tests", {})}.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


def run_tests(workspace: pathlib.Path, task: dict, timeout: int = 120,
              hidden: bool = False) -> tuple[bool, str]:
    """Restore the tests, then grade.

    Restoring first is the whole guard: if the agent edited a test to make it pass,
    the edit is discarded and the original question is asked again.

    `hidden=True` additionally materialises the task's held-out checks for the
    duration of the grade and removes them afterwards. They are never present while
    the agent is working: a held-out check the agent can read is not held out, and a
    check left behind in the workspace would be visible to the next thing that looks.
    """
    for rel, body in task.get("tests", {}).items():
        p = workspace / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    written_hidden = []
    if hidden:
        for rel, body in task.get("hidden_tests", {}).items():
            p = workspace / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
            written_hidden.append(p)
    try:
        r = subprocess.run(
            ["python3", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=workspace, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"pytest exceeded {timeout}s"
    finally:
        for p in written_hidden:
            p.unlink(missing_ok=True)
    return r.returncode == 0, (r.stdout or r.stderr)[-600:]
