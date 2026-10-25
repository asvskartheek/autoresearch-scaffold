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


def _up(root: Path, port: int, restart: bool = False) -> str:
    """Start the dashboard detached (idempotent); its port and pid are kept in .research/server.json."""
    info = root / ".research" / "server.json"
    if info.exists():
        old = json.loads(info.read_text())
        if old.get("port") and _port_open(old["port"]):
            if not restart:
                return f"http://127.0.0.1:{old['port']}"
            if old.get("pid"):
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
    print(_up(Project().root, a.port, a.restart))


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
        p.explain_hill(a.name, **explainer)
        return print(f"hill {a.name} explained")
    if not (a.title and a.target):
        raise SystemExit("arx hill open needs --title and --target")
    h = p.open_hill(a.name, a.title, a.target, a.control, a.problem, a.found_in, **explainer)
    print(f"hill {a.name} open: target {h['target']}, control {h.get('control')}")


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
        print(f"every rung passed: `arx promote {a.model}` (then baselines it on every hill; see `arx promote -h`)")


def cmd_promote(a):
    p = Project()
    p.promote(a.model, a.force)
    print(f"{a.model} is champion")
    if a.no_baseline:
        return print("skipped baselining; run `arx baseline` to cover every hill")
    print("baselining the new champion on every hill (reuses runs it already has; `arx promote -h` explains)")
    _baseline(p, a.model)


def _baseline(p, model, dry=False):
    """Establish the new champion's baseline on every hill: reuse the runs it already has, run the rest with
    `baseline_cmd` from research.json (placeholders {model} {slice}); without one, list what to run."""
    plan, cmd, slices = p.baseline_plan(model), p.config.get("baseline_cmd"), p.slices()
    print(f"baseline for {model}: {len(plan['have'])} of {len(plan['roles'])} slices already run, {len(plan['need'])} to run")
    what = lambda sl: ", ".join(plan["roles"][sl])
    for sl, h in plan["have"].items():
        print(f"  reused   {sl:<28} {_fmt(h['score'], False)}  n={h['n']}  {what(sl)}  ({h['task']})")
    for sl in plan["need"]:
        print(f"  {'run' if cmd and not dry else 'missing':<8} {sl:<28} n={slices[sl]['n']}  {what(sl)}")
    if not plan["need"] or dry:
        return plan
    if not cmd:
        print('to run these automatically, set "baseline_cmd" in research.json, e.g. '
              '"python eval.py --model {model} --slice {slice}"; or run each with arx.evaluate / arx run')
        return plan
    with Task(p, "baseline", f"Baseline {model}", f"Run champion {model} on every hill and dataset slice it has no "
              f"complete run on ({len(plan['need'])}); {len(plan['have'])} existing runs reused.", model=model,
              total=len(plan["need"]), config=dict(baseline_cmd=cmd)) as t:
        for i, sl in enumerate(plan["need"]):
            t.check()
            t.note(f"{sl} ({what(sl)}): running")
            r = subprocess.run(cmd.format(model=model, slice=sl), shell=True, cwd=p.root)
            if r.returncode:
                t.note(f"{sl}: baseline_cmd exited {r.returncode}", "error")
            t.progress(i + 1)
        after = p.baseline_plan(model)
        t.note(f"still missing: {', '.join(after['need'])}" if after["need"] else f"every slice has a {model} baseline",
               "warn" if after["need"] else "info")
        t.meta["summary"] = dict(reused=len(plan["have"]), ran=len(plan["need"]) - len(after["need"]), missing=len(after["need"]))
    print(f"still missing: {', '.join(after['need'])} (baseline_cmd must record a complete eval for {{model}} on {{slice}})"
          if after["need"] else f"done: {model} has a baseline on all {len(after['roles'])} slices")
    return after


def cmd_baseline(a):
    p = Project()
    plan = _baseline(p, a.model or p.champion() or sys.exit("no champion"), a.dry_run)
    if plan["need"]:
        sys.exit(3)  # scripts can tell "baseline complete" (0) from "slices still missing" (3)


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
    champ = p.champion()
    print(f"{p.config.get('name')} · champion {champ}")
    if champ:
        b = p.baseline_plan(champ)
        print(f"  baseline {len(b['have'])}/{len(b['roles'])} slices" + (f"; missing {', '.join(b['need'])} (`arx baseline`)" if b["need"] else ""))
    for t in p.tasks():
        if t["status"] in ("running", "stalled"):
            pr = t.get("progress") or {}
            print(f"  [{t['status']}] {t['id']} {t['title']} {pr.get('done')}/{pr.get('total')}")
    for name, m in p.models().items():
        if m.get("status") == "candidate":
            g = p.gate(name)
            print(f"  candidate {name}: " + " → ".join(f"{r['rung']}:{r['status']}" for r in g["rungs"]))
    for name, h in p.hills().items():
        print(f"  hill {name} [{h['status']}] {h['title']}")


def cmd_serve(a):
    from .server import serve
    serve(a.port)


PROMOTE_NOTES = """what happens after the champion changes:
  The new champion is baselined on every hill so each one has a current number to beat (same as `arx baseline`):
    slices   every hill's target and control slice, plus the dataset's full and random slices
    reused   a slice the model already ran as a candidate keeps that run: nothing is re-run (printed as "reused")
    run      slices with no complete run at the slice's current hash run `baseline_cmd` from research.json,
             e.g. "python eval.py --model {model} --slice {slice}", under one "Baseline <model>" task
    unset    without baseline_cmd the missing slices are only listed: run them with arx.evaluate / arx run
  Skip with --no-baseline; repeat any time with `arx baseline` (only missing slices run). The ledger records a
  `baseline` decision (slices reused, slices still needed) in .research/decisions.jsonl.
"""

WORKFLOW = """workflow:
  setup      arx init -> arx dataset add -> arx slice add (dev/control) -> arx model add NAME --champion
  per hill   arx hill open + arx hill explain -> arx model add CAND --hill H -> arx gate CAND (follow "next runs",
             run them with arx.evaluate / arx run, repeat) -> arx promote CAND  (or arx reject CAND --reason ...)
  after      arx promote re-baselines the new champion on every hill (arx baseline; set baseline_cmd in research.json)
  any time   arx status, arx up (dashboard), arx task start/note/finish (log any work longer than a minute)
"""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arx", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="Auto-research ledger, gate ladder and live dashboard. `arx <command> -h` for details.",
                                 epilog=WORKFLOW)
    sp = ap.add_subparsers(dest="cmd", required=True, metavar="command")
    _add = sp.add_parser
    sp.add_parser = lambda name, help=None, **kw: _add(name, help=help, description=help, **kw)  # `arx X -h` shows it too

    s = sp.add_parser("init", help="create research.json and .research/ in a folder, open the setup task, start the dashboard"); s.add_argument("path", nargs="?", default=".", help="project folder (default .)"); s.add_argument("--name", help="project name shown in the dashboard")
    s.add_argument("--port", type=int, default=8890, help="dashboard port"); s.add_argument("--no-serve", action="store_true", help="do not start the dashboard"); s.set_defaults(fn=cmd_init)
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
    s.set_defaults(fn=cmd_hill)

    s = sp.add_parser("model", help="register a version (candidate, or --champion for the baseline)")
    s.add_argument("verb", choices=["add"]); s.add_argument("name"); s.add_argument("--parent"); s.add_argument("--hill")
    s.add_argument("--no-parent", action="store_true", help="not derived from the champion (e.g. a backfilled run)")
    s.add_argument("--change"); s.add_argument("--title"); s.add_argument("--link", action="append", help="label=url")
    s.add_argument("--status", choices=["candidate", "historical", "planned"], default="candidate")
    s.add_argument("--champion", action="store_true"); s.set_defaults(fn=cmd_model)

    s = sp.add_parser("reject", help="keep a failed candidate in the ledger as rejected, with the reason"); s.add_argument("name", help="model name"); s.add_argument("--reason", required=True, help="why it failed, with the numbers"); s.set_defaults(fn=cmd_reject)
    s = sp.add_parser("gate", help="where a candidate is on the ladder, and what to run next")
    s.add_argument("model"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_gate)
    s = sp.add_parser("promote", help="make a candidate champion once every rung passes, then baseline it on all hills (see `arx baseline`)"); s.add_argument("model"); s.add_argument("--force", action="store_true", help="promote even if a rung has not passed (recorded in the ledger)")
    s.add_argument("--no-baseline", action="store_true", help="skip the automatic baselining; run `arx baseline` later")
    s.epilog = PROMOTE_NOTES; s.formatter_class = argparse.RawDescriptionHelpFormatter
    s.set_defaults(fn=cmd_promote)

    s = sp.add_parser("baseline", help="baseline the champion on all hills: reuse its runs, run the rest via `baseline_cmd` (auto after promote)")
    s.add_argument("model", nargs="?", help="default: the current champion")
    s.epilog = ("covers every hill target/control plus the full/random slices. Runs it already has are reused; each other\n"
                "slice runs `baseline_cmd` from research.json ({model} and {slice} filled in, run from the project root).\n"
                "Without baseline_cmd the missing slices are only listed. Safe to repeat.\n"
                "exit status: 0 when every slice has a baseline, 3 when some are still missing.")
    s.formatter_class = argparse.RawDescriptionHelpFormatter; s.add_argument("--dry-run", action="store_true", help="print the plan, run nothing"); s.set_defaults(fn=cmd_baseline)

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

    s = sp.add_parser("status", help="champion, running tasks, each candidate's ladder position, open hills"); s.set_defaults(fn=cmd_status)
    s = sp.add_parser("serve", help="run the dashboard in the foreground (`arx up` runs it in the background)"); s.add_argument("--port", type=int, default=8890, help="dashboard port"); s.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    if a.cmd == "task" and a.action == "start" and not a.title:
        ap.error("task start needs --title")
    a.fn(a)


if __name__ == "__main__":
    main()
