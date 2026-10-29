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


if __name__ == "__main__":
    unittest.main()
