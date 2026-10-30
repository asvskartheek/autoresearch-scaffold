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
