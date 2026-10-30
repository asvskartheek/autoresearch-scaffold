// Pages. Each returns HTML. Concrete first, then the aggregate; names everywhere, keys only on hover.
const GLYPH = { pass: "✓", fail: "✕", unclear: "~", running: "●", todo: "○", no_base: "?" };
const STATE_WORD = { pass: "passed", fail: "failed", unclear: "not clear yet (interval crosses the bar)", running: "running now", todo: "not run yet", no_base: "waiting for a champion run on this set" };
const RULE_WORD = (r) => r.rule === "improve" ? `must be better${r.margin ? ` by ${pts(r.margin)}` : ""}` :
  r.rule === "hold" ? (r.tol ? `may not drop more than ${pts(r.tol).replace("+", "")}` : "may not drop") :
  r.rule === "at_least" ? `at least ${r.value}` : r.rule === "at_most" ? `at most ${r.value}` : r.rule;

function projNav(active) {
  const st = S.state, k = S.key;
  const tabs = [["map", "Overview"], ["hills", "Hills"], ["ladder", "Ladder"], ["work", "Work"], ["sets", "Sets"], ["library", "Library"], ["learn", `Learn${st.learner.n_due ? ` · ${st.learner.n_due}` : ""}`]];
  crumbs([{ label: "All projects", href: "#/" }, { label: st.project.name, href: `#/p/${k}` }]);
  return `<nav class="tabs">${tabs.map(([r, l]) => `<a class="${active === r ? "on" : ""}" href="#/p/${k}/${r}">${l}</a>`).join("")}
    <span style="flex:1"></span><a href="javascript:replayTo(${Math.floor(S.state.span[1] - 86400 * 3)})" title="See the project as it was at any moment">Replay ⟲</a></nav>`;
}

function stepCounts(s) {
  if (s.n == null || s.cand == null) return "";
  if (S.state.measure.scale !== "binary") return `${num(s.cand, 3)} vs ${num(s.base, 3)}`;
  return `${Math.round(s.cand * s.n)} of ${s.n} vs ${Math.round(s.base * s.n)} of ${s.n}`;
}

function noEvidence(hk) {
  const e = (S.state.evidence || {})[hk];
  return e && !e.ok && !e.waived ? e : null;
}

function waived(hk) {
  return (S.state.evidence || {})[hk]?.waived || null;
}

function evidenceLine(e) {
  return `No evidence: ${e.missing.join(", ")}.`;
}

function needsYou() {
  const st = S.state, out = [];
  for (const t of Object.values(st.tasks)) if (t.stale) out.push(`Task ${ent("task", t.id)} has been silent for ${ago(t.beat).replace(" ago", "")}. Fix it or end it.`);
  const bad = st.split.pairs.filter((p) => p.shared);
  if (bad.length) out.push(`${bad.length} hill${bad.length > 1 ? "s" : ""} share items between sets that must be separate. <a href="#/p/${S.key}/sets">See the split check</a>.`);
  const lacking = {};  // what is missing -> open hills missing it
  for (const [hk, h] of Object.entries(st.hills)) {
    const e = h.status === "open" && noEvidence(hk);
    if (e) (lacking[e.missing.join(", ")] ||= []).push(hk);
  }
  for (const [why, hks] of Object.entries(lacking))
    out.push(hks.length === 1 ? `${hillN(hks[0])} has no evidence: ${why}. Freeze a symptom set or close the hill.`
      : `${hks.length} open hills have no evidence (${why}): ${hks.map(hillN).join(", ")}. Freeze a symptom set for each or close it.`);
  for (const t of Object.values(st.tasks)) if (t.status === "failed" && t.ended && Date.now() / 1000 - t.ended < 86400) out.push(`Task ${ent("task", t.id)} failed ${ago(t.ended)}.`);
  return out;
}

// ---- all projects ----------------------------------------------------------
const PAGES = {};
PAGES.home = async () => {
  crumbs([{ label: "All projects" }]);
  document.title = "Research Bridge";
  const ps = await getJSON("/api/projects");
  if (!ps.length) return `<div class="sheet"><h3>No projects yet</h3><p class="mono">arx2 init --name "Two Words" --task "..." --measure "..."</p></div>`;
  return `<h1>Research</h1><p class="sub">Every project the agents are working on.</p><div class="grid g2 section">${ps.map((p) => p.error ? `<div class="sheet"><h3>${esc(p.key)}</h3><p class="alarm small">${esc(p.error)}</p></div>` : `
    <a class="sheet" href="#/p/${encodeURIComponent(p.key)}" style="text-decoration:none">
      <div class="spread"><h3>${esc(p.name)}</h3><span class="small mute">active ${ago(p.last)}</span></div>
      <p class="mute small">${esc((p.task || "").slice(0, 160))}</p>
      ${p.goals.filter((g) => g.status === "open").map((g) => goalMini(g)).join("")}
      <div class="row small" style="margin-top:10px">
        <span>Champion <b>${esc(p.champion || "–")}</b></span>
        ${p.running ? `<span class="pill live"><span class="dot live"></span>${p.running} running</span>` : ""}
        ${p.stale ? `<span class="pill alarm">${p.stale} stalled</span>` : ""}
        ${p.split_ok ? "" : `<span class="pill alarm">sets overlap</span>`}
        ${p.n_due ? `<span class="pill">${p.n_due} cards to review</span>` : ""}
      </div></a>`).join("")}</div>`;
};

function goalMini(g) {
  const hib = g.direction !== "min";
  const frac = g.now == null ? 0 : hib ? g.now / g.target : g.target / g.now;
  return `<div style="margin-top:8px"><div class="spread small"><span>${esc(g.name)}</span><span><b>${metricVal(g.metric, g.now)}</b> <span class="mute">of ${metricVal(g.metric, g.target)}</span>${g.met ? ' <span class="pill champ">met</span>' : ""}</span></div>
    <div class="bar"><span style="width:${Math.min(100, frac * 100)}%;background:${g.met ? "var(--champ)" : "var(--ink)"}"></span></div></div>`;
}

// ---- overview: the two-minute page -----------------------------------------
PAGES.map = () => {
  const st = S.state, k = S.key;
  const champ = st.candidates[st.champion] || {};
  const open = Object.entries(st.goals).filter(([, g]) => g.status === "open");
  const flags = needsYou();
  const running = Object.values(st.tasks).filter((t) => t.status === "running");
  return `${projNav("map")}
  <div class="spread"><div><h1>${esc(st.project.name)}</h1>
    <p class="sub">${esc(st.project.task || "")}</p>
    <p class="small mute">Each answer is scored as <b>${esc(st.measure.name)}</b> (${st.measure.scale === "binary" ? "right or wrong" : st.measure.unit || "a number"}, ${st.measure.direction === "max" ? "higher is better" : "lower is better"}). Champion: ${cand(st.champion)}.</p></div></div>
  ${sinceLastVisit()}
  ${flags.length ? `<div class="sheet section" style="border-color:var(--alarm)"><h2 class="alarm">Needs you</h2>${flags.map((f) => `<p>${f}</p>`).join("")}</div>` : ""}
  <div class="grid ${open.length > 1 ? "g2" : ""} section">${open.map(([gk, g]) => goalPanel(gk, g)).join("") || '<div class="sheet empty">No open goal. A goal turns a wish into one number on one set.</div>'}</div>
  <div class="sheet section"><h2>How the champion got here</h2>${lineage()}</div>
  <div class="grid g-main section">
    <div class="sheet"><div class="spread"><h2>The ladder</h2><a class="small" href="#/p/${k}/ladder">All candidates →</a></div>${ladderBoard(12)}</div>
    <div class="grid" style="align-content:start">
      <div class="sheet"><h2>Running now</h2>${running.length ? running.map(liveCard).join("") : `<p class="empty">Nothing running. Last activity ${ago(Math.max(...Object.values(st.tasks).map((t) => t.beat || 0)))}.</p>`}</div>
      <div class="sheet">${splitBanner()}</div>
    </div>
  </div>
  <div class="section"><div class="spread"><h2>Hills: what is wrong, and how often</h2><a class="small" href="#/p/${k}/hills">All hills →</a></div>${hillMultiples(false)}</div>
  <div class="sheet section"><h2>Recent decisions</h2>${decisions(8)}</div>`;
};

function sinceLastVisit() {
  const st = S.state;
  let prev = null;
  try { prev = +localStorage.getItem(`arx2:seen:${S.key}`) || null; localStorage.setItem(`arx2:seen:${S.key}`, Date.now() / 1000); } catch (e) { }
  if (!prev || S.until) return "";
  const ev = st.timeline.filter((e) => e.t > prev);
  if (!ev.length) return "";
  const champs = ev.filter((e) => e.type === "champion");
  const rej = ev.filter((e) => e.type === "candidate.status" && e.status === "rejected");
  const runs = ev.filter((e) => e.type === "run").length;
  const reveal = `<div id="since-ans" hidden><p>${champs.length ? `Yes: ${champs.map((e) => cand(e.key)).join(" then ")} became champion.` : "No, the champion is the same."}
    ${rej.length ? ` ${rej.length} candidate${rej.length > 1 ? "s were" : " was"} rejected: ${rej.slice(-5).map((e) => cand(e.key)).join(", ")}.` : ""} ${runs} eval run${runs === 1 ? "" : "s"} finished.</p></div>`;
  return `<div class="quiz section"><b>Since you were last here (${ago(prev)}), ${ev.length} things happened.</b> Before you look: did the champion change?
    <div style="margin-top:8px"><button onclick="answerSince(this, true, ${champs.length > 0})">Yes</button><button onclick="answerSince(this, false, ${champs.length > 0})">No</button></div>${reveal}</div>`;
}
function answerSince(btn, said, truth) {
  learn({ kind: "quiz", q: "champion-changed", right: said === truth });
  btn.parentElement.innerHTML = said === truth ? '<span class="champ">Right.</span>' : '<span class="alarm">Not quite.</span>';
  $("#since-ans").hidden = false;
}

function goalPanel(gk, g) {
  const tr = g.track, hib = g.direction !== "min";
  const gap = tr.current == null ? null : hib ? g.target - tr.current : tr.current - g.target;
  let gapText = "";
  if (tr.met) gapText = `<span class="pill champ">met</span>`;
  else if (gap != null && g.metric === "score") gapText = `<b>${pts(gap).replace("+", "")}</b> short: about <b>${Math.ceil(gap * g.n - 1e-9)} more of ${g.n}</b> items right`;
  else if (gap != null) gapText = `<b>${metricVal(g.metric, Math.abs(gap))}</b> to go`;
  return `<div class="sheet"><div class="spread"><h2>Goal · ${ent("goal", gk)}</h2><span class="small mute">opened ${day(g.created)}</span></div>
    <p class="statement">${goalSentence(g)}</p>
    <div class="row" style="gap:22px;margin:10px 0"><div><div class="big">${metricVal(g.metric, tr.current)}</div><div class="small mute">now</div></div>
      <div><div class="big mute">${metricVal(g.metric, g.target)}</div><div class="small mute">target</div></div><div class="small">${gapText}</div></div>
    ${goalChart(g)}
    ${g.vague ? `<details class="small" style="margin-top:6px"><summary class="mute">Where this goal came from</summary><p style="margin-top:6px">${esc(g.vague)}</p></details>` : ""}</div>`;
}

function goalChart(g) {
  const st = S.state, tr = g.track, open = Object.values(st.goals).filter((x) => x.status === "open").length, w = chartW(open > 1 ? 0.5 : 1), h = 220;
  const champs = tr.points.filter((p) => p.value != null).sort((a, b) => a.t - b.t);
  const tried = tr.tried.filter((p) => p.value != null);
  const all = [...champs, ...tried];
  if (!all.length) return '<p class="empty">The champion has no run on this set yet.</p>';
  const t0 = Math.min(...all.map((p) => p.t)), t1 = Math.max(st.span[1], ...all.map((p) => p.t));
  const vals = [...all.map((p) => p.value), g.target];
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * 0.12 || 0.05; lo -= pad; hi += pad;
  const x = scale(t0, t1, 30, w - 120), y = scale(lo, hi, h - 24, 12);
  let path = "";
  champs.forEach((p, i) => {
    const nx = i + 1 < champs.length ? champs[i + 1].t : t1;
    path += `${i ? "L" : "M"}${x(p.t)},${y(p.value)} L${x(nx)},${y(p.value)} `;
  });
  const dots = tried.map((p) => {
    const c = st.candidates[p.model] || {};
    const isC = c.status === "champion" || c.status === "retired";
    return `<circle cx="${x(p.t)}" cy="${y(p.value)}" r="${isC ? 4.5 : 3.2}" fill="${isC ? "var(--champ)" : "var(--sheet)"}" stroke="${isC ? "var(--champ)" : "var(--mute)"}" stroke-width="1.4"><title>${esc(c.name || p.model)}: ${metricVal(g.metric, p.value)} (${esc(c.status || "")}) · ${when(p.t)}</title></circle>`;
  }).join("");
  const last = champs[champs.length - 1];
  const steps = champs.map((p, i) => i === 0 ? "" : `<text x="${x(p.t) + 3}" y="${y(p.value) - 7}" font-size="10">${esc(st.candidates[p.model]?.name || "")}</text>`).join("");
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="max-width:100%">
    <line x1="30" x2="${w - 120}" y1="${y(g.target)}" y2="${y(g.target)}" stroke="var(--ink)" stroke-dasharray="4 4" opacity=".55"/>
    <text x="${w - 116}" y="${y(g.target) + 4}" class="lbl">target ${metricVal(g.metric, g.target)}</text>
    ${dots}<path d="${path}" fill="none" stroke="var(--champ)" stroke-width="2.6"/>${steps}
    ${last ? `<text x="${w - 116}" y="${y(last.value) + 4}" class="lbl" fill="var(--champ)">champion ${metricVal(g.metric, last.value)}</text>` : ""}
    <text x="30" y="${h - 6}">${day(t0)}</text><text x="${w - 120}" y="${h - 6}" text-anchor="end">${day(t1)}</text></svg>
    <div class="small mute">Line: the champion over time. Dots: every candidate run on this set (filled = became champion).</div>`;
}

function lineage() {
  const st = S.state;
  const chain = [];
  const seen = new Set();
  for (const c of st.champions) if (!seen.has(c.key)) { seen.add(c.key); chain.push(c); }
  if (!chain.length) return '<p class="empty">No champion yet.</p>';
  const g = Object.values(st.goals).find((x) => x.status === "open" && x.metric === "score") || Object.values(st.goals)[0];
  const val = (m) => {
    const r = Object.values(st.runs).filter((r) => r.candidate === m && g && r.set === g.set && r.summary?.score != null).sort((a, b) => b.created - a.created)[0];
    return r ? r.summary.score : null;
  };
  const kids = (m) => Object.values(st.candidates).filter((c) => c.parent === m && c.status === "rejected").length;
  return `<div class="lineage">${chain.map((c, i) => `<div class="step ${c.key === st.champion ? "now" : ""}">
      <div class="small mute">${day(c.t)}${i ? "" : " · start"}</div><div>${cand(c.key)}</div>
      <div class="v">${pct(val(c.key))}</div><div class="small mute">${kids(c.key)} tried on top, rejected</div></div>`).join("")}</div>
    ${g ? `<p class="small mute" style="margin-top:6px">Scores are on ${setN(g.set)}.</p>` : ""}`;
}

// ---- the ladder ------------------------------------------------------------
function rungCols() {
  return (S.state.ladder.rungs || []).map((r, i) => ({ ...r, i }));
}

function aggSteps(steps) {
  if (!steps.length) return "todo";
  const s = steps.map((x) => x.state);
  if (s.includes("fail")) return "fail";
  if (s.includes("running")) return "running";
  if (s.includes("unclear")) return "unclear";
  if (s.every((x) => x === "pass")) return "pass";
  if (s.includes("no_base")) return "no_base";
  return s.includes("pass") ? "unclear" : "todo";
}

function stepTitle(x) {
  return `${S.state.sets[x.set]?.name || x.set}: ${STATE_WORD[x.state]}${x.delta != null ? `. ${stepCounts(x)}, ${pts(x.delta)} (90% interval ${pts(x.lo)} to ${pts(x.hi)})` : ""}`;
}

function ladderBoard(limit, filter) {
  const st = S.state, cols = rungCols();
  let cs = Object.values(st.candidates).filter((c) => c.climb.length && (!filter || filter(c)));
  const ran = (c) => c.climb.some((x) => x.state !== "todo");
  cs.sort((a, b) => ran(b) - ran(a) || (b.status === "trying") - (a.status === "trying") || b.created - a.created);
  const total = cs.length;
  if (limit) cs = cs.slice(0, limit);
  if (!cs.length) return '<p class="empty">No candidates on the ladder yet.</p>';
  const head = cols.map((r) => {
    const s = st.sets[r.set];
    return `<th title="${esc(RULE_WORD(r))}" style="text-align:center;white-space:normal;min-width:64px">${esc(r.name)}<div class="mute" style="font-weight:400">${s ? `${s.n} items` : ""}</div></th>`;
  }).join("");
  const rows = cs.map((c) => {
    const cells = cols.map((r) => {
      const steps = c.climb.filter((x) => x.from === r.i);
      const a = aggSteps(steps);
      return `<td style="text-align:center" data-ask="candidate|${esc(c.key)}|ladder cell: ${esc(c.name)} × ${esc(r.name)}"><span class="cell st-${a}" title="${esc(steps.map(stepTitle).join("\n") || STATE_WORD.todo)}">${GLYPH[a]}</span></td>`;
    }).join("");
    return `<tr class="click" onclick="location.hash='#/p/${S.key}/cand/${encodeURIComponent(c.key)}'"><td>${cand(c.key)}<div class="small mute">${c.hill ? esc(st.hills[c.hill]?.name || c.hill) : ""} · ${esc(c.status === "trying" ? "climbing" : c.status)}</div></td>${cells}</tr>`;
  }).join("");
  return `<div class="scroll-x"><table><tr><th>Candidate</th>${head}</tr>${rows}</table></div>
    <div class="small mute" style="margin-top:8px"><span class="key"><span class="cell st-pass" style="width:18px;height:18px">✓</span>passed</span><span class="key"><span class="cell st-fail" style="width:18px;height:18px">✕</span>failed</span><span class="key"><span class="cell st-unclear" style="width:18px;height:18px">~</span>not clear</span><span class="key"><span class="cell st-running" style="width:18px;height:18px">●</span>running</span><span class="key">○ not run</span>
    ${limit && total > limit ? ` · showing ${limit} of ${total}` : ""}</div>`;
}

PAGES.ladder = () => {
  const st = S.state;
  const cols = rungCols();
  return `${projNav("ladder")}<h1>The ladder</h1>
    <p class="sub">A candidate becomes champion only by passing every step, in order, cheapest first. Each step compares it with the model it was built on, on the same items.</p>
    <div class="sheet section"><div class="row" style="gap:0;align-items:stretch">${cols.map((r, i) => `<div style="flex:1;padding:6px 12px;border-left:3px solid var(--line)">
      <div class="small mute">Step ${i + 1}</div><b>${esc(r.name)}</b><div class="small">${r.set.startsWith("@") ? { "@hill.eval": "the hill's own target set", "@hill.control": "the hill's control set", "@hills.climbed": "every hill already climbed" }[r.set] : setN(r.set)}</div>
      <div class="small mute">${esc(RULE_WORD(r))}</div></div>`).join("")}</div></div>
    <div class="sheet section">${ladderBoard(0)}</div>`;
};

// ---- live work -------------------------------------------------------------
function liveCard(t) {
  const st = S.state;
  const run = Object.values(st.runs).find((r) => r.task === t.id);
  const frac = t.total ? t.done / t.total : null;
  let meaning = "";
  if (run) {
    const c = st.candidates[run.candidate];
    const step = c?.climb.find((x) => x.set === run.set);
    meaning = `${cand(run.candidate)} on ${setN(run.set)}${step ? `, ladder step “${esc(step.name)}”` : ""}. ${run.summary?.n ? `So far ${pct(run.summary.score)} on ${run.summary.n} items.` : ""}`;
  } else meaning = esc((t.about || "").slice(0, 160));
  const last = t.notes?.[t.notes.length - 1];
  return `<a href="#/p/${S.key}/task/${encodeURIComponent(t.id)}" style="display:block;text-decoration:none;padding:8px 0;border-bottom:1px solid var(--soft)">
    <div class="spread"><b>${esc(t.name)}</b><span class="small ${t.stale ? "alarm" : "mute"}">${t.stale ? "silent " : "heard from "}${ago(t.beat)}</span></div>
    ${frac != null ? `<div class="bar live" style="margin:6px 0"><span style="width:${frac * 100}%"></span></div>` : ""}
    <div class="small">${t.done ?? 0}${t.total ? ` of ${t.total}` : ""} done${t.eta_s ? ` · about ${dur(t.eta_s)} left` : ""}</div>
    <div class="small mute">${meaning}</div>${last ? `<div class="small" style="margin-top:4px">“${esc(last.text.slice(0, 200))}”</div>` : ""}</a>`;
}

PAGES.work = (filter) => {
  const st = S.state;
  filter = filter || "all";
  let ts = Object.values(st.tasks);
  if (filter === "running") ts = ts.filter((t) => t.status === "running");
  if (filter === "failed") ts = ts.filter((t) => ["failed", "cancelled", "budget"].includes(t.status));
  if (filter === "evals") ts = ts.filter((t) => t.kind === "eval");
  ts.sort((a, b) => b.started - a.started);
  const byDay = {};
  for (const t of ts.slice(0, 400)) (byDay[day(t.started)] ||= []).push(t);
  const f = (k, l) => `<a class="${filter === k ? "on" : ""}" href="#/p/${S.key}/work/${k}">${l}</a>`;
  return `${projNav("work")}<h1>Work</h1><p class="sub">Every job the agents ran, newest first. Each is one task with a clear end.</p>
    <nav class="tabs">${f("all", "All")}${f("running", "Running")}${f("evals", "Evals")}${f("failed", "Failed or stopped")}</nav>
    ${Object.entries(byDay).map(([d, list]) => `<div class="section"><h2>${d} · ${list.length}</h2><div class="sheet flush"><table>
      ${list.map((t) => `<tr class="click" onclick="location.hash='#/p/${S.key}/task/${encodeURIComponent(t.id)}'">
        <td style="width:28%"><b>${esc(t.name)}</b><div class="small mute">${esc(t.kind || "")}${t.agent ? ` · ${esc(t.agent)}` : ""}</div></td>
        <td class="small">${esc((t.about || "").slice(0, 150))}</td>
        <td class="small" style="width:120px">${statusPill(t)}</td>
        <td class="small mute" style="width:90px">${t.ended ? dur(t.ended - t.started) : ago(t.started)}</td></tr>`).join("")}</table></div></div>`).join("") || '<p class="empty">No tasks.</p>'}`;
};

function statusPill(t) {
  if (t.stale) return '<span class="pill alarm">silent</span>';
  if (t.status === "running") return '<span class="pill live"><span class="dot live"></span>running</span>';
  if (t.status === "failed") return '<span class="pill alarm">failed</span>';
  if (t.status === "done") return '<span class="pill">done</span>';
  return `<span class="pill">${esc(t.status)}</span>`;
}

PAGES.task = async (id) => {
  const st = S.state;
  const t = await api(`task/${encodeURIComponent(id)}`);
  const run = Object.values(st.runs).find((r) => r.task === id);
  const metricKeys = [...new Set(t.metrics.flatMap((m) => Object.keys(m)))].filter((k) => !["t", "step"].includes(k));
  const series = metricKeys.map((k) => ({ name: k, points: t.metrics.filter((m) => m[k] != null).map((m, i) => [m.step ?? i, m[k]]) }));
  const parent = t.parent && st.tasks[t.parent];
  const proj = t.status === "running" && t.total ? `About ${dur(t.eta_s)} left at the current pace.` : t.ended ? `Took ${dur(t.ended - t.started)}.` : "";
  return `${projNav("work")}
    <div class="spread"><div><div class="small mute">Task · ${esc(t.kind || "")}${t.agent ? ` · by ${esc(t.agent)}` : ""}${parent ? ` · part of ${ent("task", t.parent)}` : ""}</div><h1>${esc(t.name)}</h1>
    <p class="sub">${esc(t.about || "")}</p>${t.description ? `<p class="small mute">${esc(t.description)}</p>` : ""}</div>${statusPill(t)}</div>
    <div class="grid g3 section">
      <div class="sheet"><h2>What is happening</h2><div class="big">${t.done ?? 0}<span class="mute" style="font-size:18px"> ${t.total ? `of ${t.total}` : ""}</span></div>
        ${t.total ? `<div class="bar live" style="margin-top:8px"><span style="width:${(100 * (t.done || 0)) / t.total}%"></span></div>` : ""}<p class="small mute" style="margin-top:6px">Last heard from ${ago(t.beat)}.</p></div>
      <div class="sheet"><h2>What it means</h2><p>${run ? `${cand(run.candidate)} on ${setN(run.set)}: ${pct(run.summary?.score)} so far on ${run.summary?.n ?? 0} items.` : esc(t.result || (t.notes[t.notes.length - 1]?.text || "No notes yet."))}</p></div>
      <div class="sheet"><h2>What comes next</h2><p>${proj}</p>${t.budget_s ? `<p class="small">Time budget ${dur(t.budget_s)}.</p>` : ""}</div>
    </div>
    ${run ? `<div class="section" id="runbox"></div>` : ""}
    ${series.length ? `<div class="sheet section"><h2>Curves</h2>${lineChart(series)}</div>` : ""}
    ${t.children.length ? `<div class="sheet section"><h2>Sub-tasks</h2><table>${t.children.map((c) => `<tr class="click" onclick="location.hash='#/p/${S.key}/task/${encodeURIComponent(c.id)}'"><td><b>${esc(c.name)}</b></td><td class="small">${esc((c.about || "").slice(0, 140))}</td><td>${statusPill(c)}</td></tr>`).join("")}</table></div>` : ""}
    <div class="sheet section"><h2>Notes</h2>${st.tasks[id]?.n_notes > t.notes.length ? "" : ""}${t.notes.length ? t.notes.slice().reverse().map((n) => `<div class="note"><div class="when">${when(n.t)}</div>${esc(n.text)}</div>`).join("") : '<p class="empty">No notes.</p>'}
    ${Object.keys(t.links || {}).length ? `<p class="small">${Object.entries(t.links).map(([l, u]) => `<a href="${esc(u)}" target="_blank">${esc(l)}</a>`).join(" · ")}</p>` : ""}</div>
    ${run ? `<script>0</script>` : ""}`;
};

// After a page draws, fill the async run comparison if there is a slot for it.
PAGES._after = async () => {
  const box = $("#runbox");
  if (!box) return;
  const st = S.state;
  const tid = S.route[0] === "task" ? S.route[1] : null;
  const runKey = box.dataset.run || Object.values(st.runs).find((r) => r.task === tid)?.key;
  if (!runKey) return;
  const d = await api(`run/${encodeURIComponent(runKey)}`);
  box.innerHTML = runComparison(d);
};

function runComparison(d) {
  const st = S.state;
  const rows = Object.fromEntries(d.rows.map((r) => [String(r.id), r]));
  const base = d.base ? Object.fromEntries(d.base.rows.map((r) => [String(r.id), r])) : null;
  const ok = (r) => r && !r.error && (r.score ?? 0) >= 1;
  const counts = { fixed: 0, broke: 0, both: 0, neither: 0, pending: 0, pass: 0, fail: 0, err: 0 };
  const cells = d.ids.map((id) => {
    const r = rows[id];
    if (!r) { counts.pending++; return { c: "pending", t: `${id}: not scored yet` }; }
    if (r.error) counts.err++;
    if (base && base[id]) {
      const a = ok(base[id]), b = ok(r);
      const c = a && b ? "both" : !a && !b ? "neither" : b ? "fixed" : "broke";
      counts[c]++;
      return { c, t: `${id}: ${c === "fixed" ? "fixed (was wrong, now right)" : c === "broke" ? "broke (was right, now wrong)" : c === "both" ? "right in both" : "wrong in both"}${r.error ? " · error" : ""}` };
    }
    const c = r.error ? "err" : ok(r) ? "pass" : "fail";
    counts[c]++;
    return { c, t: `${id}: ${c}` };
  });
  const s = d.summary;
  const legend = base ? `<span class="key"><i style="background:var(--fixed)"></i>fixed ${counts.fixed}</span><span class="key"><i style="background:var(--broke)"></i>broke ${counts.broke}</span><span class="key"><i style="background:var(--both)"></i>right in both ${counts.both}</span><span class="key"><i style="background:var(--neither)"></i>wrong in both ${counts.neither}</span>`
    : `<span class="key"><i style="background:var(--champ)"></i>right ${counts.pass}</span><span class="key"><i style="background:var(--neither)"></i>wrong ${counts.fail}</span><span class="key"><i style="background:var(--alarm)"></i>error ${counts.err}</span>`;
  const f = d.funnel || [];
  return `<div class="grid g2"><div class="sheet"><h2>Every item, one square${base ? ` · against ${esc(st.candidates[d.base.model]?.name || d.base.model)}` : ""}</h2>
      ${waffle(cells, "lg")}<div style="margin-top:10px">${legend}${counts.pending ? `<span class="key"><i style="box-shadow:inset 0 0 0 1px var(--line)"></i>waiting ${counts.pending}</span>` : ""}</div>
      <p class="small" style="margin-top:8px">${s.n} scored: ${pct(s.score)} right, ${s.errors} errors${s.latency_p50 != null ? `, median ${num(s.latency_p50)} s` : ""}${s.cost != null ? `, $${num(s.cost, 3)} per item` : ""}.</p></div>
    <div class="sheet"><h2>How sure, as items came in</h2>${f.length > 1 ? funnelChart(f, d.ids.length) : '<p class="empty">The comparison builds as items finish.</p>'}</div></div>`;
}

function funnelChart(f, total) {
  const w = chartW(0.5), h = 200;
  const x = scale(0, total, 36, w - 10);
  const ys = f.flatMap((p) => [p.lo, p.hi]);
  const lo = Math.min(-0.05, ...ys), hi = Math.max(0.05, ...ys);
  const y = scale(lo, hi, h - 22, 10);
  const band = f.map((p) => `${x(p.n)},${y(p.hi)}`).join(" ") + " " + f.slice().reverse().map((p) => `${x(p.n)},${y(p.lo)}`).join(" ");
  const last = f[f.length - 1];
  const half = (last.hi - last.lo) / 2;
  const projHalf = half * Math.sqrt(last.n / total);
  const proj = last.n < total ? `At all ${total} items the interval should be about ±${(projHalf * 100).toFixed(1)} pts${Math.abs(last.delta) > projHalf ? ", narrow enough to call it" : ", still too wide to call it if the gain stays this size"}.` : "";
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="max-width:100%">
    <polygon points="${band}" fill="var(--live)" opacity=".15"/>
    <line x1="36" x2="${w - 10}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink)" stroke-width="1" opacity=".5"/>
    <polyline fill="none" stroke="var(--live)" stroke-width="2" points="${f.map((p) => `${x(p.n)},${y(p.delta)}`).join(" ")}"/>
    <text x="${x(last.n)}" y="${y(last.delta) - 8}" text-anchor="end" class="lbl">${pts(last.delta)}</text>
    <text x="0" y="${y(0) + 4}">0</text><text x="36" y="${h - 4}">0</text><text x="${w - 10}" y="${h - 4}" text-anchor="end">${total} items</text></svg>
    <p class="small">Blue line: the gain over the base model on the items finished so far. Band: the 90% interval. It narrows as items arrive. Now ${pts(last.delta)} (${pts(last.lo)} to ${pts(last.hi)}) on ${last.n} items.</p><p class="small mute">${proj}</p>`;
}

// ---- hills -----------------------------------------------------------------
function hillMultiples(all) {
  const st = S.state;
  const hs = Object.entries(st.hills).filter(([, h]) => all || h.status !== "closed").sort((a, b) => (a[1].status === "open" ? 0 : 1) - (b[1].status === "open" ? 0 : 1) || b[1].created - a[1].created);
  return `<div class="grid g3">${hs.map(([hk, h]) => hillCard(hk, h)).join("")}</div>
    ${all ? "" : `<p class="small mute" style="margin-top:8px">${Object.values(st.hills).filter((h) => h.status === "closed").length} closed hills are on the <a href="#/p/${S.key}/hills">Hills</a> page.</p>`}`;
}

function prevalence(p, big) {
  if (!p || !p.count || !p.of) return "";
  const n = Math.min(p.of, 200), k = Math.round((p.count / p.of) * n);
  return `${waffle(Array.from({ length: n }, (_, i) => ({ c: i < k ? "on" : "" })), big ? "lg" : "")}<div class="small" style="margin-top:4px"><b>${p.count} of ${p.of}</b> <span class="mute">${esc(p.of_what || "")}${p.of > 200 ? " (each square ≈ " + (p.of / 200).toFixed(1) + ")" : ""}</span></div>`;
}

function hillTargetResults(hk) {
  const st = S.state, h = st.hills[hk];
  const tgt = (h.eval_sets || [])[0];
  const out = [];
  for (const c of Object.values(st.candidates)) {
    const s = c.climb.find((x) => x.set === tgt && x.delta != null);
    if (s) out.push({ c, s });
  }
  return out.sort((a, b) => a.c.created - b.c.created);
}

function hillCard(hk, h) {
  const st = S.state;
  const p = st.patterns[h.pattern];
  const res = hillTargetResults(hk);
  const best = res.slice().sort((a, b) => b.s.delta - a.s.delta)[0];
  return `<a class="sheet" href="#/p/${S.key}/hill/${encodeURIComponent(hk)}" data-ask="hill|${esc(hk)}|hill card: ${esc(h.name)}" style="text-decoration:none;display:block">
    <div class="spread"><h3>${esc(h.name)}</h3><span class="row">${noEvidence(hk) ? `<span class="pill alarm" title="${esc(evidenceLine(noEvidence(hk)))}">no evidence</span>` : ""}${waived(hk) ? `<span class="pill" title="${esc(waived(hk))}">waived</span>` : ""}<span class="pill ${h.status === "climbed" ? "champ" : ""}">${esc(h.status)}</span></span></div>
    <p class="small" style="min-height:3.6em">${esc((h.symptom || "").slice(0, 150))}</p>
    ${prevalence(p)}
    <div class="small mute" style="margin-top:8px">${res.length} candidate${res.length === 1 ? "" : "s"} tried${best ? ` · best ${pts(best.s.delta)} by ${esc(best.c.name)}` : ""}</div></a>`;
}

PAGES.hills = () => `${projNav("hills")}<h1>Hills</h1><p class="sub">A hill is one weakness of the champion that can be named, shown and measured. Size of the dark area is how often it happens.</p><div class="section">${hillMultiples(true)}</div>`;

PAGES.hill = (hk) => {
  const st = S.state, h = st.hills[hk];
  if (!h) return `${projNav("hills")}<p class="empty">No hill ${esc(hk)}.</p>`;
  const p = st.patterns[h.pattern];
  const ex = h.example || (h.examples || [])[0];
  const res = hillTargetResults(hk);
  const checks = st.split.pairs.filter((c) => c.hill === hk);
  const docs = Object.entries(st.docs).filter(([, d]) => d.about === hk);
  const roleSets = [["Symptom set", h.symptom_set ? [h.symptom_set] : [], "where the failures were found"], ["Hill eval sets", h.eval_sets || [], "what the ladder scores"], ["Training sets", h.train_sets || [], "what a fix may learn from"], ["Control", h.control ? [h.control] : [], "ordinary items that must not get worse"]];
  return `${projNav("hills")}
    <div class="small mute">Hill · serves ${ent("goal", h.goal)} · opened ${day(h.created)}</div>
    <div class="spread"><h1>${esc(h.name)}</h1><span class="pill ${h.status === "climbed" ? "champ" : ""}">${esc(h.status)}</span></div>
    <p class="statement">${esc(h.symptom || h.problem || "")}</p>
    ${noEvidence(hk) ? `<p class="${h.status === "closed" ? "small mute" : "alarm"}"><b>${esc(evidenceLine(noEvidence(hk)))}</b></p>` : ""}
    ${waived(hk) ? `<p class="small mute">Waived: ${esc(waived(hk))}</p>` : ""}
    ${h.reason ? `<p class="small mute">${esc(h.reason)}</p>` : ""}
    <div class="grid g2 section">
      <div class="sheet"><h2>One real case</h2>${ex ? `<dl class="example"><dt>Question</dt><dd>${esc(ex.input)}</dd><dt>Model said</dt><dd class="wrong">${esc(ex.wrong)}</dd><dt>Should say</dt><dd class="right">${esc(ex.right)}</dd><dt>Why wrong</dt><dd>${esc(ex.why)}</dd></dl>` : '<p class="empty">No example recorded. A hill should show one.</p>'}
        ${(h.examples || []).length > 1 ? `<p class="small mute" style="margin-top:8px">${h.examples.length - 1} more example${h.examples.length > 2 ? "s" : ""} recorded.</p>` : ""}</div>
      <div class="sheet"><h2>How often</h2>${prevalence(p, true) || '<p class="empty">Prevalence not counted. Count it in the champion\'s full run.</p>'}
        <h2 style="margin-top:16px">How it is measured</h2><p>${esc(h.measure || "Not written down.")}</p></div>
    </div>
    <div class="sheet section"><h2>Sets, and whether they are separate</h2>
      <div class="grid g2">${roleSets.map(([l, ks, why]) => `<div><b>${l}</b> <span class="small mute">${why}</span><div>${ks.length ? ks.map((k) => `${setN(k)} <span class="small mute">${st.sets[k]?.n ?? "?"} items</span>`).join("<br>") : '<span class="small mute">none</span>'}</div></div>`).join("")}</div>
      <div style="margin-top:12px">${checks.length ? checks.map((c) => `<div class="row small"><span class="dot ${c.shared ? "bad" : ""}"></span>${setN(c.a)} and ${setN(c.b)}: <b class="${c.shared ? "alarm" : ""}">${c.shared} shared</b></div>`).join("") : '<p class="small mute">Only one set: nothing to compare.</p>'}
      <p class="small mute">Checked ${ago(st.split.checked)} from the frozen id lists. <a href="#/p/${S.key}/sets">Re-check now</a>.</p></div></div>
    <div class="sheet section"><h2>Every candidate on the target set, against the model it was built on</h2>${forest(res)}</div>
    ${docs.length ? `<div class="sheet section"><h2>Papers</h2>${docs.map(([k, d]) => `<p>${ent("doc", k)} <span class="small mute">${esc(d.title || "")} · ${d.audience} · updated ${ago(d.updated)}</span></p>`).join("")}</div>` : ""}`;
};

function forest(res) {
  if (!res.length) return '<p class="empty">No candidate has run on this hill\'s target yet.</p>';
  const m = Math.max(0.15, ...res.flatMap((r) => [Math.abs(r.s.lo), Math.abs(r.s.hi)]));
  return `<div class="forest-row small mute"><span></span><span style="display:flex;justify-content:space-between"><span>worse ${pts(-m, 0)}</span><span>0</span><span>better ${pts(m, 0)}</span></span><span></span></div>
    ${res.map(({ c, s }) => `<div class="forest-row"><span>${cand(c.key)}<div class="small mute">${esc(c.status === "trying" ? "climbing" : c.status)}</div></span>${ciBar(s.lo, s.hi, s.delta, { min: -m, max: m, w: chartW(1) - 330 })}<span class="small">${pts(s.delta)}<div class="mute">${stepCounts(s)}</div></span></div>`).join("")}
    <p class="small mute" style="margin-top:6px">Dot: gain on the same items. Line: 90% interval. Filled and thick when the interval clears zero; hollow when luck could explain it.</p>`;
}

// ---- candidate -------------------------------------------------------------
PAGES.cand = (ck) => {
  const st = S.state, c = st.candidates[ck];
  if (!c) return `${projNav("ladder")}<p class="empty">No candidate ${esc(ck)}.</p>`;
  const chain = [];
  for (let p = c.parent, i = 0; p && st.candidates[p] && i < 30; p = st.candidates[p].parent, i++) chain.unshift(p);
  const runs = Object.values(st.runs).filter((r) => r.candidate === ck).sort((a, b) => b.created - a.created);
  const firstRun = c.climb.find((x) => x.run && x.state !== "todo")?.run || runs.find((r) => !r.aggregate_only)?.key;
  const kids = Object.values(st.candidates).filter((x) => x.parent === ck);
  return `${projNav("ladder")}
    <div class="small mute">Candidate · ${chain.length ? chain.map((k) => cand(k)).join(" → ") + " → " : ""}<b>this</b></div>
    <div class="spread"><h1>${esc(c.name)}</h1><span class="pill ${c.status === "champion" ? "champ" : ""}">${esc(c.status === "trying" ? "climbing" : c.status)}</span></div>
    <p class="statement">${esc(c.change || c.title || "")}</p>
    ${c.hill ? `<p class="small">Aims at the hill ${hillN(c.hill)}.</p>` : ""}
    ${c.predict ? `<p class="small"><b>Predicted before running:</b> ${esc(c.predict)}</p>` : ""}
    ${c.reason ? `<div class="sheet section"><h2>${c.status === "rejected" ? "Why it was rejected" : "Decision"}</h2><p>${esc(c.reason)}</p></div>` : ""}
    <div class="sheet section"><h2>The climb</h2>${c.climb.length ? `<table><tr><th>Step</th><th>Set</th><th>Rule</th><th>Result</th><th style="width:34%">Gain on the same items</th></tr>
      ${c.climb.map((x) => `<tr class="${x.run ? "click" : ""}" ${x.run ? `onclick="showRun('${esc(x.run)}')"` : ""}><td><span class="cell st-${x.state}" style="width:22px;height:22px">${GLYPH[x.state]}</span> ${esc(x.name)}</td><td>${setN(x.set)}</td><td class="small">${esc(RULE_WORD(x))}</td>
        <td class="small">${STATE_WORD[x.state]}${x.delta != null ? `<div class="mute">${stepCounts(x)}</div>` : x.value != null ? `<div class="mute">${num(x.value, 3)}</div>` : ""}</td>
        <td>${x.delta != null ? `<div class="row" style="flex-wrap:nowrap">${ciBar(x.lo, x.hi, x.delta, { w: 200 })}<span class="small">${pts(x.delta)}</span></div>` : ""}</td></tr>`).join("")}</table>
      <p class="small mute" style="margin-top:6px">Click a step to see its items below.</p>` : '<p class="empty">Not on the ladder.</p>'}</div>
    <div class="section" id="runbox" data-run="${esc(firstRun || "")}"></div>
    <div class="sheet section"><h2>All runs</h2>${runs.length ? `<table><tr><th>Set</th><th>Score</th><th>Items</th><th>Median time</th><th>When</th></tr>${runs.map((r) => `<tr class="click" onclick="showRun('${esc(r.key)}')"><td>${setN(r.set)}${r.aggregate_only ? ' <span class="pill">totals only</span>' : ""}</td><td>${pct(r.summary?.score)}</td><td>${r.summary?.n ?? "–"}</td><td>${r.summary?.latency_p50 != null ? num(r.summary.latency_p50) + " s" : "–"}</td><td class="small mute">${when(r.created)}</td></tr>`).join("")}</table>` : '<p class="empty">No runs.</p>'}</div>
    ${kids.length ? `<div class="sheet section"><h2>Built on this one</h2>${kids.map((x) => `<span style="margin-right:14px">${cand(x.key)} <span class="small mute">${esc(x.status)}</span></span>`).join("")}</div>` : ""}`;
};

async function showRun(run) {
  const box = $("#runbox");
  if (!box || !run) return;
  box.dataset.run = run;
  box.innerHTML = '<p class="empty">Loading items…</p>';
  box.innerHTML = runComparison(await api(`run/${encodeURIComponent(run)}`));
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---- goals -----------------------------------------------------------------
PAGES.goal = (gk) => {
  const st = S.state, g = st.goals[gk];
  if (!g) return `${projNav("map")}<p class="empty">No goal.</p>`;
  const hills = Object.entries(st.hills).filter(([, h]) => h.goal === gk);
  const done = g.history?.[g.history.length - 1];
  return `${projNav("map")}<div class="small mute">Goal · ${esc(g.status)}</div><h1>${esc(g.name)}</h1>
    ${done ? `<p class="sub">${esc(done.status)}: ${esc(done.reason || "")}</p>` : ""}
    <div class="section">${goalPanel(gk, g)}</div>
    <div class="section"><h2>Hills serving this goal</h2><div class="grid g3">${hills.map(([k, h]) => hillCard(k, h)).join("") || '<p class="empty">None.</p>'}</div></div>`;
};

// ---- sets and the split check ------------------------------------------------
PAGES.sets = () => {
  const st = S.state;
  const byDs = {};
  for (const s of Object.values(st.sets)) (byDs[s.dataset || "other"] ||= []).push(s);
  const ds = st.project.context?.datasets || {};
  return `${projNav("sets")}<h1>Sets</h1><p class="sub">Frozen lists of items. A hill's symptom set, its eval sets and its training sets must share no item.</p>
    <div class="sheet section" id="splitbox">${splitBanner(true)}</div>
    ${splitMatrix()}
    ${Object.entries(byDs).sort((a, b) => b[1].length - a[1].length).map(([d, list]) => `<div class="section"><h2>${esc(ds[d]?.name || d)} · ${list.length} sets</h2><div class="sheet flush"><table>
      ${list.sort((a, b) => b.created - a.created).map((s) => `<tr class="click" onclick="location.hash='#/p/${S.key}/set/${encodeURIComponent(s.key)}'"><td style="width:24%">${setN(s.key)}</td><td><span class="pill">${esc(s.role)}</span></td><td>${s.n}</td><td class="small mute">${esc((s.purpose || "").slice(0, 140))}</td></tr>`).join("")}</table></div></div>`).join("")}`;
};

function splitBanner(full) {
  const sp = S.state.split;
  const bad = sp.pairs.filter((p) => p.shared);
  const head = bad.length ? `<div class="ok-banner"><span class="dot bad"></span><div><b class="alarm">${bad.length} of ${sp.pairs.length} set pairs share items.</b><div class="small mute">They should share none. Checked ${ago(sp.checked)}.</div></div></div>`
    : `<div class="ok-banner"><span class="dot"></span><div><b>All ${sp.pairs.length} set pairs are separate.</b><div class="small mute">Zero shared items. Checked ${ago(sp.checked)}.</div></div></div>`;
  const list = full && bad.length ? `<table style="margin-top:10px">${bad.map((p) => `<tr><td>${hillN(p.hill)}</td><td>${setN(p.a)} <span class="small mute">${p.ra}</span></td><td>${setN(p.b)} <span class="small mute">${p.rb}</span></td><td class="alarm"><b>${p.shared}</b> shared</td></tr>`).join("")}</table>` : "";
  const hashes = Object.values(sp.hash_ok || {});
  const cross = (sp.cross || []).length ? `<p class="small" style="margin-top:8px">Also: ${sp.cross.length} pairs of open hills score on sets that share items, so one fix can move two hills at once.</p>` : "";
  return `<h2>Split check</h2>${head}${list}${full ? cross : ""}<div class="row" style="margin-top:10px"><button onclick="recheck()">Re-check now</button><span class="small mute">${hashes.filter(Boolean).length} of ${hashes.length} sets match their frozen fingerprint.</span>${!full ? `<a class="small" href="#/p/${S.key}/sets">Details →</a>` : ""}</div>`;
}

async function recheck() {
  S.state.split = await api("check");
  learn({ kind: "recheck" });
  render(true);
}

function splitMatrix() {
  const st = S.state;
  const keys = [...new Set(Object.values(st.hills).filter((h) => h.status !== "closed").flatMap((h) => [...(h.eval_sets || []), h.control, h.symptom_set, ...(h.train_sets || [])]).filter(Boolean))];
  if (keys.length < 2) return "";
  return `<div class="sheet section" id="matrix" data-keys="${esc(JSON.stringify(keys))}"><h2>Shared items between the sets of open hills</h2><p class="small mute">Loading…</p></div>`;
}

const _sets = {};
async function fillMatrix() {
  const el = $("#matrix");
  if (!el) return;
  const keys = JSON.parse(el.dataset.keys);
  await Promise.all(keys.filter((k) => !_sets[k]).map(async (k) => { _sets[k] = await api(`set/${encodeURIComponent(k)}`); }));
  const shared = (a, b) => a === b ? null : (_sets[a].overlaps.find((o) => o.key === b)?.shared || 0);
  const st = S.state;
  el.innerHTML = `<h2>Shared items between the sets of open hills</h2><div class="scroll-x"><table style="width:auto"><tr><th></th>${keys.map((k) => `<th style="writing-mode:vertical-rl;transform:rotate(180deg);height:120px">${esc(st.sets[k].name)}</th>`).join("")}</tr>
    ${keys.map((a) => `<tr><th>${setN(a)} <span class="mute">${st.sets[a].n}</span></th>${keys.map((b) => { const v = shared(a, b); return `<td style="text-align:center;${v ? "background:var(--alarm-soft);color:var(--alarm);font-weight:650" : ""}">${v == null ? "·" : v || ""}</td>`; }).join("")}</tr>`).join("")}</table></div>
    <p class="small mute">Empty cell: nothing shared. Red: the number of shared items. Sets that are only compared across different hills may share items on purpose (a common control).</p>`;
}

PAGES.set = async (sk) => {
  const st = S.state;
  const d = await api(`set/${encodeURIComponent(sk)}`);
  return `${projNav("sets")}<div class="small mute">Set · ${esc(d.role)} · ${esc(st.project.context?.datasets?.[d.dataset]?.name || d.dataset)}</div><h1>${esc(d.name)}</h1>
    <p class="sub">${esc(d.purpose || "")}</p>
    <div class="grid g3 section"><div class="sheet"><div class="big">${d.n}</div><div class="small mute">items, frozen ${day(d.created)}</div><div class="mono small" style="margin-top:6px">fingerprint ${esc(d.hash || "")}</div></div>
      <div class="sheet"><h2>Used by</h2>${d.users.length ? d.users.map((u) => `<p>${hillN(u.key)} <span class="small mute">as ${u.as}</span></p>`).join("") : '<p class="empty">No hill.</p>'}</div>
      <div class="sheet"><h2>Shares items with</h2>${d.overlaps.slice(0, 8).map((o) => `<p>${setN(o.key)} <span class="small mute">${o.shared} of ${o.n}</span></p>`).join("") || '<p class="empty">No other set.</p>'}</div></div>
    <div class="sheet section"><h2>Runs on this set</h2>${d.runs.length ? `<table><tr><th>Model</th><th>Score</th><th>Errors</th><th>When</th></tr>${d.runs.sort((a, b) => b.score - a.score).map((r) => `<tr class="click" onclick="location.hash='#/p/${S.key}/cand/${encodeURIComponent(r.candidate)}'"><td>${cand(r.candidate)}</td><td>${pct(r.score)} <span class="small mute">${r.passed} of ${r.n}</span></td><td>${r.errors}</td><td class="small mute">${when(r.created)}</td></tr>`).join("")}</table>` : '<p class="empty">No runs.</p>'}</div>
    ${d.annotations.length ? `<div class="sheet section"><h2>Annotations</h2>${d.annotations.map((a) => `<div class="note"><div class="when">item ${esc(a.item)}</div>${esc(a.text)}</div>`).join("")}</div>` : ""}
    <details class="section"><summary class="mute small">Item ids</summary><p class="mono small">${esc(d.ids.join(", "))}</p></details>`;
};

// ---- decisions ---------------------------------------------------------------
function decisions(n) {
  const st = S.state;
  const ev = st.timeline.filter((e) => e.type === "champion" || (e.type === "candidate.status" && e.status === "rejected") || e.type === "goal.status" || e.type === "hill.status").filter((e, i, a) => !i || a[i - 1].key !== e.key || a[i - 1].type !== e.type).slice(-n).reverse();
  if (!ev.length) return '<p class="empty">No decisions yet.</p>';
  return `<div class="list-tight">${ev.map((e) => {
    let what;
    if (e.type === "champion") what = `<span class="pill champ">champion</span> ${cand(e.key)}`;
    else if (e.type === "candidate.status") what = `<span class="pill">rejected</span> ${cand(e.key)} <span class="small mute">${esc((st.candidates[e.key]?.reason || "").slice(0, 170))}</span>`;
    else if (e.type === "goal.status") what = `<span class="pill ${e.status === "achieved" ? "champ" : ""}">goal ${esc(e.status)}</span> ${ent("goal", e.key)}`;
    else what = `<span class="pill">hill ${esc(e.status)}</span> ${hillN(e.key)}`;
    return `<div class="spread" style="flex-wrap:nowrap"><div>${what}</div><span class="small mute" style="white-space:nowrap">${ago(e.t)}</span></div>`;
  }).join("")}</div>`;
}

// ---- library -----------------------------------------------------------------
PAGES.library = (tab) => {
  const st = S.state;
  tab = tab || "external";
  const docs = Object.entries(st.docs);
  const pick = { external: ([, d]) => d.audience === "external", internal: ([, d]) => d.audience !== "external" && ["paper", "report"].includes(d.kind), notes: ([, d]) => d.kind === "note", diagrams: ([, d]) => d.kind === "diagram" };
  const list = docs.filter(pick[tab] || (() => true)).sort((a, b) => b[1].updated - a[1].updated);
  const t = (k, l) => `<a class="${tab === k ? "on" : ""}" href="#/p/${S.key}/library/${k}">${l} · ${docs.filter(pick[k]).length}</a>`;
  return `${projNav("library")}<h1>Library</h1><p class="sub">External papers explain a goal to anyone. Internal papers are the working notes of one hill.</p>
    <nav class="tabs">${t("external", "External papers")}${t("internal", "Internal papers")}${t("notes", "Notes")}${t("diagrams", "Diagrams")}</nav>
    <div class="grid g3">${list.map(([k, d]) => `<a class="sheet" href="#/p/${S.key}/doc/${encodeURIComponent(k)}" style="text-decoration:none"><div class="small mute">${esc(d.kind)} · ${esc(d.audience || "internal")}</div><h3>${esc(d.name)}</h3><p class="small">${esc(d.title || "")}</p><p class="small mute">about ${d.about ? esc(st.goals[d.about]?.name || st.hills[d.about]?.name || st.candidates[d.about]?.name || st.sets[d.about]?.name || (d.about === S.key ? "the project" : d.about)) : "the project"} · updated ${ago(d.updated)}</p></a>`).join("") || '<p class="empty">Nothing here yet.</p>'}</div>`;
};

PAGES.doc = (k) => {
  const d = S.state.docs[k];
  if (!d) return `${projNav("library")}<p class="empty">No document.</p>`;
  const src = `/api/p/${S.key}/doc/${encodeURIComponent(k)}`, v = `${src}@${d.updated}`;
  const nav = projNav("library");
  crumbs([{ label: "All projects", href: "#/" }, { label: S.state.project.name, href: `#/p/${S.key}` }, { label: d.name }]);
  if ($("#app iframe.doc")?.dataset.v === v) return null; // same paper: keep the frame, its height and the reader's place
  return `${nav}<a class="doc-alone small" href="${src}" target="_blank">Open alone ↗</a>
    <iframe class="doc" data-v="${esc(v)}" src="${src}" onload="docLoaded(this)"></iframe>`;
};

// The paper sits in the page as part of it: no frame, no inner scroll, the dashboard's theme.
const EMBED_CSS = `:root{color-scheme:light}:root[data-theme=dark]{color-scheme:dark}html,body{background:transparent!important;overflow:hidden}
html.arx-embedded main{padding:0 0 40px}.ask-hl{outline:2px solid #2f5bd3!important;outline-offset:2px}html.asking *{cursor:crosshair!important}`;
function docLoaded(f) {
  const d = f.contentDocument;
  if (!d?.body) return;
  d.documentElement.classList.add("arx-embedded");
  d.head.insertAdjacentHTML("beforeend", `<style>${EMBED_CSS}</style>`);
  docTheme();
  const fit = () => {
    const h = Math.ceil(d.documentElement.getBoundingClientRect().height);
    if (Math.abs(h - f.offsetHeight) > 1) f.style.height = `${h}px`;
    placePins();
  };
  new f.contentWindow.ResizeObserver(fit).observe(d.documentElement);
  askFrame(d);
}
function docTheme() {
  const d = $("#app iframe.doc")?.contentDocument;
  if (d?.body) d.documentElement.dataset.theme = theme() === "auto" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme();
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", docTheme);

// ---- learn: cards, review, calibration -----------------------------------------
let deck = null;
PAGES.learn = () => {
  const st = S.state, L = st.learner;
  if (!deck) deck = { i: 0, cards: L.due.slice(0, 8), phase: "front", conf: null, right: 0 };
  const c = deck.cards[deck.i];
  const calib = Object.entries(L.calibration || {});
  const fading = Object.entries(L.recall || {}).filter(([, r]) => r > 0 && r < 0.6).length;
  let body;
  if (!c) body = `<div class="card-face"><div><b>Done for now.</b><p class="small mute">${deck.right} of ${deck.cards.length} remembered. Cards come back just before you would forget them.</p><button onclick="deck=null;render()">Check for more</button></div></div>`;
  else body = `<div class="small mute" style="margin-bottom:8px">Card ${deck.i + 1} of ${deck.cards.length} · ${esc(c.kind)}${c.new ? " · new" : ""}</div>
    <div class="card-face"><div>${esc(c.front)}${deck.phase !== "front" ? `<hr style="border:0;border-top:1px solid var(--line);margin:18px 0"><div class="card-back">${esc(c.back)}</div>` : ""}</div></div>
    <div style="margin-top:14px">${deck.phase === "front" ? `<p class="small mute">Say your answer, then how sure you are:</p><button onclick="cardConf(1)">Guessing</button> <button onclick="cardConf(2)">Fairly sure</button> <button onclick="cardConf(3)">Certain</button>`
      : `<p class="small mute">How did you do?</p><button onclick="cardGrade('again')">Missed it</button> <button onclick="cardGrade('hard')">Partly</button> <button class="primary" onclick="cardGrade('good')">Got it</button> <button onclick="cardGrade('easy')">Easy</button>`}</div>`;
  return `${projNav("learn")}<h1>Learn</h1><p class="sub">Cards are written from the ledger, so they change when the research does. Answering from memory is what makes it stay.</p>
    <div class="grid g-main section"><div class="card-review">${body}</div>
    <div class="grid" style="align-content:start"><div class="sheet"><h2>Your memory</h2><p><b>${L.n_cards}</b> cards · <b>${L.n_due}</b> due · <b>${fading}</b> fading</p>
      ${Object.keys(L.hovers || {}).length ? `<h2 style="margin-top:12px">Names you keep checking</h2>${Object.entries(L.hovers).slice(0, 6).map(([e, n]) => { const [k, key] = e.split(/:(.*)/); return `<p class="small">${ent(k, key)} <span class="mute">${n}×</span></p>`; }).join("")}` : ""}</div>
      <div class="sheet"><h2>Confidence vs being right</h2>${calib.length ? calib.map(([k, v]) => `<div class="small" style="margin:6px 0">${["", "Guessing", "Fairly sure", "Certain"][k]}: right ${v.right} of ${v.n}<div class="bar"><span style="width:${(100 * v.right) / v.n}%"></span></div></div>`).join("") : '<p class="small mute">Shows up after a few cards. Being certain and wrong is the best moment to learn.</p>'}</div></div></div>`;
};
function cardConf(n) { deck.conf = n; deck.phase = "back"; render(true); }
function cardGrade(g) {
  const c = deck.cards[deck.i];
  learn({ kind: "review", card: c.key, grade: g, confidence: deck.conf, about: c.about });
  flush();
  if (g !== "again") deck.right++;
  deck.i++; deck.phase = "front"; deck.conf = null;
  render(true);
}

// Fill async parts once the page is in the DOM.
const _afterBase = PAGES._after;
PAGES._after = async () => { await _afterBase(); await fillMatrix(); };
