"""The Brief: "since you last looked" as predict-then-reveal cards built from the ledger, predictions and calibration,
and understanding telemetry. See features.py for the plug-in contracts. The 101 course (course.py) teaches the ideas
the cards lean on; each card names them in `needs`.

Routes (relative to the project: `/api/...` on its own server, `/p/<key>/api/...` on a shared dashboard)

  GET  /api/brief?since=<unix s>&viewer=<name>
       {now, since, cards: [card], course: {lessons, memory, due}, calibration, understanding, open: [prediction]}
       A card's answer (`reveal`) is only sent once this viewer has predicted it.
  POST /api/predictions  {viewer, card, guess, conf}
       guess: an option label (choice cards) or a number (number cards); conf: chance..1 (sure it is right / in the
       band; chance is the card's `cmin`: 1/options for a choice, 0.05 for a number band).
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
import re
import time

from . import features
from .core import Project, _append, _jsonl, _read, paired

MAX_CARDS = 14


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


DEAD_S = 86400  # stalled for longer than this is dead


def _dead(t: dict) -> bool:
    return t.get("status") == "stalled" and _now() - _f(t.get("heartbeat") or t.get("updated")) > DEAD_S


# ---------------------------------------------------------------- units (the same rule as sv/sd in web/core.js)
# A 0/1 slice: scores as "1,224 of 1,319", deltas in points. A continuous slice: its own unit; a "minus ms" metric is
# stored negated (higher is better) and reads as the plain amount.

def _slc(p: Project, sl: str) -> dict:
    """The slice with `scale` filled in (read off the newest run's scores for slices frozen before it existed)."""
    memo = p.__dict__.setdefault("_scales", {})
    if sl not in memo:
        s = dict(p.slices().get(sl) or {})
        if not s.get("scale"):
            ts = [t for t in p.evals() if t.get("slice") == sl and t.get("ended")]
            t = max(ts, key=lambda t: _f(t.get("ended")), default=None)
            vals = {r.get("score") for r in p.rows(t["id"]) if not r.get("error")} if t else set()
            s["scale"] = "continuous" if vals and not vals <= {0, 1} else "binary"
        memo[sl] = s
    return memo[sl]


def _cont(p: Project, sl: str) -> bool:
    return _slc(p, sl).get("scale") == "continuous"


def _unit(p: Project, sl: str) -> str:
    s = _slc(p, sl)
    return s.get("unit") or ("tok/s" if re.search(r"tokens?\s*/\s*s", s.get("metric") or "", re.I) else "")


def _neg(p: Project, sl: str) -> bool:
    return bool(re.match(r"\s*minus\b", _slc(p, sl).get("metric") or "", re.I))


def _grp(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{float(f'{x:.3g}'):,g}"


def sv(p: Project, sl: str, v: float | None, n: int | None = None) -> str:
    """A score in its slice's units."""
    if v is None:
        return "—"
    if _cont(p, sl):
        return f"{_grp(-v if _neg(p, sl) else v)} {_unit(p, sl)}".strip()
    n = n or _slc(p, sl).get("n")
    return f"{round(v * n):,} of {n:,} ({100 * v:.1f}%)" if n else f"{100 * v:.1f}%"


def sd(p: Project, sl: str, d: float | None) -> str:
    """A delta in its slice's units: "+5.2 pts" on a 0/1 slice, "−1,071 ms" on a continuous one."""
    if d is None:
        return "—"
    x = (-d if _neg(p, sl) else d) if _cont(p, sl) else 100 * d
    sg = "+" if x > 0 else "−" if x < 0 else ""
    if _cont(p, sl):
        return f"{sg}{_grp(abs(x))} {_unit(p, sl)}".strip()
    return f"{sg}{abs(x):.1f}".removesuffix(".0") + (" pt" if round(abs(x), 1) == 1 else " pts")


def _ci_viz(r: dict, p: Project = None, sl: str = None, bar: float = None) -> dict:
    """The interval chart, in display units: points on a 0/1 slice, the slice's unit on a continuous one."""
    k = (-1 if _neg(p, sl) else 1) if p and sl and _cont(p, sl) else 100
    lo, hi = sorted((k * r["lo"], k * r["hi"]))
    out = dict(kind="ci", delta=k * r["delta"], lo=lo, hi=hi, wins=r["wins"], losses=r["losses"], n=r["n"],
               unit=_unit(p, sl) if k != 100 else "pts", better=-1 if k < 0 else 1)
    if bar:
        out["bar"] = k * bar
    if k == 100:  # (fixed - broken) / n only when each side ran once on 0/1 scores; else the delta is a mean of runs
        out["exact"] = abs((r["wins"] - r["losses"]) / r["n"] - r["delta"]) <= 5e-5 if r.get("n") else False
    return out


def _nice(x: float) -> float:
    """The smallest of 1, 2, 2.5, 5 × 10^k at or above x."""
    if x <= 0:
        return 1.0
    m = 10 ** math.floor(math.log10(x))
    return next(c * m for c in (1, 2, 2.5, 5, 10) if c * m >= x - 1e-12)


def _delta_card(cid, r, p: Project = None, sl: str = None, sign: int = 1, **kw) -> dict:
    """A number card on a paired delta. A hit is a guess inside the 90% interval (at least ±1 pt).
    The axis never depends on the answer: on a 0/1 slice it is the room the comparator leaves (from −its score to
    +what it misses), on a continuous one ± the comparator's own value."""
    viz = _ci_viz(r, p, sl)
    d, lo, hi = viz["delta"], viz["lo"], viz["hi"]
    a, b = _room(r, viz, sign)
    if viz["unit"] != "pts":
        tol = max(b / 100, round((hi - lo) / 2, 3))
        return dict(id=cid, type="number", unit=viz["unit"], min=a, max=b, step=b / 200, start=0, tol=tol,
                    truth=round(d, 3), viz=viz, **kw)
    tol = max(1.0, round((hi - lo) / 2, 2))
    return dict(id=cid, type="number", unit="pts", min=a, max=b, step=0.25 if b - a <= 20 else 0.5, start=0,
                tol=tol, truth=round(d, 2), viz=viz, **kw)


def _room(r: dict, viz: dict, sign: int = 1) -> tuple[float, float]:
    """The axis a delta can be drawn on without knowing it: on a 0/1 slice the room the comparator leaves (from −its
    score to +what it misses, in points), on a continuous one ± the comparator's own value."""
    base = r.get("base")
    if viz["unit"] != "pts":
        span = _nice(abs(base)) if base else _nice(max(abs(viz["lo"]), abs(viz["hi"])) * 4)
        return -span, span
    if base is None:
        return -100, 100
    down, up = (100 * base, 100 * (1 - base)) if sign > 0 else (100 * (1 - base), 100 * base)
    return -max(5, 5 * math.ceil(down / 5 - 1e-9)), max(5, 5 * math.ceil(up / 5 - 1e-9))


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
    return _delta_card(f"promote|{model}", c, p, c["slice"], _sign(p), label="Promoted", tone="acc", t=dec.get("t"),
                       q=f"{_title(p, model)} replaced {_title(p, old) if old else 'the champion'}. Paired change on {_short(c['slice'])}?",
                       ctx=f"n = {c['n']:,}", ev=c.get("cand_task") or model, why=why, w=100)


def _card_goal(p: Project, name: str) -> dict | None:
    try:
        g = p.goal_status(name)
    except SystemExit:
        return None
    if g.get("value") is None or g.get("kpi", "score") != "score" or not g.get("n") or _cont(p, g["slice"]):
        return None  # the card counts examples right: a continuous goal slice has no count
    N, have = int(g["n"]), round(g["value"] * g["n"])
    need = math.ceil(g["target"] * N - 1e-9)
    traj = []
    for m in dict.fromkeys([g.get("baseline"), *(d.get("model") for d in _decisions(p) if d.get("kind") == "promote"), g["model"]]):
        v = _score(p, m, g["slice"]) if m else None
        if v is not None:
            traj.append(dict(label=_title(p, m), v=round(v * N), champ=m == g["model"]))
    lo = 0  # a floor near the target would give the target (and on a "keep" goal, the answer) away
    left = need - have
    why = (f"{left:,} more to reach {need:,}." if left > 0 else f"{-left:,} past the target of {need:,}." if left else f"Exactly at the target of {need:,}.")
    vb = g.get("vs_baseline")
    if vb and vb.get("n"):
        why += f" Against the starting champion: {vb['wins']} fixed, {vb['losses']} broken."
    return dict(id=f"goal|{name}", type="number", unit="", int=True, min=lo, max=N, step=1, start=lo + (N - lo) // 2,
                tol=max(2, round(N * 0.01)), truth=have, label="Goal", tone="acc", t=g.get("created"),
                q=f"How many of {N:,} does the champion get right on {_short(g['slice'])}?",
                ctx=_goal_ctx(g, name), ev=g.get("task") or g["slice"], why=why, w=95,
                viz=dict(kind="goal", have=have, need=need, N=N, lo=lo, traj=traj))


def _goal_ctx(g: dict, name: str) -> str:
    """The goal by name, without numbers: a target count ("Keep 1,224 correct", "1,224 needed") can be the answer
    itself. The target shows in the reveal."""
    t = str(g.get("title") or "")
    return t if t and not re.search(r"\d[\d,.]*\d|\d{2,}", t) else name


def _rule_text(p: Project, c: dict) -> str:
    thr = abs(c.get("threshold") or 0)
    amt = sd(p, c.get("slice"), thr).lstrip("+−")  # an amount: a "minus" metric must not make it read negative
    if c.get("rule") == "better":
        return "must be better" + (f" by {amt}" if thr else "")
    return f"may lose at most {amt}" if thr else "must not be worse"


def _card_gate(p: Project, model: str, sl: str) -> dict | None:
    try:
        g = _gate(p, model)
    except SystemExit:
        return None
    for r in g.get("rungs", []):
        for c in r.get("checks", []):
            if c.get("slice") == sl and c.get("state") in ("pass", "fail") and c.get("delta") is not None:
                ok = c["state"] == "pass"
                why = f"Δ {sd(p, sl, c['delta'])} against a bar of {sd(p, sl, c['threshold'])}."
                if c.get("noisy"):
                    why += " The interval crosses zero, so the next rung decides."
                ended = next((t.get("ended") for t in p.evals() if t["id"] == c.get("cand_task")), None)
                return dict(id=f"gate|{model}|{sl}", type="choice", opts=["Pass", "Fail"], truth="Pass" if ok else "Fail",
                            label=f"Gate · {r['rung']}", tone="pos" if ok else "neg", t=ended,
                            q=f"{_title(p, model)} on {_short(sl)}: it {_rule_text(p, c)}. Pass or fail?",
                            ctx=f"n = {c['n']:,} · against {_title(p, g.get('champion'))}", ev=c.get("cand_task") or sl,
                            why=why, w=85 if r["rung"] != (g["rungs"][0]["rung"] if g["rungs"] else "") else 80,
                            viz=(vz := _ci_viz(c, p, sl, c.get("threshold"))), axis=_room(c, vz, _sign(p)),
                            gate=dict(rule=c.get("rule"), thr=c.get("threshold") or 0))
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
    return _delta_card(f"rej|{model}", r, p, sl, _sign(p), label="Rejected", tone="neg", t=dec.get("t"),
                       q=f"{_title(p, model)}: paired change against {_title(p, base)} on {_short(sl)}?",
                       ctx=f"n = {r['n']:,}", ev=(p.latest_eval(model, sl) or {}).get("id", model),
                       why=_rej_why(p, r, sl, dec.get("reason") or m.get("reason")), w=70)


def _counts(p: Project, r: dict, sl: str) -> str:
    """The pair in words: "fixed / broken" when they give the delta, "better on / worse on" when scores are means."""
    exact = not _cont(p, sl) and abs((r["wins"] - r["losses"]) / r["n"] - r["delta"]) <= 5e-5
    a, b = ("fixed", "broke") if exact else ("was better on", "worse on")
    return f"It {a} {r['wins']:,} and {b} {r['losses']:,} of {r['n']:,}"


def _rej_why(p: Project, r: dict, sl: str, reason) -> str:
    """Why a candidate was rejected: its own result against the bar it missed, then the ledger's reason when that
    reads as a sentence (a squashed or path-laden note teaches nothing)."""
    lo, hi = sorted((r["lo"], r["hi"]))
    side = ("the whole 90% interval is below zero" if hi < 0 else "the whole 90% interval is above zero, yet another check failed"
            if lo > 0 else "the 90% interval crosses zero, so no gain is shown")  # deltas come signed: above zero is better
    out = f"{_counts(p, r, sl)} on {_short(sl)}: {side}."
    txt = re.sub(r"(?:/[\w.\-]+){2,}\S*", "", _first(reason, 160)).strip(" ;:,")
    if txt and txt.count(" ") >= 3:
        out += f" Ledger: {txt.rstrip('.')}."
    return out


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
    rows = [dict(label=_title(p, m), tag="", v=vals[m], hl=2 if m == best else 0) for m in ms]
    if ref is not None:
        rows.append(dict(label=_title(p, champ), tag="champion", v=ref, hl=3))
    return dict(id="batch|" + sl + "|" + ",".join(ms), type="choice", opts=[_title(p, m) for m in ms], truth=_title(p, best),
                label=f"{len(ms)} rejected", tone="neg", t=max(_f((p.latest_eval(m, sl) or {}).get("ended")) for m in ms),
                q=f"Which of these scored highest on {_short(sl)}?", ctx=f"n = {p.slices()[sl]['n']:,}",
                ev=sl, why=f"All {len(ms)} were rejected; the best reached {sv(p, sl, vals[best])}.", w=65,
                viz=_bars(p, sl, rows, ref))


def _bars(p: Project, sl: str, rows: list[dict], ref: float | None = None) -> dict:
    """A bar chart of scores. Each row: label (a model label), tag ("champion", "on <control>"), v, and its slice's
    n (0/1, shown as a count) or unit (continuous, shown in the unit; a "minus" metric flipped to the plain amount)."""
    for r in rows:
        rs = r.pop("sl", None) or sl
        if _cont(p, rs):
            r |= dict(unit=_unit(p, rs), v=-r["v"] if _neg(p, rs) else r["v"])
        else:
            r["n"] = _slc(p, rs).get("n")
    if ref is not None and _cont(p, sl) and _neg(p, sl):
        ref = -ref
    return dict(kind="bars", rows=rows, ref=ref)


def _card_hill(p: Project, name: str, model: str, counts: str = None) -> dict | None:
    """A new hill: how many of the target slice does the champion get right? (`hill|name|model|n`, a count; the
    older `hill|name|model` cards asked for a percentage and keep doing so, so old predictions still resolve.)"""
    h = p.hills().get(name)
    if not h or not h.get("target") or not model:
        return None
    sl, n = h["target"], (p.slices().get(h["target"]) or {}).get("n", 0)
    if _cont(p, sl) or not n:
        return None  # a continuous target has no answer-free axis for a guess
    v = _score(p, model, sl)
    found = h.get("found_in")
    fv = _score(p, found, sl) if found and found != model else None
    rows = [dict(label=_title(p, model), tag="champion" if model == p.champion() else "", v=v, hl=2)] if v is not None else []
    if fv is not None:
        rows.append(dict(label=_title(p, found), tag="found in", v=fv, hl=0))
    if h.get("control") and v is not None:
        cv = _score(p, model, h["control"])
        if cv is not None:
            rows.append(dict(label=_title(p, model), tag=f"on {_short(h['control'])}", v=cv, hl=0, sl=h["control"]))
    sym = h.get("symptom") or h.get("title") or name
    ran = v is not None
    band = _band(n, v if ran else 0.5)
    if counts:
        num = dict(id=f"hill|{name}|{model}|n", unit="", int=True, min=0, max=n, step=1, start=n // 2,
                   tol=max(1, round(band * n / 100)), truth=round(v * n) if ran else None,
                   q=f"How many of {n:,} does {_title(p, model)} get right on {_short(sl)}?")
    else:
        num = dict(id=f"hill|{name}|{model}", unit="%", min=0, max=100, step=0.5, start=50, tol=band,
                   truth=round(100 * v, 1) if ran else None, q=f"{_title(p, model)} on {_short(sl)}: its score?")
    return dict(type="number", **num,
                label="New hill" if ran else "Hill · no run yet", tone="acc" if ran else "warn", t=h.get("created"),
                ctx=f"n = {n:,} · {_first(sym, 140)}", ev=sl,
                why=(f"{h['share']['count']} of {h['share']['of']} {h['share'].get('of_what') or 'errors'}." if isinstance(h.get("share"), dict) and h["share"].get("count") is not None
                     else _first(h.get("problem"), 200)) if ran else "Logged. Scored when the run lands.",
                w=60, viz=_bars(p, sl, rows) if ran else None)


def _card_run(p: Project, model: str, base: str, sl: str, task: dict | None = None) -> dict | None:
    """A run that has not landed: will the candidate beat `base`? Resolves when a complete run exists."""
    r = _pair(p, model, base, sl, _sign(p))
    live = task or next((t for t in p.tasks() if t.get("kind") == "eval" and t.get("model") == model and t.get("slice") == sl), None)
    if not r and not live:
        return None
    pr = (live or {}).get("progress") or {}
    stalled = r is None and (live or {}).get("status") == "stalled"
    ctx = f"{pr.get('done', 0):,} of {pr['total']:,} done" if r is None and pr.get("total") else f"n = {(r or {}).get('n') or (p.slices().get(sl) or {}).get('n', 0):,}"
    truth = None if r is None else ("Yes" if r["delta"] > 0 else "No")
    why = ("No heartbeat; scored if the run is restarted and lands." if stalled else "Logged. Scored when the run lands.") if r is None else f"Δ {sd(p, sl, r['delta'])}: {r['wins']} fixed, {r['losses']} broken."
    return dict(id=f"run|{model}|{base}|{sl}", type="choice", opts=["Yes", "No"], truth=truth,
                label="Landed" if r else "Stalled" if stalled else "Running", tone="acc" if r else "neg" if stalled else "warn",
                t=(live or {}).get("created"), q=f"Will {_title(p, model)} beat {_title(p, base)} on {_short(sl)}?",
                ctx=ctx, ev=(live or {}).get("id") or sl, why=why, w=50, viz=(vz := _ci_viz(r, p, sl) if r else None),
                axis=_room(r, vz, _sign(p)) if r else None)


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
                    q=f"{_title(p, ev['model'])} against {_title(p, base)} on {_short(sl)}: better, worse or can't tell yet?",
                    ctx=f"From the question “{_first(q.get('title') or qid, 90)}” · n = {r['n']:,}",
                    ev=(p.latest_eval(ev["model"], sl) or {}).get("id", sl),
                    why=_first(q.get("claim"), 200) or truth, w=75, viz=(vz := _ci_viz(r, p, sl)), axis=_room(r, vz, _sign(p)))
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

    facts: set = set()

    def add(c):
        if not c or c["id"] in seen:
            return
        v = c.get("viz") or {}
        # one card per fact: the same pair (same counts and delta) or the same goal count asked twice is one card
        fact = (v.get("kind"), v.get("n"), v.get("wins"), v.get("losses"), round(v.get("delta") or 0, 6)) if v.get("kind") == "ci" \
            else ("goal", v.get("N"), v.get("have")) if v.get("kind") == "goal" else None
        if fact and fact in facts:
            return
        if fact:
            facts.add(fact)
        seen.add(c["id"])
        out.append(c)

    decs = [d for d in _decisions(p) if _f(d.get("t")) > since]
    champ, models = p.champion(), p.models()
    for d in decs:
        if d.get("kind") == "promote":
            add(_card_promote(p, d["model"]))
    for name, g in p.goals().items():  # an open goal is news when it opened or the champion's score on it moved
        moved = g.get("status") == "open" and champ and _f((p.latest_eval(champ, g.get("slice")) or {}).get("ended")) > since
        if moved or _f(g.get("created")) > since or any(d.get("kind") == "promote" for d in decs):
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
            add(_card_hill(p, name, champ, "n"))
    for qid, q in (_read(p.dir / "questions.json", {}) or {}).items():
        if isinstance(q, dict) and _f(q.get("answered") or q.get("updated") or q.get("created")) > since:
            add(_card_question(p, qid))
    for t in p.tasks():  # a run stalled for more than a day is dead: no card asks about it
        if t.get("kind") == "eval" and (t.get("status") == "running" or t.get("status") == "stalled" and not _dead(t)) and t.get("model") not in (None, champ) \
                and champ and t.get("slice") and p.slice_evals(champ, t["slice"]):
            add(_card_run(p, t["model"], champ, t["slice"], t))
    out.sort(key=lambda c: (-c.get("w", 0), -_f(c.get("t"))))
    return out[:MAX_CARDS]


PUBLIC = ("id", "type", "opts", "unit", "int", "min", "max", "step", "start", "tol", "label", "tone", "t", "q", "ctx", "ev")


def conf_floor(c: dict) -> float:
    """The lowest confidence a card takes: chance for a choice (1 in 4 -> 0.25, on a 5% step), near 0 for a band."""
    if c.get("type") == "choice" and c.get("opts"):
        return max(0.05, (100 // len(c["opts"])) // 5 * 5 / 100)
    return 0.05


def public(c: dict, pred: dict | None = None) -> dict:
    """What the page gets: the question always, the answer only once this viewer has predicted."""
    out = {k: c[k] for k in PUBLIC if k in c} | dict(open=c.get("truth") is None, cmin=conf_floor(c))
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
    conf = min(1.0, max(conf_floor(c), _f(body.get("conf"), 0.7)))
    rec = dict(t=_now(), viewer=viewer, card=c["id"], q=c["q"], guess=guess, conf=round(conf, 3),
               truth=c.get("truth"), hit=_hit(c, guess))
    _append(p.dir / "predictions.jsonl", rec)
    from .teach import step_for
    st = step_for(p, c, viewer)
    return 200, dict(prediction=rec, card=public(c, rec) | (dict(step=st) if st else {}))


def calibration(preds: list[dict]) -> dict:
    """Hits, Brier score and a reliability curve (stated confidence vs hit rate) over the scored predictions."""
    sc = [r for r in preds if r.get("hit") is not None]
    bins = []
    for a, b in ((0, 0.2), (0.2, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
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


# ---------------------------------------------------------------- routes and CLI

def _why_empty(p: Project) -> str | None:
    """Why a project has nothing to predict at all, when the reason is in the ledger."""
    done = any(t.get("slice_hash") == (p.slices().get(t.get("slice")) or {}).get("hash") for t in p.evals())
    if not p.champion():
        return "No champion yet, and no finished runs on a current slice." if not done else "No champion yet."
    return None if done else "No finished runs on a current slice."


def aliases(viewer: str) -> set:
    """A person id (people.py) also owns what they did under their name before ids existed."""
    from . import people
    n = (people.roster().get(viewer) or {}).get("name") if people.ID.match(viewer or "") else None
    return {n} if n else set()


def brief(p: Project, since: float = 0, viewer: str = "anon") -> dict:
    from . import course, teach
    p._gates = {}
    with p.snapshot():
        cs = cards(p, since)
        al = aliases(viewer)
        preds = [r for v in {viewer} | al for r in predictions(p, v)]
        mine = {r["card"]: r for r in preds}
        # a predicted card that has since dropped out of the window still shows when it is open
        extra = [card(p, r["card"]) for r in preds if r.get("truth") is None and not r.get("resolved") and r["card"] not in {c["id"] for c in cs}]
        cs += [c for c in extra if c]
        pub = [public(c, mine.get(c["id"])) | dict(needs=course.needs(c["id"])) for c in cs]
        prof = teach.attach(p, cs, pub, viewer, al)
        cal = calibration(preds)
        # "right" counts every answered card, predictions and the other methods alike; Brier is predictions only
        done = [r for r in teach.attempts(p, viewer, al) if not r.get("skip") and r.get("hit") is not None]
        cal |= dict(all_n=cal["n"] + len(done), all_hits=cal["hits"] + sum(bool(r["hit"]) for r in done))
        return dict(now=_now(), since=since, viewer=viewer, cards=pub,
                    empty=None if cs else _why_empty(p),
                    course=course.summary(p, viewer, al), calibration=cal,
                    understanding=understanding(p, viewer),
                    open=[r for r in preds if r.get("hit") is None],
                    teach=dict(profile=prof, labels=teach.LABEL))


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


from . import course as _course  # noqa: E402,F401  (registers /api/course with the Brief)
