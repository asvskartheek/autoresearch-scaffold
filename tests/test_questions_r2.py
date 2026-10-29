"""Questions, round 2: pooled numbers for answers, prompts, hand-offs, notes, comment threads and readable titles."""
import json, os, tempfile, unittest

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

    def test_leaderboard_and_answer_agree_after_repeats_and_supersession(self):
        from autoresearch import server
        p = self.p
        latest = run(p, "base", [1] * 6 + [0] * 4, "ds/hard")
        row = server.state(p)["leaderboard"]["ds/hard"]["base"]
        self.assertAlmostEqual(row["score"], sum(p.pooled_scores("base", "ds/hard").values()) / 10)
        self.assertEqual((row["n"], row["runs"]), (10, 3))
        p.supersede("base", "ds/hard", latest.id)
        row = server.state(p)["leaderboard"]["ds/hard"]["base"]
        self.assertEqual((row["score"], row["runs"]), (0.6, 1))

    def test_contract_scoped_evidence_agrees_with_gate_and_leaderboard(self):
        from autoresearch import server
        p = self.p
        p.add_slice("ds/contract", list(range(4)))
        cfg = p.config | dict(ladder=[dict(rung="full", checks=[dict(slice="ds/contract", rule="better")])])
        (p.root / "research.json").write_text(json.dumps(cfg))
        for model, contract, scores in (("base", "A", [1, 1, 0, 0]),
                                         ("base", "B", [1, 1, 1, 1]),
                                         ("base+hint", "B", [0, 0, 0, 0]),
                                         ("base+hint", "A", [1, 1, 1, 0])):
            task = Task(p, "eval", model, model=model, slice="ds/contract", config=dict(baseline_contract=contract))
            for i, score in enumerate(scores):
                task.add_row(dict(id=str(i), score=score))
            task.finish()
        gate = p.gate("base+hint")["rungs"][0]["checks"][0]
        node = q.add(p, "Does it improve?", evidence=[dict(model="base+hint", slice="ds/contract")])
        ev = next(n for n in q.tree(p)["nodes"] if n["id"] == node["id"])["ev"][0]
        self.assertEqual((ev["delta"], ev["runs"], ev["base_runs"]), (gate["delta"], 1, 1))
        self.assertEqual((ev["c"], ev["bc"]), (3, 2))
        board = server.state(p)["leaderboard"]["ds/contract"]
        self.assertEqual((board["base+hint"]["score"], board["base+hint"]["runs"]), (gate["cand"], 1))
        self.assertEqual(board["base+hint"]["baseline_contract"], "A")
        self.assertEqual(board["base"]["baseline_contract"], "B")
        self.assertEqual(server.task_detail(p, task.id)["vs_champion"]["delta"], gate["delta"])
        text = "\n".join(q.number_lines(p, ["base+hint"], ["ds/contract"]))
        self.assertIn("ds/contract: 3 of 4 (1 run); vs Plain base [base] 2 of 4: +25.0 pts", text)

    def test_half_counts_match_browser_rounding(self):
        p = self.p
        p.add_model("half", parent="", title="Half")
        run(p, "half", [1] * 4 + [0] * 6, "ds/hard")
        run(p, "half", [1] * 5 + [0] * 5, "ds/hard")
        text = "\n".join(q.number_lines(p, ["half"]))
        self.assertIn("ds/hard: 5 of 10", text)  # Math.round(4.5), not Python's round-to-even 4

    def test_continuous_evidence_keeps_subunit_precision(self):
        p = self.p
        p.add_slice("ds/seconds", list(range(2)), scale="continuous", unit="s")
        run(p, "base", [-0.21, -0.23], "ds/seconds")
        run(p, "base+hint", [-0.11, -0.13], "ds/seconds")
        node = q.add(p, "Faster?", evidence=[dict(model="base+hint", slice="ds/seconds")])
        ev = next(n for n in q.tree(p)["nodes"] if n["id"] == node["id"])["ev"][0]
        self.assertAlmostEqual(ev["c"] / ev["n"], -0.12)
        self.assertAlmostEqual(ev["bc"] / ev["n"], -0.22)
        text = "\n".join(q.number_lines(p, ["base+hint"], ["ds/seconds"]))
        self.assertIn("n = 2", text)
        self.assertIn("0.1 s (90% CI", text)
        self.assertNotIn("fixed", text)

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

    def test_comment_answers_show_in_questions(self):
        p = self.p
        th = comments.post(p, "comment", body="Why is the hint better here?", author="Ann", anchor=dict(route="hill/hard"))
        comments.reply(p, th["id"], '<svg viewBox="0 0 10 10"></svg>\nIt fixes 3 of 10. More here.\n#answer/a-12345678')
        comments.post(p, "comment", body="Ping @Bob", author="Ann", anchor=dict(route="overview"), mentions=["bob"])
        wait = comments.post(p, "comment", body="And on the full set?", author="Ann", anchor=dict(route="overview"))
        t = {n["id"]: n for n in q.tree(p)["nodes"]}
        n = t["c:" + th["id"]]
        self.assertEqual((n["parent"], n["status"], n["claim"], n.get("doc"), n["thread"]),
                         ("h:hard", "answered", "It fixes 3 of 10.", None, th["id"]))  # no such doc file: dropped
        self.assertEqual((t["c:" + wait["id"]]["parent"], t["c:" + wait["id"]]["status"]), ("x:comments", "agent"))
        self.assertEqual(sum(1 for k in t if k.startswith("c:")), 2)  # people talking to people stay in comments
        self.assertIn("running", q.tree(p)["answer_agent"])

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


class Titles(unittest.TestCase):
    def test_model_questions_read_without_raw_ids(self):
        ms = {"v0": {}, "v1": dict(parent="v0", change="Persist encoded icons to files keyed by version, so a cold start skips it."),
              "a-32768-v1": dict(title="Universal numeric line"), "a-8192-v1": dict(title="Universal numeric line"),
              "base.r2": {}, "base": dict(title="Plain base")}
        self.assertEqual(q._model_title("v1", ms["v1"], ms), "Persist encoded icons to files keyed by…: does it help?")
        self.assertEqual(q._model_title("base.r2", {}, ms), "Does Plain base hold on rerun 2?")
        out = {f"m:{k}": dict(seed="model", parent="h:x", model=k, title=q._model_title(k, ms[k], ms))
               for k in ("a-32768-v1", "a-8192-v1")}
        q._distinct_siblings(out, ms)
        self.assertEqual(out["m:a-32768-v1"]["title"], "Does Universal numeric line help (32768)?")
        self.assertEqual(out["m:a-8192-v1"]["title"], "Does Universal numeric line help (8192)?")
