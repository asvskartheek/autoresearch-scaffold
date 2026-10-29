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
import signal
import subprocess
import sys
import tempfile
import threading
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
    return f"""You answer a comment on the paper {name!r} (.research/papers/{name}/paper.html) of the arx research project in
the current directory.

Thread {tid} (oldest first; answer the newest message):
{convo}

Where: block {a.get('block')!r}, quoted text: "{a.get('quote') or ''}"

How to answer
- Post your answer with: arx paper reply {name} {tid} "<answer>"   (exactly once, at the end). If the paper itself
  should change, say what and why in the reply; do not edit it.
- While you work: arx task note $ARX_TASK "<what you are checking>".
- Read-only: read the paper, research.json, PROTOCOL.md and the ledger in .research/; read-only arx commands only.
- Be short: at most three plain sentences.

Reporting rules (PROTOCOL.md):
{comments._rules(p)}
"""


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
    return True  # other kinds report through their own commands; the exit code decides


def _fail_reply(p: Project, item: dict, msg: str) -> None:
    k, pl = item["kind"], item.get("payload") or {}
    try:
        if k == "comment":
            comments.reply(p, pl.get("thread") or item["ref"], msg, error=True)
        elif k == "paper":
            papers.post(p, pl["paper"], "reply", parent=pl["thread"], body=msg, agent=True, author="agent")
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
