"""Goal intake: the inbox item, the agent's proposal, answers, opening goals with parent/role, and the CLI."""
import contextlib, io, json, os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import features, intake
from autoresearch.cli import main
from autoresearch.core import Project, Task


def ledger():
    d = Path(tempfile.mkdtemp()) / "demo"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="demo", higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(20)))
    p.add_slice("ds/dev-a", list(range(10)))
    p.add_model("base", status="champion")
    t = Task(p, "eval", "base on full", model="base", slice="ds/full")
    for i in range(20):
        t.add_row(dict(id=str(i), score=1 if i < 14 else 0, latency_s=2.0))
    t.finish()
    return p


PROPOSAL = {
    "questions": [{"id": "done", "text": "Done when", "options": [
        {"label": "90%", "sub": ">= 18 of 20", "value": "18"}, {"label": "Any gain", "sub": ">= 15 of 20", "value": "15"}]},
        {"id": "bad", "text": "One option only", "options": [{"label": "x"}]}],
    "goal": {"name": "ds-90", "title": "DS at 90%", "slice": "full", "target": 0.9, "constraints": ["open weights"],
             "why": {"target": "90% of 20 is 18."}},
    "related": [{"role": "guard", "name": "ds-90-fast", "title": "No slower", "kpi": "latency_p50", "slice": "ds/full", "target": 2.5},
                {"role": "guard", "name": "ds-90-heldout", "title": "Unseen", "slice": "held/full", "count": 9, "n": 10}],
}


def call(p, verb, body):
    return intake._post(p, f"/api/intake/{verb}", body)


class Intake(unittest.TestCase):
    def setUp(self):
        self.p = ledger()

    def test_round_trip(self):
        code, it = call(self.p, "new", {"ask": "get ds to 90%"})
        self.assertEqual((code, it["kind"], it["status"]), (200, "goal", "queued"))
        self.assertEqual([i["id"] for i in features.pending(self.p)], [it["id"]])
        text = features.PROMPTS["goal"](self.p, intake.item(self.p, it["id"]))
        self.assertIn('"get ds to 90%"', text)
        self.assertIn(f"arx goal propose {it['id']} --json", text)

        prop = intake.propose(self.p, it["id"], PROPOSAL)
        self.assertEqual(len(prop["questions"]), 1)  # a question with one option is dropped
        self.assertEqual((prop["goal"]["slice"], prop["goal"]["count"], prop["goal"]["n"]), ("ds/full", 18, 20))
        self.assertTrue(prop["related"][1]["missing_slice"])
        st = {}
        intake._state(self.p, st)
        self.assertEqual(st["intake"][0]["status"], "done")  # the answer is in: not run again
        self.assertEqual(features.pending(self.p), [])

        code, r = call(self.p, "answer", {"id": it["id"], "answers": {"done": "18"}})
        self.assertEqual(code, 200)
        i = intake.item(self.p, it["id"])
        self.assertEqual((i["status"], i["round"], i["answered"][0]["label"]), ("queued", 1, "90%"))
        self.assertIn("Done when: 90% (18)", features.PROMPTS["goal"](self.p, i))

        code, g = call(self.p, "open", {"id": it["id"], "goal": prop["goal"] | {"role": "main"}})
        self.assertEqual(code, 200, g)
        self.assertAlmostEqual(self.p.goals()["ds-90"]["target"], 0.9)
        self.assertEqual(self.p.goals()["ds-90"]["constraints"], ["open weights"])
        code, g = call(self.p, "open", {"id": it["id"], "goal": prop["related"][0] | {"parent": "ds-90"}})
        self.assertEqual(code, 200, g)
        fast = self.p.goal_status("ds-90-fast")
        self.assertEqual((fast["role"], fast["parent"], fast["higher_is_better"], fast["met"]), ("guard", "ds-90", False, True))
        self.assertEqual(intake.item(self.p, it["id"])["opened"], ["ds-90", "ds-90-fast"])

        code, e = call(self.p, "open", {"id": it["id"], "goal": prop["goal"]})  # the ledger refuses: a message, not a crash
        self.assertEqual(code, 400)
        self.assertIn("already exists", e["error"])
        code, e = call(self.p, "open", {"id": it["id"], "goal": prop["related"][1] | {"parent": "ds-90"}})
        self.assertEqual(code, 400)

        call(self.p, "dismiss", {"id": it["id"]})
        self.assertEqual(intake.items(self.p), [])

    def test_use_existing_and_bad_input(self):
        self.p.open_goal("g", "G", "full", 0.9)
        _, it = call(self.p, "new", {"ask": "90 please"})
        self.assertEqual(call(self.p, "open", {"id": it["id"], "goal": {"use": "g"}})[0], 200)
        self.assertEqual(call(self.p, "new", {"ask": "  "})[0], 400)
        self.assertEqual(call(self.p, "answer", {"id": "nope", "answers": {"a": "b"}})[0], 400)
        with self.assertRaises(SystemExit):
            intake.propose(self.p, it["id"], {"goal": {"name": "x", "title": "x", "slice": "full", "count": 99}})
        with self.assertRaises(SystemExit):
            intake.propose(self.p, it["id"], {"goal": {"name": "x", "title": "x", "slice": "full", "kpi": "vibes", "target": 1}})

    def test_meta_rules(self):
        self.p.open_goal("a", "A", "full", 0.9)
        self.p.open_goal("b", "B", "full", 0.8)
        with self.assertRaises(SystemExit):
            intake.set_meta(self.p, "b", role="guard")  # a guard needs a parent
        intake.set_meta(self.p, "b", parent="a")
        self.assertEqual(self.p.goals()["b"]["role"], "sub")
        with self.assertRaises(SystemExit):
            intake.set_meta(self.p, "a", parent="b")  # no loops
        with self.assertRaises(SystemExit):
            intake.set_meta(self.p, "a", parent="nope")


class Cli(unittest.TestCase):
    def setUp(self):
        self.p = ledger()
        self.cwd = os.getcwd()
        os.chdir(self.p.root)

    def tearDown(self):
        os.chdir(self.cwd)

    def arx(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(list(argv))
        return out.getvalue()

    def test_propose_open_parent_and_status_json(self):
        it = features.enqueue(self.p, "goal", {"ask": "faster"})
        f = Path(self.p.root) / "prop.json"
        f.write_text(json.dumps(PROPOSAL))
        self.assertIn("ds-90 (≥ 18 of 20 correct", self.arx("goal", "propose", it["id"], "--json", f"@{f}"))
        self.assertIn("ds-90", self.arx("goal", "propose", it["id"], "--json", json.dumps(PROPOSAL)))
        self.arx("goal", "open", "main", "--title", "Main", "--slice", "full", "--target", "0.9", "--constraint", "open weights")
        self.arx("goal", "open", "fast", "--title", "Fast", "--slice", "full", "--target", "3", "--kpi", "latency_p50",
                 "--lower-is-better", "--parent", "main", "--role", "guard")
        st = json.loads(self.arx("goal", "status", "--json", "fast"))  # --json still a flag before the name
        self.assertEqual((st["parent"], st["role"]), ("main", "guard"))
        self.assertEqual(json.loads(self.arx("goal", "status", "main", "--json"))["constraints"], ["open weights"])
        self.arx("goal", "link", "fast", "--parent", "main", "--role", "sub")
        self.assertEqual(self.p.goals()["fast"]["role"], "sub")
        with self.assertRaises(SystemExit):
            self.arx("goal", "open", "bad", "--title", "B", "--slice", "full", "--target", "0.5", "--parent", "nope")
        self.assertNotIn("bad", self.p.goals())  # refused before anything was opened


if __name__ == "__main__":
    unittest.main()
