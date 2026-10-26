<div align="center">

# autoresearch-scaffold

**Research infrastructure for AI agents that improve models.**

A ledger, a gate ladder and a live dashboard, so an agent (or a team of subagents) can hill-climb a model against
eval sets while you watch every step.

Python stdlib only · one CLI (`arx`) · one Python API · local dashboard

<img src="docs/overview.png" alt="Overview: champion, candidate ladder and leaderboard" width="900">

</div>

<br/>

> **AI agents:** read [`AGENTS.md`](AGENTS.md) (the rules) and [`PROTOCOL.md`](PROTOCOL.md) (one research step)
> before touching a model, an eval or a slice. When unsure what to run next, run `arx gate <model>`.

# Why

Agents doing research fail in the same ways: they compare scores from different subsets, celebrate noise on 20
examples, fix one weakness and quietly break another, and run long jobs nobody can see. The scaffold makes the
right way the default:

- **Frozen slices.** Every score names an exact ID set and its hash, so comparisons are like for like.
- **A gate ladder.** A candidate climbs `dev → random50 → random100 → full` against the champion. Each rung is a
  paired comparison on identical IDs with a 90% bootstrap CI. The full eval runs only once it is earned.
- **Hills that stay climbed.** Each weakness you fix becomes a regression check for every later version.
- **Everything visible.** Setup, downloads, evals and training are tasks: live Workbench cards with progress, ETA,
  curves and notes, moved to the Archive when they end.
- **Time budgets.** Put a wall-clock cap on a task; arx enforces it on evals and every sub-task under it.

# Quickstart

## Let your agent set it up

Paste into Claude Code, Codex, Cursor or any coding agent:

```text
Install autoresearch-scaffold with `uv tool install git+https://github.com/asvskartheek/autoresearch-scaffold`,
then run `arx init <project-dir> --name "<what we are improving>"`. Read AGENTS.md and PROTOCOL.md in the new
project, give me the dashboard URL, and follow them for all research work from now on.
```

## Or by hand

```bash
uv tool install git+https://github.com/asvskartheek/autoresearch-scaffold   # `arx` on PATH (`ar` is the system archiver)

arx init my-research --name "GSM8K · Qwen 0.8B"   # starts the dashboard, opens a "Project setup" task
cd my-research
arx dataset add gsm8k --size 1319 --url https://huggingface.co/datasets/openai/gsm8k   # freezes full, random50, random100
arx model add v1 --champion --change "Baseline"
```

# One research step

```bash
# 1. Name the weakness: a target slice that shows it, a control slice that must not move
arx slice add dev-arith   --ids-file arith_ids.txt   --kind dev --description "Arithmetic slips"
arx slice add dev-control --ids-file control_ids.txt --kind control
arx hill open arith --title "Arithmetic slips" --target dev-arith --control dev-control \
    --problem "v1 sets up the problem right but miscalculates. Expect +15 pts on dev-arith; nothing else moves."
arx hill explain arith --symptom "Right setup, wrong arithmetic" \
    --example-input "17 × 24?" --example-wrong "398" --example-right "408" --share 63/495

# 2. Register the candidate and climb
arx model add v2 --hill arith --change "Calculator tool call for every operation"
arx gate v2        # names the next run: the champion's baseline first, then v2, rung by rung
arx promote v2     # only after every rung passes
arx reject v2 --reason "Broke multi-step word problems by 6 pts"   # or keep it in the ledger as a negative result
```

`arx gate` always says what to run next:

```text
v2 vs champion v1
  dev        PENDING
      need_baseline  gsm8k/dev-arith              better +0.0
      need_baseline  gsm8k/dev-control            not_worse -5.0
  random50   LOCKED
  random100  LOCKED
  full       LOCKED
next runs:
  v1 on gsm8k/dev-arith
  v1 on gsm8k/dev-control
```

# Python API

```python
import autoresearch as ar

def run_one(example_id):                   # your harness: a score in [0, 1]
    ...
    return {"score": 1.0, "latency_s": 2.1}

ar.evaluate("v2", "dev-arith", run_one, workers=8, deadline_s=1800)   # exact slice IDs; errors and timeouts score 0

with ar.task("train", "SFT v3", model="v3", config={"lr": 2e-4}) as t:   # live curves on the task page
    for step, loss in training_loop():
        t.log(step=step, loss=loss)
    t.note("Loss plateaued at 1.0; dropping lr")
    t.link("Checkpoint", "https://huggingface.co/you/v3")

with ar.task("experiment", "prompt sweep", budget_s=1800) as t:   # 30 minutes
    while t.ok():                                    # or t.check(): raises, card ends as "budget"
        ar.evaluate(next_prompt(), "dev-arith", run_one)   # the eval's deadline shrinks to the time left
```

Budgets nest: a sub-task never outlives its parent. Checks are cooperative: arx stops an eval on time, but a plain
task stops only when its code calls `ok()` or `check()`.

**From a shell:** `arx task start --title "Download weights" --budget-s 600` prints an id, then
`arx task log | note | link | progress | left | finish <id>`. Loop with `while arx task left $id; do ...; done`.
**Another harness:** `arx eval record --model v2 --slice random100 --rows rows.jsonl`, or launch a reviewed,
hash-pinned command with `arx run --manifest m.json --expected-sha256 <sha> --dry-run`.

# The dashboard

`arx up` serves it on `127.0.0.1:8890` and refreshes every few seconds. `arx init` starts it for you.

### Workbench: every running task

Progress, ETA, a sparkline of the latest metric and a heartbeat. Sub-tasks nest under the task that started them.
A task with no heartbeat for 10 minutes turns red.

<img src="docs/workbench.png" alt="Workbench with a training run, a live eval, a data job and the setup task" width="900">

### Task page: curves, notes, links

Every series logged with `t.log(...)` becomes a chart. Eval tasks also show the paired diff with the champion and a
per-example strip.

<img src="docs/task.png" alt="Training task page with loss, lr, grad norm and dev score curves" width="900">

### Model page: the gate

Each rung's checks against the champion: both scores, Δ, the 90% CI, wins/losses on the paired IDs, and the next run.

<img src="docs/model-v8.png" alt="Gate table for candidate v8 with paired deltas and confidence intervals" width="900">

### Hill page: one weakness

What goes wrong, an example, how many failures it explains, and every attempt at it on the dev set, down to which
examples each version fixed or broke.

<img src="docs/hills.png" alt="Hill page with an example, its share of failures, the dev set table and per-example grid" width="900">

| Slices | Archive |
|---|---|
| <img src="docs/slices.png" alt="Frozen slices with hash, kind and size"> | <img src="docs/archive.png" alt="Finished, failed and budget-stopped tasks"> |
| Frozen ID sets with hash, seed, metric and dataset link | Finished, failed and budget-stopped tasks, each with its full page |

# Commands

| Command | Does |
|---|---|
| `arx init [dir]` | Scaffold a project, start the dashboard, open a setup task |
| `arx up [--restart]` | Start the dashboard, or restart it after an upgrade |
| `arx sync` | Refresh the project's vendored `autoresearch/` copy and restart the dashboard |
| `arx dataset add` | Register a full eval set and its nested random slices |
| `arx slice add` | Freeze a dev / control / synthetic slice. Frozen slices never change |
| `arx hill open` | Name a weakness with its target and control slices |
| `arx hill explain` | Give a hill its symptom, example, measure and share |
| `arx model add` | Register a candidate (`--champion` for the baseline; `--status historical\|planned`) |
| `arx gate <model>` | Where a candidate stands on the ladder, and the next run |
| `arx promote <model>` | Make it champion and mark its hill climbed |
| `arx reject <model> --reason` | Keep a failed candidate in the ledger, with the reason |
| `arx eval record` | Record rows from another harness |
| `arx run` | Launch a hash-pinned command manifest as a task |
| `arx task ...` | Workbench tasks from a shell: `start`, `log`, `note`, `link`, `progress`, `left`, `finish` |
| `arx status` | What is running, where each candidate stands, which hills are open |

# Configure

`research.json` holds the datasets, KPIs and the ladder. The default ladder:

| Rung | Checks vs champion |
|---|---|
| `dev` | Hill target **better**. Hill control within −5 pts. Every climbed hill within −3 pts |
| `random50` | Within −2 pts |
| `random100` | Within −1 pt |
| `full` | **Better**: this makes a new champion |

The middle rungs are "not worse" on purpose: a targeted fix often shouldn't move a random slice, and requiring
"better" on 50 examples is a coin toss. See [`PROTOCOL.md`](PROTOCOL.md).

# Demo

The screenshots above are this demo. Scores are simulated; nothing calls a model.

```bash
git clone https://github.com/asvskartheek/autoresearch-scaffold && cd autoresearch-scaffold
python3 examples/demo/seed.py demo-project      # v5 → v6 → v7 promoted, v8b rejected, v8 mid-ladder
cd demo-project
PYTHONPATH=.. python3 ../examples/demo/live.py &  # a live eval, a training run and a data job
PYTHONPATH=.. python3 -m autoresearch.cli up
```

# Layout

```
research.json          datasets, ladder, thresholds, KPIs
AGENTS.md  PROTOCOL.md rules for agents, and the research method
.research/             the ledger: datasets, slices, hills, models, decisions, tasks/<id>/{task.json, metrics, rows, events}
autoresearch/          ledger, gates, task tracker, evaluate(), dashboard server
```

The ledger is plain JSON / JSONL, so agents, scripts and the dashboard read the same files. Gate results are never
stored; they are recomputed from finished evals. Rows hold id, score, cost, latency and error only, never prompts or
outputs.

# License

MIT
