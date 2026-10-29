"""The 101 course: lessons from the project's own ledger, checks, and spaced review per person (course.py)."""
import json, os, tempfile, unittest

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import course, learn
from tests.test_learn import ledger, run

DAY = course.DAY


class Course(unittest.TestCase):
    def setUp(self):
        self.p = p = ledger()
        p.add_model("base", status="champion", title="Base model")
        run(p, "base", [1] * 28 + [0] * 12)
        run(p, "base", [1] * 12 + [0] * 8, "ds/target")
        run(p, "base", [1] * 7 + [0] * 3, "ds/random10")
        p.open_hill("h1", "Hill one", "target", symptom="Something goes wrong", share=dict(count=8, of=12, of_what="errors"))
        p.open_goal("g", "Goal", "full", 0.9)
        p.add_model("cand", parent="base", hill="h1", change="try a thing")
        run(p, "cand", [1] * 18 + [0] * 2, "ds/target")

    def test_every_lesson_has_a_figure_a_line_and_a_check(self):
        ls = {x["id"]: x for x in course.lessons(self.p)}
        for i in ("goal", "champion", "candidate", "hill", "slice", "paired-delta", "interval", "gate", "rung", "ladder", "brief",
                  "project-goal", "project-data", "project-champion", "project-hills"):
            self.assertIn(i, ls)
            x = ls[i]
            self.assertTrue(x["fig"]["kind"]); self.assertTrue(x["checks"], i)
            self.assertLessEqual(x["say"].count(". "), 2, i)  # a sentence or two
            for c in x["checks"]:
                self.assertIn(c["a"], c["o"]); self.assertEqual(len(c["o"]), len(set(c["o"])))
        g = ls["goal"]["fig"]
        self.assertEqual((g["N"], g["have"], g["need"]), (40, 28, 36))  # this project's goal: 28 of 40, needs 36
        self.assertFalse(g.get("example"))
        self.assertEqual(ls["goal"]["checks"][0]["a"], "8")
        self.assertEqual(ls["gate"]["fig"]["rule"], "better")  # the candidate's own dev check
        self.assertEqual([r["rung"] for r in ls["ladder"]["fig"]["rungs"]], ["dev", "random10", "full"])
        sl = {r["name"]: r["n"] for r in ls["project-data"]["fig"]["rows"]}
        self.assertEqual((sl["full"], sl["random10"], sl["target"]), (40, 10, 20))

    def test_an_empty_project_still_teaches_with_examples(self):
        p = ledger()
        ls = {x["id"]: x for x in course.lessons(p)}
        self.assertTrue(ls["paired-delta"]["fig"]["example"])
        self.assertTrue(ls["goal"]["fig"]["example"])

    def test_spaced_review(self):
        t0 = 1_000_000.0
        rs = lambda *hits: [dict(t=t0 + i * DAY, item="gate", hit=h) for i, h in enumerate(hits)]
        m = course.memory(rs(True), now=t0)["gate"]
        self.assertEqual((m["run"], m["due"], m["is_due"]), (1, t0 + 1 * DAY, False))
        m = course.memory(rs(True, True, True), now=t0 + 2 * DAY)["gate"]
        self.assertEqual(m["due"], t0 + 2 * DAY + 7 * DAY)  # third right in a row: a week
        m = course.memory(rs(True, True, True, True, True), now=t0)["gate"]
        self.assertEqual(m["due"], t0 + 4 * DAY + 21 * DAY)  # and 21 days after that
        m = course.memory(rs(True, True, False), now=t0 + 2 * DAY)["gate"]
        self.assertEqual((m["run"], m["is_due"], m["learned"]), (0, True, True))  # a miss resets and is due now
        mem = course.memory(rs(True) + [dict(t=t0 - 5 * DAY, item="ladder", hit=True)], now=t0 + 2 * DAY)
        self.assertEqual(course.due(mem), ["ladder", "gate"])  # the most overdue first

    def test_record_per_person(self):
        self.assertEqual(course.record(self.p, dict(viewer="ann", item="nope", hit=True))[0], 404)
        code, d = course.record(self.p, dict(viewer="ann", item="gate", hit=False, how="review"))
        self.assertEqual(code, 200); self.assertTrue(d["memory"]["is_due"])
        course.record(self.p, dict(viewer="bob", item="gate", hit=True))
        row = json.loads((self.p.dir / "course.jsonl").read_text().splitlines()[0])
        self.assertEqual(set(row), {"t", "viewer", "item", "hit", "how"})  # simple rows another store can import
        self.assertEqual(course.summary(self.p, "ann")["due"], ["gate"])
        self.assertEqual(course.summary(self.p, "bob")["due"], [])
        b = learn.brief(self.p, 0, "ann")
        self.assertEqual(b["course"]["due"], ["gate"])

    def test_record_rejects_non_boolean_results(self):
        for value in ("false", 1, None, []):
            code, _ = course.record(self.p, dict(viewer="ann", item="gate", hit=value))
            self.assertEqual(code, 400)
        self.assertEqual(course.rows(self.p, "ann"), [])

    def test_achieved_goal_needs_no_negative_answers(self):
        self.p.open_goal("met", "Already met", "full", 0.5)
        data = course._ledger(self.p)
        data["goal"] = self.p.goal_status("met")
        lesson = course.lesson_goal(self.p, data, learn)
        self.assertEqual(lesson["checks"][0]["a"], "0")

    def test_cards_name_the_lessons_they_need(self):
        self.assertEqual(course.needs("promote|x"), ["champion", "paired-delta", "interval"])
        self.assertEqual(course.needs("nope|x"), [])
        for ids in course.NEEDS.values():
            self.assertTrue(set(ids) <= set(course.IDS))


if __name__ == "__main__":
    unittest.main()
