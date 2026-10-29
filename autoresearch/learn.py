"""The Brief: "since you last looked" as predict-then-reveal cards built from the ledger, predictions and calibration,
and understanding telemetry. See features.py for the plug-in contracts.

Routes (relative to the project: `/api/...` on its own server, `/p/<key>/api/...` on a shared dashboard)

  GET  /api/brief?since=<unix s>&viewer=<name>
       {now, since, cards: [card], concepts: [concept], calibration, understanding, open: [prediction]}
       A card's answer (`reveal`) is only sent once this viewer has predicted it.
  POST /api/predictions  {viewer, card, guess, conf}
       guess: an option label (choice cards) or a number (number cards); conf: 0.5..1 (sure it is right / in the band).
       The server rebuilds the card, so truth and hit are its own: -> {prediction, card (with reveal)}.
  GET  /api/predictions?viewer=<name>     {predictions: [...], calibration}
  POST /api/understanding                 see UNDERSTANDING below
  GET  /api/understanding?viewer=&doc=    {viewer, total_ms, docs: {doc: {...}}, missed: [...]}

UNDERSTANDING: the body stream E's explainer kit (web/explain-kit.js) and the Brief POST. Keep it stable.
  One event object, or {"events": [event, ...]} (at most 200 per request). Each event:
    viewer    str      who is reading (the dashboard's "arx-name" in localStorage; default "anon"), <= 60 chars
    doc       str      what was read: "brief", "concept:<id>", or a paper/explainer name, <= 200 chars
    step      str|int  the card id, step index or block id within the doc
    ms        number   active milliseconds on that step (paused / hidden time excluded), 0 .. 86,400,000
    check     str|null the id of a check question answered at this step, if any
    ok        bool|null whether that check was answered right
    replays   int      times the step was replayed (default 0)
    alt_used  bool|str whether "see it another way" was used (or which alternative)
  Unknown keys are dropped, bad types become null, and the server adds `t`. Response: {"ok": true, "n": <written>}.
  Rows go to .research/understanding.jsonl, one per event.

Predictions go to .research/predictions.jsonl: {t, viewer, card, q, guess, conf, truth, hit}. A prediction about a run
that has not landed is written with truth/hit null ("open"); it resolves on read once the card has a truth.
"""
from __future__ import annotations

import json
import math
import time

from . import features
from .core import Project, _append, _jsonl, _read, paired

MAX_CARDS = 14
MAX_HILL_CONCEPTS = 5


# ---------------------------------------------------------------- small helpers

def _now() -> float:
    return time.time()


def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _decisions(p: Project) -> list[dict]:
    return _jsonl(p.dir / "decisions.jsonl")


def _short(slice_name: str) -> str:
    return slice_name.split("/", 1)[-1] if slice_name else ""


def _title(p: Project, model: str) -> str:
    t = str(features.model_label(p, model))
    t = t.split(" — ")[0].strip()
    return t if len(t) <= 60 else t[:59].rstrip() + "…"


def _gate(p: Project, model: str) -> dict:
    """p.gate() once per model per brief: every gate check runs bootstraps."""
    memo = getattr(p, "_gates", None)
    if memo is None:
        return p.gate(model)
    if model not in memo:
        memo[model] = p.gate(model)
    return memo[model]


def _first(text, n=140) -> str:
    """The first sentence of a ledger field, cut to n characters."""
    s = str(text or "").strip().split(". ")[0].strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


_PAIR: dict = {}  # (root, cand, base, slice, run ids) -> paired(); bootstraps are the slow part of a brief


def _pair(p: Project, cand: str, base: str, sl: str, sign: int) -> dict | None:
    if not cand or not base or cand == base:
        return None
    ca, ba = p.slice_evals(cand, sl), p.slice_evals(base, sl)
    if not ca or not ba:
        return None
    key = (str(p.root), cand, base, sl, sign, tuple(t["id"] for t in ca), tuple(t["id"] for t in ba))
    if key not in _PAIR:
        r = paired(p.pooled_scores(cand, sl), p.pooled_scores(base, sl), sign, iters=1000)
        _PAIR[key] = r if r.get("n") else None
    return _PAIR[key]


def _score(p: Project, model: str, sl: str) -> float | None:
    sc = p.pooled_scores(model, sl) if model and p.slice_evals(model, sl) else {}
    return sum(sc.values()) / len(sc) if sc else None


def _sign(p: Project) -> int:
    return 1 if p.config.get("higher_is_better", True) else -1


def _band(n: int, v: float) -> float:
    """Half-width of a 90% interval on a mean score, in points: the tolerance for guessing a score."""
    v = min(max(v or 0.5, 0.02), 0.98)
    return max(1.0, round(1.645 * math.sqrt(v * (1 - v) / max(n, 1)) * 100, 1))


def _ci_viz(r: dict) -> dict:
    return dict(kind="ci", delta=r["delta"], lo=r["lo"], hi=r["hi"], wins=r["wins"], losses=r["losses"], n=r["n"])


def _delta_card(cid, r, **kw) -> dict:
    """A number card on a paired delta, in points. A hit is a guess inside the 90% interval (at least ±1 pt)."""
    d, lo, hi = 100 * r["delta"], 100 * r["lo"], 100 * r["hi"]
    tol = max(1.0, round((hi - lo) / 2, 2))
    span = next(s for s in (5, 10, 20, 50, 100) if abs(d) + tol <= s * 0.9 or s == 100)
    return dict(id=cid, type="number", unit="pts", min=-span, max=span, step=0.25 if span <= 10 else 0.5, start=0,
                tol=tol, truth=round(d, 2), viz=_ci_viz(r), **kw)


# ---------------------------------------------------------------- cards
# Every card id is "<kind>|<key...>", so a prediction can rebuild its card later (and resolve when the run lands).

def _card_promote(p: Project, model: str, t: float = None) -> dict | None:
    dec = next((d for d in reversed(_decisions(p)) if d.get("kind") == "promote" and d.get("model") == model), None)
    if not dec:
        return None
    checks = [c for r in (dec.get("gate") or {}).get("rungs", []) for c in r.get("checks", []) if c.get("delta") is not None]
    full = f"{p.config.get('primary_dataset')}/full"
    c = next((c for c in checks if c.get("slice") == full), checks[-1] if checks else None)
    if not c:
        return None
    old = dec.get("replaced")
    why = f"It fixed {c['wins']} and broke {c['losses']} of {c['n']:,}."
    if c.get("lo") is not None and c["lo"] > 0:
        why += " The whole 90% interval is above zero."
    elif c.get("lo") is not None:
        why += " The 90% interval still touches zero."
    return _delta_card(f"promote|{model}", c, label="Promoted", tone="acc", t=dec.get("t"),
                       q=f"{_title(p, model)} replaced {_title(p, old) if old else 'the champion'}. Paired change on {_short(c['slice'])}?",
                       ctx=f"n = {c['n']:,}", ev=c.get("cand_task") or model, why=why, w=100)


def _card_goal(p: Project, name: str) -> dict | None:
    try:
        g = p.goal_status(name)
    except SystemExit:
        return None
    if g.get("value") is None or g.get("kpi", "score") != "score" or not g.get("n"):
        return None
    N, have = int(g["n"]), round(g["value"] * g["n"])
    need = math.ceil(g["target"] * N - 1e-9)
    traj = []
    for m in dict.fromkeys([g.get("baseline"), *(d.get("model") for d in _decisions(p) if d.get("kind") == "promote"), g["model"]]):
        v = _score(p, m, g["slice"]) if m else None
        if v is not None:
            traj.append(dict(label=_title(p, m), v=round(v * N), champ=m == g["model"]))
    lo = max(0, int(N * max(0.0, g["target"] - 0.3)) // 10 * 10)
    left = need - have
    why = (f"{left:,} more to reach {need:,}." if left > 0 else f"{-left:,} past the target of {need:,}.")
    vb = g.get("vs_baseline")
    if vb and vb.get("n"):
        why += f" Against the starting champion: {vb['wins']} fixed, {vb['losses']} broken."
    return dict(id=f"goal|{name}", type="number", unit="", int=True, min=lo, max=N, step=1, start=lo + (N - lo) // 2,
                tol=max(2, round(N * 0.01)), truth=have, label="Goal", tone="acc", t=g.get("created"),
                q=f"How many of {N:,} does the champion get right on {_short(g['slice'])}?",
                ctx=f"{g.get('title') or name}: {need:,} needed", ev=g.get("task") or g["slice"], why=why, w=95,
                viz=dict(kind="goal", have=have, need=need, N=N, lo=lo, traj=traj))


def _rule_text(c: dict) -> str:
    thr = abs(100 * (c.get("threshold") or 0))
    if c.get("rule") == "better":
        return "must be better" + (f" by {thr:g} pts" if thr else "")
    return f"may lose at most {thr:g} pts" if thr else "must not be worse"


def _card_gate(p: Project, model: str, sl: str) -> dict | None:
    try:
        g = _gate(p, model)
    except SystemExit:
        return None
    for r in g.get("rungs", []):
        for c in r.get("checks", []):
            if c.get("slice") == sl and c.get("state") in ("pass", "fail") and c.get("delta") is not None:
                ok = c["state"] == "pass"
                why = f"Δ {100 * c['delta']:+.2f} pts against a bar of {100 * c['threshold']:+.2f}."
                if c.get("noisy"):
                    why += " The interval crosses zero, so the next rung decides."
                ended = next((t.get("ended") for t in p.evals() if t["id"] == c.get("cand_task")), None)
                return dict(id=f"gate|{model}|{sl}", type="choice", opts=["Pass", "Fail"], truth="Pass" if ok else "Fail",
                            label=f"Gate · {r['rung']}", tone="pos" if ok else "neg", t=ended,
                            q=f"{_title(p, model)} on {_short(sl)}: it {_rule_text(c)}. Pass or fail?",
                            ctx=f"n = {c['n']:,} · against {_title(p, g.get('champion'))}", ev=c.get("cand_task") or sl,
                            why=why, w=85 if r["rung"] != (g["rungs"][0]["rung"] if g["rungs"] else "") else 80,
                            viz=_ci_viz(c))
    return None


def _comparator(p: Project, model: str, sl: str) -> str | None:
    m = p.models().get(model) or {}
    for base in (m.get("parent"), p.champion()):
        if base and base != model and p.slice_evals(base, sl):
            return base
    return None


def _model_slice(p: Project, model: str) -> str | None:
    """The slice a model's story is told on: its hill's target, else the primary full slice, else any run."""
    m, hills = p.models().get(model) or {}, p.hills()
    cands = [(hills.get(m.get("hill") or "") or {}).get("target"), f"{p.config.get('primary_dataset')}/full"]
    cands += [t["slice"] for t in p.evals() if t.get("model") == model]
    return next((s for s in cands if s and p.slice_evals(model, s) and _comparator(p, model, s)), None)


def _card_rejected(p: Project, model: str) -> dict | None:
    dec = next((d for d in reversed(_decisions(p)) if d.get("kind") == "rejected" and d.get("model") == model), None)
    sl = _model_slice(p, model)
    base = _comparator(p, model, sl) if sl else None
    r = _pair(p, model, base, sl, _sign(p)) if base else None
    if not dec or not r:
        return None
    m = p.models().get(model) or {}
    return _delta_card(f"rej|{model}", r, label="Rejected", tone="neg", t=dec.get("t"),
                       q=f"{_title(p, model)}: paired change against {_title(p, base)} on {_short(sl)}?",
                       ctx=f"n = {r['n']:,}", ev=(p.latest_eval(model, sl) or {}).get("id", model),
                       why=_first(dec.get("reason") or m.get("reason"), 200) or "Rejected.", w=70)


def _card_rejected_batch(p: Project, models: list[str]) -> dict | None:
    """Several rejections on one slice: which scored highest?"""
    groups: dict = {}
    for m in models:
        sl = _model_slice(p, m)
        if sl:
            groups.setdefault(sl, []).append(m)
    sl, ms = max(groups.items(), key=lambda kv: len(kv[1]), default=(None, []))
    if len(ms) < 3:
        return None
    ms = sorted(ms)[:4]
    vals = {m: _score(p, m, sl) for m in ms}
    best = max(ms, key=lambda m: vals[m] * _sign(p))
    champ = p.champion()
    ref = _score(p, champ, sl) if champ else None
    rows = [dict(label=_title(p, m), v=vals[m], hl=2 if m == best else 0) for m in ms]
    if ref is not None:
        rows.append(dict(label=_title(p, champ) + " (champion)", v=ref, hl=3))
    return dict(id="batch|" + sl + "|" + ",".join(ms), type="choice", opts=[_title(p, m) for m in ms], truth=_title(p, best),
                label=f"{len(ms)} rejected", tone="neg", t=max(_f((p.latest_eval(m, sl) or {}).get("ended")) for m in ms),
                q=f"Which of these scored highest on {_short(sl)}?", ctx=f"n = {p.slices()[sl]['n']:,}",
                ev=sl, why=f"All {len(ms)} were rejected; the best reached {100 * vals[best]:.1f}%.", w=65,
                viz=dict(kind="bars", rows=rows, ref=ref))


def _card_hill(p: Project, name: str, model: str) -> dict | None:
    h = p.hills().get(name)
    if not h or not h.get("target") or not model:
        return None
    sl, n = h["target"], (p.slices().get(h["target"]) or {}).get("n", 0)
    v = _score(p, model, sl)
    found = h.get("found_in")
    fv = _score(p, found, sl) if found and found != model else None
    rows = [dict(label=_title(p, model), v=v, hl=2)] if v is not None else []
    if fv is not None:
        rows.append(dict(label=_title(p, found) + " (found in)", v=fv, hl=0))
    if h.get("control") and v is not None:
        cv = _score(p, model, h["control"])
        if cv is not None:
            rows.append(dict(label=f"{_title(p, model)} on {_short(h['control'])}", v=cv, hl=0))
    sym = h.get("symptom") or h.get("title") or name
    ran = v is not None
    return dict(id=f"hill|{name}|{model}", type="number", unit="%", min=0, max=100, step=0.5, start=50,
                tol=_band(n, v if ran else 0.5), truth=round(100 * v, 2) if ran else None,
                label="New hill" if ran else "Hill · no run yet", tone="acc" if ran else "warn", t=h.get("created"),
                q=f"{_title(p, model)} on {_short(sl)}: its score?", ctx=_first(sym, 160), ev=sl,
                why=(f"{h['share']['count']} of {h['share']['of']} {h['share'].get('of_what') or 'errors'}." if isinstance(h.get("share"), dict) and h["share"].get("count") is not None
                     else _first(h.get("problem"), 200)) if ran else "Logged. Scored when the run lands.",
                w=60, viz=dict(kind="bars", rows=rows, ref=None) if ran else None)


def _card_run(p: Project, model: str, base: str, sl: str, task: dict | None = None) -> dict | None:
    """A run that has not landed: will the candidate beat `base`? Resolves when a complete run exists."""
    r = _pair(p, model, base, sl, _sign(p))
    live = task or next((t for t in p.tasks() if t.get("kind") == "eval" and t.get("model") == model and t.get("slice") == sl), None)
    if not r and not live:
        return None
    pr = (live or {}).get("progress") or {}
    ctx = f"{pr.get('done', 0):,} of {pr['total']:,} done" if r is None and pr.get("total") else f"n = {(r or {}).get('n') or (p.slices().get(sl) or {}).get('n', 0):,}"
    truth = None if r is None else ("Yes" if r["delta"] > 0 else "No")
    why = "Logged. Scored when the run lands." if r is None else f"Δ {100 * r['delta']:+.2f} pts: {r['wins']} fixed, {r['losses']} broken."
    return dict(id=f"run|{model}|{base}|{sl}", type="choice", opts=["Yes", "No"], truth=truth,
                label="Running" if r is None else "Landed", tone="warn" if r is None else "acc",
                t=(live or {}).get("created"), q=f"Will {_title(p, model)} beat {_title(p, base)} on {_short(sl)}?",
                ctx=ctx, ev=(live or {}).get("id") or sl, why=why, w=50, viz=_ci_viz(r) if r else None)


def _card_question(p: Project, qid: str) -> dict | None:
    q = (_read(p.dir / "questions.json", {}) or {}).get(qid)
    if not isinstance(q, dict) or q.get("status") != "answered":
        return None
    for ev in q.get("evidence") or []:
        if not isinstance(ev, dict) or not ev.get("model") or not ev.get("slice"):
            continue
        try:
            sl = p.slice(ev["slice"])["name"]
        except SystemExit:
            continue
        base = _comparator(p, ev["model"], sl)
        r = _pair(p, ev["model"], base, sl, _sign(p)) if base else None
        if not r:
            continue
        truth = "Better" if r["lo"] > 0 else "Worse" if r["hi"] < 0 else "Can't tell yet"
        return dict(id=f"q|{qid}", type="choice", opts=["Better", "Worse", "Can't tell yet"], truth=truth,
                    label="Answered", tone="acc", t=q.get("answered") or q.get("updated") or q.get("created"),
                    q=f"{q.get('title') or qid}: {_title(p, ev['model'])} against {_title(p, base)} on {_short(sl)}?",
                    ctx=f"n = {r['n']:,}", ev=(p.latest_eval(ev["model"], sl) or {}).get("id", sl),
                    why=_first(q.get("claim"), 200) or truth, w=75, viz=_ci_viz(r))
    return None


BUILD = {"promote": _card_promote, "goal": _card_goal, "gate": _card_gate, "rej": _card_rejected,
         "hill": _card_hill, "run": _card_run, "q": _card_question,
         "batch": lambda p, sl, ms: _card_rejected_batch(p, ms.split(","))}


def card(p: Project, cid: str) -> dict | None:
    kind, *args = cid.split("|")
    try:
        return BUILD[kind](p, *args)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, StopIteration):
        return None


def cards(p: Project, since: float = 0) -> list[dict]:
    """The cards for everything that changed after `since`: decisions, finished evals, rejections, new hills,
    answered questions, and runs still going (open predictions). Most important first, at most MAX_CARDS."""
    out, seen = [], set()

    def add(c):
        if c and c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)

    decs = [d for d in _decisions(p) if _f(d.get("t")) > since]
    champ, models = p.champion(), p.models()
    for d in decs:
        if d.get("kind") == "promote":
            add(_card_promote(p, d["model"]))
    for name, g in p.goals().items():
        if g.get("status") == "open" or _f(g.get("created")) > since:
            add(_card_goal(p, name))
    rejected = list(dict.fromkeys(d["model"] for d in decs if d.get("kind") == "rejected" and d.get("model") in models
                                  and models[d["model"]].get("status") == "rejected"))
    if len(rejected) >= 3:
        add(_card_rejected_batch(p, rejected))
    for m in rejected[-4:]:
        add(_card_rejected(p, m))
    latest: dict = {}
    for t in p.evals():  # one gate card per candidate: the check its newest finished run settled
        if _f(t.get("ended")) > since and t.get("model") != champ and (models.get(t.get("model")) or {}).get("status") == "candidate":
            latest.setdefault(t["model"], []).append(t)
    for m, ts in latest.items():
        for t in sorted(ts, key=lambda t: -_f(t.get("ended"))):
            c = _card_gate(p, m, t["slice"])
            if c:
                add(c)
                break
    for name, h in p.hills().items():
        if _f(h.get("created")) > since or (h.get("status") == "open" and champ and not p.slice_evals(champ, h.get("target"))):
            add(_card_hill(p, name, champ))
    for qid, q in (_read(p.dir / "questions.json", {}) or {}).items():
        if isinstance(q, dict) and _f(q.get("answered") or q.get("updated") or q.get("created")) > since:
            add(_card_question(p, qid))
    for t in p.tasks():
        if t.get("kind") == "eval" and t.get("status") in ("running", "stalled") and t.get("model") not in (None, champ) \
                and champ and t.get("slice") and p.slice_evals(champ, t["slice"]):
            add(_card_run(p, t["model"], champ, t["slice"], t))
    out.sort(key=lambda c: (-c.get("w", 0), -_f(c.get("t"))))
    return out[:MAX_CARDS]


PUBLIC = ("id", "type", "opts", "unit", "int", "min", "max", "step", "start", "tol", "label", "tone", "t", "q", "ctx", "ev")


def public(c: dict, pred: dict | None = None) -> dict:
    """What the page gets: the question always, the answer only once this viewer has predicted."""
    out = {k: c[k] for k in PUBLIC if k in c} | dict(open=c.get("truth") is None)
    if pred:
        out["reveal"] = dict(truth=c.get("truth"), why=c.get("why"), viz=c.get("viz"))
        out["pred"] = pred
    return out


# ---------------------------------------------------------------- predictions

def _hit(c: dict, guess) -> bool | None:
    if c.get("truth") is None:
        return None
    if c["type"] == "choice":
        return guess == c["truth"]
    return abs(_f(guess) - c["truth"]) <= c["tol"] + 1e-9


def predictions(p: Project, viewer: str | None = None) -> list[dict]:
    """Every prediction (one per viewer and card, the first stands), open ones resolved against the ledger now."""
    out: dict = {}
    for r in _jsonl(p.dir / "predictions.jsonl"):
        if isinstance(r, dict) and (viewer is None or r.get("viewer") == viewer):
            out.setdefault((r.get("viewer"), r.get("card")), r)
    res = []
    for r in out.values():
        if r.get("truth") is None:
            c = card(p, r.get("card") or "")
            if c and c.get("truth") is not None:
                r = r | dict(truth=c["truth"], hit=_hit(c, r.get("guess")), resolved=True)
        res.append(r)
    return sorted(res, key=lambda r: _f(r.get("t")))


def predict(p: Project, body: dict) -> tuple[int, dict]:
    viewer = str(body.get("viewer") or "anon")[:60]
    c = card(p, str(body.get("card") or ""))
    if not c:
        return 404, dict(error="unknown card")
    have = next((r for r in predictions(p, viewer) if r.get("card") == c["id"]), None)
    if have:
        return 200, dict(prediction=have, card=public(c, have))
    guess = body.get("guess")
    if c["type"] == "choice":
        if guess not in c["opts"]:
            return 400, dict(error="guess must be one of the options")
    else:
        g = _f(guess, None)
        if g is None or not c["min"] <= g <= c["max"]:
            return 400, dict(error="guess out of range")
        guess = g
    conf = min(1.0, max(0.5, _f(body.get("conf"), 0.7)))
    rec = dict(t=_now(), viewer=viewer, card=c["id"], q=c["q"], guess=guess, conf=round(conf, 3),
               truth=c.get("truth"), hit=_hit(c, guess))
    _append(p.dir / "predictions.jsonl", rec)
    return 200, dict(prediction=rec, card=public(c, rec))


def calibration(preds: list[dict]) -> dict:
    """Hits, Brier score and a reliability curve (stated confidence vs hit rate) over the scored predictions."""
    sc = [r for r in preds if r.get("hit") is not None]
    bins = []
    for a, b in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        g = [r for r in sc if a <= _f(r.get("conf")) < b]
        if g:
            bins.append(dict(conf=sum(_f(r["conf"]) for r in g) / len(g), hit=sum(bool(r["hit"]) for r in g) / len(g), n=len(g)))
    brier = sum((_f(r["conf"]) - (1.0 if r["hit"] else 0.0)) ** 2 for r in sc) / len(sc) if sc else None
    return dict(n=len(sc), hits=sum(bool(r["hit"]) for r in sc), brier=brier, open=len(preds) - len(sc), bins=bins)


# ---------------------------------------------------------------- understanding telemetry

def _event(e: dict) -> dict | None:
    if not isinstance(e, dict):
        return None
    s = lambda v, n: str(v)[:n] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else None
    ms = e.get("ms")
    ok = e.get("ok")
    alt = e.get("alt_used")
    rep = e.get("replays")
    return dict(t=_now(), viewer=s(e.get("viewer"), 60) or "anon", doc=s(e.get("doc"), 200) or "unknown",
                step=s(e.get("step"), 200), ms=min(86_400_000.0, max(0.0, float(ms))) if isinstance(ms, (int, float)) and not isinstance(ms, bool) else None,
                check=s(e.get("check"), 200), ok=ok if isinstance(ok, bool) else None,
                replays=max(0, int(rep)) if isinstance(rep, (int, float)) and not isinstance(rep, bool) else 0,
                alt_used=alt if isinstance(alt, bool) else s(alt, 60) if alt is not None else False)


def record(p: Project, body) -> tuple[int, dict]:
    evs = body.get("events") if isinstance(body, dict) and "events" in body else [body]
    if not isinstance(evs, list) or len(evs) > 200:
        return 400, dict(error="send one event or {events: [...]} (at most 200)")
    rows = [r for r in map(_event, evs) if r]
    for r in rows:
        _append(p.dir / "understanding.jsonl", r)
    return 200, dict(ok=True, n=len(rows))


def understanding(p: Project, viewer: str | None = None, doc: str | None = None) -> dict:
    """Per doc: active time (in all and per step), steps seen, the latest result per check, and the checks whose
    latest answer was wrong."""
    docs: dict = {}
    for r in _jsonl(p.dir / "understanding.jsonl"):
        if not isinstance(r, dict) or (viewer and r.get("viewer") != viewer) or (doc and r.get("doc") != doc):
            continue
        d = docs.setdefault(r.get("doc") or "unknown", dict(ms=0.0, steps=set(), step_ms={}, last={}, replays=0, alt=0, first=r.get("t"), latest=r.get("t")))
        d["ms"] += _f(r.get("ms"))
        if r.get("step") is not None:
            d["step_ms"][r["step"]] = d["step_ms"].get(r["step"], 0.0) + _f(r.get("ms"))
        d["latest"] = r.get("t")
        if r.get("step") is not None:
            d["steps"].add(r["step"])
        if r.get("check") and r.get("ok") is not None:
            d["last"][r["check"]] = r["ok"]
        d["replays"] += int(_f(r.get("replays")))
        d["alt"] += bool(r.get("alt_used"))
    out, missed = {}, []
    for k, d in docs.items():
        wrong = [c for c, ok in d["last"].items() if not ok]
        missed += [dict(doc=k, check=c) for c in wrong]
        out[k] = dict(ms=d["ms"], steps=len(d["steps"]), checks=len(d["last"]), right=sum(d["last"].values()),
                      missed=wrong, results=d["last"], step_ms=d["step_ms"], replays=d["replays"], alt_used=d["alt"], first=d["first"], latest=d["latest"])
    return dict(viewer=viewer, total_ms=sum(d["ms"] for d in out.values()), docs=out, missed=missed)


# ---------------------------------------------------------------- concepts: the project's own vocabulary

def concepts(p: Project) -> list[dict]:
    """Concept cards with checks, built from the ledger: paired delta, the gate ladder, an interval that crosses zero,
    and one per hill from its symptom and example. Each check: {q, o: [options], a: right option}."""
    out, cfg, champ = [], p.config, p.champion()
    promo = next((c for c in (_card_promote(p, d["model"]) for d in reversed(_decisions(p)) if d.get("kind") == "promote") if c), None)
    ref = (promo or {}).get("viz")
    if ref and ref.get("n"):
        w, l, n = ref["wins"], ref["losses"], ref["n"]
        o = [f"{100 * (w - l) / n:+.1f} pts", f"{100 * w / n:+.1f} pts", f"{100 * (w + l) / n:+.1f} pts"]
        qs = [dict(q=f"{w} fixed, {l} broken, n = {n:,}. Paired delta?", o=o, a=o[0])] if len(set(o)) == 3 else []
        qs.append(dict(q="Two models score the same on one slice. Can their paired delta be non-zero?", o=["Yes", "No"], a="No"))
        out.append(dict(id="paired", t="Paired delta", viz=dict(kind="paired", wins=w, losses=l, n=n), qs=qs))
    ladder = [r.get("rung") for r in cfg.get("ladder", []) if r.get("rung")]
    if len(ladder) >= 2:
        qs = []
        if len(ladder) >= 3:
            o = [ladder[1], ladder[-1], ladder[2] if len(ladder) > 3 else ladder[0]]
            qs.append(dict(q=f"A candidate passes {ladder[0]}. What runs next?", o=list(dict.fromkeys(o)), a=ladder[1]))
        better = [r["rung"] for r in cfg["ladder"][1:] if any(c.get("rule") == "better" for c in r.get("checks", []))]
        soft = [r["rung"] for r in cfg["ladder"][1:] if all(c.get("rule") != "better" for c in r.get("checks", []))]
        if better and soft:
            qs.append(dict(q='Which rung needs "better", not just "not worse"?', o=[better[-1], *soft[:2]], a=better[-1]))
        qs.append(dict(q="A candidate fails a rung. Do later rungs run?", o=["No", "Yes"], a="No"))
        out.append(dict(id="ladder", t="The gate ladder", viz=dict(kind="ladder", rungs=ladder), qs=qs))
    noisy, rows = None, []
    for m, g in ((m, _gate(p, m)) for m, v in p.models().items() if v.get("status") == "candidate"):
        for r in g.get("rungs", []):
            for c in r.get("checks", []):
                if c.get("delta") is not None:
                    rows.append([c["delta"], c["lo"], c["hi"]])
                    if c.get("noisy") and noisy is None:
                        noisy = c
    qs = []
    if noisy:
        qs.append(dict(q=f"{100 * noisy['delta']:+.2f} pts, 90% interval [{100 * noisy['lo']:+.2f}, {100 * noisy['hi']:+.2f}]. Is the gain shown?",
                       o=["Not yet", "Yes"], a="Not yet"))
    qs.append(dict(q="What narrows a paired interval most?", o=["More examples", "Re-running the same greedy eval"], a="More examples"))
    out.append(dict(id="ci", t="Interval crosses zero", viz=dict(kind="ci-mini", rows=rows[:3] or [[0.016, -0.005, 0.037]]), qs=qs))
    order = {"open": 0, "climbed": 1}
    hills = sorted(p.hills().items(), key=lambda kv: (order.get(kv[1].get("status"), 2), -_f((kv[1].get("share") or {}).get("count") if isinstance(kv[1].get("share"), dict) else 0)))
    for name, h in hills:
        if sum(c["id"].startswith("hill:") for c in out) >= MAX_HILL_CONCEPTS:
            break
        ex = next((e for e in (h.get("examples") or []) if isinstance(e, dict) and e.get("right") and e.get("wrong")), None)
        qs = []
        if ex:
            qs.append(dict(q=f"{str(ex.get('input') or h.get('symptom')).rstrip(' ?.:')}. Which is right?", o=[str(ex["right"]), str(ex["wrong"])], a=str(ex["right"])))
        v = _score(p, champ, h["target"]) if champ and h.get("target") else None
        if v is not None:
            vals = [100 * v, min(100.0, 100 * v + 9), max(0.0, 100 * v - 9)]
            o = [f"{x:.0f}%" for x in vals]
            if len(set(o)) == 3:
                qs.append(dict(q=f"The champion on {_short(h['target'])}?", o=o, a=o[0]))
        if not qs:
            continue
        out.append(dict(id=f"hill:{name}", t=_first(h.get("title") or name, 40).split(" [")[0], hill=name,
                        viz=dict(kind="hill", symptom=_first(h.get("symptom"), 90), share=h.get("share") if isinstance(h.get("share"), dict) else None,
                                 status=h.get("status")), qs=qs))
    return out


# ---------------------------------------------------------------- routes and CLI

def brief(p: Project, since: float = 0, viewer: str = "anon") -> dict:
    p._gates = {}
    with p.snapshot():
        cs = cards(p, since)
        preds = predictions(p, viewer)
        mine = {r["card"]: r for r in preds}
        # a predicted card that has since dropped out of the window still shows when it is open
        extra = [card(p, r["card"]) for r in preds if r.get("truth") is None and not r.get("resolved") and r["card"] not in {c["id"] for c in cs}]
        cs += [c for c in extra if c]
        return dict(now=_now(), since=since, viewer=viewer, cards=[public(c, mine.get(c["id"])) for c in cs],
                    concepts=concepts(p), calibration=calibration(preds),
                    understanding=understanding(p, viewer),
                    open=[r for r in preds if r.get("hit") is None])


@features.get("/api/brief")
def _get_brief(p, path, q):
    return 200, brief(p, _f(q.get("since"), 0.0), str(q.get("viewer") or "anon")[:60])


@features.get("/api/predictions")
def _get_predictions(p, path, q):
    preds = predictions(p, q.get("viewer") or None)
    return 200, dict(predictions=preds, calibration=calibration(preds))


@features.post("/api/predictions")
def _post_prediction(p, path, body):
    return predict(p, body) if isinstance(body, dict) else (400, dict(error="send an object"))


@features.get("/api/understanding")
def _get_understanding(p, path, q):
    return 200, understanding(p, q.get("viewer") or None, q.get("doc") or None)


@features.post("/api/understanding")
def _post_understanding(p, path, body):
    return record(p, body)


def _since(s: str | None) -> float:
    if not s:
        return 0.0
    unit = {"h": 3600, "d": 86400, "w": 604800}.get(s[-1:])
    return _now() - float(s[:-1]) * unit if unit else float(s)


def cmd_brief(a):
    p = Project()
    b = brief(p, _since(a.since), a.viewer)
    for c in b["cards"]:
        st = "open" if c["open"] else ("seen" if c.get("pred") else "new")
        print(f"{c['label']:<18} {st:<5} {c['q']}")
    cal = b["calibration"]
    br = "—" if cal["brier"] is None else f"{cal['brier']:.2f}"
    print(f"{a.viewer}: {cal['hits']} of {cal['n']} hits, Brier {br}, {cal['open']} open")


@features.CLI.append
def _cli(sp):
    s = sp.add_parser("brief", help="what changed since you last looked, as the dashboard's Brief cards")
    s.add_argument("--since", help="unix seconds, or 12h / 2d / 1w ago (default: all)")
    s.add_argument("--viewer", default="anon", help="whose predictions to count")
    s.set_defaults(fn=cmd_brief)
