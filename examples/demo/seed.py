"""Seed a demo project with a plausible history: v5 → v6 → v7 champions, a politeness hill, v8 climbing.

    python examples/demo/seed.py /tmp/ar-demo && cd /tmp/ar-demo && ../path/to/ar serve
Scores are simulated; nothing here calls a model.
"""
import json, random, shutil, sys, time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]))
from autoresearch.cli import main as ar
from autoresearch.core import Project, Task, _read, _write

root = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-project").resolve()
if root.exists():
    shutil.rmtree(root)
ar(["init", str(root), "--name", "QA agent · politeness"])
import os; os.chdir(root)
p = Project(root)

# Per-example difficulty is shared across models so paired comparisons behave like real ones.
rng = random.Random(7)
diff = {}
def d(i): return diff.setdefault(i, rng.random())
SKILL = {  # model -> slice kind -> skill; difficulty is shared, so a higher skill solves a superset
    "v5": dict(full=.58, please=.50, long=.40, hop=.45, control=.58),
    "v6": dict(full=.64, please=.52, long=.62, hop=.47, control=.64),
    "v7": dict(full=.71, please=.50, long=.63, hop=.68, control=.71),
    "v8": dict(full=.74, please=.82, long=.64, hop=.69, control=.72),
    "v8b": dict(full=.72, please=.85, long=.48, hop=.68, control=.71),
}
KIND = {"qa/dev-please": "please", "qa/dev-longctx": "long", "qa/dev-multihop": "hop", "qa/dev-control": "control"}

def rows_for(model, slice_name):
    s = p.slice(slice_name)
    k = KIND.get(slice_name, "full")
    out = []
    for i in s["ids"]:
        r = random.Random(f"{model}:{i}")
        ok = (d(i) < SKILL[model][k]) != (r.random() < .01)  # 1% run-to-run flips
        out.append(dict(id=i, score=1.0 if ok else 0.0, cost=round(r.uniform(.002, .006), 5),
                        latency_s=round(r.lognormvariate(1.6, .5), 2), error="timeout" if r.random() < .01 else None))
    return out

t0 = time.time() - 9 * 86400
clock = [t0]
def backdate(task, hours):
    """Move a finished task into the past so the archive reads like a real week."""
    start = clock[0]; clock[0] += hours * 3600
    m = _read(task.dir / "task.json")
    m.update(created=start, ended=clock[0], updated=clock[0], heartbeat=clock[0])
    _write(task.dir / "task.json", m)

def run_eval(model, slice_name, hours=0.4, note=None):
    t = Task(p, "eval", f"{model} on {slice_name.split('/')[-1]}", model=model, slice=slice_name,
             agent=f"eval-{model}", config=dict(workers=8, judge="rubric-v2"))
    rs = rows_for(model, slice_name)
    acc = 0
    for n, r in enumerate(rs, 1):
        t.add_row(r); acc += r["score"] if not r["error"] else 0
        if n % max(1, len(rs) // 40) == 0 or n == len(rs):
            t.log(step=n, running_score=acc / n, latency_s=r["latency_s"])
    t.progress(len(rs))
    if note: t.note(note)
    t.finish()
    backdate(t, hours)
    return t

ar(["dataset", "add", "qa", "--size", "600", "--title", "QA eval", "--url", "https://huggingface.co/datasets/your-org/qa-eval",
    "--description", "Full held-out evaluation set"])
# ids from --size are 0..599
full = p.slice("qa/full")["ids"]
pick = random.Random(3)
p.add_slice("qa/dev-control", pick.sample(full, 20), kind="control", description="Random 20 shown with every dev slice")
p.add_slice("qa/dev-longctx", pick.sample(full, 30), kind="dev", description="Questions with > 12k tokens of context")
p.add_slice("qa/dev-multihop", pick.sample(full, 30), kind="dev", description="Answers need two or more documents")
p.add_slice("qa/dev-please", [f"please-{i:03d}" for i in range(40)], kind="synthetic", metric="1 if the answer with and without 'please' agree and are correct",
            description="40 paired prompts with politeness markers", url="https://huggingface.co/datasets/your-org/qa-please-probes")

# v5 baseline
p.add_model("v5", parent="", change="Baseline agent", status="champion")
for s in ("qa/full", "qa/random100", "qa/random50", "qa/dev-control", "qa/dev-longctx"):
    run_eval("v5", s, 1.5 if s.endswith("full") else .3)
# v6 climbs long-context
p.open_hill("long-context", "Long context", "qa/dev-longctx", "qa/dev-control", "v5 loses facts beyond 12k tokens. Expect +15 pts on dev-longctx, flat elsewhere.", "v5")
p.add_model("v6", parent="v5", hill="long-context", change="Chunked retrieval with re-ranking before answering")
for s in ("qa/dev-longctx", "qa/dev-control", "qa/random50", "qa/random100", "qa/full"):
    run_eval("v6", s, 1.5 if s.endswith("full") else .3)
p.promote("v6")
# v7 climbs multi-hop
run_eval("v6", "qa/dev-multihop")
p.open_hill("multi-hop", "Multi-hop", "qa/dev-multihop", "qa/dev-control", "v6 stops after the first document. Expect +10 pts on dev-multihop.", "v6")
p.add_model("v7", parent="v6", hill="multi-hop", change="Plan-then-retrieve loop, up to 3 hops")
for s in ("qa/dev-multihop", "qa/dev-control", "qa/dev-longctx", "qa/random50", "qa/random100", "qa/full"):
    run_eval("v7", s, 1.5 if s.endswith("full") else .3)
p.promote("v7")

# The goal the next hills serve, then the politeness hill, found in v7
p.open_goal("qa-75", "QA accuracy at 75%", "qa/full", 0.75)
t = Task(p, "analysis", "v7 error analysis: politeness flips", "Paired prompts with and without 'please' disagree on 23% of examples.", model="v7")
t.note("Clustered 140 full-set failures; 31 involve a politeness marker.")
t.note("Built 40 synthetic paired probes; v7 agrees and is correct on 52%.")
t.link("Probe set", "https://huggingface.co/datasets/your-org/qa-please-probes")
t.finish(); backdate(t, 2)
run_eval("v7", "qa/dev-please")
p.open_hill("please-robust", "Politeness robustness", "qa/dev-please", "qa/dev-control",
            "Adding 'please' changes v7's answer. Expect +20 pts on dev-please; no other slice should move.", "v7", goal="qa-75")
p.explain_hill("please-robust", symptom="Adding 'please' to a question changes v7's answer.",
               measure="1 if the answer with and without 'please' agree and are correct",
               examples=[{"input": "Please, what year did the Berlin Wall fall?", "wrong": "1991",
                          "right": "1989", "why": "the politeness marker pulls attention off the retrieved passage"}],
               share={"count": 31, "of": 140, "of_what": "v7's wrong answers on full"})

# v8b: fixes politeness but breaks long-context → stops at dev
p.add_model("v8b", parent="v7", hill="please-robust", change="Strip politeness tokens in the system prompt")
for s in ("qa/dev-please", "qa/dev-control", "qa/dev-longctx", "qa/dev-multihop"):
    run_eval("v8b", s)
p.set_model_status("v8b", "rejected", "Regressed long-context by 15 pts: prompt rewrite drops the retrieved-chunk header.")

# v8: politeness augmentation; passed dev and random50. random100 runs live in live.py.
p.add_model("v8", parent="v7", hill="please-robust", change="SFT on 4k politeness-augmented pairs",
            links={"Model": "https://huggingface.co/your-org/qa-agent-v8", "Train data": "https://huggingface.co/datasets/your-org/please-aug-4k"})
tr = Task(p, "train", "SFT v8 · politeness pairs", "LoRA r=16 on v7, 4k augmented pairs, 2 epochs.", model="v8", agent="trainer-v8",
          config=dict(lr=2e-4, lora_r=16, epochs=2, batch=32))
r = random.Random(1)
for step in range(0, 500, 5):
    tr.log(step=step, loss=2.1 * (0.985 ** step) + 0.35 + r.uniform(-.03, .03), lr=2e-4 * min(1, step / 50) * (1 - step / 520),
           grad_norm=1.4 * (0.995 ** step) + r.uniform(0, .2))
tr.link("Checkpoint", "https://huggingface.co/your-org/qa-agent-v8")
tr.finish(); backdate(tr, 3)
for s in ("qa/dev-please", "qa/dev-control", "qa/dev-longctx", "qa/dev-multihop", "qa/random50"):
    run_eval("v8", s)
print(f"seeded {root}")
