"""Resuming a grid a flaky endpoint interrupted.

The rule: a completed cell is kept, and a cell the endpoint broke is redone. Keeping
an `llm_error` row would let an infrastructure failure occupy a cell permanently and
be counted, later, as though the agent had been asked the question.
"""
import json
import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parents[1] / "run_grid.py").read_text()


def test_resume_keeps_a_completed_cell():
    assert 'if args.resume and existing.exists():' in SRC
    assert 'kept:' in SRC


def test_resume_redoes_a_cell_the_endpoint_broke():
    assert '{"llm_error", "adapter_error"}' in SRC
    assert 'redoing' in SRC


def test_resume_is_opt_in_so_a_fresh_grid_is_never_contaminated():
    """Without --resume the grid starts from what is on disk and overwrites it. A
    default-on resume would silently blend two manifests' runs into one table."""
    assert '"--resume", action="store_true"' in SRC


def test_the_manifest_decides_which_tasks_run_not_the_tasks_directory():
    """A task file left on disk because an earlier grid was recorded against it must
    not silently join a later grid."""
    assert 'declared = [t["id"] for t in manifest["tasks"]]' in SRC
    i_manifest = SRC.index('manifest = json.loads(pathlib.Path(args.manifest).read_text())')
    i_declared = SRC.index('declared = [t["id"] for t in manifest["tasks"]]')
    assert i_manifest < i_declared, "the manifest is read after it is used"
