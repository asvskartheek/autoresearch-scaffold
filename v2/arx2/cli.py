"""arx2: the agent side of the bridge. Output follows AXI (axi.md): compact, content first, next steps."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import api, asks, stats
from .axi import clip, emit, fail, kv, table
from .store import LedgerError, Project, check_name, find_root, ids_hash, register, registry, slug
from .view import Views

VERSION = "2.0.0"


def P() -> Project:
    return Project(find_root())


def _ago(t):
    if not t:
        return "-"
    d = time.time() - t
    return f"{d:.0f}s" if d < 90 else f"{d / 60:.0f}m" if d < 5400 else f"{d / 3600:.0f}h" if d < 172800 else f"{d / 86400:.0f}d"


def _pct(v):
    return None if v is None else f"{v:.1%}"


# ---- home ----------------------------------------------------------------

def cmd_home(a):
    try:
        p = P()
    except LedgerError:
        emit("arx2: research bridge. No ledger here.",
             help=['arx2 init --name "<two words>" --task "<what the model does>" --measure "<how one output is scored>"',
                   "arx2 projects"])
        return
    v = Views(p)
    s = v.s
    pr = s["project"]
    champ = s["candidates"].get(s["champion"] or "", {})
    blocks = [f"project: {pr.get('name')} ({p.root})", f"task: {pr.get('task')}",
              f"champion: {champ.get('name', '-')} [{s['champion']}]"]
    goals = []
    for gk, g in s["goals"].items():
        if g["status"] != "open":
            continue
        tr = v.goal_track(gk)
        goals.append({"key": gk, "name": g["name"], "now": tr["current"], "target": g["target"], "met": tr["met"]})
    blocks.append(table("goals", goals, ["key", "name", "now", "target", "met"]))
    hills = [{"key": k, "name": h["name"], "status": h["status"]} for k, h in s["hills"].items() if h["status"] == "open"]
    blocks.append(table("open_hills", hills, ["key", "name", "status"]))
    unproven = []
    for h in hills:
        e = v.hill_evidence(h["key"])
        if not e["ok"] and not e.get("waived"):
            unproven.append({"key": h["key"], "name": h["name"], "missing": "; ".join(e["missing"])})
    blocks.append(table("hills_without_evidence", unproven, ["key", "name", "missing"]) if unproven else "")
    running = [v.task_view(k) for k, t in s["tasks"].items() if t["status"] == "running"]
    blocks.append(table("running", [{**t, "beat": _ago(t["beat"]), "stale": t["stale"]} for t in running],
                        ["id", "name", "done", "total", "beat", "stale"]))
    trying = [k for k, c in s["candidates"].items() if c["status"] == "trying"]
    nexts = []
    for ck in trying[-5:]:
        for r in v.climb(ck):
            if r["v"]["state"] != "pass":
                nexts.append({"cand": ck, "rung": r["name"], "set": r["set"], "state": r["v"]["state"]})
                break
    blocks.append(table("next_gates", nexts, ["cand", "rung", "set", "state"]))
    hints = ['arx2 task start --name "<two words>" --about "<what and why>"', "arx2 gate <cand>"]
    if unproven:
        k0 = unproven[0]["key"]
        hints.insert(0, f'arx2 set add {k0}-symptom --name "<two words>" --dataset <d> --role symptom --ids-file <champion failures>.txt '
                        f'(or arx2 hill close {k0} --status closed --reason "<why>")')
    if any(t["stale"] for t in running):
        hints.insert(0, "arx2 task end <id> --status failed --result \"<why it stalled>\"")
    emit(*blocks, help=hints)


# ---- project -------------------------------------------------------------

def cmd_init(a):
    root = Path(a.root or os.getcwd())
    p = Project(root)
    name = check_name(a.name, "project name")
    if p.events_path.exists():
        emit(f"noop: ledger already exists at {p.dir}", help=["arx2"])
        return
    p.append("project", name=name, task=a.task,
             measure={"name": a.measure, "scale": a.scale, "direction": a.direction, "unit": a.unit})
    register(a.key or slug(name), root)
    emit(f"created: {p.dir}", help=['arx2 set add <key> --name "<two words>" --dataset <d> --role eval --ids-file ids.txt',
                                   'arx2 goal open <key> --name "<two words>" --vague "<the wish>" --set <set> --target 0.9',
                                   "arx2 up"])


def cmd_projects(a):
    rows = [{"key": k, "root": v["root"], "ok": (Path(v["root"]) / ".arx2").is_dir()} for k, v in registry().items()]
    emit(table("projects", rows, ["key", "ok", "root"]))


# ---- sets ----------------------------------------------------------------

ROLES = ["eval", "symptom", "hill", "train", "control", "random", "full"]


def cmd_set_add(a):
    p = P()
    s = p.state()
    ids = [l.strip() for l in open(a.ids_file)] if a.ids_file else a.ids.split(",")
    ids = [i for i in ids if i]
    if a.key in s["sets"]:
        old = s["sets"][a.key]
        if old["ids"] == ids:
            emit(f"noop: set {a.key} already frozen with the same {len(ids)} ids")
            return
        fail(f"set {a.key} is frozen with different ids", fix=f"arx2 set add {a.key}-v2 ... (never edit a frozen set)")
    if len(set(ids)) != len(ids):
        fail("duplicate ids in the list", fix="dedupe the ids file")
    p.append("set", key=a.key, name=check_name(a.name, "set name"), dataset=a.dataset, role=a.role,
             purpose=a.purpose, ids=ids, n=len(ids), hash=ids_hash(ids))
    emit(f"frozen: {a.key} n={len(ids)} hash={ids_hash(ids)}", help=["arx2 check splits"])


def cmd_set_list(a):
    s = P().state()
    rows = [{"key": k, "name": v["name"], "role": v["role"], "dataset": v["dataset"], "n": v["n"]} for k, v in s["sets"].items()]
    emit(table("sets", rows, ["key", "name", "role", "dataset", "n"]))


# ---- goals ---------------------------------------------------------------

def cmd_goal_open(a):
    p = P()
    s = p.state()
    if a.key in s["goals"]:
        emit(f"noop: goal {a.key} exists ({s['goals'][a.key]['status']})")
        return
    if a.set not in s["sets"]:
        fail(f"no set {a.set!r}", fix="arx2 set list")
    st = s["sets"][a.set]
    p.append("goal", key=a.key, name=check_name(a.name, "goal name"), vague=a.vague, set=a.set, metric=a.metric,
             direction=a.direction, target=a.target, n=st["n"], hash=st["hash"])
    op = ">=" if a.direction == "max" else "<="
    emit(f"goal: {a.metric}(champion, {a.set}, n={st['n']}) {op} {a.target}",
         help=[f'arx2 annotate <item> "<what in the input makes the output wrong>" --set {a.set}'])


def cmd_goal_close(a):
    p = P()
    s = p.state()
    g = s["goals"].get(a.key) or fail(f"no goal {a.key}", fix="arx2")
    if a.status == "achieved":
        tr = Views(p).goal_track(a.key)
        if not tr["met"]:
            fail(f"the champion is at {tr['current']} on {g['set']}, target {g['target']}", fix="keep climbing; a goal is achieved by the ledger, not by hand")
    p.append("goal.status", key=a.key, status=a.status, reason=a.reason)
    emit(f"goal {a.key}: {a.status}")


# ---- annotations, patterns, hills -----------------------------------------

def cmd_annotate(a):
    p = P()
    p.append("annotation", set=a.set, item=str(a.item), text=a.text, run=a.run)
    n = sum(1 for x in p.state()["annotations"] if x.get("set") == a.set)
    emit(f"annotated: {a.item} ({n} on {a.set})",
         help=['arx2 pattern add <key> --name "<two words>" --items 3,7,9 --cause "<one sentence>"'])


def cmd_pattern_add(a):
    p = P()
    s = p.state()
    items = [i for i in (a.items or "").split(",") if i]
    if a.items_file:
        items += [l.strip() for l in open(a.items_file) if l.strip()]
    items = list(dict.fromkeys(items))
    if not items:
        fail("a pattern needs the items it was seen on", fix=f"arx2 pattern add {a.key} ... --items 3,7,9 (or --items-file ids.txt)")
    if a.count and a.count > len(items):
        fail(f"--count {a.count} but only {len(items)} items listed; prevalence must be backed by ids",
             fix=f"arx2 pattern add {a.key} ... --items-file ids.txt --set <set> (at least {a.count} ids), or drop --count")
    if a.count:
        frozen = s["sets"][a.set]["ids"] if a.set in s["sets"] else [i for st in s["sets"].values() for i in st["ids"]]
        unknown = [i for i in items if i not in {str(x) for x in frozen}]
        if unknown:
            fail(f"{len(unknown)} listed items are in no frozen set{' ' + a.set if a.set else ''} (e.g. {unknown[0]})",
                 fix="arx2 set add <key> ... --ids-file ids.txt, then list items from it")
    p.append("pattern", key=a.key, name=check_name(a.name, "pattern name"), cause=a.cause, items=items,
             count=a.count or len(items), of=a.of, of_what=a.of_what, set=a.set)
    emit(f"pattern: {a.key} ({len(items)} items)", help=[f"arx2 hill open <key> --pattern {a.key} --goal <goal> ..."])


def cmd_hill_open(a):
    p = P()
    s = p.state()
    if a.key in s["hills"]:
        emit(f"noop: hill {a.key} exists ({s['hills'][a.key]['status']})")
        return
    ev = [x for x in a.eval_sets.split(",") if x]
    tr = [x for x in (a.train_sets or "").split(",") if x]
    for k in ev + tr + [a.symptom_set, a.control]:
        if k and k not in s["sets"]:
            fail(f"no set {k!r}", fix="arx2 set add ...")
    hill = dict(key=a.key, name=check_name(a.name, "hill name"), goal=a.goal, pattern=a.pattern,
                symptom=a.symptom, measure=a.measure_text, example=json.loads(a.example) if a.example else None,
                predict=a.predict, symptom_set=a.symptom_set, eval_sets=ev, train_sets=tr, control=a.control)
    if a.no_evidence:
        hill["evidence_waived"] = a.no_evidence
    else:
        e = _would_be_evidence(p, hill)
        if not a.symptom_set or not e["ok"]:
            why = "no symptom set" if not a.symptom_set else e["missing"][0]
            fail(f"hill {a.key} has no evidence: {why}",
                 fix=f'arx2 set add {a.key}-symptom --name "<two words>" --dataset <d> --role symptom --ids-file <champion failures>.txt, '
                     f'then rerun with --symptom-set {a.key}-symptom (or --no-evidence "<why this hill exists without observed failures>")')
    p.append("hill", **hill)
    chk = [c for c in Views(p).split_check()["pairs"] if c["hill"] == a.key and c["shared"]]
    if chk:
        emit(table("overlaps", chk, ["a", "b", "shared"]))
        fail("the hill's sets share items", fix="make disjoint sets with new names, then reopen the hill")
    emit(f"hill: {a.key} open; splits disjoint", help=['arx2 cand add <key> --name "<two words>" --hill ' + a.key + ' --change "..." --predict "..."'])


def _would_be_evidence(p: Project, hill: dict) -> dict:
    """Evidence for a hill before it is written: fold it into the state in memory, then derive."""
    v = Views(p)
    v.s["hills"][hill["key"]] = {"status": "open", **hill, "created": time.time()}
    return v.hill_evidence(hill["key"])


def cmd_hill_close(a):
    P().append("hill.status", key=a.key, status=a.status, reason=a.reason)
    emit(f"hill {a.key}: {a.status}")


def cmd_ladder(a):
    rungs = json.load(open(a.file))
    for r in rungs:
        check_name(r["name"], "rung name")
    P().append("ladder", key="main", rungs=rungs)
    emit(table("ladder", rungs, ["name", "set", "rule", "metric"]))


# ---- candidates ----------------------------------------------------------

def cmd_cand_add(a):
    p = P()
    s = p.state()
    if a.key in s["candidates"]:
        emit(f"noop: candidate {a.key} exists ({s['candidates'][a.key]['status']})")
        return
    parent = a.parent or s["champion"]
    p.append("candidate", key=a.key, name=check_name(a.name, "candidate name"), parent=parent, hill=a.hill,
             change=a.change, predict=a.predict)
    warn = ""
    if a.hill in s["hills"]:
        e = Views(p).hill_evidence(a.hill)
        if not e["ok"] and not e.get("waived"):
            warn = f"warning: hill {a.hill} has no evidence ({', '.join(e['missing'])}); a gain on it may fix nothing real"
    emit(f"candidate: {a.key} (parent {parent})", warn, help=[f"arx2 gate {a.key}"])


def cmd_gate(a):
    p = P()
    v = Views(p)
    if a.key not in v.s["candidates"]:
        fail(f"no candidate {a.key}", fix="arx2 cand list")
    rows = []
    nxt = None
    for r in v.climb(a.key):
        vv = r["v"]
        c = vv.get("cmp") or {}
        rows.append({"rung": r["name"], "set": r["set"], "rule": r.get("rule"), "state": vv["state"],
                     "delta": c.get("delta"), "lo": c.get("lo"), "hi": c.get("hi"), "n": c.get("n")})
        if nxt is None and vv["state"] != "pass":
            nxt = (r, vv)
    hints = []
    if nxt:
        r, vv = nxt
        if vv["state"] == "no_base":
            hints.append(f"baseline first: run {v.s['champion']} on {r['set']}")
        elif vv["state"] in ("todo",):
            hints.append(f"run {a.key} on {r['set']}  (python: arx2.evaluate('{a.key}', '{r['set']}', run_one))")
        elif vv["state"] in ("fail", "unclear"):
            hints.append(f'arx2 cand reject {a.key} --reason "<rung, set, n, delta and interval>"')
    else:
        hints.append(f'arx2 promote {a.key} --reason "<what climbed>"')
    emit(table("ladder", rows, ["rung", "set", "rule", "state", "delta", "lo", "hi", "n"]), help=hints)


def cmd_cand_status(a, status):
    p = P()
    s = p.state()
    c = s["candidates"].get(a.key) or fail(f"no candidate {a.key}", fix="arx2 cand list")
    if status == "champion":
        if s["champion"] == a.key:
            emit(f"noop: {a.key} is already champion")
            return
        p.append("champion", key=a.key, reason=a.reason, previous=s["champion"])
    else:
        p.append("candidate.status", key=a.key, status=status, reason=a.reason)
    emit(f"{a.key}: {status}")


def cmd_cand_list(a):
    s = P().state()
    rows = [{"key": k, "name": c["name"], "status": c["status"], "hill": c.get("hill")} for k, c in s["candidates"].items()]
    rows = rows[-a.limit:]
    emit(table("candidates", rows, ["key", "name", "status", "hill"], total=len(s["candidates"])))


# ---- tasks and runs ------------------------------------------------------

def cmd_task_start(a):
    t = api.Task(a.name, kind=a.kind, about=a.about or "", total=a.total, parent=a.parent, budget_s=a.budget_s,
                 agent=a.agent, project=P())
    print(t.id)


def cmd_task_note(a):
    P().append("task.note", id=a.id, text=a.text)
    emit("noted")


def cmd_task_progress(a):
    ev = {"id": a.id, "done": a.done}
    if a.total is not None:
        ev["total"] = a.total
    P().append("task.progress", **ev)


def cmd_task_log(a):
    point = {"t": time.time()}
    for kvp in a.points:
        k, _, val = kvp.partition("=")
        point[k] = float(val)
    P().append_metric(a.id, point)


def cmd_task_end(a):
    p = P()
    t = p.state()["tasks"].get(a.id) or fail(f"no task {a.id}", fix="arx2")
    if t["status"] != "running":
        emit(f"noop: task {a.id} already {t['status']}")
        return
    p.append("task.end", id=a.id, status=a.status, result=a.result)
    emit(f"task {a.id}: {a.status}")


def cmd_task_left(a):
    t = P().state()["tasks"].get(a.id)
    ok = t and t["status"] == "running" and (not t.get("budget_s") or time.time() - t["started"] < t["budget_s"])
    sys.exit(0 if ok else 1)


def cmd_run_rows(a):
    """Record rows from a file: creates the run (and its task) if needed, appends rows, finishes when complete."""
    p = P()
    s = p.state()
    if a.set not in s["sets"]:
        fail(f"no set {a.set!r}", fix="arx2 set list")
    if a.model not in s["candidates"]:
        fail(f"no candidate {a.model!r}", fix="arx2 cand add ...")
    ids = set(s["sets"][a.set]["ids"])
    rows = [json.loads(l) for l in open(a.file) if l.strip()]
    bad = [r["id"] for r in rows if str(r["id"]) not in ids]
    if bad:
        fail(f"{len(bad)} row ids are not in set {a.set} (e.g. {bad[:3]})", fix="rows must use the set's exact ids")
    keep = ("id", "score", "cost", "latency_s", "error")
    rows = [{k: r.get(k) for k in keep} for r in rows]
    t = api.Task(a.name or "Eval run", kind="eval", total=len(ids), project=p,
                 about=f"{s['candidates'][a.model]['name']} on {s['sets'][a.set]['name']}")
    run = api.new_id("run")
    p.append("run", key=run, candidate=a.model, set=a.set, task=t.id, hash=s["sets"][a.set]["hash"])
    p.append_rows(run, rows)
    sm = stats.summarize(rows)
    t.progress(len(rows))
    t.note(f"Recorded {sm['n']} of {len(ids)} rows: {sm.get('passed')} passed ({sm.get('score', 0):.1%}).")
    t.end("done" if len(rows) == len(ids) else "partial")
    emit(kv({"run": run, "n": sm["n"], "score": sm.get("score"), "errors": sm.get("errors")}), help=[f"arx2 gate {a.model}"])


def cmd_check(a):
    v = Views(P())
    c = v.split_check()
    bad = [x for x in c["pairs"] if x["shared"]]
    emit(f"splits: {'disjoint' if c['ok'] else 'OVERLAP'} ({len(c['pairs'])} pairs checked)",
         table("overlaps", bad, ["hill", "a", "b", "shared"]) if bad else "",
         table("shared_across_hills", c["cross"], ["a_hill", "b_hill", "a", "b", "shared"]) if c["cross"] else "",
         f"hashes: {sum(c['hash_ok'].values())} of {len(c['hash_ok'])} sets match their frozen hash")
    if not c["ok"]:
        sys.exit(1)


# ---- docs, cards, learner --------------------------------------------------

DOC_KINDS = ["paper", "report", "note", "diagram", "card"]


def cmd_doc(a):
    p = P()
    src = Path(a.file)
    dst = p.dir / "docs" / (a.key + src.suffix)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    p.append("doc", key=a.key, kind=a.kind, name=check_name(a.name, "doc name"), file=dst.name,
             about=a.about, audience=a.audience)
    emit(f"doc: {a.key} ({a.kind}, {a.audience})", help=["arx2 up"])


def cmd_card(a):
    p = P()
    key = a.key or slug(a.front)[:30]
    p.append("card", key=key, front=a.front, back=a.back, about=a.about)
    emit(f"card: {key}")


def cmd_learner(a):
    from .learner import report
    emit(report(P()))


# ---- asks: questions people click on the dashboard -------------------------

class Part(argparse.Action):
    """Keeps --text, --file and --link in the order they were given: one answer, many parts."""

    def __call__(self, ap, ns, values, opt=None):
        ns.parts = [*(getattr(ns, "parts", None) or []), (self.dest, values)]


def _wait_open(p, timeout, skip=(), interval=1.0, agent=None):
    t0, seen, s = time.time(), None, None
    while True:
        m = p.events_path.stat().st_mtime if p.events_path.exists() else 0
        if m != seen:
            seen, s = m, p.state()
        a = asks.next_open(s, skip, agent=agent)
        if a:
            return a
        if timeout and time.time() - t0 >= timeout:
            return None
        time.sleep(interval)


def cmd_ask_poll(a):
    p = P()
    q = _wait_open(p, a.timeout, agent=a.agent)
    if not q:
        emit(f"noop: no open question after {a.timeout:g}s", help=["arx2 ask poll"])
        return
    p.append("ask.claim", key=q["key"], agent=a.agent)
    emit(asks.describe(p, q), help=[f'arx2 ask answer {q["key"]} --file figure.svg --text "<one real item; the aggregate with set and n; ~60 words>" '
                                    f'[--link "Label=#/hill/<key>"]', "arx2 ask poll"])


def cmd_ask_answer(a):
    p = P()
    asks.answer(p, a.key, a.parts, agent=a.agent or os.environ.get("ARX2_AGENT"))
    words = sum(len(v.split()) for k, v in a.parts if k == "text")
    pictures = sum(1 for k, _ in a.parts if k == "file")
    warn = []
    if words > 80:
        warn.append(f"warn: {words} words; answers read best as one figure and about 60 words")
    if not pictures and words > 40:
        warn.append("warn: no figure; draw the numbers (--file x.svg) instead of writing them")
    emit(f"answered: {a.key} ({len(a.parts)} part{'s' if len(a.parts) != 1 else ''})", *warn, help=["arx2 ask poll"])


def cmd_ask_reply(a):
    asks.reply(P(), a.key, a.text)
    emit(f"reopened: {a.key}", help=["arx2 ask poll"])


def cmd_ask_list(a):
    s = P().state()
    rows = [{"key": k, "status": q["status"], "age": _ago(q["created"]), "turns": len(q["thread"]), "on": q.get("what"),
             "question": asks.latest(q)[:80],
             "saved": ",".join(x["as"] for x in q["saved"]) or None}
            for k, q in s["asks"].items() if a.all or q["status"] != "answered"]
    emit(table("asks", rows[-a.limit:], ["key", "status", "age", "turns", "on", "question", "saved"], total=len(rows)),
         help=["arx2 ask poll", "arx2 ask list --all"])


def cmd_ask_watch(a):
    """Always on: each question gets its own agent, run in parallel; a follow-up goes back to that question's agent."""
    import threading
    import uuid
    p = P()
    base = a.agent or "watch"
    busy, failed, lock = set(), {}, threading.Lock()

    def say(msg):
        with lock:
            print(msg, flush=True)

    def run(q):
        key, sub = q["key"], f"{base}/{q['key']}"
        turn = sum(1 for x in q["thread"] if x["who"] == "person")
        f = p.dir / "asks" / f"{key}.txt"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(asks.describe(p, q) + "\n\n" + ASK_GUIDE.format(key=key))
        say(f"ask {key} turn {turn}: {asks.latest(q)[:80]}")
        env = {**os.environ, "ARX2_ASK": key, "ARX2_ASK_FILE": str(f), "ARX2_AGENT": sub, "ARX2_ASK_TURN": str(turn),
               "ARX2_ASK_SESSION": str(uuid.uuid5(uuid.NAMESPACE_URL, f"arx2-ask:{p.root}:{key}"))}
        rc = subprocess.call(a.exec, shell=True, cwd=p.root, env=env)
        if p.state()["asks"][key]["status"] == "answered":
            say(f"  {key}: answered")
        else:
            failed[key] = failed.get(key, 0) + 1
            p.append("ask.release", key=key, agent=sub)
            say(f"  {key}: not answered (exit {rc}); released")
        with lock:
            busy.discard(key)

    say(f"watching {p.root} for questions, up to {a.jobs} at once (ctrl-c stops)")
    while True:
        while len(busy) >= a.jobs:
            time.sleep(0.5)
        with lock:
            skip = busy | {k for k, n in failed.items() if n >= 2}
        q = _wait_open(p, 0, skip=skip, interval=0.5, agent=base)
        with lock:
            busy.add(q["key"])
        p.append("ask.claim", key=q["key"], agent=f"{base}/{q['key']}")
        threading.Thread(target=run, args=(q,), daemon=True).start()


ASK_GUIDE = """A person clicked the thing above on the arx2 dashboard and asked the question. Answer with
  arx2 ask answer {key} --text "..." [--file x.svg|x.png|x.html|x.md] [--link "Label=#/hill/<key>"]
Follow "Answering questions" in v2/AGENTS.md: lead with one figure (SVG or HTML) drawn from the ledger rows, then at
most three short lines (one real item, the aggregate with set and n, the takeaway). About 60 words in all."""


# ---- server --------------------------------------------------------------

def cmd_serve(a):
    from .server import serve
    serve(a.port, a.host)


def cmd_up(a):
    import urllib.request
    url = f"http://127.0.0.1:{a.port}/"
    try:
        urllib.request.urlopen(url + "api/projects", timeout=1)
        emit(f"up: {url}")
        return
    except Exception:
        pass
    log = Path.home() / ".arx2" / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([sys.executable, "-m", "arx2.cli", "serve", "--port", str(a.port)],
                     stdout=open(log, "a"), stderr=subprocess.STDOUT, start_new_session=True,
                     env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)})
    for _ in range(30):
        time.sleep(0.2)
        try:
            urllib.request.urlopen(url + "api/projects", timeout=1)
            emit(f"up: {url}")
            return
        except Exception:
            continue
    fail("the dashboard did not start", fix=f"read {log}")


def cmd_import(a):
    from .importer import import_arx1
    out = import_arx1(Path(a.src), Path(a.dest), key=a.key)
    emit(kv(out), help=["arx2 verify-import " + a.src + " " + a.dest])


def cmd_verify_import(a):
    from .importer import verify
    out = verify(Path(a.src), Path(a.dest))
    emit(kv({k: v for k, v in out.items() if k != "mismatches"}),
         table("mismatches", out["mismatches"][:20], ["what", "key", "old", "new"], total=len(out["mismatches"])))
    if out["mismatches"]:
        sys.exit(1)


# ---- parser --------------------------------------------------------------

def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="arx2", description="Research bridge: agents log work, people understand it.")
    ap.add_argument("-v", "--version", action="version", version=VERSION)
    sp = ap.add_subparsers(dest="cmd")

    def cmd(name, fn, help_):
        x = sp.add_parser(name, help=help_)
        x.set_defaults(fn=fn)
        return x

    x = cmd("init", cmd_init, "create a ledger here")
    x.add_argument("--name", required=True); x.add_argument("--task", required=True)
    x.add_argument("--measure", required=True, help="how one output becomes one number")
    x.add_argument("--scale", choices=["binary", "continuous"], default="binary")
    x.add_argument("--direction", choices=["max", "min"], default="max")
    x.add_argument("--unit", default=""); x.add_argument("--key"); x.add_argument("--root")
    cmd("projects", cmd_projects, "list registered projects")

    x = cmd("set", None, "frozen item lists"); ssp = x.add_subparsers(dest="sub")
    y = ssp.add_parser("add"); y.set_defaults(fn=cmd_set_add)
    y.add_argument("key"); y.add_argument("--name", required=True); y.add_argument("--dataset", required=True)
    y.add_argument("--role", choices=ROLES, required=True); y.add_argument("--purpose", default="")
    g = y.add_mutually_exclusive_group(required=True); g.add_argument("--ids-file"); g.add_argument("--ids")
    ssp.add_parser("list").set_defaults(fn=cmd_set_list)

    x = cmd("goal", None, "precise goals"); gsp = x.add_subparsers(dest="sub")
    y = gsp.add_parser("open"); y.set_defaults(fn=cmd_goal_open)
    y.add_argument("key"); y.add_argument("--name", required=True); y.add_argument("--vague", required=True)
    y.add_argument("--set", required=True); y.add_argument("--metric", default="score")
    y.add_argument("--direction", choices=["max", "min"], default="max"); y.add_argument("--target", type=float, required=True)
    y = gsp.add_parser("close"); y.set_defaults(fn=cmd_goal_close)
    y.add_argument("key"); y.add_argument("--status", choices=["achieved", "abandoned"], required=True); y.add_argument("--reason", required=True)

    x = cmd("annotate", cmd_annotate, "note what in the input makes an output wrong")
    x.add_argument("item"); x.add_argument("text"); x.add_argument("--set", required=True); x.add_argument("--run")

    x = cmd("pattern", None, "group annotations"); psp = x.add_subparsers(dest="sub")
    y = psp.add_parser("add"); y.set_defaults(fn=cmd_pattern_add)
    y.add_argument("key"); y.add_argument("--name", required=True); y.add_argument("--items"); y.add_argument("--items-file")
    y.add_argument("--cause", required=True); y.add_argument("--count", type=int); y.add_argument("--of", type=int)
    y.add_argument("--of-what"); y.add_argument("--set")

    x = cmd("hill", None, "symptom-targeted efforts"); hsp = x.add_subparsers(dest="sub")
    y = hsp.add_parser("open"); y.set_defaults(fn=cmd_hill_open)
    y.add_argument("key"); y.add_argument("--name", required=True); y.add_argument("--goal", required=True)
    y.add_argument("--pattern"); y.add_argument("--symptom", required=True); y.add_argument("--measure-text")
    y.add_argument("--example", help='json {"input","wrong","right","why"}'); y.add_argument("--predict")
    y.add_argument("--symptom-set"); y.add_argument("--eval-sets", required=True); y.add_argument("--train-sets")
    y.add_argument("--control")
    y.add_argument("--no-evidence", metavar="WHY", help="open without a symptom set the champion fails; say why")
    y = hsp.add_parser("close"); y.set_defaults(fn=cmd_hill_close)
    y.add_argument("key"); y.add_argument("--status", choices=["climbed", "closed"], required=True); y.add_argument("--reason", required=True)

    x = cmd("ladder", cmd_ladder, "set the ladder from a json list of rungs"); x.add_argument("file")

    x = cmd("cand", None, "candidates"); csp = x.add_subparsers(dest="sub")
    y = csp.add_parser("add"); y.set_defaults(fn=cmd_cand_add)
    y.add_argument("key"); y.add_argument("--name", required=True); y.add_argument("--parent"); y.add_argument("--hill")
    y.add_argument("--change", required=True); y.add_argument("--predict")
    y = csp.add_parser("reject"); y.set_defaults(fn=lambda a: cmd_cand_status(a, "rejected"))
    y.add_argument("key"); y.add_argument("--reason", required=True)
    y = csp.add_parser("list"); y.set_defaults(fn=cmd_cand_list); y.add_argument("--limit", type=int, default=30)
    x = cmd("promote", lambda a: cmd_cand_status(a, "champion"), "make a candidate champion")
    x.add_argument("key"); x.add_argument("--reason", required=True)
    x = cmd("gate", cmd_gate, "where a candidate stands on the ladder"); x.add_argument("key")

    x = cmd("task", None, "atomic visible work"); tsp = x.add_subparsers(dest="sub")
    y = tsp.add_parser("start"); y.set_defaults(fn=cmd_task_start)
    y.add_argument("--name", required=True); y.add_argument("--kind", default="work"); y.add_argument("--about")
    y.add_argument("--total", type=int); y.add_argument("--parent"); y.add_argument("--budget-s", type=float); y.add_argument("--agent")
    y = tsp.add_parser("note"); y.set_defaults(fn=cmd_task_note); y.add_argument("id"); y.add_argument("text")
    y = tsp.add_parser("progress"); y.set_defaults(fn=cmd_task_progress)
    y.add_argument("id"); y.add_argument("--done", type=int, required=True); y.add_argument("--total", type=int)
    y = tsp.add_parser("log"); y.set_defaults(fn=cmd_task_log); y.add_argument("id"); y.add_argument("points", nargs="+")
    y = tsp.add_parser("end"); y.set_defaults(fn=cmd_task_end); y.add_argument("id")
    y.add_argument("--status", default="done", choices=["done", "failed", "cancelled", "budget"]); y.add_argument("--result")
    y = tsp.add_parser("left"); y.set_defaults(fn=cmd_task_left); y.add_argument("id")

    x = cmd("run", cmd_run_rows, "record eval rows from a jsonl file")
    x.add_argument("--model", required=True); x.add_argument("--set", required=True); x.add_argument("--file", required=True)
    x.add_argument("--name")
    cmd("check", cmd_check, "verify split disjointness and set hashes")

    x = cmd("doc", cmd_doc, "add a paper, note or diagram")
    x.add_argument("key"); x.add_argument("--kind", choices=DOC_KINDS, required=True); x.add_argument("--name", required=True)
    x.add_argument("--file", required=True); x.add_argument("--about"); x.add_argument("--audience", choices=["internal", "external"], default="internal")
    x = cmd("card", cmd_card, "add a flash card")
    x.add_argument("--front", required=True); x.add_argument("--back", required=True); x.add_argument("--about"); x.add_argument("--key")
    cmd("learner", cmd_learner, "how the person uses the dashboard (to improve it)")

    x = cmd("ask", None, "questions people ask by clicking the dashboard"); qsp = x.add_subparsers(dest="sub")
    y = qsp.add_parser("poll", help="wait for an open question, claim it and print it"); y.set_defaults(fn=cmd_ask_poll)
    y.add_argument("--timeout", type=float, default=0, help="seconds; 0 waits forever"); y.add_argument("--agent")
    y = qsp.add_parser("answer", help="answer in parts: --text, --file and --link, in order"); y.set_defaults(fn=cmd_ask_answer, parts=[])
    y.add_argument("key"); y.add_argument("--agent")
    for f, h in (("--text", "markdown"), ("--file", "svg, png, html or md"), ("--link", "label=#/hill/<key> or an url")):
        y.add_argument(f, action=Part, help=h)
    y = qsp.add_parser("reply", help="a follow-up in the same thread"); y.set_defaults(fn=cmd_ask_reply)
    y.add_argument("key"); y.add_argument("--text", required=True)
    y = qsp.add_parser("list"); y.set_defaults(fn=cmd_ask_list)
    y.add_argument("--all", action="store_true"); y.add_argument("--limit", type=int, default=30)
    y = qsp.add_parser("watch", help="always on: run an agent command for every question"); y.set_defaults(fn=cmd_ask_watch)
    y.add_argument("--exec", required=True, help="shell command, one per question; gets $ARX2_ASK, $ARX2_ASK_FILE, "
                   "$ARX2_ASK_TURN and $ARX2_ASK_SESSION (stable per question)")
    y.add_argument("--agent"); y.add_argument("--jobs", type=int, default=4, help="questions answered at once")

    x = cmd("serve", cmd_serve, "run the dashboard in the foreground")
    x.add_argument("--port", type=int, default=8790); x.add_argument("--host", default="127.0.0.1")
    x = cmd("up", cmd_up, "start the dashboard in the background"); x.add_argument("--port", type=int, default=8790)
    x = cmd("import-arx1", cmd_import, "rebuild an arx v1 ledger in arx2 form")
    x.add_argument("src"); x.add_argument("dest"); x.add_argument("--key")
    x = cmd("verify-import", cmd_verify_import, "prove the rebuilt ledger matches the old one row for row")
    x.add_argument("src"); x.add_argument("dest")
    return ap


def main(argv=None):
    ap = build()
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        if a.cmd:
            ap.parse_args([a.cmd, "--help"])
        return cmd_home(a)
    try:
        a.fn(a)
    except LedgerError as e:
        fail(str(e), e.fix)


if __name__ == "__main__":
    main()
