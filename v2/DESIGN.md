# arx2: the research bridge

One ledger, two faces. Agents write to it through a CLI built for agents (AXI). People read the same
ledger through one dashboard built for thorough understanding. Nothing is shown to a person that the
ledger cannot back with a row.

## The research loop it models

1. **Task**: what the model does, in one sentence.
2. **Measure**: how one output becomes one number (pass/fail or a quantity), and whether higher or lower is better.
3. **Eval sets**: frozen lists of item ids, each with a short name and a hash.
4. **Goal**: a vague wish refined into a precise statement: `metric(champion, set) >= target`.
5. **Annotations**: free text on failing items, answering "what in the input makes the output wrong".
6. **Patterns**: annotations grouped by cause. Each pattern has a **symptom set** and a prevalence.
7. **Hills**: a pattern worth fixing. A hill owns its own eval sets and training sets. Symptom set,
   hill eval sets and training sets must share **zero** items; the check is live and always shown.
8. **Ladder**: an ordered, cheapest-first list of rungs a candidate must pass to become champion.
   Each rung is a set plus a rule: `improve`, `hold` (do not get worse), `at_least`, `at_most`.
9. **Candidates**: a change on top of a parent, with a prediction written before it runs.
10. **Runs**: rows of `id, score, cost, latency, error`, streamed as they finish.

## Storage

```
<project>/.arx2/
  events.jsonl        append-only; every change to the project is one event
  rows/<run>.jsonl    eval rows, appended as they finish (streamed live to the dashboard)
  docs/<key>.*        papers, notes, diagrams (html, md, svg)
  learner.jsonl       what the person did on the dashboard (views, dwell, card reviews)
~/.arx2/projects.json one registry, one dashboard for every project
```

State is a fold over `events.jsonl`, so the dashboard can show the project at any past moment.

## Names

Every entity has a `key` (stable, machine) and a `name`: at most two plain words, no symbols like `+`
or `/`. The CLI refuses longer names. The dashboard never shows a key where a name exists.

## Statistics

Comparisons are paired on shared item ids. Pass/fail uses the Agresti–Min adjusted interval for a paired
difference, which stays wide when n is tiny (three wins out of three is not "solid"). Quantities use a
paired t interval. Intervals are 90%.
