"""Baselining a new champion: reuse its runs, run the rest with `baseline_cmd`. `python -m unittest discover tests`"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch import Project  # noqa: E402
from autoresearch.core import Task, evaluate  # noqa: E402

RUN = "import sys, autoresearch as ar; ar.evaluate(sys.argv[1], sys.argv[2], lambda i: {'score': 1.0}, workers=2)\n"


class Baseline(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "research.json").write_text(json.dumps(dict(name="t", ladder=[])))
        (self.root / "run.py").write_text(RUN)
        p = self.p = Project(self.root)
        p.add_dataset("qa", range(20))
        p.random_slices("qa", (5, 10))
        p.add_slice("qa/t1", [1, 2, 3], hill="h")
        p.add_slice("qa/c1", [4, 5], kind="control")
        p.open_hill("h", "H", "qa/t1", "qa/c1")
        p.add_model("v1", status="champion")
        p.add_model("v2", hill="h")
        evaluate(p, "v2", "qa/t1", lambda i: {"score": 1.0})

    def arx(self, *args):
        env = os.environ | {"PYTHONPATH": str(REPO)}
        env.pop("ARX_PARENT", None)
        return subprocess.run([sys.executable, "-m", "autoresearch.cli", *args], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def test_plan_covers_hills_and_dataset_slices(self):
        plan = self.p.baseline_plan("v2")
        self.assertEqual(set(plan["roles"]), {"qa/t1", "qa/c1", "qa/full", "qa/random5", "qa/random10"})
        self.assertEqual(plan["roles"]["qa/c1"], ["hill h control"])
        self.assertEqual(list(plan["have"]), ["qa/t1"])  # its ladder run is reused
        self.assertEqual(sorted(plan["need"]), ["qa/c1", "qa/full", "qa/random10", "qa/random5"])

    def test_partial_run_does_not_count(self):
        t = Task(self.p, "eval", "partial", model="v2", slice="qa/c1")
        t.add_row(dict(id="4", score=1.0))  # id 5 never ran
        t.finish()
        self.assertIn("qa/c1", self.p.baseline_plan("v2")["need"])

    def test_promote_without_cmd_lists_missing(self):
        r = self.arx("promote", "v2", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("missing  qa/full", r.stdout)
        self.assertIn("baseline_cmd", r.stdout)
        self.assertEqual(self.arx("baseline").returncode, 3)
        last = [json.loads(l) for l in (self.root / ".research/decisions.jsonl").read_text().splitlines()][-1]
        self.assertEqual((last["kind"], last["reused"]), ("baseline", 1))

    def test_promote_runs_missing_with_cmd(self):
        cfg = json.loads((self.root / "research.json").read_text())
        (self.root / "research.json").write_text(json.dumps(cfg | {"baseline_cmd": f"{sys.executable} run.py {{model}} {{slice}}"}))
        r = self.arx("promote", "v2", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("done: v2 has a baseline on all 5 slices", r.stdout)
        self.assertEqual(self.p.baseline_plan("v2")["need"], [])
        base = next(t for t in self.p.tasks() if t["kind"] == "baseline")
        self.assertEqual((base["status"], base["summary"]["ran"]), ("done", 4))
        evals = [t for t in self.p.tasks() if t["kind"] == "eval" and t["model"] == "v2" and t["slice"] != "qa/t1"]
        self.assertTrue(evals and all(t["parent"] == base["id"] for t in evals))  # nested under the baseline card
        self.assertEqual(self.arx("baseline").returncode, 0)

    def test_failing_cmd_reports_missing(self):
        cfg = json.loads((self.root / "research.json").read_text())
        (self.root / "research.json").write_text(json.dumps(cfg | {"baseline_cmd": "exit 1"}))
        r = self.arx("baseline", "v2")
        self.assertEqual(r.returncode, 3)
        self.assertIn("still missing", r.stdout)

    def test_no_baseline_flag(self):
        r = self.arx("promote", "v2", "--force", "--no-baseline")
        self.assertIn("skipped baselining", r.stdout)
        self.assertFalse(any(t["kind"] == "baseline" for t in self.p.tasks()))


if __name__ == "__main__":
    unittest.main()
