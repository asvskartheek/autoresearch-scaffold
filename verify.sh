#!/usr/bin/env bash
# Rerunnable proof for papers and goals: unit + route tests, the lint on both examples, a CLI round trip
# (publish -> comment over HTTP -> poll -> reply -> @agent on a resolved thread), and goals across two projects
# served by one dashboard, all against throwaway projects.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; export PYTHONPATH="$here"
export ARX_HOME="$(mktemp -d)"  # the projects registry; never the real ~/.arx
echo "== unit and route tests"; python3 -m unittest discover -s "$here/tests" 2>&1 | tail -3
d="$(mktemp -d)"; trap 'kill $srv 2>/dev/null || true; rm -rf "$d"' EXIT
cd "$d"; python3 -m autoresearch init --no-serve . >/dev/null 2>&1; rm -rf autoresearch
echo "== arx paper check on the example (expect 0 errors)"; python3 -m autoresearch paper check --file "$here/examples/papers/gsm8k-percent-base.html"
echo "== arx paper check on a bare page (expect errors, exit 1)"; echo '<p>81% better</p>' > bad.html
if python3 -m autoresearch paper check --file bad.html >/dev/null; then echo FAIL; exit 1; else echo "ok: rejected"; fi
python3 -m autoresearch paper new demo --file demo.html >/dev/null
python3 -m autoresearch paper add demo --hill demo --file demo.html >/dev/null
port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
python3 -m autoresearch serve --port "$port" >/dev/null 2>&1 & srv=$!; sleep 1
api="http://127.0.0.1:$port/api/paper/demo"
cid=$(curl -sf "$api/comment" -H 'Content-Type: application/json' -d '{"body":"What n?","author":"Ann","anchor":{"block":"now-1","quote":"The goal"}}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
echo "== poll sees the comment"; python3 -m autoresearch paper poll demo --timeout 3 | grep -q "$cid" && echo "ok: $cid"
python3 -m autoresearch paper reply demo "$cid" "full, n = 1319" --link "§5=#now-1"
curl -sf "$api/resolve" -H 'Content-Type: application/json' -d "{\"parent\":\"$cid\",\"author\":\"Ann\"}" >/dev/null
curl -sf "$api/reply" -H 'Content-Type: application/json' -d "{\"parent\":\"$cid\",\"author\":\"Ann\",\"body\":\"@agent one more check?\"}" >/dev/null
echo "== @agent on a resolved thread pages the agent with the whole thread"
python3 -m autoresearch paper poll demo --timeout 3 | python3 -c 'import json,sys;t=json.loads(sys.stdin.readline());assert t["mention"] and len(t["messages"])==3,t;print("ok:",len(t["messages"]),"messages")'
echo "== cross-site POST and rebound Host are refused"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$api/comment" -H 'Origin: https://evil.com' -d '{}')" = 403 ] && echo "ok: origin"
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/state" -H 'Host: evil.com')" = 403 ] && echo "ok: host"
echo "== goals: open, status, refuse, achieve, goal paper check"
python3 - <<'PY'
from autoresearch.core import Project, Task
p = Project("."); p.add_dataset("ds", list(range(10))); p.add_model("base", status="champion")
t = Task(p, "eval", "base on full", model="base", slice="ds/full")
for i in range(10): t.add_row(dict(id=str(i), score=float(i < 7)))
t.finish()
PY
python3 -m autoresearch goal open g90 --title "90% on full" --slice full --target 0.9 >/dev/null
python3 -m autoresearch hill open h --title H --target full --goal g90 >/dev/null
python3 -m autoresearch goal status g90 | grep -q "70.0%" && echo "ok: status 70.0% of 90.0%"
if python3 -m autoresearch goal achieve g90 2>/dev/null; then echo FAIL; exit 1; else echo "ok: achieve refused below target"; fi
python3 -m autoresearch paper new --goal g90 --file g90.html >/dev/null
if python3 -m autoresearch paper check --goal g90 --file g90.html >/dev/null; then echo FAIL; exit 1; else echo "ok: unedited goal template rejected for this goal"; fi
echo "== the goal example passes the goal check against its own ledger numbers"
python3 - "$here/examples/papers/gsm8k-96.html" <<'PY'
import sys; from autoresearch import papers
st = dict(status="open", slice="gsm8k-test/full", n=1319, kpi="score", target=0.96, value=1224/1319, model="m",
          baseline="qwen3-4b-rl-fresh-v1", vs_baseline=dict(delta=0.0523, lo=0.0379, hi=0.0667), hills={"percent-base": "climbed"})
errs = [m for lv, m in papers.check_goal(open(sys.argv[1]).read(), st, ["percent-base"]) if lv == "error"]
assert not errs, errs; print("ok: 0 errors")
PY
echo "== one dashboard, two projects"
d2="$(mktemp -d)"; (cd "$d2" && python3 -m autoresearch init --no-serve --name second . >/dev/null 2>&1 && rm -rf autoresearch)
key=$(python3 -c 'import sys;from autoresearch.projects import key_for;print(key_for(sys.argv[1]))' "$d2")
[ "$(curl -sf "http://127.0.0.1:$port/p/$key/api/state" | python3 -c 'import json,sys;print(json.load(sys.stdin)["config"]["name"])')" = second ] || { echo FAIL; exit 1; }
echo "ok: /p/$key/ serves the second project"
curl -sf "http://127.0.0.1:$port/api/projects" | python3 -c 'import json,sys;ps=json.load(sys.stdin);assert len(ps)>=2,ps;print("ok:",len(ps),"projects listed")'
curl -sf "http://127.0.0.1:$port/api/state" | python3 -c 'import json,sys;g=json.load(sys.stdin)["goals"]["g90"];assert g["hills"]=={"h":"open"},g;print("ok: goal g90 with hill h")'
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/p/nope/api/state")" = 404 ] || { echo FAIL; exit 1; }
echo "ok: unregistered key is 404"
rm -rf "$d2"
echo "ALL PASSED"
