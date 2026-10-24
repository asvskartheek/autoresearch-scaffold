# Champions

A champion is official or it does not exist. A model becomes champion only after it ran every gate of the pipeline
(`research.json` `ladder`, ending on the full dataset) and beat the champion it replaced. The dashboard never
invents champions from history.

| | |
|---|---|
| Made by | `arx model add --champion` (the seeded baseline), then `arx promote` |
| Stored in | `models.json` status, `decisions.jsonl` |
| Gate | every rung passed (or `--force`) |
| Has a page | yes: `#champion/<model>` |

## The Champions page

- **Champions**: official champions, newest first: model, score and n, points over the champion it replaced, how long
  it held the title. Each row opens the champion's page.
- **Next champion**: the pipeline as a row of gates (problem-specific, dev set, ..., full dataset). For each gate it
  shows the champion's result, the best challenger's result on the gate's eval set, and what blocks it ("Needs
  sign-off", "Needs +5 pts, lead has +3.3", "No eval data"). Below it, every candidate with its gates and where it
  stopped.

A champion's page shows what it changed, its hill, the gate it passed, and paired deltas against the champion it
replaced on every eval set where both have a complete run. `GET /api/champion/<model>` returns the same data, and 404
for a model that was never champion.

Promotion time is the time of the command, so do not `arx promote --force` old models to backfill history: they
would all be dated today.

## Leads

Recorded runs still tell the story of a long project. The dashboard computes a **lead** for each comparable eval
set: take all scored runs on one track (a dataset plus an eval-set hash), ordered by the run's own date; the first
run with `n >= 20` is a lead, and each later run joins only if its score is strictly higher than every run before
it. Leads are shown on the Overview chart ("best so far", ringed points) and in Latest activity. A lead on a dev set
is not a champion: it did not pass the pipeline.

Scores of different eval sets are never merged. A variant is the task title without its trailing
` · <cohort_label>`, so give every configuration its own title (see [Recording history](history.md)).
