"""Python API for agents: tasks with live progress, and evals that stream rows as they finish."""
from __future__ import annotations

import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import stats
from .store import LedgerError, Project, check_name, find_root


def _project(root=None) -> Project:
    return Project(find_root(root))


def new_id(kind: str) -> str:
    return time.strftime("%m%d-%H%M%S") + f"-{kind}-" + secrets.token_hex(2)


class Task:
    def __init__(self, name: str, kind: str = "work", about: str = "", total: int | None = None,
                 parent: str | None = None, budget_s: float | None = None, agent: str | None = None,
                 project: Project | None = None):
        self.p = project or _project()
        self.id = new_id(kind)
        self.budget_s = budget_s
        self.t0 = time.time()
        parent = parent or os.environ.get("ARX2_PARENT")
        self.p.append("task.start", id=self.id, name=check_name(name, "task name"), kind=kind, about=about,
                      total=total, parent=parent, budget_s=budget_s, agent=agent)
        os.environ["ARX2_PARENT"] = self.id
        self._parent = parent
        self._done = 0

    def note(self, text: str):
        self.p.append("task.note", id=self.id, text=text)

    def progress(self, done: int, total: int | None = None):
        self._done = done
        ev = {"id": self.id, "done": done}
        if total is not None:
            ev["total"] = total
        self.p.append("task.progress", **ev)

    def log(self, **point):
        self.p.append_metric(self.id, {"t": time.time(), **point})

    def link(self, label: str, url: str):
        self.p.append("task.link", id=self.id, label=label, url=url)

    def ok(self) -> bool:
        return self.budget_s is None or time.time() - self.t0 < self.budget_s

    def end(self, status: str = "done", result: str | None = None):
        self.p.append("task.end", id=self.id, status=status, result=result)
        if self._parent:
            os.environ["ARX2_PARENT"] = self._parent
        else:
            os.environ.pop("ARX2_PARENT", None)

    def __enter__(self):
        return self

    def __exit__(self, et, e, tb):
        if et is None:
            self.end("done")
        elif et is KeyboardInterrupt:
            self.end("cancelled", "Stopped by hand.")
        else:
            self.end("failed", f"{et.__name__}: {e}")
        return False


def task(name: str, **kw) -> Task:
    return Task(name, **kw)


def evaluate(model: str, set_key: str, run_one, name: str | None = None, workers: int = 8,
             budget_s: float | None = None, project: Project | None = None) -> dict:
    """Run `run_one(item_id) -> {score, cost?, latency_s?}` over a frozen set; rows stream to the ledger."""
    p = project or _project()
    s = p.state()
    if set_key not in s["sets"]:
        raise LedgerError(f"no set {set_key!r}", fix="arx2 set list")
    if model not in s["candidates"]:
        raise LedgerError(f"no candidate {model!r}", fix=f'arx2 cand add {model} --name "<two words>" --change "<what changed>"')
    st = s["sets"][set_key]
    ids = list(st["ids"])
    label = name or f"{s['candidates'][model]['name']} run"[:24]
    with Task(label if len(label.split()) <= 2 else "Eval run", kind="eval", total=len(ids), budget_s=budget_s,
              about=f"{s['candidates'][model]['name']} on {st['name']}", project=p) as t:
        run = new_id("run")
        p.append("run", key=run, candidate=model, set=set_key, task=t.id, hash=st["hash"])
        done = 0
        with ThreadPoolExecutor(workers) as ex:
            futs = {ex.submit(_safe, run_one, i): i for i in ids}
            for f in as_completed(futs):
                p.append_rows(run, [{"id": str(futs[f]), **f.result()}])
                done += 1
                if done % max(1, len(ids) // 50) == 0 or done == len(ids):
                    t.progress(done)
                if not t.ok():
                    for g in futs:
                        g.cancel()
                    t.note(f"Stopped at {done} of {len(ids)} items: the time budget ran out.")
                    break
        summary = stats.summarize(p.rows(run))
        t.note(f"Scored {summary.get('passed', 0)} of {summary['n']} on {st['name']}"
               f" ({summary.get('score', 0):.1%}), {summary.get('errors', 0)} errors.")
    return {"run": run, **summary}


def _safe(fn, item):
    t0 = time.time()
    try:
        r = fn(item) or {}
        return {"score": r.get("score"), "cost": r.get("cost"), "latency_s": r.get("latency_s", round(time.time() - t0, 3)),
                "error": r.get("error")}
    except Exception as e:  # errors count as 0
        return {"score": 0.0, "cost": None, "latency_s": round(time.time() - t0, 3), "error": f"{type(e).__name__}: {e}"[:200]}
