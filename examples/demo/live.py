"""Keep the demo's Workbench busy: v8 evaluating on random100, v9 training, a probe-generation job.

    cd demo-project && python ../examples/demo/live.py
"""
import random, sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import autoresearch as ar

p = ar.project()


def run_one(i):
    r = random.Random(f"v8:{i}")
    time.sleep(r.uniform(.5, 3))
    return dict(score=float(r.random() < .71), cost=round(r.uniform(.002, .006), 5))


def train():
    with ar.task("train", "SFT v9 · politeness + long-context mix", model="v9", agent="trainer-v9",
                 description="LoRA r=32 on v8 with long-context replay to protect the climbed hill.",
                 config=dict(lr=1e-4, lora_r=32, epochs=3, batch=32), total=1500) as t:
        r = random.Random(2)
        for step in range(0, 1500, 5):
            t.log(step=step, loss=2.3 * (0.993 ** step) + .3 + r.uniform(-.04, .04),
                  lr=1e-4 * min(1, step / 100) * (1 - step / 1600), grad_norm=1.6 * (0.997 ** step) + r.uniform(0, .25),
                  **({"dev_please": .55 + .3 * (1 - 0.996 ** step) + r.uniform(-.02, .02)} if step % 100 == 0 else {}))
            t.progress(step + 5)
            if step % 250 == 0:
                t.note(f"checkpoint step {step}")
            time.sleep(.8)


def probes():
    with ar.task("data", "Politeness probes v2", description="Generating 200 paired probes across 5 politeness markers.",
                 total=200, agent="data-gen") as t:
        for n in range(1, 201):
            t.progress(n)
            t.log(step=n, kept_ratio=.8 + random.uniform(-.05, .05))
            time.sleep(2.5)


threading.Thread(target=train, daemon=True).start()
threading.Thread(target=probes, daemon=True).start()
ar.evaluate("v8", "random100", run_one, workers=3, agent="eval-v8",
            description="Rung 3 of 4 for v8. Champion v7 scored on the same 100 ids.")
print(ar.gate("v8")["rungs"])
while threading.active_count() > 1:
    time.sleep(1)
