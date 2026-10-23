"""`arx run`: launch a reviewed command from a manifest and record what it produced.

The manifest is JSON, pinned by its sha256 so what runs is exactly what was reviewed:

    {"title": "...", "description": "...", "argv": ["python", "run_eval.py", "--out", "out/rows.jsonl"],
     "cwd": ".", "deadline_s": 1800, "record_mode": "scored", "rows_path": "out/rows.jsonl",
     "frozen_inputs": [{"path": "data/questions.json", "sha256": "..."}],
     "paid": false, "budget_usd": 0, "artifacts": [{"label": "Outputs", "path": "out/"}]}

`record_mode` is "scored" (the command writes rows.jsonl for a slice; ids are checked against it) or
"artifact_only" (no score is recorded; process success is not a score).
"""
import hashlib
import json
import math
import os
import signal
import subprocess
import time
from pathlib import Path

from .core import Project, Task


def _inside(p: Project, rel: str, what: str) -> Path:
    path = (p.root / rel).resolve()
    if not path.is_relative_to(p.root.resolve()):
        raise SystemExit(f"{what} must stay inside the project")
    return path


def _number(v) -> bool:
    return type(v) in (int, float) and math.isfinite(v)


def check_manifest(p: Project, path: Path, expected_sha: str, model: str | None, slice: str | None,
                   approve_paid: bool) -> dict:
    """Validate everything before anything runs. Returns the parsed manifest plus resolved paths."""
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != expected_sha:
        raise SystemExit(f"manifest hash is {sha}, expected {expected_sha}; nothing executed")
    m = json.loads(data)
    argv = m.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise SystemExit("argv must be a non-empty list of strings (no shell strings)")
    for src in m.get("frozen_inputs", []):
        if hashlib.sha256(_inside(p, src["path"], "frozen input").read_bytes()).hexdigest() != src["sha256"]:
            raise SystemExit(f"frozen input changed: {src['path']}")
    if m.get("paid"):
        cap = p.config.get("max_paid_usd")
        budget = float(m.get("budget_usd", 0))
        if not approve_paid:
            raise SystemExit("paid manifest: review it, then pass --approve-paid")
        if not budget > 0 or (cap is not None and budget > cap):
            raise SystemExit(f"paid manifest needs budget_usd in (0, {cap or 'inf'}]")
    mode = m.get("record_mode", "artifact_only")
    if mode not in ("artifact_only", "scored"):
        raise SystemExit(f"unknown record_mode {mode}")
    deadline = float(m.get("deadline_s", 1800))
    if not math.isfinite(deadline) or deadline <= 0:
        raise SystemExit("deadline_s must be finite and positive")
    rows_path = None
    if mode == "scored":
        if not model or not slice:
            raise SystemExit("scored runs need --model and --slice")
        p.slice(slice)
        rows_path = _inside(p, m["rows_path"], "rows_path")
        if rows_path.exists():
            raise SystemExit(f"{m['rows_path']} already exists; remove it so stale rows are not scored")
    return m | dict(sha=sha, raw=data, mode=mode, deadline=deadline, rows_path=rows_path,
                    cwd=_inside(p, m.get("cwd", "."), "cwd"))


def _run(t: Task, m: dict) -> tuple[int | None, bool, str | None]:
    """Run argv in its own process group with a wall-clock deadline. Output goes to the task dir, not rows."""
    t0, timed_out = time.monotonic(), False
    try:
        with (t.dir / "stdout.private.log").open("w") as out, (t.dir / "stderr.private.log").open("w") as err:
            proc = subprocess.Popen(m["argv"], cwd=m["cwd"], env=os.environ | {"ARX_PARENT": t.id},
                                    stdout=out, stderr=err, start_new_session=True)
            while proc.poll() is None:
                t.heartbeat()
                if time.monotonic() - t0 > m["deadline"]:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                    break
                time.sleep(0.5)
            return proc.wait(), timed_out, None
    except Exception as e:
        t.note(f"launch failed: {type(e).__name__}", "error")
        return None, timed_out, type(e).__name__


def _collect_rows(p: Project, t: Task, slice: str, rows_path: Path) -> tuple[int, bool]:
    """Read the command's rows against the slice. Bad, duplicate or missing ids become score-0 error rows."""
    want, got, bad = {str(i) for i in p.slice(slice)["ids"]}, {}, False
    lines = rows_path.read_text().splitlines() if rows_path.exists() else []
    for line in filter(str.strip, lines):
        try:
            r = json.loads(line)
            key = str(r["id"])
        except (ValueError, KeyError, TypeError):
            bad = True
            continue
        if key not in want or key in got:
            bad = True
            continue
        row = {k: r[k] for k in ("score", "cost", "latency_s") if k in r} | {"id": key}
        for k in ("cost", "latency_s"):
            if k in row and row[k] is not None and not (_number(row[k]) and row[k] >= 0):
                row[k], bad = None, True
        if r.get("error"):
            row |= dict(score=0, error="harness_error")
        elif not (_number(row.get("score")) and 0 <= row["score"] <= 1):
            row, bad = row | dict(score=0, error="invalid_score"), True
        got[key] = row
    if bad:
        t.note("output had malformed, unexpected or duplicate rows; they were dropped", "error")
    for key in sorted(want):
        t.add_row(got.get(key, dict(id=key, score=0, error="missing_output")))
    t.progress(len(want), len(want))
    return len(got), bad or set(got) != want


def run_manifest(a):
    p = Project()
    if not a.manifest or not a.expected_sha256:
        raise SystemExit("run needs --manifest and --expected-sha256")
    path = Path(a.manifest).resolve()
    m = check_manifest(p, path, a.expected_sha256, a.model, a.slice, a.approve_paid)
    if a.dry_run:
        print(json.dumps(dict(status="validated", manifest_sha256=m["sha"], mode=m["mode"], paid=bool(m.get("paid")),
                              argv=m["argv"])))
        return
    scored = m["mode"] == "scored"
    t = Task(p, "eval" if scored else "experiment", a.title or m.get("title") or " ".join(m["argv"])[:80],
             a.description or m.get("description"), model=a.model, slice=a.slice if scored else None, agent=a.agent)
    t.link("Manifest", str(path))
    for ref in m.get("artifacts", []):
        t.link(ref.get("label", "Artifact"), str(_inside(p, ref["path"], "artifact")))
    (t.dir / "manifest.json").write_bytes(m["raw"])
    t0 = time.monotonic()
    code, timed_out, exc = _run(t, m)
    failed = timed_out or exc is not None or code != 0
    summary = dict(exit_code=code, timed_out=timed_out, wall_s=round(time.monotonic() - t0, 1), manifest_sha256=m["sha"])
    if scored:
        observed, bad = _collect_rows(p, t, a.slice, m["rows_path"])
        failed |= bad
        summary["observed"] = observed
    else:
        t.note("artifact-only run; no score recorded")
    t.finish("failed" if failed else "done", summary=summary)
    print(json.dumps(dict(task=t.id, status=t.meta["status"], summary=t.meta.get("summary", {}))))
    if failed:
        raise SystemExit(1)
