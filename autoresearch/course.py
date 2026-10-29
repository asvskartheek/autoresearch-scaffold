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
def _check(q, o, a, why=""):
    """A multiple-choice check; numbers read with thousands separators, repeats and negatives dropped."""
    fmt = lambda x: f"{x:,}" if isinstance(x, int) else str(x)
    o = list(dict.fromkeys(fmt(x) for x in o if not (isinstance(x, int) and x < 0)))
    return dict(q=q, o=o, a=fmt(a), why=why) if fmt(a) in o and len(o) >= 2 else None


def _n(x) -> str:
    return f"{int(round(x)):,}"


def _amt(u: str, x: float) -> str:
    """A signed amount: "+5.2 pts" on a 0/1 slice, "−1,071 ms" in a continuous unit."""
    sg = "+" if x > 0 else "−" if x < 0 else ""
    a = abs(x)
    num = f"{a:.2f}".rstrip("0").rstrip(".") if u == "pts" else (f"{a:,.0f}" if a >= 100 else f"{float(f'{a:.3g}'):g}")
    return f"{sg}{num} {u}".strip()


def _goal(p: Project) -> dict | None:
    """The first open goal counted in examples right (a 0/1 slice), else any such goal."""
    best = None
    for name, g in p.goals().items():
        try:
            st = p.goal_status(name)
        except SystemExit:
            continue
        if st.get("kpi", "score") != "score" or st.get("value") is None or not st.get("n") or st.get("scale") == "continuous":
            continue
        if best is None or (st.get("status") == "open" and best.get("status") != "open"):
            best = st
    return best


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
    return dict(champ=champ, models=models, full=full, promo=promo, checks=checks, goal=_goal(p))


def lesson_goal(p, L, learn):
    g = L["goal"]
    if g:
        N, have, need = int(g["n"]), round(g["value"] * g["n"]), math.ceil(g["target"] * g["n"] - 1e-9)
        fig = dict(kind="goal", N=N, have=have, need=need, slice=learn._short(g["slice"]), title=g.get("title") or g["name"])
    else:
        N, have, need = 100, 80, 90
        fig = dict(kind="goal", N=N, have=have, need=need, slice="full", title="Example goal", example=True)
    left = max(0, need - have)
    return dict(say="A goal is one target on one frozen slice. Work counts when it moves that number.", fig=fig,
                checks=[_check(f"The champion gets {_n(have)} of {_n(N)} right. The goal needs {_n(need)}. How many more?",
                               [left, need, have, left + 10], left, f"{_n(need)} − {_n(have)} = {_n(left)}." if left else "The champion already meets the target."),
                        _check("Is a goal a task?", ["No: tasks serve it", "Yes: one long task"], "No: tasks serve it",
                               "A task is one job with an end. A goal is what the jobs are for.")])


def _scores(p, L, learn, k=7):
    """Models with a run on the primary full slice, as counts right (0/1) or values."""
    sl = L["full"]
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
    fig = dict(kind="bars", slice=learn._short(sl) if sl else "", n=None if cont else n,
               rows=[dict(label=r["label"], v=r["v"], status=r["status"], hl=r["champ"]) for r in rs])
    champ = next((r for r in rs if r["champ"]), None)
    cs = [_check("A new idea is measured against what?", ["The champion, on the same examples", "Its own earlier run", "Nothing"],
                 "The champion, on the same examples", "Same examples, so every difference is the change itself.")]
    if champ and len(rs) >= 3:
        cs.insert(0, _check("Which one is the champion?", [champ["label"]] + [r["label"] for r in rs if not r["champ"]][:2],
                            champ["label"], "The champion is the model every candidate must beat."))
    return dict(say="The champion is the best model so far. Every candidate is compared with it.", fig=fig, checks=cs)


def lesson_candidate(p, L, learn):
    rows_ = []
    for m, v in sorted(L["models"].items(), key=lambda kv: -float(kv[1].get("created") or 0)):
        if v.get("status") in ("candidate", "rejected", "champion"):
            rows_.append(dict(label=learn._title(p, m), status=v["status"], detail=learn._first(v.get("change") or v.get("reason"), 140),
                              parent=learn._title(p, v["parent"]) if v.get("parent") and v.get("parent") != m else ""))
        if len(rows_) >= 6:
            break
    rej = sum(v.get("status") == "rejected" for v in L["models"].values())
    cs = [_check("A candidate passes every rung. What happens?", ["It is promoted to champion", "It stays a candidate", "It is rejected"],
                 "It is promoted to champion", "Passing the whole ladder is what earns a promotion.")]
    if rej:
        cs.append(_check("How many candidates were rejected here so far?", [rej, rej + 2, max(0, rej - 2), rej * 2], rej,
                         "Rejected candidates stay in the ledger with their reason."))
    return dict(say="A candidate is one change to the champion. It climbs the ladder and is promoted, or is rejected with its reason kept.",
                fig=dict(kind="list", rows=rows_), checks=cs)


def _slice_rows(p, learn, only=None):
    out = []
    for name, s in p.slices().items():
        ds = name.split("/", 1)[0]
        if only and ds != only:
            continue
        out.append(dict(name=learn._short(name), ds=ds, n=s.get("n") or len(s.get("ids") or []), kind=s.get("kind") or ""))
    return sorted(out, key=lambda r: (r["ds"], -r["n"]))


def lesson_slice(p, L, learn):
    ds = (p.config.get("primary_dataset") or "")
    rs = _slice_rows(p, learn, ds or None)
    N = max((r["n"] for r in rs), default=0)
    cs = []
    pick = next((r for r in rs if r["n"] != N), None)
    if pick:
        cs.append(_check(f"How many examples are in {pick['name']}?", [pick["n"], N, pick["n"] * 2, max(1, pick["n"] // 2)], pick["n"],
                         f"{pick['name']} holds {_n(pick['n'])} of the {_n(N)}."))
    cs.append(_check("A slice is frozen. Someone needs it changed. What now?", ["Make a new slice with a new name", "Edit the slice"],
                     "Make a new slice with a new name", "Old runs stay comparable only if their slice never changes."))
    return dict(say="A slice is a frozen list of example ids. Two runs on one slice ran on the same examples, so they pair.",
                fig=dict(kind="slices", N=N, rows=rs[:8]), checks=cs)


def lesson_paired(p, L, learn):
    v = (L["promo"] or {}).get("viz") or {}
    from .teach import counts_give_delta
    if v.get("unit") == "pts" and v.get("n") and counts_give_delta(v):
        w, l, n, ex = v["wins"], v["losses"], v["n"], False
    else:
        w, l, n, ex = 12, 5, 200, True
    right = f"{100 * (w - l) / n:+.2f} pts"
    return dict(say="Pair each example: fixed if the new model gets it and the champion did not, broken the other way. Δ = (fixed − broken) / n.",
                fig=dict(kind="paired", fixed=w, broken=l, n=n, example=ex),
                checks=[_check(f"{w} fixed, {l} broken, n = {n:,}. Δ?", [right, f"{100 * w / n:+.2f} pts", f"{100 * (w + l) / n:+.2f} pts"], right,
                               "Broken examples cancel fixed ones: (fixed − broken) / n."),
                        _check("Two models score the same on one slice. Can their paired Δ be non-zero?", ["No", "Yes"], "No",
                               "Same score means fixed = broken, so the Δ is 0.")])


def _ci_of(p, learn, c):
    """A check or card as an interval figure in display units, ends in order (a "minus" metric flips them)."""
    v = learn._ci_viz(c, p, c.get("slice")) if c.get("slice") else c
    return dict(delta=v["delta"], lo=min(v["lo"], v["hi"]), hi=max(v["lo"], v["hi"]), n=v["n"], unit=v.get("unit") or "pts")


def lesson_interval(p, L, learn):
    noisy = next((c for c in L["checks"] if c.get("noisy") and c.get("lo") is not None and abs(c.get("delta") or 0) > 1e-9), None)
    src = _ci_of(p, learn, noisy) if noisy else None
    fig = dict(kind="interval", **(src or dict(delta=1.6, lo=-0.5, hi=3.7, n=185, unit="pts")), example=src is None)
    crosses = fig["lo"] <= 0 <= fig["hi"]
    ans = "Not yet: it crosses zero" if crosses else "Yes: it clears zero"
    return dict(say="An interval crossing zero does not establish a direction. This projection holds the effect fixed and narrows uncertainty as 1/√n; it is not a new measurement. If the effect is zero, more examples alone cannot make it clear zero.",
                fig=fig,
                checks=[_check(f"Δ {_amt(fig['unit'], fig['delta'])}, 90% interval {_amt(fig['unit'], fig['lo'])} to {_amt(fig['unit'], fig['hi'])}. Is the change shown?",
                               ["Yes: it clears zero", "Not yet: it crosses zero"], ans,
                               "Shown means the whole interval sits on one side of zero."),
                        _check("What narrows an interval most?", ["More examples", "Re-running the same greedy eval"], "More examples",
                               "The width shrinks as 1/√n. A greedy rerun gives the same answers.")])


def lesson_gate(p, L, learn):
    c = next((c for c in L["checks"] if c.get("rule") in ("better", "not_worse")), None)
    if c:
        v = _ci_of(p, learn, c)
        k = 100 if v["unit"] == "pts" else (-1 if learn._neg(p, c["slice"]) else 1)
        fig = dict(kind="gate", rule=c["rule"], bar=k * (c.get("threshold") or 0), delta=v["delta"], unit=v["unit"],
                   slice=learn._short(c["slice"]), model=learn._title(p, c["model"]), rung=c["rung"], better=-1 if k < 0 else 1)
        ok = c["state"] == "pass"
        q = f"{fig['model']} on {fig['slice']}: it {learn._rule_text(p, c)}. Δ {learn.sd(p, c['slice'], c['delta'])}. Pass or fail?"
    else:
        fig = dict(kind="gate", rule="not_worse", bar=-1.0, delta=-0.4, unit="pts", slice="random100", model="Example", rung="random100", example=True)
        ok, q = True, "It may lose at most 1 pt. Δ −0.4 pts. Pass or fail?"
    return dict(say="A gate check sets a bar for Δ. “Better” needs Δ above zero; “not worse” allows a small loss.", fig=fig,
                checks=[_check(q, ["Pass", "Fail"], "Pass" if ok else "Fail", "Pass when Δ is on the good side of the bar.")])


def _ladder(p):
    return [dict(rung=r.get("rung"), checks=[dict(slice=c.get("slice"), rule=c.get("rule"),
                                                  bar=-(c.get("tolerance") or 0) if c.get("rule") == "not_worse" else (c.get("margin") or 0))
                                             for c in r.get("checks", [])]) for r in p.config.get("ladder", []) if r.get("rung")]


def lesson_rung(p, L, learn):
    lad = _ladder(p)
    r = max(lad, key=lambda r: len(r["checks"]), default=None) or dict(rung="dev", checks=[dict(slice="@hill.target", rule="better", bar=0),
                                                                                          dict(slice="@hill.control", rule="not_worse", bar=-0.02)])
    k = len(r["checks"])
    cs = [_check(f"A rung has {k if k > 1 else 3} checks and one fails. Does the rung pass?", ["No", "Yes"], "No",
                 "Every check on a rung must pass.")]
    return dict(say="A rung is a set of checks run together. It passes only when every check passes.",
                fig=dict(kind="rung", rung=r["rung"], checks=r["checks"]), checks=cs)


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
    return dict(say="Rungs go from small, cheap slices to the full one. A candidate climbs one rung at a time and stops at the first fail.",
                fig=dict(kind="ladder", rungs=lad, model=learn._title(p, cand) if cand else "", status=status), checks=cs)


def _hill_rows(p, learn):
    out = []
    for name, h in p.hills().items():
        sh = h.get("share") if isinstance(h.get("share"), dict) else {}
        out.append(dict(id=name, label=learn._first(h.get("title") or name, 60).split(" [")[0], status=h.get("status") or "",
                        count=sh.get("count"), of=sh.get("of"), of_what=learn._first(sh.get("of_what") or "", 60),
                        target=learn._short(h.get("target") or ""), control=learn._short(h.get("control") or ""),
                        detail=learn._first(h.get("symptom") or h.get("problem"), 140)))
    return sorted(out, key=lambda r: -(r["count"] or 0))


def lesson_hill(p, L, learn):
    hs = _hill_rows(p, learn)
    h = next((r for r in hs if r["target"] and r["control"]), None)
    cs = []
    if h:
        cs.append(_check(f"“{h['label']}”: which slice measures it?", [h["target"], h["control"], "full"], h["target"],
                         "A hill's own slice holds the failure. Its control slice checks nothing else broke."))
    cs.append(_check("A hill is climbed when…", ["a candidate fixes that failure without breaking others", "its slice is edited", "a task ends"],
                     "a candidate fixes that failure without breaking others", "Climbed means passed on the target and not worse on the control."))
    return dict(say="A hill is one kind of failure with its own slice to measure it.", fig=dict(kind="share", rows=hs[:5]), checks=cs)


def lesson_brief(p, L, learn):
    g = L["goal"]
    fig = dict(kind="guess", N=int(g["n"]), truth=round(g["value"] * g["n"]), slice=learn._short(g["slice"]),
               tol=max(2, round(int(g["n"]) * 0.01))) if g else dict(kind="guess", N=100, truth=81, slice="full", tol=2, example=True)
    return dict(say="The Brief turns what changed into cards. You guess first, then see: the guess makes it stick.", fig=fig,
                checks=[_check("When does a Brief card show its answer?", ["After you answer it", "Before you answer", "Never"],
                               "After you answer it", "Guessing first is the point.")])


def lesson_project_goal(p, L, learn):
    rows_ = []
    for name, g in p.goals().items():
        try:
            st = p.goal_status(name)
        except SystemExit:
            continue
        if st.get("value") is None:
            continue
        if st.get("kpi", "score") == "score" and st.get("n") and st.get("scale") != "continuous":
            N = int(st["n"])
            rows_.append(dict(label=st.get("title") or name, status=st.get("status"), have=round(st["value"] * N), need=math.ceil(st["target"] * N - 1e-9),
                              N=N, slice=learn._short(st["slice"]), met=st.get("met")))
        else:
            rows_.append(dict(label=st.get("title") or name, status=st.get("status"), value=st["value"], target=st["target"], kpi=st.get("kpi"),
                              slice=learn._short(st["slice"]), met=st.get("met"), lower=not st.get("higher_is_better", True)))
    g = L["goal"]
    cs = []
    if g:
        sls = [learn._short(s) for s in p.slices() if s != g["slice"]][:2]
        cs.append(_check(f"“{g.get('title') or g['name']}”: on which slice?", [learn._short(g["slice"])] + sls, learn._short(g["slice"]),
                         f"It is measured on all {int(g['n']):,} examples of {learn._short(g['slice'])}."))
        left = math.ceil(g["target"] * g["n"] - 1e-9) - round(g["value"] * g["n"])
        if left > 0:
            cs.append(_check("How many more right answers does it need?", [left, left * 2, max(1, left // 2), left + 25], left, ""))
    say = f"{len(rows_)} goals here." if len(rows_) != 1 else "One goal here."
    return dict(say=say, fig=dict(kind="goals", rows=rows_), checks=cs)


def lesson_project_data(p, L, learn):
    dss = [dict(name=k, title=learn._first(v.get("title") or k, 80), n=v.get("size") or 0) for k, v in p.datasets().items()]
    rs = _slice_rows(p, learn)
    N = max((d["n"] for d in dss), default=max((r["n"] for r in rs), default=0))
    cs = []
    if rs:
        small = min(rs, key=lambda r: r["n"])
        cs.append(_check("Which slice is the smallest?", [small["name"]] + [r["name"] for r in rs if r is not small][:2], small["name"],
                         f"{small['name']}: {_n(small['n'])} examples."))
    if dss:
        d = dss[0]
        cs.append(_check(f"How many examples are in {d['name']}?", [d["n"], d["n"] // 2, d["n"] * 2, 1000], d["n"], ""))
    return dict(say=" ".join(f"{d['title']}: {_n(d['n'])} examples." for d in dss[:2]) or "No dataset yet.",
                fig=dict(kind="slices", N=N, rows=rs[:10], datasets=dss), checks=cs)


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
        m = v.get("parent")
    cs = []
    if len(chain) >= 2:
        cs.append(_check("Which model did the champion grow from?", [chain[1]["label"]] + [r["label"] for r in _scores(p, L, learn)[1] if r["label"] not in (chain[0]["label"], chain[1]["label"])][:2],
                         chain[1]["label"], "Each model names its parent; the change is what differs."))
    sc = learn._score(p, champ, L["full"]) if L["full"] else None
    if sc is not None and not learn._cont(p, L["full"]):
        n = (p.slices().get(L["full"]) or {}).get("n")
        have = round(sc * n)
        cs.append(_check(f"How many of {n:,} does it get right on {learn._short(L['full'])}?", [have, have - 40, min(n, have + 40), have - 90], have, ""))
    return dict(say=f"{chain[0]['label']}. {chain[0]['detail']}".strip(), fig=dict(kind="list", rows=chain, lineage=True), checks=cs)


def lesson_project_hills(p, L, learn):
    hs = _hill_rows(p, learn)
    cs = []
    big = [h for h in hs if h["count"] is not None]
    if len(big) >= 2:
        cs.append(_check(f"Which hill covers the most {big[0]['of_what'] or 'errors'}?", [h["label"] for h in big[:3]], big[0]["label"], ""))
    op = sum(h["status"] == "open" for h in hs)
    cs.append(_check("How many hills are open?", [op, op + 1, op + 2, op - 1], op, ""))
    return dict(say=f"{len(hs)} hills: {op} open, {sum(h['status'] == 'climbed' for h in hs)} climbed.", fig=dict(kind="share", rows=hs), checks=cs)


BUILD = {"goal": lesson_goal, "champion": lesson_champion, "candidate": lesson_candidate, "slice": lesson_slice,
         "paired-delta": lesson_paired, "interval": lesson_interval, "gate": lesson_gate, "rung": lesson_rung,
         "ladder": lesson_ladder, "hill": lesson_hill, "brief": lesson_brief, "project-goal": lesson_project_goal,
         "project-data": lesson_project_data, "project-champion": lesson_project_champion, "project-hills": lesson_project_hills}


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
