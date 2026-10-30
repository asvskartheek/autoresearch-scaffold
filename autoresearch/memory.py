"""Learner memory: what each person has seen, answered and understood, across every project, for months.

One SQLite file per machine, `~/.arx/memory.sqlite` (or `$ARX_HOME`), WAL mode, migrated by `PRAGMA user_version`.
The project ledgers stay the source of truth: memory reads their append-only files incrementally (an offset per file)
and never writes to a project. Live writes and the backfill take the same path, and every event's id is a hash of the
project, the file and the raw line, so reading a file twice changes nothing.

Read from each project's `.research/`:
  predictions.jsonl    Brief predictions            -> predict (hit, conf, a numeric guess)
  teach.jsonl          method attempts and skips    -> attempt (method, hit, err, ms) / skip
  understanding.jsonl  time on a card or doc, checks -> seen (Brief card) / read (paper, explainer) / check (concept)
  comments.jsonl       dashboard comments           -> comment / reply / thread_seen (person's own, no body)
  papers/*/thread.jsonl paper threads               -> the same, on a paper
  questions.json       questions people asked       -> question
Never stored: card questions, option labels, comment bodies, hill examples, or any other project text (some projects
hold client data). Kept: ids, categories, numbers, and the person's own typed answers (code lines, explanations).

Concepts: general ones with stable ids (`paired`, `ci`, `ladder`, `hill`, `goal`) and per-project ones
(`hill:<project>/<name>`, `model:<project>/<name>`, `goal:<project>/<name>`). An event touches one or more.

Knowledge (per person and concept) is rebuilt from that person's events whenever they change, so it never drifts:
  graded events (a hit or a miss) drive a spaced-repetition schedule: stability S in days (the gap after which recall
  drops to 90%), mastery m (a moving average of hits), due = last review + S.
  a hit after a real gap multiplies S by 2.5 (hard methods 3), a hit while crammed by 1.3; a miss cuts S to 35%.
  strength now = m * 0.9 ** (days since review / S). Exposures (seen, read, skip, comment) only update last seen.

  GET /api/memory?viewer=<person id>   {person, name, now, concepts, due, methods, changed, projects}
  arx memory [show|due|changed|backfill] [--viewer ID]
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import features, projects

DAY = 86400.0
GENERAL = dict(paired="Paired delta", ci="Interval crosses zero", ladder="The gate ladder", hill="Hills", goal="Goals")
HARD = {"code", "explain", "prototype"}
SCHEMA = [
    """
    CREATE TABLE people (id TEXT PRIMARY KEY, name TEXT, first REAL, last REAL);
    CREATE TABLE concepts (id TEXT PRIMARY KEY, project TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL, title TEXT,
                           parent TEXT, added REAL);
    CREATE TABLE events (uid TEXT PRIMARY KEY, t REAL NOT NULL, person TEXT NOT NULL, project TEXT NOT NULL,
                         kind TEXT NOT NULL, ref TEXT, method TEXT, hit INTEGER, err REAL, ms REAL, conf REAL,
                         answer TEXT, source TEXT NOT NULL DEFAULT 'live');
    CREATE INDEX events_person ON events (person, t);
    CREATE TABLE event_concepts (uid TEXT NOT NULL, concept TEXT NOT NULL, PRIMARY KEY (uid, concept));
    CREATE INDEX event_concepts_concept ON event_concepts (concept);
    CREATE TABLE knowledge (person TEXT NOT NULL, concept TEXT NOT NULL, project TEXT NOT NULL DEFAULT '',
                            mastery REAL, stability REAL, reps INTEGER, lapses INTEGER, n INTEGER, hits INTEGER,
                            seen INTEGER, ms REAL, last_seen REAL, last_review REAL, last_hit INTEGER, due REAL,
                            PRIMARY KEY (person, concept));
    CREATE INDEX knowledge_due ON knowledge (person, due);
    CREATE TABLE sources (project TEXT NOT NULL, path TEXT NOT NULL, pos INTEGER NOT NULL, mtime REAL,
                          PRIMARY KEY (project, path));
    """,
]
_lock = threading.RLock()


def path() -> Path:
    return projects.home() / "memory.sqlite"


@contextmanager
def db():
    """A connection with the schema migrated; commits on success. One writer per process at a time (WAL lets
    readers and other processes through)."""
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        migrate(con)
        with _lock:
            yield con
            con.commit()
    finally:
        con.close()


def migrate(con: sqlite3.Connection) -> int:
    v = con.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(SCHEMA[v:], start=v + 1):
        con.executescript("BEGIN;" + sql + f"PRAGMA user_version={i};COMMIT;")
    return len(SCHEMA)


# ---------------------------------------------------------------- who and what
def _roster() -> dict:
    from . import people
    return people.roster()


def person(viewer, roster: dict | None = None) -> str | None:
    """The person an event belongs to: a person id as is; a name (written before ids existed) maps to the one person
    who has or had it; anything else stays its own person. Anonymous rows belong to no one."""
    from . import people
    v = str(viewer or "").strip()[:60]
    if not v or v == "anon":
        return None
    if people.ID.match(v):
        return v
    r = _roster() if roster is None else roster
    ids = [k for k, p in r.items() if v in {p.get("name"), *(p.get("aka") or [])}]
    return ids[0] if len(ids) == 1 else v


def card_concepts(key: str, cid: str) -> list[str]:
    """The concepts a Brief card (learn.py ids: "<kind>|<args>") exercises."""
    kind, *a = str(cid or "").split("|")
    out: list[str] = []
    if kind in ("promote", "rej", "run"):
        out += ["paired", "ci"]
    elif kind == "gate":
        out += ["ladder", "ci"]
    elif kind == "batch":
        out += ["paired"]
    elif kind == "hill" and a:
        out += ["hill", f"hill:{key}/{a[0]}"]
    elif kind == "goal" and a:
        out += ["goal", f"goal:{key}/{a[0]}"]
    if kind in ("promote", "rej", "gate", "run") and a:
        out.append(f"model:{key}/{a[0]}")
    return out


def doc_concepts(key: str, doc: str, check: str | None = None, known: dict | None = None) -> list[str]:
    """Concepts of a doc read on the dashboard: a Brief concept tile, or a paper about a hill or goal."""
    d = str(doc or "")
    if d.startswith("concept:"):
        c = d[8:]
        return ["hill", f"hill:{key}/{c[5:]}"] if c.startswith("hill:") else [c] if c in GENERAL else []
    name = d[6:] if d.startswith("paper:") else d
    return (known or {}).get(name, [])


def route_concepts(key: str, route: str) -> list[str]:
    """A comment's page: hill/<name>, model/<name>, goal/<name>."""
    kind, _, name = str(route or "").lstrip("#").partition("/")
    return [kind, f"{kind}:{key}/{name}"] if kind in ("hill", "goal") and name else [f"model:{key}/{name}"] if kind == "model" and name else []


def _title(cid: str) -> tuple[str, str, str, str | None]:
    """(project, kind, title, parent) of a concept id."""
    if cid in GENERAL:
        return "", "general", GENERAL[cid], None
    kind, _, rest = cid.partition(":")
    key, _, name = rest.partition("/")
    return key, kind, name, kind if kind in ("hill", "goal") else None


# ---------------------------------------------------------------- reading the ledgers
def _uid(*xs) -> str:
    return hashlib.sha1("\x1f".join(map(str, xs)).encode()).hexdigest()[:20]


def _num(x):
    try:
        f = float(x)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _hit(x):
    return None if x is None else int(bool(x))


SAFE_CHOICES = {"Pass", "Fail", "Yes", "No", "Better", "Worse", "Can't tell yet"}


def _events_from(key: str, name: str, r: dict, ctx: dict) -> list[tuple[dict, list[str]]]:
    """One ledger row -> [(event, concepts)]. Nothing but ids, categories, numbers and the person's own answers."""
    roster = ctx["roster"]
    t = _num(r.get("t"))
    if t is None:
        return []
    if name == "predictions.jsonl":
        who = person(r.get("viewer"), roster)
        g = r.get("guess")
        guess = g if isinstance(g, (int, float)) and not isinstance(g, bool) else g if g in SAFE_CHOICES else None
        return [(dict(t=t, person=who, kind="predict", ref=r.get("card"), method="predict", hit=_hit(r.get("hit")),
                      conf=_num(r.get("conf")), answer=None if guess is None else json.dumps(guess)),
                 card_concepts(key, r.get("card")))] if who else []
    if name == "teach.jsonl":
        who = person(r.get("viewer"), roster)
        if not who:
            return []
        got = (r.get("show") or {}).get("got") if isinstance(r.get("show"), dict) else None
        ev = dict(t=t, person=who, kind="skip" if r.get("skip") else "attempt", ref=r.get("card"), method=r.get("method"),
                  hit=None if r.get("skip") else _hit(r.get("hit")), err=_num(r.get("err")), ms=_num(r.get("ms")),
                  answer=None if got is None else json.dumps(dict(got=got)))
        extra = ["paired"] if r.get("method") == "code" else []  # writing the line is the paired delta itself
        return [(ev, card_concepts(key, r.get("card")) + extra)]
    if name == "understanding.jsonl":
        who = person(r.get("viewer"), roster)
        if not who:
            return []
        doc, step, chk = str(r.get("doc") or ""), r.get("step"), r.get("check")
        if doc == "brief":  # time on a card; a check equal to the card is the prediction's echo, graded there
            return [(dict(t=t, person=who, kind="seen", ref=str(step), ms=_num(r.get("ms"))), card_concepts(key, step))]
        cs = doc_concepts(key, doc, chk, ctx["papers"])
        if chk and r.get("ok") is not None and doc.startswith("concept:"):
            return [(dict(t=t, person=who, kind="check", ref=str(chk), hit=_hit(r.get("ok")), ms=_num(r.get("ms"))), cs)]
        return [(dict(t=t, person=who, kind="read", ref=f"{doc}#{step}" if step is not None else doc, ms=_num(r.get("ms"))), cs)]
    # comments: the dashboard's (anchor.route) and a paper's thread (the paper's hill or goal)
    k = r.get("kind")
    who = person(r.get("by"), roster) if r.get("by") else None
    if not who or r.get("agent") or k not in ("comment", "reply", "seen"):
        return []
    if name == "comments.jsonl":
        route = (r.get("anchor") or {}).get("route") if isinstance(r.get("anchor"), dict) else None
        cs = route_concepts(key, route) if k == "comment" else ctx["threads"].get(r.get("parent"), [])
        if k == "comment":
            ctx["threads"][r.get("id")] = cs
        ref = r.get("id") if k == "comment" else r.get("parent")
    else:  # papers/<paper>/thread.jsonl
        cs = ctx["papers"].get(name.split("/")[1], [])
        ref = "paper:" + name.split("/")[1]
    return [(dict(t=t, person=who, kind="thread_seen" if k == "seen" else k, ref=ref), cs)]


def _paper_concepts(key: str, root: Path) -> dict:
    """paper name -> concepts, from each paper's meta (hill / goal) or its name when that is a hill or goal."""
    out = {}
    d = root / ".research" / "papers"
    try:
        hills = set(json.loads((root / ".research" / "hills.json").read_text()) or {}) if (root / ".research" / "hills.json").exists() else set()
    except (OSError, ValueError):
        hills = set()
    for pd in (d.iterdir() if d.is_dir() else []):
        try:
            meta = json.loads((pd / "meta.json").read_text()) if (pd / "meta.json").exists() else {}
        except (OSError, ValueError):
            meta = {}
        if meta.get("hill") or pd.name in hills:
            out[pd.name] = ["hill", f"hill:{key}/{meta.get('hill') or pd.name}"]
        elif meta.get("goal"):
            out[pd.name] = ["goal", f"goal:{key}/{meta['goal']}"]
    return out


def _files(root: Path) -> list[str]:
    d = root / ".research"
    fs = ["predictions.jsonl", "teach.jsonl", "understanding.jsonl", "comments.jsonl"]
    pd = d / "papers"
    fs += [f"papers/{x.name}/thread.jsonl" for x in sorted(pd.iterdir())] if pd.is_dir() else []
    return [f for f in fs if (d / f).exists()]


def _insert(con, key: str, ev: dict, cs: list[str], uid: str, source: str) -> bool:
    cur = con.execute("INSERT OR IGNORE INTO events (uid, t, person, project, kind, ref, method, hit, err, ms, conf, answer, source)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (uid, ev["t"], ev["person"], key, ev["kind"], ev.get("ref"), ev.get("method"), ev.get("hit"), ev.get("err"),
                       ev.get("ms"), ev.get("conf"), ev.get("answer"), source))
    if not cur.rowcount:
        return False
    for c in dict.fromkeys(cs):
        con.execute("INSERT OR IGNORE INTO event_concepts VALUES (?,?)", (uid, c))
        if not con.execute("SELECT 1 FROM concepts WHERE id=?", (c,)).fetchone():
            proj, kind, title, parent = _title(c)
            con.execute("INSERT OR IGNORE INTO concepts VALUES (?,?,?,?,?,?)", (c, proj, kind, title, parent, ev["t"]))
    con.execute("INSERT INTO people (id, first, last) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET"
                " first=min(first, excluded.first), last=max(last, excluded.last)", (ev["person"], ev["t"], ev["t"]))
    return True


def sync(key: str, root: Path, source: str = "live", full: bool = False) -> dict:
    """Read what is new in one project's ledgers into memory (read-only on the project). `full` rereads every file
    from the start (a backfill; already-known rows are skipped by their uid). Returns {added, people}."""
    root = Path(root)
    d = root / ".research"
    touched: set = set()
    added = 0
    ctx = dict(roster=_roster(), papers=_paper_concepts(key, root), threads={})
    with db() as con:
        for name in _files(root):
            f = d / name
            st = f.stat()
            row = con.execute("SELECT pos, mtime FROM sources WHERE project=? AND path=?", (key, name)).fetchone()
            if row and not full and st.st_size == row["pos"]:
                continue
            pos = 0 if full or not row or st.st_size < row["pos"] else row["pos"]
            if name == "comments.jsonl":
                pos = 0  # replies find their thread's page through the comment, which may sit before the offset
            with open(f, "rb") as fh:
                fh.seek(pos)
                data = fh.read()
            end = data.rfind(b"\n") + 1  # a writer may be mid-line: leave the tail for next time
            for line in data[:end].splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                for i, (ev, cs) in enumerate(_events_from(key, name, r, ctx)):
                    if _insert(con, key, ev, cs, _uid(key, name, line.decode(errors="replace"), i), source):
                        added += 1
                        touched.add(ev["person"])
            con.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?,?)", (key, name, pos + end, st.st_mtime))
        added += _questions(con, key, d, ctx, source, touched)
        for who in touched:
            rebuild(con, who)
    return dict(added=added, people=sorted(touched))


def _questions(con, key, d: Path, ctx: dict, source: str, touched: set) -> int:
    f = d / "questions.json"
    try:
        qs = json.loads(f.read_text()) if f.exists() else {}
    except (OSError, ValueError):
        return 0
    n = 0
    for qid, q in (qs.items() if isinstance(qs, dict) else []):
        if not isinstance(q, dict) or q.get("by") in (None, "agent", "you"):
            continue
        who = person(q.get("by"), ctx["roster"])
        t = _num(q.get("created"))
        if not who or not who.startswith("p-") or t is None:  # agents ask questions under their own names too
            continue
        kind, _, name = str(q.get("parent") or "").partition(":")
        cs = {"h": ["hill", f"hill:{key}/{name}"], "g": ["goal", f"goal:{key}/{name}"], "m": [f"model:{key}/{name}"]}.get(kind, []) if name else []
        if _insert(con, key, dict(t=t, person=who, kind="question", ref=qid), cs, _uid(key, "questions.json", qid, t), source):
            n += 1
            touched.add(who)
    return n


def sync_all(source: str = "live", full: bool = False) -> dict:
    """Every registered project; one that cannot be read is skipped and named."""
    out, bad = {}, {}
    for key, v in projects.registry().items():
        try:
            out[key] = sync(key, Path(v["root"]), source, full)["added"]
        except (OSError, sqlite3.Error) as e:
            bad[key] = str(e)
    return dict(added=out, errors=bad)


# ---------------------------------------------------------------- spaced repetition
def step(k: dict, t: float, hit: bool, method: str | None = None) -> dict:
    """One graded review of a concept at time t. k: {mastery, stability, reps, lapses, last_review}."""
    s, m = k.get("stability"), k.get("mastery")
    if s is None:
        s, m = (1.0, 0.75) if hit else (0.2, 0.25)
    else:
        gap = (t - (k.get("last_review") or t)) / DAY
        if hit:
            s *= (3.0 if method in HARD else 2.5) if gap >= 0.5 * s else 1.3
        else:
            s *= 0.35
            k["lapses"] = (k.get("lapses") or 0) + 1
        m += 0.4 * ((1.0 if hit else 0.0) - m)
    s = min(365.0, max(0.1, s))
    return k | dict(stability=s, mastery=m, reps=(k.get("reps") or 0) + 1, last_review=t, due=t + s * DAY)


def recall(k: dict, now: float) -> float | None:
    if not k.get("stability") or not k.get("last_review"):
        return None
    return 0.9 ** (max(0.0, now - k["last_review"]) / DAY / k["stability"])


def rebuild(con, who: str) -> int:
    """Replay a person's events into their knowledge rows. Several graded events on one concept within ten minutes
    (a card answered by prediction and by a method, a check retried) count as one review: the last result stands."""
    rows = con.execute("SELECT e.*, c.concept FROM events e JOIN event_concepts c ON c.uid=e.uid WHERE e.person=? ORDER BY e.t", (who,)).fetchall()
    state: dict[str, dict] = {}
    for r in rows:
        k = state.setdefault(r["concept"], dict(n=0, hits=0, seen=0, ms=0.0, last_seen=None, reps=0, lapses=0))
        k["seen"] += 1
        k["ms"] += r["ms"] or 0.0
        k["last_seen"] = r["t"]
        if r["hit"] is None or r["kind"] not in ("predict", "attempt", "check"):
            continue
        k["n"] += 1
        k["hits"] += r["hit"]
        k["last_hit"] = r["hit"]
        if k.get("last_review") and r["t"] - k["last_review"] < 600 and k.get("_prev"):
            k |= step(dict(k["_prev"]), r["t"], bool(r["hit"]), r["method"])  # redo the review with this result
        else:
            prev = {x: k.get(x) for x in ("stability", "mastery", "reps", "lapses", "last_review")}
            k |= step(dict(prev), r["t"], bool(r["hit"]), r["method"])
            k["_prev"] = prev
    con.execute("DELETE FROM knowledge WHERE person=?", (who,))
    for c, k in state.items():
        con.execute("INSERT INTO knowledge VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (who, c, _title(c)[0], k.get("mastery"), k.get("stability"), k["reps"], k["lapses"], k["n"], k["hits"],
                     k["seen"], k["ms"], k["last_seen"], k.get("last_review"), k.get("last_hit"), k.get("due")))
    return len(state)


def state_of(k: dict, now: float) -> str:
    if not k.get("n"):
        return "untested"
    if k.get("due") and k["due"] <= now:
        return "due"
    return "known" if (k.get("mastery") or 0) >= 0.7 else "shaky"


# ---------------------------------------------------------------- reading memory
def knowledge(who: str, now: float | None = None) -> list[dict]:
    now = now or time.time()
    with db() as con:
        rows = con.execute("SELECT k.*, c.title, c.kind, c.parent FROM knowledge k LEFT JOIN concepts c ON c.id=k.concept"
                           " WHERE k.person=?", (who,)).fetchall()
    out = []
    for r in rows:
        k = dict(r)
        rc = recall(k, now)
        k |= dict(id=k.pop("concept"), recall=rc, strength=None if rc is None else round(rc * (k["mastery"] or 0), 3), state=state_of(k, now))
        out.append(k)
    return sorted(out, key=lambda k: (k["project"] != "", k["project"], k["id"]))


def due(who: str, now: float | None = None, project: str | None = None) -> list[dict]:
    """Concepts to review now, most overdue (relative to their stability) first."""
    now = now or time.time()
    ks = [k for k in knowledge(who, now) if k["state"] == "due" and (project is None or k["project"] in ("", project))]
    return sorted(ks, key=lambda k: -(now - k["due"]) / DAY / (k["stability"] or 1))


def methods(who: str, project: str | None = None, exclude: str | None = None) -> dict:
    """Per teaching method across projects: tries, hits, skips and the last five results (teach.profile's shape)."""
    q = "SELECT method, kind, hit FROM events WHERE person=? AND kind IN ('predict','attempt','skip') AND method IS NOT NULL"
    args: list = [who]
    if project:
        q += " AND project=?"
        args.append(project)
    if exclude:
        q += " AND project<>?"
        args.append(exclude)
    with db() as con:
        rows = con.execute(q + " ORDER BY t", args).fetchall()
    out: dict = {}
    for r in rows:
        s = out.setdefault(r["method"], dict(n=0, hits=0, skips=0, last=[]))
        if r["kind"] == "skip":
            s["skips"] += 1
            continue
        s["n"] += 1
        s["hits"] += r["hit"] or 0
        if r["hit"] is not None:
            s["last"] = (s["last"] + [bool(r["hit"])])[-5:]
    return out


def changed(who: str, since: float) -> list[dict]:
    """What moved after `since`: per concept, how many graded events and hits, and the newest time."""
    with db() as con:
        rows = con.execute("SELECT c.concept, count(*) n, sum(e.hit IS NOT NULL) graded, sum(coalesce(e.hit,0)) hits, max(e.t) t"
                           " FROM events e JOIN event_concepts c ON c.uid=e.uid WHERE e.person=? AND e.t>? GROUP BY c.concept ORDER BY t DESC",
                           (who, since)).fetchall()
    return [dict(r) for r in rows]


def timeline(who: str, since: float) -> list[dict]:
    with db() as con:
        rows = con.execute("SELECT t, kind, hit, method, project FROM events WHERE person=? AND t>? ORDER BY t", (who, since)).fetchall()
    return [dict(r) for r in rows]


def people_known() -> list[dict]:
    with db() as con:
        rows = con.execute("SELECT p.id, p.last, count(e.uid) n FROM people p LEFT JOIN events e ON e.person=p.id GROUP BY p.id ORDER BY n DESC").fetchall()
    names = _roster()
    return [dict(r) | dict(name=(names.get(r["id"]) or {}).get("name") or r["id"]) for r in rows]


# ---------------------------------------------------------------- what the Brief asks of memory
def blend(p, prof: dict, viewer: str, aliases: set | None = None) -> dict:
    """teach.profile for one project, plus what this person did with each method in every other project, so the
    method that works for them carries across projects. Never raises: the Brief works without memory."""
    try:
        key = projects.key_for(p.root)
        who = person(viewer)
        if not who or not key:
            return prof
        other = methods(who, exclude=key)
        for m, s in prof.get("methods", {}).items():
            o = other.get(m)
            if o:
                s["n"] += o["n"]
                s["hits"] += o["hits"]
                s["skips"] += o["skips"]
                if len(s["last"]) < 5:
                    s["last"] = (o["last"] + s["last"])[-5:]
        return prof
    except Exception:  # noqa: BLE001
        return prof


def view(p, viewer: str, now: float | None = None, others: bool = True) -> dict:
    now = now or time.time()
    key = projects.key_for(p.root) or ""
    if key:
        sync(key, p.root)
    if others:
        for k, v in projects.registry().items():
            if k != key:
                try:
                    sync(k, Path(v["root"]))
                except (OSError, sqlite3.Error):
                    pass
    who = person(viewer)
    if not who:
        return dict(person=None, now=now, project=key, concepts=[], due=[], methods={}, changed=[], timeline=[], people=people_known())
    ks = knowledge(who, now)
    return dict(person=who, name=(_roster().get(who) or {}).get("name") or who, now=now, project=key, concepts=ks,
                due=[k["id"] for k in sorted((k for k in ks if k["state"] == "due"), key=lambda k: k["due"])],
                methods=methods(who), changed=changed(who, now - 7 * DAY), timeline=timeline(who, now - 30 * DAY),
                people=people_known())


@features.get("/api/memory")
def _get(p, path, q):
    return 200, view(p, str(q.get("viewer") or ""), others=q.get("others") != "0")


# ---------------------------------------------------------------- live writes
# The Brief's own routes stay as they are; after one of them writes its ledger, memory reads the new lines. The typed
# answer of a code or explain attempt is not in teach.jsonl, so it is taken from the request (the person's own words).
WATCH = ("/api/teach", "/api/predictions", "/api/understanding", "/api/comments")


def after_post(p, path: str, body, res) -> None:
    try:
        key = projects.key_for(p.root)
        if not key or not res or res[0] != 200:
            return
        sync(key, p.root)
        a = res[1].get("attempt") if path.startswith("/api/teach") and isinstance(res[1], dict) else None
        if a and a.get("method") in ("code", "explain") and isinstance(body, dict) and isinstance(body.get("answer"), str):
            who = person(a.get("viewer"))
            got = (a.get("show") or {}).get("got")
            with db() as con:
                con.execute("UPDATE events SET answer=? WHERE project=? AND person=? AND kind='attempt' AND ref=? AND abs(t-?)<1e-3",
                            (json.dumps(dict(text=body["answer"][:1000], **({"got": got} if got is not None else {}))), key, who, a.get("card"), a.get("t")))
    except Exception:  # noqa: BLE001  the write already happened; memory catches up on the next sync
        pass


def _wrap(prefix, fn):
    def run(p, path, body):
        res = fn(p, path, body)
        after_post(p, path, body, res)
        return res
    run._memory = True
    return run


def hook() -> None:
    """Wrap the watched POST routes once (idempotent; feature modules loaded later are wrapped on the next call)."""
    features.POST[:] = [(pre, fn if getattr(fn, "_memory", False) or not pre.startswith(WATCH) else _wrap(pre, fn)) for pre, fn in features.POST]


hook()


# ---------------------------------------------------------------- CLI
def _pick(viewer: str | None) -> str | None:
    if viewer:
        return person(viewer) or viewer
    ps = people_known()
    return ps[0]["id"] if ps else None


def _bar(x: float | None, w: int = 10) -> str:
    return "·" * w if x is None else "█" * round(x * w) + "░" * (w - round(x * w))


def _when(t: float, now: float) -> str:
    d = (t - now) / DAY
    return "now" if abs(d) < 1 / 24 else (f"in {d:.1f} d" if d > 0 else f"{-d:.1f} d ago")


def cmd_memory(a):
    now = time.time()
    if a.what == "backfill":
        r = sync_all("backfill", full=True)
        for k, n in r["added"].items():
            print(f"{k:<40} {n:>5} new events")
        for k, e in r["errors"].items():
            print(f"{k:<40} skipped: {e}")
        print(f"memory: {path()}")
        return
    sync_all()
    who = _pick(a.viewer)
    if not who:
        print("No one in memory yet. Answer a Brief card, or run `arx memory backfill`.")
        return
    name = (_roster().get(who) or {}).get("name") or who
    if a.what == "due":
        ds = due(who, now)
        print(f"{name}: {len(ds)} due")
        for k in ds:
            print(f"  {k['title'] or k['id']:<34} {k['project'] or 'all projects':<28} due {_when(k['due'], now)}")
        return
    if a.what == "changed":
        from .learn import _since
        since = _since(a.since or "1w")
        for r in changed(who, since):
            print(f"  {r['concept']:<50} {r['n']:>3} events, {r['hits']} of {r['graded']} right, {_when(r['t'], now)}")
        return
    ks = knowledge(who, now)
    print(f"{name} ({who}): {len(ks)} concepts, {sum(k['state'] == 'due' for k in ks)} due")
    for k in ks:
        print(f"  {_bar(k['strength'])} {k['state']:<8} {(k['title'] or k['id'])[:34]:<34} {k['project'] or 'all':<24}"
              f" {k['hits']} of {k['n']} right" + (f", due {_when(k['due'], now)}" if k.get("due") else ""))
    ms = methods(who)
    if ms:
        print("  methods: " + ", ".join(f"{m} {s['hits']}/{s['n']}" + (f" ({s['skips']} skipped)" if s["skips"] else "") for m, s in ms.items()))


@features.CLI.append
def _cli(sp):
    s = sp.add_parser("memory", help="what a person knows across projects, what is due, what changed (learner memory)")
    s.add_argument("what", nargs="?", default="show", choices=("show", "due", "changed", "backfill"))
    s.add_argument("--viewer", help="person id or name (default: the person with the most history)")
    s.add_argument("--since", help="for changed: unix seconds, or 12h / 2d / 1w ago (default 1w)")
    s.set_defaults(fn=cmd_memory)
