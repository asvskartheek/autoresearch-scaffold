# Migrating a mature project

Goal: an existing project, with months of results in folders, notebooks and spreadsheets, gets a ledger whose
dashboard is not empty on day one. Work in this order; each step is visible in the dashboard when it is done.
Open a task for the migration and note each step on it.

## 1. Initialise in place

```bash
cd my-project
arx init . --name "My project" --no-serve
```

Existing `AGENTS.md`, `CLAUDE.md`, `PROTOCOL.md` and `research.json` are kept; missing ones are copied from the
templates. If you keep your own `AGENTS.md`, merge in the ARX sections by hand (the dashboard, "Every piece of work
is visible", "Evaluating", "Resuming"). `.research/`, the vendored `autoresearch/` and `.claude/settings.json`
(session hooks) are created if absent. Then `arx up` and give the user the URL.

Check `research.json`: `name`, `kpis` and the `ladder` rungs match how the project judges a model. Change
rules before any new candidate runs, never after.

## 2. Register what you evaluate on

Datasets and the slices you kept reusing, each with the example IDs:

```bash
arx dataset add pid --ids-file pid_ids.json --title "P&ID questions" --url https://huggingface.co/datasets/org/pid --random 60 120
arx slice add pid/dev60 --ids-file dev60_ids.json --kind dev --description "Frozen dev pool"
```

Only the IDs and a URL go in the ledger; datasets stay private on Hugging Face. Skip a slice whose exact IDs are
lost: imported runs do not need one (step 5).

## 3. Seed the champion

The model currently in use is the baseline:

```bash
arx model add kimi-v5 --champion --no-parent --change "current production configuration"
```

Do not `arx promote --force` older models to fill the Champions page: promotion dates are the time of the command.
Earlier bests come back from step 5.

## 4. Record the weaknesses

One hill per known failure mode, with its explainer, as in [Hills](hills.md). A hill needs a target slice. If the
real one is not registered yet, point it at a registered one and tighten it later.

```bash
arx hill open legend-reading --title "Misreads legends" --target pid/dev60 --problem "..." \
    --symptom "..." --measure "..." --share 63/495 --share-of "wrong answers on full"
```

## 5. Backfill the earlier runs

For each earlier version, one `historical` model with its `hill` (an attempt on that hill), and one
`historical_run` task per recorded result. The exact summary is in [Recording history](history.md). Script it from
whatever index you have (a results CSV, a folder of JSON):

- one model per version, `--status historical --no-parent`;
- one task per result, titled `<model label> · <agent> · <cohort_label>`;
- the same `dataset` and `cohort_hash` for runs that scored the same examples;
- `catalog_record.date` from the file's own date;
- a link to the original file or report, not a copy of it.

Candidates you tried and dropped:

```bash
arx model add try-ocr --no-parent --hill legend-reading --change "OCR pre-pass"
arx reject try-ocr --reason "no gain on dev60 (-1.7 pts, n=60)"
```

## 6. Close the loop

```bash
arx status
```

Expect the run count to equal the results you imported, one line per hill with its attempts, and the champion you
seeded. Then look at the dashboard: Overview shows a track per example set; Champions shows the seeded champion and the
pipeline of candidates; a hill lists its attempts.

If a page is empty, the usual causes are: `n` or `score` missing from a summary (the run is ignored), different
`cohort_hash` strings for the same examples (runs split into tracks of one), titles that are identical for different
configurations (they collapse into one variant), or a model without `hill`.

## 7. From here on

New work goes through the gate ladder as usual. The champion must have a run on the same slice with the same
harness before a candidate runs a rung; imported runs do not satisfy that.
