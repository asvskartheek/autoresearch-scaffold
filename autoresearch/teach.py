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
LABEL = dict(predict="Predict", sketch="Sketch", spot="Spot the error", prototype="Prototype", code="Code", explain="Explain back")


def _h(*xs) -> int:
    return int(hashlib.sha1("|".join(map(str, xs)).encode()).hexdigest()[:8], 16)


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- which methods fit a card
def methods_for(c: dict) -> list[str]:
    v = c.get("viz") or {}
    out = ["predict"]
    if c.get("truth") is None:
        return out  # a run that has not landed: only a prediction can wait for it
    if v.get("kind") == "ci":
        out += ["sketch", "spot"]
        if v.get("unit") == "pts" and v.get("n"):
            out += ["prototype", "code"]
    elif v.get("kind") == "bars" and any(r.get("v") is not None for r in v.get("rows") or []):
        out += ["sketch", "spot"]
    if c.get("why") or v:
        out.append("explain")
    return out


# ---------------------------------------------------------------- the task each method shows (never the answer)
def _ci_axis(c: dict) -> dict:
    return dict(min=c.get("min", -10), max=c.get("max", 10), unit=(c.get("viz") or {}).get("unit") or c.get("unit") or "pts")


def _spot_ci(c: dict) -> dict:
    """The CI figure with one part made inconsistent: the counts swapped, the delta's sign flipped, or the interval
    moved off the delta. Which part is the card's own (stable) choice."""
    v = dict(c["viz"])
    opts = ["counts", "delta", "interval"]
    if v.get("wins") == v.get("losses"):
        opts.remove("counts")
    if abs(v.get("delta") or 0) < 1e-9:
        opts.remove("delta")
    wrong = opts[_h(c["id"], "spot") % len(opts)]
    if wrong == "counts":
        v["wins"], v["losses"] = v["losses"], v["wins"]
    elif wrong == "delta":
        v["delta"] = -v["delta"]
    else:
        w = (v["hi"] - v["lo"]) or 1
        shift = (w + abs(v["delta"]) + 1) * (1 if v["delta"] <= 0 else -1)
        v["lo"], v["hi"] = v["lo"] + shift, v["hi"] + shift
    return dict(viz=v, parts=["counts", "delta", "interval"]), wrong


def _spot_bars(c: dict) -> dict:
    v = c["viz"]
    rows = [dict(r) for r in v["rows"] if r.get("v") is not None]
    i = _h(c["id"], "spot") % len(rows)
    r = rows[i]
    r["shown"] = r["v"] * (0.6 if r["v"] > 0.5 else 1.6) if not r.get("unit") else r["v"] * 1.5  # the label lies, the bar does not
    return dict(viz=dict(v, rows=rows), parts=[str(k) for k in range(len(rows))]), str(i)


def _proto(c: dict) -> dict:
    v = c["viz"]
    return dict(delta=v["delta"], lo=v["lo"], hi=v["hi"], n=v["n"], wins=v["wins"], losses=v["losses"])


def _n_needed(v: dict) -> float:
    """The n at which this effect's 90% interval just clears zero: the half-width shrinks as 1/sqrt(n)."""
    half = (v["hi"] - v["lo"]) / 2
    return v["n"] * (half / abs(v["delta"])) ** 2 if v["delta"] else float("inf")


def task(c: dict, method: str) -> dict:
    v = c.get("viz") or {}
    if method == "sketch":
        if v.get("kind") == "ci":
            return dict(kind="ci", **_ci_axis(c))
        rows = [dict(label=r.get("label"), tag=r.get("tag"), n=r.get("n"), unit=r.get("unit")) for r in v.get("rows") or [] if r.get("v") is not None]
        cont = any(r.get("unit") for r in rows)
        top = max(abs(r["v"]) for r in v["rows"] if r.get("v") is not None) if cont else 1
        return dict(kind="bars", rows=rows, max=_nice_up(top * 1.6) if cont else 1)
    if method == "spot":
        return (_spot_ci(c) if v.get("kind") == "ci" else _spot_bars(c))[0]
    if method == "prototype":
        return _proto(c)
    if method == "code":
        return dict(vars=dict(fixed=v["wins"], broken=v["losses"], n=v["n"]), target="delta_pts")
    if method == "explain":
        return dict(ideas=[i[0] for i in _ideas(c)])
    return {}


def _nice_up(x: float) -> float:
    if x <= 0:
        return 1.0
    m = 10 ** math.floor(math.log10(x))
    return next(k * m for k in (1, 2, 2.5, 5, 10) if k * m >= x)


def _ideas(c: dict) -> list[tuple[str, str]]:
    """What a good explanation names, as (idea, words that count) pairs."""
    v = c.get("viz") or {}
    if v.get("kind") == "ci":
        return [("what it fixed", r"fix|win|right|gain|more correct|improv"), ("what it broke", r"brok|los|wrong|regress|worse"),
                ("whether it is noise", r"nois|interval|ci\b|zero|confiden|chance|luck|significan")]
    if v.get("kind") == "bars":
        return [("the score", r"\d|score|right|correct|count"), ("compared with what", r"than|vs|versus|compar|champion|control|other"),
                ("what it means", r"so|means|because|hill|weak|fix|need")]
    return [("the answer", r"\w{3,}"), ("why", r"because|since|so\b|means|due")]


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
        return float(eval(compile(tree, "<code>", "eval"), {"__builtins__": {}}, dict(names)))
    except (ZeroDivisionError, OverflowError, TypeError, ValueError):
        return None


def grade(c: dict, method: str, ans) -> dict:
    """{hit, err, show}: show is what the reveal adds for this method (the right part, the needed n, the right line)."""
    v = c.get("viz") or {}
    if method == "sketch" and v.get("kind") == "ci":
        d = _f((ans or {}).get("delta")) if isinstance(ans, dict) else None
        if d is None:
            return dict(hit=False, err=None, show={})
        sides = (_f(ans.get("lo"), d) <= 0 <= _f(ans.get("hi"), d)) == (v["lo"] <= 0 <= v["hi"])
        err = abs(d - v["delta"])
        return dict(hit=err <= max(c.get("tol") or 1, (v["hi"] - v["lo"]) / 2) and sides, err=round(err, 3), show=dict(noise_right=sides))
    if method == "sketch":
        rows = [r for r in v.get("rows") or [] if r.get("v") is not None]
        got = ans.get("rows") if isinstance(ans, dict) else None
        if not isinstance(got, list) or len(got) != len(rows):
            return dict(hit=False, err=None, show={})
        scale = max(abs(r["v"]) for r in rows) if any(r.get("unit") for r in rows) else 1
        errs = [abs((_f(g, 0) - r["v"]) / (scale or 1)) for g, r in zip(got, rows)]
        err = sum(errs) / len(errs)
        return dict(hit=err <= 0.1, err=round(err, 3), show={})
    if method == "spot":
        wrong = (_spot_ci(c) if v.get("kind") == "ci" else _spot_bars(c))[1]
        return dict(hit=str(ans) == wrong, err=None, show=dict(wrong=wrong))
    if method == "prototype":
        need, n = _n_needed(v), _f(ans)
        if n is None or not math.isfinite(need):
            return dict(hit=False, err=None, show=dict(need=None))
        err = abs(math.log(max(n, 1) / max(need, 1)))
        return dict(hit=err <= math.log(1.35), err=round(err, 3), show=dict(need=round(need)))
    if method == "code":
        got = safe_eval(ans, dict(fixed=v["wins"], broken=v["losses"], n=v["n"]))
        want = 100 * (v["wins"] - v["losses"]) / v["n"]
        hit = got is not None and abs(got - want) <= max(0.05, abs(want) * 0.01)
        return dict(hit=hit, err=None if got is None else round(abs(got - want), 3), show=dict(line="100 * (fixed - broken) / n", value=round(want, 2), got=got))
    if method == "explain":
        text = str(ans or "")[:1000].lower()
        got = [name for name, rx in _ideas(c) if re.search(rx, text)]
        return dict(hit=len(got) >= 2, err=None, show=dict(named=got))
    return dict(hit=None, err=None, show={})


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
    return works


def choose(prof: dict, c: dict, viewer: str, avoid: set | None = None, deck: dict | None = None) -> str:
    """The method for this card. `deck` counts methods already given to earlier cards in the same Brief, so one deck
    mixes methods instead of repeating the best one."""
    ms = [m for m in methods_for(c) if m not in (avoid or set())] or ["predict"]
    used = deck or {}
    return max(ms, key=lambda m: (round(score(prof, m) * 0.7 ** used.get(m, 0), 3), _h(viewer, c["id"], m) % 97))


def attach(p: Project, cards_full: list[dict], public_cards: list[dict], viewer: str, aliases: set) -> dict:
    """Give each public card its method and task (the reveal waits for an answer), and return the profile."""
    rows = attempts(p, viewer, aliases)
    from .learn import predictions
    preds = [r for a in {viewer} | aliases for r in predictions(p, a)]
    prof = profile(rows, preds)
    from . import memory
    prof = memory.blend(p, prof, viewer, aliases)  # what worked for this person in other projects counts too
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
        _append(_log(p), dict(t=time.time(), viewer=viewer, card=c["id"], method=m, skip=True, ms=ms))
        rows = attempts(p, viewer)
        prof = profile(rows, [])
        avoid = {r["method"] for r in rows if r.get("card") == c["id"] and r.get("skip")}
        nxt = choose(prof, c, viewer, avoid)
        return 200, dict(method=nxt, task=task(c, nxt) if nxt != "predict" else None)
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
