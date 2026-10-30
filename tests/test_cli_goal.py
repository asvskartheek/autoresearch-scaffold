"""arx goal status: a target count never rounds to a count that misses, and latency and cost carry units."""
import unittest
from unittest import mock

from autoresearch import cli


class KpiFmt(unittest.TestCase):
    def fmt(self, g, v, **kw):
        with mock.patch.object(cli, "Project") as P:
            P.return_value.slices.return_value = {}
            return cli._kpi_fmt(g, v, **kw)

    def test_target_count_meets_the_target(self):
        g = dict(kpi="score", n=1319, higher_is_better=True)
        self.assertEqual(self.fmt(g, 0.96, target=True), "1267/1319 (96.0%)")  # 1266/1319 is 95.98%
        self.assertEqual(self.fmt(g, 0.928, target=False), "1224/1319 (92.8%)")
        self.assertEqual(self.fmt(dict(g, n=183), 0.9, target=True), "165/183 (90.0%)")
        low = dict(kpi="score", n=7, higher_is_better=False)
        self.assertEqual(self.fmt(low, 0.5, target=True), "3/7 (50.0%)")

    def test_units(self):
        self.assertEqual(self.fmt(dict(kpi="latency_p50"), 13.0), "13 s")
        self.assertEqual(self.fmt(dict(kpi="cost"), 0.0123), "$0.0123")

    def test_minus_ms_goal_reads_as_the_plain_amount(self):
        sl = {"cold/n24": dict(scale="continuous", unit="ms", metric="minus ms to paint")}
        st = dict(kpi="score", slice="cold/n24", n=24, higher_is_better=True, scale="continuous", unit="ms",
                  metric="minus ms to paint")
        with mock.patch.object(cli, "Project") as P:
            P.return_value.slices.return_value = sl
            self.assertEqual(cli._kpi_fmt(st, -1458.125), "1458 ms")
            self.assertEqual(cli._kpi_fmt(st, -1000.0, target=True), "1000 ms")
        self.assertEqual(cli._goal_op(st), "<=")
        # a paired gain of 1,071 ms is a drop in ms, never "+107100.0 pts"
        self.assertEqual(cli._goal_delta(st, dict(delta=1071.0, lo=1012.0, hi=1169.0)), "-1071 ms [-1169 ms, -1012 ms]")
        self.assertEqual(cli._goal_op(dict(st, scale="binary", metric=None)), ">=")

    def test_throughput_carries_tok_s(self):
        self.assertEqual(self.fmt(dict(kpi="tokens_per_second_c1"), 322.0), "322 tok/s")


if __name__ == "__main__":
    unittest.main()
