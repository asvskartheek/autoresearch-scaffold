"""Questions: the seeded tree, the ledger, the CLI, the agent prompt and the dashboard routes."""
import contextlib, io, json, os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import features, questions as q
from autoresearch.core import Project, Task


def ledger():
    d = Path(tempfile.mkdtemp()) / "qdemo"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="qdemo", higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(20)))
    p.add_slice("ds/hard", list(range(10)))
    return p


def run(p, model, scores, slice="ds/full"):
    t = Task(p, "eval", f"{model} on {slice}", model=model, slice=slice)
    for i, s in enumerate(scores):
        t.add_row(dict(id=p.slice(slice)["ids"][i], score=s))
    t.finish()
    return t


class Questions(unittest.TestCase):
    def setUp(self):
        self.p = p = ledger()
        p.add_model("base", parent="", status="champion")
        run(p, "base", [1] * 14 + [0] * 6)
        run(p, "base", [1] * 5 + [0] * 5, "ds/hard")
        p.open_goal("ninety", "Ninety on full", "full", 0.9)
        p.open_hill("hard", "Hard ones", "ds/hard", goal="ninety", symptom="The hard ones fail.")
        p.add_model("base+hint", parent="base", hill="hard", change="Add a hint line.")
        run(p, "base+hint", [1] * 8 + [0] * 2, "ds/hard")
        p.add_model("worse", parent="base", hill="hard", change="Drop the system prompt.")
        run(p, "worse", [1] * 2 + [0] * 8, "ds/hard")
        p.set_model_status("worse", "rejected", "Lost 3 of 10 on target; the CI is below zero.")

    def by(self):
        return {n["id"]: n for n in q.tree(self.p)["nodes"]}

    def test_seeded_tree_is_derived_not_written(self):
        t = self.by()
        self.assertEqual(t["g:ninety"]["parent"], None)
        self.assertEqual(t["h:hard"]["parent"], "g:ninety")
        self.assertEqual((t["m:worse"]["status"], t["m:worse"]["parent"]), ("dead", "h:hard"))
        self.assertTrue(t["m:worse"]["claim"].startswith("No. Lost 3 of 10"))
        self.assertEqual(t["m:base+hint"]["title"], "Does +hint help?")
        self.assertEqual(t["m:base+hint"]["status"], "open")
        self.assertIn("14 of 20", t["g:ninety"]["claim"])
        self.assertFalse((self.p.dir / "questions.json").exists())
        for n in t.values():  # goal questions carry the target in units ("to 1,267 of 1,319"), so they get more room
            self.assertLessEqual(len(n["title"].split()), 14 if n.get("seed") == "goal" else 6, n["title"])

    def test_evidence_is_paired_against_the_parent(self):
        ev = self.by()["m:worse"]["ev"]
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertEqual((e["kind"], e["role"], e["base"], e["n"], e["c"], e["bc"]), ("paired", "target", "base", 10, 2, 5))
        self.assertAlmostEqual(e["delta"], -0.3)
        self.assertEqual((e["wins"], e["losses"]), (0, 3))
        self.assertLess(e["hi"], 0)

    def test_add_answer_dead_and_seeded_edit(self):
        a = q.add(self.p, "Is the scorer strict?", parent="h:hard", needs_human=True, choices=["Keep", "Loosen"])
        t = q.tree(self.p)
        self.assertEqual(t["needs_human"], 1)
        r = q.settle(self.p, a["id"], "answered", "Keep it frozen.", by="kartheek")
        self.assertEqual((r["status"], r["needs_human"]), ("answered", False))
        self.assertEqual(q.tree(self.p)["needs_human"], 0)
        q.settle(self.p, "m:base+hint", "dead", "Not worth the tokens.", q.parse_evidence(self.p, ["base+hint:hard"]))
        st = q.stored(self.p)
        self.assertEqual(st["m:base+hint"]["evidence"], [dict(model="base+hint", slice="ds/hard")])
        n = self.by()["m:base+hint"]
        self.assertEqual((n["status"], n["claim"], n["edited"]), ("dead", "Not worth the tokens.", True))
        with self.assertRaises(SystemExit):
            q.add(self.p, "Orphan", parent="nope")
        with self.assertRaises(SystemExit):
            q.parse_evidence(self.p, ["nomodel:hard"])
        with self.assertRaises(SystemExit):
            q.settle(self.p, a["id"], "answered", "  ")

    def test_ask_enqueues_and_answer_closes_the_queued_item(self):
        r = q.ask(self.p, "Why does worse lose?", parent="m:worse", quote="Lost 3 of 10", route="#model/worse")
        self.assertEqual(r["status"], "agent")
        items = [i for i in features.inbox(self.p) if i["kind"] == "question"]
        self.assertEqual((len(items), items[0]["ref"], items[0]["status"]), (1, r["id"], "queued"))
        prompt = features.PROMPTS["question"](self.p, items[0])
        for want in (r["id"], "Why does worse lose?", "Lost 3 of 10", "arx q answer", "Read-only", "m:worse", "paired"):
            self.assertIn(want, prompt)
        t = Task(self.p, "answer", "Answer it")
        t.note("Reading the gate")
        features.update(self.p, items[0]["id"], status="running", task=t.id)
        live = self.by()[r["id"]]["live"]
        self.assertEqual((live["status"], live["task"], live["note"]), ("running", t.id, "Reading the gate"))
        t.finish()
        q.settle(self.p, r["id"], "answered", "It drops the system prompt: 2 vs 5 of 10.")
        self.assertEqual(self.by()[r["id"]]["status"], "answered")
        # a queued item nobody started is closed when the question is answered
        r2 = q.ask(self.p, "Another?", parent=None)
        q.settle(self.p, r2["id"], "dead", "Duplicate.")
        it = next(i for i in features.inbox(self.p) if i.get("ref") == r2["id"])
        self.assertEqual(it["status"], "done")
        # an unknown parent from a stale page lands at the top instead of failing
        self.assertIsNone(q.ask(self.p, "Loose?", parent="h:gone")["parent"])

    def test_routes_and_state(self):
        get = dict(features.GET)
        post = dict(features.POST)
        code, body = get["/api/questions"](self.p, "/api/questions", {})
        self.assertEqual(code, 200)
        self.assertIn("ninety", body["goals"])
        self.assertTrue(body["goals"]["ninety"]["points"])
        code, r = post["/api/questions/"](self.p, "/api/questions/ask", dict(title="From the UI", parent="h:hard", by="k<b>"))
        self.assertEqual((code, r["by"]), (200, "kb"))
        code, r = post["/api/questions/"](self.p, "/api/questions/answer", dict(id=r["id"], claim="Done."))
        self.assertEqual((code, r["status"]), (200, "answered"))
        self.assertEqual(post["/api/questions/"](self.p, "/api/questions/answer", dict(id="x", claim="y"))[0], 400)
        code, r = get["/api/questions/notes"](self.p, "/api/questions/notes", {"id": "m:worse"})
        self.assertEqual(code, 200)
        self.assertTrue(any(n["node"] == "m:worse" and "Lost 3" in n["text"] for n in r["notes"]))
        self.assertEqual(get["/api/questions/notes"](self.p, "", {"id": "nope"})[0], 404)
        out = {}
        q._state(self.p, out)
        self.assertEqual(out["questions"], dict(needs_human=0, agent=0))

    def test_cli(self):
        import argparse
        ap = argparse.ArgumentParser()
        sp = ap.add_subparsers(dest="cmd")
        q._register(sp)
        cwd = os.getcwd()
        os.chdir(self.p.root)
        try:
            def cli(*argv):
                a = ap.parse_args(list(argv))
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    a.fn(a)
                return buf.getvalue()
            qid = cli("q", "add", "Is it the parser?", "--parent", "h:hard", "--needs-human").strip()
            self.assertTrue(qid.startswith("q-"))
            self.assertIn("answered", cli("q", "answer", qid, "No, the parser is fine.", "--evidence", "worse:ds/hard"))
            self.assertIn("dead", cli("q", "dead", "m:worse", "Dead end."))
            out = cli("q", "list", "--claims")
            self.assertIn("+ " + qid, out)
            self.assertIn("No, the parser is fine.", out)
            self.assertIn("x m:worse", out)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
