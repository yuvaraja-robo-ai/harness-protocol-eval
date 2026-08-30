"""L2 dependency. One seam, two routes, real token counts.

Everything above this line sees `Reply`. Nothing above this line knows whether the
call went to Ollama directly or through the GLC gateway, which is what lets the cost
field be upgraded without touching a harness.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

#: Read at call time, not at import time: run_grid.py sets them from the manifest it
#: was given, and a module-level snapshot would silently keep the default.
def ollama_url() -> str:
    return os.getenv("S18_OLLAMA_URL", "http://192.168.32.2:11434")


def glc_url() -> str:
    return os.getenv("S18_GLC_URL", "http://127.0.0.1:8111")


def model_id() -> str:
    return os.getenv("S18_MODEL", "qwen3.8:latest")


def timeout_s() -> int:
    """Generous on purpose.

    Measured 2026-08-29: the 27B model is resident with only 4.5 GB of 18.3 GB in
    VRAM, so most of it runs on CPU and a single call can take many minutes. At the
    original 600 s ceiling one call in a3 timed out after the agent had already read,
    edited, verified and been refused a protected write — seven steps of real evidence
    discarded because the harness gave up on the eighth call. The timeout is a property
    of our impatience, not of the agent, and it must not be recorded as one.
    """
    return int(os.getenv("S18_TIMEOUT", "1800"))


MODEL = model_id()


@dataclass
class Reply:
    """One model reply, with its real usage.

    `input_tokens` and `output_tokens` come from the provider's usage block. When a
    route cannot supply them they stay 0 and the journal says 0 — a `len(text)//4`
    estimate is not a token count and must never be published beside one.
    """

    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    #: How many transport retries this one reply cost.
    retries: int = 0
    raw: dict = field(default_factory=dict)


#: A transient loss of the endpoint is not an agent outcome.
#:
#: Measured 2026-08-29: the model host is on wifi and leaves the network when it
#: sleeps. Twice this killed a run mid-flight with `URLError Errno 113`, and the
#: second time it discarded seven steps of real behaviour including a correct refusal.
#: Waiting is the honest response — the agent did nothing wrong and neither did the
#: task. What is NOT honest is retrying an error the provider actually returned, so
#: only transport failures are retried; an HTTP error from a reachable server is
#: raised immediately.
RETRY_ATTEMPTS = int(os.getenv("S18_RETRIES", "10"))
RETRY_WAIT_S = int(os.getenv("S18_RETRY_WAIT", "30"))
#: How long to spend deciding whether the host is there at all.
REACH_TIMEOUT_S = float(os.getenv("S18_REACH_TIMEOUT", "5"))

TRANSPORT_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, OSError)


class TransportExhausted(Exception):
    """The endpoint never came back within the retry budget.

    Carries the attempt count so the journal can record what the wait cost. The first
    version of the retry loop recorded retries only on success, so a run that spent
    2.9 hours waiting for a sleeping host wrote `llm_retries: 0` and `seconds: 10292`
    — a wait that expensive being invisible in the record is the same class of error
    as an infrastructure failure scored as an agent outcome.
    """

    def __init__(self, cause: Exception, attempts: int, waited_s: float):
        super().__init__(f"{type(cause).__name__}: {cause} after {attempts} attempts "
                         f"over {waited_s:.0f}s")
        self.cause, self.attempts, self.waited_s = cause, attempts, waited_s


def _reachable(url: str, timeout: float = REACH_TIMEOUT_S) -> bool:
    """Cheap TCP probe before committing to a long read timeout.

    Without this, a host that blackholes packets consumes the full call timeout per
    attempt: one run spent 10292 seconds discovering that a sleeping laptop was
    asleep. The probe answers the same question in five.
    """
    parsed = urllib.parse.urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def _post(url: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _post_with_retry(url: str, body: dict, timeout: int) -> tuple[dict, int]:
    """Returns the response and how many retries it took to get it.

    The retry count is carried into the journal rather than swallowed: a run that
    needed eleven attempts to reach the endpoint had a different wall clock from one
    that needed none, and `seconds` is one of the four reported fields.
    """
    last: Exception | None = None
    started = time.time()
    for attempt in range(RETRY_ATTEMPTS):
        if not _reachable(url):
            last = ConnectionError(f"endpoint unreachable: {url}")
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_WAIT_S)
            continue
        try:
            return _post(url, body, timeout), attempt
        except urllib.error.HTTPError:
            raise                      # the server answered; that is a real result
        except TRANSPORT_ERRORS as e:  # noqa: PERF203
            last = e
            if attempt == RETRY_ATTEMPTS - 1:
                break
            time.sleep(RETRY_WAIT_S)
    raise TransportExhausted(last or ConnectionError(url), RETRY_ATTEMPTS,
                             time.time() - started)


class OllamaLLM:
    """Direct to the OpenAI-compatible endpoint. No second service required."""

    route = "ollama"

    def __init__(self, model: str | None = None, temperature: float = 0.2,
                 max_tokens: int = 1200, timeout: int | None = None):
        self.model, self.temperature = model or model_id(), temperature
        self.max_tokens, self.timeout = max_tokens, timeout or timeout_s()

    async def __call__(self, messages, system, tools=None) -> Reply:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        d, retries = await asyncio.to_thread(
            _post_with_retry, f"{ollama_url()}/v1/chat/completions", body, self.timeout)
        choice = (d.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = d.get("usage") or {}
        return Reply(
            text=msg.get("content") or "",
            tool_calls=msg.get("tool_calls") or [],
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            usd=0.0,
            retries=retries,
            raw=d,
        )


class GlcLLM:
    """Through the gateway, which owns pricing and writes one ledger row per call.

    `session` is tagged with the run id, so `/v1/cost/by_principal` gives a per-run
    cost rollup this harness did not compute for itself — an independent record of
    the same calls. The semantic cache is left OFF deliberately: a cached reply
    shared between two runs of the grid would make the repeats not repeats.
    """

    route = "glc"

    def __init__(self, model: str | None = None, temperature: float = 0.2,
                 max_tokens: int = 1200, timeout: int | None = None,
                 session: str = "", agent: str = "s18-eval"):
        self.model, self.temperature = model or model_id(), temperature
        self.max_tokens, self.timeout = max_tokens, timeout or timeout_s()
        self.session, self.agent = session, agent

    async def __call__(self, messages, system, tools=None) -> Reply:
        body = {
            "messages": messages,
            "system": system,
            "provider": "ollama",
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "semantic_cache": False,
            "agent": self.agent,
            "session": self.session,
        }
        if tools:
            body["tools"] = tools
        d, retries = await asyncio.to_thread(
            _post_with_retry, f"{glc_url()}/v1/chat", body, self.timeout)
        cost = d.get("cost") or {}
        return Reply(
            text=d.get("text") or "",
            tool_calls=d.get("tool_calls") or [],
            input_tokens=int(d.get("input_tokens") or 0),
            output_tokens=int(d.get("output_tokens") or 0),
            usd=float(cost.get("usd") or 0.0),
            retries=retries,
            raw=d,
        )


def build_llm(session: str = "") -> object:
    """`S18_LLM=glc` routes through the gateway; anything else goes direct."""
    if os.getenv("S18_LLM", "ollama").lower() == "glc":
        return GlcLLM(session=session)
    return OllamaLLM()
