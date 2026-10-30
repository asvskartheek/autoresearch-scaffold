"""The 101 course: one short lesson per idea the dashboard uses, built from this project's own ledger, and spaced
review of what each person has learned.

Each lesson is a figure to drag or click first, a sentence or two, and a check. Figures use this project's real
numbers where the ledger has them (labelled `example` where it does not). Lesson ids are stable: other views link
terms to `#course/<id>`.

Memory: every check answered (in a lesson, a review or a Brief primer) is a row in .research/course.jsonl:
{t, viewer, item, hit, how}. Kept that simple so another learner store can import it. An item is due again 1, 3, 7
and then 21 days after a run of 1, 2, 3, 4+ right answers; a miss resets the run and makes it due now.

  GET  /api/course?viewer=          {lessons: [lesson], memory: {item: state}, due: [item], intervals}
  POST /api/course {viewer, item, hit, how}   -> {memory: state}
"""
from __future__ import annotations

import math
import time

from . import features
from .core import Project, _append, _jsonl

BASICS = ("goal", "champion", "candidate", "slice", "paired-delta", "interval", "gate", "rung", "ladder", "hill", "brief")
PROJECT = ("project-goal", "project-data", "project-champion", "project-hills")
IDS = BASICS + PROJECT
TITLE = {"goal": "Goal", "champion": "Champion", "candidate": "Candidate", "slice": "Slice", "paired-delta": "Paired delta",
         "interval": "Interval", "gate": "Gate", "rung": "Rung", "ladder": "Ladder", "hill": "Hill", "brief": "Brief",
         "project-goal": "This goal", "project-data": "Data and slices", "project-champion": "This champion",
         "project-hills": "These hills"}
INTERVALS = (1, 3, 7, 21)  # days until the next review after 1, 2, 3, 4+ right answers in a row
DAY = 86400.0

# the ideas a Brief card leans on: a catch-up shows each one's lesson before the first card that needs it
NEEDS = {"promote": ["champion", "paired-delta", "interval"], "rej": ["candidate", "paired-delta", "interval"],
         "gate": ["candidate", "gate", "rung"], "goal": ["goal", "champion"], "hill": ["hill", "slice"],
         "run": ["candidate", "slice"], "q": ["paired-delta", "interval"], "batch": ["candidate", "slice"]}


def needs(card_id: str) -> list[str]:
    return list(NEEDS.get(str(card_id).split("|")[0], []))


# ---------------------------------------------------------------- memory
def _log(p: Project):
    return p.dir / "course.jsonl"


def rows(p: Project, viewer: str | None = None, aliases: set | None = None) -> list[dict]:
    who = {viewer} | (aliases or set()) if viewer else None
    return [r for r in _jsonl(_log(p)) if isinstance(r, dict) and r.get("item") and (who is None or r.get("viewer") in who)]


def memory(rs: list[dict], now: float | None = None) -> dict:
    """Per item: tries, right, the current run of right answers, when it was last tried and when it is due."""
    now = time.time() if now is None else now
    out: dict = {}
    for r in sorted(rs, key=lambda r: r.get("t") or 0):
        s = out.setdefault(r["item"], dict(n=0, hits=0, run=0, last=None, due=None, learned=False))
        t = float(r.get("t") or 0)
        s["n"] += 1
        s["last"] = t
        if r.get("hit"):
            s["hits"] += 1
            s["run"] += 1
            s["learned"] = True
            s["due"] = t + INTERVALS[min(s["run"], len(INTERVALS)) - 1] * DAY
        else:
            s["run"] = 0
            s["due"] = t  # a miss: due again now
    for s in out.values():
        s["is_due"] = s["due"] is not None and s["due"] <= now
    return out


def due(mem: dict) -> list[str]:
    """Items to review now, the most overdue first."""
    return [k for k, s in sorted(mem.items(), key=lambda kv: kv[1]["due"] or 0) if s["is_due"]]


def record(p: Project, body: dict) -> tuple[int, dict]:
    item = str(body.get("item") or "")
    if not isinstance(body.get("hit"), bool):
        return 400, dict(error="hit must be true or false")
    if item not in IDS:
        return 404, dict(error="unknown lesson")
    viewer = str(body.get("viewer") or "anon")[:60]
    how = body.get("how") if body.get("how") in ("lesson", "review", "primer") else "lesson"
    _append(_log(p), dict(t=time.time(), viewer=viewer, item=item, hit=bool(body.get("hit")), how=how))
    return 200, dict(memory=memory(rows(p, viewer)).get(item))


def summary(p: Project, viewer: str, aliases: set | None = None) -> dict:
    """What the Brief needs without building the lessons: ids, titles, memory and what is due."""
    mem = memory(rows(p, viewer, aliases))
    return dict(lessons=[dict(id=i, t=TITLE[i], group="basics" if i in BASICS else "project") for i in IDS],
                memory=mem, due=due(mem))


# ---------------------------------------------------------------- the lessons
def _check(q, o, a, why="", live=False):
    """A multiple-choice check; numbers read with thousands separators, repeats and negatives dropped. `live` marks a
    check built from recorded results, which a Brief primer must not ask: it would give away the card's answer."""
    fmt = lambda x: f"{x:,}" if isinstance(x, int) else str(x)
    o = list(dict.fromkeys(fmt(x) for x in o if not (isinstance(x, int) and x < 0)))
    if fmt(a) not in o or len(o) < 2:
        return None
    return dict(q=q, o=o, a=fmt(a), why=why, live=True) if live else dict(q=q, o=o, a=fmt(a), why=why)


def _count(a: int, near: list, lo: int, hi: int, k: int = 3) -> list[int]:
    """`a` and up to `k` wrong counts a learner could reach: the slips in `near` first, then neighbours of `a`, all
    distinct and inside [lo, hi] (no "13" on a 3-example slice)."""
    out = [a]
    for x in list(near) + [a + d for d in (1, -1, 2, -2, 5, -5)]:
        if len(out) > k:
            break
        if isinstance(x, (int, float)) and lo <= int(x) <= hi and int(x) not in out:
            out.append(int(x))
    return out


def _others(a: str, pool, k: int = 2) -> list[str]:
    """`a` and up to `k` other names from `pool`, none equal to `a`."""
    return [a] + [x for x in dict.fromkeys(pool) if x and x != a][:k]


def _n(x) -> str:
    return f"{int(round(x)):,}"


def _amt(u: str, x: float) -> str:
    """A signed amount: "+5.2 pts" on a 0/1 slice, "−1,071 ms" in a continuous unit."""
    sg = "+" if x > 0 else "−" if x < 0 else ""
    a = abs(x)
    num = f"{a:.2f}".rstrip("0").rstrip(".") if u == "pts" else (f"{a:,.0f}" if a >= 100 else f"{float(f'{a:.3g}'):g}")
    return f"{sg}{num} {u}".strip()


def _goals(p: Project) -> list[dict]:
    out = []
    for name in p.goals():
        try:
            out.append(p.goal_status(name))
        except SystemExit:
            continue
    return sorted(out, key=lambda g: g.get("status") != "open")


def _goal(p: Project) -> dict | None:
    """A measured binary goal, used only by exercises that count correct answers."""
    from . import learn
    return next((g for g in _goals(p) if g.get("kpi", "score") == "score" and
                 g.get("value") is not None and g.get("n") and not learn._cont(p, g["slice"])), None)


def _goal_row(p, st, learn):
    """Normalize the ledger's score convention once; no unitless negative latency."""
    sl, kpi = st["slice"], st.get("kpi", "score")
    row = dict(label=st.get("title") or st["name"], status=st.get("status"), slice=sl,
               met=st.get("met", False), measured=st.get("value") is not None,
               n=st.get("n") or (p.slices().get(sl) or {}).get("n"),
               model=learn._title(p, st.get("model")) if st.get("model") else None)
    if kpi == "score" and st.get("n") and not learn._cont(p, sl):
        n = int(st["n"])
        row.update(N=n, have=round(st["value"] * n) if st.get("value") is not None else None,
                   need=math.ceil(st["target"] * n - 1e-9))
    else:
        sign = -1 if kpi == "score" and learn._neg(p, sl) else 1
        from .questions import _goal_units_of
        unit = _goal_units_of(st, learn._slc(p, sl))["unit"]
        if kpi in ("cost", "cost_per_example"):
            unit = "USD/example"
        row.update(value=sign * st["value"] if st.get("value") is not None else None,
                   target=sign * st["target"], unit=unit, kpi=kpi,
                   lower=((not st.get("higher_is_better", True)) != (sign == -1)))
    return row


def _goal_checks(p, st, learn):
    """Test the evidence needed for this claim, not copying a displayed count."""
    title, sl = st.get("title") or st["name"], st["slice"]
    if not st.get("model"):
        answer = f"Register a champion and measure it on {sl}"
        return [_check(f"“{title}” has a target, but no champion is registered. What evidence step comes first?",
                       [answer, "Treat the target as the current result", "Promote an unmeasured candidate"], answer,
                       "The claim needs a named reference system and a qualifying measurement; the target alone supplies neither.")]
    if st.get("value") is None:
        return [_check(f"“{title}” has a target on {sl}, but no qualifying champion measurement. What is missing?",
                       [f"A complete champion measurement on {sl}", "A successful development example", "A finished implementation task"],
                       f"A complete champion measurement on {sl}", "A target is a requirement, not evidence that it has been met.")]
    return [_check(f"A candidate improves one targeted failure, but its result on {sl} is still unknown. Does that establish “{title}”?",
                   [f"No; the champion must meet the target on {sl}", "Yes; a hill improvement establishes the goal", "Yes; any complete run establishes it"],
                   f"No; the champion must meet the target on {sl}", "The goal claim is tied to its declared slice and target; a local improvement does not establish it.")]


def _ledger(p: Project) -> dict:
    """What several lessons share, read once."""
    from . import learn
    champ, models, cfg = p.champion(), p.models(), p.config
    full = f"{cfg.get('primary_dataset')}/full" if cfg.get("primary_dataset") else None
    if full and full not in p.slices():
        full = None
    promo = next((c for c in (learn._card_promote(p, d["model"]) for d in reversed(learn._decisions(p)) if d.get("kind") == "promote") if c), None)
    checks = []
    for m, v in models.items():
        if v.get("status") == "candidate":
            try:
                g = learn._gate(p, m)
            except SystemExit:
                continue
            for r in g.get("rungs", []):
                for c in r.get("checks", []):
                    if c.get("delta") is not None and c.get("state") in ("pass", "fail"):
                        checks.append(dict(c, model=m, rung=r["rung"]))
    return dict(champ=champ, models=models, full=full, promo=promo, checks=checks, goal=_goal(p), goals=_goals(p))


def lesson_goal(p, L, learn):
    goals = L.get("goals") or _goals(p)
    if goals:
        g = goals[0]
        cs = []
        if g.get("value") is not None and g.get("kpi", "score") == "score" and g.get("n") and not learn._cont(p, g["slice"]):
            n = int(g["n"])
            have, need = round(g["value"] * n), math.ceil(g["target"] * n - 1e-9)
            fig = dict(kind="goal", N=n, have=have, need=need, slice=g["slice"], title=g.get("title") or g["name"])
            left = need - have
            head = f"On {g['slice']} the champion gets {_n(have)} of {_n(n)} right. The goal needs {_n(need)}."
            b = max(1, min(have, left // 4))
            if left > 1 and have:  # the figure prints the gap; ask it after a candidate also breaks some
                cs.append(_check(f"{head} A candidate fixes {_n(left)} of the champion's wrong answers but breaks {_n(b)} it had right. How many more does it still need?",
                                 _count(b, [0, left, left - b, 2 * b], 0, n), b,
                                 f"{_n(have)} + {_n(left)} − {_n(b)} = {_n(have + left - b)}, so {_n(need - have - left + b)} short of {_n(need)}. Broken answers cancel fixed ones.", live=True))
            elif left > 0:  # a met goal has nothing to count; its evidence check stands alone
                cs.append(_check(f"{head} How many more?", _count(left, [need, n - have, have], 0, n), left, f"{_n(need)} − {_n(have)} = {_n(left)}.", live=True))
        else:
            fig = dict(kind="goals", rows=[_goal_row(p, g, learn)])
        return dict(say="This goal fixes the measurement and target for the project's claim; development results are evidence toward it, not substitutes for it.",
                    fig=fig, checks=cs + _goal_checks(p, g, learn))
    return dict(say="No goal is registered yet. Define a measurement, a frozen slice and a target before claiming progress.",
                fig=dict(kind="goals", rows=[]), checks=[_check("What makes a research goal testable?",
                     ["A named metric, frozen slice and target", "A model name alone", "A deadline alone"], "A named metric, frozen slice and target",
                     "These specify exactly what evidence can meet the goal.")])


def _scores(p, L, learn, k=7):
    """Models with a run on the primary full slice, as counts right (0/1) or values."""
    sl = L["full"] or next((g["slice"] for g in L.get("goals", []) if g.get("kpi", "score") == "score"), None)
    if not sl:
        return sl, []
    out = []
    for m, v in L["models"].items():
        s = learn._score(p, m, sl)
        if s is not None:
            out.append(dict(id=m, label=learn._title(p, m), v=s, status=v.get("status") or "", champ=m == L["champ"]))
    out.sort(key=lambda r: -r["v"] * learn._sign(p))
    if not any(r["champ"] for r in out[:k]):
        out = out[: k - 1] + [r for r in out if r["champ"]]
    return sl, out[:k]


def lesson_champion(p, L, learn):
    sl, rs = _scores(p, L, learn)
    n = (p.slices().get(sl) or {}).get("n") if sl else None
    cont = bool(sl) and learn._cont(p, sl)
    fig = dict(kind="bars", slice=sl or "", n=None if cont else n,
               empty="No recorded champion measurement on a declared goal slice." if not sl else f"No completed measurements on {sl}.",
               unit=learn._unit(p, sl) if cont else "", better=-1 if cont and learn._neg(p, sl) else 1,
               rows=[dict(label=r["label"], v=-r["v"] if cont and learn._neg(p, sl) else r["v"], status=r["status"], hl=r["champ"]) for r in rs])
    champ = next((r for r in rs if r["champ"]), None)
    cs = [_check("A new idea is measured against what?", ["The champion, on the same examples", "Its own earlier run", "Nothing"],
                 "The champion, on the same examples", "Use the same examples and compatible evaluation setup; a changed judge or harness can confound the comparison.")]
    nxt = next((r for r in rs if not r["champ"]), None)
    if champ and nxt and n and not cont and champ["v"] >= nxt["v"]:
        a, b = round(champ["v"] * n), round(nxt["v"] * n)
        cs.insert(0, _check(f"On {sl}, how many more examples does the champion get right than {nxt['label']}?",
                            _count(a - b, [a, b, n - a, 2 * (a - b)], 0, n), a - b,
                            f"{_n(a)} − {_n(b)} = {_n(a - b)} of the same {_n(n)} examples.", live=True))
    elif champ and nxt and n and not cont:
        a, b = round(champ["v"] * n), round(nxt["v"] * n)
        ans = "No: only a recorded promotion changes the champion"
        cs.insert(0, _check(f"On {sl}, {nxt['label']} gets {_n(b)} of {_n(n)} right, more than the champion's {_n(a)}. Is it the champion now?",
                            [ans, "Yes: the highest score is the champion", "Yes, once it is measured on the full slice"], ans,
                            "A candidate becomes the champion when it passes its gates and the promotion is recorded, not by a single higher score.", live=True))
    return dict(say="The champion is the registered reference system. A fair candidate comparison uses the same examples and a compatible evaluation setup.", fig=fig, checks=cs)


def lesson_candidate(p, L, learn):
    rows_ = []
    for m, v in sorted(L["models"].items(), key=lambda kv: -float(kv[1].get("created") or 0)):
        if v.get("status") in ("candidate", "rejected", "champion"):
            rows_.append(dict(label=learn._title(p, m), status=v["status"], detail=learn._first(v.get("change") or v.get("reason"), 140),
                              parent=learn._title(p, v["parent"]) if v.get("parent") and v.get("parent") != m else ""))
        if len(rows_) >= 6:
            break
    cs = [_check("A candidate passes every required rung, but no promotion has been recorded. What is its status?",
                 ["Ready for promotion; still a candidate", "Already the champion", "Rejected until retrained"],
                 "Ready for promotion; still a candidate", "Passing gates makes promotion eligible. The registered champion changes only when promotion is recorded.")]
    rej = sum(v.get("status") == "rejected" for v in L["models"].values())
    if rej:
        cs.append(_check("How many candidates have been rejected in this project so far?", _count(rej, [rej + 1, rej - 1, rej * 2], 0, len(L["models"])), rej,
                         "Rejected candidates stay in the ledger with their reason. Negative results are results.", live=True))
    return dict(say="A candidate tests a proposed change. Its gates can make it ready for promotion; the recorded promotion is a separate decision.",
                fig=dict(kind="list", rows=rows_), checks=cs)


def _slice_rows(p, learn, only=None):
    out, datasets = [], p.datasets()
    selected = [(name, sl) for name, sl in p.slices().items() if not only or name.split("/", 1)[0] == only]
    many = len({name.split("/", 1)[0] for name, _ in selected}) > 1
    for name, sl in selected:
        ds = name.split("/", 1)[0]
        owner = datasets.get(ds)
        dataset_n = owner.get("size") if owner else None
        n = sl.get("n") if sl.get("n") is not None else len(sl.get("ids") or [])
        # A registered dataset supplies the denominator; another slice never does.
        if dataset_n is not None and dataset_n < n:
            dataset_n = None
        out.append(dict(id=name, name=name if many else learn._short(name), ds=ds, n=n,
                        dataset_n=dataset_n, kind=sl.get("kind") or ""))
    return sorted(out, key=lambda r: (r["ds"], -r["n"]))


def lesson_slice(p, L, learn):
    rs = _slice_rows(p, learn, p.config.get("primary_dataset") or None)
    picked = rs[0]["id"] if rs else "a frozen slice"
    cs = []
    shown = rs[:8]
    # a 0/1 slice smaller than the largest, so its own denominator and the bigger one differ
    pick = next((r for r in shown if r["n"] and r["n"] < shown[0]["n"] and not learn._cont(p, r["id"])), None) if shown else None
    if pick:
        big = pick["dataset_n"] or shown[0]["n"]
        one = lambda m: _amt("pts", 100 / m)
        cs.append(_check(f"One more right answer on {pick['id']} moves a model's score on it by how much?",
                         [one(pick["n"]), one(big), "+1 pt", one(pick["n"] / 2)], one(pick["n"]),
                         f"{pick['id']} has {_n(pick['n'])} examples, so one is 100 / {_n(pick['n'])} = {one(pick['n'])}. Each slice is its own denominator."))
    return dict(say="A slice fixes which examples are measured. Its size is not a score, and slices from different datasets do not share a denominator.",
                fig=dict(kind="slices", scale_max=max((r["n"] for r in rs), default=1), rows=shown),
                checks=cs + [_check(f"One example must change in {picked}. How can earlier results remain interpretable?",
                               ["Create a new slice and measure both systems on it", "Edit the frozen slice and reuse the old scores", "Compare the new candidate score with any old baseline"],
                               "Create a new slice and measure both systems on it", "A changed ID set is a new measurement scope; both sides need matching evidence.")])


def lesson_paired(p, L, learn):
    v = (L["promo"] or {}).get("viz") or {}
    from .teach import counts_give_delta
    if v.get("unit") == "pts" and v.get("n") and counts_give_delta(v):
        w, l, n, ex = v["wins"], v["losses"], v["n"], False
    else:
        w, l, n, ex = 12, 5, 200, True
    # the figure already prints (fixed − broken) / n, so ask for the Δ after k of the fixed examples break instead
    k = min(w, 10)
    w2, l2 = w - k, l + k
    right = _amt("pts", 100 * (w2 - l2) / n)
    return dict(say="Pair each example: fixed if the new model gets it and the champion did not, broken the other way. Δ = (fixed − broken) / n.",
                fig=dict(kind="paired", fixed=w, broken=l, n=n, example=ex, provenance="Frozen promotion evidence" if not ex else ""),
                checks=[_check(f"{w:,} fixed, {l:,} broken, n = {n:,}. If {k} of the fixed examples had broken instead, what would the paired Δ be?",
                               [_amt("pts", 100 * x / n) for x in (w2 - l2, w2 - l, w - l, l2 - w2)], right,
                               f"{w2:,} fixed and {l2:,} broken: ({w2:,} − {l2:,}) / {n:,} = {right}. Each one moves from fixed to broken, so Δ falls twice as fast.", live=not ex),
                        _check(f"On the same {n:,} examples, one extra case changes from correct under the baseline to wrong under the candidate. Fixed cases do not change. What happens to paired Δ?",
                               [f"It falls by {100 / n:.3g} points", f"It rises by {100 / n:.3g} points", "It stays unchanged"], f"It falls by {100 / n:.3g} points",
                               "The broken count increases by one while n and the fixed count stay constant."),
                        _check("Two models score the same on one slice. Can their paired Δ be non-zero?", ["No", "Yes"], "No",
                               "Same score means fixed = broken, so the Δ is 0.")])


def _ci_of(p, learn, c):
    """A check or card as an interval figure in display units, ends in order (a "minus" metric flips them)."""
    v = learn._ci_viz(c, p, c.get("slice")) if c.get("slice") else c
    return dict(delta=v["delta"], lo=min(v["lo"], v["hi"]), hi=max(v["lo"], v["hi"]), n=v["n"], unit=v.get("unit") or "pts", better=v.get("better", 1))


def _about(x: float) -> str:
    return f"About {float(f'{x:.2g}'):,.0f}"


def _reach_zero(fig):
    """Holding the effect fixed, the n at which the interval's edge reaches zero: n × (half-width / |Δ|)²."""
    d, half, n = abs(fig["delta"]), (fig["hi"] - fig["lo"]) / 2, fig["n"]
    if d < 1e-12 or half <= 0:
        return None
    r = half / d
    at = n * r * r
    if at < 4:
        return None
    return _check(f"Δ {_amt(fig['unit'], fig['delta'])}, 90% interval {_amt(fig['unit'], fig['lo'])} to {_amt(fig['unit'], fig['hi'])} on n = {n:,}. "
                  "Holding the effect fixed, at about what n does the interval's edge reach zero?",
                  [_about(at), _about(n * r), _about(at * 4), _about(at / 4)], _about(at),
                  f"The width shrinks as 1/√n: n × ({_amt(fig['unit'], half).lstrip('+')} / {_amt(fig['unit'], d).lstrip('+')})² ≈ {at:,.0f}. "
                  + ("More examples than that make it clear zero." if fig["lo"] <= 0 <= fig["hi"] else "Fewer than that and it would cross zero."), live=not fig.get("example"))


def lesson_interval(p, L, learn):
    noisy = next((c for c in L["checks"] if c.get("noisy") and c.get("lo") is not None and abs(c.get("delta") or 0) > 1e-9), None)
    src = _ci_of(p, learn, noisy) if noisy else None
    fig = dict(kind="interval", **(src or dict(delta=1.6, lo=-0.5, hi=3.7, n=185, unit="pts")), example=src is None, source_slice=noisy.get("slice", "") if noisy else "")
    return dict(say="An interval that crosses zero does not establish a direction. Holding the effect fixed, its width shrinks as 1/√n.",
                fig=fig,
                checks=[_reach_zero(fig),
                        _check("In this fixed-effect projection, four times as many independent observations would do what to interval width?",
                               ["Halve the width", "Quarter the width", "Leave the width unchanged"], "Halve the width",
                               "Width scales as 1/√n, so multiplying n by four divides width by two. A real new sample may also change the measured effect."),
                        _check("Under this fixed-effect projection, what can reduce uncertainty?", ["More independent observations from the same population", "Recounting identical observations as new data"], "More independent observations from the same population",
                               "The 1/√n approximation assumes independent observations; repeating identical data does not add independent evidence.")])


def lesson_gate(p, L, learn):
    c = next((c for c in L["checks"] if c.get("rule") in ("better", "not_worse")), None)
    if c:
        v = _ci_of(p, learn, c)
        k = 100 if v["unit"] == "pts" else (-1 if learn._neg(p, c["slice"]) else 1)
        fig = dict(kind="gate", rule=c["rule"], bar=k * (c.get("threshold") or 0), delta=v["delta"], unit=v["unit"],
                   slice=learn._short(c["slice"]), model=learn._title(p, c["model"]), rung=c["rung"], better=-1 if k < 0 else 1)
        rule = f"{fig['model']} on {c['slice']}: it {learn._rule_text(p, c)}. It measured Δ {learn.sd(p, c['slice'], c['delta'])}."
    else:
        fig = dict(kind="gate", rule="not_worse", bar=-1.0, delta=-0.4, unit="pts", slice="random100", model="Example", rung="random100", example=True)
        rule = "It may lose at most 1 pt. It measured Δ −0.4 pts."
    # the figure shows this run's verdict; ask for the Δ on the other side of the bar
    sign, bar = fig.get("better", 1), fig["bar"]
    other = 2 * bar - fig["delta"] if abs(fig["delta"] - bar) > 1e-9 else bar - sign * (1 if fig["unit"] == "pts" else abs(bar) or 1)
    other = round(other, 1) if fig["unit"] == "pts" else float(f"{other:.3g}")  # as precise as the Δ it mirrors reads
    ok = sign * other > sign * bar if fig["rule"] == "better" else sign * other >= sign * bar
    q = f"{rule} Same rule, but say the Δ had been {_amt(fig['unit'], other)}. Pass or fail?"
    direction = "below" if fig.get("better", 1) < 0 else "above"
    return dict(say=f"For this metric, improvement moves Δ {direction} zero. The configured gate compares Δ with its declared bar; uncertainty is shown separately.", fig=fig,
                checks=[_check(q, ["Pass", "Fail"], "Pass" if ok else "Fail", f"The bar is {_amt(fig['unit'], bar)}; pass when Δ is on the good side of it.", live=not fig.get("example")),
                        _check("Say a candidate passes this comparison, but the next run uses a changed harness. Can the old gate result establish that the new run passes?",
                               ["No; obtain a compatible baseline and apply the declared rule", "Yes; the model name is unchanged", "Yes; a prior pass applies to every harness"],
                               "No; obtain a compatible baseline and apply the declared rule", "A gate result belongs to its measured scope and evaluation setup; it is not a permanent property of a model.")])


def _ladder(p):
    """Resolve scope before turning a stored tolerance into a display quantity."""
    from . import learn
    models = p.models()
    chosen = next((name for name, model in models.items() if model.get("status") == "candidate"), p.champion())
    model = models.get(chosen) or {}
    if not model.get("hill") and len(p.hills()) == 1:
        model = dict(model, hill=next(iter(p.hills())))
    out = []
    for rung in p.config.get("ladder", []):
        if not rung.get("rung"):
            continue
        checks = []
        for check in rung.get("checks", []):
            ref, rule = check.get("slice") or "manual", "manual" if check.get("manual") else check.get("rule") or "manual"
            raw = -(check.get("tolerance") or 0) if rule == "not_worse" else check.get("margin") or 0
            try:
                scopes = p._resolve(ref, model) if not check.get("manual") else []
            except (KeyError, ValueError, SystemExit):
                scopes = []
            if not scopes and ref == "@hills.climbed":
                continue  # no applicable regression scope; this is not an unmeasured required check
            if not scopes:
                checks.append(dict(slice=ref, rule=rule, bar=raw, display_bar=None, unit=None, better=None, resolved=False))
                continue
            for scope in scopes:
                if learn._cont(p, scope):
                    factor = -1 if learn._neg(p, scope) else 1
                    unit = learn._unit(p, scope)
                else:
                    factor, unit = 100, "pts"
                checks.append(dict(slice=scope, source_ref=ref, rule=rule, bar=raw,
                                   display_bar=factor * raw, unit=unit, better=-1 if factor < 0 else 1, resolved=True))
        out.append(dict(rung=rung["rung"], checks=checks, model=learn._title(p, chosen) if chosen else None))
    return out


def lesson_rung(p, L, learn):
    lad = _ladder(p)
    r = max(lad, key=lambda r: len(r["checks"]), default=None)
    if not r or not r["checks"]:
        return dict(say="No applicable rung checks are configured yet. Define the measurement scopes and rules before claiming that a candidate passed.",
                    fig=dict(kind="list", rows=[]), checks=[_check("Can an empty check list establish that a proposed change is safe?",
                         ["No; required measurements and rules must be declared", "Yes; no check failed"],
                         "No; required measurements and rules must be declared", "An absence of checks is not evidence of a successful change.")])
    k = len(r["checks"])
    cs = [_check(f"A rung has {k} required check{'s' if k != 1 else ''} and one fails. Does the rung pass?", ["No", "Yes"], "No",
                 "Every required check on a rung must pass.")]
    return dict(say="A rung passes only when every required check on it passes.",
                fig=dict(kind="rung", rung=r["rung"], checks=r["checks"], model=r.get("model")), checks=cs)


def lesson_ladder(p, L, learn):
    lad = _ladder(p) or [dict(rung=x, checks=[]) for x in ("dev", "random100", "full")]
    names = [r["rung"] for r in lad]
    cand = next((m for m, v in L["models"].items() if v.get("status") == "candidate"), None)
    status = []
    if cand:
        try:
            status = [r.get("status") for r in learn._gate(p, cand).get("rungs", [])]
        except SystemExit:
            status = []
    cs = []
    if len(names) >= 2:
        cs.append(_check(f"A candidate passes {names[0]}. What runs next?", names[1:3] + names[:1], names[1],
                         "Rungs run in order, small and cheap first."))
    cs.append(_check("A candidate fails a rung. Do later rungs run?", ["No", "Yes"], "No", "The first fail stops the climb."))
    return dict(say="The project declares its gate order. A candidate follows that order and stops at the first failed rung; passing the ladder makes it ready for a promotion decision.",
                fig=dict(kind="ladder", rungs=lad, model=learn._title(p, cand) if cand else "", status=status), checks=cs)


def _hill_rows(p, learn):
    out = []
    for name, h in p.hills().items():
        sh = h.get("share") if isinstance(h.get("share"), dict) else {}
        out.append(dict(id=name, label=learn._first(h.get("title") or name, 60).split(" [")[0], status=h.get("status") or "",
                        count=sh.get("count"), of=sh.get("of"), of_what=sh.get("of_what") or "",
                        target=h.get("target") or "", control=h.get("control") or "",
                        examples=h.get("examples") or [],
                        detail=learn._first(h.get("symptom") or h.get("problem"), 140)))
    return sorted(out, key=lambda r: -(r["count"] or 0))


def lesson_hill(p, L, learn):
    hs = _hill_rows(p, learn)
    h = next((r for r in hs if r["target"] and r["control"]), None)
    cs = []
    if h:
        cs.append(_check(f"“{h['label']}”: which slice measures it?", [h["target"], h["control"]], h["target"],
                         "A hill's own slice holds the failure. Its control slice checks nothing else broke."))
    cs.append(_check("A hill is climbed when…", ["a candidate fixes that failure without breaking others", "its slice is edited", "a task ends"],
                     "a candidate fixes that failure without breaking others", "The declared gate ladder and recorded promotion establish the hill result; one illustrative example cannot establish it."))
    return dict(say="A hill is one kind of failure with its own slice to measure it.", fig=dict(kind="share", rows=hs[:5]), checks=cs)


def lesson_brief(p, L, learn):
    g = L["goal"]
    if g:
        fig = dict(kind="guess", N=int(g["n"]), truth=round(g["value"] * g["n"]), slice=g["slice"], tol=max(2, round(int(g["n"]) * .01)))
    else:
        fig = dict(kind="goals", rows=[_goal_row(p, g, learn) for g in (L.get("goals") or _goals(p))])
    return dict(say="The Brief asks you to predict a recorded result before revealing its evidence. A prediction changes your understanding, not the research record.", fig=fig,
                checks=[_check("Your prediction was wrong, but the measured result is valid. What should change?",
                               ["Your expectation; keep the measured evidence", "The recorded score to match your prediction", "The goal target to make the prediction right"],
                               "Your expectation; keep the measured evidence", "The exercise is for learning; it does not edit research evidence or acceptance criteria.")])


def lesson_project_goal(p, L, learn):
    goals = L.get("goals") or _goals(p)
    rows_ = [_goal_row(p, g, learn) for g in goals]
    cs = []
    if goals and rows_[0]["measured"]:
        g, r = goals[0], rows_[0]
        title, sl = r["label"], g["slice"]
        ds = sl.split("/", 1)[0]
        pool = sorted((s for s in p.slices() if s != sl), key=lambda s: s.split("/", 1)[0] != ds)
        if pool:
            ans = f"No: it is measured only on {sl}"
            cs.append(_check(f"A candidate improves on {pool[0]}. Does that alone move “{title}”?",
                             [ans, "Yes: any slice of the dataset counts", "Yes, if the gain is large enough"], ans,
                             f"A goal is one target on one frozen slice: {sl}" + (f", n = {_n(r['n'])}." if r.get("n") else ".")))
    return dict(say="Each goal keeps its own metric, slice and target. Unmeasured goals remain requirements, not results." if goals else "No goal has been registered.",
                fig=dict(kind="goals", rows=rows_), checks=cs + (_goal_checks(p, goals[0], learn) if goals else []))


def lesson_project_data(p, L, learn):
    dss = [dict(name=k, title=learn._first(v.get("title") or k, 80), n=v.get("size")) for k, v in p.datasets().items()]
    rs = _slice_rows(p, learn)
    checks = []
    small = min(rs, key=lambda r: r["n"]) if rs else None
    if small and sum(r["n"] == small["n"] for r in rs) == 1:
        checks.append(_check("Which slice is the smallest?", _others(small["id"], [r["id"] for r in rs if r is not small]), small["id"],
                             f"{small['id']}: {_n(small['n'])} examples."))
    if rs:
        selected = rs[0]
        checks.append(_check(f"A candidate is measured on {selected['id']}, but its baseline uses different example IDs. Can their score difference isolate the change?",
                             ["No; measure both on the same frozen IDs and compatible setup", "Yes; equal example counts are enough", "Yes; choose the baseline with the closest score"],
                             "No; measure both on the same frozen IDs and compatible setup", "Equal counts do not imply the same cases, difficulty or evaluation setup."))
    return dict(say="These are the project's recorded measurement scopes. A denominator appears only when the owning dataset is registered; otherwise the row gives a slice count.",
                fig=dict(kind="slices", scale_max=max((r["n"] for r in rs), default=1), rows=rs[:10], datasets=dss), checks=checks)


def lesson_project_champion(p, L, learn):
    champ = L["champ"]
    if not champ:
        return dict(say="No champion yet.", fig=dict(kind="list", rows=[]), checks=[])
    chain, m, seen = [], champ, set()
    while m and m not in seen and len(chain) < 5:
        seen.add(m)
        v = L["models"].get(m) or {}
        sc = learn._score(p, m, L["full"]) if L["full"] else None
        chain.append(dict(label=learn._title(p, m), status=v.get("status") or "", detail=learn._first(v.get("change"), 160),
                          score=learn.sv(p, L["full"], sc) if sc is not None else ""))
        policy = v.get("serving_policy") or {}
        settings = []
        if policy.get("adapter_mode"):
            settings.append(dict(label="Adapter", value=str(policy["adapter_mode"]).replace("_", " ").capitalize()))
        if isinstance(policy.get("max_new_tokens"), int) and policy["max_new_tokens"] > 0:
            settings.append(dict(label="Output budget", value=f"{policy['max_new_tokens']:,} tokens"))
        if isinstance(policy.get("do_sample"), bool):
            settings.append(dict(label="Decoding", value="Sampling" if policy["do_sample"] else "Greedy"))
        if settings:
            chain[-1]["settings"] = settings
        m = v.get("parent")
    parent = L["models"].get(champ, {}).get("parent")
    comparator = learn._title(p, parent) if parent else "the registered baseline"
    cs = [_check(f"To test whether {chain[0]['label']} improved on {comparator}, which comparison is valid?",
                 ["Both systems on the same frozen examples with a compatible harness", "Their highest scores from any available runs", "The new system's targeted score against the old full-set score"],
                 "Both systems on the same frozen examples with a compatible harness", "Model identity alone does not make runs comparable; scope and evaluation setup must match.")]
    if chain[0].get("settings"):
        cs = [_check("If this combined serving setup improves performance, how would you test which setting caused the gain?",
                     ["Vary one setting while holding the others, evaluation cases and harness fixed",
                      "Attribute the whole gain to the larger output budget", "Attribute the whole gain to the adapter setting"],
                     "Vary one setting while holding the others, evaluation cases and harness fixed",
                     "The combined result does not isolate a component's contribution. A controlled comparison is needed before attributing the gain.")]
    return dict(say=f"{chain[0]['label']} is the registered champion. Its recorded changes and lineage explain what was tried; matched measurements establish what improved.",
                fig=dict(kind="list", rows=chain, lineage=True), checks=cs)


def lesson_project_hills(p, L, learn):
    hs = _hill_rows(p, learn)
    h = next((h for h in hs if h["status"] == "open" and h["target"]), hs[0] if hs else None)
    checks = []
    if h:
        example = "the illustrated error" if h.get("examples") else "an observed target failure"
        checks.append(_check(f"For “{h['label']}”, a candidate fixes {example}, but its control result violates the declared tolerance. Is that enough to promote?",
                             ["No; inspect the regression and satisfy the required gates", "Yes; one target failure is fixed", "Yes; a targeted improvement overrides the control"],
                             "No; inspect the regression and satisfy the required gates", "An individual fix does not establish an acceptable system change. The target, control and remaining gate measurements determine that."))
    return dict(say="Each hill links a concrete failure to a testable change. Its examples illustrate the failure; the measured target and controls determine whether a fix generalizes safely.",
                fig=dict(kind="share", rows=hs), checks=checks)


BUILD = {"goal": lesson_goal, "champion": lesson_champion, "candidate": lesson_candidate, "slice": lesson_slice,
         "paired-delta": lesson_paired, "interval": lesson_interval, "gate": lesson_gate, "rung": lesson_rung,
         "ladder": lesson_ladder, "hill": lesson_hill, "brief": lesson_brief, "project-goal": lesson_project_goal,
         "project-data": lesson_project_data, "project-champion": lesson_project_champion, "project-hills": lesson_project_hills}


LIVE = {"goal", "champion", "candidate", "hill", "brief", "project-goal", "project-champion", "project-hills"}


def lessons(p: Project) -> list[dict]:
    from . import learn
    p._gates = getattr(p, "_gates", None) or {}
    with p.snapshot():
        L = _ledger(p)
        out = []
        for i in IDS:
            try:
                x = BUILD[i](p, L, learn)
            except (KeyError, TypeError, ValueError, ZeroDivisionError, SystemExit):
                x = None
            if not x:
                continue
            x["checks"] = [c for c in x["checks"] if c]
            # a figure drawn from recorded results: a Brief primer leaves it out so it cannot give away the card
            x["live"] = i in LIVE or (i in ("paired-delta", "interval", "gate") and not x["fig"].get("example"))
            out.append(dict(id=i, t=TITLE[i], group="basics" if i in BASICS else "project", **x))
        return out


@features.get("/api/course")
def _get(p, path, q):
    from .learn import aliases
    v = str(q.get("viewer") or "anon")[:60]
    mem = memory(rows(p, v, aliases(v)))
    return 200, dict(lessons=lessons(p), memory=mem, due=due(mem), intervals=list(INTERVALS))


@features.post("/api/course")
def _post(p, path, body):
    return record(p, body) if isinstance(body, dict) else (400, dict(error="send an object"))
