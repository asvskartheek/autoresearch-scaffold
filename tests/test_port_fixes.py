"""Fixes found while porting real projects: legacy continuous slices, units of unpaired gate checks, pooled error
shares, CLI links and labels. Run: PYTHONPATH=. python3 -m unittest discover -s tests"""
import io, json, os, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import core
from autoresearch.core import Project, Task


def project(ladder=None, **cfg):
    d = Path(tempfile.mkdtemp()) / "bench"
    d.mkdir()
    ladder = ladder or [dict(rung="dev", checks=[dict(slice="lat/n6", rule="not_worse", tolerance=0.05)])]
    (d / "research.json").write_text(json.dumps(dict(name="bench", higher_is_better=True, ladder=ladder, **cfg)))
    return Project(d)


def legacy_slice(p, name="lat/n6", n=6):
    """A continuous slice frozen before `scale` existed: no scale, no unit in slices.json."""
    p.add_slice(name, [f"x{i}" for i in range(n)], kind="synthetic")
    data = json.loads((p.dir / "slices.json").read_text())
    data[name].pop("scale", None)
    (p.dir / "slices.json").write_text(json.dumps(data))
    return name


def run(p, model, sl, scores, errors=(), contract=None):
    t = Task(p, "eval", f"{model} on {sl}", model=model, slice=sl,
             config=dict(baseline_contract=contract) if contract else None)
    for i, s in enumerate(scores):
        row = dict(id=f"x{i}", score=0.0 if i in errors else s)
        if i in errors:
            row["error"] = "timeout"
        t.add_row(row)
    t.finish()
    return t


class LegacyContinuousScale(unittest.TestCase):
    def test_errored_row_is_left_out_on_a_legacy_continuous_slice(self):
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [-2.5] * 6, errors={0})
        self.assertIsNone(p._slice_field(sl, "scale"))
        self.assertEqual(p.slice_scale(sl), "continuous")
        self.assertTrue(p.is_continuous(sl))
        sc = p.pooled_scores("v0", sl)
        self.assertEqual(len(sc), 5)  # the errored row is not a perfect 0 seconds
        self.assertAlmostEqual(sum(sc.values()) / len(sc), -2.5)

    def test_server_state_and_learn_agree_with_core(self):
        from autoresearch import learn, server
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [-2.5] * 6, errors={0})
        st = server._state(p)
        self.assertEqual(st["slices"][sl]["scale"], "continuous")
        self.assertAlmostEqual(st["leaderboard"][sl]["v0"]["score"], -2.5)
        self.assertTrue(learn._cont(p, sl))

    def test_binary_legacy_slice_stays_binary(self):
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [1, 0, 1, 1, 0, 1])
        self.assertEqual(p.slice_scale(sl), "binary")


class SharedDashboardScale(unittest.TestCase):
    def test_learn_sees_a_slice_edit_on_a_long_lived_project(self):
        from autoresearch import learn
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        run(p, "v0", sl, [1, 0, 1, 1, 0, 1])
        self.assertFalse(learn._cont(p, sl))  # cached on this Project, as the shared dashboard keeps it
        data = json.loads((p.dir / "slices.json").read_text())
        data[sl].update(scale="continuous", unit="s", metric="minus seconds")
        (p.dir / "slices.json").write_text(json.dumps(data, indent=2))
        self.assertTrue(learn._cont(p, sl))
        self.assertEqual(learn._unit(p, sl), "s")

    def test_first_run_decides_a_legacy_slice_on_a_long_lived_project(self):
        from autoresearch import learn
        p = project()
        sl = legacy_slice(p)
        p.add_model("v0", status="champion")
        self.assertFalse(learn._cont(p, sl))  # no run yet
        run(p, "v0", sl, [-2.5] * 6)
        self.assertTrue(learn._cont(p, sl))


if __name__ == "__main__":
    unittest.main()
