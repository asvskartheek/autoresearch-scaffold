"""Questions view text: goals in their slice's units, readable model labels, seeded titles that read as questions."""
import json, os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import questions as q
from autoresearch.core import Project, Task


def ledger():
    d = Path(tempfile.mkdtemp()) / "qunits"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="qunits", higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(20)))
    return p


def run(p, model, scores, slice="ds/full", latency=None):
    t = Task(p, "eval", f"{model} on {slice}", model=model, slice=slice)
    for i, s in enumerate(scores):
        t.add_row(dict(id=p.slice(slice)["ids"][i], score=s, latency_s=latency))
    t.finish()
    return t


class GoalUnits(unittest.TestCase):
    def test_continuous_negated_goal_reads_in_ms(self):
        p = ledger()
        p.add_slice("ds/cold", list(range(4)), scale="continuous", unit="ms", metric="minus ms to first paint")
        p.add_model("v0", parent="", status="champion", title="Launcher as shipped")
        run(p, "v0", [-1400, -1500, -1450, -1482], "ds/cold")
        p.open_goal("fast", "Home appears in under a second", "ds/cold", -1000.0)
        t = q.tree(p)
        g = t["goals"]["fast"]
        self.assertEqual((g["value_txt"], g["target_txt"], g["gap_txt"]), ("1,458 ms", "at most 1,000 ms", "458 ms to go"))
        claim = {n["id"]: n for n in t["nodes"]}["g:fast"]["claim"]
        self.assertEqual(claim, "Launcher as shipped: 1,458 ms; target at most 1,000 ms.")

    def test_latency_kpi_reads_in_seconds_and_met_has_no_gap(self):
        p = ledger()
        p.add_model("base", parent="", status="champion")
        run(p, "base", [1] * 20, latency=13.0)
        p.open_goal("lat", "P&ID median latency at 45 s", "full", 45.0, kpi="latency_p50")
        g = q.tree(p)["goals"]["lat"]
        self.assertEqual((g["value_txt"], g["target_txt"]), ("13 s", "at most 45 s"))
        self.assertNotIn("gap_txt", g)

    def test_count_goal_reads_as_count_with_percent_in_brackets(self):
        p = ledger()
        p.add_model("base", parent="", status="champion")
        run(p, "base", [1] * 14 + [0] * 6)
        p.open_goal("ninety", "GSM8K at 90%", "full", 0.9)
        g = q.tree(p)["goals"]["ninety"]
        self.assertEqual((g["value_txt"], g["target_txt"], g["gap_txt"]), ("14 of 20", "18 of 20 (90%)", "4 more of 20"))


if __name__ == "__main__":
    unittest.main()
