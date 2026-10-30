"""The paper gate: a paper is published only when it is complete, self-contained and backed by the ledger.

`check(p, html, kind, about)` returns issues `{"level": "error"|"warn", "what", "fix"}`. `kind` is the paper's
audience: "external" (a goal paper for the world) or "internal" (a hill paper for the team).

Numbers are written as claim elements and recomputed from the rows:

  <span data-claim="score" data-run="<run>">74.3%</span>
  <span data-claim="delta" data-base-run="<run>" data-run="<run>" data-lo="0.4" data-hi="3.6">+2.0 pts</span>
  <span data-claim="n" data-set="<set>">183</span>
  <span data-claim="count" data-set="<set>" data-of="<what>">151</span>
  <span data-claim="target" data-goal="<goal>">84%</span>

`data-metric` (score, latency_p50, latency_p95, cost) picks another summary for score and delta claims.
"""
from __future__ import annotations

import html as htmlmod
import math
import re
from html.parser import HTMLParser

from .store import Project
from .view import METRICS, Views, measure_of

EXTERNAL = [  # part, synonyms (lower case, matched at the start of a heading); "negative results" before "results"
    ("abstract", ["abstract"]),
    ("introduction", ["introduction", "intro"]),
    ("setup", ["setup", "experimental setup", "evaluation setup", "set-up"]),
    ("method", ["method", "methods", "approach"]),
    ("negative", ["negative results", "negative", "what did not work", "what didn't work", "what did not"]),
    ("results", ["results", "result"]),
    ("threats", ["threats to validity", "threats", "limitations"]),
    ("conclusion", ["conclusion", "conclusions"]),
]
INTERNAL = [
    ("problem", ["problem", "symptom"]),
    ("measure", ["measure", "metric"]),
    ("sets", ["sets", "eval sets", "data"]),
    ("candidates", ["candidates", "what we tried"]),
    ("result", ["result", "results"]),
    ("next", ["next", "next steps", "what next"]),
]
TITLES = {"abstract": "Abstract", "introduction": "Introduction", "setup": "Setup", "method": "Method",
          "results": "Results", "negative": "What did not work", "threats": "Threats to validity",
          "conclusion": "Conclusion", "problem": "Problem", "measure": "Measure", "sets": "Sets",
          "candidates": "Candidates", "result": "Result", "next": "Next"}
ORDER = {"external": ["abstract", "introduction", "setup", "method", "results", "negative", "threats", "conclusion"],
         "internal": [x for x, _ in INTERNAL]}
BUDGETS = {  # prose words per section; over is a warning, over twice is an error (the abstract: over is an error)
    "external": {"abstract": 80, "introduction": 120, "setup": 150, "method": 150, "results": 200, "negative": 150,
                 "threats": 200, "conclusion": 80},
    "internal": {"problem": 60, "measure": 75, "sets": 75, "candidates": 75, "result": 100, "next": 40},
}
TOTAL = {"external": 1500, "internal": 750}
CHECKED = {"external": {"abstract", "results", "conclusion"}, "internal": {"result"}}
FIGURE_IN = {"external": "results", "internal": "result"}

BLOCKS = {"p", "li", "figcaption", "td", "th", "dt", "dd", "blockquote", "caption", "h1", "h2", "h3", "h4", "h5", "h6"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BARE = re.compile(r"[+\-−–]?\d[\d,]*(?:\.\d+)?\s*(?:%|pts?\b|pp\b|points?\b|percentage points?\b)", re.I)
NUM = re.compile(r"[+\-−–]?\d[\d,]*(?:\.\d+)?")
EXTERNAL_URL = re.compile(r"""url\(\s*['"]?\s*(?!data:)[^)'"\s]+""", re.I)


def part_of(text: str, kinds: list) -> str | None:
    t = re.sub(r"^[\s\d.:§)\-–]+", "", " ".join(text.lower().split()))
    for part, syn in kinds:
        if t == part or any(t.startswith(s) for s in syn):
            return part
    return None


class _Node:
    __slots__ = ("tag", "attrs", "id")

    def __init__(self, tag, attrs, id_):
        self.tag, self.attrs, self.id = tag, attrs, id_


class _Reader(HTMLParser):
    """One pass over the page: parts, text runs, claims, figures and outside resources."""

    def __init__(self, kinds):
        super().__init__(convert_charrefs=True)
        self.kinds = kinds
        self.stack: list[_Node] = []
        self.n = 0
        self.title = ""
        self.h1 = 0
        self.color_scheme = False
        self.external: list[str] = []
        self.parts: list[str] = []  # in the order they appear
        self.h2_part = None
        self.h2_text: list[str] | None = None
        self.h2_attr = None
        self.texts: list[dict] = []  # {text, part, claim, svg, axis}
        self.claims: dict[int, dict] = {}
        self.blocks: dict[int, list] = {}  # block id -> list of (text, claim id)
        self.captions: dict[int, list] = {}  # figure/table id -> caption text
        self.figures: dict[str | None, int] = {}
        self.items: list[tuple[str | None, str]] = []  # (part, data-item)
        self.words: dict[str | None, int] = {}  # prose words per part, outside svg, figure and table
        self.first: dict[str | None, str] = {}  # what a part opens with after its heading: "figure" or "prose"

    # ---- context -------------------------------------------------------
    def part(self):
        for node in reversed(self.stack):
            if node.tag == "section" and node.attrs.get("data-part"):
                return part_of(node.attrs["data-part"], self.kinds) or node.attrs["data-part"].lower()
        return self.h2_part

    def _inner(self, pred):
        for node in reversed(self.stack):
            if pred(node):
                return node
        return None

    # ---- events --------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in ("p", "li") and self.stack and self.stack[-1].tag == tag:
            self.stack.pop()  # an unclosed <p> or <li> ends where the next one starts
        if tag == "meta" and a.get("name", "").lower() == "color-scheme":
            self.color_scheme = " ".join(a.get("content", "").split()) == "light dark"
        elif tag == "link":
            if a.get("href", "") != "/static/app.css":
                self.external.append(f'<link href="{a.get("href", "")}">')
        elif tag in ("script", "img", "iframe", "audio", "video", "source", "embed", "object", "image", "use"):
            src = a.get("src") or a.get("href") or a.get("xlink:href") or a.get("data") or ""
            if src and not src.startswith(("data:", "#")):
                self.external.append(f'<{tag} src="{src}">')
        if EXTERNAL_URL.search(a.get("style", "")):
            self.external.append(f'style="{a["style"][:60]}"')
        if tag == "h1":
            self.h1 += 1
        if tag in ("figure", "svg") and not self._inner(lambda x: x.tag in ("figure", "svg")):
            pt = self.part()
            self.figures[pt] = self.figures.get(pt, 0) + 1
            self.first.setdefault(pt, "figure")
        if "data-item" in a:
            self.items.append((self.part(), a["data-item"]))
        if tag == "section" and a.get("data-part"):
            self._saw(part_of(a["data-part"], self.kinds) or a["data-part"].lower())
        if tag == "h2":
            self.h2_text, self.h2_attr = [], a.get("data-part")
        if tag in VOID:
            return
        self.n += 1
        node = _Node(tag, a, self.n)
        if "data-claim" in a:
            blk = self._inner(lambda x: x.tag in BLOCKS)
            fig = self._inner(lambda x: x.tag in ("figure", "table"))
            self.claims[self.n] = {"attrs": a, "text": "", "part": self.part(), "block": blk.id if blk else None,
                                   "cap": fig.id if fig else None, "off": None}
            if blk:
                self.claims[self.n]["off"] = sum(len(t) for t, _ in self.blocks.get(blk.id, []))
        self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag == "h2" and self.h2_text is not None:
            text = "".join(self.h2_text)
            pt = part_of(self.h2_attr, self.kinds) if self.h2_attr else None
            self.h2_part = pt or part_of(text, self.kinds) or ("other:" + text.strip().lower())
            self._saw(self.h2_part)
            self.h2_text = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def _saw(self, part):
        if part and part not in self.parts:
            self.parts.append(part)

    def handle_data(self, data):
        if not data:
            return
        tags = [x.tag for x in self.stack]
        if "style" in tags:
            if EXTERNAL_URL.search(data) or re.search(r"@import", data, re.I):
                self.external.append("<style> " + (EXTERNAL_URL.search(data) or re.search(r"@import[^;]*", data, re.I)).group(0)[:80])
            return
        if "script" in tags:
            return
        if "title" in tags:
            self.title += data
            return
        if self.h2_text is not None:
            self.h2_text.append(data)
        claim = self._inner(lambda x: "data-claim" in x.attrs)
        cid = claim.id if claim else None
        if cid:
            self.claims[cid]["text"] += data
        heading = self.h2_text is not None or "h1" in tags
        prose = not heading and not any(t in ("svg", "figure", "table") for t in tags)
        pt = self.part()
        if prose and data.strip():
            self.words[pt] = self.words.get(pt, 0) + len(data.split())
            self.first.setdefault(pt, "prose")
        self.texts.append({"text": data, "part": pt, "claim": cid, "svg": "svg" in tags, "prose": prose})
        blk = self._inner(lambda x: x.tag in BLOCKS)
        if blk:
            self.blocks.setdefault(blk.id, []).append((data, cid))
        owner = self._inner(lambda x: x.tag in ("figure", "table"))
        if owner:  # a figure's labels and caption together say what its numbers are about
            self.captions.setdefault(owner.id, []).append((data, cid))


# ---- numbers ---------------------------------------------------------------

def _num(text: str):
    m = NUM.search(text or "")
    if not m:
        return None, 0
    s = m.group(0).replace("−", "-").replace("–", "-").replace(",", "")
    dec = len(s.split(".")[1]) if "." in s else 0
    try:
        return float(s), dec
    except ValueError:
        return None, 0


def _scaled(text: str) -> bool:
    return bool(re.search(r"%|\bpts?\b|\bpp\b|\bpoints?\b", text or "", re.I))


def _close(shown: float, dec: int, truth: float) -> bool:
    return abs(shown - truth) <= 0.5 * 10 ** -dec + 1e-9


def _fmt(v: float, dec: int, unit: str) -> str:
    return f"{v:.{dec}f}" + ("%" if unit == "%" else f" {unit}" if unit else "")


class _Ledger:
    def __init__(self, p: Project):
        self.p = p
        self.v = Views(p)
        self.s = self.v.s
        self.measure = measure_of(self.s)

    def binary(self, metric: str) -> bool:
        return metric == "score" and self.measure["scale"] == "binary"

    def higher_better(self, metric: str) -> bool:
        if metric == "score":
            return self.measure["direction"] == "max"
        return METRICS.get(metric, METRICS["score"])[1]


def _claim_set(L: _Ledger, a: dict) -> str | None:
    if a.get("data-set"):
        return a["data-set"]
    r = L.s["runs"].get(a.get("data-run") or "")
    return r["set"] if r else None


def _verify(L: _Ledger, c: dict) -> list[dict]:
    """Recompute one claim from the rows; an issue when the page and the ledger disagree."""
    a, text = c["attrs"], " ".join(c["text"].split())
    kind = a.get("data-claim", "")
    label = f'{kind} claim "{text}"'
    shown, dec = _num(text)
    out = []

    def err(what, fix):
        out.append({"level": "error", "what": f"{label}: {what}", "fix": fix})
        return out

    if shown is None:
        return err("shows no number", "put the number itself inside the claim element")
    runs = L.s["runs"]
    metric = a.get("data-metric", "score")
    if metric not in METRICS:
        return err(f"unknown data-metric {metric!r}", "use one of " + ", ".join(METRICS))
    for attr in ("data-run", "data-base-run"):
        if a.get(attr) and a[attr] not in runs:
            return err(f"{attr}={a[attr]!r} is not a run in the ledger", "copy the run key from `arx2 cand list` or the dashboard")
    if a.get("data-set") and a["data-set"] not in L.s["sets"]:
        return err(f"data-set={a['data-set']!r} is not a set in the ledger", "arx2 set list")

    scale = 100.0 if _scaled(text) else 1.0
    unit = "%" if "%" in text else ("pts" if scale == 100 else "")
    # A bare number for a pass/fail score (a chart label like "66.7") may be a fraction or a percentage.
    scales = [100.0, 1.0] if scale == 1.0 and L.binary(metric) else [scale]
    scale = scales[0]
    if kind == "score":
        if not a.get("data-run"):
            return err("has no data-run", 'add data-run="<run>"')
        v = L.v.run_view(a["data-run"])["summary"].get(METRICS[metric][0])
        if v is None:
            return err(f"run {a['data-run']} has no {metric}", "point data-run at a run with rows")
        if not any(_close(shown, dec, v * k) for k in scales):
            return err(f"the ledger says {_fmt(v * scale, dec, unit)} for run {a['data-run']}",
                       f"write {_fmt(v * scale, dec, unit)}, or point data-run at the run you meant")
    elif kind == "delta":
        if not (a.get("data-run") and a.get("data-base-run")):
            return err("needs data-base-run and data-run", 'add data-base-run="<run>" data-run="<run>"')
        cmp = L.v.compare(a["data-base-run"], a["data-run"], metric)
        if not cmp.get("n"):
            return err("the two runs share no items", "compare two runs on the same set")
        signs = [1] if L.higher_better(metric) else [1, -1]  # lower-is-better may be shown as the raw change
        truth = cmp["delta"] * scale
        if not any(_close(shown, dec, s * cmp["delta"] * k) for s in signs for k in scales):
            return err(f"the ledger says {truth:+.{dec}f}{' ' + unit if unit else ''} (paired, n={cmp['n']})",
                       f"write {truth:+.{dec}f}{' ' + unit if unit else ''}, or fix data-base-run / data-run")
        for attr, key in (("data-lo", "lo"), ("data-hi", "hi")):
            if a.get(attr):
                b, bdec = _num(a[attr])
                flip = "hi" if key == "lo" else "lo"
                # the bound may be written as a fraction (0.074) or in the shown unit (7.4 pts)
                ok = [cmp[key] * k for k in {1.0, scale}] + ([-cmp[flip] * k for k in {1.0, scale}] if len(signs) > 1 else [])
                if b is None or not any(_close(b, bdec, x) for x in ok):
                    return err(f"{attr}={a[attr]} but the 90% interval is {cmp['lo'] * scale:+.{max(bdec, 1)}f} to "
                               f"{cmp['hi'] * scale:+.{max(bdec, 1)}f}", f"set {attr} from `arx2 gate` or Views.compare")
    elif kind == "n":
        if a.get("data-run"):
            truth = len(L.v.rows(a["data-run"]))
        elif a.get("data-set"):
            truth = L.s["sets"][a["data-set"]]["n"]
        else:
            return err("has no data-set", 'add data-set="<set>"')
        if shown != truth:
            return err(f"the ledger says n = {truth}", f"write {truth}")
    elif kind == "count":
        truth = _count(L, a)
        if isinstance(truth, str):
            return err(truth, 'count claims take data-set, data-run (passed items), data-base-run and data-run '
                              '(fixed, broken, both right or both wrong), or data-of naming another set or a pattern')
        if shown not in truth:
            return err(f"the ledger says {' or '.join(str(x) for x in sorted(set(truth)))}",
                       f"write {sorted(set(truth))[0]}" if len(set(truth)) == 1 else "write the count the sentence means")
    elif kind == "target":
        g = L.s["goals"].get(a.get("data-goal") or "")
        if not g:
            return err("needs data-goal naming a goal", "arx2")
        if a.get("data-unit") == "count":  # items needed to meet the goal, or (with data-run) items still missing
            gn = L.s["sets"].get(g["set"], {}).get("n") or 0
            need = math.ceil(g["target"] * gn - 1e-9)
            truth, what = need, "items needed"
            if a.get("data-run"):
                passed = sum(1 for r in L.v.rows(a["data-run"]) if not r.get("error") and (r.get("score") or 0) >= 1)
                truth, what = max(need - passed, 0), "items still missing"
            if shown != truth:
                return err(f"the ledger says {truth} {what} (target {g['target']:g} of {gn})", f"write {truth}")
        elif not any(_close(shown, dec, g["target"] * k) for k in {scale, 100.0 if L.binary(g.get("metric", "score")) else 1.0}):
            return err(f"the goal's target is {g['target'] * scale:.{dec}f}", f"write {g['target'] * scale:.{dec}f}")
    else:
        return err("unknown data-claim", "use score, delta, n, count or target")
    return out


def _count(L: _Ledger, a: dict):
    """The counts a count claim may mean, or a reason it cannot be resolved."""
    of = (a.get("data-of") or "").lower()
    run, base = a.get("data-run"), a.get("data-base-run")

    def ok(r):
        return not r.get("error") and (r.get("score") or 0) >= 1

    if of.isdigit():  # "151 of 183": data-of is the denominator
        denom = len(L.v.rows(run)) if run else L.s["sets"].get(a.get("data-set") or "", {}).get("n")
        if denom is not None and int(of) != denom:
            return f'data-of="{of}" but the set has {denom} items'
        of = ""
    if of in ("pass", "passed", "fail", "failed", "error", "errors", "wrong") or (of == "" and run and not base):
        if not run:
            return f'data-of="{of}" needs data-run'
        rows = L.v.rows(run)
        if of in ("", "pass", "passed"):
            return [sum(1 for r in rows if ok(r))]
        if of.startswith("error"):
            return [sum(1 for r in rows if r.get("error"))]
        return [sum(1 for r in rows if not ok(r))]
    if of in ("", "better", "worse", "same", "fixed", "broke", "broken", "both", "neither") and run and base:
        b = {str(r["id"]): ok(r) for r in L.v.rows(base)}
        c = {str(r["id"]): ok(r) for r in L.v.rows(run)}
        ids = [i for i in c if i in b]
        cells = {"fixed": sum(1 for i in ids if c[i] and not b[i]), "broke": sum(1 for i in ids if b[i] and not c[i]),
                 "both": sum(1 for i in ids if b[i] and c[i]), "neither": sum(1 for i in ids if not b[i] and not c[i])}
        cells.update(better=cells["fixed"], worse=cells["broke"], broken=cells["broke"], same=cells["both"] + cells["neither"])
        return [cells[of]] if of else list(cells.values())
    sets = L.s["sets"]
    if a.get("data-of") in sets and a.get("data-set") in sets:
        x, y = sets[a["data-set"]], sets[a["data-of"]]
        return [len({str(i) for i in x["ids"]} & {str(i) for i in y["ids"]})]
    pat = L.s["patterns"].get(a.get("data-of") or "")
    if pat and pat.get("count") is not None:
        return [pat["count"]]
    return f'cannot resolve data-of="{a.get("data-of", "")}"'


def _sentence(chunks: list, cid: int) -> tuple[str, set]:
    """The sentence holding claim `cid`, and the claims inside that sentence."""
    text, spans, start, end = "", [], None, None
    for t, c in chunks:
        if c == cid and start is None:
            start = len(text)
        spans.append((len(text), len(text) + len(t), c))
        text += t
        if c == cid:
            end = len(text)
    if start is None:
        return "", set()
    cuts = [0] + [m.end() for m in re.finditer(r"[.!?;](?=\s+[A-Z(\[])", text)] + [len(text)]
    lo = max(x for x in cuts if x <= start)
    hi = min(x for x in cuts if x >= end)
    return text[lo:hi], {c for a, b, c in spans if c and a < hi and b > lo}


def _names_set_and_n(L: _Ledger, R: _Reader, cid: int, c: dict, goal_set: str | None = None) -> bool:
    sk = _claim_set(L, c["attrs"])
    if not sk:
        return True
    st = L.s["sets"].get(sk, {})
    n = st.get("n")
    if c["attrs"].get("data-run"):
        n = len(L.v.rows(c["attrs"]["data-run"]))
    places = []
    if c["block"] is not None:
        places.append(_sentence(R.blocks.get(c["block"], []), cid))
    if c["cap"] is not None:
        chunks = R.captions.get(c["cap"], [])
        places.append(("".join(t for t, _ in chunks), {x for _, x in chunks if x}))
    for text, ids in places:
        low = text.lower()
        named = sk.lower() in low or bool(st.get("name") and st["name"].lower() in low) \
            or (sk == goal_set and "goal set" in low)
        has_n = c["attrs"].get("data-claim") == "n" or bool(n is not None and re.search(rf"(?<![\d.]){n}(?![\d.])", text)) \
            or any(R.claims[x]["attrs"].get("data-claim") == "n" and _claim_set(L, R.claims[x]["attrs"]) == sk for x in ids)
        if named and has_n:
            return True
    return False


# ---- the gate --------------------------------------------------------------

def check(p: Project, html: str, kind: str, about: str | None, draft: bool = False) -> list[dict]:
    """Issues that stop `html` from being published as a paper. `kind` is "external" or "internal".

    With `draft`, missing sections and figures are warnings, so an unfinished paper can be shared as a draft;
    wrong numbers and outside resources stay errors.
    """
    kinds = EXTERNAL if kind == "external" else INTERNAL
    R = _Reader(kinds)
    R.feed(html)
    R.close()
    L = _Ledger(p)
    s = L.s
    issues: list[dict] = []

    def add(level, what, fix, completeness=False):
        if completeness and draft and level == "error":
            level = "warn"
        issues.append({"level": level, "what": what, "fix": fix})

    # self-contained
    for x in dict.fromkeys(R.external):
        add("error", f"loads something from outside the page: {x}",
            "inline it (svg, data: url) or drop it; only /static/app.css may be linked")
    if not R.title.strip():
        add("error", "no <title>", "add <title>Two to eight words</title> in the head")
    if not R.h1:
        add("error", "no <h1>", "add one <h1> with the paper's title")
    if not R.color_scheme:
        add("error", 'no <meta name="color-scheme" content="light dark">', "start the head with arx2 paper new's theme head")

    # about
    goal = s["goals"].get(about or "")
    if kind == "external" and not goal:
        add("error", f"an external paper is about a goal; {about!r} is not one", "pass --about <goal>")
    if kind == "internal" and about and about not in s["hills"] and not goal:
        add("warn", f"an internal paper is usually about a hill; {about!r} is not one", "pass --about <hill>")

    # structure
    for part in ORDER[kind]:
        if part not in R.parts:
            add("error", f"no {TITLES[part]} section", f'add <section data-part="{part}"><h2>{TITLES[part]}</h2>…</section>', True)
    order = [x for x in R.parts if x in dict(kinds)]
    want = [x for x in ORDER[kind] if x in order]
    if kind == "external" and order != want:
        add("warn", "sections are out of order: " + ", ".join(order), "order them " + ", ".join(want))
    if kind == "internal" and "problem" in R.parts:
        ids = {str(i) for st in s["sets"].values() for i in st.get("ids") or []}
        real = [i for pt, i in R.items if pt == "problem" and i in ids]
        if not real:
            add("error", "the Problem section shows no real item",
                'add one failing item from the ledger, e.g. <span data-item="<item id>">…</span>, and what went wrong on it', True)
    fig_part = FIGURE_IN[kind]
    if fig_part in R.parts and not R.figures.get(fig_part):
        add("error", f"no figure in {TITLES[fig_part]}", f"add an inline <svg> or <figure> to {TITLES[fig_part]}", True)

    # word budgets: prose outside svg, figure and table
    budgets = BUDGETS[kind]
    for part, cap in budgets.items():
        w = R.words.get(part, 0)
        if part == "abstract" and w > cap:
            add("error", f"Abstract has {w} words, budget {cap}",
                f"cut to {cap} words: one sentence each for task, result with interval, status")
        elif w > 2 * cap:
            add("error", f"{TITLES[part]} has {w} words, more than twice its budget of {cap}",
                f"cut {TITLES[part]} to {cap} words; move detail into a figure or the appendix")
        elif w > cap:
            add("warn", f"{TITLES[part]} has {w} words, budget {cap}",
                f"cut {TITLES[part]} to {cap} words; let a figure carry the numbers")
    total = sum(R.words.values())
    if total > TOTAL[kind]:
        add("error", f"the paper has {total} words of prose, budget {TOTAL[kind]}",
            f"cut to {TOTAL[kind]} words: figures carry the numbers, prose says what they mean")
    if fig_part in R.parts and R.first.get(fig_part) == "prose":
        add("warn", f"{TITLES[fig_part]} opens with prose, not a figure",
            f"put the main figure first in {TITLES[fig_part]}, right after its heading")

    # placeholders
    visible = " ".join(t["text"] for t in R.texts)
    left = len(re.findall(r"\bTODO\b", visible)) + sum(1 for _, i in R.items if i == "TODO")
    if left:
        add("error", f"{left} TODO placeholders left", "write the prose; replace every TODO", True)

    # bare numbers where claims belong
    bare = []
    for t in R.texts:
        if t["part"] in CHECKED[kind] and not t["claim"] and not t["svg"]:
            bare += [m.group(0).strip() for m in BARE.finditer(t["text"])]
    if bare:
        shown = ", ".join(dict.fromkeys(bare))
        add("error", f"{len(bare)} numbers in {'/'.join(sorted(CHECKED[kind]))} are not claims: {shown[:160]}",
            'wrap each in <span data-claim="score|delta|n|count" data-run=…>; numbers drawn inside an <svg> are exempt')

    # claims
    unnamed: dict[str, list[str]] = {}
    goal_set = goal["set"] if goal else None
    for cid, c in R.claims.items():
        issues += _verify(L, c)
        if c["attrs"].get("data-claim") != "target" and not _names_set_and_n(L, R, cid, c, goal_set):
            sk = _claim_set(L, c["attrs"])
            unnamed.setdefault(s["sets"].get(sk, {}).get("name", sk), []).append(" ".join(c["text"].split()))
    for name, shown in unnamed.items():  # one line per set, not one per claim
        add("warn", f"{len(shown)} claims on {name} do not name the set and its n in the same sentence or figure: "
                    + ", ".join(shown[:5]) + (" …" if len(shown) > 5 else ""),
            f"say “{name} (n = …)” in each sentence or caption that uses these numbers")
    if not R.claims and kind == "external":
        add("error", "no claim elements: no number in the paper is backed by the ledger",
            'write numbers as <span data-claim="score" data-run="<run>">74.3%</span>')

    # goal papers: no claim of success the ledger does not back
    if kind == "external" and goal:
        met = L.v.goal_track(about)["met"]
        if not met:
            abstract = " ".join(t["text"] for t in R.texts if t["part"] == "abstract")
            if "draft" not in R.title.lower() and "draft" not in abstract.lower():
                add("error", f"the goal {goal['name']} is not met in the ledger, but the paper does not say draft",
                    "put Draft in the <title> and say so in the abstract")
            if re.search(r"\bachieved\b", visible + " " + R.title, re.I):
                add("error", f"says achieved, but the goal {goal['name']} is not met in the ledger",
                    "remove achieved; state the current number as a claim")
    issues.sort(key=lambda x: x["level"] != "error")
    return issues


def errors(issues: list[dict]) -> list[dict]:
    return [x for x in issues if x["level"] == "error"]


def title_of(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return htmlmod.unescape(m.group(1)).strip() if m else ""


# ---- the template ----------------------------------------------------------

def _e(x) -> str:
    return htmlmod.escape(str(x if x is not None else ""))


def numbers(p: Project, about: str) -> dict:
    """The champion's current numbers on the set a paper is about: set, n, score, last promotion's delta."""
    L = _Ledger(p)
    s, v = L.s, L.v
    goal, hill = s["goals"].get(about), s["hills"].get(about)
    sk = goal["set"] if goal else ((hill or {}).get("eval_sets") or [None])[0]
    metric = (goal or {}).get("metric", "score")
    champ = s["champion"]
    st = s["sets"].get(sk or "", {})
    out = {"set": sk, "set_name": st.get("name", sk), "n": st.get("n"), "metric": metric, "champion": champ,
           "champion_name": s["candidates"].get(champ or "", {}).get("name", champ),
           "goal": about if goal else None, "target": (goal or {}).get("target"),
           "met": v.goal_track(about)["met"] if goal else None}
    run = v.latest_run(champ, sk) if champ and sk else None
    if run:
        out["run"] = run
        out["score"] = v.run_view(run)["summary"].get(METRICS[metric][0])
    prev = next((c["key"] for c in reversed(s["champions"][:-1]) if c["key"] != champ and v.latest_run(c["key"], sk)), None)
    if run and prev:
        base = v.latest_run(prev, sk)
        cmp = v.compare(base, run, metric)
        if cmp.get("n"):
            out.update(base_run=base, base_name=s["candidates"].get(prev, {}).get("name", prev), delta=cmp)
    return out


def _claims(N: dict, L: _Ledger) -> dict:
    """Claim elements for the template, formatted the way check reads them back."""
    pct = L.binary(N["metric"])
    unit = " s" if "latency" in N["metric"] else (" " + L.measure["unit"] if N["metric"] == "score" and L.measure["unit"] else "")
    met = f' data-metric="{N["metric"]}"' if N["metric"] != "score" else ""
    c = {"set": _e(N["set_name"]), "n": f'<span data-claim="n" data-set="{_e(N["set"])}">{N["n"]}</span>'}
    if N.get("score") is not None:
        txt = f'{N["score"] * 100:.1f}%' if pct else f'{N["score"]:.1f}{unit}'
        c["score"] = f'<span data-claim="score" data-run="{_e(N["run"])}"{met}>{txt}</span>'
    if N.get("delta"):
        d = N["delta"]
        k, u = (100, " pts") if pct else (1, unit)
        c["delta"] = (f'<span data-claim="delta" data-base-run="{_e(N["base_run"])}" data-run="{_e(N["run"])}"{met} '
                      f'data-lo="{d["lo"] * k:.1f}" data-hi="{d["hi"] * k:.1f}">{d["delta"] * k:+.1f}{u}</span>')
    if N.get("target") is not None:
        txt = f'{N["target"] * 100:.0f}%' if pct else f'{N["target"]:g}{unit}'
        c["target"] = f'<span data-claim="target" data-goal="{_e(N["goal"])}">{txt}</span>'
    return c


def template(p: Project, about: str, audience: str, title: str | None = None) -> str:
    """A skeleton paper with every required section and the champion's numbers as claim elements."""
    from .asks import THEME_HEAD
    L = _Ledger(p)
    s = L.s
    N = numbers(p, about)
    C = _claims(N, L)
    thing = s["goals"].get(about) or s["hills"].get(about) or {}
    draft = audience == "external" and not N.get("met")
    title = title or (("Draft: " if draft else "") + (thing.get("name") or about))
    score = C.get("score", "TODO (no champion run on this set yet)")
    delta = (f'The last promotion moved it by {C["delta"]} against {_e(N.get("base_name"))} on the {C["set"]} set '
             f'(n = {C["n"]}, paired on the same items).') if C.get("delta") else "TODO: the last paired change."
    target = f' against a target of {C["target"]}' if C.get("target") else ""
    w = 400 * min(max(N.get("score") or 0, 0), 1) if L.binary(N["metric"]) else 0
    mark = ""
    if N.get("target") is not None and L.binary(N["metric"]):
        x = 400 * min(N["target"], 1)
        mark = f'<line x1="{x:.0f}" x2="{x:.0f}" y1="12" y2="48" stroke="currentColor" stroke-width="2"/>'
    fig = f'''<figure>
<svg viewBox="0 0 400 60" role="img" aria-label="Champion against target">
<rect x="0" y="20" width="400" height="20" rx="4" fill="var(--soft, #eee)"/>
<rect x="0" y="20" width="{w:.0f}" height="20" rx="4" fill="var(--champ, currentColor)"/>{mark}
</svg>
<figcaption>Figure 1. {_e(N["champion_name"])} on the {C["set"]} set (n = {C["n"]}): {score}{target}.</figcaption>
</figure>'''
    head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{_e(title)}</title>{THEME_HEAD}'
            '<style>body{max-width:760px;margin:28px auto;padding:0 18px;font-size:16px;line-height:1.6}'
            'figure{margin:16px 0}figure svg{max-width:100%;height:auto}</style></head><body>\n')
    if audience == "external":
        status = " This is a draft: the goal is not met yet." if draft else ""
        body = f'''<h1>{_e(title)}</h1>
<section data-part="abstract"><h2>Abstract</h2>
<p>TODO: the task and why it matters, in one sentence. The champion, {_e(N["champion_name"])}, scores {score} on the {C["set"]} set (n = {C["n"]}){target}.{status}</p>
<p>{delta}</p></section>
<section data-part="introduction"><h2>Introduction</h2><p>TODO: the problem, who needs it solved, and what this paper shows.</p></section>
<section data-part="setup"><h2>Setup</h2><p>TODO: the task, the measure (how one output becomes one number), the eval sets and how they were frozen.</p></section>
<section data-part="method"><h2>Method</h2><p>TODO: the champion's design, and each change that climbed, with what it was predicted to move.</p></section>
<section data-part="results"><h2>Results</h2>
{fig}
<p>The champion scores {score} on the {C["set"]} set (n = {C["n"]}). {delta}</p></section>
<section data-part="negative"><h2>What did not work</h2><p>TODO: rejected candidates and the reason each failed its gate.</p></section>
<section data-part="threats"><h2>Threats to validity</h2><p>TODO: set size, judge noise, overlap between sets, anything that could make these numbers wrong.</p></section>
<section data-part="conclusion"><h2>Conclusion</h2><p>TODO: what the reader should take away. The champion stands at {score} on the {C["set"]} set (n = {C["n"]}).</p></section>'''
    else:
        hill = s["hills"].get(about) or {}
        item = "TODO"
        sym = hill.get("symptom_set")
        if sym in s["sets"]:
            r = L.v.latest_run(s["champion"], sym, complete_only=False) if s["champion"] else None
            bad = [x for x in (L.v.rows(r) if r else []) if x.get("error") or (x.get("score") or 0) < 1]
            ids = s["sets"][sym].get("ids") or []
            item = str(bad[0]["id"]) if bad else (str(ids[0]) if ids else "TODO")
        body = f'''<h1>{_e(title)}</h1>
<section data-part="problem"><h2>Problem</h2><p>{_e(hill.get("symptom") or "TODO: the symptom.")}</p>
<p>One real item: <span data-item="{_e(item)}">{_e(item)}</span>. TODO: what in the input makes the output wrong.</p></section>
<section data-part="measure"><h2>Measure</h2><p>TODO: how one output on this hill becomes one number.</p></section>
<section data-part="sets"><h2>Sets</h2><p>TODO: symptom, eval, training and control sets, and that they share no item.</p></section>
<section data-part="candidates"><h2>Candidates</h2><p>TODO: each change, its prediction, and its gate result.</p></section>
<section data-part="result"><h2>Result</h2>
{fig}
<p>The champion scores {score} on the {C["set"]} set (n = {C["n"]}). {delta}</p></section>
<section data-part="next"><h2>Next</h2><p>TODO: the next change worth trying, and why.</p></section>'''
    return head + body + "\n</body></html>\n"
