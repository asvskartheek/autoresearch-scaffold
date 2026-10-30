"""The research ledger: datasets, slices, hills, models, tasks, and the gate ladder computed from them.

Everything lives as plain JSON / JSONL under `.research/` so agents, scripts and the dashboard share one source of
truth. Gate results are never stored; they are derived from finished eval tasks every time they are asked for.
"""
from __future__ import annotations

import contextlib, fcntl, hashlib, itertools, json, math, os, random, shlex, signal, statistics, subprocess, sys, threading, time, uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path


def find_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for d in [p, *p.parents]:
        if (d / "research.json").exists():
            return d
    raise SystemExit("research.json not found; run `arx init` in the project root")


def now() -> float:
    return time.time()


_SCALES: dict = {}  # (ledger dir, slice) -> (slices.json version, scale inferred from its runs)
_CACHE: dict = {}  # path -> (mtime_ns, size, parsed); the dashboard re-reads the same files on every poll


def _cached(p: Path, parse):
    """Parse a file once per version (mtime and size); callers get a fresh copy, so mutating it is safe."""
    st = os.stat(p)
    key = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(p)
    if hit and hit[0] == key:
        return hit[1]
    val = parse(p.read_text())
    _CACHE[p] = (key, val)
    return val


def _read(p: Path, default=None):
    try:
        return _copy(_cached(p, json.loads))
    except (OSError, ValueError):
        return default


def _copy(o):
    if isinstance(o, dict):
        return {k: _copy(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_copy(v) for v in o]
    return o


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f"{p.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")  # one per writer: no shared tmp to race on
    tmp.write_text(json.dumps(obj, indent=2, default=str))
    os.replace(tmp, p)


@contextlib.contextmanager
def locked(p: Path):
    """Hold an exclusive lock on `p` (via `p.lock`) across processes and threads, for read-modify-write of a ledger file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(p.suffix + ".lock"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _append(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def _parse_jsonl(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass  # a writer may be mid-line
    return out


def _jsonl(p: Path) -> list[dict]:
    try:
        return [dict(r) if isinstance(r, dict) else r for r in _cached(p, _parse_jsonl)]
    except OSError:
        return []


def ids_hash(ids) -> str:
    return hashlib.sha256(json.dumps(sorted(map(str, ids))).encode()).hexdigest()[:10]


# ---------------------------------------------------------------- statistics

def summarize(rows: list[dict], continuous: bool = False) -> dict:
    """On a 0/1 slice an errored row scores 0. On a continuous slice 0 can be the best value (minus ms), so errored rows
    are left out of the mean and only counted in `errors`."""
    n = len(rows)
    if continuous:
        scores = [float(r.get("score") or 0) for r in rows if not r.get("error")]
    else:
        scores = [0.0 if r.get("error") else float(r.get("score") or 0) for r in rows]
    lat = sorted(r["latency_s"] for r in rows if isinstance(r.get("latency_s"), (int, float)))
    costs = [r["cost"] for r in rows if isinstance(r.get("cost"), (int, float))]
    pct = lambda q: lat[min(len(lat) - 1, math.ceil(q * len(lat)) - 1)] if lat else None
    return dict(n=n, score=statistics.mean(scores) if scores else None, errors=sum(bool(r.get("error")) for r in rows),
                cost=sum(costs) / n if costs and n else None, cost_total=sum(costs) if costs else None,
                latency_p50=pct(0.5), latency_p95=pct(0.95), latency_mean=statistics.mean(lat) if lat else None)


ERROR_SHARE_WARN = 0.2  # a pooled side with at least this share of errored rows is flagged (PROTOCOL.md § Rules of evidence)


def pool_errors(rows: list[dict]) -> dict:
    """How much of a pooled score is errors: rows pooled, rows errored, their share. Errors still count as 0 (or drop
    out on a continuous slice); this only makes them visible wherever the pooled score is served."""
    n, e = len(rows), sum(bool(r.get("error")) for r in rows)
    return dict(pooled_rows=n, pooled_errors=e, error_share=e / n if n else None)


def scale_of_rows(rows: list[dict]) -> str | None:
    """The scale a run's scores show: "binary" when every non-errored score is 0 or 1, else "continuous"; None when
    no row has a score to read (no rows, or every row errored)."""
    vals = {r.get("score") for r in rows if not r.get("error")}
    vals.discard(None)
    if not vals:
        return None
    return "binary" if vals <= {0, 1} else "continuous"


def per_id(rows: list[dict], continuous: bool = False) -> dict[str, float]:
    """Mean score per example id; repeated samples of one id are averaged. On a continuous slice errored rows are
    skipped (an id with only errors drops out of pairing) instead of scoring 0."""
    acc: dict[str, list[float]] = {}
    for r in rows:
        if continuous and r.get("error"):
            continue
        acc.setdefault(str(r["id"]), []).append(0.0 if r.get("error") else float(r.get("score") or 0))
    return {k: statistics.mean(v) for k, v in acc.items()}


_BOOT: dict = {}  # (deltas, iters) -> (lo, hi): a bootstrap is a pure function of its deltas


def paired(cand: dict[str, float], base: dict[str, float], sign: int = 1, iters: int = 2000) -> dict:
    """Paired delta of cand over base on their shared ids, with a 90% bootstrap CI (seed 0, `iters` resamples).

    The resamples draw exactly what `random.Random(0).choices(d, k=n)` draws, one draw `floor(random() * n)` per
    pick, but run the whole draw-index-sum chain in C (islice/map/fsum) instead of a Python loop and
    statistics.mean (about 3x faster), and remember each CI by its deltas, so the dashboard's next poll of the same
    pair costs nothing."""
    ids = sorted(set(cand) & set(base))
    if not ids:
        return dict(n=0, delta=None, lo=None, hi=None, wins=0, losses=0)
    d = [sign * (cand[i] - base[i]) for i in ids]
    n, key = len(d), (tuple(d), iters)
    ci = _BOOT.get(key)
    if ci is None:
        draws = iter(random.Random(0).random, None)  # an endless stream of the same floats choices() would use
        pick, scale = d.__getitem__, float(n).__mul__
        boots = sorted(math.fsum(map(pick, map(int, map(scale, itertools.islice(draws, n))))) / n for _ in range(iters))
        ci = _BOOT[key] = (boots[int(0.05 * iters)], boots[int(0.95 * iters) - 1])
        with contextlib.suppress(RuntimeError, StopIteration, KeyError):  # another thread may be trimming too
            while len(_BOOT) > 512:  # the dashboard re-asks the same pairs every poll; keep the recent ones
                _BOOT.pop(next(iter(_BOOT)))
    return dict(n=n, delta=math.fsum(d) / n, lo=ci[0], hi=ci[1],
                wins=sum(x > 0 for x in d), losses=sum(x < 0 for x in d),
                cand=math.fsum(cand[i] for i in ids) / n, base=math.fsum(base[i] for i in ids) / n)


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
    def goals(self) -> dict: return self._coll("goals")

    def champion(self) -> str | None:
        return next((k for k, m in self.models().items() if m.get("status") == "champion"), None)

    def _upsert(self, coll: str, key: str, **fields) -> dict:
        with locked(self.dir / f"{coll}.json"):
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
                  seed: int = None, hill: str = None, metric: str = None,
                  scale: str = None, unit: str = None):
        if "/" not in name:
            name = f"{self.config['primary_dataset']}/{name}"
        ids = [str(i) for i in ids]
        old = self.slices().get(name)
        if old and old["hash"] != ids_hash(ids):
            raise SystemExit(f"slice {name} is frozen with different ids; create a new slice name")
        return self._upsert("slices", name, dataset=name.split("/")[0], kind=kind, ids=ids, n=len(ids),
                            hash=ids_hash(ids), description=description, url=url, seed=seed, hill=hill, metric=metric,
                            scale=scale, unit=unit)

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
    def open_hill(self, name, title, target, control=None, problem=None, found_in=None, goal=None, **explainer):
        target, control = self.slice(target)["name"], (self.slice(control)["name"] if control else None)
        if goal and goal not in self.goals():
            raise SystemExit(f"unknown goal {goal}; `arx goal open {goal} ...` first")
        self._upsert("hills", name, title=title, target=target, control=control, problem=problem,
                     found_in=found_in or self.champion(), status="open", goal=goal)
        return self.explain_hill(name, **explainer)

    def explain_hill(self, name, symptom=None, measure=None, examples=None, share=None, goal=None):
        """The hill's page: `symptom` one plain line; `measure` when one target example scores 1; `examples` a list
        of {input, wrong, right, why} (illustrative, never client text); `share` {count, of, of_what}: how many of
        which failures this hill explains."""
        if name not in self.hills():
            raise SystemExit(f"unknown hill {name}")
        if goal and goal not in self.goals():
            raise SystemExit(f"unknown goal {goal}")
        return self._upsert("hills", name, symptom=symptom, measure=measure, examples=examples, share=share, goal=goal)

    # goals: the outward-facing claim a set of hills serves ---------------------------------
    KPI_LOWER = ("cost", "latency_p50", "latency_p95", "latency_mean")

    def open_goal(self, name, title, slice, target: float, kpi="score", baseline=None, problem=None,
                  higher_is_better=None):
        """A goal is a target KPI on one slice (usually a full slice), e.g. score >= 0.96 on gsm8k-test/full.
        `baseline` is the starting champion: the final result is reported as a paired delta against it."""
        sl = self.slice(slice)
        if higher_is_better is None:
            higher_is_better = kpi not in self.KPI_LOWER and self.config.get("higher_is_better", True)
        base = baseline or self.champion()
        if name in self.goals() and self.goals()[name].get("status") != "open":
            raise SystemExit(f"goal {name} is {self.goals()[name]['status']}; open a new goal with a new name")
        rec = self._upsert("goals", name, title=title, slice=sl["name"], slice_hash=sl["hash"], n=sl["n"], kpi=kpi,
                           target=float(target), higher_is_better=bool(higher_is_better), baseline=base,
                           problem=problem, status="open")
        self.log_decision("goal_open", goal=name, target=target, slice=sl["name"], baseline=base)
        return rec

    def _kpi(self, model, sl, kpi) -> tuple[float | None, dict | None]:
        ev = self.latest_eval(model, sl) if model else None
        if not ev:
            return None, None
        if kpi == "score":  # pooled over every complete run, like the gates
            sc = self.pooled_scores(model, sl)
            return (sum(sc.values()) / len(sc) if sc else None), ev
        return (ev.get("summary") or {}).get(kpi), ev

    def goal_status(self, name) -> dict:
        """Where a goal stands: the champion's KPI on the goal slice, the gap to target, the paired delta vs the
        starting champion, and the hills that serve it. Pure function of the ledger, like the gates."""
        g = self.goals().get(name)
        if not g:
            raise SystemExit(f"unknown goal {name}")
        sl, kpi, sign = g["slice"], g.get("kpi", "score"), 1 if g.get("higher_is_better", True) else -1
        slr = self.slices().get(sl) or {}
        cur = slr.get("hash")
        model = (g.get("evidence") or {}).get("model") if g.get("status") == "achieved" else self.champion()
        value, ev = self._kpi(model, sl, kpi)
        vs = None
        if kpi == "score" and model and g.get("baseline") and g["baseline"] != model and self.latest_eval(g["baseline"], sl):
            mine, theirs = latest_shared(self.slice_evals(model, sl), self.slice_evals(g["baseline"], sl))
            vs = paired(per_id([r for t in mine for r in self.rows(t["id"])]),
                        per_id([r for t in theirs for r in self.rows(t["id"])]), sign)
        hills = {k: h.get("status") for k, h in self.hills().items() if h.get("goal") == name}
        errs = pool_errors([r for t in self.score_runs(model, sl) for r in self.rows(t["id"])]) if model and ev else \
            dict(pooled_rows=0, pooled_errors=0, error_share=None)
        status = dict(g, name=name, model=model, value=value, task=ev["id"] if ev else None, **errs,
                    runs=len(self.score_runs(model, sl)) if model else 0,
                    met=value is not None and sign * (value - g["target"]) >= 0,
                    gap=None if value is None else sign * (g["target"] - value), vs_baseline=vs, hills=hills,
                    slice_changed=bool(cur and g.get("slice_hash") and cur != g["slice_hash"]),
                    # how the slice's score reads: 0/1 per example (counts of n) or a continuous amount in `unit`
                    scale=self.slice_scale(sl), unit=slr.get("unit"), metric=slr.get("metric"))

        return goal_evidence_status(status, bool(self.latest_eval(g.get("baseline"), sl)))

    def achieve_goal(self, name, force=False, note=None) -> dict:
        st = self.goal_status(name)
        if st["status"] != "open":
            raise SystemExit(f"goal {name} is {st['status']}")
        if st["slice_changed"]:
            raise SystemExit(f"slice {st['slice']} changed since the goal opened; open a new goal")
        if not st["met"] and not force:
            have = "no complete run" if st["value"] is None else f"{st['value']:.4f}"
            raise SystemExit(f"champion {st['model']} has {have} on {st['slice']}; target {st['target']}")
        evidence = dict(model=st["model"], task=st["task"], value=st["value"], runs=st["runs"], slice=st["slice"],
                        n=st["n"], vs_baseline=st["vs_baseline"], forced=bool(force and not st["met"]), note=note)
        self._upsert("goals", name, status="achieved", achieved=now(), evidence=evidence)
        self.log_decision("goal_achieved", goal=name, **{k: v for k, v in evidence.items() if k != "vs_baseline"})
        return evidence

    def abandon_goal(self, name, reason):
        if name not in self.goals():
            raise SystemExit(f"unknown goal {name}")
        self._upsert("goals", name, status="abandoned", abandoned=now(), reason=reason)
        self.log_decision("goal_abandoned", goal=name, reason=reason)

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

    def snapshot(self):
        """Within the block, tasks() is read once: the dashboard's state and gates call it many times per request."""
        proj = self

        class _Snap:
            def __enter__(self):
                proj._snap = None
                proj._snap = proj.tasks()
                return proj

            def __exit__(self, *exc):
                proj._snap = None
        return _Snap()

    def tasks(self) -> list[dict]:
        if getattr(self, "_snap", None) is not None:
            return [dict(t) for t in self._snap]
        out, stall = [], self._stall()
        try:
            dirs = os.scandir(self.dir / "tasks")
        except OSError:
            return []
        for d in dirs:
            t = _read(Path(d.path) / "task.json") if d.is_dir() else None
            if t:
                out.append(self._liveness(t, stall))
        return sorted(out, key=lambda t: t.get("updated", 0), reverse=True)

    def task(self, tid: str) -> dict:
        t = _read(self.task_dir(tid) / "task.json")
        if not t:
            raise KeyError(tid)
        return self._liveness(t)

    def _stall(self) -> float:
        return 60 * self.config.get("stall_minutes", 10)

    def _liveness(self, t: dict, stall: float = None) -> dict:
        stall = self._stall() if stall is None else stall
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

    def _slice_field(self, slice_name: str, field: str):
        """One field of one frozen slice, read from the parsed file without copying every slice's id list: the
        dashboard asks this hundreds of times per poll on a project with a hundred slices."""
        try:
            return (_cached(self.dir / "slices.json", json.loads).get(slice_name) or {}).get(field)
        except (OSError, ValueError):
            return None

    def slice_evals(self, model: str, slice_name: str) -> list[dict]:
        """Every complete run of the model on the slice's current version, oldest first."""
        h = self._slice_field(slice_name, "hash")
        c = [t for t in self.evals() if t.get("model") == model and t.get("slice") == slice_name and t.get("slice_hash") == h
             and not t.get("superseded_by")]
        return sorted(c, key=lambda t: t.get("ended", 0))

    def supersede(self, model: str, slice_name: str, keep: str) -> list[str]:
        """Stop counting every earlier run of the model on the slice except `keep` (e.g. after a harness change).
        The runs stay in the Archive; gates and baselines skip them."""
        old = [t["id"] for t in self.slice_evals(model, slice_name) if t["id"] != keep]
        for tid in old:
            t = _read(self.task_dir(tid) / "task.json")
            _write(self.task_dir(tid) / "task.json", t | {"superseded_by": keep})
        if old:
            self.log_decision("supersede", model=model, slice=slice_name, keep=keep, runs=old)
        return old

    def latest_eval(self, model: str, slice_name: str) -> dict | None:
        c = self.slice_evals(model, slice_name)
        return c[-1] if c else None

    def score_runs(self, model: str, slice_name: str, reference_model: str | None = None) -> list[dict]:
        """The model's complete runs made under the same declared harness (`config.baseline_contract`) as the
        reference model's latest run on the slice (default: this model's own latest). Comparisons pass the candidate
        as the reference for both sides. A run that declares no contract matches only runs that declare none."""
        return same_contract(self.slice_evals(model, slice_name), self.latest_eval(reference_model or model, slice_name))

    def pooled_scores(self, model: str, slice_name: str, reference_model: str | None = None) -> dict[str, float]:
        """Per-id mean over compatible complete repeats; never pool across a declared harness change."""
        return per_id([r for t in self.score_runs(model, slice_name, reference_model) for r in self.rows(t["id"])],
                      continuous=self.is_continuous(slice_name))

    def slice_scale(self, slice_name: str, tasks: list[dict] | None = None) -> str:
        """"continuous" or "binary". The stored `scale`; for a slice frozen before `scale` existed, read off the newest
        complete run's scores on it (any model): every score 0 or 1 is binary, anything else continuous. The one rule
        the CLI, the gates and the dashboard share. `tasks` is the task list to infer from (default: every eval)."""
        stored = self._slice_field(slice_name, "scale")
        if stored:
            return stored
        # an inferred scale holds until slices.json changes (a long-lived dashboard must not keep a stale one); a slice
        # with no scored run yet is not cached, so its first run decides
        try:
            st = os.stat(self.dir / "slices.json")
            ver = (st.st_mtime_ns, st.st_size)
        except OSError:
            ver = None
        key = (str(self.dir), slice_name)
        hit = _SCALES.get(key)
        if hit and hit[0] == ver:
            return hit[1]
        runs = [t for t in (self.evals() if tasks is None else tasks)
                if t.get("kind") == "eval" and t.get("slice") == slice_name and t.get("ended") and t.get("status") == "done"]
        for t in sorted(runs, key=lambda t: t.get("ended") or 0, reverse=True):
            scale = scale_of_rows(self.rows(t["id"]))
            if scale:
                _SCALES[key] = (ver, scale)
                return scale
        return "binary"

    def versus_champion(self, model: str, slice_name: str) -> dict | None:
        """The model's paired delta vs the champion on one slice under the model's own latest harness, as the gate
        pairs it: its runs under that contract against the champion's runs under the same one. None for the champion
        itself or a model with no run; `state` "paired" (with paired()'s fields, runs and errors on each side),
        "champion_other_harness" (the champion ran the slice, never under this harness) or "no_champion_run"."""
        champ = self.champion()
        mine = self.score_runs(model, slice_name)
        if not champ or champ == model or not mine:
            return None
        theirs = self.score_runs(champ, slice_name, reference_model=model)
        out = dict(champion=champ, baseline_contract=contract_of(mine[-1]), cand_runs=len(mine), base_runs=len(theirs))
        if not theirs:
            return out | dict(state="champion_other_harness" if self.slice_evals(champ, slice_name) else "no_champion_run")
        cont = self.is_continuous(slice_name)
        crows = [r for t in mine for r in self.rows(t["id"])]
        brows = [r for t in theirs for r in self.rows(t["id"])]
        ce, be = pool_errors(crows), pool_errors(brows)
        sign = 1 if self.config.get("higher_is_better", True) else -1
        return out | dict(state="paired", cand_task=mine[-1]["id"], base_task=theirs[-1]["id"],
                          cand_errors=ce["pooled_errors"], base_errors=be["pooled_errors"],
                          cand_error_share=ce["error_share"], base_error_share=be["error_share"],
                          **paired(per_id(crows, cont), per_id(brows, cont), sign))

    def is_continuous(self, slice_name: str, tasks: list[dict] | None = None) -> bool:
        return self.slice_scale(slice_name, tasks) == "continuous"

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
                    # both sides pool only the runs made under the candidate's latest declared harness
                    cand_runs = self.score_runs(model_name, sl)
                    base_runs = self.score_runs(champ, sl, reference_model=model_name) if champ else []
                    ce, be = (cand_runs or [None])[-1], (base_runs or [None])[-1]
                    cont = self.is_continuous(sl)
                    if cont:  # margin / tolerance are a fraction of the champion's mean here, paired or not yet
                        c |= dict(relative=True, threshold_fraction=c["threshold"])
                    if contract_of(ce) is not None:
                        c["baseline_contract"] = contract_of(ce)
                    if champ == model_name:
                        c["state"] = "champion"
                        # the champion is not paired with itself: what it has on the slice, or that it has no run
                        sc = per_id([row for t in cand_runs for row in self.rows(t["id"])], cont) if cand_runs else {}
                        c |= dict(champion_runs=len(cand_runs), champion_task=ce["id"] if ce else None,
                                  champion_score=sum(sc.values()) / len(sc) if sc else None)
                    elif not champ:
                        c["state"] = "no_champion"
                    elif not be:
                        c["state"] = "need_baseline"
                        # the champion ran this slice, only under another harness: say so, never "not run"
                        other = len(self.slice_evals(champ, sl))
                        if other:
                            c["harness_mismatch"], c["champion_runs_other_harness"] = True, other
                        next_runs.append((champ, sl))
                    elif not ce:
                        c["state"] = "need_run"
                        next_runs.append((model_name, sl))
                    else:
                        crows = [row for t in cand_runs for row in self.rows(t["id"])]
                        brows = [row for t in base_runs for row in self.rows(t["id"])]
                        p = paired(per_id(crows, cont), per_id(brows, cont), sign)
                        ce_, be_ = pool_errors(crows), pool_errors(brows)
                        c |= dict(cand_rows=ce_["pooled_rows"], cand_error_share=ce_["error_share"],
                                  base_rows=be_["pooled_rows"], base_error_share=be_["error_share"],
                                  error_warn=any((x["error_share"] or 0) >= ERROR_SHARE_WARN for x in (ce_, be_)))
                        if cont and p.get("base") is not None:
                            # margin / tolerance are written for 0/1 slices; on a continuous one read them as a
                            # fraction of the champion's mean (0.05 on ~160 MB allows 8 MB), not as raw units
                            c["threshold"] *= abs(p["base"])
                        ok = p["delta"] is not None and (p["delta"] > c["threshold"] if chk["rule"] == "better" else p["delta"] >= c["threshold"])
                        c |= dict(state="pass" if ok else "fail", noisy=p["lo"] is not None and p["lo"] < 0 < p["hi"],
                                  cand_task=ce["id"], base_task=be["id"],
                                  cand_runs=len(cand_runs), base_runs=len(base_runs),
                                  cand_errors=ce_["pooled_errors"], base_errors=be_["pooled_errors"], **p)
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

    def baseline_slices(self) -> dict[str, list[str]]:
        """Every slice a champion is measured on, with what it measures: each hill's target and control, plus the
        datasets' full and random slices. These are the numbers any future candidate is compared against."""
        slices, roles = self.slices(), {}
        for k, h in self.hills().items():
            for role in ("target", "control"):
                if h.get(role) in slices:
                    roles.setdefault(h[role], []).append(f"hill {k} {role}")
        for k, v in slices.items():
            if v.get("kind") in ("full", "random"):
                roles.setdefault(k, []).append(v["kind"])
        return roles

    def baseline_plan(self, model: str) -> dict:
        """Where `model` stands on every baseline slice. A complete run at the slice's current hash is reused as it
        is (a promoted model already ran most of them on the ladder); only slices without one need a run."""
        have, need, roles, slices = {}, [], self.baseline_slices(), self.slices()
        mine = [t for t in self.evals() if t.get("model") == model and not t.get("superseded_by")]  # one scan, not one per slice
        for sl in roles:
            runs = sorted((t for t in mine if t.get("slice") == sl and t.get("slice_hash") == slices[sl]["hash"]),
                          key=lambda t: t.get("ended", 0))
            if runs:
                # the score the gates pair against: pooled over the runs under the latest run's harness
                pool = same_contract(runs, runs[-1])
                sc = per_id([r for t in pool for r in self.rows(t["id"])], self.is_continuous(sl))
                s = runs[-1].get("summary") or {}
                have[sl] = dict(task=runs[-1]["id"], score=sum(sc.values()) / len(sc) if sc else None,
                                latest_score=s.get("score"), n=s.get("n"), ended=runs[-1].get("ended"), runs=len(pool))
            else:
                need.append(sl)
        return dict(model=model, have=have, need=need, roles=roles)

    def baseline(self, model: str, dry: bool = False, rerun: bool = False, replace: bool = False, jobs: int = 1,
                 budget_s: float = None, say=print) -> dict:
        """Give `model` (normally a new champion) a run on every baseline slice. Its complete runs are reused; the
        rest run `baseline_cmd` from research.json ({model} and {slice} replaced, shell-quoted) under one Baseline
        task, `jobs` at a time. Without baseline_cmd the slices are only listed. `rerun` runs every slice again
        (pooled with earlier runs); `replace` does too, and each fresh complete run supersedes the earlier ones.
        Returns the plan after the work, plus `ran` (slices that got a fresh run) when anything was run."""
        plan, cmd, slices = self.baseline_plan(model), self.config.get("baseline_cmd"), self.slices()
        rerun = rerun or replace
        todo = list(plan["roles"]) if rerun else plan["need"]
        nh = len(plan["have"])
        if replace:
            say(f"baseline for {model}: {len(todo)} slices to run; the runs on {nh} of them are replaced once each fresh run completes")
        elif rerun:
            say(f"baseline for {model}: {len(todo)} slices to run; {nh} of them already run, pooled with the fresh runs")
        else:
            say(f"baseline for {model}: {nh} of {len(plan['roles'])} slices already run, {len(todo)} to run")
        what = lambda sl: ", ".join(plan["roles"][sl])
        verb = "would run" if dry and cmd else "run" if cmd else "missing"
        again = "replace" if replace else "rerun"  # a slice that has runs is never "missing"
        again = f"would {again}" if dry and cmd else again if cmd else f"to {again}"
        for sl, h in plan["have"].items():
            score = "—" if h["score"] is None else f"{h['score']:.3f}"
            pooled = f", {h['runs']} runs pooled" if h["runs"] > 1 else ""
            say(f"  {again if rerun else 'reused':<13} {sl:<28} {score}  n={h['n']}  {what(sl)}  ({h['task']}, {_ago(h['ended'])}{pooled})")
        for sl in plan["need"]:
            say(f"  {verb:<13} {sl:<28} n={slices[sl]['n']}  {what(sl)}")
        if not todo or dry:
            return plan
        if not cmd:
            say('to run these automatically, set "baseline_cmd" in research.json, e.g. '
                '"python eval.py --model {model} --slice {slice}"; or run each with arx.evaluate / arx run')
            self.log_decision("baseline", model=model, reused=len(plan["have"]), ran=0, missing=plan["need"])
            return plan
        desc = (f"Re-run champion {model} on every hill and dataset slice ({len(todo)})." if rerun else
                f"Run champion {model} on each hill and dataset slice it has no complete run on ({len(todo)}); "
                f"{len(plan['have'])} existing runs reused.")
        lock, finished, fresh = threading.Lock(), [], []
        with Task(self, "baseline", f"Baseline {model}", desc, model=model, total=len(todo), budget_s=budget_s,
                  config=dict(baseline_cmd=cmd, jobs=jobs, rerun=rerun, replace=replace)) as t:
            def one(sl):
                if not t.ok():
                    return t.note(f"{sl}: skipped, time budget spent", "warn")
                t.note(f"{sl} ({what(sl)}): running")
                before = {e["id"] for e in self.slice_evals(model, sl)}
                # its own process group, so a timeout stops the whole command, not just the shell
                proc = subprocess.Popen(cmd.replace("{model}", shlex.quote(model)).replace("{slice}", shlex.quote(sl)),
                                        shell=True, cwd=self.root, start_new_session=True)
                try:  # the command's evals nest under this task ($ARX_PARENT) and share its budget
                    code = proc.wait(timeout=t.left())
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait()
                    return t.note(f"{sl}: stopped, time budget spent", "warn")
                if code:
                    t.note(f"{sl}: baseline_cmd exited {code}", "error")
                new = [e for e in self.slice_evals(model, sl) if e["id"] not in before]
                if replace and new:  # the old runs stop counting only once a fresh complete one exists
                    gone = self.supersede(model, sl, new[-1]["id"])
                    if gone:
                        t.note(f"{sl}: {len(gone)} earlier run(s) superseded by {new[-1]['id']}")
                with lock:
                    finished.append(sl)
                    fresh.extend([sl] if new else [])
                    t.progress(len(finished))

            with ThreadPoolExecutor(max(1, jobs)) as pool:
                list(pool.map(one, todo))
            after = self.baseline_plan(model)
            t.note(f"still missing: {', '.join(after['need'])}" if after["need"] else f"every slice has a {model} baseline",
                   "warn" if after["need"] else "info")
            t.meta["summary"] = dict(reused=0 if rerun else len(plan["have"]), ran=len(fresh), missing=len(after["need"]))
            self.log_decision("baseline", model=model, task=t.id, reused=t.meta["summary"]["reused"], ran=len(fresh),
                              missing=after["need"])
            t.check()  # a spent budget ends the card as `budget`, not `done`
        say(f"still missing: {', '.join(after['need'])} (baseline_cmd must record a complete eval of {{model}} on {{slice}})"
            if after["need"] else f"done: {model} has a baseline on all {len(after['roles'])} slices ({len(fresh)} run now)")
        return after | dict(ran=len(fresh))

    def promote(self, model_name: str, force: bool = False, baseline: bool = True, **baseline_kw) -> dict | None:
        """Make the model champion, then (unless `baseline=False`) baseline it on every hill: see `baseline()`.
        Returns the baseline result."""
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
        return self.baseline(model_name, **baseline_kw) if baseline else None


def _ago(t) -> str:
    if not t:
        return "age unknown"
    d = now() - t
    if d < 60:
        return "just now"
    return f"{d / 86400:.0f}d ago" if d >= 86400 else f"{d / 3600:.0f}h ago" if d >= 3600 else f"{d / 60:.0f}m ago"


# ---------------------------------------------------------------- live tasks

_open: list["Task"] = []  # tasks running in this process, innermost last; new tasks nest under the top one

# ---------- system vitals: one sampler thread per process writes GPU readings into every task open in it.
# Rows carry `sys: true` and never touch `last`, the step counter or the heartbeat (a hung job must still go stalled).
# Off with ARX_SAMPLE=0; skipped silently without nvidia-smi. ARX_SAMPLE_CMD swaps the command (tests, other tools):
# it must print "util %, used MiB, total MiB" per GPU, one line each, like nvidia-smi's csv.
_sampled: list["Task"] = []
_sampler_lock = threading.Lock()
_sampler: threading.Thread | None = None


def _gpu_cmd() -> list[str] | None:
    if os.environ.get("ARX_SAMPLE_CMD"):
        return shlex.split(os.environ["ARX_SAMPLE_CMD"])
    import shutil
    exe = shutil.which("nvidia-smi")
    return [exe, "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"] if exe else None


def gpu_sample() -> dict | None:
    """One reading over every GPU: mean utilisation (%), memory used and total (GB). None when nothing answers."""
    cmd = _gpu_cmd()
    if not cmd:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        rows = [[float(x) for x in line.split(",")[:3]] for line in out.strip().splitlines() if line.count(",") >= 2]
    except Exception:
        return None
    if not rows:
        return None
    return dict(gpu_util=round(sum(r[0] for r in rows) / len(rows), 1), gpu_mem_gb=round(sum(r[1] for r in rows) / 1024, 2),
                gpu_mem_total_gb=round(sum(r[2] for r in rows) / 1024, 2), gpus=len(rows))


def _sample_loop():
    global _sampler
    period = max(1.0, float(os.environ.get("ARX_SAMPLE_S") or 15))
    ok, misses = False, 0
    while True:
        time.sleep(period)  # first reading after one period: a short-lived `arx task start` never samples
        with _sampler_lock:
            tasks = [t for t in _sampled if t.meta.get("status") == "running"]
            if not tasks or (not ok and misses >= 3):  # nothing open, or the command never answers: stop quietly
                _sampled.clear()
                _sampler = None
                return
        s = gpu_sample()
        ok, misses = ok or bool(s), misses + (not s)
        for t in tasks if s else ():
            try:
                t._sys(s)
            except Exception:
                pass


def _sample(task: "Task") -> None:
    global _sampler
    if os.environ.get("ARX_SAMPLE", "1") == "0" or not _gpu_cmd():
        return
    with _sampler_lock:
        _sampled.append(task)
        if _sampler is None:
            _sampler = threading.Thread(target=_sample_loop, name="arx-sampler", daemon=True)
            _sampler.start()


class BudgetExceeded(Exception):
    """Raised by `Task.check()` once a task (or one of its ancestors) has run out of time."""


class Task:
    """A unit of visible work. Shows on the Workbench while running, in the Archive after.

    `parent` nests this task under another card. Left out, it is the innermost task still running in this process,
    else $ARX_PARENT (exported to child processes while a task runs), so a loop's evals sit under the loop.

    `budget_s` caps wall-clock time. `t.left()` is the seconds remaining here or in any ancestor, whichever is
    tighter, so a sub-task never outlives its parent's budget. Loop on `while t.ok():` or call `t.check()`.
    """

    def __init__(self, project: Project, kind: str, title: str, description: str = None, model: str = None,
                 slice: str = None, agent: str = None, total: int = None, links: dict = None, config: dict = None,
                 tid: str = None, parent: str = None, budget_s: float = None):
        self.p = project
        self.id = tid or self._claim(project, kind)
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
                             command=" ".join(sys.argv), budget_s=budget_s)
            self._flush()
            if kind != "eval":  # evals are leaves; anything else can hold sub-tasks
                self._env = os.environ.get("ARX_PARENT")
                _open.append(self)
                os.environ["ARX_PARENT"] = self.id
            try:
                _sample(self)
            except Exception:  # vitals are a nicety; they never stop a task from starting
                pass
        else:
            self.meta = _read(self.dir / "task.json")

    @staticmethod
    def _claim(project: Project, kind: str) -> str:
        """A fresh id, its directory made atomically: two tasks started in the same second never share one."""
        while True:
            tid = f"{time.strftime('%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:4]}"
            d = project.task_dir(tid)
            d.parent.mkdir(parents=True, exist_ok=True)
            try:
                d.mkdir()
                return tid
            except FileExistsError:
                continue

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

    def left(self) -> float | None:
        """Seconds left: the tightest over this task and its ancestors. None = no time budget anywhere."""
        out, m = None, self.meta
        while m:
            if m.get("budget_s") is not None:
                rem = m["budget_s"] - (now() - m["created"])
                out = rem if out is None else min(out, rem)
            tid = m.get("parent")
            live = next((o for o in _open if o.id == tid), None)
            m = live.meta if live else _read(self.p.task_dir(tid) / "task.json") if tid else None
        return out

    def ok(self) -> bool:
        left = self.left()
        return left is None or left > 0

    def check(self):
        """Raise BudgetExceeded once time is up. The task finishes as `budget` instead of `failed`."""
        if not self.ok():
            raise BudgetExceeded(f"{self.id}: time budget spent")

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

    def _sys(self, reading: dict):
        """A system reading (see _sample_loop): appended to metrics with `sys: true`; no heartbeat, `last` untouched."""
        with self._lock:
            if self.meta.get("status") == "running":
                _append(self.dir / "metrics.jsonl", dict(t=now(), step=self._step, sys=True, **reading))

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
                sl = self.meta["slice"]
                # a slice frozen without `scale` and never run before: its first run's own scores decide
                cont = self.p.is_continuous(sl) if (self.p._slice_field(sl, "scale") or any(
                    t.get("slice") == sl for t in self.p.evals())) else scale_of_rows(rows) == "continuous"
                self.meta["summary"] = summarize(rows, cont) | {"missing": len(want - got)}
            if summary:
                self.meta["summary"] = self.meta.get("summary", {}) | summary
            self.meta["status"], self.meta["ended"] = status, now()
            self._flush()
        with _sampler_lock:
            if self in _sampled:
                _sampled.remove(self)
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
        if et is BudgetExceeded:
            self.note(str(ev), "warn")
            self.finish("budget")
            return ev.args[0].startswith(self.id + ":")  # swallow our own; an ancestor's keeps unwinding to it
        if et:
            self.note(f"{et.__name__}: {ev}", "error")
        self.finish("failed" if et else "done")
        return False


def evaluate(project: Project, model: str, slice: str, run_one, workers: int = 8, deadline_s: float | None = None,
             title: str = None, description: str = None, agent: str = None, repeats: int = 1, config: dict = None,
             parent: str = None) -> Task:
    """Run `run_one(example_id) -> {"score": float, "cost": .., "latency_s": .., ...}` on every id of a slice.

    Exceptions and deadline overruns become error rows (score 0). The deadline also shrinks to whatever time the
    parent task has left. The card shows progress and running score live.
    """
    sl = project.slice(slice)
    ids = [i for i in sl["ids"] for _ in range(repeats)]
    if not title:  # how the Workbench says it: "LoRA r16 on dev60", not the raw ids
        from .features import model_label  # features imports nothing from core; imported here to keep core light
        title = f"{model_label(project, model) or model} on {sl['name'].split('/', 1)[-1]}"
    t = Task(project, "eval", title, description, model=model, slice=sl["name"],
             agent=agent, total=len(ids), parent=parent, budget_s=deadline_s,  # a budget only when the caller set one
             config=(config or {}) | {"workers": workers, "deadline_s": deadline_s or 3600, "repeats": repeats})
    end = now() + (deadline_s or 3600)  # with no budget, still stop after an hour; a budget or a parent's may be tighter
    start, done, total_score, stop = now(), 0, 0.0, False
    pool = ThreadPoolExecutor(workers)
    queue, futs = list(reversed(ids)), {}
    try:
        while queue or futs:
            stop = stop or not t.ok() or now() >= end
            while queue and not stop and len(futs) < workers:  # submit lazily so a spent budget stops new calls
                i = queue.pop()
                futs[pool.submit(_timed, run_one, i)] = i
            if not futs:
                break
            secs = t.left()
            secs = end - now() if secs is None else min(secs, end - now())
            fin, _ = wait(futs, timeout=None if secs is None else max(0.0, secs), return_when=FIRST_COMPLETED)
            if not fin:
                stop = True
                break
            for f in fin:
                futs.pop(f)
                row = f.result()
                t.add_row(row)
                done += 1
                total_score += 0.0 if row.get("error") else float(row.get("score") or 0)
                t.progress(done)
                t.log(step=done, running_score=total_score / done, latency_s=row.get("latency_s"))
                if sys.stderr.isatty() or done == len(ids) or done % 50 == 0:
                    sys.stderr.write(f"\r{t.id} {done}/{len(ids)} score={total_score / done:.3f} {now() - start:.0f}s")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        sys.stderr.write("\n")
    if stop:
        t.note(f"deadline reached; {len(futs) + len(queue)} unfinished examples count as errors", "warn")
        for i in [*futs.values(), *queue]:
            t.add_row(dict(id=str(i), score=0.0, error="deadline", latency_s=round(now() - start, 3)))
    t.finish("done")
    return t


def _timed(fn, i):
    t0 = time.time()
    try:
        out = fn(i) or {}
        return dict(id=str(i), latency_s=round(time.time() - t0, 3)) | out | {"id": str(i)}
    except Exception as e:  # an example that crashes is wrong, never skipped
        return dict(id=str(i), score=0.0, error=f"{type(e).__name__}: {e}"[:300], latency_s=round(time.time() - t0, 3))


def contract_of(task: dict | None):
    """The harness a run declares it was made with (`config.baseline_contract`); None when it declares none."""
    return ((task or {}).get("config") or {}).get("baseline_contract")


def same_contract(runs: list[dict], reference: dict | None) -> list[dict]:
    """The runs made under the reference run's declared harness. Never pools across a declared harness change: a
    reference without a contract keeps only the runs without one. No reference run: every run."""
    if reference is None:
        return runs
    c = contract_of(reference)
    return [t for t in runs if contract_of(t) == c]


def latest_shared(mine: list[dict], theirs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Both sides' runs under the most recent declared harness they both ran (newest of `mine` first), for a
    comparison that is not a gate: a goal's champion vs its baseline. ([], []) when they share none."""
    key = lambda t: json.dumps(contract_of(t), sort_keys=True, default=str)
    have = {key(t) for t in theirs}
    for t in reversed(mine):
        if key(t) in have:
            k = key(t)
            return [x for x in mine if key(x) == k], [x for x in theirs if key(x) == k]
    return [], []


def goal_evidence_status(status, baseline_exists):
    """One frozen achievement and explicit comparison scope for dashboard and references."""
    sign = 1 if status.get("higher_is_better", True) else -1
    if status.get("status") == "achieved" and status.get("evidence"):
        frozen = status["evidence"]
        status["current_observation"] = {key: status[key] for key in
                                         ("model", "value", "task", "runs", "met", "gap", "vs_baseline")}
        for key in ("model", "value", "task", "runs", "n", "vs_baseline"):
            status[key] = frozen.get(key)
        value = frozen.get("value")
        status["met"] = value is not None and sign * (value - status["target"]) >= 0
        status["gap"] = None if value is None else sign * (status["target"] - value)
    if status.get("model") and status.get("model") == status.get("baseline"):
        status["comparison_state"] = "same_model"
    elif status.get("kpi", "score") != "score":
        status["comparison_state"] = "unpaired"  # cost and latency are per-run summaries: nothing to pair
    elif status.get("vs_baseline", None) and status["vs_baseline"].get("n"):
        status["comparison_state"] = "paired"
    elif not baseline_exists:
        status["comparison_state"] = "missing_baseline"
    elif status.get("value") is None:
        status["comparison_state"] = "missing_measurement"
    else:
        status["comparison_state"] = "different_harness"
    return status
