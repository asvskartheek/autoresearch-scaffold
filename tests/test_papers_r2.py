"""Papers, round 2: one paper per hill or goal, the goal lint takes the model's title, owed edits and paper health."""
import json, os, tempfile, time, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()
from autoresearch import papers
from autoresearch.core import Project


def project():
    d = Path(tempfile.mkdtemp())
    (d / "research.json").write_text("{}")
    (d / ".research").mkdir()
    src = d / "p.html"
    src.write_text('<p data-block="b1">some text here</p>')
    return Project(d), src


class OnePaper(unittest.TestCase):
    def test_second_paper_for_a_hill_or_goal_is_refused(self):
        p, src = project()
        papers.add(p, "route-trace", src, hill="route-trace")
        papers.add(p, "route-trace", src, hill="route-trace")  # republishing is fine
        with self.assertRaises(ValueError):
            papers.add(p, "route-trace-v2", src, hill="route-trace")
        papers.add(p, "context-engine", src)  # named after the hill, no meta
        with self.assertRaises(ValueError):
            papers.add(p, "ctx-notes", src, hill="context-engine")
        papers.add(p, "g1", src, goal="g1")
        with self.assertRaises(ValueError):
            papers.add(p, "g1-final", src, goal="g1")
        self.assertEqual(papers.owner(p, goal="g1"), "g1")


if __name__ == "__main__":
    unittest.main()
