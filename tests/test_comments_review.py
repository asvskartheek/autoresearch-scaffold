"""Review fixes for comments and `arx answer` (tester-7): agent command parsing, shim cleanup, daemon state, anchors.
Run: python3 -m pytest -q tests"""
import os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import answer, comments, features
from autoresearch.core import Project


def project():
    d = Path(tempfile.mkdtemp())
    (d / "research.json").write_text("{}")
    (d / ".research").mkdir()
    return Project(d)


class AgentCmd(unittest.TestCase):
    def test_quoted_args(self):
        os.environ["ARX_AGENT_CMD"] = 'claude -p --append-system-prompt "be brief please"'
        try:
            self.assertEqual(features.agent_cmd(), ["claude", "-p", "--append-system-prompt", "be brief please"])
        finally:
            os.environ.pop("ARX_AGENT_CMD", None)

    def test_shim_removed_on_exit(self):
        p = project()
        made = []
        real = answer._shim
        answer._shim = lambda: made.append(real()) or made[-1]
        try:
            answer.main(p, once=True, interval=0.1)
        finally:
            answer._shim = real
        self.assertEqual(len(made), 1)
        self.assertFalse(Path(made[0]).exists())


class AgentState(unittest.TestCase):
    def test_no_daemon(self):
        p = project()
        st = {}
        answer._state(p, st)
        self.assertEqual(st["answer_agent"], dict(running=False, pid=None))
        self.assertIn(answer._state, features.STATE)
        self.assertEqual(comments._get(p, "/api/comments", {})[1]["answer_agent"]["running"], False)


class Describe(unittest.TestCase):
    def test_arrow_names_the_tip(self):
        a = dict(route="goals", text="1,224", what="span.tick", ctx="GSM8K 96%", rx=0.43, ry=0.5,
                 shape=dict(tool="arrow", mode="tip"), **{"from": "43 more"})
        text = "\n".join(comments.describe_anchor(a))
        for want in ('an arrow pointing at "1,224"', "span.tick", "43% across", 'starts at: "43 more"', 'Inside: "GSM8K 96%"'):
            self.assertIn(want, text)

    def test_box_and_highlight(self):
        box = comments.describe_anchor(dict(text="Candidates 3", what="div.kpi", shape=dict(tool="box", fit=True)))
        self.assertIn('Drawn: a box around "Candidates 3" (a div.kpi element)', box)
        hl = comments.describe_anchor(dict(text="x", quote="43 more", shape=dict(tool="highlight", mode="text")))
        self.assertIn('Drawn: a highlight over the text "43 more"', hl)

    def test_old_anchor_article(self):
        old = comments.describe_anchor(dict(text="card", shape=dict(tool="arrow", bw=10, bh=3)))
        self.assertIn("Drawn: an arrow (10 x 3 px) on that element", old)

    def test_new_anchor_keys_kept(self):
        p = project()
        ev = comments._post(p, "/api/comments", dict(kind="comment", body="?", anchor=dict(route="goals", qn=1, what="b", ctx="c", **{"from": "f"})))[1]
        self.assertEqual({k: ev["anchor"][k] for k in ("qn", "what", "ctx", "from")}, dict(qn=1, what="b", ctx="c", **{"from": "f"}))


if __name__ == "__main__":
    unittest.main()
