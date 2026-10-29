"""Questions view text: goals in their slice's units, readable model labels, seeded titles that read as questions."""
import json, os, tempfile, unittest
from pathlib import Path

os.environ["ARX_HOME"] = tempfile.mkdtemp()  # never touch the real ~/.arx
from autoresearch import questions as q
from autoresearch.core import Project, Task


def ledger():
    d = Path(tempfile.mkdtemp()) / "qunits"
    d.mkdir()
    (d / "research.json").write_text(json.dumps(dict(name="qunits", higher_is_better=True, ladder=[])))
    p = Project(d)
    p.add_dataset("ds", list(range(20)))
    return p


def run(p, model, scores, slice="ds/full", latency=None):
    t = Task(p, "eval", f"{model} on {slice}", model=model, slice=slice)
    for i, s in enumerate(scores):
        t.add_row(dict(id=p.slice(slice)["ids"][i], score=s, latency_s=latency))
    t.finish()
    return t


class GoalUnits(unittest.TestCase):
    def test_continuous_negated_goal_reads_in_ms(self):
        p = ledger()
        p.add_slice("ds/cold", list(range(4)), scale="continuous", unit="ms", metric="minus ms to first paint")
        p.add_model("v0", parent="", status="champion", title="Launcher as shipped")
        run(p, "v0", [-1400, -1500, -1450, -1482], "ds/cold")
        p.open_goal("fast", "Home appears in under a second", "ds/cold", -1000.0)
        t = q.tree(p)
        g = t["goals"]["fast"]
        self.assertEqual((g["value_txt"], g["target_txt"], g["gap_txt"]), ("1,458 ms", "at most 1,000 ms", "458 ms to go"))
        claim = {n["id"]: n for n in t["nodes"]}["g:fast"]["claim"]
        self.assertEqual(claim, "Launcher as shipped: 1,458 ms; target at most 1,000 ms.")

    def test_latency_kpi_reads_in_seconds_and_met_has_no_gap(self):
        p = ledger()
        p.add_model("base", parent="", status="champion")
        run(p, "base", [1] * 20, latency=13.0)
        p.open_goal("lat", "P&ID median latency at 45 s", "full", 45.0, kpi="latency_p50")
        g = q.tree(p)["goals"]["lat"]
        self.assertEqual((g["value_txt"], g["target_txt"]), ("13 s", "at most 45 s"))
        self.assertNotIn("gap_txt", g)

    def test_count_goal_reads_as_count_with_percent_in_brackets(self):
        p = ledger()
        p.add_model("base", parent="", status="champion")
        run(p, "base", [1] * 14 + [0] * 6)
        p.open_goal("ninety", "GSM8K at 90%", "full", 0.9)
        g = q.tree(p)["goals"]["ninety"]
        self.assertEqual((g["value_txt"], g["target_txt"], g["gap_txt"]), ("14 of 20", "18 of 20 (90%)", "4 more of 20"))


class GoalTitles(unittest.TestCase):
    def t(self, title, target=0.9, kpi="score", hib=True, n=None, sl=None):
        return q._goal_title(dict(title=title, target=target, kpi=kpi, higher_is_better=hib, n=n), "k", sl)

    def test_every_real_goal_title_reads_as_a_question(self):
        ms = dict(scale="continuous", unit="ms", metric="minus ms to paint")
        cases = [
            (self.t("GSM8K at 96%", 0.96, n=1319), "Can we get GSM8K to 1,267 of 1,319 (96%)?"),
            (self.t("P&ID accuracy at 84%", 0.84, n=183), "Can we get P&ID accuracy to 154 of 183 (84%)?"),
            (self.t("P&ID median latency at 45 s", 45, "latency_p50", False), "Can we get P&ID median latency under 45 s?"),
            (self.t("Median under 10 s", 10, "latency_p50", False), "Can we get the median under 10 s?"),
            (self.t("Keep 1,224 correct", 0.928, n=1319), "Can we keep 1,224 correct?"),
            (self.t("No open review findings", 0, hib=False, sl=dict(scale="continuous", unit="findings")),
             "Can we get to zero open review findings?"),
            (self.t("Single-sequence vLLM throughput +3%", 322, "tokens_per_second_c1"),
             "Can we get the single-sequence vLLM throughput to 322 tok/s (+3%)?"),
            (self.t("Home appears in under a second", -1000, sl=ms), "Can we make Home appear in under a second?"),
            (self.t("The projector behaves like plain Android", 1.0, n=13),
             "Can we make the projector behave like plain Android?"),
        ]
        for got, want in cases:
            self.assertEqual(got, want)


class ModelTitles(unittest.TestCase):
    def test_titles_reruns_and_sibling_collisions(self):
        p = ledger()
        p.add_slice("ds/hard", list(range(10)))
        p.add_model("po4", parent="", status="champion")
        p.open_hill("count", "Counting", "ds/hard")
        p.add_model("po4+inv", parent="po4", hill="count")
        p.add_model("po4+inv+trace", parent="po4+inv", status="candidate")
        p.add_model("po4+inv+count", parent="po4+inv", hill="count")
        p.add_model("po4+inv+trace+count", parent="po4+inv+trace", hill="count")
        p.add_model("po4+inv.r4", parent="po4+inv", hill="count")
        p.add_model("sft-v1", parent="po4", hill="count", title="Percentage SFT · 1 epoch · 1e-6")
        p.add_model("twin-a", parent="po4", hill="count", title="Same idea")
        p.add_model("twin-b", parent="po4", hill="count", title="Same idea")
        t = {k: n["title"] for k, n in q.tree(p, full=False)["byid"].items()}
        self.assertEqual(t["m:po4+inv+count"], "Does +count help on po4+inv?")
        self.assertEqual(t["m:po4+inv+trace+count"], "Does +count help on po4+inv+trace?")
        self.assertEqual(t["m:po4+inv.r4"], "Does po4+inv hold on rerun 4?")
        self.assertEqual(t["m:sft-v1"], "Does Percentage SFT · 1 epoch · 1e-6 help?")
        self.assertEqual((t["m:twin-a"], t["m:twin-b"]), ("Does twin-a help?", "Does twin-b help?"))


class ReadPane(unittest.TestCase):
    def test_answer_agent_notes_show_and_other_branches_do_not(self):
        from autoresearch import features
        p = ledger()
        p.add_model("base", parent="", status="champion")
        p.open_goal("g1", "Ninety", "full", 0.9)
        p.open_hill("h1", "Hard ones", "ds/full", goal="g1")
        p.open_hill("h2", "Other ones", "ds/full", goal="g1")
        other = Task(p, "eval", "h2 lesson building", description="work on h2")
        other.note("A long note about the other hill h2 and its lesson building from days ago.")
        other.finish()
        qq = q.ask(p, "Why do hard ones fail?", parent="h:h1")
        agent = Task(p, "answer", "Answer the question")
        agent.note("Read the hard slice: units are lost in step two.")
        agent.finish()
        features.update(p, qq["inbox"], task=agent.id)
        texts = [n["text"] for n in q.notes(p, qq["id"])]
        self.assertTrue(any("units are lost" in x for x in texts), texts)
        self.assertFalse(any("lesson building" in x for x in texts), texts)


if __name__ == "__main__":
    unittest.main()
