# Goals

A goal is the number the work is for: one KPI, one target, on one frozen slice. Hills serve a goal; the gate ladder
decides champions; the goal says when the effort is done.

```bash
arx goal open gsm8k-96 --title "GSM8K at 96%" --slice gsm8k/full --target 0.96 \
  --problem "the product needs 96% on held-out maths"
arx hill open percent-base --goal gsm8k-96 --title "Percent of the wrong base" --target percent-dev
arx goal status [gsm8k-96] [--json]      # value now, gap, Δ vs the starting champion with a 90% CI
arx goal achieve gsm8k-96 [--note "..."]  # refused unless the champion's ledger run meets the target
arx goal abandon gsm8k-96 --reason "..."  # negative results stay in the ledger
```

| Flag | Meaning |
|---|---|
| `--kpi` | `score` (default), `cost`, `latency_p50`, `latency_p95` |
| `--lower-is-better` | for cost and latency targets |
| `--baseline` | the starting champion the paired delta is measured against (default: the champion now) |
| `--force` | achieve without the target met; the record says so |

Rules:

- A goal is not a task. Its evidence is always computed from ledger runs on the goal's slice, never typed by hand.
- If the slice behind a goal changes, the goal shows **slice changed** and cannot be achieved.
- Every goal has one public paper (see [Papers](papers.md)).
