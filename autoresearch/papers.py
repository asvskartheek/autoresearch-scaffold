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

import json, os, re, secrets, shutil, time
from pathlib import Path

from .core import Project, _jsonl, _read, _write, now

MENTION = re.compile(r"(?<![\w@])@agent\b", re.I)
KINDS = ("comment", "reply", "seen", "resolve", "reopen", "edit", "delete")


NAME = re.compile(r"[A-Za-z0-9][\w.+-]{0,99}")  # paper and file names: no separators, dotfiles or control chars


def pdir(p: Project, name: str) -> Path:
    if not name or not NAME.fullmatch(name):
        raise KeyError("bad paper name")
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


def add(p: Project, name: str, src: Path, title: str = None, hill: str = None, goal: str = None) -> Path:
    """Publish or republish a paper. Open pages swap the new version in place."""
    d = pdir(p, name)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".paper.html.tmp"
    shutil.copyfile(src, tmp)
    tmp.replace(d / "paper.html")  # atomic: a page polling mid-write never reads half a paper
    meta = _read(d / "meta.json", {}) | {k: v for k, v in dict(title=title, hill=hill, goal=goal).items() if v}
    meta.setdefault("created", now())
    meta["updated"] = now()
    _write(d / "meta.json", meta)
    return d / "paper.html"


def attach(p: Project, name: str, src: Path) -> str:
    """Copy a page (widget, poster) next to the paper; returns the URL path a reply can link to."""
    if not (pdir(p, name) / "paper.html").exists():
        raise KeyError(f"no paper {name!r}")
    f = file(p, name, Path(src).name)
    f.parent.mkdir(exist_ok=True)
    shutil.copyfile(src, f)
    return f"/papers/{name}/files/{f.name}"


def file(p: Project, name: str, fname: str) -> Path:
    if not fname or not NAME.fullmatch(fname):
        raise KeyError("bad file name")
    return pdir(p, name) / "files" / fname


def thread(p: Project, name: str) -> list[dict]:
    """The event log; a hand-edited or foreign line is dropped, never allowed to take the paper down."""
    return [e for e in _jsonl(pdir(p, name) / "thread.jsonl")
            if isinstance(e, dict) and isinstance(e.get("id"), str) and e.get("kind") in KINDS]


def post(p: Project, name: str, kind: str, **fields) -> dict:
    if kind not in KINDS:
        raise ValueError(f"bad kind {kind!r}")
    if not (pdir(p, name) / "paper.html").exists():
        raise KeyError(f"no paper {name!r}")
    ev = dict(id=secrets.token_hex(4), t=now(), kind=kind, **{k: v for k, v in fields.items() if v is not None})
    # one write(2) on an O_APPEND fd: concurrent writers (the page, `arx paper reply`) never interleave a line
    fd = os.open(pdir(p, name) / "thread.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(ev, default=str) + "\n").encode())
    finally:
        os.close(fd)
    return ev


def threads(log: list[dict]) -> list[dict]:
    """Fold the event log into threads, oldest first. Each has its messages (edits applied, deletes dropped),
    `resolved`, `waiting` (the last message is from a person: the agent owes an answer) and `thinking`
    (the agent has seen that message)."""
    out, msgs, owner = {}, {}, {}  # owner: message id -> thread id
    for e in log:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or e.get("kind") not in KINDS:
            continue  # same filter as thread(), for logs built elsewhere
        e.setdefault("t", "")
        k = e["kind"]
        if k == "comment":
            m = dict(id=e["id"], t=e["t"], author=e.get("author") or "you", body=e.get("body", ""), agent=False)
            out[e["id"]] = dict(id=e["id"], t=e["t"], anchor=e.get("anchor"), resolved=False, resolved_by=None,
                                messages=[m], seen=set())
            msgs[e["id"]] = m; owner[e["id"]] = e["id"]
        elif k == "reply" and e.get("parent") in out:
            m = dict(id=e["id"], t=e["t"], author=e.get("author") or ("agent" if e.get("agent") else "you"),
                     body=e.get("body") or "", agent=bool(e.get("agent")), link=e.get("link"))
            out[e["parent"]]["messages"].append(m)
            msgs[e["id"]] = m; owner[e["id"]] = e["parent"]
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
        elif k == "seen" and e.get("parent") in owner:
            out[owner[e["parent"]]]["seen"].add(e["parent"])
    res = []
    for th in out.values():
        root_gone = th["messages"][0].get("deleted")
        th["messages"] = [m for m in th["messages"] if not m.get("deleted")]
        if root_gone and not any(m for m in th["messages"]):
            continue
        if root_gone:  # replies outlive a deleted first comment; the thread keeps its anchor
            th["root_deleted"] = True
        last = th["messages"][-1] if th["messages"] else None
        # "@agent" in a person's message summons the agent with the whole thread, even on a resolved thread
        th["mention"] = bool(last and not last["agent"] and MENTION.search(last["body"]))
        th["waiting"] = bool(last and not last["agent"] and (not th["resolved"] or th["mention"]))
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


SERIF = re.compile(r"font-family\s*:[^;}\"]*\b(Georgia|Times|Garamond|Merriweather|Palatino|Cambria|Lora|(?<!sans-)serif)\b", re.I)
PILL = re.compile(r"border-radius\s*:\s*(\d{3,}px|50%|\d+(\.\d+)?em)", re.I)
WIDGET = re.compile(r"<(input|button|select|textarea|details|canvas)\b|data-widget", re.I)
NUMBER = re.compile(r"(\d+(\.\d+)?\s*%|\d+/\d+)(?!\s*(CI|goal|target|interval))")
N_SIZE = re.compile(r"\bn\s*=\s*\d", re.I)


def check(html: str, slices=()) -> list[tuple[str, str]]:
    """Lint a paper against the rules in PROTOCOL.md. Returns (level, message); level is "error" or "warn"."""
    out = []
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", html, flags=re.S | re.I)
    blocks = re.findall(r'data-block="([^"]*)"', body)
    dup = sorted({b for b in blocks if blocks.count(b) > 1})
    if dup:
        out.append(("error", f"duplicate data-block ids: {', '.join(dup)}"))
    for tag in ("section", "p", "figure"):
        miss = [m for m in re.findall(rf"<{tag}\b[^>]*>", body, re.I) if "data-block=" not in m]
        if miss:
            out.append(("error", f"{len(miss)} <{tag}> without data-block (comments cannot anchor to them)"))
    sections = re.findall(r'<section\b[^>]*data-block="([^"]*)"[^>]*>(.*?)</section>', body, re.S | re.I)
    if not sections:
        out.append(("error", "no <section data-block=...>: the paper needs sections"))
    for sid, inner in sections:
        if not WIDGET.search(inner):
            out.append(("error", f"section {sid!r} has nothing to interact with (input, button, select, details, canvas)"))
        if not re.search(r"<svg\b|<canvas\b|<img\b|class=\"[^\"]*poster", inner, re.I):
            out.append(("warn", f"section {sid!r} has no visual (svg, canvas, img or poster)"))
        text = re.sub(r"<[^>]+>", " ", inner)
        if NUMBER.search(text) and not N_SIZE.search(text):
            out.append(("error", f"section {sid!r} reports numbers but never says n = …"))
    quizzes = len(re.findall(r'class="[^"]*\bquiz\b', body))
    if quizzes < 3:
        out.append(("error", f"{quizzes} quizzes (class=\"quiz\"); give a pop quiz per section and a closing test"))
    if not re.search(r'data-block="remember"', body):
        out.append(("error", "no Remember section (<section data-block=\"remember\">) for long-term recall"))
    if slices and not any(s in body or s.rsplit("/", 1)[-1] in body for s in slices):  # gsm8k-test/full or full
        out.append(("error", "names no slice from the ledger; every number names its slice and n"))
    for m in SERIF.finditer(html):
        out.append(("error", f"serif font: {m.group(0)[:60]!r}; use the shared theme (Instrument Sans)"))
    for m in PILL.finditer(html):
        out.append(("warn", f"rounded pill: {m.group(0)!r}; no pill bubbles"))
    if 'data-theme="dark"' not in html:  # the reader sets data-theme on the paper; it follows the page's toggle
        out.append(("error", 'no dark mode: style :root[data-theme="dark"] (the reader sets it)'))
    for left in ("gsm8k-percent-base", "Removing the inherited adapter", "arx-mem:gsm8k-96", "a 4B model from 87.6%"):  # `arx paper new` leftovers
        if left in html:
            out.append(("warn", f"still has the example's {left!r}: rewrite it (a shared storage key mixes Remember progress)"))
    if "Instrument Sans" not in html:
        out.append(("warn", "does not use the shared theme fonts (Instrument Sans, Bricolage Grotesque, JetBrains Mono)"))
    return out


def _kpi_text(kpi: str, v: float) -> list[str]:
    """How a KPI value may be written: 0.928 -> 92.8%, 92.8 % ; a target 0.96 -> 96%."""
    if kpi != "score":
        return [f"{v:g}", f"{v:.3g}", f"{v:.2f}"]
    return list(dict.fromkeys([f"{100 * v:g}%", f"{100 * v:.1f}%", f"{100 * v:.0f}%", f"{100 * v:.1f} %"]))


def check_goal(html: str, st: dict, hill_papers=()) -> list[tuple[str, str]]:
    """The goal paper is the public one. On top of `check`: a `result` section that states the goal KPI, slice
    and n, the champion's value and the paired delta vs the starting champion; links to every internal hill paper
    of the goal (relative `../<hill>`, marked class="internal"); and a draft / negative-result label that matches
    the goal's status. `st` is `Project.goal_status(goal)`."""
    out = []
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", html, flags=re.S | re.I)
    m = re.search(r'<section\b[^>]*data-block="result"[^>]*>(.*?)</section>', body, re.S | re.I)
    if not m:
        out.append(("error", 'no final-result section (<section data-block="result">)'))
    else:
        text = " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split())
        if st["slice"] not in text:
            out.append(("error", f"result section does not name the goal slice {st['slice']}"))
        if not re.search(rf"\bn\s*=\s*{st['n']}\b", text):
            out.append(("error", f"result section does not give n = {st['n']}"))
        if not any(t in text for t in _kpi_text(st["kpi"], st["target"])):
            out.append(("error", f"result section does not state the target ({_kpi_text(st['kpi'], st['target'])[0]})"))
        if st.get("value") is not None and not any(t in text for t in _kpi_text(st["kpi"], st["value"])):
            out.append(("error", f"result section does not state the ledger value {_kpi_text(st['kpi'], st['value'])[1]} "
                                 f"({st['model']}); numbers come from the ledger"))
        vs = st.get("vs_baseline")
        if vs and vs.get("delta") is not None:
            if st.get("baseline") and st["baseline"] not in text:
                out.append(("error", f"result section does not name the starting champion {st['baseline']}"))
            if f"{100 * vs['delta']:+.1f}" not in text:
                out.append(("error", f"result section does not give the paired delta {100 * vs['delta']:+.1f} pts vs the start"))
            if not re.search(r"90% CI|interval", text):
                out.append(("error", "result section gives no 90% interval for the paired delta"))
    for h in st.get("hills") or {}:
        if h not in hill_papers:
            continue
        a = re.search(rf'<a\b[^>]*href="(?:\.\./|/papers/){re.escape(h)}"[^>]*>', body, re.I)
        if not a:
            out.append(("error", f"no link to the internal hill paper {h!r} (href=\"../{h}\")"))
        elif not re.search(r'class="[^"]*\binternal\b', a.group(0)):
            out.append(("error", f"the link to hill paper {h!r} is not marked class=\"internal\""))
    status = st.get("status")
    if status == "open" and not re.search(r"\bdraft\b", body, re.I):
        out.append(("error", "the goal is open: label the paper a draft"))
    if status == "abandoned" and not re.search(r"\babandoned\b", body, re.I):
        out.append(("error", "the goal was abandoned: say so (\"abandoned\") and report the negative result"))
    if status == "achieved" and re.search(r'data-block="draft"', body):
        out.append(("warn", "the goal is achieved: remove the draft label"))
    if st.get("slice_changed"):
        out.append(("error", f"slice {st['slice']} changed since the goal opened; its numbers do not hold"))
    return out
