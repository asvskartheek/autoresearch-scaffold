# arx prototype round 1: shared brief

The user (an ML researcher) has used arx for a few days and finds it inefficient. Their complaints, in their words:

- Research is often not hill-climbing but discovery: asking a question, which branches into a tree of sub-questions,
  many of which come up while reading and understanding a paper.
- Papers are horrible. They want visual storytelling of the research, graspable in minutes. Possibly no prose at all.
- "I do not think I'm learning enough or well enough. I feel very lost." Agents work in parallel at agent speed; the
  human must learn at human speed well enough to solve what agents cannot. They are falling behind.
- Workbench visibility is bad. It should show only atomic tasks. They want continuous progress like tqdm, much larger.
- Goals always show percentages, which feels stupid.
- Papers have no parallel agents answering questions and comments, no share feature, no collaboration.
- Loss curves look horrible.

## What using the hardest real project (a client document-reading agent) showed

(Do not copy any of that project's content into prototypes; it is client data. Use it only as a picture of the failure.)

- Cold load is a blank dark frame for ~3 s.
- Identity is unreadable: the champion's name is ten plus-joined abbreviations. 19
  models on full, 14 candidates, 29 slices shown as a pill wall. Nothing gives a candidate a human name or a picture.
- Overview answers "what is the state of the ledger", never "what do we now know". 629 archived tasks are a flat log.
- Hill "share of failures" percentages sum to well over 100% (two duplicate hills both say 43.7%). The champion shows
  "not run" on all six open hills, so no hill tells you where the current system stands.
- The user's own comment on the champion paper: "where do we get all these green layer from. You wrote text there,
  you should visually explain." Sent to the agent and still unanswered 22 hours later. Two papers have waiting
  comments nobody answered. This is the comments-summon-agents problem in one line.
- A paper about a *visual* reading agent shows no drawing, no example of a right vs wrong answer, no trace of what the
  agent looked at. The most useful figure (one failing example, what the agent saw, what it said, what was right) is
  missing. Evidence should be examples you can see, not only aggregates.

## Product decisions already taken (build to these)

1. **Questions, not just hills.** The unit of research is a question tree. A hill is one kind of question
   ("can we raise score on slice X?"). A question is open, answered (with a one-line claim + the evidence that
   settles it), or a dead end. Sub-questions branch off anything: a node, a figure, a sentence while reading.
2. **Stories, not papers.** A story is a sequence of frames. Each frame = one figure + one caption of at most 20
   words. No paragraphs anywhere. Every number is clickable to its evidence.
3. **The human learns by predicting.** Before a result is revealed, the human guesses. Calibration over time is the
   measure of whether they understand the project. A daily brief shows only what changed since they last looked.
4. **Workbench = atomic jobs only**, each a large live progress bar (tqdm philosophy: count, rate, ETA, elapsed),
   no nested trees, no umbrella cards.
5. **Goals show distance in units**, e.g. "34 more problems of 1,319" and a trajectory over time, never "92.8% / 96%".
6. **Comments summon agents.** Every question asked on a story/paper fans out to its own agent; answers stream back in
   parallel. Stories can be shared by link with named collaborators.
7. **Charts done properly**: smoothed line over a faint raw trace, log-y toggle, overlay runs, hover crosshair with
   exact values, sensible ticks, no chartjunk.

## Rules for every prototype

- One self-contained `prototypes/<name>/index.html` (inline CSS + JS, vanilla, inline SVG for charts; no build step,
  no CDN needed). It is served by `python3 prototypes/serve.py` from the repo root at `http://127.0.0.1:8940/<name>/`.
- Use **real data** from `prototypes/data/` (fetch it with a relative URL like `../data/gsm8k-ft-state.json`):
  - `gsm8k-ft-state.json`, `qwen-throughput-state.json`: full dashboard state (keys: config, champion, datasets,
    slices, hills, models, papers, gates, tasks, leaderboard, goals, baseline, decisions). Tasks have id, kind,
    title, description, status, created, ended, progress {done,total}, note {t,msg}, parent, model, slice.
  - `hill-<name>.json`: hill detail. `tasks/<id>.json`: {task, metrics:[{t,step,loss,...}], events}. Training runs
    with loss: 1026-011325-train-d155, 1026-012433-train-1304, 1026-015519-train-2f1c (193 points, many metrics),
    1026-033035-train-45b9, 1026-043538-train-2130.
  - `paper.html`: the current gsm8k-96 goal paper (the thing the user calls horrible). Read it to see what fails.
  Where a concept does not exist in the ledger yet (questions, predictions, comments), derive plausible content from
  the real ledger (hills, model `change` fields, notes, decisions) and mark it as derived in a small `data-proto` note
  in the code, not in the UI.
- Look and feel: match arx's current design system. Read `autoresearch/web/app.css` and `autoresearch/ui.css` for the
  tokens (colours, type, radii) and copy the ones you use. Light and dark (`prefers-color-scheme`). Works at 375px.
- AGENTS.md UI rule: cut taglines, helper text and secondary labels. Minimal words. Show, don't tell.
- Interactive enough that the user can actually try it for 2 minutes and form an opinion. Simulate live updates
  where the idea depends on them (setInterval), clearly fed from the real data's shape.
- Verify it renders: run `python3 prototypes/serve.py &` (it may already be running on 8940; if the port is taken,
  just use it), and load your page with the browser tools if you have them, or at least `curl` it and check the JS
  with `node --check` on the extracted script. Fix console errors.
- Do not touch files outside `prototypes/<name>/`. Do not commit.
- Finish with a 5-line report: what the prototype shows, the one decision it tests, and 2 questions to ask the user.
