# Auto-research scaffold

Good defaults for any project that improves a model or agent against eval sets: a research protocol, agent rules,
a ledger, a gate ladder, and a live dashboard. Python stdlib only.

| File | What it is |
|---|---|
| `PROTOCOL.md` | How one research step works: hill → dev set → candidate → gate ladder → promotion |
| `AGENTS.md` | Rules every agent and subagent follows (`CLAUDE.md` imports it) |
| `research.json` | The project's ladder, thresholds and KPIs |
| `autoresearch/` | Ledger, gates, task tracker, `evaluate()`, dashboard server |
| `arx` | CLI over the same ledger |
| `.research/` | The ledger itself (created per project) |

## Install once

```bash
uv tool install --editable /path/to/autoresearch-scaffold   # puts `arx` on your PATH (`ar` is the system archiver)
```

## Start a project

```bash
arx init ~/code/my-research --name "QA agent"   # starts the dashboard and opens a "Project setup" task
```

Then from inside the new project:

```bash
arx dataset add qa --ids-file ids.txt --url https://huggingface.co/datasets/org/qa-eval   # freezes full, random50, random100
arx model add v1 --champion --change "Baseline"
arx up                                                                                    # dashboard again if it stopped
```

## One step, end to end

```bash
arx slice add dev-please --ids-file please_ids.txt --kind synthetic --metric "agree with/without please"
arx slice add dev-control --ids-file control_ids.txt --kind control
arx hill open please-robust --title "Politeness robustness" --target dev-please --control dev-control \
    --problem "Adding 'please' flips answers. Expect +20 pts on dev-please; nothing else moves."
arx model add v8 --hill please-robust --change "SFT on 4k politeness pairs" --link "Model=https://huggingface.co/org/v8"
arx gate v8          # names the next run: champion baseline first, then v8, rung by rung
arx promote v8       # only when every rung passes
```

```python
import autoresearch as ar

def run_one(example_id):                      # your harness; return a score in [0, 1]
    ...
    return {"score": 1.0, "cost": 0.003}

ar.evaluate("v8", "dev-please", run_one, workers=8, deadline_s=1800)

with ar.task("train", "SFT v8", model="v8", config={"lr": 2e-4}) as t:   # W&B-style curves on the Workbench
    for step, loss in loop():
        t.log(step=step, loss=loss, lr=lr)
    t.link("Checkpoint", "https://huggingface.co/org/v8")
```

Evals run elsewhere (cloud jobs, another harness) come in with `arx eval record --model v8 --slice random100 --rows rows.jsonl`.
Shell-only work uses `arx task start|log|note|link|progress|finish`.

## Dashboard

| View | Shows |
|---|---|
| Overview | Champion, the candidate ladder, leaderboards per dataset and slice (score, Δ champion, errors, cost, p50, p95) |
| Workbench | One card per running task with progress, live sparkline and heartbeat; stalled tasks turn red |
| Task page | Every logged series as a chart, paired comparison with the champion, per-example strip, log, links, setup |
| Models | Lineage and each version's rungs; a model page shows every gate check with its paired delta and 90% CI |
| Hills | Each weakness with its slices, and the regression matrix (every model × every hill) |
| Slices | Frozen ID sets with hash, seed, metric and Hugging Face link |
| Archive | Finished, failed and partial tasks, with the same full page |

## Demo

```bash
python3 examples/demo/seed.py demo-project               # v5 → v6 → v7, a rejected v8b, v8 mid-ladder
cd demo-project && PYTHONPATH=.. python3 ../examples/demo/live.py &   # live eval, training and data cards
.arx serve
```
