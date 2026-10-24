# CLI

Every command runs against the project found by walking up from the current directory to `research.json`
(except `init`).

## Project

| Command | Does |
|---|---|
| `arx init [dir] [--name N] [--port 8890] [--no-serve]` | Scaffold a project, vendor `autoresearch/`, start the dashboard, open a "Project setup" task |
| `arx up [--port 8890] [--restart]` | Start this project's dashboard detached if it is not running, and print its URL. `--port` is the first port tried |
| `arx down [--all]` | Stop this project's dashboard, or every project's |
| `arx ps` | List running dashboards: URL, pid, project folder |
| `arx sync` | Replace the vendored `autoresearch/` with the installed package and restart the dashboard |
| `arx serve [--port]` | Run the server in the foreground (what `up` launches) |
| `arx status` | Champion, counts, best run per dataset, each hill's attempts, live tasks, each candidate's rungs |
| `arx sweep [--hours 2]` | Close tasks stalled for longer than `--hours` as `abandoned` |

See [The dashboard lifecycle](../guides/dashboard.md) and [Resuming work](../guides/resume.md).

## Data

| Command | Does |
|---|---|
| `arx dataset add NAME (--ids-file F \| --size N) [--url] [--title] [--description] [--random 50 100] [--seed 42] [--no-random]` | Register a dataset; freeze `full` and nested random slices |
| `arx slice add NAME (--ids-file F \| --size N) [--kind dev\|control\|synthetic\|random\|full] [--description] [--url] [--hill] [--metric]` | Freeze a slice. Fails if NAME exists with different IDs |

## Hills and models

| Command | Does |
|---|---|
| `arx hill open NAME --title T --target S [--control S] [--problem P] [--found-in M]` | Open a hill (accepts the explain flags too) |
| `arx hill explain NAME [--symptom] [--measure] [--example-input --example-wrong --example-right --example-why] [--examples-file F] [--share C/N --share-of W]` | Add the hill's explainer; each `--example-*` set appends one example |
| `arx poster model\|hill ID FILE` | Set the poster (json spec, svg, html, png, jpg, webp; max 2 MB, spec 16 KB); `model add` and `hill open/explain` take `--poster FILE` |
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
arx task resume ID                     # note "resumed" and refresh the heartbeat of a stalled task
arx task finish ID [--status done|failed|budget] [--summary-file F]
```

`--parent` defaults to `$ARX_PARENT`. Task subcommands print a warning if the dashboard is not running.
