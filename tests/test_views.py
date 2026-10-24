"""Render every dashboard route in Node (tests/render.js, stub DOM) against three ledgers: the synthetic RMCO-shaped
fixture, a brand-new empty project and the demo seed. Assertions are about facts, never layout."""
import json, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

import helpers as H  # noqa: F401  (must come first)
import fixture
from autoresearch import server
from autoresearch.core import Project

NODE = shutil.which("node")
RENDER = H.REPO / "tests" / "render.js"
LIST_ROUTES = ["overview", "workbench", "champions", "models", "hills", "slices", "archive"]
BAD = ("undefined", "NaN", "[object Object]", "null", "Infinity")


def dump(obj, path: Path) -> str:
    path.write_text(json.dumps(obj, default=str))
    return str(path)


@unittest.skipUnless(NODE, "node is not installed")
class GoalsView(unittest.TestCase):
    def test_goals_page_lists_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "g"
            fixture.build(root)
            state = dump(server.state(Project(root)), Path(tmp) / "state.json")
            detail = dump({"goals": [dict(name="Goal A", goal="Reach 90%", port=8890, root="/x", models=3, current=True, champion="Champ", started=0),
                                     dict(name="Goal B", goal=None, port=8891, root="/y", models=0, current=False, champion=None, started=0)]},
                          Path(tmp) / "detail.json")
            r = subprocess.run(["node", str(RENDER), state, "goals", detail], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            for want in ("Goal A", "Goal B", "Champion · Champ", "No champion yet", "this dashboard"):
                self.assertIn(want, r.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class Views(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.projects = {}

    @classmethod
    def tearDownClass(cls):
        H.kill_all_servers()
        cls._tmp.cleanup()

    # ---- helpers ---------------------------------------------------------------------
    def render(self, state_file, route, detail_file=None, expect_ok=True) -> str:
        args = ["node", str(RENDER), state_file, route] + ([detail_file] if detail_file else [])
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if expect_ok:
            self.assertEqual(r.returncode, 0, f"{route}: {r.stderr}\n{r.stdout[:500]}")
        return r.stdout

    def check_text(self, route, text, minlen):
        self.assertGreaterEqual(len(text.strip()), minlen, f"{route} rendered almost nothing: {text!r}")
        for bad in BAD:
            self.assertNotRegex(text, rf"\b{__import__('re').escape(bad)}\b", f"{route} shows {bad}")

    def detail_for(self, p: Project, st: dict, route: str, d: Path):
        kind, _, arg = route.partition("/")
        if kind == "hill":
            return dump(dict(hill=dict(key=arg, data=server.hill_detail(p, arg))), d / f"h-{arg}.json")
        if kind == "champion":
            return dump(dict(champ=dict(key=arg, data=server.champion_detail(p, arg))), d / f"c-{arg}.json")
        if kind == "task":
            return dump(dict(detail=server.task_detail(p, arg)), d / f"t-{arg}.json")

    def routes_for(self, st: dict) -> list:
        routes = list(LIST_ROUTES)
        routes += [f"hill/{k}" for k in st["hills"]]
        by_status = {}
        for k, m in st["models"].items():
            by_status.setdefault(m["status"], []).append(k)
        for ks in by_status.values():
            routes += [f"model/{k}" for k in ks[:3]]
        routes += [f"champion/{c['model']}" for c in st["champions"]]
        seen = set()
        for t in st["tasks"]:
            key = (t["kind"], t["status"])
            if key not in seen:
                seen.add(key)
                routes.append(f"task/{t['id']}")
        return routes

    def run_project(self, name, root: Path, minlen=200):
        p = Project(root)
        st = json.loads(json.dumps(server.state(p), default=str))
        d = self.tmp / name
        d.mkdir(exist_ok=True)
        sf = dump(st, d / "state.json")
        texts = {}
        for route in self.routes_for(st):
            with self.subTest(project=name, route=route):
                text = self.render(sf, route, self.detail_for(p, st, route, d))
                self.check_text(route, text, minlen if route in LIST_ROUTES else 40)
                texts[route] = text
        return st, texts

    # ---- the synthetic mature ledger ------------------------------------------------------
    def test_fixture(self):
        root = self.tmp / "fx"
        f = fixture.build(root)
        st, t = self.run_project("fx", root)
        self.assertIn(f["champion"], t["overview"])
        self.assertIn("Seeded baseline", t["champions"])
        self.assertIn("Next champion", t["champions"])
        self.assertNotIn("econstructed", t["champions"] + t["overview"])
        self.assertIn(f["best"], t["overview"], "best score of the main track appears on the overview")
        self.assertIn("Pipeline", t["overview"])
        self.assertIn("Best score over experiments", t["overview"])
        self.assertFalse(re.search(r"\bslices?\b", t["overview"] + t["champions"], re.I), "no 'slice' in the UI text")
        self.assertIn(f["hill_title"], t["hills"])
        self.assertIn(f["empty_hill_title"], t["hills"])
        self.assertIn(f["hill_title"], t[f"hill/{f['hill_key']}"])
        self.assertIn(f["empty_hill_title"], t[f"hill/{f['empty_hill_key']}"])
        self.assertIn("Good candidate", t["models"])  # cards show the title; the id is on the model page
        self.assertIn(f["champion"], t[f"model/{f['model_key']}"])
        self.assertIn("Live job", t["workbench"])
        self.assertIn("Stalled job 0", t["workbench"])
        self.assertIn("Alpha drawings", t["slices"])
        self.assertIn(f["champion"], t["archive"])
        for k in st["hills"]:  # every hill has a title on its own page, evals or not
            self.assertIn(st["hills"][k]["title"], t[f"hill/{k}"])
        self.assertTrue(any(f["task_eval"] in r for r in t), "an eval task page was rendered")

    # ---- a brand-new project -----------------------------------------------------------------
    def test_empty_project(self):
        root = self.tmp / "empty"
        H.arx(self.tmp, "init", root, "--name", "Brand New", "--no-serve")
        st, t = self.run_project("empty", root, minlen=20)
        self.assertEqual((st["hills"], st["models"], st["runs"]), ({}, {}, []))
        for route in LIST_ROUTES:
            self.assertIn("Brand New", t[route], route)

    def test_empty_project_without_setup_task(self):
        root = H.new_project(self.tmp, "bare")
        st = server.state(Project(root))
        sf = dump(json.loads(json.dumps(st, default=str)), self.tmp / "bare-state.json")
        for route in LIST_ROUTES:
            with self.subTest(route=route):
                self.check_text(route, self.render(sf, route), 20)

    # ---- the demo seed --------------------------------------------------------------------------
    def test_demo_seed(self):
        root = self.tmp / "demo"
        r = subprocess.run([sys.executable, str(H.REPO / "examples" / "demo" / "seed.py"), str(root)], env=H.env(),
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        H.arx(root, "down", "--all", check=False)
        st, t = self.run_project("demo", root)
        self.assertIn(st["champion"], t["overview"])
        self.assertIn(st["models"][st["champion"]].get("title") or st["champion"], t["champions"])
        for h in st["hills"].values():
            self.assertIn(h["title"], t["hills"])
        best = max(st["runs"], key=lambda x: x["score"])
        self.assertTrue(f"{100 * best['score']:.1f}" in t["overview"] or f"{100 * best['score']:.1f}" in t["champions"]
                        or f"{100 * best['score']:.1f}" in t["archive"])

    # ---- hills are posters, not walls of chips ---------------------------------------------------
    def hill_html(self, state_file, route, detail_file=None):
        js = ("const {render}=require(%r),fs=require('fs');const a=process.argv;"
              "process.stdout.write(render(JSON.parse(fs.readFileSync(a[1],'utf8')),a[2],a[3]?JSON.parse(fs.readFileSync(a[3],'utf8')):{}))") % str(RENDER)
        r = subprocess.run(["node", "-e", js, state_file, route] + ([detail_file] if detail_file else []), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_hills_list_and_page_are_visual(self):
        import re
        root = self.tmp / "fxh"
        f = fixture.build(root)
        p = Project(root)
        st = json.loads(json.dumps(server.state(p), default=str))
        sf = dump(st, self.tmp / "fxh-state.json")
        lst = self.hill_html(sf, "hills")
        self.assertEqual(lst.count('class="card hcard"'), len(st["hills"]))
        self.assertEqual(lst.count('class="pxs"'), len(st["hills"]), "one poster per hill card")
        self.assertNotRegex(lst, r'class="chip ', "no stacked state chips on the list")
        self.assertNotRegex(lst, r"<p[ >]", "no paragraphs on the list")
        d = dump(dict(hill=dict(key=f["hill_key"], data=server.hill_detail(p, f["hill_key"]))), self.tmp / "fxh-h.json")
        page = self.hill_html(sf, "hill/" + f["hill_key"], d)
        self.assertIn("pxs big", page, "the hill page opens with the big poster")
        n = len([m for m in st["models"].values() if m.get("hill") == f["hill_key"]])
        self.assertEqual(page.count('class="hltile '), n, "one poster tile per attempt")
        self.assertNotIn("hlreason", page)

    # ---- the harness itself -----------------------------------------------------------------------
    def test_harness_flags_bad_text(self):
        js = ("const {problems}=require(%r);"
              "const bad=problems('<p>score undefined</p>').length+problems('<p>NaN%%</p>').length+problems('<p>[object Object]</p>').length;"
              "if(bad!==3||problems('<p>fine 12.5%%</p>').length)process.exit(1)") % str(RENDER)
        self.assertEqual(subprocess.run(["node", "-e", js]).returncode, 0)

    def test_unknown_route_does_not_crash(self):
        root = H.new_project(self.tmp, "bare2")
        sf = dump(json.loads(json.dumps(server.state(Project(root)), default=str)), self.tmp / "bare2-state.json")
        for route in ("hill/nope", "model/nope", "task/nope", "champion/nope", "nonsense"):
            with self.subTest(route=route):
                self.render(sf, route)


if __name__ == "__main__":
    unittest.main()
