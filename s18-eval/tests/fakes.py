"""A scripted model. No test in this suite touches the network.

`ScriptedLLM` raises when the loop asks for more replies than the script holds, so a
harness that spins forever fails loudly instead of hanging a CI run.
"""
from __future__ import annotations

from harnesses.llm import Reply


class ScriptedLLM:
    def __init__(self, replies: list[Reply | str]):
        self.script = [r if isinstance(r, Reply) else Reply(text=r) for r in replies]
        self.seen: list[dict] = []

    async def __call__(self, messages, system, tools=None):
        self.seen.append({"messages": messages, "system": system, "tools": tools})
        if not self.script:
            raise AssertionError("harness asked for more replies than the script holds")
        return self.script.pop(0)


class ExplodingLLM:
    """Every call fails. Stands in for the quota-exhausted provider."""

    def __init__(self, exc=RuntimeError("HTTPError 429")):
        self.exc = exc
        self.calls = 0

    async def __call__(self, messages, system, tools=None):
        self.calls += 1
        raise self.exc
