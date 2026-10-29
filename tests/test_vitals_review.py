"""Review fixes for the Workbench vital signs: budget overrun, silence slips the ETA, dead jobs, panel domains."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch import vitals  # noqa: E402


class Budget(unittest.TestCase):
    def test_finish_past_budget_warns(self):
        n = 1000.0
        t = dict(status="running", heartbeat=n, created=n - 51, budget_s=75)
        eta = dict(finish_at=n + 129, eta_s=129, drift_s=0)
        h = vitals.health(t, eta, n)
        self.assertEqual(h["state"], "over")
        self.assertAlmostEqual(h["by_s"], 129 + 51 - 75)
        self.assertEqual(vitals.health(t | dict(budget_s=600), eta, n)["state"], "ok")


if __name__ == "__main__":
    unittest.main()
