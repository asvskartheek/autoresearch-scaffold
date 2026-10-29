"""Intake in units: a continuous slice takes an amount, not a count; the CLI prints the target with its comparator."""
import json, os, tempfile, unittest
from pathlib import Path

os.environ.setdefault("ARX_HOME", tempfile.mkdtemp())
from autoresearch import intake
from autoresearch.core import Project


def ledger():
    d = Path(tempfile.mkdtemp()) / "iu"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="iu", higher_is_better=True, ladder=[], primary_dataset="ds")))
    p = Project(d)
    p.add_dataset("ds", list(range(1319)))
    p.add_slice("ds/cold", list(range(24)), kind="synthetic", metric="minus ms to paint", scale="continuous", unit="ms")
    return p


class IntakeUnitsTest(unittest.TestCase):
    def test_target_text(self):
        p = ledger()
        T = lambda g: intake.target_text(p, g)
        self.assertEqual(T(dict(kpi="score", slice="ds/full", count=1267, n=1319)), "≥ 1,267 of 1,319 correct")
        self.assertEqual(T(dict(kpi="latency_p50", slice="ds/full", target=10.0)), "≤ 10 s median")
        self.assertEqual(T(dict(kpi="score", slice="ds/cold", target=-1000.0)), "≤ 1,000 ms")
        self.assertEqual(T(dict(kpi="cost", slice="ds/full", target=0.002)), "≤ $0.002 per answer")

    def test_continuous_slice_has_no_count(self):
        p = ledger()
        g = intake._clean_goal(p, dict(name="fast", title="Home under 1 s", slice="ds/cold", target=-1000))
        self.assertNotIn("count", g)
        self.assertEqual((g["target"], g["unit"], g["scale"]), (-1000.0, "ms", "continuous"))
        self.assertEqual(intake._target(dict(target=-1000, count=3), "score", 24, continuous=True), -1000.0)

    def test_example_title_is_in_units(self):
        self.assertNotIn("at 96%", intake.PROPOSAL)


if __name__ == "__main__":
    unittest.main()
