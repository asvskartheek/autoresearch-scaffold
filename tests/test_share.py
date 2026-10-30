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
        row = dict(kind="comment", body="hi from Bo", author="Bo", by="p-0b0b0b0b", anchor=dict(route="overview"))
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

    def test_guest_identity_and_ownership(self):
        from autoresearch import comments, features, people
        people.remember("p-0000cafe", "Owner", self.ka)
        o = f"http://192.168.7.9:{self.port}"
        row = dict(kind="comment", body="as owner", author="Owner", by="p-0000cafe", anchor=dict(route="overview"))
        self.assertEqual(self.req(f"/p/{self.ka}/api/comments", row, cookie=self.tok, origin=o)[0], 403)
        own = comments.post(self.a, "comment", author="Owner", by="p-0000cafe", body="mine", anchor=dict(route="overview"))
        for k in ("delete", "edit"):
            self.assertEqual(self.req(f"/p/{self.ka}/api/comments", dict(kind=k, target=own["id"], body="x", by="p-0b0b0b0b"), cookie=self.tok, origin=o)[0], 403)
        code, b, _ = self.req(f"/p/{self.ka}/api/comments", dict(kind="comment", body="a guest asks", by="p-0b0b0b0b", anchor=dict(route="overview")), cookie=self.tok, origin=o)
        self.assertEqual(code, 200)
        self.assertTrue(features.inbox(self.a)[-1].get("guest"))
        code, b, _ = self.req(f"/p/{self.ka}/api/questions/add", dict(title="Is it fake", by="Kartheek"), cookie=self.tok, origin=o)
        self.assertTrue(json.loads(b)["by"].startswith("guest: "))

    def test_guest_cannot_approve_project_decisions(self):
        from autoresearch import features, questions
        q = questions.add(self.a, "Approve a new run?", needs_human=True)
        item = features.enqueue(self.a, "goal", dict(ask="An owner request"))
        origin = f"http://192.168.7.9:{self.port}"
        for action in ("answer", "dead", "reopen", "flag"):
            code, _, _ = self.req(f"/p/{self.ka}/api/questions/{action}",
                                  dict(id=q["id"], claim="Approved"), cookie=self.tok, origin=origin)
            self.assertEqual(code, 403, action)
        for action in ("open", "answer", "retry", "dismiss"):
            code, _, _ = self.req(f"/p/{self.ka}/api/intake/{action}",
                                  dict(id=item["id"], goal={}), cookie=self.tok, origin=origin)
            self.assertEqual(code, 403, action)
        self.assertEqual(questions.stored(self.a)[q["id"]]["status"], "open")
        self.assertEqual(self.req(f"/p/{self.ka}/api/questions/ask", dict(title="What does this mean?"),
                                  cookie=self.tok, origin=origin)[0], 200)
        self.assertTrue(features.inbox(self.a)[-1]["guest"])

    def test_paper_guest_cannot_impersonate_display_name_or_resolve_owner(self):
        from autoresearch import answer, features, people
        people.remember("p-1111cafe", "Paper Owner", self.ka)
        people.remember("p-2222cafe", "Paper Owner", self.ka, remote=True)
        src = self.a.root / "ownership.html"
        src.write_text('<p data-block="a">Evidence</p>')
        papers.add(self.a, "ownership", src)
        own = papers.post(self.a, "ownership", "comment", author="Paper Owner", by="p-1111cafe",
                          body="Keep this", anchor=dict(block="a", quote="Evidence"))
        origin = f"http://192.168.7.9:{self.port}"
        for kind in ("edit", "delete", "resolve", "reopen"):
            code, _, _ = self.req(f"/p/{self.ka}/api/paper/ownership/{kind}",
                                  dict(target=own["id"], parent=own["id"], by="p-2222cafe", body="Changed"),
                                  cookie=self.tok, origin=origin)
            self.assertGreaterEqual(code, 400, kind)
        code, body, _ = self.req(f"/p/{self.ka}/api/paper/ownership/reply",
                                dict(parent=own["id"], by="p-2222cafe", body="What does this mean?"),
                                cookie=self.tok, origin=origin)
        self.assertEqual(code, 200)
        answer.sync_papers(self.a)
        pending = [i for i in features.inbox(self.a) if i["kind"] == "paper" and i["payload"]["paper"] == "ownership"]
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0].get("guest"))
        self.assertEqual(papers.threads(papers.thread(self.a, "ownership"))[0]["messages"][0]["body"], "Keep this")

    def test_guest_learning_cannot_write_owner_history(self):
        from autoresearch import course, learn, people, teach
        from autoresearch.core import Task
        p = ledger("learning-guests")
        key = projects.register(p.root)
        token = share.token_for(key, create=True)
        self.addCleanup(share.revoke, key)
        owner, guest = "p-3333cafe", "p-4444cafe"
        people.remember(owner, "Local learner", key)
        people.remember(guest, "Remote learner", key, remote=True)
        p.add_model("base", status="champion")
        p.open_hill("hard", "Hard", "ds/full")
        p.add_model("cand", parent="base", hill="hard")
        for model, scores in (("base", [1, 0, 0, 0]), ("cand", [1, 1, 1, 0])):
            t = Task(p, "eval", model, model=model, slice="ds/full")
            for i, score in enumerate(scores):
                t.add_row(dict(id=str(i), score=score))
            t.finish()
        p.set_model_status("cand", "rejected", "Development result alone is insufficient.")
        card = next(c for c in learn.cards(p) if c["type"] == "number" and c.get("truth") is not None and "explain" in teach.methods_for(c))
        cases = {
            "course": dict(item="goal", hit=True),
            "predictions": dict(card=card["id"], guess=card["truth"], conf=0.8),
            "teach": dict(card=card["id"], method="explain", answer="The candidate improves on this slice."),
            "understanding": dict(kind="active", doc="brief", ms=100),
        }
        origin = f"http://192.168.7.9:{self.port}"
        for route, payload in cases.items():
            for viewer in (owner, "Local learner", "anon", None):
                code, _, _ = self.req(f"/p/{key}/api/{route}", dict(payload, viewer=viewer), cookie=token, origin=origin)
                self.assertEqual(code, 403, (route, viewer))
            code, body, _ = self.req(f"/p/{key}/api/{route}", dict(payload, viewer=guest), cookie=token, origin=origin)
            self.assertEqual(code, 200, (route, body))
        for viewer in (owner, "Local learner"):
            self.assertEqual(course.rows(p, viewer), [])
            self.assertEqual(learn.predictions(p, viewer), [])
            self.assertEqual(teach.attempts(p, viewer), [])
        self.assertTrue(course.rows(p, guest))
        self.assertTrue(learn.predictions(p, guest))
        self.assertTrue(teach.attempts(p, guest))
        self.assertEqual(learn.understanding(p, guest)["docs"]["brief"]["ms"], 100)
        self.assertEqual(learn.understanding(p, owner)["docs"], {})
        # Telemetry accepts batches: a guest must not hide an owner's write behind their own outer ID.
        code, _, _ = self.req(f"/p/{key}/api/understanding", dict(viewer=guest, events=[
            dict(viewer=guest, kind="active", doc="brief", ms=100),
            dict(viewer=owner, kind="active", doc="brief", ms=100)]), cookie=token, origin=origin)
        self.assertEqual(code, 403)

    def test_guest_reads_only_own_learning(self):
        from autoresearch import course, people
        owner, guest = "p-5555cafe", "p-6666cafe"
        people.remember(owner, "Local reader", self.ka)
        people.remember(guest, "Remote reader", self.ka, remote=True)
        course.record(self.a, dict(viewer=owner, item="goal", hit=True))
        base = f"/p/{self.ka}/api/"
        for route in ("course", "brief", "teach", "predictions", "understanding", "memory"):
            for q in (f"?viewer={owner}", "?viewer=Local%20reader", "?viewer=anon", ""):
                self.assertEqual(self.req(base + route + q, cookie=self.tok)[0], 403, (route, q))
            code, body, _ = self.req(base + route + f"?viewer={guest}", cookie=self.tok)
            self.assertEqual(code, 200, (route, body))
        self.assertEqual(json.loads(self.req(base + f"course?viewer={guest}", cookie=self.tok)[1])["memory"], {})
        mem = json.loads(self.req(base + f"memory?viewer={guest}", cookie=self.tok)[1])
        self.assertTrue(all(x["id"] == guest for x in mem["people"]))
        local = json.loads(self.req(base + f"course?viewer={owner}", host="127.0.0.1")[1])
        self.assertIn("goal", local["memory"])  # loopback still reads anyone's

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
        self.assertIn("@layer arx{", one); self.assertIn('<div class="arx-fig"><svg><rect/></svg></div>', one)
        html = share.export_dashboard(p, "gamma", view="#hill/x")
        self.assertIn("window.ARX_SNAP=", html); self.assertNotIn('<script src="', html); self.assertNotIn('<link rel="stylesheet"', html)
        snap = json.loads(html.split("window.ARX_SNAP=", 1)[1].split(";</script>", 1)[0])
        self.assertIn("base", snap["ref"]["models"]); self.assertEqual(snap["ref"]["champion"], "base")  # model papers open
        self.assertIn(share.SNAP_TAG, snap["ref"]["tpl"]); self.assertEqual(snap["view"], "hill/x")  # opens on that view
        self.assertIn("demo", snap["papers"]); self.assertIn("api/state", snap["data"]); self.assertEqual(snap["data"]["api/projects"][0]["key"], "gamma")
        self.assertNotIn("</script", html.split("window.ARX_SNAP=", 1)[1].split(";</script>", 1)[0])
        for write in (".cm-pop textarea", ".cm-pop .go", ".gi,", ".q-form", "[data-t=go]"):  # read-only: no write control shows
            self.assertIn(write, html)

    def test_snapshot_redacts_paths(self):
        p = ledger("delta")
        p.add_model("base", status="champion", change=f"see {p.root}/scratch/gate.json")
        html = share.export_dashboard(p, "delta")
        self.assertNotIn(str(p.root), html)
        self.assertIn("…/scratch/gate.json", html)
        self.assertNotIn("<!--", html.split("window.ARX_SNAP=", 1)[1].split(";</script>", 1)[0])

    def test_snapshot_quiet_writes_and_people(self):
        from autoresearch import people
        p = ledger("eps")
        k = projects.register(p.root)
        people.remember("p-0000bbbb", "Ann", k)
        snap = share.snapshot_data(p, k)
        self.assertEqual(snap["api/people"]["people"]["p-0000bbbb"]["name"], "Ann")
        self.assertEqual(snap["api/people"]["here"], [])
        for k in ("api/people", "api/understanding", "kind!=='seen'", "sendBeacon", "not in this snapshot"):
            self.assertIn(k, share.SHIM)

    def test_snapshot_every_task(self):
        from autoresearch.core import Task
        p = ledger("zeta")
        ids = []
        for i in range(3):
            t = Task(p, "train", f"run {i}")
            for k in range(300):
                t.log(step=k, loss=1 / (k + 1))
            t.finish(); ids.append(t.id)
        full = share.snapshot_data(p, "zeta")
        self.assertTrue(all(f"api/task/{i}" in full and not full[f"api/task/{i}"].get("snapshot_cut") for i in ids))
        tight = share.snapshot_data(p, "zeta", budget=1)  # past the budget a task still comes, cut
        self.assertTrue(all(tight[f"api/task/{i}"]["snapshot_cut"] for i in ids))
        self.assertLessEqual(len(tight[f"api/task/{ids[0]}"]["metrics"]), 150)

    def test_paper_export_keeps_marks_ids_links_theme(self):
        p = ledger("eta")
        for n, body in (("other", "<html><head></head><body><p>x</p></body></html>"),
                        ("main", "<html data-theme='light'><head></head><body><section data-block='a'><p>see "
                                 "<a href='../other'>other</a> and <a href='../nope'>gone</a></p></section>"
                                 "<style>:root[data-theme='dark']{}</style></body></html>")):
            (p.root / f"{n}.html").write_text(body); papers.add(p, n, p.root / f"{n}.html")
        shape = dict(tool="box", d="M1 2M1 14M0 0H40V20H0Z", bw=600, x=0, y=0)
        c = papers.post(p, "main", "comment", body="look", author="Ann", anchor=dict(block="a", quote="see", shape=shape))
        r = papers.post(p, "main", "comment", body="old <svg onload='x()'><path d='M0 0'/></svg>", author="Bo", anchor=dict(block="a", quote="see"))
        papers.post(p, "main", "resolve", parent=r["id"], author="Bo")
        bad = dict(tool="box", d="M0 0\"/><script>x()</script>", bw=1)
        papers.post(p, "main", "comment", body="evil", author="Cy", anchor=dict(block="a", quote="see", shape=bad))
        one = share.export_paper(p, "main")
        self.assertIn(f'id="c-{c["id"]}"', one); self.assertIn(f'id="c-{r["id"]}" class=res', one)  # #c- links land
        self.assertIn("Resolved · 1", one)
        self.assertIn('"d":"M1 2M1 14M0 0H40V20H0Z"', one)  # the drawn mark goes on the page
        self.assertNotIn("<script>x()", one); self.assertNotIn("onload", one)
        self.assertIn("href='other.html'", one); self.assertIn("href='../nope'", one)
        self.assertIn("prefers-color-scheme: dark", one)  # follows the reader's theme


if __name__ == "__main__":
    unittest.main()
