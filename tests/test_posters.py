import http.client, json, subprocess, tempfile, unittest
from pathlib import Path

import helpers as H  # noqa: F401  (must come first)
import fixture
from autoresearch import server
from autoresearch.core import Project
from test_server import Served

RENDER = H.REPO / "tests" / "render.js"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
SPEC = {"v": 1, "headline": "Check the answer against the drawing's own markers",
        "idea": [{"icon": "drawing", "text": "Read the drawing"}, {"icon": "ruler", "text": "Measure circle centers"},
                 {"icon": "check", "text": "Answer only if matched"}],
        "result": {"label": "6 hard valve questions", "before": {"name": "Parent", "value": 5, "of": 6},
                   "after": {"name": "This", "value": 6, "of": 6}},
        "also": [{"text": "1 answer lost support", "tone": "bad"}], "verdict": "rejected",
        "why": "Fixed the target but one answer lost its evidence", "tags": ["Valve body"]}
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180"><rect width="320" height="180"/></svg>'
HTML = b"<!doctype html><title>w</title><script>document.title='x'</script>"


def write(d: Path, name: str, data: bytes) -> Path:
    f = d / name
    f.write_bytes(data)
    return f


class Storage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.p = Project(H.new_project(self.tmp, "ps"))
        self.p.add_dataset("d", [str(i) for i in range(10)])
        self.p.open_hill("h", "Hill", "d/full")
        self.p.add_model("m", parent="", status="champion")

    def test_set_and_replace(self):
        f = self.p.set_poster("model", "m", write(self.tmp, "a.svg", SVG))
        self.assertEqual(f, self.p.dir / "posters" / "model-m.svg")
        self.assertEqual(f.read_bytes(), SVG)
        g = self.p.set_poster("model", "m", write(self.tmp, "b.html", HTML))  # one poster per model
        self.assertEqual(self.p.poster_path("model", "m"), g)
        self.assertFalse(f.exists())
        self.p.set_poster("hill", "h", write(self.tmp, "c.png", PNG))
        self.assertEqual(self.p.poster_path("hill", "h").name, "hill-h.png")
        self.assertIsNone(self.p.poster_path("model", "nope"))

    def test_rejected_inputs(self):
        bad = [("model", "m", write(self.tmp, "a.exe", b"x")), ("model", "m", write(self.tmp, "a.gif", b"GIF89a")),
               ("model", "m", write(self.tmp, "a.png", b"not a png")), ("model", "m", write(self.tmp, "a.jpg", b"nope")),
               ("model", "m", write(self.tmp, "big.svg", b"x" * (2 * 1024 * 1024 + 1))),
               ("model", "m", self.tmp / "missing.svg"), ("model", "ghost", write(self.tmp, "g.svg", SVG)),
               ("thing", "m", write(self.tmp, "t.svg", SVG)), ("model", "m", write(self.tmp, "u.svg", b"\xff\xfe\x00"))]
        for kind, ident, f in bad:
            with self.subTest(f=f.name, kind=kind, ident=ident), self.assertRaises(SystemExit):
                self.p.set_poster(kind, ident, f)
        self.assertIsNone(self.p.poster_path("model", "m"))
        self.p.set_poster("model", "m", write(self.tmp, "ok.svg", b"x" * (2 * 1024 * 1024)))  # exactly the cap

    def test_ids_are_names_not_paths(self):
        self.p.add_model("../../evil", parent="", status="candidate")
        f = self.p.set_poster("model", "../../evil", write(self.tmp, "e.svg", SVG))
        self.assertEqual(f.parent, self.p.dir / "posters")
        self.assertEqual(f.resolve().parent, (self.p.dir / "posters").resolve())
        self.assertFalse((self.p.dir.parent / "evil.svg").exists())

    def test_add_model_and_open_hill_take_a_poster(self):
        self.p.add_model("n", parent="m", poster=write(self.tmp, "n.html", HTML))
        self.assertEqual(self.p.poster_path("model", "n").suffix, ".html")
        self.p.open_hill("h2", "Hill 2", "d/full", poster=write(self.tmp, "h2.svg", SVG))
        self.assertEqual(self.p.poster_path("hill", "h2").suffix, ".svg")

    def test_cli(self):
        root = self.p.root
        H.arx(root, "model", "add", "c1", "--poster", write(self.tmp, "c1.svg", SVG))
        self.assertTrue(self.p.poster_path("model", "c1"))
        H.arx(root, "poster", "model", "c1", write(self.tmp, "c1.png", PNG))
        self.assertEqual(self.p.poster_path("model", "c1").suffix, ".png")
        H.arx(root, "poster", "hill", "h", write(self.tmp, "h.html", HTML))
        H.arx(root, "hill", "explain", "h", "--symptom", "s", "--poster", write(self.tmp, "h2.svg", SVG))
        self.assertEqual(self.p.poster_path("hill", "h").suffix, ".svg")
        r = H.arx(root, "poster", "model", "c1", write(self.tmp, "x.exe", b"x"), check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.p.poster_path("model", "c1").suffix, ".png")


def spec(**kw):
    d = json.loads(json.dumps(SPEC))
    d.update(kw)
    return json.dumps(d).encode()


class Specs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.p = Project(H.new_project(self.tmp, "sp"))
        self.p.add_dataset("d", [str(i) for i in range(10)])
        self.p.open_hill("h", "Hill", "d/full")
        self.p.add_model("m", parent="", status="champion")

    def test_valid_spec_is_stored_and_parsed(self):
        f = self.p.set_poster("model", "m", write(self.tmp, "a.json", spec()))
        self.assertEqual(f.name, "model-m.json")
        self.assertEqual(self.p.poster_spec("model", "m")["headline"], SPEC["headline"])
        self.p.set_poster("model", "m", write(self.tmp, "b.svg", SVG))  # one poster per model
        self.assertIsNone(self.p.poster_spec("model", "m"))
        self.p.set_poster("hill", "h", write(self.tmp, "h.json", spec(verdict="open")))
        self.assertEqual(self.p.poster_spec("hill", "h")["verdict"], "open")

    def test_invalid_specs_are_refused(self):
        ok = json.loads(spec())
        res = ok["result"]

        def mut(**kw):
            return json.dumps({**ok, **kw}).encode()

        def side(**kw):
            return mut(result={"label": "l", "before": {"name": "a", "value": 5, "of": 6, **kw}, "after": res["after"]})

        bad = {"not json": b"{", "list": b"[]", "v": mut(v=2), "no headline": mut(headline=""),
               "long headline": mut(headline="x" * 71), "one step": mut(idea=ok["idea"][:1]),
               "five steps": mut(idea=ok["idea"] + ok["idea"]),
               "bad icon": mut(idea=[{"icon": "banana", "text": "a"}, {"icon": "check", "text": "b"}]),
               "long step": mut(idea=[{"icon": "check", "text": "x" * 29}, {"icon": "check", "text": "b"}]),
               "bad verdict": mut(verdict="great"), "long why": mut(why="x" * 91),
               "value above of": side(value=7), "string value": side(value="5"), "bool value": side(value=True),
               "of zero": side(value=0, of=0),
               "bad tone": mut(also=[{"text": "t", "tone": "loud"}]), "four chips": mut(also=[{"text": "t"}] * 4),
               "three tags": mut(tags=["a", "b", "c"]), "too big": mut(extra="z" * 17000), "not utf8": b"\xff\xfe"}
        for name, data in bad.items():
            with self.subTest(name), self.assertRaises(SystemExit):
                self.p.set_poster("model", "m", write(self.tmp, "x.json", data))
        self.assertIsNone(self.p.poster_path("model", "m"))
        self.p.set_poster("model", "m", write(self.tmp, "min.json", json.dumps(  # smallest valid spec
            {"v": 1, "headline": "h", "idea": ok["idea"][:2], "verdict": "open"}).encode()))

    def test_cli(self):
        H.arx(self.p.root, "poster", "model", "m", write(self.tmp, "a.json", spec()))
        self.assertEqual(self.p.poster_path("model", "m").suffix, ".json")
        H.arx(self.p.root, "model", "add", "c1", "--poster", write(self.tmp, "c.json", spec()))
        self.assertTrue(self.p.poster_spec("model", "c1"))
        r = H.arx(self.p.root, "poster", "model", "m", write(self.tmp, "b.json", spec(verdict="nope")), check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("verdict", r.stderr + r.stdout)
        self.assertEqual(self.p.poster_spec("model", "m")["verdict"], "rejected")  # the old one stays


class Serving(Served):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmpf = Path(cls._tmp.name)
        cls.mk = fixture.CHAMPION
        cls.p.set_poster("model", cls.mk, write(cls.tmpf, "a.svg", SVG))
        h = next(iter(cls.p.hills()))
        cls.hk = h
        cls.p.set_poster("hill", h, write(cls.tmpf, "h.html", HTML))
        other = next(k for k in cls.p.models() if k != cls.mk)
        cls.other = other
        cls.p.set_poster("model", other, write(cls.tmpf, "o.png", PNG))
        cls.spec_model = next(k for k in cls.p.models() if k not in (cls.mk, other))
        cls.p.set_poster("model", cls.spec_model, write(cls.tmpf, "s.json", spec()))

    def headers(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path)
        r = c.getresponse()
        r.read()
        return r.status, {k.lower(): v for k, v in r.getheaders()}

    def test_state_flags(self):
        _, s = self.get("/api/state")
        self.assertIs(s["models"][self.mk]["poster"], True)
        self.assertEqual(s["models"][self.mk]["poster_type"], "svg")
        self.assertIs(s["hills"][self.hk]["poster"], True)
        self.assertEqual(s["hills"][self.hk]["poster_type"], "html")
        bare = [m for k, m in s["models"].items() if k not in (self.mk, self.other, self.spec_model)]
        self.assertTrue(bare and all(m["poster"] is False for m in bare))

    def test_state_carries_the_parsed_spec(self):
        _, s = self.get("/api/state")
        m = s["models"][self.spec_model]
        self.assertEqual((m["poster"], m["poster_type"]), (True, "json"))
        self.assertEqual(m["poster_spec"], SPEC)
        self.assertNotIn("poster_spec", s["models"][self.mk])  # only json posters carry one
        code, body = self.get(f"/api/poster/model/{self.spec_model}", raw=True)  # the raw file is still served
        self.assertEqual((code, json.loads(body)), (200, SPEC))
        self.assertEqual(self.headers(f"/api/poster/model/{self.spec_model}")[1]["content-type"], "application/json")

    def test_serves_with_type_and_csp(self):
        code, body = self.get(f"/api/poster/model/{self.mk}", raw=True)
        self.assertEqual((code, body), (200, SVG))
        code, h = self.headers(f"/api/poster/model/{self.mk}")
        self.assertEqual(h["content-type"], "image/svg+xml")
        self.assertEqual(h["x-content-type-options"], "nosniff")
        csp = h["content-security-policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("img-src data:", csp)
        self.assertNotIn("script-src", csp)  # only html widgets run scripts
        code, h = self.headers(f"/api/poster/hill/{self.hk}")
        self.assertEqual(h["content-type"], "text/html; charset=utf-8")
        self.assertIn("script-src 'unsafe-inline'", h["content-security-policy"])
        self.assertIn("default-src 'none'", h["content-security-policy"])
        self.assertEqual(self.headers(f"/api/poster/model/{self.other}")[1]["content-type"], "image/png")

    def test_missing_and_traversal(self):
        bare = next(k for k, m in self.p.models().items() if k not in (self.mk, self.other, self.spec_model))
        for path in (f"/api/poster/model/{bare}", "/api/poster/model/nope", "/api/poster/thing/x", "/api/poster/model/",
                     "/api/poster/model", "/api/poster/model/../../research.json", "/api/poster/model/%2e%2e%2fmodels",
                     "/api/poster/model/..%2f..%2fresearch.json", f"/api/poster/model/{self.mk}/extra",
                     "/api/poster/hill/..", "/api/poster/model/%2e%2e/%2e%2e/research.json"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, raw=True)[0], 404)

    def test_static_poster_js_served(self):
        code, body = self.get("/static/poster.js", raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b"posterThumb", body)


class Rendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.root = cls.tmp / "fx"
        cls.f = fixture.build(cls.root)
        cls.p = Project(cls.root)
        cls.p.set_poster("model", fixture.CHAMPION, write(cls.tmp, "a.svg", SVG))
        cls.html_model = next(k for k, m in cls.p.models().items() if m["status"] == "rejected")
        cls.p.set_poster("model", cls.html_model, write(cls.tmp, "w.html", HTML))
        cls.state = cls.tmp / "state.json"
        cls.state.write_text(json.dumps(server.state(cls.p), default=str))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def html(self, route):
        js = (f"const r=require({str(RENDER)!r});const fs=require('fs');"
              f"const h=r.render(JSON.parse(fs.readFileSync({str(self.state)!r},'utf8')),{route!r});"
              "if(r.problems(h).length){console.error(r.problems(h));process.exit(1)}process.stdout.write(h)")
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_models_page_is_poster_cards(self):
        h = self.html("models")
        self.assertIn('class="mdgrid"', h)
        self.assertNotIn("<table", h)
        self.assertGreater(h.count('class="mdcard"'), 10)
        self.assertIn(f"api/poster/model/{fixture.CHAMPION}", h)  # stored svg
        self.assertIn('sandbox="allow-scripts"', h)  # html widget in a sandboxed frame
        self.assertNotIn("allow-same-origin", h)
        self.assertIn('class="pxs"', h)  # the rest are derived from the ledger
        self.assertNotIn('class="neg', h)  # no red reason text on the list

    def test_model_page_leads_with_poster_and_hides_reason(self):
        h = self.html(f"model/{self.html_model}")
        self.assertLess(h.index("pxcard big"), h.index("<h2"))
        self.assertIn("allow-scripts", h)
        self.assertIn('<details class="mdwhy"', h)
        reason = self.p.models()[self.html_model]["reason"]
        self.assertIn(reason[:30], h)
        self.assertGreater(h.index(reason[:30]), h.index('<details class="mdwhy"'))
        self.assertNotIn('class="desc neg', h)

    def test_auto_poster_has_verdict_and_bars(self):
        h = self.html(f"model/{fixture.CHAMPION}")
        self.assertIn("api/poster/model/", h)
        other = next(k for k, m in self.p.models().items() if m["status"] == "historical")
        h = self.html(f"model/{other}")
        self.assertIn("pxs big", h)
        self.assertLess(h.index("pxs big"), h.index("<h2"))  # the poster is the hero, facts come after
        self.assertIn("Historical", h)  # the verdict stamp
        self.assertIn(">auto<", h)

    def test_spec_poster_is_drawn(self):
        spec_model = next(k for k, m in self.p.models().items() if m["status"] == "candidate")
        self.p.set_poster("model", spec_model, write(self.tmp, "s.json", spec()))
        self.state.write_text(json.dumps(server.state(self.p), default=str))
        h = self.html(f"model/{spec_model}")
        for want in ("Check the answer against the drawing", "Measure circle centers", "5/6", "6/6", "Rejected",
                     "pxHi(this,1)", "pxMode(this,'pct')", "1 answer lost support"):
            self.assertIn(want, h)
        self.assertNotIn(">auto<", h)
        self.assertLess(h.index("pxs big"), h.index("<h2"))
        self.assertIn("Measure circle centers", self.html("models"))
        self.p.poster_path("model", spec_model).unlink()
        self.state.write_text(json.dumps(server.state(self.p), default=str))

    def test_hill_page_leads_with_poster(self):
        hk = next(iter(self.p.hills()))
        h = self.html(f"hill/{hk}")
        self.assertIn("pxs big", h)
        self.assertLess(h.index("pxs big"), h.index("hrow"))

    def test_filters_kept(self):
        h = self.html("models")
        self.assertIn("All hills", h)
        self.assertIn("S.mf=", h)


if __name__ == "__main__":
    unittest.main()
