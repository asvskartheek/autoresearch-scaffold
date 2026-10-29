"""Questions, round 2: pooled numbers for answers, prompts, hand-offs, notes, comment threads and readable titles."""
import os, tempfile, unittest

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import comments, features, questions as q
from autoresearch.core import Task
from tests.test_questions import ledger, run


class R2(unittest.TestCase):
    def setUp(self):
        self.p = p = ledger()
        p.add_model("base", parent="", status="champion", title="Plain base")
        run(p, "base", [1] * 14 + [0] * 6)
        run(p, "base", [1] * 5 + [0] * 5, "ds/hard")
        run(p, "base", [1] * 6 + [0] * 4, "ds/hard")  # a repeat run: pooled, 5.5 of 10 -> 6 (rounded) everywhere
        p.open_goal("ninety", "Ninety on full", "full", 0.9)
        p.open_hill("hard", "Hard ones", "ds/hard", goal="ninety", symptom="The hard ones fail.")
        p.add_model("base+hint", parent="base", hill="hard", change="Add a hint line.", title="Hint line")
        run(p, "base+hint", [1] * 8 + [0] * 2, "ds/hard")

    def test_numbers_are_pooled_and_paired(self):
        lines = q.number_lines(self.p, ["base", "base+hint"])
        text = "\n".join(lines)
        self.assertIn("Plain base [base] (champion)", text)
        self.assertIn("ds/hard: 6 of 10 (pooled over 2 runs)", text)
        self.assertIn("ds/hard: 8 of 10 (1 run); vs Plain base [base] 6 of 10: +25.0 pts", text)
        self.assertIn("ds/full: 14 of 20 (1 run)", text)
        with self.assertRaises(SystemExit):
            q.number_lines(self.p, ["nope"])

    def test_every_prompt_carries_the_pooled_numbers_and_titles(self):
        brief = q.ledger_brief(self.p)
        self.assertIn("arx q numbers", brief)
        self.assertIn("14 of 20 on ds/full", brief)
        self.assertIn("4 more of 20", brief)  # the goal gap as the page reads it, never re-subtracted by the agent
        it = q.ask(self.p, "How did the gate decide this?", parent="h:hard")
        text = q._prompt(self.p, dict(ref=it["id"], payload={}))
        self.assertIn("base+hint: Hint line", text)
        self.assertIn("Name models by their titles", text)
        self.assertIn("ds/hard: 6 of 10 (pooled over 2 runs)", text)
        self.assertIn("a long answer is probably right", text)
        self.assertIn("--choice", text)
        self.assertIn("--why", text)
        ev = comments.post(self.p, "comment", body="How many?", author="Ann", anchor=dict(route="overview"))
        ctext = comments.prompt(self.p, dict(kind="comment", ref=ev["id"], payload=dict(thread=ev["id"])))
        self.assertIn("ds/hard: 6 of 10 (pooled over 2 runs)", ctext)

    def test_how_questions_read_as_long(self):
        for t in ("How does the gate decide that this candidate passed?", "How did the gate decide this hill was climbed?",
                  "What does the gate do?"):
            self.assertTrue(comments.wants_long(t), t)
        for t in ("Which candidate is closest to the target?", "How many does the champion get right?"):
            self.assertFalse(comments.wants_long(t), t)

    def test_hand_off_keeps_why_choices_and_evidence(self):
        a = q.add(self.p, "Rerun the stalled evals?", parent="h:hard", needs_human=True, choices=["Rerun", "Drop"],
                  why="Two runs stopped at 4 of 10.", evidence=q.parse_evidence(self.p, ["base+hint:hard"]))
        n = {x["id"]: x for x in q.tree(self.p)["nodes"]}[a["id"]]
        self.assertEqual((n["why"], n["choices"]), ("Two runs stopped at 4 of 10.", ["Rerun", "Drop"]))
        self.assertEqual(n["ev"][0]["kind"], "paired")

    def test_a_run_cited_twice_draws_once(self):
        tid = next(t["id"] for t in self.p.evals() if t.get("model") == "base+hint")
        a = q.add(self.p, "Does the hint hold?", parent="h:hard",
                  evidence=q.parse_evidence(self.p, ["base+hint:hard", f"task:{tid}", "base+hint:hard"]))
        n = {x["id"]: x for x in q.tree(self.p)["nodes"]}[a["id"]]
        self.assertEqual([e["kind"] for e in n["ev"]], ["paired"])

    def test_notes_leave_out_tooling_dicts_and_other_questions_evidence(self):
        p = self.p
        t = Task(p, "paper", "Port the goal paper", model="base")
        t.note("Draft goal paper ninety published (paper check 0 errors, 0 warnings)")
        t.finish()
        t = Task(p, "analysis", "Look at base on hard", model="base")
        t.note("Base misses the long multi-step ones on the hard slice, about half of them.")
        t.finish()
        p.log_decision("reject", model="base+hint", reason="Lower CI not above zero. {'n': 10, 'delta': 0.1}")
        texts = [x["text"] for x in q.notes(p, "g:ninety")]
        self.assertFalse(any("paper check" in x for x in texts), texts)
        self.assertIn("Lower CI not above zero.", texts)
        a = q.add(p, "Is base the best here?", parent="h:hard", evidence=q.parse_evidence(p, ["base:hard"]))
        self.assertEqual(q.notes(p, a["id"]), [])  # the champion's own run notes stay on the champion's question


if __name__ == "__main__":
    unittest.main()
