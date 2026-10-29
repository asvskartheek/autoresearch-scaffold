"""Comments on dashboard views and the `arx answer` daemon, with a fake agent. Run: python3 -m pytest -q tests"""
import json, os, stat, sys, tempfile, time, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import answer, comments, features, papers
from autoresearch.core import Project

ANCHOR = dict(route="model/v2", key=dict(href="#model/v2", card="div.card"), rel="h3:nth-of-type(1)", text="v2 · rejected",
              quote="rejected", rx=0.5, ry=0.5, shape=dict(tool="box", d="M0 0H10V10H0Z", bw=10, bh=10, fit=True, ox=0, oy=0))


def project():
    d = Path(tempfile.mkdtemp())
    (d / "research.json").write_text("{}")
    (d / ".research").mkdir()
    (d / "PROTOCOL.md").write_text("# P\n\n## Rules of evidence\n\n- Report n and the 90% interval.\n\n## Other\n\nx\n")
    return Project(d)


def fake_agent(d: Path, body: str) -> str:
    """A shell 'agent' that reads the prompt on stdin, notes progress and runs `body` (with $ARX_TASK, arx on PATH)."""
    f = d / "agent.sh"
    f.write_text(f"#!/bin/sh\ncat > \"$ARX_TASK.prompt\"\narx task note \"$ARX_TASK\" 'Reading the ledger'\n{body}\n")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return str(f)


class Fold(unittest.TestCase):
    def test_threads_and_routes(self):
        p = project()
        code, ev = features.POST[[x for x, _ in features.POST].index("/api/comments")][1](
            p, "/api/comments", dict(kind="comment", body="why rejected?", author="Ann", anchor=dict(ANCHOR, junk=1)))
        self.assertEqual(code, 200)
        self.assertNotIn("junk", ev["anchor"])
        th = comments.threads(comments.events(p))
        self.assertEqual(len(th), 1); self.assertTrue(th[0]["waiting"]); self.assertEqual(th[0]["route"], "model/v2")
        items = features.inbox(p)
        self.assertEqual([(i["kind"], i["ref"]) for i in items], [("comment", ev["id"])])
        comments.reply(p, ev["id"][3:7], "Because the gate failed.")  # id prefix without cm-
        th = comments.threads(comments.events(p))[0]
        self.assertFalse(th["waiting"]); self.assertTrue(th["messages"][-1]["agent"])
        comments.post(p, "resolve", parent=ev["id"])
        self.assertTrue(comments.threads(comments.events(p))[0]["resolved"])
        _, body = comments._get(p, "/api/comments", dict(route="overview"))
        self.assertEqual(body["threads"], [])

    def test_prompt(self):
        p = project()
        ev = comments.post(p, "comment", body="what is this?", author="Ann", anchor=ANCHOR)
        text = comments.prompt(p, dict(kind="comment", ref=ev["id"], payload=dict(thread=ev["id"])))
        for want in ("#model/v2", "v2 · rejected", "box", f"arx comment reply {ev['id']}", "90% interval", "<svg"):
            self.assertIn(want, text)


class Daemon(unittest.TestCase):
    def run_daemon(self, p, cmd, budget=60):
        os.environ["ARX_AGENT_CMD"] = cmd
        try:
            answer.main(p, jobs=4, budget_s=budget, once=True, interval=0.2)
        finally:
            os.environ.pop("ARX_AGENT_CMD", None)

    def test_answers(self):
        p = project()
        ev = comments._post(p, "/api/comments", dict(kind="comment", body="hi", author="Ann", anchor=ANCHOR))[1]
        self.run_daemon(p, fake_agent(p.root, 'arx comment reply "$(arx comment ls --waiting | cut -d" " -f1)" "Hello <svg width=\\"20\\" height=\\"20\\"><rect width=\\"10\\" height=\\"10\\"/></svg>"'))
        th = comments.find(p, ev["id"])
        self.assertEqual(len(th["messages"]), 2, th)
        self.assertTrue(th["messages"][1]["agent"]); self.assertIn("<svg", th["messages"][1]["body"])
        item = features.inbox(p)[0]
        self.assertEqual(item["status"], "done")
        t = p.task(item["task"])
        self.assertEqual((t["kind"], t["status"], t["budget_s"]), ("answer", "done", 60))
        self.assertIn("Reading the ledger", [e["msg"] for e in p.events(item["task"])])
        self.assertIn("arx comment reply", (p.root / f"{item['task']}.prompt").read_text())

    def test_failure_and_silence(self):
        p = project()
        a = comments._post(p, "/api/comments", dict(kind="comment", body="alpha", anchor=ANCHOR))[1]
        b = comments._post(p, "/api/comments", dict(kind="comment", body="beta", anchor=ANCHOR))[1]
        self.run_daemon(p, fake_agent(p.root, 'case "$(cat $ARX_TASK.prompt)" in *alpha*) exit 3;; esac'))
        ma, mb = comments.find(p, a["id"])["messages"], comments.find(p, b["id"])["messages"]
        self.assertIn("exit code 3", ma[-1]["body"]); self.assertTrue(ma[-1]["error"])
        self.assertIn("without replying", mb[-1]["body"])
        self.assertEqual({i["status"] for i in features.inbox(p)}, {"failed"})

    def test_usage_limit_requeues(self):
        p = project()
        a = comments._post(p, "/api/comments", dict(kind="comment", body="later", anchor=ANCHOR))[1]
        self.run_daemon(p, fake_agent(p.root, "echo \"You've hit your session limit · resets 11:20pm (Asia/Calcutta)\"; exit 1"))
        th = comments.find(p, a["id"])
        self.assertEqual(len(th["messages"]), 1)  # no failure reply: the question waits its turn
        item = features.inbox(p)[0]
        self.assertEqual(item["status"], "queued"); self.assertGreater(item["not_before"], time.time())
        self.assertEqual(features.pending(p), [])
        self.assertIn("usage limit", comments.with_agent(p, [th])[0]["agent"]["note"])
        self.assertIsNone(answer.limited(Path(p.root / "research.json")))

    def test_silent_question_agent_is_not_answered(self):
        from autoresearch import questions
        p = project()
        q = questions.ask(p, "Give me an intro to the data") if hasattr(questions, "ask") else None
        self.assertIsNotNone(q)
        self.run_daemon(p, fake_agent(p.root, "echo 'a glossary written only to the log'"))
        item = features.inbox(p)[0]
        self.assertEqual(item["status"], "failed")
        rec = questions.stored(p)[q["id"]]
        self.assertEqual(rec["status"], "open"); self.assertIn("without replying", rec["error"])

    def test_timeout(self):
        p = project()
        a = comments._post(p, "/api/comments", dict(kind="comment", body="slow", anchor=ANCHOR))[1]
        self.run_daemon(p, fake_agent(p.root, "sleep 60"), budget=1)
        self.assertIn("budget", comments.find(p, a["id"])["messages"][-1]["body"])
        self.assertEqual(p.task(features.inbox(p)[0]["task"])["status"], "budget")

    def test_merges_and_papers(self):
        p = project()
        a = comments._post(p, "/api/comments", dict(kind="comment", body="first", anchor=ANCHOR))[1]
        comments._post(p, "/api/comments", dict(kind="reply", parent=a["id"], body="and also"))
        src = p.root / "paper.html"; src.write_text('<p data-block="b1">text</p>')
        papers.add(p, "demo", src)
        c = papers.post(p, "demo", "comment", body="why?", anchor=dict(block="b1", quote="text"), author="Ann")
        self.run_daemon(p, fake_agent(p.root, 'if [ -n "$(grep -l "paper reply" $ARX_TASK.prompt)" ]; then '
                                              f'arx paper reply demo {c["id"]} "paper answer"; '
                                              f'else arx comment reply {a["id"]} "comment answer"; fi'))
        msgs = comments.find(p, a["id"])["messages"]
        self.assertEqual([m["body"] for m in msgs], ["first", "and also", "comment answer"])  # one answer for two asks
        th = papers.threads(papers.thread(p, "demo"))[0]
        self.assertEqual(th["messages"][-1]["body"], "paper answer"); self.assertFalse(th["waiting"])
        self.assertEqual(sorted(i.get("result", i["status"]) for i in features.inbox(p)), ["done", "done", "merged"])

    def test_recover_and_lock(self):
        p = project()
        a = comments._post(p, "/api/comments", dict(kind="comment", body="x", anchor=ANCHOR))[1]
        item = features.inbox(p)[0]
        features.update(p, item["id"], status="running")
        answer.recover(p)
        self.assertIn("interrupted", comments.find(p, a["id"])["messages"][-1]["body"])
        self.assertIsNone(answer.running_pid(p))


if __name__ == "__main__":
    unittest.main()
