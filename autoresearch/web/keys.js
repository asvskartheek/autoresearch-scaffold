'use strict';
// Keys, Vim-like, shared by the dashboard and the paper reader. Controls carry no hints: the sidebar shows each page's
// g-key, f labels what is on screen when asked, and ? lists exactly the keys that work right now.
//   j / k        the ring down / up through the view's items in visual order (top to bottom, row by row, the left
//                column before the right); with no item near, they scroll, so a long page reads with j / k too
//   gg / G       first / last item       o, Enter  open the ringed item (follow its link, open its thread: never a
//                write control)          O  its link in a new tab
//   h, Backspace back in history (as a browser)     l  forward     u  up a level (the crumb above)
//   g + letter   a page (g r Start, g o Overview, g b Brief, g c Course, g t Goals ...); g 1-9 a project, numbered in
//                registry order, the same from every project (11 or more: g 1 1); a pending g wins over a view's keys
//   f / F        hint labels on every visible control (the paper's own too); type one to press it, F opens in a tab
//   /            the view's search box (Enter: to the first result; Esc: leave it), else a find line over the items
//   n / N        next / previous match after a find, else next / previous comment thread
//   c / r / x    comment on the ringed item / reply in / resolve its open thread
//   ?            the sheet; click (or f) a key to rebind it. Rebinds are per person, localStorage `arx-keys`.
// The ring and the browser's focus are one: j moves focus to the item, Tab onto an item moves the ring there.
// Never while typing, never with Cmd/Ctrl/Alt, never a key a view took first (defaultPrevented: the Brief's space,
// Enter, digits, arrows, [ ]) or one the page reserves (ARXK.reserve: the paper keeps B A D H P for its tools).
//   ARXK.key(e)  handle a keydown from elsewhere (the paper's iframe)     ARXK.focused()  the item under the ring
(()=>{
if(window.ARXK)return;
// pages: g + this letter (gg stays "top", so Goals is g t: targets; Start is g r: root)
const PAGES={start:'r',overview:'o',learn:'b',course:'c',workbench:'w',goals:'t',questions:'q',models:'m',hills:'h',papers:'p',slices:'s',archive:'a',memory:'y'};
const NAMES={r:'Start',o:'Overview',b:'Brief',c:'Course',w:'Workbench',t:'Goals',q:'Questions',m:'Models',h:'Hills',p:'Papers',s:'Slices',a:'Archive',y:'Memory'};
// a view's items: rows, cards, tiles, comment cards; plus (below) any block-sized link in the view
const ITEMS=['tr.click','#main tbody tr:has(a[href])','article.wb-job','a.wb-chip','.q-row','a.ov-goal','a.ov-task',
 'a.sx-g','a.sx-need','a.sx-job','a.sx-tile','a.sx-pg','a.sx-champ','a.sx-brief','a.gm-node','section.gl-card',
 'article.hcard','.lrn section.stage','.lrn aside.lside>section.card','.concepts>button.concept','#main details>summary','[data-item]','#col .card'].join(',');
const CLICKABLE='a[href],button,[role=button],[role=tab],[role=menuitem],[role=switch],[role=checkbox],[role=radio],[role=option],summary,input:not([type=hidden]),select,textarea,tr.click,[onclick],[data-qgo],.cm-pin,'+ITEMS;
// keys no action may take: fixed ones and the views' own (the Brief's); the paper's tools keep B A D H P
const FIXED=new Set(['Escape','Enter','Backspace','Tab','g',' ','[',']','+','-','=','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','1','2','3','4','5','6','7','8','9','0']);
const PAPER={b:'box',a:'arrow',d:'pen',h:'highlight',p:'pause'};
const css=`.kf{outline:2px solid var(--ring,var(--accent,#1b6c80))!important;outline-offset:2px;border-radius:4px;
box-shadow:0 0 0 6px color-mix(in srgb,var(--ring,var(--accent,#1b6c80)) 16%,transparent)!important}
tr.kf{outline-offset:-2px;box-shadow:none!important}
tr.kf>td{background-image:linear-gradient(color-mix(in srgb,var(--ring,var(--accent,#1b6c80)) 9%,transparent),color-mix(in srgb,var(--ring,var(--accent,#1b6c80)) 9%,transparent))}
.kn{flex:none;margin-left:auto;padding-left:8px;font:500 10px/1 var(--mono,ui-monospace,Menlo,monospace);color:var(--faint,#8a9097);opacity:.7;letter-spacing:.06em;white-space:nowrap}
.count+.kn{margin-left:6px;padding-left:0}
@media (hover:none) and (pointer:coarse){.kn{display:none}}
.kh-ov{position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;background:color-mix(in srgb,#000 30%,transparent)}
.kh-ov>div{width:min(620px,calc(100vw - 32px));max-height:86vh;overflow:auto;padding:14px 18px 12px;border-radius:10px;
background:var(--surface,var(--page,var(--background,#fff)));color:var(--text,var(--foreground,#131416));border:1px solid var(--border,#e3e7eb);
font:13px/1.45 var(--font,system-ui,sans-serif)}
.kh-hd{display:flex;align-items:baseline;gap:12px;margin-bottom:8px}.kh-hd b{font-size:14px;font-weight:600}
.kh-hd .kh-x{margin-left:auto;font-size:12px;color:var(--muted-fg,var(--muted,#5b6168))}
.kh-gs{display:grid;grid-template-columns:1fr 1fr;gap:10px 26px}
.kh-g h4{margin:0 0 3px;font:600 11px/1.6 var(--font,system-ui,sans-serif);color:var(--muted-fg,var(--muted,#5b6168));text-transform:uppercase;letter-spacing:.06em}
.kh-g span{display:flex;align-items:center;gap:10px;min-width:0;padding:1px 0}.kh-g i{font-style:normal;color:var(--muted-fg,var(--muted,#5b6168));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kh-k{flex:none;display:flex;align-items:center;gap:4px;min-width:72px;font-weight:inherit}
.kh-ov kbd{all:unset;flex:none;min-width:22px;font:500 11px/20px var(--mono,ui-monospace,Menlo,monospace);color:var(--text,var(--foreground,#131416))}
.kh-ov kbd.sym{font:400 14px/20px system-ui,sans-serif;text-align:center}
.kh-ov button{all:unset;flex:none;min-width:22px;padding:0 5px;border-radius:4px;cursor:pointer;text-align:center;font:500 11px/20px var(--mono,ui-monospace,Menlo,monospace);
color:var(--text,var(--foreground,#131416));box-shadow:inset 0 0 0 1px var(--border,#e3e7eb)}
.kh-ov button:hover,.kh-ov button.on{box-shadow:inset 0 0 0 1px var(--ring,var(--accent,#1b6c80))}
.kh-ov button:focus-visible{box-shadow:inset 0 0 0 2px var(--ring,var(--accent,#1b6c80))}
.kh-ov button.kh-rs{font-family:var(--font,system-ui,sans-serif);font-size:12px}
@media (max-width:520px){.kh-gs{grid-template-columns:1fr}}
.kh-l{position:fixed;inset:0;z-index:2147483001;pointer-events:none}
.kh-l b{position:absolute;padding:0 3px;border-radius:3px;font:600 11px/15px var(--mono,ui-monospace,Menlo,monospace);text-transform:uppercase;
background:var(--text,var(--foreground,#131416));color:var(--surface,var(--page,var(--background,#fff)));box-shadow:0 1px 2px rgba(0,0,0,.25);white-space:nowrap}
.kh-l b u{text-decoration:none;opacity:.45}.kh-l b.no{display:none}
.kh-find{position:fixed;left:16px;bottom:16px;z-index:2147483000;display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:8px;
background:var(--surface,var(--page,var(--background,#fff)));color:var(--text,var(--foreground,#131416));border:1px solid var(--ring,var(--accent,#1b6c80));
box-shadow:0 4px 14px rgba(0,0,0,.18);font:500 13px/1.4 var(--mono,ui-monospace,Menlo,monospace)}
.kh-find input{all:unset;width:min(260px,calc(100vw - 110px));font:inherit}.kh-find i{font-style:normal;color:var(--muted-fg,var(--muted,#5b6168));font-size:12px}`;
const st=document.createElement('style');st.textContent=css;(document.head||document.documentElement).append(st);

const RES=new Set();
let cur=null,sig=null,idx=-1,gw=null,ov=null,ovFrom=null,hm=null,listen=null,msg='',used=false,wantSel=0,fb=null,findQ='';
const get=()=>{try{return JSON.parse(localStorage.getItem('arx-keys')||'{}')||{}}catch(e){return {}}};
const put=o=>{try{localStorage.setItem('arx-keys',JSON.stringify(o))}catch(e){}};
let over=get();addEventListener('storage',e=>{if(e.key==='arx-keys')over=get()});
const shown=el=>el.getClientRects().length>0&&!el.closest('[hidden]')&&(!el.checkVisibility||el.checkVisibility({visibilityProperty:true,opacityProperty:true}));
const main=()=>document.querySelector('#main')||document.querySelector('#root')||document.body;
const topEdge=()=>(document.querySelector('#top,.bar')?.getBoundingClientRect().bottom||0)+8;
// the lowest line not covered by a bar fixed to the bottom of the window (the comment bar, a toast)
function bottomEdge(){let b=innerHeight;
 for(const f of [.2,.5,.8]){let el=document.elementFromPoint(innerWidth*f,innerHeight-6);
  for(;el&&el!==document.body&&el!==document.documentElement;el=el.parentElement){const p=getComputedStyle(el).position;
   if(p==='fixed'||p==='sticky'){if(!el.closest('.kh-l,.kh-ov,.kh-find')){const t=el.getBoundingClientRect().top;if(t>innerHeight*.5)b=Math.min(b,t)}break}}}
 return b-8}
const route=()=>(location.hash.slice(1)||'overview').split('/')[0];
const base=()=>(location.pathname.match(/^\/p\/[^/]+/)||[''])[0];
const where=()=>location.pathname+location.hash;

// ---------- items, in visual order
// a pane: a column with another column beside it (Questions' tree and notes, the paper and its comments). Items read
// pane by pane, left to right; inside a pane, row by row
function besideOf(p,cache){let v=cache.get(p);if(v!==undefined)return v;v=false;const r=p.getBoundingClientRect();
 if(r.height>=150)for(const s of [p.previousElementSibling,p.nextElementSibling]){if(!s||!s.getClientRects().length)continue;const q=s.getBoundingClientRect();
  if(q.width>0&&q.height>40&&(q.right<=r.left+1||q.left>=r.right-1)&&q.top<r.bottom&&q.bottom>r.top){v=true;break}}
 cache.set(p,v);return v}
function paneOf(el,cache){let best=null;for(let p=el.parentElement;p&&p!==document.body&&p.id!=='main'&&p.id!=='root';p=p.parentElement)if(besideOf(p,cache))best=p;return best}
function sortVisual(list){const cache=new Map(),R=new Map(list.map(el=>{const p=paneOf(el,cache);return [el,{r:el.getBoundingClientRect(),p,pr:p&&p.getBoundingClientRect()}]}));
 const rowMajor=(a,b)=>{const h=Math.min(a.height,b.height)/2;return Math.abs(a.top-b.top)<Math.max(4,h)?a.left-b.left:a.top-b.top};
 return list.sort((x,y)=>{const a=R.get(x),b=R.get(y);
  if(a.p!==b.p){const pa=a.pr||a.r,pb=b.pr||b.r;if(pa.right<=pb.left+1)return -1;if(pb.right<=pa.left+1)return 1}
  return rowMajor(a.r,b.r)})}
const blockLink=a=>{if(a.matches('.btn,nav a,.crumbs a'))return false;const d=getComputedStyle(a).display;if(d==='inline'||d==='contents')return false;
 const r=a.getBoundingClientRect();return r.width>=200&&r.height>=28};
function items(){
 const m=main(),inv=el=>shown(el)&&(m.contains(el)||!!el.closest('#col'));
 const all=new Set([...document.querySelectorAll(ITEMS)].filter(inv));
 if(m.id==='main')for(const a of m.querySelectorAll('a[href]'))if(!all.has(a)&&shown(a)&&blockLink(a))all.add(a);
 const arr=[...all];return sortVisual(arr.filter(el=>!arr.some(o=>o!==el&&o.contains(el))))}  // the outermost item only
// an item's signature: what it links to, else its first words; keeps the ring on the same item across re-renders
const sigOf=el=>(el.matches('a[href]')?el:el.querySelector('a[href]'))?.getAttribute('href')||el.getAttribute('onclick')||el.dataset.id||el.dataset.qgo||(el.textContent||'').replace(/\s+/g,' ').trim().slice(0,60);
const inView=el=>{const r=el.getBoundingClientRect();return r.bottom>topEdge()&&r.top<bottomEdge()};

// ---------- the ring: one item, and the browser's focus on it
let ringing=false;
function ring(el,scroll=true,focus=true){
 const was=cur;document.querySelectorAll('.kf').forEach(x=>x!==el&&x.classList.remove('kf'));
 cur=el||null;sig=el?sigOf(el):null;
 if(!el){idx=-1;if(was&&document.activeElement===was)was.blur();return}
 el.classList.add('kf');idx=items().indexOf(el);
 if(focus&&document.activeElement!==el){if(!el.matches('a[href],button,input,select,textarea,summary,[tabindex]'))el.setAttribute('tabindex','-1');
  ringing=true;try{el.focus({preventScroll:true})}catch(e){}ringing=false}
 if(scroll){const r=el.getBoundingClientRect(),top=topEdge(),bot=bottomEdge();
  if(r.top<top||r.height>bot-top)scrollBy({top:r.top-top});else if(r.bottom>bot)scrollBy({top:r.bottom-bot})}}
// after a render the old node is gone: find the same item again, else (after a move within a view) the selected one,
// else the one at the same place. The focus follows only if it was on the ring (never out of a box being typed in)
function reattach(){if(!sig&&!wantSel)return;if(cur&&cur.isConnected&&cur.classList.contains('kf'))return;
 const its=items();let el=sig?its.find(x=>sigOf(x)===sig):null;
 if(!el&&wantSel&&Date.now()-wantSel<3000)el=its.find(x=>x.matches('.on,.sel,[aria-current]:not([aria-current=false]),[aria-selected=true]'));
 if(!el&&sig&&idx>=0&&its.length&&!wantSel)el=its[Math.min(idx,its.length-1)];
 if(el){const a=document.activeElement;wantSel=0;ring(el,false,!a||a===document.body||a===cur)}
 else if(!wantSel||Date.now()-wantSel>=3000){wantSel=0;if(sig&&!its.length)return;cur=null;sig=null;idx=-1}}
const focused=()=>{reattach();return cur&&cur.isConnected?cur:null};
function move(d){
 const its=items(),H=innerHeight,step=Math.round(H*.4);
 if(!its.length){scrollBy({top:d*step});return}
 reattach();let i=cur?its.indexOf(cur):-1;if(i>=0&&!inView(cur))i=-1;  // the ring scrolled away: start from what is on screen
 let t;
 if(i<0){t=d>0?its.find(inView):its.findLast(inView);
  if(!t)t=d>0?its.find(x=>x.getBoundingClientRect().top>=topEdge()):its.findLast(x=>x.getBoundingClientRect().bottom<=bottomEdge())}
 else t=its[i+d];
 if(!t){scrollBy({top:d*step});return}  // past the last item: keep reading
 const r=t.getBoundingClientRect(),far=d>0?r.top-bottomEdge():topEdge()-r.bottom;
 if(far>H*.6){scrollBy({top:d*step});return}  // the next item is a page away: read towards it first
 ring(t)}
function edge(last){if(last)scrollTo({top:document.documentElement.scrollHeight});else scrollTo({top:0});
 const its=items();if(its.length)ring(last?its.at(-1):its[0])}

// ---------- open: what each kind of item opens. Never a button inside it (Resolve, a caret, Delete): the item itself
// when it is the control (a row, a link, a card that opens its thread), else its heading link, else its first link
function openTarget(el){
 if(el.matches('a[href],tr.click,[onclick],summary,[data-qgo],[data-open],button.concept,#col .card'))return el;
 return el.querySelector('[data-open]')||el.querySelector('h1 a[href],h2 a[href],h3 a[href],h4 a[href]')||el.querySelector('a[href]')}
const linkOf=el=>{const t=openTarget(el);return t&&t.matches('a[href]')?t:el.querySelector('a[href]')};
function open(el,tab){if(!el)return;if(tab){const a=linkOf(el);if(a)open1(a.href);return}const t=openTarget(el);if(t)t.click()}
const open1=u=>{const w=window.open(u,'_blank','noopener');if(w)w.opener=null};
const crumbUp=()=>[...document.querySelectorAll('#top .crumbs a[href],.bar .ttl a.crumb')].at(-1);
function up(){const c=crumbUp();if(c)c.click()}
function back(){if(history.length>1)history.back();else up()}

// ---------- search: the view's box, else a find line over the items
const search=()=>[...main().querySelectorAll('input[type=search],.sl-q input,.arc-q input')].find(shown);
const textOf=el=>(el.textContent||'').replace(/\s+/g,' ').toLowerCase();
function matches(){const q=findQ.trim().toLowerCase();if(!q)return [];let pool=items();
 if(!pool.length)pool=sortVisual([...main().querySelectorAll('a[href]')].filter(shown));return pool.filter(x=>textOf(x).includes(q))}
function findOpen(){
 if(fb){fb.querySelector('input').focus();return}
 const from=cur;fb=document.createElement('div');fb.className='kh-find';fb.innerHTML='<span>/</span><input spellcheck="false" autocomplete="off" aria-label="Find"><i></i>';
 document.body.append(fb);const inp=fb.querySelector('input'),out=fb.querySelector('i');
 inp.oninput=()=>{findQ=inp.value;const m=matches();
  const at=from&&from.isConnected?from.getBoundingClientRect().top:-1e9,t=m.find(x=>x.getBoundingClientRect().top>=at)||m[0];
  if(t)ring(t,true,false);out.textContent=findQ.trim()?(m.length?`${m.indexOf(t)+1} of ${m.length}`:'0'):''};
 inp.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();findClose();cur&&ring(cur,false)}
  else if(e.key==='Escape'){e.preventDefault();findQ='';findClose();ring(from&&from.isConnected?from:null)}};
 inp.focus()}
function findClose(){if(fb){fb.remove();fb=null}}
function findStep(d){const m=matches();if(!m.length)return;let i=cur?m.indexOf(cur):-1;
 if(i<0){const at=cur?cur.getBoundingClientRect().top:topEdge();i=d>0?m.findIndex(x=>x.getBoundingClientRect().top>at)-1:m.findIndex(x=>x.getBoundingClientRect().top>=at);if(i<-1)i=d>0?-1:m.length}
 ring(m[(i+d+m.length)%m.length])}

// ---------- pages and projects
const label=a=>{const c=a.cloneNode(true);c.querySelectorAll('.count,.kn,.pdot').forEach(x=>x.remove());return (c.textContent||a.title||'').replace(/\s+/g,' ').trim()};
function pages(){const out=new Map(),extra=[];
 for(const a of document.querySelectorAll('aside#nav a.nav:not(.proj),#rail a[href]')){const href=a.getAttribute('href')||'';
  const r=(href.split('#')[1]||'').split('/')[0],k=PAGES[r];
  if(k){if(!out.has(k))out.set(k,{el:a,name:label(a)||NAMES[k],go:()=>a.click()})}else if(r)extra.push(a)}
 // a page this file does not know yet takes the first free letter of its name
 for(const a of extra){const k=[...label(a).toLowerCase()].find(c=>/[a-z]/.test(c)&&c!=='g'&&!out.has(c)&&!Object.values(PAGES).includes(c));if(k)out.set(k,{el:a,name:label(a),go:()=>a.click()})}
 // the pages this page's nav does not show (the paper's rail has no Start, Brief or Questions): by URL
 const dash=typeof VIEWS!=='undefined';
 for(const [r,k] of Object.entries(PAGES))if(!out.has(k)&&(dash?!!VIEWS[r]:r!=='memory'))
  out.set(k,{name:NAMES[k],go:()=>{if(dash)location.hash=r;else location.href=base()+'/#'+r}});
 return out}
// projects, numbered in registry order (the sidebar's order), the same numbers from every project
let reg=null;
function projects(){const ls=[...document.querySelectorAll('aside#nav a.nav.proj')];
 if(ls.length)return ls.map(a=>({el:a,name:label(a),on:a.classList.contains('on'),go:()=>a.click()}));
 if(!reg){reg=[];fetch('/api/projects').then(r=>r.json()).then(ps=>{reg=ps.map(q=>({name:q.name,on:'/p/'+encodeURIComponent(q.key)===base()||!base()&&q.default,go:()=>{location.href='/p/'+encodeURIComponent(q.key)+'/'}}))}).catch(()=>{})}
 return reg.length>1?reg:[]}
function goProject(n){const p=projects()[n-1];if(p&&!p.on)p.go()}
// the sidebar shows each page's key, quietly, after its label
function navHints(){const nav=document.querySelector('aside#nav');if(!nav)return;
 const put=(a,t)=>{let n=a.querySelector(':scope>.kn');if(!n){n=document.createElement('span');n.className='kn';n.setAttribute('aria-hidden','true');a.append(n)}if(n.textContent!==t)n.textContent=t};
 for(const [k,p] of pages())if(p.el&&nav.contains(p.el))put(p.el,'g '+k);
 projects().forEach((p,i)=>p.el&&put(p.el,'g '+(i+1)))}
// g pressed: the next key (or two digits, with 10 or more projects) picks the page
function gKey(e){
 if(!gw)return false;if(Date.now()-gw.t>1500&&!gw.d){gw=null;return false}
 const k=e.key;if(['Shift','Meta','Control','Alt','CapsLock'].includes(k))return true;
 e.preventDefault();e.stopImmediatePropagation();clearTimeout(gw.tm);
 const first=gw.d;gw=null;
 if(/^\d$/.test(k)){
  if(first){goProject(+(first+k));return true}
  const n=projects().length;
  if(k!=='0'&&n>=+k*10){gw={t:Date.now(),d:k,tm:setTimeout(()=>{if(gw&&gw.d===k){gw=null;goProject(+k)}},800)};return true}
  goProject(k==='0'?10:+k);return true}
 if(first){goProject(+first);return true}
 if(k==='g'){edge(false);return true}
 const p=pages().get(k.toLowerCase());if(p){ov&&closeSheet();p.go()}
 return true}

// ---------- the Brief, the hill and the paper keep keys of their own; the sheet lists the ones live now
function own(){const r=[];
 if(route()==='learn'&&typeof L!=='undefined'&&L.b){
  const c=L.b.cards[L.cur];
  if(!c)r.push(['space','Start']);
  else if(c.pred)r.push(['space','Next card']);
  else{r.push(['space','Check']);const t=c.task||{};
   if(typeof TEACH!=='undefined'&&TEACH.active(c)){
    if(c.method==='sketch'){r.push(['← → ↑ ↓','Move the sketch']);if(t.kind==='ci')r.push(['+ −','Zoom'])}
    else if(c.method==='spot')r.push([t.parts?'1 – '+t.parts.length:'1 – 9','Pick a part'])}
   else if(c.type==='choice')r.push(['1 – '+c.opts.length,'Pick an answer'],['← →','Change the answer'],['↑ ↓','Confidence']);
   else if(c.type==='number')r.push(['← →','Move the guess'],['⇧ ← →','Move it further'],['↑ ↓','Confidence'])}
  r.push(['[ ]','Previous, next card'])}
 if(route()==='hill'&&typeof exsOf==='function'&&typeof S!=='undefined'){const a=location.hash.split('/')[1];
  if(exsOf(S.state?.hills?.[decodeURIComponent(a||'')]).length>1)r.push(['← →','Previous, next example'])}
 if(RES.has('b')){const tl=document.querySelector('#tools');if(tl&&shown(tl))r.push(['b a d h','Box, arrow, pen, highlight']);r.push(['⌘⌥M','Comment on the selection'])}
 if(RES.has('p')){try{const d=document.querySelector('#page iframe')?.contentDocument;if(d&&d.querySelector('script[src*="explain-kit"]'))r.push(['p','Pause the figure'])}catch(e){}}
 return r}

// ---------- actions: a default key, a fixed name, a live label, when it is live, what it does. Rebindable by id.
const C=()=>window.ARXC;
const pagerBtn=s=>{const b=document.querySelector(s);return b&&shown(b)&&!b.disabled?b:null};
const thing=()=>({workbench:'task',archive:'task',models:'model',hills:'hill',goals:'goal',papers:'paper',questions:'question',slices:'slice',start:'item',overview:'item',learn:'card'}[route()]||(cur&&cur.closest('#col')?'thread':'item'));
const ACTS=[
 {id:'down',g:'Move',k:'j',n:'Next item',l:()=>items().length?'Next '+thing():'Scroll down',run:()=>move(1)},
 {id:'up',g:'Move',k:'k',n:'Previous item',l:()=>items().length?'Previous '+thing():'Scroll up',run:()=>move(-1)},
 {id:'bottom',g:'Move',k:'G',n:'Last item',l:()=>items().length?'Last '+thing():'Bottom',run:()=>edge(true)},
 {id:'back',g:'Move',k:'h',alt:'⌫',n:'Back',l:()=>'Back',run:back},
 {id:'forward',g:'Move',k:'l',n:'Forward',l:()=>'Forward',run:()=>history.forward()},
 {id:'upLevel',g:'Move',k:'u',n:'Up a level',l:()=>'Up to '+(crumbUp()?label(crumbUp()):''),when:()=>!!crumbUp(),run:up},
 {id:'open',g:'Act',k:'o',alt:'Enter',n:'Open',l:()=>'Open the '+thing(),when:()=>!!focused(),run:()=>open(cur)},
 {id:'openTab',g:'Act',k:'O',n:'Open in a new tab',l:()=>'Open in a new tab',when:()=>!!(focused()&&linkOf(cur)),run:()=>open(cur,true)},
 {id:'hints',g:'Act',k:'f',n:'Label what is on screen',l:()=>'Press anything on screen',run:()=>hintMode(false)},
 {id:'hintsTab',g:'Act',k:'F',n:'Label links for a new tab',l:()=>'Open a link in a new tab',run:()=>hintMode(true)},
 {id:'search',g:'Act',k:'/',n:'Search',l:()=>search()?'Search':'Find',run:()=>{const s=search();if(s){s.focus();s.select?.()}else findOpen()}},
 {id:'next',g:'Act',k:'n',n:'Next match or thread',l:()=>findQ?'Next match':'Next comment',when:()=>!!findQ||(C()?C().count()>0:!!pagerBtn('#next')),run:()=>findQ?findStep(1):C()?C().step(1):pagerBtn('#next').click()},
 {id:'prev',g:'Act',k:'N',n:'Previous match or thread',l:()=>findQ?'Previous match':'Previous comment',when:()=>!!findQ||(C()?C().count()>0:!!pagerBtn('#prev')),run:()=>findQ?findStep(-1):C()?C().step(-1):pagerBtn('#prev').click()},
 {id:'comment',g:'Comments',k:'c',n:'Comment',l:()=>focused()?'Comment on the '+thing():C()&&C().mode()?'Stop picking':'Pick something to comment on',when:()=>!!C(),run:()=>C().comment(focused())},
 {id:'reply',g:'Comments',k:'r',n:'Reply',l:()=>'Reply in the thread',when:()=>!!C()&&C().has(focused()),run:()=>C().reply(focused())},
 {id:'resolve',g:'Comments',k:'x',n:'Resolve',l:()=>'Resolve the thread',when:()=>!!C()&&C().has(focused()),run:()=>C().resolve(focused())},
 {id:'help',g:'Act',k:'?',n:'Keys',l:()=>'Keys',run:()=>sheet()}];
const keyOf=a=>over[a.id]||a.k;
const live=a=>!a.when||a.when();

// ---------- the sheet: grouped, only what works here; click (or f) a key, then press the new one
function sheet(){if(ov){closeSheet();return}
 ovFrom=document.activeElement;ov=document.createElement('div');ov.className='kh-ov';ov.setAttribute('role','dialog');ov.setAttribute('aria-modal','true');ov.setAttribute('aria-label','Keys');
 ov.onclick=e=>{if(e.target===ov)closeSheet()};document.body.append(ov);drawSheet();ov.querySelector('button')?.focus()}
function closeSheet(){if(!ov)return;ov.remove();ov=null;listen=null;msg='';if(ovFrom&&ovFrom.isConnected&&ovFrom!==document.body)try{ovFrom.focus({preventScroll:true})}catch(e){}ovFrom=null}
function drawSheet(){if(!ov)return;
 const had=ov.contains(document.activeElement)?document.activeElement.dataset.id:null;
 const groups={Move:[],Act:[],Comments:[],'Go to':[],'This page':[]};
 const kb=t=>{const k=document.createElement('kbd');k.textContent=t;if(/[^\x20-\x7e]/.test(t.replace(/–/g,'')))k.className='sym';return k};
 const row=(g,keys,l)=>{const s=document.createElement('span'),c=document.createElement('b'),i=document.createElement('i');c.className='kh-k';c.append(...keys);i.textContent=l;s.append(c,i);groups[g].push(s)};
 row('Move',[kb('gg')],items().length?'First '+thing():'Top');
 for(const a of ACTS){if(!live(a))continue;const k=keyOf(a);if(RES.has(k.toLowerCase())&&!a.alt)continue;
  const ks=[];
  if(!RES.has(k.toLowerCase())){const b=document.createElement('button');b.dataset.id=a.id;b.textContent=listen===a.id?'…':k;b.title='Change key';b.setAttribute('aria-label','Change the key for '+a.n);b.className=listen===a.id?'on':'';
   b.onclick=e=>{e.stopPropagation();listen=listen===a.id?null:a.id;msg=listen?'Press the new key':'';drawSheet()};ks.push(b)}
  if(a.alt)ks.push(kb(a.alt));
  row(a.g,ks,a.l())}
 row('Act',[kb('Esc')],'Close');
 const ps=pages(),pj=projects();
 for(const [k,p] of [...ps].sort((x,y)=>(x[1].el?0:1)-(y[1].el?0:1)))row('Go to',[kb('g '+k)],p.name);
 if(pj.length)row('Go to',[kb(pj.length>1?'g 1 – '+pj.length:'g 1')],'Project, in sidebar order');
 for(const [k,l] of own())row('This page',[kb(k)],l);
 const box=document.createElement('div'),hd=document.createElement('div');hd.className='kh-hd';
 const t=document.createElement('b');t.textContent='Keys';const x=document.createElement('span');x.className='kh-x';x.textContent=msg;hd.append(t,x);
 if(Object.keys(over).length){const r=document.createElement('button');r.className='kh-rs';r.dataset.id='reset';r.textContent='Reset keys';r.onclick=e=>{e.stopPropagation();over={};put(over);msg='';drawSheet()};hd.append(r)}
 const gs=document.createElement('div');gs.className='kh-gs';
 for(const [g,rs] of Object.entries(groups)){if(!rs.length)continue;const d=document.createElement('div'),h=document.createElement('h4');d.className='kh-g';h.textContent=g;d.append(h,...rs);gs.append(d)}
 box.append(hd,gs);ov.replaceChildren(box);
 if(had)ov.querySelector(`button[data-id="${had}"]`)?.focus()}
function rebind(e){
 e.preventDefault();e.stopPropagation();
 if(e.key==='Escape'){listen=null;msg='';drawSheet();return}
 if(['Shift','Meta','Control','Alt','CapsLock'].includes(e.key))return;
 const a=ACTS.find(x=>x.id===listen),k=e.key;
 const taken=ACTS.find(x=>x!==a&&keyOf(x)===k);
 if(k.length!==1||e.metaKey||e.ctrlKey||e.altKey||FIXED.has(k))msg=`${k===' '?'Space':k} is kept for the views`;
 else if(PAPER[k.toLowerCase()]&&k.toLowerCase()!==a.k.toLowerCase())msg=`${k} is kept for the paper's ${PAPER[k.toLowerCase()]}`;
 else if(taken)msg=`${k} is taken by ${taken.n}`;
 else{if(k===a.k)delete over[a.id];else over[a.id]=k;put(over);msg=`${a.n}: ${k}`;listen=null}
 drawSheet()}

// ---------- hint mode: labels from the home row on what is clickable and in view, in the paper's frame too
const HOME='asdfghjkl',WIDE='asdfghjklqwertyuiopzxcvbnm';
function codes(n){if(n<=HOME.length)return [...HOME].slice(0,n);
 const al=n<=HOME.length*HOME.length?HOME:WIDE,out=[];for(const a of al)for(const b of al)out.push(a+b);return out.slice(0,n)}
function frames(){if(ov)return [[document,0,0]];const out=[[document,0,0]];
 for(const f of document.querySelectorAll('#page iframe,iframe.arx-hint')){let d=null;try{d=f.contentDocument}catch(e){}
  if(!d||!d.body||!shown(f))continue;const r=f.getBoundingClientRect();out.push([d,r.left+f.clientLeft,r.top+f.clientTop])}
 return out}
// clipped away by a scrolling or collapsed box around it (a folded form, a closed drawer)
function clipped(el,r){const w=el.ownerDocument.defaultView;
 for(let p=el.parentElement;p&&p!==el.ownerDocument.body;p=p.parentElement){const s=w.getComputedStyle(p);
  if(s.overflowX==='visible'&&s.overflowY==='visible')continue;const q=p.getBoundingClientRect();
  if(r.bottom<=q.top+1||r.top>=q.bottom-1||r.right<=q.left+1||r.left>=q.right-1)return true}
 return false}
function targets(){const W=innerWidth,H=innerHeight,seen=new Set(),out=[];
 for(const [d,ox,oy] of frames())for(const el of d.querySelectorAll(CLICKABLE)){
  if(el.disabled||el.closest('.kh-l,.kh-find,[inert],[aria-hidden=true]')||(ov?!el.closest('.kh-ov'):el.closest('.kh-ov'))||!shown(el))continue;
  if(el.getAttribute('tabindex')==='-1'&&el.tagName==='BUTTON')continue;  // kept off the keyboard on purpose (the tree's caret)
  const lr=[...el.getClientRects()].find(q=>q.width>2&&q.height>2);if(!lr)continue;
  const r={left:lr.left+ox,top:lr.top+oy,right:lr.right+ox,bottom:lr.bottom+oy,width:lr.width,height:lr.height};
  if(r.bottom<0||r.right<0||r.top>H||r.left>W||clipped(el,lr))continue;
  const x=Math.min(W-2,Math.max(1,r.left+Math.min(6,r.width/2))),y=Math.min(H-2,Math.max(1,r.top+Math.min(6,r.height/2)));
  if(d===document){const hit=document.elementFromPoint(x,y);if(hit&&!el.contains(hit)&&!hit.contains(el)&&!hit.closest('label')?.contains(el))continue}  // covered
  else{const hit=d.elementFromPoint(x-ox,y-oy),top=document.elementFromPoint(x,y);if(hit&&!el.contains(hit)&&!hit.contains(el)||top&&top.tagName!=='IFRAME')continue}
  const k=Math.round(r.left/4)+','+Math.round(r.top/4);if(seen.has(k))continue;seen.add(k);  // one label per spot
  out.push([el,r])}
 return out.filter(([el])=>!out.some(([o])=>o!==el&&el.contains(o)))}  // a row or card holding its own link: label the link
function hintMode(tab){
 endHints();const ts=targets().filter(([el])=>!tab||el.matches('a[href]'));if(!ts.length)return;
 const cs=codes(ts.length),layer=document.createElement('div');layer.className='kh-l';
 hm={tab,typed:'',list:ts.map(([el,r],i)=>{const b=document.createElement('b');b.textContent=cs[i];
  // beside the element, on its left, so its first words stay readable; inside its corner when there is no room
  const w=8*cs[i].length+7,left=r.left-w-3>=0?r.left-w-3:r.left,top=r.top+Math.min(r.height,22)/2-8;
  b.style.left=Math.max(0,Math.min(innerWidth-24,left))+'px';b.style.top=Math.max(0,Math.min(innerHeight-16,top))+'px';layer.append(b);
  return {el,s:sigOf(el),code:cs[i],b}}),layer};
 document.body.append(layer)}
function endHints(){if(hm){hm.layer.remove();hm=null}}
function hintKey(e){
 e.preventDefault();e.stopImmediatePropagation();
 if(e.key==='Escape'){endHints();return}
 if(e.key==='Backspace'){hm.typed=hm.typed.slice(0,-1)}
 else if(e.key.length===1&&/[a-z]/i.test(e.key))hm.typed+=e.key.toLowerCase();else return;
 const m=hm.list.filter(x=>x.code.startsWith(hm.typed));
 if(!m.length){endHints();return}
 for(const x of hm.list){const on=x.code.startsWith(hm.typed);x.b.classList.toggle('no',!on);
  if(on)x.b.innerHTML=`<u>${hm.typed}</u>${x.code.slice(hm.typed.length)}`}
 if(m.length===1&&m[0].code===hm.typed){let {el,s}=m[0];const tab=hm.tab;endHints();
  // the page re-rendered under the labels (Start does on every poll): the same control, found again
  if(!el.isConnected)el=[...el.ownerDocument.querySelectorAll(el.tagName)].find(x=>shown(x)&&sigOf(x)===s)||null;
  if(el)press(el,tab)}}
function press(el,tab){
 const it=items().find(x=>x===el||x.contains(el));if(it)ring(it,false,false);
 if(tab&&el.matches('a[href]')){open1(el.href);return}
 if(el.matches('input:not([type=checkbox]):not([type=radio]),textarea,select')){el.focus();return}
 el.click();if(el.matches('a[href],button')&&el.isConnected&&!it)try{el.focus({preventScroll:true})}catch(e){}}

// ---------- dispatch
const typing=t=>t&&t.closest&&t.closest('input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,select,[contenteditable=""],[contenteditable=true]')||t&&t.isContentEditable;
const mods=e=>e.metaKey||e.ctrlKey||e.altKey||e.isComposing;
const tgt=e=>(e.composedPath&&e.composedPath()[0])||e.target;
// capture: hint mode, the rebind listener, a pending g, the search box's Enter and Esc and the sheet's Tab come before
// any view's own keys
addEventListener('keydown',e=>{
 if(hm){hintKey(e);return}
 if(ov&&listen){rebind(e);return}
 const t=tgt(e);
 if(ov&&e.key==='Tab'){const bs=[...ov.querySelectorAll('button')];if(bs.length){e.preventDefault();const i=bs.indexOf(document.activeElement);bs[(i+(e.shiftKey?-1:1)+bs.length)%bs.length].focus()}return}
 if(mods(e))return;
 if(gw&&!typing(t)){used=true;gKey(e);return}
 const sb=t&&t.closest&&t.closest('input[type=search],.sl-q input,.arc-q input');
 if(sb&&(e.key==='Enter'||e.key==='Escape')){e.preventDefault();e.stopImmediatePropagation();sb.blur();
  if(e.key==='Enter'){const found=items().filter(x=>sb.compareDocumentPosition(x)&Node.DOCUMENT_POSITION_FOLLOWING);
   const r=found.find(x=>x.matches('tr,[data-q],.q-row,[data-item]'))||found[0];if(r)ring(r)}}},true);  // the first result
function key(e){
 if(hm){if(!e.defaultPrevented)hintKey(e);return}
 if(ov&&listen){rebind(e);return}
 if(mods(e))return;
 const t=tgt(e);if(typing(t))return;
 if(gw&&gKey(e))return;  // from the paper's frame, where the capture above does not see the key
 if(e.defaultPrevented)return;
 const k=e.key,stop=()=>{e.preventDefault();used=true};
 if(k==='Escape'){if(ov){closeSheet();return}if(fb){findClose();return}const m=[...document.querySelectorAll('.sh-pop,#shp')].at(-1);if(m){m.remove();return}
  if(findQ){findQ='';return}if(cur)ring(null);return}
 if(k.length===1&&RES.has(k.toLowerCase()))return;
 if(k==='g'&&!ACTS.some(a=>keyOf(a)==='g')){gw={t:Date.now(),d:''};stop();return}
 if(k==='Enter'){const f=focused(),a=document.activeElement;
  if(f&&(!a||a===document.body||a===f||a.tagName==='IFRAME')){open(f);stop()}return}
 if(k==='Backspace'){back();stop();return}
 const a=ACTS.find(x=>keyOf(x)===k);if(!a||!live(a))return;
 if(ov&&a.id!=='help'&&a.id!=='hints')closeSheet();
 stop();a.run()}
addEventListener('keydown',key);
// Tab (or a click with the keyboard) onto an item moves the ring there: the ring and the focus never disagree
document.addEventListener('focusin',e=>{if(ringing)return;const t=e.target;if(!t||t===document.body||!t.matches||!t.matches(':focus-visible'))return;
 if(t.closest('.kh-ov,.kh-find'))return;const it=items().find(x=>x===t||x.contains(t));if(it&&it!==cur)ring(it,false,false)});

// re-attach the ring and the sidebar hints after each dashboard render and on DOM changes (batched); a hint layer is
// stale once the page scrolls or changes under it
let tm=0;const later=()=>{if(!tm)tm=setTimeout(()=>{tm=0;reattach();navHints();ov&&!listen&&drawSheet()},40)};
new MutationObserver(ms=>{if(ms.some(m=>[...m.addedNodes].some(n=>n.nodeType===1&&!/^(kn|kh-ov|kh-l|kh-find)$/.test(n.className)&&!n.closest?.('.kh-ov,.kh-l,.kh-find'))))later()})
 .observe(document.documentElement,{childList:true,subtree:true});
if(typeof S!=='undefined')(S.afterRender=S.afterRender||[]).push(later);
// each place keeps its ring: back (h) on a list lands on the row you opened; within a view (a question to the next)
// the ring follows the selection
const MEMO='arx-kring';let memo={};try{memo=JSON.parse(sessionStorage.getItem(MEMO)||'{}')||{}}catch(e){}
const keep=()=>{try{sessionStorage.setItem(MEMO,JSON.stringify(memo))}catch(e){}};
let at=where(),atRoute=route();
const leave=()=>{if(used&&sig){memo[at]=sig;keep()}};
addEventListener('pagehide',leave);
addEventListener('hashchange',()=>{leave();const same=route()===atRoute;at=where();atRoute=route();
 document.querySelectorAll('.kf').forEach(x=>x.classList.remove('kf'));cur=null;idx=-1;endHints();findClose();findQ='';
 sig=used?memo[at]||null:null;wantSel=used&&(same||!sig)?Date.now():0;later()});
if(memo[at]){sig=memo[at];used=true}
addEventListener('scroll',endHints,{passive:true});addEventListener('resize',endHints);
later();
window.ARXK={key,focused,reserve:k=>RES.add(String(k).toLowerCase())};
})();
