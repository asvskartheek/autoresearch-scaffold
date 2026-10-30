"""readable() review fixes: inflections and compounds stay whole, run-together acronyms and numbers split."""
import unittest

from types import SimpleNamespace
from autoresearch.readable import names, readable


class Readable(unittest.TestCase):
    def test_words_stay_whole(self):
        for w in ("planned", "readouts", "handoff", "inlines", "base64", "getApps()", "drawing(s)", "bf16 sha256",
                  "HTTPServer", "4B and 10k gsm8k", "round7 stack ladder on pid183/full", "dropped", "Bluetooth", "Launcher as shipped, with Bluetooth button"):
            self.assertEqual(readable(w), w)

    def test_run_together_splits(self):
        self.assertEqual(readable("GRPO192steps"), "GRPO 192 steps")
        self.assertEqual(readable("90CInotpositive"), "90 CI not positive")
        self.assertEqual(readable("Failedfrozenpairedgate"), "Failed frozen paired gate")
        self.assertEqual(readable("Plannedrerun"), "Planned rerun")
        self.assertEqual(readable("plus4096 tokens"), "plus 4096 tokens")

    def test_project_names_stay_whole(self):
        self.assertEqual(readable("vs150 for the champion"), "vs 150 for the champion")
        keep = names(SimpleNamespace(models=lambda: {"v2": {}}, slices=lambda: {"gsm8k-test/random50": {}}))
        self.assertEqual(keep, {"v2", "gsm8k-test/random50", "random50"})
        self.assertEqual(readable("Scored the candidate on random50 against the champion.", keep),
                         "Scored the candidate on random50 against the champion.")
        self.assertEqual(readable("audit1319 on random50", keep), "audit 1319 on random50")

    def test_earlier_cases_hold(self):
        self.assertEqual(readable("audit1319:95wrong,34cap hits"), "audit 1319: 95 wrong, 34 cap hits")
        self.assertEqual(readable("rescored151/185 vs150,90%CI"), "rescored 151/185 vs 150, 90% CI")
        self.assertEqual(readable("see results(table 2)"), "see results (table 2)")


if __name__ == "__main__":
    unittest.main()
