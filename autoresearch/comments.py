"""Comments on any dashboard view, answered by an agent (see features.py for the plug-in contracts).

`.research/comments.jsonl` is an append-only event log, one JSON object per line:

  comment  a new thread: anchor = {route, key, rel, sel, text, quote, rx, ry, px, py, vw, shape}
  reply    a message in a thread (parent = thread id); `agent: true` for the agent, `error: true` when it failed
  resolve / reopen   on a thread (parent)
  edit / delete      on one message (target)
  seen               a person read the thread as it stood (parent, by = person id; see people.py)

Every event a person makes carries `author` (their name then) and `by` (their person id, people.py).

`route` is the view's location.hash without '#', so a comment stays on its view. `key` names a stable element
(an id, a data-* attribute, or the card holding one entity link such as #task/<id>); `rel` is the path from it.
`shape` is a drawn comment: {tool: box|arrow|pen|highlight, d (SVG path in px from the anchor's top-left), bw, bh,
fit, ox, oy}. Every person's comment or reply enqueues an inbox item kind="comment" (ref = thread id); `arx answer`
hands it to an agent, which posts back with `arx comment reply <thread> "..."`.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path

from . import features, people
from .core import Project, _jsonl, now

KINDS = ("comment", "reply", "resolve", "reopen", "edit", "delete", "seen")
MAX_BODY = 20_000


def _log(p: Project) -> Path:
    return p.dir / "comments.jsonl"


def events(p: Project) -> list[dict]:
    """The log; a hand-edited or foreign line is dropped, never allowed to take the dashboard down."""
    return [e for e in _jsonl(_log(p)) if isinstance(e, dict) and isinstance(e.get("id"), str) and e.get("kind") in KINDS]


def post(p: Project, kind: str, **fields) -> dict:
    if kind not in KINDS:
        raise ValueError(f"bad kind {kind!r}")
    ev = dict(id=("cm-" if kind == "comment" else "") + secrets.token_hex(4), t=now(), kind=kind,
              **{k: v for k, v in fields.items() if v is not None})
    p.dir.mkdir(parents=True, exist_ok=True)
    # one write(2) on an O_APPEND fd: the page, the daemon and `arx comment reply` never interleave a line
    fd = os.open(_log(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(ev, default=str) + "\n").encode())
    finally:
        os.close(fd)
    return ev


def threads(log: list[dict]) -> list[dict]:
    """Fold the log into threads, oldest first: messages (edits applied, deletes dropped), resolved, waiting (the last
    message is a person's: the agent owes an answer)."""
    out, msgs, owner = {}, {}, {}
    for e in log:
        k, t = e.get("kind"), e.get("t") or 0
        if k == "comment":
            m = dict(id=e["id"], t=t, author=e.get("author") or "you", body=str(e.get("body") or ""), agent=False, by=e.get("by"), mentions=e.get("mentions") or [])
            out[e["id"]] = dict(id=e["id"], t=t, anchor=e.get("anchor") or {}, resolved=False, messages=[m], seen={})
            msgs[e["id"]] = m; owner[e["id"]] = e["id"]
        elif k == "reply" and e.get("parent") in out:
            m = dict(id=e["id"], t=t, author=e.get("author") or ("agent" if e.get("agent") else "you"),
                     body=str(e.get("body") or ""), agent=bool(e.get("agent")), error=bool(e.get("error")), by=e.get("by"), mentions=e.get("mentions") or [])
            out[e["parent"]]["messages"].append(m)
            msgs[e["id"]] = m; owner[e["id"]] = e["parent"]
        elif k in ("resolve", "reopen") and e.get("parent") in out:
            out[e["parent"]]["resolved"] = k == "resolve"
            out[e["parent"]]["resolved_by"] = e.get("author") if k == "resolve" else None
        elif k == "seen" and e.get("parent") in out and e.get("by"):
            out[e["parent"]]["seen"][e["by"]] = t
        elif k == "edit" and e.get("target") in msgs:
            msgs[e["target"]].update(body=str(e.get("body") or ""), edited=t)
        elif k == "delete" and e.get("target") in msgs:
            msgs[e["target"]]["deleted"] = True
    res = []
    for th in out.values():
        if th["messages"][0].get("deleted"):  # deleting the first comment removes the thread
            continue
        th["messages"] = [m for m in th["messages"] if not m.get("deleted")]
        last = th["messages"][-1]
        th["route"] = (th["anchor"] or {}).get("route") or "overview"
        th["waiting"] = not last["agent"] and not th["resolved"]
        th["last"] = last["id"]
        th["last_t"] = last["t"]
        th["people"] = sorted({m["by"] for m in th["messages"] if m.get("by")})
        th["mentions"] = sorted({x for m in th["messages"] for x in m.get("mentions") or []})
        # a message that names people and not @agent is people talking: the agent does not owe an answer
        th["waiting"] = th["waiting"] and not for_people(last)
        res.append(th)
    return res


def for_people(m: dict) -> bool:
    """A person's message addressed to other people (it @mentions someone and not @agent)."""
    return bool(m.get("mentions")) and not m.get("agent") and not AGENT_AT.search(str(m.get("body") or ""))


AGENT_AT = re.compile(r"(^|[\s(])@(agent|claude|arx)\b", re.I)


def find(p: Project, tid: str) -> dict:
    """A thread by id or unique id prefix (with or without the cm- prefix)."""
    ts = threads(events(p))
    hit = [t for t in ts if t["id"] == tid] or [t for t in ts if t["id"].startswith(tid) or t["id"][3:].startswith(tid)]
    if len(hit) != 1:
        raise KeyError(f"no comment {tid!r}" if not hit else f"{tid!r} is ambiguous")
    return hit[0]


def _last_note(p: Project, task_id: str) -> str | None:
    for e in reversed(p.events(task_id)):
        if isinstance(e, dict) and e.get("msg"):
            return e["msg"]
    return None


def with_agent(p: Project, ts: list[dict]) -> list[dict]:
    """Add each thread's agent state from the inbox: {status queued|running, task, note} while the agent owes work."""
    latest = {}
    for i in features.inbox(p):
        if i.get("kind") == "comment" and i.get("ref"):
            latest[i["ref"]] = i
    for th in ts:
        i = latest.get(th["id"])
        if i and i.get("status") in ("queued", "running"):
            th["agent"] = dict(status=i["status"], task=i.get("task"), item=i["id"],
                               note=_last_note(p, i["task"]) if i.get("task") else None)
    return ts


def reply(p: Project, tid: str, body: str, author: str = "agent", agent: bool = True, error: bool = False) -> dict:
    th = find(p, tid)
    return post(p, "reply", parent=th["id"], body=body[:MAX_BODY], author=author, agent=agent, error=error or None)


# ---------- HTTP: GET /api/comments -> {threads}; POST /api/comments {kind, ...}
@features.get("/api/comments")
def _get(p, path, q):
    ts = with_agent(p, threads(events(p)))
    if q.get("route"):
        ts = [t for t in ts if t["route"] == q["route"]]
    from . import answer  # answer imports this module
    return 200, dict(threads=ts, answer_agent=answer.agent_state(p))


ANCHOR_KEYS = ("route", "key", "rel", "sel", "text", "quote", "qn", "what", "ctx", "from", "rx", "ry", "px", "py", "vw", "shape")


@features.post("/api/comments")
def _post(p, path, d):
    if not isinstance(d, dict) or d.get("kind") not in KINDS:
        return 400, dict(error="bad request")
    k, author = d["kind"], str(d.get("author") or "you")[:60]
    by = str(d.get("by") or "") if people.ID.match(str(d.get("by") or "")) else None
    body = str(d.get("body") or "")[:MAX_BODY]
    if k == "comment":
        if not body.strip():
            return 400, dict(error="empty comment")
        a = d.get("anchor") if isinstance(d.get("anchor"), dict) else {}
        anchor = {x: a[x] for x in ANCHOR_KEYS if x in a}
        anchor["route"] = str(anchor.get("route") or "overview").lstrip("#")[:300]
        ev = post(p, "comment", author=author, by=by, body=body, anchor=anchor, mentions=people.mentioned(body, people.members(p)) or None)
        if not for_people(ev):
            features.enqueue(p, "comment", dict(thread=ev["id"], message=ev["id"]), ref=ev["id"])
        return 200, ev
    try:
        th = find(p, str(d.get("parent") or ""))
    except KeyError:
        if k not in ("edit", "delete"):
            return 404, dict(error="no such comment")
        th = None
    if k == "reply":
        if not body.strip():
            return 400, dict(error="empty reply")
        ev = post(p, "reply", parent=th["id"], body=body, author=author, by=by, agent=False, mentions=people.mentioned(body, people.members(p)) or None)
        if not for_people(ev):
            features.enqueue(p, "comment", dict(thread=th["id"], message=ev["id"]), ref=th["id"])
        return 200, ev
    if k in ("resolve", "reopen"):
        return 200, post(p, k, parent=th["id"], author=author, by=by)
    if k == "seen":
        return (200, post(p, k, parent=th["id"], by=by)) if by else (400, dict(error="seen needs by"))
    return 200, post(p, k, target=str(d.get("target") or ""), body=body or None, author=author, by=by)


@features.STATE.append
def _state(p, st):
    ts = threads(events(p))
    st["comments"] = dict(open=sum(1 for t in ts if not t["resolved"]), waiting=sum(1 for t in ts if t["waiting"]))


# ---------- the prompt an agent gets for one comment
def _rules(p: Project) -> str:
    """PROTOCOL.md's rules of evidence, so the answer reports numbers the way the dashboard does."""
    f = p.root / "PROTOCOL.md"
    text = f.read_text() if f.exists() else ""
    m = re.search(r"^## Rules of evidence\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return (m.group(1).strip() if m else
            "- Every number names its slice and n.\n- Show paired deltas vs the champion with the 90% interval; "
            "a delta whose interval spans 0 is noisy.")


def _where(rx, ry) -> str:
    try:
        x, y = float(rx), float(ry)
    except (TypeError, ValueError):
        return ""
    return f" ({x * 100:.0f}% across, {y * 100:.0f}% down that element)"


def describe_anchor(a: dict) -> list[str]:
    """What the comment points at, in words an agent can act on: the element under an arrow's tip or inside a box,
    the highlighted text, and the card it sits in."""
    out = [f"View: #{a.get('route') or 'overview'} (the dashboard route; e.g. #model/v3 is model v3's page)"]
    s = a.get("shape") if isinstance(a.get("shape"), dict) else {}
    tool, text, what = s.get("tool"), a.get("text"), a.get("what")
    if what and text == what.split(".")[0]:
        text = None  # an element with no text of its own (a bar, a tick): its tag and the card it sits in say more
    el = f"\"{text}\"" + (f" (element {what})" if what else "") if text else (f"element {what}" if what else "the page")
    if tool == "arrow" and s.get("mode") == "tip":
        out.append(f"Drawn: an arrow pointing at {el}{_where(a.get('rx'), a.get('ry'))}")
        if a.get("from"):
            out.append(f"The arrow starts at: \"{a['from']}\"")
    elif tool == "highlight" and a.get("quote"):
        out.append(f"Drawn: a highlight over the text \"{a['quote']}\"")
    elif tool in ("box", "pen") and (s.get("fit") or what):
        out.append(f"Drawn: {'a box around' if tool == 'box' else 'a pen mark on'} {el}")
    else:
        if text:
            out.append(f"Element: {el}")
        if a.get("quote"):
            out.append(f"Selected text: \"{a['quote']}\"")
        if tool:
            art = "an" if tool[0] in "aeiou" else "a"
            out.append(f"Drawn: {art} {tool} ({s.get('bw', '?')} x {s.get('bh', '?')} px) on that element")
    if a.get("ctx"):
        out.append(f"Inside: \"{a['ctx']}\"")
    return out


def prompt(p: Project, item: dict) -> str:
    tid = (item.get("payload") or {}).get("thread") or item.get("ref")
    th = find(p, tid)
    convo = "\n".join(f"[{m['author']}{' (agent)' if m['agent'] else ''}] {m['body']}" for m in th["messages"])
    return f"""You answer a comment someone left on the arx research dashboard for the project in the current directory.

Thread {th['id']} (oldest first; answer the newest message):
{convo}

Where it was left:
{chr(10).join('- ' + x for x in describe_anchor(th['anchor']))}

How to answer
- Post your answer with: arx comment reply {th['id']} "<answer>"   (exactly once, at the end).
- While you work, post short progress notes with: arx task note $ARX_TASK "<what you are checking>". The person sees
  the latest note live in the thread.
- Read-only: read research.json, PROTOCOL.md and the ledger in .research/ (models.json, hills.json, slices.json,
  goals.json, tasks/*/task.json, decisions), and use read-only commands (arx status, arx gate <model>,
  arx goal status, arx comment show {th['id']}). Never change models, slices, hills, goals, tasks or files.
- Visual first. When the answer has two or more numbers, lead with one figure: an inline
  <svg viewBox="0 0 400 H" width="400"> (H at most 240) built only from svg, g, path, rect, circle, line, polyline and
  text. Text at font-size 12 or more; text and axes in currentColor; one accent colour (#3b82f6, or #22c55e / #ef4444
  for better / worse). No scripts, styles or links inside it. The page shows the figure first, at full width.
- Then at most one or two short plain sentences. No headings, no lists.
- Name models by their titles (below), never by raw ids. Link views as #route (e.g. #model/v3, #hill/please,
  #task/<id>); they become links.
- If the ledger cannot answer it, say what is missing and which run would answer it.

Model titles (id: title):
{_titles(p)}

Reporting rules (PROTOCOL.md):
{_rules(p)}
"""


def _titles(p: Project, limit: int = 40) -> str:
    """How models read on the dashboard, so the answer never names a raw id: the champion first, then the newest."""
    ms = p.models()
    champ = [k for k, m in ms.items() if (m or {}).get("status") == "champion"]
    names = champ + [k for k in reversed(list(ms)) if k not in champ]
    rows = [f"- {k}: {features.model_label(p, k)}" for k in names[:limit]]
    return "\n".join(rows) or "- (no models yet)"


features.PROMPTS["comment"] = prompt


# ---------- CLI: arx comment ls|show|reply|resolve ; arx answer
def _fmt(th: dict) -> str:
    first = th["messages"][0]
    flag = "resolved" if th["resolved"] else "waiting" if th["waiting"] else "answered"
    return f"{th['id']}  #{th['route']}  {flag}  {len(th['messages'])} msg  {first['author']}: {first['body'][:70]}"


def cmd_comment(a):
    p = Project()
    if a.verb == "ls":
        ts = threads(events(p))
        if a.route:
            ts = [t for t in ts if t["route"] == a.route.lstrip("#")]
        if a.waiting:
            ts = [t for t in ts if t["waiting"]]
        if a.json:
            return print(json.dumps(with_agent(p, ts), indent=2, default=str))
        for t in ts:
            print(_fmt(t))
        if not ts:
            print("no comments")
        return
    if not a.id:
        sys.exit(f"arx comment {a.verb} needs a comment id")
    try:
        if a.verb == "show":
            th = with_agent(p, [find(p, a.id)])[0]
            if a.json:
                return print(json.dumps(th, indent=2, default=str))
            print(_fmt(th))
            for x in describe_anchor(th["anchor"]):
                print("  " + x)
            for m in th["messages"]:
                print(f"  [{m['author']}] {m['body']}")
        elif a.verb == "reply":
            text = " ".join(a.text)
            if a.file:
                text = (text + "\n" if text else "") + Path(a.file).read_text()
            if not text.strip():
                sys.exit("nothing to reply: give the text or --file")
            ev = reply(p, a.id, text, author=a.author)
            print(ev["id"])
        elif a.verb == "resolve":
            th = find(p, a.id)
            if a.text:
                post(p, "reply", parent=th["id"], body=" ".join(a.text), author=a.author, agent=True)
            post(p, "resolve", parent=th["id"], author=a.author)
    except KeyError as e:
        sys.exit(str(e).strip("'\""))


def cmd_answer(a):
    from . import answer
    answer.main(Project(), jobs=a.jobs, budget_s=a.budget_s, once=a.once, interval=a.interval)


@features.CLI.append
def _cli(sp):
    s = sp.add_parser("comment", help="comments left on dashboard views: list, show, reply (the agent answers here)")
    s.add_argument("verb", choices=["ls", "show", "reply", "resolve"]); s.add_argument("id", nargs="?")
    s.add_argument("text", nargs="*"); s.add_argument("--file", help="reply: append this file (e.g. an inline SVG)")
    s.add_argument("--author", default="agent"); s.add_argument("--route", help="ls: only this view, e.g. model/v3")
    s.add_argument("--waiting", action="store_true", help="ls: only threads waiting for the agent")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_comment)
    s = sp.add_parser("answer", help="hand inbox items (comments, questions, goals) and paper threads to agents (`arx up` starts it)")
    s.add_argument("--jobs", type=int, default=4, help="agents at once (default 4)")
    s.add_argument("--budget-s", type=float, default=900, help="wall-clock cap per agent (default 900)")
    s.add_argument("--once", action="store_true", help="start what is queued, wait for it, exit")
    s.add_argument("--interval", type=float, default=2.0, help="seconds between inbox scans")
    s.set_defaults(fn=cmd_answer)
