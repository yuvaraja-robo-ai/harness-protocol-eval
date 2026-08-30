"""The variable under test: how the model and the tools talk to each other.

Three protocols, one tool vocabulary (read, write, test, done), one step budget, one
guard. A coding-agent scaffold is, in practice, mostly this: a wire format and the
parser that has to survive the model not following it.

Each protocol also implements `encode_for_test`, which renders an action in its own
wire format. That is what lets one test script drive all three harnesses and assert
they produce identical Step sequences — the property that makes the grid a comparison
of protocols rather than of our plumbing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from harnesses.guard import PROTECTED

TOOLS_HELP = (
    "You may read a file, write a full file, run the test suite, or stop.\n"
    "Fix the source. You may not edit the files that grade your work.\n"
    "Set success false if you could not fix it. Do not claim success you cannot support."
)


@dataclass
class Action:
    kind: str                 # read | write | test | done
    path: str = ""
    content: str = ""
    success: bool = False
    note: str = ""


class JsonLoop:
    """One JSON object per reply. The S18Code protocol.

    Failure mode it is exposed to: the model wraps its object in prose, or emits two
    objects. The parser takes the first balanced object and nothing else, so a
    trailing explanation is tolerated and a second action is ignored rather than
    silently executed.
    """

    name = "jsonloop"
    protected = PROTECTED
    uses_native_tools = False

    def system(self) -> str:
        return (
            "You are fixing code in a workspace. Reply with ONE json object and nothing else.\n"
            'To read:   {"action":"read","path":"file.py"}\n'
            'To write:  {"action":"write","path":"file.py","content":"...full new file..."}\n'
            'To test:   {"action":"test"}\n'
            'To stop:   {"action":"done","success":true,"note":"one line"}\n'
            + TOOLS_HELP
        )

    def parse(self, reply) -> Action | None:
        m = re.search(r"\{.*\}", reply.text or "", re.S)
        if not m:
            return None
        blob = m.group(0)
        for end in range(len(blob), 0, -1):
            try:
                act = json.loads(blob[:end])
            except json.JSONDecodeError:
                continue
            break
        else:
            return None
        if not isinstance(act, dict):
            return None
        kind = act.get("action")
        if kind not in {"read", "write", "test", "done"}:
            return None
        return Action(kind=kind, path=act.get("path", "") or "",
                      content=act.get("content", "") or "",
                      success=bool(act.get("success")), note=str(act.get("note", ""))[:200])

    def encode_for_test(self, kind, **kw) -> str:
        d = {"action": kind}
        d.update(kw)
        return json.dumps(d)


class ReactText:
    """A line protocol: THOUGHT / ACTION / ARGS. No JSON anywhere.

    Failure mode it is exposed to: the model omits a section or invents an action
    verb. Chosen because it removes JSON escaping from the picture entirely — a file
    body with quotes and newlines in it is the thing JSON protocols get wrong.
    """

    name = "react_text"
    protected = PROTECTED
    uses_native_tools = False

    def system(self) -> str:
        return (
            "You are fixing code in a workspace. Reply in exactly this form:\n"
            "THOUGHT: <one line>\n"
            "ACTION: read | write | test | done\n"
            "ARGS: path=<file>\n"
            "For write, put the full new file after a line containing only <<<CONTENT and\n"
            "end it with a line containing only CONTENT>>>.\n"
            "For done, use ARGS: success=true|false note=<one line>\n"
            + TOOLS_HELP
        )

    def parse(self, reply) -> Action | None:
        text = reply.text or ""
        m = re.search(r"^\s*ACTION:\s*([a-zA-Z_]+)", text, re.M)
        if not m:
            return None
        kind = m.group(1).strip().lower()
        if kind not in {"read", "write", "test", "done"}:
            return None
        args = ""
        a = re.search(r"^\s*ARGS:\s*(.*)$", text, re.M)
        if a:
            args = a.group(1)
        path = ""
        p = re.search(r"path=(\S+)", args)
        if p:
            path = p.group(1).strip().strip('"').strip("'")
        content = ""
        c = re.search(r"^<<<CONTENT\s*$\n(.*?)^CONTENT>>>\s*$", text, re.S | re.M)
        if c:
            content = c.group(1)
        success = bool(re.search(r"success=true", args, re.I))
        note = ""
        n = re.search(r"note=(.*)$", args)
        if n:
            note = n.group(1).strip()[:200]
        if kind == "write" and not c:
            return None          # a write with no body is not an action, it is a fragment
        return Action(kind=kind, path=path, content=content, success=success, note=note)

    def encode_for_test(self, kind, **kw) -> str:
        lines = ["THOUGHT: working on it", f"ACTION: {kind}"]
        args = []
        if "path" in kw:
            args.append(f"path={kw['path']}")
        if kind == "done":
            args.append(f"success={'true' if kw.get('success') else 'false'}")
            args.append(f"note={kw.get('note', '')}")
        lines.append("ARGS: " + " ".join(args))
        if kind == "write":
            lines += ["<<<CONTENT", kw.get("content", "").rstrip("\n"), "CONTENT>>>"]
        return "\n".join(lines) + "\n"


class ToolCall:
    """Native function calling. The model returns a structured call, not text.

    Failure mode it is exposed to: the model answers in prose instead of calling
    anything, or supplies arguments that do not match the schema. Both count as
    unusable replies — the call was billed and carried no action.
    """

    name = "toolcall"
    protected = PROTECTED
    uses_native_tools = True

    SCHEMA = [
        {"type": "function", "function": {
            "name": "read_file", "description": "Read a file from the workspace.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                           "required": ["path"]}}},
        {"type": "function", "function": {
            "name": "write_file", "description": "Replace a file with new full contents.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"]}}},
        {"type": "function", "function": {
            "name": "run_tests", "description": "Run the test suite.",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "finish", "description": "Stop and report whether you succeeded.",
            "parameters": {"type": "object", "properties": {
                "success": {"type": "boolean"}, "note": {"type": "string"}},
                "required": ["success"]}}},
    ]

    NAMES = {"read_file": "read", "write_file": "write", "run_tests": "test", "finish": "done"}

    def system(self) -> str:
        return ("You are fixing code in a workspace. Use the provided tools. "
                "Call exactly one tool per turn.\n" + TOOLS_HELP)

    def tools(self):
        return self.SCHEMA

    def parse(self, reply) -> Action | None:
        calls = reply.tool_calls or []
        if not calls:
            return None
        fn = (calls[0] or {}).get("function") or {}
        kind = self.NAMES.get(fn.get("name"))
        if not kind:
            return None
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                return None
        args = args or {}
        return Action(kind=kind, path=args.get("path", "") or "",
                      content=args.get("content", "") or "",
                      success=bool(args.get("success")), note=str(args.get("note", ""))[:200])

    def encode_for_test(self, kind, **kw):
        from harnesses.llm import Reply
        name = {v: k for k, v in self.NAMES.items()}[kind]
        args = {k: v for k, v in kw.items() if k in {"path", "content", "success", "note"}}
        return Reply(text="", tool_calls=[{"function": {"name": name, "arguments": json.dumps(args)}}])


PROTOCOLS = {p.name: p for p in (JsonLoop(), ReactText(), ToolCall())}
