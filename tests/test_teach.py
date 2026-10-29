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

    def test_no_task_depends_on_the_truth(self):
        """Change every number the card is graded on: each method's task stays the same, so none can carry it."""
        c = self.gate
        other = dict(c, truth="Fail" if c["truth"] == "Pass" else "Pass",
                     viz=dict(c["viz"], delta=-7.5, lo=-9.0, hi=-6.0, wins=1, losses=4))
        for m in teach.methods_for(c)[1:]:
            self.assertEqual(teach.task(c, m), teach.task(other, m), m)
        hill = next(x for x in learn.cards(self.p) if x["id"].startswith("hill|"))
        self.assertNotIn("spot", teach.methods_for(hill))  # a bars figure is its card's answer

    def test_counts_methods_only_where_counts_give_the_delta(self):
        pooled = dict(self.gate, viz=dict(self.gate["viz"], delta=self.gate["viz"]["delta"] + 1.5))  # several runs per id
        self.assertEqual([m for m in teach.methods_for(pooled) if m in ("spot", "code")], [])
        self.assertIn("prototype", teach.methods_for(pooled))
        cont = dict(self.gate, viz=dict(self.gate["viz"], unit="ms"))
        self.assertFalse({"spot", "code", "prototype"} & set(teach.methods_for(cont)))

    def test_goal_context_has_no_target_count(self):
        self.p.open_goal("keep", "Keep 28 correct", "full", 0.7)
        g = learn.card(self.p, "goal|keep")
        self.assertEqual(g["truth"], 28); self.assertNotIn("28", g["ctx"])

    def test_code_is_graded_safely(self):
        v = teach._example(self.gate)
        self.assertTrue(teach.grade(self.gate, "code", "100 * (fixed - broken) / n")["hit"])
        self.assertFalse(teach.grade(self.gate, "code", "(fixed + broken) / n")["hit"])
        self.assertIsNone(teach.safe_eval("__import__('os').system('true')", dict(n=1)))
        self.assertIsNone(teach.safe_eval("n ** 99999", dict(n=2)))
        self.assertEqual(teach.safe_eval("(fixed-broken)/n*100", dict(fixed=v["wins"], broken=v["losses"], n=v["n"])), 100 * (v["wins"] - v["losses"]) / v["n"])

    def test_code_refuses_non_finite_and_bare_constants(self):
        v = teach._example(self.gate)
        for bad in ("1e309", "1e308*10", "0*1e309", "fixed/0"):
            self.assertIsNone(teach.safe_eval(bad, dict(fixed=1, broken=0, n=1)))
            g = teach.grade(self.gate, "code", bad)
            self.assertFalse(g["hit"]); json.dumps(g, allow_nan=False)
        const = repr(100 * (v["wins"] - v["losses"]) / v["n"])
        self.assertFalse(teach.grade(self.gate, "code", const)["hit"])  # the value typed in is not a line
        self.assertEqual(teach._f("nan"), None); self.assertEqual(teach._f("inf", 0), 0)

    def test_spot_prototype_explain(self):
        s, wrong = teach._spot_ci(self.gate)
        self.assertTrue(teach.grade(self.gate, "spot", wrong)["hit"])
        self.assertFalse(teach.grade(self.gate, "spot", "nope")["hit"])
        need = teach._n_needed(teach._example(self.gate))
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
