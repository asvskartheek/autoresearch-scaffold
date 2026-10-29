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


class GoalLintTitles(unittest.TestCase):
    ST = dict(slice="pid/full", n=183, kpi="score", target=0.84, value=0.825, model="a+b+c+d", baseline="a",
              vs_baseline=dict(delta=0.137, lo=0.07, hi=0.19, n=183), hills={}, status="open")

    def html(self, system):
        return (f'<section data-block="result"><p data-block="r">draft. pid/full n = 183, target 84%, now 82.5%, '
                f'Context engine v2 vs Start: +13.7 pts, 90% CI</p></section>'
                f'<section data-block="system"><figure data-block="f"><svg></svg>{system}</figure></section>')

    def test_title_names_the_model(self):
        titles = {"a+b+c+d": "Context engine v2", "a": "Start"}
        errs = [m for _, m in papers.check_goal(self.html("Start then Context engine v2"), self.ST, titles=titles)]
        self.assertEqual(errs, [])
        errs = [m for _, m in papers.check_goal(self.html("a then a+b+c+d"), self.ST, titles=titles)]
        self.assertEqual(errs, [])  # the id still counts
        errs = [m for _, m in papers.check_goal(self.html("Start only"), self.ST, titles=titles)]
        self.assertTrue(any("'Context engine v2' or 'a+b+c+d'" in m for m in errs), errs)


class OwedEdit(unittest.TestCase):
    def test_promised_edit_stays_pending_until_republished(self):
        p, src = project()
        papers.add(p, "demo", src, hill="h")
        c = papers.post(p, "demo", "comment", body="draw it", anchor=dict(block="b1"), author="Ann")
        time.sleep(0.02)
        papers.post(p, "demo", "reply", parent=c["id"], body="Agreed, I will redraw it.", agent=True, owe=True)
        self.assertEqual([t["id"] for t in papers.owed(p)], [c["id"]])
        self.assertEqual(papers.papers(p)["demo"]["owed"], 1)
        self.assertFalse(papers.threads(papers.thread(p, "demo"))[0]["waiting"])
        time.sleep(0.02)
        papers.add(p, "demo", src, hill="h")  # republished
        self.assertEqual(papers.owed(p), [])

    def test_promise_detection(self):
        self.assertTrue(papers.promises("Agreed, the figure is thin. I'll draw each part with its input."))
        self.assertFalse(papers.promises("Redrawn and republished: each part now shows its input."))
        self.assertFalse(papers.promises("The judge is a separate model with no rubric."))


class Health(unittest.TestCase):
    def test_lint_errors_and_champion_drift(self):
        p, src = project()
        p.add_dataset("ds", list(range(4)))
        p.open_hill("h", "Hill", "ds/full") if hasattr(p, "open_hill") else None
        papers.add(p, "h", src, hill="h")
        hl = papers.papers(p, with_health=True)["h"]["health"]
        self.assertGreater(hl["errors"], 0); self.assertTrue(hl["first"])
        self.assertEqual(hl["stale"], [])
        time.sleep(0.02)
        p.add_model("m", status="champion"); p._upsert("models", "m", promoted=time.time())
        self.assertEqual(papers.health(p, "h")["stale"], ["champion changed after it was published"])


if __name__ == "__main__":
    unittest.main()
