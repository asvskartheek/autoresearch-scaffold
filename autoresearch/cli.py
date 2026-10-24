"""`ar` command line: the same ledger operations agents use from Python, for shells and subagents."""
from __future__ import annotations

import argparse, json, os, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path

from .core import Project, Task, _jsonl

TEMPLATE = Path(__file__).resolve().parent / "templates"  # works from a checkout and from an install


def _ids(args) -> list[str]:
    if args.ids_file:
        text = Path(args.ids_file).read_text()
        try:
            data = json.loads(text)
            return [str(x["id"] if isinstance(x, dict) else x) for x in data]
        except ValueError:
            return [line.strip() for line in text.splitlines() if line.strip()]
    if args.size:
        return [str(i) for i in range(args.size)]
    raise SystemExit("give --ids-file or --size")


def _fmt(x, pct=True):
    if x is None:
        return "—"
    return f"{100 * x:+.1f}" if pct else f"{x:.3f}"


def cmd_init(a):
    root = Path(a.path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for f in ("AGENTS.md", "CLAUDE.md", "PROTOCOL.md", "research.json"):
        if not (root / f).exists():
            shutil.copy(TEMPLATE / f, root / f)
    pkg = Path(__file__).resolve().parent
    if not (root / "autoresearch").exists():  # vendored so `import autoresearch` works in the project's own Python
        shutil.copytree(pkg, root / "autoresearch", ignore=shutil.ignore_patterns("__pycache__"))
    hooks = root / ".claude" / "settings.json"  # the dashboard follows the agent session: up on start, down on end
    if not hooks.exists():
        hooks.parent.mkdir(exist_ok=True)
        hooks.write_text((TEMPLATE / "claude-settings.json").read_text())
    cfg = json.loads((root / "research.json").read_text())
    cfg["name"] = a.name or cfg["name"]
    (root / "research.json").write_text(json.dumps(cfg, indent=2))
    (root / ".research").mkdir(exist_ok=True)
    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    for want in ("scratch/", ".research/tasks/*/rows.jsonl"):
        if want not in lines:
            lines.append(want)
    gi.write_text("\n".join(lines) + "\n")
    # Step 0: the dashboard is up and setup itself is a visible task before any other work happens.
    url = _up(root, a.port) if not a.no_serve else None
    os.chdir(root)
    t = Task(Project(root), "setup", "Project setup", "Environment, model and dataset preparation. Note each step; finish when the first eval can run.")
    t.note("ar init")
    if url:
        t.link("Dashboard", url)
    print(f"initialised {root}\ndashboard: {url or 'not started (arx up)'}\nsetup task: {t.id}  (arx task note {t.id} ... ; arx task finish {t.id})")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _serves(port: int, root: Path) -> bool:
    """True when the dashboard on `port` is this project's, not another project's that happens to hold the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
            return Path(json.load(r)["root"]) == root
    except (OSError, ValueError, KeyError):
        return False


def _stop(rec: dict) -> None:
    try:
        os.kill(rec["pid"], 15)
    except OSError:
        pass
    for _ in range(30):
        if not _port_open(rec["port"]):
            return
        time.sleep(0.1)


def _up(root: Path, port: int, restart: bool = False) -> str:
    """Start this project's dashboard detached (idempotent). It records itself in .research/server.json and in
    ~/.arx/servers.json, and shuts itself down when nobody is looking and nothing is running."""
    from .server import servers
    mine = next((r for r in servers() if Path(r["root"]) == root and _serves(r["port"], root)), None)
    if mine and not restart:
        return f"http://127.0.0.1:{mine['port']}"
    if mine:
        _stop(mine)
        port = mine["port"]
    while _port_open(port):
        port += 1
    (root / ".research").mkdir(exist_ok=True)
    log = open(root / ".research" / "server.log", "a")
    # `python -m` would put the project dir first on sys.path and pick up a vendored copy; run the CLI's own package.
    pkg = str(Path(__file__).resolve().parents[1])
    boot = f"import sys; sys.path.insert(0, {pkg!r}); from autoresearch.cli import main; main()"
    subprocess.Popen([sys.executable, "-c", boot, "serve", "--port", str(port)], cwd=root,
                     stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        if _serves(port, root):
            break
        time.sleep(0.1)
    return f"http://127.0.0.1:{port}"


def cmd_up(a):
    print(_up(Project().root, a.port, a.restart))


def cmd_down(a):
    """Stop this project's dashboard (or every one with --all)."""
    from .server import servers
    root = None if a.all else Project().root
    stopped = [r for r in servers() if root is None or Path(r["root"]) == root]
    for r in stopped:
        _stop(r)
    print("\n".join(f"stopped {r['root']} :{r['port']}" for r in stopped) or "no dashboard running")


def cmd_ps(a):
    from .server import servers
    for r in servers():
        print(f"http://127.0.0.1:{r['port']}  pid {r['pid']}  {r['root']}")


def cmd_sync(a):
    """Refresh the project's vendored `autoresearch/` from the installed package, then restart the dashboard."""
    root = Project().root
    src, dst = Path(__file__).resolve().parent, root / "autoresearch"
    if src == dst.resolve():
        raise SystemExit("this is the vendored copy itself; run the installed `arx sync`")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"vendored copy updated from {src}\n{_up(root, 8890, restart=True)}")


def cmd_dataset(a):
    p = Project()
    p.add_dataset(a.name, _ids(a), title=a.title, url=a.url, description=a.description)
    if not a.no_random:
        p.random_slices(a.name, tuple(a.random), a.seed)
    print(json.dumps({k: {kk: v[kk] for kk in ("n", "hash", "kind")} for k, v in p.slices().items() if k.startswith(a.name + "/")}, indent=1))


def cmd_slice(a):
    p = Project()
    s = p.add_slice(a.name, _ids(a), kind=a.kind, description=a.description, url=a.url, hill=a.hill, metric=a.metric)
    print(f"{a.name}: n={s['n']} hash={s['hash']}")


def cmd_hill(a):
    p = Project()
    examples = json.loads(Path(a.examples_file).read_text()) if a.examples_file else None
    ex = {k: v for k, v in dict(input=a.example_input, wrong=a.example_wrong, right=a.example_right, why=a.example_why).items() if v}
    if ex:
        examples = (examples or (p.hills().get(a.name) or {}).get("examples") or []) + [ex]
    share = None
    if a.share:
        count, of = a.share.split("/")
        share = dict(count=int(count), of=int(of), of_what=a.share_of)
    explainer = dict(symptom=a.symptom, measure=a.measure, examples=examples, share=share)
    if a.verb == "explain":
        p.explain_hill(a.name, **explainer)
        if a.poster:
            p.set_poster("hill", a.name, a.poster)
        return print(f"hill {a.name} explained")
    if not (a.title and a.target):
        raise SystemExit("arx hill open needs --title and --target")
    h = p.open_hill(a.name, a.title, a.target, a.control, a.problem, a.found_in, poster=a.poster, **explainer)
    print(f"hill {a.name} open: target {h['target']}, control {h.get('control')}")


def cmd_model(a):
    p = Project()
    links = dict(kv.split("=", 1) for kv in a.link or [])
    p.add_model(a.name, parent="" if a.no_parent else a.parent, hill=a.hill, change=a.change, title=a.title,
                links=links or None, status="champion" if a.champion else a.status, poster=a.poster)
    print(f"model {a.name} added{' as champion' if a.champion else ''}")


def cmd_poster(a):
    f = Project().set_poster(a.kind, a.id, a.file)
    print(f"poster for {a.kind} {a.id}: {f.name}")


def cmd_reject(a):
    Project().set_model_status(a.name, "rejected", a.reason)


def cmd_gate(a):
    p = Project()
    g = p.gate(a.model)
    if a.json:
        return print(json.dumps(g, indent=1, default=str))
    print(f"{a.model} vs champion {g['champion']}")
    for r in g["rungs"]:
        print(f"  {r['rung']:<10} {r['status'].upper()}")
        for c in r["checks"]:
            extra = ""
            if c.get("delta") is not None:
                extra = f"Δ {_fmt(c['delta'])} pts [{_fmt(c['lo'])}, {_fmt(c['hi'])}] n={c['n']} W/L {c['wins']}/{c['losses']}{' noisy' if c.get('noisy') else ''}"
            print(f"      {c['state']:<14} {c['slice']:<28} {c['rule']} {_fmt(c['threshold'])}  {extra}")
    if g["next"]:
        print("next runs:")
        for n in g["next"]:
            print(f"  {n['model']} on {n['slice']}")
    if g["promotable"]:
        print(f"every rung passed: `arx promote {a.model}`")


def cmd_promote(a):
    p = Project()
    p.promote(a.model, a.force)
    print(f"{a.model} is champion")


def cmd_eval_record(a):
    """Record rows produced elsewhere (a cloud job, another harness) as a finished eval task."""
    p = Project()
    rows = _jsonl(Path(a.rows)) if a.rows.endswith(".jsonl") else json.loads(Path(a.rows).read_text())
    t = Task(p, "eval", a.title or f"{a.model} on {a.slice}", a.description, model=a.model, slice=a.slice, agent=a.agent)
    for r in rows:
        t.add_row(r | {"id": str(r["id"])})
    t.progress(len(rows))
    t.finish()
    print(f"{t.id}: complete={t.meta['complete']} score={t.meta['summary'].get('score')}")


def cmd_eval_run(a):
    from .execution import run_manifest
    run_manifest(a)


def cmd_task(a):
    p = Project()
    if a.action == "start":
        t = Task(p, a.kind, a.title, a.description, model=a.model, slice=a.slice, agent=a.agent, total=a.total,
                 parent=a.parent, budget_s=a.budget_s)
        print(t.id)
        return
    t = Task(p, "", "", tid=a.id)
    if a.action == "log":
        t.log(step=a.step, **{k: float(v) for k, v in (kv.split("=", 1) for kv in a.values)})
    elif a.action == "note":
        t.note(" ".join(a.values), a.level)
    elif a.action == "link":
        t.link(a.values[0], a.values[1])
    elif a.action == "progress":
        t.progress(int(a.values[0]), int(a.values[1]) if len(a.values) > 1 else None)
    elif a.action == "left":  # exit 3 once spent, so shell loops can `while arx task left $id; do ...; done`
        left = t.left()
        print("unlimited" if left is None else f"{left:.1f}s")
        if not t.ok():
            sys.exit(3)
    elif a.action == "resume":  # an agent picking up a stalled task: it is the same job, not a new card
        t.note("resumed")
    elif a.action == "finish":
        t.finish(a.status, summary=json.loads(Path(a.summary_file).read_text()) if a.summary_file else None)
    info = p.dir / "server.json"
    if not (info.exists() and _port_open(json.loads(info.read_text()).get("port", 0))):
        print("warning: dashboard is not running; `arx up`", file=sys.stderr)


def cmd_sweep(a):
    """Close tasks that have been stalled for `--hours` as `abandoned`, so the Workbench shows only live work."""
    p = Project()
    n = 0
    for t in p.tasks():
        if t["status"] == "stalled" and time.time() - t.get("heartbeat", 0) > 3600 * a.hours:
            Task(p, "", "", tid=t["id"]).finish("abandoned")
            n += 1
    print(f"{n} abandoned")


def cmd_status(a):
    from .server import _runs, _tracks
    p = Project()
    runs = _runs(p.tasks())
    print(f"{p.config.get('name')} · champion {p.champion()} · {len(p.models())} models · {len(runs)} scored runs · {len(p.hills())} hills")
    higher = p.config.get("higher_is_better", True)
    by = {r["id"]: r for r in runs}
    seen = set()
    for tr in _tracks(runs, p.slices(), higher):  # one line per dataset, on its most contested slice
        if tr["dataset"] in seen or not tr["frontier"]:
            continue
        seen.add(tr["dataset"])
        r = by[tr["frontier"][-1]["id"]]
        print(f"  best on {tr['label']} (n={tr['n']}, {tr['runs']} runs): {r['variant']} {100 * r['score']:.1f}%")
    for name, h in p.hills().items():
        ms = [k for k, m in p.models().items() if m.get("hill") == name]
        print(f"  hill {name} [{h['status']}] {len(ms)} attempts: " + ", ".join(f"{k}({p.models()[k].get('status')})" for k in ms[:6]))
    for t in p.tasks():
        if t["status"] in ("running", "stalled"):
            pr = t.get("progress") or {}
            print(f"  [{t['status']}] {t['id']} {t['title']} {pr.get('done')}/{pr.get('total')}")
    for name, m in p.models().items():
        if m.get("status") == "candidate":
            g = p.gate(name)
            print(f"  candidate {name}: " + " → ".join(f"{r['rung']}:{r['status']}" for r in g["rungs"]))


def cmd_serve(a):
    from .server import serve
    serve(a.port)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arx")
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("init"); s.add_argument("path", nargs="?", default="."); s.add_argument("--name")
    s.add_argument("--port", type=int, default=8890); s.add_argument("--no-serve", action="store_true"); s.set_defaults(fn=cmd_init)
    s = sp.add_parser("up", help="start the dashboard in the background if it is not running"); s.add_argument("--port", type=int, default=8890)
    s.add_argument("--restart", action="store_true", help="restart it, e.g. after upgrading the scaffold"); s.set_defaults(fn=cmd_up)
    s = sp.add_parser("down", help="stop this project's dashboard"); s.add_argument("--all", action="store_true", help="every project's"); s.set_defaults(fn=cmd_down)
    s = sp.add_parser("ps", help="list running dashboards and the project each serves"); s.set_defaults(fn=cmd_ps)
    s = sp.add_parser("sync", help="refresh the vendored autoresearch/ copy and restart the dashboard"); s.set_defaults(fn=cmd_sync)

    s = sp.add_parser("dataset", help="register a full eval set and its random slices")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--ids-file"); s.add_argument("--size", type=int)
    s.add_argument("--title"); s.add_argument("--url", help="e.g. https://huggingface.co/datasets/org/name (private)")
    s.add_argument("--description"); s.add_argument("--random", type=int, nargs="+", default=[50, 100]); s.add_argument("--seed", type=int, default=42)
    s.add_argument("--no-random", action="store_true"); s.set_defaults(fn=cmd_dataset)

    s = sp.add_parser("slice", help="freeze a development / synthetic / control slice")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--ids-file"); s.add_argument("--size", type=int)
    s.add_argument("--kind", default="dev", choices=["dev", "control", "synthetic", "random", "full"]); s.add_argument("--description")
    s.add_argument("--url"); s.add_argument("--hill"); s.add_argument("--metric", help="what `score` means on this slice"); s.set_defaults(fn=cmd_slice)

    s = sp.add_parser("hill", help="open a hill (a named weakness) with its target and control slices")
    s.add_argument("verb", choices=["open", "explain"]); s.add_argument("name"); s.add_argument("--title")
    s.add_argument("--target"); s.add_argument("--control"); s.add_argument("--problem"); s.add_argument("--found-in")
    s.add_argument("--symptom", help="one plain line: what the model does wrong")
    s.add_argument("--measure", help="what a target score of 1 means for one example")
    s.add_argument("--example-input"); s.add_argument("--example-wrong"); s.add_argument("--example-right")
    s.add_argument("--example-why", help="one clause: why the model gets it wrong"); s.add_argument("--examples-file", help="JSON list of {input, wrong, right, why}")
    s.add_argument("--share", help="failures this hill explains, COUNT/OF, e.g. 63/495"); s.add_argument("--share-of", help="what OF counts, e.g. \"v1's wrong answers on full\"")
    s.add_argument("--poster", help="JSON spec (see docs/guides/posters.md), svg, html, png, jpg or webp card (max 2 MB) that explains the hill")
    s.set_defaults(fn=cmd_hill)

    s = sp.add_parser("model", help="register a version (candidate, or --champion for the baseline)")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--parent"); s.add_argument("--hill")
    s.add_argument("--no-parent", action="store_true", help="not derived from the champion (e.g. a backfilled run)")
    s.add_argument("--change"); s.add_argument("--title"); s.add_argument("--link", action="append", help="label=url")
    s.add_argument("--status", choices=["candidate", "historical", "planned"], default="candidate")
    s.add_argument("--poster", help="JSON spec (see docs/guides/posters.md), svg, html, png, jpg or webp card (max 2 MB) that explains the idea")
    s.add_argument("--champion", action="store_true"); s.set_defaults(fn=cmd_model)

    s = sp.add_parser("poster", help="set the poster of a model or hill")
    s.add_argument("kind", choices=["model", "hill"]); s.add_argument("id"); s.add_argument("file"); s.set_defaults(fn=cmd_poster)

    s = sp.add_parser("reject"); s.add_argument("name"); s.add_argument("--reason", required=True); s.set_defaults(fn=cmd_reject)
    s = sp.add_parser("gate", help="where a candidate is on the ladder, and what to run next")
    s.add_argument("model"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_gate)
    s = sp.add_parser("promote"); s.add_argument("model"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_promote)

    s = sp.add_parser("eval", help="record rows produced by another harness")
    s.add_argument("verb", choices=["record"]); s.add_argument("--model", required=True); s.add_argument("--slice", required=True)
    s.add_argument("--rows", required=True); s.add_argument("--title"); s.add_argument("--description"); s.add_argument("--agent")
    s.set_defaults(fn=cmd_eval_record)

    s = sp.add_parser("run", help="launch a hash-pinned command manifest as a task (see autoresearch/execution.py)")
    s.add_argument("--manifest", required=True); s.add_argument("--expected-sha256", required=True)
    s.add_argument("--model"); s.add_argument("--slice"); s.add_argument("--title"); s.add_argument("--description")
    s.add_argument("--agent"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--approve-paid", action="store_true")
    s.set_defaults(fn=cmd_eval_run)

    s = sp.add_parser("task", help="workbench tasks from a shell")
    s.add_argument("action", choices=["start", "log", "note", "link", "progress", "left", "finish", "resume"])
    s.add_argument("id", nargs="?"); s.add_argument("values", nargs="*")
    s.add_argument("--kind", default="experiment"); s.add_argument("--title"); s.add_argument("--description")
    s.add_argument("--model"); s.add_argument("--slice"); s.add_argument("--agent"); s.add_argument("--total", type=int)
    s.add_argument("--parent", help="task id this one sits under (default $ARX_PARENT)")
    s.add_argument("--budget-s", type=float, help="wall-clock seconds")
    s.add_argument("--step", type=int); s.add_argument("--level", default="info"); s.add_argument("--status", default="done")
    s.add_argument("--summary-file", help="JSON merged into the task summary on finish")
    s.set_defaults(fn=cmd_task)

    s = sp.add_parser("sweep", help="mark long-stalled tasks abandoned"); s.add_argument("--hours", type=float, default=2); s.set_defaults(fn=cmd_sweep)
    s = sp.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sp.add_parser("serve"); s.add_argument("--port", type=int, default=8890); s.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    if a.cmd == "task" and a.action == "start" and not a.title:
        ap.error("task start needs --title")
    a.fn(a)


if __name__ == "__main__":
    main()
