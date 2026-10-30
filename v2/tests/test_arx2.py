"""End-to-end checks: a project built only through the CLI and API, read back through the views and server."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arx2 import stats  # noqa: E402
from arx2.api import evaluate  # noqa: E402
from arx2.server import build_state  # noqa: E402
from arx2.store import LedgerError, Project, check_name, ids_hash  # noqa: E402
from arx2.view import Views  # noqa: E402


def cli(cwd, *args, ok=True):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "ARX2_HOME": str(Path(cwd) / ".home")}
    r = subprocess.run([sys.executable, "-m", "arx2.cli", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setenv("ARX2_HOME", str(tmp_path / ".home"))
    cli(tmp_path, "init", "--name", "Toy Math", "--task", "Answer grade-school maths questions.", "--measure", "Exact answer")
    ids = [str(i) for i in range(100)]
    (tmp_path / "all.txt").write_text("\n".join(ids))
    (tmp_path / "sym.txt").write_text("\n".join(ids[:10]))
    (tmp_path / "hill.txt").write_text("\n".join(ids[10:40]))
    (tmp_path / "train.txt").write_text("\n".join(ids[40:60]))
    (tmp_path / "ctl.txt").write_text("\n".join(ids[60:80]))
    for key, name, role, f in [("all", "All 100", "full", "all"), ("sym", "Unit Slips", "symptom", "sym"),
                               ("hill", "Unit Targets", "hill", "hill"), ("train", "Unit Training", "train", "train"),
                               ("ctl", "Plain Control", "control", "ctl")]:
        cli(tmp_path, "set", "add", key, "--name", name, "--dataset", "toy", "--role", role, "--ids-file", f"{f}.txt")
    return tmp_path


def test_names_must_be_two_plain_words():
    assert check_name("Route Tracing") == "Route Tracing"
    for bad in ["po4+inv+cat", "three word name", "web/v1", ""]:
        with pytest.raises(LedgerError):
            check_name(bad)


def test_fingerprint_is_order_free():
    assert ids_hash(["2", "1"]) == ids_hash(["1", "2"])


def test_tiny_samples_stay_unsure():
    base = [{"id": i, "score": 0} for i in range(3)]
    cand = [{"id": i, "score": 1} for i in range(3)]
    c = stats.paired(base, cand)
    assert c["delta"] == 1.0 and c["lo"] < 0.5  # three wins out of three is not "solid"
    big = stats.paired([{"id": i, "score": 0} for i in range(200)], [{"id": i, "score": int(i < 60)} for i in range(200)])
    assert big["lo"] > 0.2


def test_errors_count_as_zero():
    s = stats.summarize([{"id": 1, "score": 1, "error": "timeout"}, {"id": 2, "score": 1}])
    assert s["score"] == 0.5 and s["errors"] == 1


def test_frozen_sets_refuse_edits(proj):
    (proj / "x.txt").write_text("1\n2")
    r = cli(proj, "set", "add", "all", "--name", "All 100", "--dataset", "toy", "--role", "full", "--ids-file", "x.txt", ok=False)
    assert r.returncode == 1 and "frozen" in r.stdout and "fix:" in r.stdout


def test_full_loop(proj):
    cli(proj, "goal", "open", "acc", "--name", "Accuracy 80", "--vague", "Get better at maths", "--set", "all", "--target", "0.8")
    cli(proj, "annotate", "3", "Answer in metres when cm were asked", "--set", "sym")
    cli(proj, "pattern", "add", "units", "--name", "Unit Slips", "--items", "3", "--cause", "Converts units wrongly", "--count", "10", "--of", "40")
    cli(proj, "hill", "open", "units", "--name", "Unit Slips", "--goal", "acc", "--pattern", "units", "--symptom", "Converts units wrongly",
        "--symptom-set", "sym", "--eval-sets", "hill", "--train-sets", "train", "--control", "ctl")
    ladder = [{"name": "Hill target", "set": "@hill.eval", "rule": "improve"}, {"name": "Hill control", "set": "@hill.control", "rule": "hold", "tol": 0.05},
              {"name": "Full set", "set": "all", "rule": "improve"}]
    (proj / "ladder.json").write_text(json.dumps(ladder))
    cli(proj, "ladder", "ladder.json")
    cli(proj, "cand", "add", "base", "--name", "Plain Prompt", "--change", "The starting prompt.")
    cli(proj, "promote", "base", "--reason", "Seeded as the starting champion.")
    cli(proj, "cand", "add", "units-v1", "--name", "Unit Check", "--hill", "units", "--change", "Ask the model to restate units.", "--predict", "+20 pts on the hill target")

    p = Project(proj)
    for model, good in [("base", lambda i: int(i) % 2 == 0), ("units-v1", lambda i: int(i) % 2 == 0 or 10 <= int(i) < 40)]:
        for s in ["hill", "ctl", "all"]:
            out = evaluate(model, s, lambda i, g=good: {"score": float(g(i)), "cost": 0.01}, project=p, workers=4)
            assert out["n"] == p.state()["sets"][s]["n"]

    v = Views(p)
    steps = {r["name"]: r["v"]["state"] for r in v.climb("units-v1")}
    assert steps == {"Hill target": "pass", "Hill control": "pass", "Full set": "pass"}
    assert v.split_check()["ok"]
    r = cli(proj, "gate", "units-v1")
    assert "promote" in r.stdout
    cli(proj, "promote", "units-v1", "--reason", "Passed every step.")
    assert "noop" in cli(proj, "promote", "units-v1", "--reason", "again").stdout  # idempotent
    st = build_state(p)
    assert st["champion"] == "units-v1" and st["goals"]["acc"]["track"]["current"] == 0.65
    assert all(t["status"] == "done" for t in st["tasks"].values())
    assert st["learner"]["n_cards"] >= 4


def test_overlap_is_caught(proj):
    cli(proj, "goal", "open", "acc", "--name", "Accuracy 80", "--vague", "x", "--set", "all", "--target", "0.8")
    r = cli(proj, "hill", "open", "bad", "--name", "Leaky Hill", "--goal", "acc", "--symptom", "x", "--symptom-set", "sym",
            "--eval-sets", "all", ok=False)
    assert r.returncode == 1 and "share items" in r.stdout


def test_replay_shows_the_past(proj):
    p = Project(proj)
    cli(proj, "cand", "add", "a", "--name", "First Try", "--change", "x")
    t_mid = p.events()[-1]["t"]
    cli(proj, "cand", "add", "b", "--name", "Second Try", "--change", "y")
    assert set(p.state(until=t_mid)["candidates"]) == {"a"}


def test_ask_answer_save_folds(proj):
    from arx2 import asks
    p = Project(proj)
    cli(proj, "cand", "add", "a", "--name", "First Try", "--change", "x")
    q = asks.ask(p, "Why did it fail here?", "candidate", "a", "ladder cell: First Try × Hill target", route="ladder", loc="[data-ask]")
    s = p.state()
    assert s["asks"][q["key"]]["status"] == "open" and asks.next_open(s)["key"] == q["key"]
    p.append("ask.claim", key=q["key"], agent="t")
    assert asks.next_open(p.state()) is None  # a fresh claim hides it from other agents
    with pytest.raises(LedgerError):
        asks.save(p, q["key"], "note", "Why Failed")  # nothing to save before an answer
    asks.answer(p, q["key"], [("text", "One item: **3**.\n\n- then the aggregate")])
    a = p.state()["asks"][q["key"]]
    assert a["status"] == "answered" and a["answers"][0]["parts"][0]["type"] == "md"
    asks.save(p, q["key"], "note", "Why Failed")
    asks.save(p, q["key"], "card", "")
    s = p.state()
    doc = s["docs"][f"note-{q['key']}"]
    assert doc["about"] == "a" and doc["kind"] == "note" and doc["ask"] == q["key"]
    assert "<b>3</b>" in (p.dir / "docs" / doc["file"]).read_text()
    assert s["cards"][f"ask-{q['key']}"]["front"] == "Why did it fail here?"
    assert [x["as"] for x in s["asks"][q["key"]]["saved"]] == ["note", "card"]
