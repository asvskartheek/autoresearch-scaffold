"""Workbench vital signs: ETA from a recent rate window, its history, panels by kind, and the GPU sampler."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch import Project, core, features, server, vitals  # noqa: E402
from autoresearch.core import Task, evaluate  # noqa: E402


class Vitals(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "research.json").write_text(json.dumps(dict(name="t", ladder=[])))
        self.p = Project(self.root)
        os.environ.pop("ARX_PARENT", None)

    def test_eta_uses_recent_window_and_records_history(self):
        # 1 item/s for 600 s, then 0.5 item/s: the estimate moves later, and drift says by how much
        b, x, d = [(0.0, 0)], 0.0, 0
        while x < 900:
            x += 10
            d += 10 if x <= 600 else 5
            b.append((x, d))
        e = vitals.eta_track(b, 2000, now=x)
        self.assertAlmostEqual(e["per_min"], 30, delta=0.5)           # the last 5 minutes only
        self.assertAlmostEqual(e["finish_at"], x + (2000 - d) / 0.5, delta=1)
        self.assertGreater(e["drift_s"], 0)
        self.assertTrue(e["hist"] and e["hist"][-1][1] == e["finish_at"])
        self.assertLessEqual(len(e["hist"]), 80)

    def test_eta_none_without_rate(self):
        self.assertIsNone(vitals.eta_track([(0, 0)], 10, 0))
        self.assertIsNone(vitals.eta_track([(0, 0), (5, 0)], 10, 5))

    def test_health_states(self):
        n = time.time()
        self.assertEqual(vitals.health(dict(status="running", heartbeat=n), None, n)["state"], "ok")
        self.assertEqual(vitals.health(dict(status="running", heartbeat=n - 90), None, n)["state"], "quiet")
        self.assertEqual(vitals.health(dict(status="stalled", heartbeat=n - 900), None, n)["state"], "stalled")
        slip = dict(drift_s=600, eta_s=300)
        self.assertEqual(vitals.health(dict(status="running", heartbeat=n), slip, n)["state"], "slipping")

    def test_train_panels_in_state(self):
        t = Task(self.p, "train", "fake", total=100)
        for s in range(1, 30):
            t.log(step=s, loss=1 / s, reward=s / 30, grad_norm=1.0 + s % 3, num_tokens=100 * s, clip=0.0)
            t.progress(s)
        features.load()
        st = server.state(self.p)
        self.assertNotIn("feature_errors", st)
        tt = next(x for x in st["tasks"] if x["id"] == t.id)
        ids = [p["id"] for p in tt["vitals"]]
        self.assertEqual(ids[0], "main")
        self.assertEqual(tt["vitals"][0]["key"], "reward")                # reward leads, loss comes second
        self.assertIn("sec", ids)
        self.assertEqual(next(p for p in tt["vitals"] if p["id"] == "sec")["key"], "loss")
        self.assertTrue(tt["long"])
        self.assertEqual(tt["health"]["state"], "ok")
        t.finish()

    def test_eval_panels_pair_against_champion(self):
        self.p.add_dataset("q", range(20))
        self.p.add_slice("q/d", list(range(20)))
        self.p.add_model("base", status="champion")
        self.p.add_model("c")
        evaluate(self.p, "base", "q/d", lambda i: {"score": float(int(i) < 10)})
        t = Task(self.p, "eval", "c on q/d", model="c", slice="q/d")
        for k, i in enumerate(range(12), 1):
            t.add_row(dict(id=str(i), score=1.0, latency_s=0.5 + k / 10))
            t.progress(k)
            t.log(step=k, running_score=1.0, latency_s=0.5)
        features.load()
        st = server.state(self.p)
        tt = next(x for x in st["tasks"] if x["id"] == t.id)
        pair = next(p for p in tt["vitals"] if p["id"] == "pair")
        self.assertEqual((pair["won"], pair["lost"], pair["value"]), (2, 0, 2))  # ids 10, 11: right where base was wrong
        main = tt["vitals"][0]
        self.assertEqual(main["ref"]["y"], 0.5)
        self.assertEqual(len(main["band"]), 12)
        t.finish()

    def test_series_route(self):
        t = Task(self.p, "train", "x")
        t.log(step=1, loss=1.0)
        t._sys(dict(gpu_util=50.0))
        t.finish()
        features.load()
        code, out = next(fn for pre, fn in features.GET if pre == "/api/vitals/series")(self.p, "/api/vitals/series", {"ids": t.id + ",nope"})
        self.assertEqual(code, 200)
        self.assertEqual(list(out), [t.id])
        self.assertTrue(all(not m.get("sys") for m in out[t.id]["metrics"]))


class Sampler(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "research.json").write_text(json.dumps(dict(name="t", ladder=[])))
        self.p = Project(self.root)
        self.env = dict(os.environ)
        os.environ.pop("ARX_PARENT", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)

    def fake(self, text):
        f = self.root / "gpu.py"
        f.write_text(f"print({text!r})\n")
        os.environ["ARX_SAMPLE_CMD"] = f"{sys.executable} {f}"

    def test_reading_parses_every_gpu(self):
        self.fake("80, 40960, 81920\n100, 20480, 81920")
        self.assertEqual(core.gpu_sample(), dict(gpu_util=90.0, gpu_mem_gb=60.0, gpu_mem_total_gb=160.0, gpus=2))

    def test_sampler_writes_sys_rows_without_touching_last(self):
        self.fake("75, 1024, 2048")
        os.environ["ARX_SAMPLE_S"] = "1"
        t = Task(self.p, "train", "s")
        t.log(step=3, loss=0.5)
        hb = t.meta["heartbeat"]
        time.sleep(2.6)
        rows = self.p.metrics(t.id)
        sysr = [m for m in rows if m.get("sys")]
        self.assertTrue(sysr)
        self.assertEqual(sysr[0]["gpu_util"], 75.0)
        self.assertEqual(sysr[0]["step"], 3)
        self.assertEqual(self.p.task(t.id)["last"], {"loss": 0.5})
        self.assertEqual(self.p.task(t.id)["heartbeat"], hb)   # a hung job still goes stalled
        t.finish()
        n = len(self.p.metrics(t.id))
        time.sleep(1.5)
        self.assertEqual(len(self.p.metrics(t.id)), n)         # nothing after finish

    def test_off_switch_and_missing_tool(self):
        os.environ["ARX_SAMPLE"] = "0"
        self.fake("1, 1, 1")
        t = Task(self.p, "train", "off")
        self.assertNotIn(t, core._sampled)
        t.finish()
        os.environ.pop("ARX_SAMPLE")
        os.environ.pop("ARX_SAMPLE_CMD")
        os.environ["PATH"] = str(self.root)  # no nvidia-smi anywhere
        t = Task(self.p, "train", "none")
        self.assertNotIn(t, core._sampled)
        t.finish()

    def test_broken_command_never_raises(self):
        os.environ["ARX_SAMPLE_CMD"] = "/nonexistent/tool"
        self.assertIsNone(core.gpu_sample())
        self.fake("garbage")
        self.assertIsNone(core.gpu_sample())


if __name__ == "__main__":
    unittest.main()
