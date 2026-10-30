// Core: data, routing, names, hover cards, charts, and the learner log.
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { key: null, state: null, until: null, route: [], es: null, viewT: 0 };

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}
const api = (path) => getJSON(`/api/p/${encodeURIComponent(S.key)}/${path}`);

// ---- formatting ----------------------------------------------------------
const pct = (v, d = 1) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);
const pts = (v, d = 1) => (v == null ? "–" : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(d)} pts`);
const num = (v, d = 1) => (v == null ? "–" : Number(v).toFixed(d));
function ago(t) {
  if (!t) return "–";
  const d = Date.now() / 1000 - t;
  if (d < 60) return `${Math.max(0, d | 0)} s ago`;
  if (d < 3600) return `${(d / 60) | 0} min ago`;
  if (d < 86400 * 2) return `${(d / 3600) | 0} h ago`;
  return `${(d / 86400) | 0} days ago`;
}
function dur(s) {
  if (s == null) return "–";
  if (s < 90) return `${s | 0} s`;
  if (s < 5400) return `${(s / 60) | 0} min`;
  return `${(s / 3600).toFixed(1)} h`;
}
const day = (t) => new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const when = (t) => new Date(t * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

// Metric values in the units people think in.
function metricVal(metric, v) {
  if (v == null) return "–";
  if (metric === "score") return pct(v);
  if (metric?.startsWith("latency")) return `${num(v, 1)} s`;
  if (metric === "cost") return `$${num(v, 3)}`;
  return num(v, 3);
}
const METRIC_WORDS = { score: "share judged correct", latency_p50: "median answer time", latency_p95: "slowest 5% answer time", cost: "cost per question" };

// ---- names: never show a key where a name exists -------------------------
function ent(kind, key, label) {
  const st = S.state;
  if (!key) return '<span class="mute">–</span>';
  let name = label, cls = "";
  if (!name && st) {
    const src = { candidate: st.candidates, hill: st.hills, set: st.sets, goal: st.goals, task: st.tasks, doc: st.docs }[kind];
    name = src?.[key]?.name;
    if (kind === "candidate" && key === st.champion) cls = " champion";
  }
  const href = { candidate: "cand", hill: "hill", set: "set", goal: "goal", task: "task", doc: "doc" }[kind];
  return `<a class="ent k-${kind}${cls}" data-k="${kind}" data-key="${esc(key)}" href="#/p/${S.key}/${href}/${encodeURIComponent(key)}">${esc(name || key)}</a>`;
}
const cand = (k) => ent("candidate", k), setN = (k) => ent("set", k), hillN = (k) => ent("hill", k);

function hoverHTML(kind, key) {
  const st = S.state;
  const id = `<div class="id">${esc(key)}</div>`;
  if (kind === "candidate") {
    const c = st.candidates[key]; if (!c) return null;
    const par = c.parent && st.candidates[c.parent] ? `Built on ${esc(st.candidates[c.parent].name)}. ` : "";
    return `<div class="k">Candidate · ${esc(c.status)}</div><div class="t">${esc(c.name)}</div>${par}${esc((c.change || c.title || "").slice(0, 260))}${id}`;
  }
  if (kind === "set") {
    const s = st.sets[key]; if (!s) return null;
    return `<div class="k">Set · ${esc(s.role)} · ${s.n} items</div><div class="t">${esc(s.name)}</div>${esc((s.purpose || "").slice(0, 260))}${id}`;
  }
  if (kind === "hill") {
    const h = st.hills[key]; if (!h) return null;
    const p = st.patterns[h.pattern] || {};
    return `<div class="k">Hill · ${esc(h.status)}</div><div class="t">${esc(h.name)}</div>${esc((h.symptom || "").slice(0, 240))}${p.count ? `<p class="small mute" style="margin-top:6px">${p.count} of ${p.of} ${esc(p.of_what || "")}</p>` : ""}${id}`;
  }
  if (kind === "goal") {
    const g = st.goals[key]; if (!g) return null;
    return `<div class="k">Goal · ${esc(g.status)}</div><div class="t">${esc(g.name)}</div>${goalSentence(g)}${id}`;
  }
  if (kind === "task") {
    const t = st.tasks[key]; if (!t) return null;
    return `<div class="k">Task · ${esc(t.kind || "")} · ${esc(t.status)}</div><div class="t">${esc(t.name)}</div>${esc((t.about || "").slice(0, 240))}${id}`;
  }
  return null;
}

function goalSentence(g) {
  const op = g.direction === "min" ? "at most" : "at least";
  return `The champion's <b>${METRIC_WORDS[g.metric] || g.metric}</b> on ${ent("set", g.set)} (${g.n} items) is ${op} <b>${metricVal(g.metric, g.target)}</b>.`;
}

let hoverTimer = null;
document.addEventListener("mouseover", (e) => {
  const a = e.target.closest?.(".ent");
  const hc = $("#hovercard");
  if (!a) { hc.hidden = true; clearTimeout(hoverTimer); return; }
  const html = hoverHTML(a.dataset.k, a.dataset.key);
  if (!html) return;
  hc.innerHTML = html;
  hc.hidden = false;
  const r = a.getBoundingClientRect();
  const x = Math.min(r.left, innerWidth - 380), y = r.bottom + 8 + 200 > innerHeight ? r.top - hc.offsetHeight - 8 : r.bottom + 8;
  hc.style.left = `${Math.max(8, x)}px`; hc.style.top = `${y}px`;
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => learn({ kind: "hover", entity: `${a.dataset.k}:${a.dataset.key}`, view: S.route[0] }), 700);
});

// ---- learner log: what the person looks at, so the dashboard can improve -----
const queue = [];
function learn(e) {
  if (!S.key) return;
  queue.push({ t: Date.now() / 1000, ...e });
}
setInterval(flush, 4000);
function flush() {
  if (!queue.length || !S.key) return;
  const body = JSON.stringify(queue.splice(0));
  navigator.sendBeacon?.(`/api/p/${S.key}/learn`, new Blob([body], { type: "application/json" })) ||
    fetch(`/api/p/${S.key}/learn`, { method: "POST", body });
}
addEventListener("pagehide", () => { leaveView(); flush(); });
function leaveView() {
  if (S.viewT && S.key) learn({ kind: "leave", view: S.route.join("/"), entity: S.route[1] ? `${S.route[0]}:${S.route[1]}` : null, dwell_ms: Date.now() - S.viewT });
}

// ---- charts (inline SVG) -------------------------------------------------
// Charts are drawn at the pixel width they will show at, so text stays at reading size.
function chartW(frac = 1) { const m = $("main"); return Math.max(320, Math.floor(((m?.clientWidth || 1200) - 48) * frac) - 40); }
function scale(d0, d1, r0, r1) { const k = (r1 - r0) / ((d1 - d0) || 1); return (v) => r0 + (v - d0) * k; }

function ciBar(lo, hi, delta, { w = 260, h = 22, min = -0.3, max = 0.3, solid } = {}) {
  if (delta == null) return `<svg viewBox="0 0 ${w} ${h}"></svg>`;
  const x = scale(min, max, 6, w - 6), c = (v) => Math.max(6, Math.min(w - 6, x(v)));
  const sig = solid ?? (lo > 0 || hi < 0);
  const col = lo > 0 ? "var(--champ)" : hi < 0 ? "var(--broke)" : "var(--mute)";
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
    <line x1="${x(0)}" x2="${x(0)}" y1="2" y2="${h - 2}" stroke="var(--line)" stroke-width="1.5"/>
    <line x1="${c(lo)}" x2="${c(hi)}" y1="${h / 2}" y2="${h / 2}" stroke="${col}" stroke-width="${sig ? 4 : 2}" stroke-linecap="round" opacity="${sig ? 1 : .7}"/>
    <circle cx="${c(delta)}" cy="${h / 2}" r="5" fill="${sig ? col : "var(--sheet)"}" stroke="${col}" stroke-width="2"/></svg>`;
}

function waffle(cells, cls = "") {
  return `<div class="waffle ${cls}">${cells.map((c) => `<i class="${c.c}" title="${esc(c.t || "")}"></i>`).join("")}</div>`;
}

function sparkline(values, { w = 120, h = 26, color = "var(--ink2)" } = {}) {
  const v = values.filter((x) => x != null);
  if (v.length < 2) return "";
  const x = scale(0, v.length - 1, 2, w - 2), y = scale(Math.min(...v), Math.max(...v), h - 3, 3);
  return `<svg width="${w}" height="${h}"><polyline fill="none" stroke="${color}" stroke-width="1.5" points="${v.map((d, i) => `${x(i)},${y(d)}`).join(" ")}"/></svg>`;
}

function lineChart(series, { w = chartW(), h = 200, xlab = "step" } = {}) {
  const pts = series.flatMap((s) => s.points);
  if (pts.length < 2) return '<div class="empty">Not enough points yet.</div>';
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x = scale(Math.min(...xs), Math.max(...xs), 40, w - 70), y = scale(Math.min(...ys), Math.max(...ys), h - 22, 10);
  const lines = series.map((s, i) => {
    const last = s.points[s.points.length - 1];
    return `<polyline fill="none" stroke="${s.color || ["var(--ink)", "var(--champ)", "var(--live)", "var(--broke)"][i % 4]}" stroke-width="1.8" points="${s.points.map((p) => `${x(p[0])},${y(p[1])}`).join(" ")}"/>
      <text class="lbl" x="${x(last[0]) + 6}" y="${y(last[1]) + 4}">${esc(s.name)} ${num(last[1], 3)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="max-width:100%">${lines}
    <text x="40" y="${h - 4}">${num(Math.min(...xs), 0)}</text><text x="${w - 70}" y="${h - 4}" text-anchor="end">${num(Math.max(...xs), 0)} ${xlab}</text>
    <text x="0" y="14">${num(Math.max(...ys), 3)}</text><text x="0" y="${h - 22}">${num(Math.min(...ys), 3)}</text></svg>`;
}

// ---- routing and refresh -------------------------------------------------
async function loadState() {
  const q = S.until ? `?until=${S.until}` : "";
  S.state = await api(`state${q}`);
  document.title = `${S.state.project.name} · arx`;
}

function subscribe() {
  if (S.es) S.es.close();
  if (!S.key) return;
  let timer = null;
  S.es = new EventSource(`/api/p/${encodeURIComponent(S.key)}/events`);
  S.es.addEventListener("change", () => {
    if (S.until) return; // replaying the past: hold still
    clearTimeout(timer);
    timer = setTimeout(async () => { await loadState(); render(true); }, 300);
  });
}

function crumbs(parts) {
  $("#crumbs").innerHTML = parts.map((p) => (p.href ? `<a href="${p.href}">${esc(p.label)}</a>` : `<span>${esc(p.label)}</span>`)).join('<span class="sep">/</span>');
}

async function route() {
  leaveView();
  const h = location.hash.replace(/^#\/?/, "");
  const parts = h.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "p" && parts[1]) {
    if (S.key !== parts[1]) {
      S.key = parts[1]; S.until = null; S.state = null;
      await loadState(); subscribe();
      learn({ kind: "visit" });
    }
    S.route = parts.slice(2);
    if (!S.route.length) S.route = ["map"];
  } else {
    S.key = null; S.route = ["home"];
    if (S.es) S.es.close();
  }
  S.viewT = Date.now();
  learn({ kind: "view", view: S.route.join("/"), entity: S.route[1] ? `${S.route[0]}:${S.route[1]}` : null });
  await render(false);
  scrollTo(0, 0);
}

async function render(soft) {
  const y = scrollY;
  const page = PAGES[S.route[0]] || PAGES.map;
  try {
    const html = await page(...S.route.slice(1));
    if (html != null) $("#app").innerHTML = html;
    renderReplay();
    PAGES._after?.();
  } catch (e) {
    $("#app").innerHTML = `<div class="sheet"><h3>Could not draw this page</h3><p class="mono">${esc(e.stack || e)}</p></div>`;
  }
  if (soft) scrollTo(0, y);
  $("#clock").textContent = S.state && !S.until ? `live · ${S.state.n_events} events` : "";
}

function renderReplay() {
  const el = $("#replay");
  if (!S.state || !S.until) { el.hidden = true; return; }
  const [a, b] = S.state.span;
  el.hidden = false;
  el.innerHTML = `<b>Replaying</b><span>${when(S.until)}</span>
    <input type="range" min="${a}" max="${b}" step="60" value="${S.until}" oninput="this.previousElementSibling.textContent=when(+this.value)" onchange="replayTo(+this.value)">
    <button onclick="replayTo(null)">Back to now</button>`;
}

async function replayTo(t) {
  S.until = t;
  await loadState();
  render(true);
}

// ---- theme: follow the system, or pin light or dark. Answer frames and saved notes follow it too. -----
const THEMES = { auto: "◐", light: "☀", dark: "☾" };
function theme() { return document.documentElement.dataset.theme || "auto"; }
function showTheme() { const b = $("#theme"); if (b) { b.textContent = THEMES[theme()]; b.title = `Theme: ${theme()}`; } }
function cycleTheme() {
  const next = { auto: "light", light: "dark", dark: "auto" }[theme()];
  if (next === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = next;
  try { localStorage.setItem("arx2.theme", next); } catch (e) {}
  showTheme();
}
addEventListener("DOMContentLoaded", showTheme);

addEventListener("hashchange", route);
addEventListener("DOMContentLoaded", route);
