"""The paper (complete reference): built from the ledger alone, for any project. `python -m pytest tests/test_reference.py`"""
import json, random, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch import Project, features, reference  # noqa: E402
from autoresearch.core import evaluate, paired  # noqa: E402

LADDER = [dict(rung="dev", checks=[dict(slice="@hill.target", rule="better", margin=0.0),
                                   dict(slice="@hill.control", rule="not_worse", tolerance=0.05)]),
          dict(rung="full", checks=[dict(slice="full", rule="better", margin=0.0)])]


class Reference(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "research.json").write_text(json.dumps(dict(name="t", ladder=LADDER)))
        p = self.p = Project(self.root)
        p.add_dataset("qa", range(40))
        p.add_slice("qa/t1", list(range(10)), hill="h")
        p.add_slice("qa/c1", list(range(10, 20)), kind="control")
        p.open_hill("h", "Hill", "qa/t1", "qa/c1")
        p.explain_hill("h", symptom="breaks on <b>", examples=[dict(input="q", wrong="w", right="r", why="y")])
        p.add_model("v1", status="champion", change="baseline")
        p.add_model("v2", parent="v1", hill="h", change="fix", title="Fix it")
        p.add_model("v3", parent="v1", hill="h", change="other")
        p.set_model_status("v3", "rejected", reason="failed dev")
        good = {str(i) for i in range(30)}
        for m, sl, f in [("v1", "qa/t1", lambda i: 0.0), ("v2", "qa/t1", lambda i: 1.0),
                         ("v1", "qa/c1", lambda i: 1.0), ("v2", "qa/c1", lambda i: 1.0),
                         ("v1", "qa/full", lambda i: float(i in good and int(i) >= 10)), ("v2", "qa/full", lambda i: float(i in good))]:
            evaluate(p, m, sl, lambda i, f=f: {"score": f(i), "latency_s": 1.5})

    def test_candidate_paper_has_every_section(self):
        d = reference.build(self.p, "v2")
        self.assertEqual(d["model"]["name"], "v2")
        self.assertEqual(d["base"], "v1")  # the nearest ancestor measured on the main slice
        self.assertEqual(d["main"], "qa/full")
        r = {x["slice"]: x for x in d["results"]}
        self.assertEqual(set(r), {"qa/t1", "qa/c1", "qa/full"})
        self.assertEqual(r["qa/full"]["right"], 30)
        self.assertEqual(r["qa/full"]["vs"]["wins"], 10)
        self.assertEqual(r["qa/full"]["vs"]["losses"], 0)
        self.assertEqual(len(r["qa/full"]["cells"]["m"]), 40)  # real per-id cells, aligned with the slice ids
        self.assertEqual([x["rung"] for x in d["ladder"]], ["dev", "full"])
        self.assertTrue(all(x["status"] == "pass" for x in d["ladder"]))
        self.assertEqual([s["name"] for s in d["lineage"]], ["v1", "v2"])
        self.assertEqual([s["name"] for s in d["lineage"][-1]["siblings"]], ["v3"])
        self.assertEqual(d["lineage"][-1]["siblings"][0]["reason"], "failed dev")
        self.assertEqual(d["gallery"][0]["examples"][0]["wrong"], "w")
        self.assertIn("no_cost", {u["kind"] for u in d["unknown"]})
        self.assertEqual(r["qa/full"]["latency_p50"], 1.5)
        json.dumps(d)

    def test_champion_default_and_explicit_comparator(self):
        d = reference.build(self.p)
        self.assertEqual(d["model"]["name"], "v1")
        self.assertIsNone(d["base"])  # nothing above the root, no other champion
        d = reference.build(self.p, "v1", vs="v2")
        self.assertEqual(d["base"], "v2")
        self.assertLess(d["results"][0]["vs"]["delta"], 0)

    def test_unknown_model_is_a_404(self):
        with self.assertRaises(KeyError):
            reference.build(self.p, "nope")

    def test_empty_ledger_is_a_404_not_a_crash(self):
        root = Path(tempfile.mkdtemp())
        (root / "research.json").write_text(json.dumps(dict(name="e")))
        with self.assertRaises(KeyError):
            reference.build(Project(root))

    def test_fast_paired_matches_core(self):
        rng = random.Random(1)
        a = {str(i): float(rng.random() < .8) for i in range(300)}
        b = {str(i): float(rng.random() < .7) for i in range(300)}
        x, y = paired(a, b), reference.fast_paired(a, b)
        for k in x:
            self.assertAlmostEqual(x[k], y[k], places=12)

    def test_routes(self):
        get = {pre: fn for pre, fn in features.GET if fn.__module__.endswith("reference")}
        code, body, ctype = get["/reference"](self.p, "/reference/v2", {})
        self.assertEqual((code, ctype.split(";")[0]), (200, "text/html"))
        self.assertIn(b'id="snap"', body)
        code, data = get["/api/reference"](self.p, "/api/reference", {"model": "v2"})
        self.assertEqual(data["model"]["name"], "v2")
        code, js, ctype = get["/explain-kit.js"](self.p, "/explain-kit.js", {})
        self.assertIn(b"window.XK", js)
        self.assertIn("javascript", ctype)


if __name__ == "__main__":
    unittest.main()
