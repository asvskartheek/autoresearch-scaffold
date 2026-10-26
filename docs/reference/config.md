# `research.json`

The project's config lives at its root. `arx init` writes the defaults:

```json
{
  "name": "Untitled research",
  "higher_is_better": true,
  "kpis": ["score", "cost", "latency_p50", "latency_p95"],
  "stall_minutes": 10,
  "ladder": [
    {"rung": "dev", "checks": [
      {"slice": "@hill.target", "rule": "better", "margin": 0.0},
      {"slice": "@hill.control", "rule": "not_worse", "tolerance": 0.05},
      {"slice": "@hills.climbed", "rule": "not_worse", "tolerance": 0.03}
    ]},
    {"rung": "random50", "checks": [{"slice": "random50", "rule": "not_worse", "tolerance": 0.02}]},
    {"rung": "random100", "checks": [{"slice": "random100", "rule": "not_worse", "tolerance": 0.01}]},
    {"rung": "full", "checks": [{"slice": "full", "rule": "better", "margin": 0.0}]}
  ]
}
```

| Key | Meaning |
|---|---|
| `name` | Shown in the dashboard. |
| `primary_dataset` | Set by the first `arx dataset add`; bare slice names resolve against it. |
| `higher_is_better` | Flips the sign of paired deltas when `false` (e.g. error rate). |
| `kpis` | Columns that travel together on leaderboards. |
| `stall_minutes` | A running task with no heartbeat this long shows as stalled. |
| `max_paid_usd` | Upper bound on `budget_usd` for paid `arx run` manifests. |
| `baseline_cmd` | Shell command that runs one eval for `arx baseline` / `arx promote`, with `{model}` and `{slice}` filled in, run from the project root (values shell-quoted, `--jobs` may run several at once), e.g. `python eval.py --model {model} --slice {slice}`. It should call `arx.evaluate`. Unset: missing baselines are only listed. |
| `ladder` | The rungs, in order. |

## Checks

| Field | Meaning |
|---|---|
| `slice` | A slice name, or `@hill.target`, `@hill.control` (the candidate's hill), `@hills.climbed` (every climbed hill's target except the candidate's own). |
| `rule` | `better` (passes when delta `> margin`) or `not_worse` (passes when delta `>= -tolerance`). |
| `margin` / `tolerance` | In score units: `0.05` is 5 points on a 0–1 score. |
| `manual` | `true` makes a check a human sign-off: it shows as `needs_review` and never passes on its own. |

Change rules before running a candidate, never after seeing its results.
