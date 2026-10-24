# Getting started

## Install

```bash
uv tool install git+https://github.com/asvskartheek/autoresearch-scaffold
```

This puts `arx` on your `PATH`. (It is not called `ar` because `ar` is the system archiver.)

### Or let your agent do it

Paste into Claude Code, Codex, Cursor or any coding agent:

```text
Install autoresearch-scaffold with `uv tool install git+https://github.com/asvskartheek/autoresearch-scaffold`,
then run `arx init <project-dir> --name "<what we are improving>"`. Read AGENTS.md and PROTOCOL.md in the new
project, give me the dashboard URL, and follow them for all research work from now on.
```

## `arx init`

```bash
arx init my-research --name "GSM8K · Qwen 0.8B"
cd my-research
```

`init` does four things, in this order:

1. Copies `AGENTS.md`, `CLAUDE.md`, `PROTOCOL.md` and `research.json` into the project (only those missing).
2. **Vendors** the `autoresearch/` package into the project, so `import autoresearch` works from the project's own
   Python environment without installing anything into it. Run `arx sync` after upgrading ARX to refresh the copy.
3. Adds `scratch/` and `.research/tasks/*/rows.jsonl` to `.gitignore`.
4. Writes the session hooks (`.claude/settings.json`), starts the dashboard (`arx up`) and opens a running **Project setup** task.

Why a setup task? Setup is work too: installs, model downloads and data prep take time and fail in interesting ways.
Note each step on it (`arx task note <id> "downloaded weights"`) and finish it when the first eval can run.

## The dashboard: `arx up`

```bash
arx up            # prints http://127.0.0.1:8890 (or the next free port)
arx up --restart  # after upgrading
```

`arx up` is idempotent: if this project's dashboard is running it prints the URL and exits; otherwise it starts
`arx serve` detached (logging to `.research/server.log`) and records the port and pid. The server only binds to
`127.0.0.1`, serves one project, and stops itself when idle. `arx ps` lists dashboards, `arx down` stops one. See
[The dashboard lifecycle](guides/dashboard.md).

| View | Shows |
|---|---|
| Overview | Champion, candidate ladder, leaderboards by dataset and slice: score, Δ champion, errors, cost, p50/p95 |
| Workbench | A card per running task: progress, ETA, sparkline, heartbeat. Stalled tasks turn red |
| Task page | Every logged series as a chart, paired diff vs the champion, per-example strip, log, links |
| Models | Lineage and rungs; each gate check with its delta, CI and win/loss count |
| Hills | Each weakness as a card, with an example, how common it is and every attempt |
| Slices | Frozen ID sets with hash, seed, metric and dataset link |
| Archive | Finished, failed and partial tasks |

## One research step

```bash
arx dataset add gsm8k --size 1319 --url https://huggingface.co/datasets/openai/gsm8k  # freezes full, random50, random100
arx model add v1 --champion --change "Baseline"

arx slice add dev-arith   --ids-file arith_ids.txt   --kind dev --description "Arithmetic slips"
arx slice add dev-control --ids-file control_ids.txt --kind control
arx hill open arith --title "Arithmetic slips" --target dev-arith --control dev-control \
    --problem "v1 sets up the problem right but miscalculates. Expect +15 pts on dev-arith; nothing else moves."

arx model add v2 --hill arith --change "Calculator tool call for every operation"
arx gate v2        # names the next run: champion baseline first, then v2, rung by rung
# ... run the evals it names ...
arx promote v2     # only after every rung passes
```

The full method, with the reasoning behind each step, is in the [hills](guides/hills.md) and
[gates](guides/gates.md) guides and in `PROTOCOL.md`.

## Try the demo

```bash
git clone https://github.com/asvskartheek/autoresearch-scaffold && cd autoresearch-scaffold
python3 examples/demo/seed.py demo-project      # v5 → v6 → v7 promoted, v8b rejected, v8 mid-ladder
cd demo-project
PYTHONPATH=.. python3 ../examples/demo/live.py &  # a live eval, a training run and a data job
PYTHONPATH=.. python3 -m autoresearch.cli up
```

Scores in the demo are simulated; nothing calls a model.
