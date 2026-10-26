"""Papers: the thread fold, agent polling and the reader's HTTP routes. Run: python3 -m unittest discover tests"""
import contextlib, http.client, io, json, os, socket, subprocess, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # the server registers projects; never touch the real ~/.arx
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

    def test_at_agent_summons_with_whole_thread(self):
        p, _ = project()
        c = papers.post(p, "demo", "comment", body="Ann and Bo talk", anchor=ANCHOR, author="Ann")
        papers.post(p, "demo", "reply", parent=c["id"], body="noted", agent=True)
        papers.post(p, "demo", "resolve", parent=c["id"], author="Ann")
        papers.post(p, "demo", "reply", parent=c["id"], body="email me at bo@agentcorp.com", author="Bo")
        self.assertEqual(papers.pending(papers.thread(p, "demo")), [])  # resolved, no mention
        papers.post(p, "demo", "reply", parent=c["id"], body="@agent can you check this again?", author="Bo")
        [th] = papers.poll(p, "demo", timeout=0)
        self.assertTrue(th["mention"]); self.assertTrue(th["resolved"])
        self.assertEqual([m["body"][:4] for m in th["messages"]], ["Ann ", "note", "emai", "@age"])
        papers.post(p, "demo", "reply", parent=c["id"], body="done", agent=True)
        self.assertEqual(papers.pending(papers.thread(p, "demo")), [])

    def test_concurrent_appends_never_interleave(self):
        p, _ = project()
        big = "x" * 20000  # past one stdio buffer: a buffered write could split the line
        def w(i):
            for j in range(40):
                papers.post(p, "demo", "comment", body=f"{i}-{j}-{big}", anchor=ANCHOR, author="Ann")
        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        lines = (papers.pdir(p, "demo") / "thread.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 320)
        self.assertEqual(len(papers.threads([json.loads(l) for l in lines])), 320)

    def test_malformed_lines_are_skipped(self):
        p, _ = project()
        c = papers.post(p, "demo", "comment", body="ok", anchor=ANCHOR)
        with open(papers.pdir(p, "demo") / "thread.jsonl", "a") as f:
            f.write('{"half": \n[1,2]\n"str"\n{"kind": "reply"}\n{"id": 5, "kind": "comment"}\n'
                    '{"id": "zz", "kind": "nope"}\n{"id": "s1", "kind": "seen", "parent": "missing"}\n')
        papers.post(p, "demo", "reply", parent=c["id"], body="still works", agent=True)
        th = papers.threads(papers.thread(p, "demo"))
        self.assertEqual([len(t["messages"]) for t in th], [2])

    def test_threads_survive_republish(self):
        p, src = project()
        c = papers.post(p, "demo", "comment", body="hi", anchor=ANCHOR)
        v = papers.version(p, "demo"); time.sleep(0.02)
        src.write_text('<p data-block="b0">new intro</p><p data-block="b1">some text here, edited</p>')
        papers.add(p, "demo", src)
        self.assertGreater(papers.version(p, "demo"), v)
        self.assertEqual(papers.threads(papers.thread(p, "demo"))[0]["anchor"]["block"], "b1")
        self.assertEqual(papers.papers(p)["demo"]["title"], "Demo")  # meta kept on republish

    def test_many_threads_fold_fast(self):
        log = []
        for i in range(3000):
            log.append(dict(id=f"c{i}", t="", kind="comment", body="q", anchor=ANCHOR))
            log.append(dict(id=f"s{i}", t="", kind="seen", parent=f"c{i}"))
            log.append(dict(id=f"r{i}", t="", kind="reply", parent=f"c{i}", body="a", agent=True))
        t0 = time.time(); th = papers.threads(log)
        self.assertEqual(len(th), 3000); self.assertLess(time.time() - t0, 0.5)


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "papers" / "gsm8k-percent-base.html"


class Check(unittest.TestCase):
    def test_example_passes(self):
        errs = [m for lv, m in papers.check(EXAMPLE.read_text(), slices=["full"]) if lv == "error"]
        self.assertEqual(errs, [])

    def test_prose_budget(self):
        wall = " ".join(["word"] * 60)
        html = EXAMPLE.read_text().replace('<section data-block="abstract"', f'<section data-block="abstract"><p data-block="wall">{wall}</p', 1)
        errs = [m for lv, m in papers.check(html, slices=["full"]) if lv == "error"]
        self.assertTrue(any("60-word paragraph" in m for m in errs), errs)
        self.assertTrue(any("words of prose" in m for m in errs), errs)

    def test_template_is_the_example(self):
        self.assertEqual((Path(papers.__file__).parent / "templates" / "paper-example.html").read_text(), EXAMPLE.read_text())

    def test_flags(self):
        bad = ('<style>body{font-family:Georgia,serif}.t{border-radius:999px}</style>'
               '<section data-block="a"><p>Accuracy rose to 81%.</p><p data-block="x">x</p><p data-block="x">y</p></section>')
        msgs = " | ".join(m for _, m in papers.check(bad, slices=["full"]))
        for want in ("duplicate data-block", "<p> without data-block", "nothing to interact", "never says n",
                     "0 quizzes", "Remember", "names no slice", "serif font", "pill", "dark mode"):
            self.assertIn(want, msgs)
        self.assertNotIn("serif font", " ".join(m for _, m in papers.check("<style>a{font-family:ui-sans-serif,sans-serif}</style>")))


class Cli(unittest.TestCase):
    def arx(self, root, *args):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        return subprocess.run([sys.executable, "-m", "autoresearch", "paper", *args], cwd=root, env=env,
                              capture_output=True, text=True)

    def test_reply_needs_a_real_thread(self):
        p, _ = project()
        r = self.arx(p.root, "reply", "demo", "deadbeef", "hello")
        self.assertNotEqual(r.returncode, 0); self.assertIn("no thread", r.stderr)
        c = papers.post(p, "demo", "comment", body="q", anchor=ANCHOR)
        self.assertEqual(self.arx(p.root, "reply", "demo", c["id"], "a", "--link", "§1=#b1").returncode, 0)
        m = papers.threads(papers.thread(p, "demo"))[0]["messages"][-1]
        self.assertEqual((m["agent"], m["link"]), (True, dict(label="§1", url="#b1")))

    def test_new_then_check(self):
        p, _ = project()
        r = self.arx(p.root, "new", "arith")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((p.root / "paper-arith.html").exists())
        self.assertNotEqual(self.arx(p.root, "new", "arith").returncode, 0)  # never overwrites
        bad = p.root / "bad.html"; bad.write_text("<p>hi</p>")
        r = self.arx(p.root, "check", "--file", str(bad))
        self.assertEqual(r.returncode, 1); self.assertIn("errors", r.stdout)


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
        self.assertEqual(self.req("/api/paper/demo/comment", dict(body="x", anchor=ANCHOR, author="Agent"))[0], 400)
        for o in ("null", "http://localhost.evil.com", "http://127.0.0.1.nip.io:8890"):
            self.assertEqual(self.req("/api/paper/demo/comment", dict(body="x", anchor=ANCHOR), origin=o)[0], 403, o)
        self.assertEqual(self.req("/api/paper/demo/comment", dict(body="x", anchor=ANCHOR, author="Ann"),
                                  origin=self.base)[0], 200)
        for bad in ("/papers/..%2F..%2Fetc/raw", "/papers/%2e%2e/raw", "/api/paper/%00x", "/papers/demo/files/%2e%2e",
                    "/api/paper/nope"):
            self.assertEqual(self.req(bad)[0], 404, bad)

    def test_host_check_blocks_dns_rebinding(self):
        c = http.client.HTTPConnection(self.base.split("//")[1])
        c.request("GET", "/api/state", headers={"Host": "evil.example:8890"})
        self.assertEqual(c.getresponse().status, 403)

    def test_hardening(self):
        c = http.client.HTTPConnection(self.base.split("//")[1])
        c.request("POST", "/api/paper/demo/comment", body=b"{}", headers={"Content-Length": "999999999"})
        self.assertEqual(c.getresponse().status, 413)
        self.assertEqual(self.req("/api/paper/demo/comment", [1, 2])[0], 400)  # body must be an object
        code, body = self.req("/papers/nope/raw")
        self.assertEqual(code, 404); self.assertNotIn(str(self.p.root).encode(), body)  # no paths in errors
        self.assertEqual(self.req("/p/not-registered/api/state")[0], 404)
        w = Path(tempfile.mkdtemp()) / "w.html"; w.write_text("<p>widget</p>")
        url = papers.attach(self.p, "demo", w)
        with urllib.request.urlopen(self.base + url) as f:
            self.assertIn("sandbox", f.headers["Content-Security-Policy"])  # attachments get an opaque origin
            self.assertEqual(f.headers["X-Content-Type-Options"], "nosniff")
        for bad in ("a\x00b", "x" * 200, "-x", "a b"):
            with self.assertRaises(KeyError):
                papers.pdir(self.p, bad)

    def test_malformed_log_still_serves(self):
        with open(papers.pdir(self.p, "demo") / "thread.jsonl", "a") as f:
            f.write('[]\n{"kind":"comment"}\n')
        self.assertEqual(self.req("/api/paper/demo")[0], 200)


if __name__ == "__main__":
    unittest.main()


class PaperViewerNoFlash(unittest.TestCase):
    def test_frame_hidden_until_themed(self):
        src = (Path(__file__).resolve().parents[1] / "autoresearch" / "paper.html").read_text()
        self.assertIn(".page iframe{display:block;width:100%;border:0;height:600px;background:transparent;color-scheme:normal;visibility:hidden}", src)
        self.assertIn('f.classList.add("ready")', src)
        self.assertIn('f.className = "ready"; old.remove()', src)  # live swap keeps the new frame visible
        self.assertNotIn("background:#fff", src)
