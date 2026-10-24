# Posters

A poster is the picture that stands for a model or a hill: on the Models page it is the card, on the model page it is
the large figure at the top. It replaces written explanation. Write one for every model you register and every hill
you open.

```bash
arx model add v8 --parent v7 --hill please-robust --poster scratch/v8.json
arx hill open please-robust --title "Politeness" --target dev-please --poster scratch/hill.json
arx poster model v8 scratch/v8-new.json      # replace one later
```

## The spec

A spec is a small JSON file. The dashboard draws every spec with one template: a thumbnail on the lists, and a
full-width interactive poster at the top of the model or hill page.

```json
{"v": 1,
 "headline": "Check the answer against the drawing's own vector markers",
 "idea": [{"icon": "drawing", "text": "Read the drawing"}, {"icon": "ruler", "text": "Measure circle centers"},
          {"icon": "compare", "text": "Match to legend shapes"}, {"icon": "check", "text": "Answer only if matched"}],
 "result": {"label": "6 hard valve questions",
            "before": {"name": "Parent", "value": 5, "of": 6}, "after": {"name": "This", "value": 6, "of": 6}},
 "also": [{"text": "1 answer lost support", "tone": "bad"}, {"text": "Controls 2/3", "tone": "neutral"}],
 "verdict": "rejected", "why": "Fixed the target but one answer lost its evidence", "tags": ["Valve body versus state"]}
```

| Field | Rule |
|---|---|
| `v` | `1` |
| `headline` | at most 70 chars; the idea as a plain sentence, not the id |
| `idea` | 2 to 4 steps, left to right; each `{icon, text}` with text at most 28 chars |
| `icon` | drawing crop zoom ruler compare tag link graph filter vote brain check cross search code legend layers route count shield clock coin book wand step |
| `result` | optional: `label` (at most 40 chars), `before` and `after` each `{name, value, of}`; omit when nothing was measured |
| `also` | 0 to 3 chips `{text, tone}`, tone `good`, `bad` or `neutral` |
| `verdict` | rejected, passed, champion, candidate, historical, open (hills), climbed (hills) |
| `why` | at most 90 chars; the one reason that matters |
| `tags` | at most 2 short strings, such as the hill title |

At most 16 KB, validated when you run `arx poster`. Never invent a number: every value comes from the ledger text
(`change`, `reason`, decisions, task summaries). For a hill, `headline` is the weakness, `idea` is the failure story in
three steps (ask, model says, truth), `result` is omitted (the dashboard draws the attempts under it), `verdict` is
`open` or `climbed`, and `why` is what fixing it would unlock.

On the large poster, hover or click a step to read it in full, switch the bars between question counts and
percent, and click the stamp to open the reason.

## Other formats

| | |
|---|---|
| Formats | `json` spec, `svg`, `html`, `png`, `jpg`, `webp` |
| Size | at most 2 MB (a spec: 16 KB); images and widgets are about 320 x 180 (16:9), scaled up on the detail page |
| Stored at | `.research/posters/<kind>-<id>.<ext>`, served at `/api/poster/<kind>/<id>`; the parsed spec is also in `/api/state` as `poster_spec` |

Anything else is refused. Ids are used as names only, so a poster can never be written outside `.research/posters/`.
Use an svg, image or html poster only when a spec cannot say it.

## Without a poster

The dashboard derives a spec from the ledger and marks it `auto`. The headline is the title; the steps are the first
clauses of `change` plus an outcome step; the result is the model's best run against its parent (or the champion) on the
same eval set, or a `5/6 to 6/6` pattern found in `reason`; the verdict follows the status and the reason's first
clause is the why. It is a stopgap: write the spec.

## Interactive HTML posters

An `html` poster is a widget. It is shown in a sandboxed frame (`sandbox="allow-scripts"`, no same-origin) and served
with a Content-Security-Policy of `default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'`.
So: one self-contained file, inline CSS and JavaScript, no network, no external fonts or libraries, images as `data:`
URIs. Size it with `vh` and `vmin` so it fills a thumbnail and the large page alike, and support dark mode with
`prefers-color-scheme`.

The worked example is [`examples/posters/politeness-widget.html`](https://github.com/asvskartheek/autoresearch-scaffold/blob/main/examples/posters/politeness-widget.html):
a slider for the number of politeness pairs in training, and two bars that move with it, v7 against v8. The pattern:

```html
<style>:root{--bg:#fff;--ink:#202a32} @media (prefers-color-scheme:dark){:root{--bg:#1d252b;--ink:#e6eaed}}
body{margin:0;height:100vh;background:var(--bg);color:var(--ink);font:13px system-ui;padding:4vmin}</style>
<input id="s" type="range" min="0" max="4000" value="4000">
<div class="bar"><i id="b"></i></div>
<script>
  const s = document.getElementById('s'), b = document.getElementById('b');
  s.oninput = () => b.style.width = (52 + 30 * (1 - Math.exp(-s.value / 1500))) + '%';
  s.oninput();
</script>
```

Keep it to one idea, one control, and one number that changes. Label what is an illustration. Never put client text,
answers or traces in a poster: it is stored with the ledger.

`examples/posters/chunked-retrieval.svg` is a static one, and three specs sit next to it (`plan-then-retrieve.json`,
`strip-politeness.json`, `politeness-hill.json`). `examples/demo/seed.py` attaches all of them.
