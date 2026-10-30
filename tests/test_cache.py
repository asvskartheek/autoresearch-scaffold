import json, tempfile, unittest
from pathlib import Path

from autoresearch.core import Project, _jsonl, _read


class ReadCache(unittest.TestCase):
    def test_rewrite_is_seen_and_copies_are_independent(self):
        p = Path(tempfile.mkdtemp()) / "x.json"
        p.write_text(json.dumps({"a": [1]}))
        first = _read(p)
        first["a"].append(2)  # mutating a result must not touch the cache
        self.assertEqual(_read(p), {"a": [1]})
        p.write_text(json.dumps({"a": [1, 2, 3]}))
        self.assertEqual(_read(p), {"a": [1, 2, 3]})

    def test_jsonl_append_is_seen(self):
        p = Path(tempfile.mkdtemp()) / "r.jsonl"
        p.write_text('{"id": 1}\n')
        self.assertEqual(len(_jsonl(p)), 1)
        with p.open("a") as f:
            f.write('{"id": 2}\n')
        self.assertEqual([r["id"] for r in _jsonl(p)], [1, 2])

    def test_slice_lookups_follow_a_refrozen_slice_without_copying_its_ids(self):
        root = Path(tempfile.mkdtemp())
        (root / ".research").mkdir()
        p = Project(root)
        p._save("slices", {"d/s": {"hash": "h1", "ids": list(range(5000))}})
        self.assertEqual(p._slice_field("d/s", "hash"), "h1")
        self.assertFalse(p.is_continuous("d/s"))
        p._save("slices", {"d/s": {"hash": "h2", "scale": "continuous", "ids": [1]}})
        self.assertEqual(p._slice_field("d/s", "hash"), "h2")
        self.assertTrue(p.is_continuous("d/s"))
        self.assertIsNone(p._slice_field("d/missing", "hash"))


if __name__ == "__main__":
    unittest.main()
