# Budgets

A task can carry a wall-clock cap, `budget_s`. ARX keeps the clock: a sub-task is held to the tightest cap above it,
and a task stopped by its budget ends with status `budget`.

## Why ARX keeps the clock

Agents running sweeps are bad at stopping. A separate timer next to the loop does not know about the evals a
sub-task launched or the time its parent has left. Putting the cap on the task means one number, visible on the
card, that every nested eval and sub-task is held to.

## Python

```python
import autoresearch as ar

with ar.task("experiment", "prompt sweep", budget_s=1800) as t:
    while t.ok():                                        # False once time is up, here or in any ancestor
        ar.evaluate(next_prompt(), "dev-arith", run_one) # each eval stops at the sweep's remaining time
```

Or raise instead of looping:

```python
with ar.task("experiment", "search", budget_s=600) as t:
    for cand in candidates:
        t.check()                 # raises BudgetExceeded; the card ends as "budget", not "failed"
        try_one(cand)
```

| Call | Does |
|---|---|
| `t.left()` | Seconds left, the tightest over this task and its ancestors. `None` if nothing in the chain has a budget. |
| `t.ok()` | `True` while `left()` is `None` or `> 0`. |
| `t.check()` | Raises `BudgetExceeded` once time is up. |

## Shell

```bash
id=$(arx task start --title "sweep" --budget-s 1800)
while arx task left $id; do           # prints e.g. "912.4s" or "unlimited"; exits 3 once time is up
    ./try_one.sh
done
arx task finish $id --status budget
```

## Inside `evaluate`

`evaluate(..., deadline_s=)` treats its deadline as the eval's time budget, and also honours whatever time its
parent has left. It submits work **lazily**: at most `workers` examples are in flight, and before each submission it
checks `t.left()`. Once time is up it stops submitting and stops waiting; every unfinished example becomes an error
row (`error="deadline"`, score 0), so the run is marked incomplete and never ranked.

## What to know

- **Time budgets are cooperative.** They are measured from the task's `created` timestamp and enforced only when you
  check (`ok()`, `check()`, `arx task left`, or inside `evaluate`). Nothing kills your process.
- **Nesting:** a sub-task never outlives its parent's budget, because `left()` walks the whole ancestor chain.
- `BudgetExceeded` raised for a *parent's* budget is not swallowed by the child: the child finishes as `budget`,
  and the exception keeps unwinding to the task whose budget it was.

## Money budgets: not yet

There is no `budget_usd`. ARX can't see cost: it never calls your model, so it only learns what a call cost if the
harness reports it, and most harnesses report nothing or report it late. A money cap that silently counts $0 would
look like a guardrail without being one. Row `cost` is still recorded and shown on leaderboards, but it does not
count against anything. The open design question is tracked in
[issue #6 "Money budgets for tasks"](https://github.com/asvskartheek/autoresearch-scaffold/issues/6).

!!! note
    Budgets were added in PR #5 (`task-budgets`). These docs describe that branch.
