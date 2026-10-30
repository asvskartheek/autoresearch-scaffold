"""Questions a person asks by clicking the dashboard, and the answers an agent gives. All of it is ledger events."""
from __future__ import annotations

import base64
import html
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import quote, unquote

from .axi import clip
from .store import LedgerError, Project, check_name, registry
from .view import Views

KINDS = {".svg": "svg", ".png": "png", ".jpg": "png", ".jpeg": "png", ".gif": "png", ".webp": "png",
         ".html": "html", ".htm": "html", ".md": "md", ".txt": "text"}
INLINE = ("svg", "md", "text")  # small text parts live in the event; html and images are files
CLAIM_S = 600
MAX_WORDS, BARE_WORDS = 60, 30  # people read answers in a small box by what they clicked  # a claim older than this is taken to be abandoned
SAVE_AS = ("note", "card", "paper")


def new_key() -> str:
    return time.strftime("%m%d-%H%M%S") + "-ask-" + secrets.token_hex(2)


def project_key(p: Project) -> str | None:
    root = str(p.root.resolve())
    return next((k for k, v in registry().items() if v["root"] == root), None)


def ask(p: Project, text: str, kind: str, key: str, what: str, route: str = "", loc: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        raise LedgerError("the question is empty", fix="type what you want to understand")
    return p.append("ask", actor="person", key=new_key(), text=text[:2000], kind=kind, entity=key,
                    what=(what or "")[:300], route=route, loc=loc)


def reply(p: Project, key: str, text: str) -> dict:
    """A follow-up in the same thread: the question opens again, with everything said so far."""
    text = (text or "").strip()
    if key not in p.state()["asks"]:
        raise LedgerError(f"no question {key}", fix="arx2 ask list")
    if not text:
        raise LedgerError("the follow-up is empty", fix="type what you want to understand")
    return p.append("ask.reply", actor="person", key=key, text=text[:2000])


def latest(a: dict) -> str:
    return next(x["text"] for x in reversed(a["thread"]) if x["who"] == "person")


def _turn(x: dict) -> str:
    if x["who"] == "person":
        return f"person: {clip(x['text'], 300)}"
    bits = [clip(y["body"], 400) if y["type"] in ("md", "text") else f"[{y['type']}: {y.get('label') or y.get('file') or 'inline'}]"
            for y in x["parts"]]
    return "agent: " + " ".join(bits).replace("\n", " ")


def owner(a: dict) -> str | None:
    """The agent that answered this thread last: its follow-ups go back to it, since it holds the context."""
    return next((x.get("agent") for x in reversed(a["thread"]) if x["who"] == "agent"), None)


def next_open(s: dict, skip=(), now: float | None = None, agent: str | None = None) -> dict | None:
    now = now or time.time()

    def mine(a):  # a follow-up waits for the agent that owns the thread, unless that agent has gone quiet
        o = owner(a)
        return not o or agent and (o == agent or o.startswith(agent + "/")) or now - s["agents"].get(o, 0) > CLAIM_S

    waiting = [a for a in s["asks"].values() if a["key"] not in skip and mine(a) and
               (a["status"] == "open" or a["status"] == "claimed" and now - a.get("claimed", 0) > CLAIM_S)]
    return min(waiting, key=lambda a: (owner(a) != agent or not agent, a["created"])) if waiting else None


def part_from_file(p: Project, ask_key: str, path: str, n: int) -> dict:
    src = Path(path)
    kind = KINDS.get(src.suffix.lower())
    if not kind:
        raise LedgerError(f"cannot show {src.name}: use svg, png, jpg, gif, html, md or txt", fix="convert it, or pass --text")
    if not src.exists():
        raise LedgerError(f"no file {path}", fix="check the path")
    if kind in INLINE:
        return {"type": kind, "body": src.read_text()[:200_000]}
    dst = p.dir / "answers" / f"{ask_key}-{n}{src.suffix.lower()}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return {"type": kind, "file": dst.name}


def parse_link(spec: str) -> dict:
    label, sep, url = spec.partition("=")
    if not sep or not url.startswith(("#/", "http://", "https://")):
        raise LedgerError(f"link {spec!r} must be label=target, target a dashboard view (#/hill/<key>) or an http url",
                          fix='--link "Hill page=#/hill/<key>"')
    return {"type": "link", "label": label.strip(), "url": url.strip()}


def answer(p: Project, key: str, parts: list[tuple[str, str]], agent: str | None = None) -> dict:
    """parts: (kind, value) in the order given on the command line; kind is text, file or link."""
    if key not in p.state()["asks"]:
        raise LedgerError(f"no question {key}", fix="arx2 ask list")
    if not parts:
        raise LedgerError("an answer needs at least one part", fix='--text "..." or --file diagram.svg or --link "label=#/..."')
    words = sum(len(v.split()) for k, v in parts if k == "text")
    if words > MAX_WORDS:
        raise LedgerError(f"{words} words; an answer has at most {MAX_WORDS}", fix="cut it: one real item, the aggregate with set and n, the takeaway; draw the rest (--file x.svg)")
    if words > BARE_WORDS and not any(k == "file" for k, _ in parts):
        raise LedgerError(f"{words} words and no figure; past {BARE_WORDS} words the numbers go in a figure", fix="--file figure.svg with the numbers, and fewer words")
    out = []
    for i, (kind, val) in enumerate(parts):
        if kind == "text":
            out.append({"type": "md", "body": val})
        elif kind == "file":
            out.append(part_from_file(p, key, val, i))
        else:
            out.append(parse_link(val))
    return p.append("answer", key=key, parts=out, agent=agent)


# ---- what the agent is told about the clicked thing ---------------------------

def _pts(v):
    return "-" if v is None else f"{v * 100:+.1f} pts"


def context(v: Views, a: dict) -> list[str]:
    """Compact facts about the anchored entity, with the run keys an agent needs to pull real rows."""
    s, kind, key = v.s, a.get("kind"), a.get("entity")
    out = []
    if kind == "candidate" and key in s["candidates"]:
        c = s["candidates"][key]
        par = s["candidates"].get(c.get("parent") or "", {}).get("name")
        out += [f"candidate: {c['name']} ({c['status']}), built on {par or '-'}", f"change: {clip(c.get('change') or '', 300)}"]
        if c.get("predict"):
            out.append(f"predicted: {clip(c['predict'], 200)}")
        if c.get("reason"):
            out.append(f"decision: {clip(c['reason'], 300)}")
        for r in v.climb(key):
            vv, cmp = r["v"], r["v"].get("cmp") or {}
            st = s["sets"].get(r["set"], {})
            out.append(f"  rung {r['name']}: set {st.get('name', r['set'])} [{r['set']}] n={cmp.get('n', st.get('n'))} "
                       f"{vv['state']} delta={_pts(cmp.get('delta'))} 90%=[{_pts(cmp.get('lo'))}, {_pts(cmp.get('hi'))}] "
                       f"run={vv.get('run') or '-'} base_run={vv.get('base_run') or '-'}")
    elif kind == "hill" and key in s["hills"]:
        h = s["hills"][key]
        pt = s["patterns"].get(h.get("pattern") or "", {})
        out += [f"hill: {h['name']} ({h['status']})", f"symptom: {clip(h.get('symptom') or '', 300)}"]
        if pt.get("count"):
            out.append(f"prevalence: {pt['count']} of {pt.get('of')} {pt.get('of_what') or ''}".rstrip())
        for role in ("symptom_set", "eval_sets", "train_sets", "control"):
            ks = h.get(role) or []
            for sk in [ks] if isinstance(ks, str) else ks:
                out.append(f"  {role}: {s['sets'].get(sk, {}).get('name', sk)} [{sk}] n={s['sets'].get(sk, {}).get('n')}")
        tried = [ck for ck, c in s["candidates"].items() if c.get("hill") == key]
        out.append(f"candidates on this hill: {len(tried)} ({', '.join(tried[-6:])})")
    elif kind == "set" and key in s["sets"]:
        st = s["sets"][key]
        out += [f"set: {st['name']} role={st['role']} n={st['n']} dataset={st.get('dataset')}", f"purpose: {clip(st.get('purpose') or '', 200)}"]
        runs = [(rk, r["candidate"]) for rk, r in s["runs"].items() if r["set"] == key]
        out.append(f"runs on it: {len(runs)} (latest: {', '.join(f'{rk} by {ck}' for rk, ck in runs[-4:])})")
    elif kind == "goal" and key in s["goals"]:
        g = s["goals"][key]
        tr = v.goal_track(key)
        out += [f"goal: {g['name']} {g.get('metric')} on {g['set']} target {g['target']}, now {tr['current']} (met={tr['met']})",
                f"wish: {clip(g.get('vague') or '', 200)}"]
    elif kind == "task" and key in s["tasks"]:
        t = s["tasks"][key]
        out += [f"task: {t['name']} ({t['status']}) {t.get('done')}/{t.get('total')}", f"about: {clip(t.get('about') or '', 200)}"]
        out += [f"  note: {clip(n['text'], 200)}" for n in t["notes"][-3:]]
    else:
        champ = s["candidates"].get(s["champion"] or "", {})
        out += [f"project: {s['project'].get('name')}: {s['project'].get('task')}", f"champion: {champ.get('name')} [{s['champion']}]"]
    out.append(f"rows: {v.p.dir / 'rows'}/<run>.jsonl (id, score, cost, latency_s, error); views: arx2/view.py Views")
    return out


def describe(p: Project, a: dict, base_url: str = os.environ.get("ARX2_URL", "http://127.0.0.1:8790/")) -> str:
    v = Views(p)
    pk = project_key(p)
    turns = a["thread"]
    lines = [f"ask: {a['key']}", f"question: {latest(a)}" + (" (follow-up)" if len(turns) > 1 else ""),
             f"clicked: {a.get('what') or '-'}", f"entity: {a.get('kind')} {a.get('entity')}"]
    if pk:
        lines.append(f"page: {base_url}#/p/{pk}/{a.get('route') or ''}")
    if len(turns) > 1:
        lines.append(f"thread[{len(turns) - 1}] (earlier turns, oldest first):")
        lines += ["  " + _turn(x) for x in turns[:-1]]
    lines.append("context:")
    lines += ["  " + x for x in context(v, a)]
    return "\n".join(lines)


# ---- saving an answer as a note, card or paper ----------------------------------

def _md_html(text: str) -> str:
    out = []
    for b in re.split(r"\n{2,}", text.strip()):
        e = html.escape(b)
        e = re.sub(r"`([^`]+)`", r"<code>\1</code>", e)
        e = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", e)
        e = re.sub(r"(^|[^*\w])\*([^*\s][^*]*)\*", r"\1<i>\2</i>", e)
        lines = e.split("\n")
        if all(re.match(r"[-*] ", l) for l in lines):
            out.append("<ul>" + "".join(f"<li>{l[2:]}</li>" for l in lines) + "</ul>")
        elif re.match(r"#{1,3} ", e):
            out.append(f"<h3>{e.lstrip('#').strip()}</h3>")
        else:
            out.append(f"<p>{'<br>'.join(lines)}</p>")
    return "".join(out)


def clean_svg(svg: str) -> str:
    svg = re.sub(r"<script.*?</script>", "", svg, flags=re.S | re.I)
    return re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", svg)


# Answer pages use the dashboard's colour tokens (var(--ink), var(--sheet), ...) and follow its theme: the pinned
# choice when the page can read it, otherwise the theme of the frame it sits in.
THEME_HEAD = ('<meta name="color-scheme" content="light dark"><link rel="stylesheet" href="/static/app.css">'
              '<script>try{const t=localStorage.getItem("arx2.theme");if(t==="light"||t==="dark")'
              'document.documentElement.dataset.theme=t}catch(e){}</script>'
              '<style>html,body{background:var(--sheet)}body{margin:10px}</style>')


def themed(page: str) -> str:
    m = re.search(r"<head[^>]*>", page, re.I) or re.match(r"\s*<!doctype[^>]*>", page, re.I)
    if m:
        return page[:m.end()] + THEME_HEAD + page[m.end():]
    return "<!doctype html>" + THEME_HEAD + page


def note_html(p: Project, a: dict, title: str) -> str:
    """A self-contained page for the saved answer: images inlined, explorables in sandboxed frames."""
    pk = project_key(p) or ""
    body = []
    for i, turn in enumerate(a["thread"]):
        if turn["who"] == "person":
            if i:
                body.append(f'<p class="q">{html.escape(turn["text"])}</p>')
            continue
        for x in turn["parts"]:
            if x["type"] in ("md", "text"):
                body.append(_md_html(x["body"]))
            elif x["type"] == "svg":
                body.append(f'<figure>{clean_svg(x["body"])}</figure>')
            elif x["type"] == "png":
                f = p.dir / "answers" / x["file"]
                mime = {".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".webp": "webp"}.get(f.suffix, "png")
                body.append(f'<figure><img src="data:image/{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"></figure>')
            elif x["type"] == "html":
                src = html.escape(themed((p.dir / "answers" / x["file"]).read_text()), quote=True)
                body.append(f'<iframe sandbox="allow-scripts" srcdoc="{src}"></iframe>')
            elif x["type"] == "link":
                url = x["url"]
                m = re.match(r"#/(set|hill|cand|goal|task|doc)/(.+)$", url)
                if m:
                    url = f"#/p/{pk}/{m[1]}/{quote(unquote(m[2]), safe='')}"
                elif url.startswith("#/") and not url.startswith("#/p/"):
                    url = f"#/p/{pk}/{url[2:]}"
                href = "/" + url if url.startswith("#") else url
                body.append(f'<p><a target="_top" href="{html.escape(href)}">{html.escape(x["label"])} →</a></p>')
    return f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>{THEME_HEAD}
<style>body{{max-width:760px;margin:28px auto;padding:0 18px;font-size:15px;line-height:1.55}}
.q{{color:var(--ink2);border-left:3px solid var(--line);padding-left:12px;font-weight:600}}
figure{{margin:14px 0}}figure svg,figure img{{max-width:100%;height:auto}}a{{color:var(--live)}}
iframe{{width:100%;height:360px;border:1px solid var(--line);border-radius:8px;background:var(--sheet)}}
code{{font:12px var(--mono);background:var(--soft);padding:1px 4px;border-radius:4px}}</style>
<h1>{html.escape(title)}</h1><p class="small mute">{html.escape(a.get('what') or '')}</p><p class="q">{html.escape(a['text'])}</p>
{''.join(body)}"""


def answer_text(a: dict) -> str:
    return "\n\n".join(x["body"] for ans in a["answers"] for x in ans["parts"] if x["type"] in ("md", "text"))


def save(p: Project, key: str, as_: str, name: str) -> dict:
    a = p.state()["asks"].get(key)
    if not a:
        raise LedgerError(f"no question {key}", fix="arx2 ask list")
    if not a["answers"]:
        raise LedgerError("nothing to save yet: the question has no answer", fix=f"arx2 ask answer {key} --text ...")
    if as_ not in SAVE_AS:
        raise LedgerError(f"save as one of {', '.join(SAVE_AS)}")
    if as_ == "card":
        back = answer_text(a) or "See the saved answer on the dashboard."
        return p.append("card", actor="person", key=f"ask-{key}", front=a["text"], back=clip(back, 600),
                        about=a.get("entity"), ask=key)
    name = check_name(name, "note name")
    dkey = f"{as_}-{key}"
    f = p.dir / "docs" / f"{dkey}.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(note_html(p, a, name))
    return p.append("doc", actor="person", key=dkey, kind=as_, name=name, file=f.name, about=a.get("entity"),
                    about_kind=a.get("kind"), audience="internal", title=a["text"][:140], ask=key)
