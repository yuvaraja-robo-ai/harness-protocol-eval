"""L0 contracts. Dataclasses only, no behaviour.

Three harnesses produce one shape, and the scorers never learn which one produced a
run. That is the entire reason the comparison can be attributed to the protocol: the
moment a harness gets a bespoke record, the result measures our plumbing instead of
their scaffold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

JOURNAL_SCHEMA = "s18-journal/1"

#: How a run stopped. A scorer that cannot tell these apart will score a run that
#: exhausted its budget identically to one that answered "I could not do this", and
#: those are different events with different meanings.
ENDINGS = frozenset({
    "done",           # the agent emitted a final answer
    "ceiling",        # the repeat-failure ceiling fired
    "max_steps",      # the step budget ran out mid-work
    "llm_error",      # the model call failed; nothing about the agent was measured
    "adapter_error",  # the harness itself broke; likewise
})


@dataclass
class Step:
    """One action that actually happened, whatever the harness calls it internally."""

    kind: str            # read | edit | create | command | answer | refused
    target: str = ""     # a path, or the command string
    ok: bool = True
    detail: str = ""


@dataclass
class TaskRun:
    """What every harness must produce, and all the scorers ever see.

    Deliberately absent: whether the task actually passed. That is the grader's
    field, computed from the task's own restored tests and attached at the journal
    layer. Keeping the agent's claim and the truth in separate places is the point —
    their disagreement is the false_success axis, and it is the number we came for.
    """

    task_id: str
    harness: str
    model: str
    steps: list[Step] = field(default_factory=list)

    #: What the agent SAID about its own work.
    claimed_success: bool = False

    #: One of ENDINGS. Empty only while the run is still in progress.
    ended: str = ""

    #: Cost, as four separate observations. There is no single `tokens` field on
    #: purpose: the S18Code record carried one that was `len(reply)//4`, saw neither
    #: the prompt nor the reasoning channel, and was reported next to real figures.
    #: Real counts come from the provider's usage block; if a route cannot supply
    #: them they stay 0 and the run says so rather than substituting an estimate.
    seconds: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    #: Billing honesty. A reply is unusable when it came back with no parseable
    #: action in it — on a reasoning model that is a fully billed non-answer, and no
    #: public benchmark counts it. Kept as a count, not a flag: one bad reply in
    #: twelve is not the same defect as twelve out of twelve.
    unusable_replies: int = 0

    #: Transport retries spent waiting for a flaky endpoint. Not an agent property —
    #: recorded so that a long `seconds` figure can be read correctly rather than
    #: mistaken for a slow agent.
    llm_retries: int = 0

    #: Every attempt to write something that grades the work, refused or not.
    protected_write_attempts: list[dict] = field(default_factory=list)

    error: str = ""
