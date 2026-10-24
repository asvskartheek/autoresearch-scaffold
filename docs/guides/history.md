# Recording history

Work done before the ledger existed, or outside it, can be recorded after the fact. A recorded run shows on the
Overview, on its model's page, on the hill it belongs to, and in the leads on the Overview chart. It is metadata, not a
new evaluation: no rows, no slice ladder, and it never counts toward a gate.

## What to record

Per earlier run, one **task** of kind `historical_run` whose `summary` carries the result, and one **model** that
the task points at.

```python
import autoresearch as ar

p = ar.project("/path/to/project")   # or run from inside the project folder
p.add_model("kimi-v3", parent="", hill="legend-reading", status="historical",
            change="legend crop + 3-way vote")           # once per version

t = ar.task("historical_run", "Kimi K3 · po2_vote=3 · Development 60", model="kimi-v3",
            agent="historical-import", links={"Original source": "https://..."},
            description="Original completed run. Imported metadata, not a new evaluation.")
t.finish(summary={
    "n": 60, "score": 0.80, "errors": 0, "cost": 0.004, "latency_p50": 44.1, "latency_p95": 90.0,
    "dataset": "pid", "cohort_hash": "a1b2c3d4e5", "registered_slice": None, "evidence": "Historical",
    "catalog_record": {"model": "Kimi K3", "agent": "po2_vote=3",
                       "cohort_label": "Development 60", "date": "2026-10-09 10:00"},
})
```

From a shell:

```bash
arx model add kimi-v3 --no-parent --hill legend-reading --status historical --change "legend crop + 3-way vote"
id=$(arx task start --kind historical_run --model kimi-v3 --agent historical-import \
       --title "Kimi K3 · po2_vote=3 · Development 60" --description "Imported metadata, not a new evaluation.")
arx task link $id "Original source" https://...
arx task finish $id --summary-file summary.json
```

Put the imports under one parent task (`with ar.task("import", "Backfill history"): ...`, or pass
`--parent`) so they stay together in the Archive.

## The summary

| Key | Meaning |
|---|---|
| `n` | examples scored. Required; a run without it is ignored |
| `score` | 0 to 1, higher is better (champions and "new best" assume it). Required; must be a number |
| `errors` | examples that failed (already counted as 0 in `score`) |
| `cost` | cost per example |
| `latency_p50`, `latency_p95` | seconds per example |
| `dataset` | dataset name; groups runs into a track |
| `cohort_hash` | identifies the exact example set. Same string, same examples; different string, not comparable |
| `registered_slice` | the registered slice name when the examples match one, else `null` |
| `evidence` | short label shown next to the run, such as `Historical` |
| `catalog_record.model` | display label for the run's model, such as `Kimi K3` |
| `catalog_record.agent` | the configuration that varied, such as `po2_vote=3` |
| `catalog_record.cohort_label` | readable name of the example set, such as `Development 60` |
| `catalog_record.date` | when the run originally happened, `YYYY-MM-DD HH:MM`, local time |

Extra keys are kept and ignored. Do not put client text, answers or traces in a summary.

How the pieces are used:

- **Date.** `catalog_record.date` places the run on the timeline. Without it the run is dated when it was imported,
  which says nothing about when it ran.
- **Variant.** The task title minus a trailing ` · <cohort_label>`. Runs with the same variant are repeats of one
  configuration; give each configuration its own title, normally `<model> · <agent> · <cohort_label>`.
- **Model.** The task's `model` ties the run to `models.json`: the run appears under "Recorded runs" on that model.
  Set `hill` on the model and the model counts as an attempt on that hill.
- **Track.** `dataset` plus `cohort_hash`. See below.

## Why runs are only comparable within a track

A score is a property of a model on a set of examples. 80% on a 60-example development set and 65% on a random 120
are not on one scale: the sets differ in difficulty and size. The dashboard therefore groups runs by dataset and
example-set hash and compares only inside a group (a track). Leaderboards, "vs first", new-best markers and
leads are all per track. A track needs at least 20 examples to produce leads. History never creates champions.

Use one `cohort_hash` for runs that really scored the same examples. If you cannot tell, use different hashes; a
false merge is worse than a split. Runs recorded with `arx eval` or `arx.evaluate` take the slice hash
automatically.

## Check what you recorded

```bash
arx status          # "N scored runs", best per dataset, each hill's attempts
```

Then open Overview (one track per example set), Models (the model's recorded runs), Hills (attempts) and Champions
(the seeded champion plus the pipeline).

To tell the project's current champion apart from history, leave it as the one model added with `--champion`. Record
past models with `--status historical --no-parent`; they sit beside the lineage and never appear on the ladder.
