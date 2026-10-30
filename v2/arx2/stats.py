"""Run summaries and paired comparisons. 90% intervals throughout."""
from __future__ import annotations

import math
import statistics

Z90 = 1.6448536269514722


def t90(df: int) -> float:
    """Two-sided 90% t quantile (Cornish-Fisher expansion of the normal quantile)."""
    if df <= 0:
        return float("inf")
    z = Z90
    return z + (z**3 + z) / (4 * df) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2) + \
        (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)


def score_of(row: dict) -> float:
    """Errors count as a score of 0."""
    if row.get("error"):
        return 0.0
    s = row.get("score")
    return float(s) if s is not None else 0.0


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    scores = [score_of(r) for r in rows]
    lat = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    cost = [r["cost"] for r in rows if r.get("cost") is not None]
    out = {
        "n": n,
        "score": sum(scores) / n,
        "passed": sum(1 for x in scores if x >= 1.0),
        "errors": sum(1 for r in rows if r.get("error")),
    }
    if lat:
        out["latency_p50"] = statistics.median(lat)
        out["latency_p95"] = _pct(lat, 95)
        out["latency_mean"] = sum(lat) / len(lat)
    if cost:
        out["cost"] = sum(cost) / len(cost)
        out["cost_total"] = sum(cost)
    return out


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def paired(base: list[dict], cand: list[dict], binary: bool = True, higher_better: bool = True,
           field: str = "score") -> dict:
    """Candidate minus base on shared ids. Positive `delta` always means better."""
    b = {str(r["id"]): r for r in base}
    c = {str(r["id"]): r for r in cand}
    ids = [i for i in c if i in b]
    n = len(ids)
    if not n:
        return {"n": 0}

    def val(r):
        return score_of(r) if field == "score" else r.get(field)

    pairs = [(val(b[i]), val(c[i])) for i in ids if val(b[i]) is not None and val(c[i]) is not None]
    n = len(pairs)
    sign = 1 if higher_better else -1
    diffs = [sign * (y - x) for x, y in pairs]
    better = sum(1 for d in diffs if d > 0)
    worse = sum(1 for d in diffs if d < 0)
    delta = sum(diffs) / n
    if binary:
        # Agresti-Min: add half a pair to each discordant cell. Wide when n is tiny.
        bb, ww, nn = better + 0.5, worse + 0.5, n + 2
        d_adj = (bb - ww) / nn
        var = ((bb + ww) - (bb - ww) ** 2 / nn) / nn**2
        half = Z90 * math.sqrt(max(var, 0.0))
        lo, hi = max(-1.0, d_adj - half), min(1.0, d_adj + half)
    else:
        sd = statistics.stdev(diffs) if n > 1 else float("inf")
        half = t90(n - 1) * sd / math.sqrt(n)
        lo, hi = delta - half, delta + half
    return {
        "n": n, "delta": delta, "lo": lo, "hi": hi, "better": better, "worse": worse,
        "same": n - better - worse,
        "base": sum(x for x, _ in pairs) / n, "cand": sum(y for _, y in pairs) / n,
    }


def needed_n(sd: float, gain: float, power: float = 0.8) -> int:
    """Examples needed to see `gain` against noise `sd` (two-sided 90% test)."""
    z_power = {0.8: 0.8416, 0.9: 1.2816}.get(power, 0.8416)
    if gain <= 0:
        return 0
    return math.ceil(((Z90 + z_power) * sd / gain) ** 2)
