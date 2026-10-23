# `arx run` manifests

`arx run` launches a reviewed command as a task and records what it produced. Use it when the harness is not Python,
or when an agent wants to run a command whose exact shape a human approved.

## Why a hash-pinned manifest?

An agent can rewrite a shell command between "here's what I'll run" and running it. A manifest is a JSON file pinned
by its sha256: you review the file, record the hash, and `arx run` refuses to execute anything else.

```json
{
  "title": "v2 on random100 via the TS harness",
  "argv": ["node", "harness/run.js", "--out", "out/rows.jsonl"],
  "cwd": ".",
  "deadline_s": 1800,
  "record_mode": "scored",
  "rows_path": "out/rows.jsonl",
  "frozen_inputs": [{"path": "data/questions.json", "sha256": "…"}],
  "paid": false,
  "artifacts": [{"label": "Outputs", "path": "out/"}]
}
```

```bash
shasum -a 256 m.json
arx run --manifest m.json --expected-sha256 <sha> --model v2 --slice random100 --dry-run   # validate only
arx run --manifest m.json --expected-sha256 <sha> --model v2 --slice random100
```

## What is checked before anything runs

- The manifest's sha256 equals `--expected-sha256`.
- `argv` is a non-empty list of strings. No shell strings, so no shell injection.
- Every `frozen_inputs` file still has its recorded sha256.
- `cwd`, `rows_path` and artifact paths stay inside the project.
- `deadline_s` is finite and positive.
- `paid: true` needs `--approve-paid` and a `budget_usd` in `(0, max_paid_usd]` from `research.json`.
- Scored runs need `--model` and `--slice`, and `rows_path` must not already exist, so stale rows are never scored.

## While it runs

The command runs in its own process group with `ARX_PARENT` set to the task's id (so anything it opens nests
under it), and the task heartbeats every 0.5 s. Past the deadline it gets SIGTERM, then SIGKILL after 5 s.
stdout and stderr go to `stdout.private.log` / `stderr.private.log` in the task directory; they never become rows.
The manifest bytes are copied into the task dir as `manifest.json`.

## Record modes

| Mode | Task kind | What is recorded |
|---|---|---|
| `scored` | `eval` | The command writes JSONL rows. Each slice ID gets exactly one row: unknown or duplicate IDs are dropped, a row with `error` becomes `harness_error` (score 0), a score outside `[0, 1]` becomes `invalid_score`, a missing ID becomes `missing_output`. Any of these fails the task. |
| `artifact_only` | `experiment` | No score. A zero exit code is not a score. |

The task fails on a non-zero exit, a timeout, a launch error or bad rows, and `arx run` exits 1.
