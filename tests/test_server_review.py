"""Server review fixes: the state's task window, the full task list, cheap project rows and readable reject reasons."""
import json, os, tempfile, time, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import projects, server
from autoresearch.core import Project, Task


def ledger(name="demo"):
    d = Path(tempfile.mkdtemp()) / name
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name=name, higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(4)))
    return p


class Window(unittest.TestCase):
    def test_live_newest_kept_and_parents(self):
        ts = [dict(id=f"d{i}", status="done", ended=i, updated=i) for i in range(200)]
        ts += [dict(id="old-parent", status="done", ended=-5, updated=-5),
               dict(id="live", status="running", parent="old-parent", updated=300),
               dict(id="kid", status="done", parent="live", ended=-9, updated=-9),
               dict(id="goal-ev", status="done", ended=-3, updated=-3)]
        ids = {t["id"] for t in server.window(ts, {"goal-ev"})}
        self.assertTrue({"live", "kid", "old-parent", "goal-ev", "d199", f"d{200 - server.WINDOW}"} <= ids)
        self.assertNotIn("d0", ids)
        self.assertEqual(len(ids), server.WINDOW + 4)

    def test_running_jobs_counts_atomic_only(self):
        t = time.time()
        ts = [dict(id="parent", status="running", heartbeat=t), dict(id="child", status="running", parent="parent", heartbeat=t),
              dict(id="ans", status="running", kind="answer", heartbeat=t),
              dict(id="stale", status="running", heartbeat=t - 1200), dict(id="dead", status="stalled", heartbeat=t - 3 * 86400)]
        self.assertEqual(server.running_jobs(ts, 600, t), (1, 1))  # child runs; stale is stalled; dead counts as neither


class State(unittest.TestCase):
    def test_state_window_and_all_tasks(self):
        p = ledger()
        p.add_model("base", status="champion")
        for i in range(server.WINDOW + 5):
            Task(p, "experiment", f"job {i}").finish()
        st = server.state(p)
        self.assertEqual(st["tasks_total"], server.WINDOW + 5)
        self.assertEqual(len(st["tasks"]), server.WINDOW)
        full = server.all_tasks(p)
        self.assertEqual(len(full["tasks"]), server.WINDOW + 5)
        self.assertEqual(full["rev"], st["tasks_rev"])

    def test_project_rows_are_cheap_and_count_waiting_questions(self):
        p = ledger("alpha")
        projects.register(p.root)
        (p.dir / "questions.json").write_text(json.dumps({"q1": dict(title="Ship?", status="open", needs_human=True),
                                                          "q2": dict(title="Done", status="answered", needs_human=True)}))
        Task(p, "experiment", "runs")  # left running
        row = next(r for r in server.project_list(p) if r["name"] == "alpha")
        self.assertEqual((row["running"], row["stalled"], row["asks"], row["waiting"]), (1, 0, 1, 0))


class Decisions(unittest.TestCase):
    def test_old_promotes_kept_with_slim_gate(self):
        f = Path(tempfile.mkdtemp()) / "decisions.jsonl"
        gate = dict(rungs=[dict(rung="dev", status="pass", checks=[dict(slice="ds/dev", n=10, delta=0.1, lo=0.0, hi=0.2, cand_task="x")])])
        lines = [dict(t=0, kind="promote", model="m1", replaced="m0", gate=gate)] + [dict(t=i, kind="note", gate=gate) for i in range(1, 80)]
        f.write_text("\n".join(json.dumps(d) for d in lines))
        out = server._tail(f, 50)
        self.assertEqual(len(out), 51)
        self.assertEqual(out[0]["gate"]["rungs"][0]["checks"][0], dict(slice="ds/dev", n=10, delta=0.1, lo=0.0, hi=0.2))
        self.assertNotIn("gate", out[-1])


class Reasons(unittest.TestCase):
    def test_paths_and_dicts(self):
        r = server._clean_reason("No climb {'n': 185, 'delta': 0.010811, 'lo': -0.011} see /Users/me/work/run/out.json.")
        self.assertEqual(r, "No climb (n 185, delta 0.0108, lo -0.011) see out.json.")


if __name__ == "__main__":
    unittest.main()


class LiveDetail(unittest.TestCase):
    def test_eval_takes_its_subtask_progress_and_marks_next_running(self):
        ts = [dict(id="ev", kind="eval", status="running", model="v2", slice="ds/u", progress=dict(done=0, total=10)),
              dict(id="live", kind="experiment", status="running", parent="ev", progress=dict(done=7, total=10))]
        server.lift_progress(ts)
        self.assertEqual(ts[0]["progress"]["done"], 7); self.assertEqual(ts[1]["detail_of"], "ev")
        gates = {"v2": dict(next=[dict(model="v2", slice="ds/a"), dict(model="base", slice="ds/a")])}
        out = server.running_next(gates, ts, {"ds/a": dict(ids=[1, 2]), "ds/u": dict(ids=[1, 2, 3])})
        self.assertEqual([n.get("running") for n in out["v2"]["next"]], ["ev", None])
        self.assertNotIn("running", gates["v2"]["next"][0])  # the memoised gate is untouched
