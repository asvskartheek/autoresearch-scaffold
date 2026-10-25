"""Loopback-only dashboard server. Serves dashboard.html and aggregate JSON computed from `.research/`."""
from __future__ import annotations

import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .core import Project, paired, per_id

HTML = Path(__file__).with_name("dashboard.html")


def _downsample(points: list[dict], cap: int = 600) -> list[dict]:
    if len(points) <= cap:
        return points
    stride = len(points) / cap
    return [points[int(i * stride)] for i in range(cap)] + [points[-1]]


def eta(p: Project, t: dict) -> dict | None:
    """Rate over the last 15 minutes of progress (falls back to the whole run); None until there is a rate."""
    pr = t.get("progress") or {}
    done, total = pr.get("done") or 0, pr.get("total")
    if not total or t.get("status") not in ("running", "stalled") or done >= total:
        return None
    pts = [tuple(x) for x in pr.get("hist", [])]
    if len(pts) < 2 and t.get("kind") == "eval":
        pts = [(m["t"], m["step"]) for m in p.metrics(t["id"]) if "t" in m and "step" in m]
    if len(pts) < 2:
        pts = [(t["created"], 0), (time.time(), done)]
    recent = [x for x in pts if x[0] >= pts[-1][0] - 900]
    a, b = (recent[0] if len(recent) >= 2 and recent[-1][1] > recent[0][1] else pts[0]), pts[-1]
    rate = (b[1] - a[1]) / max(b[0] - a[0], 1e-6)
    if rate <= 0:
        return None
    left = (total - done) / rate
    return dict(per_min=rate * 60, eta_s=left, finish_at=time.time() + left)


def infer_parents(tasks: list[dict]) -> None:
    """Tasks logged before `parent` existed: nest each under the newest non-eval task of the same process that was
    running when it started (a loop script and the evals it launched share a pid)."""
    for t in tasks:
        if "parent" in t or not t.get("pid"):
            continue
        hosts = [o for o in tasks if o is not t and o.get("kind") != "eval" and o.get("pid") == t["pid"]
                 and o.get("host") == t.get("host") and o.get("command") == t.get("command")
                 and o["created"] < t["created"] <= (o.get("ended") or float("inf"))]
        t["parent"] = max(hosts, key=lambda o: o["created"])["id"] if hosts else None


def state(p: Project) -> dict:
    slices = {k: {kk: vv for kk, vv in v.items() if kk != "ids"} | {"name": k} for k, v in p.slices().items()}
    models, tasks = p.models(), p.tasks()
    champ = p.champion()
    board, newest = {}, {}
    for t in p.evals():
        cur = board.setdefault(t["slice"], {}).get(t["model"])
        if t.get("slice_hash") == slices.get(t["slice"], {}).get("hash") and (not cur or t["ended"] > cur["ended"]):
            board[t["slice"]][t["model"]] = dict(task=t["id"], ended=t["ended"], **t.get("summary", {}))
            if t["ended"] > newest.get(t["slice"], (0, 0))[0]:
                newest[t["slice"]] = (t["ended"], t["id"])
    for name, sl in slices.items():  # slices frozen before `scale` existed: read it off the scores
        if not sl.get("scale") and name in newest:
            vals = {r.get("score") for r in p.rows(newest[name][1]) if not r.get("error")}
            sl["scale"] = "binary" if vals <= {0, 1} else "continuous"
    gates = {}
    for name, m in models.items():
        if m.get("status") in ("candidate", "champion"):
            try:
                gates[name] = p.gate(name)
            except SystemExit as e:
                gates[name] = dict(error=str(e))
    infer_parents(tasks)
    for t in tasks:
        ev = p.events(t["id"])
        t["note"] = ev[-1] if ev else None
        series = p.metrics(t["id"])[-40:]
        keys = [k for k in (t.get("last") or {}) if isinstance(t["last"][k], (int, float))]
        t["eta"] = eta(p, t)
        t["spark"] = {"key": keys[0], "y": [s.get(keys[0]) for s in series if isinstance(s.get(keys[0]), (int, float))]} if keys else None
    return dict(config=p.config, now=time.time(), champion=champ, datasets=p.datasets(), slices=slices,
                hills=p.hills(), models=models, gates=gates, tasks=tasks, leaderboard=board,
                decisions=_tail(p.dir / "decisions.jsonl", 50))


def _tail(path: Path, n: int) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines()[-n:]:
        try:
            d = json.loads(line)
            d.pop("gate", None)
            out.append(d)
        except ValueError:
            pass
    return out


def hill_detail(p: Project, name: str) -> dict:
    """Per-example scores on the hill's target and control slices: the slice's ids, and id -> score per model."""
    h, slices = p.hills()[name], p.slices()
    out = {}
    for role in ("target", "control"):
        sl = slices.get(h.get(role) or "")
        if not sl:
            continue
        runs = {}
        for m in {t["model"] for t in p.evals() if t.get("slice") == h[role]}:
            t = p.latest_eval(m, h[role])
            if t:
                runs[m] = per_id(p.rows(t["id"]))
        out[role] = dict(slice=h[role], ids=[str(i) for i in sl.get("ids", [])], runs=runs)
    return out


def task_detail(p: Project, tid: str) -> dict:
    tasks = p.tasks()
    infer_parents(tasks)
    t = next((x for x in tasks if x["id"] == tid), None) or p.task(tid)
    t["eta"] = eta(p, t)
    out = dict(task=t, metrics=_downsample(p.metrics(tid)), events=p.events(tid)[-300:])
    if t.get("kind") == "eval":
        rows = p.rows(tid)
        out["rows"] = [dict(id=r["id"], score=r.get("score"), error=bool(r.get("error")), latency_s=r.get("latency_s"), cost=r.get("cost")) for r in rows]
        champ = p.champion()
        base = p.latest_eval(champ, t["slice"]) if champ and champ != t.get("model") else None
        if base:
            out["vs_champion"] = dict(model=champ, task=base["id"], **paired(per_id(rows), per_id(p.rows(base["id"])), 1 if p.config.get("higher_is_better", True) else -1))
    return out


def serve(port: int = 8890, root=None):
    p = Project(root)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
                if path == "/api/state":
                    return self._send(200, json.dumps(state(p), default=str).encode(), "application/json")
                if path.startswith("/api/task/"):
                    return self._send(200, json.dumps(task_detail(p, path.rsplit("/", 1)[1]), default=str).encode(), "application/json")
                if path.startswith("/api/hill/"):
                    return self._send(200, json.dumps(hill_detail(p, unquote(path.rsplit("/", 1)[1])), default=str).encode(), "application/json")
                if path.startswith("/api/gate/"):
                    return self._send(200, json.dumps(p.gate(path.rsplit("/", 1)[1]), default=str).encode(), "application/json")
            except (KeyError, SystemExit) as e:
                return self._send(404, json.dumps(dict(error=str(e))).encode(), "application/json")
            self._send(404, b"not found", "text/plain")

    for port_try in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port_try), H)
            break
        except OSError:
            continue
    print(f"dashboard: http://127.0.0.1:{port_try}")
    srv.serve_forever()
