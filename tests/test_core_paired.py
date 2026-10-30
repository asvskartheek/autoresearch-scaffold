"""core.paired: the fast bootstrap draws what the plain statistics.mean loop drew. Run: python3 -m unittest discover tests"""
import random, statistics, unittest

from autoresearch import core


def slow_paired(cand, base, sign=1, iters=2000):
    ids = sorted(set(cand) & set(base))
    d = [sign * (cand[i] - base[i]) for i in ids]
    rng = random.Random(0)
    boots = sorted(statistics.mean(rng.choices(d, k=len(d))) for _ in range(iters))
    return dict(n=len(ids), delta=statistics.mean(d), lo=boots[int(0.05 * iters)], hi=boots[int(0.95 * iters) - 1],
                wins=sum(x > 0 for x in d), losses=sum(x < 0 for x in d))


class PairedTest(unittest.TestCase):
    def test_same_draws_as_the_plain_loop(self):
        rng = random.Random(3)
        for n, cont in ((1, False), (7, False), (300, False), (120, True)):
            a = {str(i): (rng.random() * 900 if cont else float(rng.random() < .8)) for i in range(n)}
            b = {str(i): (rng.random() * 900 if cont else float(rng.random() < .6)) for i in range(n)}
            for sign in (1, -1):
                core._BOOT.clear()
                want, got = slow_paired(a, b, sign, iters=500), core.paired(a, b, sign, iters=500)
                for k in want:
                    self.assertAlmostEqual(want[k], got[k], places=9, msg=(n, sign, k))

    def test_a_repeat_comes_from_the_cache(self):
        a, b = {str(i): float(i % 3 == 0) for i in range(50)}, {str(i): float(i % 4 == 0) for i in range(50)}
        core._BOOT.clear()
        first = core.paired(a, b)
        self.assertEqual(len(core._BOOT), 1)
        self.assertEqual(core.paired(a, b), first)
        self.assertEqual(len(core._BOOT), 1)

    def test_no_shared_ids(self):
        self.assertEqual(core.paired({"a": 1.0}, {"b": 0.0})["delta"], None)


if __name__ == "__main__":
    unittest.main()
