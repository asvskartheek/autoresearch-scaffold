"""Goals, the projects registry, goal papers and the multi-project routes. Run: python3 -m unittest discover tests"""
import contextlib, io, json, os, socket, subprocess, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import papers, projects
from autoresearch.core import Project, Task
from autoresearch.server import serve

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "papers" / "gsm8k-96.html"


def ledger(name="demo"):
    d = Path(tempfile.mkdtemp()) / name
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name=name, higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(20)))
    return p


def run(p, model, scores, slice="ds/full"):
    t = Task(p, "eval", f"{model} on {slice}", model=model, slice=slice)
    for i, s in enumerate(scores):
        t.add_row(dict(id=str(i), score=s))
    t.finish()
    return t


class Goals(unittest.TestCase):
    def setUp(self):
        self.p = ledger()
        self.p.add_model("base", status="champion")
        run(self.p, "base", [1] * 14 + [0] * 6)  # 70%

    def test_open_status_and_refuse_until_met(self):
        g = self.p.open_goal("ninety", "90% on full", "full", 0.9)
        self.assertEqual((g["slice"], g["n"], g["baseline"], g["status"]), ("ds/full", 20, "base", "open"))
        st = self.p.goal_status("ninety")
        self.assertAlmostEqual(st["value"], 0.7); self.assertFalse(st["met"]); self.assertAlmostEqual(st["gap"], 0.2)
        self.assertIsNone(st["vs_baseline"])  # the champion is the baseline
        with self.assertRaises(SystemExit):
            self.p.achieve_goal("ninety")
        self.p.add_model("better")
        run(self.p, "better", [1] * 19 + [0])
        self.p.promote("better", force=True)
        st = self.p.goal_status("ninety")
        self.assertTrue(st["met"]); self.assertAlmostEqual(st["vs_baseline"]["delta"], 0.25)
        ev = self.p.achieve_goal("ninety", note="done")
        self.assertEqual((ev["model"], ev["n"], ev["forced"]), ("better", 20, False))
        self.assertEqual(self.p.goals()["ninety"]["status"], "achieved")
        with self.assertRaises(SystemExit):  # closed goals stay closed
            self.p.open_goal("ninety", "again", "full", 0.5)
        self.p.add_model("later"); run(self.p, "later", [1] * 20); self.p.promote("later", force=True)
        self.assertEqual(self.p.goal_status("ninety")["model"], "better")  # evidence is frozen at achieve

    def test_hills_serve_goals_and_abandon(self):
        with self.assertRaises(SystemExit):
            self.p.open_hill("h", "H", "full", goal="nope")
        self.p.open_goal("g", "G", "full", 0.99)
        self.p.open_hill("h", "H", "full", goal="g")
        self.assertEqual(self.p.goal_status("g")["hills"], {"h": "open"})
        self.p.abandon_goal("g", "ceiling of the base model")
        self.assertEqual((self.p.goals()["g"]["status"], self.p.goals()["g"]["reason"]), ("abandoned", "ceiling of the base model"))

    def test_lower_is_better_kpi(self):
        g = self.p.open_goal("cheap", "cheap", "full", 0.5, kpi="cost")
        self.assertFalse(g["higher_is_better"])


GOAL = dict(name="gsm8k-96", status="open", slice="gsm8k-test/full", n=1319, kpi="score", target=0.96,
            value=1224 / 1319, model="percent-base-1024-v1", baseline="qwen3-4b-rl-fresh-v1",
            vs_baseline=dict(delta=0.0523, lo=0.0379, hi=0.0667, n=1319),
            hills={"percent-base": "climbed", "time-rate": "open"})


class GoalPaper(unittest.TestCase):
    def errs(self, html, **st):
        return [m for lv, m in papers.check_goal(html, GOAL | st, hill_papers=["percent-base"]) if lv == "error"]

    def test_example_passes_both_checks(self):
        html = EXAMPLE.read_text()
        self.assertEqual([m for lv, m in papers.check(html, slices=["gsm8k-test/full"]) if lv == "error"], [])
        self.assertEqual(self.errs(html), [])

    def test_template_is_the_example(self):
        self.assertEqual((ROOT / "autoresearch" / "templates" / "paper-goal-example.html").read_text(), EXAMPLE.read_text())

    def test_flags(self):
        html = EXAMPLE.read_text()
        self.assertIn("label the paper a draft", " ".join(self.errs(html.replace("Draft", "Note").replace("draft", "note"))))
        self.assertIn("not marked", " ".join(self.errs(html.replace('class="internal" ', ""))))
        self.assertIn("no link to the internal", " ".join(self.errs(html.replace('href="../percent-base"', 'href="#"'))))
        self.assertIn("paired delta", " ".join(self.errs(html, vs_baseline=dict(delta=0.07, lo=0.05, hi=0.09, n=1319))))
        self.assertIn("ledger value", " ".join(self.errs(html, value=0.95)))
        self.assertIn("negative result", " ".join(self.errs(html, status="abandoned")))
        self.assertIn("no system section", " ".join(self.errs(html.replace('data-block="system"', 'data-block="sys"'))))
        self.assertTrue(any("system section does not name" in error and "qwen3-other-v1" in error
                            for error in self.errs(html, baseline="qwen3-other-v1")))
        self.assertIn("no final-result", " ".join(self.errs("<section data-block=\"x\"></section>")))
        self.assertEqual(self.errs(html, hills={"time-rate": "open"}), [])  # a hill without a paper needs no link


class Registry(unittest.TestCase):
    def test_register_is_idempotent_and_unique(self):
        a, b = ledger("same"), ledger("same")
        ka, kb = projects.register(a.root), projects.register(b.root)
        self.assertNotEqual(ka, kb); self.assertEqual(projects.register(a.root), ka)
        self.assertEqual(projects.root(kb), b.root)
        self.assertTrue(projects.unregister(kb))
        with self.assertRaises(KeyError):
            projects.root(kb)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = ledger("alpha"), ledger("beta")
        cls.b.add_model("m", status="champion"); run(cls.b, "m", [1] * 20)
        cls.b.open_goal("all", "Everything", "full", 1.0)
        src = cls.b.root / "p.html"; src.write_text('<p data-block="b1">beta text</p>')
        papers.add(cls.b, "all", src, goal="all")
        cls.kb = projects.register(cls.b.root)
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        with contextlib.redirect_stdout(io.StringIO()):
            threading.Thread(target=serve, args=(port, cls.a.root), daemon=True).start()
            time.sleep(0.4)
        cls.base = f"http://127.0.0.1:{port}"

    def req(self, path, body=None):
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r) as f:
                return f.status, f.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_one_server_many_projects(self):
        self.assertEqual(json.loads(self.req("/api/state")[1])["config"]["name"], "alpha")
        st = json.loads(self.req(f"/p/{self.kb}/api/state")[1])
        self.assertEqual(st["config"]["name"], "beta"); self.assertTrue(st["goals"]["all"]["met"])
        self.assertEqual(st["papers"]["all"]["goal"], "all")
        ps = {q["name"]: q for q in json.loads(self.req("/api/projects")[1])}
        self.assertTrue(ps["alpha"]["default"]); self.assertEqual(ps["beta"]["goals"]["all"]["status"], "open")
        self.assertIn(b"beta text", self.req(f"/p/{self.kb}/papers/all/raw")[1])
        self.assertEqual(self.req(f"/p/{self.kb}/papers/all")[0], 200)
        code, ev = self.req(f"/p/{self.kb}/api/paper/all/comment", dict(body="hi", author="Ann", anchor=dict(block="b1", quote="beta")))
        self.assertEqual(code, 200)
        self.assertEqual(len(papers.threads(papers.thread(self.b, "all"))), 1)

    def test_only_registered_projects(self):
        for bad in ("/p/nope/api/state", "/p/..%2F..%2Fetc/api/state", f"/p/{self.kb}/papers/..%2F/raw"):
            self.assertEqual(self.req(bad)[0], 404, bad)

    def test_bare_key_redirects(self):
        import http.client
        c = http.client.HTTPConnection(self.base.split("//")[1]); c.request("GET", f"/p/{self.kb}")
        r = c.getresponse(); self.assertEqual((r.status, r.getheader("Location")), (302, f"/p/{self.kb}/"))


class Cli(unittest.TestCase):
    def arx(self, root, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        return subprocess.run([sys.executable, "-m", "autoresearch", *args], cwd=root, env=env, capture_output=True, text=True)

    def test_goal_round_trip(self):
        p = ledger()
        p.add_model("base", status="champion"); run(p, "base", [1] * 10 + [0] * 10)
        r = self.arx(p.root, "goal", "open", "half", "--title", "Half", "--slice", "full", "--target", "0.5")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("n = 20", r.stdout)
        self.assertIn("MET", self.arx(p.root, "goal", "status", "half").stdout)
        r = self.arx(p.root, "paper", "new", "--goal", "half")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertTrue((p.root / "paper-half.html").exists())
        r = self.arx(p.root, "paper", "check", "--goal", "half", "--file", "paper-half.html")
        self.assertEqual(r.returncode, 1); self.assertIn("does not name the goal slice ds/full", r.stdout)
        self.assertEqual(self.arx(p.root, "goal", "achieve", "half").returncode, 0)
        self.assertNotEqual(self.arx(p.root, "goal", "abandon", "half").returncode, 0)  # needs --reason
        self.assertIn("[achieved]", self.arx(p.root, "status").stdout)

    def test_open_before_any_champion(self):
        p = ledger()
        r = self.arx(p.root, "goal", "open", "g", "--title", "G", "--slice", "full", "--target", "0.9")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("no champion", r.stdout)


if __name__ == "__main__":
    unittest.main()
