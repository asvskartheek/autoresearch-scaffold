"""The ledger: an append-only event log per project, folded into state on read."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

HOME = Path(os.environ.get("ARX2_HOME", Path.home() / ".arx2"))
DIR = ".arx2"

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9'&.\-]*( [A-Za-z0-9'&.\-]+)?$")


class LedgerError(Exception):
    """An error the agent can fix; `fix` names the command that fixes it."""

    def __init__(self, msg: str, fix: str | None = None):
        super().__init__(msg)
        self.fix = fix


def check_name(name: str, what: str = "name") -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name) or len(name) > 24:
        raise LedgerError(
            f"{what} {name!r} must be one or two plain words (no + / _ or digits-only codes), at most 24 characters",
            fix=f'pass a name a person remembers, e.g. --name "Route Tracing"',
        )
    return name


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "x"


def ids_hash(ids) -> str:
    """Order-free fingerprint of an id list (same recipe as arx v1, so old and new fingerprints agree)."""
    return hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()[:10]


def find_root(start: Path | None = None) -> Path:
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / DIR).is_dir():
            return d
    raise LedgerError(f"no {DIR}/ ledger in {p} or its parents", fix='arx2 init --name "<two words>" --task "<what the model does>"')


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / DIR
        self.events_path = self.dir / "events.jsonl"

    # ---- writing -------------------------------------------------------
    def append(self, type_: str, actor: str = "agent", t: float | None = None, **data) -> dict:
        ev = {"t": t if t is not None else time.time(), "type": type_, "actor": actor, **data}
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.events_path, "a") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def append_rows(self, run: str, rows: list[dict]) -> None:
        p = self.dir / "rows" / f"{run}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def append_metric(self, task: str, point: dict) -> None:
        p = self.dir / "metrics" / f"{task}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(point) + "\n")

    def learner(self, ev: dict) -> None:
        with open(self.dir / "learner.jsonl", "a") as f:
            f.write(json.dumps(ev) + "\n")

    # ---- reading -------------------------------------------------------
    def events(self) -> list[dict]:
        if not self.events_path.exists():
            return []
        with open(self.events_path) as f:
            return [json.loads(l) for l in f if l.strip()]

    def rows(self, run: str) -> list[dict]:
        p = self.dir / "rows" / f"{run}.jsonl"
        if not p.exists():
            return []
        with open(p) as f:
            return [json.loads(l) for l in f if l.strip()]

    def metrics(self, task: str) -> list[dict]:
        p = self.dir / "metrics" / f"{task}.jsonl"
        if not p.exists():
            return []
        with open(p) as f:
            return [json.loads(l) for l in f if l.strip()]

    def learner_events(self) -> list[dict]:
        p = self.dir / "learner.jsonl"
        if not p.exists():
            return []
        with open(p) as f:
            return [json.loads(l) for l in f if l.strip()]

    def state(self, until: float | None = None) -> dict:
        return fold(self.events(), until)

    def mtime(self) -> float:
        newest = 0.0
        for p in (self.events_path, self.dir / "rows", self.dir / "metrics"):
            if p.exists():
                newest = max(newest, p.stat().st_mtime)
                if p.is_dir():
                    for c in p.iterdir():
                        newest = max(newest, c.stat().st_mtime)
        return newest


def empty_state() -> dict:
    return {
        "project": {}, "sets": {}, "goals": {}, "annotations": [], "patterns": {}, "hills": {},
        "ladders": {}, "candidates": {}, "champion": None, "champions": [], "tasks": {}, "runs": {},
        "docs": {}, "cards": {}, "asks": {}, "agents": {}, "log": [],
    }


def fold(events: list[dict], until: float | None = None) -> dict:
    s = empty_state()
    for ev in events:
        if until is not None and ev["t"] > until:
            break
        apply(s, ev)
    return s


def _body(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if k not in ("type", "actor")}


def apply(s: dict, ev: dict) -> None:
    ty, t = ev["type"], ev["t"]
    d = _body(ev)
    if ty == "project":
        s["project"].update({k: v for k, v in d.items() if k != "t"})
        s["project"].setdefault("created", t)
    elif ty == "set":
        s["sets"][d["key"]] = {**d, "created": t}
    elif ty == "goal":
        s["goals"][d["key"]] = {"status": "open", **d, "created": t, "history": []}
    elif ty == "goal.status":
        g = s["goals"][d["key"]]
        g["status"] = d["status"]
        g["history"].append(d)
    elif ty == "annotation":
        s["annotations"].append(d)
    elif ty == "pattern":
        s["patterns"][d["key"]] = {**s["patterns"].get(d["key"], {}), **d}
    elif ty == "hill":
        s["hills"][d["key"]] = {"status": "open", **d, "created": t}
    elif ty == "hill.status":
        s["hills"][d["key"]].update({k: v for k, v in d.items() if k != "key"})
    elif ty == "ladder":
        s["ladders"][d["key"]] = d
    elif ty == "candidate":
        s["candidates"][d["key"]] = {"status": "trying", **d, "created": t}
    elif ty == "candidate.status":
        s["candidates"][d["key"]].update({k: v for k, v in d.items() if k != "key"})
    elif ty == "champion":
        prev = s["champion"]
        if prev and prev != d["key"] and prev in s["candidates"]:
            s["candidates"][prev]["status"] = "retired"
        s["champion"] = d["key"]
        s["champions"].append(d)
        if d["key"] in s["candidates"]:
            s["candidates"][d["key"]]["status"] = "champion"
    elif ty == "task.start":
        s["tasks"][d["id"]] = {"status": "running", "notes": [], "links": {}, "done": 0, **d,
                               "started": t, "beat": t}
    elif ty in ("task.note", "task.progress", "task.link", "task.end"):
        task = s["tasks"].get(d["id"])
        if task is None:
            return
        task["beat"] = t
        if ty == "task.note":
            task["notes"].append({"t": t, "text": d["text"]})
        elif ty == "task.progress":
            task["done"] = d.get("done", task["done"])
            if "total" in d:
                task["total"] = d["total"]
        elif ty == "task.link":
            task["links"][d["label"]] = d["url"]
        else:
            task["status"] = d.get("status", "done")
            task["ended"] = t
            if d.get("result"):
                task["result"] = d["result"]
    elif ty == "run":
        s["runs"][d["key"]] = {**d, "created": t}
    elif ty == "doc":
        s["docs"][d["key"]] = {**s["docs"].get(d["key"], {}), **d, "updated": t}
        _saved(s, d, d.get("kind"))
    elif ty == "card":
        s["cards"][d["key"]] = d
        _saved(s, d, "card")
    elif ty == "ask":
        s["asks"][d["key"]] = {"status": "open", **d, "created": t, "answers": [], "saved": [],
                               "thread": [{"who": "person", "t": t, "text": d["text"]}]}
    elif ty == "ask.reply":
        a = s["asks"].get(d["key"])
        if a:
            a["thread"].append({"who": "person", "t": t, "text": d["text"]})
            a["status"] = "open"
    elif ty in ("ask.claim", "ask.release"):
        if d.get("agent"):
            s["agents"][d["agent"]] = t
        a = s["asks"].get(d["key"])
        if a and a["status"] != "answered":
            a["status"] = "claimed" if ty == "ask.claim" else "open"
            a["claimed"], a["agent"] = t, d.get("agent")
    elif ty == "answer":
        if d.get("agent"):
            s["agents"][d["agent"]] = t
        a = s["asks"].get(d["key"])
        if a:
            a["answers"].append({"t": t, "parts": d["parts"], "agent": d.get("agent")})
            a["thread"].append({"who": "agent", "t": t, "parts": d["parts"], "agent": d.get("agent")})
            a["status"] = "answered"
    s["log"].append(ev)


def _saved(s: dict, d: dict, kind) -> None:
    """A doc or card saved from an answer is listed on the question it came from."""
    a = s["asks"].get(d.get("ask") or "")
    if a and not any(x["key"] == d["key"] for x in a["saved"]):
        a["saved"].append({"as": kind, "key": d["key"]})


# ---- registry ----------------------------------------------------------

def registry() -> dict:
    p = HOME / "projects.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def register(key: str, root: Path) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    reg = registry()
    reg[key] = {"root": str(Path(root).resolve())}
    (HOME / "projects.json").write_text(json.dumps(reg, indent=2))
