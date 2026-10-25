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
        self.assertRegex(r.stdout, r"missing +qa/full")
        self.assertIn("baseline_cmd", r.stdout)
        self.assertEqual(self.arx("baseline").returncode, 3)
        last = [json.loads(l) for l in (self.root / ".research/decisions.jsonl").read_text().splitlines()][-1]
        self.assertEqual((last["kind"], last["reused"], last["ran"]), ("baseline", 1, 0))

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

    def test_python_promote_baselines(self):
        self.set_cmd(f"PYTHONPATH={REPO} {sys.executable} run.py {{model}} {{slice}}")
        res = self.p.promote("v2", force=True, say=lambda *_: None)
        self.assertEqual((res["need"], res["ran"]), ([], 4))
        self.assertIsNone(Project(self.root).promote("v2", force=True, baseline=False))

    def test_timeout_kills_the_whole_command(self):
        self.set_cmd("sleep 29.4417; touch late")  # a compound command: the shell does not exec into sleep
        self.arx("baseline", "v2", "--budget-s", "1")
        out = subprocess.run(["pgrep", "-f", "sleep 29.4417"], capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "")

    def test_braces_in_cmd_are_left_alone(self):
        self.set_cmd(f"{sys.executable} run.py {{model}} {{slice}} && echo '{{not a placeholder}}'")
        r = self.arx("baseline", "v2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("{not a placeholder}", r.stdout)

    def test_no_baseline_flag(self):
        r = self.arx("promote", "v2", "--force", "--no-baseline")
        self.assertIn("skipped baselining", r.stdout)
        self.assertFalse(any(t["kind"] == "baseline" for t in self.p.tasks()))

    def set_cmd(self, cmd):
        cfg = json.loads((self.root / "research.json").read_text())
        (self.root / "research.json").write_text(json.dumps(cfg | {"baseline_cmd": cmd}))

    def test_dry_run_with_cmd_says_would_run(self):
        self.set_cmd(f"{sys.executable} run.py {{model}} {{slice}}")
        r = self.arx("baseline", "v2", "--dry-run")
        self.assertRegex(r.stdout, r"would run +qa/full")
        self.assertFalse(any(t["kind"] == "baseline" for t in self.p.tasks()))

    def test_slice_names_are_shell_quoted(self):
        self.p.add_slice("qa/odd name;touch pwned", [6, 7], hill="h2")
        self.p.open_hill("h2", "H2", "qa/odd name;touch pwned")
        self.set_cmd(f"{sys.executable} run.py {{model}} {{slice}}")
        r = self.arx("baseline", "v2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.root / "pwned").exists())
        self.assertIn("qa/odd name;touch pwned", self.p.baseline_plan("v2")["have"])

    def test_jobs_run_in_parallel(self):
        self.set_cmd(f"{sys.executable} run.py {{model}} {{slice}}")
        r = self.arx("baseline", "v2", "--jobs", "4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.p.baseline_plan("v2")["need"], [])

    def test_budget_stops_and_leaves_missing(self):
        self.set_cmd("sleep 5")
        r = self.arx("baseline", "v2", "--budget-s", "1")
        self.assertEqual(r.returncode, 3)
        base = next(t for t in self.p.tasks() if t["kind"] == "baseline")
        self.assertEqual(base["status"], "budget")
        self.assertLess(base["ended"] - base["created"], 10)  # stopped long before the 5 s commands finished

    def test_rerun_pools_replace_supersedes(self):
        self.set_cmd(f"{sys.executable} run.py {{model}} {{slice}}")
        self.arx("baseline", "v2")
        self.arx("baseline", "v2", "--rerun")
        self.assertEqual(self.p.baseline_plan("v2")["have"]["qa/t1"]["runs"], 2)
        r = self.arx("baseline", "v2", "--replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(5 run now)", r.stdout)
        self.assertEqual(self.p.baseline_plan("v2")["have"]["qa/t1"]["runs"], 1)
        old = [t for t in self.p.tasks() if t.get("slice") == "qa/t1" and t.get("superseded_by")]
        self.assertEqual(len(old), 2)  # kept in the archive, not counted

    def test_promote_exits_3_when_cmd_leaves_gaps(self):
        self.set_cmd("exit 1")
        r = self.arx("promote", "v2", "--force")
        self.assertEqual(r.returncode, 3)
        self.assertEqual(self.p.champion(), "v2")  # the promotion itself stands


if __name__ == "__main__":
    unittest.main()
