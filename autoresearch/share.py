"""Sharing: links that work for someone else, and a self-contained export.

Links. The dashboard listens on loopback only until someone shares a project: `arx share on` mints a token for this
project (`~/.arx/share.json`: {"tokens": {token: {"projects": [key], "created", "by"}}}) and restarts the dashboard on
every interface. A request from another machine needs that token (once as `?k=<token>`, then as a cookie) and only
reaches the projects the token names: /p/<key>/ for those keys, the shared web assets, and nothing else. Writes from
another machine also need a same-origin Origin. Loopback keeps full access. `arx share off` drops this project's tokens.

  arx share on | off | status
  arx share link [#route | paper:<name> | thread:<comment id>]   the LAN link (with token) for someone else
  arx share export [--paper <name>] [-o file.html]                one HTML file that opens anywhere, read-only

Export. The dashboard snapshot is index.html with every stylesheet and script inlined and a fetch shim that answers
the dashboard's own reads (`api/state`, `api/tasks`, `api/comments`, `api/hill/<k>`, `api/task/<id>` for recent tasks,
...) from data embedded at export time; writes answer 403. Papers open from the snapshot as embedded pages. A paper
export is the paper's HTML with the dashboard's base tokens inlined and its comment threads appended as notes.
"""
from __future__ import annotations

import base64
import html as _html
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from . import features, papers, projects

WEB = Path(__file__).resolve().parent / "web"
_lock = threading.Lock()


# ---------- tokens
def _file() -> Path:
    return projects.home() / "share.json"


def config() -> dict:
    try:
        d = json.loads(_file().read_text())
        return d if isinstance(d, dict) and isinstance(d.get("tokens"), dict) else {"tokens": {}}
    except (OSError, ValueError):
        return {"tokens": {}}


def _save(d: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def token_for(key: str, create: bool = False, by: str = "") -> str | None:
    with _lock:
        d = config()
        for t, g in d["tokens"].items():
            if g.get("projects") == [key]:
                return t
        if not create:
            return None
        t = secrets.token_urlsafe(18)
        d["tokens"][t] = dict(projects=[key], created=time.time(), by=by)
        _save(d)
        return t


def revoke(key: str) -> int:
    with _lock:
        d = config()
        gone = [t for t, g in d["tokens"].items() if key in (g.get("projects") or [])]
        for t in gone:
            d["tokens"].pop(t)
        _save(d)
        return len(gone)


def allowed(token: str | None, key: str | None) -> bool:
    """A remote request with this token may read or write project `key` (None: a shared asset, any valid token)."""
    if not token:
        return False
    g = config()["tokens"].get(token)
    if not g:
        return False
    return key is None or key in (g.get("projects") or [])


def granted(token: str | None) -> list[str]:
    g = config()["tokens"].get(token or "") or {}
    return list(g.get("projects") or [])


def sharing() -> bool:
    return bool(config()["tokens"])


def bind_host() -> str:
    return "0.0.0.0" if sharing() else "127.0.0.1"


def lan_ip() -> str:
    """This machine's address on its local network (no packet is sent); loopback when there is none."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


PATH_RX = re.compile(r"(?<![\w.])(?:/(?:Users|home|private|tmp|var|Volumes|workspace|root|opt|mnt|srv|data)/[^\"'<>\n]*?)(?=[\"'<>\n]|\s(?!\S*/)|$)")


def redact(text: str) -> str:
    """What someone else sees: no absolute paths on this machine (a path keeps its last two parts, e.g. …/run/gate.json)."""
    return PATH_RX.sub(lambda m: "…/" + "/".join(m.group(0).rstrip("/").split("/")[-2:]), text)


def scrub(v):
    """redact() over every string in a JSON value (keys included): what goes into a file someone else opens."""
    if isinstance(v, str):
        return redact(v)
    if isinstance(v, dict):
        return {scrub(k) if isinstance(k, str) else k: scrub(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [scrub(x) for x in v]
    return v


def _js(v) -> str:
    """JSON safe inside a <script> element: no "<" at all, so no </script> and no <!-- in it."""
    return json.dumps(v, default=str, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")


def link(key: str, port: int, target: str = "", token: str | None = None) -> str:
    """The URL someone else opens: the project's view, a paper, or one comment thread."""
    token = token or token_for(key)
    base = f"http://{lan_ip()}:{port}/p/{quote(key)}/"
    q = f"?k={token}" if token else ""
    if target.startswith("paper:"):
        return f"{base}papers/{quote(target[6:])}{q}"
    if target.startswith("thread:"):
        return f"{base}{q}{'&' if q else '?'}c={quote(target[7:])}"
    return base + q + ("#" + target.lstrip("#") if target else "")


# ---------- export
def _inline(text: str) -> str:
    """Script or style text safe to put inside its tag."""
    return re.sub(r"</(script|style)", r"<\\/\1", text, flags=re.I)


def _get(p, path: str, q: dict | None = None):
    """The JSON a dashboard read returns, through the same functions the server uses."""
    from . import server
    if path == "api/state":
        return server.state(p)
    if path == "api/tasks":
        return server.all_tasks(p)
    if path.startswith("api/task/"):
        return server.task_detail(p, path.rsplit("/", 1)[1])
    if path.startswith("api/hill/"):
        return server.hill_detail(p, path.split("/", 2)[2])
    if path == "api/papers":
        return papers.papers(p)
    for pre, fn in features.GET:
        if ("/" + path).startswith(pre):
            code, body = fn(p, "/" + path, q or {})[:2]
            return body if code == 200 and not isinstance(body, bytes) else None
    return None


TASK_BUDGET = 6_000_000  # bytes of task detail a snapshot carries in full; past it, older tasks come without per-example rows


def _lite(d: dict) -> dict:
    """A task detail cut to fit: the card, its notes and a thinned curve; no per-example rows."""
    m = d.get("metrics") or []
    step = max(1, len(m) // 120)
    out = dict(task=d.get("task"), metrics=m[::step], events=(d.get("events") or [])[-60:], snapshot_cut=True)
    if d.get("vs_champion"):
        out["vs_champion"] = d["vs_champion"]
    return out


def _compact_rows(d: dict) -> dict:
    if d.get("rows"):
        d["rows"] = [{k: v for k, v in r.items() if v is not None and v is not False} for r in d["rows"]]
    return d


def snapshot_data(p, key: str | None = None, budget: int = TASK_BUDGET) -> dict:
    """Every read the dashboard makes, as embedded JSON: every task's detail, newest first, in full while `budget`
    lasts and cut (no per-example rows) after it."""
    data: dict = {}
    learner = ("api/predictions", "api/understanding", "api/brief")
    guest = getattr(features.REQUEST, "remote", False)  # a share-link guest's snapshot carries nobody's learning record
    for path in ("api/state", "api/tasks", "api/comments", "api/papers", "api/questions", "api/intake", "api/papers-missing") + (() if guest else learner):
        try:
            v = _get(p, path)
        except Exception:  # one feature failing to read never blocks the export
            v = None
        if v is not None:
            data[path] = v
    st = data.get("api/state") or {}
    for h in (st.get("hills") or {}):
        try:
            data[f"api/hill/{h}"] = _get(p, f"api/hill/{h}")
        except Exception:
            pass
    spent = 0
    for t in ((data.get("api/tasks") or {}).get("tasks") or []):
        try:
            d = _compact_rows(_get(p, f"api/task/{t['id']}"))
        except Exception:
            continue
        n = len(json.dumps(d, default=str, separators=(",", ":")))
        if spent + n > budget:
            d = _lite(d)
            n = len(json.dumps(d, default=str, separators=(",", ":")))
        spent += n
        data[f"api/task/{t['id']}"] = d
    data["api/projects"] = [dict(key=key or "", name=(st.get("config") or {}).get("name") or "", root="")]
    try:  # this project's people (names on comments and "Seen" faces); nobody is "here" in a file
        from . import people
        data["api/people"] = dict(people={k: dict(name=v.get("name")) for k, v in people.members(p).items()}, here=[])
    except Exception:
        data["api/people"] = dict(people={}, here=[])
    return scrub(json.loads(json.dumps(data, default=str)))


SHIM = r"""(()=>{const S=window.ARX_SNAP;const _f=window.fetch;
if(!location.hash&&S.view)history.replaceState(null,'','#'+S.view);  // opens on the view it was taken from
const key=u=>{const m=String(u).match(/api\/[^?#]*/);return m?decodeURIComponent(m[0]):null};
const ok=b=>new Response(JSON.stringify(b),{status:200,headers:{'Content-Type':'application/json'}});
// a short line at the foot of the page: what this file cannot show
const note=t=>{let n=document.querySelector('.arx-note');if(!n){n=document.createElement('div');n.className='arx-note';n.setAttribute('role','status');document.body.append(n)}
 n.textContent=t;n.classList.add('on');clearTimeout(n._t);n._t=setTimeout(()=>n.classList.remove('on'),3500)};
window.ARX_NOTE=note;
// writes the page makes on its own (presence, reading time, "seen") are answered quietly; a "seen" marks the thread read here
const quiet=(k,o)=>{if(k==='api/people')return ok(S.data['api/people']);if(k==='api/understanding')return ok({ok:true});
 if(k==='api/comments'){let b={};try{b=JSON.parse(o.body||'{}')}catch(_){}if(b.kind!=='seen')return null;
  const t=((S.data['api/comments']||{}).threads||[]).find(x=>x.id===b.parent);if(t&&b.by)t.seen={...(t.seen||{}),[b.by]:t.last_t};return ok({ok:true})}
 return null};
window.fetch=async(u,o)=>{const k=key(u);if(o&&o.method&&o.method!=='GET'){const q=k&&quiet(k,o);
  return q||new Response('{"error":"read-only snapshot"}',{status:403})}
 if(k&&k in S.data)return ok(S.data[k]);
 if(k)return new Response('{"error":"not in this snapshot"}',{status:404});return _f(u,o)};
const _b=navigator.sendBeacon&&navigator.sendBeacon.bind(navigator);
try{navigator.sendBeacon=(u,d)=>key(u)?true:_b(u,d)}catch(_){}
addEventListener('keydown',e=>{const t=e.composedPath()[0]||{};if(/INPUT|TEXTAREA|SELECT/.test(t.tagName)||t.isContentEditable)return;
 if(!e.metaKey&&!e.ctrlKey&&!e.altKey&&e.key.toLowerCase()==='c')e.stopImmediatePropagation()},true);
// papers and model papers open over the dashboard, in a frame; Back or the close button returns
const SNAPTAG='<script id="snap" type="application/json" data-keep></'+'script>';
const refPage=d=>{const j=JSON.stringify(d).replace(/</g,'\\u003c');return S.ref.tpl.replace(SNAPTAG,()=>SNAPTAG.replace('><',()=>'>'+j+'<'))};
const target=(href,inner)=>{let m=href.match(/(?:^|\/)papers\/([^/?#]+)/);
 if(!m&&inner)m=href.match(/^(?:\.{1,2}\/)?([\w.+-]+?)(?:\.html)?(?:[?#].*)?$/);
 if(m){const n=decodeURIComponent(m[1]);if(S.papers[n]!=null)return {html:S.papers[n]};if(!inner||/papers\//.test(href))return {miss:'paper'};return null}
 m=href.match(/(?:^|\/)reference(?:\/([^/?#]*))?\/?(?:[?#].*)?$/);
 if(m){const n=decodeURIComponent(m[1]||'')||(S.ref&&S.ref.champion),d=S.ref&&S.ref.models[n];return d?{html:refPage(d)}:{miss:'model paper'}}
 return null};
const shut=()=>{const o=document.querySelector('.arx-ov');if(o){o.remove();document.documentElement.style.overflow=''}};
const back=()=>{if(history.state&&history.state.arxov)history.back();else shut()};
addEventListener('popstate',shut);
const go=(e,inner)=>{const a=e.target.closest&&e.target.closest('a[href]');if(!a)return;const h=a.getAttribute('href');if(!h||h[0]==='#')return;
 const t=target(h,inner);if(!t)return;e.preventDefault();e.stopPropagation();if(t.miss)return note(`That ${t.miss} is not in this snapshot`);view(t.html)};
const view=html=>{let o=document.querySelector('.arx-ov');
 if(!o){o=document.createElement('div');o.className='arx-ov';o.innerHTML='<iframe title="Paper"></iframe><button class="arx-x" aria-label="Close">×</button>';
  document.body.append(o);o.lastChild.onclick=back;document.documentElement.style.overflow='hidden';try{history.pushState({arxov:1},'')}catch(_){}}
 const f=o.firstChild;f.onload=()=>{try{const d=f.contentDocument;d.addEventListener('click',e=>go(e,true),true);
  d.addEventListener('keydown',e=>{if(e.key==='Escape')back()})}catch(_){}};f.srcdoc=html};
document.addEventListener('click',e=>go(e,false),true);
addEventListener('keydown',e=>{if(e.key==='Escape'&&document.querySelector('.arx-ov'))back()});
addEventListener('DOMContentLoaded',()=>{const b=document.createElement('div');b.className='arx-snap';
 b.textContent='Snapshot · '+new Date(S.taken*1000).toLocaleString();document.body.append(b);
 const c=new URLSearchParams(location.search).get('c'),ts=(S.data['api/comments']||{}).threads||[];
 if(c&&!ts.some(t=>t.id===c))setTimeout(()=>note('That comment is not in this snapshot'),800);miss()});
// a task or hill view this file has no data for says so instead of loading forever
const miss=()=>{const m=location.hash.match(/^#(task|hill)\/([^?]+)/);if(m&&!(`api/${m[1]}/${decodeURIComponent(m[2])}` in S.data))note(`This ${m[1]} is not in this snapshot`)};
addEventListener('hashchange',miss);})();"""

SNAP_CSS = """.arx-snap{position:fixed;left:12px;bottom:12px;z-index:50;padding:4px 10px;border-radius:999px;font-size:12px;
background:var(--surface,#fff);color:var(--muted,#666);box-shadow:0 0 0 1px var(--border,#ddd)}
.arx-note{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:3000;padding:8px 14px;border-radius:8px;font-size:13px;
background:var(--text,#222);color:var(--surface,#fff);opacity:0;pointer-events:none;transition:opacity .2s}.arx-note.on{opacity:1}
.arx-ov{position:fixed;inset:0;z-index:2500;background:var(--ground,#fff)}.arx-ov iframe{display:block;width:100%;height:100%;border:0}
.arx-x{position:fixed;right:16px;bottom:16px;z-index:2501;width:40px;height:40px;border:0;border-radius:50%;font-size:22px;line-height:1;
cursor:pointer;background:var(--text,#222);color:var(--surface,#fff);box-shadow:0 2px 8px rgba(0,0,0,.25)}
.cm-fab .cm-mode,.cm-chip,.top .live,.top [aria-label=Share]{display:none!important}
.cm-pop textarea,.cm-pop .cm-name,.cm-pop .rs,.cm-pop .go,.cm-me .cm-name,.cm-list .cm-it:not([data-id]),
.gi,.q-form,.q-acts [data-qact]:not([data-qact=read]),.q-askf,
.lrn [data-l=commit],.lrn [data-t=go],.lrn [data-t=skip]{display:none!important}"""
# a snapshot is read-only: every control that writes is hidden (above), C (comment mode) does nothing


SNAP_TAG = '<script id="snap" type="application/json" data-keep></script>'


def _refs(p) -> dict | None:
    """Every model's paper (web/reference.html reads its data from #snap when that is filled): the page once, the data
    per model, so a "Paper" link on a model opens in the snapshot."""
    from . import reference
    tpl = (WEB / "reference.html").read_text()
    if SNAP_TAG not in tpl:
        return None
    models = {}
    for m in p.models():
        try:
            models[m] = scrub(json.loads(json.dumps(reference.build(p, m), default=str)))
        except Exception:  # a model the paper cannot be built for stays out; its link says so
            pass
    return dict(tpl=tpl, models=models, champion=p.champion())


def export_dashboard(p, key: str | None = None, view: str = "") -> str:
    page = (WEB / "index.html").read_text()
    page = re.sub(r"<script>/\* start the ledger reads.*?</script>\n", "", page, flags=re.S)
    page = re.sub(r'<link rel="(?:preconnect|preload)"[^>]*>\n?', "", page)
    page = re.sub(r'<link rel="stylesheet" href="([^"]+)">',
                  lambda m: f"<style>{_inline((WEB / m.group(1)).read_text())}</style>", page)
    page = re.sub(r'<script src="([^"]+)"></script>',
                  lambda m: f"<script>{_inline((WEB / m.group(1)).read_text())}</script>", page)
    snap = dict(taken=time.time(), project=key or "", data=snapshot_data(p, key),
                papers={n: export_paper(p, n) for n in papers.names(p)}, ref=_refs(p),
                view=str(view or "").lstrip("#")[:300])
    head = (f"<script>window.ARX_SNAP={_js(snap)};</script>"
            f"<script>{_inline(SHIM)}</script><style>{SNAP_CSS}</style>")
    return page.replace("<head>", "<head>\n<meta charset=\"utf-8\">" + head, 1)  # the charset within the first 1 KB


def _base_css() -> str:
    return (Path(__file__).resolve().parent / "web" / "app.css").read_text().split("/* app shell")[0]


FIG = re.compile(r"<svg[\s\S]*?</svg>", re.I)
SVG_OK = {"svg", "g", "path", "rect", "circle", "line", "text", "polyline"}  # as comments.js cleanSvg
ATTR_OK = re.compile(r"^(viewbox|width|height|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|d|points|fill|stroke|stroke-width|stroke-dasharray|"
                     r"stroke-linecap|stroke-linejoin|opacity|fill-opacity|stroke-opacity|transform|font-size|font-weight|"
                     r"font-family|text-anchor|dominant-baseline|xmlns|preserveaspectratio)$", re.I)
ATTR_BAD = re.compile(r"url\s*\(|javascript:|expression|&#|\\", re.I)


def clean_svg(src: str) -> str:
    """An agent's figure, safe to put in a file someone else opens: allowed SVG elements and attributes only."""
    from html.parser import HTMLParser
    out, skip = [], [0]

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs, end=False):
            if skip[0] or tag not in SVG_OK:
                skip[0] += 0 if end else 1
                return
            a = "".join(f' {k}="{_html.escape(v or "")}"' for k, v in attrs if ATTR_OK.match(k) and not ATTR_BAD.search(v or ""))
            out.append(f"<{tag}{a}{'/' if end else ''}>")

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs, end=True)

        def handle_endtag(self, tag):
            if skip[0]:
                skip[0] -= 1
            elif tag in SVG_OK:
                out.append(f"</{tag}>")

        def handle_data(self, data):
            if not skip[0]:
                out.append(_html.escape(data))
    P(convert_charrefs=True).feed(src)
    return "".join(out)


PATH_D = re.compile(r"^[MLHVZmlhvz\d.\s,-]{1,20000}$")
TOOLS = ("box", "arrow", "pen", "highlight")
DARK = re.compile(r"""data-theme=["']dark|prefers-color-scheme""")
THEME = ("<script>(()=>{const r=document.documentElement,m=matchMedia('(prefers-color-scheme: dark)');let t=null;"
         "try{t=localStorage.getItem('arx-theme')}catch(e){}const set=()=>{r.dataset.theme=t||(m.matches?'dark':'light')};set();"
         "m.addEventListener&&m.addEventListener('change',set)})()</script>")
NOTES_CSS = """.arx-notes{max-width:760px;margin:48px auto;padding:0 24px;font-size:14px}.arx-notes ol{padding:0;list-style:none}
.arx-notes li{margin:0 0 18px;padding:8px 10px;border-radius:8px;scroll-margin-top:40vh}.arx-notes li:target{box-shadow:0 0 0 2px #e8590c}
.arx-notes li.res{opacity:.7}.arx-nh{display:flex;gap:8px;align-items:baseline}.arx-notes q{color:var(--muted-fg,#666)}
.arx-m{margin:6px 0 0 28px}.arx-m time{color:var(--muted-fg,#888);font-size:12px;margin-left:6px}.arx-fig svg{max-width:100%;height:auto}
.arx-notes summary{cursor:pointer;margin:0 0 12px}.arx-gone{color:var(--muted-fg,#888)}
.arx-pin{display:inline-block;min-width:20px;height:20px;padding:0 4px;box-sizing:border-box;border-radius:10px;background:#e8590c;color:#fff;
font:600 11px/20px system-ui,sans-serif;text-align:center;text-decoration:none;flex:none}.res .arx-pin,.arx-pin.res{opacity:.55}
.arx-ink{position:absolute;left:0;top:0;width:0;height:0;pointer-events:none;z-index:40}
.arx-ink svg{position:absolute;left:0;top:0;width:1px;height:1px;overflow:visible}
.arx-ink path{fill:none;stroke:#e8590c;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.arx-ink .highlight path{stroke:#facc15;stroke-width:16;stroke-opacity:.38}.arx-ink .res path{stroke-opacity:.35}
.arx-ink .arx-pin{position:absolute;pointer-events:auto;box-shadow:0 0 0 2px #fff}"""
# drawn marks on their blocks, as the reader places them (paper.html shapeXf): follow the reference word when it is
# still there, else the block scaled by its width; a numbered pin on each links to its note (#c-<id>)
INK_JS = r"""(()=>{const M=__MARKS__;const L=document.createElement('div');L.className='arx-ink';
L.innerHTML='<svg xmlns="http://www.w3.org/2000/svg"></svg>';document.body.append(L);const svg=L.firstChild;
const blk=b=>[...document.querySelectorAll('[data-block]')].find(x=>x.dataset.block===b)||null;
const texts=b=>{const w=document.createTreeWalker(b,NodeFilter.SHOW_TEXT),o=[];let n,i=0;while((n=w.nextNode())){o.push([n,i]);i+=n.data.length}return o};
const rangeAt=(ns,s,e)=>{const r=document.createRange();let a=0;for(const [n,i] of ns){const j=i+n.data.length;if(!a&&s<=j){r.setStart(n,s-i);a=1}if(a&&e<=j){r.setEnd(n,e-i);return r}}return null};
const word=(b,m)=>{if(!m.suffix)return null;const ns=texts(b);if(!ns.length)return null;const full=ns.map(x=>x[0].data).join('');
 let i=m.prefix?full.indexOf(m.prefix+m.suffix):-1;if(i>=0)i+=m.prefix.length;else i=full.indexOf(m.suffix);return i<0?null:rangeAt(ns,i,i+m.suffix.length)};
const REF=/^M(-?[\d.]+) (-?[\d.]+)M(-?[\d.]+) (-?[\d.]+)(?=M)/;
function draw(){const o=L.getBoundingClientRect();let g='',pins='';
 for(const m of M){const b=m.block?blk(m.block):m.d?document.body:null;if(!b)continue;const br=b.getBoundingClientRect();
  let tx=br.left-o.left,ty=br.top-o.top,k=1,px=tx-24,py=ty;
  if(m.d){const r=REF.exec(m.d),w=r&&word(b,m),wr=w&&w.getClientRects()[0];
   if(wr&&wr.height){k=wr.height/Math.max(1,r[4]-r[2]);tx=wr.left-o.left-r[1]*k;ty=wr.top-o.top-r[2]*k}else k=br.width/Math.max(1,m.bw||br.width);
   g+=`<g class="${m.tool}${m.res?' res':''}" transform="translate(${tx} ${ty}) scale(${k})"><path d="${m.d}"/></g>`;px=tx+m.x*k-10;py=ty+m.y*k-10}
  pins+=`<a class="arx-pin${m.res?' res':''}" id="m-${m.id}" href="#c-${m.id}" style="left:${Math.max(0,px)}px;top:${py}px">${m.n}</a>`}
 svg.innerHTML=g;L.querySelectorAll('.arx-pin').forEach(a=>a.remove());L.insertAdjacentHTML('beforeend',pins)}
const show=()=>{const h=decodeURIComponent(location.hash.slice(1));if(!/^c-/.test(h))return;const el=document.getElementById(h);
 if(!el){const n=document.querySelector('.arx-gone');if(n)n.hidden=false;return}const d=el.closest('details');if(d&&!d.open){d.open=true;el.scrollIntoView({block:'center'})}};
draw();addEventListener('load',draw);addEventListener('resize',draw);document.fonts&&document.fonts.ready.then(draw);
new ResizeObserver(draw).observe(document.body);addEventListener('hashchange',show);show()})()"""


def _when(t) -> str:
    try:
        return time.strftime("%d %b %H:%M", time.localtime(float(t)))
    except (TypeError, ValueError):
        return ""


def _msg_html(m: dict) -> str:
    body = redact(m.get("body") or "")
    figs = "".join(f'<div class="arx-fig">{clean_svg(x)}</div>' for x in FIG.findall(body))
    text = _html.escape(FIG.sub("", body).strip())
    text = re.sub(r"(https?://[^\s<]+[^\s<.,;:)])", r'<a href="\1" target="_blank" rel="noopener">\1</a>', text).replace("\n", "<br>")
    who = "Agent" if m.get("agent") else (m.get("author") or "")
    return f'<div class="arx-m"><b>{_html.escape(who)}</b><time>{_when(m.get("t"))}</time><div>{figs}{text}</div></div>'


def _notes(ths: list[dict]) -> tuple[str, list[dict]]:
    """The threads as notes (open, then resolved folded), each with id c-<thread id> so #c- links land; and the marks."""
    marks, li = [], {False: [], True: []}
    for n, t in enumerate(ths, 1):
        if not re.fullmatch(r"[\w-]{1,80}", str(t.get("id") or "")):
            continue
        a, res = t.get("anchor") or {}, bool(t.get("resolved"))
        sh = a.get("shape") if isinstance(a.get("shape"), dict) else {}
        d = sh.get("d") if isinstance(sh.get("d"), str) and PATH_D.match(sh.get("d")) and sh.get("tool") in TOOLS else None
        block = a.get("block") if isinstance(a.get("block"), str) else ""
        if d or block:
            num = lambda v: float(v) if isinstance(v, (int, float)) else 0
            marks.append(dict(id=t["id"], n=n, block=block, d=d, tool=sh.get("tool") if d else "", bw=num(sh.get("bw")), x=num(sh.get("x")),
                              y=num(sh.get("y")), prefix=str(a.get("prefix") or ""), suffix=str(a.get("suffix") or ""), res=res))
        pin = f'<a class="arx-pin" href="#m-{t["id"]}">{n}</a>' if d or block else f'<span class="arx-pin">{n}</span>'
        quote = _html.escape(redact((a.get("quote") or "").strip())[:160])
        li[res].append(f'<li id="c-{t["id"]}"{" class=res" if res else ""}><div class="arx-nh">{pin}{f"<q>{quote}</q>" if quote else ""}</div>'
                       + "".join(_msg_html(m) for m in t.get("messages") or []) + "</li>")
    if not li[False] and not li[True]:
        return "", []
    html = (f'<aside class="arx-notes"><h2>Comments</h2><p class="arx-gone" hidden>That comment is not in this file.</p>'
            + (f"<ol>{''.join(li[False])}</ol>" if li[False] else "")
            + (f"<details><summary>Resolved · {len(li[True])}</summary><ol>{''.join(li[True])}</ol></details>" if li[True] else "")
            + "</aside>")
    return html, marks


def export_paper(p, name: str) -> str:
    """The paper as one file: base tokens inlined, attachments as data: URLs, links to sibling papers as <name>.html
    (the file `arx share export --paper <name>` writes), the reader's theme, every comment thread as a note with its
    drawn mark on the paper."""
    d = papers.pdir(p, name)
    text = redact((d / "paper.html").read_text())  # before the data: URLs, whose base64 may hold "/Users"

    def data_url(m):
        f = d / "files" / m.group(2)
        if not f.is_file():
            return m.group(0)
        mt = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        return f'{m.group(1)}data:{mt};base64,{base64.b64encode(f.read_bytes()).decode()}'
    text = re.sub(r'((?:src|href)=["\'])(?:\./)?files/([\w.+-]+)', data_url, text)
    known = set(papers.names(p))
    text = re.sub(r'(href=["\'])\.\./([\w.+-]+)/?(?=[#"\'])',
                  lambda m: f"{m.group(1)}{m.group(2)}.html" if m.group(2) in known else m.group(0), text)
    notes, marks = _notes(papers.threads(papers.thread(p, name)))
    if notes:
        notes += f"<style>{NOTES_CSS}</style><script>{_inline(INK_JS.replace('__MARKS__', _js(marks)))}</script>"
    head = f"<style>@layer arx{{{_base_css()}}}</style>" + (THEME if DARK.search(text) else "")
    text = re.sub(r"<head[^>]*>", lambda m: m.group(0) + head, text, count=1) if re.search(r"<head", text, re.I) else head + text
    return re.sub(r"</body>", lambda m: notes + m.group(0), text, count=1, flags=re.I) if re.search(r"</body>", text, re.I) else text + notes


# ---------- HTTP
@features.get("/api/share")
def _status(p, path, q):
    key = projects.key_for(p.root)
    t = token_for(key) if key else None
    port = q.get("_port")
    return 200, dict(on=bool(t), key=key, lan=lan_ip(), link=link(key, int(port), token=t) if t and port else None)


@features.get("/api/export")
def _export(p, path, q):
    key = projects.key_for(p.root)
    if q.get("paper"):
        body, fname = export_paper(p, q["paper"]), f"{q['paper']}.html"
    else:
        body, fname = export_dashboard(p, key, q.get("view") or ""), f"{key or 'arx'}-{time.strftime('%Y%m%d-%H%M')}.html"
    return 200, body.encode(), "text/html; charset=utf-8", {"Content-Disposition": f'attachment; filename="{fname}"'}


# ---------- CLI
def cmd_share(a):
    from .cli import _served, _up
    from .core import Project
    p = Project()
    key = projects.register(p.root)
    if a.verb == "on":
        t = token_for(key, create=True, by=os.environ.get("USER", ""))
        url = _up(p.root, 8890, restart=True)
        port = int(url.rsplit(":", 1)[1])
        print(f"sharing {key} on your network (token {t[:6]}…)\n{link(key, port, a.target or '', t)}")
    elif a.verb == "off":
        n = revoke(key)
        print(f"stopped sharing {key} ({n} token{'s' if n != 1 else ''} revoked)")
        if not sharing():
            _up(p.root, 8890, restart=True)
    elif a.verb == "status":
        t = token_for(key)
        print(f"{key}: {'shared' if t else 'not shared'}; dashboard listens on {bind_host()}")
    elif a.verb == "link":
        base = _served(p)
        if not base:
            sys.exit("the dashboard is not running: arx up")
        port = int(base.split(":")[2].split("/")[0])
        if not token_for(key):
            print("(not shared yet: this link only works on this machine; `arx share on` makes it work for others)", file=sys.stderr)
            print(f"http://127.0.0.1:{port}/p/{quote(key)}/" + ("#" + a.target.lstrip("#") if a.target and ":" not in a.target else ""))
            return
        print(link(key, port, a.target or ""))
    elif a.verb == "export":
        out = Path(a.out or (f"{a.paper}.html" if a.paper else f"{key}-snapshot.html"))
        out.write_text(export_paper(p, a.paper) if a.paper else export_dashboard(p, key), encoding="utf-8")
        print(f"{out}  ({out.stat().st_size / 1e6:.1f} MB, opens anywhere, read-only)")


@features.CLI.append
def _cli(sp):
    s = sp.add_parser("share", help="links that work for someone else on your network, and a self-contained export")
    s.add_argument("verb", choices=["on", "off", "status", "link", "export"])
    s.add_argument("target", nargs="?", help="link: #route, paper:<name> or thread:<comment id>")
    s.add_argument("--paper", help="export: this paper instead of the dashboard")
    s.add_argument("-o", "--out", help="export: the file to write")
    s.set_defaults(fn=cmd_share)
