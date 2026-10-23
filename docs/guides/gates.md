# The gate ladder

A candidate climbs a ladder of rungs against the champion. Each rung is a set of **paired comparisons on identical
IDs**. A candidate runs a rung only after passing the one below.

![Gate checks for a candidate](../model-v8.png)

## The default ladder

| Rung | Slices | Rule vs champion | Cost |
|---|---|---|---|
| `dev` | hill target | **better** | tiny |
|  | hill control | not worse (−5 pts) | tiny |
|  | every climbed hill's target | not worse (−3 pts) | small |
| `random50` | random50 | not worse (−2 pts) | small |
| `random100` | random100 | not worse (−1 pt) | medium |
| `full` | full dataset | **better** | large |

### Why "not worse" in the middle

A hill fix often *should not* move a random slice. Requiring "better" on 50 or 100 examples would make the ladder a
coin toss and reject correct fixes. The middle rungs guard against regressions cheaply; only `full` makes the claim.
And you only pay for `full` once the cheaper rungs have earned it.

### Why paired deltas

Comparing two means from independent runs mixes up "the candidate is better" with "this sample was easier". A
paired delta subtracts the champion's score from the candidate's **on each example**, then averages. ARX reports:

- `delta`: mean per-example difference (sign-flipped if `higher_is_better` is false),
- `lo`, `hi`: a 90% bootstrap interval (2,000 resamples, fixed seed, so it is reproducible),
- `wins` / `losses`: examples where the candidate did better / worse,
- `noisy`: true when the interval spans 0. On 20–50 examples most deltas are noisy; that is why the ladder widens
  before the claim does.

A `better` check passes when `delta > margin`; a `not_worse` check passes when `delta >= -tolerance`. The pass/fail
decision uses the point delta; `noisy` is shown so you do not over-read it.

## Using it

```bash
arx gate v2
```

```text
v2 vs champion v1
  dev        PENDING
      need_baseline  gsm8k/dev-arith     better +0.0
      need_run       gsm8k/dev-control   not_worse -5.0
  random50   LOCKED
  ...
next runs:
  v1 on gsm8k/dev-arith
  v2 on gsm8k/dev-control
```

Follow `next runs`, then ask again. Do not skip rungs. When every rung passes:

```bash
arx promote v2    # re-checks every rung, makes v2 champion, retires v1, marks the hill climbed
arx reject v8b --reason "dev-control −7 pts: calculator calls broke unit conversions"
```

Rejected candidates stay in the ledger with their reason. Negative results are results.

## Check states

| State | Meaning |
|---|---|
| `need_baseline` | The champion has no complete run on this slice (at the current hash). Run it first. |
| `need_run` | The candidate has no complete run on this slice. |
| `pass` / `fail` | Both runs exist; the rule was applied to the paired delta. |
| `needs_review` | A `manual` check: a human signs it off; it never passes on its own. |
| `champion` | This model *is* the champion. |

Rung states: `pass`, `fail` (stops the candidate; later rungs `locked`), `pending` (lists the next runs, later rungs
`locked`), `skipped` (no checks resolved, for example no climbed hills yet).

How gates are computed from the ledger is in [Architecture](../architecture.md#how-gates-are-derived). Customise the
ladder in [`research.json`](../reference/config.md).
