"""Loopback-only dashboard server. Serves dashboard.html and aggregate JSON computed from `.research/`."""
from __future__ import annotations

import json, os, signal, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .core import Project, paired, per_id

HTML = Path(__file__).with_name("dashboard.html")
STATIC = Path(__file__).with_name("static")
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


# ---- servers: one record per project, in the project and in a user-level index so `arx ps` can see them all

INDEX = Path.home() / ".arx" / "servers.json"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def servers() -> list[dict]:
    """Running dashboards, newest first; records whose process is gone are dropped."""
    try:
        recs = json.loads(INDEX.read_text())
    except (OSError, ValueError):
        recs = []
    live = [r for r in recs if _alive(r.get("pid", 0))]
    if len(live) != len(recs):
        INDEX.write_text(json.dumps(live))
    return sorted(live, key=lambda r: -r.get("started", 0))


def register(root: Path, port: int, pid: int) -> None:
    INDEX.parent.mkdir(exist_ok=True)
    recs = [r for r in servers() if r["root"] != str(root) and r["pid"] != pid]
    rec = dict(root=str(root), port=port, pid=pid, started=time.time())
    INDEX.write_text(json.dumps(recs + [rec]))
    (root / ".research").mkdir(exist_ok=True)
    (root / ".research" / "server.json").write_text(json.dumps(rec))


def unregister(root: Path, pid: int) -> None:
    if INDEX.exists():
        INDEX.write_text(json.dumps([r for r in servers() if r["pid"] != pid]))
    info = root / ".research" / "server.json"
    try:
        if json.loads(info.read_text()).get("pid") == pid:
            info.unlink()
    except (OSError, ValueError):
        pass


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


def _when(cr: dict) -> float | None:
    """The run's own date (imports are stamped with the import time, which says nothing about when it ran)."""
    try:
        return time.mktime(time.strptime(cr["date"], "%Y-%m-%d %H:%M"))
    except (KeyError, ValueError, TypeError):
        return None


def _runs(tasks: list[dict]) -> list[dict]:
    """Every task that carries a score, whatever its kind: complete evals and imported historical runs alike, so the
    dashboard remembers work that predates (or sits beside) the slice ladder."""
    out = []
    for t in tasks:
        sm = t.get("summary") or {}
        if not isinstance(sm.get("score"), (int, float)) or not sm.get("n"):
            continue
        cr = sm.get("catalog_record") or {}
        ds = sm.get("dataset") or (t.get("slice") or "").split("/")[0] or None
        coh = sm.get("cohort_hash") or t.get("slice_hash")
        tl = t.get("title") or ""
        if cr.get("cohort_label") and tl.endswith(" · " + cr["cohort_label"]):
            tl = tl[: -len(cr["cohort_label"]) - 3]
        out.append(dict(track=f"{ds}|{coh}", variant=tl if cr else (t.get("model") or tl), dev_label=cr.get("cohort_label"),id=t["id"], kind=t["kind"], status=t["status"], model=t.get("model"), title=t.get("title"),
                        label=cr.get("model") or t.get("model") or t["title"], cohort=cr.get("cohort_label"),
                        dataset=sm.get("dataset") or (t.get("slice") or "").split("/")[0] or None,
                        slice=sm.get("registered_slice") or t.get("slice"), n=sm["n"], score=sm["score"],
                        cost=sm.get("cost"), errors=sm.get("errors"), p50=sm.get("latency_p50"), t=_when(cr) or t.get("ended") or t.get("created"),
                        agent=cr.get("raw_agent") or t.get("agent"), evidence=sm.get("evidence"),
                        ladder=t["kind"] == "eval" and bool(t.get("complete"))))
    return sorted(out, key=lambda r: r["t"] or 0)


def _tracks(runs: list[dict], slices: dict, higher: bool = True) -> list[dict]:
    """Runs are only comparable on the same examples: group by dataset + slice hash. Each track also gets its
    frontier: the runs that beat everything before them, i.e. the champions it would have had."""
    by: dict[str, list[dict]] = {}
    for r in runs:
        by.setdefault(r["track"], []).append(r)
    out = []
    for k, rs in by.items():
        n = max(r["n"] for r in rs)
        if n < 20:
            continue
        sign, best, front = (1 if higher else -1), None, []
        for r in rs:
            if r["n"] < 20 or (higher and not r["score"]):  # a run that solved nothing leads nothing
                continue
            if best is None or sign * r["score"] > sign * best:
                front.append(dict(id=r["id"], prev=best, prev_id=front[-1]["id"] if front else None))
                best = r["score"]
        ds = rs[0]["dataset"] or "other"
        name = next((r["dev_label"] for r in rs if r.get("dev_label")), None) or (rs[0]["slice"] or "unregistered eval set").split("/")[-1]
        out.append(dict(id=k, dataset=ds, label=f"{ds} · {name}", n=n, runs=len(rs), variants=len({r['variant'] for r in rs}),
                        frontier=front, first=rs[0]["t"], last=rs[-1]["t"]))
    return sorted(out, key=lambda x: (-x["variants"], -x["runs"]))


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
    champs = p.champions()
    for c in champs:
        c.pop("gate", None)
    runs = _runs(tasks)
    tracks = _tracks(runs, slices, p.config.get("higher_is_better", True))
    hills = p.hills()
    for kind, coll in (("model", models), ("hill", hills)):
        for k, rec in coll.items():
            f = p.poster_path(kind, k)
            rec["poster"] = bool(f)
            if f:
                rec["poster_type"] = f.suffix[1:]
                rec["poster_v"] = int(f.stat().st_mtime)
                if rec["poster_type"] == "json":
                    rec["poster_spec"] = p.poster_spec(kind, k)
    return dict(config=p.config, now=time.time(), champion=champ, champions=champs,
                project=dict(name=p.config.get("name"), root=str(p.root), pid=os.getpid()), datasets=p.datasets(), slices=slices,
                hills=hills, models=models, gates=gates, tasks=tasks, runs=runs, tracks=tracks, leaderboard=board,
                decisions=_tail(p.dir / "decisions.jsonl", 50), timeline=_timeline(p, runs, tracks, champs, models))


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
    """Per-example scores on the hill's target and control slices (the slice's ids, and id -> score per model), plus the
    hill's attempts (models filed under it). Slices without evals or ids give empty runs; never raises."""
    if name not in p.hills():
        raise KeyError(name)
    out: dict = {}
    try:
        h, slices = p.hills()[name], p.slices()
        for role in ("target", "control"):
            sl = slices.get(h.get(role) or "")
            if not sl:
                continue
            runs = {}
            try:
                for m in {t["model"] for t in p.evals() if t.get("slice") == h[role]}:
                    t = p.latest_eval(m, h[role])
                    if t:
                        runs[m] = per_id(p.rows(t["id"]))
            except Exception:
                runs = {}
            out[role] = dict(slice=h[role], ids=[str(i) for i in sl.get("ids", [])], runs=runs)
        out["attempts"] = [dict(model=k, status=m.get("status"), parent=m.get("parent"), created=m.get("created"),
                                title=m.get("title"), change=m.get("change"), reason=m.get("reason"))
                           for k, m in p.models().items() if m.get("hill") == name]
    except Exception:
        pass
    return out


def _pick(rs: list[dict]) -> dict | None:
    """A model's representative run on one slice: gate-grade evals first, then the best score."""
    return max(rs, key=lambda r: (r["ladder"], r["score"], r["t"] or 0)) if rs else None


def _rv(r: dict | None) -> dict | None:
    if not r:
        return None
    return {k: r.get(k) for k in ("id", "model", "label", "variant", "score", "n", "p50", "cost", "errors", "t", "kind", "evidence",
                                   "slice", "track", "dataset", "ladder")}


def _timeline(p: Project, runs: list[dict], tracks: list[dict], champs: list[dict], models: dict) -> list[dict]:
    """Every official champion the project has had, newest first: promoted through the gate ladder (decisions.jsonl),
    the id is the model id. A run that merely beat earlier runs on one eval set is a lead (state.tracks[].frontier),
    never a champion. `prev_id`/`next_id` link the promotion order, and every id resolves in champion_detail."""
    try:
        sign = 1 if p.config.get("higher_is_better", True) else -1
        ft = p.config.get("final_target")
        ft = ft if isinstance(ft, dict) else {}
        goal = ft.get("dataset") or p.config.get("primary_dataset")
        tinfo = {t["id"]: t for t in tracks}
        by_model: dict[str, dict[str, list[dict]]] = {}
        for r in runs:
            if r.get("model"):
                by_model.setdefault(r["model"], {}).setdefault(r["track"], []).append(r)
        out = []
        for i, c in enumerate(champs):
            m = c["model"]
            prev = c.get("replaced") or (champs[i - 1]["model"] if i else None)
            mine, theirs = by_model.get(m, {}), by_model.get(prev, {}) if prev else {}
            shared = [k for k in mine if k in theirs]
            pool = shared or list(mine)
            tr = max(pool, key=lambda k: (max(r["n"] for r in mine[k]), any(r["ladder"] for r in mine[k]))) if pool else None
            cand = _pick(mine[tr]) if tr else None
            base = _pick(theirs[tr]) if tr and tr in theirs else None
            nxt = champs[i + 1] if i + 1 < len(champs) else None
            ti = tinfo.get(tr or "", {})
            out.append(dict(id=m, kind="official", model=m, label=models.get(m, {}).get("title") or m, variant=cand and cand["variant"],
                            t=c["t"], seeded=bool(c.get("seeded")), track=tr, track_label=ti.get("label") or (cand or {}).get("slice"),
                            dataset=(cand or {}).get("dataset"), goal=bool(goal) and (cand or {}).get("dataset") == goal,
                            slice=(cand or {}).get("slice"), n=(cand or {}).get("n"), score=(cand or {}).get("score"),
                            p50=(cand or {}).get("p50"), cost=(cand or {}).get("cost"), errors=(cand or {}).get("errors"),
                            run_id=(cand or {}).get("id"), base_score=(base or {}).get("score"),
                            delta=sign * (cand["score"] - base["score"]) if cand and base else None,
                            prev_id=prev, prev_label=(models.get(prev, {}).get("title") or prev) if prev else None,
                            next_id=nxt["model"] if nxt else None, held_s=(nxt["t"] - c["t"]) if nxt else None,
                            current=nxt is None, hill=models.get(m, {}).get("hill")))
        return sorted(out, key=lambda e: e["t"] or 0, reverse=True)
    except Exception:  # a ledger the dashboard cannot make sense of must not take the page down
        return []


def _notes(task: dict | None) -> dict:
    """What the run's own record says about it. The local file path in an imported record stays out."""
    sm = (task or {}).get("summary") or {}
    cr = sm.get("catalog_record") or {}
    keep = ("agent", "cohort_label", "date", "experiment_code", "scored", "correct", "latency_kind", "cost_kind", "cost_note")
    out = {k: cr[k] for k in keep if cr.get(k) is not None}
    out["notes"] = [str(x) for x in (cr.get("notes") or [])]
    out["evidence"] = cr.get("evidence") or sm.get("evidence")
    out["description"] = (task or {}).get("description")
    out["imported"] = bool(cr)
    return out


def _paired_runs(p: Project, cand_id: str | None, base_id: str | None) -> dict | None:
    """Per-example paired comparison when both runs wrote rows; None means only aggregates exist."""
    if not cand_id or not base_id or cand_id == base_id:
        return None
    try:
        a, b = per_id(p.rows(cand_id)), per_id(p.rows(base_id))
        if not a or not b:
            return None
        r = paired(a, b, 1 if p.config.get("higher_is_better", True) else -1)
        return r if r["n"] else None
    except Exception:
        return None


def goals(p: Project) -> list[dict]:
    """Every research project with a running dashboard: one goal each, this one first."""
    out = []
    for r in servers():
        root = Path(r["root"])
        try:
            cfg = json.loads((root / "research.json").read_text())
            models = json.loads((root / ".research" / "models.json").read_text()) if (root / ".research" / "models.json").exists() else {}
        except (OSError, ValueError):
            continue
        ft = cfg.get("final_target")
        champ = next((m for m in models.values() if m.get("status") == "champion"), None)
        out.append(dict(name=cfg.get("name") or root.name, goal=cfg.get("solver_goal") or (ft if isinstance(ft, str) else None),
                        port=r["port"], root=str(root), models=len(models), current=root == p.root,
                        champion=(champ or {}).get("title"), started=r.get("started")))
    return sorted(out, key=lambda g: (not g["current"], g["name"]))


def champion_detail(p: Project, ident: str) -> dict:
    """One official champion's page. `ident` is a model id promoted through the gate (or the id of one of its runs).
    Never raises on missing data; an id that never held the title raises KeyError (404)."""
    models, champs, tasks = p.models(), p.champions(), p.tasks()
    runs = _runs(tasks)
    tracks = _tracks(runs, p.slices(), p.config.get("higher_is_better", True))
    tl = _timeline(p, runs, tracks, champs, models)
    by_id = {r["id"]: r for r in runs}
    e = next((x for x in tl if x["id"] == ident), None)
    if not e:
        r = by_id.get(ident)
        e = next((x for x in tl if x["id"] == (r or {}).get("model")), None)
    if not e:
        raise KeyError(ident)
    tmap = {t["id"]: t for t in tasks}
    ent = {x["id"]: x for x in tl}
    cand, base = by_id.get(e["run_id"] or ""), None
    prev = ent.get(e["prev_id"] or "")
    if prev:
        base = by_id.get(prev["run_id"] or "")
        if prev.get("track") != e["track"]:  # no run of the previous champion on this track: nothing to compare on
            base = next(iter(sorted((r for r in runs if r["track"] == e["track"] and r.get("model") == e["prev_id"]), key=lambda r: -r["score"])), None)
    if not prev and e["prev_id"]:
        prev = dict(id=e["prev_id"], label=e["prev_label"])
    m = models.get(e["model"] or "") or {}
    c = next((x for x in champs if x["model"] == e["id"]), None)
    vs = []
    if e["kind"] == "official" and e["prev_id"]:  # the gate's own slices, paired where both sides wrote rows
        sign = 1 if p.config.get("higher_is_better", True) else -1
        for sl, sv in p.slices().items():
            ce, be = p.latest_eval(e["id"], sl), p.latest_eval(e["prev_id"], sl)
            if not ce:
                continue
            row = dict(slice=sl, kind=sv.get("kind"), n_slice=sv.get("n"), cand_task=ce["id"], cand=ce.get("summary", {}).get("score"))
            if be:
                row |= dict(base_task=be["id"], **paired(per_id(p.rows(ce["id"])), per_id(p.rows(be["id"])), sign))
            vs.append(row)
    pr = _paired_runs(p, cand and cand["id"], base and base["id"])
    nx = ent.get(e["next_id"] or "")
    return dict(
        id=e["id"], kind=e["kind"], entry=e, model=e["model"], record=m, champion=c or {},
        current=e["kind"] == "official" and p.champion() == e["id"],
        previous=e["prev_id"], previous_entry=prev, next_entry=nx, previous_record=models.get(e["prev_id"] or ""),
        hill=p.hills().get(m.get("hill") or ""), hill_name=m.get("hill"), vs_previous=vs, gate=(c or {}).get("gate"),
        cand=_rv(cand), base=_rv(base), paired=pr, aggregates_only=pr is None,
        notes=_notes(tmap.get(cand["id"]) if cand else None), base_notes=_notes(tmap.get(base["id"])) if base else None,
        decisions=[d for d in _tail(p.dir / "decisions.jsonl", 400) if d.get("model") == e["model"]][-10:],
        tasks=[dict(id=t["id"], title=t["title"], status=t["status"], kind=t["kind"], slice=t.get("slice"),
                    score=(t.get("summary") or {}).get("score")) for t in tasks if e["model"] and t.get("model") == e["model"]][:40])


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


class _Server(ThreadingHTTPServer):
    request_queue_size = 128  # a page load fires a dozen requests at once; the default backlog of 5 resets them
    daemon_threads = True


def _fingerprint(p: Project) -> tuple:
    """Changes whenever anything state() reads changes, so a repeated poll costs a few stats, not a rebuild."""
    out = []
    for f in sorted(p.dir.glob("*.json*")) + sorted((p.dir / "posters").glob("*")) + sorted((p.dir / "tasks").glob("*/task.json")):
        try:
            out.append((f.name, f.parent.name, f.stat().st_mtime_ns))
        except OSError:
            pass
    return (tuple(out), int(time.time() // 30))  # time moves stall detection and ETAs, so re-render at least every 30 s


def serve(port: int = 8890, root=None):
    p = Project(root)
    cache: dict = {"fp": None, "body": b""}
    lock = threading.Lock()

    def state_body() -> bytes:
        with lock:
            fp = _fingerprint(p)
            if fp != cache["fp"]:
                cache.update(fp=fp, body=json.dumps(state(p), default=str).encode())
            return cache["body"]
    seen = {"t": time.time()}  # last request; an open dashboard tab polls, so a quiet server has no viewer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype, poster=False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if poster:  # a poster is untrusted markup: no network, no frames, scripts only in html widgets
                scripts = " script-src 'unsafe-inline';" if ctype.startswith("text/html") else ""
                self.send_header("Content-Security-Policy", f"default-src 'none'; img-src data:; style-src 'unsafe-inline';{scripts}")
                self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            seen["t"] = time.time()
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
                if path.startswith("/static/") and (STATIC / path[8:]).is_file() and "/" not in path[8:]:
                    f = STATIC / path[8:]
                    return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
                if path.startswith("/api/poster/"):
                    parts = unquote(path[len("/api/poster/"):]).split("/")
                    f = p.poster_path(parts[0], parts[1]) if len(parts) == 2 and parts[0] in ("model", "hill") and parts[1] else None
                    if f is None:
                        return self._send(404, b"no poster", "text/plain")
                    return self._send(200, f.read_bytes(), Project.POSTER_TYPES[f.suffix[1:]], poster=True)
                if path == "/api/state":
                    return self._send(200, state_body(), "application/json")
                if path.startswith("/api/task/"):
                    return self._send(200, json.dumps(task_detail(p, path.rsplit("/", 1)[1]), default=str).encode(), "application/json")
                if path.startswith("/api/hill/"):
                    return self._send(200, json.dumps(hill_detail(p, unquote(path.rsplit("/", 1)[1])), default=str).encode(), "application/json")
                if path == "/api/goals":
                    return self._send(200, json.dumps(goals(p), default=str).encode(), "application/json")
                if path == "/api/ping":
                    return self._send(200, json.dumps(dict(root=str(p.root), name=p.config.get("name"), pid=os.getpid())).encode(), "application/json")
                if path.startswith("/api/champion/"):
                    return self._send(200, json.dumps(champion_detail(p, unquote(path.rsplit("/", 1)[1])), default=str).encode(), "application/json")
                if path.startswith("/api/gate/"):
                    return self._send(200, json.dumps(p.gate(path.rsplit("/", 1)[1]), default=str).encode(), "application/json")
            except (KeyError, SystemExit) as e:
                return self._send(404, json.dumps(dict(error=str(e))).encode(), "application/json")
            self._send(404, b"not found", "text/plain")

    for port_try in range(port, port + 20):
        try:
            srv = _Server(("127.0.0.1", port_try), H)
            break
        except OSError:
            continue
    print(f"dashboard: http://127.0.0.1:{port_try}", flush=True)
    register(p.root, port_try, os.getpid())
    idle_s = 60 * float(p.config.get("dashboard_idle_minutes", 30))

    def watch():
        """Shut down once nobody has looked for `dashboard_idle_minutes` and no task is running."""
        while True:
            time.sleep(15)
            if idle_s and time.time() - seen["t"] > idle_s and not any(t["status"] in ("running", "stalled") for t in p.tasks()):
                print("idle; shutting down", flush=True)
                srv.shutdown()
                return

    threading.Thread(target=watch, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown).start())
    try:
        srv.serve_forever()
    finally:
        unregister(p.root, os.getpid())
