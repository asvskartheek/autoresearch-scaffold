"""Papers: human-readable write-ups of the work, served by the dashboard and reviewed like a shared doc.

A paper lives in `.research/papers/<name>/`: `paper.html` (self-contained, written by the agent), `meta.json`,
`files/` (pages the agent links from a reply: widgets, posters) and `thread.jsonl`, an append-only event log:

  comment  a new thread on a passage (anchor: block, quote, prefix, suffix)
  reply    a message in a thread (parent = thread id); `agent: true` for the agent, `link` when the answer is a page
  seen     the agent picked up a message (parent = message id); the page shows "thinking…"
  resolve / reopen   on a thread
  edit / delete      on one message (target = message id)

People comment from the browser; the agent waits on `arx paper poll` and answers with `arx paper reply`.
`threads()` folds the log into the current state; both the page and the agent read that.
"""
from __future__ import annotations

import secrets, shutil, time
from pathlib import Path

from .core import Project, _append, _jsonl, _read, _write, now

KINDS = ("comment", "reply", "seen", "resolve", "reopen", "edit", "delete")


def pdir(p: Project, name: str) -> Path:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise KeyError(f"bad paper name {name!r}")
    return p.dir / "papers" / name


def names(p: Project) -> list[str]:
    return [d.parent.name for d in sorted((p.dir / "papers").glob("*/paper.html"))]


def papers(p: Project) -> dict:
    out = {}
    for name in names(p):
        d = pdir(p, name)
        ts = threads(thread(p, name))
        out[name] = dict(_read(d / "meta.json", {}), name=name, version=version(p, name),
                         comments=len(ts), open=sum(1 for t in ts if not t["resolved"]),
                         waiting=sum(1 for t in ts if t["waiting"]))
    return out


def version(p: Project, name: str) -> float:
    return (pdir(p, name) / "paper.html").stat().st_mtime


def add(p: Project, name: str, src: Path, title: str = None, hill: str = None) -> Path:
    """Publish or republish a paper. Open pages swap the new version in place."""
    d = pdir(p, name)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".paper.html.tmp"
    shutil.copyfile(src, tmp)
    tmp.replace(d / "paper.html")  # atomic: a page polling mid-write never reads half a paper
    meta = _read(d / "meta.json", {}) | {k: v for k, v in dict(title=title, hill=hill).items() if v}
    meta.setdefault("created", now())
    meta["updated"] = now()
    _write(d / "meta.json", meta)
    return d / "paper.html"


def attach(p: Project, name: str, src: Path) -> str:
    """Copy a page (widget, poster) next to the paper; returns the URL path a reply can link to."""
    if not (pdir(p, name) / "paper.html").exists():
        raise KeyError(f"no paper {name!r}")
    f = pdir(p, name) / "files" / Path(src).name
    f.parent.mkdir(exist_ok=True)
    shutil.copyfile(src, f)
    return f"/papers/{name}/files/{f.name}"


def file(p: Project, name: str, fname: str) -> Path:
    if not fname or "/" in fname or "\\" in fname or fname.startswith("."):
        raise KeyError(f"bad file {fname!r}")
    return pdir(p, name) / "files" / fname


def thread(p: Project, name: str) -> list[dict]:
    return _jsonl(pdir(p, name) / "thread.jsonl")


def post(p: Project, name: str, kind: str, **fields) -> dict:
    if kind not in KINDS:
        raise ValueError(f"bad kind {kind!r}")
    if not (pdir(p, name) / "paper.html").exists():
        raise KeyError(f"no paper {name!r}")
    ev = dict(id=secrets.token_hex(4), t=now(), kind=kind, **{k: v for k, v in fields.items() if v is not None})
    _append(pdir(p, name) / "thread.jsonl", ev)
    return ev


def threads(log: list[dict]) -> list[dict]:
    """Fold the event log into threads, oldest first. Each has its messages (edits applied, deletes dropped),
    `resolved`, `waiting` (the last message is from a person: the agent owes an answer) and `thinking`
    (the agent has seen that message)."""
    out, msgs = {}, {}
    for e in log:
        k = e["kind"]
        if k == "comment":
            m = dict(id=e["id"], t=e["t"], author=e.get("author") or "you", body=e.get("body", ""), agent=False)
            out[e["id"]] = dict(id=e["id"], t=e["t"], anchor=e.get("anchor"), resolved=False, resolved_by=None,
                                messages=[m], seen=set())
            msgs[e["id"]] = m
        elif k == "reply" and e.get("parent") in out:
            m = dict(id=e["id"], t=e["t"], author=e.get("author") or ("agent" if e.get("agent") else "you"),
                     body=e.get("body") or "", agent=bool(e.get("agent")), link=e.get("link"))
            out[e["parent"]]["messages"].append(m)
            msgs[e["id"]] = m
        elif k in ("resolve", "reopen") and e.get("parent") in out:
            th = out[e["parent"]]
            th["resolved"], th["resolved_by"] = k == "resolve", e.get("author") if k == "resolve" else None
            if e.get("body") and k == "resolve":  # the agent may resolve with a closing note
                m = dict(id=e["id"], t=e["t"], author=e.get("author") or "agent", body=e["body"],
                         agent=bool(e.get("agent")), link=e.get("link"))
                th["messages"].append(m)
        elif k == "edit" and e.get("target") in msgs:
            msgs[e["target"]].update(body=e.get("body") or "", edited=e["t"])
        elif k == "delete" and e.get("target") in msgs:
            msgs[e["target"]]["deleted"] = True
        elif k == "seen":
            for th in out.values():
                if any(m["id"] == e.get("parent") for m in th["messages"]):
                    th["seen"].add(e["parent"])
    res = []
    for th in out.values():
        root_gone = th["messages"][0].get("deleted")
        th["messages"] = [m for m in th["messages"] if not m.get("deleted")]
        if root_gone and not any(m for m in th["messages"]):
            continue
        if root_gone:  # replies outlive a deleted first comment; the thread keeps its anchor
            th["root_deleted"] = True
        last = th["messages"][-1] if th["messages"] else None
        th["waiting"] = bool(last and not last["agent"] and not th["resolved"])
        th["thinking"] = bool(th["waiting"] and last["id"] in th["seen"])
        th["last"] = last["id"] if last else None
        th.pop("seen")
        res.append(th)
    return res


def pending(log: list[dict]) -> list[dict]:
    """Threads where the agent owes an answer, oldest first."""
    return [t for t in threads(log) if t["waiting"]]


def poll(p: Project, name: str = None, timeout: float = None, interval: float = 1.0) -> list[dict]:
    """Block until some thread is waiting on the agent (one paper, or all of them); mark the newest message of each
    as seen so the page shows "thinking…", and return the threads with `paper` set."""
    end = None if timeout is None else time.time() + timeout
    while True:
        out = []
        for n in ([name] if name else names(p)):
            for th in pending(thread(p, n)):
                if not th["thinking"]:
                    post(p, n, "seen", parent=th["last"])
                out.append(dict(th, paper=n))
        if out:
            return out
        if end is not None and time.time() >= end:
            return []
        time.sleep(interval)
