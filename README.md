<div align="center">

# autoresearch-scaffold

**Research infrastructure for AI agents that improve models.**

A protocol, a ledger, a gate ladder and a live dashboard, so an agent (or a team of subagents) can hill-climb a
model or agent against eval sets while you watch every step.

Python stdlib only · one CLI (`arx`) · one Python API · local dashboard

<img src="docs/overview.png" alt="Observatory overview: champion, candidate ladder and leaderboard" width="900">

</div>

<br/>

> **AI agents:** read [`AGENTS.md`](AGENTS.md) (rules you follow) and [`PROTOCOL.md`](PROTOCOL.md) (how one research
> step works) before touching a model, an eval or a slice. Run `arx gate <model>` whenever you are unsure what to run
> next. It always names the next eval.

# Why

Agents doing research go wrong in the same ways: they compare scores from different subsets, celebrate noise on 20
examples, fix one weakness and quietly break another, and do long work nobody can see. This scaffold makes the right
way the default:

- **Frozen slices.** Every score names an exact ID set with a hash, so comparisons are always like for like.
- **A gate ladder.** A candidate climbs `dev → random50 → random100 → full` against the champion. Each rung is a
  paired comparison on identical IDs with a 90% bootstrap CI. You only pay for the full eval once it is earned.
- **Hills that stay climbed.** Each weakness you fix becomes a permanent regression check for every future version.
- **Everything visible.** Setup, downloads, evals and training are all tasks. They show as live Workbench cards with
  progress, ETA, curves and logs, and move to the Archive when they finish.

# Quickstart

## Path 1: Let your agent set it up

Paste this into Claude Code, Codex, Cursor, pi or any coding agent:

```text
Install autoresearch-scaffold with `uv tool install git+https://github.com/asvskartheek/autoresearch-scaffold`,
then run `arx init <project-dir> --name "<what we are improving>"`. Read AGENTS.md and PROTOCOL.md in the new
project, give me the dashboard URL, and follow them for all research work from now on.
```

## Path 2: CLI

```bash
uv tool install git+https://github.com/asvskartheek/autoresearch-scaffold   # puts `arx` on PATH (`ar` is the system archiver)

arx init my-research --name "GSM8K · Qwen 0.8B"   # starts the dashboard, opens a "Project setup" task
cd my-research
arx dataset add gsm8k --size 1319 --url https://huggingface.co/datasets/openai/gsm8k   # freezes full, random50, random100
arx model add v1 --champion --change "Baseline"
```

One research step, end to end:

```bash
arx slice add dev-arith --ids-file arith_ids.txt --kind dev --description "Arithmetic slips"
arx slice add dev-control --ids-file control_ids.txt --kind control
arx hill open arith --title "Arithmetic slips" --target dev-arith --control dev-control \
    --problem "v1 sets up the problem right but miscalculates. Expect +15 pts on dev-arith; nothing else moves."
arx model add v2 --hill arith --change "Calculator tool call for every operation"
arx gate v2        # names the next run: champion baseline first, then v2, rung by rung
arx promote v2     # only after every rung passes
```

## Path 3: Python API

```python
import autoresearch as ar

def run_one(example_id):                  # your harness: return a score in [0, 1]
    ...
    return {"score": 1.0, "cost": 0.003}

ar.evaluate("v2", "dev-arith", run_one, workers=8, deadline_s=1800)   # errors and timeouts count as 0

with ar.task("train", "SFT v3", model="v3", config={"lr": 2e-4}) as t:  # W&B-style live curves
    for step, loss in training_loop():
        t.log(step=step, loss=loss)
    t.link("Checkpoint", "https://huggingface.co/you/v3")
```

Evals from another harness or a cloud job: `arx eval record --model v2 --slice random100 --rows rows.jsonl`.
Shell-only work: `arx task start | log | note | link | progress | finish`.

# The dashboard

`arx up` serves it on `127.0.0.1` (it starts automatically with `arx init`). It refreshes every few seconds.

| Workbench | Gate |
|---|---|
| <img src="docs/workbench.png" alt="Workbench with live eval, training and data cards"> | <img src="docs/model-v8.png" alt="Gate checks for a candidate with paired deltas and CIs"> |
| **Task page** | **Hills** |
| <img src="docs/task.png" alt="Training task with loss, lr and grad norm curves"> | <img src="docs/hills.png" alt="Hills and the model × hill regression matrix"> |

| View | Shows |
|---|---|
| Overview | Champion, the candidate ladder, leaderboards by dataset and slice: score, Δ champion, errors, cost, p50/p95 |
| Workbench | A card for every running task: progress, ETA, sparkline, heartbeat. Stalled tasks turn red |
| Task page | Every logged series as a chart, paired diff with the champion, per-example strip, log, links, setup |
| Models | Lineage and rungs. A model page lists every gate check with its delta, CI and win/loss count |
| Hills | Every weakness found so far, plus the model × hill regression matrix |
| Slices | Frozen ID sets with hash, seed, metric and dataset link |
| Archive | Finished, failed and partial tasks, each with the same full page |

# Commands

| Command | Does |
|---|---|
| `arx init [dir]` | Scaffold a project, start the dashboard, open a setup task |
| `arx up [--restart]` | Start the dashboard, or restart it after an upgrade |
| `arx sync` | Refresh the project's vendored `autoresearch/` copy and restart the dashboard |
| `arx dataset add` | Register a full eval set and its nested random slices |
| `arx slice add` | Freeze a dev / control / synthetic slice. Slices never change once frozen |
| `arx hill open` | Name a weakness with its target and control slices |
| `arx model add` | Register a candidate (or `--champion` for the baseline) |
| `arx run --manifest m.json --expected-sha256 <sha>` | Launch a reviewed, hash-pinned command as a task; scored runs check rows against the slice |
| `arx gate <model>` | Where a candidate stands on the ladder, and the next run |
| `arx promote <model>` | Make it champion, and mark its hill as climbed |
| `arx reject <model>` | Keep a failed candidate in the ledger, with the reason |
| `arx status` | What is running, where each candidate stands, which hills are open |

# Configure

`research.json` in each project holds the ladder. The defaults are:

| Rung | Checks vs champion |
|---|---|
| `dev` | hill target **better**. Hill control within −5 pts. Every climbed hill within −3 pts |
| `random50` | within −2 pts |
| `random100` | within −1 pt |
| `full` | **better**: this is what makes a new champion |

The middle rungs are "not worse" on purpose: a targeted fix often shouldn't move a random slice, and requiring
"better" on 50 examples is a coin toss. See [`PROTOCOL.md`](PROTOCOL.md).

# Demo

```bash
git clone https://github.com/asvskartheek/autoresearch-scaffold && cd autoresearch-scaffold
python3 examples/demo/seed.py demo-project      # v5 → v6 → v7 promoted, v8b rejected, v8 mid-ladder
cd demo-project
PYTHONPATH=.. python3 ../examples/demo/live.py &  # a live eval, a training run and a data job
PYTHONPATH=.. python3 -m autoresearch.cli up
```

Scores in the demo are simulated. Nothing calls a model.

# Layout

```
research.json          ladder, thresholds, KPIs
AGENTS.md  PROTOCOL.md rules for agents, and the research method
.research/             the ledger: datasets, slices, hills, models, decisions, tasks/<id>/{task.json, metrics, rows, events}
autoresearch/          ledger, gates, task tracker, evaluate(), dashboard server
```

The ledger is plain JSON / JSONL, so agents, scripts and the dashboard all read the same files. Gate results are never
stored; they are recomputed from finished evals every time. Rows hold ids, scores, cost and latency only, not prompts or outputs.

# License

MIT
