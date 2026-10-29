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


def snapshot_data(p, key: str | None = None, tasks: int = 40) -> dict:
    data: dict = {}
    for path in ("api/state", "api/tasks", "api/comments", "api/papers", "api/questions", "api/predictions",
                 "api/understanding", "api/brief", "api/intake", "api/papers-missing"):
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
    for t in ((data.get("api/tasks") or {}).get("tasks") or [])[:tasks]:
        try:
            data[f"api/task/{t['id']}"] = _get(p, f"api/task/{t['id']}")
        except Exception:
            pass
    data["api/projects"] = [dict(key=key or "", name=(st.get("config") or {}).get("name") or "", root="")]
    data["api/people"] = dict(people={}, here=[])
    return data


SHIM = r"""(()=>{const S=window.ARX_SNAP;const _f=window.fetch;
const key=u=>{const m=String(u).match(/api\/[^?#]*/);return m?decodeURIComponent(m[0]):null};
window.fetch=async(u,o)=>{const k=key(u);if(o&&o.method&&o.method!=='GET')return new Response('{"error":"read-only snapshot"}',{status:403});
 if(k&&k in S.data)return new Response(JSON.stringify(S.data[k]),{status:200,headers:{'Content-Type':'application/json'}});
 if(k)return new Response('{"error":"not in this snapshot"}',{status:404});return _f(u,o)};
// papers open as embedded pages
document.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('a[href]');if(!a)return;
 const m=a.getAttribute('href').match(/papers\/([^/?#]+)/);if(!m||!S.papers[decodeURIComponent(m[1])])return;e.preventDefault();
 const w=window.open(URL.createObjectURL(new Blob([S.papers[decodeURIComponent(m[1])]],{type:'text/html'})),'_blank');},true);
addEventListener('DOMContentLoaded',()=>{const b=document.createElement('div');b.className='arx-snap';
 b.textContent='Snapshot · '+new Date(S.taken*1000).toLocaleString();document.body.append(b)});})();"""

SNAP_CSS = """.arx-snap{position:fixed;left:12px;bottom:12px;z-index:50;padding:4px 10px;border-radius:999px;font-size:12px;
background:var(--surface,#fff);color:var(--muted,#666);box-shadow:0 0 0 1px var(--border,#ddd)}
.cm-fab .cm-mode,.cm-chip{display:none!important}"""


def export_dashboard(p, key: str | None = None) -> str:
    page = (WEB / "index.html").read_text()
    page = re.sub(r"<script>/\* start the ledger reads.*?</script>\n", "", page, flags=re.S)
    page = re.sub(r'<link rel="(?:preconnect|preload)"[^>]*>\n?', "", page)
    page = re.sub(r'<link rel="stylesheet" href="([^"]+)">',
                  lambda m: f"<style>{_inline((WEB / m.group(1)).read_text())}</style>", page)
    page = re.sub(r'<script src="([^"]+)"></script>',
                  lambda m: f"<script>{_inline((WEB / m.group(1)).read_text())}</script>", page)
    snap = dict(taken=time.time(), project=key or "", data=snapshot_data(p, key),
                papers={n: export_paper(p, n) for n in papers.names(p)})
    head = (f"<script>window.ARX_SNAP={_inline(json.dumps(snap, default=str))};</script>"
            f"<script>{_inline(SHIM)}</script><style>{SNAP_CSS}</style>")
    return page.replace("<head>", "<head>\n" + head, 1)


def _base_css() -> str:
    return (Path(__file__).resolve().parent / "web" / "app.css").read_text().split("/* app shell")[0]


FIG = re.compile(r"<svg[\s\S]*?</svg>", re.I)


def export_paper(p, name: str) -> str:
    """The paper as one file: base tokens inlined, attachments as data: URLs, its threads appended as notes."""
    d = papers.pdir(p, name)
    text = (d / "paper.html").read_text()

    def data_url(m):
        f = d / "files" / m.group(2)
        if not f.is_file():
            return m.group(0)
        mt = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        return f'{m.group(1)}data:{mt};base64,{base64.b64encode(f.read_bytes()).decode()}'
    text = re.sub(r'((?:src|href)=["\'])(?:\./)?files/([\w.+-]+)', data_url, text)
    ths = [t for t in papers.threads(papers.thread(p, name)) if not t.get("resolved")]
    notes = ""
    if ths:
        items = "".join(
            f"<li><q>{_html.escape((t.get('anchor') or {}).get('quote') or '')[:160]}</q>"
            + "".join(f"<p><b>{_html.escape(m['author'])}</b> {_html.escape(FIG.sub('[figure]', m['body']))}</p>" for m in t["messages"])
            + "</li>" for t in ths)
        notes = (f'<aside class="arx-notes"><h2>Open comments</h2><ol>{items}</ol></aside>'
                 "<style>.arx-notes{max-width:760px;margin:48px auto;padding:0 24px;font-size:14px}"
                 ".arx-notes li{margin:0 0 16px}.arx-notes q{color:var(--muted-fg,#666)}.arx-notes p{margin:4px 0}</style>")
    style = f"<style>@layer arx{{{_base_css()}}}</style>"
    text = re.sub(r"<head[^>]*>", lambda m: m.group(0) + style, text, count=1) if re.search(r"<head", text, re.I) else style + text
    return re.sub(r"</body>", notes + "</body>", text, count=1, flags=re.I) if notes else text + notes


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
        body, fname = export_dashboard(p, key), f"{key or 'arx'}-{time.strftime('%Y%m%d-%H%M')}.html"
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
        out.write_text(export_paper(p, a.paper) if a.paper else export_dashboard(p, key))
        print(f"{out}  ({out.stat().st_size / 1e6:.1f} MB, opens anywhere, read-only)")


@features.CLI.append
def _cli(sp):
    s = sp.add_parser("share", help="links that work for someone else on your network, and a self-contained export")
    s.add_argument("verb", choices=["on", "off", "status", "link", "export"])
    s.add_argument("target", nargs="?", help="link: #route, paper:<name> or thread:<comment id>")
    s.add_argument("--paper", help="export: this paper instead of the dashboard")
    s.add_argument("-o", "--out", help="export: the file to write")
    s.set_defaults(fn=cmd_share)
