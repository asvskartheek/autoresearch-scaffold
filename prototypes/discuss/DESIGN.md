# Comments summon agents, and sharing

## Today
A comment is a `comment` event in `.research/papers/<name>/thread.jsonl`. `threads()` marks it `waiting`; nothing
reads that until some agent happens to run `arx paper poll`, which blocks, marks it `seen` ("thinking…") and hands
the thread to that one agent, who answers serially with `arx paper reply`. No agent polling means no answer: the
22-hour wait. One agent polling means questions queue behind each other.

## `arx answer`: a daemon started by `arx up`
- `arx up` starts `arx answer` next to the dashboard (same pidfile pattern, one per registered project; `arx answer
  --status` and the topbar pill show `running/cap` and the queue). Off switch: `research.json` `"answer": false`.
- Loop: the same fold as `poll` (`pending()` over every paper and story), but non-blocking: every waiting thread
  without a live worker gets one. Waiting already covers follow-ups and `@agent` on resolved threads.
- One worker = one headless `claude -p` subprocess per thread, in parallel, capped (`--max-agents`, default 4).
  Over the cap, threads queue FIFO and the card says "waiting for a slot". A thread never has two workers; a new
  message while one runs is picked up when it ends (it re-reads the thread).
- Each worker is an arx task (`kind=answer`, `parent` none, `agent="answer #k"`), so it shows on the Workbench as one
  atomic job with elapsed time and a budget (`budget_s` 300 default). Steps it takes are `t.note`s; the page streams
  them as the "read hill… / ran paired diff…" lines. Stalled or over budget: the task fails and the thread gets a
  visible "couldn't answer: <reason>" reply instead of silence.

## What each worker gets
- System prompt: AGENTS.md + PROTOCOL.md § Reporting (every number names slice and n, paired deltas, CI), plus
  "answer in at most 3 sentences; include a figure when the answer is a comparison".
- The question: the thread (all messages), the anchor (frame/block id, quoted text, or figure region resolved to data:
  model ids, problem ids, step range), and the frame's figure spec.
- Read-only ledger tools: an `arx` allowlist (`arx state --json`, `arx hill show`, `arx diff A B --slice S`,
  `arx task show`, per-id rows). No write commands except `arx paper reply|attach` for its own thread. Working dir is
  the project; `--allowedTools` enforces it. No client text leaves `.research/` (rows stay aggregate-safe).
- It must not start training or evals. If the answer needs a new run, it replies with the proposed run and a
  "Run it" button that opens a normal task, so cost is a human decision.

## How answers post back
- `arx paper reply <name> <thread> "text" --file fig.html` already exists: the figure is attached under `files/` and
  linked from the reply. Add `--fig fig.svg` to inline a small SVG in the message (sanitised: no script).
- Live steps: the worker appends `progress` events (`{kind: "progress", parent, body: "ran paired diff"}`) to
  thread.jsonl; the page already re-reads the log, so steps stream with no new transport.
- Out-of-order arrival is natural: each worker posts when done; the page orders threads by anchor, not by answer time.

## Sharing
| option | how | collaborators | cost |
|---|---|---|---|
| static snapshot | `arx story export` writes one HTML with data inlined | view only, no live agents | none; mail it |
| tunnel | `arx up --share` runs cloudflared/tailscale funnel to the local dashboard | live, comments summon agents | laptop must stay on; auth is ours to get right |
| hosted page | `arx story publish` uploads the story + a read-only ledger extract to a hosted page (e.g. a claude.ai artifact or HF Space) | live comments synced back to thread.jsonl; agents run locally | needs a sync service |

Recommendation: ship the static snapshot first (it is just the story page with data inlined, and it is what people
forward). Then the hosted page as the real collaboration path: comments land in a hosted store, `arx answer` pulls
them into thread.jsonl like local comments, so agents still run on the researcher's machine with the ledger.
Skip the tunnel except as a dev convenience: exposing a local dashboard that can spawn agents is the wrong default.
Access is per link (no access / view / comment) plus named invites; only "comment" can summon agents, and the owner
sees each question's cost on its task card.
