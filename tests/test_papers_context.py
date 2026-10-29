"""The paper reader's context from the ledger: titles, a goal's current status, and goals or hills with no paper."""
import json, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch import Project, papers  # noqa: E402
from autoresearch.core import evaluate  # noqa: E402


class PaperContext(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "research.json").write_text(json.dumps(dict(name="t", primary_dataset="qa")))
        p = self.p = Project(self.root)
        p.add_dataset("qa", range(20))
        p.add_slice("qa/t1", list(range(5)), hill="h")
        p.open_hill("h", "Breaks on units", "qa/t1")
        p.open_hill("h2", "Another hill", "qa/t1")
        p.add_model("v1", status="champion", change="baseline")
        evaluate(p, "v1", "qa/full", lambda i: {"score": 1.0})
        p.open_goal("g", "Reach 90", "qa/full", 0.9)
        p.open_goal("g2", "Reach 99", "qa/full", 0.99)
        src = self.root / "x.html"
        src.write_text('<h1 data-block="t">Units, <i>explained</i> &amp; fixed</h1>')
        papers.add(p, "h", src, hill="h")
        papers.add(p, "g", src, goal="g", title="Reach 90: draft")

    def test_title_falls_back_to_h1(self):
        self.assertEqual(papers.papers(self.p)["h"]["title"], "Units, explained & fixed")
        self.assertEqual(papers.papers(self.p)["g"]["title"], "Reach 90: draft")

    def test_context_reads_the_goal_status_from_the_ledger(self):
        c = papers.context(self.p, "g")
        self.assertEqual(c["goal"]["status"], "open")
        self.assertEqual(c["goal"]["title"], "Reach 90")
        self.p.abandon_goal("g", "target moved")
        c = papers.context(self.p, "g")
        self.assertEqual(c["goal"]["status"], "abandoned")
        self.assertEqual(c["goal"]["reason"], "target moved")
        self.assertEqual(papers.context(self.p, "h")["hill"]["title"], "Breaks on units")
        with self.assertRaises(KeyError):
            papers.context(self.p, "nope")

    def test_missing_lists_goals_and_live_hills_without_a_paper(self):
        m = papers.missing(self.p)
        self.assertEqual([x["name"] for x in m["goals"]], ["g2"])
        self.assertEqual([x["name"] for x in m["hills"]], ["h2"])


if __name__ == "__main__":
    unittest.main()
