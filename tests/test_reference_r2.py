"""Reference paper, round 2: a promoted model's ladder is its promotion gate, and later runs are marked against it."""
import json, tempfile, time, unittest
from pathlib import Path

from autoresearch import Project, reference
from autoresearch.core import evaluate

LADDER = [dict(rung="full", checks=[dict(slice="full", rule="better", margin=0.0)])]


class Promotion(unittest.TestCase):
    def test_ladder_is_the_promotion_gate_and_later_runs_show_against_it(self):
        root = Path(tempfile.mkdtemp())
        (root / "research.json").write_text(json.dumps(dict(name="t", ladder=LADDER)))
        p = Project(root)
        p.add_dataset("qa", range(10))
        p.add_model("v1", status="champion")
        p.add_model("v2", parent="v1")
        evaluate(p, "v1", "qa/full", lambda i: {"score": float(int(i) < 5)})
        evaluate(p, "v2", "qa/full", lambda i: {"score": float(int(i) < 8)})
        p.promote("v2", baseline=False)
        time.sleep(0.01)
        evaluate(p, "v2", "qa/full", lambda i: {"score": float(int(i) < 7)})  # a later run moves the pool
        d = reference.build(p, "v2", cache=False)
        self.assertEqual(d["promotion"]["replaced"], "v1")
        c = d["ladder"][0]["checks"][0]
        self.assertAlmostEqual(c["delta"], 0.3); self.assertEqual(c["cand_runs"], 1)
        r = next(x for x in d["results"] if x["slice"] == "qa/full")
        self.assertAlmostEqual(r["vs"]["delta"], 0.25); self.assertEqual(r["right"], 7.5)
        self.assertAlmostEqual(r["at_promotion"]["delta"], 0.3)


if __name__ == "__main__":
    unittest.main()
