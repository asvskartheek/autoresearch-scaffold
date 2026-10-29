"""goal_status carries the slice's scale and unit, so a continuous goal reads in ms, not as a count of n."""
import json, os, tempfile, unittest
from pathlib import Path

os.environ.setdefault("ARX_HOME", tempfile.mkdtemp())
from autoresearch.core import Project, Task


def ledger():
    d = Path(tempfile.mkdtemp()) / "u"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="u", higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("cold", list(range(4)))
    return p


class GoalUnitsTest(unittest.TestCase):
    def test_continuous_goal_has_scale_and_unit(self):
        p = ledger()
        p.add_slice("cold/n4", list(range(4)), kind="synthetic", metric="minus ms to paint", scale="continuous", unit="ms")
        p.add_model("v0", status="champion")
        p.add_model("v1")
        p.open_goal("fast", "Fast", "cold/n4", -1000.0, baseline="v0")
        for m, v in (("v0", -1500.0), ("v1", -900.0)):
            t = Task(p, "eval", f"{m} on cold/n4", model=m, slice="cold/n4")
            for i in range(4):
                t.add_row(dict(id=str(i), score=v + i))
            t.finish()
        p.set_model_status("v1", "champion")
        p.set_model_status("v0", "rejected")
        st = p.goal_status("fast")
        self.assertEqual((st["scale"], st["unit"], st["metric"]), ("continuous", "ms", "minus ms to paint"))
        self.assertAlmostEqual(st["vs_baseline"]["delta"], 600.0)
        self.assertTrue(st["met"])

    def test_binary_goal_defaults(self):
        p = ledger()
        p.add_model("v0", status="champion")
        p.open_goal("acc", "Acc", "cold/full", 0.9)
        st = p.goal_status("acc")
        self.assertEqual((st["scale"], st["unit"]), ("binary", None))


if __name__ == "__main__":
    unittest.main()
