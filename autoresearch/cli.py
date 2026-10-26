"""`ar` command line: the same ledger operations agents use from Python, for shells and subagents."""
from __future__ import annotations

import argparse, json, os, shutil, socket, subprocess, sys, time
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
    cfg = json.loads((root / "research.json").read_text())
    cfg["name"] = a.name or cfg["name"]
    (root / "research.json").write_text(json.dumps(cfg, indent=2))
    (root / ".research").mkdir(exist_ok=True)
    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    for want in ("scratch/", ".research/tasks/*/rows.jsonl", ".research/server.json", ".research/server.log"):
        if want not in lines:
            lines.append(want)
    gi.write_text("\n".join(lines) + "\n")
    # Step 0: the dashboard is up and setup itself is a visible task before any other work happens.
    from .projects import register
    register(root)
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


def _up(root: Path, port: int, restart: bool = False) -> str:
    """Start the dashboard detached (idempotent); its port and pid are kept in .research/server.json."""
    info = root / ".research" / "server.json"
    if info.exists():
        old = json.loads(info.read_text())
        try:
            old["port"], old["pid"] = int(old.get("port") or 0), int(old.get("pid") or 0)
        except (TypeError, ValueError):
            old = {}
        if old.get("port") and _port_open(old["port"]):
            if not restart:
                return f"http://127.0.0.1:{old['port']}"
            if old.get("pid") and _is_dashboard(old["pid"], old["port"]):
                try:
                    os.kill(old["pid"], 15)
                except OSError:
                    pass
            else:  # started by an older version that did not record its pid
                subprocess.run(["pkill", "-f", f"autoresearch.cli serve --port {old['port']}"])
            for _ in range(30):
                if not _port_open(old["port"]):
                    break
                time.sleep(0.1)
            port = old["port"]
    while _port_open(port):
        port += 1
    (root / ".research").mkdir(exist_ok=True)
    log = open(root / ".research" / "server.log", "a")
    # `python -m` would put the project dir first on sys.path and pick up a vendored copy; run the CLI's own package.
    pkg = str(Path(__file__).resolve().parents[1])
    boot = f"import sys; sys.path.insert(0, {pkg!r}); from autoresearch.cli import main; main()"
    proc = subprocess.Popen([sys.executable, "-c", boot, "serve", "--port", str(port)], cwd=root,
                            stdout=log, stderr=log, start_new_session=True)
    for _ in range(30):
        if _port_open(port):
            break
        time.sleep(0.1)
    info.write_text(json.dumps(dict(port=port, pid=proc.pid, started=time.time())))
    return f"http://127.0.0.1:{port}"


def cmd_up(a):
    from .projects import register
    root = Project().root
    key = register(root)
    url = _up(root, a.port, a.restart)
    print(f"{url}\n{url}/p/{key}/  (this project; every registered project is listed in the sidebar)")


def cmd_projects(a):
    from . import projects
    if a.verb == "add":
        print(projects.register(Path(a.path or ".")))
    elif a.verb == "rm":
        if not projects.unregister(a.path or ""):
            sys.exit(f"no project {a.path!r}")
    else:
        for k, v in projects.registry().items():
            print(f"{k}  {v['root']}")


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
    s = p.add_slice(a.name, _ids(a), kind=a.kind, description=a.description, url=a.url, hill=a.hill, metric=a.metric,
                    scale=a.scale, unit=a.unit)
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
        explainer["goal"] = a.goal
        p.explain_hill(a.name, **explainer)
        return print(f"hill {a.name} explained")
    if not (a.title and a.target):
        raise SystemExit("arx hill open needs --title and --target")
    h = p.open_hill(a.name, a.title, a.target, a.control, a.problem, a.found_in, goal=a.goal, **explainer)
    print(f"hill {a.name} open: target {h['target']}, control {h.get('control')}" + (f", serves goal {a.goal}" if a.goal else ""))


def _kpi_fmt(g, v):
    if v is None:
        return "—"
    return f"{100 * v:.1f}%" if g.get("kpi", "score") == "score" else f"{v:.4g}"


def cmd_goal(a):
    p = Project()
    if a.verb == "open":
        if not (a.title and a.slice and a.target is not None):
            raise SystemExit("arx goal open needs --title, --slice and --target")
        g = p.open_goal(a.name, a.title, a.slice, a.target, kpi=a.kpi, baseline=a.baseline, problem=a.problem,
                        higher_is_better=False if a.lower_is_better else None)
        return print(f"goal {a.name} open: {g['kpi']} {'>=' if g['higher_is_better'] else '<='} {g['target']} "
                     f"on {g['slice']} (n = {g['n']}), baseline {g.get('baseline') or 'none yet (no champion)'}")
    if a.verb == "achieve":
        ev = p.achieve_goal(a.name, a.force, a.note)
        return print(f"goal {a.name} achieved by {ev['model']} ({ev['task']}); write its paper: arx paper new --goal {a.name}")
    if a.verb == "abandon":
        if not a.reason:
            raise SystemExit("arx goal abandon needs --reason")
        p.abandon_goal(a.name, a.reason)
        return print(f"goal {a.name} abandoned; its paper reports the negative result")
    for name in ([a.name] if a.name else list(p.goals())):
        st = p.goal_status(name)
        if a.json:
            print(json.dumps(st, default=str))
            continue
        vs = st["vs_baseline"]
        print(f"{name} [{st['status']}] {st['title']}\n"
              f"  target {st['kpi']} {'>=' if st['higher_is_better'] else '<='} {_kpi_fmt(st, st['target'])} on {st['slice']} (n = {st['n']})\n"
              f"  {st['model'] or 'no champion'}: {_kpi_fmt(st, st['value'])}{'  MET' if st['met'] else ''}"
              + (f"  Δ vs {st['baseline']} {_fmt(vs['delta'])} pts [{_fmt(vs['lo'])}, {_fmt(vs['hi'])}] n={vs['n']}" if vs and vs['delta'] is not None else ""))
        for h, s in st["hills"].items():
            print(f"  hill {h} [{s}]")


def cmd_model(a):
    p = Project()
    links = dict(kv.split("=", 1) for kv in a.link or [])
    p.add_model(a.name, parent="" if a.no_parent else a.parent, hill=a.hill, change=a.change, title=a.title,
                links=links or None, status="champion" if a.champion else a.status)
    print(f"model {a.name} added{' as champion' if a.champion else ''}")


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
    elif a.action == "finish":
        t.finish(a.status, summary=json.loads(Path(a.summary_file).read_text()) if a.summary_file else None)
    if a.action != "start" and not _port_open(json.loads((p.dir / "server.json").read_text()).get("port", 0)) if (p.dir / "server.json").exists() else True:
        print("warning: dashboard is not running; `arx up`", file=sys.stderr)


def cmd_status(a):
    p = Project()
    print(f"{p.config.get('name')} · champion {p.champion()}")
    for t in p.tasks():
        if t["status"] in ("running", "stalled"):
            pr = t.get("progress") or {}
            print(f"  [{t['status']}] {t['id']} {t['title']} {pr.get('done')}/{pr.get('total')}")
    for name, m in p.models().items():
        if m.get("status") == "candidate":
            g = p.gate(name)
            print(f"  candidate {name}: " + " → ".join(f"{r['rung']}:{r['status']}" for r in g["rungs"]))
    for name in p.goals():
        st = p.goal_status(name)
        print(f"  goal {name} [{st['status']}] {_kpi_fmt(st, st['value'])} / {_kpi_fmt(st, st['target'])} on {st['slice']}")
    for name, h in p.hills().items():
        print(f"  hill {name} [{h['status']}] {h['title']}" + (f" (goal {h['goal']})" if h.get("goal") else ""))


def _is_dashboard(pid: int, port: int) -> bool:
    """The pid in server.json may have been reused: only signal it if it is still our server on that port."""
    try:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    except OSError:
        return False
    return "autoresearch.cli" in cmd and f"serve --port {port}" in cmd


def cmd_paper(a):
    from . import papers
    p = Project()
    port = (json.loads((p.dir / "server.json").read_text()).get("port") if (p.dir / "server.json").exists() else None) or 8890
    if a.verb in ("add", "edit"):  # edit = republish; open pages swap the new version in without reloading
        if not a.name or not a.file:
            sys.exit(f"usage: arx paper {a.verb} <name> --file paper.html")
        if a.goal and a.goal not in p.goals():
            sys.exit(f"unknown goal {a.goal}")
        f = papers.add(p, a.name, Path(a.file), title=a.title, hill=a.hill, goal=a.goal)
        print(f"{f}\nhttp://127.0.0.1:{port}/papers/{a.name}")
    elif a.verb == "ls":
        for name, m in papers.papers(p).items():
            print(f"{name}  {m.get('title') or ''}  threads={m['comments']} open={m['open']} waiting={m['waiting']}"
                  f"  http://127.0.0.1:{port}/papers/{name}")
    elif a.verb == "poll":  # blocks until a person is waiting on the agent; one JSON line per thread
        for th in papers.poll(p, a.name, timeout=a.timeout):
            print(json.dumps(dict(paper=th["paper"], thread=th["id"], quote=(th.get("anchor") or {}).get("quote"),
                                  block=(th.get("anchor") or {}).get("block"), mention=th["mention"],
                                  resolved=th["resolved"],  # the whole thread, so the agent answers in context
                                  messages=[dict(author=m["author"], agent=m["agent"], body=m["body"], link=m.get("link"))
                                            for m in th["messages"]])))
    elif a.verb == "attach":
        if not a.file:
            sys.exit("usage: arx paper attach <name> --file page.html")
        print(f"http://127.0.0.1:{port}" + papers.attach(p, a.name, Path(a.file)))
    elif a.verb == "new" and a.goal:  # the public paper: the worked goal example, to rewrite with this goal's result
        if a.goal not in p.goals():
            sys.exit(f"unknown goal {a.goal}")
        out = Path(a.file or f"paper-{a.goal}.html")
        if out.exists():
            sys.exit(f"{out} exists")
        shutil.copy(TEMPLATE / "paper-goal-example.html", out)
        st = p.goal_status(a.goal)
        print(f"{out}\nrewrite it for goal {a.goal!r} (checklist: PROTOCOL.md § Goal papers). From the ledger:\n"
              f"  target  {st['kpi']} {_kpi_fmt(st, st['target'])} on {st['slice']}, n = {st['n']}\n"
              f"  now     {st['model']}: {_kpi_fmt(st, st['value'])} [{st['status']}]\n"
              + (f"  vs {st['baseline']}: Δ {_fmt(st['vs_baseline']['delta'])} pts, 90% CI [{_fmt(st['vs_baseline']['lo'])}, {_fmt(st['vs_baseline']['hi'])}], n = {st['vs_baseline']['n']}\n" if st["vs_baseline"] else "")
              + "".join(f"  internal: ../{h} (hill {h}, {s})\n" for h, s in st["hills"].items())
              + f"  arx paper check --goal {a.goal} --file {out}\n  arx paper add {a.goal} --goal {a.goal} --file {out}")
    elif a.verb == "new":  # a starter page: the worked example, to rewrite with this hill's content
        if not a.name:
            sys.exit("usage: arx paper new <hill> [--file paper-<hill>.html] | arx paper new --goal <goal>")
        out = Path(a.file or f"paper-{a.name}.html")
        if out.exists():
            sys.exit(f"{out} exists")
        shutil.copy(TEMPLATE / "paper-example.html", out)
        print(f"{out}\nrewrite it for hill {a.name!r} (checklist: PROTOCOL.md § Papers), then:\n"
              f"  arx paper check --file {out}\n  arx paper add {a.name} --hill {a.name} --file {out}")
    elif a.verb == "check":  # lint a paper (published name or a file) against PROTOCOL.md before publishing it
        src = Path(a.file) if a.file else papers.pdir(p, a.name or "") / "paper.html"
        if not src.exists():
            sys.exit(f"usage: arx paper check <name> | --file paper.html  (no {src})")
        goal = a.goal or (papers._read(papers.pdir(p, a.name) / "meta.json", {}).get("goal") if a.name else None)
        if goal and goal not in p.goals():
            sys.exit(f"unknown goal {goal}")
        found = papers.check(src.read_text(), slices=list(p.slices()))
        if goal:  # the public paper: final result, paired delta, internal hill papers
            found += papers.check_goal(src.read_text(), p.goal_status(goal), hill_papers=papers.names(p))
        for level, msg in found:
            print(f"{level}: {msg}")
        errs = sum(1 for lv, _ in found if lv == "error")
        print(f"{errs} errors, {len(found) - errs} warnings in {src}")
        sys.exit(1 if errs else 0)
    elif a.verb in ("reply", "resolve"):
        if not a.name or not a.comment:
            sys.exit(f"usage: arx paper {a.verb} <name> <thread id> [text] [--link label=url | --file page.html]")
        if a.comment not in {t["id"] for t in papers.threads(papers.thread(p, a.name))}:
            sys.exit(f"no thread {a.comment!r} in paper {a.name!r}; `arx paper poll` prints thread ids")
        link = None
        if a.file:  # the answer is its own page: copy it next to the paper and link to it
            url = papers.attach(p, a.name, Path(a.file))
            link = dict(label=a.link or Path(a.file).stem.replace("-", " "), url=url)
        elif a.link:
            label, _, url = a.link.rpartition("=") if "=" in a.link else ("", "", a.link)
            link = dict(label=label or url, url=url)
        papers.post(p, a.name, a.verb, parent=a.comment, body=" ".join(a.text) or None, link=link, agent=True,
                    author=a.author)


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
    s = sp.add_parser("sync", help="refresh the vendored autoresearch/ copy and restart the dashboard"); s.set_defaults(fn=cmd_sync)

    s = sp.add_parser("dataset", help="register a full eval set and its random slices")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--ids-file"); s.add_argument("--size", type=int)
    s.add_argument("--title"); s.add_argument("--url", help="e.g. https://huggingface.co/datasets/org/name (private)")
    s.add_argument("--description"); s.add_argument("--random", type=int, nargs="+", default=[50, 100]); s.add_argument("--seed", type=int, default=42)
    s.add_argument("--no-random", action="store_true"); s.set_defaults(fn=cmd_dataset)

    s = sp.add_parser("slice", help="freeze a development / synthetic / control slice")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--ids-file"); s.add_argument("--size", type=int)
    s.add_argument("--kind", default="dev", choices=["dev", "control", "synthetic", "random", "full"]); s.add_argument("--description")
    s.add_argument("--url"); s.add_argument("--hill"); s.add_argument("--metric", help="what `score` means on this slice")
    s.add_argument("--scale", choices=["binary", "continuous"], help="binary: each example scores 0 or 1 (the default); continuous: any number")
    s.add_argument("--unit", help="unit of a continuous score, e.g. s"); s.set_defaults(fn=cmd_slice)

    s = sp.add_parser("hill", help="open a hill (a named weakness) with its target and control slices")
    s.add_argument("verb", choices=["open", "explain"]); s.add_argument("name"); s.add_argument("--title")
    s.add_argument("--target"); s.add_argument("--control"); s.add_argument("--problem"); s.add_argument("--found-in")
    s.add_argument("--symptom", help="one plain line: what the model does wrong")
    s.add_argument("--measure", help="what a target score of 1 means for one example")
    s.add_argument("--example-input"); s.add_argument("--example-wrong"); s.add_argument("--example-right")
    s.add_argument("--example-why", help="one clause: why the model gets it wrong"); s.add_argument("--examples-file", help="JSON list of {input, wrong, right, why}")
    s.add_argument("--share", help="failures this hill explains, COUNT/OF, e.g. 63/495"); s.add_argument("--share-of", help="what OF counts, e.g. \"v1's wrong answers on full\"")
    s.add_argument("--goal", help="the goal this hill serves")
    s.set_defaults(fn=cmd_hill)

    s = sp.add_parser("goal", help="a target KPI on one slice; hills serve it; it gets the public paper")
    s.add_argument("verb", choices=["open", "status", "achieve", "abandon"]); s.add_argument("name", nargs="?")
    s.add_argument("--title"); s.add_argument("--slice", help="e.g. gsm8k-test/full"); s.add_argument("--target", type=float, help="e.g. 0.96")
    s.add_argument("--kpi", default="score", help="score (default), cost, latency_p50, latency_p95")
    s.add_argument("--lower-is-better", action="store_true"); s.add_argument("--baseline", help="starting champion (default: the champion now)")
    s.add_argument("--problem", help="why this goal matters"); s.add_argument("--reason", help="abandon: why")
    s.add_argument("--note", help="achieve: a line for the record"); s.add_argument("--force", action="store_true", help="achieve without the target met")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_goal)

    s = sp.add_parser("projects", help="the projects one dashboard serves (~/.arx/projects.json)")
    s.add_argument("verb", nargs="?", choices=["ls", "add", "rm"], default="ls"); s.add_argument("path", nargs="?", help="add: project root; rm: key")
    s.set_defaults(fn=cmd_projects)

    s = sp.add_parser("model", help="register a version (candidate, or --champion for the baseline)")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--parent"); s.add_argument("--hill")
    s.add_argument("--no-parent", action="store_true", help="not derived from the champion (e.g. a backfilled run)")
    s.add_argument("--change"); s.add_argument("--title"); s.add_argument("--link", action="append", help="label=url")
    s.add_argument("--status", choices=["candidate", "historical", "planned"], default="candidate")
    s.add_argument("--champion", action="store_true"); s.set_defaults(fn=cmd_model)

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
    s.add_argument("action", choices=["start", "log", "note", "link", "progress", "left", "finish"])
    s.add_argument("id", nargs="?"); s.add_argument("values", nargs="*")
    s.add_argument("--kind", default="experiment"); s.add_argument("--title"); s.add_argument("--description")
    s.add_argument("--model"); s.add_argument("--slice"); s.add_argument("--agent"); s.add_argument("--total", type=int)
    s.add_argument("--parent", help="task id this one sits under (default $ARX_PARENT)")
    s.add_argument("--budget-s", type=float, help="wall-clock seconds")
    s.add_argument("--step", type=int); s.add_argument("--level", default="info"); s.add_argument("--status", default="done")
    s.add_argument("--summary-file", help="JSON merged into the task summary on finish")
    s.set_defaults(fn=cmd_task)

    s = sp.add_parser("paper", help="papers: write-ups served at /papers/<name>; people comment, the agent replies",
                     formatter_class=argparse.RawDescriptionHelpFormatter, description="""verbs:
  new <hill> | new --goal <goal>   copy the worked example to start a paper
  check <name> | --file F          lint against PROTOCOL.md (add --goal for goal papers); exit 1 on errors
  add|edit <name> --file F         publish / republish (open pages update in place)
  ls                               papers with thread counts
  poll [name]                      block until someone waits on the agent; one JSON line per thread
  reply <name> <thread> "text"     answer a thread (--link label=url, --file page.html)
  resolve <name> <thread> [note]   close a thread
  attach <name> --file F           serve a page next to the paper""")
    s.add_argument("verb", choices=["new", "add", "edit", "check", "ls", "poll", "reply", "resolve", "attach"]); s.add_argument("name", nargs="?")
    s.add_argument("comment", nargs="?", help="thread id, for reply / resolve"); s.add_argument("text", nargs="*")
    s.add_argument("--file", dest="file", help="add/edit/check: the paper's HTML; reply/attach: a page to link (widget, poster)")
    s.add_argument("--title"); s.add_argument("--hill"); s.add_argument("--goal", help="new/add/check: the goal paper (public)")
    s.add_argument("--link", help="reply: label=url (url may be #block, /papers/<name>#block, an arx page or https://)")
    s.add_argument("--author", default="agent", help="reply: the name shown on the agent's message")
    s.add_argument("--timeout", type=float, help="poll: give up after this many seconds")
    s.set_defaults(fn=cmd_paper)

    s = sp.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sp.add_parser("serve"); s.add_argument("--port", type=int, default=8890); s.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    if a.cmd == "task" and a.action == "start" and not a.title:
        ap.error("task start needs --title")
    a.fn(a)


if __name__ == "__main__":
    main()
