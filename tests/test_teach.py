"""Teaching methods: each card's methods, server-side grading, per-person profiles and the method chooser (teach.py)."""
import json, os, tempfile, unittest

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import learn, teach
from tests.test_learn import ledger, run


class Teach(unittest.TestCase):
    def setUp(self):
        self.p = p = ledger()
        p.add_model("base", status="champion")
        run(p, "base", [1] * 28 + [0] * 12)
        run(p, "base", [1] * 12 + [0] * 8, "ds/target")
        p.open_hill("h1", "Hill one", "target", symptom="Something goes wrong")
        p.add_model("cand", parent="base", hill="h1", change="try a thing")
        run(p, "cand", [1] * 18 + [0] * 2, "ds/target")
        self.gate = next(c for c in learn.cards(self.p) if c["id"].startswith("gate|"))

    def post(self, **kw):
        return teach.answer(self.p, dict(viewer="ann", card=self.gate["id"], **kw))

    def test_methods_and_tasks_hide_truth(self):
        self.assertEqual(teach.methods_for(self.gate), ["predict", "sketch", "spot", "prototype", "code", "explain"])
        for m in teach.METHODS[1:]:
            t = json.dumps(teach.task(self.gate, m))
            self.assertNotIn('"truth"', t)
        self.assertNotIn("\"delta\":", json.dumps(teach.task(self.gate, "code")))  # the line to write is the answer
        b = learn.brief(self.p, 0, "ann")
        g = next(c for c in b["cards"] if c["id"] == self.gate["id"])
        self.assertIn(g["method"], g["methods"]); self.assertNotIn("reveal", g)
        self.assertIn("profile", b["teach"])

    def test_code_is_graded_safely(self):
        v = self.gate["viz"]
        self.assertTrue(teach.grade(self.gate, "code", "100 * (fixed - broken) / n")["hit"])
        self.assertFalse(teach.grade(self.gate, "code", "(fixed + broken) / n")["hit"])
        self.assertIsNone(teach.safe_eval("__import__('os').system('true')", dict(n=1)))
        self.assertIsNone(teach.safe_eval("n ** 99999", dict(n=2)))
        self.assertEqual(teach.safe_eval("(fixed-broken)/n*100", dict(fixed=v["wins"], broken=v["losses"], n=v["n"])), 100 * (v["wins"] - v["losses"]) / v["n"])

    def test_spot_prototype_explain(self):
        s, wrong = teach._spot_ci(self.gate)
        self.assertTrue(teach.grade(self.gate, "spot", wrong)["hit"])
        self.assertFalse(teach.grade(self.gate, "spot", "nope")["hit"])
        need = teach._n_needed(self.gate["viz"])
        self.assertTrue(teach.grade(self.gate, "prototype", need * 1.2)["hit"])
        self.assertFalse(teach.grade(self.gate, "prototype", need * 3)["hit"])
        self.assertTrue(teach.grade(self.gate, "explain", "It fixed 6, broke none, and the interval clears zero")["hit"])

    def test_answer_reveals_and_counts(self):
        code, d = self.post(method="code", answer="100*(fixed-broken)/n", ms=4000)
        self.assertEqual(code, 200); self.assertTrue(d["attempt"]["hit"]); self.assertIn("reveal", d["card"])
        again = self.post(method="spot", answer="delta")[1]
        self.assertEqual(again["attempt"]["method"], "code")  # the first answer stands
        b = learn.brief(self.p, 0, "ann")
        g = next(c for c in b["cards"] if c["id"] == self.gate["id"])
        self.assertEqual(g["pred"]["method"], "code"); self.assertIn("reveal", g)
        self.assertEqual(b["teach"]["profile"]["methods"]["code"]["hits"], 1)

    def test_chooser_adapts(self):
        prof = teach.profile([dict(t=i, method="sketch", hit=True) for i in range(5)], [])
        self.assertNotEqual(teach.choose(prof, self.gate, "ann"), "sketch")  # easy now and used twice running
        skip = self.post(method="spot", skip=True)[1]
        self.assertNotEqual(skip["method"], "spot")


if __name__ == "__main__":
    unittest.main()
