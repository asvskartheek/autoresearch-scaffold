"""Derived views: run summaries, ladder verdicts, split checks, goal tracks.

Everything here is computed from the ledger on read; nothing derived is ever stored.
"""
from __future__ import annotations

import itertools
import time

from . import stats
from .store import Project, ids_hash

STALE_S = 600


def measure_of(state: dict) -> dict:
    m = state["project"].get("measure") or {}
    return {"name": m.get("name", "score"), "scale": m.get("scale", "binary"),
            "direction": m.get("direction", "max"), "unit": m.get("unit", "")}


METRICS = {  # metric -> (field in summary, higher is better, row field for pairing, binary)
    "score": ("score", True, "score", True),
    "latency_p50": ("latency_p50", False, "latency_s", False),
    "latency_p95": ("latency_p95", False, "latency_s", False),
    "cost": ("cost", False, "cost", False),
}


class Views:
    def __init__(self, project: Project, until: float | None = None):
        self.p = project
        self.s = project.state(until)
        self._rows: dict[str, list] = {}

    # ---- runs ----------------------------------------------------------
    def rows(self, run: str) -> list[dict]:
        if run not in self._rows:
            self._rows[run] = self.p.rows(run)
        return self._rows[run]

    def run_view(self, key: str) -> dict:
        r = self.s["runs"][key]
        rows = self.rows(key)
        st = self.s["sets"].get(r["set"], {})
        total = st.get("n") or len(rows)
        task = self.s["tasks"].get(r.get("task") or "", {})
        return {**r, "summary": stats.summarize(rows), "total": total,
                "live": task.get("status") == "running", "complete": len(rows) >= total}

    def latest_run(self, model: str, set_key: str, complete_only: bool = True) -> str | None:
        best = None
        for k, r in self.s["runs"].items():
            if r["candidate"] != model or r["set"] != set_key:
                continue
            if complete_only and len(self.rows(k)) < (self.s["sets"].get(set_key, {}).get("n") or 0):
                continue
            if best is None or r["created"] >= self.s["runs"][best]["created"]:
                best = k
        return best

    def compare(self, base_run: str, cand_run: str, metric: str = "score") -> dict:
        field, hib, rowf, binary = METRICS.get(metric, METRICS["score"])
        if metric == "score":
            m = measure_of(self.s)
            binary = m["scale"] == "binary"
            hib = m["direction"] == "max"
        return stats.paired(self.rows(base_run), self.rows(cand_run), binary=binary,
                            higher_better=hib, field=rowf)

    # ---- ladder --------------------------------------------------------
    def rungs_for(self, cand: dict) -> list[dict]:
        ladder = self.s["ladders"].get("main", {"rungs": []})
        hill = self.s["hills"].get(cand.get("hill") or "", {})
        out = []
        for i, rung in enumerate(ladder["rungs"]):
            if rung["set"] == "@hill.eval":
                for j, sk in enumerate(hill.get("eval_sets") or []):
                    out.append({**rung, "set": sk, "name": f"{rung['name']} {j + 1}" if len(hill["eval_sets"]) > 1 else rung["name"], "from": i})
            elif rung["set"] == "@hill.control":
                if hill.get("control"):
                    out.append({**rung, "set": hill["control"], "from": i})
            elif rung["set"] == "@hills.climbed":
                for hk, h in self.s["hills"].items():
                    if h.get("status") == "climbed" and hk != cand.get("hill"):
                        for sk in h.get("eval_sets") or []:
                            out.append({**rung, "set": sk, "name": f"Keep {h['name']}"[:24], "from": i})
            else:
                out.append({**rung, "from": i})
        return out

    def baseline_for(self, cand_key: str, set_key: str) -> str | None:
        """The model a candidate is compared with: its parent if the parent ran this set, else the champion."""
        cand = self.s["candidates"].get(cand_key, {})
        for m in (cand.get("parent"), self.s["champion"]):
            if m and m != cand_key and self.latest_run(m, set_key):
                return m
        return None

    def verdict(self, cand_key: str, rung: dict) -> dict:
        set_key = rung["set"]
        cr = self.latest_run(cand_key, set_key)
        if not cr:
            partial = self.latest_run(cand_key, set_key, complete_only=False)
            return {"state": "running" if partial and self.run_view(partial)["live"] else "todo", "run": partial}
        rule = rung.get("rule", "improve")
        metric = rung.get("metric", "score")
        if rule in ("at_least", "at_most"):
            v = self.run_view(cr)["summary"].get(METRICS[metric][0])
            ok = v is not None and (v >= rung["value"] if rule == "at_least" else v <= rung["value"])
            return {"state": "pass" if ok else "fail", "run": cr, "value": v}
        base = self.baseline_for(cand_key, set_key)
        if not base:
            return {"state": "no_base", "run": cr}
        br = self.latest_run(base, set_key)
        cmp = self.compare(br, cr, metric)
        if rule == "improve":
            margin = rung.get("margin", 0.0)
            state = "pass" if cmp["lo"] > margin else ("fail" if cmp["delta"] <= margin else "unclear")
        else:  # hold: do not get worse by more than tol (point estimate)
            state = "pass" if cmp["delta"] >= -rung.get("tol", 0.0) else "fail"
        return {"state": state, "run": cr, "base": base, "base_run": br, "cmp": cmp}

    def climb(self, cand_key: str) -> list[dict]:
        cand = self.s["candidates"][cand_key]
        return [{**r, **{"v": self.verdict(cand_key, r)}} for r in self.rungs_for(cand)]

    # ---- split checks --------------------------------------------------
    def split_check(self) -> dict:
        """Zero shared items between a hill's symptom set, eval sets, training sets and control."""
        sets = self.s["sets"]

        def items(k):
            st = sets.get(k)
            return {(st.get("dataset"), str(i)) for i in st["ids"]} if st else set()

        checks = []
        for hk, h in self.s["hills"].items():
            groups = {"symptom": [h["symptom_set"]] if h.get("symptom_set") else [],
                      "eval": list(h.get("eval_sets") or []), "train": list(h.get("train_sets") or []),
                      "control": [h["control"]] if h.get("control") else []}
            for (ga, la), (gb, lb) in itertools.combinations(groups.items(), 2):
                if {ga, gb} == {"symptom", "control"}:
                    continue
                for a in la:
                    for b in lb:
                        if a == b and ga != gb:
                            shared = len(items(a))
                        else:
                            shared = len(items(a) & items(b))
                        checks.append({"hill": hk, "a": a, "b": b, "ra": ga, "rb": gb, "shared": shared})
        # No eval set may be shared between two open hills.
        cross = []
        live = [(k, h) for k, h in self.s["hills"].items() if h.get("status") in ("open", "climbed")]
        for (ka, ha), (kb, hb) in itertools.combinations(live, 2):
            for a in ha.get("eval_sets") or []:
                for b in hb.get("eval_sets") or []:
                    n = len(items(a) & items(b))
                    if n:
                        cross.append({"a_hill": ka, "b_hill": kb, "a": a, "b": b, "shared": n})
        hashes = {k: ids_hash(v["ids"]) == v.get("hash") for k, v in sets.items() if v.get("hash")}
        return {"checked": time.time(), "pairs": checks, "cross": cross,
                "ok": all(c["shared"] == 0 for c in checks), "hash_ok": hashes}

    # ---- goals ---------------------------------------------------------
    def goal_track(self, gk: str) -> dict:
        g = self.s["goals"][gk]
        metric = g.get("metric", "score")
        field = METRICS.get(metric, METRICS["score"])[0]
        points = []
        for c in self.s["champions"]:
            r = self.latest_run(c["key"], g["set"])
            v = self.run_view(r)["summary"].get(field) if r else None
            points.append({"t": c["t"], "model": c["key"], "value": v, "run": r})
        tried = []
        for ck in self.s["candidates"]:
            r = self.latest_run(ck, g["set"])
            if r:
                sm = self.run_view(r)["summary"]
                tried.append({"model": ck, "t": self.s["runs"][r]["created"], "value": sm.get(field), "run": r})
        cur = points[-1]["value"] if points else None
        hib = g.get("direction", "max") == "max"
        met = cur is not None and (cur >= g["target"] if hib else cur <= g["target"])
        return {"points": points, "tried": tried, "current": cur, "met": met}

    # ---- tasks ---------------------------------------------------------
    def task_view(self, tid: str) -> dict:
        t = dict(self.s["tasks"][tid])
        now = time.time()
        t["stale"] = t["status"] == "running" and now - t["beat"] > STALE_S
        t["children"] = [k for k, v in self.s["tasks"].items() if v.get("parent") == tid]
        run = next((k for k, r in self.s["runs"].items() if r.get("task") == tid), None)
        if run:
            t["run"] = run
            rows = self.rows(run)
            t["done"] = max(t.get("done", 0), len(rows))
            t.setdefault("total", self.s["sets"].get(self.s["runs"][run]["set"], {}).get("n"))
        if t["status"] == "running" and t.get("total") and t["done"]:
            rate = t["done"] / max(now - t["started"], 1)
            t["eta_s"] = (t["total"] - t["done"]) / rate if rate else None
        return t
