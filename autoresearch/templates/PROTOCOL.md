# Research protocol

How a model or agent goes from V7 to V8. Every auto-research project follows this; `research.json` holds the
project-specific numbers.

## Vocabulary

| Term | Meaning |
|---|---|
| **Dataset** | A full eval set (e.g. `qa`, 1,000 examples). Its ID list is frozen once. |
| **Slice** | A frozen list of example IDs from one dataset, with a hash. Every score names its slice. |
| **Random slice** | `random50`, `random100`: seeded draws. Nested: `random50` is the first 50 of `random100`. |
| **Hill** | A specific weakness found in the champion ("V7 flips answers when the prompt says *please*"). |
| **Target slice** | The slice that measures one hill. Small (20–60), targeted, often synthetic. Its score can be a custom metric (e.g. agreement with/without *please*). |
| **Control slice** | A small random slice evaluated with every target slice, to see the overall effect. |
| **Champion** | The model with the best full-dataset score. Every candidate is compared with it. |
| **Candidate** | A new version (V8) that claims to climb one hill. |
| **Gate** | A rung of the ladder. A candidate runs a rung only after passing the one below. |

## One research step

1. **Find the hill.** Error analysis on the champion's full run: cluster failures, name one. Open it:
   `arx hill open please-robust --title "Robust to politeness" --target dev-please --control dev-control`.
2. **Build the development set.** Target slice (real failures, synthetic probes, or both) plus a control slice.
   Run the **champion** on both first: that is the number to beat. Store large or private sets on Hugging Face
   (private) and put the URL on the slice.
3. **Pre-declare.** Write in the hill's `problem` what the change is expected to move and what would count as
   failure. Do not edit thresholds after seeing results.
4. **Build candidates.** One change per candidate. `arx model add v8 --parent v7 --hill please-robust --change "..."`.
   Several candidates can run in parallel (one per subagent / worktree).
5. **Climb the ladder** (`arx gate v8` always says what to run next):

   | Rung | Slices | Default rule vs champion | Cost |
   |---|---|---|---|
   | `dev` | hill target | **better** | tiny |
   |  | hill control | not worse (−5 pts) | tiny |
   |  | every climbed hill's target | not worse (−3 pts) | small |
   | `random50` | random50 | not worse (−2 pts) | small |
   | `random100` | random100 | not worse (−1 pt) | medium |
   | `full` | full dataset | **better** | large |

   A failed rung stops the candidate. Record why (`arx task note`) and either fix it as a new candidate or reject.
6. **Promote.** `arx promote v8` re-checks every rung, makes V8 the champion and marks the hill *climbed*.
   A climbed hill's target slice becomes a permanent regression check for every future candidate.

## Rules of evidence

- Compare only on identical ID sets. Gates use paired deltas on the same IDs, never scores from different slices.
- Errors, crashes and timeouts score 0. A partial run is never ranked.
- Report n, the paired delta and its 90% bootstrap interval. A delta whose interval spans 0 is shown as *noisy*;
  on 20–50 examples most deltas are. That is why the ladder widens before the claim does.
- Re-run the champion when the harness, judge, data or tools change. Old numbers do not transfer.
- The target slice is used for development. It is never evidence of general improvement; the full rung is.
- Never show gold answers, gold sources or judge rationale to the system being evaluated.
- Primary KPIs travel together: score, cost per example, latency p50/p95. A win that triples cost is reported as such.

## Why "not worse" on the middle rungs

A hill fix (robustness to *please*) often should not move a random slice at all. Requiring "better" on 50 and
100 examples would turn the ladder into a coin toss and reject correct fixes. The middle rungs guard against
regressions cheaply; the full rung makes the claim. Change any rule in `research.json`.
