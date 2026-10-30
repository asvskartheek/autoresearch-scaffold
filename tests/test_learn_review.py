"""The Brief after review: stalled runs, axis ranges, chance-level confidence, no-champion projects, units."""
import json, time, unittest

from tests.test_learn import ledger, run
from autoresearch import learn


def _age(t, seconds):
    """Make a running task look like it has had no heartbeat for `seconds`."""
    m = json.loads((t.dir / "task.json").read_text())
    m["heartbeat"] = m["updated"] = time.time() - seconds
    (t.dir / "task.json").write_text(json.dumps(m))


class Review(unittest.TestCase):
    def setUp(self):
        self.p = p = ledger()
        p.add_model("base", status="champion")
        run(p, "base", [1] * 28 + [0] * 12)
        run(p, "base", [1] * 12 + [0] * 8, "ds/target")
        p.add_model("cand", parent="base")

    def test_stalled_run_is_labelled_and_dead_run_dropped(self):
        t = run(self.p, "cand", [1] * 5, "ds/full", finish=False)
        cid = "run|cand|base|ds/full"
        _age(t, 3600)
        c = next(c for c in learn.cards(self.p) if c["id"] == cid)
        self.assertEqual(c["label"], "Stalled")
        _age(t, 3 * 86400)
        self.assertNotIn(cid, {c["id"] for c in learn.cards(self.p)})

    def test_open_goal_is_not_news_once_seen(self):
        self.p.open_goal("g", "Goal", "full", 0.9)
        self.assertIn("goal|g", {c["id"] for c in learn.cards(self.p, 0)})
        self.assertNotIn("goal|g", {c["id"] for c in learn.cards(self.p, time.time() + 1)})

    def test_delta_axis_does_not_depend_on_the_answer(self):
        small = dict(delta=0.01, lo=-0.01, hi=0.03, wins=3, losses=1, n=40, base=0.7)
        big = dict(small, delta=-0.25, lo=-0.35, hi=-0.15)
        a, b = learn._delta_card("x", small), learn._delta_card("y", big)
        self.assertEqual((a["min"], a["max"]), (b["min"], b["max"]))
        self.assertEqual((a["min"], a["max"]), (-70, 30))
        self.assertTrue(a["min"] <= b["truth"] <= a["max"])

    def test_units(self):
        self.assertEqual(learn.sd(self.p, "ds/full", 0.01), "+1 pt")
        self.assertEqual(learn.sd(self.p, "ds/full", -0.052), "−5.2 pts")
        self.assertEqual(learn.sv(self.p, "ds/full", 0.7), "28 of 40 (70.0%)")
        self.p.add_slice("ds/lat", list(range(4)), kind="hill")
        sl = json.loads((self.p.dir / "slices.json").read_text())
        sl["ds/lat"] |= dict(scale="continuous", unit="ms", metric="minus latency in ms")
        (self.p.dir / "slices.json").write_text(json.dumps(sl))
        self.assertEqual(learn.sd(self.p, "ds/lat", 1071.0), "−1,071 ms")
        self.assertEqual(learn.sv(self.p, "ds/lat", -387.0), "387 ms")
        c = learn._delta_card("z", dict(delta=50.0, lo=20.0, hi=80.0, wins=3, losses=1, n=4, base=-400.0),
                              self.p, "ds/lat")
        self.assertEqual((c["unit"], c["truth"], c["viz"]["better"]), ("ms", -50.0, -1))

    def test_rule_text_singular(self):
        self.assertEqual(learn._rule_text(self.p, dict(slice="ds/full", rule="not_worse", threshold=-0.01)),
                         "may lose at most 1 pt")

    def test_confidence_goes_down_to_chance(self):
        self.assertEqual(learn.conf_floor(dict(type="choice", opts=list("abcd"))), 0.25)
        self.assertEqual(learn.conf_floor(dict(type="choice", opts=["Yes", "No"])), 0.5)
        self.assertEqual(learn.conf_floor(dict(type="number")), 0.05)
        self.p.open_goal("g", "Goal", "full", 0.9)
        _, r = learn.predict(self.p, dict(viewer="ann", card="goal|g", guess=20, conf=0.1))
        self.assertEqual(r["prediction"]["conf"], 0.1)
        self.assertEqual(r["card"]["cmin"], 0.05)

    def test_hill_card_asks_for_a_count_with_n(self):
        self.p.open_hill("h1", "Hill one", "target", symptom="Something goes wrong")
        c = next(c for c in learn.cards(self.p) if c["id"].startswith("hill|"))
        self.assertEqual(c["id"], "hill|h1|base|n")
        self.assertEqual((c["truth"], c["max"], c["unit"]), (12, 20, ""))
        self.assertIn("n = 20", c["ctx"])
        row = c["viz"]["rows"][0]
        self.assertEqual((row["tag"], row["n"]), ("champion", 20))
        self.assertEqual(learn.card(self.p, "hill|h1|base")["unit"], "%")  # older predictions keep their card


if __name__ == "__main__":
    unittest.main()
