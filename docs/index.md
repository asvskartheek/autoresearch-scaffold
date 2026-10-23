# Why ARX

ARX (the `autoresearch` Python package and its `arx` CLI) is research infrastructure for AI agents that improve
models. It gives an agent, or a team of subagents, a protocol, a ledger, a gate ladder and a live dashboard, so it
can hill-climb a model or an agent against eval sets while you watch every step.

Python stdlib only · one CLI · one Python API · a local dashboard.

![Overview: champion, candidate ladder and leaderboard](overview.png)

## The problem

Agents doing research fail in the same handful of ways:

| Failure | What it looks like | What ARX does about it |
|---|---|---|
| Unlike-for-like comparisons | "v8 scored 71% and v7 scored 68%", on different subsets | **Frozen slices.** Every score names an exact ID set and its hash. Gates only compare runs on the same hash. |
| Celebrating noise | +4 pts on 20 examples | **Paired deltas with a 90% bootstrap CI.** A delta whose interval spans 0 is marked *noisy*. |
| Fix one thing, break another | A politeness fix that silently costs arithmetic | **Hills that stay climbed.** Every fixed weakness becomes a permanent regression check. |
| Paying for the full eval too early | Running 1,300 examples for every idea | **A gate ladder.** `dev → random50 → random100 → full`. The expensive rung is earned. |
| Invisible work | A 40-minute job nobody knows is running, or that died | **Tasks.** Everything is a live Workbench card with progress, ETA, curves and a heartbeat. Stalled cards turn red. |
| Runaway spend | A sweep that keeps calling a paid API | **Budgets.** Money and time caps that roll up the task tree. |

The common thread: ARX makes the right way the *default* way. An agent following `arx gate <model>` cannot skip the
baseline, cannot compare against a different slice and cannot promote without passing every rung.

## Design choices

- **The ledger is plain files.** Everything lives as JSON / JSONL under `.research/`. Agents, shell scripts and the
  dashboard read the same files; there is no database or daemon that has to be up for work to be recorded.
- **Gate results are never stored.** They are recomputed from finished eval tasks every time they are asked for, so
  they cannot drift from the evidence. See [Architecture](architecture.md#how-gates-are-derived).
- **Rows are aggregate-safe.** An eval row holds `id`, `score`, `cost`, `latency_s` and `error`, never prompts,
  outputs or traces, so the ledger can be shared without leaking client data.
- **Nothing calls a model.** ARX never runs your model. You hand it a function (`run_one`) or a command
  (`arx run`) and it records what comes back.

## Where to go next

- [Getting started](getting-started.md): install, `arx init`, the dashboard, one research step end to end.
- How-to guides: [tasks](guides/tasks.md), [slices](guides/slices.md), [hills](guides/hills.md),
  [evals](guides/evals.md), [gates](guides/gates.md), [`arx run`](guides/run.md), [budgets](guides/budgets.md).
- [Architecture](architecture.md): how the pieces fit, and how nesting, budgets and gates work inside.
- Reference: [Python API](reference/python.md), [CLI](reference/cli.md), [`research.json`](reference/config.md).
