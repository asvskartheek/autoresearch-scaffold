#!/usr/bin/env bash
# Rerunnable proof for the papers feature: unit + route tests, the lint on the example, and a CLI round trip
# (publish -> comment over HTTP -> poll -> reply -> @agent on a resolved thread) against a throwaway project.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; export PYTHONPATH="$here"
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
echo "ALL PASSED"
