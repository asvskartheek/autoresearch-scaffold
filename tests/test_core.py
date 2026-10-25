import tempfile, unittest
from pathlib import Path

import helpers as H  # noqa: F401  (must come first)
import fixture
from autoresearch.core import Project, Task, _append, paired, per_id, summarize

ONE_RUNG = [{"rung": "dev", "checks": [{"slice": "@hill.target", "rule": "better", "margin": 0.0}]}]


def tiny(tmp, ladder=None, name="proj"):
    """A project with dataset d (20 ids), slice d/dev (10 ids), hill h on it, baseline champion `base`."""
    root = H.new_project(tmp, name, **({"ladder": ladder} if ladder else {}))
    p = Project(root)
    p.add_dataset("d", [str(i) for i in range(20)])
    p.add_slice("dev", [str(i) for i in range(10)])
    p.open_hill("h", "Hill", "dev")
    p.add_model("base", parent="", status="champion")
    return p


def ev(p, model, sl, ok_ids):
    t = Task(p, "eval", f"{model} {sl}", model=model, slice=sl)
    for i in p.slice(sl)["ids"]:
        t.add_row(dict(id=i, score=1.0 if i in ok_ids else 0.0))
    t.finish()
    return t


class Stats(unittest.TestCase):
    def test_summarize_errors_score_zero(self):
        s = summarize([dict(id="a", score=1.0, latency_s=2), dict(id="b", score=1.0, error="boom"), dict(id="c", score=0.0)])
        self.assertEqual((s["n"], s["errors"]), (3, 1))
        self.assertAlmostEqual(s["score"], 1 / 3)

    def test_summarize_empty(self):
        s = summarize([])
        self.assertEqual(s["n"], 0)
        self.assertIsNone(s["score"])

    def test_per_id_averages_repeats(self):
        self.assertEqual(per_id([dict(id=1, score=1), dict(id=1, score=0), dict(id=2, score=1, error="x")]), {"1": 0.5, "2": 0.0})

    def test_paired(self):
        c = {str(i): 1.0 for i in range(10)}
        b = {str(i): 1.0 if i < 5 else 0.0 for i in range(10)}
        r = paired(c, b)
        self.assertEqual((r["n"], r["wins"], r["losses"]), (10, 5, 0))
        self.assertAlmostEqual(r["delta"], 0.5)
        self.assertGreater(r["lo"], 0)
        self.assertAlmostEqual(paired(c, b, sign=-1)["delta"], -0.5)

    def test_paired_disjoint(self):
        r = paired({"a": 1.0}, {"b": 0.0})
        self.assertEqual((r["n"], r["delta"]), (0, None))


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name


class Champions(Base):
    def test_duplicate_seeding_collapses(self):
        root = Path(self.tmp) / "fx"
        fixture.build(root)
        p = Project(root)
        self.assertEqual([c["model"] for c in p.champions()], [fixture.CHAMPION])
        self.assertTrue(p.champions()[0]["seeded"])
        self.assertEqual(p.champion(), fixture.CHAMPION)

    def test_promotion_trail(self):
        p = tiny(self.tmp, ONE_RUNG)
        p.add_model("v2", parent="base", hill="h")
        p.promote("v2", force=True)
        cs = p.champions()
        self.assertEqual([c["model"] for c in cs], ["base", "v2"])
        self.assertEqual(cs[1]["replaced"], "base")
        self.assertEqual(p.models()["base"]["status"], "retired")

    def test_hand_edited_models_appear(self):
        p = tiny(self.tmp)
        data = p.models()
        data["ghost"] = dict(status="retired", created=5.0)
        data["usurper"] = dict(status="champion", created=9e9, parent="ghost")
        data["base"]["status"] = "retired"
        p._save("models", data)
        names = [c["model"] for c in p.champions()]
        self.assertEqual(set(names), {"base", "ghost", "usurper"})
        self.assertEqual(names[-1], "usurper")  # sorted by time

    def test_decision_without_model_ignored(self):
        p = tiny(self.tmp)
        _append(p.dir / "decisions.jsonl", dict(t=1.0, kind="champion"))
        _append(p.dir / "decisions.jsonl", dict(t=2.0, kind="promote", model="base", replaced=None))
        self.assertEqual([c["model"] for c in p.champions()], ["base"])

    def test_empty_ledger(self):
        p = Project(H.new_project(self.tmp))
        self.assertEqual(p.champions(), [])
        self.assertIsNone(p.champion())

    def test_garbage_lines_tolerated(self):
        p = tiny(self.tmp)
        with (p.dir / "decisions.jsonl").open("a") as f:
            f.write("{not json\n")
        self.assertEqual(len(p.champions()), 1)

    def test_reseeded_after_promotion_does_not_duplicate(self):
        p = tiny(self.tmp, ONE_RUNG)
        p.add_model("v2", parent="base", hill="h")
        p.promote("v2", force=True)
        p.log_decision("champion", model="base", note="seeded again by a re-run setup script")
        self.assertEqual([c["model"] for c in p.champions()].count("base"), 1)


class Gate(Base):
    def setUp(self):
        super().setUp()
        self.p = tiny(self.tmp, ONE_RUNG)
        self.p.add_model("cand", parent="base", hill="h")

    def test_need_baseline_then_need_run(self):
        g = self.p.gate("cand")
        self.assertEqual(g["rungs"][0]["checks"][0]["state"], "need_baseline")
        self.assertEqual(g["next"], [dict(model="base", slice="d/dev")])
        ev(self.p, "base", "dev", {"0", "1", "2"})
        g = self.p.gate("cand")
        self.assertEqual(g["rungs"][0]["checks"][0]["state"], "need_run")
        self.assertEqual(g["next"], [dict(model="cand", slice="d/dev")])
        self.assertFalse(g["promotable"])

    def test_pass_and_promote(self):
        ev(self.p, "base", "dev", {"0", "1", "2"})
        ev(self.p, "cand", "dev", {"0", "1", "2", "3", "4"})
        g = self.p.gate("cand")
        self.assertEqual(g["rungs"][0]["status"], "pass")
        self.assertTrue(g["promotable"])
        self.p.promote("cand")
        self.assertEqual(self.p.champion(), "cand")
        self.assertEqual(self.p.hills()["h"]["status"], "climbed")
        self.assertEqual(self.p.hills()["h"]["climbed_by"], "cand")
        self.assertEqual(self.p.champions()[-1]["replaced"], "base")

    def test_fail_blocks(self):
        ev(self.p, "base", "dev", {"0", "1", "2"})
        ev(self.p, "cand", "dev", {"0"})
        g = self.p.gate("cand")
        self.assertEqual(g["rungs"][0]["status"], "fail")
        self.assertFalse(g["promotable"])
        self.assertEqual(g["next"], [])
        with self.assertRaises(SystemExit):
            self.p.promote("cand")
        self.assertEqual(self.p.champion(), "base")

    def test_equal_is_not_better(self):
        ev(self.p, "base", "dev", {"0", "1"})
        ev(self.p, "cand", "dev", {"0", "1"})
        self.assertEqual(self.p.gate("cand")["rungs"][0]["status"], "fail")

    def test_partial_eval_does_not_count(self):
        ev(self.p, "base", "dev", {"0"})
        t = Task(self.p, "eval", "partial", model="cand", slice="dev")
        t.add_row(dict(id="0", score=1.0))
        t.finish()
        self.assertFalse(t.meta["complete"])
        self.assertEqual(self.p.gate("cand")["rungs"][0]["checks"][0]["state"], "need_run")

    def test_force_promote(self):
        self.p.promote("cand", force=True)
        self.assertEqual(self.p.champion(), "cand")

    def test_rejected_and_historical_are_not_candidates(self):
        self.p.set_model_status("cand", "rejected", "nope")
        g = self.p.gate("cand")
        self.assertEqual(g["rungs"][0]["status"], "fail")
        self.assertFalse(g["promotable"])
        self.p.add_model("old", status="historical")
        self.assertEqual(self.p.gate("old")["rungs"][0]["status"], "locked")

    def test_unknown_model(self):
        with self.assertRaises(SystemExit):
            self.p.gate("nope")

    def test_champion_cannot_be_promoted(self):
        self.assertFalse(self.p.gate("base")["promotable"])

    def test_later_rungs_locked_until_earlier_pass(self):
        ladder = ONE_RUNG + [{"rung": "full", "checks": [{"slice": "full", "rule": "better", "margin": 0}]}]
        p = tiny(self.tmp, ladder, name="two")
        p.add_model("cand", parent="base", hill="h")
        self.assertEqual([r["status"] for r in p.gate("cand")["rungs"]], ["pending", "locked"])

    def test_fixture_gates(self):
        root = Path(self.tmp) / "fx"
        fixture.build(root)
        p = Project(root)
        self.assertEqual(p.gate("cand-good")["rungs"][0]["status"], "pass")
        self.assertEqual(p.gate("cand-bad")["rungs"][0]["status"], "fail")


class Slices(Base):
    def test_frozen(self):
        p = tiny(self.tmp)
        p.add_slice("dev", [str(i) for i in range(10)])  # same ids: fine
        with self.assertRaises(SystemExit):
            p.add_slice("dev", ["0", "1"])

    def test_random_nested(self):
        p = tiny(self.tmp)
        p.random_slices("d", (5, 10))
        s = p.slices()
        self.assertEqual(s["d/random5"]["ids"], s["d/random10"]["ids"][:5])


if __name__ == "__main__":
    unittest.main()
