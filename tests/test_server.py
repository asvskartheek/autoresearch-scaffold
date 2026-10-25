import json, subprocess, sys, tempfile, unittest
from pathlib import Path

import helpers as H  # noqa: F401  (must come first)
import fixture
from autoresearch import server
from autoresearch.core import Project

STATE_KEYS = {"timeline", "config", "now", "champion", "champions", "project", "datasets", "slices", "hills", "models", "gates",
              "tasks", "runs", "tracks", "leaderboard", "decisions"}


class Served(unittest.TestCase):
    """One fixture project and one real server process for the whole class."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "fx"
        cls.facts = fixture.build(cls.root)
        cls.p = Project(cls.root)
        cls.port = H.free_port()
        cls.proc = subprocess.Popen([sys.executable, "-c", H.BOOT, "serve", "--port", str(cls.port)], cwd=cls.root,
                                    env=H.env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert H.wait_for(lambda: _up(cls.port)), "server did not start"

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait()
        cls._tmp.cleanup()

    def get(self, path, raw=False):
        return H.get(self.port, path, raw)


def _up(port):
    try:
        return H.get(port, "/api/ping")[0] == 200
    except OSError:
        return False


class State(Served):
    def test_keys_and_shape(self):
        code, s = self.get("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(set(s), STATE_KEYS)
        self.assertEqual(s["champion"], fixture.CHAMPION)
        self.assertEqual([c["model"] for c in s["champions"]], [fixture.CHAMPION])
        self.assertTrue(all("gate" not in c for c in s["champions"]))
        by = {}
        for m in s["models"].values():
            by[m["status"]] = by.get(m["status"], 0) + 1
        self.assertEqual((by["rejected"], by["historical"], by["champion"]), (22, 65, 1))
        self.assertTrue(all(m.get("reason") for m in s["models"].values() if m["status"] == "rejected"))
        self.assertEqual(len(s["hills"]), 7)
        self.assertEqual(s["project"]["name"], "Synthetic Lab")
        self.assertLessEqual(len(s["decisions"]), 50)
        self.assertTrue(all("ids" not in sl for sl in s["slices"].values()))

    def test_gates_only_for_live_models(self):
        _, s = self.get("/api/state")
        self.assertEqual(set(s["gates"]), {fixture.CHAMPION, "cand-good", "cand-bad"})

    def test_stalled_tasks(self):
        _, s = self.get("/api/state")
        st = [t for t in s["tasks"] if t["status"] == "stalled"]
        self.assertEqual(len(st), 3)
        self.assertEqual([t["status"] for t in s["tasks"] if t["id"] == "live-0"], ["running"])

    def test_runs(self):
        _, s = self.get("/api/state")
        runs = s["runs"]
        hist = [r for r in runs if r["kind"] == "historical_run"]
        self.assertEqual(len(hist), 150)
        self.assertEqual(sum(r["kind"] == "eval" for r in runs), 7)
        self.assertEqual([r["t"] for r in runs], sorted(r["t"] for r in runs))
        for r in runs:
            self.assertIsInstance(r["score"], float)
            self.assertTrue(r["track"] and r["n"] and r["t"])
        best = max(runs, key=lambda r: r["score"])
        self.assertEqual(f"{100 * best['score']:.1f}", fixture.BEST_SCORE_STR)
        self.assertEqual(best["n"], 60)
        week = (max(r["t"] for r in hist) - min(r["t"] for r in hist)) / 86400
        self.assertGreater(week, 5)  # dates come from catalog_record.date, spread over a week
        self.assertTrue(all(r["label"] in {"Orion K3", "Lynx 2", "Heron 7"} for r in hist))
        self.assertTrue(all(" · " not in r["variant"] or r["variant"].split(" · ")[1] not in {"Development 60", "Random 120", "All 120", "All 90", "Tiny 12"}
                            for r in hist), "cohort label is stripped from the variant")

    def test_tracks_frontier(self):
        _, s = self.get("/api/state")
        by_id = {r["id"]: r for r in s["runs"]}
        self.assertGreaterEqual(len(s["tracks"]), 4)
        for tr in s["tracks"]:
            members = [r for r in s["runs"] if r["track"] == tr["id"]]
            self.assertEqual(tr["runs"], len(members))
            self.assertGreaterEqual(tr["n"], 20)
            best, expect = -1.0, []
            for r in members:  # recompute independently: every run that strictly beat all earlier ones
                if r["n"] >= 20 and r["score"] > best:
                    expect.append(r["id"])
                    best = r["score"]
            self.assertEqual([f["id"] for f in tr["frontier"]], expect, tr["label"])
            scores = [by_id[f["id"]]["score"] for f in tr["frontier"]]
            self.assertEqual(scores, sorted(set(scores)), "frontier is strictly increasing")
            self.assertIsNone(tr["frontier"][0]["prev"])
            for a, b in zip(tr["frontier"], tr["frontier"][1:]):
                self.assertEqual(b["prev_id"], a["id"])
                self.assertAlmostEqual(b["prev"], by_id[a["id"]]["score"])
        main = next(t for t in s["tracks"] if t["label"] == "alpha · Development 60")
        self.assertEqual(by_id[main["frontier"][-1]["id"]]["n"], 60)
        self.assertEqual(f"{100 * by_id[main['frontier'][-1]['id']]['score']:.1f}", fixture.BEST_SCORE_STR)
        self.assertNotIn("alpha · Tiny 12", {t["label"] for t in s["tracks"]})  # n < 20 never forms a track

    def test_tracks_unit(self):
        mk = lambda i, sc, n=30, tr="a|1", t=None: dict(id=i, track=tr, n=n, score=sc, t=t or i, dataset="a", slice=None, dev_label=None, variant="v")
        runs = [mk(1, .5), mk(2, .5), mk(3, .7), mk(4, .6), mk(5, .9, n=5), mk(6, .8)]
        (tr,) = server._tracks(runs, {})
        self.assertEqual([f["id"] for f in tr["frontier"]], [1, 3, 6])
        self.assertEqual(server._tracks([mk(1, .5, n=10)], {}), [])
        (zero,) = server._tracks([mk(1, 0.0), mk(2, .3)], {})  # solving nothing does not make a champion
        self.assertEqual([f["id"] for f in zero["frontier"]], [2])
        (low,) = server._tracks([mk(1, .5), mk(2, .4), mk(3, .45), mk(4, .2)], {}, higher=False)  # lower is better
        self.assertEqual([f["id"] for f in low["frontier"]], [1, 2, 4])


class Details(Served):
    def test_burst_of_requests_is_not_reset(self):
        """A page load fires a dozen requests at once; the old backlog of 5 reset some of them."""
        from concurrent.futures import ThreadPoolExecutor
        paths = ["/static/lib.js", "/api/state", "/", "/api/goals"] * 30
        with ThreadPoolExecutor(60) as ex:
            codes = list(ex.map(lambda x: self.get(x, raw=True)[0], paths))
        self.assertEqual(set(codes) - {404}, {200}, codes)  # /static/* is 404 until the UI lands in the next PR

    def test_state_is_cached_until_the_ledger_changes(self):
        a = self.get("/api/state")[1]
        self.assertEqual(self.get("/api/state")[1]["models"].keys(), a["models"].keys())
        p = Project(self.root)
        p.add_model("cache-probe", change="x", status="candidate")
        try:
            self.assertIn("cache-probe", self.get("/api/state")[1]["models"])
        finally:
            data = p.models()
            data.pop("cache-probe")
            p._save("models", data)
        self.assertNotIn("cache-probe", self.get("/api/state")[1]["models"])

    def test_goals_lists_this_project_first(self):
        code, g = self.get("/api/goals")
        self.assertEqual(code, 200)
        self.assertTrue(g and g[0]["current"] and g[0]["name"] == "Synthetic Lab" and g[0]["port"] == self.port)

    def test_ping(self):
        code, d = self.get("/api/ping")
        self.assertEqual(code, 200)
        self.assertEqual(Path(d["root"]), self.root.resolve())
        self.assertEqual(d["name"], "Synthetic Lab")


    def test_champion_detail(self):
        code, d = self.get(f"/api/champion/{fixture.CHAMPION}")
        self.assertEqual(code, 200)
        self.assertEqual((d["model"], d["current"], d["previous"]), (fixture.CHAMPION, True, None))
        self.assertIsInstance(d["vs_previous"], list)
        self.assertEqual(d["vs_previous"], [])  # the first champion has nothing before it
        self.assertTrue(all(t["status"] for t in d["tasks"]))

    def test_champion_detail_unknown_and_non_champion(self):
        self.assertEqual(self.get("/api/champion/nope")[0], 404)
        rejected = next(k for k, m in self.p.models().items() if m["status"] == "rejected")
        self.assertEqual(self.get(f"/api/champion/{rejected}")[0], 404)  # a model that never led anything

    def test_champion_detail_after_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fx"
            fixture.build(root)
            p = Project(root)
            p.promote("cand-good", force=True)
            d = server.champion_detail(p, "cand-good")
            self.assertEqual(d["previous"], fixture.CHAMPION)
            vs = {v["slice"]: v for v in d["vs_previous"]}
            self.assertGreater(vs["alpha/dev60"]["delta"], 0)
            self.assertEqual(vs["alpha/dev60"]["n"], 60)
            self.assertTrue(server.champion_detail(p, "cand-good")["current"])
            self.assertFalse(server.champion_detail(p, fixture.CHAMPION)["current"])

    def test_hill_detail_with_evals(self):
        code, d = self.get("/api/hill/units")
        self.assertEqual(code, 200)
        self.assertEqual(d["target"]["slice"], "alpha/dev60")
        self.assertEqual(len(d["target"]["ids"]), 60)
        self.assertEqual(set(d["target"]["runs"]), {fixture.CHAMPION, "cand-good", "cand-bad"})
        self.assertEqual(set(d["control"]["runs"]), {fixture.CHAMPION, "cand-good", "cand-bad"})

    def test_hill_detail_without_evals(self):
        code, d = self.get(f"/api/hill/{self.facts['empty_hill_key']}")
        self.assertEqual(code, 200)
        self.assertEqual(d["target"]["runs"], {})
        self.assertEqual(d["target"]["slice"], "beta/dev30")
        self.assertNotIn("control", d)  # this hill has no control slice

    def test_hill_detail_unknown(self):
        self.assertEqual(self.get("/api/hill/nope")[0], 404)

    def test_task_detail_historical(self):
        code, d = self.get(f"/api/task/{self.facts['task_hist']}")
        self.assertEqual(code, 200)
        self.assertEqual(d["task"]["kind"], "historical_run")
        self.assertEqual((d["metrics"], d["events"]), ([], []))
        self.assertNotIn("rows", d)
        self.assertIn("catalog_record", d["task"]["summary"])

    def test_task_detail_eval(self):
        code, d = self.get(f"/api/task/{self.facts['task_eval']}")
        self.assertEqual(code, 200)
        self.assertGreater(len(d["rows"]), 0)
        self.assertEqual(set(d["rows"][0]), {"id", "score", "error", "latency_s", "cost"})

    def test_task_detail_vs_champion(self):
        t = next(t for t in self.p.evals() if t["model"] == "cand-good" and t["slice"] == "alpha/dev60")
        _, d = self.get(f"/api/task/{t['id']}")
        self.assertEqual(d["vs_champion"]["model"], fixture.CHAMPION)
        self.assertEqual(d["vs_champion"]["n"], 60)

    def test_task_detail_unknown(self):
        self.assertEqual(self.get("/api/task/nope")[0], 404)

    def test_gate_endpoint(self):
        code, g = self.get("/api/gate/cand-good")
        self.assertEqual((code, g["rungs"][0]["status"]), (200, "pass"))
        self.assertEqual(self.get("/api/gate/nope")[0], 404)


class Pure(unittest.TestCase):
    def test_runs_ignores_unscored(self):
        mk = lambda **k: dict(id="x", kind="experiment", status="done", title="t", summary={}, created=1.0) | k
        self.assertEqual(server._runs([mk(), mk(summary=dict(score=0.5, n=0)), mk(summary=dict(score="x", n=3))]), [])

    def test_runs_bad_date_falls_back(self):
        t = dict(id="x", kind="historical_run", status="done", title="V · C", created=5.0, model="m",
                 summary=dict(score=.5, n=10, catalog_record=dict(date="garbage", cohort_label="C", model="M")))
        (r,) = server._runs([t])
        self.assertEqual((r["t"], r["variant"], r["label"]), (5.0, "V", "M"))

    def test_downsample(self):
        pts = [{"i": i} for i in range(5000)]
        out = server._downsample(pts)
        self.assertLessEqual(len(out), 601)
        self.assertEqual(out[-1], pts[-1])

    def test_state_on_empty_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = server.state(Project(H.new_project(tmp)))
            self.assertEqual(set(s), STATE_KEYS)
            self.assertEqual((s["runs"], s["tracks"], s["champions"], s["champion"]), ([], [], [], None))
            json.dumps(s, default=str)


if __name__ == "__main__":
    unittest.main()
