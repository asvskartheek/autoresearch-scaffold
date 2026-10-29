"""Compact result metadata for archive discovery without inflating task lists."""
import unittest
from autoresearch.server import _slim

class ResultSummaries(unittest.TestCase):
    def test_conclusion_preserved_as_compact_line(self):
        source = dict(summary=dict(benchmark_report=dict(conclusion="A"*700, scope="Offline batches")))
        row = _slim(source)
        self.assertEqual(row["result_summary"], "A"*600)
        self.assertEqual(row["summary"], {})
        self.assertEqual(source["summary"]["benchmark_report"]["scope"], "Offline batches")

    def test_throughput_count_and_malformed_report(self):
        row = _slim(dict(summary=dict(benchmark_report="legacy", throughput=[{},{}], score=.8)))
        self.assertEqual(row["result_summary"], "2 measured throughput rows")
        self.assertEqual(row["summary"], dict(score=.8))
