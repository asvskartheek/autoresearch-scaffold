# Slices and datasets

A **slice** is a frozen list of example IDs from one dataset, with a hash. Every score in ARX names its slice.

## Why freeze IDs?

Two scores are only comparable if they were computed on the same examples. "71% vs 68%" on different subsets says
almost nothing; a few hard examples in or out move the number more than most changes do. Freezing the ID list and
hashing it makes "same examples" checkable, and the gate ladder only ever compares runs whose `slice_hash` matches
the slice's current hash.

## Datasets

```bash
arx dataset add gsm8k --size 1319 --url https://huggingface.co/datasets/openai/gsm8k
arx dataset add qa --ids-file qa_ids.txt --random 50 100 200 --seed 7
```

This registers the dataset and freezes:

- `gsm8k/full`: every ID.
- `gsm8k/random50`, `gsm8k/random100`: seeded random draws, **nested**: `random50` is the first 50 of `random100`.
  Nesting means a candidate that has run `random100` has implicitly been seen on `random50`'s examples, and the two
  rungs never disagree about which examples are "random".

The first dataset you add becomes `primary_dataset` in `research.json`. Slice names without a `/` are resolved
against it, so `random50` means `gsm8k/random50`.

`--ids-file` takes one ID per line, or a JSON list of IDs or of `{"id": ...}` objects. `--size N` uses IDs `0..N-1`.

## Dev, control and synthetic slices

```bash
arx slice add dev-arith   --ids-file arith_ids.txt   --kind dev --description "Arithmetic slips" --hill arith
arx slice add dev-control --ids-file control_ids.txt --kind control
arx slice add dev-please  --ids-file probes.json     --kind synthetic --metric "agreement with/without 'please'"
```

`--metric` says what `score` means on this slice when it is not plain accuracy.

A score is 0 or 1 per example unless you say otherwise. A hill about speed, cost or length is not binary: freeze its
slice with `--scale continuous` (and `--unit s`), and score each row with the number itself, signed so that higher is
better (minus seconds, not seconds).

```bash
arx slice add slow-target --ids-file slow.json --kind dev --scale continuous --unit s \
    --metric "minus the seconds the agent took; a faster run scores higher"
```

The dashboard then shows the mean score, the signed delta in that unit, and better/worse counts per example, in place of
"solved" counts. A slice with no `--scale` is read off its scores: all 0/1 means binary.

## Never edit a frozen slice

Adding a slice under an existing name with different IDs fails:

```text
slice gsm8k/dev-arith is frozen with different ids; create a new slice name
```

Re-adding with the *same* IDs is a no-op, so scripts can be re-run safely. To change a slice, make a new one
(`dev-arith-v2`). Old runs keep pointing at the old hash, so history stays interpretable.

## Where the data lives

The ledger keeps IDs and a URL, not the examples. Datasets and large slices belong on Hugging Face as **private**
repos; put the URL on the dataset or slice.
