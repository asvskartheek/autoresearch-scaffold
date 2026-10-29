"""The paper (complete reference) for one model, built from the ledger alone, plus the explainer kit.

Routes (see features.py for the contracts):
  GET /reference/[<model>]     the page (web/reference.html); it fetches the data route below
  GET /api/reference?model=&vs=  everything the page draws: system, lineage, every slice with paired deltas,
                               the gate ladder, per-id fixed/broke, failure gallery, cost/latency, unknowns, reproduce
  GET /explain-kit.js          the explainer toolkit (web/explain-kit.js)

Default model: the champion. Default comparator: the model's parent (the system it had to beat), else the baseline of
the goal it serves. Nothing here writes to the ledger.
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
import random
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from . import features
from .core import per_id
from .readable import readable

WEB = Path(__file__).with_name("web")
HTML = "text/html; charset=utf-8"
KIND_ORDER = {"full": 0, "random": 1, "control": 2, "dev": 3, "synthetic": 4}
CORE_FIELDS = ("created", "parent", "hill", "change", "title", "status", "reason", "promoted", "links", "updated")
MAX_IDS = 40_000  # per-id cells sent to the page, over every slice


def _r(x, d=6):
    return round(x, d) if isinstance(x, float) and math.isfinite(x) else (None if isinstance(x, float) else x)


def _txt(s):
    return readable(s) if isinstance(s, str) else s


_PATH = re.compile(r"(?<![\w:/.~])(?:~/|/)(?:[^\s/'\"]+/)+([^\s/'\",;)]+)")
_DICT = re.compile(r"\{'[^{}]*\}")


def _num(v):
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _short_dict(m):
    """A Python dict pasted into a note, as a short phrase: a paired result reads as delta, CI and n."""
    try:
        d = ast.literal_eval(m.group(0))
    except (ValueError, SyntaxError):
        return "{…}"
    if not isinstance(d, dict):
        return "{…}"
    if all(isinstance(d.get(k), (int, float)) for k in ("delta", "lo", "hi")):
        pts = all(abs(d[k]) <= 1 for k in ("delta", "lo", "hi"))
        f = (lambda x: f"{x * 100:+.1f}".replace("-", "−")) if pts else (lambda x: f"{x:+.4g}".replace("-", "−"))
        out = f"{f(d['delta'])}{' pts' if pts else ''} (90% CI {f(d['lo'])} to {f(d['hi'])})"
        return out + (f", n {d['n']}" if d.get("n") else "")
    items = [f"{k} {_num(v)}" for k, v in d.items() if isinstance(v, (int, float, str)) and len(str(v)) < 40][:4]
    return ", ".join(items) or "{…}"


def clean_note(s, cap=240):
    """A ledger note fit to share: local paths cut to their file name, dict dumps to a phrase, length capped."""
    if not isinstance(s, str):
        return s
    s = _DICT.sub(_short_dict, _PATH.sub(lambda m: m.group(1), s))
    return s if len(s) <= cap else s[:cap - 1].rstrip() + "…"


class _Index:
    """One pass over the ledger: complete runs per (model, slice) at the slice's current hash, rows read once."""

    def __init__(self, p):
        self.p = p
        self.slices = p.slices()
        self.runs: dict[tuple, list] = {}
        for t in p.evals():
            sl = self.slices.get(t.get("slice"))
            if not sl or t.get("slice_hash") != sl.get("hash") or t.get("superseded_by"):
                continue
            self.runs.setdefault((t.get("model"), t["slice"]), []).append(t)
        for v in self.runs.values():
            v.sort(key=lambda t: t.get("ended", 0))
        self._rows: dict[str, list] = {}
        self._pooled: dict[tuple, dict] = {}
        self.pairs: dict[tuple, dict | None] = {}

    def has(self, m, sl):
        return bool(m) and (m, sl) in self.runs

    def latest(self, m, sl):
        r = self.runs.get((m, sl))
        return r[-1] if r else None

    def rows(self, tid):
        if tid not in self._rows:
            self._rows[tid] = self.p.rows(tid)
        return self._rows[tid]

    def pooled(self, m, sl):
        k = (m, sl)
        if k not in self._pooled:
            self._pooled[k] = per_id([r for t in self.runs.get(k, []) for r in self.rows(t["id"])])
        return self._pooled[k]

    def slices_of(self, m):
        return [sl for (mm, sl) in self.runs if mm == m]


def fast_paired(cand: dict, base: dict, sign: int = 1, iters: int = 2000) -> dict:
    """core.paired with the same seed and draws, summed with fsum instead of statistics.mean (about 20x faster;
    equal to it within one ulp)."""
    ids = sorted(set(cand) & set(base))
    if not ids:
        return dict(n=0, delta=None, lo=None, hi=None, wins=0, losses=0)
    d = [sign * (cand[i] - base[i]) for i in ids]
    n, rng = len(d), random.Random(0)
    boots = sorted(math.fsum(rng.choices(d, k=n)) / n for _ in range(iters))
    return dict(n=n, delta=math.fsum(d) / n, lo=boots[int(0.05 * iters)], hi=boots[int(0.95 * iters) - 1],
                wins=sum(x > 0 for x in d), losses=sum(x < 0 for x in d),
                cand=math.fsum(cand[i] for i in ids) / n, base=math.fsum(base[i] for i in ids) / n)


_PAIRS: dict = {}  # (root, slice, sign, run ids of each side) -> fast_paired; the same pairs recur across papers


def _pair(ix, m, b, sl, sign):
    key = (str(ix.p.root), sl, sign, tuple(t["id"] for t in ix.runs[(m, sl)]), tuple(t["id"] for t in ix.runs[(b, sl)]))
    hit = _PAIRS.get(key)
    if hit is None:
        if len(_PAIRS) > 4096:
            _PAIRS.clear()
        hit = _PAIRS[key] = fast_paired(ix.pooled(m, sl), ix.pooled(b, sl), sign)
    return dict(hit)


def _paired(ix, m, b, sl, sign):
    if not (ix.has(m, sl) and ix.has(b, sl)) or m == b:
        return None
    key = (m, b, sl, sign)
    if key not in ix.pairs:
        d = _pair(ix, m, b, sl, sign)
        if d.get("delta") is None:
            ix.pairs[key] = None
        else:
            d = {k: _r(v) for k, v in d.items()}
            d["noisy"] = d["lo"] is not None and d["lo"] < 0 < d["hi"]
            ix.pairs[key] = d
    return dict(ix.pairs[key]) if ix.pairs[key] else None


def _ancestors(models, name):
    chain, seen = [], set()
    while name and name in models and name not in seen:
        seen.add(name)
        chain.append(name)
        par = models[name].get("parent")
        name = par if par != name else None
    return chain[::-1]  # root first


def _main_slice(p, ix, model, goals):
    mine = set(ix.slices_of(model))
    for g in goals.values():
        if g.get("status") == "open" and g.get("slice") in mine:
            return g["slice"]
    for g in goals.values():
        if g.get("slice") in mine:
            return g["slice"]
    full = f"{p.config.get('primary_dataset')}/full"
    if full in mine:
        return full
    fulls = [s for s in mine if ix.slices[s].get("kind") == "full"]
    pool = fulls or list(mine)
    return max(pool, key=lambda s: ix.slices[s].get("n") or 0) if pool else None


def _ladder(p, ix, model, base, sign):
    """The ladder walked for `model` against `base` (not only the current champion): how the model earned its place."""
    m = p.models().get(model) or {}
    rungs, blocked = [], False
    for rung in p.config.get("ladder", []):
        checks = []
        for chk in rung.get("checks", []):
            if chk.get("manual"):
                checks.append(dict(slice=chk.get("slice", "manual"), rule="manual", state="needs_review"))
                continue
            try:
                targets = p._resolve(chk["slice"], m)
            except SystemExit:
                targets = []
            for sl in targets:
                thr = chk.get("margin", 0) if chk["rule"] == "better" else -chk.get("tolerance", 0)
                c = dict(slice=sl, rule=chk["rule"], threshold=thr, ref=chk["slice"])
                if not base:
                    c["state"] = "no_comparator"
                elif not ix.has(base, sl):
                    c["state"] = "need_baseline"
                elif not ix.has(model, sl):
                    c["state"] = "need_run"
                else:
                    d = _paired(ix, model, base, sl, sign)
                    ok = d and (d["delta"] > thr if chk["rule"] == "better" else d["delta"] >= thr)
                    c |= dict(state="pass" if ok else "fail", **(d or {}))
                checks.append(c)
        states = {c["state"] for c in checks}
        if blocked:
            status = "locked"
        elif not checks:
            status = "skipped"
        elif states <= {"pass"}:
            status = "pass"
        elif "fail" in states:
            status, blocked = "fail", True
        else:
            status, blocked = "pending", True
        rungs.append(dict(rung=rung.get("rung"), status=status, checks=checks))
    return rungs


def _promotion(p, ix, model):
    """The gate a model was promoted on, from its promote decision: the same checks and numbers the model page shows.
    A record written before run counts were kept gets them back from the runs that had ended by then."""
    rec = None
    f = p.dir / "decisions.jsonl"
    if not f.exists():
        return None
    for line in f.read_text().splitlines():
        if '"promote"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("kind") == "promote" and d.get("model") == model and isinstance(d.get("gate"), dict):
            rec = d
    if not rec:
        return None
    t, old = rec.get("t") or 0, rec.get("replaced")
    upto = lambda m, sl: sum(1 for r in ix.runs.get((m, sl), []) if (r.get("ended") or 0) <= t) or None
    rungs = []
    for rg in rec["gate"].get("rungs") or []:
        if not isinstance(rg, dict):
            continue
        checks = []
        for c in rg.get("checks") or []:
            if not isinstance(c, dict):
                continue
            c = {k: v for k, v in c.items() if k not in ("trace",)}
            if c.get("delta") is not None:
                c.setdefault("cand_runs", upto(model, c.get("slice")))
                c.setdefault("base_runs", upto(old, c.get("slice")))
            c.setdefault("ref", c.get("slice"))
            checks.append({k: _r(v) for k, v in c.items()})
        rungs.append(dict(rung=rg.get("rung"), status=rg.get("status"), checks=checks))
    return dict(t=t, replaced=old, rungs=rungs)


def _norm(x) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(x or "").lower()).strip("-")


def papers_for(p, model: str) -> list[dict]:
    """The hand-written papers about this model: one named after it (`champion-<model>` too), then its hill's paper."""
    from . import papers
    me, hill = _norm(model), (p.models().get(model) or {}).get("hill")
    out = []
    for n in papers.names(p):
        meta = papers._read(papers.pdir(p, n) / "meta.json", {})
        nn = _norm(n)
        if meta.get("model") == model or nn == me or nn.endswith("-" + me):
            out.insert(0, dict(name=n, title=papers.title_of(p, n, meta), kind="model"))
        elif hill and (meta.get("hill") == hill or (n == hill and not meta.get("goal"))):
            out.append(dict(name=n, title=papers.title_of(p, n, meta), kind="hill"))
    return out


def _flat(d, pre="", out=None, depth=0):
    out = [] if out is None else out
    for k, v in (d or {}).items():
        key = f"{pre}{k}"
        if isinstance(v, dict) and depth < 2:
            _flat(v, key + ".", out, depth + 1)
        else:
            s = v if isinstance(v, (int, float, bool)) or v is None else (json.dumps(v, default=str) if not isinstance(v, str) else v)
            out.append([key, s if not isinstance(s, str) else s[:400]])
    return out


def _goal_status(p, ix, name, g, champ):
    """core.goal_status from the index, with fast_paired: the same fields, a fraction of the time."""
    sl, kpi, sign = g["slice"], g.get("kpi", "score"), 1 if g.get("higher_is_better", True) else -1
    model = (g.get("evidence") or {}).get("model") if g.get("status") == "achieved" else champ
    ev = ix.latest(model, sl) if model else None
    value = None
    if ev:
        if kpi == "score":
            sc = ix.pooled(model, sl)
            value = sum(sc.values()) / len(sc) if sc else None
        else:
            value = (ev.get("summary") or {}).get(kpi)
    vs = None
    if kpi == "score" and model and g.get("baseline") and g["baseline"] != model and ix.has(g["baseline"], sl):
        vs = _pair(ix, model, g["baseline"], sl, sign)
    slr = ix.slices.get(sl) or {}
    cur = slr.get("hash")
    return dict(g, name=name, model=model, value=value, task=ev["id"] if ev else None,
                runs=len(ix.runs.get((model, sl), [])) if model else 0,
                met=value is not None and sign * (value - g["target"]) >= 0,
                gap=None if value is None else sign * (g["target"] - value), vs_baseline=vs,
                hills={k: h.get("status") for k, h in p.hills().items() if h.get("goal") == name},
                slice_changed=bool(cur and g.get("slice_hash") and cur != g["slice_hash"]),
                scale=slr.get("scale") or "binary", unit=slr.get("unit"), metric=slr.get("metric"))


def _signature(p) -> tuple:
    """What the paper depends on: the ledger files and every task's task.json, by mtime and size."""
    out = []
    for f in [p.root / "research.json", *sorted(p.dir.glob("*.json")), p.dir / "decisions.jsonl", p.dir / "papers"]:
        try:
            st = f.stat()
            out.append((f.name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    try:
        with os.scandir(p.dir / "tasks") as it:
            for d in it:
                try:
                    st = os.stat(os.path.join(d.path, "task.json"))
                    out.append((d.name, st.st_mtime_ns, st.st_size))
                except OSError:
                    pass
    except OSError:
        pass
    return tuple(sorted(out))


_CACHE: dict = {}  # (root, model, vs) -> (signature, paper); the page and its pickers ask for the same papers again
_LOCK = threading.Lock()
_BUSY: dict = {}


def build(p, model: str | None = None, vs: str | None = None, cache: bool = True) -> dict:
    """The paper's data. Cached per (project, model, vs) until a ledger file or a task changes; do not mutate it."""
    if not cache:
        with p.snapshot():
            return _build(p, model, vs)
    key = (str(p.root), model or "", vs or "")
    with _LOCK:
        lock = _BUSY.setdefault(key, threading.Lock())
    with lock:  # a second request for the same paper waits for the first build instead of repeating it
        sig = _signature(p)
        hit = _CACHE.get(key)
        if hit and hit[0] == sig:
            return hit[1]
        with p.snapshot():
            d = _build(p, model, vs)
        with _LOCK:
            if len(_CACHE) > 64:
                _CACHE.clear()
            _CACHE[key] = (sig, d)
    return d


def prewarm(p, model=None, vs=None):
    """Start building a paper in the background, so the page's data request finds it ready or half done."""
    def run():
        try:
            build(type(p)(p.root), model, vs)  # its own Project: snapshot() state is per instance
        except Exception:  # noqa: BLE001 - the data route reports the real error
            pass
    threading.Thread(target=run, daemon=True).start()


def _build(p, model, vs):
    cfg, models, hills = p.config, p.models(), p.hills()
    champ = p.champion()
    ix = _Index(p)
    if not model:
        model = champ or next((k for k, _ in sorted(((m, max(t.get("ended", 0) for t in r)) for (m, _s), r in ix.runs.items()),
                                                     key=lambda x: -x[1])), None)
    if not model or model not in models:
        raise KeyError(model)
    me = models[model]
    sign = 1 if cfg.get("higher_is_better", True) else -1
    goals = {}
    for g, rec in p.goals().items():
        try:
            goals[g] = _goal_status(p, ix, g, rec, champ)
        except (KeyError, TypeError):
            goals[g] = dict(rec, name=g)
    # comparator: what this model had to beat, i.e. the nearest ancestor measured on the main slice
    par = me.get("parent") if me.get("parent") != model else None
    main = _main_slice(p, ix, model, goals)
    up = _ancestors(models, model)[:-1][::-1]  # parent first
    if vs and vs in models and vs != model:
        base = vs
    else:
        base = next((a for a in up if ix.has(a, main)), None) or next((a for a in up if ix.slices_of(a)), None)
        if not base:
            base = next((g.get("baseline") for g in goals.values() if g.get("baseline") and g["baseline"] != model
                         and ix.slices_of(g["baseline"])), None)
        if not base and champ and champ != model:
            base = champ

    # every slice this model ran, with paired deltas vs the comparator and the field of every other try
    roles = p.baseline_slices()
    results, budget = [], MAX_IDS
    for sl in sorted(ix.slices_of(model), key=lambda s: (s != main, KIND_ORDER.get(ix.slices[s].get("kind"), 9),
                                                         -(ix.slices[s].get("n") or 0), s)):
        meta = ix.slices[sl]
        last = ix.latest(model, sl)
        summ = last.get("summary") or {}
        pm = ix.pooled(model, sl)
        bm = ix.pooled(base, sl) if ix.has(base, sl) else {}
        raw = {0.0 if x.get("error") else float(x.get("score") or 0) for t in ix.runs[(model, sl)] for x in ix.rows(t["id"])}
        scale = meta.get("scale") or ("binary" if raw <= {0.0, 1.0} else "continuous")  # per run, not pooled means
        bsum = (ix.latest(base, sl) or {}).get("summary") or {}
        field = []
        for (mm, ss), runs in ix.runs.items():
            if ss == sl:
                sc = ix.pooled(mm, ss)
                field.append([mm, _r(sum(sc.values()) / len(sc) if sc else None), (models.get(mm) or {}).get("status"),
                              [t["id"] for t in runs]])
        ids = [str(i) for i in meta.get("ids", [])]
        cells = None
        if ids and budget >= len(ids):
            budget -= len(ids)
            cells = dict(m=[_r(pm.get(i), 4) for i in ids], b=[_r(bm.get(i), 4) for i in ids] if bm else None)
        results.append(dict(
            slice=sl, kind=meta.get("kind"), n=meta.get("n"), hash=meta.get("hash"), scale=scale, unit=meta.get("unit"),
            metric=meta.get("metric"), description=_txt(meta.get("description")), url=meta.get("url"), hill=meta.get("hill"),
            roles=roles.get(sl, []), runs=len(ix.runs[(model, sl)]), task=last["id"], ended=last.get("ended"),
            run_ids=[t["id"] for t in ix.runs[(model, sl)]],
            score=_r(sum(pm.values()) / len(pm) if pm else None), scored=len(pm),
            right=round(sum(pm.values()), 1) if scale == "binary" else None,  # 96.6 of 100 when runs are pooled
            errors=summ.get("errors"), cost=_r(summ.get("cost")), cost_total=_r(summ.get("cost_total")),
            latency_p50=_r(summ.get("latency_p50")), latency_p95=_r(summ.get("latency_p95")),
            base=dict(task=(ix.latest(base, sl) or {}).get("id"), runs=len(ix.runs.get((base, sl), [])),
                      run_ids=[t["id"] for t in ix.runs.get((base, sl), [])],
                      cost=_r(bsum.get("cost")), latency_p50=_r(bsum.get("latency_p50")),
                      latency_p95=_r(bsum.get("latency_p95"))) if bm else None,
            vs=_paired(ix, model, base, sl, sign), field=sorted(field, key=lambda f: -(f[1] or -1e18) * sign), ids=ids if cells else None,
            cells=cells))

    # lineage: root -> model, each step's delta vs its own parent on the main slice, and the siblings that lost
    chain = _ancestors(models, model)
    lineage = []
    for name in chain:
        m = models[name]
        pp = m.get("parent") if m.get("parent") != name else None
        sib = [dict(name=k, title=_txt(o.get("title")), status=o.get("status"), reason=_txt(o.get("reason")),
                    change=_txt(o.get("change")), hill=o.get("hill"))
               for k, o in models.items() if pp and o.get("parent") == pp and k != name and k not in chain]
        step_d = None
        if pp:
            sl = main if ix.has(name, main) and ix.has(pp, main) else next(
                (s for s in ix.slices_of(name) if ix.has(pp, s) and ix.slices[s].get("kind") == "full"), None)
            if sl:
                step_d = dict(slice=sl, **(_paired(ix, name, pp, sl, sign) or {}))
        lineage.append(dict(name=name, title=_txt(m.get("title")), change=_txt(m.get("change")), status=m.get("status"),
                            hill=m.get("hill"), reason=_txt(m.get("reason")), created=m.get("created"),
                            promoted=m.get("promoted"), parent=pp, delta=step_d, siblings=sib))
    children = [dict(name=k, title=_txt(o.get("title")), status=o.get("status"), reason=_txt(o.get("reason")),
                     change=_txt(o.get("change")), hill=o.get("hill"))
                for k, o in models.items() if o.get("parent") == model and k != model]

    # failure gallery: every hill, its examples, and how this model and the comparator score on its target
    gallery = []
    for k, h in hills.items():
        t = h.get("target")
        gallery.append(dict(
            name=k, title=_txt(h.get("title")), status=h.get("status"), symptom=_txt(h.get("symptom")),
            measure=_txt(h.get("measure")), problem=_txt(h.get("problem")), share=h.get("share"), goal=h.get("goal"),
            target=t, control=h.get("control"), climbed_by=h.get("climbed_by"), mine=model == (h.get("climbed_by")) or me.get("hill") == k,
            examples=[{f: _txt(e.get(f)) for f in ("input", "wrong", "right", "why")} for e in (h.get("examples") or []) if isinstance(e, dict)][:6],
            score=_r(_mean(ix.pooled(model, t))) if ix.has(model, t) else None,
            base_score=_r(_mean(ix.pooled(base, t))) if ix.has(base, t) else None,
            vs=_paired(ix, model, base, t, sign) if t else None))
    gallery.sort(key=lambda g: (not g["mine"], g["status"] not in ("climbed", "open"), g["name"]))

    ladder = _ladder(p, ix, model, base, sign)
    promotion = _promotion(p, ix, model)
    if promotion:  # a promoted model's ladder is the evidence it was promoted on, as the model page shows it
        ladder = promotion["rungs"]
        for r in results:
            c = next((c for rg in ladder for c in rg["checks"] if c.get("slice") == r["slice"] and c.get("delta") is not None), None)
            if c and promotion["replaced"] == base:
                r["at_promotion"] = {k: c.get(k) for k in ("delta", "lo", "hi", "cand", "base", "n", "cand_runs", "base_runs")}
    plan = p.baseline_plan(model)

    # what is unknown or not run
    unknown = []
    for sl in plan["need"]:
        unknown.append(dict(kind="not_run", slice=sl, roles=plan["roles"].get(sl, [])))
    for r in results:
        if r["vs"] and r["vs"]["noisy"]:
            unknown.append(dict(kind="noisy", slice=r["slice"], n=r["vs"]["n"], lo=r["vs"]["lo"], hi=r["vs"]["hi"]))
        if r["errors"]:
            unknown.append(dict(kind="errors", slice=r["slice"], errors=r["errors"], n=r["n"]))
        if base and not r["vs"]:
            unknown.append(dict(kind="no_pair", slice=r["slice"], base=base))
    for rg in ladder:
        for c in rg["checks"]:
            if c["state"] in ("need_run", "need_baseline"):
                unknown.append(dict(kind=c["state"], slice=c["slice"], rung=rg["rung"]))
    if results and all(r["cost"] is None for r in results):
        unknown.append(dict(kind="no_cost"))
    if results and all(r["latency_p50"] is None for r in results):
        unknown.append(dict(kind="no_latency"))
    for g in goals.values():
        if g.get("status") == "open" and g.get("model") == model and not g.get("met"):
            unknown.append(dict(kind="goal_open", goal=g["name"], title=g.get("title")))
    for c in children:
        if c["status"] in ("candidate", "planned"):
            unknown.append(dict(kind="pending_child", model=c["name"], status=c["status"]))
    seen, uniq = set(), []
    for u in unknown:
        key = json.dumps(u, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            uniq.append(u)

    # decisions that touch this model's story
    touch = set(chain) | {s["name"] for st in lineage for s in st["siblings"]} | {c["name"] for c in children}
    decisions = []
    f = p.dir / "decisions.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("model") in touch or d.get("goal") in goals:
                decisions.append({k: _txt(clean_note(v)) if k in ("reason", "note") else clean_note(v, 120)
                                  for k, v in d.items() if k not in ("gate", "runs", "evidence", "vs_baseline")
                                  and not isinstance(v, (dict, list))})
    decisions = decisions[-200:]

    # reproduce: the spec on the model record, the runs behind every number, the commands
    runs = []
    for r in results:  # every complete run pooled into a number on this page, not only the latest
        for t in ix.runs[(model, r["slice"])]:
            runs.append(dict(slice=r["slice"], hash=r["hash"], task=t["id"], command=clean_note(str(t.get("command") or ""), 400),
                             config=_flat(t.get("config")) if isinstance(t.get("config"), dict) else [],
                             ended=t.get("ended"), url=r["url"]))
    spec = _flat({k: v for k, v in me.items() if k not in CORE_FIELDS})

    goal_list = []
    for g in goals.values():
        n = g.get("n")
        need = math.ceil(g["target"] * n - 1e-9) if g.get("kpi", "score") == "score" and n and g.get("target") is not None else None
        have = round(g["value"] * n) if need is not None and isinstance(g.get("value"), (int, float)) else None
        goal_list.append(dict(name=g["name"], title=_txt(g.get("title")), status=g.get("status"), slice=g.get("slice"),
                              n=n, kpi=g.get("kpi", "score"), target=g.get("target"), value=_r(g.get("value")),
                              model=g.get("model"), met=g.get("met"), need=need, have=have, baseline=g.get("baseline"),
                              vs_baseline={k: _r(v) for k, v in (g.get("vs_baseline") or {}).items()} or None,
                              higher_is_better=g.get("higher_is_better", True), problem=_txt(g.get("problem")),
                              hills=g.get("hills"), task=g.get("task"), scale=g.get("scale"), unit=g.get("unit"),
                              metric=g.get("metric")))

    return dict(
        generated=time.time(), project=dict(name=cfg.get("name"), higher_is_better=cfg.get("higher_is_better", True),
                                            primary_dataset=cfg.get("primary_dataset"), ladder=cfg.get("ladder", []),
                                            kpis=cfg.get("kpis")),
        model=dict(name=model, title=_txt(me.get("title")), change=_txt(me.get("change")), status=me.get("status"),
                   hill=me.get("hill"), parent=par, reason=_txt(me.get("reason")), created=me.get("created"),
                   promoted=me.get("promoted"), links=me.get("links"), champion=model == champ),
        champion=champ, base=base, base_title=_txt((models.get(base) or {}).get("title")) if base else None,
        main=main, goals=goal_list, results=results, lineage=lineage, children=children, ladder=ladder,
        gallery=gallery, unknown=uniq, decisions=decisions, runs=runs, spec=spec,
        promotion=dict(t=promotion["t"], replaced=promotion["replaced"]) if promotion else None,
        papers=papers_for(p, model),
        base_spec=_flat({k: v for k, v in models[base].items() if k not in CORE_FIELDS}) if base in models else [],
        baseline=dict(have=list(plan["have"]), need=plan["need"],
                      meta={sl: dict(kind=ix.slices[sl].get("kind"), n=ix.slices[sl].get("n"), hash=ix.slices[sl].get("hash"),
                                     metric=ix.slices[sl].get("metric"), description=_txt(ix.slices[sl].get("description")),
                                     roles=plan["roles"].get(sl, [])) for sl in plan["need"] if sl in ix.slices}),
        models=[dict(name=k, status=m.get("status"), title=_txt(m.get("title"))) for k, m in models.items()],
        labels={k: features.model_label(p, k) for k in models},
        datasets={k: dict(title=v.get("title"), size=v.get("size"), url=v.get("url"), description=_txt(v.get("description")))
                  for k, v in p.datasets().items()})


def _mean(d):
    return sum(d.values()) / len(d) if d else None


# ---------------------------------------------------------------- routes
@features.get("/reference")
def _page(p, path, q):
    if path.rstrip("/") == "/reference" or path.startswith("/reference/"):
        prewarm(p, unquote(path[len("/reference"):].strip("/")) or None, q.get("vs") or None)
        return 200, (WEB / "reference.html").read_bytes(), HTML
    raise KeyError(path)


@features.get("/api/reference")
def _data(p, path, q):
    return 200, build(p, q.get("model") or None, q.get("vs") or None)


@features.get("/explain-kit.js")
def _kit(p, path, q):
    return 200, (WEB / "explain-kit.js").read_bytes(), "text/javascript; charset=utf-8"
