"""Exercise the live view: copy a project, then replay one of its stored runs item by item through arx2.evaluate.

The copy is a separate project ("Live Demo"); the original ledger is never touched.
usage: python live_replay.py <source project dir> <demo dir> <candidate key> <set key> [seconds per item]
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arx2  # noqa: E402
from arx2.store import Project, register  # noqa: E402
from arx2.view import Views  # noqa: E402

src, dst, model, set_key = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
pace = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src / ".arx2", dst / ".arx2")
p = Project(dst)
p.append("project", name="Live Demo")
register("live-demo", dst)

v = Views(p)
stored = {str(r["id"]): r for r in v.rows(v.latest_run(model, set_key))}
p.append("candidate", key="replay-check", name="Replay Check", parent=v.s["champion"], hill=v.s["candidates"][model].get("hill"),
         change=f"Replays the stored run of {v.s['candidates'][model]['name']} item by item, to exercise the live view. Not a new experiment.",
         predict="Same result as the stored run.")


def run_one(item):
    time.sleep(pace)
    r = stored[item]
    return {"score": r.get("score"), "cost": r.get("cost"), "latency_s": r.get("latency_s"), "error": r.get("error")}


out = arx2.evaluate("replay-check", set_key, run_one, name="Replay eval", workers=2, project=p)
print(json.dumps(out))
