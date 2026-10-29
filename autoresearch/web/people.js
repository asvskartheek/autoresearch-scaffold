'use strict';
// People (autoresearch/people.py), shared by the dashboard and the paper reader: one person per browser,
// {id, name} in localStorage `arx-me` (taken over from the old `arx-name` / `arx-reviewer`), a heartbeat that says
// which view they are on, the roster for @mentions, and the face chips that show who else is here.
//   ARXP.me()                 {id, name}
//   ARXP.setName(n)           rename (the roster follows on the next beat)
//   ARXP.start(api, routeFn)  beat to `api` (…/api/people) every 20 s and on hashchange; ARXP.on(fn) hears each answer
//   ARXP.face(id|name, name)  a round initials chip in the person's colour
//   ARXP.at(html)             @mentions of known people, wrapped in <b class="at">
//   ARXP.complete(textarea)   @ + letters offers matching names
//   ARXP.figs(body)           an agent's answer split into [sanitised inline SVG figures (HTML), the rest as text]
(()=>{
if(window.ARXP)return;
const K='arx-me',get=k=>{try{return localStorage.getItem(k)}catch(e){return null}},put=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
const hex=()=>[...crypto.getRandomValues(new Uint8Array(4))].map(b=>b.toString(16).padStart(2,'0')).join('');
let me=null;try{me=JSON.parse(get(K)||'null')}catch(e){}
if(!me||!/^p-[0-9a-f]{6,16}$/.test(me.id||'')){me={id:'p-'+hex(),name:(get('arx-name')||get('arx-reviewer')||'').trim().slice(0,40)};put(K,JSON.stringify(me))}
// another tab renamed this person: follow it
addEventListener('storage',e=>{if(e.key===K)try{const m=JSON.parse(e.newValue);if(m&&m.id===me.id){me=m;tell()}}catch(_){}});
const COLORS=['#2563eb','#db2777','#059669','#d97706','#0891b2','#dc2626','#4f46e5','#65a30d'];
const color=s=>COLORS[[...String(s)].reduce((a,c)=>(a*31+c.charCodeAt(0))>>>0,7)%COLORS.length];
const initials=n=>String(n||'').trim().split(/\s+/).map(w=>w[0]).slice(0,2).join('').toUpperCase()||'?';
const esc=s=>String(s).replace(/[.*+?^${}()|[\]\\\/-]/g,'\\$&');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let roster={},here=[],api=null,routeFn=()=>location.hash.slice(1),subs=[],timer=null;
const tell=()=>subs.forEach(f=>{try{f({roster,here,me})}catch(e){console.error(e)}});
async function beat(){if(!api)return;
 try{const r=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:me.id,name:me.name||'',route:routeFn()})});
  if(r.ok){const d=await r.json();roster=d.people||{};here=(d.here||[]).filter(x=>x.id!==me.id);tell()}}catch(e){}}
const ARXP=window.ARXP={
 me:()=>me,
 named:()=>!!me.name,
 setName(n){n=String(n||'').replace(/\s+/g,' ').trim().slice(0,40);if(!n)return;me={...me,name:n};put(K,JSON.stringify(me));beat()},
 start(url,fn){api=url;if(fn)routeFn=fn;beat();clearInterval(timer);timer=setInterval(()=>{if(!document.hidden)beat()},20000);
  addEventListener('hashchange',beat);document.addEventListener('visibilitychange',()=>{if(!document.hidden)beat()})},
 on(fn){subs.push(fn)},
 roster:()=>roster,here:()=>here,
 name:id=>id===me.id?me.name:roster[id]?.name,
 color,initials,
 face(id,name,cls=''){const n=name||ARXP.name(id)||'?';return `<span class="px-face ${cls}" style="--pc:${color(id||n)}" title="${h(n)}">${h(initials(n))}</span>`},
 // names are data: every one is escaped, the match ends where a word does (so "C++" and "tester-1" work), and a
 // name the regex cannot take only loses its highlight, never the comment
 at(html){try{const names=Object.values(roster).map(p=>String(p.name||'').trim()).filter(Boolean);
  const firsts={};names.forEach(n=>{const f=n.split(' ')[0].toLowerCase();firsts[f]=(firsts[f]||0)+1});
  const all=[...new Set([...names,...names.map(n=>n.split(' ')[0]).filter(f=>firsts[f.toLowerCase()]===1),'agent'])].sort((a,b)=>b.length-a.length);
  const re=new RegExp('(^|[\\s(>])@('+all.map(n=>esc(h(n))).join('|')+')(?![\\w-])','gi');
  return String(html).replace(re,(m,pre,n)=>`${pre}<b class="at">@${n}</b>`)}catch(e){return html}},
 complete(ta){if(!ta||ta.dataset.px)return;ta.dataset.px='1';let box=null;
  const close=()=>{box?.remove();box=null};
  ta.addEventListener('input',()=>{const v=ta.value.slice(0,ta.selectionStart),m=/(^|\s)@([\w-]{0,20})$/.exec(v);close();if(!m)return;
   const q=m[2].toLowerCase(),opts=[...Object.entries(roster).filter(([k,p])=>k!==me.id&&p.name&&p.name.toLowerCase().startsWith(q)).map(([k,p])=>[k,p.name]),...('agent'.startsWith(q)?[['agent','agent']]:[])].slice(0,5);
   if(!opts.length)return;box=document.createElement('div');box.className='px-pick';
   box.innerHTML=opts.map(([k,n])=>`<button type="button" data-n="${h(n)}">${k==='agent'?'<span class="px-face" style="--pc:var(--accent,#3b82f6)">AI</span>':ARXP.face(k,n)}${h(n)}</button>`).join('');
   const r=ta.getBoundingClientRect();Object.assign(box.style,{left:r.left+'px',top:(r.bottom+4)+'px'});document.body.append(box);
   box.onmousedown=e=>{const b=e.target.closest('button');if(!b)return;e.preventDefault();const s=ta.selectionStart,pre=ta.value.slice(0,s).replace(/@[\w-]*$/,'@'+b.dataset.n+' ');
    ta.value=pre+ta.value.slice(s);ta.selectionStart=ta.selectionEnd=pre.length;close();ta.focus()}});
  ta.addEventListener('blur',()=>setTimeout(close,150));ta.addEventListener('keydown',e=>{if(e.key==='Escape')close()})},
 // who read a thread: faces of everyone in seen (id -> t) except the authors' own last message
 seenFaces(seen,skip){return Object.keys(seen||{}).filter(k=>k!==skip).map(k=>ARXP.face(k,null,'sm')).join('')},
 figs(body){const parts=String(body||'').split(/(<svg[\s\S]*?<\/svg>)/i);
  return [parts.filter((x,i)=>i%2).map(cleanSvg).join(''),parts.filter((x,i)=>!(i%2)).join('').replace(/\n{3,}/g,'\n\n').trim()]},
 beat
};
// figures from an answer: only drawing elements and plain attributes survive; the page fits them to its width
const SVG_OK=new Set(['svg','g','path','rect','circle','line','text','polyline','tspan']);
const ATTR_OK=/^(viewbox|width|height|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|d|points|fill|stroke|stroke-width|stroke-dasharray|stroke-linecap|stroke-linejoin|opacity|fill-opacity|stroke-opacity|transform|font-size|font-weight|font-family|text-anchor|dominant-baseline|xmlns|preserveaspectratio)$/i;
function cleanSvg(src){const t=document.createElement('template');t.innerHTML=src;const svg=t.content.querySelector('svg');if(!svg)return '';
 const walk=el=>{for(const a of [...el.attributes])if(!ATTR_OK.test(a.name)||/url\s*\(|javascript:|expression|&#|\\/i.test(a.value))el.removeAttribute(a.name);
  for(const c of [...el.childNodes]){if(c.nodeType===3)continue;if(c.nodeType!==1||!SVG_OK.has(c.localName)){c.remove();continue}walk(c)}};
 walk(svg);if(!svg.getAttribute('viewBox')){const w=parseFloat(svg.getAttribute('width')),ht=parseFloat(svg.getAttribute('height'));if(w&&ht)svg.setAttribute('viewBox',`0 0 ${w} ${ht}`)}
 svg.removeAttribute('width');svg.removeAttribute('height');return `<div class="px-fig">${svg.outerHTML}</div>`}
const css=document.createElement('style');
css.textContent=`.px-face{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;flex:none;font:600 10px/1 var(--sans,system-ui);
 background:color-mix(in srgb,var(--pc) 18%,var(--page,#fff));color:var(--pc);box-shadow:0 0 0 2px var(--page,#fff)}
.px-face.sm{width:18px;height:18px;font-size:8.5px}
.px-face.on{box-shadow:0 0 0 2px var(--page,#fff),0 0 0 3.5px var(--pc)}
.px-here{display:inline-flex;align-items:center}.px-here .px-face+.px-face{margin-left:-6px}
.px-pick{position:fixed;z-index:2147483600;display:flex;flex-direction:column;min-width:180px;padding:4px;border-radius:10px;background:var(--surface,#fff);color:var(--text,#111);box-shadow:0 8px 28px rgba(0,0,0,.18),0 0 0 1px var(--border,#ddd)}
.px-pick button{all:unset;display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:6px;cursor:pointer;font:13px var(--sans,system-ui)}
.px-pick button:hover{background:var(--hover,rgba(0,0,0,.05))}
b.at{font-weight:600;color:var(--accent,#2563eb)}
.px-fig{margin:6px 0 8px;color:var(--text,inherit)}.px-fig svg{display:block;width:100%;height:auto;max-height:260px}`;
document.head.append(css);
})();
