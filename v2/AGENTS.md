# Working with arx2 (for agents)

Run `arx2` with no arguments first. It prints this project's state and the next commands to run.
Every command prints compact text with a `help[]` block of next steps; errors print `fix:` with the command that fixes them.

## The loop

1. `arx2 init --name "<two words>" --task "<what the model does>" --measure "<how one output is scored>"`, then `arx2 up`
   and give the person the dashboard URL.
2. Freeze sets: `arx2 set add <key> --name "<two words>" --dataset <d> --role full|random|eval|symptom|hill|train|control --ids-file ids.txt`.
3. Turn the wish into a goal: `arx2 goal open <key> --name "<two words>" --vague "<the wish as said>" --set <set> --target 0.9`.
4. Read failing outputs and write what in the input makes each one wrong: `arx2 annotate <item> "<text>" --set <set>`.
5. Group annotations: `arx2 pattern add <key> --name ... --items 3,7,9 --cause "<one sentence>" --count 15 --of 57 --of-what "wrong answers"`.
6. Open a hill from a pattern. Its symptom set, eval sets, training sets and control must share no item; the command refuses otherwise.
7. Set the ladder once (`arx2 ladder ladder.json`), cheapest step first. Rules: `improve`, `hold` (with `tol`), `at_least`, `at_most`.
8. Each candidate: `arx2 cand add <key> --name ... --hill <hill> --change "<what changed>" --predict "<what should move, by how much>"`.
9. `arx2 gate <cand>` names the next run. Run it with `arx2.evaluate(cand, set, run_one)`; rows stream to the dashboard as they finish.
10. Promote or reject with the step, set, n, gain and interval in the reason.

## Rules

- Run `arx2 verify` before reporting any result, and fix every error. `arx2 rules` lists what it enforces and why.
- Names are one or two plain words a person remembers ("Route Tracing", "Random 50"). Keys can be anything; people never see them.
- Every job longer than a minute is a task (`arx2.task(...)` or `arx2 task start`). Note decisions as plain sentences.
- Never edit a frozen set; make a new one. Rows hold only id, score, cost, latency_s, error.
- Write cards for facts a person must not forget: `arx2 card add --front ... --back ...`. Papers: `arx2 doc add <key> --kind paper --audience internal|external` (see Papers below).
- Read `arx2 learner` now and then: it says which names the person keeps hovering and which cards they miss. Make those clearer.

## UI

- Dashboard text: labels of at most three words, no sentences about data; the test enforces it.

## Papers

A paper is published only when it is complete, self-contained and backed by the ledger. `arx2 doc add --kind paper`
runs the gate and refuses on any error; `arx2 paper check <file> --about <key>` runs it without publishing.

- Start from `arx2 paper new <key> --about <goal-or-hill>`: every section, the theme head, and the champion's
  numbers already written as claims. Replace every TODO.
- External (about a goal): abstract, introduction, setup, method, results, what did not work (`negative`), threats to
  validity, conclusion. Internal (about a hill): problem with one real item (`data-item="<id>"`), measure, sets,
  candidates, result, next. Use `<section data-part="...">` or `<h2>` headings; an `appendix` part is allowed.
- Self-contained: no outside scripts, images or fonts; only `/static/app.css` may be linked. A `<title>`, an `<h1>`,
  `<meta name="color-scheme" content="light dark">`. Results open with a figure (inline `<svg>` or `<figure>`).
- Every number in abstract, results and conclusion is a claim the gate recomputes from the rows:
  `<span data-claim="score" data-run="<run>">74.3%</span>` (`data-metric="latency_p50|cost"` for other summaries),
  `data-claim="delta" data-base-run data-run [data-lo data-hi]`, `data-claim="n" data-set`,
  `data-claim="count"` (`data-run` for passed items, `data-base-run` + `data-run` for fixed or broken, `data-of`
  for the denominator), `data-claim="target" data-goal [data-unit="count" [data-run]]`. Numbers inside an `<svg>` are exempt
  from the bare-number rule. Name the set and its n in the same sentence or caption.
- Short: abstract at most 80 words; sections 120 to 200; the paper at most 1,500 words of prose (hill papers half).
- A goal the ledger has not met: the title or abstract says Draft, and the word "achieved" never appears.
- `--draft` lets an unfinished paper through (missing sections or figures) when its title says Draft; the dashboard
  marks it draft. Wrong numbers and outside resources are never let through.

## Answering questions

People press `A` (or **Ask**) on the dashboard, click anything and type a question. Each one is an `ask` event
anchored to what they clicked. Keep one agent listening while people use the dashboard:

```
arx2 ask poll --agent <name>                  # in an agent session: answer it, then poll again
arx2 ask watch --jobs 4 --exec 'claude -p "$(cat "$ARX2_ASK_FILE")" --allowedTools Bash \
  $([ "$ARX2_ASK_TURN" = 1 ] && echo --session-id || echo --resume) "$ARX2_ASK_SESSION"'   # headless, always on
```

Every question is a thread: the person can ask more under any answer, and the question opens again. Each thread has
its own agent. `watch` runs one agent per question, several at once, and sends a follow-up back to the same agent
(`$ARX2_ASK_SESSION` is stable per question, `$ARX2_ASK_TURN` counts the person's turns). `poll --agent <name>` gets
follow-ups on threads it answered first, and never takes another live agent's thread.

`poll` blocks until a question is open, claims it and prints it with the clicked thing (`clicked:`), its entity,
the earlier turns (`thread[]`) and the facts and run keys around it. Answer with `arx2 ask answer <id>` and any mix of parts, shown in the order given:
`--text` (markdown), `--file` (svg, png, html, md) and `--link "Label=#/hill/<key>"` (a dashboard view; keys may
contain `/`). `arx2 ask list` shows what is waiting.

How to answer: a picture first, then a few words. People read answers next to the thing they clicked; walls of text
get skipped.
- Read the rows (`.arx2/rows/<run>.jsonl`, or `Views(p).rows(run)`) before you write a number.
- Lead with one figure that carries the numbers: the real items as squares (fixed, broke, both, neither), a paired
  delta with its interval, a small flow. SVG for a still picture, HTML when hovering or clicking shows the item ids.
  Use `currentColor` and the dashboard tokens (`var(--ink)`, `var(--champ)`, `var(--broke)`, `var(--mute)`), so it reads
  in light and dark.
- Then at most three short lines: the one real example (item id, what happened on each side), the aggregate (set, n,
  paired delta, 90% interval) and the takeaway. At most 60 words; past 30 the numbers must be in a figure. `ask answer` refuses otherwise.
- If the ledger cannot back a claim, say so in one line. "The ledger does not show this" is a good answer.
- Add a `--link` to the dashboard view that shows more, rather than describing it.
- Never paste client text, questions or model outputs into an answer; ids, counts and your own words only.

The person saves good answers as a note, card or paper; they then show on the entity's page and in the Library.

## Directives (@orchestrator)

A message that starts with `@orchestrator` (in the Ask box or under any answer) is a directive for the agent running
the research, not a question: "@orchestrator open a goal to hill climb on dev41". It is an `ask` event with
`to: "orchestrator"` and the same anchor. `arx2 ask poll` never hands it out; the orchestrating agent does:

```
arx2 orchestrator poll                         # blocks, claims the next directive, prints it with its anchor
arx2 orchestrator ack <id> --text "Opened goal dev41: #/goal/dev41"   # what you did or will do; at most 60 words
arx2 orchestrator list [--all]
```

A directive stays open until acked; a follow-up in its thread opens it again. `arx2` lists open directives first.
