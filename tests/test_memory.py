"""Learner memory (memory.py): the schema, backfill idempotence, the spaced-repetition schedule, live writes through
the Brief's routes (teach phases, 101 course checks), and GET /api/memory."""
import json, os, sqlite3, tempfile, time, unittest

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import course, features, learn, memory, projects, teach
from autoresearch.server import _feature
from tests.test_learn import ledger, run

DAY = memory.DAY


class Memory(unittest.TestCase):
    def setUp(self):
        self.home = os.environ["ARX_HOME"]
        os.environ["ARX_HOME"] = tempfile.mkdtemp()
        features.load()
        memory.hook()
        self.p = p = ledger()
        p.add_model("base", status="champion")
        run(p, "base", [1] * 28 + [0] * 12)
        run(p, "base", [1] * 12 + [0] * 8, "ds/target")
        p.open_hill("h1", "Hill one", "target", symptom="Something goes wrong")
        p.add_model("cand", parent="base", hill="h1", change="try a thing")
        run(p, "cand", [1] * 18 + [0] * 2, "ds/target")
        self.key = projects.register(p.root)
        self.gate = next(c for c in learn.cards(p) if c["id"].startswith("gate|"))

    def tearDown(self):
        os.environ["ARX_HOME"] = self.home

    def post(self, path, body):
        return json.loads(_feature(features.POST, self.p, path, body)[1])

    def test_schema_is_migrated_once(self):
        with memory.db() as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], len(memory.SCHEMA))
            self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"people", "concepts", "events", "event_concepts", "knowledge", "sources"} <= tables)
        with memory.db() as con:  # a second open applies nothing
            self.assertEqual(memory.migrate(con), len(memory.SCHEMA))

    def test_live_answers_land_in_memory(self):
        self.post("/api/predictions", dict(viewer="p-00aa11bb", card=self.gate["id"], guess="Pass", conf=0.8))
        self.post("/api/teach", dict(viewer="p-00aa11bb", card=self.gate["id"], method="code", step=True, answer="fixed - broken", ms=900))
        self.post("/api/understanding", dict(events=[dict(viewer="p-00aa11bb", doc="concept:ladder", step=0, check="ladder#0", ok=True, ms=500)]))
        with memory.db() as con:
            ev = [dict(r) for r in con.execute("SELECT * FROM events WHERE person='p-00aa11bb' ORDER BY t")]
        self.assertEqual([e["kind"] for e in ev], ["predict", "step", "check"])  # an old concept-tile check still reads
        self.assertEqual((ev[0]["hit"], ev[1]["method"], ev[1]["hit"]), (1, "code", 0))
        self.assertEqual(json.loads(ev[1]["answer"])["text"], "fixed - broken")  # the person's own line is kept
        ks = {k["id"]: k for k in memory.knowledge("p-00aa11bb")}
        self.assertEqual(set(ks), {"paired", "ladder", "ci", f"model:{self.key}/cand"})
        self.assertEqual(ks["ladder"]["state"], "known")  # the check, minutes after the step, is the review that stands
        self.assertEqual(ks[f"model:{self.key}/cand"]["state"], "shaky")  # a model is never due for review
        self.assertEqual(ks["paired"]["state"], "due"); self.assertEqual(ks["ci"]["state"], "due")  # the step was missed

    def test_teach_phases(self):
        """answer, self and step rows (and rows from before phases) are read as what they are."""
        c, g = "gate|cand|ds/target", self.gate["id"]
        rows = [dict(t=100.0, viewer="p-00aa11bb", card=c, method="explain", phase="answer", hit=None, show={}),
                dict(t=110.0, viewer="p-00aa11bb", card=c, method="explain", phase="self", hit=True, show=dict(named=["which way"])),
                dict(t=120.0, viewer="p-00aa11bb", card=g, method="spot", phase="step", hit=False, show=dict(got="delta")),
                dict(t=130.0, viewer="p-00aa11bb", card=g, method="ndrag", phase="step", skip=True),
                dict(t=140.0, viewer="p-00aa11bb", card=g, method="sketch", phase="answer", skip=True),
                dict(t=150.0, viewer="p-00aa11bb", card=g, method="code", hit=True)]  # no phase: an answer
        with open(self.p.dir / "teach.jsonl", "a") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
        memory.sync(self.key, self.p.root)
        with memory.db() as con:
            ev = [dict(r) for r in con.execute("SELECT kind, method, hit FROM events WHERE person='p-00aa11bb' ORDER BY t")]
            spot = con.execute("SELECT group_concat(concept) FROM event_concepts c JOIN events e ON e.uid=c.uid WHERE e.method='spot'").fetchone()[0]
        self.assertEqual([(e["kind"], e["method"], e["hit"]) for e in ev],
                         [("attempt", "explain", None), ("self", "explain", 1), ("step", "spot", 0), ("skip", "ndrag", None),
                          ("skip", "sketch", None), ("attempt", "code", 1)])
        self.assertEqual(set(spot.split(",")), {"ladder", "ci", f"model:{self.key}/cand"})
        ms = memory.methods("p-00aa11bb")
        self.assertEqual(ms["explain"], dict(n=1, hits=1, skips=0, last=[True]))  # the self-check grades the answer
        self.assertEqual(ms["spot"], dict(n=1, hits=0, skips=0, last=[False]))
        self.assertEqual((ms["ndrag"]["skips"], ms["sketch"]["skips"], ms["code"]["hits"]), (1, 1, 1))
        prof = teach.profile(teach.attempts(self.p, "p-00aa11bb"), [])
        self.assertEqual({m: prof["methods"][m] for m in ms}, ms)  # the same record teach.profile keeps

    def test_no_project_text_is_stored(self):
        c = learn.card(self.p, f"hill|h1|base")
        learn.predict(self.p, dict(viewer="p-00aa11bb", card=c["id"], guess=c["truth"], conf=0.8))
        memory.sync(self.key, self.p.root)
        with memory.db() as con:
            dump = "\n".join(str(tuple(r)) for t in ("events", "concepts") for r in con.execute(f"SELECT * FROM {t}"))
        self.assertNotIn("Something goes wrong", dump); self.assertNotIn("Hill one", dump)
        self.assertNotIn(c["q"], dump)
        self.assertIn(f"hill:{self.key}/h1", dump)

    def test_course_checks_map_onto_concepts(self):
        for item, hit, how in (("paired-delta", True, "lesson"), ("gate", False, "primer"), ("project-hills", True, "review"),
                               ("interval", True, "lesson")):
            self.assertEqual(self.post("/api/course", dict(viewer="p-00aa11bb", item=item, hit=hit, how=how))["memory"]["n"], 1)
        self.post("/api/course", dict(viewer="anon", item="gate", hit=True))  # no one's
        with memory.db() as con:
            ev = [dict(r) for r in con.execute("SELECT kind, ref, hit FROM events ORDER BY t")]
            titles = dict(con.execute("SELECT id, title FROM concepts").fetchall())
        self.assertEqual([(e["kind"], e["ref"], e["hit"]) for e in ev],
                         [("check", "course:paired-delta", 1), ("check", "course:gate", 0), ("check", "course:project-hills", 1),
                          ("check", "course:interval", 1)])
        ks = {k["id"]: k for k in memory.knowledge("p-00aa11bb")}
        self.assertEqual(set(ks), {"paired", "ci", "lesson:gate", f"lesson:{self.key}/project-hills"})
        self.assertEqual({i: k["lesson"] for i, k in ks.items()},
                         {"paired": "paired-delta", "ci": "interval", "lesson:gate": "gate", f"lesson:{self.key}/project-hills": "project-hills"})
        self.assertEqual((ks["lesson:gate"]["project"], ks[f"lesson:{self.key}/project-hills"]["project"]), ("", self.key))
        self.assertEqual(titles["lesson:gate"], "Gate"); self.assertEqual(ks["lesson:gate"]["state"], "due")
        self.assertEqual(course.memory(course.rows(self.p, "p-00aa11bb"))["gate"]["is_due"], True)  # the course agrees
        mem = course.memory(course.rows(self.p, "p-00aa11bb"))  # the course's own schedule reads the same rows
        self.assertEqual(set(mem), {"paired-delta", "gate", "project-hills", "interval"})
        self.assertEqual(memory.sync_all("backfill", full=True)["added"][self.key], 0)

    def test_backfill_is_idempotent(self):
        learn.predict(self.p, dict(viewer="ann", card=self.gate["id"], guess="Fail", conf=0.6))
        teach.answer(self.p, dict(viewer="ann", card=self.gate["id"], method="spot", step=True, answer="delta"))
        learn.record(self.p, dict(viewer="ann", doc="brief", step=self.gate["id"], ms=1200))
        with open(self.p.dir / "understanding.jsonl", "a") as f:
            f.write('{"t": 1, "viewer": "ann", "doc": "br')  # a writer mid-line
        first = memory.sync_all("backfill", full=True)["added"][self.key]
        self.assertEqual(first, 3)
        self.assertEqual(memory.sync_all("backfill", full=True)["added"][self.key], 0)
        self.assertEqual(memory.sync(self.key, self.p.root)["added"], 0)
        with open(self.p.dir / "understanding.jsonl", "a") as f:
            f.write('ief", "step": "x", "ms": 5}\n')
        self.assertEqual(memory.sync(self.key, self.p.root)["added"], 1)  # the finished line is read once
        with memory.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM events").fetchone()[0], 4)
            self.assertEqual(con.execute("SELECT count(*) FROM knowledge WHERE person='ann'").fetchone()[0], 3)

    def test_spaced_repetition(self):
        t0 = 1_000_000.0
        k = memory.step({}, t0, True)
        self.assertEqual(k["stability"], 1.0); self.assertEqual(k["due"], t0 + DAY)
        crammed = memory.step(dict(k), t0 + 60, True)
        spaced = memory.step(dict(k), t0 + DAY, True)
        self.assertLess(crammed["stability"], spaced["stability"])  # a gap makes the review count
        self.assertEqual(spaced["stability"], 2.5)
        self.assertEqual(memory.step(dict(k), t0 + DAY, True, "code")["stability"], 3.0)  # harder methods count more
        miss = memory.step(dict(spaced), t0 + 4 * DAY, False)
        self.assertAlmostEqual(miss["stability"], 2.5 * 0.35); self.assertEqual(miss["lapses"], 1)
        self.assertLess(miss["mastery"], spaced["mastery"])
        self.assertEqual(miss["due"], t0 + 4 * DAY)  # a miss is due again now, as in the 101 course
        relearn = memory.step(dict(memory.step(dict(miss), t0 + 5 * DAY, False)), t0 + 5.2 * DAY, True)
        self.assertEqual(relearn["stability"], 1.0)  # a right answer is never due again within the course's first day
        self.assertEqual(relearn["due"], t0 + 6.2 * DAY)
        self.assertAlmostEqual(memory.recall(spaced, spaced["last_review"] + 2.5 * DAY), 0.9)
        self.assertEqual(memory.state_of(dict(n=1, due=t0, mastery=0.9), t0 + 1), "due")
        self.assertEqual(memory.state_of(dict(n=0), t0), "untested")

    def test_knowledge_is_rebuilt_when_the_rules_change(self):
        with memory.db() as con:
            memory._insert(con, "k", dict(t=1000.0, person="p-0000beef", kind="check", hit=0), ["ci"], "u0", "live")
            memory.rebuild(con, "p-0000beef")
            con.execute("UPDATE knowledge SET due=99999")  # as an older version scheduled it
            con.execute("UPDATE meta SET v='old' WHERE k='rules'")
        self.assertEqual(memory.knowledge("p-0000beef", 2000.0)[0]["due"], 1000.0)

    def test_reviews_close_together_count_once(self):
        with memory.db() as con:
            for i, (dt, hit) in enumerate(((0, 0), (120, 1))):
                memory._insert(con, "k", dict(t=1000.0 + dt, person="p-0000beef", kind="check", hit=hit), ["ci"], f"u{i}", "live")
            memory.rebuild(con, "p-0000beef")
        k = memory.knowledge("p-0000beef", 2000.0)[0]
        self.assertEqual((k["reps"], k["n"], k["hits"]), (1, 2, 1))
        self.assertEqual(k["stability"], 1.0)  # the retry replaced the first result

    def test_api(self):
        learn.predict(self.p, dict(viewer="p-00aa11bb", card=self.gate["id"], guess="Pass", conf=0.8))
        self.post("/api/teach", dict(viewer="p-00aa11bb", card=self.gate["id"], method="spot", step=True, answer="nope"))
        code, body, _ = _feature(features.GET, self.p, "/api/memory", dict(viewer="p-00aa11bb"))[:3]
        d = json.loads(body)
        self.assertEqual(code, 200); self.assertEqual(d["person"], "p-00aa11bb"); self.assertEqual(d["project"], self.key)
        self.assertEqual(d["methods"]["spot"], dict(n=1, hits=0, skips=0, last=[False]))
        self.assertEqual(d["methods"]["predict"], dict(n=1, hits=1, skips=0, last=[True]))
        self.assertIn("ladder", {k["id"] for k in d["concepts"]})
        anon = json.loads(_feature(features.GET, self.p, "/api/memory", dict(viewer="anon"))[1])
        self.assertIsNone(anon["person"]); self.assertEqual(anon["concepts"], [])

    def test_a_guest_reads_only_their_own_memory_of_this_project(self):
        from autoresearch import people
        people.remember("p-0c0c0c0c", "Owner", self.key)
        people.remember("p-0e0e0e0e", "Guest", self.key, remote=True)
        with memory.db() as con:
            for who in ("p-0c0c0c0c", "p-0e0e0e0e"):
                for i, proj in enumerate(("elsewhere", self.key)):
                    memory._insert(con, proj, dict(t=time.time() - 60 + i, person=who, kind="attempt", method="code", hit=1),
                                   ["paired", f"hill:{proj}/h"], f"{who}{i}", "live")
                memory.rebuild(con, who)
        get = lambda v: json.loads(_feature(features.GET, self.p, "/api/memory", dict(viewer=v))[1])
        self.assertNotIn("people", get("p-0c0c0c0c"))  # who else is in memory is no one's business here
        self.assertIn("hill:elsewhere/h", {k["id"] for k in get("p-0c0c0c0c")["concepts"]})  # on this machine: everything
        features.REQUEST.remote = True
        try:
            self.assertIsNone(get("p-0c0c0c0c")["person"])  # a person of this machine is not the guest's to read
            g = get("p-0e0e0e0e")
        finally:
            features.REQUEST.remote = False
        self.assertEqual({k["id"] for k in g["concepts"]}, {"paired", f"hill:{self.key}/h"})
        self.assertEqual(g["methods"]["code"]["n"], 1)
        self.assertEqual({e["project"] for e in g["timeline"]}, {self.key})

    def test_methods_carry_across_projects(self):
        with memory.db() as con:
            for i in range(4):
                memory._insert(con, "elsewhere", dict(t=10.0 + i, person="p-00aa11bb", kind="attempt", method="code", hit=1), [], f"x{i}", "live")
        prof = teach.profile([], [])
        memory.blend(self.p, prof, "p-00aa11bb")
        self.assertEqual(prof["methods"]["code"]["hits"], 4)
        self.assertEqual(teach.profile([], [])["methods"]["code"]["n"], 0)  # the project's own profile is untouched


if __name__ == "__main__":
    unittest.main()
