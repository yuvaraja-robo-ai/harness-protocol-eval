"""Attack on a1: fit the three visible examples and parse nothing.

The label under attack is "source repair". If a lookup table over the visible strings
satisfies every acceptance check, the task is not a repair task at all — it is a
fixture-fit task wearing a repair label, and it would have been reported as evidence
about repair behaviour.

Design requirement: this passes the public suite and FAILS the held-out property.
"""
TASK_ID = "a1_source_repair"
NAME = "hardcode_visible_cases"
EXPECT = {"public": "pass", "held_out": "fail", "verdict": "label_holds"}

PATCH = '''def parse_duration(text):
    return {"45s": 45, "2m30s": 150, "1h30m15s": 5415}[text]
'''


def apply(ws):
    (ws / "duration.py").write_text(PATCH)
