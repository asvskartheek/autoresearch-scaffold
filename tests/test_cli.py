import json, os, signal, socket, tempfile, time, unittest
from pathlib import Path

import helpers as H  # noqa: F401  (must come first)
from autoresearch.core import Project, _write
from helpers import arx


def port_of(url: str) -> int:
    return int(url.strip().rsplit(":", 1)[1])


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(H.kill_all_servers)
        self.addCleanup(lambda: arx(self.tmp, "down", "--all", check=False) if self.tmp.exists() else None)

    def proj(self, name="a", **cfg) -> Path:
        return H.new_project(self.tmp, name, **cfg)

    def up(self, root, port=None, *extra) -> str:
        return arx(root, "up", "--port", port or H.free_port(), *extra).stdout.strip()

    def info(self, root) -> dict:
        return json.loads((root / ".research" / "server.json").read_text())

    # ---- up / down / ps -------------------------------------------------------------
    def test_up_is_idempotent(self):
        a = self.proj()
        u1 = self.up(a)
        self.assertTrue(port_open(port_of(u1)))
        pid = self.info(a)["pid"]
        u2 = self.up(a, H.free_port())  # a different requested port must not spawn a second server
        self.assertEqual(u1, u2)
        self.assertEqual(self.info(a)["pid"], pid)
        self.assertEqual(len(H.registry()), 1)
        self.assertEqual(H.get(port_of(u1), "/api/ping")[1]["name"], "a")

    def test_second_project_gets_another_port(self):
        a, b = self.proj("a"), self.proj("b")
        port = H.free_port()
        ua, ub = self.up(a, port), self.up(b, port)
        self.assertNotEqual(ua, ub)
        self.assertEqual(Path(H.get(port_of(ua), "/api/ping")[1]["root"]), a.resolve())
        self.assertEqual(Path(H.get(port_of(ub), "/api/ping")[1]["root"]), b.resolve())
        self.assertEqual(len(H.registry()), 2)

    def test_up_ignores_port_held_by_other_project(self):
        a, b = self.proj("a"), self.proj("b")
        ua = self.up(a)
        ub = self.up(b, port_of(ua))  # asks for A's port
        self.assertNotEqual(port_of(ub), port_of(ua))
        self.assertEqual(Path(H.get(port_of(ub), "/api/ping")[1]["root"]), b.resolve())
        self.assertEqual(self.up(a, port_of(ua)), ua)  # A still resolves to its own server

    def test_up_skips_port_held_by_non_arx_process(self):
        a = self.proj()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            held = s.getsockname()[1]
            u = self.up(a, held)
            self.assertNotEqual(port_of(u), held)
            self.assertEqual(H.get(port_of(u), "/api/ping")[0], 200)

    def test_down_and_ps(self):
        a, b = self.proj("a"), self.proj("b")
        ua, ub = self.up(a), self.up(b)
        ps = arx(a, "ps").stdout
        self.assertIn(ua, ps)
        self.assertIn(ub, ps)
        self.assertEqual(ps.strip().count("\n"), 1)
        out = arx(a, "down").stdout
        self.assertIn("stopped", out)
        self.assertTrue(H.wait_for(lambda: not port_open(port_of(ua))))
        self.assertTrue(port_open(port_of(ub)), "down only stops this project")
        self.assertNotIn(ua, arx(a, "ps").stdout)
        self.assertIn("no dashboard running", arx(a, "down").stdout)
        arx(b, "down", "--all")
        self.assertTrue(H.wait_for(lambda: not port_open(port_of(ub))))
        self.assertEqual(arx(a, "ps").stdout.strip(), "")
        self.assertEqual(H.registry(), [])

    def test_down_all_stops_every_project(self):
        roots = [self.proj(n) for n in "abc"]
        urls = [self.up(r) for r in roots]
        arx(self.tmp, "down", "--all")
        for u in urls:
            self.assertTrue(H.wait_for(lambda: not port_open(port_of(u))), u)
        self.assertEqual(H.registry(), [])

    def test_restart_keeps_port(self):
        a = self.proj()
        u = self.up(a)
        pid = self.info(a)["pid"]
        self.assertEqual(self.up(a, None, "--restart"), u)
        self.assertNotEqual(self.info(a)["pid"], pid)

    # ---- stale records -----------------------------------------------------------------
    def test_stale_registry_entries_pruned(self):
        a = self.proj()
        dead = os.fork() if hasattr(os, "fork") else None
        if dead == 0:
            os._exit(0)
        os.waitpid(dead, 0)  # a pid that certainly is not running
        (H.HOME / ".arx").mkdir(exist_ok=True)
        (H.HOME / ".arx" / "servers.json").write_text(json.dumps([dict(root="/gone", port=1, pid=dead, started=1)]))
        self.assertEqual(arx(a, "ps").stdout.strip(), "")
        self.assertEqual(H.registry(), [])

    def test_corrupt_registry_tolerated(self):
        a = self.proj()
        (H.HOME / ".arx").mkdir(exist_ok=True)
        (H.HOME / ".arx" / "servers.json").write_text("{not json")
        self.assertEqual(arx(a, "ps").stdout.strip(), "")
        u = self.up(a)
        self.assertEqual(H.get(port_of(u), "/api/ping")[0], 200)

    def test_stale_server_json_after_crash(self):
        a = self.proj()
        u = self.up(a)
        old = self.info(a)["pid"]
        os.kill(old, signal.SIGKILL)
        self.assertTrue(H.wait_for(lambda: not H.pid_alive(old)))
        self.assertTrue((a / ".research" / "server.json").exists())  # SIGKILL leaves it behind
        self.assertEqual(arx(a, "ps").stdout.strip(), "")  # registry pruned
        u2 = self.up(a)
        self.assertEqual(H.get(port_of(u2), "/api/ping")[0], 200)
        self.assertNotEqual(self.info(a)["pid"], old)
        self.assertEqual(port_of(u2), self.info(a)["port"])

    def test_sigterm_unregisters(self):
        a = self.proj()
        u = self.up(a)
        pid = self.info(a)["pid"]
        os.kill(pid, signal.SIGTERM)
        self.assertTrue(H.wait_for(lambda: not H.pid_alive(pid)))
        self.assertTrue(H.wait_for(lambda: not (a / ".research" / "server.json").exists()))
        self.assertEqual(H.registry(), [])
        self.assertFalse(port_open(port_of(u)))

    # ---- idle shutdown (the watcher polls every 15 s) ------------------------------------
    def test_idle_shutdown_only_without_running_task(self):
        quiet = self.proj("quiet", dashboard_idle_minutes=0.005)
        busy = self.proj("busy", dashboard_idle_minutes=0.005)
        pq, pb = self.up(quiet), self.up(busy)
        pidq, pidb = self.info(quiet)["pid"], self.info(busy)["pid"]
        tid = arx(busy, "task", "start", "--title", "long job", "--kind", "experiment").stdout.strip()
        self.assertTrue(tid)
        self.assertTrue(H.wait_for(lambda: not H.pid_alive(pidq), timeout=45), "idle server with no task shuts down")
        self.assertFalse(port_open(port_of(pq)))
        self.assertEqual(H.registry()[0]["pid"], pidb)  # quiet one unregistered itself
        self.assertTrue(H.pid_alive(pidb), "a running task keeps the dashboard up")
        self.assertTrue(port_open(port_of(pb)))
        arx(busy, "task", "finish", tid)
        self.assertTrue(H.wait_for(lambda: not H.pid_alive(pidb), timeout=45), "shuts down once the task has finished")

    # ---- init --------------------------------------------------------------------------------
    def test_init_writes_hooks_once_and_never_overwrites(self):
        root = self.tmp / "fresh"
        arx(self.tmp, "init", root, "--name", "Fresh", "--no-serve")
        settings = root / ".claude" / "settings.json"
        hooks = json.loads(settings.read_text())["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "SessionEnd"})
        self.assertEqual(json.loads((root / "research.json").read_text())["name"], "Fresh")
        gi = (root / ".gitignore").read_text().splitlines()
        self.assertIn("scratch/", gi)
        settings.write_text(json.dumps({"hooks": {}, "mine": True}))
        arx(self.tmp, "init", root, "--no-serve")
        self.assertEqual(json.loads(settings.read_text()), {"hooks": {}, "mine": True})
        self.assertEqual((root / ".gitignore").read_text().splitlines().count("scratch/"), 1)
        self.assertEqual(json.loads((root / "research.json").read_text())["name"], "Fresh")

    def test_init_opens_setup_task_and_starts_dashboard(self):
        root = self.tmp / "fresh2"
        out = arx(self.tmp, "init", root, "--port", H.free_port()).stdout
        self.assertIn("dashboard: http://127.0.0.1:", out)
        tasks = Project(root).tasks()
        self.assertEqual([(t["kind"], t["status"]) for t in tasks], [("setup", "running")])
        url = out.split("dashboard: ")[1].split()[0]
        self.assertEqual(H.get(port_of(url), "/api/ping")[0], 200)
        self.assertEqual(self.up(root), url)  # idempotent with init's server

    def test_init_does_not_clobber_existing_files(self):
        root = self.tmp / "fresh3"
        root.mkdir()
        (root / "AGENTS.md").write_text("mine")
        arx(self.tmp, "init", root, "--no-serve")
        self.assertEqual((root / "AGENTS.md").read_text(), "mine")

    # ---- tasks from the shell --------------------------------------------------------------------
    def stale_task(self, p: Project, tid: str, age_s: float, status="running"):
        t0 = time.time() - age_s
        _write(p.task_dir(tid) / "task.json", dict(id=tid, kind="experiment", title=tid, status=status, created=t0 - 5,
                                                   updated=t0, heartbeat=t0, progress={}, links={}, summary={}))

    def test_sweep(self):
        p = Project(self.proj())
        self.stale_task(p, "old", 3 * 3600)
        self.stale_task(p, "recent-stall", 1800)
        self.stale_task(p, "alive", 10)
        self.stale_task(p, "done-old", 9 * 3600, status="done")
        self.assertEqual({t["id"]: t["status"] for t in p.tasks()},
                         {"old": "stalled", "recent-stall": "stalled", "alive": "running", "done-old": "done"})
        self.assertIn("1 abandoned", arx(p.root, "sweep").stdout)
        st = {t["id"]: t["status"] for t in p.tasks()}
        self.assertEqual(st, {"old": "abandoned", "recent-stall": "stalled", "alive": "running", "done-old": "done"})
        self.assertIn("1 abandoned", arx(p.root, "sweep", "--hours", "0.1").stdout)
        self.assertEqual(p.task("recent-stall")["status"], "abandoned")
        self.assertIn("0 abandoned", arx(p.root, "sweep").stdout)

    def test_task_resume(self):
        p = Project(self.proj())
        self.stale_task(p, "stuck", 3600)
        self.assertEqual(p.task("stuck")["status"], "stalled")
        arx(p.root, "task", "resume", "stuck")
        t = p.task("stuck")
        self.assertEqual(t["status"], "running")  # the same card is alive again
        self.assertEqual([e["msg"] for e in p.events("stuck")], ["resumed"])
        self.assertEqual(len(p.tasks()), 1)

    def test_task_shell_roundtrip(self):
        p = Project(self.proj())
        tid = arx(p.root, "task", "start", "--title", "Build index", "--total", "4").stdout.strip()
        arx(p.root, "task", "log", tid, "loss=0.5", "--step", "1")
        arx(p.root, "task", "note", tid, "halfway there")
        arx(p.root, "task", "progress", tid, "2", "4")
        arx(p.root, "task", "link", tid, "HF", "https://example.invalid/x")
        t = p.task(tid)
        self.assertEqual((t["progress"]["done"], t["links"]["HF"], t["last"]), (2, "https://example.invalid/x", {"loss": 0.5}))
        self.assertEqual(p.events(tid)[-1]["msg"], "halfway there")
        arx(p.root, "task", "finish", tid)
        self.assertEqual(p.task(tid)["status"], "done")

    def test_task_budget_left(self):
        p = Project(self.proj())
        tid = arx(p.root, "task", "start", "--title", "capped", "--budget-s", "3600").stdout.strip()
        self.assertEqual(arx(p.root, "task", "left", tid).returncode, 0)
        spent = arx(p.root, "task", "start", "--title", "spent", "--budget-s", "0.01").stdout.strip()
        time.sleep(0.05)
        self.assertEqual(arx(p.root, "task", "left", spent, check=False).returncode, 3)

    def test_status_on_fixture(self):
        import fixture
        root = self.tmp / "fx"
        fixture.build(root)
        out = arx(root, "status").stdout
        self.assertIn(fixture.CHAMPION, out)
        self.assertIn(f"best on alpha", out)
        self.assertIn(fixture.BEST_SCORE_STR, out)


if __name__ == "__main__":
    unittest.main()
