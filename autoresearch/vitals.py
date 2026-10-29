"""Vital signs for running jobs (see features.py for the contracts).

STATE: every live task gets `eta` (re-estimated from a recent rate window, with its history) and `health`; a long job
also gets `vitals`: 2-4 panels chosen by its kind and the metrics it logs, each a small series the Workbench draws.
GET /api/vitals/series?ids=a,b: downsampled metrics of other runs, for the task view's overlay.
"""
from __future__ import annotations

import math
import re
import time

from . import features

WIN_S = 300      # rate window for the ETA
QUIET_S = 60     # silent this long: "quiet"
LONG_S = 240     # a job expected to run this long gets a card with panels (trains and evals always); shorter ones are rows
CAP = 160        # points per panel series
Z = 1.645        # 90% intervals


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def thin(pts: list, cap: int = CAP) -> list:
    """Every point when few, else an even stride that keeps the last one."""
    if len(pts) <= cap:
        return pts
    k = len(pts) / (cap - 1)
    return [pts[int(i * k)] for i in range(cap - 1)] + [pts[-1]]


def beats(t: dict, metrics: list[dict]) -> list[tuple[float, float]]:
    """(time, done) samples for a job with a total. Metrics rows (one per step) when their steps track progress, else
    the throttled progress history; the start (created, 0) first."""
    pr = t.get("progress") or {}
    done, total = pr.get("done") or 0, pr.get("total") or 0
    ms = [(m["t"], m["step"]) for m in metrics if not m.get("sys") and _num(m.get("t")) and _num(m.get("step"))]
    hist = [tuple(x) for x in pr.get("hist") or [] if len(x) == 2]
    use = ms if ms and abs(ms[-1][1] - done) <= max(1, 0.02 * total) and len(ms) >= len(hist) else hist
    out = [(t.get("created") or (use[0][0] if use else 0), 0)]
    for x, d in use:
        if x >= out[-1][0] and d >= out[-1][1]:
            out.append((x, d))
    return out


def eta_track(b: list[tuple[float, float]], total: float, now: float, win: float = WIN_S) -> dict | None:
    """At each beat, the finish time the rate over the last `win` seconds predicts. The latest is the ETA; the list is
    how the estimate moved (`hist`: [time, predicted finish]); `drift_s` is how far it moved in the last window."""
    if not total or len(b) < 2:
        return None
    hist, k0, rate = [], 0, None
    for i, (x, d) in enumerate(b):
        while k0 < i and b[k0][0] < x - win:
            k0 += 1
        j = min(k0, i - 1) if i else 0
        dx, dd = x - b[j][0], d - b[j][1]
        if i and dx > 2 and dd > 0 and d < total:
            r = dd / dx
            hist.append([x, x + (total - d) / r])
            rate = r
    if rate is None:
        return None
    x, d = b[-1]
    finish = x + (total - d) / rate
    old = [h for h in hist if h[0] <= x - win]
    drift = finish - old[-1][1] if old else (finish - hist[0][1] if len(hist) > 1 else 0.0)
    return dict(per_min=rate * 60, eta_s=max(0.0, finish - now), finish_at=finish, window_s=win, drift_s=drift,
                hist=thin(hist, 80))


def health(t: dict, eta: dict | None, now: float) -> dict:
    """ok, quiet (no heartbeat for a minute), slipping (the ETA moved out by > max(2 min, 15% of what is left)), stalled."""
    silent = now - (t.get("heartbeat") or t.get("updated") or now)
    if t.get("status") == "stalled":
        return dict(state="stalled", silent_s=silent)
    if silent >= QUIET_S:
        return dict(state="quiet", silent_s=silent)
    if eta and eta["drift_s"] > max(120, 0.15 * eta["eta_s"]):
        return dict(state="slipping", silent_s=silent, by_s=eta["drift_s"])
    return dict(state="ok", silent_s=silent)


# ---------- panels
REWARD = re.compile(r"^(reward|mean_reward|rewards/[^/]+/mean|running_score|score|accuracy|acc|mean_token_accuracy)$")
PRIORITY = ("reward", "running_score", "score", "accuracy", "mean_token_accuracy")
SKIP = re.compile(r"(^|/|_)(min|max|std)(_|/|$)|clip_ratio|^epoch$|^step_time$|^num_tokens$|^total_flos$|^train_")


def _series(rows, key, x="step"):
    return [[m[x], m[key]] for m in rows if _num(m.get(key)) and _num(m.get(x))]


def _flat(pts) -> bool:
    ys = [p[1] for p in pts]
    return not ys or max(ys) - min(ys) <= 1e-12 * max(1.0, abs(ys[0]))


def _wilson(k, n):
    if not n:
        return 0.0, 1.0
    p, d = k / n, 1 + Z * Z / n
    c, h = (p + Z * Z / (2 * n)) / d, Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return c - h, c + h


def _gpu(rows, t0):
    sy = [m for m in rows if m.get("sys") and _num(m.get("gpu_util"))]
    if not sy:
        return None
    last = sy[-1]
    sy = [m for m in sy if m["t"] >= last["t"] - 1800]
    return dict(id="gpu", title="GPU", fmt="pct100", value=last["gpu_util"], x="time", ymin=0, ymax=100,
                mem=[last.get("gpu_mem_gb"), last.get("gpu_mem_total_gb")], gpus=last.get("gpus"),
                series=[dict(name="GPU utilisation", pts=thin([[m["t"] - t0, m["gpu_util"]] for m in sy]))])


def _eta_panel(eta):
    if not eta or not eta.get("hist"):
        return None
    h0 = eta["hist"][0][1]
    return dict(id="eta", title="Finish estimate", fmt="clock", value=eta["finish_at"], drift_s=eta["drift_s"],
                n=len(eta["hist"]), x="clock", yfmt="dmin", smooth=False,
                series=[dict(name="Moved by", pts=[[x, (f - h0) / 60] for x, f in eta["hist"]])])


def _throughput(t, b, rows):
    """Tokens a second from a cumulative token counter, else items a minute from the beats."""
    tk = [m for m in rows if _num(m.get("num_tokens")) and _num(m.get("t"))]
    if len(tk) > 2:
        pts = [[b_["t"] - t["created"], (b_["num_tokens"] - a["num_tokens"]) / max(0.1, b_["t"] - a["t"])] for a, b_ in zip(tk, tk[1:])]
        st = next((m["step_time"] for m in reversed(rows) if _num(m.get("step_time"))), None)
        return dict(id="tps", title="Tokens a second", fmt="int", value=pts[-1][1], x="time", ymin=0, step_time=st,
                    series=[dict(name="Tokens/s", pts=thin(pts))])
    if len(b) > 2:
        pts = [[y[0] - t["created"], (y[1] - x[1]) / max(1, y[0] - x[0]) * 60] for x, y in zip(b, b[1:]) if y[0] > x[0]]
        if pts:
            return dict(id="rate", title="Rate", fmt="num", unit="a minute", value=pts[-1][1], x="time", ymin=0,
                        series=[dict(name="Per minute", pts=thin(pts))])
    return None


def _metric(rows, key, total, pid="m"):
    pts = _series(rows, key)
    if len(pts) < 2:
        return None
    return dict(id=pid, key=key, title=key, fmt="num", value=pts[-1][1], domain=[0, total] if total else None,
                series=[dict(name=key, pts=thin(pts, 240))], smooth=True)


def panels(p, t: dict, st: dict, eta: dict | None) -> list[dict]:
    rows = p.metrics(t["id"])
    pr = t.get("progress") or {}
    total = pr.get("total")
    ml = [m for m in rows if not m.get("sys")]
    keys = []
    for m in ml:
        for k, v in m.items():
            if k not in ("t", "step") and _num(v) and k not in keys:
                keys.append(k)
    live = [k for k in keys if not _flat(_series(ml, k))]
    out: list[dict | None] = []
    if t.get("kind") == "eval":
        out += _eval_panels(p, t, st, ml, total)
    else:
        main = next((k for k in PRIORITY if k in live), None) or next((k for k in live if REWARD.match(k)), None) or ("loss" if "loss" in live else next((k for k in live if not SKIP.search(k)), None))
        if main:
            out.append(_metric(ml, main, total, "main"))
        out.append(_eta_panel(eta))
        sec = next((k for k in ("loss", "grad_norm", "kl", "entropy") if k in live and k != main), None) or next((k for k in live if k != main and not SKIP.search(k)), None)
        if sec:
            out.append(_metric(ml, sec, total, "sec"))
        out.append(_gpu(rows, t["created"]) or _throughput(t, beats(t, rows), ml))
    out = [x for x in out if x]
    if out and out[0]["id"] != "main":  # the biggest panel is whatever leads
        out[0] = out[0] | {"lead": True}
    return out[:4]


def _eval_panels(p, t, st, ml, total):
    sl = (st.get("slices") or {}).get(t.get("slice")) or {}
    binary = sl.get("scale") != "continuous"
    pts = _series(ml, "running_score")
    main = None
    if pts:
        band = [[n, *_wilson(round(s * n), n)] for n, s in pts if n] if binary else None
        champ = st.get("champion")
        ref = ((st.get("leaderboard") or {}).get(t.get("slice")) or {}).get(champ) if champ and champ != t.get("model") else None
        main = dict(id="main", title="Score so far", fmt="pct" if binary else "num", value=pts[-1][1], n=pts[-1][0],
                    domain=[0, total] if total else None, ymin=0 if binary else None, ymax=1 if binary else None,
                    series=[dict(name="Score", pts=thin(pts, 240))], band=thin(band, 240) if band else None, smooth=False,
                    ref=dict(y=ref["score"], label="champion") if ref and _num(ref.get("score")) else None)
    out = [main, _eta_panel(t.get("eta"))]
    rows = p.rows(t["id"])
    champ = st.get("champion")
    pair = None
    if binary and champ and champ != t.get("model") and rows:
        try:
            base = p.pooled_scores(champ, t["slice"])
        except Exception:
            base = {}
        if base:
            won = lost = n = 0
            line, band = [], []
            for r in rows:
                i = str(r.get("id"))
                if i not in base:
                    continue
                c = 0.0 if r.get("error") else float(r.get("score") or 0)
                n += 1
                won += c > base[i]
                lost += c < base[i]
                d = won - lost
                se = math.sqrt(max(0.0, won + lost - d * d / n))
                line.append([n, d])
                band.append([n, d - Z * se, d + Z * se])
            if line:
                pair = dict(id="pair", title="Against the champion", fmt="signed", value=line[-1][1], won=won, lost=lost,
                            domain=[0, total] if total else None, zero=True, smooth=False, ci=band[-1][1:],
                            series=[dict(name="Won minus lost", pts=thin(line, 240))], band=thin(band, 240))
    lat = [float(r["latency_s"]) for r in rows if _num(r.get("latency_s"))]
    latp = None
    if len(lat) >= 8:
        roll50, roll95 = [], []
        for i in range(8, len(lat) + 1, max(1, len(lat) // 120)):
            w = sorted(lat[max(0, i - 48):i])
            roll50.append([i, w[len(w) // 2]])
            roll95.append([i, w[min(len(w) - 1, int(len(w) * .95))]])
        s = sorted(lat)
        latp = dict(id="lat", title="Latency", fmt="s", value=s[len(s) // 2], p95=s[min(len(s) - 1, int(len(s) * .95))],
                    domain=[0, total] if total else None, ymin=0, smooth=False,
                    series=[dict(name="Median", pts=roll50), dict(name="95th percentile", pts=roll95, faint=True)])
    gpu = _gpu(p.metrics(t["id"]), t["created"])
    out += [pair or latp, gpu or (latp if pair else None)]
    return out


def is_long(t: dict, eta: dict | None, now: float, n_panels: int) -> bool:
    if t.get("status") == "stalled":
        return True
    el = now - t.get("created", now)
    expected = el + (eta["eta_s"] if eta else 0)
    return n_panels >= 2 and (t.get("kind") in ("train", "eval") or expected >= LONG_S or el >= LONG_S)


def _vitals(p, st):
    now = time.time()
    for t in st.get("tasks") or []:
        if t.get("status") not in ("running", "stalled"):
            continue
        total = (t.get("progress") or {}).get("total")
        try:
            rows = p.metrics(t["id"])
            e = eta_track(beats(t, rows), total, now) if total and t.get("status") == "running" else None
            if e:
                t["eta"] = e
            elif t.get("status") == "stalled":
                t["eta"] = None
            t["health"] = health(t, t.get("eta") if e else None, now)
            ps = panels(p, t, st, t.get("eta"))
            t["long"] = is_long(t, t.get("eta"), now, len(ps))
            t["vitals"] = ps
        except Exception as ex:  # one odd task never breaks the state
            t["vitals_error"] = f"{type(ex).__name__}: {ex}"
    return st


features.STATE.append(_vitals)


@features.get("/api/vitals/series")
def _runs(p, path, q):
    """Other runs' metric curves for the overlay: {id: {title, model, kind, created, ended, status, metrics}}."""
    out = {}
    for tid in [x for x in (q.get("ids") or "").split(",") if x][:12]:
        try:
            t = p.task(tid)
        except KeyError:
            continue
        rows = [m for m in p.metrics(tid) if not m.get("sys")]
        out[tid] = dict(title=t.get("title"), model=t.get("model"), kind=t.get("kind"), created=t.get("created"),
                        ended=t.get("ended"), status=t.get("status"), metrics=thin(rows, 400))
    return 200, out
