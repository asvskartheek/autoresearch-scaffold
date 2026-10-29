"""Teaching methods for the Brief: each card can be learned in more than one way, and each person gets the ways that
work for them. The cards and their truth come from learn.py; this module adds a method per card, grades answers on the
server (the truth never reaches the page before an answer) and keeps every attempt.

Methods (which apply depends on the card's figure):
  predict    the original: pick or slide a guess, say how sure (learn.py /api/predictions)
  sketch     draw the result: drag the paired delta and its interval, or each bar's height
  spot       spot the error: the real figure with one number made inconsistent; tap the wrong one
  prototype  a live model of the measurement: drag n and watch the interval narrow; set the n where it clears zero
  code       write the one line: the paired delta from fixed, broken and n
  explain    explain it back in a sentence; the ideas it names are checked off

Attempts go to .research/teach.jsonl: {t, viewer, card, method, hit, err, ms, skip}. A person's profile per method
(tries, hits, skips) picks the next card's method: methods they finish and get right more often, a new method now and
then, never the same one three cards running, and a harder one once a method is easy for them (5 of the last 5 right).

  POST /api/teach {viewer, card, method, answer, ms}  -> {attempt, card (with reveal)}
  POST /api/teach {viewer, card, method, skip: true}  -> {method: the next one for that card}
  GET  /api/teach?viewer=                              -> {profile}
"""
from __future__ import annotations

import ast
import hashlib
import math
import re
import time

from . import features
from .core import Project, _append, _jsonl

METHODS = ("predict", "sketch", "spot", "prototype", "code", "explain")
HARDER = {m: i for i, m in enumerate(METHODS)}  # predict is the easiest to finish, explain the hardest
# before a person has tried a method: the hands-on, visual ones first (people asked for less text), explain last
PRIOR = dict(predict=0.30, sketch=0.42, spot=0.40, prototype=0.42, code=0.36, explain=0.22)
TEXT = {"explain"}  # the one method that is writing, not doing
LABEL = dict(predict="Predict", sketch="Sketch", spot="Spot the error", prototype="Prototype", code="Code", explain="Explain back")


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
# No method's task may hold the truth its card is graded on. A real figure (counts, delta, interval, bars) is the
# answer to every card it belongs to, so spot, prototype and code work on an example built at the card's own n and
# labelled as one; the card's real result shows in the reveal. Bars cards keep only sketch (the bars are the answer).
def methods_for(c: dict) -> list[str]:
    v = c.get("viz") or {}
    out = ["predict"]
    if c.get("truth") is None:
        return out  # a run that has not landed: only a prediction can wait for it
    if v.get("kind") == "ci":
        out.append("sketch")
        if c.get("gate"):
            return out  # the question is pass or fail: predict it, or sketch the result against the bar
        if v.get("unit") == "pts" and v.get("n"):
            # spot and code teach delta = (fixed - broken) / n: only where that is how this card's delta was made (one
            # 0/1 run per example). Pooled or fractional scores make it the mean difference, which the counts miss.
            out += ["spot", "prototype", "code"] if counts_give_delta(v) else ["prototype"]
        out.append("explain")  # which way it went and whether it is noise: two claims a sentence can get right
    elif v.get("kind") == "bars" and _sketch_rows(v) and _bars_max(v):
        out.append("sketch")
    return out


def counts_give_delta(v: dict) -> bool:
    try:
        return abs(100 * (v["wins"] - v["losses"]) / v["n"] - v["delta"]) <= 0.005
    except (KeyError, TypeError, ZeroDivisionError):
        return False


# ---------------------------------------------------------------- the task each method shows (never the answer)
def _ci_axis(c: dict) -> dict:
    """The sketch's axis in the card's own unit, never from its answer: a number card's own range, else the room its
    comparator leaves (learn._room). `view` is the half-width it opens at (± 10 pts on a 0/1 slice, the whole range on
    a continuous one); the page zooms between the range and a twentieth of it."""
    v = c.get("viz") or {}
    unit = v.get("unit") or c.get("unit") or "pts"
    a, b = (c["min"], c["max"]) if c.get("type") == "number" and c.get("min") is not None else tuple(c.get("axis") or ((-100, 100) if unit == "pts" else (-10, 10)))
    full = max(abs(a), abs(b))
    return dict(min=a, max=b, unit=unit, view=min(full, 10) if unit == "pts" else full)


def _example(c: dict) -> dict:
    """A paired result on a 0/1 slice at the card's own n, independent of the card's result (stable per card): fixed
    and broken counts, the delta they give and its 90% interval (normal approximation of the paired bootstrap). Its
    interval clears zero at an n well away from the card's, so the prototype has something to find."""
    n = int((c.get("viz") or {}).get("n") or 100)
    for k in range(40):
        h = _h(c["id"], "example", k)
        w, l = max(1, round((0.02 + (h % 997) / 997 * 0.10) * n)), round((0.01 + (h // 997 % 991) / 991 * 0.07) * n)
        if (h >> 20) & 1:
            w, l = l, w
        if w == l:
            continue
        d = (w - l) / n
        half = 1.645 * math.sqrt(max((w + l) / n - d * d, 1e-9) / n) * 100
        need = n * (half / abs(100 * d)) ** 2
        if 4 <= need and abs(math.log(need / n)) > math.log(1.6) and need < 60 * n:
            break
    else:
        w, l = max(2, round(0.09 * n)), round(0.03 * n)
        d = (w - l) / n
        half = 1.645 * math.sqrt(max((w + l) / n - d * d, 1e-9) / n) * 100
    return dict(kind="ci", unit="pts", better=1, example=True, n=n, wins=w, losses=l,
                delta=round(100 * d, 2), lo=round(100 * d - half, 2), hi=round(100 * d + half, 2))


def _spot_ci(c: dict) -> tuple[dict, str]:
    """The example figure with one part made inconsistent: the counts swapped, the delta's sign flipped, or the
    interval moved off the delta. Which part is the card's own (stable) choice."""
    v = _example(c)
    wrong = ["counts", "delta", "interval"][_h(c["id"], "spot") % 3]
    if wrong == "counts":
        v["wins"], v["losses"] = v["losses"], v["wins"]
    elif wrong == "delta":
        v["delta"] = -v["delta"]
    else:
        w = (v["hi"] - v["lo"]) or 1
        shift = (w + abs(v["delta"]) + 1) * (1 if v["delta"] <= 0 else -1)
        v["lo"], v["hi"] = round(v["lo"] + shift, 2), round(v["hi"] + shift, 2)
    return dict(viz=v, parts=["counts", "delta", "interval"]), wrong


def _proto(c: dict) -> dict:
    v = _example(c)
    return dict(delta=v["delta"], lo=v["lo"], hi=v["hi"], n=v["n"], example=True)


def _n_needed(v: dict) -> float:
    """The n at which this effect's 90% interval just clears zero: the half-width shrinks as 1/sqrt(n)."""
    half = (v["hi"] - v["lo"]) / 2
    return v["n"] * (half / abs(v["delta"])) ** 2 if v["delta"] else float("inf")


def task(c: dict, method: str) -> dict:
    v = c.get("viz") or {}
    if method == "sketch":
        if v.get("kind") == "ci":
            return dict(kind="ci", **_ci_axis(c), bar=v.get("bar") if c.get("gate") else None)
        rows = [dict(label=r.get("label"), tag=r.get("tag"), n=r.get("n"), unit=r.get("unit")) for r in _sketch_rows(v)]
        return dict(kind="bars", rows=rows, max=_bars_max(v))
    if method == "spot":
        return _spot_ci(c)[0]
    if method == "prototype":
        return _proto(c)
    if method == "code":
        e = _example(c)
        return dict(vars=dict(fixed=e["wins"], broken=e["losses"], n=e["n"]), target="delta_pts", example=True)
    if method == "explain":
        return dict(ideas=_ideas(c))
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


IDEAS = ("which way", "real or noise")
_NOT = r"(?:not|no|n't|never|without|hardly)\W+(?:\w+\W+){0,2}?"
_GOOD = (r"improv\w*|better|gain\w*|helped|helps|\bwin\b|a win|beat\w*|more (?:right|correct)|increas\w*|up by|went up"
         r"|fixe?d? more than (?:it )?br\w*")
_BAD = (r"worse|regress\w*|drop\w*|hurt\w*|declin\w*|degrad\w*|decreas\w*|went down|down by|fewer (?:right|correct)|\blost\b"
        r"|\bloses\b|a loss|br\w* more than (?:it )?fix\w*")
_HIGH, _LOW = r"\bhigher\b|\bfaster\b", r"\blower\b|\bslower\b"
_NOT_NOISE = r"not (?:just |only )?(?:noise|chance|luck)"
_NOISE = (r"nois\w*|chance|luck\w*|random\w*|can'?t tell|cannot tell|unclear|uncertain|inconclusive|not (?:yet )?(?:shown|clear|sure|certain|real|reliabl\w*)"
          r"|not (?:statistically )?significant\w*|insignificant|cross\w* (?:over )?zero|includes? zero|straddl\w*|touch\w* zero|span\w* zero"
          r"|could be zero|might be zero|either way|too (?:small|few|close)|within (?:the )?(?:noise|interval)")
_REAL = (r"significant\w*|clears? zero|cleared zero|above zero|below zero|excludes? zero|\breal(?= (?:gain|drop|effect|improvement|regression|change|win|loss))"
         r"|clearly|definite\w*|confident\w*|reliabl\w*|shown|proven|for sure|certain\w*")


def _ideas(c: dict) -> list[str]:
    """What a good explanation of a paired result says: which way it went, and whether the interval rules out noise."""
    return list(IDEAS) if (c.get("viz") or {}).get("kind") == "ci" else []


def _claims(text: str, better: int = 1) -> dict:
    """The claims a sentence makes: way (+1 better, -1 worse, 0 no change, None unsaid; 'not better' is -0.5, 'not
    worse' +0.5) and noise (True it may be noise, False it is real, None unsaid). Contradicting claims cancel out."""
    t = " " + re.sub(r"\s+", " ", text.lower().replace("’", "'")) + " "
    real = bool(re.search(_NOT_NOISE, t))
    t = re.sub(_NOT_NOISE, " ", t)
    noisy = bool(re.search(_NOISE, t))
    t = re.sub(_NOISE, " ", t)
    real = real or bool(re.search(_REAL, t))
    t = re.sub(_REAL, " ", t)
    noise = None if noisy == real else noisy  # both said, or neither: no claim
    ways = set()
    for rx, w in ((_GOOD, 1), (_BAD, -1), (_HIGH, better), (_LOW, -better)):
        for m in re.finditer(rx, t):
            negated = re.search(_NOT + r"$", t[max(0, m.start() - 30):m.start()])
            ways.add(-w * 0.5 if negated else w)  # "not better" says it did not help; it does not say it hurt
    fx = re.search(r"fix\w*\D{0,12}?(\d+|none|nothing|no)\b", t)
    br = re.search(r"brok\w*\D{0,12}?(\d+|none|nothing|no)\b|(\d+|none|nothing|no) brok", t)
    if fx and br:  # "fixed 23 and broke 11": the counts say which way
        num = lambda m: next((int(g) if g.isdigit() else 0 for g in m.groups() if g), 0)
        f, b = num(fx), num(br)
        ways.add((f > b) - (f < b))
    if re.search(r"no (?:real )?change|unchanged|the same|flat|no difference|tie\b|even\b", t):
        ways.add(0)
    way = None if not ways or (any(w > 0 for w in ways) and any(w < 0 for w in ways)) else max(ways, key=abs)
    return dict(way=way, noise=noise)


def _grade_explain(c: dict, text: str) -> dict:
    """Right when the sentence says which way it went and whether it could be noise, and both match the result.
    Keywords alone do not count: "it improved, clearly significant" on a loss that crosses zero is two wrong claims."""
    v = c.get("viz") or {}
    b = v.get("better") or 1
    good = v["delta"] * b
    crosses = min(v["lo"], v["hi"]) <= 0 <= max(v["lo"], v["hi"])
    cl = _claims(text, b)
    w = cl["way"]
    way_ok = w is not None and ((good > 0 and w > 0) or (good < 0 and w < 0) or (good == 0 and w == 0)
                                or (w == -0.5 and good <= 0) or (w == 0.5 and good >= 0))
    noise_ok = cl["noise"] is not None and cl["noise"] == crosses
    named = [i for i, ok in zip(IDEAS, (way_ok, noise_ok)) if ok]
    return dict(hit=way_ok and noise_ok, err=None, show=dict(named=named, said=cl))


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
    """{hit, err, show}: show is what the reveal adds for this method (the right part, the needed n, the right line)."""
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
    if method == "spot":
        wrong = _spot_ci(c)[1]
        return dict(hit=str(ans) == wrong, err=None, show=dict(wrong=wrong))
    if method == "prototype":
        need, n = _n_needed(_example(c)), _f(ans)
        if n is None or not math.isfinite(need):
            return dict(hit=False, err=None, show=dict(need=None))
        err = abs(math.log(max(n, 1) / max(need, 1)))
        return dict(hit=err <= math.log(1.35), err=round(err, 3), show=dict(need=round(need)))
    if method == "code":
        e = _example(c)
        g = _grade_code(ans, e["wins"], e["losses"], e["n"])
        g["show"]["card"] = round(100 * (v["wins"] - v["losses"]) / v["n"], 2)  # the same line on the card's own counts
        return g
    if method == "explain":
        return _grade_explain(c, str(ans or "")[:1000])
    return dict(hit=None, err=None, show={})


def _grade_sketch_ci(c: dict, v: dict, ans) -> dict:
    """A sketched delta and interval, graded on the card's own question: a number card on the delta (inside its band)
    and the interval's side of zero; a gate on pass or fail against its bar; "better, worse or can't tell" on where
    the interval sits; "will it beat" on the delta's sign."""
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
        return dict(hit=verdict == c.get("truth"), err=err, show=dict(verdict=verdict))
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
    return dict(hit=hit, err=None if got is None else round(abs(got - want), 3),
                show=dict(line="100 * (fixed - broken) / n", value=round(want, 2), got=None if got is None else round(got, 4), ok=hit))


# ---------------------------------------------------------------- attempts and profiles
def _log(p: Project):
    return p.dir / "teach.jsonl"


def attempts(p: Project, viewer: str | None = None, aliases: set | None = None) -> list[dict]:
    who = {viewer} | (aliases or set()) if viewer else None
    return [r for r in _jsonl(_log(p)) if isinstance(r, dict) and (who is None or r.get("viewer") in who)]


def profile(rows: list[dict], preds: list[dict]) -> dict:
    """Per method: tries, hits, skips and the last five results; predictions count as the predict method."""
    out = {m: dict(n=0, hits=0, skips=0, last=[]) for m in METHODS}
    seq = [(r.get("t") or 0, r.get("method"), r.get("hit"), bool(r.get("skip"))) for r in rows if r.get("method") in out]
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
    recent = [m for _, m, _, skip in sorted(seq, key=lambda x: x[0]) if not skip][-2:]
    return dict(methods=out, recent=recent)


def score(prof: dict, m: str) -> float:
    s = prof["methods"][m]
    works = (s["hits"] + 1) / (s["n"] + 2) * (s["n"] + 1) / (s["n"] + s["skips"] + 1)  # right, and finished not skipped
    if s["n"] < 2:
        works += PRIOR[m]  # try what they have not tried
    if len(s["last"]) == 5 and all(s["last"]):
        works *= 0.6  # easy for them now: step up
    if prof["recent"].count(m) == 2:
        works *= 0.3  # never three in a row
    if m in TEXT:
        works *= 0.7  # people learn here by doing: at equal results a hands-on method comes first
    return works


def choose(prof: dict, c: dict, viewer: str, avoid: set | None = None, deck: dict | None = None) -> str:
    """The method for this card. `deck` counts methods already given to earlier cards in the same Brief, so one deck
    mixes methods instead of repeating the best one."""
    ms = [m for m in methods_for(c) if m not in (avoid or set())] or ["predict"]
    used = deck or {}
    return max(ms, key=lambda m: (round(score(prof, m) * 0.7 ** used.get(m, 0), 3), _h(viewer, c["id"], m) % 97))


def _person(p: Project, viewer: str, aliases: set | None = None) -> tuple[list[dict], dict]:
    """A person's attempts (under their id and their older names) and their profile, predictions included."""
    from .learn import aliases as names, predictions
    al = names(viewer) if aliases is None else aliases
    rows = attempts(p, viewer, al)
    return rows, profile(rows, [r for a in {viewer} | al for r in predictions(p, a)])


def attach(p: Project, cards_full: list[dict], public_cards: list[dict], viewer: str, aliases: set) -> dict:
    """Give each public card its method and task (the reveal waits for an answer), and return the profile."""
    rows, prof = _person(p, viewer, aliases)
    done = {r["card"]: r for r in rows if not r.get("skip") and r.get("card")}
    skipped: dict = {}
    for r in rows:
        if r.get("skip"):
            skipped.setdefault(r.get("card"), set()).add(r.get("method"))
    deck: dict = {}
    for full, pub in zip(cards_full, public_cards):
        a = done.get(full["id"])
        if a and not pub.get("pred"):  # learned another way: the card is answered, the reveal shows
            pub["pred"] = dict(method=a["method"], hit=a.get("hit"), t=a.get("t"), guess=None, conf=None)
            pub["reveal"] = dict(truth=full.get("truth"), why=full.get("why"), viz=full.get("viz"), show=a.get("show") or {})
        m = a["method"] if a else ("predict" if pub.get("pred") else choose(prof, full, viewer, skipped.get(full["id"]), deck))
        deck[m] = deck.get(m, 0) + 1
        pub["method"] = m
        pub["methods"] = methods_for(full)
        pub["others"] = 0 if a or pub.get("pred") else len(set(pub["methods"]) - skipped.get(full["id"], set()) - {m})
        if m != "predict" and not pub.get("pred"):
            pub["task"] = task(full, m)
    return prof


def answer(p: Project, body: dict) -> tuple[int, dict]:
    from .learn import card, public
    viewer = str(body.get("viewer") or "anon")[:60]
    c = card(p, str(body.get("card") or ""))
    m = body.get("method")
    if not c or m not in methods_for(c) or m == "predict" and not body.get("skip"):
        return 404, dict(error="unknown card or method")
    ms = max(0, min(int(_f(body.get("ms"), 0) or 0), 3_600_000))
    if body.get("skip"):
        rows, prof = _person(p, viewer)
        avoid = {r["method"] for r in rows if r.get("card") == c["id"] and r.get("skip")} | {m}
        left = [x for x in methods_for(c) if x not in avoid]
        if not left:  # nothing else fits this card: stay, and log no skip (it would count against this method)
            return 200, dict(method=m, task=task(c, m) if m != "predict" else None, others=0)
        _append(_log(p), dict(t=time.time(), viewer=viewer, card=c["id"], method=m, skip=True, ms=ms))
        nxt = choose(prof, c, viewer, avoid)
        return 200, dict(method=nxt, task=task(c, nxt) if nxt != "predict" else None, others=len(left) - 1)
    have = next((r for r in attempts(p, viewer) if r.get("card") == c["id"] and not r.get("skip")), None)
    g = grade(c, m, body.get("answer")) if not have else dict(hit=have.get("hit"), err=have.get("err"), show=have.get("show") or {})
    rec = have or dict(t=time.time(), viewer=viewer, card=c["id"], method=m, hit=g["hit"], err=g["err"], ms=ms, show=g["show"])
    if not have:
        _append(_log(p), rec)
    pub = public(c) | dict(method=rec["method"], pred=dict(method=rec["method"], hit=rec["hit"], t=rec["t"], guess=None, conf=None),
                           reveal=dict(truth=c.get("truth"), why=c.get("why"), viz=c.get("viz"), show=rec.get("show") or {}))
    return 200, dict(attempt=rec, card=pub)


@features.post("/api/teach")
def _post(p, path, body):
    return answer(p, body) if isinstance(body, dict) else (400, dict(error="send an object"))


@features.get("/api/teach")
def _get(p, path, q):
    v = str(q.get("viewer") or "anon")[:60]
    from .learn import predictions
    return 200, dict(profile=profile(attempts(p, v), predictions(p, v)), labels=LABEL)
