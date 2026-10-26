# Evals

An eval runs one model on one slice and records one row per example. Evals are always tasks of kind `eval`.

## `ar.evaluate`

```python
import autoresearch as ar

def run_one(example_id):          # your harness; ARX never calls a model itself
    ex = load(example_id)
    answer, usage = my_model(ex.question)
    return {"score": float(answer == ex.gold), "cost": usage.usd}

t = ar.evaluate("v2", "dev-arith", run_one, workers=8, deadline_s=1800)
print(t.meta["summary"])          # n, score, errors, cost, cost_total, latency_p50/p95, missing
```

What `evaluate` guarantees, and why:

| Guarantee | Why |
|---|---|
| Runs exactly the slice's IDs (times `repeats`) | So the run is comparable to every other run on that slice. |
| An exception becomes a row with `score=0` and `error` | A crash is a wrong answer. Skipping it would flatter the model. |
| Examples left at the deadline or when the money runs out become error rows | Same reason; a partial run is never quietly ranked. |
| `latency_s` is measured for you | `run_one` only needs to return `score` (and `cost` if it knows it). |
| Rows are written as they finish | The card is live and a crash loses nothing already done. |
| `complete` is set on finish | Only complete, `done` evals count for gates and leaderboards. |

`run_one` returns a dict; ARX keeps `id` authoritative. Keep rows aggregate-safe: `score`, `cost`, `latency_s`,
`error`. **No prompts, answers or traces in rows.**

`repeats=k` runs each ID k times; per-example scores are averaged before any paired comparison.

## Rows from elsewhere: `arx eval record`

For a cloud job or another harness that already produced rows:

```bash
arx eval record --model v2 --slice random100 --rows rows.jsonl
```

It creates a finished eval task and marks it `complete` only if the row IDs equal the slice's IDs.

## Commands outside Python: `arx run`

For a harness that is a command, use a hash-pinned manifest. See [`arx run` manifests](run.md).

## Before a candidate runs a rung

The champion must already have a run on the same slice with the same harness. `arx gate <model>` lists the champion's
baseline first whenever it is missing. Re-run the champion when the harness, judge, data or tools change: old
numbers do not transfer.
