# CLI

Every command runs against the project found by walking up from the current directory to `research.json`
(except `init`).

## Project

| Command | Does |
|---|---|
| `arx init [dir] [--name N] [--port 8890] [--no-serve]` | Scaffold a project, vendor `autoresearch/`, start the dashboard, open a "Project setup" task |
| `arx up [--port 8890] [--restart]` | Start the dashboard detached if it is not running, and print its URL |
| `arx sync` | Refresh the vendored `autoresearch/` from the installed package and restart the dashboard |
| `arx serve [--port]` | Run the server in the foreground (what `up` launches) |
| `arx status` | Running tasks, each candidate's rungs, goals, hills |
| `arx projects [ls \| add PATH \| rm KEY]` | The projects one dashboard serves (`~/.arx/projects.json`); each is at `/p/<key>/` |

## Data

| Command | Does |
|---|---|
| `arx dataset add NAME (--ids-file F \| --size N) [--url] [--title] [--description] [--random 50 100] [--seed 42] [--no-random]` | Register a dataset; freeze `full` and nested random slices |
| `arx slice add NAME (--ids-file F \| --size N) [--kind dev\|control\|synthetic\|random\|full] [--description] [--url] [--hill] [--metric] [--scale binary\|continuous] [--unit]` | Freeze a slice. Fails if NAME exists with different IDs |

## Goals

| Command | Does |
|---|---|
| `arx goal open NAME --slice S --target T [--title] [--kpi score\|cost\|latency_p50\|latency_p95] [--lower-is-better] [--baseline M] [--problem P]` | Open a goal: a target KPI on one slice |
| `arx goal status [NAME] [--json]` | Value now, gap to target, paired Δ vs the starting champion |
| `arx goal achieve NAME [--note N] [--force]` | Close it as achieved; refused unless the ledger meets the target (or `--force`) |
| `arx goal abandon NAME --reason R` | Close it as abandoned, with the reason |

See [Goals](../guides/goals.md).

## Hills and models

| Command | Does |
|---|---|
| `arx hill open NAME --title T --target S [--control S] [--goal G] [--problem P] [--found-in M]` | Open a hill (accepts the explain flags too) |
| `arx hill explain NAME [--symptom] [--measure] [--example-input --example-wrong --example-right --example-why] [--examples-file F] [--share C/N --share-of W]` | Add the hill's explainer; each `--example-*` set appends one example |
| `arx model add NAME [--champion] [--parent P \| --no-parent] [--hill H] [--change C] [--title] [--link label=url ...] [--status candidate\|historical\|planned]` | Register a model; parent defaults to the champion |
| `arx gate MODEL [--json]` | Ladder status and next runs |
| `arx promote MODEL [--force]` | Make champion (re-checks every rung), retire the old one, mark the hill climbed |
| `arx reject MODEL --reason R` | Mark rejected, with the reason |

## Evals

| Command | Does |
|---|---|
| `arx eval record --model M --slice S --rows rows.jsonl [--title] [--description] [--agent]` | Record rows from another harness as a finished eval |
| `arx run --manifest F --expected-sha256 SHA [--model M --slice S] [--title] [--description] [--agent] [--dry-run] [--approve-paid]` | Run a hash-pinned manifest as a task. See [`arx run`](../guides/run.md) |

## Tasks

```text
arx task start --title T [--kind experiment] [--description] [--model] [--slice] [--agent] [--total N]
               [--parent ID] [--budget-s S]          # prints the new id
arx task log ID key=value ... [--step N]
arx task note ID message ... [--level info|warn|error]
arx task link ID LABEL URL
arx task progress ID DONE [TOTAL]
arx task left ID                       # prints e.g. "0.9s" or "unlimited"; exit code 3 once time is up
arx task finish ID [--status done|failed|budget] [--summary-file F]
```

`--parent` defaults to `$ARX_PARENT`. Task subcommands print a warning if the dashboard is not running.

## Papers

```text
arx paper new HILL [--file F] | arx paper new --goal GOAL [--file F]   # starter page from the worked example
arx paper check (NAME | --file F) [--goal GOAL]                       # lint; exit 1 on errors
arx paper add|edit NAME --file F [--title] [--hill H] [--goal G]       # publish / republish
arx paper ls
arx paper poll [NAME] [--timeout S]                                   # block until someone waits on the agent
arx paper reply NAME THREAD "text" [--link label=url] [--file page.html] [--author agent]
arx paper resolve NAME THREAD ["note"]
arx paper attach NAME --file page.html
```

See [Papers](../guides/papers.md).
