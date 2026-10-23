"""Auto-research scaffold: a ledger, a gate ladder and a live dashboard for improving models and agents.

    import autoresearch as ar

    with ar.task("train", "SFT v9 on politeness augmentations", model="v9") as t:
        for step in range(n):
            t.log(step=step, loss=loss, lr=lr)

    with ar.task("experiment", "sweep prompts", budget_s=1800) as t:
        while t.ok():                      # or t.check(): raises BudgetExceeded, card ends as "budget"
            try_next_prompt()              # sub-tasks and evals inherit the tighter time cap

    ar.evaluate("v9", "dev-please", run_one)   # run_one(id) -> {"score": 1.0, "cost": 0.002}
    print(ar.gate("v9"))
"""
from .core import BudgetExceeded, Project, Task, evaluate as _evaluate, summarize, paired

_project = None


def project(root=None) -> Project:
    global _project
    if root is not None or _project is None:
        _project = Project(root)
    return _project


def task(kind: str, title: str, **kw) -> Task:
    """kind: eval | train | experiment | data | analysis. Use as a context manager or call .finish()."""
    return Task(project(), kind, title, **kw)


def evaluate(model: str, slice: str, run_one, **kw) -> Task:
    return _evaluate(project(), model, slice, run_one, **kw)


def gate(model: str) -> dict:
    return project().gate(model)


__all__ = ["BudgetExceeded", "Project", "Task", "project", "task", "evaluate", "gate", "summarize", "paired"]
