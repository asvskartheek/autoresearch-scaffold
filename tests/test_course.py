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
        self.assertEqual(ls["goal"]["checks"][0]["a"], "2")  # 28 right, 8 fixed, 2 broken: 2 short of 36
        self.assertIn("champion must meet the target", ls["goal"]["checks"][1]["a"])
        self.assertEqual(ls["gate"]["fig"]["rule"], "better")  # the candidate's own dev check
        self.assertEqual([r["rung"] for r in ls["ladder"]["fig"]["rungs"]], ["dev", "random10", "full"])
        sl = {r["name"]: r["n"] for r in ls["project-data"]["fig"]["rows"]}
        self.assertEqual((sl["full"], sl["random10"], sl["target"]), (40, 10, 20))

    def test_an_empty_project_still_teaches_with_examples(self):
        p = ledger()
        ls = {x["id"]: x for x in course.lessons(p)}
        self.assertTrue(ls["paired-delta"]["fig"]["example"])
        self.assertEqual(ls["goal"]["fig"]["rows"], [])
        self.assertIn("No goal", ls["goal"]["say"])

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

    def test_met_goal_uses_an_evidence_check_instead_of_numeric_distractors(self):
        self.p.open_goal("met", "Already met", "full", 0.5)
        data = course._ledger(self.p)
        data["goals"] = [self.p.goal_status("met")]
        lesson = course.lesson_goal(self.p, data, learn)
        self.assertTrue(lesson["checks"])
        self.assertTrue(all(not option.lstrip("-").isdigit() for c in lesson["checks"] for option in c["o"]))

    def test_checks_use_this_projects_numbers_with_plausible_distractors(self):
        ls = {x["id"]: x for x in course.lessons(self.p)}
        more = ls["goal"]["checks"][0]
        self.assertIn("28 of 40", more["q"]); self.assertIn("ds/full", more["q"]); self.assertIn("breaks 2", more["q"])
        self.assertEqual(more["o"], ["2", "0", "8", "6"])  # the answer, then slips: nothing left, ignoring the breaks, net gain
        one = ls["slice"]["checks"][0]
        self.assertIn("ds/target", one["q"]); self.assertEqual(one["a"], "+5 pts")
        self.assertIn("+2.5 pts", one["o"])  # the slip: dividing by the bigger slice's 40
        self.assertEqual(ls["project-data"]["checks"][0]["a"], "ds/random10")
        on = ls["project-goal"]["checks"][0]
        self.assertEqual(on["a"], "No: it is measured only on ds/full"); self.assertIn("ds/random10", on["q"])
        gate = ls["gate"]["checks"][0]
        self.assertIn("+30 pts", gate["q"]); self.assertIn("−30 pts", gate["q"]); self.assertEqual(gate["a"], "Fail")
        ci = ls["interval"]["checks"][0]  # the example interval, +1.6 [−0.5, +3.7] at n = 185: 185 × (2.1 / 1.6)² ≈ 319
        self.assertEqual(ci["a"], "About 320"); self.assertIn("About 240", ci["o"])  # 240: forgot to square
        paired = ls["paired-delta"]["checks"][0]
        self.assertEqual(paired["a"], "−6.5 pts"); self.assertEqual(len(paired["o"]), 4)  # 12 fixed, 5 broken, 10 flip: (2 − 15) / 200
        for x in ls.values():
            for c in x["checks"]:
                self.assertIn(c["a"], c["o"]); self.assertEqual(len(c["o"]), len(set(c["o"])))

    def test_champion_checks_are_asked_from_the_ledger(self):
        run(self.p, "cand", [1] * 22 + [0] * 18)
        self.p.add_model("cand3", parent="base", hill="h1", change="cand3")
        run(self.p, "cand3", [1] * 25 + [0] * 15)
        self.p.set_model_status("cand3", "rejected", "worse on full")
        ls = {x["id"]: x for x in course.lessons(self.p)}
        lead = ls["champion"]["checks"][0]
        self.assertIn("than cand3?", lead["q"]); self.assertEqual(lead["a"], "3")  # 28 against the runner-up's 25
        rej = next(c for c in ls["candidate"]["checks"] if c["q"].startswith("How many candidates"))
        self.assertEqual(rej["a"], "1")
        self.assertTrue(all(0 <= int(o) <= len(self.p.models()) for o in rej["o"]))
        self.p.add_model("cand4", parent="base", hill="h1", change="cand4")
        run(self.p, "cand4", [1] * 30 + [0] * 10)  # above the champion's 28
        above = course.lesson_champion(self.p, course._ledger(self.p), learn)["checks"][0]
        self.assertIn("30 of 40", above["q"]); self.assertEqual(above["a"], "No: only a recorded promotion changes the champion")

    def test_cards_name_the_lessons_they_need(self):
        self.assertEqual(course.needs("promote|x"), ["champion", "paired-delta", "interval"])
        self.assertEqual(course.needs("nope|x"), [])
        for ids in course.NEEDS.values():
            self.assertTrue(set(ids) <= set(course.IDS))


if __name__ == "__main__":
    unittest.main()
