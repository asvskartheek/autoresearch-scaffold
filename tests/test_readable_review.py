"""readable() review fixes: inflections and compounds stay whole, run-together acronyms and numbers split."""
import unittest

from autoresearch.readable import readable


class Readable(unittest.TestCase):
    def test_words_stay_whole(self):
        for w in ("planned", "readouts", "handoff", "inlines", "base64", "getApps()", "drawing(s)", "bf16 sha256",
                  "HTTPServer", "4B and 10k gsm8k"):
            self.assertEqual(readable(w), w)

    def test_run_together_splits(self):
        self.assertEqual(readable("GRPO192steps"), "GRPO 192 steps")
        self.assertEqual(readable("90CInotpositive"), "90 CI not positive")
        self.assertEqual(readable("Failedfrozenpairedgate"), "Failed frozen paired gate")
        self.assertEqual(readable("Plannedrerun"), "Planned rerun")
        self.assertEqual(readable("plus4096 tokens"), "plus 4096 tokens")

    def test_earlier_cases_hold(self):
        self.assertEqual(readable("audit1319:95wrong,34cap hits"), "audit 1319: 95 wrong, 34 cap hits")
        self.assertEqual(readable("rescored151/185 vs150,90%CI"), "rescored 151/185 vs 150, 90% CI")
        self.assertEqual(readable("see results(table 2)"), "see results (table 2)")


if __name__ == "__main__":
    unittest.main()
