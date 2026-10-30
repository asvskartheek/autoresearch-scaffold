"""Exercise a fresh server, so test imports cannot hide missing feature registration."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen


class DashboardBoot(unittest.TestCase):
    def test_course_and_all_shell_assets_survive_a_fresh_boot(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "research.json").write_text(json.dumps({"name": "Empty boot", "ladder": []}))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, PYTHONPATH=str(source), ARX_HOME=str(root / "registry"))
            with (root / "server.log").open("w+") as log:
                process = subprocess.Popen([sys.executable, "-m", "autoresearch", "serve", "--port", str(port)],
                                           cwd=root, env=env, stdout=log, stderr=log)
                base = f"http://127.0.0.1:{port}"
                try:
                    for _ in range(100):
                        try:
                            with urlopen(base + "/", timeout=1) as response:
                                html = response.read().decode()
                            break
                        except OSError:
                            if process.poll() is not None:
                                log.seek(0)
                                self.fail(log.read())
                            time.sleep(.05)
                    else:
                        self.fail("Dashboard did not start")
                    assets = re.findall(r'(?:src|href)="([^"#]+\.(?:js|css))"', html)
                    self.assertIn("views/course.js", assets)
                    for asset in assets:
                        if "://" in asset:
                            continue
                        with self.subTest(asset=asset), urlopen(base + "/" + asset) as response:
                            self.assertEqual(response.status, 200)
                            self.assertGreater(len(response.read()), 0)
                    with urlopen(base + "/api/course?viewer=boot-test") as response:
                        course = json.load(response)
                    self.assertIn("paired-delta", {lesson["id"] for lesson in course["lessons"]})
                    self.assertEqual(course["due"], [])
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
