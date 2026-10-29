/* explain-kit.js: measure how fast and how well a reader understands an explainer. Include it in a paper whose meta
 * has kind: "explainer":  <script src="/explain-kit.js"></script>  (it starts itself on DOMContentLoaded).
 *
 * Markup (data attributes are the API; the kit adds its own classes and styles):
 *   <html data-doc="gsm8k-96-explainer">       doc id for telemetry; default: the paper name in the URL
 *   <section data-step="gap" data-title="Distance to goal"> ... </section>   one step; active time is per step
 *   <div data-check="c-gap">                    a predict gate: answer before the figure unlocks
 *     <div data-q>How many more problems?</div>
 *     <button data-right>43</button><button>12</button><button>130</button>   options; shuffled unless data-fixed
 *     <div data-why>1,267 needed, 1,224 now.</div>                           shown after the answer
 *   </div>
 *   <div data-lock="c-gap"> figure </div>       blurred until c-gap is answered (or skipped)
 *   <div data-alt="c-gap"> another view </div>  hidden; "See it another way" shows it after a wrong answer
 *   <button data-replay="gap">Replay</button>   counts a replay of step "gap" (call your own animation too)
 *   <div data-summary></div>                    time per step, replays, misses, and where the reader got stuck
 *   <span data-ev='{"h":"Champion on full","rows":[["slice","full"],["n",1319]]}'>1,224</span>   evidence popover
 *
 * JS (window.XK):
 *   XK.onReveal(checkId, fn)   run fn when the check is answered (draw the unlocked figure)
 *   XK.onAlt(checkId, fn)      run fn when its alternative view opens
 *   XK.replay(stepId)          count a replay;  XK.pause(bool?) toggles the timer (also key P, or the meter button)
 *   XK.ev(text, title, rows)   returns HTML for an evidence span; rows = [[label, value], ...]
 *   XK.state()                 the reader's log {active, steps, checks, alts, done};  XK.reset() starts over
 *   XK.flush()                 send pending telemetry now (also every 15 s and when the tab hides)
 *   XK.init({doc, viewer, endpoint, meter})   only needed to override defaults before DOMContentLoaded
 *
 * Telemetry: POST {events:[{viewer, doc, step, ms, check, ok, replays, alt_used}]} to <project>/api/understanding.
 * ms and replays are deltas since the last send. Active time counts only while the tab is visible, the reader has
 * moved in the last 90 s and the timer is not paused. Viewer = localStorage "arx-name" (the dashboard's), else "anon".
 * The reader's own log stays in localStorage, so a reload resumes. Opened from a file, it sends nothing.
 */
(() => {
  "use strict";
  if (window.XK) return;
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const mmss = ms => { const s = Math.round(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const mins = ms => { const s = Math.round(ms / 1000); return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`; };
  const store = { get: k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };

  const CSS = `
.xk-check{border:1px solid var(--border,#e3e7eb);background:var(--raised,#f5f7f9);border-radius:8px;padding:14px 16px;margin:0 0 16px}
.xk-check [data-q]{font-weight:600;font-size:16px;margin-bottom:10px}
.xk-check [data-q]:before{content:"Predict";font:600 11px var(--mono,ui-monospace,monospace);letter-spacing:.06em;text-transform:uppercase;color:var(--accent,#1b6c80);display:block;margin-bottom:4px}
.xk-opts{display:flex;flex-wrap:wrap;gap:8px}
.xk-opts button{font:inherit;color:inherit;cursor:pointer;border:1px solid var(--control,#cdd3d9);background:var(--surface,#fff);border-radius:6px;padding:8px 14px;font-weight:500;min-height:38px}
.xk-opts button:hover:not([disabled]){border-color:var(--accent,#1b6c80)}
.xk-opts button[disabled]{cursor:default;opacity:.55}
.xk-opts button.xk-ok{opacity:1;border-color:var(--positive,#1e7b4f);background:var(--pill-positive-bg,#dcfae5);color:var(--positive,#1e7b4f)}
.xk-opts button.xk-no{opacity:1;border-color:var(--negative,#c4242a);background:var(--pill-negative-bg,#ffedea);color:var(--negative,#c4242a)}
.xk-res{margin-top:10px;font-size:14px;display:none;align-items:center;gap:12px;flex-wrap:wrap}
.xk-res.xk-show{display:flex}
.xk-check [data-why]{display:none;color:var(--muted,#5b6168)}
.xk-res [data-why]{display:inline}
.xk-mark .xk-pos{color:var(--positive,#1e7b4f)}.xk-mark .xk-neg{color:var(--negative,#c4242a)}.xk-mark .xk-warn{color:var(--warning,#92400e)}
.xk-alt-btn{font:600 13px inherit;cursor:pointer;border:1px solid var(--accent,#1b6c80);background:var(--accent-soft,#e3f0f3);color:var(--accent,#1b6c80);border-radius:6px;padding:5px 10px}
.xk-skip{border:0;background:none;color:var(--faint,#6f767d);font-size:12.5px;text-decoration:underline;padding:0;margin-top:8px;cursor:pointer}
[data-lock]{transition:filter .4s}
[data-lock].xk-locked{filter:blur(7px) grayscale(.6);pointer-events:none;user-select:none;opacity:.6}
[data-alt]{margin-top:14px;border-top:1px dashed var(--border,#e3e7eb);padding-top:14px;display:none}
[data-alt].xk-show{display:block}
[data-ev]{cursor:pointer;text-decoration:underline dotted var(--control,#cdd3d9);text-underline-offset:4px}
[data-ev]:hover{color:var(--accent,#1b6c80)}
#xk-pop{position:fixed;z-index:60;background:var(--surface,#fff);color:var(--text,#131416);border:1px solid var(--border,#e3e7eb);border-radius:8px;box-shadow:0 8px 28px rgba(0,0,0,.18);padding:10px 12px;font:12.5px/1.45 var(--font,system-ui);max-width:min(340px,calc(100vw - 24px));display:none}
#xk-pop.xk-show{display:block}#xk-pop .xk-h{font-weight:600;font-size:13.5px;margin-bottom:6px}
#xk-pop dl{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:0}#xk-pop dt{color:var(--faint,#6f767d)}#xk-pop dd{margin:0;font-family:var(--mono,monospace);font-size:12px;word-break:break-word}
#xk-meter{position:fixed;top:10px;right:12px;z-index:50;background:var(--surface,#fff);color:var(--text,#131416);border:1px solid var(--border,#e3e7eb);border-radius:8px;padding:7px 12px;font:500 12.5px var(--mono,monospace);display:flex;gap:14px;align-items:center;box-shadow:0 2px 10px rgba(0,0,0,.06)}
#xk-meter b{font-weight:600}#xk-meter span{color:var(--faint,#6f767d)}
#xk-meter .xk-dots{display:flex;gap:3px}#xk-meter .xk-dots i{width:8px;height:8px;border-radius:50%;background:var(--control,#cdd3d9)}
#xk-meter .xk-dots i.ok{background:var(--positive,#1e7b4f)}#xk-meter .xk-dots i.no{background:var(--negative,#c4242a)}#xk-meter .xk-dots i.skip{background:var(--warning,#92400e)}#xk-meter .xk-dots i.cur{box-shadow:0 0 0 2px var(--accent,#1b6c80)}
#xk-meter button{width:24px;height:24px;border-radius:12px;border:1px solid var(--control,#cdd3d9);background:var(--raised,#f5f7f9);color:inherit;font:600 10px var(--mono,monospace);cursor:pointer;padding:0}
#xk-meter.xk-paused{border-color:var(--warning,#92400e)}#xk-meter.xk-paused b:first-of-type{color:var(--warning,#92400e)}
.xk-sum .xk-row{display:grid;grid-template-columns:minmax(0,1fr) 70px 70px 60px;gap:10px;padding:7px 0;border-bottom:1px solid var(--rule,#eef1f4);font-size:14px;align-items:center}
.xk-sum .xk-row.xk-hd{font:600 11px var(--mono,monospace);color:var(--faint,#6f767d);text-transform:uppercase;letter-spacing:.05em}
.xk-sum .xk-row>:not(:first-child){text-align:right;font-family:var(--mono,monospace);font-variant-numeric:tabular-nums}
.xk-sum .xk-row.xk-stuck{background:var(--pill-warning-bg,#fff5db)}
.xk-sum h3{font:600 17px/1.3 var(--font,system-ui);margin:0 0 10px}
.xk-tbar{height:6px;border-radius:3px;background:var(--accent,#1b6c80);margin-top:4px}
@media (max-width:640px){#xk-meter{left:12px;right:12px;justify-content:space-between;gap:8px}.xk-sum .xk-row{grid-template-columns:minmax(0,1fr) 54px 54px 44px}}
@media print{#xk-meter,#xk-pop,.xk-skip{display:none!important}[data-lock].xk-locked{filter:none;opacity:1}}`;

  const O = { doc: null, viewer: null, endpoint: null, meter: true };
  let LOG, KEY, PAUSED = false, curStep = null, started = false;
  const REVEAL = {}, ALT = {}, PEND = { steps: {}, events: [] };
  const STEPS = () => $$("[data-step]").map(s => ({ id: s.dataset.step, title: s.dataset.title || s.querySelector("h1,h2,h3")?.textContent?.trim() || s.dataset.step }));
  const CHECKS = () => $$("[data-check]").map(c => c.dataset.check);
  const stepOf = id => $(`[data-check="${CSS_ESC(id)}"]`)?.closest("[data-step]")?.dataset.step || null;
  const CSS_ESC = s => (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/"/g, '\\"');
  const stepLog = id => LOG.steps[id] || (LOG.steps[id] = { ms: 0, replays: 0 });
  const save = () => store.set(KEY, LOG);
  const pend = id => PEND.steps[id] || (PEND.steps[id] = { ms: 0, replays: 0 });

  function docId() {
    if (O.doc) return O.doc;
    const d = document.documentElement.dataset.doc; if (d) return d;
    const m = location.pathname.match(/\/papers\/([^/]+)/); if (m) return decodeURIComponent(m[1]);
    return location.pathname.replace(/\/+$/, "") || "explainer";
  }
  function viewer() { if (O.viewer) return O.viewer; try { return localStorage.getItem("arx-name") || "anon"; } catch { return "anon"; } }
  function endpoint() {
    if (O.endpoint !== null) return O.endpoint;
    if (!/^https?:$/.test(location.protocol)) return "";
    // a paper opened in the dashboard runs at /p/<key>/papers/<name>/raw; the project's API lives at /p/<key>/api
    let path = location.pathname;
    try { if (window.top !== window && window.top.location.origin === location.origin) path = window.top.location.pathname; } catch {}
    const m = path.match(/^(\/p\/[^/]+)/);
    return (m ? m[1] : "") + "/api/understanding";
  }
  function send(events, beacon) {
    const url = endpoint(); if (!url || !events.length) return;
    const body = JSON.stringify({ events: events.slice(0, 200) });
    try { fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: !!beacon }).catch(() => {}); } catch {}
  }
  function flush(beacon) {
    const base = { viewer: viewer(), doc: docId() };
    const evs = PEND.events.splice(0).map(e => ({ ...base, ...e }));
    for (const [step, p] of Object.entries(PEND.steps)) {
      if (p.ms >= 250 || p.replays) evs.push({ ...base, step, ms: Math.round(p.ms), check: null, ok: null, replays: p.replays, alt_used: false });
    }
    PEND.steps = {};
    send(evs, beacon);
  }

  /* ---------- checks ---------- */
  function wire(c) {
    if (c.dataset.xkWired) return; c.dataset.xkWired = 1; c.classList.add("xk-check");
    const btns = $$("button", c).filter(b => !b.closest("[data-why]") && !b.classList.contains("xk-skip"));
    const opts = document.createElement("div"); opts.className = "xk-opts";
    const order = btns.map((b, i) => i);
    if (!("fixed" in c.dataset)) for (let i = order.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
    order.forEach(i => opts.append(btns[i]));
    btns.forEach((b, i) => { b.type = "button"; b.dataset.xkI = i; });
    const q = $("[data-q]", c); (q ? q.after(opts) : c.prepend(opts));
    const res = document.createElement("div"); res.className = "xk-res"; res.innerHTML = '<b class="xk-mark"></b>';
    const why = $("[data-why]", c); if (why) res.append(why);
    opts.after(res);
    const skip = document.createElement("button"); skip.type = "button"; skip.className = "xk-skip"; skip.textContent = "show me"; res.after(skip);
    opts.onclick = e => { const b = e.target.closest("button"); if (!b || b.disabled) return; answer(c.dataset.check, +b.dataset.xkI); };
    skip.onclick = () => answer(c.dataset.check, -1);
  }
  function answer(id, i, restoring = false) {
    const c = $(`[data-check="${CSS_ESC(id)}"]`); if (!c || c.dataset.xkDone) return; c.dataset.xkDone = 1;
    const btns = $$(".xk-opts button", c).sort((a, b) => a.dataset.xkI - b.dataset.xkI);
    const right = btns.findIndex(b => "right" in b.dataset);
    const ok = i >= 0 && i === right;
    if (!restoring) {
      const step = stepOf(id) || curStep;
      LOG.checks[id] = { i, ok, skip: i < 0, step, t: LOG.active }; save();
      PEND.events.push({ step, ms: 0, check: id, ok: i < 0 ? false : ok, replays: 0, alt_used: false });
      flush();
    }
    btns.forEach((b, j) => { b.disabled = true; if (j === right) b.classList.add("xk-ok"); else if (j === i) b.classList.add("xk-no"); });
    const res = $(".xk-res", c); res.classList.add("xk-show"); $(".xk-skip", c)?.remove();
    $(".xk-mark", c).innerHTML = i < 0 ? '<span class="xk-warn">skipped</span>' : ok ? '<span class="xk-pos">✓ right</span>' : '<span class="xk-neg">✗ not quite</span>';
    const alt = $(`[data-alt="${CSS_ESC(id)}"]`);
    if (!ok && alt) {
      const b = document.createElement("button"); b.type = "button"; b.className = "xk-alt-btn"; b.textContent = "See it another way"; res.append(b);
      b.onclick = () => openAlt(id, b, restoring);
      if (restoring && LOG.alts[id]) openAlt(id, b, true);
    }
    $$(`[data-lock="${CSS_ESC(id)}"]`).forEach(l => l.classList.remove("xk-locked"));
    try { REVEAL[id]?.(); } catch (e) { console.warn("explain-kit reveal", id, e); }
    meter(); summary();
  }
  function openAlt(id, btn, restoring) {
    const a = $(`[data-alt="${CSS_ESC(id)}"]`); if (!a) return;
    a.classList.add("xk-show"); btn?.remove();
    if (!restoring) { LOG.alts[id] = (LOG.alts[id] || 0) + 1; save(); PEND.events.push({ step: stepOf(id) || curStep, ms: 0, check: id, ok: null, replays: 0, alt_used: true }); flush(); a.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
    try { ALT[id]?.(); } catch (e) { console.warn("explain-kit alt", id, e); }
  }

  /* ---------- time ---------- */
  function track() {
    const vis = new Map();
    const io = new IntersectionObserver(es => { es.forEach(e => vis.set(e.target.dataset.step, e.intersectionRatio)); let best = null, br = 0; vis.forEach((r, k) => { if (r > br) { br = r; best = k; } }); curStep = best; meter(); }, { threshold: [0, .1, .25, .5, .75, 1] });
    $$("[data-step]").forEach(s => io.observe(s));
    const sumEl = $("[data-summary]"); if (sumEl) new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && CHECKS().every(id => LOG.checks[id]) && !LOG.done) { LOG.done = LOG.active; save(); summary(); PEND.events.push({ step: "summary", ms: 0, check: null, ok: null, replays: 0, alt_used: false }); flush(); } }), { threshold: .3 }).observe(sumEl);
    let last = Date.now(), lastInput = Date.now();
    ["pointerdown", "pointermove", "keydown", "scroll", "wheel", "touchstart"].forEach(t => addEventListener(t, () => (lastInput = Date.now()), { passive: true }));
    setInterval(() => {
      const t = Date.now(), dt = Math.min(t - last, 2000); last = t;
      if (!PAUSED && document.visibilityState === "visible" && t - lastInput < 90000 && curStep && !LOG.done) { LOG.active += dt; stepLog(curStep).ms += dt; pend(curStep).ms += dt; save(); }
      const m = $("#xk-t"); if (m) m.textContent = mmss(LOG.done || LOG.active);
    }, 500);
    setInterval(() => flush(), 15000);
    addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(true); });
    addEventListener("pagehide", () => flush(true));
  }
  function pause(v) {
    PAUSED = v === undefined ? !PAUSED : !!v;
    const b = $("#xk-p"); if (b) { b.textContent = PAUSED ? "▶" : "❚❚"; b.title = PAUSED ? "Resume timer (P)" : "Pause timer (P)"; }
    $("#xk-meter")?.classList.toggle("xk-paused", PAUSED);
    return PAUSED;
  }
  function meter() {
    const el = $("#xk-meter"); if (!el) return;
    const ids = CHECKS(), ok = ids.filter(id => LOG.checks[id]?.ok).length;
    $("#xk-c").textContent = `${ok} / ${ids.length}`;
    $(".xk-dots", el).innerHTML = ids.map(id => { const r = LOG.checks[id]; return `<i class="${r ? (r.skip ? "skip" : r.ok ? "ok" : "no") : ""} ${stepOf(id) === curStep ? "cur" : ""}" title="${esc(id)}"></i>`; }).join("");
  }
  function summary() {
    const el = $("[data-summary]"); if (!el) return;
    el.classList.add("xk-sum");
    const ids = CHECKS(), ans = ids.filter(id => LOG.checks[id]), ok = ans.filter(id => LOG.checks[id].ok).length;
    const rows = STEPS().map(s => { const l = LOG.steps[s.id] || { ms: 0, replays: 0 }; const chk = ids.filter(id => stepOf(id) === s.id);
      return { ...s, ...l, chk: chk.length, miss: chk.filter(id => LOG.checks[id] && !LOG.checks[id].ok).length }; });
    const mx = Math.max(1, ...rows.map(r => r.ms));
    const score = r => r.miss * 60000 + r.replays * 8000 + r.ms;  // stuck: missed checks first, then replays, then time
    const top = rows.slice().sort((a, b) => score(b) - score(a))[0];
    const stuck = top && (top.miss || top.replays > 2 || top.ms > 90000) ? top : null;
    const t = LOG.done || LOG.active;
    el.innerHTML = `<h3>${ans.length < ids.length ? `So far: ${mins(t)}, ${ok} of ${ids.length} checks` : `Understood in ${mins(t)}, ${ok} of ${ids.length} checks${stuck ? `, stuck on ${esc(stuck.title.toLowerCase())}` : ""}`}</h3>
      <div class="xk-row xk-hd"><span>step</span><span>time</span><span>replays</span><span>missed</span></div>${rows.map(r => `<div class="xk-row${stuck && r.id === stuck.id ? " xk-stuck" : ""}"><span>${esc(r.title)}<div class="xk-tbar" style="width:${r.ms / mx * 100}%"></div></span><span>${mmss(r.ms)}</span><span>${r.replays}</span><span>${r.chk ? r.miss : "–"}</span></div>`).join("")}
      <button type="button" class="xk-skip" id="xk-reset">Start over</button>`;
    $("#xk-reset").onclick = () => XK.reset();
  }

  /* ---------- evidence popover ---------- */
  function popover() {
    const pop = document.createElement("div"); pop.id = "xk-pop"; pop.setAttribute("role", "dialog"); document.body.append(pop);
    const show = el => {
      let d; try { d = JSON.parse(el.dataset.ev); } catch { d = { h: el.dataset.ev, rows: [] }; }
      pop.innerHTML = `<div class="xk-h">${esc(d.h || "")}</div><dl>${(d.rows || []).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`; pop.classList.add("xk-show");
      const r = el.getBoundingClientRect(), pw = pop.offsetWidth, ph = pop.offsetHeight;
      pop.style.left = Math.min(Math.max(8, r.left + r.width / 2 - pw / 2), innerWidth - pw - 8) + "px";
      let y = r.top - ph - 10; if (y < 56) y = r.bottom + 10; pop.style.top = Math.min(y, innerHeight - ph - 8) + "px";
    };
    document.addEventListener("click", e => { const el = e.target.closest("[data-ev]"); if (el) { e.stopPropagation(); show(el); } else if (!e.target.closest("#xk-pop")) pop.classList.remove("xk-show"); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") pop.classList.remove("xk-show"); if (e.key === "Enter" && e.target.dataset?.ev) show(e.target); });
    addEventListener("scroll", () => pop.classList.remove("xk-show"), { passive: true });
  }

  function start() {
    if (started) return; started = true;
    KEY = "arx-xk:" + docId();
    LOG = store.get(KEY) || { started: Date.now(), active: 0, steps: {}, checks: {}, alts: {}, done: null };
    const st = document.createElement("style"); st.textContent = CSS; document.head.append(st);
    $$("[data-check]").forEach(wire);
    $$("[data-lock]").forEach(l => { if (!LOG.checks[l.dataset.lock]) l.classList.add("xk-locked"); });
    $$("[data-ev]").forEach(e => e.tabIndex = 0);
    $$("[data-replay]").forEach(b => b.addEventListener("click", () => XK.replay(b.dataset.replay)));
    if (O.meter && CHECKS().length) {
      const m = document.createElement("div"); m.id = "xk-meter";
      m.innerHTML = `<button id="xk-p" type="button" title="Pause timer (P)" aria-label="Pause timer">❚❚</button><span>⏱ <b id="xk-t">0:00</b></span><span>checks <b id="xk-c">0 / 0</b></span><div class="xk-dots"></div>`;
      document.body.append(m); $("#xk-p").onclick = () => pause();
    }
    addEventListener("keydown", e => { if ((e.key === "p" || e.key === "P") && !/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) && !e.target.isContentEditable && !e.metaKey && !e.ctrlKey && !e.altKey) pause(); });
    popover();
    Object.entries(LOG.checks).forEach(([id, r]) => answer(id, r.i, true));
    track(); meter(); summary();
  }

  const XK = window.XK = {
    init(o = {}) { Object.assign(O, o); if (document.readyState !== "loading") start(); return XK; },
    onReveal(id, fn) { REVEAL[id] = fn; if (LOG?.checks[id]) try { fn(); } catch (e) { console.warn(e); } return XK; },
    onAlt(id, fn) { ALT[id] = fn; return XK; },
    replay(stepId) { const id = stepId || curStep; if (!id || !LOG) return; stepLog(id).replays++; pend(id).replays++; save(); summary(); },
    pause,
    ev(text, title, rows) { return `<span data-ev="${esc(JSON.stringify({ h: title, rows: rows || [] }))}" tabindex="0">${esc(text)}</span>`; },
    state() { return LOG && JSON.parse(JSON.stringify(LOG)); },
    reset() { flush(); try { localStorage.removeItem(KEY); } catch {} location.reload(); },
    flush() { flush(); }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else setTimeout(start);
})();
