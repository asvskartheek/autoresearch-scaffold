"""The research ledger: datasets, slices, hills, models, tasks, and the gate ladder computed from them.

Everything lives as plain JSON / JSONL under `.research/` so agents, scripts and the dashboard share one source of
truth. Gate results are never stored; they are derived from finished eval tasks every time they are asked for.
"""
from __future__ import annotations

import hashlib, json, math, os, random, statistics, sys, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def find_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for d in [p, *p.parents]:
        if (d / "research.json").exists():
            return d
    raise SystemExit("research.json not found; run `arx init` in the project root")


def now() -> float:
    return time.time()


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str))
    os.replace(tmp, p)


def _append(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass  # a writer may be mid-line
    return out


def ids_hash(ids) -> str:
    return hashlib.sha256(json.dumps(sorted(map(str, ids))).encode()).hexdigest()[:10]


# ---------------------------------------------------------------- statistics

def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    scores = [0.0 if r.get("error") else float(r.get("score") or 0) for r in rows]
    lat = sorted(r["latency_s"] for r in rows if isinstance(r.get("latency_s"), (int, float)))
    costs = [r["cost"] for r in rows if isinstance(r.get("cost"), (int, float))]
    pct = lambda q: lat[min(len(lat) - 1, math.ceil(q * len(lat)) - 1)] if lat else None
    return dict(n=n, score=statistics.mean(scores) if n else None, errors=sum(bool(r.get("error")) for r in rows),
                cost=sum(costs) / n if costs and n else None, cost_total=sum(costs) if costs else None,
                latency_p50=pct(0.5), latency_p95=pct(0.95), latency_mean=statistics.mean(lat) if lat else None)


def per_id(rows: list[dict]) -> dict[str, float]:
    """Mean score per example id; repeated samples of one id are averaged."""
    acc: dict[str, list[float]] = {}
    for r in rows:
        acc.setdefault(str(r["id"]), []).append(0.0 if r.get("error") else float(r.get("score") or 0))
    return {k: statistics.mean(v) for k, v in acc.items()}


def paired(cand: dict[str, float], base: dict[str, float], sign: int = 1, iters: int = 2000) -> dict:
    ids = sorted(set(cand) & set(base))
    if not ids:
        return dict(n=0, delta=None, lo=None, hi=None, wins=0, losses=0)
    d = [sign * (cand[i] - base[i]) for i in ids]
    rng = random.Random(0)
    boots = sorted(statistics.mean(rng.choices(d, k=len(d))) for _ in range(iters))
    return dict(n=len(ids), delta=statistics.mean(d), lo=boots[int(0.05 * iters)], hi=boots[int(0.95 * iters) - 1],
                wins=sum(x > 0 for x in d), losses=sum(x < 0 for x in d),
                cand=statistics.mean(cand[i] for i in ids), base=statistics.mean(base[i] for i in ids))


# ---------------------------------------------------------------- the project

class Project:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root).resolve() if root else find_root()
        self.dir = self.root / ".research"

    # config and simple collections -------------------------------------------------
    @property
    def config(self) -> dict:
        return _read(self.root / "research.json", {})

    def _coll(self, name: str) -> dict:
        return _read(self.dir / f"{name}.json", {})

    def _save(self, name: str, data: dict) -> None:
        _write(self.dir / f"{name}.json", data)

    def datasets(self) -> dict: return self._coll("datasets")
    def slices(self) -> dict: return self._coll("slices")
    def hills(self) -> dict: return self._coll("hills")
    def models(self) -> dict: return self._coll("models")

    def champion(self) -> str | None:
        return next((k for k, m in self.models().items() if m.get("status") == "champion"), None)

    def _upsert(self, coll: str, key: str, **fields) -> dict:
        data = self._coll(coll)
        rec = {**data.get(key, {"created": now()}), **{k: v for k, v in fields.items() if v is not None}}
        data[key] = rec
        self._save(coll, data)
        return rec

    def log_decision(self, kind: str, **fields) -> None:
        _append(self.dir / "decisions.jsonl", dict(t=now(), kind=kind, **fields))

    # datasets and slices -------------------------------------------------------------
    def add_dataset(self, name: str, ids: list, title: str = None, url: str = None, description: str = None):
        ids = [str(i) for i in ids]
        self._upsert("datasets", name, title=title or name, url=url, description=description, size=len(ids))
        self.add_slice(f"{name}/full", ids, kind="full", description="Every example", url=url)
        if not self.config.get("primary_dataset"):
            cfg = self.config | {"primary_dataset": name}
            _write(self.root / "research.json", cfg)

    def add_slice(self, name: str, ids: list, kind: str = "dev", description: str = None, url: str = None,
                  seed: int = None, hill: str = None, metric: str = None):
        if "/" not in name:
            name = f"{self.config['primary_dataset']}/{name}"
        ids = [str(i) for i in ids]
        old = self.slices().get(name)
        if old and old["hash"] != ids_hash(ids):
            raise SystemExit(f"slice {name} is frozen with different ids; create a new slice name")
        return self._upsert("slices", name, dataset=name.split("/")[0], kind=kind, ids=ids, n=len(ids),
                            hash=ids_hash(ids), description=description, url=url, seed=seed, hill=hill, metric=metric)

    def random_slices(self, dataset: str, sizes=(50, 100), seed: int = 42):
        """Nested random slices: random50 is the first 50 of random100."""
        pool = self.slices()[f"{dataset}/full"]["ids"]
        draw = random.Random(seed).sample(pool, min(max(sizes), len(pool)))
        for n in sizes:
            self.add_slice(f"{dataset}/random{n}", draw[:n], kind="random", seed=seed,
                           description=f"Seeded random {n} (seed {seed}), nested")

    def slice(self, name: str) -> dict:
        s = self.slices()
        if name in s:
            return s[name] | {"name": name}
        full = f"{self.config.get('primary_dataset')}/{name}"
        if full in s:
            return s[full] | {"name": full}
        raise SystemExit(f"unknown slice {name}")

    # hills and models ------------------------------------------------------------------
    def open_hill(self, name, title, target, control=None, problem=None, found_in=None):
        target, control = self.slice(target)["name"], (self.slice(control)["name"] if control else None)
        return self._upsert("hills", name, title=title, target=target, control=control, problem=problem,
                            found_in=found_in or self.champion(), status="open")

    def add_model(self, name, parent=None, hill=None, change=None, title=None, links=None, status="candidate"):
        rec = self._upsert("models", name, parent=parent if parent is not None else self.champion(), hill=hill,
                           change=change, title=title, links=links, status=status)
        if status == "champion":
            self.log_decision("champion", model=name, note="seeded as baseline")
        return rec

    def set_model_status(self, name, status, reason=None):
        self._upsert("models", name, status=status, reason=reason)
        self.log_decision(status, model=name, reason=reason)

    # tasks -----------------------------------------------------------------------------
    def task_dir(self, tid: str) -> Path:
        return self.dir / "tasks" / tid

    def tasks(self) -> list[dict]:
        out = []
        for p in (self.dir / "tasks").glob("*/task.json"):
            t = _read(p)
            if t:
                out.append(self._liveness(t))
        return sorted(out, key=lambda t: t.get("updated", 0), reverse=True)

    def task(self, tid: str) -> dict:
        t = _read(self.task_dir(tid) / "task.json")
        if not t:
            raise KeyError(tid)
        return self._liveness(t)

    def _liveness(self, t: dict) -> dict:
        stall = 60 * self.config.get("stall_minutes", 10)
        if t.get("status") == "running" and now() - t.get("heartbeat", t.get("updated", 0)) > stall:
            t = t | {"status": "stalled"}
        return t

    def rows(self, tid: str) -> list[dict]:
        return _jsonl(self.task_dir(tid) / "rows.jsonl")

    def metrics(self, tid: str) -> list[dict]:
        return _jsonl(self.task_dir(tid) / "metrics.jsonl")

    def events(self, tid: str) -> list[dict]:
        return _jsonl(self.task_dir(tid) / "events.jsonl")

    def evals(self) -> list[dict]:
        """Finished, complete eval tasks only; partial runs never count."""
        return [t for t in self.tasks() if t.get("kind") == "eval" and t.get("status") == "done" and t.get("complete")]

    def latest_eval(self, model: str, slice_name: str) -> dict | None:
        h = self.slices().get(slice_name, {}).get("hash")
        c = [t for t in self.evals() if t.get("model") == model and t.get("slice") == slice_name and t.get("slice_hash") == h]
        return max(c, key=lambda t: t.get("ended", 0)) if c else None

    # gates -----------------------------------------------------------------------------
    def _resolve(self, ref: str, model: dict) -> list[str]:
        hills = self.hills()
        if ref == "@hill.target":
            h = hills.get(model.get("hill") or "")
            return [h["target"]] if h else []
        if ref == "@hill.control":
            h = hills.get(model.get("hill") or "")
            return [h["control"]] if h and h.get("control") else []
        if ref == "@hills.climbed":
            return [h["target"] for k, h in hills.items() if h.get("status") == "climbed" and k != model.get("hill")]
        return [self.slice(ref)["name"]]

    def gate(self, model_name: str) -> dict:
        """Walk the ladder for a candidate against the champion. Pure function of the ledger."""
        cfg, models = self.config, self.models()
        m = models.get(model_name)
        if not m:
            raise SystemExit(f"unknown model {model_name}")
        champ = self.champion()
        if m.get("status") in ("rejected", "historical", "planned"):  # recorded decisions, not ladder candidates
            rung = dict(rung="decision", status="fail" if m["status"] == "rejected" else "locked",
                        checks=[dict(slice="-", rule="recorded", threshold=0, state=m["status"], reason=m.get("reason"))])
            return dict(model=model_name, champion=champ, rungs=[rung], promotable=False, next=[])
        sign = 1 if cfg.get("higher_is_better", True) else -1
        rungs, blocked, next_runs = [], False, []
        for rung in cfg.get("ladder", []):
            checks = []
            for chk in rung["checks"]:
                if chk.get("manual"):  # a human signs this off; it never passes on its own
                    checks.append(dict(slice=chk.get("slice", "manual"), rule="manual", threshold=0,
                                       state="needs_review", reason=chk.get("reason")))
                    continue
                for sl in self._resolve(chk["slice"], m):
                    c = dict(slice=sl, rule=chk["rule"], threshold=chk.get("margin", 0) if chk["rule"] == "better" else -chk.get("tolerance", 0))
                    ce, be = self.latest_eval(model_name, sl), self.latest_eval(champ, sl) if champ else None
                    if champ == model_name:
                        c["state"] = "champion"
                    elif not champ:
                        c["state"] = "no_champion"
                    elif not be:
                        c["state"] = "need_baseline"
                        next_runs.append((champ, sl))
                    elif not ce:
                        c["state"] = "need_run"
                        next_runs.append((model_name, sl))
                    else:
                        p = paired(per_id(self.rows(ce["id"])), per_id(self.rows(be["id"])), sign)
                        ok = p["delta"] is not None and (p["delta"] > c["threshold"] if chk["rule"] == "better" else p["delta"] >= c["threshold"])
                        c |= dict(state="pass" if ok else "fail", noisy=p["lo"] is not None and p["lo"] < 0 < p["hi"],
                                  cand_task=ce["id"], base_task=be["id"], **p)
                    checks.append(c)
            states = {c["state"] for c in checks}
            if blocked:
                status = "locked"
            elif not checks:
                status = "skipped"
            elif states <= {"pass", "champion"}:
                status = "champion" if states == {"champion"} else "pass"
            elif "fail" in states:
                status, blocked = "fail", True
            else:
                status, blocked = "pending", True
            rungs.append(dict(rung=rung["rung"], status=status, checks=checks))
            if status == "pending":
                break  # only the first unfinished rung lists runs to do
        for r in cfg.get("ladder", [])[len(rungs):]:
            rungs.append(dict(rung=r["rung"], status="locked", checks=[]))
        promotable = bool(rungs) and all(r["status"] in ("pass", "skipped") for r in rungs) and champ != model_name
        return dict(model=model_name, champion=champ, rungs=rungs, promotable=promotable,
                    next=[dict(model=a, slice=b) for a, b in dict.fromkeys(next_runs)] if not any(r["status"] == "fail" for r in rungs) else [])

    def promote(self, model_name: str, force: bool = False) -> None:
        g = self.gate(model_name)
        if not g["promotable"] and not force:
            raise SystemExit(f"{model_name} has not passed every rung; see `arx gate {model_name}`")
        old = self.champion()
        if old:
            self._upsert("models", old, status="retired")
        self._upsert("models", model_name, status="champion", promoted=now())
        hill = self.models()[model_name].get("hill")
        if hill and hill in self.hills():
            self._upsert("hills", hill, status="climbed", climbed_by=model_name)
        self.log_decision("promote", model=model_name, replaced=old, gate=g)


# ---------------------------------------------------------------- live tasks

_open: list["Task"] = []  # tasks running in this process, innermost last; new tasks nest under the top one


class Task:
    """A unit of visible work. Shows on the Workbench while running, in the Archive after.

    `parent` nests this task under another card. Left out, it is the innermost task still running in this process,
    else $ARX_PARENT (exported to child processes while a task runs), so a loop's evals sit under the loop.
    """

    def __init__(self, project: Project, kind: str, title: str, description: str = None, model: str = None,
                 slice: str = None, agent: str = None, total: int = None, links: dict = None, config: dict = None,
                 tid: str = None, parent: str = None):
        self.p = project
        self.id = tid or f"{time.strftime('%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:4]}"
        self.dir = project.task_dir(self.id)
        self._lock = threading.Lock()
        self._step = 0
        if not (self.dir / "task.json").exists():
            sl = project.slice(slice) if slice else None
            if parent is None:
                parent = _open[-1].id if _open else os.environ.get("ARX_PARENT") or None
            self.meta = dict(id=self.id, kind=kind, title=title, description=description, model=model, parent=parent,
                             slice=sl["name"] if sl else None, slice_hash=sl["hash"] if sl else None,
                             agent=agent, status="running", created=now(), updated=now(), heartbeat=now(),
                             progress=dict(done=0, total=total or (sl["n"] if sl else None)), links=links or {},
                             config=config or {}, summary={}, host=os.uname().nodename, pid=os.getpid(),
                             command=" ".join(sys.argv))
            self._flush()
            if kind != "eval":  # evals are leaves; anything else can hold sub-tasks
                self._env = os.environ.get("ARX_PARENT")
                _open.append(self)
                os.environ["ARX_PARENT"] = self.id
        else:
            self.meta = _read(self.dir / "task.json")

    def _flush(self):
        self.meta["updated"] = self.meta["heartbeat"] = now()
        _write(self.dir / "task.json", self.meta)

    def log(self, step: int | None = None, **values):
        """Append a point to every named series (loss, lr, running score...). Charts appear automatically."""
        with self._lock:
            self._step = step if step is not None else self._step + 1
            _append(self.dir / "metrics.jsonl", dict(t=now(), step=self._step, **values))
            self.meta["last"] = values
            self._flush()

    def note(self, msg: str, level: str = "info"):
        with self._lock:
            _append(self.dir / "events.jsonl", dict(t=now(), level=level, msg=msg))
            self._flush()

    def link(self, label: str, url: str):
        with self._lock:
            self.meta["links"][label] = url
            self._flush()

    def progress(self, done: int, total: int | None = None):
        with self._lock:
            prev = self.meta.get("progress") or {}
            hist = prev.get("hist", [])
            if not hist or now() - hist[-1][0] >= 5:  # throttled samples for rate / ETA
                hist = (hist + [[now(), done]])[-60:]
            self.meta["progress"] = dict(done=done, total=total or prev.get("total"), hist=hist)
            self._flush()

    def heartbeat(self):
        with self._lock:
            self._flush()

    def add_row(self, row: dict):
        with self._lock:
            _append(self.dir / "rows.jsonl", row)

    def finish(self, status: str = "done", summary: dict | None = None):
        with self._lock:
            if self.meta.get("kind") == "eval" and self.meta.get("slice"):
                rows = self.p.rows(self.id)
                want = set(self.p.slice(self.meta["slice"])["ids"])
                got = {str(r["id"]) for r in rows}
                self.meta["complete"] = got == want
                self.meta["summary"] = summarize(rows) | {"missing": len(want - got)}
            if summary:
                self.meta["summary"] = self.meta.get("summary", {}) | summary
            self.meta["status"], self.meta["ended"] = status, now()
            self._flush()
        if self in _open:
            _open.remove(self)
            env = _open[-1].id if _open else self._env
            if env:
                os.environ["ARX_PARENT"] = env
            else:
                os.environ.pop("ARX_PARENT", None)

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et:
            self.note(f"{et.__name__}: {ev}", "error")
        self.finish("failed" if et else "done")
        return False


def evaluate(project: Project, model: str, slice: str, run_one, workers: int = 8, deadline_s: float = 3600,
             title: str = None, description: str = None, agent: str = None, repeats: int = 1, config: dict = None,
             parent: str = None) -> Task:
    """Run `run_one(example_id) -> {"score": float, "cost": .., "latency_s": .., ...}` on every id of a slice.

    Exceptions and deadline overruns become error rows (score 0). The card shows progress and running score live.
    """
    sl = project.slice(slice)
    ids = [i for i in sl["ids"] for _ in range(repeats)]
    t = Task(project, "eval", title or f"{model} on {sl['name']}", description, model=model, slice=sl["name"],
             agent=agent, total=len(ids), parent=parent, config=(config or {}) | {"workers": workers, "deadline_s": deadline_s, "repeats": repeats})
    start, done, total_score = now(), 0, 0.0
    pool = ThreadPoolExecutor(workers)
    futs = {}
    for i in ids:
        futs[pool.submit(_timed, run_one, i)] = i
    try:
        for f in as_completed(futs, timeout=deadline_s):
            row = f.result()
            t.add_row(row)
            done += 1
            total_score += 0.0 if row.get("error") else float(row.get("score") or 0)
            t.progress(done)
            t.log(step=done, running_score=total_score / done, latency_s=row.get("latency_s"))
            if sys.stderr.isatty() or done == len(ids) or done % 50 == 0:
                sys.stderr.write(f"\r{t.id} {done}/{len(ids)} score={total_score / done:.3f} {now() - start:.0f}s")
    except TimeoutError:
        t.note(f"deadline {deadline_s}s reached; unfinished examples count as errors", "warn")
        for f, i in futs.items():
            if not f.done():
                t.add_row(dict(id=i, score=0.0, error="deadline", latency_s=deadline_s))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        sys.stderr.write("\n")
    t.finish("done")
    return t


def _timed(fn, i):
    t0 = time.time()
    try:
        out = fn(i) or {}
        return dict(id=str(i), latency_s=round(time.time() - t0, 3)) | out | {"id": str(i)}
    except Exception as e:  # an example that crashes is wrong, never skipped
        return dict(id=str(i), score=0.0, error=f"{type(e).__name__}: {e}"[:300], latency_s=round(time.time() - t0, 3))
