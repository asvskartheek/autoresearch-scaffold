"""Continuous slices (minus ms, minus MB): errored rows and gate tolerances. Run: python3 -m unittest discover tests"""
import json, os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch.core import Project, Task, summarize


def ledger():
    d = Path(tempfile.mkdtemp()) / "bench"
    d.mkdir()
    ladder = [dict(rung="dev", checks=[dict(slice="mem/n12", rule="not_worse", tolerance=0.05)])]
    (d / "research.json").write_text(json.dumps(dict(name="bench", higher_is_better=True, ladder=ladder)))
    p = Project(d)
    p.add_slice("mem/n12", [f"m{i:02d}" for i in range(12)], kind="synthetic", scale="continuous", unit="MB")
    return p


def run(p, model, scores, errors=()):
    t = Task(p, "eval", f"{model} on mem/n12", model=model, slice="mem/n12")
    for i, s in enumerate(scores):
        row = dict(id=f"m{i:02d}", score=0.0 if i in errors else s)
        if i in errors:
            row["error"] = "no PSS"
        t.add_row(row)
    t.finish()
    return t


class Continuous(unittest.TestCase):
    def test_errored_rows_are_not_the_best_score(self):
        p = ledger()
        p.add_model("v0", status="champion")
        t = run(p, "v0", [-160.0] * 12, errors={0, 1})
        s = p.task(t.id)["summary"]
        self.assertEqual((s["n"], s["errors"]), (12, 2))
        self.assertAlmostEqual(s["score"], -160.0)  # not lifted toward 0 by the two failures
        self.assertEqual(len(p.pooled_scores("v0", "mem/n12")), 10)

    def test_binary_errors_still_score_zero(self):
        self.assertAlmostEqual(summarize([dict(id="a", score=1), dict(id="b", score=1, error="x")])["score"], 0.5)

    def test_reference_gates_keep_continuous_units(self):
        from autoresearch import reference
        p = ledger()
        p.add_model("v0", status="champion")
        p.add_model("v1", parent="v0")
        run(p, "v0", [-160.0] * 12)
        run(p, "v1", [-150.0] * 12)
        p.open_goal("lean", "Under 100 MB", "mem/n12", -100.0)
        d = reference.build(p, "v1", cache=False)
        c = d["ladder"][0]["checks"][0]
        # the paper writes the threshold in MB, as a fraction of the champion's mean, never in pts
        self.assertEqual((c["scale"], c["unit"], c["relative"]), ("continuous", "MB", True))
        self.assertAlmostEqual(c["threshold"], -8.0)
        g = d["goals"][0]
        self.assertEqual((g["scale"], g["need"], g["have"]), ("continuous", None, None))  # no "N more of 12" on MB

    def test_tolerance_is_a_fraction_of_the_champion(self):
        p = ledger()
        p.add_model("v0", status="champion")
        p.add_model("v1", parent="v0")
        run(p, "v0", [-160.0] * 12)
        run(p, "v1", [-162.0] * 12)  # 2 MB worse: inside 5% of 160 MB, far outside a raw 0.05
        c = p.gate("v1")["rungs"][0]["checks"][0]
        self.assertEqual(c["state"], "pass")
        self.assertAlmostEqual(c["threshold"], -8.0)
        self.assertTrue(c["relative"])


if __name__ == "__main__":
    unittest.main()
