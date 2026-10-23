# Python API

```python
import autoresearch as ar
```

The module-level functions use one `Project`, found by walking up from the current directory to the nearest
`research.json`. Call `ar.project(root)` to point it elsewhere.

## `ar.task(kind, title, **kw) -> Task`

| Argument | Meaning |
|---|---|
| `kind` | `eval`, `train`, `experiment`, `data`, `analysis`, `setup` (free-form) |
| `title`, `description` | What the card shows. Write the description for someone who missed the chat. |
| `model`, `slice` | Optional. A slice records its name and hash, and sets `total` to its size. |
| `agent` | Subagent name, shown on the card. |
| `total` | Progress denominator. |
| `links`, `config` | `{label: url}` and free-form settings shown on the task page. |
| `parent` | Task ID to nest under. Default: innermost open task in this process, else `$ARX_PARENT`. |
| `budget_usd`, `budget_s` | Money and wall-clock caps. See [Budgets](../guides/budgets.md). |
| `tid` | Re-open an existing task by ID instead of creating one. |

Use as a context manager (finishes `done`, `failed` on exception, `budget` on `BudgetExceeded`) or call `finish()`.

### `Task` methods

| Method | Does |
|---|---|
| `log(step=None, **values)` | Append a point to each named series. `cost=` also calls `spend`. |
| `note(msg, level="info")` | Append to the log; the latest note is the card's headline. |
| `link(label, url)` | Add a link (HF dataset, checkpoint, W&B run). |
| `progress(done, total=None)` | Update the progress bar and ETA samples. |
| `heartbeat()` | Refresh the heartbeat without other changes. |
| `add_row(row)` | Append an eval row (`evaluate` does this for you). |
| `spend(usd)` | Charge money to this task and every ancestor. |
| `left()` | Remaining `{"usd", "s"}`, tightest over the ancestor chain; missing key = unlimited. |
| `ok()` | Every remaining value `> 0`. |
| `check()` | Raise `BudgetExceeded` if any is spent. |
| `finish(status="done", summary=None)` | End the task. For evals, computes `complete` and the summary. |

`t.id`, `t.meta` (the `task.json` dict) and `t.dir` are available.

## `ar.evaluate(model, slice, run_one, **kw) -> Task`

`run_one(example_id) -> {"score": float, "cost"?: float, "latency_s"?: float, ...}`.

| Argument | Default | Meaning |
|---|---|---|
| `workers` | 8 | Concurrent calls (thread pool). Also bounds budget overshoot. |
| `deadline_s` | 3600 | Time budget for the eval. Unfinished examples become `deadline` error rows. |
| `budget_usd` | None | Money cap. Unfinished examples become `budget` error rows. |
| `repeats` | 1 | Run each ID this many times; scores are averaged per ID. |
| `title`, `description`, `agent`, `config`, `parent` | | As for `task`. |

Exceptions in `run_one` become rows with `score=0` and `error`.

## `ar.gate(model) -> dict`

```python
{"model": "v2", "champion": "v1", "promotable": False,
 "rungs": [{"rung": "dev", "status": "pending", "checks": [
     {"slice": "gsm8k/dev-arith", "rule": "better", "threshold": 0.0, "state": "pass",
      "n": 40, "delta": 0.15, "lo": 0.05, "hi": 0.25, "wins": 8, "losses": 2, "noisy": False,
      "cand": 0.8, "base": 0.65, "cand_task": "...", "base_task": "..."}]}],
 "next": [{"model": "v1", "slice": "gsm8k/random50"}]}
```

## `ar.project(root=None) -> Project`

`Project` exposes the ledger: `config`, `datasets()`, `slices()`, `slice(name)`, `hills()`, `models()`,
`champion()`, `tasks()`, `task(id)`, `rows(id)`, `metrics(id)`, `events(id)`, `evals()`,
`latest_eval(model, slice)`, and the writers `add_dataset`, `add_slice`, `random_slices`, `open_hill`,
`explain_hill`, `add_model`, `set_model_status`, `gate`, `promote`.

## Statistics

| Function | Returns |
|---|---|
| `ar.summarize(rows)` | `n, score, errors, cost, cost_total, latency_p50, latency_p95, latency_mean`; errors score 0 |
| `ar.paired(cand, base, sign=1, iters=2000)` | Paired delta over shared IDs of two `{id: score}` maps with a 90% bootstrap CI |

## `ar.BudgetExceeded`

Raised by `Task.check()`. Its message starts with the ID of the task whose budget ran out.
