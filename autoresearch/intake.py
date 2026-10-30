"""Goal intake: a person writes the ask in their own words, an agent turns it into a goal proposal, the person answers
its questions, edits the card and opens the goal.

Flow
- POST /api/intake/new {ask}          -> inbox item kind="goal" (queued). `arx answer` runs an agent with PROMPTS["goal"].
- the agent reads the ledger and runs `arx goal propose <item> --json '{...}'` (schema: PROPOSAL below).
- POST /api/intake/answer {id, answers} -> the answers are stored and the item is queued again for a new proposal.
- POST /api/intake/open {id, goal}    -> opens the goal through Project.open_goal, with parent/role/constraints.
- POST /api/intake/dismiss {id}       -> hides the item.
- STATE adds `intake`: the goal items still in play, newest first.

Goals get three optional fields, kept here rather than in core.py: `parent` (another goal), `role` main|guard|sub and
`constraints` (plain lines). `arx goal open` takes them as --parent, --role and --constraint through the CLI hook.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

from . import features

ROLES = ("main", "guard", "sub")
KPIS = ("score", "cost", "latency_p50", "latency_p95", "latency_mean")
LOWER = ("cost", "latency_p50", "latency_p95", "latency_mean")
MAX_Q, MAX_OPTS, MAX_RELATED = 3, 4, 6

PROPOSAL = """{
  "questions": [                      // 0 to 3, only where the answer changes the goal; skip what the ask settles
    {"id": "kpi", "text": "Measured as",  // a few words
     "options": [{"label": "Accuracy", "sub": "correct of 1,319", "value": "score"}, ...]}  // 2 to 4 one-tap options
  ],
  "goal": {
    "name": "gsm8k-1267", "title": "GSM8K 1,267 correct",  // titles in units, never percentages
    "kpi": "score",                   // score | cost | latency_p50 | latency_p95
    "slice": "gsm8k-test/full",       // an existing slice, usually a full one
    "count": 1267,                    // score goals: the target as a count of N (rounded up, so rounding can't meet it)
    "target": 0.9606,                 // other KPIs: the value (seconds, dollars); score goals may give this instead of count
    "against": "the champion now",    // what the paired delta is measured against
    "constraints": ["open weights", "Qwen3 4B or a LoRA of it"],
    "problem": "why the goal matters, one line",
    "why": {"target": "...", "now": "...", "slice": "...", "against": "...", "constraints": "..."}  // one line each
  },
  "related": [                        // guards, held-out robustness, hill sub-goals; up to 6
    {"role": "guard", "name": "gsm8k-96-latency", "title": "No slower than 14 s median", "kpi": "latency_p50",
     "slice": "gsm8k-test/full", "target": 14.0, "why": "..."},
    {"role": "sub", "name": "gsm8k-96-percent-base", "title": "Fix percent-base", "hill": "percent-base",
     "kpi": "score", "slice": "gsm8k-test/dev-percent-base-v1", "count": 170, "why": "..."}
  ],
  "note": "one line: what you read and what you are unsure of"
}"""


# ---------- goals: parent / role / constraints ----------------------------------------------------------------------
def set_meta(p, name, parent=None, role=None, constraints=None) -> dict:
    goals = p.goals()
    if name not in goals:
        raise SystemExit(f"unknown goal {name}")
    _check_meta(p, name, parent, role)
    if role is None and parent:
        role = "sub"
    return p._upsert("goals", name, parent=parent, role=role,
                     constraints=[str(c).strip() for c in constraints if str(c).strip()] if constraints else None)


def _check_meta(p, name, parent, role):
    if role is not None and role not in ROLES:
        raise SystemExit(f"--role must be one of {', '.join(ROLES)}")
    if parent:
        goals = p.goals()
        if parent not in goals:
            raise SystemExit(f"unknown parent goal {parent}")
        seen, g = {name}, parent
        while g:  # a goal can't sit under itself
            if g in seen:
                raise SystemExit(f"goal {name} under {parent} would make a loop")
            seen.add(g)
            g = goals.get(g, {}).get("parent")
    if role in ("guard", "sub") and not parent:
        raise SystemExit(f"a {role} goal needs --parent")


def open_goal(p, g: dict) -> dict:
    """Open one goal from a (possibly edited) proposal card: the existing goal-open code, then parent/role/constraints."""
    name = str(g.get("name") or "").strip()
    if not name or any(c.isspace() for c in name) or "/" in name:
        raise SystemExit("the goal needs a name without spaces or slashes")
    if name in p.goals():
        raise SystemExit(f"goal {name} already exists; give this one a new name")
    if not g.get("title"):
        raise SystemExit("the goal needs a title")
    kpi = g.get("kpi") or "score"
    if kpi not in KPIS:
        raise SystemExit(f"unknown KPI {kpi}")
    sl = p.slice(g.get("slice") or "")
    target = _target(g, kpi, sl["n"], sl.get("scale") == "continuous")
    parent, role = g.get("parent") or None, g.get("role") or ("sub" if g.get("parent") else "main")
    _check_meta(p, name, parent, role)
    rec = p.open_goal(name, g["title"], sl["name"], target, kpi=kpi, problem=g.get("problem") or None,
                      higher_is_better=False if kpi in LOWER else None)
    return set_meta(p, name, parent, role, g.get("constraints")) | rec | {"name": name}


def _target(g, kpi, n, continuous=False) -> float:
    """A score target on a 0/1 slice is a count of n (or a fraction); on a continuous slice it is the amount itself."""
    if kpi == "score" and continuous:
        g = {k: v for k, v in g.items() if k != "count"}
    if kpi == "score" and g.get("count") is not None:
        c = int(g["count"])
        if not 0 < c <= n:
            raise SystemExit(f"the target count must be between 1 and {n}")
        return c / n
    try:
        t = float(g.get("target"))
    except (TypeError, ValueError):
        raise SystemExit("the goal needs a target")
    if not math.isfinite(t) or (kpi == "score" and not continuous and not 0 <= t <= 1):
        raise SystemExit("a score target is a fraction between 0 and 1, or give count")
    return t


# ---------- proposals ----------------------------------------------------------------------------------------------
def item(p, item_id) -> dict:
    it = next((i for i in features.inbox(p) if i["id"] == item_id), None)
    if not it or it.get("kind") != "goal":
        raise SystemExit(f"no goal intake item {item_id}")
    return it


def _clean_goal(p, g, related=False) -> dict:
    if not isinstance(g, dict):
        raise SystemExit("each goal is an object")
    keep = ("name", "title", "kpi", "slice", "count", "target", "against", "problem", "hill", "role")
    out = {k: g[k] for k in keep if g.get(k) is not None}
    for k in ("name", "title", "slice"):
        if not out.get(k):
            raise SystemExit(f"a proposed goal needs {k}")
    out["kpi"] = out.get("kpi") or "score"
    if out["kpi"] not in KPIS:
        raise SystemExit(f"unknown KPI {out['kpi']}; use one of {', '.join(KPIS)}")
    if out.get("count") is None and out.get("target") is None:
        raise SystemExit(f"goal {out['name']} needs count (score) or target")
    out["constraints"] = [str(c) for c in (g.get("constraints") or [])][:8]
    out["why"] = {str(k): str(v) for k, v in (g.get("why") or {}).items()} if isinstance(g.get("why"), dict) else {}
    if g.get("why") and isinstance(g["why"], str):
        out["why"] = {"target": g["why"]}
    if related:
        out["role"] = out.get("role") or "guard"
        if out["role"] not in ("guard", "sub"):
            raise SystemExit("a related goal's role is guard or sub")
    sl = p.slices().get(out["slice"]) or p.slices().get(f"{p.config.get('primary_dataset')}/{out['slice']}")
    if sl:
        out["slice"] = out["slice"] if out["slice"] in p.slices() else f"{p.config.get('primary_dataset')}/{out['slice']}"
        out["n"] = sl["n"]
        if out["kpi"] == "score" and sl.get("scale") == "continuous":  # an amount in the slice's unit, never a count
            out.pop("count", None)
            if out.get("target") is None:
                raise SystemExit(f"goal {out['name']}: {out['slice']} is continuous; give target in {sl.get('unit') or 'its unit'}")
            out["target"] = float(out["target"])
            out["scale"], out["unit"] = "continuous", sl.get("unit")
        elif out["kpi"] == "score" and out.get("count") is None:
            out["count"] = math.ceil(float(out["target"]) * sl["n"] - 1e-9)
        if out["kpi"] == "score" and out.get("count") is not None:
            out["count"] = int(out["count"])
            if not 0 < out["count"] <= sl["n"]:
                raise SystemExit(f"goal {out['name']}: count {out['count']} is not between 1 and {sl['n']}")
    else:
        out["missing_slice"] = True  # e.g. a held-out slice that does not exist yet: shown, can't be opened
        if g.get("n"):
            out["n"] = int(g["n"])
    return out


def propose(p, item_id, data: dict) -> dict:
    it = item(p, item_id)
    if not isinstance(data, dict) or not isinstance(data.get("goal"), dict):
        raise SystemExit("the proposal needs a goal object; see `arx goal propose --help`")
    qs = []
    for i, q in enumerate((data.get("questions") or [])[:MAX_Q]):
        opts = [dict(label=str(o.get("label") or o.get("value")), sub=str(o.get("sub") or ""),
                     value=str(o.get("value") or o.get("label"))) for o in (q.get("options") or [])[:MAX_OPTS]
                if isinstance(o, dict) and (o.get("label") or o.get("value"))]
        if q.get("text") and len(opts) >= 2:
            qs.append(dict(id=str(q.get("id") or f"q{i + 1}"), text=str(q["text"]), options=opts))
    prop = dict(questions=qs, goal=_clean_goal(p, data["goal"]),
                related=[_clean_goal(p, r, related=True) for r in (data.get("related") or [])[:MAX_RELATED]],
                note=str(data.get("note") or ""), round=it.get("round", 0), t=time.time())
    features.update(p, item_id, proposal=prop, status="done", error="")  # the answer is in; a queued copy must not run again
    return prop


# ---------- the prompt ---------------------------------------------------------------------------------------------
def prompt(p, it) -> str:
    ask = (it.get("payload") or {}).get("ask", "")
    answers = it.get("answers") or {}
    prev = it.get("proposal")
    lines = [
        f"You are the goal-intake agent for the arx research project at {p.root}.",
        "A person typed what they want in their own words. Turn it into one measurable goal proposal they can open with one tap.",
        "",
        f"The ask, word for word: {json.dumps(ask)}",
        "",
        "1. Read the ledger first, read-only: `arx status`, `arx goal status --json`, research.json, and",
        "   .research/{slices,models,hills,goals}.json. Read PROTOCOL.md's reporting rules. Do not open goals, run evals,",
        "   train, or write anything else in the project; your only write is the propose command below.",
        "2. Every number comes from the ledger: the champion's KPI on the slice, n, the counts. `arx q numbers` prints",
        "   them pooled over every complete run, as the dashboard and the gates show them; quote those. Never invent a run.",
        "   If something the goal needs is not in the ledger (a closed model's run, a held-out slice, cost logging), say",
        "   so in `why` and propose the related goal with its slice anyway; the dashboard marks it as not yet runnable.",
        "3. The goal: one KPI on one frozen slice (usually the full slice). A score target is a count of N, rounded up",
        "   (96% of 1,319 is 1,266.2, so the target is 1,267). Latency targets are seconds, cost targets dollars.",
        "   On a continuous slice (scale continuous in slices.json) the target is the amount as stored, in its unit.",
        "   Read constraints from the ask and research.json (open weights, model size, hardware).",
        "4. Questions: at most 3, only where the answer would change the goal (the KPI, what it is compared to, when it",
        "   is done). Each has 2 to 4 one-tap options with a short sub-line that shows the number. Skip anything the",
        "   ask or earlier answers settle. With no real ambiguity, ask nothing.",
        "5. Related goals: guards (do not get slower, cheaper or less accurate than the champion now), held-out",
        "   robustness (the same score on unseen examples) and sub-goals from open hills whose target slices sit inside",
        "   the goal slice. Each with its own name, slice and target.",
        "6. Text is read on a small card: titles of 2 to 6 words in units (\"1,267 correct\", \"under 1 s\"), never a",
        "   bare percentage; each `why` one plain sentence with the numbers.",
        "",
        f"When done, run exactly once: arx goal propose {it['id']} --json '<the JSON>'",
        "(or write the JSON to a scratch file and pass --json @path). Schema, comments are not part of the JSON:",
        PROPOSAL,
    ]
    if answers:
        lines += ["", "The person answered your earlier questions; settle them in the new goal and do not ask them again:"]
        qmap = {q["id"]: q for q in (prev or {}).get("questions", [])}
        for qid, v in answers.items():
            q = qmap.get(qid, {})
            lab = next((o["label"] for o in q.get("options", []) if o["value"] == v), v)
            lines.append(f"- {q.get('text', qid)}: {lab} ({v})")
    if prev:
        lines += ["", "Your previous proposal, to revise:", json.dumps({k: prev[k] for k in ("questions", "goal", "related")})]
    return "\n".join(lines)


features.PROMPTS["goal"] = prompt


# ---------- state and routes ---------------------------------------------------------------------------------------
def items(p) -> list[dict]:
    out = []
    for it in features.inbox(p):
        if it.get("kind") != "goal" or it.get("dismissed"):
            continue
        out.append({k: it.get(k) for k in ("id", "status", "task", "error", "result", "proposal", "answers", "answered",
                                             "round", "opened")} | {"ask": (it.get("payload") or {}).get("ask", ""),
                                                           "created": (it.get("payload") or {}).get("created")})
    return sorted(out, key=lambda i: -(i.get("created") or 0))


def _state(p, out):
    out["intake"] = items(p)


features.STATE.append(_state)


def _err(e):
    return 400, {"error": str(e.code if isinstance(e, SystemExit) else e)}


@features.get("/api/intake")
def _get(p, path, q):
    return 200, items(p)


@features.post("/api/intake/")
def _post(p, path, d):
    if not isinstance(d, dict):
        return 400, {"error": "bad request"}
    verb = path.rstrip("/").rsplit("/", 1)[-1]
    try:
        if verb == "new":
            ask = str(d.get("ask") or "").strip()
            if not ask:
                return 400, {"error": "write the ask first"}
            return 200, features.enqueue(p, "goal", dict(ask=ask[:4000], created=time.time()))
        it = item(p, str(d.get("id") or ""))
        if verb == "answer":
            ans = {str(k): str(v) for k, v in (d.get("answers") or {}).items()} if isinstance(d.get("answers"), dict) else {}
            if not ans:
                return 400, {"error": "no answers"}
            merged = (it.get("answers") or {}) | ans
            said = {a["id"]: a for a in it.get("answered") or []}  # what was asked and picked, kept for the thread
            for q in (it.get("proposal") or {}).get("questions", []):
                if q["id"] in ans:
                    lab = next((o["label"] for o in q["options"] if o["value"] == ans[q["id"]]), ans[q["id"]])
                    said[q["id"]] = dict(id=q["id"], text=q["text"], label=lab)
            features.update(p, it["id"], answers=merged, answered=list(said.values()), status="queued", error="",
                            round=it.get("round", 0) + 1)
            return 200, {"id": it["id"], "answers": merged}
        if verb == "open":
            g = d.get("goal")
            if not isinstance(g, dict):
                return 400, {"error": "no goal"}
            if g.get("use"):  # the proposal matches a goal that is already open: record it, open nothing
                if g["use"] not in p.goals():
                    return 400, {"error": f"unknown goal {g['use']}"}
                rec = {"name": g["use"]}
            else:
                rec = open_goal(p, g)
            features.update(p, it["id"], opened=list(dict.fromkeys((it.get("opened") or []) + [rec["name"]])))
            return 200, rec
        if verb == "retry":
            features.update(p, it["id"], status="queued", error="", round=it.get("round", 0) + 1)
            return 200, {"id": it["id"]}
        if verb == "dismiss":
            features.update(p, it["id"], dismissed=True)
            return 200, {"id": it["id"]}
    except SystemExit as e:  # the ledger's own refusals become a message on the card
        return _err(e)
    return 404, {"error": "not found"}


# ---------- CLI: `arx goal propose`, and --parent / --role / --constraint on `arx goal open` --------------------------
def _read_json(v: str):
    if v == "-":
        return json.loads(sys.stdin.read())
    if v.startswith("@"):
        return json.loads(Path(v[1:]).read_text())
    return json.loads(v)


def _n(k, word) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def target_text(p, g) -> str:
    """A proposed goal's target as a person reads it: "≥ 1,267 of 1,319 correct", "≤ 10 s median", "≤ 1,000 ms"."""
    kpi, t = g.get("kpi") or "score", g.get("target")
    sl = p.slices().get(g.get("slice") or "") or {}
    if kpi == "score" and sl.get("scale") != "continuous" and g.get("count") is not None and g.get("n"):
        return f"≥ {int(g['count']):,} of {int(g['n']):,} correct"
    if t is None:
        return "no target"
    t = float(t)
    amt = lambda x: f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}"
    if kpi == "score":  # continuous: a "minus ms" metric is stored negated, so its target reads as the plain amount
        neg = str(sl.get("metric") or "").strip().lower().startswith("minus")
        up = (g.get("higher_is_better", True) is not False) != neg
        return f"{'≥' if up else '≤'} {amt(-t if neg else t)}{(' ' + sl['unit']) if sl.get('unit') else ''}"
    if kpi == "cost":
        return f"≤ ${t:.4g} per answer"
    return f"≤ {amt(t)} s {dict(latency_p50='median', latency_p95='p95', latency_mean='mean').get(kpi, '')}".rstrip()


def _cli(sp):
    gp = sp.choices.get("goal")
    if gp is None:
        return
    verb = next(a for a in gp._actions if a.dest == "verb")
    verb.choices = list(verb.choices) + ["propose", "link"]
    gp.conflict_handler = gp._optionals.conflict_handler = "resolve"  # --json becomes "flag or value": status --json, propose <item> --json '{...}'
    gp.add_argument("--json", nargs="?", const=True, default=False,
                    help="status: print JSON; propose: the proposal JSON, @file or - for stdin")
    gp.add_argument("--parent", help="open/link: the goal this one serves")
    gp.add_argument("--role", choices=ROLES, help="open/link: main, guard (must not get worse) or sub (a part of the parent)")
    gp.add_argument("--constraint", action="append", help="open/link: a rule the result must keep, e.g. \"open weights\"")
    base = gp.get_default("fn")

    def cmd(a):
        if isinstance(a.json, str) and a.verb not in ("propose",) and not a.name:  # `status --json <name>`
            a.name, a.json = a.json, True
        from .core import Project
        if a.verb == "propose":
            if not a.name or not isinstance(a.json, str):
                raise SystemExit("usage: arx goal propose <inbox item> --json '{...}'   (or --json @file, --json -)\n\n" + PROPOSAL)
            try:
                data = _read_json(a.json)
            except (ValueError, OSError) as e:
                raise SystemExit(f"could not read the proposal JSON: {e}")
            prop = propose(Project(), a.name, data)
            g = prop["goal"]
            return print(f"proposal for {a.name}: {g['name']} ({target_text(Project(), g)} on {g['slice']}), "
                         f"{_n(len(prop['questions']), 'question')}, {_n(len(prop['related']), 'related goal')}")
        if a.verb == "link":  # set parent/role/constraints on a goal that is already open
            if not a.name:
                raise SystemExit("usage: arx goal link <goal> --parent <goal> --role guard|sub [--constraint ...]")
            g = set_meta(Project(), a.name, a.parent, a.role, a.constraint)
            return print(f"goal {a.name}: role {g.get('role') or 'main'}" + (f" under {g['parent']}" if g.get("parent") else ""))
        if a.verb == "open" and (a.parent or a.role or a.constraint):
            p = Project()
            _check_meta(p, a.name, a.parent, a.role)
            base(a)
            set_meta(p, a.name, a.parent, a.role, a.constraint)
            return print(f"  role {a.role or ('sub' if a.parent else 'main')}" + (f" under {a.parent}" if a.parent else ""))
        a.json = bool(a.json)
        return base(a)

    gp.set_defaults(fn=cmd)


features.CLI.append(_cli)
