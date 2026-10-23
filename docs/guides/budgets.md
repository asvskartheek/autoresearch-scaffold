# Budgets

A task can carry a money cap (`budget_usd`), a wall-clock cap (`budget_s`), or both. ARX keeps the books: spend rolls
up the task tree, sub-tasks are held to the tightest cap above them, and a task stopped by its budget ends with
status `budget`.

## Why ARX keeps the books

Agents running sweeps are bad at stopping. A separate cost counter next to the loop drifts from what was actually
spent and does not know about the evals a sub-task launched. Putting the cap on the task means one number, visible
on the card, that every nested eval and sub-task charges against.

## Python

```python
import autoresearch as ar

with ar.task("experiment", "prompt sweep", budget_usd=5, budget_s=1800) as t:
    while t.ok():                                        # False once money or time is gone, here or above
        ar.evaluate(next_prompt(), "dev-arith", run_one) # row costs roll up into the sweep
```

Or raise instead of looping:

```python
with ar.task("experiment", "search", budget_usd=2) as t:
    for cand in candidates:
        t.check()                 # raises BudgetExceeded; the card ends as "budget", not "failed"
        t.spend(score(cand))      # report money you spent outside evaluate
```

| Call | Does |
|---|---|
| `t.spend(usd)` | Charge money to this task and every ancestor. |
| `t.log(..., cost=x)` | Same as `spend(x)`, plus a point on the `cost` series. |
| `t.left()` | `{"usd": ..., "s": ...}`: the remaining amount, tightest over this task and its ancestors. A missing key means unlimited. |
| `t.ok()` | `True` while every remaining value is `> 0`. |
| `t.check()` | Raises `BudgetExceeded` once any is `<= 0`. |

## Shell

```bash
id=$(arx task start --title "sweep" --budget-usd 5 --budget-s 1800)
while arx task left $id; do           # prints {"usd": .., "s": ..}; exits 3 once spent
    ./try_one.sh && arx task spend $id 0.12
done
arx task finish $id --status budget
```

## Inside `evaluate`

`evaluate(..., budget_usd=, deadline_s=)` treats its deadline as a time budget and also inherits whatever its parent
has left. It submits work **lazily**: at most `workers` examples are in flight, and before each submission it checks
`t.left()`. Once money or time is gone it stops submitting; every example not finished becomes an error row
(`error="budget"` or `"deadline"`, score 0), so the run is marked incomplete and never ranked.

## What to know

- **Cost is only known when the harness reports it**: row `cost`, `log(cost=)` or `spend()`. A harness that reports
  nothing spends nothing, as far as ARX can tell.
- **Time budgets are cooperative.** They are measured from the task's `created` timestamp and enforced only when you
  check (`ok()`, `check()`, `arx task left`, or inside `evaluate`). Nothing kills your process.
- **Overshoot is bounded by concurrency.** Calls already in flight finish, so spend can overshoot by up to `workers`
  examples.
- **Nesting:** a sub-task never outspends its parent, because `left()` walks the whole ancestor chain.
- `BudgetExceeded` raised for a *parent's* budget is not swallowed by the child: the child finishes as `budget`,
  and the exception keeps unwinding to the task whose budget it was.

!!! note
    Budgets were added in PR #5 (`task-budgets`). These docs describe that branch.
