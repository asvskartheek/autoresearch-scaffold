"""Display-only cleanup for notes an agent wrote with the spaces squeezed out ("audit1319:95wrong,34cap hits").
The ledger keeps the raw text; the dashboard shows this. Identifiers (anything with - _ / . or inner capitals) are left
alone, and nothing is ever reworded: only spaces are added."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_DICT = Path("/usr/share/dict/words")
_COMMON = set("""a an and are as at be but by for from has have if in into is it no not of on or per same so than that the
then this to up was with without all any each every only also more less over under after before vs""".split())


# research vocabulary the system dictionary lacks
_VOCAB = set("""box boxed answer answers numeric line lines token tokens eval evals prompt prompts greedy parse parses parsed
config dataset datasets baseline checkpoint checkpoints seed seeds slice slices rung rungs gate gates champion candidate
candidates score scores scorer rescore rescored run runs rerun reran train trained training finetune lora sft rlvr rl
batch batches epoch epochs loss lr warmup decode decoding sampler sampling temperature format formatting truncation
truncated cap caps hit hits miss missing wrong right fixed broke climb climbed hill hills control dev full random synthetic
engine comparator raw global local fresh same simple diagnostic diagnostics audit audits headroom policy inference vote
votes voting majority output outputs input inputs model models merge merged adapter adapters vllm cache cached latency
cost costs error errors retry retries timeout timeouts queue queued job jobs worker workers gpu gpus cpu memory oom
max min mean median p50 p95 ci delta deltas paired noisy noise pts acc accuracy pass fail passed failed promote promoted
reject rejected verify verified complete incomplete partial benchmark benchmarks leaderboard regex json schema tool tools
agent agents trace traces retrieval context chunk chunks page pages table tables tag tags valve valves pump pumps unit units
readout handoff inline rollout workflow walkthrough timestep codebase backend frontend endpoint runtime subtask offline
online upstream downstream tradeoff lookup pipeline toolchain overfit underfit dropout dataloader tokenizer prefill
""".split())
_TECH = re.compile(r"(?:base|sha|u?int|float|fp|bf|utf|ipv|md)\d+", re.I)  # base64, sha256, bf16: one word


@lru_cache(maxsize=1)
def _words() -> frozenset:
    try:
        return frozenset(w.lower() for w in _DICT.read_text().split() if len(w) > 2 or w.lower() in _COMMON) | _COMMON | _VOCAB
    except OSError:
        return frozenset(_COMMON | _VOCAB)


@lru_cache(maxsize=65536)
def _is(w: str) -> bool:
    """A word, or a regular inflection of one (boxed, parses, matching, numerically)."""
    W = _words()
    if w in W:
        return True
    for suf, back in (("ies", ("y",)), ("ing", ("", "e")), ("ed", ("", "e")), ("es", ("",)), ("s", ("",)), ("ly", ("",)), ("er", ("", "e")), ("al", ("",))):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[: -len(suf)]
            if any(stem + b in W for b in back) or (suf == "s" and stem in _VOCAB):
                return True
            if suf in ("ing", "ed", "er") and len(stem) >= 4 and stem[-1] == stem[-2] and stem[-1] not in "aeiou" and stem[:-1] in W:
                return True  # planned, stopping, runner
    return False


@lru_cache(maxsize=4096)
def _split(tok: str, min_n: int = 12) -> str:
    """Split a run of letters into dictionary words, fewest and longest pieces first; unchanged if it can't.
    Only long runs (12+ letters) split: a shorter token is far likelier one word the dictionary lacks (Bluetooth)
    than several squeezed together. Text glued to a number or an acronym passes a lower `min_n`."""
    W, low, n = _words(), tok.lower(), len(tok)
    if not W or n < min_n or _is(low):
        return tok
    best = [None] * (n + 1)
    best[0] = (0, 0, [])
    for i in range(1, n + 1):
        for j in range(max(0, i - 18), i):
            w = low[j:i]
            if best[j] is None or not _is(w) or (len(w) <= 3 and w not in _COMMON and w not in _VOCAB):
                continue  # "rea douts", "han doff": a short obscure piece is a wrong split
            cost = (best[j][0] + 1, best[j][1] - (2 if w in _COMMON else 0) - (1 if len(w) <= 3 and w not in _COMMON else 0) - (1 if w in _VOCAB else 0))
            if best[i] is None or cost < best[i][:2]:
                best[i] = (*cost, best[j][2] + [(j, i)])
    if not best[n] or len(best[n][2]) < 2:
        return tok
    return " ".join(tok[a:b] for a, b in best[n][2])


def _word(tok: str) -> str:
    if re.fullmatch(r"[0-9a-f]{7,}", tok.lower()) and re.search(r"\d", tok):
        return tok  # a hash
    if re.search(r"[-_@#]|[A-Za-z0-9][./][A-Za-z]|[a-z][A-Z]", tok) or not re.search(r"[A-Za-z]", tok) or _TECH.fullmatch(tok):
        return tok  # an identifier, a path or slice name, a number, base64
    m = re.fullmatch(r"(\d*)([A-Z]{2,})(\d{2,})?([a-z]{3,})", tok)  # GRPO192steps, 90CInotpositive
    if m and (m.group(3) or _is(m.group(4)) or _split(m.group(4), 7) != m.group(4)):
        return " ".join(x for x in (m.group(1), m.group(2), m.group(3), _split(m.group(4), 7)) if x)
    if "/" in tok:
        return "/".join(_word(p) for p in tok.split("/"))
    tok = re.sub(r"(?<=[a-z]{2})(?=\d{2,})", " ", tok)      # audit1319 -> audit 1319, vs150 -> vs 150; keeps gsm8k
    tok = re.sub(r"(?<=[a-z]{3})(\d)(?=[a-z]{3,})", r" \1 ", tok)  # fix5regress -> fix 5 regress
    tok = re.sub(r"(?:^|(?<= ))(\d+)(?=[a-z]{3,})", r"\1 ", tok)       # 95wrong -> 95 wrong; keeps 4B and 10k
    return " ".join(_split(p) if p.isalpha() else p for p in tok.split(" "))


def _paren(m) -> str:
    """word(x) -> word (x), but getApps(), f(x) on an identifier, drawing(s) and list[] stay as written."""
    w, nxt = m.group(1), m.string[m.end():m.end() + 4]
    if re.search(r"[a-z][A-Z]|[_.]", w) or nxt.startswith(("()", "(s)", "(es)", "[]")):
        return w
    return w + " "


def readable(msg: str) -> str:
    if not isinstance(msg, str) or not msg or msg.lstrip()[:1] in "{[":
        return msg  # empty, or a JSON payload
    s = re.sub(r"([,;:])(?=[A-Za-z0-9(\[])", r"\1 ", msg)            # a,b -> a, b (but 1,319 stays)
    s = re.sub(r"(?<=\d), (?=\d{3}\b)", ",", s)                      # undo for thousands separators
    s = re.sub(r"\b(\d{1,2}): (?=\d{2}\b)", r"\1:", s)               # 12:30 stays a time
    s = re.sub(r"(?<=\d{3}):(?=\d)", ": ", s)                         # 1319:95 is a label, not a time
    s = re.sub(r"(?<=[%\]\)])(?=[A-Za-z])", " ", s)                    # 90%CI -> 90% CI, ]pts -> ] pts
    s = re.sub(r"([A-Za-z_][\w.]*[a-z])(?=[\[(])", _paren, s)
    s = re.sub(r"(?<=\w)\+(?=[A-Za-z])", " + ", s)
    s = re.sub(r"\b\d+\.\d{5,}\b", lambda m: f"{float(m.group(0)):.4g}", s)  # loss 1.0619175910949707 -> 1.062
    return re.sub(r"[A-Za-z0-9](?:[\w\-/.@#]*\w)?", lambda m: _word(m.group(0)), s)
