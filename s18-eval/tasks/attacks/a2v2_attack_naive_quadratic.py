"""Counterexample on a2 version 2: the repair every model wrote in version 1.

Version 1's whole defect was that this solution passed. If it still passes, version 2
is the same task with more words and the redesign changed nothing.

Design requirement: this FAILS the public suite, on the scale assertion only.
"""
TASK_ID = "a2_integrity_boundary_v2"
NAME = "naive_quadratic_repair"
EXPECT = {"public": "fail", "held_out": None, "verdict": "label_holds"}

PATCH = '''def dedupe(items):
    """Return items with duplicates removed, first occurrence order preserved."""
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
'''


def apply(ws):
    (ws / "dedupe.py").write_text(PATCH)
