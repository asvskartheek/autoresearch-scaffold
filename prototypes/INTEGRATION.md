# Round 2: build the prototypes into arx itself

The user tried the round-1 prototypes (`prototypes/*/index.html`, brief in `prototypes/BRIEF.md`) and said: "overall very
good attempt, I'm excited to see how you create something combining all this and show me a real project". Their
pinned comments, now acted on: too much text (cut words, show visuals); no PAPER (a complete, visual, shareable
document of the champion); drawing comments must be Lavish-level; answers must visibly be right or wrong. The metric
that matters most to them: **how fast and how well they understand the project**. Their real projects are gsm8k-ft and
a hard client P&ID project. You may read the P&ID project locally, but never copy its content into the repo, tests or
commits.

## How the code is split (read this first)

- `autoresearch/features.py` is the plug-in layer: register `GET`/`POST` routes, `STATE` keys, `CLI` commands and inbox
  `PROMPTS` from **your own module**. server.py and cli.py already call these hooks. Do not edit server.py, cli.py,
  index.html or core.js's ROUTES/ICON (already wired) unless your section says so.
- The **inbox** (`features.enqueue/update/inbox/pending`) is how a person asks for agent work. `arx answer` (stream A)
  runs one headless agent per queued item.
- New nav routes already exist: `#questions` (views/questions.js) and `#learn` (views/learn.js, nav label "Brief").
  `charts.js`, `comments.js`, `comments.css` are loaded on every page.
- Look and feel: the dashboard's own design system (`web/app.css`, the helpers at the top of `web/core.js`). Reuse
  `page()`, `panel()`, `pill()`, `empty()`. AGENTS.md UI rule: no taglines, helper text or secondary labels.
- Python stays stdlib-only. Add tests in `tests/test_<feature>.py`. `uv run --with pytest python -m pytest -q tests` must pass.
- Dev dashboard on this branch: http://127.0.0.1:8960/ (already running; Python changes need a restart:
  `pkill -f "autoresearch serve --port 8960"` and then start `PYTHONPATH=. python3 -m autoresearch serve --port 8960`
  in the background from the repo root). Real projects: `/p/gsm8k-ft/`, `/p/qwen-throughput/`,
  and the other registered projects. It reads their ledgers, so **do not write into a real project's
  `.research/`** except through the feature you build, and clean up any test data you add there. Prefer a scratch
  project: `PYTHONPATH=. python3 -m autoresearch init scratch/<you> --no-serve`.
- Browser: the user is looking at the main tab. Open your own tab (`tabs_create`) and close it when done.
- Do not commit. Do not touch another stream's files. Finish with a 6-line report: what works end to end, what is
  stubbed, what you verified and how.

## Streams and the files each owns

**A. Comments everywhere + agents that answer.** Owns: `autoresearch/comments.py`, `autoresearch/answer.py` (new),
`web/comments.js`, `web/comments.css`, tests. May add the `arx answer` launch to `cmd_up` in cli.py (one line).
- Port `prototypes/comment.js` (pins, threads, select text, and the box/arrow/pen/highlight drawing another agent is
  adding now) into the dashboard. Anchors include the route (`location.hash`), so comments stay on their view. Storage:
  `.research/comments.jsonl`, through feature routes `/api/comments`. Author names come from a "Set your name" prompt
  kept in localStorage. Pins re-place after each dashboard re-render (core.js calls `S.afterRender` hooks).
- Every new comment enqueues an inbox item `kind="comment"`. `arx answer` (also started in the background by `arx up`)
  watches the inbox **and** paper threads waiting for the agent (`papers.pending`). For each one it launches
  `features.agent_cmd()` with the prompt from `PROMPTS[kind]`, cwd = project root, at most 4 at once, each inside its
  own arx task (kind `answer`, budget 15 min) so it shows on the Workbench.
- The agent posts back with `arx comment reply <id> "..."` (add this command). A failure or timeout posts a reply that
  says so. In the thread UI show a live "agent working" state with the latest task note.
- The comment prompt gives the agent: the comment, the anchor (route, element text, quote, shape), PROTOCOL.md's
  reporting rules, read-only ledger access, and the instruction to answer visually where it can (reply bodies may
  contain a small inline SVG; sanitise on render: allow only svg/path/rect/circle/line/text/g/polyline).
- Commenting must work on every view, including the Workbench, which re-renders every 4 s.

**B. Workbench vital signs + charts.** Owns: `web/charts.js`, `web/views/workbench.js/.css`, `web/views/task.js/.css`,
`autoresearch/vitals.py`, plus `lineChart`/`spark` in core.js (replace their bodies with charts.js calls), plus
`Task` in core.py for system sampling.
- Port `prototypes/charts/` into `charts.js`: smoothing over a faint raw trace, log-y, overlay with a legend you can
  toggle, crosshair with exact values, synced small multiples, drag-zoom, 1-2-5 ticks. Use it in the task view and the
  workbench.
- Port `prototypes/workbench/` onto the real data. Atomic jobs only. Each long job's card has 2–4 live panels chosen by
  kind and by which metrics it logs, an ETA re-estimated from a recent rate window, and the ETA's history (vitals.py
  computes it server-side and adds it via `STATE` or the task route). Stalled jobs float to the top with the fix
  command. Short jobs are rows.
- System vitals: while a `Task` is open, a background thread samples `nvidia-smi` (when present; it is skipped
  silently otherwise) every 15 s and logs `gpu_util`, `gpu_mem_gb`, `gpu_mem_total_gb` into metrics with a `sys`
  marker. Turn it off with `ARX_SAMPLE=0`. It must never crash or slow a task.

**C. Questions.** Owns: `autoresearch/questions.py`, `web/views/questions.js/.css`, tests.
- Ledger `.research/questions.json`: id → {title (≤ 6 words), parent, status open|answered|dead|agent, claim (one line),
  evidence: [{model, slice}|{task}], needs_human: bool, created, by}.
- CLI: `arx q add "<title>" [--parent id] [--needs-human]`, `arx q answer <id> "<claim>" --evidence model:slice ...`,
  `arx q dead <id> "<claim>"`, `arx q list`. Python: `project.question(...)` is optional; the CLI is enough.
- Seed the tree from the ledger when it is empty: the root is each goal, its children are the hills, and each
  rejected or promoted model is an answered or dead child of its hill, with the model's `change`/reason as the claim
  and its gate runs as evidence. Seeded nodes are derived on read, not written, until someone edits them.
- View: port `prototypes/questions/` as it is now (minimal text, claims on hover, evidence as paired-delta dots with CI
  and fixed/broke squares from the leaderboard and gates). "Ask" or "Branch" from any node, or from selected text on
  any view (a small chip), creates a question with status `agent` and enqueues inbox `kind="question"` with a prompt
  (`PROMPTS["question"]`) telling the agent to investigate with read-only ledger access and answer through
  `arx q answer`. Questions marked needs_human show at the top as one amber count.

**D. Brief (learn).** Owns: `autoresearch/learn.py`, `web/views/learn.js/.css`, tests.
- Port `prototypes/learn/`, including the fixes: a clear ✓/✗ verdict, shuffled options, no option that gives the
  answer away. "Since you last looked": the server builds the cards from the decisions, finished evals, rejections,
  new hills and answered questions since a `since` timestamp (the client keeps last-seen in localStorage). Each card is
  predict-then-reveal from real paired deltas.
- Predictions persist in the ledger: `.research/predictions.jsonl` via POST (viewer name, card id, guess, confidence,
  truth, hit). Calibration (hits, Brier score, a calibration chart) is computed from that file. A prediction about a
  run that has not finished yet is "open" and resolves when the run lands.
- Understanding telemetry: `.research/understanding.jsonl` takes events from the Brief and from explainers (stream E's
  kit posts here too): {viewer, doc, step, ms, check, ok, replays, alt_used}. Show "how well you know this project" on
  the Brief: a calibration score, time to catch up and the concepts you missed. Concept cards come from the project's
  own vocabulary (paired delta, gate ladder, CI crossing zero, plus one per hill built from its symptom/example).

**E. Paper (complete reference) + explainer kit.** Owns: `autoresearch/reference.py`, `web/reference.html` (new),
`web/explain-kit.js` (new), tests. May add one "Paper" link in `web/views/model.js` and `web/views/goals.js`
(coordinate: just a link).
- `/reference/<model>` (default: the champion), generated entirely from the ledger, for any project: port
  `prototypes/paper/` (being built now; read it when it lands, and until then use the user's spec). It is complete and
  visual: the system (model `change` lineage), slices, results on every slice with paired deltas and CIs, the gate
  ladder, a fixed/broke grid, a failure gallery from hill examples, lineage with rejected siblings and reasons, cost
  and latency, what is unknown or not run, and how to reproduce. It has a sticky outline, deep links and evidence
  popovers, and it is shareable: "Download" builds one self-contained HTML (data inlined), print CSS works, and
  "Copy link" works per section.
- `explain-kit.js`: the measurement and medium toolkit from `prototypes/story/` (the predict gate, "see it another
  way", the active-time timer with pause, the summary, telemetry POSTed to D's understanding endpoint
  `/api/understanding`). An agent-written explainer (a paper with `kind: explainer` in its meta) includes it with
  `<script src="/explain-kit.js">`. Document the kit's API at the top of the file in about 30 lines.

**F. Goal intake.** Owns: `autoresearch/intake.py`, `web/views/goals.js/.css`, tests.
- Port `prototypes/goals/`. A "New goal" box on the Goals view: the user pastes the ask in their own words. The
  server enqueues inbox `kind="goal"`. `PROMPTS["goal"]` tells the agent to read the ledger, then write a proposal
  (`arx goal propose <item> --json '{...}'`, add it): up to 3 one-tap clarifying questions, a goal card (KPI, slice,
  target as "≥ X of N", where we are now, constraints), and related goals (guards, held-out robustness, hill
  sub-goals). The UI shows the proposal, lets you answer the questions (the answers re-enqueue the item) and edit
  fields, and "Open goal" calls the existing goal-open code.
- The goals view shows distance in units ("43 more of 1,319"), never a bare percentage, and goals as a small map of
  main goal, guards and sub-goals. Add `--parent` and `--role main|guard|sub` to goals (in intake.py through a CLI
  hook, or a minimal change in core.py's goal code; say which you chose).
