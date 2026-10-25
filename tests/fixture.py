"""Synthetic project shaped like a mature research ledger. Every name is invented; the RNG is seeded.

    from fixture import build
    facts = build(Path("/tmp/x"))      # -> dict of names/numbers the tests assert on

It contains: a seeded champion with duplicate champion decisions, 22 rejected models (reason + hill), 65 historical
models, 150 `historical_run` tasks (3 datasets, cohort hashes, dev/random cohorts, variants, dates over a week),
real eval tasks with rows on registered slices, 3 stalled tasks, 7 hills (most with no eval rows).
"""
from __future__ import annotations

import json, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autoresearch.core import Project, Task, _append, _write, ids_hash  # noqa: E402

CHAMPION = "falcon-baseline"
BEST_CORRECT, BEST_N = 50, 60            # best historical run: 50/60 = 83.3%
BEST_SCORE_STR = "83.3"
HILLS = {  # key -> title
    "units": "Unit conversion drift", "legend": "Legend symbols misread", "tiny": "Tiny labels dropped",
    "rotate": "Rotated text confusion", "tables": "Table totals off by one", "multi": "Multi-sheet references",
    "noise": "Scan noise robustness",
}
VARIANTS = ["Orion K3", "Orion K3 · vote=3", "Orion K3 · vote=5", "Lynx 2", "Lynx 2 · crop", "Heron 7", "Heron 7 · zoom"]
DATASETS = {"alpha": 200, "beta": 120, "gamma": 90}
WEEK0 = time.mktime(time.strptime("2026-10-14 09:00", "%Y-%m-%d %H:%M"))


def _task(p: Project, tid: str, **kw) -> dict:
    t0 = kw.pop("t", time.time() - 3600)
    meta = dict(id=tid, kind="experiment", title=tid, description=None, model=None, parent=None, slice=None,
                slice_hash=None, agent=None, status="done", created=t0, updated=t0, heartbeat=t0, ended=t0 + 60,
                progress=dict(done=0, total=None), links={}, config={}, summary={}, host="h", pid=1, command="x",
                budget_s=None) | kw
    _write(p.task_dir(tid) / "task.json", meta)
    return meta


def build(root: Path, seed: int = 7) -> dict:
    rng = random.Random(seed)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((Path(__file__).resolve().parents[1] / "autoresearch" / "templates" / "research.json").read_text())
    cfg |= dict(name="Synthetic Lab", primary_dataset="alpha", final_target="90% accuracy, p50 under 45 s", dashboard_idle_minutes=0)
    (root / "research.json").write_text(json.dumps(cfg, indent=2))
    (root / ".research").mkdir(exist_ok=True)
    p = Project(root)

    ids = {d: [f"{d}-{i:03d}" for i in range(n)] for d, n in DATASETS.items()}
    for d, title in (("alpha", "Alpha drawings"), ("beta", "Beta; NOT the evaluation set"), ("gamma", "Gamma sheets")):
        p.add_dataset(d, ids[d], title=title, description="invented " + d)
    p.random_slices("alpha", (50, 100), seed=3)
    p.add_slice("alpha/dev60", ids["alpha"][:60], kind="dev", description="Frozen dev pool " + "run-on-text-" * 12)
    p.add_slice("alpha/ctl40", ids["alpha"][100:140], kind="control", description="control")
    p.add_slice("beta/dev30", ids["beta"][:30], kind="dev")

    # hills: the first two have real slices with evals, the rest are empty shells
    keys = list(HILLS)
    for i, k in enumerate(keys):
        tgt = "alpha/dev60" if i == 0 else "beta/dev30" if i == 1 else "alpha/random50"
        ctl = "alpha/ctl40" if i == 0 else None
        p.open_hill(k, HILLS[k], tgt, ctl, problem=f"{HILLS[k]}: invented failure mode", symptom=f"symptom {k}",
                    measure="exact match", share=dict(count=10 + i, of=100, of_what="failures"))

    # models
    p.add_model(CHAMPION, parent="", title="Seeded baseline", status="champion", change="baseline")
    for extra in (1, 2):  # duplicate seeding, as happens when a setup script runs twice
        p.log_decision("champion", model=CHAMPION, note=f"seeded as baseline (again {extra})")
    for i in range(22):
        k = f"rej-{i:02d}"
        p.add_model(k, parent=CHAMPION, hill=keys[i % 7], change=f"tweak {i}", status="candidate")
        p.set_model_status(k, "rejected", f"did not beat the champion on {keys[i % 7]} (invented {i})")
    for i in range(65):
        k = f"archive-{rng.getrandbits(32):08x}"
        p.add_model(k, parent="", status="historical", hill=keys[i % 7] if i % 4 == 0 else None, change="imported")
    p.add_model("cand-good", parent=CHAMPION, hill="units", change="better units", title="Good candidate")
    p.add_model("cand-bad", parent=CHAMPION, hill="units", change="worse units", title="Bad candidate")

    # real eval tasks with rows: champion and two candidates on the hill's slices
    def run_eval(model, sl, acc, base=None):
        t = Task(p, "eval", f"{model} on {sl}", model=model, slice=sl)
        sid = p.slice(sl)["ids"]
        for i in sid:
            ok = (base[i] if base else rng.random() < acc)
            t.add_row(dict(id=i, score=1.0 if ok else 0.0, latency_s=round(rng.uniform(5, 50), 1), cost=0.01))
        t.progress(len(sid))
        t.finish()
        return {i: None for i in sid}

    sl_tgt, sl_ctl = "alpha/dev60", "alpha/ctl40"
    tgt_ids, ctl_ids = p.slice(sl_tgt)["ids"], p.slice(sl_ctl)["ids"]
    base_t = {i: rng.random() < 0.55 for i in tgt_ids}
    good_t = {i: base_t[i] or rng.random() < 0.3 for i in tgt_ids}
    bad_t = {i: base_t[i] and rng.random() < 0.8 for i in tgt_ids}
    base_c = {i: rng.random() < 0.6 for i in ctl_ids}
    for m, tg in ((CHAMPION, base_t), ("cand-good", good_t), ("cand-bad", bad_t)):
        run_eval(m, sl_tgt, 0, base=tg)
        run_eval(m, sl_ctl, 0, base=base_c)
    run_eval(CHAMPION, "alpha/random50", 0.62)

    # historical runs: 150 imported, no rows, no slice
    cohorts = [("alpha", "Development 60", 60), ("alpha", "Random 120", 120), ("beta", "All 120", 120),
               ("gamma", "All 90", 90), ("alpha", "Tiny 12", 12)]
    chash = {c: f"{rng.getrandbits(40):010x}" for c in cohorts}
    arch = [k for k, m in p.models().items() if m["status"] == "historical"]
    for i in range(150):
        coh = cohorts[0] if i < 40 else rng.choice(cohorts)
        variant = rng.choice(VARIANTS)
        if i == 77:
            coh = cohorts[0]
        ds, label, n = coh
        correct = rng.randint(int(n * .5), int(n * .78)) if n > 12 else rng.randint(3, 8)
        if i == 77:
            correct = BEST_CORRECT
        date = time.strftime("%Y-%m-%d %H:%M", time.localtime(WEEK0 + i * 3600 * 168 / 150))
        base = variant.split(" · ")[0]
        tid = f"hist-{i:03d}"
        _task(p, tid, kind="historical_run", title=f"{variant} · {label}", model=rng.choice(arch), t=WEEK0 + i * 100,
              summary=dict(n=n, correct=correct, errors=0, score=correct / n, cost=0.05, latency_p50=round(rng.uniform(30, 60), 1),
                           latency_p95=90.0, dataset=ds, cohort_hash=chash[coh],
                           registered_slice=None, evidence="invented", catalog_record=dict(model=base, agent="agent-x", cohort_label=label, date=date)))
    # stalled
    for i in range(3):
        _task(p, f"stalled-{i}", title=f"Stalled job {i}", status="running", t=time.time() - 7200, ended=None,
              progress=dict(done=3, total=10))
    # a running task that is alive
    _task(p, "live-0", title="Live job", status="running", t=time.time(), ended=None, progress=dict(done=1, total=10))
    return dict(root=root, champion=CHAMPION, best=BEST_SCORE_STR, hill_key="units", hill_title=HILLS["units"],
                empty_hill_key="legend", empty_hill_title=HILLS["legend"], rejected="rej-03", n_hist_models=65,
                n_hist_runs=150, model_key="cand-good", task_hist="hist-005", task_eval=p.evals()[0]["id"])


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
