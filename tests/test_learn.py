"""The Brief: cards from the ledger, predictions (hit, open, resolve), calibration and understanding telemetry."""
import json, os, tempfile, time, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import learn
from autoresearch.core import Project, Task


LADDER = [dict(rung="dev", checks=[dict(slice="@hill.target", rule="better", margin=0)]),
          dict(rung="random10", checks=[dict(slice="random10", rule="not_worse", tolerance=0.02)]),
          dict(rung="full", checks=[dict(slice="full", rule="better", margin=0)])]


def ledger():
    d = Path(tempfile.mkdtemp()) / "demo"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="demo", higher_is_better=True, ladder=LADDER)))
    p = Project(d)
    p.add_dataset("ds", list(range(40)))
    p.random_slices("ds", sizes=(10,))
    p.add_slice("ds/target", list(range(20)), kind="hill")
    return p


def run(p, model, scores, slice="ds/full", finish=True):
    sl = p.slice(slice)
    t = Task(p, "eval", f"{model} on {slice}", model=model, slice=slice)
    for i, s in zip(sl["ids"], scores):
        t.add_row(dict(id=i, score=s))
    if finish:
        t.finish()
    return t


class Brief(unittest.TestCase):
    def setUp(self):
        self.p = p = ledger()
        p.add_model("base", status="champion")
        run(p, "base", [1] * 28 + [0] * 12)
        run(p, "base", [1] * 12 + [0] * 8, "ds/target")
        run(p, "base", [1] * 7 + [0] * 3, "ds/random10")
        p.open_hill("h1", "Hill one", "target", symptom="Something goes wrong",
                    examples=[dict(input="2 + 2", wrong="5", right="4")], share=dict(count=8, of=12, of_what="errors"))
        p.open_goal("g", "Goal", "full", 0.9)
        p.add_model("cand", parent="base", hill="h1", change="try a thing")
        run(p, "cand", [1] * 18 + [0] * 2, "ds/target")
        self.t0 = time.time() - 1

    def ids(self, since=0):
        return {c["id"].split("|")[0] for c in learn.cards(self.p, since)}

    def test_cards_cover_the_ledger_and_hide_answers(self):
        b = learn.brief(self.p, 0, "ann")
        kinds = {c["id"].split("|")[0] for c in b["cards"]}
        self.assertTrue({"goal", "gate", "hill"} <= kinds, kinds)
        for c in b["cards"]:
            self.assertNotIn("reveal", c)
            self.assertNotIn("truth", c)
        gate = next(c for c in b["cards"] if c["id"].startswith("gate|"))
        self.assertEqual(sorted(gate["opts"]), ["Fail", "Pass"])
        self.assertEqual(gate["needs"], ["candidate", "gate", "rung"])  # the lessons a catch-up shows first
        self.assertIn("paired-delta", {x["id"] for x in b["course"]["lessons"]})
        self.assertEqual(b["course"]["due"], [])

    def test_one_card_per_fact(self):
        """Two goals on one slice ask the same count: one card. The goal axis starts at 0, never near the target."""
        self.p.open_goal("keep", "Keep them", "full", 0.7)
        ids = [c["id"] for c in learn.cards(self.p) if c["id"].startswith("goal|")]
        self.assertEqual(len(ids), 1)
        self.assertEqual(learn.card(self.p, "goal|keep")["min"], 0)

    def test_rejected_why_reads_and_counts_match(self):
        self.p.add_model("bad", parent="base", hill="h1")
        run(self.p, "bad", [1] * 6 + [0] * 14, "ds/target")
        self.p.set_model_status("bad", "rejected", "Failedfrozenpairedgate")
        c = learn.card(self.p, "rej|bad")
        self.assertTrue(c["why"].startswith("It fixed 0 and broke 6 of 20 on ds/target"), c["why"])
        self.assertNotIn("Failedfrozen", c["why"])
        self.assertTrue(c["viz"]["exact"])
        pooled = learn._ci_viz(dict(delta=-0.03, lo=-0.05, hi=0.0, wins=11, losses=13, n=185))
        self.assertFalse(pooled["exact"])  # 11 and 13 do not give −3 pts: the page must not say fixed/broken

    def test_since_filters(self):
        self.assertNotIn("gate", self.ids(time.time() + 10))

    def test_prediction_hit_and_first_one_stands(self):
        gate = next(c for c in learn.cards(self.p) if c["id"].startswith("gate|"))
        code, r = learn.predict(self.p, dict(viewer="ann", card=gate["id"], guess="Pass", conf=0.8))
        self.assertEqual(code, 200)
        self.assertEqual((r["prediction"]["truth"], r["prediction"]["hit"]), ("Pass", True))
        self.assertIn("reveal", r["card"])
        learn.predict(self.p, dict(viewer="ann", card=gate["id"], guess="Fail", conf=0.9))
        preds = learn.predictions(self.p, "ann")
        self.assertEqual(len(preds), 1)
        cal = learn.calibration(preds)
        self.assertEqual((cal["n"], cal["hits"]), (1, 1))
        self.assertAlmostEqual(cal["brier"], 0.04)
        self.assertEqual(learn.predict(self.p, dict(viewer="ann", card="gate|nope|x", guess="Pass"))[0], 404)
        self.assertEqual(learn.predict(self.p, dict(viewer="bob", card=gate["id"], guess="Maybe"))[0], 400)

    def test_number_card_band(self):
        goal = learn.card(self.p, "goal|g")
        self.assertEqual(goal["truth"], 28)
        _, r = learn.predict(self.p, dict(viewer="ann", card="goal|g", guess=goal["truth"] + goal["tol"], conf=0.6))
        self.assertTrue(r["prediction"]["hit"])
        _, r = learn.predict(self.p, dict(viewer="bob", card="goal|g", guess=goal["truth"] + goal["tol"] + 1, conf=0.6))
        self.assertFalse(r["prediction"]["hit"])

    def test_open_prediction_resolves_when_the_run_lands(self):
        t = run(self.p, "cand", [1] * 30, "ds/full", finish=False)
        cid = f"run|cand|base|ds/full"
        self.assertIn(cid, {c["id"] for c in learn.cards(self.p)})
        _, r = learn.predict(self.p, dict(viewer="ann", card=cid, guess="Yes", conf=0.7))
        self.assertIsNone(r["prediction"]["hit"])
        self.assertEqual(learn.calibration(learn.predictions(self.p, "ann"))["open"], 1)
        for i in range(30, 40):
            t.add_row(dict(id=str(i), score=1))
        t.finish()
        pr = learn.predictions(self.p, "ann")[0]
        self.assertEqual((pr["truth"], pr["hit"], pr.get("resolved")), ("Yes", True, True))

    def test_hill_without_champion_run_is_open(self):
        self.p.add_slice("ds/other", list(range(5)), kind="hill")
        self.p.open_hill("h2", "Hill two", "other")
        c = learn.card(self.p, f"hill|h2|base")
        self.assertIsNone(c["truth"])
        self.assertTrue(learn.public(c)["open"])

    def test_understanding_events(self):
        code, r = learn.record(self.p, dict(viewer="ann", doc="explainer-x", step=2, ms=1500, check="c1", ok=False,
                                            replays=1, alt_used=True, junk="dropped"))
        self.assertEqual((code, r), (200, dict(ok=True, n=1)))
        learn.record(self.p, dict(events=[dict(viewer="ann", doc="explainer-x", step=3, ms="bad", check="c2", ok=True)]))
        self.assertEqual(learn.record(self.p, dict(events="nope"))[0], 400)
        row = [json.loads(l) for l in (self.p.dir / "understanding.jsonl").read_text().splitlines()][0]
        self.assertNotIn("junk", row)
        u = learn.understanding(self.p, "ann")
        d = u["docs"]["explainer-x"]
        self.assertEqual((d["ms"], d["steps"], d["checks"], d["right"], d["missed"]), (1500, 2, 2, 1, ["c1"]))
        self.assertEqual(u["missed"], [dict(doc="explainer-x", check="c1")])
        learn.record(self.p, dict(viewer="ann", doc="explainer-x", step=2, check="c1", ok=True))
        self.assertEqual(learn.understanding(self.p, "ann")["missed"], [])

    def test_routes_registered(self):
        from autoresearch import features
        self.assertTrue(any(pre == "/api/brief" for pre, _ in features.GET))
        self.assertTrue(any(pre == "/api/understanding" for pre, _ in features.POST))
        self.assertTrue(any(pre == "/api/course" for pre, _ in features.GET))


if __name__ == "__main__":
    unittest.main()
