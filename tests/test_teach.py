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
        p.add_model("rej1", parent="base", hill="h1")
        run(p, "rej1", [1] * 10 + [0] * 10, "ds/target")
        p.set_model_status("rej1", "rejected", "worse on the target")
        self.ci = learn.card(p, "rej|rej1")  # a number card on a paired delta: every method fits it

    def post(self, card=None, **kw):
        return teach.answer(self.p, dict(viewer="ann", card=card or self.ci["id"], **kw))

    def test_methods_and_tasks_hide_truth(self):
        self.assertEqual(teach.methods_for(self.gate), ["predict", "sketch"])  # a gate asks pass or fail
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
        for c in (self.gate, self.ci):
            other = dict(c, truth="Fail" if c["truth"] == "Pass" else 12.5,
                         viz=dict(c["viz"], delta=-7.5, lo=-9.0, hi=-6.0, wins=1, losses=4))
            for m in teach.methods_for(c)[1:]:
                self.assertEqual(teach.task(c, m), teach.task(other, m), m)
        self.assertEqual(teach.methods_for(self.ci), list(teach.METHODS))
        hill = next(x for x in learn.cards(self.p) if x["id"].startswith("hill|"))
        self.assertNotIn("spot", teach.methods_for(hill))  # a bars figure is its card's answer

    def test_counts_methods_only_where_counts_give_the_delta(self):
        pooled = dict(self.ci, viz=dict(self.ci["viz"], delta=self.ci["viz"]["delta"] + 1.5))  # several runs per id
        self.assertEqual([m for m in teach.methods_for(pooled) if m in ("spot", "code")], [])
        self.assertIn("prototype", teach.methods_for(pooled))
        cont = dict(self.ci, viz=dict(self.ci["viz"], unit="ms"))
        self.assertFalse({"spot", "code", "prototype"} & set(teach.methods_for(cont)))

    def test_prototype_is_answerable_on_a_zero_delta_card(self):
        zero = dict(self.ci, id="rej|zero", viz=dict(self.gate["viz"], delta=0.0, lo=0.0, hi=0.0, wins=0, losses=0))
        need = teach._n_needed(teach._example(zero))
        self.assertTrue(4 <= need < float("inf"))
        self.assertTrue(teach.grade(zero, "prototype", round(need))["hit"])

    def test_sketch_axis_is_the_cards_own_scale(self):
        c = self.gate
        ax = teach.task(c, "sketch")
        self.assertEqual((ax["min"], ax["max"]), tuple(c["axis"]))  # from the comparator, not the answer
        self.assertTrue(ax["min"] <= c["viz"]["delta"] <= ax["max"])
        num = dict(id="rej|x", type="number", unit="ms", min=-5000, max=5000, truth=-104.6,
                   viz=dict(kind="ci", unit="ms", delta=-104.6, lo=-119.7, hi=-87.1, n=12, wins=1, losses=11))
        ax = teach.task(num, "sketch")
        self.assertEqual((ax["unit"], ax["min"], ax["max"], ax["view"]), ("ms", -5000, 5000, 5000))
        bars = dict(kind="bars", ref=200.0, rows=[dict(label="a", v=150.0, unit="ms"), dict(label="b", v=900.0, unit="ms"),
                                                  dict(label="champ", v=200.0, unit="ms", hl=3)])
        t = teach.task(dict(id="batch|x", truth="b", viz=bars), "sketch")
        self.assertEqual((t["max"], len(t["rows"])), (500, 2))  # from the champion's value, its own row left out
        self.assertNotIn("sketch", teach.methods_for(dict(id="batch|y", truth="b", viz=dict(bars, ref=None))))

    def test_sketch_is_graded_on_the_cards_question(self):
        g = self.gate  # cand fixed 6 of 20 on the target: Pass against a "better" bar at 0
        self.assertEqual(g["truth"], "Pass")
        self.assertTrue(teach.grade(g, "sketch", dict(delta=4, lo=1, hi=8))["hit"])
        self.assertFalse(teach.grade(g, "sketch", dict(delta=0, lo=-2, hi=2))["hit"])  # the untouched default fails
        self.assertEqual(teach.task(g, "sketch")["bar"], g["viz"].get("bar"))
        q = dict(id="q|x", type="choice", opts=["Better", "Worse", "Can't tell yet"], truth="Can't tell yet",
                 viz=dict(kind="ci", unit="pts", delta=1.0, lo=-0.5, hi=2.5, n=100, wins=3, losses=2, better=1))
        self.assertTrue(teach.grade(q, "sketch", dict(delta=1, lo=-1, hi=3))["hit"])
        self.assertFalse(teach.grade(q, "sketch", dict(delta=1, lo=0.5, hi=3))["hit"])
        run = dict(q, id="run|x", opts=["Yes", "No"], truth="Yes")
        self.assertTrue(teach.grade(run, "sketch", dict(delta=0.5, lo=0, hi=1))["hit"])
        hill = next(x for x in learn.cards(self.p) if x["id"].startswith("hill|"))
        n = hill["max"]
        right = [hill["truth"] / n] + [0.5] * (len(teach.task(hill, "sketch")["rows"]) - 1)
        self.assertTrue(teach.grade(hill, "sketch", dict(rows=right))["hit"])
        self.assertFalse(teach.grade(hill, "sketch", dict(rows=[0.0] * len(right)))["hit"])

    def test_goal_context_has_no_target_count(self):
        self.p.open_goal("keep", "Keep 28 correct", "full", 0.7)
        g = learn.card(self.p, "goal|keep")
        self.assertEqual(g["truth"], 28); self.assertNotIn("28", g["ctx"])

    def test_code_is_graded_safely(self):
        v = teach._example(self.ci)
        self.assertTrue(teach.grade(self.ci, "code", "100 * (fixed - broken) / n")["hit"])
        self.assertFalse(teach.grade(self.ci, "code", "(fixed + broken) / n")["hit"])
        self.assertIsNone(teach.safe_eval("__import__('os').system('true')", dict(n=1)))
        self.assertIsNone(teach.safe_eval("n ** 99999", dict(n=2)))
        self.assertEqual(teach.safe_eval("(fixed-broken)/n*100", dict(fixed=v["wins"], broken=v["losses"], n=v["n"])), 100 * (v["wins"] - v["losses"]) / v["n"])

    def test_code_refuses_non_finite_and_bare_constants(self):
        v = teach._example(self.ci)
        for bad in ("1e309", "1e308*10", "0*1e309", "fixed/0"):
            self.assertIsNone(teach.safe_eval(bad, dict(fixed=1, broken=0, n=1)))
            g = teach.grade(self.ci, "code", bad)
            self.assertFalse(g["hit"]); json.dumps(g, allow_nan=False)
        const = repr(100 * (v["wins"] - v["losses"]) / v["n"])
        self.assertFalse(teach.grade(self.ci, "code", const)["hit"])  # the value typed in is not a line
        self.assertEqual(teach._f("nan"), None); self.assertEqual(teach._f("inf", 0), 0)

    def test_spot_prototype_explain(self):
        s, wrong = teach._spot_ci(self.ci)
        self.assertTrue(teach.grade(self.ci, "spot", wrong)["hit"])
        self.assertFalse(teach.grade(self.ci, "spot", "nope")["hit"])
        need = teach._n_needed(teach._example(self.ci))
        self.assertTrue(teach.grade(self.ci, "prototype", need * 1.2)["hit"])
        self.assertFalse(teach.grade(self.ci, "prototype", need * 3)["hit"])
        self.assertTrue(teach.grade(self.ci, "explain", "It fixed 6, broke none, and the interval clears zero")["hit"])

    def test_answer_reveals_and_counts(self):
        code, d = self.post(method="code", answer="100*(fixed-broken)/n", ms=4000)
        self.assertEqual(code, 200); self.assertTrue(d["attempt"]["hit"]); self.assertIn("reveal", d["card"])
        again = self.post(method="spot", answer="delta")[1]
        self.assertEqual(again["attempt"]["method"], "code")  # the first answer stands
        b = learn.brief(self.p, 0, "ann")
        g = next(c for c in b["cards"] if c["id"] == self.ci["id"])
        self.assertEqual(g["pred"]["method"], "code"); self.assertIn("reveal", g)
        self.assertEqual(b["teach"]["profile"]["methods"]["code"]["hits"], 1)

    def test_chooser_adapts(self):
        prof = teach.profile([dict(t=i, method="sketch", hit=True) for i in range(5)], [])
        self.assertNotEqual(teach.choose(prof, self.ci, "ann"), "sketch")  # easy now and used twice running
        skip = self.post(method="spot", skip=True)[1]
        self.assertNotEqual(skip["method"], "spot")


if __name__ == "__main__":
    unittest.main()
