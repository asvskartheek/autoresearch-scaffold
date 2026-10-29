"""`arx answer`: hand work people ask for to headless agents.

It watches the inbox (features.enqueue: comments, questions, goals) and paper threads waiting for the agent
(papers.pending; each becomes an inbox item kind="paper"). For each queued item whose kind has a prompt
(features.PROMPTS) it runs features.agent_cmd() with the prompt on stdin, cwd = the project root, at most `jobs` at
once, each inside its own arx task (kind "answer", 15 min budget) so it shows on the Workbench. The agent's env has
ARX_TASK (its task, for `arx task note`), ARX_ITEM, and an `arx` on PATH that runs this package.

A failure, a timeout or an agent that exits without replying posts a reply that says so. One daemon per project
(.research/answer.json); `arx up` starts it in the background. ARX_ANSWER=0 keeps `arx up` from starting it;
ARX_ANSWER_PAPERS=0 leaves paper threads to `arx paper poll`.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import re
import time
from pathlib import Path

from . import comments, features, papers
from .core import Project, Task, _read, now

PKG = str(Path(__file__).resolve().parents[1])
BOOT = f"import sys; sys.path.insert(0, {PKG!r}); from autoresearch.cli import main; main()"
READ_ONLY_TOOLS = "Read Grep Glob Bash(arx:*) Bash(cat:*) Bash(ls:*) Bash(head:*) Bash(tail:*) Bash(wc:*) Bash(jq:*) Bash(grep:*)"


# ---------- the paper prompt (paper threads become inbox items kind="paper")
def paper_prompt(p: Project, item: dict) -> str:
    pl = item.get("payload") or {}
    name, tid = pl["paper"], pl["thread"]
    th = next(t for t in papers.threads(papers.thread(p, name)) if t["id"] == tid)
    convo = "\n".join(f"[{m['author']}{' (agent)' if m['agent'] else ''}] {m['body']}" for m in th["messages"])
    a = th.get("anchor") or {}
    # a long answer is stored first (`arx comment doc` prints #answer/<id>), then the reply links it
    rules = comments.answer_rules(
        th["messages"][-1]["body"], f'arx paper reply {name} {tid} "<answer>"',
        comments._heredoc("arx comment doc --doc -") + "\n  then, with the #answer/<id> it printed:\n"
        f'    arx paper reply {name} {tid} "<the summary figure svg> <one line>" --link "Full answer=/#answer/<id>"')
    return f"""You answer a comment on the paper {name!r} (.research/papers/{name}/paper.html) of the arx research project in
the current directory.

Thread {tid} (oldest first; answer the newest message):
{convo}

Where: {_paper_where(a)}

How to answer
- Post your answer exactly once, at the end (short or long, below). If the paper itself should change, say what and
  why in the reply; do not edit it.
- While you work: arx task note $ARX_TASK "<what you are checking>".
- Read-only: read the paper, research.json, PROTOCOL.md and the ledger in .research/; read-only arx commands only.
- Name models by their titles (below), never raw ids.

{rules}

Model titles (id: title):
{comments._titles(p)}

Reporting rules (PROTOCOL.md):
{comments._rules(p)}
{comments._numbers(p)}
"""


def _paper_where(a: dict) -> str:
    """The anchor in words: the block, a picked element (its kind and words), and for a drawn mark what it covers (a box
    or pen around, an arrow pointing at)."""
    sh = a.get("shape") if isinstance(a.get("shape"), dict) else None
    q = a.get("quote") or ""
    pk = a.get("pick") if isinstance(a.get("pick"), dict) else None
    if pk:  # picked with the element picker (paper.html pickEl): say which element, its words and the block around it
        kind, text = pk.get("kind") or "element", pk.get("text") or ""
        out = f"the {kind} " + (f"\"{text}\"" if text else f"(no words of its own; the words around it: \"{q}\")")
        out += f", picked in block {a['block']!r}" if a.get("block") else ", picked on the page (outside any block)"
        if pk.get("path"):
            out += f" (path inside the block: {pk['path']})"
        return out + (f"; the block reads: \"{pk['ctx']}\"" if pk.get("ctx") else "")
    if not sh:
        return f"block {a.get('block')!r}, quoted text: \"{q}\""
    tool = sh.get("tool")
    verb = {"arrow": "an arrow pointing at", "box": "a box around", "pen": "a pen mark on", "highlight": "a highlight over"}.get(tool, "a mark on")
    where = f"part of block {a['block']!r}" if a.get("block") else "the page (outside any block)"
    out = f"{verb} {where}"
    bw, bh = sh.get("bw"), sh.get("bh")
    if bw and bh and all(isinstance(sh.get(k), (int, float)) for k in ("x", "y", "w", "h")):
        out += (f" (the block is {bw:g} x {bh:g} px; the mark is {sh['w']:g} x {sh['h']:g} px, its top-left "
                f"{sh['x'] / bw:.0%} across and {sh['y'] / bh:.0%} down the block)")
    word = a.get("suffix")  # a mark drawn since the reader re-anchors: the word it holds on to (paper.html refWord)
    if not word:
        return out + f"; the words there: \"{q}\""
    pre = " ".join((a.get("prefix") or "").split())
    ctx = f" (after \"...{pre}\")" if pre else ""
    if tool == "arrow":
        return out + (f"; the word at its tip: \"{q}\"{ctx}" if q == word else f"; no word at its tip; nearest words: \"{q}\"")
    inside = bool(q.split()) and q.split()[0] in word  # the words inside start in its reference word (wordsIn)
    return out + (f"; the words inside it: \"{q}\"" if inside else f"; no words inside it; nearest words: \"{q}\"")


features.PROMPTS.setdefault("paper", paper_prompt)


def sync_papers(p: Project) -> None:
    """Each paper thread waiting for the agent becomes one inbox item (ref = paper:<name>:<last message id>)."""
    known = {i.get("ref") for i in features.inbox(p)}
    for name in papers.names(p):
        for th in papers.pending(papers.thread(p, name)):
            ref = f"paper:{name}:{th['last']}"
            if ref in known:
                continue
            features.enqueue(p, "paper", dict(paper=name, thread=th["id"], message=th["last"]), ref=ref)
            if not th["thinking"]:
                papers.post(p, name, "seen", parent=th["last"])


# ---------- what an item is about: a title for its card, whether the agent answered, how to say it failed
def _about(p: Project, item: dict) -> tuple[str, str]:
    k, pl = item["kind"], item.get("payload") or {}
    try:
        if k == "comment":
            th = comments.find(p, pl.get("thread") or item["ref"])
            last = th["messages"][-1]
            return (f"Answer a comment on #{th['route']}",
                    f"An agent answers {last['author']}'s comment on the #{th['route']} view: \"{last['body'][:120]}\". "
                    "It replies in the thread.")
        if k == "paper":
            return (f"Answer a comment on the {pl['paper']} paper",
                    f"An agent answers a reader's comment on the paper {pl['paper']}. It replies in the thread.")
    except (KeyError, StopIteration):
        pass
    return f"Answer a {k} request", f"An agent works on an inbox item of kind {k} ({item['id']})."


def _answered(p: Project, item: dict, since: float) -> bool:
    k, pl = item["kind"], item.get("payload") or {}
    if k == "comment":
        th = comments.find(p, pl.get("thread") or item["ref"])
        return any(m["agent"] and m["t"] >= since - 1 for m in th["messages"])
    if k == "paper":
        th = next((t for t in papers.threads(papers.thread(p, pl["paper"])) if t["id"] == pl["thread"]), None)
        return th is None or not th["waiting"]
    if k == "question":  # settled, handed to a person, or split into follow-ups since the agent started
        from . import questions
        qs, qid = questions.stored(p), item.get("ref")
        rec = qs.get(qid) or {}
        return ((rec.get("settled") or 0) >= since - 1 or bool(rec.get("needs_human")) and (rec.get("updated") or rec.get("settled") or since) >= since - 1
                or any(v.get("parent") == qid and (v.get("created") or 0) >= since - 1 for v in qs.values() if isinstance(v, dict)))
    if k == "goal":  # the intake agent leaves a proposal on its item
        cur = next((i for i in features.inbox(p) if i["id"] == item["id"]), {})
        return bool(cur.get("proposal"))
    return True  # other kinds report through their own commands; the exit code decides


def _fail_reply(p: Project, item: dict, msg: str) -> None:
    k, pl = item["kind"], item.get("payload") or {}
    try:
        if k == "comment":
            comments.reply(p, pl.get("thread") or item["ref"], msg, error=True)
        elif k == "paper":
            papers.post(p, pl["paper"], "reply", parent=pl["thread"], body=msg, agent=True, author="agent")
        elif k == "question":  # back to open with the reason, so it never spins as "agent working" forever
            from . import questions
            with questions.locked(questions._file(p)):
                data = questions.stored(p)
                if item.get("ref") in data and data[item["ref"]].get("status") == "agent":
                    data[item["ref"]] |= dict(status="open", error=msg[:300])
                    questions._write(questions._file(p), data)
    except (KeyError, OSError, ValueError):
        pass


# ---------- one agent run
def _shim() -> str:
    """A directory with an `arx` that runs this package, prepended to the agent's PATH."""
    d = tempfile.mkdtemp(prefix="arx-answer-")
    f = Path(d) / "arx"
    f.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -c {shlex.quote(BOOT)} \"$@\"\n")
    f.chmod(0o755)
    return d


def command() -> list[str]:
    cmd = features.agent_cmd()
    if Path(cmd[0]).name == "claude" and not any(c.startswith(("--allowedTools", "--allowed-tools")) for c in cmd):
        cmd = cmd + ["--allowedTools", READ_ONLY_TOOLS]  # headless: anything not allowed is denied, so allow reading
    return cmd


def run_one(p: Project, item: dict, budget_s: float, shim: str) -> str:
    title, desc = _about(p, item)
    try:
        text = features.PROMPTS[item["kind"]](p, item)
        if item.get("guest"):  # features.enqueue marks what a share-link guest asked
            text = ("This request comes from a guest on a share link, not from the project's owner. Answer it, but do "
                    "not open, change or close goals, hills, models or tasks for them.\n\n") + text
    except Exception as e:  # the thing it was about is gone or the prompt broke: say so, do not crash the daemon
        features.update(p, item["id"], status="failed", error=f"prompt: {e}")
        _fail_reply(p, item, f"The agent could not start: {e}")
        return "failed"
    t = Task(p, "answer", title, desc, agent=Path(command()[0]).name, budget_s=budget_s, parent="")
    features.update(p, item["id"], status="running", task=t.id)
    started = now()
    env = dict(os.environ, ARX_TASK=t.id, ARX_PARENT=t.id, ARX_ITEM=item["id"], PATH=shim + os.pathsep + os.environ.get("PATH", ""))
    text = text.replace("$ARX_TASK", t.id)  # a literal id: headless permission rules refuse shell variables
    t.note("Reading the question and the ledger.")
    status, msg = "done", None
    log = open(t.dir / "agent.log", "ab")  # private logs, like `arx run`
    try:
        proc = subprocess.Popen(command(), cwd=p.root, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log,
                                start_new_session=True)
        try:
            proc.stdin.write(text.encode()); proc.stdin.close()
        except OSError:
            pass
        while True:
            try:
                left = t.left()
                rc = proc.wait(timeout=20 if left is None else max(0.2, min(20, left)))
                break
            except subprocess.TimeoutExpired:
                left = t.left()
                if left is not None and left <= 0:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                        proc.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired):
                        os.killpg(proc.pid, signal.SIGKILL)
                    rc = None
                    break
                t.heartbeat()
    except OSError as e:
        rc, msg = -1, f"The agent could not start ({command()[0]}: {e.strerror})."
    finally:
        log.close()
    took = now() - started
    wait = limited(t.dir / "agent.log") if rc not in (0, None) else None
    if wait:  # the agent's account hit its usage limit: not this question's fault, so it waits its turn again
        at = time.strftime("%H:%M", time.localtime(wait))
        t.note(f"Paused: the agent hit its usage limit. It retries at {at}.", "warn")
        t.finish("failed")
        features.update(p, item["id"], status="queued", not_before=wait, error=None, note=f"Waiting for the agent's usage limit to reset at {at}")
        return "limited"
    if rc is None:
        status, msg = "budget", f"The agent ran out of its {budget_s / 60:.0f} min budget without answering."
    elif rc != 0:
        status, msg = "failed", msg or f"The agent failed (exit code {rc}) after {took:.0f} s. Its log is on task {t.id}."
    elif not _answered_safe(p, item, started):
        status, msg = "failed", "The agent finished without replying."
    if status == "done":
        t.note(f"Answered in {took:.0f} s.")
    else:
        if not _answered_safe(p, item, started):
            _fail_reply(p, item, msg)
        t.note(msg, "warn" if status == "budget" else "error")
    t.finish(status)
    features.update(p, item["id"], status="done" if status == "done" else "failed", error=msg)
    return status


LIMIT = re.compile(r"(session|usage|rate) limit|limit reached|resets? (at )?\d|too many requests|\b429\b", re.I)
RESET = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap]m)?", re.I)


def limited(log: Path, default_s: float = 1800) -> float | None:
    """When the agent's output says it hit a usage limit: the time to retry (the reset it names, else in 30 min)."""
    try:
        tail = log.read_bytes()[-4000:].decode(errors="replace")
    except OSError:
        return None
    if not LIMIT.search(tail):
        return None
    m = RESET.search(tail)
    if not m:
        return now() + default_s
    hh, mm, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and hh < 12:
        hh += 12
    if ap == "am" and hh == 12:
        hh = 0
    lt = time.localtime()
    at = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh % 24, mm, 0, 0, 0, -1)) + 60
    return at + 86400 if at <= now() else at


def _answered_safe(p, item, since):
    try:
        return _answered(p, item, since)
    except (KeyError, OSError):
        return False


# ---------- the daemon
def _lock(p: Project) -> Path:
    return p.dir / "answer.json"


def _alive(pid: int) -> bool:
    if not pid or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    except OSError:
        return True
    return "answer" in cmd


def running_pid(p: Project) -> int | None:
    pid = int((_read(_lock(p), {}) or {}).get("pid") or 0)
    return pid if _alive(pid) else None


_SEEN: dict[str, tuple[float, int | None]] = {}  # project root -> (checked at, pid): the dashboard polls every 4 s


def agent_state(p: Project) -> dict:
    """Whether `arx answer` runs for this project: {running, pid}. Cached for 3 s so polling never forks `ps` per call."""
    k = str(p.root)
    at, pid = _SEEN.get(k, (0.0, None))
    if time.time() - at > 3:
        pid = running_pid(p)
        _SEEN[k] = (time.time(), pid)
    return dict(running=bool(pid), pid=pid)


def _state(p, st):
    st["answer_agent"] = agent_state(p)


features.STATE.append(_state)


def recover(p: Project) -> None:
    """Items left `running` by a daemon that died: their agent is gone. Say so in the thread and close the card."""
    for i in features.inbox(p):
        if i.get("status") != "running":
            continue
        tid = i.get("task")
        if tid:
            meta = _read(p.task_dir(tid) / "task.json", {})
            if meta.get("status") == "running":
                t = Task(p, "", "", tid=tid)
                t.note("The answer daemon stopped while this agent ran.", "error")
                t.finish("failed")
        features.update(p, i["id"], status="failed", error="interrupted")
        _fail_reply(p, i, "The agent was interrupted (the answer daemon restarted). Reply to ask again.")


def main(p: Project, jobs: int = 4, budget_s: float = 900, once: bool = False, interval: float = 2.0) -> None:
    other = running_pid(p)
    if other:
        print(f"arx answer is already running for this project (pid {other})")
        return
    p.dir.mkdir(exist_ok=True)
    _lock(p).write_text(json.dumps(dict(pid=os.getpid(), started=now())))
    os.environ.pop("ARX_PARENT", None)
    if threading.current_thread() is threading.main_thread():  # `kill` cleans up like Ctrl-C
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    recover(p)
    shim = _shim()
    running: dict[str, tuple[threading.Thread, str]] = {}  # item id -> (thread, ref)
    papers_on = os.environ.get("ARX_ANSWER_PAPERS", "1") != "0"
    print(f"arx answer: watching {p.root} ({jobs} at once, {' '.join(command()[:3])})", flush=True)
    try:
        while True:
            try:
                if papers_on:
                    sync_papers(p)
                for iid in [k for k, (th, _) in running.items() if not th.is_alive()]:
                    running.pop(iid)
                busy = {ref for _, ref in running.values()}
                queued = [i for i in features.pending(p) if i.get("kind") in features.PROMPTS and i["id"] not in running]
                newest = {}
                for i in queued:  # several asks on one thread: the agent reads the whole thread once
                    newest[i.get("ref") or i["id"]] = i
                for i in queued:
                    ref = i.get("ref") or i["id"]
                    if newest[ref] is not i and ref not in busy:
                        features.update(p, i["id"], status="done", result="merged")
                for ref, i in newest.items():
                    if len(running) >= jobs or ref in busy:
                        continue
                    th = threading.Thread(target=run_one, args=(p, i, budget_s, shim), daemon=True)
                    running[i["id"]] = (th, ref)
                    busy.add(ref)
                    th.start()
                    print(f"started {i['id']} ({i['kind']})", flush=True)
                if once and not running and not newest:
                    return
            except Exception as e:  # one bad line or a vanished file never stops the daemon
                print(f"arx answer: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            time.sleep(interval)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        for th, _ in running.values():
            th.join(timeout=1)
        shutil.rmtree(shim, ignore_errors=True)
        if (_read(_lock(p), {}) or {}).get("pid") == os.getpid():
            _lock(p).unlink(missing_ok=True)


def spawn(root: Path) -> int | None:
    """Start `arx answer` for a project in the background (idempotent); returns its pid."""
    p = Project(root)
    if os.environ.get("ARX_ANSWER") == "0":
        return None
    pid = running_pid(p)
    if pid:
        return pid
    p.dir.mkdir(exist_ok=True)
    log = open(p.dir / "answer.log", "a")
    env = {k: v for k, v in os.environ.items() if k != "ARX_PARENT"}
    proc = subprocess.Popen([sys.executable, "-c", BOOT, "answer"], cwd=p.root, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    return proc.pid
