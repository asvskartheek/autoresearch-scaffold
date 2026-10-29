"""Sharing: token-scoped access from other machines and the self-contained export (share.py). Run: python3 -m pytest -q tests"""
import contextlib, http.client, io, json, os, socket, tempfile, threading, time, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import papers, projects, share
from autoresearch.core import Project
from autoresearch.server import serve


def ledger(name):
    d = Path(tempfile.mkdtemp()) / name
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name=name, higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(4)))
    return p


class Remote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = ledger("alpha"), ledger("beta")
        cls.ka, cls.kb = projects.register(cls.a.root), projects.register(cls.b.root)
        s = socket.socket(); s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]; s.close()
        with contextlib.redirect_stdout(io.StringIO()):
            threading.Thread(target=serve, args=(cls.port, cls.a.root), daemon=True).start()
            time.sleep(0.4)
        cls.tok = share.token_for(cls.ka, create=True)

    @classmethod
    def tearDownClass(cls):
        share.revoke(cls.ka)

    def req(self, path, body=None, cookie=None, origin=None, host="192.168.7.9"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": f"{host}:{self.port}", "Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = f"arx_k={cookie}"
        if origin:
            h["Origin"] = origin
        c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())

    def test_scoped(self):
        self.assertEqual(self.req(f"/p/{self.ka}/api/state")[0], 403)  # no token
        code, _, hd = self.req(f"/p/{self.ka}/?k={self.tok}")
        self.assertEqual(code, 302); self.assertIn("arx_k=" + self.tok, hd["Set-Cookie"]); self.assertNotIn("k=", hd["Location"])
        self.assertEqual(self.req(f"/p/{self.ka}/api/state", cookie=self.tok)[0], 200)
        self.assertEqual(self.req(f"/p/{self.kb}/api/state", cookie=self.tok)[0], 403)  # another project stays private
        self.assertEqual(self.req("/app.css", cookie=self.tok)[0], 200)
        ps = json.loads(self.req("/api/projects", cookie=self.tok)[1])
        self.assertEqual([(x["key"], x["root"]) for x in ps], [(self.ka, "")])
        self.assertEqual(self.req("/api/state", cookie="wrong")[0], 403)
        self.assertEqual(self.req("/api/state", host="127.0.0.1")[0], 200)  # loopback keeps full access

    def test_writes_same_origin(self):
        row = dict(kind="comment", body="hi from Bo", author="Bo", anchor=dict(route="overview"))
        self.assertEqual(self.req(f"/p/{self.ka}/api/comments", row, cookie=self.tok)[0], 403)  # no Origin
        self.assertEqual(self.req(f"/p/{self.ka}/api/comments", row, cookie=self.tok, origin="http://evil.example")[0], 403)
        self.assertEqual(self.req(f"/p/{self.ka}/api/comments", row, cookie=self.tok, origin=f"http://192.168.7.9:{self.port}")[0], 200)

    def test_redirect_and_redact(self):
        code, _, hd = self.req(f"/p/{self.ka}/?k={self.tok}&c=x%0d%0aX-Injected:%20yes")
        self.assertEqual(code, 302); self.assertNotIn("X-Injected", hd); self.assertNotIn("\r", hd["Location"])
        self.assertEqual(self.req(f"/p/{self.ka}/?k=bad%0d%0aX:1")[0], 403)
        self.assertEqual(share.redact("run /Users/me/proj/scratch/gate.json now"), "run …/scratch/gate.json now")
        body = self.req(f"/p/{self.ka}/api/state", cookie=self.tok)[1].decode()
        self.assertNotIn(str(self.a.root), body)

    def test_guest_cannot_rename(self):
        from autoresearch import people
        people.remember("p-0000aaaa", "Owner", self.ka)
        row = dict(id="p-0000aaaa", name="Pwned", route="overview")
        self.req(f"/p/{self.ka}/api/people", row, cookie=self.tok, origin=f"http://192.168.7.9:{self.port}")
        self.assertEqual(people.roster()["p-0000aaaa"]["name"], "Owner")

    def test_link(self):
        u = share.link(self.ka, 8890, "thread:cm-1234", self.tok)
        self.assertIn(f"/p/{self.ka}/?k={self.tok}&c=cm-1234", u)
        self.assertTrue(share.link(self.ka, 8890, "paper:demo", self.tok).endswith(f"/papers/demo?k={self.tok}"))


class Export(unittest.TestCase):
    def test_dashboard_and_paper(self):
        p = ledger("gamma")
        p.add_model("base", status="champion")
        src = p.root / "demo.html"
        src.write_text("<html><head></head><body><section data-block='a'><p>some text</p></section></body></html>")
        papers.add(p, "demo", src)
        papers.post(p, "demo", "comment", body="why <svg><rect/></svg>?", author="Ann", anchor=dict(block="a", quote="some"))
        one = share.export_paper(p, "demo")
        self.assertIn("@layer arx{", one); self.assertIn("Open comments", one); self.assertIn("[figure]", one)
        html = share.export_dashboard(p, "gamma")
        self.assertIn("window.ARX_SNAP=", html); self.assertNotIn('<script src="', html); self.assertNotIn('<link rel="stylesheet"', html)
        snap = json.loads(html.split("window.ARX_SNAP=", 1)[1].split(";</script>", 1)[0])
        self.assertIn("demo", snap["papers"]); self.assertIn("api/state", snap["data"]); self.assertEqual(snap["data"]["api/projects"][0]["key"], "gamma")
        self.assertNotIn("</script>", json.dumps(snap).replace("<\\/script", ""))
        for write in (".cm-pop textarea", ".cm-pop .go", ".gi,", ".q-form", "[data-t=go]"):  # read-only: no write control shows
            self.assertIn(write, html)

    def test_snapshot_redacts_paths(self):
        p = ledger("delta")
        p.add_model("base", status="champion", change=f"see {p.root}/scratch/gate.json")
        html = share.export_dashboard(p, "delta")
        self.assertNotIn(str(p.root), html)
        self.assertIn("…/scratch/gate.json", html)
        self.assertNotIn("<!--", html.split("window.ARX_SNAP=", 1)[1].split(";</script>", 1)[0])


if __name__ == "__main__":
    unittest.main()
