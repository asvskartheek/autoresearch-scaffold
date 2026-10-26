"""Loopback-only dashboard server. Serves dashboard.html and aggregate JSON computed from `.research/`."""
from __future__ import annotations

import gzip, json, mimetypes, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import papers, projects
from .core import Project, paired, per_id

HTML = Path(__file__).with_name("dashboard.html")
PAPER = Path(__file__).with_name("paper.html")
UI = Path(__file__).with_name("ui.css")


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
    with p.snapshot():
        return _state(p)


_SUMMARY_KEEP = (int, float, bool, type(None))


def _slim(t: dict) -> dict:
    """List views need a task's status, numbers and a line of text; the full record loads with /api/task/<id>."""
    t = {k: v for k, v in t.items() if k not in ("command", "links", "host", "pid", "env", "manifest")}
    if isinstance(t.get("summary"), dict):
        t["summary"] = {k: v for k, v in t["summary"].items() if isinstance(v, _SUMMARY_KEEP)}
    if isinstance(t.get("description"), str) and len(t["description"]) > 280:
        t["description"] = t["description"][:277] + "..."
    return t


def _state(p: Project) -> dict:
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
                hills=p.hills(), models=models, papers=papers.papers(p), gates=gates, tasks=[_slim(t) for t in tasks], leaderboard=board,
                goals=goals(p),
                decisions=_tail(p.dir / "decisions.jsonl", 50))


def goals(p: Project) -> dict:
    out = {}
    for name in p.goals():
        try:
            out[name] = p.goal_status(name)
        except SystemExit as e:
            out[name] = dict(p.goals()[name], name=name, error=str(e))
    return out


def project_list(default: Project) -> list[dict]:
    """Every registered project with its goals, for the sidebar and the projects view. The served one comes first."""
    reg = projects.registry()
    dk = projects.key_for(default.root)
    keys = ([dk] if dk in reg else []) + [k for k in reg if k != dk]
    out = []
    for k in keys:
        try:
            q = Project(reg[k]["root"])
            ps = papers.papers(q)
            with q.snapshot():
                out.append(dict(key=k, name=q.config.get("name") or k, root=str(q.root), default=k == dk,
                                champion=q.champion(), goals=goals(q), hills=len(q.hills()),
                                open_hills=sum(1 for h in q.hills().values() if h.get("status") == "open"),
                                waiting=sum(m["waiting"] for m in ps.values()),
                                running=sum(1 for t in q.tasks() if t.get("status") in ("running", "stalled"))))
        except Exception as e:  # a broken project never takes the list down
            out.append(dict(key=k, name=k, root=reg[k]["root"], error=f"{type(e).__name__}: {e}"))
    return out


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
            if p.slice_evals(m, h[role]):
                runs[m] = p.pooled_scores(m, h[role])
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
            out["vs_champion"] = dict(model=champ, task=base["id"], runs=len(p.slice_evals(champ, t["slice"])),
                                      **paired(per_id(rows), p.pooled_scores(champ, t["slice"]), 1 if p.config.get("higher_is_better", True) else -1))
    return out


LOCAL = ("127.0.0.1", "localhost", "::1")
HUMAN_KINDS = ("comment", "reply", "resolve", "reopen", "edit", "delete")


def human_event(p: Project, name: str, kind: str, d: dict) -> dict | None:
    """One event from the reader. People never post as the agent; ids they point at must exist in that paper."""
    author = str(d.get("author") or "").strip()[:40] or "Reviewer"
    if author.lower() in ("agent", "claude", "arx"):  # names the agent signs with; a person never posts as it
        return None
    body = str(d.get("body") or "").strip()[:4000]
    log = {e["id"]: e for e in papers.thread(p, name)}
    ids = set(log)
    if kind == "comment":
        a = d.get("anchor") if isinstance(d.get("anchor"), dict) else None
        anchor = {k: str(a[k])[:600] for k in ("block", "quote", "prefix", "suffix") if a and a.get(k)} or None
        return papers.post(p, name, "comment", body=body, anchor=anchor, author=author) if body and anchor else None
    ref = str(d.get("parent" if kind in ("reply", "resolve", "reopen") else "target") or "")
    if ref not in ids or (kind in ("reply", "edit") and not body):
        return None
    if kind == "reply":
        return papers.post(p, name, "reply", parent=ref, body=body, author=author)
    if kind in ("resolve", "reopen"):
        return papers.post(p, name, kind, parent=ref, author=author)
    t = log[ref]  # edit / delete: only your own message, never the agent's
    if t["kind"] not in ("comment", "reply") or t.get("agent") or (t.get("author") or "") != author:
        return None
    return papers.post(p, name, kind, target=ref, body=body or None, author=author)


def serve(port: int = 8890, root=None):
    home = Project(root)
    try:
        projects.register(home.root)
    except OSError:
        pass  # a read-only home: the served project still works at /
    cache: dict[str, Project] = {}

    def pick(path: str) -> tuple[Project, str]:
        """`/p/<key>/rest` serves a registered project; anything else serves the one this server started in."""
        parts = path.split("/", 3)
        if len(parts) >= 3 and parts[1] == "p" and parts[2]:
            key = unquote(parts[2])
            r = projects.root(key)  # KeyError for anything not in the registry: never an arbitrary path
            if key not in cache or cache[key].root != r:
                cache[key] = Project(r)
            return cache[key], "/" + (parts[3] if len(parts) > 3 else "")
        return home, path

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if len(body) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                body = gzip.compress(body, compresslevel=5)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _local(self) -> bool:
            # loopback only: a DNS-rebound page carries a foreign Host; a cross-site POST carries a foreign Origin
            host = urlsplit("//" + (self.headers.get("Host") or "")).hostname
            origin = self.headers.get("Origin")
            return host in LOCAL and (not origin or urlsplit(origin).hostname in LOCAL)

        def do_GET(self):
            path = self.path.split("?")[0]
            if not self._local():
                return self._send(403, b'{"error":"not local"}', "application/json")
            if path.startswith("/p/") and path.count("/") == 2:  # /p/<key> -> /p/<key>/ so relative fetches resolve
                self.send_response(302); self.send_header("Location", path + "/"); self.end_headers(); return
            try:
                full = path
                p, path = pick(path)
                base = full[:len(full) - len(path)]  # "/p/<key>" or ""
                if path == "/api/projects":
                    return self._send(200, json.dumps(project_list(home), default=str).encode(), "application/json")
                if path == "/ui.css":
                    return self._send(200, UI.read_bytes(), "text/css; charset=utf-8")
                if path.rstrip("/") == "/papers":  # the list of papers is a dashboard view
                    self.send_response(302); self.send_header("Location", base + "/#papers"); self.end_headers(); return
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
                if path == "/api/papers":
                    return self._send(200, json.dumps(papers.papers(p), default=str).encode(), "application/json")
                parts = [unquote(x) for x in path.strip("/").split("/")]
                if parts[0] == "papers" and len(parts) == 2:  # the reader
                    return self._send(200, PAPER.read_bytes(), "text/html; charset=utf-8")
                if parts[0] == "papers" and len(parts) == 3 and parts[2] == "raw":
                    return self._send(200, (papers.pdir(p, parts[1]) / "paper.html").read_bytes(), "text/html; charset=utf-8")
                if parts[0] == "papers" and len(parts) == 4 and parts[2] == "files":
                    f = papers.file(p, parts[1], parts[3])
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                if parts[:2] == ["api", "paper"] and len(parts) == 3:
                    body = dict(version=papers.version(p, parts[2]), meta=papers._read(papers.pdir(p, parts[2]) / "meta.json", {}),
                                threads=papers.threads(papers.thread(p, parts[2])))
                    return self._send(200, json.dumps(body, default=str).encode(), "application/json")
            except (KeyError, SystemExit, FileNotFoundError, ValueError) as e:
                return self._send(404, json.dumps(dict(error=str(e))).encode(), "application/json")
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self._local():
                return self._send(403, b'{"error":"cross-origin"}', "application/json")
            try:
                p, path = pick(self.path.split("?")[0])
                parts = [unquote(x) for x in path.strip("/").split("/")]
                if parts[:2] == ["api", "paper"] and len(parts) == 4 and parts[3] in HUMAN_KINDS:
                    d = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                    ev = human_event(p, parts[2], parts[3], d)
                    if ev is None:
                        return self._send(400, b'{"error":"bad request"}', "application/json")
                    return self._send(200, json.dumps(ev).encode(), "application/json")
            except (KeyError, ValueError) as e:
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
