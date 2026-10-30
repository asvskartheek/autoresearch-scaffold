"""Teaching methods for the Brief. Every card is about its own result, in two steps.

Before the reveal (the truth stays on the server) the person answers the card one way:
  predict    pick or slide a guess and say how sure (learn.py /api/predictions)
  sketch     draw the result on the card's own axis: the delta and its interval (against the bar on a gate), or each bar
  explain    say it in one sentence; after the reveal the person checks their own sentence against it (which way it
             went, and whether it could be noise). No keyword grading: the person is the judge, the reveal the key.

After the reveal, one consolidation step works on the card's real numbers (its verdict is about the step only):
  code       write the line that gives this card's delta from its real counts (only where it is exactly (fixed-broken)/n)
  ndrag      drag n: when would this result stop being noise (or start clearing zero)?
  spot       spot the error in a variant of this card's own figure

Attempts go to .research/teach.jsonl: {t, viewer, card, method, phase, hit, err, ms, show, skip}; phase is "answer",
"step" or "self" (an explain self-check). A person's record per method (tries, right, skipped, last five) picks the
next method: what they finish and get right, a switch after two misses running, a step up once one is easy (5 of 5).
Each pick carries the reason when it is the evidence, not the default, that chose it, so a deck visibly adapts.

  POST /api/teach {viewer, card, method, answer, ms}            -> {attempt, card (with reveal and its step)}
  POST /api/teach {viewer, card, method, skip: true}            -> {method, task, others}
  POST /api/teach {viewer, card, method, step: true, answer}    -> {attempt, step}
  POST /api/teach {viewer, card, method, step: true, skip: true} -> {step}
  POST /api/teach {viewer, card, method: "explain", self: [way, noise]} -> {attempt}
  GET  /api/teach?viewer=                                       -> {profile}
"""
from __future__ import annotations

import ast
import hashlib
import math
import time

from . import features
from .core import Project, _append, _jsonl

BEFORE = ("predict", "sketch", "explain")
AFTER = ("code", "ndrag", "spot")
METHODS = BEFORE + AFTER
HARDER = dict(predict=0, sketch=1, explain=2, spot=0, ndrag=1, code=2)  # within each step, easiest first
PRIOR = dict(predict=0.52, sketch=0.56, explain=0.40, code=0.50, ndrag=0.55, spot=0.52)  # hands-on first, writing last
LABEL = dict(predict="Predict", sketch="Sketch", explain="Say it", code="Write the line", ndrag="Drag n", spot="Spot the error")
IDEAS = ("which way", "real or noise")
NDRAG_WHY = "This is a projection, not a new measurement. Holding the effect fixed, interval width scales as 1/√n: four times as many independent examples halves the width. The threshold is approximate; a new sample can also change the effect."


def selfcheck(c: dict) -> list[str]:
    v = c.get("viz") or {}
    d, lo, hi = v.get("delta", 0), v.get("lo", 0), v.get("hi", 0)
    direction = "no measured change" if d == 0 else "an improvement" if d * (v.get("better") or 1) > 0 else "a degradation"
    uncertainty = "the interval crosses zero, so the direction is uncertain" if lo <= 0 <= hi else "the interval clears zero"
    return [f"My explanation agrees with {direction} in the result.", f"My explanation says {uncertainty}."]


def _h(*xs) -> int:
    return int(hashlib.sha1("|".join(map(str, xs)).encode()).hexdigest()[:8], 16)


def _f(x, d=None):
    """A finite float, else d: "nan", "inf" and 1e309 never reach a grade or the log (the log must stay valid JSON)."""
    try:
        x = float(x)
    except (TypeError, ValueError, OverflowError):
        return d
    return x if math.isfinite(x) else d


# ---------------------------------------------------------------- which methods fit a card
def methods_for(c: dict) -> list[str]:
    """The ways to answer a card before its reveal."""
    v = c.get("viz") or {}
    out = ["predict"]
    if c.get("truth") is None:
        return out  # a run that has not landed: only a prediction can wait for it
    if v.get("kind") == "ci":
        out.append("sketch")
        if not c.get("gate"):
            out.append("explain")
    elif v.get("kind") == "bars" and _sketch_rows(v) and _bars_max(v):
        out.append("sketch")
    return out


def counts_give_delta(v: dict) -> bool:
    """True when this delta is exactly (fixed - broken) / n: one 0/1 run per example on each side."""
    try:
        return v.get("unit", "pts") == "pts" and abs(100 * (v["wins"] - v["losses"]) / v["n"] - v["delta"]) <= 0.005
    except (KeyError, TypeError, ZeroDivisionError):
        return False


def _n_needed(v: dict) -> float:
    """The n at which this effect's 90% interval just touches zero: the half-width shrinks as 1/sqrt(n)."""
    half = (v["hi"] - v["lo"]) / 2
    return v["n"] * (half / abs(v["delta"])) ** 2 if v.get("delta") else float("inf")


def steps_for(c: dict) -> list[str]:
    """The consolidation steps a revealed card offers, all on its own numbers."""
    v = c.get("viz") or {}
    if c.get("truth") is None or v.get("kind") != "ci" or not v.get("n"):
        return []
    out = []
    if counts_give_delta(v) and v["wins"] != v["losses"]:
        out.append("code")
    need = _n_needed(v) if v.get("hi") != v.get("lo") else float("inf")
    if math.isfinite(need) and 4 <= need <= 1000 * v["n"] and abs(math.log(need / v["n"])) > math.log(1.2):
        out.append("ndrag")
    if len(_spot_parts(c)) >= 2:
        out.append("spot")
    return out


# ---------------------------------------------------------------- the task each method shows (never the answer)
def _ci_axis(c: dict) -> dict:
    """The sketch's axis in the card's own unit, never from its answer: a number card's own range, else the room its
    comparator leaves (learn._room). `view` is the half-width it opens at (± 10 pts on a 0/1 slice, the whole range on
    a continuous one); the page zooms between the range and a thousandth of it, so a small bar can be seen."""
    v = c.get("viz") or {}
    unit = v.get("unit") or c.get("unit") or "pts"
    a, b = (c["min"], c["max"]) if c.get("type") == "number" and c.get("min") is not None else tuple(c.get("axis") or ((-100, 100) if unit == "pts" else (-10, 10)))
    full = max(abs(a), abs(b))
    return dict(min=a, max=b, unit=unit, view=min(full, 10) if unit == "pts" else full, better=v.get("better") or 1)


def task(c: dict, method: str) -> dict:
    v = c.get("viz") or {}
    if method == "sketch":
        if v.get("kind") == "ci":
            return dict(kind="ci", **_ci_axis(c), bar=v.get("bar") if c.get("gate") else None)
        rows = [dict(label=r.get("label"), tag=r.get("tag"), n=r.get("n"), unit=r.get("unit")) for r in _sketch_rows(v)]
        return dict(kind="bars", rows=rows, max=_bars_max(v))
    if method == "explain":
        return dict(ideas=list(IDEAS))
    return {}


def _spot_parts(c: dict) -> list[str]:
    """Which parts of the real figure can be made wrong and still be caught: the counts (only where they give the
    delta), the delta (not on a number card, whose answer shows the delta; and only when flipping it leaves its
    interval), the interval (always)."""
    v = c.get("viz") or {}
    out = []
    if counts_give_delta(v) and v["wins"] != v["losses"]:
        out.append("counts")
    if c.get("type") != "number" and v.get("delta") and not (v["lo"] <= -v["delta"] <= v["hi"]):
        out.append("delta")
    out.append("interval")
    return out


def _spot(c: dict) -> tuple[dict, str, str]:
    """This card's figure with one part made inconsistent, which part, and why it cannot be right."""
    v = dict(c["viz"])
    parts = _spot_parts(c)
    wrong = parts[_h(c["id"], "spot") % len(parts)]
    u = v.get("unit") or "pts"
    amt = lambda x: f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.2f} {u}"
    if wrong == "counts":
        v["wins"], v["losses"] = v["losses"], v["wins"]
        why = f"{v['wins']} fixed and {v['losses']} broken give {amt(100 * (v['wins'] - v['losses']) / v['n'])}, not {amt(v['delta'])}."
    elif wrong == "delta":
        v["delta"] = -v["delta"]
        why = f"Δ {amt(v['delta'])} sits outside its own interval [{amt(v['lo'])}, {amt(v['hi'])}]."
    else:
        w = (v["hi"] - v["lo"]) or 1
        shift = (w + abs(v["delta"]) + 1) * (1 if v["delta"] <= 0 else -1)
        v["lo"], v["hi"] = round(v["lo"] + shift, 2), round(v["hi"] + shift, 2)
        why = f"The interval [{amt(v['lo'])}, {amt(v['hi'])}] does not hold its own Δ {amt(v['delta'])}."
    return v, wrong, why


def step_task(c: dict, m: str) -> dict:
    """A consolidation step's task. It is shown after the reveal, so it may use the card's real numbers."""
    v = c.get("viz") or {}
    if m == "code":
        return dict(vars=dict(fixed=v["wins"], broken=v["losses"], n=v["n"]))
    if m == "ndrag":
        crosses = min(v["lo"], v["hi"]) <= 0 <= max(v["lo"], v["hi"])
        return dict(delta=v["delta"], lo=v["lo"], hi=v["hi"], n=v["n"], unit=v.get("unit") or "pts", better=v.get("better") or 1,
                    dir="up" if crosses else "down")
    if m == "spot":
        fig = _spot(c)[0]
        return dict(viz=fig, parts=_spot_parts(c))
    return {}


def _sketch_rows(v: dict) -> list[dict]:
    """The bars a sketch asks for: every scored row but the champion's reference (it is not the question)."""
    return [r for r in v.get("rows") or [] if r.get("v") is not None and r.get("hl") != 3]


def _bars_max(v: dict) -> float | None:
    """The sketch's scale without its answer: a share (0 to 1) on 0/1 slices; on a continuous slice twice the
    champion's reference value, and no sketch at all without one."""
    if not any(r.get("unit") for r in _sketch_rows(v)):
        return 1
    return _nice_up(abs(v["ref"]) * 2) if v.get("ref") else None


def _nice_up(x: float) -> float:
    if x <= 0:
        return 1.0
    m = 10 ** math.floor(math.log10(x))
    return next(k * m for k in (1, 2, 2.5, 5, 10) if k * m >= x)


# ---------------------------------------------------------------- grading (server side)
_OK = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Constant, ast.Name, ast.Load)


def safe_eval(expr: str, names: dict) -> float | None:
    """An arithmetic expression over the given names (+ - * / and parentheses); anything else is refused."""
    try:
        tree = ast.parse(str(expr).strip().rstrip(";")[:200], mode="eval")
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        if not isinstance(n, _OK) or isinstance(n, ast.Name) and n.id not in names or isinstance(n, ast.Constant) and not isinstance(n.value, (int, float)):
            return None
    try:
        x = float(eval(compile(tree, "<code>", "eval"), {"__builtins__": {}}, dict(names)))
    except (ZeroDivisionError, OverflowError, TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def grade(c: dict, method: str, ans) -> dict:
    """An answer before the reveal: {hit, err, show}. Explain has no grade yet: the person checks it after."""
    v = c.get("viz") or {}
    if method == "sketch" and v.get("kind") == "ci":
        return _grade_sketch_ci(c, v, ans)
    if method == "sketch":
        rows = _sketch_rows(v)
        got = ans.get("rows") if isinstance(ans, dict) else None
        if not isinstance(got, list) or len(got) != len(rows) or any(_f(g) is None for g in got):
            return dict(hit=False, err=None, show={})
        got = [_f(g) for g in got]
        scale = max(abs(r["v"]) for r in rows) if any(r.get("unit") for r in rows) else 1
        err = sum(abs((g - r["v"]) / (scale or 1)) for g, r in zip(got, rows)) / len(rows)
        if c.get("type") == "choice":  # which is highest: the sketch's tallest bar, alone at the top
            top = max(got)
            hit = got.count(top) == 1 and rows[got.index(top)].get("label") == c.get("truth")
        else:  # how many does the champion get right: its own bar, within the card's band
            i = next((k for k, r in enumerate(rows) if r.get("hl") == 2), 0)
            n = rows[i].get("n")
            hit = abs((got[i] * n if n and c.get("int") else got[i] * (100 if c.get("unit") == "%" else 1)) - c["truth"]) <= (c.get("tol") or 0) + 1e-9
        return dict(hit=hit, err=round(err, 3), show={})
    if method == "explain":
        return dict(hit=None, err=None, show=dict(selfcheck=selfcheck(c)))
    return dict(hit=None, err=None, show={})


def grade_step(c: dict, m: str, ans) -> dict:
    v = c.get("viz") or {}
    if m == "code":
        return _grade_code(ans, v["wins"], v["losses"], v["n"])
    if m == "ndrag":
        need, n = _n_needed(v), _f(ans)
        if n is None or not math.isfinite(need):
            return dict(hit=False, err=None, show=dict(need=None))
        err = abs(math.log(max(n, 1) / max(need, 1)))
        return dict(hit=err <= math.log(1.35), err=round(err, 3), show=dict(need=round(need), got=round(n), why=NDRAG_WHY))
    if m == "spot":
        _, wrong, why = _spot(c)
        return dict(hit=str(ans) == wrong, err=None, show=dict(wrong=wrong, why=why, got=str(ans)[:20]))
    return dict(hit=None, err=None, show={})


def _grade_sketch_ci(c: dict, v: dict, ans) -> dict:
    """A sketched delta and interval, graded on the card's own question, always with the interval's side of zero:
    a number card on the delta (inside its band); a gate on pass or fail against its bar; "better, worse or can't
    tell" on where the interval sits; "will it beat" on the delta's sign."""
    d = _f((ans or {}).get("delta")) if isinstance(ans, dict) else None
    if d is None:
        return dict(hit=False, err=None, show={})
    lo, hi = sorted((_f(ans.get("lo"), d), _f(ans.get("hi"), d)))
    lo, hi = min(lo, d), max(hi, d)
    err = round(abs(d - v["delta"]), 3)
    noisy = (lo <= 0 <= hi) == (v["lo"] <= 0 <= v["hi"])
    if c.get("gate"):
        k = 100 if v.get("unit") == "pts" else (v.get("better") or 1)
        raw, g = d / k, c["gate"]
        ok = raw > g["thr"] if g.get("rule") == "better" else raw >= g["thr"]
        verdict = "Pass" if ok else "Fail"
        return dict(hit=verdict == c.get("truth") and noisy, err=err, show=dict(verdict=verdict, noise_right=noisy))
    if c.get("type") == "choice" and set(c.get("opts") or []) == {"Better", "Worse", "Can't tell yet"}:
        b = v.get("better") or 1
        cls = "Better" if (lo > 0 if b > 0 else hi < 0) else "Worse" if (hi < 0 if b > 0 else lo > 0) else "Can't tell yet"
        return dict(hit=cls == c.get("truth"), err=err, show=dict(verdict=cls))
    if c.get("type") == "choice":  # will it beat: the sign of the sketched delta, in the ledger's direction
        yes = "Yes" if d / (100 if v.get("unit") == "pts" else (v.get("better") or 1)) > 0 else "No"
        return dict(hit=yes == c.get("truth"), err=err, show=dict(verdict=yes))
    return dict(hit=err <= max(c.get("tol") or 1, (v["hi"] - v["lo"]) / 2) and noisy, err=err, show=dict(noise_right=noisy))


def _code_ok(got, want) -> bool:
    return got is not None and abs(got - want) <= max(0.05, abs(want) * 0.01)


def _grade_code(ans, fixed: int, broken: int, n: int) -> dict:
    """The line is right when it gives the paired delta on these numbers and on two other sets of counts, so a typed
    constant (the value itself) is not a line that computes it."""
    sets = [(fixed, broken, n), (fixed + 7, broken + 3, n + 50), (broken + 2, fixed + 5, 2 * n + 9)]
    gots = [safe_eval(ans, dict(fixed=f, broken=b, n=k)) for f, b, k in sets]
    want = 100 * (fixed - broken) / n
    hit = all(_code_ok(g, 100 * (f - b) / k) for g, (f, b, k) in zip(gots, sets))
    got = gots[0]
    const = got is not None and _code_ok(got, want) and not hit
    return dict(hit=hit, err=None if got is None else round(abs(got - want), 3),
                show=dict(line="100 * (fixed - broken) / n", value=round(want, 2), got=None if got is None else round(got, 4), ok=hit, const=const))


# ---------------------------------------------------------------- attempts and profiles
def _log(p: Project):
    return p.dir / "teach.jsonl"


def attempts(p: Project, viewer: str | None = None, aliases: set | None = None) -> list[dict]:
    who = {viewer} | (aliases or set()) if viewer else None
    return [r for r in _jsonl(_log(p)) if isinstance(r, dict) and (who is None or r.get("viewer") in who)]


def _phase(r: dict) -> str:
    return r.get("phase") or ("step" if r.get("method") in AFTER and r.get("step") else "answer")


def _settled(rows: list[dict]) -> list[dict]:
    """Answers with an explain's self-check folded in (its hit is the person's own check, once given)."""
    selfs = {(r.get("viewer"), r.get("card")): r.get("hit") for r in rows if r.get("phase") == "self"}
    out = []
    for r in rows:
        if r.get("phase") == "self":
            continue
        if r.get("method") == "explain" and r.get("hit") is None and (r.get("viewer"), r.get("card")) in selfs:
            r = dict(r, hit=selfs[(r.get("viewer"), r.get("card"))])
        out.append(r)
    return out


def profile(rows: list[dict], preds: list[dict]) -> dict:
    """Per method: tries, right, skips and the last five results; predictions count as the predict method."""
    out = {m: dict(n=0, hits=0, skips=0, last=[]) for m in METHODS}
    seq = [(r.get("t") or 0, r.get("method"), r.get("hit"), bool(r.get("skip"))) for r in _settled(rows) if r.get("method") in out]
    seq += [(r.get("t") or 0, "predict", r.get("hit"), False) for r in preds]
    for _, m, hit, skip in sorted(seq, key=lambda x: x[0]):
        s = out[m]
        if skip:
            s["skips"] += 1
            continue
        s["n"] += 1
        if hit:
            s["hits"] += 1
        if hit is not None:
            s["last"] = (s["last"] + [bool(hit)])[-5:]
    order = [m for _, m, _, skip in sorted(seq, key=lambda x: x[0]) if not skip]
    return dict(methods=out, recent=order[-2:])


def _easy(prof: dict) -> list[str]:
    return [m for m, s in prof["methods"].items() if len(s["last"]) == 5 and all(s["last"])]


def score(prof: dict, m: str) -> tuple[float, str | None]:
    """How well a method works for this person, and the reason when the evidence (not the default) set it.
    The prior is worth two answers, so a person's own results take over after a couple of cards."""
    s = prof["methods"][m]
    rate = (s["hits"] + 2 * PRIOR[m]) / (s["n"] + 2)  # right, with the prior as two pretend answers
    finish = (s["n"] + 1) / (s["n"] + 2 * s["skips"] + 1)  # finished, not skipped (a skip weighs double)
    x, why = rate * finish, None
    if s["skips"] >= 2 and s["skips"] > s["n"]:
        why = f"you skipped {LABEL[m]} {s['skips']} times"
    if s["last"][-2:] == [False, False]:
        x *= 0.4  # two misses running: try another way
        why = f"{LABEL[m]} missed twice"
    if len(s["last"]) == 5 and all(s["last"]):
        x *= 0.6  # easy for them now: step up
        why = f"{LABEL[m]} is easy for you now"
    elif any(HARDER[m] > HARDER[e] and (m in BEFORE) == (e in BEFORE) for e in _easy(prof)):
        x *= 1.25
    if prof["recent"].count(m) == 2:
        x *= 0.5  # never three in a row
    return x, why


def choose(prof: dict, ms: list[str], viewer: str, cid: str, avoid: set | None = None, deck: dict | None = None) -> tuple[str, str | None]:
    """The method for this card, and why when a person's record (not the default) decided it. `deck` counts the
    methods already given in this Brief, so a deck mixes them."""
    ms = [m for m in ms if m not in (avoid or set())] or ms[:1]
    used = deck or {}
    sc = {m: score(prof, m) for m in ms}
    rank = lambda f: (lambda m: (round(f(m) * 0.75 ** used.get(m, 0), 4), _h(viewer, cid, m) % 97))
    best = max(ms, key=rank(lambda m: sc[m][0]))
    base = max(ms, key=rank(lambda m: PRIOR[m]))  # what the default alone would give
    if best == base:
        return best, None
    s = prof["methods"][best]
    return best, sc[base][1] or (f"{LABEL[best]}: {s['hits']} of {s['n']} right" if s["n"] else None)


def _person(p: Project, viewer: str, aliases: set | None = None) -> tuple[list[dict], dict]:
    """A person's attempts (under their id and their older names) and their profile, predictions included."""
    from .learn import aliases as names, predictions
    al = names(viewer) if aliases is None else aliases
    rows = attempts(p, viewer, al)
    return rows, profile(rows, [r for a in {viewer} | al for r in predictions(p, a)])


def _step_pub(full: dict, rows: list[dict], prof: dict, viewer: str, deck: dict) -> dict | None:
    """The consolidation step a revealed card shows: the one done (with its result), else the one chosen now."""
    ms = steps_for(full)
    if not ms:
        return None
    done = next((r for r in rows if r.get("card") == full["id"] and _phase(r) == "step" and not r.get("skip")), None)
    if done:
        show = dict(done.get("show") or {})
        if done["method"] == "ndrag":
            show.setdefault("why", NDRAG_WHY)
        return dict(method=done["method"], done=True, hit=done.get("hit"), show=show, task=step_task(full, done["method"]) if done["method"] in ms else {})
    avoid = {r.get("method") for r in rows if r.get("card") == full["id"] and _phase(r) == "step" and r.get("skip")}
    if not set(ms) - avoid:
        return None  # every step was passed over: the card is done
    m, why = choose(prof, ms, viewer, full["id"], avoid, deck)
    deck[m] = deck.get(m, 0) + 1
    return dict(method=m, task=step_task(full, m), why=why, others=len(set(ms) - avoid - {m}))


def reveal(full: dict, show: dict | None = None) -> dict:
    return dict(truth=full.get("truth"), why=full.get("why"), viz=full.get("viz"), show=show or {})


def attach(p: Project, cards_full: list[dict], public_cards: list[dict], viewer: str, aliases: set) -> dict:
    """Give each public card its method and task (the reveal waits for an answer), its step once revealed, and
    return the profile."""
    rows, prof = _person(p, viewer, aliases)
    from . import memory
    prof = memory.blend(p, prof, viewer, aliases)  # what worked for this person in other projects counts too
    rows_s = _settled(rows)
    done = {r["card"]: r for r in rows_s if not r.get("skip") and r.get("card") and _phase(r) == "answer"}
    selfed = {r.get("card") for r in rows if r.get("phase") == "self"}
    skipped: dict = {}
    for r in rows:
        if r.get("skip") and _phase(r) == "answer":
            skipped.setdefault(r.get("card"), set()).add(r.get("method"))
    deck, sdeck = {}, {}
    for full, pub in zip(cards_full, public_cards):
        a = done.get(full["id"])
        if a and not pub.get("pred"):  # answered another way: the card is answered, the reveal shows
            pub["pred"] = dict(method=a["method"], hit=a.get("hit"), t=a.get("t"), guess=None, conf=None)
            pub["reveal"] = reveal(full, a.get("show"))
            if a["method"] == "explain" and full["id"] not in selfed:
                pub["selfcheck"] = selfcheck(full)
        ms = methods_for(full)
        if a or pub.get("pred"):
            m, why = (a["method"] if a else "predict"), None
        else:
            m, why = choose(prof, ms, viewer, full["id"], skipped.get(full["id"]), deck)
        deck[m] = deck.get(m, 0) + 1
        pub["method"], pub["methods"] = m, ms
        if why:
            pub["adapt"] = why
        pub["others"] = 0 if a or pub.get("pred") else len(set(ms) - skipped.get(full["id"], set()) - {m})
        if m != "predict" and not pub.get("pred"):
            pub["task"] = task(full, m)
        if pub.get("pred") and full.get("truth") is not None:
            st = _step_pub(full, rows, prof, viewer, sdeck)
            if st:
                pub["step"] = st
    return prof


def step_for(p: Project, c: dict, viewer: str) -> dict | None:
    """The step a card shows right after its reveal (for the answer responses)."""
    rows, prof = _person(p, viewer)
    return _step_pub(c, rows, prof, viewer, {}) if c.get("truth") is not None else None


def _answered(p: Project, viewer: str, cid: str) -> bool:
    from .learn import aliases, predictions
    al = aliases(viewer)
    if any(r.get("card") == cid and not r.get("skip") and _phase(r) == "answer" for r in attempts(p, viewer, al)):
        return True
    return any(r.get("card") == cid for v in {viewer} | al for r in predictions(p, v))


def _step(p: Project, c: dict, viewer: str, m: str, body: dict, ms: int) -> tuple[int, dict]:
    if m not in steps_for(c):
        return 404, dict(error="unknown step")
    if not _answered(p, viewer, c["id"]):
        return 409, dict(error="answer the card first")
    rows = attempts(p, viewer)
    if body.get("skip"):
        _append(_log(p), dict(t=time.time(), viewer=viewer, card=c["id"], method=m, phase="step", skip=True, ms=ms))
        return 200, dict(step=step_for(p, c, viewer))
    have = next((r for r in rows if r.get("card") == c["id"] and _phase(r) == "step" and not r.get("skip")), None)
    if have:
        return 200, dict(attempt=have, step=dict(method=have["method"], done=True, hit=have.get("hit"), show=have.get("show") or {}))
    g = grade_step(c, m, body.get("answer"))
    rec = dict(t=time.time(), viewer=viewer, card=c["id"], method=m, phase="step", hit=g["hit"], err=g["err"], ms=ms, show=g["show"])
    _append(_log(p), rec)
    return 200, dict(attempt=rec, step=dict(method=m, done=True, hit=rec["hit"], show=rec["show"], task=step_task(c, m)))


def answer(p: Project, body: dict) -> tuple[int, dict]:
    from .learn import card, public
    viewer = str(body.get("viewer") or "anon")[:60]
    c = card(p, str(body.get("card") or ""))
    m = body.get("method")
    if not c:
        return 404, dict(error="unknown card")
    ms = max(0, min(int(_f(body.get("ms"), 0) or 0), 3_600_000))
    if body.get("step"):
        return _step(p, c, viewer, m, body, ms)
    if m not in methods_for(c) or m == "predict" and not body.get("skip"):
        return 404, dict(error="unknown card or method")
    if "self" in body:  # an explain's self-check against the reveal: [said which way, said real or noise]
        s = body.get("self")
        first = next((r for r in attempts(p, viewer) if r.get("card") == c["id"] and _phase(r) == "answer" and not r.get("skip")), None)
        if m != "explain" or not first or first.get("method") != "explain" or not isinstance(s, list) or len(s) != len(IDEAS):
            return 400, dict(error="check an explained card with one yes or no per idea")
        if any(r.get("phase") == "self" and r.get("card") == c["id"] for r in attempts(p, viewer)):
            return 200, dict(attempt=first)
        rec = dict(t=time.time(), viewer=viewer, card=c["id"], method="explain", phase="self", hit=all(bool(x) for x in s),
                   show=dict(named=[i for i, x in zip(IDEAS, s) if x]))
        _append(_log(p), rec)
        return 200, dict(attempt=rec, step=step_for(p, c, viewer))
    if body.get("skip"):
        rows, prof = _person(p, viewer)
        avoid = {r["method"] for r in rows if r.get("card") == c["id"] and r.get("skip") and _phase(r) == "answer"} | {m}
        left = [x for x in methods_for(c) if x not in avoid]
        if not left:  # nothing else fits this card: stay, and log no skip (it would count against this method)
            return 200, dict(method=m, task=task(c, m) if m != "predict" else None, others=0)
        _append(_log(p), dict(t=time.time(), viewer=viewer, card=c["id"], method=m, phase="answer", skip=True, ms=ms))
        prof = _person(p, viewer)[1]
        nxt, why = choose(prof, methods_for(c), viewer, c["id"], avoid)
        return 200, dict(method=nxt, task=task(c, nxt) if nxt != "predict" else None, others=len(left) - 1, adapt=why)
    have = next((r for r in attempts(p, viewer) if r.get("card") == c["id"] and not r.get("skip") and _phase(r) == "answer"), None)
    g = grade(c, m, body.get("answer")) if not have else dict(hit=have.get("hit"), err=have.get("err"), show=have.get("show") or {})
    rec = have or dict(t=time.time(), viewer=viewer, card=c["id"], method=m, phase="answer", hit=g["hit"], err=g["err"], ms=ms, show=g["show"])
    if not have:
        _append(_log(p), rec)
    pub = public(c) | dict(method=rec["method"], pred=dict(method=rec["method"], hit=rec["hit"], t=rec["t"], guess=None, conf=None),
                           reveal=reveal(c, rec.get("show")))
    if rec["method"] == "explain" and rec.get("hit") is None:
        pub["selfcheck"] = selfcheck(c)
    else:
        st = step_for(p, c, viewer)
        if st:
            pub["step"] = st
    return 200, dict(attempt=rec, card=pub)


@features.post("/api/teach")
def _post(p, path, body):
    return answer(p, body) if isinstance(body, dict) else (400, dict(error="send an object"))


@features.get("/api/teach")
def _get(p, path, q):
    v = str(q.get("viewer") or "anon")[:60]
    from .learn import predictions
    return 200, dict(profile=profile(attempts(p, v), predictions(p, v)), labels=LABEL)
