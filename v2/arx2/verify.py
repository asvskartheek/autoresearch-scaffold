"""arx2 verify: a deep audit that every claim the project makes is backed by its own rows.

Each check is a small function over one context (the ledger now, its events, its rows) that returns findings:
`{"level": "error"|"warn"|"info", "check", "what", "entity": "<kind>:<key>", "fix", "link"}`. `link` is the
dashboard route that shows the entity. Errors block `promote` and `goal close --status achieved`.
"""
from __future__ import annotations

import re
import time

from . import stats
from .store import Project, fold, ids_hash
from .view import STALE_S, Views

FLAKY = re.compile(r"flak|inconsisten", re.I)
ANSWER_WORDS, FIGURE_WORDS = 80, 40
TEXT_PARTS = ("md", "text", "txt", "link")

CHECKS: dict = {}


def check(name):
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def finding(level, check_, what, entity, fix, link=None) -> dict:
    return {"level": level, "check": check_, "what": what, "entity": entity, "fix": fix, "link": link}


class Ctx:
    """The ledger now, its events, and a row cache shared by every past moment the checks look at."""

    def __init__(self, p: Project, v: Views | None = None):
        self.p = p
        self.v = v or Views(p)
        self.s = self.v.s
        self._events = None
        self._broken = None

    @property
    def events(self):
        if self._events is None:  # the fold keeps every event it applied, so no second read of the file
            self._events = self.s["log"]
        return self._events

    def at(self, t: float) -> Views:
        """Views as the ledger stood at time t (inclusive), reusing rows already read."""
        vt = Views.__new__(Views)
        vt.p, vt.s, vt._rows = self.p, fold(self.events, t), self.v._rows
        return vt

    def name(self, kind, key):
        src = {"hill": "hills", "candidate": "candidates", "set": "sets", "goal": "goals", "pattern": "patterns",
               "task": "tasks", "doc": "docs"}.get(kind)
        return (self.s.get(src, {}).get(key) or {}).get("name") or key if src else key

    def complete(self, rk) -> bool:
        r = self.s["runs"][rk]
        n = self.s["sets"].get(r["set"], {}).get("n") or 0
        return bool(n) and len(self.v.rows(rk)) >= n

    def broken(self) -> dict:
        """run -> why its rows cannot be trusted."""
        if self._broken is None:
            self._broken = {}
            for rk in self.s["runs"]:
                why = broken_why(self, rk)
                if why:
                    self._broken[rk] = why
        return self._broken

    def repeats(self, sets=None) -> dict:
        """(candidate, set) -> complete, unbroken runs, oldest first."""
        out: dict = {}
        bad = self.broken()
        for rk, r in sorted(self.s["runs"].items(), key=lambda kv: kv[1]["created"]):
            if (sets is None or r["set"] in sets) and rk not in bad and self.complete(rk):
                out.setdefault((r["candidate"], r["set"]), []).append(rk)
        return out


def broken_why(c: Ctx, rk: str) -> str | None:
    r = c.s["runs"][rk]
    rows = c.v.rows(rk)
    st = c.s["sets"].get(r["set"], {})
    n = st.get("n") or 0
    task = c.s["tasks"].get(r.get("task") or "", {})
    if not rows:
        if r.get("recorded") or r.get("aggregate_only"):
            return None  # an imported aggregate: no rows were ever claimed
        return f"no rows, but its task ended {task['status']}" if task.get("status") == "done" else None
    errs = sum(1 for x in rows if x.get("error"))
    if errs > len(rows) / 2:
        return f"{errs} of {len(rows)} rows are errors"
    if n and len(rows) >= n and st.get("role") != "symptom" and all(stats.score_of(x) == 0 for x in rows):
        return f"every one of its {len(rows)} scores is 0"
    if task.get("status") == "done" and len(rows) < n:
        return f"{len(rows)} of {n} rows, but its task ended done"
    return None


def _link_for(c: Ctx, kind: str, key: str) -> str | None:
    if kind in ("hill", "set", "goal", "task", "doc"):
        return f"{kind}/{key}"
    if kind == "candidate":
        return f"cand/{key}"
    if kind == "run":
        t = c.s["runs"].get(key, {}).get("task")
        return f"task/{t}" if t else None
    if kind == "pattern":
        hk = next((k for k, h in c.s["hills"].items() if h.get("pattern") == key), None)
        return f"hill/{hk}" if hk else "hills"
    return None


# ---- checks ------------------------------------------------------------------

def group(level, check_, kind, keys, one, many, fix) -> dict:
    """One finding for many entities that fail the same way; `one(key)` and `many(keys)` word it."""
    f = finding(level, check_, one(keys[0]) if len(keys) == 1 else many(keys), f"{kind}:{','.join(keys)}", fix)
    f["entities"] = [f"{kind}:{k}" for k in keys]
    return f


@check("hill_evidence")
def hill_evidence(c: Ctx):
    out, lacking = [], {}  # what is missing -> hills missing it
    for hk, h in c.s["hills"].items():
        if h.get("status") == "closed":
            continue
        e = c.v.hill_evidence(hk)
        waived = e.get("waived") or h.get("evidence_waived")
        if waived:
            out.append(finding("info", "hill_evidence", f"Hill {h['name']} has no evidence by choice: {waived}", f"hill:{hk}", "none needed"))
        elif not e["ok"]:
            lacking.setdefault(", ".join(e["missing"]), []).append(hk)
    for why, hks in lacking.items():
        out.append(group("error", "hill_evidence", "hill", hks,
                         lambda k, why=why: f"Hill {c.name('hill', k)} has no evidence: {why}",
                         lambda ks, why=why: f"{len(ks)} live hills have no evidence ({why}): " + ", ".join(c.name("hill", k) for k in ks),
                         "freeze the champion's failing ids as a symptom set and reopen the hill on it, or close the hill"))
    return out


@check("prevalence")
def prevalence(c: Ctx):
    bad = {"error": [], "warn": []}
    for pk, pat in c.s["patterns"].items():
        count = pat.get("count")
        if not count:
            continue
        hills = [h for h in c.s["hills"].values() if h.get("pattern") == pk]
        backed = {str(i) for i in pat.get("items") or []}
        for sk in [pat.get("set")] + [h.get("symptom_set") for h in hills]:
            backed |= {str(i) for i in c.s["sets"].get(sk or "", {}).get("ids") or []}
        if count > len(backed):
            live = not hills or any(h.get("status") != "closed" for h in hills)
            bad["error" if live else "warn"].append((pk, f"{pat['name']} {count} of {pat.get('of')}", len(backed)))
    out = []
    for level, items in bad.items():
        if not items:
            continue
        said = {pk: (txt, n) for pk, txt, n in items}
        word = "live" if level == "error" else "closed"
        out.append(group(level, "prevalence", "pattern", [pk for pk, _, _ in items],
                         lambda k: f"Pattern {said[k][0]} lists only {_n(said[k][1], 'item id')}",
                         lambda ks: f"{len(ks)} {word} patterns claim counts their ids do not back: "
                                    + ", ".join(said[k][0] + (f" ({said[k][1]} ids)" if said[k][1] else "") for k in ks),
                         "list the counted ids on the pattern (arx2 pattern add <key> ... --items <ids> --set <set>), or lower the count"))
    return out


def _flaky_claims(c: Ctx):
    """(entity, name, claimed count, sets that bear on it) for every hill or pattern that says it is flaky."""
    used = set()
    for hk, h in c.s["hills"].items():
        pat = c.s["patterns"].get(h.get("pattern") or "", {})
        used.add(h.get("pattern"))
        if h.get("status") == "closed":
            continue
        text = " ".join(str(x or "") for x in (h.get("name"), h.get("symptom"), pat.get("name"), pat.get("cause"), pat.get("of_what")))
        if FLAKY.search(text):
            goal = c.s["goals"].get(h.get("goal") or "", {})
            sets = {*(h.get("eval_sets") or []), h.get("symptom_set"), h.get("control"), pat.get("set"), goal.get("set")} - {None}
            yield f"hill:{hk}", h["name"], pat.get("count"), sets
    for pk, pat in c.s["patterns"].items():
        if pk not in used and FLAKY.search(" ".join(str(pat.get(x) or "") for x in ("name", "cause", "of_what"))):
            yield f"pattern:{pk}", pat["name"], pat.get("count"), ({pat["set"]} if pat.get("set") else None)


@check("flakiness")
def flakiness(c: Ctx):
    out = []
    for ent, name, claimed, sets in _flaky_claims(c):
        reps = {k: v for k, v in c.repeats(sets).items() if len(v) >= 2}
        kind, key = ent.split(":", 1)
        if not reps:
            out.append(finding("error", "flakiness",
                               f"{name} says answers are flaky, but no model has two complete runs on the same set; "
                               "runs of different models differ for other reasons", ent,
                               "run the champion twice on the hill's set, then count items that flip between its own runs"))
            continue
        best = None
        for (m, sk), runs in reps.items():
            per = [{str(x["id"]): stats.score_of(x) for x in c.v.rows(rk)} for rk in runs]
            ids = set.intersection(*(set(d) for d in per))
            flips = sum(1 for i in ids if len({d[i] for d in per}) > 1)
            if best is None or flips > best[0]:
                best = (flips, m, sk, len(runs), len(ids))
        flips, m, sk, nr, n = best
        said = f"{flips} of {n} items flip between {nr} runs of {c.name('candidate', m)} on {c.name('set', sk)}"
        if claimed and claimed > flips:
            out.append(finding("error", "flakiness", f"{name} claims {claimed} flaky items; same-model repeats show {said}",
                               ent, "count flips only between runs of one model on one set, then correct the pattern's --count"))
        else:
            out.append(finding("info", "flakiness", f"{name}: {said}", ent, "none needed"))
    return out


@check("broken_runs")
def broken_runs(c: Ctx):
    out = []
    for rk, why in c.broken().items():
        r = c.s["runs"][rk]
        task = c.s["tasks"].get(r.get("task") or "", {})
        feeds = c.v.latest_run(r["candidate"], r["set"]) == rk
        level = "error" if feeds or task.get("status") == "done" else "warn"
        tail = " It is the run the ladder and goals read." if feeds else f" Its task ended {task.get('status', '?')}."
        out.append(finding(level, "broken_runs",
                           f"Run of {c.name('candidate', r['candidate'])} on {c.name('set', r['set'])} is broken: {why}.{tail}",
                           f"run:{rk}", f"rerun {r['candidate']} on {r['set']}; a fresh complete run supersedes this one"))
    return out


@check("frozen_sets")
def frozen_sets(c: Ctx):
    out = []
    for sk, st in c.s["sets"].items():
        if st.get("hash") and ids_hash(st["ids"]) != st["hash"]:
            out.append(finding("error", "frozen_sets", f"Set {st['name']} no longer matches its frozen fingerprint",
                               f"set:{sk}", f"freeze the new ids under a new key (arx2 set add {sk}-v2 ...)"))
    for rk, r in c.s["runs"].items():
        st = c.s["sets"].get(r["set"])
        if st is None:
            out.append(finding("error", "frozen_sets", f"A run points at set {r['set']}, which the ledger never froze",
                               f"run:{rk}", "freeze the set it ran on, with arx2 set add"))
            continue
        if r.get("hash") and st.get("hash") and r["hash"] != st["hash"]:
            out.append(finding("error", "frozen_sets", f"Run of {c.name('candidate', r['candidate'])} on {st['name']} used a different id list",
                               f"run:{rk}", "rerun it on the frozen set"))
        ids = {str(i) for i in st["ids"]}
        extra = [x["id"] for x in c.v.rows(rk) if str(x["id"]) not in ids]
        if extra:
            out.append(finding("error", "frozen_sets",
                               f"Run of {c.name('candidate', r['candidate'])} on {st['name']} has {_n(len(extra), 'row')} outside the set "
                               f"(e.g. {', '.join(map(str, extra[:3]))})", f"run:{rk}", "rerun it on the set's exact ids"))
    return out


@check("promotions")
def promotions(c: Ctx):
    out = []
    champs = [e for e in c.events if e["type"] == "champion"]
    for ev in champs[1:]:
        key = ev["key"]
        name = c.name("candidate", key)
        if not ev.get("previous"):
            out.append(finding("warn", "promotions", f"{name} was seeded as champion with no ladder", f"candidate:{key}",
                               "promote only through arx2 promote after arx2 gate passes"))
            continue
        vt = c.at(ev["t"] - 1e-6)
        if key not in vt.s["candidates"]:
            out.append(finding("error", "promotions", f"{name} was promoted before it existed", f"candidate:{key}", "add it first"))
            continue
        steps = vt.climb(key)
        bad = [f"{r['name']} {r['v']['state'].replace('_', ' ')}" for r in steps if r["v"]["state"] != "pass"]
        if not steps or bad:
            when = time.strftime("%Y-%m-%d", time.localtime(ev["t"]))
            out.append(finding("error", "promotions",
                               f"{name} became champion on {when} without passing the ladder: " + (", ".join(bad) if bad else "no rungs"),
                               f"candidate:{key}", f"arx2 gate {key}; promote only when every rung passes"))
    return out


@check("goals")
def goals(c: Ctx):
    out = []
    for gk, g in c.s["goals"].items():
        if g["status"] != "achieved":
            continue
        now = c.v.goal_track(gk)
        closes = [h for h in g["history"] if h.get("status") == "achieved"]
        then = c.at(closes[-1]["t"]).goal_track(gk) if closes and closes[-1].get("t") else None
        for label, tr in (("now", now), ("when it was closed", then)):
            if tr is not None and not tr["met"]:
                out.append(finding("error", "goals",
                                   f"Goal {g['name']} is marked achieved, but {label} the champion is at {tr['current']}, target {g['target']}",
                                   f"goal:{gk}", f'reopen it: a goal is achieved by the ledger, not by hand'))
    return out


@check("predictions")
def predictions(c: Ctx):
    out, late = [], {}
    seeds = {e["key"] for e in c.events if e["type"] == "champion" and not e.get("previous")}
    for ck, cd in c.s["candidates"].items():
        if ck in seeds:
            continue
        rung_sets = {r["set"] for r in c.v.rungs_for(cd)}
        runs = [r["created"] for r in c.s["runs"].values() if r["candidate"] == ck and r["set"] in rung_sets]
        if not runs:
            continue
        if not (cd.get("predict") or "").strip():
            late.setdefault("with no prediction", []).append(ck)
        elif cd["created"] > min(runs):
            late.setdefault("with a prediction written after the first run", []).append(ck)
    for why, cks in late.items():
        out.append(group("warn", "predictions", "candidate", cks,
                         lambda k, why=why: f"{c.name('candidate', k)} ran the ladder {why}",
                         lambda ks, why=why: f"{len(ks)} candidates ran the ladder {why}: " + ", ".join(c.name("candidate", k) for k in ks[:6])
                                             + (f" and {len(ks) - 6} more" if len(ks) > 6 else ""),
                         'arx2 cand add <key> ... --predict "<what should move, by how much>" before the first run'))
    return out


@check("splits")
def splits(c: Ctx):
    sc = c.v.split_check()
    out = []
    pairs: dict = {}  # hill -> overlapping pairs
    for x in sc["pairs"]:
        if x["shared"]:
            pairs.setdefault(x["hill"], []).append(f"{c.name('set', x['a'])} and {c.name('set', x['b'])} share {_n(x['shared'], 'item')}")
    if pairs:
        out.append(group("error", "splits", "hill", list(pairs),
                         lambda k: f"Hill {c.name('hill', k)}: {'; '.join(pairs[k])}",
                         lambda ks: f"{len(ks)} hills score on sets that must be separate but share items: "
                                    + "; ".join(f"{c.name('hill', k)} ({', '.join(pairs[k])})" for k in ks),
                         "make disjoint sets with new names and reopen each hill on them"))
    shared: dict = {}  # hill -> {other hill: items shared}
    for x in sc["cross"]:
        for a, b in ((x["a_hill"], x["b_hill"]), (x["b_hill"], x["a_hill"])):
            shared.setdefault(a, {})[b] = shared.get(a, {}).get(b, 0) + x["shared"]
    if shared:
        n_pairs = len(sc["cross"])
        out.append(group("warn", "splits", "hill", list(shared),
                         lambda k: f"Hill {c.name('hill', k)} scores on items another live hill also scores on",
                         lambda ks: f"{len(ks)} live hills score on overlapping items ({_n(n_pairs, 'set pair')}), so one fix moves several: "
                                    + ", ".join(c.name("hill", k) for k in ks),
                         "give each hill its own items"))
    return out


@check("tasks")
def tasks(c: Ctx):
    now = time.time()
    return [finding("error", "tasks", f"Task {t['name']} has been silent for {(now - t['beat']) / 60:.0f} minutes",
                    f"task:{tk}", f'arx2 task end {tk} --status failed --result "<why it stalled>"')
            for tk, t in c.s["tasks"].items() if t["status"] == "running" and now - t["beat"] > STALE_S]


@check("papers")
def papers(c: Ctx):
    try:
        from . import paper
        fn = paper.check
    except (ImportError, AttributeError):
        return [finding("info", "papers", "Papers not checked: this arx2 has no paper check yet", "project:", "none needed")]
    out = []
    for dk, d in c.s["docs"].items():
        if d.get("kind") != "paper":
            continue
        f = c.p.dir / "docs" / (d.get("file") or "")
        if not f.is_file():
            out.append(finding("error", "papers", f"Paper {d.get('name', dk)} has no file", f"doc:{dk}", f"arx2 doc add {dk} --file paper.html ..."))
            continue
        about = d.get("about")
        kind = "goal" if about in c.s["goals"] else "hill" if about in c.s["hills"] else "paper"
        try:
            res = fn(c.p, f.read_text(errors="replace"), kind, about)
        except Exception as e:  # a crashing check is itself a finding
            out.append(finding("error", "papers", f"Paper {d.get('name', dk)}: the paper check failed ({type(e).__name__}: {e})",
                               f"doc:{dk}", "arx2 paper check"))
            continue
        for item in _paper_items(res):
            out.append(finding(item[0], "papers", f"Paper {d.get('name', dk)}: {item[1]}", f"doc:{dk}",
                               f"fix the paper, then arx2 doc add {dk} --kind paper --file <fixed.html> ..."))
    return out


def _paper_items(res):
    """Accept the shapes a paper check may return: {errors, warnings}, or a list of strings or dicts."""
    if isinstance(res, dict):
        for lvl, k in (("error", "errors"), ("warn", "warnings")):
            for x in res.get(k) or []:
                yield lvl, x if isinstance(x, str) else x.get("what") or x.get("msg") or str(x)
        return
    for x in res or []:
        if isinstance(x, str):
            yield "error", x
        else:
            lvl = x.get("level", "error")
            yield ("warn" if lvl.startswith("warn") else "info" if lvl == "info" else "error"), x.get("what") or x.get("msg") or str(x)


@check("answers")
def answers(c: Ctx):
    out = []
    for ak, a in c.s["asks"].items():
        for i, ans in enumerate(a["answers"]):
            words = sum(len((x.get("body") or "").split()) for x in ans["parts"] if x["type"] in ("md", "text", "txt"))
            figure = any(x["type"] not in TEXT_PARTS for x in ans["parts"])
            why = []
            if words > ANSWER_WORDS:
                why.append(f"{words} words")
            if not figure and words > FIGURE_WORDS:
                why.append("no figure")
            if why:
                out.append(finding("warn", "answers", f"Answer {i + 1} to \"{a['text'][:60]}\" has {' and '.join(why)}",
                                   f"ask:{ak}", "lead with one figure and about 60 words (arx2 ask answer --file x.svg --text ...)",
                                   link=a.get("route") or None))
    return out


# ---- entry points --------------------------------------------------------------

def audit(p: Project, only: str | list | None = None, v: Views | None = None) -> list[dict]:
    c = Ctx(p, v)
    names = [only] if isinstance(only, str) else list(only or CHECKS)
    out = []
    for n in names:
        if n not in CHECKS:
            raise KeyError(n)
        for f in CHECKS[n](c):
            f.setdefault("entities", [f["entity"]])
            if f["link"] is None:
                kind, _, key = f["entity"].partition(":")
                f["link"] = _link_for(c, kind, key) if len(f["entities"]) == 1 else {"hill": "hills", "pattern": "hills", "candidate": "ladder"}.get(kind)
            out.append(f)
    order = {"error": 0, "warn": 1, "info": 2}
    return sorted(out, key=lambda f: order[f["level"]])


def summary(findings: list[dict], n_checks: int | None = None) -> dict:
    e = sum(1 for f in findings if f["level"] == "error")
    w = sum(1 for f in findings if f["level"] == "warn")
    return {"errors": e, "warnings": w, "checks": len(CHECKS) if n_checks is None else n_checks}


def guard(p: Project, action: str, key: str) -> list[dict]:
    """Errors that bear on one write: `promote <cand>` or `goal close <goal> --status achieved`."""
    c = Ctx(p)
    s = c.s
    out = []
    if action == "promote":
        cd = s["candidates"].get(key)
        if cd is None or not s["champion"]:
            return []  # the first champion is a seed: there is nothing to climb against yet
        steps = c.v.climb(key)
        bad = [f"{r['name']} {r['v']['state'].replace('_', ' ')}" for r in steps if r["v"]["state"] != "pass"]
        if not steps or bad:
            out.append(finding("error", "promotions", f"{cd['name']} has not passed the ladder: " + (", ".join(bad) or "no rungs"),
                               f"candidate:{key}", f"arx2 gate {key}"))
        runs = {r["v"].get(x) for r in steps for x in ("run", "base_run")} - {None}
        sets = {r["set"] for r in steps}
        ents = {f"run:{rk}" for rk in runs} | {f"set:{sk}" for sk in sets} | ({f"hill:{cd['hill']}"} if cd.get("hill") else set())
        checks = ["broken_runs", "frozen_sets", "splits", "hill_evidence"]
    elif action == "goal_close":
        g = s["goals"].get(key)
        if g is None:
            return []
        champ = s["champion"]
        run = c.v.latest_run(champ, g["set"]) if champ else None
        ents = {f"goal:{key}", f"set:{g['set']}", f"candidate:{champ}"} | ({f"run:{run}"} if run else set())
        checks = ["goals", "broken_runs", "frozen_sets", "promotions"]
    else:
        raise KeyError(action)
    for n in checks:
        out += [f for f in CHECKS[n](c) if f["level"] == "error" and ents & set(f.get("entities") or [f["entity"]])]
    return out


RULES = """# Rules arx2 enforces

`arx2 verify` checks each one against the ledger. Errors block `arx2 promote` and `arx2 goal close --status achieved`.

- Hills need evidence: a hill names its failing items (a symptom set or the pattern's ids), so the problem shows on real rows.
- Prevalence is backed by ids: "15 of 57" lists at least 15 item ids; a count nobody can check is a guess.
- Flakiness needs same-model repeats: two complete runs of one candidate on one set; different models differ for other reasons.
- Broken runs do not count: all zeros, mostly errors or missing rows mean the harness failed, not the model.
- Frozen sets stay frozen: every run uses its set's exact ids, so scores on one set compare.
- Promote through the ladder: a champion passed every rung at the time it was promoted.
- Goals are achieved by the ledger: the champion meets the target on the goal's set, now and when it was closed.
- Predict before you run: a candidate says what should move, and by how much, before its first rung.
- Hill sets share no items: symptom, eval, training and control sets are disjoint, or a gain is not a gain.
- Papers pass `paper check` before they are published.
- Answers lead with a figure: one picture of the rows, then about 60 words.
- Verify before reporting: run `arx2 verify` before you report any result, and fix every error.
"""
