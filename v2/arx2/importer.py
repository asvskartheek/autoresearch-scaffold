"""Rebuild an arx v1 ledger (.research/) as an arx2 event log, and prove nothing changed.

Rows and metric files are copied byte for byte. Every other record becomes events stamped with the
original time, so the rebuilt project replays in the order it happened.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from . import stats
from .store import DIR, NAME_RE, Project, ids_hash, register, slug

ROLE = {"full": "full", "dev": "eval", "random": "random", "control": "control", "synthetic": "eval"}
TASK_STATUS = {"done": "done", "completed": "done", "failed": "failed", "cancelled": "cancelled", "abandoned": "cancelled",
               "running": "running", "partial": "partial", "budget": "budget"}
MODEL_STATUS = {"champion": "trying", "rejected": "rejected", "candidate": "trying", "planned": "planned",
                "historical": "historical", "retired": "retired"}


def _j(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def _jl(p: Path):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _fallback(text: str, used: set) -> str:
    """Used only when the names file has no entry: two capitalised words from the text, made unique."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in (text or "Item")).split() if not w.isdigit()][:2]
    name = " ".join(w.capitalize() for w in words)[:24].strip() or "Item"
    if not NAME_RE.match(name):
        name = "Item"
    first, i = name.split(" ")[0][:16], 2
    while name in used:
        name = f"{first} No{i}"
        i += 1
    used.add(name)
    return name


def import_arx1(src: Path, dest: Path, key: str | None = None, names: Path | None = None) -> dict:
    src = Path(src)
    old = src / ".research" if (src / ".research").is_dir() else src
    root_cfg = _j(old.parent / "research.json", {})
    names_p = names or (dest / "names.json")
    nm = _j(Path(names_p), {}) if Path(names_p).exists() else {}
    for k in ("goals", "hills", "models", "sets", "datasets", "tasks"):
        nm.setdefault(k, {})

    if (dest / DIR).exists():
        shutil.rmtree(dest / DIR)
    p = Project(dest)
    evs: list[dict] = []

    def ev(t, type_, **d):
        evs.append({"t": t, "type": type_, "actor": d.pop("actor", "agent"), **d})

    goals = _j(old / "goals.json", {})
    hills = _j(old / "hills.json", {})
    models = _j(old / "models.json", {})
    slices = _j(old / "slices.json", {})
    datasets = _j(old / "datasets.json", {})
    decisions = _jl(old / "decisions.jsonl")
    t0 = min([d["t"] for d in decisions] + [v.get("created", 9e12) for v in slices.values()])

    ev(t0 - 1, "project", name="Plant Q&A", task=root_cfg.get("solver_goal") or root_cfg.get("name"),
       title=root_cfg.get("name"),
       measure={"name": "Judged correct", "scale": "binary", "direction": "max", "unit": ""},
       context={"privacy": root_cfg.get("privacy"), "datasets": {k: {"name": nm["datasets"].get(k, k), **v} for k, v in datasets.items()}},
       imported_from=str(old))

    used = set(nm["sets"].values())
    for k, v in slices.items():
        ids = [str(i) for i in v["ids"]]
        ev(v.get("created", t0), "set", key=k, name=nm["sets"].get(k) or _fallback(k.split("/")[-1], used),
           dataset=v.get("dataset"), role=ROLE.get(v.get("kind"), "eval"), purpose=v.get("description") or v.get("metric") or "",
           ids=ids, n=v.get("n", len(ids)), hash=v.get("hash"), scale=v.get("scale"), unit=v.get("unit"),
           metric=v.get("metric"), old_kind=v.get("kind"))

    # The ladder from research.json, rungs named for people.
    rung_name = {"dev": "Hill sets", "random50": "Random 50", "random100": "Random 100", "full": "Full set"}
    rungs = []
    for r in root_cfg.get("ladder", []):
        for c in r["checks"]:
            sk = c["slice"]
            set_key = {"@hill.target": "@hill.eval", "@hill.control": "@hill.control", "@hills.climbed": "@hills.climbed"}.get(
                sk, f"{root_cfg.get('primary_dataset', 'pid183')}/{sk}")
            name = {"@hill.target": "Hill target", "@hill.control": "Hill control", "@hills.climbed": "Keep climbed"}.get(
                sk, rung_name.get(sk, sk.title()))
            rungs.append({"name": name, "set": set_key, "rule": "improve" if c["rule"] == "better" else "hold",
                          "margin": c.get("margin", 0.0), "tol": c.get("tolerance", 0.0), "metric": "score", "step": r["rung"]})
    ev(t0, "ladder", key="main", rungs=rungs)

    for k, g in goals.items():
        ev(g["created"], "goal", key=k, name=nm["goals"].get(k) or _fallback(g["title"], set()), vague=g.get("problem"),
           set=g["slice"], metric=g.get("kpi", "score"), direction="max" if g.get("higher_is_better", True) else "min",
           target=g["target"], n=g.get("n"), hash=g.get("slice_hash"), title=g.get("title"), baseline=g.get("baseline"))
        if g.get("status") in ("achieved", "abandoned"):
            ev(g.get(g["status"], g["created"]), "goal.status", key=k, status=g["status"],
               reason=g.get("reason") or (g.get("evidence") or {}).get("note"), evidence=g.get("evidence"))

    used = set(nm["hills"].values())
    for k, h in hills.items():
        share = h.get("share")
        pat = None
        if share or h.get("examples"):
            pat = f"{k}-pattern"
            ev(h["created"] - 0.001, "pattern", key=pat, name=nm["hills"].get(k) or _fallback(h["title"], set()),
               cause=h.get("symptom") or h.get("problem"), items=[], count=(share or {}).get("count"),
               of=(share or {}).get("of"), of_what=(share or {}).get("of_what"), examples=h.get("examples") or [])
        ev(h["created"], "hill", key=k, name=nm["hills"].get(k) or _fallback(h["title"], used), title=h.get("title"),
           goal=h.get("goal"), pattern=pat, symptom=h.get("symptom") or h.get("problem"), problem=h.get("problem"),
           measure=h.get("measure"), example=(h.get("examples") or [None])[0], examples=h.get("examples") or [],
           found_in=h.get("found_in"), phase=h.get("phase"), symptom_set=None,
           eval_sets=[h["target"]] if h.get("target") else [], train_sets=[], control=h.get("control"))
        if h.get("status") in ("closed", "climbed"):
            ev(h.get(h["status"]) or h.get("closed") or h.get("climbed") or h["created"] + 1, "hill.status", key=k,
               status=h["status"], reason=h.get("reason"), superseded_by=h.get("superseded_by"))

    used = set(nm["models"].values())
    for k, m in models.items():
        ev(m.get("created", t0), "candidate", key=k, name=nm["models"].get(k) or _fallback(m.get("title") or k, used),
           title=m.get("title"), parent=m.get("parent"), hill=m.get("hill"), change=m.get("change"),
           predict=None, links=m.get("links") or {}, status=MODEL_STATUS.get(m.get("status"), "trying"))
        if m.get("status") in ("rejected", "retired", "historical", "planned") and m.get("status") != "historical":
            pass

    seen_champ = set()
    for d in decisions:
        if d["kind"] in ("champion", "promote"):
            if d["kind"] == "champion" and d["model"] in seen_champ:
                continue
            seen_champ.add(d["model"])
            ev(d["t"], "champion", key=d["model"], previous=d.get("replaced"), reason=d.get("note") or "Promoted after passing the ladder.",
               gate=d.get("gate"))
        elif d["kind"] == "rejected":
            ev(d["t"], "candidate.status", key=d["model"], status="rejected", reason=d.get("reason"))
        elif d["kind"] == "note":
            ev(d["t"], "note", text=d.get("note") or d.get("text"), about=d.get("model") or d.get("hill"))
    # Final model statuses that no decision recorded (rejected without a decision line, retired, planned).
    rejected_by_decision = {d["model"] for d in decisions if d["kind"] == "rejected"}
    for k, m in models.items():
        st = m.get("status")
        if st in ("rejected", "retired") and k not in rejected_by_decision:
            ev(m.get("updated") or m.get("created", t0) + 1, "candidate.status", key=k, status=st, reason=m.get("reason"))

    # Tasks, runs, rows.
    tdir = old / "tasks"
    copied = 0
    for d in sorted(tdir.iterdir()) if tdir.exists() else []:
        tj = _j(d / "task.json")
        if not tj:
            continue
        tid = tj["id"]
        name = nm["tasks"].get(tid) or _fallback(tj.get("kind", "task") + " " + (tj.get("title") or ""), set())
        ev(tj["created"], "task.start", id=tid, name=name, kind=tj.get("kind"), about=tj.get("title"),
           description=tj.get("description"), total=(tj.get("progress") or {}).get("total"), parent=tj.get("parent"),
           budget_s=tj.get("budget_s"), agent=tj.get("agent"), model=tj.get("model"), set=tj.get("slice"))
        for e in _jl(d / "events.jsonl"):
            if e.get("msg"):
                ev(e["t"], "task.note", id=tid, text=e["msg"])
        for label, url in (tj.get("links") or {}).items():
            ev(tj["created"] + 0.0001, "task.link", id=tid, label=label, url=url)
        done = (tj.get("progress") or {}).get("done")
        if done:
            ev(tj.get("updated") or tj["created"], "task.progress", id=tid, done=done)
        if (d / "rows.jsonl").exists() and tj.get("model") and tj.get("slice"):
            run = f"run-{tid}"
            ev(tj["created"] + 0.0002, "run", key=run, candidate=tj["model"], set=tj["slice"], task=tid,
               hash=tj.get("slice_hash"), recorded=tj.get("summary") or {})
            dst = p.dir / "rows" / f"{run}.jsonl"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(d / "rows.jsonl", dst)
            copied += 1
        elif tj.get("kind") == "historical_run" and tj.get("summary") and tj.get("model"):
            sm = tj["summary"]
            ev(tj["created"] + 0.0002, "run", key=f"run-{tid}", candidate=tj["model"],
               set=tj.get("slice") or sm.get("registered_slice"), task=tid, recorded=sm, aggregate_only=True)
        if (d / "metrics.jsonl").exists():
            dst = p.dir / "metrics" / f"{tid}.jsonl"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(d / "metrics.jsonl", dst)
        if tj.get("status") != "running":
            ev(tj.get("ended") or tj.get("updated") or tj["created"], "task.end", id=tid,
               status=TASK_STATUS.get(tj.get("status"), "done"),
               result=(_jl(d / "events.jsonl") or [{}])[-1].get("msg") if (d / "events.jsonl").exists() else None)

    # Papers: hill papers are internal, goal papers external.
    pdir = old / "papers"
    for d in sorted(pdir.iterdir()) if pdir.exists() else []:
        meta = _j(d / "meta.json", {})
        if not (d / "paper.html").exists():
            continue
        dst = p.dir / "docs" / f"{d.name}.html"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(d / "paper.html", dst)
        about = meta.get("goal") or meta.get("hill")
        label = nm["goals"].get(meta["goal"]) if meta.get("goal") else nm["hills"].get(meta.get("hill") or "")
        if d.name.startswith("champion-"):  # one paper per promotion: name it for the model promoted
            champ = next((m for m in models if re.sub(r"[^a-z0-9]+", "-", m.lower()).strip("-") == d.name[len("champion-"):]), None)
            label = nm["models"].get(champ) or label
        ev(meta.get("updated") or meta.get("created") or t0, "doc", key=d.name, kind="paper",
           audience="external" if meta.get("goal") else "internal",
           name=(label or _fallback(meta.get("title") or d.name, set())), title=meta.get("title") or d.name,
           file=dst.name, about=about)

    evs.sort(key=lambda e: e["t"])  # stable: same-time events keep their order
    p.dir.mkdir(parents=True, exist_ok=True)
    with open(p.events_path, "w") as f:
        for e in evs:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    register(key or "aramco", dest)
    return {"events": len(evs), "rows_files": copied, "dest": str(p.dir)}


def verify(src: Path, dest: Path) -> dict:
    """Row files byte-identical; every recorded score recomputes exactly; entity counts and statuses match."""
    src = Path(src)
    old = src / ".research" if (src / ".research").is_dir() else src
    p = Project(dest)
    s = p.state()
    mism = []
    rows_checked = files = 0
    for d in sorted((old / "tasks").iterdir()):
        tj = _j(d / "task.json")
        if not tj or not (d / "rows.jsonl").exists() or not tj.get("slice"):
            continue
        run = f"run-{tj['id']}"
        new = p.dir / "rows" / f"{run}.jsonl"
        files += 1
        if not new.exists() or _sha(new) != _sha(d / "rows.jsonl"):
            mism.append({"what": "rows sha256", "key": run, "old": _sha(d / "rows.jsonl")[:12], "new": _sha(new)[:12] if new.exists() else None})
            continue
        rows = p.rows(run)
        rows_checked += len(rows)
        old_score = (tj.get("summary") or {}).get("score")
        new_score = stats.summarize(rows).get("score")
        if old_score is not None and old_score != new_score:
            mism.append({"what": "score", "key": run, "old": old_score, "new": new_score})
        st = s["sets"].get(tj["slice"])
        if st and st.get("hash") != tj.get("slice_hash"):
            mism.append({"what": "set hash", "key": run, "old": tj.get("slice_hash"), "new": st.get("hash")})
    slices = _j(old / "slices.json", {})
    for k, v in slices.items():
        if [str(i) for i in v["ids"]] != s["sets"][k]["ids"]:
            mism.append({"what": "set ids", "key": k, "old": len(v["ids"]), "new": s["sets"][k]["n"]})
    models = _j(old / "models.json", {})
    champ = next((k for k, m in models.items() if m.get("status") == "champion"), None)
    if champ != s["champion"]:
        mism.append({"what": "champion", "key": "-", "old": champ, "new": s["champion"]})
    for k, m in models.items():
        if m.get("status") in ("rejected", "retired") and s["candidates"][k]["status"] != m["status"]:
            mism.append({"what": "model status", "key": k, "old": m["status"], "new": s["candidates"][k]["status"]})
    for k, g in _j(old / "goals.json", {}).items():
        if g.get("status", "open") != s["goals"][k]["status"]:
            mism.append({"what": "goal status", "key": k, "old": g.get("status"), "new": s["goals"][k]["status"]})
    for k, h in _j(old / "hills.json", {}).items():
        if h.get("status") != s["hills"][k]["status"]:
            mism.append({"what": "hill status", "key": k, "old": h.get("status"), "new": s["hills"][k]["status"]})
    ntasks = sum(1 for d in (old / "tasks").iterdir() if (d / "task.json").exists())
    if ntasks != len(s["tasks"]):
        mism.append({"what": "task count", "key": "-", "old": ntasks, "new": len(s["tasks"])})
    return {"row_files": files, "rows": rows_checked, "sets": len(s["sets"]), "candidates": len(s["candidates"]),
            "tasks": len(s["tasks"]), "goals": len(s["goals"]), "hills": len(s["hills"]),
            "verdict": "identical" if not mism else "MISMATCH", "mismatches": mism}
