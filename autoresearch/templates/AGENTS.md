# Agent rules for this research project

Read `PROTOCOL.md` before changing a model, an eval or a slice. `research.json` holds the project's datasets,
gate ladder and KPIs. `.research/` is the ledger; the dashboard (`arx serve`) reads only that.

## Step 0: the dashboard, before anything else
- `arx up` (also run by `arx init`) starts the dashboard in the background. Check it is up before doing other work,
  and give the user the URL. If it goes down, `arx up` again.
- Setup is work too: `arx init` opens a running "Project setup" task. Note every step on it (environment, installs,
  model download, dataset prep) and finish it when the first eval can run.

## Every piece of work is visible
- Open the task *before* starting the work, not after. No step is too small: installs, downloads, data prep,
  error analysis, slice building, evals, training.
- A task is a single job with a clear end. The project's goal, a hill or a candidate is not a task: those are
  tracked in `research.json`, hills and models. Never open one task to cover the whole effort and hang other
  work under it.
- Anything that runs longer than a minute is a task: `arx.task(...)` in Python or `arx task start` from a shell.
  It shows as a Workbench card while it runs and moves to the Archive when it ends. Never run unlogged work.
- Log as you go: `t.log(step=..., loss=...)` for curves, `t.note("...")` for decisions, `t.link("HF dataset", url)`
  for anything stored elsewhere. Write the task's description so the card makes sense to someone who missed the chat.
- Subagents get their own task (pass `agent="<subagent name>"`). One candidate per subagent / worktree.
- Sub-work nests under the task that started it: tasks opened while another runs in the same process, or in a
  process launched from it (`$ARX_PARENT`), become its sub-tasks. From another process pass `parent=<id>` /
  `arx task start --parent <id>`. Keep each card's latest note current; it is the line people read.
- Long jobs: visible progress, bulk/concurrent calls, a wall-clock deadline. A stalled task (no heartbeat for
  10 minutes) shows red; fix or fail it, never leave it.

## Evaluating
- Run evals through `arx.evaluate(model, slice, run_one)`. It enforces the slice's exact IDs, counts errors as 0,
  writes rows incrementally and keeps the card live. Rows stay aggregate-safe: id, score, cost, latency, error.
  Do not put client text, answers or traces in rows.
- A harness outside Python: `arx run` on a hash-pinned manifest (see `autoresearch/execution.py`), `--dry-run` first.
  Its stdout/stderr stay in the task dir as private logs.
- Before a candidate runs a rung, the champion must have a run on the same slice with the same harness.
  `arx gate <model>` names the next run; follow it, do not skip rungs.
- Not every hill is pass/fail. If the target's score is a number (latency, length, cost), freeze the slice with
  `--scale continuous --unit <u> --metric "<what score means>"` and score rows higher-is-better. Default is 0/1.
- Never edit a frozen slice. Make a new one with a new name.
- Every hill gets an explainer (`arx hill explain`: symptom, example, measure, share). See PROTOCOL.md.
- Pre-declare what a change should move (in the hill's `problem` or the model's `change`) before running it.

## Reporting
- Every number names its slice and n. Show paired deltas vs the champion, not raw scores from different slices.
- "Better" means the gate passed. A noisy delta on a dev slice is a lead, not a result.
- Failed candidates stay in the ledger as rejected, with the reason. Negative results are results.

## Papers
- One living paper per hill (`/papers/<hill>`), written on promote, on hill close (negative results too) and kept
  current while the hill is open. Checklist in PROTOCOL.md; start from `arx paper new <hill>`.
- `arx paper check --file paper.html` before every publish; fix every error.
- `arx paper add|edit <name> --file paper.html` publishes; open pages swap the new version in place.
- `arx paper poll` blocks until someone waits on you, in any paper, and prints one JSON line per thread.
  Answer with `arx paper reply <name> <thread> "text" [--link "label=#block"] [--file page.html]`;
  `arx paper resolve <name> <thread> ["note"]` when done. Keep polling while people review.

## Data
- Datasets and large slices live on Hugging Face as **private** repos; the slice keeps the URL and the ID hash.
- Never commit secrets, client data, model weights or `rows.jsonl` from private datasets.
- Scratch output (crops, temp files, screenshots) goes in `scratch/` (gitignored).

## UI
- Cut taglines, helper text and secondary labels. If a screen needs them to make sense, fix the layout.
