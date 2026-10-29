"""People on one dashboard: who they are, who is looking at what right now, who saw which thread, who was mentioned.

- Roster: `~/.arx/people.json` (or `$ARX_HOME`), {person id: {name, created, last}}. A browser makes its own id once
  (`p-` + 8 hex, localStorage `arx-me`) and keeps it across projects, tabs and the paper reader; the name is editable
  and every comment carries both (`author` = the name then, `by` = the id).
- Presence: in memory, per project: {person id: {name, route, t}} from the page's heartbeat (POST /api/people every
  20 s). Someone counts as here for 60 s after their last beat.
- Seen: comments.jsonl `seen` events {parent: thread, by}; a thread lists who saw it and when (comments.threads).
- Mentions: `@Name` (or `@first` when the first name is unique) in a message; `mentioned(body, roster)` -> ids.

GET /api/people -> {people: {id: {name, last}}, here: [{id, name, route, t}]}
POST /api/people {id, name, route} -> the same, after recording the beat
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from . import features, projects

HERE_S = 60
ID = re.compile(r"^p-[0-9a-f]{6,16}$")
_presence: dict[str, dict[str, dict]] = {}  # project root -> person id -> {name, route, t}
_lock = threading.Lock()


def _file() -> Path:
    return projects.home() / "people.json"


def roster() -> dict:
    try:
        d = json.loads(_file().read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_name(n) -> str:
    return re.sub(r"\s+", " ", str(n or "")).strip()[:40]


def remember(pid: str, name: str, key: str | None = None, remote: bool = False) -> bool:
    """Add or rename a person, and note the project they were in; written whole through a temp file so a reader
    never sees half a roster. Someone on another machine (a share link) cannot rename a person made on this one."""
    if not ID.match(pid or "") or not name:
        return False
    with _lock:
        r = roster()
        cur = r.get(pid) or {}
        if remote and cur and not cur.get("remote"):
            return False
        t = time.time()
        ps = sorted(set(cur.get("projects") or []) | ({key} if key else set()))
        if cur.get("name") == name and ps == (cur.get("projects") or []) and t - (cur.get("last") or 0) < 300:
            return True  # unchanged: one write per five minutes per person is enough for "last seen"
        aka = [n for n in (cur.get("aka") or []) + ([cur["name"]] if cur.get("name") and cur["name"] != name else []) if n != name][-5:]
        r[pid] = dict(name=name, created=cur.get("created") or t, last=t, projects=ps, **({"aka": aka} if aka else {}),
                      **({"remote": True} if remote or cur.get("remote") else {}))
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(r, indent=1))
        os.replace(tmp, f)
        return True


def members(p) -> dict:
    """The people of one project: those who were in it (older entries, made before projects were noted, count too)."""
    key = projects.key_for(p.root)
    return {k: v for k, v in roster().items() if key in (v.get("projects") or [key])}


def here(p) -> list[dict]:
    t = time.time()
    with _lock:
        room = _presence.get(str(p.root), {})
        for k in [k for k, v in room.items() if t - v["t"] > HERE_S]:
            room.pop(k)
        return sorted(({"id": k, **v} for k, v in room.items()), key=lambda x: -x["t"])


def beat(p, pid: str, name: str, route: str) -> None:
    with _lock:
        _presence.setdefault(str(p.root), {})[pid] = dict(name=name, route=str(route or "")[:300].lstrip("#"), t=time.time())


def mentioned(body: str, people: dict | None = None) -> list[str]:
    """Person ids named with @ in a message: the full name (case-insensitive), or a first name that only one person has."""
    people = roster() if people is None else people
    text = " " + str(body or "").lower()
    out = []
    firsts: dict[str, list[str]] = {}
    for k, v in people.items():
        firsts.setdefault(clean_name(v.get("name")).lower().split(" ")[0], []).append(k)
    fulls: dict[str, int] = {}
    for v in people.values():
        n = clean_name(v.get("name")).lower()
        fulls[n] = fulls.get(n, 0) + 1
    for k, v in people.items():
        n = clean_name(v.get("name")).lower()
        if not n or fulls[n] > 1:
            continue  # two people with one name: an @ cannot say which
        first = n.split(" ")[0]
        end = r"(?![\w-])"  # a name ends where a word or a hyphen ends: @tester-1b is not @tester, and C++ matches
        if re.search(r"[\s(]@" + re.escape(n) + end, text) or (len(firsts.get(first, [])) == 1 and re.search(r"[\s(]@" + re.escape(first) + end, text)):
            out.append(k)
    return out


def view(p) -> dict:
    return dict(people={k: dict(name=v.get("name"), last=v.get("last"), **({"aka": v["aka"]} if v.get("aka") else {}))
                        for k, v in members(p).items()}, here=here(p))


@features.get("/api/people")
def _get(p, path, q):
    return 200, view(p)


@features.post("/api/people")
def _post(p, path, d):
    if not isinstance(d, dict) or not ID.match(str(d.get("id") or "")):
        return 400, dict(error="bad request")
    name = clean_name(d.get("name"))
    if name and remember(d["id"], name, projects.key_for(p.root), remote=bool(d.get("_remote"))):
        beat(p, d["id"], name, d.get("route"))
    return 200, view(p)


@features.STATE.append
def _state(p, st):
    st["here"] = here(p)
