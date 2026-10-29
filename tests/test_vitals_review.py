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



class Silence(unittest.TestCase):
    def test_eta_slips_while_silent(self):
        b = [(float(i), i) for i in range(31)]          # 1 step a second for 30 s, then nothing
        live = vitals.eta_track(b, 1000, now=30.5)
        self.assertAlmostEqual(live["finish_at"], 30 + 970, delta=1)
        quiet = vitals.eta_track(b, 1000, now=150)
        self.assertGreater(quiet["finish_at"], 150 + 970)     # never sooner than now + what is left at the old rate
        self.assertLess(quiet["per_min"], live["per_min"])     # the rate decays with the silence
        later = vitals.eta_track(b, 1000, now=270)
        self.assertGreater(later["finish_at"], quiet["finish_at"])
        self.assertAlmostEqual(later["silent_s"], 240)


class Dead(unittest.TestCase):
    def test_silent_over_a_day_is_dead_not_long(self):
        n = time.time()
        t = dict(status="stalled", heartbeat=n - 3 * 86400, created=n - 4 * 86400, kind="eval")
        self.assertTrue(vitals.is_dead(t, n))
        self.assertFalse(vitals.is_long(t, None, n, 3))
        self.assertTrue(vitals.is_long(t | dict(heartbeat=n - 900), None, n, 3))
