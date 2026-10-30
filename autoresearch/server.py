"""Loopback-only dashboard server. Serves web/ and aggregate JSON computed from `.research/`."""
from __future__ import annotations

import ast, copy, gzip, hashlib, json, mimetypes, os, re, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from . import features, papers, people, projects, share
from .core import Project, _read, contract_of, paired, per_id, same_contract, summarize
from .readable import readable

WEB = Path(__file__).with_name("web")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
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
        out = _state(p)
        for fn in features.STATE:
            try:
                fn(p, out)
            except Exception as e:  # a broken feature never takes the dashboard down
                out.setdefault("feature_errors", []).append(f"{fn.__module__}: {e}")
        return out


def _feature(routes, p, path, arg):
    """The first registered feature route whose prefix matches: (status, body bytes, content type) or None."""
    for prefix, fn in routes:
        if path.startswith(prefix):
            r = fn(p, path, arg)
            code, payload = r[0], r[1]
            if isinstance(payload, (bytes, bytearray)):
                return (code, bytes(payload), (r[2] if len(r) > 2 else "application/octet-stream")) + tuple(r[3:4])
            return code, json.dumps(payload, default=str).encode(), "application/json"
    return None


_SUMMARY_KEEP = (int, float, bool, type(None))


def _slim(t: dict) -> dict:
    """List views need a task's status, numbers and a line of text; the full record loads with /api/task/<id>."""
    t = {k: v for k, v in t.items() if k not in ("command", "links", "host", "pid", "env", "manifest")}
    if isinstance(t.get("summary"), dict):
        report = t["summary"].get("benchmark_report")
        conclusion = report.get("conclusion") if isinstance(report, dict) else None
        throughput = t["summary"].get("throughput")
        if isinstance(conclusion, str) and conclusion:
            t["result_summary"] = conclusion[:600]
        elif isinstance(throughput, list) and throughput:
            t["result_summary"] = f"{len(throughput)} measured throughput rows"
        t["summary"] = {k: v for k, v in t["summary"].items() if isinstance(v, _SUMMARY_KEEP)}
    if isinstance(t.get("description"), str) and len(t["description"]) > 280:
        t["description"] = t["description"][:277] + "..."
    return t


WINDOW = 80  # finished tasks /api/state sends; the archive and history views load the rest from /api/tasks
_MEMO: dict = {}  # (kind, root) -> (fingerprint, value): gates, goals and hill strips only change with the ledger


def _fp(p: Project) -> tuple:
    """Changes whenever anything a gate, goal or hill strip reads changes: research.json, the ledger's json files
    and the set of finished evals (ids, end times, supersessions)."""
    fs = []
    for f in (p.root / "research.json", *sorted(p.dir.glob("*.json"))):
        try:
            fs.append((f.name, f.stat().st_mtime_ns))
        except OSError:
            pass
    return tuple(fs), tuple(sorted((t["id"], t.get("ended"), t.get("superseded_by")) for t in p.evals()))


def _memo(kind: str, p: Project, fp, fn):
    k = (kind, str(p.root))
    hit = _MEMO.get(k)
    if not hit or hit[0] != fp:
        hit = _MEMO[k] = (fp, fn())
    return copy.deepcopy(hit[1])


def _gates(p: Project, models: dict) -> dict:
    gates = {}
    for name, m in models.items():
        if m.get("status") in ("candidate", "champion"):
            try:
                gates[name] = p.gate(name)
            except SystemExit as e:
                gates[name] = dict(error=str(e))
    return gates


def _enrich(p: Project, t: dict) -> dict:
    """A list row: its latest note, a readable description, an ETA and a sparkline of its first metric."""
    ev = p.events(t["id"])
    t["note"] = ev[-1] | {"text": readable(ev[-1].get("msg"))} if ev else None
    if t.get("description"):
        t["description"] = readable(t["description"])
    if t.get("title"):
        t["title"] = readable(t["title"])
    series = p.metrics(t["id"])[-40:]
    keys = [k for k in (t.get("last") or {}) if isinstance(t["last"][k], (int, float))]
    t["eta"] = eta(p, t)
    t["spark"] = {"key": keys[0], "y": [s.get(keys[0]) for s in series if isinstance(s.get(keys[0]), (int, float))]} if keys else None
    return _slim(t)


def _rev(tasks: list[dict]) -> str:
    """Changes when a task starts, ends or is superseded: the client then refetches the full list."""
    sig = sorted((t["id"], t.get("status"), t.get("ended"), t.get("superseded_by")) for t in tasks
                 if t.get("status") not in ("running", "stalled"))
    return hashlib.md5(repr((len(tasks), sig)).encode()).hexdigest()[:12]


def window(tasks: list[dict], keep=()) -> list[dict]:
    """What the 4 s poll needs: live tasks and their children, the newest finished ones, every task in `keep`
    (goal evidence) and the parents of all of those. Views only link leaderboard runs by id."""
    live = {t["id"] for t in tasks if t.get("status") in ("running", "stalled")}
    done = sorted((t for t in tasks if t["id"] not in live), key=lambda t: t.get("ended") or t.get("updated") or 0, reverse=True)
    ids = live | {t["id"] for t in done[:WINDOW]} | set(keep) | {t["id"] for t in tasks if t.get("parent") in live}
    by = {t["id"]: t for t in tasks}
    for i in list(ids):
        x, hops = by.get(i), 0
        while x and x.get("parent") and x["parent"] not in ids and hops < 50:
            ids.add(x["parent"])
            x, hops = by.get(x["parent"]), hops + 1
    return [t for t in tasks if t["id"] in ids]


def all_tasks(p: Project) -> dict:
    """Every task as a list row, for the archive and the history views."""
    with p.snapshot():
        tasks = p.tasks()
        infer_parents(tasks)
        return dict(rev=_rev(tasks), tasks=[_enrich(p, t) for t in tasks])


def _clean_reason(s: str) -> str:
    """A reject reason reads as prose: an absolute path becomes its file name, a dumped dict a few key=value pairs."""
    s = re.sub(r"(?<![\w.])(?:~|/(?:Users|home|private|tmp|var|opt|mnt|data|workspace|root))(?:/[^\s,;:'\")\]]+)+",
               lambda m: m.group(0).rstrip(".").rsplit("/", 1)[-1] + ("." if m.group(0).endswith(".") else ""), s)

    def short(m):
        try:
            d = ast.literal_eval(m.group(0))
        except (ValueError, SyntaxError):
            return m.group(0)
        if not isinstance(d, dict):
            return m.group(0)
        kv = [f"{k} {(f'{v:.3g}' if isinstance(v, float) else v)}" for k, v in d.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool)][:4]
        return "(" + ", ".join(kv) + ")" if kv else ""
    return re.sub(r"\{[^{}]{0,2000}\}", short, s)


def _model_row(m: dict) -> dict:
    out = m | {f: readable(m[f]) for f in ("change", "title") if isinstance(m.get(f), str)}
    if isinstance(m.get("reason"), str):
        out["reason"] = readable(_clean_reason(m["reason"]))
    return out


def _state(p: Project) -> dict:
    slices = {k: {kk: vv for kk, vv in v.items() if kk != "ids"} | {"name": k} for k, v in p.slices().items()}
    models, tasks = p.models(), p.tasks()
    champ = p.champion()
    board, newest = {}, {}
    for sl, model in {(t["slice"], t["model"]) for t in p.evals()}:
        runs = p.score_runs(model, sl)
        if not runs:
            continue
        latest = runs[-1]
        scores = p.pooled_scores(model, sl)
        summary = summarize([r for t in runs for r in p.rows(t["id"])], p.is_continuous(sl))
        summary.update(n=len(scores), score=sum(scores.values()) / len(scores) if scores else None)
        board.setdefault(sl, {})[model] = dict(task=latest["id"], ended=latest["ended"], runs=len(runs),
                                              baseline_contract=contract_of(latest), **summary)
        if latest["ended"] > newest.get(sl, (0, 0))[0]:
            newest[sl] = (latest["ended"], latest["id"])
    for name, sl in slices.items():  # slices frozen before `scale` existed: read it off the scores
        if not sl.get("scale") and name in newest:
            vals = {r.get("score") for r in p.rows(newest[name][1]) if not r.get("error")}
            sl["scale"] = "binary" if vals <= {0, 1} else "continuous"
    fp = _fp(p)
    gates = _memo("gates", p, fp, lambda: _gates(p, models))
    gl = _memo("goals", p, fp, lambda: goals(p))
    infer_parents(tasks)
    lift_progress(tasks)
    gates = running_next(gates, tasks, p.slices())
    win = window(tasks, {g["task"] for g in gl.values() if g.get("task")})
    return dict(config=p.config, now=time.time(), champion=champ, datasets=p.datasets(), slices=slices,
                hills=p.hills(), models={k: _model_row(m) for k, m in models.items()}, papers=papers.papers(p, with_health=True), gates=gates,
                tasks=[_enrich(p, t) for t in win], tasks_total=len(tasks), tasks_rev=_rev(tasks), leaderboard=board,
                goals=gl,
                baseline=p.baseline_plan(champ) if champ else None,
                decisions=_tail(p.dir / "decisions.jsonl", 50))


LIVE = ("running", "stalled")


def lift_progress(tasks: list[dict]) -> None:
    """An eval whose harness counts in a sub-task (e.g. "live: ..." rolling numbers) shows that count as its own; the
    sub-task is marked `detail_of` the eval so lists show the job once."""
    kids: dict = {}
    for t in tasks:
        if t.get("parent") and (t.get("progress") or {}).get("total"):
            kids.setdefault(t["parent"], []).append(t)
    for t in tasks:
        if t.get("kind") != "eval" or t["id"] not in kids:
            continue
        own = t.get("progress") or {}
        for k in kids[t["id"]]:
            kp = k["progress"]
            if (not own.get("total") or kp.get("total") == own.get("total")) and (kp.get("done") or 0) > (own.get("done") or 0):
                t["progress"], t["progress_from"] = dict(kp), k["id"]
                own = t["progress"]
            k["detail_of"] = t["id"]


def running_next(gates: dict, tasks: list[dict], slices: dict | None = None) -> dict:
    """Each gate's next run that is already running carries `running` (its task id), so no view says "not run yet"
    while it runs: the same model on that slice, or on a slice holding all of its examples (a harness that runs one
    union pass and records each slice from it). The memoised gates are copied, never changed."""
    live = [t for t in tasks if t.get("kind") == "eval" and t.get("status") in LIVE and t.get("model")]
    if not live:
        return gates
    ids = lambda sl: set((slices or {}).get(sl, {}).get("ids") or [])

    def runner(n):
        for t in live:
            if t["model"] == n.get("model") and (t.get("slice") == n.get("slice") or ids(n.get("slice")) and ids(n.get("slice")) <= ids(t.get("slice"))):
                return t["id"]
        return None
    out = {}
    for name, g in gates.items():
        nx = (g or {}).get("next") if isinstance(g, dict) else None
        run = [runner(n) for n in nx] if nx else []
        if any(run):
            g = dict(g, next=[dict(n, running=r) if r else n for n, r in zip(nx, run)])
        out[name] = g
    return out


def goals(p: Project) -> dict:
    out = {}
    for name in p.goals():
        try:
            out[name] = p.goal_status(name)
        except SystemExit as e:
            out[name] = dict(p.goals()[name], name=name, error=str(e))
    return out


DEAD_S = 86400  # stalled longer than a day: dead, not running


def _light_tasks(q: Project) -> list[dict]:
    """status, heartbeat, parent and kind of every task, read straight from task.json (parse-cached by mtime)."""
    out = []
    try:
        dirs = list(os.scandir(q.dir / "tasks"))
    except OSError:
        return out
    for d in dirs:
        t = _read(Path(d.path) / "task.json") if d.is_dir() else None
        if t:
            out.append({k: t.get(k) for k in ("id", "status", "heartbeat", "updated", "parent", "kind")})
    return out


def running_jobs(tasks: list[dict], stall_s: float, t_now: float = None) -> tuple[int, int]:
    """(running, stalled) atomic jobs: no live child, never an answer agent; a task silent for more than a day is
    dead and counts as neither."""
    t_now = t_now or time.time()
    live = [t for t in tasks if t.get("status") in ("running", "stalled")]
    for t in live:
        if t.get("status") == "running" and t_now - (t.get("heartbeat") or t.get("updated") or 0) > stall_s:
            t["status"] = "stalled"
    parents = {t.get("parent") for t in live if t.get("parent")}
    jobs = [t for t in live if t["id"] not in parents and t.get("kind") != "answer"]
    run = sum(1 for t in jobs if t["status"] == "running")
    stalled = sum(1 for t in jobs if t["status"] == "stalled" and t_now - (t.get("heartbeat") or t.get("updated") or 0) <= DEAD_S)
    return run, stalled


_PAPERS: dict = {}  # root -> (thread mtimes, waiting count)


def _waiting(q: Project) -> int:
    fp = tuple((f.parent.name, f.stat().st_mtime_ns) for f in sorted((q.dir / "papers").glob("*/thread.jsonl")))
    hit = _PAPERS.get(str(q.root))
    if not hit or hit[0] != fp:
        hit = _PAPERS[str(q.root)] = (fp, sum(m["waiting"] for m in papers.papers(q).values()))
    return hit[1]


def _asks(q: Project) -> int:
    """Questions that wait on a person (needs_human, still open)."""
    qs = _read(q.dir / "questions.json", {}) or {}
    return sum(1 for n in qs.values() if isinstance(n, dict) and n.get("needs_human") and n.get("status") in ("open", "agent"))


def no_project_page(key: str, remote: bool) -> bytes:
    """A /p/<key>/ link to a project this dashboard does not serve (renamed, removed, a typo): say so and link the
    registered ones, instead of a bare JSON error. Someone on another machine gets only the way back."""
    import html
    links = "" if remote else "".join(
        f'<li><a href="/p/{quote(k)}/">{html.escape(r.get("name") or k)}</a> <code>{html.escape(k)}</code></li>'
        for k, r in ((k, _name_of(v)) for k, v in projects.registry().items()))
    return (f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>No project here · arx</title><link rel="stylesheet" href="/ui-base.css">'
            "<script>try{var t=localStorage.getItem('arx-theme');if(t==='dark'||!t&&matchMedia('(prefers-color-scheme: dark)').matches)"
            "document.documentElement.dataset.theme='dark'}catch(e){}</script><style>a{color:var(--ring)}</style>"
            f'<body style="max-width:560px;margin:48px auto;padding:0 16px">'
            f'<h1>No project <code>{html.escape(key)}</code></h1>'
            f'<p>This dashboard does not serve a project with that key. <code>arx projects</code> lists them.</p>'
            f'<ul>{links}</ul><p><a href="/">Open the dashboard</a></p>').encode()


def _name_of(entry: dict) -> dict:
    try:
        return {"name": _read(Path(entry["root"]) / "research.json", {}).get("name")}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def project_list(default: Project) -> list[dict]:
    """Every registered project for the sidebar: name, running and stalled jobs, comments and questions waiting, and
    each goal's status as recorded. Cheap on purpose (no gates or goal scoring): it is fetched on every page load. The served one comes first."""
    reg = projects.registry()
    dk = projects.key_for(default.root)
    keys = ([dk] if dk in reg else []) + [k for k in reg if k != dk]
    out = []
    for k in keys:
        try:
            q = Project(reg[k]["root"])
            run, stalled = running_jobs(_light_tasks(q), q._stall())
            out.append(dict(key=k, name=q.config.get("name") or k, root=str(q.root), default=k == dk,
                            running=run, stalled=stalled, waiting=_waiting(q), asks=_asks(q),
                            goals={g: dict(status=v.get("status"), title=v.get("title")) for g, v in q.goals().items()}))
        except Exception as e:  # a broken project never takes the list down
            out.append(dict(key=k, name=k, root=reg[k]["root"], error=f"{type(e).__name__}: {e}"))
    return out


_CHECK = ("slice", "rule", "state", "threshold", "noisy", "n", "delta", "lo", "hi", "wins", "losses", "cand", "base",
          "cand_runs", "base_runs", "cand_task", "base_task", "baseline_contract", "relative")


def _slim_gate(g) -> dict | None:
    """A promote record's gate: each rung's checks with their paired numbers, how many runs were pooled on each side
    and the run tasks, so the model page can mark pooled runs and link the evidence."""
    if not isinstance(g, dict):
        return None
    return dict(rungs=[dict(rung=r.get("rung"), status=r.get("status"),
                            checks=[{k: c.get(k) for k in _CHECK if k in c} for c in r.get("checks") or [] if isinstance(c, dict)])
                       for r in g.get("rungs") or [] if isinstance(r, dict)])


def _tail(path: Path, n: int) -> list:
    """The last n decisions, plus every older promote: the champion page shows its promotion evidence whatever its
    age. A promote keeps a slim gate; other decisions drop theirs."""
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    out = []
    for i, line in enumerate(lines):
        if i < len(lines) - n and '"promote"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if i < len(lines) - n and d.get("kind") != "promote":
            continue
        g = d.pop("gate", None)
        if d.get("kind") == "promote":
            d["gate"] = _slim_gate(g)
        out.append(d)
    return out


def hill_detail(p: Project, name: str) -> dict:
    """Per-example scores on the hill's target and control slices: the slice's ids, and id -> score per model.
    Memoised on the ledger: the first open reads every run's rows, later ones reuse them until an eval lands."""
    with p.snapshot():
        return _memo("hill:" + name, p, _fp(p), lambda: _hill_detail(p, name))


def _hill_detail(p: Project, name: str) -> dict:
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
    if t.get("description"):
        t["description"] = readable(t["description"])
    out = dict(task=t, metrics=_downsample(p.metrics(tid)), events=[e | {"text": readable(e.get("msg"))} for e in p.events(tid)[-300:]])
    if t.get("kind") == "eval":
        rows = p.rows(tid)
        out["rows"] = [dict(id=r["id"], score=r.get("score"), error=bool(r.get("error")), latency_s=r.get("latency_s"), cost=r.get("cost")) for r in rows]
        champ = p.champion()
        bases = same_contract(p.slice_evals(champ, t["slice"]), t) if champ and champ != t.get("model") else []
        cont = p.is_continuous(t["slice"])
        if bases:
            out["vs_champion"] = dict(model=champ, task=bases[-1]["id"], runs=len(bases), baseline_contract=contract_of(t),
                                      **paired(per_id(rows, cont), per_id([r for b in bases for r in p.rows(b["id"])], cont),
                                               1 if p.config.get("higher_is_better", True) else -1))
    return out


LOCAL = ("127.0.0.1", "localhost", "::1")
HUMAN_KINDS = ("comment", "reply", "resolve", "reopen", "edit", "delete", "seen")


LEARNING_WRITES = ("/api/course", "/api/teach", "/api/predictions", "/api/understanding")
def guest_learning_allowed(path: str, body) -> bool:
    """A shared token identifies an access group, not an individual guest. Guest browser IDs remain
    self-asserted within that group, but cannot claim a local person's ID or legacy name-based history."""
    if not path.startswith(LEARNING_WRITES):
        return True
    if not isinstance(body, dict):
        return False
    rows = body.get("events") if path.startswith("/api/understanding") and "events" in body else [body]
    if not isinstance(rows, list):
        return False
    return all(isinstance(row, dict) and people.guest_viewer(row.get("viewer")) for row in rows)


def human_event(p: Project, name: str, kind: str, d: dict) -> dict | None:
    """One event from the reader. People never post as the agent; ids they point at must exist in that paper."""
    by, author = people.who(d)
    if author is None:
        return None  # a share-link guest claiming a person of this machine
    author = author[:40] or "Reviewer"
    if author.lower() in ("agent", "claude", "arx"):  # names the agent signs with; a person never posts as it
        return None
    body = str(d.get("body") or "").strip()[:4000]
    who = dict(author=author, by=by, guest=bool(d.get("_remote")))
    log = {e["id"]: e for e in papers.thread(p, name)}
    ids = set(log)
    if kind == "comment":
        a = d.get("anchor") if isinstance(d.get("anchor"), dict) else None
        anchor = {k: str(a[k])[:600] for k in ("block", "quote", "prefix", "suffix") if a and a.get(k)} or None
        if anchor and isinstance(a.get("shape"), dict):  # a drawn comment: the shape, relative to its block (paper.html)
            anchor["shape"] = clean_shape(a["shape"])
        if anchor and isinstance(a.get("pick"), dict):  # a picked element (paper.html): its kind, words, path in the block, box
            pk = a["pick"]
            anchor["pick"] = {k: str(pk[k])[:600] for k in ("kind", "text", "path", "ctx") if pk.get(k)}
            anchor["pick"].update({k: round(float(pk[k]), 1) for k in ("x", "y", "w", "h", "bw") if isinstance(pk.get(k), (int, float))})
        return papers.post(p, name, "comment", body=body, anchor=anchor, mentions=people.mentioned(body, people.members(p)) or None, **who) if body and anchor else None
    ref = str(d.get("parent" if kind in ("reply", "resolve", "reopen", "seen") else "target") or "")
    if ref not in ids or (kind in ("reply", "edit") and not body):
        return None
    if kind == "seen":  # a person read the thread; the agent's own "seen" carries no `by`
        return papers.post(p, name, "seen", parent=ref, by=by) if by and log[ref]["kind"] == "comment" else None
    if kind == "reply":
        return papers.post(p, name, "reply", parent=ref, body=body, mentions=people.mentioned(body, people.members(p)) or None, **who)
    if kind in ("resolve", "reopen"):
        if log[ref]["kind"] != "comment" or d.get("_remote") and log[ref].get("by") != by:
            return None
        return papers.post(p, name, kind, parent=ref, **who)
    t = log[ref]  # ids establish ownership; a matching display name is not an identity
    own = t.get("by") == by if t.get("by") else not d.get("_remote") and not by and t.get("author") == author
    if t["kind"] not in ("comment", "reply") or t.get("agent") or not own:
        return None
    return papers.post(p, name, kind, target=ref, body=body or None, **who)


def clean_shape(s: dict) -> dict:
    """A drawn mark from the paper reader: tool, an SVG path in px from its block's top-left, and the block's size then."""
    out = {k: s[k] for k in ("tool",) if s.get(k) in ("box", "arrow", "pen", "highlight")}
    if "tool" not in out:
        return {}
    d = str(s.get("d") or "")[:4000]
    out["d"] = d if re.fullmatch(r"[MLHVQCZmlhvqcz0-9.,\s-]*", d) else ""
    for k in ("bw", "bh", "x", "y", "w", "h"):
        try:
            out[k] = round(float(s[k]), 1)
        except (KeyError, TypeError, ValueError):
            pass
    return out


def serve(port: int = 8890, root=None):
    features.load()
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

        def _send(self, code, body: bytes, ctype, extra=None):
            if getattr(self, "_remote", False) and (ctype.startswith(("application/json", "text/html"))):
                body = share.redact(body.decode("utf-8", "replace")).encode()  # no paths on this machine leave it
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            if len(body) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                body = gzip.compress(body, compresslevel=5)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _token(self) -> str | None:
            q = dict(parse_qsl(urlsplit(self.path).query))
            if q.get("k"):
                return q["k"]
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "arx_k":
                    return v
            return None

        def _remote_ok(self, path: str, write: bool = False) -> bool:
            """Another machine: a share token that names this project (share.py); a write must also be same-origin."""
            parts = path.split("/")
            key = unquote(parts[2]) if len(parts) > 2 and parts[1] == "p" else None
            asset = key is None and not path.startswith(("/api/", "/papers")) and path not in ("/", "/index.html")
            if key is None and not asset:
                key = projects.key_for(home.root)  # the server's own project at /
            if path.startswith("/api/projects"):
                key = None  # answered with the granted projects only
            if not share.allowed(self._token(), None if asset or key is None else key):
                return False
            if write:
                origin = self.headers.get("Origin")
                host = urlsplit("//" + (self.headers.get("Host") or "")).netloc
                return bool(origin) and urlsplit(origin).netloc == host
            return True

        def _local(self) -> bool:
            # loopback only: a DNS-rebound page carries a foreign Host; a cross-site POST carries a foreign Origin
            # and the connection itself must come from this machine: headers alone are the sender's to choose
            peer = (self.client_address or ("",))[0]
            if peer not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
                return False
            host = urlsplit("//" + (self.headers.get("Host") or "")).hostname
            origin = self.headers.get("Origin")
            return host in LOCAL and (not origin or urlsplit(origin).hostname in LOCAL)

        def do_GET(self):
            path = self.path.split("?")[0]
            remote = self._remote = not self._local()
            if remote and not self._remote_ok(path):
                return self._send(403, b'{"error":"not shared"}', "application/json")
            q0 = dict(parse_qsl(urlsplit(self.path).query))
            if remote and q0.get("k"):  # the link's token becomes a cookie; the address bar loses it
                rest = urlencode([(k, v) for k, v in q0.items() if k != "k"])  # re-encoded: no CR/LF reaches the header
                self.send_response(302); self.send_header("Location", path + ("?" + rest if rest else ""))
                if not re.fullmatch(r"[\w-]{8,64}", q0["k"]):
                    return self._send(403, b'{"error":"not shared"}', "application/json")
                self.send_header("Set-Cookie", f"arx_k={q0['k']}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
                self.end_headers(); return
            if path.startswith("/p/") and path.count("/") == 2:  # /p/<key> -> /p/<key>/ so relative fetches resolve
                self.send_response(302); self.send_header("Location", path + "/"); self.end_headers(); return
            try:
                full = path
                p, path = pick(path)
                base = full[:len(full) - len(path)]  # "/p/<key>" or ""
                if path == "/api/projects":
                    ps = project_list(home)
                    if remote:  # someone else sees only what was shared with them, and no paths on this machine
                        keep = share.granted(self._token())
                        ps = [dict(x, root="") for x in ps if x.get("key") in keep]
                    return self._send(200, json.dumps(ps, default=str).encode(), "application/json")
                if path == "/ui.css":
                    return self._send(200, UI.read_bytes(), "text/css; charset=utf-8")
                if path == "/ui-base.css":  # tokens and base type only: what an embedded paper inherits
                    return self._send(200, UI.read_text().split("/* app shell")[0].encode(), "text/css; charset=utf-8")
                if path.rstrip("/") == "/papers":  # the list of papers is a dashboard view
                    self.send_response(302); self.send_header("Location", base + "/#papers"); self.end_headers(); return
                if path in ("/", "/index.html"):
                    return self._send(200, (WEB / "index.html").read_bytes(), TYPES[".html"])
                if not path.startswith(("/api/", "/papers")):
                    f = (WEB / unquote(path).lstrip("/")).resolve()
                    if f.is_file() and f.suffix in TYPES and WEB.resolve() in f.parents:
                        return self._send(200, f.read_bytes(), TYPES[f.suffix])
                if path == "/api/state":
                    return self._send(200, json.dumps(state(p), default=str).encode(), "application/json")
                if path == "/api/tasks":
                    return self._send(200, json.dumps(all_tasks(p), default=str).encode(), "application/json")
                if path.startswith("/api/task/"):
                    return self._send(200, json.dumps(task_detail(p, path.rsplit("/", 1)[1]), default=str).encode(), "application/json")
                if path.startswith("/api/hill/"):
                    return self._send(200, json.dumps(hill_detail(p, unquote(path.rsplit("/", 1)[1])), default=str).encode(), "application/json")
                if path.startswith("/api/gate/"):
                    return self._send(200, json.dumps(p.gate(path.rsplit("/", 1)[1]), default=str).encode(), "application/json")
                if path == "/api/papers":
                    return self._send(200, json.dumps(papers.papers(p), default=str).encode(), "application/json")
                features.REQUEST.remote = remote  # a feature may answer a share-link guest with less (memory.py)
                try:
                    r = _feature(features.GET, p, path, dict(parse_qsl(urlsplit(self.path).query), _port=str(self.server.server_port)))
                finally:
                    features.REQUEST.remote = False
                if r:
                    return self._send(*r[:3], r[3] if len(r) > 3 else None)
                parts = [unquote(x) for x in path.strip("/").split("/")]
                if parts[0] == "papers" and len(parts) == 2:  # the reader
                    return self._send(200, PAPER.read_bytes(), "text/html; charset=utf-8")
                if parts[0] == "papers" and len(parts) == 3 and parts[2] == "raw":
                    return self._send(200, (papers.pdir(p, parts[1]) / "paper.html").read_bytes(), "text/html; charset=utf-8")
                if parts[0] == "papers" and len(parts) == 4 and parts[2] == "files":
                    f = papers.file(p, parts[1], parts[3])
                    # attachments run sandboxed (opaque origin): a widget cannot read other projects or post comments
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream",
                                      {"Content-Security-Policy": "sandbox allow-scripts allow-popups"})
                if parts[:2] == ["api", "paper"] and len(parts) == 3:
                    body = dict(version=papers.version(p, parts[2]), meta=papers._read(papers.pdir(p, parts[2]) / "meta.json", {}),
                                threads=papers.threads(papers.thread(p, parts[2]), published=papers.version(p, parts[2])))
                    return self._send(200, json.dumps(body, default=str).encode(), "application/json")
            except (KeyError, SystemExit, OSError, ValueError):
                if full.startswith("/p/") and full.split("/", 3)[3:] in ([""], ["index.html"]):
                    return self._send(404, no_project_page(unquote(full.split("/")[2]), remote), "text/html; charset=utf-8")
                return self._send(404, b'{"error":"not found"}', "application/json")
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            self._remote = not self._local()
            if self._remote and not self._remote_ok(self.path.split("?")[0], write=True):
                return self._send(403, b'{"error":"cross-origin"}', "application/json")
            try:
                p, path = pick(self.path.split("?")[0])
                parts = [unquote(x) for x in path.strip("/").split("/")]
                # Share links permit discussion, not approval of project decisions or changes to another
                # person's question. Enforce this before dispatch, including goal-opening intake routes.
                action = path.rstrip("/").rsplit("/", 1)[-1]
                if self._remote and ((path.startswith("/api/intake/") and action != "new")
                                     or (path.startswith("/api/questions/") and action not in ("ask", "add"))):
                    return self._send(403, b'{"error":"project decisions require the owner"}', "application/json")
                if any(path.startswith(pre) for pre, _ in features.POST):
                    n = int(self.headers.get("Content-Length") or 0)
                    if not 0 <= n <= 1_000_000:
                        return self._send(413, b'{"error":"too large"}', "application/json")
                    d = json.loads(self.rfile.read(n) or b"{}")
                    if self._remote and not guest_learning_allowed(path, d):
                        return self._send(403, b'{"error":"use your guest learner ID"}', "application/json")
                    if isinstance(d, dict):  # a feature may treat someone on another machine differently (people.py)
                        d["_remote"] = self._remote
                    features.REQUEST.remote = self._remote
                    try:
                        return self._send(*_feature(features.POST, p, path, d))
                    finally:
                        features.REQUEST.remote = False
                if parts[:2] == ["api", "paper"] and len(parts) == 4 and parts[3] in HUMAN_KINDS:
                    n = int(self.headers.get("Content-Length") or 0)
                    if not 0 <= n <= 64_000:
                        return self._send(413, b'{"error":"too large"}', "application/json")
                    d = json.loads(self.rfile.read(n) or b"{}")
                    if not isinstance(d, dict):
                        return self._send(400, b'{"error":"bad request"}', "application/json")
                    d["_remote"] = self._remote
                    features.REQUEST.remote = self._remote
                    try:
                        ev = human_event(p, parts[2], parts[3], d)
                    finally:
                        features.REQUEST.remote = False
                    if ev is None:
                        return self._send(400, b'{"error":"bad request"}', "application/json")
                    return self._send(200, json.dumps(ev).encode(), "application/json")
            except (KeyError, ValueError, OSError):
                return self._send(404, b'{"error":"not found"}', "application/json")
            self._send(404, b"not found", "text/plain")

    ThreadingHTTPServer.request_queue_size = 64  # the page loads ~20 files at once; the default backlog of 5 drops some
    srv = None
    for port_try in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer((share.bind_host(), port_try), H)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit(f"no free port in {port}-{port + 19}")
    print(f"dashboard: http://127.0.0.1:{port_try}")
    srv.serve_forever()
