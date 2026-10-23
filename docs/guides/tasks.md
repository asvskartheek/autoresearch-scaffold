# Tasks and the Workbench

A **task** is one job with a clear end: an install, a download, building a slice, an eval, a training run, an error
analysis. While it runs it is a card on the Workbench; when it ends it moves to the Archive with the same full page.

![Workbench](../workbench.png)

## Why everything is a task

Long work that nobody can see is the most expensive kind of research mistake: a job that died an hour ago, or one
that is quietly burning money. The rule is simple: **anything longer than a minute is a task, opened before the
work starts.**

What a task is *not*: the project's goal, a hill or a candidate. Those live in `research.json`, the hills and the
models. Never open one umbrella task for the whole effort and hang everything under it.

## From Python

```python
import autoresearch as ar

with ar.task("train", "SFT v3 on calculator traces", model="v3",
             description="LoRA r=16 on 4k calculator-augmented traces",
             config={"lr": 2e-4}) as t:
    for step, loss in training_loop():
        t.log(step=step, loss=loss, lr=sched.lr)     # one chart per series, automatically
    t.note("loss plateaued at step 1200; stopping early")
    t.link("Checkpoint", "https://huggingface.co/you/v3")
```

The context manager finishes the task as `done`, or as `failed` with the exception noted if the block raises.
Kinds are free-form; the usual ones are `eval`, `train`, `experiment`, `data`, `analysis` and `setup`.

## From a shell

```bash
id=$(arx task start --kind data --title "Download GSM8K" --total 1319)
arx task progress $id 400
arx task note $id "mirror was slow; switched to HF"
arx task link $id "HF dataset" https://huggingface.co/datasets/openai/gsm8k
arx task finish $id            # or --status failed
```

## Keeping a card readable

- Write the `description` for someone who missed the chat.
- The **latest note** is the line people read on the card. Keep it current.
- `progress(done, total)` drives the progress bar and the ETA. The server estimates rate over the last 15 minutes
  of progress samples (throttled to one every 5 s), so the ETA follows speed changes.

## Heartbeats and stalls

Every write (`log`, `note`, `progress`, `link`, `heartbeat`) refreshes the task's heartbeat. A `running` task with no
heartbeat for `stall_minutes` (default 10) is *shown* as `stalled` and turns red. Nothing is written: stalled is
computed on read. Fix it, or finish it as failed; never leave it.

## Nesting

Sub-work nests under the task that started it, so a sweep's evals appear under the sweep.

- In the **same process**: a task opened while another non-eval task is running becomes its child.
- In a **child process**: a running task exports `ARX_PARENT=<its id>`, so anything launched from it (a script,
  `arx task start`, `arx run`) nests automatically.
- From **anywhere else**: pass `parent=<id>` / `arx task start --parent <id>`.

Evals are leaves: they never become a parent. How this works is in
[Architecture](../architecture.md#task-nesting-via-arx_parent).

## Subagents

Each subagent gets its own task (`agent="<subagent name>"`), and one candidate per subagent or worktree.
