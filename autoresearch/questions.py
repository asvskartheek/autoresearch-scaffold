"""Questions: the project as a tree of questions, each open, answered, dead, or with an agent.

Ledger: `.research/questions.json`, id -> {title, parent, status, claim, evidence, needs_human, created, by, ...}.
Evidence items are {model, slice} (paired against the model's parent, else the champion) or {task}.

The tree is seeded from the ledger on every read and never written: each goal is a root, its hills are children, and
each promoted, rejected or candidate model is a child of its hill (ids g:<goal>, h:<hill>, m:<model>). A stored
record with the same id wins, so editing a seeded node (answer, dead) writes it; asking under one does not.

CLI: arx q add | ask | answer | dead | list. Dashboard: GET /api/questions, GET /api/questions/notes?id=,
POST /api/questions/{ask,add,answer,dead}. Asking enqueues inbox kind="question" for `arx answer`.
"""
from __future__ import annotations

import json
import re
import time
import uuid

from . import features
from .core import _read, _write, locked, paired
from .readable import readable

STATUSES = ("open", "answered", "dead", "agent")


# ---------------------------------------------------------------- ledger
def _file(p):
    return p.dir / "questions.json"


def stored(p) -> dict:
    return _read(_file(p), {}) or {}


def _save(p, qid: str, rec: dict) -> dict:
    with locked(_file(p)):  # across processes: parallel `arx q add` calls used to drop each other's questions
        data = stored(p)
        data[qid] = rec
        _write(_file(p), data)
    return rec


def _short(title: str, words: int = 6) -> str:
    w = str(title or "").split()
    return " ".join(w[:words]) + ("…" if len(w) > words else "")


def _line(text, cap: int = 160) -> str | None:
    """One readable line: the first sentence, cut at `cap` characters."""
    if not text:
        return None
    t = re.sub(r"\s+", " ", readable(str(text))).strip()
    first = re.split(r"(?<=[.;])\s", t, maxsplit=1)[0].rstrip(";:, ")
    if len(first) > cap:
        return first[:cap - 1].rstrip() + "…"
    return first if first.endswith((".", "?", "!", ")")) else first + "."


def parse_evidence(p, items) -> list[dict]:
    """`model:slice` or `task:<id>` -> evidence dicts; the model and slice must exist."""
    out, models = [], p.models()
    for raw in items or []:
        if raw.startswith("task:"):
            tid = raw[5:]
            p.task(tid)  # KeyError if unknown
            out.append(dict(task=tid))
            continue
        model, sep, sl = raw.partition(":")
        if not sep or not model or not sl:
            raise SystemExit(f"evidence {raw!r}: write model:slice or task:<id>")
        if model not in models:
            raise SystemExit(f"evidence {raw!r}: unknown model {model}")
        out.append(dict(model=model, slice=p.slice(sl)["name"]))
    return out


def add(p, title, parent=None, needs_human=False, by="agent", status="open", quote=None, route=None,
        choices=None, claim=None, lenient=False) -> dict:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        raise SystemExit("a question needs a title")
    if parent and parent not in tree(p, full=False)["byid"]:
        if not lenient:
            raise SystemExit(f"unknown question {parent}")
        parent = None
    qid = "q-" + uuid.uuid4().hex[:6]
    rec = dict(title=title[:120], parent=parent or None, status=status, claim=claim, evidence=[],
               needs_human=bool(needs_human), created=time.time(), by=by or "agent",
               quote=(str(quote)[:400] if quote else None), route=(str(route)[:200] if route else None),
               choices=[str(c)[:60] for c in choices][:4] if choices else None)
    _save(p, qid, {k: v for k, v in rec.items() if v is not None})
    return dict(rec, id=qid)


def ask(p, title, parent=None, by="you", quote=None, route=None) -> dict:
    """A question for an agent: status `agent`, and an inbox item `arx answer` picks up."""
    q = add(p, title, parent=parent, by=by, status="agent", quote=quote, route=route, lenient=True)
    item = features.enqueue(p, "question", dict(title=q["title"], parent=q["parent"], quote=quote, route=route, by=by),
                            ref=q["id"])
    _save(p, q["id"], {k: v for k, v in q.items() if k != "id" and v is not None} | {"inbox": item["id"]})
    return q | {"inbox": item["id"]}


def settle(p, qid, status, claim, evidence=None, by="agent") -> dict:
    """Answer (status answered) or close (dead) a question. A seeded node is written on its first edit."""
    if status not in ("answered", "dead"):
        raise SystemExit("status must be answered or dead")
    claim = re.sub(r"\s+", " ", str(claim or "")).strip()
    if not claim:
        raise SystemExit("give the claim: one line that answers the question")
    node = tree(p, full=False)["byid"].get(qid)
    if not node:
        raise SystemExit(f"unknown question {qid}")
    base = stored(p).get(qid) or {k: node[k] for k in ("title", "parent", "evidence", "created", "by") if node.get(k) is not None}
    ev = list(evidence) if evidence else base.get("evidence") or []
    rec = base | dict(status=status, claim=claim[:300], evidence=ev, needs_human=False, settled=time.time(), settled_by=by)
    _save(p, qid, rec)
    for it in features.inbox(p):  # a queued ask nobody started is no longer needed
        if it.get("kind") == "question" and it.get("ref") == qid and it.get("status") == "queued":
            features.update(p, it["id"], status="done", result=f"{status} by {by}")
    return rec | {"id": qid}


# ---------------------------------------------------------------- the seeded tree
def _hill_title(k, h) -> str:
    t = re.sub(r"\s*\[[^\]]*\]", "", h.get("title") or "").strip()
    if t and len(t.split()) <= 6:
        return t
    alt = f"Why does {k.replace('-', ' ').replace('_', ' ')} fail?"
    return alt if len(alt.split()) <= 6 else _short(t or k)


_VERBS = ("keep", "reach", "get", "make", "cut", "beat", "hit", "hold", "stay", "match", "stop", "reduce", "raise",
          "halve", "double", "fix", "pass", "ship", "close")
_AFTER_VERB = {"in", "like", "at", "under", "within", "on", "as", "to", "for", "with", "without", "below", "above",
               "before", "after", "by", "from", "every", "faster", "slower", "correctly", "reliably", "instantly"}


def _lower1(t: str) -> str:
    """Lower the first letter unless the first word is an acronym or a name with inner capitals (GSM8K, P&ID, vLLM)."""
    w = t.split(" ", 1)[0]
    return t if not w[:1].isupper() or any(c.isupper() or c.isdigit() for c in w[1:]) or "&" in w else t[:1].lower() + t[1:]


def _base_verb(v: str) -> str:
    if v.endswith("ies"):
        return v[:-3] + "y"
    if v.endswith(("shes", "ches", "xes", "sses", "zes")):
        return v[:-2]
    return v[:-1]


def _title_units(t: str, g, sl) -> str:
    """Bare percentages in a goal title become the amount they stand for, the percentage in brackets after it:
    "GSM8K at 96%" -> "GSM8K at 1,267 of 1,319 (96%)"; "throughput +3%" -> "throughput to 322 tok/s (+3%)"."""
    target, kpi = g.get("target"), g.get("kpi", "score")
    if target is None or "%" not in t:
        return t
    n = g.get("n") or (sl or {}).get("n")
    if kpi == "score" and (sl or {}).get("scale") != "continuous" and n:
        need = -(-round(target * n * 1e6) // 10**6)

        def cnt(m):
            return f"{need:,} of {n:,} ({m.group(1)}%)" if abs(float(m.group(1)) - 100 * target) < 0.51 else m.group(0)
        return re.sub(r"(?<![+\d.])(\d+(?:\.\d+)?)\s*%", cnt, t)
    u = _goal_units_of(g, sl)
    return re.sub(r"\s*\+(\d+(?:\.\d+)?)\s*%", lambda m: f" to {_amt(u, target)} (+{m.group(1)}%)", t, count=1)


def _goal_title(g, k, sl=None) -> str:
    """A goal as a question that reads naturally: "Can we get GSM8K to 1,267 of 1,319 (96%)?", "Can we keep 1,224
    correct?", "Can we get to zero open review findings?", "Can we make Home appear in under a second?"."""
    t = re.sub(r"\s+", " ", (g.get("title") or k.replace("-", " ")).strip().rstrip("?.!")).strip()
    t = _title_units(t, g, sl)
    w = t.split(" ")
    first = w[0].lower()
    lower = (not g.get("higher_is_better", True)) != bool(_goal_units_of(g, sl)["neg"])
    if first in _VERBS:
        q = "Can we " + first + (" " + " ".join(w[1:]) if w[1:] else "")
    elif first in ("no", "zero") and len(w) > 1:
        q = "Can we get to zero " + " ".join(w[1:])
    else:
        verb = next((i for i in range(1, min(4, len(w) - 1)) if re.fullmatch(r"[a-z]{4,}s", w[i])
                     and not w[i].endswith(("ss", "us", "is")) and w[i + 1].lower() in _AFTER_VERB), None)
        if verb is not None:
            subj = [x.lower() if x in ("The", "A", "An", "Our", "Its") else x for x in w[:verb]]
            q = "Can we make " + " ".join(subj + [_base_verb(w[verb])] + w[verb + 1:])
        else:
            low = _lower1(t)
            the = "the " if low[:1].islower() and not low.startswith(("the ", "a ", "an ", "our ")) else ""
            q = "Can we get " + the + re.sub(r"\bat (?=[\d$])", "under " if lower else "to ", low, count=1)
    return " ".join(q.split()[:14]) + "?"


def _model_title(k, m) -> str:
    par = m.get("parent") or ""
    if par and par != k and k.startswith(par) and len(k) > len(par):
        what = k[len(par):]
        what = "+" + what if what[0].isalnum() else what
        return f"Does {what} help?"
    t = m.get("title")
    if t and len(t.split()) <= 4:
        t = t[0].lower() + t[1:] if len(t) > 1 and not t[1].isupper() and not t[1].isdigit() else t
        return f"Does {t} help?"
    return f"Does {k} help?"


def seeded(p) -> dict:
    """id -> node, derived from goals, hills and models. Nothing here is written."""
    goals, hills, models, champ, slices = p.goals(), p.hills(), p.models(), p.champion(), p.slices()
    out = {}
    for k, g in goals.items():
        st = {"achieved": "answered", "abandoned": "dead"}.get(g.get("status"), "open")
        claim = _line((g.get("evidence") or {}).get("note")) if st == "answered" else _line(g.get("reason")) if st == "dead" else None
        out[f"g:{k}"] = dict(title=_goal_title(g, k, slices.get(g.get("slice") or "")), parent=None, status=st, claim=claim, created=g.get("created"),
                             evidence=[dict(goal=k)], goal=k, seed="goal")
    loose = None
    for k, h in hills.items():
        par = f"g:{h['goal']}" if h.get("goal") in goals else None
        if par is None:
            loose = loose or "x:hills"
            par = loose
        st = {"climbed": "answered", "closed": "dead", "abandoned": "dead"}.get(h.get("status"), "open")
        claim = (f"Climbed by {h['climbed_by']}." if st == "answered" and h.get("climbed_by") else
                 _line(h.get("reason")) if st == "dead" else _line(h.get("symptom") or h.get("problem")))
        ev = [dict(share=k)] if (h.get("share") or {}).get("of") else []
        best = h.get("climbed_by") if st == "answered" else champ
        for role in ("target", "control"):
            if h.get(role) and best:
                ev.append(dict(model=best, slice=h[role], base=h.get("found_in") if h.get("found_in") != best else None))
        out[f"h:{k}"] = dict(title=_hill_title(k, h), parent=par, status=st, claim=claim, created=h.get("created"),
                             evidence=ev, hill=k, seed="hill")
    if loose:
        out[loose] = dict(title="Hills without a goal", parent=None, status="open", created=None, evidence=[], seed="group")
    other = None
    for k, m in models.items():
        s = m.get("status")
        promoted = s == "champion" or (s == "retired" and m.get("promoted"))
        if not (promoted or s in ("rejected", "candidate")) or (s == "champion" and not m.get("hill") and not m.get("parent")):
            continue
        if m.get("hill") in hills:
            par = f"h:{m['hill']}"
        else:
            other = other or "x:other"
            par = other
        st = "answered" if promoted else "dead" if s == "rejected" else "open"
        claim = _line(m.get("reason")) if s == "rejected" else _line(m.get("change"))
        if st == "answered":
            claim = "Yes. " + (claim or "Promoted.")
        elif st == "dead":
            claim = "No. " + (claim or "Rejected.")
        out[f"m:{k}"] = dict(title=_model_title(k, m), parent=par, status=st, claim=claim, created=m.get("created"),
                             evidence=_model_evidence(p, k, m, hills, goals), model=k, seed="model")
    if other:
        out[other] = dict(title="Changes outside any hill", parent=None, status="open", created=None, evidence=[], seed="group")
    return out


def _model_evidence(p, k, m, hills, goals) -> list[dict]:
    """The model's gate runs: its hill's target and control and the goal slice, wherever it has a run."""
    h = hills.get(m.get("hill") or "") or {}
    want = [h.get("target"), h.get("control"), (goals.get(h.get("goal") or "") or {}).get("slice")]
    mine = {t["slice"] for t in _evals(p) if t.get("model") == k}
    picks = [s for s in dict.fromkeys(want) if s and s in mine]
    if not picks:
        picks = sorted(mine)[:3]
    return [dict(model=k, slice=s) for s in picks]


def _evals(p):
    """Complete evals at each slice's current hash, read once per request (see tree())."""
    if getattr(p, "_q_evals", None) is not None:
        return p._q_evals
    hashes = {k: v.get("hash") for k, v in p.slices().items()}
    return [t for t in p.evals() if t.get("slice_hash") == hashes.get(t.get("slice")) and not t.get("superseded_by")]


# ---------------------------------------------------------------- resolving evidence
_PAIRED: dict = {}  # (model, base, slice, run ids) -> paired(); bootstraps are the slow part


def _runs(p, model, sl):
    return tuple(t["id"] for t in _evals(p) if t.get("model") == model and t.get("slice") == sl)


def _role(p, sl, node, hills, goals):
    h = hills.get(node.get("hill") or "") or hills.get((p.models().get(node.get("model") or "") or {}).get("hill") or "") or {}
    if sl == h.get("target"):
        return "target"
    if sl == h.get("control"):
        return "control"
    if any(g.get("slice") == sl for g in goals.values()):
        return "goal"
    return sl.split("/")[-1]


def resolve(p, e: dict, node: dict, ctx: dict) -> dict | None:
    hills, goals, models, champ = ctx["hills"], ctx["goals"], ctx["models"], ctx["champion"]
    if e.get("share"):
        sh = (hills.get(e["share"]) or {}).get("share") or {}
        if not sh.get("of"):
            return None
        return dict(kind="raw", role="errors", label="share of errors", c=sh.get("count"), n=sh.get("of"),
                    what=_line(sh.get("of_what"), 120))
    if e.get("goal"):
        g = ctx["goal_status"].get(e["goal"]) or {}
        vs = g.get("vs_baseline")
        if vs and vs.get("n"):
            return _pd(vs, g.get("model"), g.get("baseline"), g.get("slice"), "goal", runs=g.get("runs"))
        if g.get("value") is not None and g.get("kpi", "score") == "score":
            return dict(kind="raw", role="goal", model=g.get("model"), slice=g.get("slice"), n=g.get("n"),
                        c=round(g["value"] * g["n"]))
        return None
    if e.get("task"):
        try:
            t = p.task(e["task"])
        except KeyError:
            return dict(kind="missing", task=e["task"])
        s = t.get("summary") or {}
        n, sc = s.get("n"), s.get("score")
        return dict(kind="raw", role=(t.get("slice") or "task").split("/")[-1], task=t["id"], label=t.get("title"),
                    model=t.get("model"), slice=t.get("slice"), n=n, c=round(sc * n) if n and sc is not None else None)
    model, sl = e.get("model"), e.get("slice")
    if not model or not sl:
        return None
    role = _role(p, sl, node, hills, goals)
    mine = _runs(p, model, sl)
    if not mine:
        return dict(kind="missing", model=model, slice=sl, role=role)
    m = models.get(model) or {}
    cands = [e.get("base"), m.get("parent"), (hills.get(m.get("hill") or "") or {}).get("found_in"), champ]
    base = next((b for b in cands if b and b != model and _runs(p, b, sl)), None)
    if not base:
        sc = p.pooled_scores(model, sl)
        return dict(kind="raw", role=role, model=model, slice=sl, n=len(sc), c=round(sum(sc.values())), runs=len(mine))
    theirs = _runs(p, base, sl)
    key = (model, base, sl, mine, theirs)
    if key not in _PAIRED:
        sign = 1 if p.config.get("higher_is_better", True) else -1
        _PAIRED[key] = paired(p.pooled_scores(model, sl), p.pooled_scores(base, sl), sign)
    return _pd(_PAIRED[key], model, base, sl, role, runs=len(mine), base_runs=len(theirs))


def _pd(r, model, base, sl, role, **kw):
    n = r.get("n") or 0
    out = dict(kind="paired", role=role, model=model, base=base, slice=sl, n=n, delta=r.get("delta"), lo=r.get("lo"),
               hi=r.get("hi"), wins=r.get("wins"), losses=r.get("losses"), **kw)
    if n and r.get("cand") is not None:
        out |= dict(c=round(r["cand"] * n), bc=round(r["base"] * n))
    return out


# ---------------------------------------------------------------- the tree a viewer gets
def tree(p, full: bool = True) -> dict:
    """Seeded and stored nodes merged. `full` adds resolved evidence (`ev`), agent progress and goal trajectories."""
    with p.snapshot():  # tasks read once per call
        p._q_evals = None
        p._q_evals = _evals(p)
        try:
            return _tree(p, full)
        finally:
            p._q_evals = None


_GOALS: dict = {}  # project root -> (key, goal statuses); goal_status bootstraps, so reuse it until evals change


def _goal_status(p, goals) -> dict:
    key = (json.dumps(goals, sort_keys=True, default=str), p.champion(), tuple(t["id"] for t in _evals(p)))
    hit = _GOALS.get(str(p.root))
    if hit and hit[0] == key:
        return hit[1]
    out = {}
    for g in goals:
        try:
            out[g] = p.goal_status(g)
        except SystemExit:
            pass
    _GOALS[str(p.root)] = (key, out)
    return out


def _tree(p, full: bool) -> dict:
    nodes = seeded(p)
    for k in nodes:
        nodes[k]["seeded"] = True
    for k, rec in stored(p).items():
        if k in nodes:
            nodes[k] = nodes[k] | {kk: v for kk, v in rec.items() if v is not None} | {"edited": True}
        else:
            nodes[k] = dict(rec)
    for k, n in nodes.items():
        n["id"] = k
        if n.get("parent") and n["parent"] not in nodes:
            n["parent"] = None  # a parent that went away: show it at the top, never drop it
    if not full:
        return dict(byid=nodes)
    if full:
        ctx = dict(hills=p.hills(), goals=p.goals(), models=p.models(), champion=p.champion())
        ctx["goal_status"] = _goal_status(p, ctx["goals"])
        items = {}
        for it in features.inbox(p):
            if it.get("kind") == "question" and it.get("ref"):
                items[it["ref"]] = it
        tasks = {}
        for n in nodes.values():
            if n.get("goal") and not n.get("claim"):
                n["claim"] = _goal_claim(p, ctx["goal_status"].get(n["goal"]) or {})
            n["ev"] = [r for r in (resolve(p, e, n, ctx) for e in n.get("evidence") or []) if r]
            it = items.get(n["id"])
            if it and n.get("status") == "agent":
                live = dict(item=it["id"], status=it.get("status"), task=it.get("task"), error=it.get("error"))
                if it.get("task"):
                    try:
                        t = tasks.get(it["task"]) or p.task(it["task"])
                        ev = p.events(t["id"])
                        live |= dict(task_status=t.get("status"), note=readable(ev[-1]["msg"]) if ev else None,
                                     progress=t.get("progress"))
                    except KeyError:
                        pass
                n["live"] = live
        return dict(nodes=sorted(nodes.values(), key=lambda n: (n.get("seed") == "group", n.get("created") or 0)), goals=_trajectories(p, ctx),
                    champion=ctx["champion"], needs_human=sum(1 for n in nodes.values() if _waiting(n)), now=time.time())


def _grp(x: float) -> str:
    """Like core.js grp(): whole numbers with commas from 100 up, else 3 significant figures."""
    return f"{round(x):,}" if abs(x) >= 100 else f"{float(f'{x:.3g}'):,g}"


def _goal_units(p, g) -> dict:
    return _goal_units_of(g, (p.slices().get(g.get("slice") or "") or {}) if g.get("slice") else {})


def _goal_units_of(g, sl) -> dict:
    """How a goal's numbers read: counts "c of n" on a 0/1 slice, else an amount in the slice's or KPI's unit.
    Metrics that start "minus ..." are stored negated (higher is better); they read as the positive amount."""
    sl = sl or {}
    kpi, hib = g.get("kpi", "score"), g.get("higher_is_better", True)
    if kpi == "score" and sl.get("scale") != "continuous":
        return dict(count=True, n=g.get("n") or sl.get("n"), neg=False, unit="", lower=not hib)
    metric = str(sl.get("metric") or "")
    neg = kpi == "score" and bool(re.match(r"\s*minus\b", metric, re.I))
    unit = sl.get("unit") if kpi == "score" else None
    if not unit:
        unit = ("s" if kpi.startswith("latency") else "tok/s" if re.search(r"tokens?_?(per_second|/\s*s)", kpi + " " + metric, re.I)
                else "")
    return dict(count=False, n=None, neg=neg, unit=unit or "", lower=(not hib) != neg)


def _amt(u, v) -> str:
    if v is None:
        return "—"
    if u["count"] and u["n"]:
        return f"{round(v * u['n']):,} of {u['n']:,}"
    if u["count"]:
        return f"{100 * v:.1f}%"
    return f"{_grp(-v if u['neg'] else v)} {u['unit']}".strip()


def _goal_text(p, g) -> dict:
    """value, target, gap and each point as text in units; the claim and the header distance both read these."""
    u = _goal_units(p, g)
    out = dict(value_txt=_amt(u, g.get("value")))
    t = g.get("target")
    if t is not None:
        if u["count"] and u["n"]:
            need = -(-round(t * u["n"] * 1e6) // 10**6)
            out["target_txt"] = f"{need:,} of {u['n']:,} ({f'{100 * t:.1f}'.rstrip('0').rstrip('.')}%)"
            if g.get("value") is not None:
                out["gap_txt"] = f"{max(0, need - round(g['value'] * u['n'])):,} more of {u['n']:,}"
        else:
            out["target_txt"] = ("at most " if u["lower"] else "at least ") + _amt(u, t)
            if g.get("gap") is not None and g["gap"] > 0:
                out["gap_txt"] = f"{_grp(abs(g['gap']))} {u['unit']}".strip() + " to go"
    return out | dict(units=u)


def _goal_claim(p, g) -> str | None:
    if g.get("value") is None:
        return "No complete champion run on the goal slice yet." if g else None
    tx = _goal_text(p, g)
    who = features.model_label(p, g.get("model"))
    met = " Met." if g.get("met") else ""
    return f"{who}: {tx['value_txt']}; target {tx.get('target_txt', '—')}.{met}"


def _waiting(n) -> bool:
    return bool(n.get("needs_human")) and n.get("status") in ("open", "agent")


def _trajectories(p, ctx) -> dict:
    """Each goal: where it stands, in units, and the champion succession's KPI on its slice."""
    order = []
    for d in _decisions(p):
        if d.get("kind") in ("champion", "promote") and d.get("model") and d.get("model") not in order:
            order.append(d["model"])
    if ctx["champion"] and ctx["champion"] not in order:
        order.append(ctx["champion"])
    out = {}
    for k, g in ctx["goal_status"].items():
        sl, kpi = g.get("slice"), g.get("kpi", "score")
        pts = []
        for m in order:
            ev = next((t for t in reversed(_evals(p)) if t.get("model") == m and t.get("slice") == sl), None)
            v = (ev.get("summary") or {}).get(kpi) if ev else None
            if v is not None:
                pts.append([m, v, features.model_label(p, m)])
        tx = _goal_text(p, g)
        u = tx.pop("units")
        for pt in pts:
            pt[2] = f"{pt[2]}: {_amt(u, pt[1])}"
        out[k] = {kk: g.get(kk) for kk in ("title", "status", "slice", "n", "kpi", "target", "value", "model",
                                            "higher_is_better", "gap", "met")} | tx | dict(points=pts)
    return out


def _decisions(p):
    try:
        lines = (p.dir / "decisions.jsonl").read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def notes(p, qid: str, cap: int = 60) -> list[dict]:
    """The reading pane: decision reasons and task notes, each placed on the node it is about (the model a task ran,
    else a model or hill its title names, else the goal). The focus's own subtree first, newest first, then the rest."""
    t = tree(p, full=False)["byid"]
    if qid not in t:
        raise KeyError(qid)
    kids = {}
    for k, n in t.items():
        kids.setdefault(n.get("parent"), []).append(k)
    sub, stack = {qid}, [qid]
    while stack:
        for k in kids.get(stack.pop(), []):
            if k not in sub:
                sub.add(k)
                stack.append(k)
    root = qid
    while t[root].get("parent"):
        root = t[root]["parent"]
    by_model = {n["model"]: k for k, n in t.items() if n.get("model")}
    by_hill = {n["hill"]: k for k, n in t.items() if n.get("hill")}
    names = sorted(by_model, key=len, reverse=True)

    def place(model, text):
        if model in by_model:
            return by_model[model]
        for m in names:
            if m in text:
                return by_model[m]
        for h, k in by_hill.items():
            if h in text:
                return k
        return root

    out = []
    for d in _decisions(p):
        txt = d.get("reason") or d.get("note")
        if isinstance(txt, str) and len(txt) > 12:
            out.append(dict(t=d.get("t"), node=place(d.get("model"), txt), src=f"decision {d.get('kind')}", text=readable(txt)))
    for task in p.tasks():
        if task.get("kind") in ("answer", "setup", "baseline"):
            continue
        head = f"{task.get('title') or ''} {task.get('description') or ''}"
        for e in p.events(task["id"])[-2:]:
            msg = e.get("msg")
            if isinstance(msg, str) and len(msg) > 40 and not msg.lstrip().startswith(("{", "[")):
                out.append(dict(t=e.get("t"), node=place(task.get("model"), head + " " + msg), src=task["id"], text=readable(msg)))
    for k, n in t.items():
        if n.get("quote"):
            out.append(dict(t=n.get("created"), node=k, src="quote", text=n["quote"]))
    out.sort(key=lambda x: (x["node"] not in sub, -(x.get("t") or 0)))
    return out[:cap]


# ---------------------------------------------------------------- dashboard routes
@features.get("/api/questions/notes")
def _get_notes(p, path, q):
    try:
        return 200, dict(notes=notes(p, q.get("id") or ""))
    except KeyError:
        return 404, dict(error="unknown question")


@features.get("/api/questions")
def _get_tree(p, path, q):
    return 200, tree(p)


def _who(d):
    return re.sub(r"[^\w .@-]", "", str(d.get("by") or "you"))[:40] or "you"


@features.post("/api/questions/")
def _post(p, path, d):
    if not isinstance(d, dict):
        return 400, dict(error="bad request")
    verb = path.rstrip("/").rsplit("/", 1)[-1]
    try:
        if verb == "ask":
            return 200, ask(p, d.get("title"), parent=d.get("parent") or None, by=_who(d), quote=d.get("quote"),
                            route=d.get("route"))
        if verb == "add":
            return 200, add(p, d.get("title"), parent=d.get("parent") or None, by=_who(d),
                            needs_human=bool(d.get("needs_human")))
        if verb in ("answer", "dead"):
            return 200, settle(p, str(d.get("id") or ""), "answered" if verb == "answer" else "dead", d.get("claim"),
                               by=_who(d))
    except SystemExit as e:
        return 400, dict(error=str(e))
    return 404, dict(error="unknown action")


def _state(p, out):
    """Cheap: stored questions only (seeded nodes never wait on a person)."""
    s = stored(p)
    out["questions"] = dict(needs_human=sum(1 for n in s.values() if _waiting(n)),
                            agent=sum(1 for n in s.values() if n.get("status") == "agent"))


# ---------------------------------------------------------------- the agent's prompt
def _prompt(p, item) -> str:
    qid = item.get("ref")
    t = tree(p, full=False)["byid"]
    n = t.get(qid) or {}
    path, x = [], t.get(n.get("parent"))
    while x:
        path.insert(0, f"{x['id']}: {x['title']}" + (f" ({x['status']}: {x['claim']})" if x.get("claim") else ""))
        x = t.get(x.get("parent"))
    pay = item.get("payload") or {}
    lines = [
        f"Someone asked a question on the arx research dashboard. Investigate it and answer it from the ledger.",
        "",
        f"Question {qid}: {n.get('title') or pay.get('title')}",
        f"Asked by: {pay.get('by') or n.get('by') or 'someone'}",
    ]
    if path:
        lines += ["Where it sits in the question tree (root first):", *[f"  {s}" for s in path]]
    if pay.get("quote") or n.get("quote"):
        lines.append(f"They selected this text when asking: \"{pay.get('quote') or n.get('quote')}\"")
    if pay.get("route") or n.get("route"):
        lines.append(f"They were on the dashboard view: {pay.get('route') or n.get('route')}")
    lines += [
        "",
        "Rules:",
        "- Read-only ledger access. Read research.json, PROTOCOL.md and .research/ (models.json, hills.json, goals.json,",
        "  slices.json, decisions.jsonl, tasks/*/task.json and events.jsonl). Use `arx status`, `arx gate <model>`,",
        "  `arx goal status` and `arx q list`. Do not run evals, train, edit the ledger or change any file.",
        "- Reporting rules from PROTOCOL.md: every number names its slice and n; show paired deltas vs the champion",
        "  (or the model's parent) with the 90% CI, not raw scores from different slices; a CI that crosses zero is a",
        "  lead, not a result; say 'not run' when the ledger has no run, never guess a number.",
        "",
        "Answer with exactly one of:",
        f"  arx q answer {qid} \"<claim>\" --evidence <model>:<slice> [--evidence task:<id> ...]",
        f"  arx q dead {qid} \"<claim>\"     (the question has no useful answer, or the idea it asks about failed)",
        "The claim is one plain sentence of at most 25 words that answers the question, with its numbers,",
        "e.g. \"No. 150 vs 157 of 185 on the target slice, paired delta -3.8 pts (90% CI -6.5 to -1.1).\"",
        "Evidence: every model:slice run the claim rests on (the dashboard draws each as a paired-delta dot with its CI).",
        "If answering needs new runs or a human decision, still answer what the ledger shows now, and add the follow-up as",
        f"  arx q add \"<title, at most 6 words>\" --parent {qid} --needs-human",
    ]
    return "\n".join(lines)


features.STATE.append(_state)
features.PROMPTS["question"] = _prompt


# ---------------------------------------------------------------- CLI
def _cmd(a):
    from .core import Project
    p = Project()
    if a.verb in ("add", "ask"):
        title = " ".join(a.args)
        if a.verb == "ask":
            q = ask(p, title, parent=a.parent, by=a.by or "you")
            return print(f"{q['id']} asked; an agent answers it (inbox {q['inbox']})")
        q = add(p, title, parent=a.parent, needs_human=a.needs_human, by=a.by or "agent", choices=a.choice)
        if len(title.split()) > 6:
            print("note: keep titles to 6 words or fewer", flush=True)
        return print(q["id"])
    if a.verb in ("answer", "dead"):
        if len(a.args) < 2:
            raise SystemExit(f"arx q {a.verb} <id> \"<claim>\"")
        ev = parse_evidence(p, a.evidence)
        r = settle(p, a.args[0], "answered" if a.verb == "answer" else "dead", " ".join(a.args[1:]), ev, by=a.by or "agent")
        return print(f"{a.args[0]} {r['status']}: {r['claim']}")
    if a.verb == "list":
        t = tree(p, full=False)["byid"]
        if a.json:
            return print(json.dumps(t, default=str, indent=1))
        kids = {}
        for k, n in sorted(t.items(), key=lambda kv: kv[1].get("created") or 0):
            kids.setdefault(n.get("parent"), []).append(k)
        mark = dict(open="o", answered="+", dead="x", agent="~")

        def walk(pid, depth):
            for k in kids.get(pid, []):
                n = t[k]
                flag = " [needs you]" if _waiting(n) else ""
                print(f"{'  ' * depth}{mark.get(n.get('status'), '?')} {k}  {n['title']}{flag}"
                      + (f"\n{'  ' * depth}    {n['claim']}" if n.get("claim") and a.claims else ""))
                walk(k, depth + 1)
        return walk(None, 0)
    raise SystemExit(f"unknown verb {a.verb}")


def _register(sp):
    import argparse
    s = sp.add_parser("q", help="questions: the project as a tree of questions with evidence",
                      formatter_class=argparse.RawDescriptionHelpFormatter, description="""verbs:
  add "<title>" [--parent id] [--needs-human]     an open question (title: 6 words or fewer)
  ask "<title>" [--parent id]                     a question for an agent (inbox kind=question)
  answer <id> "<claim>" --evidence model:slice    answered, with the runs it rests on (task:<id> also works)
  dead <id> "<claim>"                             a dead end
  list [--claims] [--json]                        the tree (seeded from goals, hills and models)""")
    s.add_argument("verb", choices=["add", "ask", "answer", "dead", "list"])
    s.add_argument("args", nargs="*")
    s.add_argument("--parent")
    s.add_argument("--needs-human", action="store_true")
    s.add_argument("--choice", action="append", help="add: a one-tap answer for the person (repeat, up to 4)")
    s.add_argument("--evidence", action="append", default=[], help="model:slice or task:<id> (repeat)")
    s.add_argument("--by", help="who is writing (default: agent)")
    s.add_argument("--claims", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd)


features.CLI.append(_register)
