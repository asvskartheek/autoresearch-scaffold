# Research protocol

How a model or agent goes from V7 to V8. Every auto-research project follows this; `research.json` holds the
project-specific numbers.

## Vocabulary

| Term | Meaning |
|---|---|
| **Dataset** | A full eval set (e.g. `qa`, 1,000 examples). Its ID list is frozen once. |
| **Slice** | A frozen list of example IDs from one dataset, with a hash. Every score names its slice. |
| **Random slice** | `random50`, `random100`: seeded draws. Nested: `random50` is the first 50 of `random100`. |
| **Goal** | The outward claim: a target KPI on one slice, usually a full slice ("96% on gsm8k/full, n = 1319"). Hills serve it. It gets the public paper. |
| **Hill** | A specific weakness found in the champion ("V7 flips answers when the prompt says *please*"). |
| **Target slice** | The slice that measures one hill. Small (20–60), targeted, often synthetic. Its score can be a custom metric (e.g. agreement with/without *please*), binary or continuous: set `--scale continuous` (and `--unit`) on a slice whose score is a number such as minus seconds; the default is 0/1. |
| **Control slice** | A small random slice evaluated with every target slice, to see the overall effect. |
| **Champion** | The model with the best full-dataset score. Every candidate is compared with it. |
| **Candidate** | A new version (V8) that claims to climb one hill. |
| **Gate** | A rung of the ladder. A candidate runs a rung only after passing the one below. |

## Goals

A project fights for one or more goals. A goal is fixed when it opens: the KPI, the slice (and its hash), the target
and the starting champion (`baseline`). It is open, achieved or abandoned.

```
arx goal open gsm8k-96 --title "GSM8K at 96%" --slice gsm8k/full --target 0.96
arx hill open time-rate ... --goal gsm8k-96      # or: arx hill explain <hill> --goal gsm8k-96
arx goal status [gsm8k-96]                         # champion's value, gap, paired delta vs the baseline, hills
arx goal achieve gsm8k-96                          # refused until the champion meets the target on the goal slice
arx goal abandon gsm8k-96 --reason "..."
```

- The value is the champion's score pooled over every complete run on the goal slice, like the gates. Cost and
  latency KPIs are lower-is-better (`--kpi latency_p50`).
- `achieve` freezes the evidence: model, eval run, value, n, and the paired delta vs the baseline. Later promotions
  do not change it. A met target on a dev or random slice never achieves a goal.
- Hills are internal debugging. They find and fix the weaknesses that stand between the champion and the goal.

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
7. **Re-baseline.** Promotion runs `arx baseline` for the new champion: slices it already ran as a candidate are
   reused, and it runs every other hill target/control and dataset slice with `baseline_cmd` from `research.json`
   (e.g. `"python eval.py --model {model} --slice {slice}"`). Without one, it lists what to run. Re-run any time;
   after a harness or judge change use `arx baseline --replace` so old numbers stop counting.

## Explaining a hill

A hill's page must make the weakness obvious at a glance to someone who missed the chat. Right after opening it:

```
arx hill explain arith \
  --symptom "The reasoning is right but a calculation is wrong." \
  --example-input "A shirt costs $18 and is 25% off. What is the price?" \
  --example-wrong "18 × 0.25 = 4.2, so 18 − 4.2 = 13.8" \
  --example-right "18 × 0.25 = 4.5, so 18 − 4.5 = 13.5" \
  --example-why "Right plan, wrong multiplication." \
  --measure "A problem counts as solved when the final number equals the reference answer." \
  --share 63/495 --share-of "of v1's wrong answers on full contain a false equation"
```

- `--symptom`: one plain sentence about the model's behaviour. No jargon, no slice names, no expectations.
- `--example-*`: one short, typical case: the question, what the model answered, the correct answer, and why
  it went wrong. Each call adds one; give 2–3 (or `--examples-file` with a JSON list). Write illustrative
  paraphrases, never client text, trimmed to the part that shows the failure.
- `--measure`: a full sentence saying when one target example counts as solved.
- `--share` and `--share-of`: how many failures this hill explains, out of what (`63/495` with
  "of v1's wrong answers on full contain a false equation"). Real counts from the error analysis only.
- Pre-declared expectations stay in `--problem`; they are shown folded under the hill.

## Papers

Two kinds, one reader (`/papers/<name>`):

- **Goal paper** (public). One per goal, named after the goal: `arx paper add <goal> --goal <goal>`. It is the
  outward-facing write-up: the goal, the final result and why it holds. Keep it as a labelled draft while the goal
  is open; finish it when the goal is achieved; when a goal is abandoned, say so and report the negative result.
- **Hill paper** (internal). One living paper per hill, named after the hill: `arx paper add <hill> --hill <hill>`.
  Debugging notes for us: every candidate, every rejection. Write it on promote and on hill close (negative results
  too), and keep it current while the hill is open. The dashboard and the goal paper label it internal.

Never start a second paper for the same goal or hill: republish with `arx paper edit <name> --file paper.html`.
Check every page before every publish: `arx paper check --file paper.html` (goal papers: add `--goal <goal>`).

### Non-negotiables

`arx paper check` enforces what a machine can see; the rest is on the author.

- [ ] **Ledger numbers only.** Every number comes from `.research/`, names its slice and n (`full, n = 1319`), and a
      comparison is a paired delta vs the champion with its 90% interval. Noisy deltas are called noisy. For a
      continuous hill, give the unit and direction (`p50 latency, ms, lower is better`).
- [ ] **A visual carries each claim.** Any section that states a number has a figure (SVG, canvas, image, poster)
      where the reader can find it without the prose.
- [ ] **Prose budget.** At most 100 words of prose per section and 50 per paragraph. Prose captions; it never
      carries the argument. A long paper is fine; a wall of text is not. Split the idea into more sections.
- [ ] **Anchors.** `data-block="<id>"` on every `<section>`, `<p>` and `<figure>`, unique: comments anchor to them.
- [ ] **Something to do.** At least one explorable the reader drives (input, button, select, details, canvas).
- [ ] **Recall.** A `remember` section (`<section data-block="remember">`) for long-term recall, progress in
      `localStorage` under a key of this paper's own, and at least one quiz (`class="quiz"`) whose answer explains why.
- [ ] **Theme.** Dark mode under `:root[data-theme="dark"]` (the reader sets it); no serif fonts; no pill bubbles.
- [ ] **Safe.** Self-contained HTML (inline CSS and JS). No client text, answers or traces: ids, categories, paraphrase.
- [ ] **Goal papers** also need: a `result` section with the goal KPI, its slice and `n = <n>`, the target, the
      champion's ledger value and the paired delta vs the starting champion with its 90% interval; a link to every
      internal hill paper (`<a class="internal" href="../<hill>" target="_top">`); "draft" while the goal is open,
      "abandoned" if it was. No dev-slice number is the claim.

### Freedom

Everything else is the author's call: structure, section names, order, length, narrative, widget types, palette
within the theme. There is no fixed section list. Pick the shape the finding needs: a mystery solved in steps, a
simulator with commentary, a gallery of failures, a single explorable with a long caption, a timeline of attempts.
`arx paper new` writes a worked example (gsm8k, real numbers): it is one possible shape, not a template. Two papers
from one project should not look alike.

### Building intuition

Readers are serious researchers. They want the mechanism in their hands, not a summary of it. Illustrating a
number is not enough; let them find it. Patterns that work:

- **Explorable explanation.** The reader turns the knob of the mechanism (a threshold, a budget, a step count) and
  watches the outcome change, using the real per-example rows.
- **Predict, then reveal.** Ask the reader to guess (a slider, a choice) before showing the ledger value. A wrong
  guess teaches more than a right caption.
- **Simulate the failure.** Replay how the baseline breaks, step by step, on a paraphrased example, then the fix.
- **Per-example drill-down.** A grid of example ids; click one to see where each model won or lost.
- **Counterfactual toggle.** Turn a component off and see which examples flip, and by how much the score moves.
- **Build it step by step.** Introduce one piece of the concept at a time; each step adds to the same figure.

One strong explorable that builds the core intuition beats five decorative widgets. Build it first; write the
captions last. Prose: ASD-STE100, short sentences, active voice, define jargon.

Review loop:
- People select text and comment. `arx paper poll` blocks until someone waits on you, in any paper, and prints one
  JSON line per thread with the whole thread (`paper`, `thread`, `quote`, `block`, `messages`, `mention`). Any
  person's message in an open thread waits on you; `@agent` summons you even on a resolved thread. The page shows
  "thinking…" from then on.
- Answer every thread: `arx paper reply <paper> <thread> "text"`. If the answer changes the paper, republish it first
  and link to the changed block (`--link "§4=#win-1"`). If the answer is its own page (a chart, a poster), reply with
  `--file page.html`: it opens next to the thread. External sources: `--link "label=https://…"`.
- `arx paper resolve <paper> <thread> ["note"]` when done. Keep polling while people review.

## Rules of evidence

- Compare only on identical ID sets. Gates use paired deltas on the same IDs, never scores from different slices.
- Errors, crashes and timeouts score 0. A partial run is never ranked.
- Report n, the paired delta and its 90% bootstrap interval. A delta whose interval spans 0 is shown as *noisy*;
  on 20–50 examples most deltas are. That is why the ladder widens before the claim does.
- Re-run the champion when the harness, judge, data or tools change. Old numbers do not transfer (`arx baseline --replace`).
- The target slice is used for development. It is never evidence of general improvement; the full rung is.
- Never show gold answers, gold sources or judge rationale to the system being evaluated.
- Primary KPIs travel together: score, cost per example, latency p50/p95. A win that triples cost is reported as such.

## Why "not worse" on the middle rungs

A hill fix (robustness to *please*) often should not move a random slice at all. Requiring "better" on 50 and
100 examples would turn the ladder into a coin toss and reject correct fixes. The middle rungs guard against
regressions cheaply; the full rung makes the claim. Change any rule in `research.json`.
