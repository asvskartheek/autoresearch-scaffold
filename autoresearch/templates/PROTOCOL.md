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
| **Target slice** | The slice that measures one hill. Small (20–60), targeted, often synthetic. Its score can be a custom metric (e.g. agreement with/without *please*), binary or continuous: set `--scale continuous` (and `--unit`) on a slice whose score is a number such as minus seconds; the default is 0/1. |
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

One living paper per hill, named after the hill (`/papers/<hill>`, `arx paper add <hill> --hill <hill>`). Never start
a second paper for the same hill: republish it with `arx paper edit <hill> --file paper.html`.

When to write it:
- When a candidate is promoted on the hill, and when the hill closes (solved, or abandoned with every candidate
  rejected: a negative result is written up the same way, with the reasons from the ledger).
- While the hill is open, after each gate result that changes the story. Say plainly that the work is in progress
  and what runs next (`arx gate <model>`).

Start from `arx paper new <hill>`: it writes `paper-<hill>.html`, a worked example (gsm8k, real numbers) that
carries the shared theme and every widget; replace its content with this hill's. Check the page with
`arx paper check --file paper.html` before every publish. The check enforces the rules below that a machine can see.

Checklist:
- [ ] Sections `abstract`, `problem`, `method`, `tried`, `win` (or `result`), `now`, `test`, `remember`.
- [ ] `data-block="<id>"` on every `<section>`, `<p>` and `<figure>`, unique. Comments anchor to blocks, replies link to them.
- [ ] Every section has a visual (inline SVG chart, poster, diagram) and something to do (slider, tabs, a reveal, a quiz).
- [ ] A pop quiz (`class="quiz"`) in most sections and a closing test: at least 3. Each answer explains why.
- [ ] A `remember` section for long-term recall: flip cards, number recall, ordering, explain-it-back; progress in
      `localStorage` so people can come back.
- [ ] Real numbers from the ledger only. Every number names its slice and n (`full, n = 1319`), with the paired delta
      and its 90% interval vs the champion. Noisy deltas are called noisy. For a continuous hill, give the unit and
      direction (`p50 latency, ms, lower is better`).
- [ ] ASD-STE100 prose: short sentences, one idea each, active voice, no jargon without a definition.
- [ ] The shared theme: Instrument Sans, Bricolage Grotesque for headings, JetBrains Mono for numbers; navy/teal/coral/gold;
      no serif fonts; no pill bubbles; dark mode under `:root[data-theme="dark"]` (the reader sets it from its toggle).
- [ ] Self-contained HTML (inline CSS and JS). No client text, answers or traces: paraphrase examples.

Review loop:
- People select text and comment. `arx paper poll` blocks until someone waits on you, in any paper, and prints one
  JSON line per thread (`paper`, `thread`, `quote`, `block`, `messages`). The page shows "thinking…" from then on.
- Answer every thread: `arx paper reply <paper> <thread> "text"`. If the answer changes the paper, republish it first
  and link to the changed block (`--link "§4=#win-1"`). If the answer is its own page (a chart, a poster), reply with
  `--file page.html`: it opens next to the thread. External sources: `--link "label=https://…"`.
- `arx paper resolve <paper> <thread> ["note"]` when done. Keep polling while people review.

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
