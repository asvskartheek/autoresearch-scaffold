"""Long answers: a question that asks to explain something gets an HTML document stored in .research/answers/,
shown in its thread as the first figure plus an #answer/<id> link. Storage, the route, the CLI and the prompt choice."""
import os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import answer, comments, features, papers, questions as q
from tests.test_comments import ANCHOR, fake_agent, project
from tests.test_questions import ledger, run

FIG = '<svg viewBox="0 0 400 120" width="400"><rect x="0" y="0" width="200" height="20"/><text x="4" y="40" font-size="12">n 20</text></svg>'
DOC = f"<!doctype html><html><head><title>Intro to the data</title></head><body><section data-block=\"a\">{FIG}</section>" \
      "<section data-block=\"b\"><svg viewBox=\"0 0 10 10\"><circle r=\"3\"/></svg></section></body></html>"


class Storage(unittest.TestCase):
    def test_save_read_and_route(self):
        p = project()
        did = comments.save_doc(p, DOC)
        self.assertTrue(did.startswith("a-"))
        f = comments.doc_path(p, did)
        self.assertEqual(f, p.dir / "answers" / f"{did}.html")
        self.assertEqual(f.read_text(), DOC)
        self.assertEqual(comments.first_figure(DOC), FIG)  # the first svg, not the second
        self.assertEqual(comments.doc_title(DOC), "Intro to the data")
        code, body, ctype, headers = comments._get_doc(p, f"/api/answers/{did}", dict(theme="dark"))
        self.assertEqual((code, ctype), (200, "text/html; charset=utf-8"))
        self.assertIn(b'<html data-theme="dark">', body)
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        code, meta = comments._get_doc(p, f"/api/answers/{did}", dict(meta="1"))
        self.assertEqual((meta["id"], meta["title"], meta["figure"]), (did, "Intro to the data", FIG))

    def test_ids_and_bad_input(self):
        p = project()
        self.assertEqual(comments.save_doc(p, DOC, "g:Ninety"), "g-ninety")
        for bad in ("../x", "", "a/b", "x" * 80):
            with self.assertRaises(KeyError):
                comments.doc_path(p, bad)
        self.assertEqual(comments._get_doc(p, "/api/answers/nope", {})[0], 404)
        for html in ("", "   ", "plain text"):
            with self.assertRaises(ValueError):
                comments.save_doc(p, html)
        with self.assertRaises(ValueError):
            comments.save_doc(p, "<p>" + "x" * comments.DOC_MAX)
        self.assertIsNone(comments.first_figure("<p>no figure</p>"))
        self.assertIsNone(comments.first_figure("<svg>" + "x" * comments.FIG_MAX + "</svg>"))

    def test_comment_reply_with_doc(self):
        p = project()
        ev = comments.post(p, "comment", body="Give me an intro to the data", author="Ann", anchor=ANCHOR)
        body = comments.doc_reply(p, ev["id"], DOC, "1,319 problems; the champion solves 1,224.")
        self.assertTrue(body.startswith(FIG))
        did = body.rsplit("#answer/", 1)[1]
        self.assertEqual(comments.doc_path(p, did).read_text(), DOC)
        with self.assertRaises(KeyError):  # an unknown thread stores nothing
            comments.doc_reply(p, "cm-nope", DOC)
        self.assertEqual(len(list((p.dir / "answers").glob("*.html"))), 1)


class Questions(unittest.TestCase):
    def test_answer_with_doc(self):
        p = ledger()
        p.add_model("base", parent="", status="champion")
        run(p, "base", [1] * 14 + [0] * 6)
        r = q.ask(p, "Give me an intro to the data")
        q.settle(p, r["id"], "answered", "20 problems; the champion solves 14.", doc=DOC)
        self.assertEqual(q.stored(p)[r["id"]]["doc"], r["id"])
        n = next(x for x in q.tree(p)["nodes"] if x["id"] == r["id"])
        self.assertEqual((n["doc"], n["fig"]), (r["id"], FIG))
        q.settle(p, r["id"], "answered", "Short again.")  # a short re-answer keeps the document
        self.assertEqual(q.stored(p)[r["id"]]["doc"], r["id"])
        with self.assertRaises(SystemExit):
            q.settle(p, r["id"], "answered", "x", doc="not html")


class PromptChoice(unittest.TestCase):
    def test_hint(self):
        for t in ("Give me an intro to the GSM8K data", "How does the agent work?", "Walk me through the ladder",
                  "explain the percent base"):
            self.assertTrue(comments.wants_long(t), t)
        for t in ("Why did v3 lose?", "What is n on the target slice?", "Is the gain real?"):
            self.assertFalse(comments.wants_long(t), t)

    def test_comment_prompt_offers_both(self):
        p = project()
        for body, hinted in (("Give me an intro to the data", True), ("why rejected?", False)):
            ev = comments.post(p, "comment", body=body, author="Ann", anchor=ANCHOR)
            text = comments.prompt(p, dict(kind="comment", ref=ev["id"], payload=dict(thread=ev["id"])))
            self.assertIn(f'arx comment reply {ev["id"]} "<answer>"', text)  # the short path still works
            self.assertIn("one or two short plain sentences", text)
            self.assertIn(f"arx comment reply {ev['id']} --doc -", text)
            self.assertIn("data-block", text)
            self.assertEqual("a long answer is probably right" in text, hinted)

    def test_question_prompt_offers_both(self):
        p = ledger()
        for title, hinted in (("How does the agent work?", True), ("Did base beat the hint?", False)):
            r = q.ask(p, title)
            item = next(i for i in features.inbox(p) if i.get("ref") == r["id"])
            text = features.PROMPTS["question"](p, item)
            self.assertIn(f'arx q answer {r["id"]} "<claim>" --evidence', text)
            self.assertIn("--doc -", text)
            self.assertEqual("a long answer is probably right" in text, hinted)

    def test_paper_prompt_offers_both(self):
        p = project()
        src = p.root / "paper.html"; src.write_text('<p data-block="b1">text</p>')
        papers.add(p, "demo", src)
        c = papers.post(p, "demo", "comment", body="Explain this section", anchor=dict(block="b1", quote="text"), author="Ann")
        text = answer.paper_prompt(p, dict(payload=dict(paper="demo", thread=c["id"])))
        self.assertIn(f'arx paper reply demo {c["id"]} "<answer>"', text)
        self.assertIn("arx comment doc --doc -", text)
        self.assertIn("/#answer/<id>", text)
        self.assertIn("a long answer is probably right", text)


class EndToEnd(unittest.TestCase):
    def test_agent_posts_a_doc_on_stdin(self):
        p = project()
        ev = comments.post(p, "comment", body="Give me an intro to the data", author="Ann", anchor=ANCHOR)
        features.enqueue(p, "comment", dict(thread=ev["id"], message=ev["id"]), ref=ev["id"])
        os.environ["ARX_AGENT_CMD"] = fake_agent(p.root, f"arx comment reply {ev['id']} --doc - \"An intro.\" <<'HTML'\n{DOC}\nHTML")
        try:
            answer.main(p, jobs=1, budget_s=60, once=True, interval=0.2)
        finally:
            os.environ.pop("ARX_AGENT_CMD", None)
        last = comments.threads(comments.events(p))[0]["messages"][-1]
        self.assertTrue(last["agent"])
        self.assertTrue(last["body"].startswith(FIG))
        self.assertIn("An intro.", last["body"])
        did = last["body"].rsplit("#answer/", 1)[1]
        self.assertIn("Intro to the data", comments.doc_path(p, did).read_text())


if __name__ == "__main__":
    unittest.main()
