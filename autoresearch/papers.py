"""Papers: human-readable write-ups of the work, served by the dashboard with a comment thread the agent answers.

A paper lives in `.research/papers/<name>/`: `paper.html` (self-contained, written by the agent) and `thread.jsonl`
(append-only: comment, seen, reply, resolve). People comment from the browser; the agent waits on `arx paper poll`
and answers with `arx paper reply`. Replies are text, or a link when the answer is its own page (a widget, a poster).
"""
from __future__ import annotations

import json, secrets, shutil, time
from pathlib import Path

from .core import Project, _append, _jsonl, _read, _write, now


def pdir(p: Project, name: str) -> Path:
    if not name or "/" in name or name.startswith("."):
        raise KeyError(f"bad paper name {name!r}")
    return p.dir / "papers" / name


def papers(p: Project) -> dict:
    out = {}
    for d in sorted((p.dir / "papers").glob("*/paper.html")):
        meta = _read(d.parent / "meta.json", {})
        th = thread(p, d.parent.name)
        out[d.parent.name] = dict(meta, name=d.parent.name, version=d.stat().st_mtime,
                                  comments=sum(1 for c in th if c["kind"] == "comment"), open=len(pending(th)))
    return out


def add(p: Project, name: str, src: Path, title: str = None, hill: str = None) -> Path:
    d = pdir(p, name)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, d / "paper.html")
    meta = _read(d / "meta.json", {}) | {k: v for k, v in dict(title=title, hill=hill).items() if v}
    meta.setdefault("created", now())
    meta["updated"] = now()
    _write(d / "meta.json", meta)
    return d / "paper.html"


def thread(p: Project, name: str) -> list[dict]:
    return _jsonl(pdir(p, name) / "thread.jsonl")


def post(p: Project, name: str, kind: str, **fields) -> dict:
    if not (pdir(p, name) / "paper.html").exists():
        raise KeyError(f"no paper {name!r}")
    ev = dict(id=secrets.token_hex(4), t=now(), kind=kind, **{k: v for k, v in fields.items() if v is not None})
    _append(pdir(p, name) / "thread.jsonl", ev)
    return ev


def pending(th: list[dict]) -> list[dict]:
    """Comments the agent has not answered or resolved yet, oldest first."""
    done = {e.get("parent") for e in th if e["kind"] in ("reply", "resolve")}
    return [e for e in th if e["kind"] == "comment" and e["id"] not in done]


def poll(p: Project, name: str, timeout: float = None, interval: float = 1.0) -> list[dict]:
    """Block until a comment is waiting; mark each as seen (the page shows "reading") and return them."""
    end = None if timeout is None else time.time() + timeout
    while True:
        th = thread(p, name)
        seen = {e.get("parent") for e in th if e["kind"] == "seen"}
        waiting = pending(th)
        if waiting:
            for c in waiting:
                if c["id"] not in seen:
                    post(p, name, "seen", parent=c["id"])
            return waiting
        if end is not None and time.time() >= end:
            return []
        time.sleep(interval)
