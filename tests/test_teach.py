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
        self.assertEqual(teach.methods_for(self.ci), list(teach.BEFORE))
        for c in (self.gate, self.ci):
            for m in teach.methods_for(c)[1:]:
                self.assertNotIn('"truth"', json.dumps(teach.task(c, m)))
                self.assertNotIn('"delta"', json.dumps(teach.task(c, m)))
        b = learn.brief(self.p, 0, "ann")
        g = next(c for c in b["cards"] if c["id"] == self.gate["id"])
        self.assertIn(g["method"], g["methods"]); self.assertNotIn("reveal", g); self.assertNotIn("step", g)
        self.assertIn("profile", b["teach"])

    def test_no_task_depends_on_the_truth(self):
        """Change every number the card is graded on: each pre-reveal task stays the same, so none can carry it."""
        for c in (self.gate, self.ci):
            other = dict(c, truth="Fail" if c["truth"] == "Pass" else 12.5,
                         viz=dict(c["viz"], delta=-7.5, lo=-9.0, hi=-6.0, wins=1, losses=4))
            for m in teach.methods_for(c)[1:]:
                self.assertEqual(teach.task(c, m), teach.task(other, m), m)
        hill = next(x for x in learn.cards(self.p) if x["id"].startswith("hill|"))
        self.assertEqual(teach.steps_for(hill), [])  # a bars figure has no counts to work on

    def test_steps_use_the_cards_own_numbers_after_the_reveal(self):
        v = self.ci["viz"]  # rej1 against base on the target: 0 fixed, 2 broken of 20
        self.assertIn("code", teach.steps_for(self.ci))
        self.assertEqual(teach.step_task(self.ci, "code")["vars"], dict(fixed=v["wins"], broken=v["losses"], n=v["n"]))
        self.assertEqual(self.post(method="code", step=True, answer="100*(fixed-broken)/n")[0], 409)  # answer first
        code, d = self.post(method="sketch", answer=dict(delta=-10, lo=-25, hi=2))
        self.assertEqual(code, 200)
        st = d["card"]["step"]
        self.assertIn(st["method"], teach.steps_for(self.ci)); self.assertIn("task", st)
        code, d = self.post(method="code", step=True, answer="100*(fixed-broken)/n")
        self.assertEqual(code, 200); self.assertTrue(d["step"]["hit"]); self.assertEqual(d["attempt"]["phase"], "step")
        again = self.post(method="code", step=True, answer="1")[1]
        self.assertTrue(again["step"]["hit"])  # the first step answer stands
        b = learn.brief(self.p, 0, "ann")
        c = next(x for x in b["cards"] if x["id"] == self.ci["id"])
        self.assertTrue(c["step"]["done"]); self.assertEqual(c["pred"]["method"], "sketch")

    def test_pooled_scores_get_no_counts_step(self):
        pooled = dict(self.ci, viz=dict(self.ci["viz"], delta=self.ci["viz"]["delta"] + 1.5))  # several runs per id
        self.assertNotIn("code", teach.steps_for(pooled))
        self.assertNotIn("counts", teach._spot_parts(pooled))
        cont = dict(self.ci, viz=dict(self.ci["viz"], unit="ms"))
        self.assertNotIn("code", teach.steps_for(cont))

    def test_spot_is_a_variant_of_the_real_figure(self):
        v, wrong, why = teach._spot(self.ci)
        self.assertNotIn("delta", teach._spot_parts(self.ci))  # a number card shows its delta in the answer
        self.assertIn(wrong, teach._spot_parts(self.ci)); self.assertTrue(why)
        self.assertEqual(v["n"], self.ci["viz"]["n"])
        g = teach.grade_step(self.ci, "spot", wrong)
        self.assertTrue(g["hit"]); self.assertEqual(g["show"]["why"], why)
        q = dict(id="q|x", type="choice", truth="Can't tell yet", viz=dict(kind="ci", unit="pts", delta=1.0, lo=-1.5, hi=2.5, n=100, wins=3, losses=2))
        self.assertNotIn("delta", teach._spot_parts(q))  # −1 sits inside [−1.5, 2.5]: a flipped delta would not be wrong

    def test_ndrag_finds_when_the_result_stops_being_noise(self):
        c = dict(self.ci, viz=dict(kind="ci", unit="pts", delta=-3.16, lo=-5.0, hi=-1.32, n=185, wins=12, losses=13, better=1))
        t = teach.step_task(c, "ndrag")
        self.assertEqual((t["dir"], t["n"]), ("down", 185))
        need = teach._n_needed(c["viz"])
        self.assertTrue(need < 185)
        self.assertTrue(teach.grade_step(c, "ndrag", need * 1.2)["hit"])
        self.assertFalse(teach.grade_step(c, "ndrag", 185)["hit"])
        zero = dict(c, viz=dict(c["viz"], delta=0.0, lo=0.0, hi=0.0))
        self.assertNotIn("ndrag", teach.steps_for(zero))

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
        v = self.ci["viz"]
        self.assertTrue(teach.grade_step(self.ci, "code", "100 * (fixed - broken) / n")["hit"])
        self.assertFalse(teach.grade_step(self.ci, "code", "(fixed + broken) / n")["hit"])
        self.assertIsNone(teach.safe_eval("__import__('os').system('true')", dict(n=1)))
        self.assertIsNone(teach.safe_eval("n ** 99999", dict(n=2)))
        for bad in ("1e309", "1e308*10", "0*1e309", "fixed/0"):
            self.assertIsNone(teach.safe_eval(bad, dict(fixed=1, broken=0, n=1)))
            g = teach.grade_step(self.ci, "code", bad)
            self.assertFalse(g["hit"]); json.dumps(g, allow_nan=False)
        const = teach.grade_step(self.ci, "code", repr(100 * (v["wins"] - v["losses"]) / v["n"]))
        self.assertFalse(const["hit"]); self.assertTrue(const["show"]["const"])  # the value typed in is not a line
        self.assertEqual(teach._f("nan"), None); self.assertEqual(teach._f("inf", 0), 0)

    def test_gate_sketch_needs_the_interval_too(self):
        g = self.gate  # Pass, and its interval clears zero
        self.assertTrue(teach.grade(g, "sketch", dict(delta=4, lo=1, hi=8))["hit"])
        self.assertFalse(teach.grade(g, "sketch", dict(delta=4, lo=-1, hi=8))["hit"])  # right verdict, wrong side of zero

    def test_explain_is_checked_by_the_person_against_the_reveal(self):
        code, d = self.post(method="explain", answer="It got worse, but it could be noise.")
        self.assertEqual(code, 200)
        self.assertIsNone(d["attempt"]["hit"]); self.assertEqual(d["card"]["selfcheck"], teach.selfcheck(self.ci))
        self.assertNotIn("could be noise", json.dumps(teach.attempts(self.p, "ann")))  # the sentence is not kept
        self.assertEqual(teach.answer(self.p, {"viewer": "ann", "card": self.ci["id"], "method": "explain", "self": [True]})[0], 400)
        code, d = teach.answer(self.p, {"viewer": "ann", "card": self.ci["id"], "method": "explain", "self": [True, False]})
        self.assertEqual(code, 200); self.assertFalse(d["attempt"]["hit"])
        prof = teach._person(self.p, "ann")[1]
        self.assertEqual((prof["methods"]["explain"]["n"], prof["methods"]["explain"]["hits"]), (1, 0))
        b = learn.brief(self.p, 0, "ann")
        c = next(x for x in b["cards"] if x["id"] == self.ci["id"])
        self.assertNotIn("selfcheck", c); self.assertFalse(c["pred"]["hit"])
        self.assertEqual(b["calibration"]["all_n"], b["calibration"]["n"])  # self-report is not tested correctness
        # writing is never preferred over doing at equal results
        p0 = teach.profile([], [])
        self.assertLess(teach.score(p0, "explain")[0], teach.score(p0, "sketch")[0])

    def test_answer_reveals_and_counts(self):
        code, d = self.post(method="sketch", answer=dict(delta=-10, lo=-20, hi=-1), ms=4000)
        self.assertEqual(code, 200); self.assertIn("reveal", d["card"])
        again = self.post(method="explain", answer="whatever it was")[1]
        self.assertEqual(again["attempt"]["method"], "sketch")  # the first answer stands
        b = learn.brief(self.p, 0, "ann")
        g = next(c for c in b["cards"] if c["id"] == self.ci["id"])
        self.assertEqual(g["pred"]["method"], "sketch"); self.assertIn("reveal", g)
        self.assertEqual(b["teach"]["profile"]["methods"]["sketch"]["n"], 1)
        self.assertEqual(b["calibration"]["all_n"], b["calibration"]["n"] + 1)

    def test_two_misses_switch_the_method_and_say_why(self):
        seq = lambda a, b: [dict(t=0, method="sketch", hit=a), dict(t=1, method="predict", hit=b), dict(t=2, method="sketch", hit=a)]
        miss, hit = teach.profile(seq(False, True), []), teach.profile(seq(True, False), [])
        m_miss, why = teach.choose(miss, teach.BEFORE, "ann", "x")
        m_hit, _ = teach.choose(hit, teach.BEFORE, "ann", "x")
        self.assertEqual(m_hit, "sketch"); self.assertNotEqual(m_miss, "sketch")
        self.assertEqual(why, "Sketch missed twice")

    def test_a_deck_adapts_to_misses_and_hits(self):
        """Two people answer the same nine cards, one always wrong, one always right: their methods part ways."""
        def deck(right):
            rows, seq = [], []
            for i in range(9):
                prof = teach.profile(rows, [])
                m, _ = teach.choose(prof, list(teach.BEFORE), "p", f"c{i}", deck={x: seq[-3:].count(x) for x in teach.BEFORE})
                seq.append(m)
                rows.append(dict(t=i, method=m, hit=right, phase="answer"))
            return seq
        wrong, right = deck(False), deck(True)
        self.assertNotEqual(wrong, right)
        self.assertTrue(all(not (a == b == c) for a, b, c in zip(wrong, wrong[1:], wrong[2:])))

    def test_steps_up_once_a_method_is_easy(self):
        prof = teach.profile([], [dict(t=i, hit=True) for i in range(5)])  # predict: 5 of the last 5 right
        self.assertNotEqual(teach.choose(prof, list(teach.BEFORE), "ann", "x")[0], "predict")
        self.assertGreater(teach.score(prof, "sketch")[0], teach.score(teach.profile([], []), "sketch")[0])

    def test_another_way(self):
        skip = self.post(method="sketch", skip=True)[1]
        self.assertNotEqual(skip["method"], "sketch")
        g = self.gate["id"]  # predict and sketch only
        d = self.post(card=g, method="sketch", skip=True)[1]
        self.assertEqual((d["method"], d["others"]), ("predict", 0))
        n = len(teach.attempts(self.p, "ann"))
        d = self.post(card=g, method="predict", skip=True)[1]
        self.assertEqual((d["method"], d["others"]), ("predict", 0))
        self.assertEqual(len(teach.attempts(self.p, "ann")), n)  # no skip logged
        b = learn.brief(self.p, 0, "ann")
        self.assertEqual(next(c for c in b["cards"] if c["id"] == g)["others"], 0)

    def test_a_prediction_gets_its_step(self):
        _, r = learn.predict(self.p, dict(viewer="bo", card=self.ci["id"], guess=-5, conf=0.6))
        self.assertIn(r["card"]["step"]["method"], teach.steps_for(self.ci))
        code, d = teach.answer(self.p, dict(viewer="bo", card=self.ci["id"], method=r["card"]["step"]["method"], step=True, skip=True))
        self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()


class Narration(unittest.TestCase):
    def test_drag_n_explains_projection(self):
        c = {"viz": {"delta": 2, "lo": -1, "hi": 5, "n": 100}}
        result = teach.grade_step(c, "ndrag", 4)
        self.assertFalse(result["hit"])
        self.assertIn("not a new measurement", result["show"]["why"])
        self.assertIn("independent examples", result["show"]["why"])

    def test_duplicate_learning_titles_keep_identity(self):
        p = ledger()
        p.add_model("adapter-512", title="Qwen3-4B RL")
        p.add_model("adapter-1024", title="Qwen3-4B RL")
        self.assertNotEqual(learn._title(p, "adapter-512"), learn._title(p, "adapter-1024"))

    def test_interval_demo_can_clear_zero(self):
        from autoresearch import course
        data = course.lesson_interval(None, {"checks": [{"noisy": True, "delta": 0, "lo": -.03, "hi": .03, "n": 100}]}, learn)
        fig = data["fig"]
        self.assertTrue(fig["example"])
        self.assertNotEqual(fig["delta"], 0)
        self.assertLess(fig["lo"], 0)
        self.assertGreater(fig["delta"] - (fig["hi"] - fig["lo"]) / 2 / (20 ** .5), 0)

    def test_historical_promotion_has_explicit_provenance(self):
        from unittest.mock import patch
        p = ledger()
        p.add_model("base", status="champion")
        p.add_model("winner", parent="base")
        check = dict(slice="ds/full", delta=.05, lo=.01, hi=.1, wins=3, losses=1, n=40)
        with patch("autoresearch.learn._decisions", return_value=[dict(kind="promote", model="winner", replaced="base", t=1, gate={"rungs": [{"checks": [check]}]})]):
            card = learn._card_promote(p, "winner")
        self.assertIn("Frozen promotion evidence", card["ctx"])
        self.assertEqual(card["viz"]["delta"], 5)
