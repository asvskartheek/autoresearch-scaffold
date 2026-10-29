'use strict';
// Keys, Vim-like and context-aware, shared by the dashboard and the paper reader. Controls carry no hints: the sidebar
// shows each page's keys, f labels what is on screen when asked, and ? lists what is live right now.
//   j / k        a focus ring down / up through the view's items (rows, cards, comment cards)
//   o, Enter     open the focused item            h, Backspace   back (the crumb above, else browser back)
//   g + letter   a page (g o Overview, g b Brief, g t Goals ...; g 1-9 another project)    gg / G   top / bottom
//   f / F        hint mode: a short home-row label on every visible control, link, card and pin; type it to press it
//                (F: a link opens in a new tab); Esc leaves
//   /            the view's search          c  comment on the focused item (none focused: comment mode)
//   r / x        reply in / resolve the open thread or the focused item's       n / N  next / previous thread
//   ?            the sheet: the keys live now (an action whose context is absent is not listed); click a key to rebind it
// Rebinds are per person, in localStorage `arx-keys` ({action: key}); a key that is taken, fixed or a view's own is refused.
// Never while typing, never with Cmd/Ctrl/Alt, never a key a view took first (defaultPrevented: the Brief's space, Enter,
// digits, arrows, [ ]) or one the page reserves (ARXK.reserve: the paper keeps B A D H P for its tools).
//   ARXK.key(e)  handle a keydown from elsewhere (the paper's iframe)     ARXK.focused()  the item under the ring
(()=>{
if(window.ARXK)return;
// pages: g + this letter (gg stays "top", so Goals is g t: targets)
const PAGES={overview:'o',learn:'b',workbench:'w',goals:'t',questions:'q',models:'m',hills:'h',papers:'p',slices:'s',archive:'a',memory:'y'};
const NAMES={o:'Overview',b:'Brief',w:'Workbench',t:'Goals',q:'Questions',m:'Models',h:'Hills',p:'Papers',s:'Slices',a:'Archive',y:'Memory'};
const ITEMS='tr.click,article.wb-job,a.wb-chip,.q-row,a.ov-goal,a.ov-task,#main details>summary,[data-item],#col .card';
const CLICKABLE='a[href],button,[role=button],[role=tab],[role=menuitem],[role=switch],[role=checkbox],[role=radio],[role=option],summary,input:not([type=hidden]),select,textarea,tr.click,[onclick],.cm-pin,'+ITEMS;
// keys no action may take: fixed ones (Esc, Enter, Backspace, the g prefix) and the views' own (the Brief's)
const FIXED=new Set(['Escape','Enter','Backspace','Tab','g',' ','[',']','+','-','=','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','1','2','3','4','5','6','7','8','9','0']);
const css=`.kf{outline:2px solid var(--accent,var(--ring,#1b6c80))!important;outline-offset:2px;border-radius:4px}
tr.kf{outline-offset:-2px}
.kn{flex:none;margin-left:auto;padding-left:8px;font:500 10px/1 var(--mono,ui-monospace,Menlo,monospace);color:var(--faint,#8a9097);opacity:.7;letter-spacing:.06em;white-space:nowrap}
.count+.kn{margin-left:6px;padding-left:0}
@media (hover:none) and (pointer:coarse){.kn{display:none}}
.kh-ov{position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;background:color-mix(in srgb,#000 30%,transparent)}
.kh-ov>div{width:min(540px,calc(100vw - 32px));max-height:84vh;overflow:auto;padding:14px 16px;border-radius:10px;
background:var(--surface,var(--background,#fff));color:var(--text,var(--foreground,#131416));border:1px solid var(--border,#e3e7eb);
display:grid;grid-template-columns:1fr 1fr;gap:4px 22px;font:13px/1.45 var(--font,system-ui,sans-serif)}
.kh-ov span{display:flex;align-items:center;gap:10px;min-width:0}.kh-ov i{font-style:normal;color:var(--muted,var(--muted-fg,#5b6168));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kh-ov kbd{all:unset;flex:none;min-width:50px;font:500 11px/20px var(--mono,ui-monospace,Menlo,monospace);color:var(--text,var(--foreground,#131416))}
.kh-ov button{all:unset;flex:none;min-width:42px;padding:0 4px;border-radius:4px;cursor:pointer;font:500 11px/20px var(--mono,ui-monospace,Menlo,monospace);
color:var(--text,var(--foreground,#131416));box-shadow:inset 0 0 0 1px var(--border,#e3e7eb)}
.kh-ov button:hover,.kh-ov button.on{box-shadow:inset 0 0 0 1px var(--accent,var(--ring,#1b6c80))}
.kh-ov .kh-x{grid-column:1/-1;font-size:12px;color:var(--muted,var(--muted-fg,#5b6168));min-height:18px}
.kh-ov .kh-x a{color:inherit;text-decoration:underline;cursor:pointer;margin-left:6px}
@media (max-width:480px){.kh-ov>div{grid-template-columns:1fr}}
.kh-l{position:fixed;inset:0;z-index:2147483001;pointer-events:none}
.kh-l b{position:absolute;padding:0 3px;border-radius:3px;font:600 11px/15px var(--mono,ui-monospace,Menlo,monospace);text-transform:uppercase;
background:var(--text,var(--foreground,#131416));color:var(--surface,var(--background,#fff));box-shadow:0 1px 2px rgba(0,0,0,.25);white-space:nowrap}
.kh-l b u{text-decoration:none;opacity:.45}.kh-l b.no{display:none}`;
const st=document.createElement('style');st.textContent=css;(document.head||document.documentElement).append(st);

const RES=new Set();let cur=null,sig=null,idx=-1,gWait=0,ov=null,hm=null,listen=null,msg='';
const get=()=>{try{return JSON.parse(localStorage.getItem('arx-keys')||'{}')||{}}catch(e){return {}}};
const put=o=>{try{localStorage.setItem('arx-keys',JSON.stringify(o))}catch(e){}};
let over=get();addEventListener('storage',e=>{if(e.key==='arx-keys')over=get()});
const shown=el=>el.getClientRects().length>0&&!el.closest('[hidden]');
const main=()=>document.querySelector('#main')||document.querySelector('#root')||document.body;
const topEdge=()=>(document.querySelector('#top,.bar')?.getBoundingClientRect().bottom||0)+8;
const route=()=>(location.hash.slice(1)||'overview').split('/')[0];
function items(){
 const m=main(),all=[...document.querySelectorAll(ITEMS)].filter(el=>shown(el)&&(m.contains(el)||el.closest('#col')));
 return all.filter(el=>!all.some(o=>o!==el&&o.contains(el)))}  // the outermost item only
// an item's signature: what it links to, else its first words; keeps the ring on the same item across re-renders
const sigOf=el=>(el.matches('a[href]')?el:el.querySelector('a[href]'))?.getAttribute('href')||el.getAttribute('onclick')||el.dataset.id||(el.textContent||'').replace(/\s+/g,' ').trim().slice(0,60);
function ring(el,scroll=true){
 document.querySelectorAll('.kf').forEach(x=>x!==el&&x.classList.remove('kf'));
 cur=el||null;sig=el?sigOf(el):null;if(!el){idx=-1;return}
 el.classList.add('kf');idx=items().indexOf(el);
 if(scroll){const r=el.getBoundingClientRect(),top=topEdge();
  if(r.top<top)scrollBy({top:r.top-top});else if(r.bottom>innerHeight-8)scrollBy({top:r.bottom-innerHeight+8})}}
// after a render the old node is gone: find the same item again, else the one at the same place
function reattach(){if(!sig)return;if(cur&&cur.isConnected&&cur.classList.contains('kf'))return;
 const its=items(),el=its.find(x=>sigOf(x)===sig)||(idx>=0&&its.length?its[Math.min(idx,its.length-1)]:null);
 if(el)ring(el,false);else{cur=null;sig=null;idx=-1}}
const focused=()=>{reattach();return cur&&cur.isConnected?cur:null};
const firstBelow=its=>{const t=topEdge(),k=its.findIndex(x=>x.getBoundingClientRect().bottom>t);return k<0?0:k};
function move(d){const its=items();if(!its.length){scrollBy({top:d*80});return}
 reattach();const i=cur?its.indexOf(cur):-1;ring(its[i<0?(d>0?firstBelow(its):its.length-1):Math.max(0,Math.min(its.length-1,i+d))])}
function open(el){const a=el.matches('a[href],button,summary,tr.click,[onclick]')?el:el.querySelector('a[href],button');if(a)a.click()}
const crumbUp=()=>[...document.querySelectorAll('#top .crumbs a[href],.bar .ttl a.crumb')].at(-1);
function back(){const c=crumbUp();if(c){c.click();return}history.back()}
const search=()=>[...main().querySelectorAll('input[type=search],.sl-q input,.arc-q input')].find(shown);
function pages(){const out=new Map(),extra=[];let d=1;
 for(const a of document.querySelectorAll('aside#nav a.nav,#rail a[href]')){const href=a.getAttribute('href')||'';
  if(a.classList.contains('proj')){if(!a.classList.contains('on')&&d<10)out.set(String(d++),a);continue}
  const r=(href.split('#')[1]||'').split('/')[0],k=PAGES[r];if(k){if(!out.has(k))out.set(k,a)}else if(r)extra.push(a)}
 // a page this file does not know yet takes the first free letter of its name
 for(const a of extra){const k=[...label(a).toLowerCase()].find(c=>/[a-z]/.test(c)&&c!=='g'&&!out.has(c)&&!Object.values(PAGES).includes(c));if(k)out.set(k,a)}
 return out}
// the sidebar shows each page's keys, quietly, after its label
function navHints(){const nav=document.querySelector('aside#nav');if(!nav)return;
 for(const [k,a] of pages()){if(!nav.contains(a))continue;let n=a.querySelector(':scope>.kn');
  if(!n){n=document.createElement('span');n.className='kn';n.setAttribute('aria-hidden','true');a.append(n)}
  if(n.textContent!=='g '+k)n.textContent='g '+k}}
const C=()=>window.ARXC;
const pagerBtn=s=>{const b=document.querySelector(s);return b&&shown(b)&&!b.disabled?b:null};

// ---------- actions: a default key, a label, when it is live, what it does. Rebindable by id.
const ACTS=[
 {id:'down',k:'j',l:()=>items().length?'Next item':'Scroll down',run:()=>move(1)},
 {id:'up',k:'k',l:()=>items().length?'Previous item':'Scroll up',run:()=>move(-1)},
 {id:'open',k:'o',l:()=>'Open '+itemName(),when:()=>!!focused(),run:()=>open(cur)},
 {id:'back',k:'h',l:()=>'Back',run:back},
 {id:'bottom',k:'G',l:()=>'Bottom',run:()=>{scrollTo({top:document.documentElement.scrollHeight});const its=items();its.length&&ring(its.at(-1),false)}},
 {id:'hints',k:'f',l:()=>'Press anything on screen',run:()=>hintMode(false)},
 {id:'hintsTab',k:'F',l:()=>'Open a link in a new tab',run:()=>hintMode(true)},
 {id:'search',k:'/',l:()=>'Search',when:()=>!!search(),run:()=>{const s=search();s.focus();s.select?.()}},
 {id:'comment',k:'c',l:()=>focused()?'Comment on '+itemName():C()&&C().mode()?'Leave comment mode':'Comment mode',when:()=>!!C(),run:()=>C().comment(focused())},
 {id:'reply',k:'r',l:()=>'Reply in the thread',when:()=>!!C()&&C().has(focused()),run:()=>C().reply(focused())},
 {id:'resolve',k:'x',l:()=>'Resolve the thread',when:()=>!!C()&&C().has(focused()),run:()=>C().resolve(focused())},
 {id:'next',k:'n',l:()=>'Next thread',when:()=>C()?C().count()>0:!!pagerBtn('#next'),run:()=>C()?C().step(1):pagerBtn('#next').click()},
 {id:'prev',k:'N',l:()=>'Previous thread',when:()=>C()?C().count()>0:!!pagerBtn('#prev'),run:()=>C()?C().step(-1):pagerBtn('#prev').click()},
 {id:'help',k:'?',l:()=>'Keys',run:()=>sheet()}];
const keyOf=a=>over[a.id]||a.k;
const live=a=>!a.when||a.when();
const itemName=()=>{const r=route();return {workbench:'the task',archive:'the task',models:'the model',hills:'the hill',goals:'the goal',papers:'the paper',questions:'the question',slices:'the slice'}[r]||'it'};
// the keys a view keeps for itself, listed in the sheet but never handled here
function own(){const r=[];
 if(route()==='learn')r.push(['space','Check, next card'],['1 – 5','Pick an answer'],['← →','Move the guess'],['[ ]','Previous, next card']);
 if(route()==='hill')r.push(['← →','Previous, next example']);
 if(RES.has('b'))r.push(['B A D H','Draw a comment'],['⌘⌥M','New comment']);
 return r}

// ---------- the sheet: what is live now; click a key, then press the new one
function sheet(){
 if(ov){ov.remove();ov=null;listen=null;msg='';return}
 ov=document.createElement('div');ov.className='kh-ov';ov.onclick=e=>{if(e.target===ov){ov.remove();ov=null;listen=null;msg=''}};
 document.body.append(ov);drawSheet()}
function drawSheet(){if(!ov)return;
 const acts=ACTS.filter(a=>live(a)&&!RES.has(keyOf(a).toLowerCase()));
 const fixed=[['Esc','Close'],['gg','Top'],...own(),...[...pages()].filter(([k])=>!/^\d$/.test(k)).map(([k,a])=>['g '+k,NAMES[k]||label(a)]),...([...pages().keys()].some(k=>/^\d$/.test(k))?[['g 1 – 9','Another project']]:[])];
 const box=document.createElement('div');
 for(const a of acts){const s=document.createElement('span'),b=document.createElement('button');
  b.textContent=listen===a.id?'…':keyOf(a);b.title='Change';b.className=listen===a.id?'on':'';
  b.onclick=e=>{e.stopPropagation();listen=listen===a.id?null:a.id;msg=listen?'Press the new key':'';drawSheet()};
  const i=document.createElement('i');i.textContent=a.l();s.append(b,i);box.append(s)}
 for(const [k,l] of fixed){const s=document.createElement('span'),kb=document.createElement('kbd'),i=document.createElement('i');kb.textContent=k;i.textContent=l;s.append(kb,i);box.append(s)}
 const x=document.createElement('div');x.className='kh-x';x.textContent=msg;
 if(Object.keys(over).length){const r=document.createElement('a');r.textContent='Reset keys';r.onclick=e=>{e.stopPropagation();over={};put(over);msg='';drawSheet()};x.append(r)}
 box.append(x);ov.replaceChildren(box)}
const label=a=>{const c=a.cloneNode(true);c.querySelectorAll('.count,.kn,.pdot').forEach(x=>x.remove());return (c.textContent||a.title||'').replace(/\s+/g,' ').trim()};
function rebind(e){
 e.preventDefault();e.stopPropagation();
 if(e.key==='Escape'){listen=null;msg='';drawSheet();return}
 if(['Shift','Meta','Control','Alt','CapsLock'].includes(e.key))return;
 const a=ACTS.find(x=>x.id===listen),k=e.key;
 const taken=ACTS.find(x=>x!==a&&keyOf(x)===k);
 if(k.length!==1||e.metaKey||e.ctrlKey||e.altKey||FIXED.has(k)||RES.has(k.toLowerCase()))msg=`${k===' '?'Space':k} is kept for the view`;
 else if(taken)msg=`${k} is taken by ${taken.l()}`;
 else{if(k===a.k)delete over[a.id];else over[a.id]=k;put(over);msg=`${a.l()}: ${k}`;listen=null}
 drawSheet()}

// ---------- hint mode: labels from the home row on what is clickable and in view
const HOME='asdfghjkl',WIDE='asdfghjklqwertyuiopzxcvbnm';
function codes(n){if(n<=HOME.length)return [...HOME].slice(0,n);
 const al=n<=HOME.length*HOME.length?HOME:WIDE,out=[];for(const a of al)for(const b of al)out.push(a+b);return out.slice(0,n)}
function targets(){const W=innerWidth,H=innerHeight,seen=new Set(),out=[];
 for(const el of document.querySelectorAll(CLICKABLE)){
  if(el.disabled||el.closest('.kh-ov,.kh-l,[inert],[aria-hidden=true]')||!shown(el))continue;
  const r=[...el.getClientRects()].find(q=>q.width>2&&q.height>2);if(!r||r.bottom<0||r.right<0||r.top>H||r.left>W)continue;
  const x=Math.min(W-2,Math.max(1,r.left+Math.min(6,r.width/2))),y=Math.min(H-2,Math.max(1,r.top+Math.min(6,r.height/2)));
  const hit=document.elementFromPoint(x,y);if(hit&&!el.contains(hit)&&!hit.contains(el)&&!hit.closest('label')?.contains(el))continue;  // covered
  const k=Math.round(r.left/4)+','+Math.round(r.top/4);if(seen.has(k))continue;seen.add(k);  // one label per spot
  out.push([el,r])}
 return out.filter(([el])=>!out.some(([o])=>o!==el&&el.contains(o)))}  // a row or card holding its own link: label the link
function hintMode(tab){
 endHints();const ts=targets().filter(([el])=>!tab||el.matches('a[href]'));if(!ts.length)return;
 const cs=codes(ts.length),layer=document.createElement('div');layer.className='kh-l';
 hm={tab,typed:'',list:ts.map(([el,r],i)=>{const b=document.createElement('b');b.textContent=cs[i];
  b.style.left=Math.max(0,Math.min(innerWidth-24,r.left-4))+'px';b.style.top=Math.max(0,Math.min(innerHeight-16,r.top-6))+'px';layer.append(b);return {el,code:cs[i],b}}),layer};
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
 if(m.length===1&&m[0].code===hm.typed){const {el}=m[0],tab=hm.tab;endHints();press(el,tab)}}
function press(el,tab){
 const it=items().find(x=>x===el||x.contains(el));if(it)ring(it,false);
 if(tab&&el.matches('a[href]')){open1(el.href);return}
 if(el.matches('input:not([type=checkbox]):not([type=radio]),textarea,select')){el.focus();return}
 el.click()}
const open1=u=>{const w=window.open(u,'_blank','noopener');if(w)w.opener=null};

// ---------- dispatch
const typing=t=>t&&t.closest&&t.closest('input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,select,[contenteditable=""],[contenteditable=true]')||t&&t.isContentEditable;
// capture: hint mode and the rebind listener take every key before any view does
addEventListener('keydown',e=>{if(hm)hintKey(e);else if(ov&&listen)rebind(e)},true);
function key(e){
 if(hm){if(!e.defaultPrevented)hintKey(e);return}
 if(ov&&listen){rebind(e);return}
 if(e.defaultPrevented||e.metaKey||e.ctrlKey||e.altKey||e.isComposing)return;
 if(typing((e.composedPath&&e.composedPath()[0])||e.target))return;
 const k=e.key,stop=()=>e.preventDefault();
 if(k==='Escape'){if(ov){sheet();return}const m=[...document.querySelectorAll('.sh-pop,#shp')].at(-1);if(m){m.remove();return}if(cur)ring(null);return}
 if(gWait&&Date.now()-gWait<1500){gWait=0;
  if(k==='g'){scrollTo({top:0});const its=items();its.length&&ring(its[0],false);stop();return}
  const a=pages().get(k.toLowerCase());if(a){stop();ov&&sheet();a.click()}return}
 gWait=0;
 if(k.length===1&&RES.has(k.toLowerCase()))return;
 if(k==='g'&&!ACTS.some(a=>keyOf(a)==='g')){gWait=Date.now();stop();return}
 if(k==='Enter'){if(focused()&&!/^(A|BUTTON|SUMMARY|INPUT)$/.test(document.activeElement?.tagName)){open(cur);stop()}return}
 if(k==='Backspace'){back();stop();return}
 const a=ACTS.find(x=>keyOf(x)===k);if(!a||!live(a))return;
 if(ov&&a.id!=='help'){ov.remove();ov=null}
 stop();a.run()}
addEventListener('keydown',key);

// re-attach the ring and the sidebar hints after each dashboard render and on DOM changes (batched); a hint layer is
// stale once the page scrolls or changes under it
let tm=0;const later=()=>{if(!tm)tm=setTimeout(()=>{tm=0;reattach();navHints();ov&&!listen&&drawSheet()},40)};
new MutationObserver(ms=>{if(ms.some(m=>[...m.addedNodes].some(n=>n.nodeType===1&&!/^(kn|kh-ov|kh-l)$/.test(n.className)&&!n.closest?.('.kh-ov,.kh-l'))))later()})
 .observe(document.documentElement,{childList:true,subtree:true});
if(typeof S!=='undefined')(S.afterRender=S.afterRender||[]).push(later);
addEventListener('hashchange',()=>{ring(null);endHints()});
addEventListener('scroll',endHints,{passive:true});addEventListener('resize',endHints);
later();
window.ARXK={key,focused,reserve:k=>RES.add(String(k).toLowerCase())};
})();
