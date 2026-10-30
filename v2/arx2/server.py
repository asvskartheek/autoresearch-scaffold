"""The people side of the bridge: one dashboard for every registered project. Stdlib only."""
from __future__ import annotations

import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import asks, learner, stats
from .store import LedgerError, Project, registry
from .view import METRICS, Views, measure_of

WEB = Path(__file__).parent / "web"
_cache: dict = {}
_lock = threading.Lock()


def project(key: str) -> Project:
    reg = registry()
    if key not in reg:
        raise KeyError(key)
    return Project(Path(reg[key]["root"]))


def _slim_set(k, v):
    return {kk: vv for kk, vv in v.items() if kk != "ids"} | {"key": k}


def build_state(p: Project, until: float | None = None) -> dict:
    v = Views(p, until)
    s = v.s
    champ = s["champion"]
    runs = {}
    for rk in s["runs"]:
        rv = v.run_view(rk)
        sm = rv["summary"] if rv["summary"].get("n") else (rv.get("recorded") or {})
        runs[rk] = {"key": rk, "candidate": rv["candidate"], "set": rv["set"], "task": rv.get("task"),
                    "created": rv["created"], "summary": sm, "total": rv["total"], "live": rv["live"],
                    "aggregate_only": bool(rv.get("aggregate_only"))}
    cands = {}
    for ck, c in s["candidates"].items():
        cl = v.climb(ck) if c["status"] in ("trying", "rejected", "champion", "retired") else []
        steps = []
        for r in cl:
            vv = r["v"]
            cmp = vv.get("cmp") or {}
            steps.append({"name": r["name"], "set": r["set"], "rule": r.get("rule"), "tol": r.get("tol"), "margin": r.get("margin"), "state": vv["state"], "from": r.get("from"),
                          "run": vv.get("run"), "base": vv.get("base"), "base_run": vv.get("base_run"), "value": vv.get("value"),
                          **{k: cmp.get(k) for k in ("delta", "lo", "hi", "n", "better", "worse", "base", "cand")}})
        cands[ck] = {**{k: c.get(k) for k in ("key", "name", "title", "parent", "hill", "change", "predict", "status",
                                               "reason", "created", "links")}, "climb": steps}
    tasks = {}
    order = sorted(s["tasks"], key=lambda k: s["tasks"][k]["started"])
    for tk in order:
        t = v.task_view(tk)
        t["notes"] = t["notes"][-6:]
        t["n_notes"] = len(s["tasks"][tk]["notes"])
        tasks[tk] = t
    goals = {}
    for gk, g in s["goals"].items():
        goals[gk] = {**g, "track": v.goal_track(gk)}
    timeline = [{"t": e["t"], "type": e["type"], "key": e.get("key") or e.get("id"), "status": e.get("status")}
                for e in s["log"] if e["type"] in ("champion", "candidate.status", "goal", "goal.status", "hill", "hill.status", "run", "set")]
    m = memory_state(p, v)
    return {
        "key": None, "project": s["project"], "measure": measure_of(s), "champion": champ,
        "champions": s["champions"], "sets": {k: _slim_set(k, x) for k, x in s["sets"].items()},
        "goals": goals, "hills": s["hills"], "patterns": s["patterns"], "annotations": s["annotations"][-200:],
        "ladder": s["ladders"].get("main", {"rungs": []}), "candidates": cands, "runs": runs, "tasks": tasks,
        "docs": s["docs"], "split": v.split_check(), "evidence": {hk: v.hill_evidence(hk) for hk in s["hills"]},
        "timeline": timeline,
        "span": [s["log"][0]["t"], s["log"][-1]["t"]] if s["log"] else [0, 0], "until": until,
        "n_events": len(s["log"]), "learner": m, "asks": s["asks"],
    }


def memory_state(p: Project, v: Views) -> dict:
    m = learner.memory(v, p.learner_events())
    return {"n_due": m["n_due"], "due": m["due"][:20], "recall": m["recall"], "seen": m["seen"],
            "hovers": m["hovers"], "calibration": m["calibration"], "last_visit": m["last_visit"],
            "n_cards": len(m["cards"])}


def cached_state(key: str, until: float | None) -> dict:
    p = project(key)
    stamp = (p.mtime(), (p.dir / "learner.jsonl").stat().st_mtime if (p.dir / "learner.jsonl").exists() else 0, until)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
    st = build_state(p, until)
    st["key"] = key
    with _lock:
        _cache[key] = (stamp, st)
    return st


def project_card(key: str, root: str) -> dict:
    try:
        st = cached_state(key, None)
    except Exception as e:  # a broken or missing project still shows, marked
        return {"key": key, "root": root, "error": str(e)[:200]}
    running = [t for t in st["tasks"].values() if t["status"] == "running"]
    champ = st["candidates"].get(st["champion"] or "", {})
    last = max([t.get("beat", 0) for t in st["tasks"].values()] + [st["span"][1]])
    return {"key": key, "root": root, "name": st["project"].get("name"), "task": st["project"].get("task"),
            "champion": champ.get("name"), "goals": [{"key": k, "name": g["name"], "target": g["target"], "direction": g.get("direction"),
                                                      "metric": g.get("metric"), "now": g["track"]["current"], "met": g["track"]["met"],
                                                      "status": g["status"]} for k, g in st["goals"].items()],
            "running": len(running), "stale": sum(1 for t in running if t["stale"]), "split_ok": st["split"]["ok"],
            "last": last, "n_candidates": len(st["candidates"]), "n_due": st["learner"]["n_due"]}


def run_detail(p: Project, run: str, base: str | None) -> dict:
    v = Views(p)
    r = v.s["runs"][run]
    rows = v.rows(run)
    st = v.s["sets"].get(r["set"], {})
    out = {"run": r, "rows": rows, "ids": st.get("ids", []), "summary": stats.summarize(rows), "set": _slim_set(r["set"], st) if st else None}
    base = base or v.baseline_for(r["candidate"], r["set"])
    if base:
        br = v.latest_run(base, r["set"])
        if br and br != run:
            out["base"] = {"model": base, "run": br, "rows": v.rows(br)}
            # The interval as items arrived: how the evidence narrowed over the run.
            m = measure_of(v.s)
            brows = {str(x["id"]): x for x in v.rows(br)}
            seq, path = [], []
            for x in rows:
                if str(x["id"]) in brows:
                    seq.append(x)
                    if len(seq) % max(1, len(rows) // 60) == 0 or len(seq) == len(rows):
                        c = stats.paired(list(brows.values()), seq, binary=m["scale"] == "binary",
                                         higher_better=m["direction"] == "max")
                        path.append({"n": c["n"], "delta": c["delta"], "lo": c["lo"], "hi": c["hi"]})
            out["funnel"] = path
    return out


def set_detail(p: Project, key: str) -> dict:
    v = Views(p)
    st = v.s["sets"][key]
    ids = set(st["ids"])
    overlaps = []
    for k, o in v.s["sets"].items():
        if k != key and o.get("dataset") == st.get("dataset"):
            n = len(ids & set(o["ids"]))
            if n:
                overlaps.append({"key": k, "name": o["name"], "role": o["role"], "shared": n, "n": o["n"]})
    users = [{"key": hk, "name": h["name"], "as": r} for hk, h in v.s["hills"].items()
             for r, ks in (("eval", h.get("eval_sets") or []), ("train", h.get("train_sets") or []),
                           ("control", [h.get("control")]), ("symptom", [h.get("symptom_set")])) if key in ks]
    runs = [{"key": rk, "candidate": r["candidate"], "created": r["created"], **stats.summarize(v.rows(rk))}
            for rk, r in v.s["runs"].items() if r["set"] == key]
    ann = [a for a in v.s["annotations"] if a.get("set") == key]
    return {**st, "overlaps": sorted(overlaps, key=lambda o: -o["shared"]), "users": users, "runs": runs, "annotations": ann}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = [unquote(x) for x in u.path.strip("/").split("/") if x]
        try:
            if not parts or parts[0] == "p" and len(parts) <= 2 and parts[0] != "api":
                return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            if parts[0] == "static":
                f = (WEB / "/".join(parts[1:])).resolve()
                if WEB.resolve() not in f.parents or not f.exists():
                    return self._send(404, {"error": "not found"})
                return self._send(200, f.read_bytes(), mimetypes.guess_type(str(f))[0] or "text/plain")
            if parts[:2] == ["api", "projects"]:
                return self._send(200, [project_card(k, v["root"]) for k, v in registry().items()
                                        if (Path(v["root"]) / ".arx2").is_dir()])
            if parts[0] == "api" and parts[1] == "p":
                key = parts[2]
                rest = parts[3:]
                p = project(key)
                if rest == ["state"]:
                    return self._send(200, cached_state(key, float(q["until"]) if q.get("until") else None))
                if rest[:1] == ["run"]:
                    return self._send(200, run_detail(p, rest[1], q.get("base")))
                if rest[:1] == ["task"]:
                    v = Views(p)
                    t = v.task_view(rest[1])
                    return self._send(200, {**t, "metrics": p.metrics(rest[1]),
                                            "children": [v.task_view(c) for c in t["children"]]})
                if rest[:1] == ["set"]:
                    return self._send(200, set_detail(p, rest[1]))
                if rest == ["check"]:
                    return self._send(200, Views(p).split_check())
                if rest == ["cards"]:
                    return self._send(200, learner.memory(Views(p), p.learner_events()))
                if rest[:1] == ["doc"]:
                    d = p.state()["docs"][rest[1]]
                    f = p.dir / "docs" / d["file"]
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(str(f))[0] or "text/plain")
                if rest[:1] == ["answer"]:
                    f = (p.dir / "answers" / rest[1]).resolve()
                    if f.parent != (p.dir / "answers").resolve() or not f.exists():
                        return self._send(404, {"error": "not found"})
                    if f.suffix in (".html", ".htm"):
                        return self._send(200, asks.themed(f.read_text()), "text/html; charset=utf-8")
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(str(f))[0] or "text/plain")
                if rest == ["events"]:
                    return self._stream(p)
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(404, {"error": f"unknown {e}"})

    def _stream(self, p: Project):
        """Server-sent events: one `change` message whenever the ledger moves."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last = None
        try:
            while True:
                m = p.mtime()
                if m != last:
                    self.wfile.write(f"event: change\ndata: {m}\n\n".encode())
                    self.wfile.flush()
                    last = m
                else:
                    self.wfile.write(b": beat\n\n")
                    self.wfile.flush()
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        parts = [unquote(x) for x in urlparse(self.path).path.strip("/").split("/") if x]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if parts[:2] == ["api", "p"] and parts[3:] == ["learn"]:
            p = project(parts[2])
            for e in body if isinstance(body, list) else [body]:
                e.setdefault("t", time.time())
                p.learner(e)
            return self._send(200, {"ok": True})
        try:
            if parts[:2] == ["api", "p"] and parts[3:] == ["ask"]:
                ev = asks.ask(project(parts[2]), body.get("text"), body.get("kind") or "project", body.get("key") or parts[2],
                              body.get("what"), route=body.get("route") or "", loc=body.get("loc") or "")
                return self._send(200, {"key": ev["key"]})
            if parts[:2] == ["api", "p"] and parts[3:] == ["reply"]:
                ev = asks.reply(project(parts[2]), body.get("ask"), body.get("text"))
                return self._send(200, {"key": ev["key"]})
            if parts[:2] == ["api", "p"] and parts[3:] == ["save"]:
                ev = asks.save(project(parts[2]), body.get("ask"), body.get("as"), body.get("name") or "")
                return self._send(200, {"key": ev["key"]})
        except LedgerError as e:
            return self._send(400, {"error": str(e), "fix": e.fix})
        except KeyError as e:
            return self._send(404, {"error": f"unknown {e}"})
        return self._send(404, {"error": "not found"})


def serve(port: int = 8790, host: str = "127.0.0.1"):
    srv = ThreadingHTTPServer((host, port), H)
    srv.daemon_threads = True
    print(f"arx2 dashboard: http://{host}:{port}/", flush=True)
    srv.serve_forever()
