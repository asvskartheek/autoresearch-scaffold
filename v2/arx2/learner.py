"""The person's side: flash cards from ledger facts, spaced review, and what they have and have not seen.

Scheduling is a small FSRS-style model: each card has a stability S (days); recall probability decays
as exp(-elapsed / S); a good answer multiplies S, a miss resets it.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict

from .view import Views

DAY = 86400.0


def _pct(v):
    return "-" if v is None else f"{v:.1%}"


def auto_cards(v: Views) -> dict:
    s = v.s
    cards = {}
    sets = s["sets"]
    champ = s["candidates"].get(s["champion"] or "", {})

    def setname(k):
        return sets.get(k, {}).get("name", k)

    for gk, g in s["goals"].items():
        if g["status"] != "open":
            continue
        tr = v.goal_track(gk)
        op = "at least" if g.get("direction", "max") == "max" else "at most"
        cards[f"goal:{gk}"] = {
            "front": f"What exactly does the goal “{g['name']}” require?",
            "back": f"The champion's {g.get('metric', 'score')} on {setname(g['set'])} (n = {g.get('n')}) must be {op} {g['target']}. "
                    f"Today it is {tr['current'] if tr['current'] is None else round(tr['current'], 4)}.",
            "about": gk, "kind": "goal"}
    if champ:
        cards["champion"] = {"front": "Which model is the champion, and what change made it champion?",
                             "back": f"{champ['name']}: {(champ.get('change') or champ.get('title') or '')[:280]}",
                             "about": s["champion"], "kind": "candidate"}
    for hk, h in s["hills"].items():
        if h["status"] not in ("open", "climbed"):
            continue
        pat = s["patterns"].get(h.get("pattern") or "", {})
        share = f" It explains {pat['count']} of {pat['of']} {pat.get('of_what') or ''}." if pat.get("count") else ""
        cards[f"hill:{hk}"] = {"front": f"What goes wrong in the hill “{h['name']}”?",
                               "back": (h.get("symptom") or "")[:300] + share, "about": hk, "kind": "hill"}
        for sk in (h.get("eval_sets") or []) + ([h["control"]] if h.get("control") else []):
            st = sets.get(sk)
            if st:
                cards[f"set:{sk}"] = {"front": f"What is in the set “{st['name']}” and what is it for?",
                                      "back": f"{st['n']} items, role {st['role']}. {(st.get('purpose') or '')[:240]}",
                                      "about": sk, "kind": "set"}
    rungs = s["ladders"].get("main", {}).get("rungs", [])
    if rungs:
        cards["ladder"] = {"front": "Name the ladder steps in order, cheapest first.",
                           "back": " → ".join(r["name"] for r in rungs), "about": "ladder", "kind": "ladder"}
    rejected = sorted((c for c in s["candidates"].items() if c[1]["status"] == "rejected" and c[1].get("reason")),
                      key=lambda kv: kv[1].get("created", 0))[-12:]
    for ck, c in rejected:
        cards[f"why:{ck}"] = {"front": f"Why was “{c['name']}” rejected?", "back": c["reason"][:320], "about": ck,
                              "kind": "candidate"}
    for k, c in s["cards"].items():
        cards[f"agent:{k}"] = {**c, "kind": c.get("kind", "agent")}
    return cards


def schedule(events: list[dict]) -> dict:
    """Card key -> {stability, last, due, reviews, lapses}."""
    st: dict[str, dict] = {}
    for e in events:
        if e.get("kind") != "review":
            continue
        c = st.setdefault(e["card"], {"stability": 0.5, "last": None, "reviews": 0, "lapses": 0, "conf_right": [], })
        g = e.get("grade", "good")
        if g == "again":
            c["stability"] = 0.02
            c["lapses"] += 1
        else:
            c["stability"] *= {"hard": 1.3, "good": 2.5, "easy": 4.0}[g]
        c["reviews"] += 1
        c["last"] = e["t"]
        c["due"] = e["t"] + c["stability"] * DAY
        if e.get("confidence") is not None:
            c["conf_right"].append((e["confidence"], g != "again"))
    return st


def recall(c: dict, now: float) -> float:
    if not c or not c.get("last"):
        return 0.0
    return math.exp(-(now - c["last"]) / (c["stability"] * DAY))


def memory(v: Views, events: list[dict]) -> dict:
    now = time.time()
    cards = auto_cards(v)
    sch = schedule(events)
    due = []
    for k, c in cards.items():
        m = sch.get(k)
        if not m or m["due"] <= now:
            due.append({"key": k, **c, "recall": recall(m, now), "new": m is None})
    due.sort(key=lambda c: (not c["new"], c["recall"]))
    seen: dict[str, float] = {}
    dwell: Counter = Counter()
    hovers: Counter = Counter()
    for e in events:
        if e.get("kind") in ("view", "hover") and e.get("entity"):
            seen[e["entity"]] = max(seen.get(e["entity"], 0), e["t"])
            if e["kind"] == "hover":
                hovers[e["entity"]] += 1
            dwell[e["entity"]] += e.get("dwell_ms", 0)
    calib = defaultdict(lambda: [0, 0])
    for m in sch.values():
        for conf, right in m["conf_right"]:
            calib[conf][0] += right
            calib[conf][1] += 1
    last_visit = max((e["t"] for e in events if e.get("kind") == "visit"), default=None)
    return {"cards": cards, "due": due[:40], "n_due": len(due), "schedule": {k: {kk: vv for kk, vv in m.items() if kk != "conf_right"} for k, m in sch.items()},
            "recall": {k: recall(sch.get(k), now) for k in cards}, "seen": seen, "hovers": dict(hovers.most_common(30)),
            "calibration": {str(k): {"right": v_[0], "n": v_[1]} for k, v_ in sorted(calib.items())},
            "last_visit": last_visit}


def report(p) -> str:
    """For the agent: how the person uses the dashboard, so the agent can improve what it shows."""
    ev = p.learner_events()
    if not ev:
        return "learner: no dashboard activity yet"
    v = Views(p)
    m = memory(v, ev)
    views = Counter(e.get("view") for e in ev if e.get("kind") == "view")
    dwell = defaultdict(int)
    for e in ev:
        if e.get("kind") == "leave":
            dwell[e.get("view")] += e.get("dwell_ms", 0)
    reviews = [e for e in ev if e.get("kind") == "review"]
    missed = Counter(e["card"] for e in reviews if e.get("grade") == "again")
    lines = [f"events: {len(ev)}  visits: {sum(1 for e in ev if e.get('kind') == 'visit')}  reviews: {len(reviews)}"
             f"  recall_rate: {_pct(sum(e.get('grade') != 'again' for e in reviews) / len(reviews)) if reviews else '-'}",
             "views[{}]{{view,opens,dwell_s}}:".format(len(views))]
    lines += [f"  {k},{n},{dwell.get(k, 0) / 1000:.0f}" for k, n in views.most_common(15)]
    if m["hovers"]:
        lines.append("hovered_most (names the person keeps checking; make them clearer):")
        lines += [f"  {k},{n}" for k, n in list(m["hovers"].items())[:10]]
    if missed:
        lines.append("cards_missed (facts that are not sticking; show them more concretely):")
        lines += [f"  {k},{n}" for k, n in missed.most_common(10)]
    lines.append("calibration{confidence,right,n}:")
    lines += [f"  {k},{c['right']},{c['n']}" for k, c in m["calibration"].items()]
    return "\n".join(lines)
