# Resuming work

A new session starts from the ledger, not from memory. Read it first.

## `arx status`

```text
$ arx status
Scratch · champion kimi-v1 · 5 models · 4 scored runs · 1 hills
  best on pid: Kimi K3 80.0% n=60
  hill legend-reading [open] 4 attempts: kimi-v2(historical), kimi-v3(historical), kimi-v4(historical), v8(candidate)
  [running] 1024-094504-experiment-8f95 Error analysis 0/40
  candidate v8: dev:pending → random50:locked → random100:locked → full:locked
```

| Line | Meaning |
|---|---|
| First | project name, current champion, models in the ledger, scored runs (every task with a `summary.score` and `n`, evals and imports alike), hills |
| `best on <dataset>` | highest score among scored runs with `n >= 10` on that dataset. Runs on different slices are mixed here; it is a pointer, not a comparison. Use the dashboard's tracks for that |
| `hill` | status and attempts: models whose `hill` is that hill, with their status (first six) |
| `[running]` / `[stalled]` | live tasks: id, title, done/total |
| `candidate` | each candidate's rung statuses; `arx gate <model>` names the next run |

Do not redo what it lists.

## A stalled task

A task is `stalled` when it is `running` but has not sent a heartbeat for `stall_minutes` (default 10). Its card is
red on the Workbench.

- It is yours to continue: `arx task resume <id>` (or `t.note(...)` / `t.log(...)` from Python). It adds a
  "resumed" note and refreshes the heartbeat, so the task runs again and keeps its history. It does not restart the
  work or reopen a task that has already ended.
- Nobody will finish it: `arx sweep` closes every task that has been stalled for more than `--hours` (default 2)
  as `abandoned`. Tasks still within the stall window, or healthy, are untouched.

```bash
arx sweep --hours 6
```

It prints `N abandoned`. Run it before starting new work so the Workbench shows only live jobs.

## Order of a resumed session

1. `arx up`, then give the user the URL.
2. `arx status`.
3. Resume or sweep stalled tasks.
4. `arx gate <model>` for each candidate, and follow its "next runs".
