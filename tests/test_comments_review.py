"""Review fixes for comments and `arx answer` (tester-7): agent command parsing, shim cleanup, daemon state, anchors.
Run: python3 -m pytest -q tests"""
import os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import answer, comments, features
from autoresearch.core import Project


def project():
    d = Path(tempfile.mkdtemp())
    (d / "research.json").write_text("{}")
    (d / ".research").mkdir()
    return Project(d)


class AgentCmd(unittest.TestCase):
    def test_quoted_args(self):
        os.environ["ARX_AGENT_CMD"] = 'claude -p --append-system-prompt "be brief please"'
        try:
            self.assertEqual(features.agent_cmd(), ["claude", "-p", "--append-system-prompt", "be brief please"])
        finally:
            os.environ.pop("ARX_AGENT_CMD", None)

    def test_shim_removed_on_exit(self):
        p = project()
        made = []
        real = answer._shim
        answer._shim = lambda: made.append(real()) or made[-1]
        try:
            answer.main(p, once=True, interval=0.1)
        finally:
            answer._shim = real
        self.assertEqual(len(made), 1)
        self.assertFalse(Path(made[0]).exists())


if __name__ == "__main__":
    unittest.main()
