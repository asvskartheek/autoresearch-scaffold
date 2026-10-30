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

- Names are one or two plain words a person remembers ("Route Tracing", "Random 50"). Keys can be anything; people never see them.
- Every job longer than a minute is a task (`arx2.task(...)` or `arx2 task start`). Note decisions as plain sentences.
- Never edit a frozen set; make a new one. Rows hold only id, score, cost, latency_s, error.
- Write cards for facts a person must not forget: `arx2 card add --front ... --back ...`. Papers: `arx2 doc add <key> --kind paper --audience internal|external`.
- Read `arx2 learner` now and then: it says which names the person keeps hovering and which cards they miss. Make those clearer.
