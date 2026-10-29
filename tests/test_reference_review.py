"""Reference paper fixes from the review: fast goal status, the build cache, labels, clean decisions."""
import json, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch import Project, reference  # noqa: E402
from autoresearch.core import evaluate  # noqa: E402


class ReferenceReview(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "research.json").write_text(json.dumps(dict(name="t", primary_dataset="qa")))
        p = self.p = Project(self.root)
        p.add_dataset("qa", range(40))
        p.add_model("v1", status="champion", change="baseline")
        p.add_model("a+b+c+d+e", parent="v1", change="chain")
        for m, f in [("v1", lambda i: float(int(i) % 2)), ("a+b+c+d+e", lambda i: float(int(i) % 3 != 0))]:
            evaluate(p, m, "qa/full", lambda i, f=f: {"score": f(i)})
        p.open_goal("g", "Get there", "qa/full", 0.9)

    def test_goal_status_matches_core(self):
        ix = reference._Index(self.p)
        for g, rec in self.p.goals().items():
            a, b = self.p.goal_status(g), reference._goal_status(self.p, ix, g, rec, self.p.champion())
            self.assertEqual(set(a), set(b))
            for k in a:
                if isinstance(a[k], dict) and k == "vs_baseline":
                    for j in a[k]:
                        self.assertAlmostEqual(a[k][j] or 0, b[k][j] or 0, places=12)
                else:
                    self.assertEqual(a[k], b[k], k)

    def test_build_is_cached_until_the_ledger_changes(self):
        d1 = reference.build(self.p, "a+b+c+d+e")
        self.assertIs(reference.build(self.p, "a+b+c+d+e"), d1)
        time.sleep(0.01)
        self.p.set_model_status("a+b+c+d+e", "rejected", reason="worse")
        d2 = reference.build(self.p, "a+b+c+d+e")
        self.assertIsNot(d2, d1)
        self.assertEqual(d2["model"]["status"], "rejected")

    def test_decisions_drop_local_paths_and_dict_dumps(self):
        self.p.set_model_status("a+b+c+d+e", "rejected",
                                reason="Failed gate. /Users/me/proj/scratch/x/gate.json {'n': 40, 'delta': 0.025, 'lo': -0.05, 'hi': 0.1}")
        d = reference.build(self.p, "a+b+c+d+e", cache=False)
        why = [x for x in d["decisions"] if x.get("kind") == "rejected"][-1]["reason"]
        self.assertNotIn("/Users", why)
        self.assertIn("gate.json", why)
        self.assertIn("n 40", why)
        self.assertNotIn("{", why)
        self.assertEqual(reference.clean_note("see https://hf.co/datasets/a/b"), "see https://hf.co/datasets/a/b")


if __name__ == "__main__":
    unittest.main()
