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
3. Adds `scratch/`, `.research/tasks/*/rows.jsonl`, `.research/server.json` and `.research/server.log` to `.gitignore`.
4. Registers the project in `~/.arx/projects.json` (`$ARX_HOME` overrides `~/.arx`), starts the dashboard
   (`arx up`; skip with `--no-serve`) and opens a running **Project setup** task.

Why a setup task? Setup is work too: installs, model downloads and data prep take time and fail in interesting ways.
Note each step on it (`arx task note <id> "downloaded weights"`) and finish it when the first eval can run.

## The dashboard: `arx up`

```bash
arx up            # prints http://127.0.0.1:8890 (or the next free port) and this project's /p/<key>/ URL
arx up --restart  # after upgrading
```

`arx up` is idempotent. It reads `.research/server.json`; if the recorded port answers, it prints the URL and
exits. Otherwise it starts `arx serve` as a detached process (its own session, logging to `.research/server.log`)
and records the new port and pid. The server only binds to `127.0.0.1`.

| View | Shows |
|---|---|
| Goals | Each target KPI: value now, gap, paired Δ vs the starting champion, the hills that serve it |
| Overview | Champion, candidate ladder, leaderboards by dataset and slice: score, Δ champion, errors, cost, p50/p95 |
| Workbench | A card per running task: progress, ETA, sparkline, heartbeat. Stalled tasks turn red |
| Task page | Every logged series as a chart, paired diff vs the champion, per-example strip, log, links |
| Models | Lineage and rungs; each gate check with its delta, CI and win/loss count |
| Hills | Each weakness as a card, with an example, how common it is and every attempt |
| Papers | Goal papers (public) and hill papers (internal), with comment threads |
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
