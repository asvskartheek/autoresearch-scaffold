"""Papers: the thread fold, agent polling and the reader's HTTP routes. Run: python3 -m unittest discover tests"""
import contextlib, io, json, socket, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path

from autoresearch import papers
from autoresearch.core import Project
from autoresearch.server import serve

ANCHOR = dict(block="b1", quote="some text", prefix="", suffix="")


def project():
    d = Path(tempfile.mkdtemp())
    (d / "research.json").write_text("{}")
    (d / ".research").mkdir()
    src = d / "p.html"
    src.write_text('<p data-block="b1">some text here</p>')
    p = Project(d)
    papers.add(p, "demo", src, title="Demo", hill="h")
    return p, src


class Threads(unittest.TestCase):
    def test_fold(self):
        p, _ = project()
        c = papers.post(p, "demo", "comment", body="why?", anchor=ANCHOR, author="Ann")
        th = papers.threads(papers.thread(p, "demo"))
        self.assertEqual(len(th), 1)
        self.assertTrue(th[0]["waiting"]); self.assertFalse(th[0]["thinking"])
        papers.post(p, "demo", "reply", parent=c["id"], body="because", agent=True, link=dict(label="x", url="#b1"))
        th = papers.threads(papers.thread(p, "demo"))[0]
        self.assertFalse(th["waiting"]); self.assertEqual(th["messages"][1]["link"]["url"], "#b1")
        r = papers.post(p, "demo", "reply", parent=c["id"], body="and?", author="Ann")
        self.assertTrue(papers.threads(papers.thread(p, "demo"))[0]["waiting"])  # a human follow-up re-opens the ask
        papers.post(p, "demo", "edit", target=r["id"], body="and then?", author="Ann")
        papers.post(p, "demo", "resolve", parent=c["id"], author="Ann")
        th = papers.threads(papers.thread(p, "demo"))[0]
        self.assertEqual(th["messages"][-1]["body"], "and then?"); self.assertTrue(th["resolved"]); self.assertFalse(th["waiting"])
        papers.post(p, "demo", "reopen", parent=c["id"], author="Ann")
        papers.post(p, "demo", "delete", target=r["id"], author="Ann")
        th = papers.threads(papers.thread(p, "demo"))[0]
        self.assertFalse(th["resolved"]); self.assertEqual(len(th["messages"]), 2)

    def test_poll_all_papers_marks_seen(self):
        p, src = project()
        papers.add(p, "other", src)
        papers.post(p, "other", "comment", body="q", anchor=ANCHOR, author="Bo")
        got = papers.poll(p, timeout=0)
        self.assertEqual([g["paper"] for g in got], ["other"])
        self.assertTrue(papers.threads(papers.thread(p, "other"))[0]["thinking"])
        self.assertEqual(sum(e["kind"] == "seen" for e in papers.thread(p, "other")), 1)
        papers.poll(p, timeout=0)  # polling again does not re-mark
        self.assertEqual(sum(e["kind"] == "seen" for e in papers.thread(p, "other")), 1)
        self.assertEqual(papers.poll(p, "demo", timeout=0), [])

    def test_attach_and_names(self):
        p, src = project()
        self.assertEqual(papers.attach(p, "demo", src), "/papers/demo/files/p.html")
        for bad in ("../x", ".hidden", ""):
            with self.assertRaises(KeyError):
                papers.file(p, "demo", bad)
        with self.assertRaises(KeyError):
            papers.pdir(p, "../etc")


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, _ = project()
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        with contextlib.redirect_stdout(io.StringIO()):
            threading.Thread(target=serve, args=(port, cls.p.root), daemon=True).start()
            time.sleep(0.4)
        cls.base = f"http://127.0.0.1:{port}"

    def req(self, path, body=None, origin=None):
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(r) as f:
                return f.status, f.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_flow(self):
        self.assertEqual(self.req("/papers/demo")[0], 200)
        self.assertIn(b"some text", self.req("/papers/demo/raw")[1])
        code, ev = self.req("/api/paper/demo/comment", dict(body="hi", anchor=ANCHOR, author="Ann"))
        self.assertEqual(code, 200); cid = json.loads(ev)["id"]
        self.assertEqual(self.req("/api/paper/demo/reply", dict(parent=cid, body="more", author="Ann"))[0], 200)
        self.assertEqual(self.req("/api/paper/demo/resolve", dict(parent=cid, author="Ann"))[0], 200)
        th = json.loads(self.req("/api/paper/demo")[1])["threads"]
        self.assertTrue(th[0]["resolved"]); self.assertEqual(len(th[0]["messages"]), 2)

    def test_rejects(self):
        self.assertEqual(self.req("/api/paper/demo/comment", dict(body="", anchor=ANCHOR))[0], 400)
        self.assertEqual(self.req("/api/paper/demo/comment", dict(body="x"))[0], 400)  # no anchor
        self.assertEqual(self.req("/api/paper/demo/reply", dict(parent="nope", body="x"))[0], 400)
        self.assertEqual(self.req("/api/paper/demo/seen", dict(parent="x"))[0], 404)  # people cannot mark seen
        self.assertEqual(self.req("/api/paper/demo/comment", dict(body="x", anchor=ANCHOR), origin="https://evil.com")[0], 403)
        _, ev = self.req("/api/paper/demo/comment", dict(body="mine", anchor=ANCHOR, author="Ann"))
        cid = json.loads(ev)["id"]
        self.assertEqual(self.req("/api/paper/demo/edit", dict(target=cid, body="x", author="Bo"))[0], 400)  # not Bo's
        self.assertEqual(self.req("/api/paper/demo/delete", dict(target=cid, author="Ann"))[0], 200)
        a = papers.post(self.p, "demo", "reply", parent=cid, body="agent says", agent=True)
        self.assertEqual(self.req("/api/paper/demo/edit", dict(target=a["id"], body="x", author="agent"))[0], 400)
        self.assertEqual(self.req("/papers/demo/files/..%2Fpaper.html")[0], 404)


if __name__ == "__main__":
    unittest.main()
