"""Feature plug-ins: each feature module registers its API routes, CLI commands and state keys here, so features live
in their own files and server.py / cli.py stay small. Also the inbox: work a person asks for (a comment, a goal in their
own words, a question to investigate) that `arx answer` hands to an agent.

Contracts
- GET / POST: (prefix, fn). fn(project, path, query_or_body) -> (status, payload). A dict/list payload is sent as JSON;
  bytes are sent as-is with the type in the third tuple item: (200, b"...", "text/html; charset=utf-8").
- STATE: fn(project, state_dict) adds keys to /api/state. Keep it cheap: the dashboard polls every 4 s.
- CLI: fn(subparsers) adds `arx <command>` parsers (set_defaults(fn=...)).
- PROMPTS[kind]: fn(project, item) -> the prompt an agent gets for an inbox item of that kind.
"""
from __future__ import annotations

import importlib
import json
import os
import shlex
import time
import uuid

GET: list = []
POST: list = []
STATE: list = []
CLI: list = []
PROMPTS: dict = {}

MODULES = ("people", "questions", "comments", "learn", "reference", "intake", "vitals", "answer")


def load() -> None:
    """Import every feature module once; a module that fails to import is skipped, never breaks the dashboard."""
    for m in MODULES:
        try:
            importlib.import_module(f"{__package__}.{m}")
        except ImportError:
            pass


def get(prefix):
    def deco(fn):
        GET.append((prefix, fn))
        return fn
    return deco


def post(prefix):
    def deco(fn):
        POST.append((prefix, fn))
        return fn
    return deco


# ---------- inbox: append-only, one line per event; the latest event for an id wins
def _inbox(p):
    return p.dir / "inbox.jsonl"


def enqueue(p, kind: str, payload: dict, ref: str | None = None) -> dict:
    """Ask for agent work. `ref` points at what it is about (a comment id, a question id); returns the item."""
    item = dict(id="ib-" + uuid.uuid4().hex[:10], kind=kind, ref=ref, payload=payload, status="queued", t=time.time())
    with open(_inbox(p), "a") as f:
        f.write(json.dumps(item) + "\n")
    return item


def update(p, item_id: str, **fields) -> None:
    """Move an item along: status queued -> running -> done | failed, with task=<arx task id>, result=..., error=..."""
    with open(_inbox(p), "a") as f:
        f.write(json.dumps(dict(id=item_id, t=time.time(), **fields)) + "\n")


def inbox(p) -> list[dict]:
    """Every item, its events merged in order."""
    items: dict[str, dict] = {}
    f = _inbox(p)
    if not f.exists():
        return []
    for line in f.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue  # a writer may be mid-line
        items.setdefault(e["id"], {}).update({k: v for k, v in e.items() if v is not None})
    return sorted(items.values(), key=lambda i: i.get("t", 0))


def pending(p) -> list[dict]:
    """Queued items whose time has come (`not_before`: an agent's usage limit resets then)."""
    t = time.time()
    return [i for i in inbox(p) if i.get("status") == "queued" and (i.get("not_before") or 0) <= t]


def model_label(p, name: str | None) -> str:
    """How a model reads to a person: its title, else a long `a+b+c+d+e` id cut to its last two changes (`…+d+e`)."""
    t = ((p.models().get(name) or {}).get("title") if name else None) or name or ""
    if t == name and t.count("+") >= 3:
        t = "…+" + "+".join(t.split("+")[-2:])
    return t


def agent_cmd() -> list[str]:
    """The headless agent each inbox item gets. Override with ARX_AGENT_CMD, e.g. "claude -p --model claude-sonnet-5-5"."""
    return shlex.split(os.environ.get("ARX_AGENT_CMD") or "claude -p --permission-mode acceptEdits")
