'use strict';
// Keys, shared by the dashboard and the paper reader: every visible, enabled control gets one key, shown as a quiet
// hint beside or on it, and pressing the key presses the control.
//   - a letter from the control's label (first letters of its words, then its other letters), kept for the same control
//     across renders and polls; markup pins one with data-key="x", opts out with data-key="none", and a control that
//     handles its own key says so with data-key-own="x" (listed in the ? overlay, no hint, not pressed here)
//   - pages: G then a letter ("G O" Overview, "G P" Papers ...), G then a digit for another project
//   - ? lists every key on the screen; Esc closes it
//   - never while typing, never with Cmd/Ctrl/Alt, never a key a view already owns: C (comments), G, digits, space,
//     Enter, arrows, [ ] + - =, and P/B/A/D/H while comment mode is on (comments.js takes those first)
//   - an open menu or popover takes the letters while it is open
//   ARXK.key(e)      handle a keydown from elsewhere (the paper's iframe)
//   ARXK.reserve(k)  a letter this page keeps for itself
//   ARXK.scan()      re-scan now (also after each dashboard render and on DOM changes, batched)
(()=>{
if(window.ARXK)return;
const LETTERS='abcdefghijklmnopqrstuvwxyz',RES=new Set(['c','g']);
const SEL='button,[role=button],[role=tab],[role=menuitem],[role=switch],[role=checkbox],[role=radio],[role=option],summary,a.btn,a.nav,a.chip,a.more,a.runchip,#rail a,#top a[href],input[type=checkbox],input[type=radio],select,[data-key],[data-key-own]';
const POPS='.sh-pop,#shp,.menu,[role=menu],[role=dialog],.ov.show';
// the hint: an empty <kbd> whose letter is CSS content, so it is never in textContent, innerText or a copied selection
const css=`.kh{all:unset;display:inline-block;flex:none;margin-left:6px;padding:0 4px;min-width:8px;text-align:center;border-radius:3px;
font:500 10px/15px var(--mono,ui-monospace,Menlo,monospace);color:var(--faint,var(--muted-fg,#8a9097));
box-shadow:inset 0 0 0 1px color-mix(in srgb,currentColor 35%,transparent);opacity:.8;pointer-events:none;vertical-align:1px;white-space:nowrap;text-transform:uppercase}
.kh::after{content:attr(data-k)}
.nav>.kh{margin-left:auto}.nav>.count+.kh{margin-left:6px}
.kh.on{position:absolute;right:0;bottom:0;margin:0;padding:0 2px;min-width:0;font-size:9px;line-height:11px;font-weight:600;box-shadow:none;
background:var(--surface,var(--background,#fff));color:var(--muted,var(--muted-fg,#5b6168));opacity:1}
.kh-hit>.kh{color:var(--accent,var(--primary,#1b6c80));opacity:1}
.btn.primary>.kh,.primary>.kh{color:inherit;opacity:.6}
@media (max-width:700px),(hover:none) and (pointer:coarse){.kh{display:none!important}}
html.arx-cm-mode .kh{display:none}
.kh-ov{position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;background:color-mix(in srgb,#000 28%,transparent)}
.kh-ov>div{max-width:min(560px,calc(100vw - 32px));max-height:80vh;overflow:auto;padding:14px 16px;border-radius:10px;
background:var(--surface,var(--background,#fff));color:var(--text,var(--foreground,#131416));border:1px solid var(--border,#e3e7eb);
display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:4px 18px;font:13px/1.5 var(--font,system-ui,sans-serif)}
.kh-ov span{display:flex;align-items:center;gap:8px;min-width:0}.kh-ov span i{font-style:normal;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kh-ov .kh{margin:0;min-width:28px;flex:none;display:inline-block!important}`;
const st=document.createElement('style');st.textContent=css;(document.head||document.documentElement).append(st);

const memo=new Map();  // control identity -> key, for the whole page life: Share keeps S on every view
let map=new Map(),gmap=new Map(),own=new Map(),gWait=0,raf=0,ov=null;
const norm=s=>String(s||'').replace(/\s+/g,' ').trim();
function labelOf(el){
 if(el.tagName==='SELECT')return norm(el.getAttribute('aria-label')||el.title||el.name);
 const t=norm(el.innerText||el.textContent);
 return norm(el.getAttribute('aria-label'))||(t&&!/^[\d\s·+−-]*$/.test(t)?t:'')||norm(el.title)||t}
const shown=el=>{if(el.closest('[hidden],[aria-hidden=true],[inert]'))return false;if(el.checkVisibility)return el.checkVisibility({visibilityProperty:true,opacityProperty:false});
 const r=el.getClientRects();return r.length>0&&getComputedStyle(el).visibility!=='hidden'};
const off=el=>el.disabled||el.getAttribute('aria-disabled')==='true'||el.closest('fieldset[disabled]');
const idOf=(el,lab)=>el.dataset.key&&el.dataset.key.length===1?'k:'+el.dataset.key:el.id?'#'+el.id:
 (el.getAttribute('href')&&!el.matches('button')?'@'+el.getAttribute('href'):'')||el.tagName+'.'+(el.classList[0]||'')+':'+lab.split(/[\s:(]/)[0].toLowerCase();
// letters the label offers, best first: each word's first letter, then the rest in order
function prefs(lab){const w=lab.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean),out=[];
 for(const x of w)if(/[a-z]/.test(x[0]))out.push(x[0]);
 for(const ch of lab.toLowerCase())if(/[a-z]/.test(ch))out.push(ch);
 return [...new Set(out)]}
const inNav=el=>el.closest('aside#nav,#rail');
function rank(el){if(el.closest('th,thead'))return 5;if(el.closest('#top,.bar'))return 1;if(el.closest('#arx-comments'))return 3;if(el.closest('#main,#root,.col'))return el.matches('.primary,.btn.primary')?0:2;return 4}

function hint(el,k){
 let h=el.querySelector(':scope>.kh');
 if(!k){h&&h.remove();return}
 const icon=!norm(el.innerText||el.textContent)||el.offsetWidth<48;
 if(!h){h=document.createElement('kbd');h.className='kh';h.setAttribute('aria-hidden','true')}
 if(h.firstChild)h.textContent='';  // a hint holds no text: the letter is CSS content
 if(h.dataset.k!==k)h.dataset.k=k;h.classList.toggle('on',icon);
 if(icon&&getComputedStyle(el).position==='static')el.style.position='relative';  // inline: a reset like all:unset would beat a class
 if(h.parentNode!==el||h.nextSibling)el.append(h)}

function scan(){
 raf=0;
 const pops=[...document.querySelectorAll(POPS)].filter(shown),scope=pops.at(-1);
 const all=[...document.querySelectorAll(SEL)].filter(el=>!el.closest('.kh-ov'));
 const nm=new Map(),ng=new Map(),no=new Map(),cand=[];
 for(const el of all){
  const dk=el.dataset.key;
  if(el.dataset.keyOwn){if(shown(el))no.set(el.dataset.keyOwn.toLowerCase(),el);hint(el,null);continue}
  if(dk==='none'||el.querySelector('kbd:not(.kh)')||off(el)||!shown(el)||scope&&!scope.contains(el)||el.closest('[data-key=none]')&&!dk){hint(el,null);continue}
  if(el.closest('aside#nav,#rail')&&!el.matches('a[href]')){hint(el,null);continue}
  const b=el.getBoundingClientRect();if(!dk&&(b.width<12||b.height<12)){hint(el,null);continue}  // a dot or a sliver: too small to carry a hint
  const lab=labelOf(el);if(!lab&&!dk){hint(el,null);continue}
  cand.push({el,lab,dk,id:idOf(el,lab||dk),r:rank(el),i:cand.length})}
 // pages: G + a letter (projects: G + a digit)
 // a label with no letter ("2"), or one that repeats down a list ("Copy" on every row), says nothing a letter could stand
 // for: those controls go without
 const seen=new Map();for(const c of cand)if(!inNav(c.el))seen.set(c.lab,(seen.get(c.lab)||0)+1);
 const mute=c=>!c.dk&&(!/[a-z]/i.test(c.lab)||seen.get(c.lab)>2);
 for(const c of cand)if(!inNav(c.el)&&mute(c))hint(c.el,null);
 const nav=cand.filter(c=>inNav(c.el)),page=cand.filter(c=>!inNav(c.el)&&!mute(c));
 let pd=1;const seenHref=new Set();
 for(const c of nav){const href=c.el.getAttribute('href')||'';
  if(c.el.classList.contains('brand')||seenHref.has(href)){hint(c.el,null);continue}seenHref.add(href);
  let k=null;
  if(c.el.classList.contains('proj')){if(!c.el.classList.contains('on')&&pd<10)k=String(pd++)}
  else k=[...(c.dk?[c.dk]:[]),...(memo.has('g'+c.id)?[memo.get('g'+c.id)]:[]),...prefs(c.lab)].find(x=>!ng.has(x));
  if(k){ng.set(k,c.el);memo.set('g'+c.id,k)}
  hint(c.el,k?'g '+k:null)}
 // the page's controls: pinned keys first
 const taken=new Set([...RES,...no.keys()]);
 if(document.documentElement.classList.contains('arx-cm-mode'))'pbadh'.split('').forEach(x=>taken.add(x));
 const got=new Map();
 for(const c of page)if(c.dk&&c.dk.length===1&&!nm.has(c.dk)){nm.set(c.dk.toLowerCase(),c.el);got.set(c,c.dk.toLowerCase())}
 const order=page.filter(c=>!got.has(c)).sort((a,b)=>a.r-b.r||a.i-b.i);
 // by rank and order, each takes the letter it had before when it is still free, else the best its label offers
 for(const c of order){
  const free=x=>LETTERS.includes(x)&&!nm.has(x)&&!taken.has(x),m=memo.get(c.id);
  const k=m&&free(m)?m:prefs(c.lab).find(free)||[...LETTERS].find(free);
  if(k){nm.set(k,c.el);got.set(c,k);memo.set(c.id,k)}}
 for(const c of page)hint(c.el,got.get(c)||null);
 if(memo.size>600)[...memo.keys()].slice(0,200).forEach(k=>memo.delete(k));
 map=nm;gmap=ng;own=no;
 if(ov)showAll(true)}
const later=()=>{if(!raf)raf=setTimeout(scan,30)};

function press(el){
 el.classList.add('kh-hit');setTimeout(()=>el.classList.remove('kh-hit'),180);
 if(el.matches('select,input:not([type=checkbox]):not([type=radio])'))el.focus();else el.click()}
function showAll(re){
 if(ov&&!re){ov.remove();ov=null;return}
 // the label without its count badge or key letter ("Goals 3" reads Goals, "Comment C" reads Comment)
 const lab=el=>{const a=norm(el.getAttribute('aria-label')||'');if(a)return a.slice(0,40);
  const c=el.cloneNode(true);c.querySelectorAll('.count,kbd,b').forEach(x=>{if(x.tagName!=='B'||x.textContent.trim().length<2)x.remove()});
  return (norm(c.textContent)||norm(el.title)).slice(0,40)};
 const rows=[];
 for(const [k,el] of map)rows.push([k,lab(el)]);
 for(const [k,el] of own)rows.push([k,lab(el)]);
 for(const [k,el] of gmap)rows.push(['g '+k,lab(el)]);
 rows.push(['?','Keys']);
 const box=ov||document.createElement('div');box.className='kh-ov';
 box.innerHTML=`<div>${rows.map(([k,l])=>`<span><kbd class="kh" data-k="${k}"></kbd><i></i></span>`).join('')}</div>`;
 box.querySelectorAll('i').forEach((x,j)=>x.textContent=rows[j][1]);
 if(!ov){box.onclick=()=>{box.remove();ov=null};document.body.append(box);ov=box}}
function key(e){
 if(e.defaultPrevented||e.metaKey||e.ctrlKey||e.altKey||e.isComposing)return;
 const t=(e.composedPath&&e.composedPath()[0])||e.target;
 if(t&&t.closest&&t.closest('input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,select,[contenteditable=""],[contenteditable=true]')||t&&t.isContentEditable)return;
 if(e.key==='Escape'&&ov){showAll();e.preventDefault();return}
 if(e.key==='?'||e.code==='Slash'&&e.shiftKey){if(raf){clearTimeout(raf);scan()}showAll();e.preventDefault();return}
 const k=e.key.length===1?e.key.toLowerCase():'';
 if(gWait&&Date.now()-gWait<1500){gWait=0;const el=gmap.get(k);if(el){e.preventDefault();ov&&showAll();press(el)}return}
 gWait=0;
 if(e.shiftKey&&!/^\d$/.test(e.key))return;
 if(k==='g'&&gmap.size){gWait=Date.now();e.preventDefault();return}
 if(raf){clearTimeout(raf);scan()}
 const el=map.get(k);if(!el||!el.isConnected)return;
 e.preventDefault();ov&&showAll();press(el)}
addEventListener('keydown',key);

// re-scan: after each dashboard render, and on DOM changes anywhere (menus, popovers, cards), batched (30 ms);
// the hints' own insertions do not count
new MutationObserver(ms=>{for(const m of ms){
 if(m.type==='attributes'){if(!(m.target.classList&&m.target.classList.contains('kh')))return later();continue}
 for(const n of [...m.addedNodes,...m.removedNodes])if(!(n.nodeType===1&&n.classList.contains('kh'))&&!(n.nodeType===1&&n.classList.contains('kh-ov'))&&!(n.nodeType===3&&!n.nodeValue.trim()))return later()}})
 .observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden','disabled','class','open','aria-disabled']});
addEventListener('resize',later);
if(typeof S!=='undefined')(S.afterRender=S.afterRender||[]).push(later);
document.readyState==='loading'?addEventListener('DOMContentLoaded',scan):later();
window.ARXK={key,scan,reserve:k=>{RES.add(String(k).toLowerCase());later()}};
})();
