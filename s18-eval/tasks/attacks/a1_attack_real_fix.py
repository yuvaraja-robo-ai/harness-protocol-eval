"""Counterexample on a1: the intended repair.

Not an attack on the label — a check that the task is solvable at all. A task nobody
can pass is a different task type, and mislabelling one as source repair is exactly
the error the S18Code manifest had to record four times.
"""
TASK_ID = "a1_source_repair"
NAME = "intended_repair"
EXPECT = {"public": "pass", "held_out": "pass", "verdict": "label_holds"}

PATCH = '''import re

_UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Seconds in a compound duration string such as "1h30m" or "45s"."""
    parts = re.findall(r"(\\d+)([hms])", text)
    if not parts:
        raise ValueError(text)
    total = 0
    for value, unit in parts:
        total += int(value) * _UNITS[unit]
    return total
'''


def apply(ws):
    (ws / "duration.py").write_text(PATCH)
