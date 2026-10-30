// Ask: click anything to ask an agent about it. Questions and answers are ledger events; pins mark where they were asked.
const A = { on: false, draft: null, open: null, saving: null, html: "" };

function askToggle(on = !A.on) {
  if (!S.key || S.until) on = false;
  A.on = on;
  document.body.classList.toggle("asking", on);
  $("#askbtn")?.classList.toggle("on", on);
  if (!on) hlOff();
}

addEventListener("keydown", (e) => {
  if (e.target.closest?.("input, textarea, select, [contenteditable]")) return;
  if (e.key === "a" && !e.metaKey && !e.ctrlKey && !e.altKey) { askToggle(); e.preventDefault(); }
  if (e.key === "Escape") {
    if (A.draft) closeDraft();
    else if (A.open) { A.open = null; placePins(); }
    else askToggle(false);
  }
});

// ---- picking an element --------------------------------------------------
let hl = null;
function hlOff() { hl?.classList.remove("ask-hl"); hl = null; }
function pickable(el) {
  if (!el?.closest || !el.closest("#app") || el.id === "app") return null;
  return el.closest("[data-ask]") || el;
}
document.addEventListener("mouseover", (e) => {
  if (!A.on || A.draft) return;
  const el = pickable(e.target);
  if (el === hl) return;
  hlOff();
  if (el) { hl = el; el.classList.add("ask-hl"); }
});
document.addEventListener("click", (e) => {
  if (!A.on || e.target.closest("#askbox, #pins, #top")) return;
  const el = pickable(e.target);
  if (!el) return;
  e.preventDefault(); e.stopPropagation();
  openDraft(el);
}, true);

const clean = (s, n = 90) => (s || "").replace(/\s+/g, " ").trim().slice(0, n);
const PAGE_KIND = { hill: "hill", cand: "candidate", goal: "goal", set: "set", task: "task", doc: "doc" };

function anchorOf(el) {
  const ex = el.closest("[data-ask]");
  if (ex) {
    const [kind, key, what] = ex.dataset.ask.split("|");
    return { kind, key, what, loc: `[data-ask="${CSS.escape(ex.dataset.ask)}"]` };
  }
  const page = PAGE_KIND[S.route[0]];
  let kind = page || "project", key = page ? S.route[1] : S.key;
  const en = el.closest(".ent");
  if (en) { kind = en.dataset.k; key = en.dataset.key; }
  return { kind, key, what: describe(el), loc: pathOf(el) };
}

function describe(el) {
  const head = clean(el.closest(".sheet, .section")?.querySelector("h2, h3")?.textContent, 50);
  const where = head ? ` in “${head}”` : "";
  if (el.closest(".waffle")) return `item square: ${clean(el.title) || "?"}${where}`;
  if (el.closest("svg")) {
    const t = clean(el.querySelector?.("title")?.textContent || (el.tagName === "text" ? el.textContent : ""), 60);
    return `chart ${el.tagName.toLowerCase()}${t ? `: ${t}` : ""}${where}`;
  }
  const en = el.closest(".ent");
  if (en) return `${en.dataset.k}: ${clean(en.textContent)}`;
  const t = clean(el.textContent);
  return t ? `“${t}”${where}` : `${el.tagName.toLowerCase()}${where}`;
}

function pathOf(el) {
  const out = [], app = $("#app");
  for (; el && el !== app; el = el.parentElement) out.unshift([...el.parentElement.children].indexOf(el));
  return out.join(".");
}
function findLoc(loc) {
  if (!loc) return null;
  if (loc.startsWith("[")) return $(loc, $("#app"));
  let el = $("#app");
  for (const i of loc.split(".")) el = el?.children[+i];
  return el || null;
}

// ---- the question box ------------------------------------------------------
function openDraft(el) {
  hlOff();
  A.draft = { ...anchorOf(el), route: S.route.join("/") };
  const r = el.getBoundingClientRect();
  const box = $("#askbox");
  box.innerHTML = `<textarea rows="3" placeholder="What do you want to understand?"></textarea>
    <div class="spread"><span class="small mute">${esc(A.draft.what)}</span><button class="primary" onclick="sendAsk()">Ask</button></div>`;
  box.hidden = false;
  box.style.left = `${Math.max(8, Math.min(r.left + scrollX, scrollX + innerWidth - 400))}px`;
  box.style.top = `${r.bottom + scrollY + 8}px`;
  el.classList.add("ask-hl"); hl = el;
  const ta = $("textarea", box);
  ta.focus();
  ta.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAsk(); } };
}
function closeDraft() { A.draft = null; $("#askbox").hidden = true; hlOff(); }

async function sendAsk() {
  const text = $("#askbox textarea").value.trim();
  if (!text || !A.draft) return;
  const d = A.draft;
  const r = await fetch(`/api/p/${S.key}/ask`, { method: "POST", body: JSON.stringify({ ...d, text }) }).then((x) => x.json());
  closeDraft(); askToggle(false);
  learn({ kind: "ask", entity: `${d.kind}:${d.key}`, view: d.route });
  A.open = r.key;
  await loadState(); render(true);
}

// ---- answers, inline --------------------------------------------------------
// "#/set/pid183/full" is the set "pid183/full": everything after the page name is one key.
function linkHref(u) {
  const m = u.match(/^#\/(set|hill|cand|goal|task|doc)\/(.+)$/);
  if (m) return `#/p/${S.key}/${m[1]}/${encodeURIComponent(decodeURIComponent(m[2]))}`;
  if (u.startsWith("#/") && !u.startsWith("#/p/")) return `#/p/${S.key}/${u.slice(2)}`;
  return /^(#|https?:)/.test(u) ? u : "#";
}
function mdHTML(s) {
  const inl = (t) => esc(t).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*\w])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, l, u) => `<a href="${linkHref(u)}">${l}</a>`);
  return String(s || "").trim().split(/\n{2,}/).map((b) => {
    const ls = b.split("\n");
    if (ls.every((l) => /^[-*] /.test(l))) return `<ul>${ls.map((l) => `<li>${inl(l.slice(2))}</li>`).join("")}</ul>`;
    if (/^#{1,3} /.test(b)) return `<h3>${inl(b.replace(/^#+ /, ""))}</h3>`;
    return `<p>${ls.map(inl).join("<br>")}</p>`;
  }).join("");
}
const cleanSVG = (s) => String(s).replace(/<script[\s\S]*?<\/script>/gi, "").replace(/\son\w+\s*=\s*("[^"]*"|'[^']*')/gi, "");
const fileURL = (f) => `/api/p/${S.key}/answer/${encodeURIComponent(f)}`;

function partHTML(x) {
  if (x.type === "md" || x.type === "text") return `<div class="md">${mdHTML(x.body)}</div>`;
  if (x.type === "svg") return `<div class="fig">${cleanSVG(x.body)}</div>`;
  if (x.type === "png") return `<img class="fig" src="${fileURL(x.file)}" alt="">`;
  if (x.type === "html") return `<iframe class="fig" sandbox="allow-scripts allow-same-origin" src="${fileURL(x.file)}"></iframe>`;
  if (x.type === "link") return `<p><a class="golink" href="${esc(linkHref(x.url))}">${esc(x.label)} →</a></p>`;
  return "";
}
// The whole conversation about one clicked thing: the person's turns as questions, the agent's as parts.
const threadHTML = (a) => a.thread.map((x) => x.who === "person" ? `<p class="q">${esc(x.text)}</p>` : x.parts.map(partHTML).join("")).join("");

function waitWord(a) {
  if (a.status === "claimed") return '<p class="small live">An agent is working on it…</p>';
  return Date.now() / 1000 - a.created > 45 ? '<p class="small mute">No agent is listening. Run <code>arx2 ask poll</code>.</p>'
    : '<p class="small mute">Waiting for an agent…</p>';
}

function saveHTML(a) {
  const done = a.saved.map((x) => x.as === "card" ? `<a href="#/p/${S.key}/learn">Saved as card</a>` : `<a href="#/p/${S.key}/doc/${encodeURIComponent(x.key)}">Saved as ${esc(x.as)}</a>`);
  if (A.saving === a.key) {
    const nm = S.state.candidates[a.entity]?.name || S.state.hills[a.entity]?.name || S.state.sets[a.entity]?.name || S.state.goals[a.entity]?.name || "Saved answer";
    return `<div class="row"><input id="savename" value="${esc(nm)}" maxlength="24" size="16">
      ${["note", "card", "paper"].map((k) => `<button onclick="saveAs('${a.key}','${k}')">${k[0].toUpperCase() + k.slice(1)}</button>`).join("")}<span id="saveerr" class="small alarm"></span></div>`;
  }
  return `<div class="row">${done.map((d) => `<span class="small">${d}</span>`).join(" · ")}<span style="flex:1"></span><button onclick="A.saving='${a.key}';placePins()">Save</button></div>`;
}

async function saveAs(key, as) {
  const name = $("#savename")?.value || "";
  const r = await fetch(`/api/p/${S.key}/save`, { method: "POST", body: JSON.stringify({ ask: key, as, name }) }).then((x) => x.json());
  if (r.error) { $("#saveerr").textContent = r.error; return; }
  A.saving = null;
  await loadState(); render(true);
}

async function replyKey(e, key) {
  if (e.key !== "Enter" || e.shiftKey) return;
  e.preventDefault();
  const text = e.target.value.trim();
  if (!text) return;
  e.target.value = "";
  await fetch(`/api/p/${S.key}/reply`, { method: "POST", body: JSON.stringify({ ask: key, text }) });
  learn({ kind: "ask.reply", view: S.route.join("/") });
  await loadState(); render(true);
}

// ---- pins: one per question on this page, re-placed after every render --------
function pageAsks() {
  if (!S.key || !S.state?.asks || S.until) return [];
  const here = S.route.join("/");
  return Object.values(S.state.asks).filter((a) => a.route === here).sort((a, b) => a.created - b.created);
}

function placePins() {
  const box = $("#pins");
  if (!box) return;
  const list = pageAsks();
  const html = list.map((a, i) => `<button class="pin st-${a.status}" data-ask-pin="${a.key}" onclick="A.open=A.open==='${a.key}'?null:'${a.key}';A.saving=null;placePins()">${i + 1}</button>
    ${A.open === a.key ? `<div class="askpop" data-pop="${a.key}"><div class="small mute">${esc(a.what)}</div>${threadHTML(a)}
      ${a.status === "answered" ? saveHTML(a) + `<textarea class="reply" rows="2" placeholder="Ask more" onkeydown="replyKey(event,'${a.key}')"></textarea>` : waitWord(a)}</div>` : ""}`).join("");
  const top = $(".askpop", box)?.scrollTop || 0;
  if (html !== A.html) {
    const ta = $("textarea.reply", box), typed = ta?.value, focused = ta && document.activeElement === ta;
    box.innerHTML = html; A.html = html;
    const nt = $("textarea.reply", box);
    if (nt && typed) nt.value = typed;
    if (nt && focused) nt.focus();
  }
  for (const a of list) {
    const el = findLoc(a.loc) || $("#app h1");
    const r = el?.getBoundingClientRect() || { right: 40, top: 80 };
    const x = Math.min(r.right + scrollX - 10, scrollX + innerWidth - 30), y = r.top + scrollY - 10;
    const pin = $(`[data-ask-pin="${a.key}"]`, box);
    pin.style.left = `${x}px`; pin.style.top = `${y}px`;
    const pop = $(`[data-pop="${a.key}"]`, box);
    if (pop) {
      pop.style.left = `${Math.max(8, Math.min(x - 20, scrollX + innerWidth - 470))}px`;
      pop.style.top = `${y + 28}px`;
      pop.style.maxHeight = `${Math.max(260, innerHeight - (y + 28 - scrollY) - 12)}px`;
      pop.scrollTop = top;
    }
  }
}
addEventListener("resize", () => placePins());

// ---- saved answers become part of the entity's page ------------------------------
function savedHere(key) {
  const st = S.state;
  const docs = Object.entries(st.docs).filter(([, d]) => d.ask && d.about === key && st.asks[d.ask]);
  if (!docs.length) return "";
  return `<div class="sheet section"><h2>Notes</h2>${docs.map(([k, d]) => {
    const a = st.asks[d.ask];
    return `<div class="saved"><div class="spread"><h3>${ent("doc", k)}</h3><span class="small mute">${esc(d.kind)} · ${ago(d.updated)}</span></div>
      ${threadHTML(a)}</div>`;
  }).join("")}</div>`;
}
for (const [page, keyOf] of [["hill", (k) => k], ["cand", (k) => k], ["goal", (k) => k], ["set", (k) => k], ["task", (k) => k], ["map", () => S.key]]) {
  const f = PAGES[page];
  PAGES[page] = async (...args) => {
    const html = await f(...args);
    return html == null ? html : html + savedHere(keyOf(args[0]));
  };
}
const _afterAsk = PAGES._after;
PAGES._after = async () => { await _afterAsk(); placePins(); };
