"""Fixes found while porting real projects: legacy continuous slices, units of unpaired gate checks, pooled error
shares, CLI links and labels. Run: PYTHONPATH=. python3 -m unittest discover -s tests"""
import io, json, os, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import core
from autoresearch.core import Project, Task


def project(ladder=None, **cfg):
    d = Path(tempfile.mkdtemp()) / "bench"
    d.mkdir()
    ladder = ladder or [dict(rung="dev", checks=[dict(slice="lat/n6", rule="not_worse", tolerance=0.05)])]
    (d / "research.json").write_text(json.dumps(dict(name="bench", higher_is_better=True, ladder=ladder, **cfg)))
    return Project(d)


def legacy_slice(p, name="lat/n6", n=6):
    """A continuous slice frozen before `scale` existed: no scale, no unit in slices.json."""
    p.add_slice(name, [f"x{i}" for i in range(n)], kind="synthetic")
    data = json.loads((p.dir / "slices.json").read_text())
    data[name].pop("scale", None)
    (p.dir / "slices.json").write_text(json.dumps(data))
    return name


def run(p, model, sl, scores, errors=(), contract=None):
    t = Task(p, "eval", f"{model} on {sl}", model=model, slice=sl,
             config=dict(baseline_contract=contract) if contract else None)
    for i, s in enumerate(scores):
        row = dict(id=f"x{i}", score=0.0 if i in errors else s)
        if i in errors:
            row["error"] = "timeout"
        t.add_row(row)
    t.finish()
    return t


def arx(p, *argv) -> str:
    """Run the CLI in the project's folder; its stdout."""
    from autoresearch import cli
    out, cwd = io.StringIO(), os.getcwd()
    os.chdir(p.root)
    try:
        with redirect_stdout(out):
            try:
                cli.main(list(argv))
            except SystemExit as e:
                if e.code not in (None, 0, 3):
                    raise
    finally:
        os.chdir(cwd)
    return out.getvalue()


def continuous_slice(p, name="tps/n6", n=6, unit="tok/s"):
    p.add_slice(name, [f"x{i}" for i in range(n)], kind="synthetic", scale="continuous", unit=unit, metric="tokens per second")
    return name


class LegacyContinuousScale(unittest.TestCase):
    def test_errored_row_is_left_out_on_a_legacy_continuous_slice(self):
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [-2.5] * 6, errors={0})
        self.assertIsNone(p._slice_field(sl, "scale"))
        self.assertEqual(p.slice_scale(sl), "continuous")
        self.assertTrue(p.is_continuous(sl))
        sc = p.pooled_scores("v0", sl)
        self.assertEqual(len(sc), 5)  # the errored row is not a perfect 0 seconds
        self.assertAlmostEqual(sum(sc.values()) / len(sc), -2.5)

    def test_server_state_and_learn_agree_with_core(self):
        from autoresearch import learn, server
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [-2.5] * 6, errors={0})
        st = server._state(p)
        self.assertEqual(st["slices"][sl]["scale"], "continuous")
        self.assertAlmostEqual(st["leaderboard"][sl]["v0"]["score"], -2.5)
        self.assertTrue(learn._cont(p, sl))

    def test_binary_legacy_slice_stays_binary(self):
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [1, 0, 1, 1, 0, 1])
        self.assertEqual(p.slice_scale(sl), "binary")


class SharedDashboardScale(unittest.TestCase):
    def test_learn_sees_a_slice_edit_on_a_long_lived_project(self):
        from autoresearch import learn
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [1, 0, 1, 1, 0, 1])
        self.assertFalse(learn._cont(p, sl))  # cached on this Project, as the shared dashboard keeps it
        data = json.loads((p.dir / "slices.json").read_text())
        data[sl].update(scale="continuous", unit="s", metric="minus seconds")
        (p.dir / "slices.json").write_text(json.dumps(data, indent=2))
        self.assertTrue(learn._cont(p, sl))
        self.assertEqual(learn._unit(p, sl), "s")

    def test_first_run_decides_a_legacy_slice_on_a_long_lived_project(self):
        from autoresearch import learn
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        self.assertFalse(learn._cont(p, sl))  # no run yet
        run(p, "v0", sl, [-2.5] * 6)
        self.assertTrue(learn._cont(p, sl))


class UnpairedRelativeTolerance(unittest.TestCase):
    def setUp(self):
        self.p = project([dict(rung="dev", checks=[dict(slice="tps/n6", rule="not_worse", tolerance=0.05)])])
        continuous_slice(self.p)
        self.p.add_model("v0", status="champion")
        self.p.add_model("v1", parent="v0")
        run(self.p, "v0", "tps/n6", [200.0] * 6)

    def test_unpaired_check_is_a_fraction_of_the_champion(self):
        c = self.p.gate("v1")["rungs"][0]["checks"][0]
        self.assertEqual(c["state"], "need_run")
        self.assertEqual((c["relative"], c["threshold_fraction"], c["threshold"]), (True, -0.05, -0.05))
        out = arx(self.p, "gate", "v1")
        self.assertIn("within 5% of the champion's mean", out)
        self.assertNotIn("tok/s", out)

    def test_paired_check_is_in_units(self):
        run(self.p, "v1", "tps/n6", [205.0] * 6)
        c = self.p.gate("v1")["rungs"][0]["checks"][0]
        self.assertEqual((c["relative"], c["threshold_fraction"]), (True, -0.05))
        self.assertAlmostEqual(c["threshold"], -10.0)
        self.assertIn("−10 tok/s", arx(self.p, "gate", "v1"))

    def test_paper_ladder_marks_unpaired_checks_relative(self):
        from autoresearch import reference
        c = reference.build(self.p, "v1", cache=False)["ladder"][0]["checks"][0]
        self.assertEqual((c["state"], c["relative"], c["threshold_fraction"]), ("need_run", True, -0.05))


class StatusGoalTarget(unittest.TestCase):
    def test_status_rounds_the_target_count_up(self):
        p = project([])
        p.add_slice("qa/n5", [f"x{i}" for i in range(5)], kind="full")
        p.add_model("v0", status="champion")
        run(p, "v0", "qa/n5", [1, 1, 0, 0, 0])
        p.open_goal("half", "Half right", "qa/n5", 0.5)  # 2.5 of 5: two misses it (round() gives 2), three meets it
        out = arx(p, "status")
        self.assertIn("2/5 (40.0%) / 3/5 (50.0%) on qa/n5", out)


class ProjectLinks(unittest.TestCase):
    def test_links_carry_the_project_prefix(self):
        import socket
        from autoresearch import cli, projects
        p = project([])
        key = projects.register(p.root)
        with socket.socket() as srv:  # stands in for the shared dashboard this project started
            srv.bind(("127.0.0.1", 0))
            srv.listen()
            port = srv.getsockname()[1]
            p.dir.mkdir(exist_ok=True)
            (p.dir / "server.json").write_text(json.dumps(dict(port=port)))
            self.assertEqual(cli._served(p), f"http://127.0.0.1:{port}/p/{key}")
            with mock.patch.object(cli, "_up", return_value=f"http://127.0.0.1:{port}"), \
                    mock.patch("autoresearch.answer.spawn"):
                self.assertEqual(arx(p, "up").split()[0], f"http://127.0.0.1:{port}/p/{key}/")

    def test_paper_fallback_link_carries_the_prefix(self):
        from autoresearch import cli, projects
        p = project([])
        key = projects.register(p.root)
        self.assertEqual(cli._project_url(p.root, "http://127.0.0.1:8890"), f"http://127.0.0.1:8890/p/{key}")


class TaskStartTitle(unittest.TestCase):
    def test_title_as_a_positional_argument(self):
        p = project([])
        tid = arx(p, "task", "start", "Download the weights").strip()
        self.assertEqual(p.task(tid)["title"], "Download the weights")
        tid = arx(p, "task", "start", "--title", "Prepare the data").strip()
        self.assertEqual(p.task(tid)["title"], "Prepare the data")


class BaselineDryRun(unittest.TestCase):
    def setUp(self):
        self.p = project([], baseline_cmd="true")
        self.p.add_slice("qa/full", [f"x{i}" for i in range(4)], kind="full")
        self.p.add_slice("qa/random2", ["x0", "x1"], kind="random")
        self.p.add_model("v0", status="champion")
        run(self.p, "v0", "qa/full", [1, 1, 1, 1])
        run(self.p, "v0", "qa/full", [0, 0, 1, 1])

    def test_pooled_runs_show_the_pooled_score(self):
        h = self.p.baseline_plan("v0")["have"]["qa/full"]
        self.assertEqual((h["runs"], h["score"], h["latest_score"]), (2, 0.75, 0.5))
        out = arx(self.p, "baseline", "--dry-run")
        self.assertRegex(out, r"reused +qa/full +0\.750 .*2 runs pooled")

    def test_replace_labels_runs_to_replace(self):
        out = arx(self.p, "baseline", "--dry-run", "--replace")
        self.assertIn("2 slices to run; the runs on 1 of them are replaced", out)
        self.assertRegex(out, r"would replace +qa/full")
        self.assertRegex(out, r"would run +qa/random2")
        self.assertNotIn("already run, 2 to run", out)
        self.assertNotRegex(out, r"missing +qa/full")


class ChampionGate(unittest.TestCase):
    def test_champion_rungs_show_no_run_not_a_bar(self):
        ladder = [dict(rung="random4", checks=[dict(slice="qa/random4", rule="not_worse", tolerance=0.02)]),
                  dict(rung="full", checks=[dict(slice="qa/full", rule="better")])]
        p = project(ladder)
        p.add_slice("qa/full", [f"x{i}" for i in range(6)], kind="full")
        p.add_slice("qa/random4", [f"x{i}" for i in range(4)], kind="random")
        p.add_model("v0", status="champion")
        run(p, "v0", "qa/full", [1, 1, 1, 0, 0, 0])
        g = p.gate("v0")
        r4, full = g["rungs"][0]["checks"][0], g["rungs"][1]["checks"][0]
        self.assertEqual((r4["champion_runs"], r4["champion_score"]), (0, None))
        self.assertEqual((full["champion_runs"], full["champion_score"]), (1, 0.5))
        out = arx(p, "gate", "v0")
        self.assertRegex(out, r"champion +qa/random4 +no run")
        self.assertRegex(out, r"champion +qa/full +3 of 6")
        self.assertNotIn("pts", out)


class PooledErrorShare(unittest.TestCase):
    def setUp(self):
        ladder = [dict(rung="full", checks=[dict(slice="qa/full", rule="better")])]
        self.p = p = project(ladder)
        p.add_slice("qa/full", [f"x{i}" for i in range(10)], kind="full")
        p.add_model("v0", status="champion")
        p.add_model("v1", parent="v0")
        run(p, "v0", "qa/full", [1] * 10)
        run(p, "v0", "qa/full", [1] * 10, errors=set(range(8)))  # a broken repeat pools in silently
        run(p, "v1", "qa/full", [1] * 10)
        p.open_goal("all", "All right", "qa/full", 1.0)

    def test_goal_status_serves_the_pooled_error_share(self):
        st = self.p.goal_status("all")
        self.assertEqual((st["pooled_rows"], st["pooled_errors"], st["errors"]), (20, 8, 8))
        self.assertAlmostEqual(st["error_share"], 0.4)
        self.assertIn("warning: 8 of 20 pooled rows of v0 are errors (40%)", arx(self.p, "goal", "status"))

    def test_gate_checks_serve_both_sides(self):
        c = self.p.gate("v1")["rungs"][0]["checks"][0]
        self.assertEqual((c["base_rows"], c["base_errors"], c["cand_rows"], c["cand_errors"]), (20, 8, 10, 0))
        self.assertAlmostEqual(c["base_error_share"], 0.4)
        self.assertEqual(c["cand_error_share"], 0.0)
        self.assertTrue(c["error_warn"])
        out = arx(self.p, "gate", "v1")
        self.assertIn("warning: 8 of 20 pooled rows of v0 are errors", out)
        self.assertNotIn("rows of v1 are errors", out)

    def test_leaderboard_serves_it(self):
        from autoresearch import server
        st = server._state(self.p)
        e = st["leaderboard"]["qa/full"]["v0"]
        self.assertEqual((e["pooled_rows"], e["pooled_errors"], e["errors"]), (20, 8, 8))
        self.assertAlmostEqual(e["error_share"], 0.4)
        self.assertEqual(st["error_share_warn"], 0.1)
        self.assertEqual(st["goals"]["all"]["pooled_errors"], 8)

    def test_the_warning_starts_at_ten_percent(self):
        from autoresearch import cli
        self.assertIsNone(cli._error_warning("v0", 1, 11))
        self.assertIn("1 of 10 pooled rows", cli._error_warning("v0", 1, 10))

    def test_a_clean_pool_prints_no_warning(self):
        p = project([])
        p.add_slice("qa/full", ["x0", "x1"], kind="full")
        p.add_model("v0", status="champion")
        run(p, "v0", "qa/full", [1, 0])
        p.open_goal("g", "G", "qa/full", 1.0)
        self.assertNotIn("warning", arx(p, "goal", "status"))


class LeaderboardPairsUnderTheRowsHarness(unittest.TestCase):
    def test_rows_carry_the_matched_delta(self):
        from autoresearch import server
        p = project([])
        p.add_slice("qa/full", [f"x{i}" for i in range(4)], kind="full")
        p.add_model("v0", status="champion")
        p.add_model("old", parent="v0")
        p.add_model("lone", parent="v0")
        run(p, "v0", "qa/full", [1, 0, 0, 0], contract="A")
        run(p, "v0", "qa/full", [1, 1, 1, 0], contract="B")  # the champion's latest run: another harness
        run(p, "old", "qa/full", [1, 1, 0, 0], contract="A")
        run(p, "lone", "qa/full", [1, 1, 0, 0], contract="C")
        board = server._state(p)["leaderboard"]["qa/full"]
        self.assertNotEqual(board["old"]["baseline_contract"], board["v0"]["baseline_contract"])
        v = board["old"]["vs_champion"]
        self.assertEqual((v["state"], v["baseline_contract"], v["n"], v["cand_runs"], v["base_runs"]), ("paired", "A", 4, 1, 1))
        self.assertAlmostEqual(v["delta"], 0.25)  # vs the champion's run under A, not its newer B run
        self.assertEqual(board["lone"]["vs_champion"]["state"], "champion_other_harness")
        self.assertIsNone(board["v0"]["vs_champion"])


class GoalPairingOnContinuousSlices(unittest.TestCase):
    def test_errored_rows_do_not_inflate_the_goal_delta(self):
        from autoresearch import reference
        p = project([])
        sl = continuous_slice(p, "lat/n6", unit="ms")
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [-100.0] * 6)
        p.open_goal("fast", "Under 50 ms", sl, -50.0)
        p.add_model("v1", parent="v0")
        run(p, "v1", sl, [-90.0] * 6, errors={0, 1})  # two timeouts: never "0 ms", a perfect score
        p.promote("v1", force=True, baseline=False)
        for vs in (p.goal_status("fast")["vs_baseline"], reference.build(p, "v1", cache=False)["goals"][0]["vs_baseline"]):
            self.assertEqual(vs["n"], 4)
            self.assertAlmostEqual(vs["delta"], 10.0)


class OldContinuousSummaries(unittest.TestCase):
    def test_summary_written_before_the_rule_is_right_on_read(self):
        from autoresearch import server
        p = project([])
        sl = continuous_slice(p, "lat/n6", unit="ms")
        p.add_model("v0", status="champion")
        t = run(p, "v0", sl, [-168.0] * 6, errors={0, 1})
        f = p.task_dir(t.id) / "task.json"
        old = json.loads(f.read_text())
        old["summary"] = dict(core.summarize(p.rows(t.id)), missing=0)  # as the 0/1 rule wrote it: errors as 0
        old["summary"].pop("errors_excluded", None)
        f.write_text(json.dumps(old))
        self.assertAlmostEqual(old["summary"]["score"], -112.0)
        self.assertAlmostEqual(p.task(t.id)["summary"]["score"], -168.0)
        self.assertAlmostEqual(next(x for x in p.tasks() if x["id"] == t.id)["summary"]["score"], -168.0)
        self.assertAlmostEqual(server.task_detail(p, t.id)["task"]["summary"]["score"], -168.0)
        self.assertEqual(json.loads(f.read_text())["summary"]["score"], -112.0)  # the ledger is not rewritten

    def test_legacy_slice_summary_is_recomputed_too(self):
        p = project([])
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [-2.0] * 6)
        t = run(p, "v0", sl, [-2.0] * 6, errors={0, 1, 2})
        f = p.task_dir(t.id) / "task.json"
        old = json.loads(f.read_text())
        old["summary"] = dict(core.summarize(p.rows(t.id)), missing=0)
        old["summary"].pop("errors_excluded", None)
        f.write_text(json.dumps(old))
        self.assertAlmostEqual(next(x for x in p.tasks() if x["id"] == t.id)["summary"]["score"], -2.0)


class ChampionWithoutAHill(unittest.TestCase):
    def test_ladder_slices_is_empty_when_nothing_resolves(self):
        from autoresearch import server
        ladder = [dict(rung="dev", checks=[dict(slice="@hill.target", rule="better"),
                                           dict(slice="@hill.control", rule="not_worse", tolerance=0.05),
                                           dict(slice="@hills.climbed", rule="not_worse", tolerance=0.03)])]
        p = project(ladder)
        p.add_slice("qa/full", ["x0", "x1"], kind="full")
        p.add_model("v0", status="champion")
        g = p.gate("v0")
        self.assertEqual(g["ladder_slices"], [])
        self.assertEqual(server._state(p)["gates"]["v0"]["ladder_slices"], [])

    def test_ladder_slices_lists_what_resolves(self):
        ladder = [dict(rung="dev", checks=[dict(slice="@hill.target", rule="better")]),
                  dict(rung="full", checks=[dict(slice="qa/full", rule="better")])]
        p = project(ladder)
        p.add_slice("qa/full", ["x0", "x1"], kind="full")
        p.add_model("v0", status="champion")
        self.assertEqual(p.gate("v0")["ladder_slices"], [dict(rung="full", slice="qa/full")])


if __name__ == "__main__":
    unittest.main()
