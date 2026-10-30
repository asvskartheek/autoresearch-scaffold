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
    cli(proj, "pattern", "add", "units", "--name", "Unit Slips", "--items-file", "sym.txt", "--set", "sym", "--cause", "Converts units wrongly", "--count", "10", "--of", "40")
    cli(proj, "cand", "add", "base", "--name", "Plain Prompt", "--change", "The starting prompt.")
    cli(proj, "promote", "base", "--reason", "Seeded as the starting champion.")
    evaluate("base", "sym", lambda i: {"score": float(int(i) % 2 == 0)}, project=Project(proj), workers=4)
    cli(proj, "hill", "open", "units", "--name", "Unit Slips", "--goal", "acc", "--pattern", "units", "--symptom", "Converts units wrongly",
        "--symptom-set", "sym", "--eval-sets", "hill", "--train-sets", "train", "--control", "ctl")
    ladder = [{"name": "Hill target", "set": "@hill.eval", "rule": "improve"}, {"name": "Hill control", "set": "@hill.control", "rule": "hold", "tol": 0.05},
              {"name": "Full set", "set": "all", "rule": "improve"}]
    (proj / "ladder.json").write_text(json.dumps(ladder))
    cli(proj, "ladder", "ladder.json")
    r = cli(proj, "cand", "add", "units-v1", "--name", "Unit Check", "--hill", "units", "--change", "Ask the model to restate units.", "--predict", "+20 pts on the hill target")
    assert "warning" not in r.stdout

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
            "--eval-sets", "all", "--no-evidence", "overlap check only", ok=False)
    assert r.returncode == 1 and "share items" in r.stdout


def _goal_and_champion(proj, fails_on_sym=True):
    cli(proj, "goal", "open", "acc", "--name", "Accuracy 80", "--vague", "x", "--set", "all", "--target", "0.8")
    cli(proj, "cand", "add", "base", "--name", "Plain Prompt", "--change", "x")
    cli(proj, "promote", "base", "--reason", "seed")
    evaluate("base", "sym", lambda i: {"score": 0.0 if fails_on_sym and int(i) < 3 else 1.0}, project=Project(proj), workers=2)


HILL = ["hill", "open", "units", "--name", "Unit Slips", "--goal", "acc", "--symptom", "x", "--eval-sets", "hill"]


def test_hill_with_failing_symptom_set_is_evidenced(proj):
    _goal_and_champion(proj)
    cli(proj, *HILL, "--symptom-set", "sym")
    e = Views(Project(proj)).hill_evidence("units")
    assert e["ok"] and e["items"] == 10 and e["failing"] == 3 and e["missing"] == []
    assert build_state(Project(proj))["evidence"]["units"]["ok"]
    assert "hills_without_evidence" not in cli(proj).stdout


def test_hill_open_refuses_without_symptom_set(proj):
    _goal_and_champion(proj)
    r = cli(proj, *HILL, ok=False)
    assert r.returncode == 1 and "no symptom set" in r.stdout and "fix:" in r.stdout and "--no-evidence" in r.stdout
    assert "units" not in Project(proj).state()["hills"]


def test_hill_open_refuses_when_the_champion_passes_the_symptom_set(proj):
    _goal_and_champion(proj, fails_on_sym=False)
    r = cli(proj, *HILL, "--symptom-set", "sym", ok=False)
    assert r.returncode == 1 and "no champion run shows these items failing" in r.stdout


def test_hill_open_refuses_before_the_champion_ran_the_symptom_set(proj):
    cli(proj, "goal", "open", "acc", "--name", "Accuracy 80", "--vague", "x", "--set", "all", "--target", "0.8")
    r = cli(proj, *HILL, "--symptom-set", "sym", ok=False)
    assert r.returncode == 1 and "no champion run covers these items" in r.stdout


def test_waived_hill_opens_and_shows_its_reason(proj):
    _goal_and_champion(proj)
    cli(proj, *HILL, "--no-evidence", "Latency target; no item is wrong yet")
    p = Project(proj)
    assert p.state()["hills"]["units"]["evidence_waived"] == "Latency target; no item is wrong yet"
    e = Views(p).hill_evidence("units")
    assert not e["ok"] and e["waived"] and e["missing"]
    assert "hills_without_evidence" not in cli(proj).stdout
    assert "warning" not in cli(proj, "cand", "add", "u1", "--name", "Unit Check", "--hill", "units", "--change", "x").stdout


def test_old_hill_without_evidence_is_flagged_with_reasons(proj):
    # Old ledgers are not rewritten: a hill event with no symptom set, an empty pattern and an example with no item.
    _goal_and_champion(proj)
    p = Project(proj)
    p.append("pattern", key="pat", name="Unit Slips", cause="x", items=[], count=4, of=183)
    p.append("hill", key="old", name="Old Hill", goal="acc", pattern="pat", symptom="x", eval_sets=["hill"],
             example={"input": "q", "wrong": "a", "right": "b", "why": "c"})
    e = Views(p).hill_evidence("old")
    assert not e["ok"] and not e["waived"]
    assert e["missing"] == ["no symptom set", "pattern lists no items", "the example names no item"]
    home = cli(proj).stdout
    assert "hills_without_evidence[1]" in home and "old,Old Hill,no symptom set" in home and "arx2 set add old-symptom" in home
    r = cli(proj, "cand", "add", "o1", "--name", "Old Fix", "--hill", "old", "--change", "x")
    assert "warning: hill old has no evidence" in r.stdout


def test_example_item_counts_as_evidence(proj):
    _goal_and_champion(proj)
    p = Project(proj)
    p.append("hill", key="ex", name="Example Hill", goal="acc", symptom="x", eval_sets=["hill"],
             example={"item": "1", "input": "q", "wrong": "a", "right": "b", "why": "c"})
    assert Views(p).hill_evidence("ex")["ok"]


def test_pattern_count_must_be_backed_by_ids(proj):
    r = cli(proj, "pattern", "add", "p1", "--name", "Unit Slips", "--items", "3", "--cause", "x", "--count", "10", "--of", "40", ok=False)
    assert r.returncode == 1 and "only 1 items listed" in r.stdout and "fix:" in r.stdout
    (proj / "ghost.txt").write_text("\n".join(f"g{i}" for i in range(10)))
    r = cli(proj, "pattern", "add", "p2", "--name", "Unit Slips", "--items-file", "ghost.txt", "--cause", "x", "--count", "10", ok=False)
    assert r.returncode == 1 and "no frozen set" in r.stdout
    r = cli(proj, "pattern", "add", "p3", "--name", "Unit Slips", "--cause", "x", ok=False)
    assert r.returncode == 1 and "needs the items" in r.stdout
    cli(proj, "pattern", "add", "p4", "--name", "Unit Slips", "--items-file", "sym.txt", "--set", "sym", "--cause", "x", "--count", "10", "--of", "40")
    assert Project(proj).state()["patterns"]["p4"]["count"] == 10


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


def test_ask_cli_poll_answer_list(proj):
    from arx2 import asks
    p = Project(proj)
    assert "noop" in cli(proj, "ask", "poll", "--timeout", "0.5").stdout
    cli(proj, "cand", "add", "a", "--name", "First Try", "--change", "Shorter prompt")
    q = asks.ask(p, "What does this cell mean?", "candidate", "a", "ladder cell: First Try × Full set", route="ladder")
    out = cli(proj, "ask", "poll", "--timeout", "5", "--agent", "t").stdout
    assert q["key"] in out and "clicked: ladder cell" in out and "change: Shorter prompt" in out and "arx2 ask answer" in out
    assert p.state()["asks"][q["key"]]["status"] == "claimed"
    (proj / "d.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>')
    bad = cli(proj, "ask", "answer", q["key"], "--link", "javascript:alert(1)", ok=False)
    assert bad.returncode == 1 and "fix:" in bad.stdout
    cli(proj, "ask", "answer", q["key"], "--text", "Item 7 failed.", "--file", "d.svg", "--link", "Hill=#/hill/units", "--text", "Overall 3 of 30.")
    parts = p.state()["asks"][q["key"]]["answers"][0]["parts"]
    assert [x["type"] for x in parts] == ["md", "svg", "link", "md"]  # order kept across flags
    assert "answered" in cli(proj, "ask", "list", "--all").stdout


def test_ask_watch_runs_an_agent_per_question(proj):
    import time as _t
    from arx2 import asks
    p = Project(proj)
    q = asks.ask(p, "Why?", "project", "toy", "sentence: x")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "ARX2_HOME": str(proj / ".home")}
    agent = f'{sys.executable} -m arx2.cli ask answer "$ARX2_ASK" --text "$(head -1 "$ARX2_ASK_FILE")"'
    w = subprocess.Popen([sys.executable, "-m", "arx2.cli", "ask", "watch", "--exec", agent], cwd=proj, env=env,
                         stdout=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            if p.state()["asks"][q["key"]]["status"] == "answered":
                break
            _t.sleep(0.1)
    finally:
        w.kill()
    a = p.state()["asks"][q["key"]]
    assert a["status"] == "answered" and a["answers"][0]["parts"][0]["body"] == f"ask: {q['key']}"


def test_dashboard_asks_and_saves_over_http(proj, monkeypatch):
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from arx2 import asks, server, store
    monkeypatch.setattr(store, "HOME", proj / ".home")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}/api/p/toy-math"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            return {"status": e.code, **json.load(e)}

    try:
        key = post("/ask", {"text": "What is this square?", "kind": "set", "key": "all", "what": "item square: 7", "route": "set/all"})["key"]
        assert post("/save", {"ask": key, "as": "note", "name": "Square Seven"})["status"] == 400  # no answer yet
        p = Project(proj)
        (proj / "x.html").write_text("<p>explorable</p>")
        asks.answer(p, key, [("text", "Item 7 passed."), ("file", str(proj / "x.html"))])
        st = json.load(urllib.request.urlopen(base + "/state"))
        a = st["asks"][key]
        assert a["status"] == "answered" and a["what"] == "item square: 7"
        f = a["answers"][0]["parts"][1]["file"]
        served = urllib.request.urlopen(f"{base}/answer/{f}").read()
        assert served.endswith(b"<p>explorable</p>") and b"/static/app.css" in served  # follows the dashboard theme
        assert post("/save", {"ask": key, "as": "note", "name": "three words here"})["status"] == 400
        assert post("/save", {"ask": key, "as": "note", "name": "Square Seven"})["key"] == f"note-{key}"
        st = json.load(urllib.request.urlopen(base + "/state"))
        assert st["docs"][f"note-{key}"]["about"] == "all" and st["asks"][key]["saved"][0]["as"] == "note"
        assert b"srcdoc" in urllib.request.urlopen(f"{base}/doc/note-{key}").read()
    finally:
        srv.shutdown()


def test_follow_ups_keep_the_thread_and_its_agent(proj):
    from arx2 import asks
    p = Project(proj)
    q = asks.ask(p, "Why is item 7 wrong?", "set", "all", "item square: 7")
    p.append("ask.claim", key=q["key"], agent="a1")
    asks.answer(p, q["key"], [("text", "It names the wrong sheet.")], agent="a1")
    asks.reply(p, q["key"], "Which sheet should it name?")
    a = p.state()["asks"][q["key"]]
    assert a["status"] == "open" and [x["who"] for x in a["thread"]] == ["person", "agent", "person"]
    assert asks.next_open(p.state(), agent="a2") is None  # a1 holds the context and is still around
    out = cli(proj, "ask", "poll", "--timeout", "3", "--agent", "a1").stdout
    assert "question: Which sheet should it name? (follow-up)" in out and "agent: It names the wrong sheet." in out
    asks.answer(p, q["key"], [("text", "Sheet 002.")], agent="a1")
    asks.save(p, q["key"], "note", "Sheet Choice")
    page = (p.dir / "docs" / f"note-{q['key']}.html").read_text()
    assert "Which sheet should it name?" in page and "Sheet 002." in page
    assert "turns" in cli(proj, "ask", "list", "--all").stdout


def test_watch_gives_each_question_its_own_agent(proj):
    import time as _t
    from arx2 import asks
    p = Project(proj)
    qs = [asks.ask(p, f"Question {i}?", "project", "toy", "sentence: x") for i in range(2)]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "ARX2_HOME": str(proj / ".home")}
    agent = f'sleep 1; {sys.executable} -m arx2.cli ask answer "$ARX2_ASK" --text "turn $ARX2_ASK_TURN in $ARX2_ASK_SESSION"'
    w = subprocess.Popen([sys.executable, "-m", "arx2.cli", "ask", "watch", "--exec", agent, "--jobs", "2"], cwd=proj, env=env,
                         stdout=subprocess.DEVNULL)

    def wait(pred):
        for _ in range(100):
            if pred():
                return True
            _t.sleep(0.1)

    try:
        t0 = _t.time()
        assert wait(lambda: all(p.state()["asks"][q["key"]]["status"] == "answered" for q in qs))
        assert _t.time() - t0 < 2.6  # both ran at once, not one after the other
        s = p.state()
        owners = {asks.owner(s["asks"][q["key"]]) for q in qs}
        assert owners == {f"watch/{q['key']}" for q in qs}
        first = s["asks"][qs[0]["key"]]["answers"][0]["parts"][0]["body"]
        asks.reply(p, qs[0]["key"], "And then?")
        assert wait(lambda: len(p.state()["asks"][qs[0]["key"]]["answers"]) == 2)
        a = p.state()["asks"][qs[0]["key"]]
        again = a["answers"][1]["parts"][0]["body"]
        assert again.startswith("turn 2") and again.split(" in ")[1] == first.split(" in ")[1]  # same session resumes
        assert asks.owner(a) == f"watch/{qs[0]['key']}"
    finally:
        w.kill()


def test_texty_answers_are_refused(proj):
    from arx2 import asks
    q = asks.ask(Project(proj), "Why?", "project", "toy", "x")
    r = cli(proj, "ask", "answer", q["key"], "--text", " ".join(["word"] * 70), ok=False)
    assert r.returncode == 1 and "at most 60" in r.stdout and "fix:" in r.stdout
    r = cli(proj, "ask", "answer", q["key"], "--text", " ".join(["word"] * 40), ok=False)
    assert "no figure" in r.stdout
    (proj / "f.svg").write_text("<svg/>")
    cli(proj, "ask", "answer", q["key"], "--file", "f.svg", "--text", " ".join(["word"] * 40))


# ---- the paper gate ----------------------------------------------------------

def climbed(proj):
    """The toy project after one promotion: champion at 65% on All 100, goal 80% not met."""
    cli(proj, "goal", "open", "acc", "--name", "Accuracy 80", "--vague", "Get better at maths", "--set", "all", "--target", "0.8")
    cli(proj, "hill", "open", "units", "--name", "Unit Slips", "--goal", "acc", "--symptom", "Converts units wrongly",
        "--symptom-set", "sym", "--eval-sets", "hill", "--train-sets", "train", "--control", "ctl",
        "--no-evidence", "Paper tests need a hill, not its evidence.")
    (proj / "ladder.json").write_text(json.dumps([{"name": "Full set", "set": "all", "rule": "improve"}]))
    cli(proj, "ladder", "ladder.json")  # promote refuses a candidate that has not passed a ladder
    cli(proj, "cand", "add", "base", "--name", "Plain Prompt", "--change", "The starting prompt.")
    cli(proj, "promote", "base", "--reason", "Seeded.")
    cli(proj, "cand", "add", "v1", "--name", "Unit Check", "--hill", "units", "--change", "Restate units.")
    p = Project(proj)
    for model, good in [("base", lambda i: int(i) % 2 == 0), ("v1", lambda i: int(i) % 2 == 0 or 10 <= int(i) < 40)]:
        for s in ["hill", "all"]:
            evaluate(model, s, lambda i, g=good: {"score": float(g(i))}, project=p, workers=4)
    cli(proj, "promote", "v1", "--reason", "Passed every step.")
    return p


def filled(proj, about, audience):
    cli(proj, "paper", "new", "pp", "--about", about, "--audience", audience, "--out", "pp.html", "--force")
    page = (proj / "pp.html").read_text()
    return page.replace("TODO", "Written")


def test_long_abstract_fails(proj):
    climbed(proj)
    page = filled(proj, "acc", "external").replace("Written: the task and why it matters, in one sentence.",
                                                   " ".join(["word"] * 200) + ".")
    r = paper_check(proj, page, "acc", ok=False)
    assert r.returncode == 1 and "Abstract has 2" in r.stdout and "cut to 80 words" in r.stdout


def paper_check(proj, page, about, audience="external", ok=True):
    (proj / "p.html").write_text(page)
    return cli(proj, "paper", "check", "p.html", "--about", about, "--audience", audience, ok=ok)


def test_paper_skeleton_passes_once_filled(proj):
    climbed(proj)
    cli(proj, "paper", "new", "pp", "--about", "acc", "--out", "pp.html")
    raw = (proj / "pp.html").read_text()
    assert 'data-claim="score"' in raw and "65.0%" in raw and "+15.0 pts" in raw and "Draft" in raw
    assert paper_check(proj, raw, "acc", ok=False).returncode == 1  # TODOs left
    out = paper_check(proj, filled(proj, "acc", "external"), "acc").stdout
    assert "0 errors, 0 warnings" in out
    cli(proj, "doc", "add", "pp", "--kind", "paper", "--name", "Accuracy Paper", "--file", "p.html", "--about", "acc",
        "--audience", "external")
    assert Project(proj).state()["docs"]["pp"]["draft"] is False
    assert "0 errors" in paper_check(proj, filled(proj, "units", "internal"), "units", "internal").stdout


def test_paper_with_a_wrong_number_fails_naming_the_claim(proj):
    climbed(proj)
    page = filled(proj, "acc", "external").replace(">65.0%<", ">70.0%<", 1)
    r = paper_check(proj, page, "acc", ok=False)
    assert r.returncode == 1 and "score claim '70.0%'" in r.stdout and "65.0%" in r.stdout
    bare = filled(proj, "acc", "external").replace("<p>The champion scores", "<p>About 64% of answers were right. The champion scores", 1)
    assert "not claims: 64%" in paper_check(proj, bare, "acc", ok=False).stdout
    (proj / "p.html").write_text(page)
    r = cli(proj, "doc", "add", "pp", "--kind", "paper", "--name", "Accuracy Paper", "--file", "p.html", "--about", "acc",
            "--audience", "external", ok=False)
    assert r.returncode == 1 and "refused" in r.stdout and "pp" not in Project(proj).state()["docs"]


def test_paper_with_an_external_script_fails(proj):
    climbed(proj)
    page = filled(proj, "acc", "external").replace("</head>", '<script src="https://cdn.example.com/x.js"></script></head>')
    r = paper_check(proj, page, "acc", ok=False)
    assert r.returncode == 1 and "https://cdn.example.com/x.js" in r.stdout and "fix:" in r.stdout


def test_paper_claiming_an_unmet_goal_achieved_fails(proj):
    climbed(proj)
    page = filled(proj, "acc", "external").replace("Written: what the reader should take away.", "We achieved the goal.")
    r = paper_check(proj, page, "acc", ok=False)
    assert r.returncode == 1 and "says achieved" in r.stdout
    undrafted = filled(proj, "acc", "external").replace("Draft: ", "").replace(" This is a draft: the goal is not met yet.", "")
    assert "does not say draft" in paper_check(proj, undrafted, "acc", ok=False).stdout


def test_draft_papers_pass_only_when_titled_draft(proj):
    climbed(proj)
    page = filled(proj, "acc", "external")
    cut = page[:page.index('<section data-part="threats">')] + "</body></html>"
    (proj / "d.html").write_text(cut)
    args = ["doc", "add", "dd", "--kind", "paper", "--name", "Early Draft", "--file", "d.html", "--about", "acc", "--audience", "external"]
    assert cli(proj, *args, ok=False).returncode == 1
    cli(proj, *args, "--draft")
    assert Project(proj).state()["docs"]["dd"]["draft"] is True
    (proj / "d.html").write_text(cut.replace("Draft: ", "").replace("This is a draft", "This is early"))
    r = cli(proj, *args, "--draft", ok=False)
    assert r.returncode == 1 and "Draft in the <title>" in r.stdout


# ---- arx2 verify ------------------------------------------------------------------

def _climbed(proj, promote=True):
    """A small honest project: a seeded champion, an evidenced hill, a ladder, and a candidate that passes it."""
    cli(proj, "goal", "open", "acc", "--name", "Accuracy 80", "--vague", "x", "--set", "all", "--target", "0.8")
    cli(proj, "pattern", "add", "units", "--name", "Unit Slips", "--items-file", "sym.txt", "--set", "sym", "--cause", "x", "--count", "10", "--of", "40")
    cli(proj, "cand", "add", "base", "--name", "Plain Prompt", "--change", "x")
    cli(proj, "promote", "base", "--reason", "seed")
    p = Project(proj)
    evaluate("base", "sym", lambda i: {"score": float(int(i) % 2 == 0)}, project=p, workers=2)
    cli(proj, "hill", "open", "units", "--name", "Unit Slips", "--goal", "acc", "--pattern", "units", "--symptom", "x",
        "--symptom-set", "sym", "--eval-sets", "hill", "--control", "ctl")
    (proj / "ladder.json").write_text(json.dumps([{"name": "Hill target", "set": "@hill.eval", "rule": "improve"},
                                                  {"name": "Hill control", "set": "@hill.control", "rule": "hold", "tol": 0.05}]))
    cli(proj, "ladder", "ladder.json")
    cli(proj, "cand", "add", "fix", "--name", "Unit Check", "--hill", "units", "--change", "x", "--predict", "+50 pts on the hill target")
    for model, good in [("base", lambda i: int(i) % 2 == 0), ("fix", lambda i: True)]:
        for s in ["hill", "ctl"]:
            evaluate(model, s, lambda i, g=good: {"score": float(g(i))}, project=p, workers=2)
    if promote:
        cli(proj, "promote", "fix", "--reason", "passed both rungs")
    return p


def _errors(p, check=None):
    from arx2 import verify
    return [f for f in verify.audit(p, check) if f["level"] == "error"]


def test_clean_ledger_verifies(proj):
    p = _climbed(proj)
    assert _errors(p) == []
    r = cli(proj, "verify")
    assert r.returncode == 0 and r.stdout.startswith("verify: 0 errors")
    assert build_state(p)["audit"]["errors"] == 0
    assert "verify: 0 errors" in cli(proj).stdout


def test_broken_run_is_caught(proj):
    p = _climbed(proj)

    def boom(i):
        raise RuntimeError("harness down")
    evaluate("fix", "all", boom, project=p, workers=2)  # a complete run, every row an error
    errs = _errors(p, "broken_runs")
    assert len(errs) == 1 and "100 of 100 rows are errors" in errs[0]["what"] and errs[0]["entity"].startswith("run:")
    r = cli(proj, "verify", ok=False)
    assert r.returncode == 1 and "fix: run:" in r.stdout


def test_promotion_with_a_failing_rung_is_caught(proj):
    p = _climbed(proj, promote=False)
    cli(proj, "cand", "add", "worse", "--name", "Worse Try", "--hill", "units", "--change", "x", "--predict", "+10 pts")
    for s in ["hill", "ctl"]:
        evaluate("worse", s, lambda i: {"score": 0.0}, project=p, workers=2)
    r = cli(proj, "promote", "worse", "--reason", "trust me", ok=False)  # the CLI refuses
    assert r.returncode == 1 and "cannot be promoted" in r.stdout and "Hill target fail" in r.stdout
    p.append("champion", key="worse", reason="by hand", previous="base")  # an old ledger that skipped the gate
    errs = _errors(p, "promotions")
    assert len(errs) == 1 and errs[0]["entity"] == "candidate:worse" and "Hill target fail" in errs[0]["what"]


def test_prevalence_without_ids_is_caught(proj):
    p = _climbed(proj)
    p.append("pattern", key="ghost", name="Ghost Count", cause="x", items=[], count=4, of=183)  # before pattern add refused this
    errs = _errors(p, "prevalence")
    assert len(errs) == 1 and errs[0]["entity"] == "pattern:ghost" and "lists only 0 item ids" in errs[0]["what"]


def test_flakiness_needs_same_model_repeats(proj):
    p = _climbed(proj)
    p.append("pattern", key="flaky", name="Flaky Answers", cause="right on one run, wrong on the next", items=[], count=0)
    errs = _errors(p, "flakiness")
    assert len(errs) == 1 and "no model has two complete runs" in errs[0]["what"]
    evaluate("fix", "hill", lambda i: {"score": float(int(i) % 3 != 0)}, project=p, workers=2)  # a second run of one model
    assert _errors(p, "flakiness") == []


def test_init_writes_the_rules(proj):
    rules = (proj / ".arx2" / "RULES.md").read_text()
    assert "Prevalence is backed by ids" in rules and "arx2 verify" in rules
    assert cli(proj, "rules").stdout == rules


WEB = ROOT / "arx2" / "web"


def _ui_prose(src, limit=12):
    """Text runs in UI code that read as prose and run past `limit` words.

    Every string literal, and the text between tags anywhere in the file, is split at its block tags (inline tags are
    dropped); a ${...} counts as one word. A run is code, not prose, when it holds braces, arrows, operators, calls or property access.
    """
    import re
    lits = re.findall(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', src)
    lits += re.findall(r">([^<>`]+)<", src)
    out = set()
    for lit in lits:
        lit = re.sub(r"</?(?:b|i|a|em|strong|span|code)\b[^<>]*>", " ", lit.strip("\"'`"))  # inline tags join a sentence
        for run in re.split(r"<[^>]*>", lit):
            text = re.sub(r"\$\{[^{}]*\}", " X ", run)
            if re.search(r"[<>{}]|=>|&&|\|\||==|\?\.|\w\.\w|\w\(|;\s*$|\\n", text):
                continue
            words = [w for w in text.split() if re.search(r"[A-Za-z]", w)]
            if len(words) > limit:
                out.add(" ".join(words))
    return sorted(out)


def test_dashboard_text_stays_short():
    bad = []
    for f in ["pages.js", "ui.js", "index.html"]:
        src = (WEB / f).read_text()
        bad += [f"{f}: {t}" for t in _ui_prose(src)]
        bad += [f"{f}: {c}" for c in ('class="sub"', 'class="hint"') if c in src]
    assert not bad, "UI prose over 12 words (use a label, a figure or a title attribute):\n" + "\n".join(bad)


def test_directive_is_stored_with_its_anchor(proj):
    from arx2 import asks
    p = Project(proj)
    d = asks.ask(p, "@orchestrator create a new goal to hill climb on dev41", "set", "all", "item square: 7",
                 route="set/all", loc="0.2.1")
    a = p.state()["asks"][d["key"]]
    assert a["to"] == "orchestrator" and a["text"] == "create a new goal to hill climb on dev41"
    assert (a["kind"], a["entity"], a["what"], a["route"], a["loc"], a["status"]) == ("set", "all", "item square: 7", "set/all", "0.2.1", "open")
    with pytest.raises(LedgerError):
        asks.ask(p, "@orchestrator  ", "set", "all", "x")
    assert "to" not in asks.ask(p, "Why is @orchestrator here?", "set", "all", "x")  # only a leading mention directs
    assert "to" not in asks.ask(p, "@orchestrator@or", "set", "all", "x")  # the mention is a whole word


def test_ask_poll_skips_directives_and_orchestrator_poll_gets_them(proj):
    from arx2 import asks
    p = Project(proj)
    d = asks.ask(p, "@orchestrator rerun the dev set", "set", "all", "item square: 7", route="set/all")
    assert asks.next_open(p.state()) is None
    assert "noop" in cli(proj, "ask", "poll", "--timeout", "0.5").stdout
    assert d["key"] not in cli(proj, "ask", "list", "--all").stdout
    q = asks.ask(p, "What is this?", "set", "all", "item square: 8")
    out = cli(proj, "ask", "poll", "--timeout", "2", "--agent", "t").stdout
    assert q["key"] in out and d["key"] not in out
    out = cli(proj, "orchestrator", "poll", "--timeout", "5").stdout
    assert f"directive: {d['key']}" in out and "rerun the dev set" in out and "clicked: item square: 7" in out
    assert "arx2 orchestrator ack" in out and p.state()["asks"][d["key"]]["status"] == "claimed"
    assert "noop" in cli(proj, "orchestrator", "poll", "--timeout", "0.5").stdout  # claimed: not handed out twice


def test_ack_closes_a_directive_and_a_follow_up_reopens_it(proj):
    from arx2 import asks
    p = Project(proj)
    d = asks.ask(p, "@orchestrator open a goal on dev41", "project", "toy", "heading “Goals”")
    assert d["key"] in cli(proj, "orchestrator", "list").stdout
    assert "directives: 1 open" in cli(proj).stdout  # the home screen points at it
    cli(proj, "orchestrator", "ack", d["key"], "--text", "Opened goal dev41.")
    a = p.state()["asks"][d["key"]]
    assert a["status"] == "answered" and a["thread"][-1]["parts"][0]["body"] == "Opened goal dev41."
    assert d["key"] not in cli(proj, "orchestrator", "list").stdout
    assert "noop" in cli(proj, "orchestrator", "poll", "--timeout", "0.5").stdout
    asks.reply(p, d["key"], "@orchestrator target 0.9 please")
    a = p.state()["asks"][d["key"]]
    assert a["status"] == "open" and a["thread"][-1]["text"] == "target 0.9 please"
    assert asks.next_open(p.state(), agent="orchestrator", to="orchestrator")["key"] == d["key"] and asks.next_open(p.state()) is None
    q = asks.ask(p, "Why?", "set", "all", "item square: 7", route="set/all", loc="1.2")
    e = asks.reply(p, q["key"], "@orchestrator fix this one")  # under a question: a new directive on the same anchor
    n = p.state()["asks"][e["key"]]
    assert e["key"] != q["key"] and n["to"] == "orchestrator" and n["after"] == q["key"] and (n["loc"], n["what"]) == ("1.2", "item square: 7")
    q2 = asks.ask(p, "Not a directive", "set", "all", "x")
    with pytest.raises(LedgerError):
        asks.ack(p, q2["key"], "done")
