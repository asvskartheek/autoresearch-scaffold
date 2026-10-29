'use strict';
// The element picker (window.ARXPICK), shared by the dashboard and the paper reader (paper.html loads this file too),
// like a browser inspector: the element under the pointer gets an outline and a tag naming it ("bar · Champion 1224").
// It picks the smallest meaningful element (a bar, a tick, a chart, a row, a tile, a cell, a paragraph), never a wrapper
// that only holds one. ] or Alt+wheel up: its parent; [ or Alt+wheel down: back to the child. j/k (or the arrows): the
// next / previous sibling (past the last, the parent's). Enter or a click picks; Esc leaves. Touch: tap to show, tap
// again to pick.
//   const p = ARXPICK({doc, off, root, skip, pick, exit})   doc(): the document the elements live in; off(): its
//   viewport's top-left in this window; root(): nothing above it is picked; skip(el): elements never picked;
//   pick(el): the chosen one; exit(): Esc. p.on(el?) / p.off() / p.point(x, y) / p.tap(x, y, touch) / p.wheel(dy) /
//   p.key(e) -> handled / p.cur()          ARXPICK.kind(el), ARXPICK.text(el), ARXPICK.path(from, el)
(()=>{
if(window.ARXPICK)return;
// the element's text as it reads on screen: text nodes in different elements that sit apart get a space between them
// ("+1" and "90% CI" are two spans with a margin, never "+190% CI"); hidden text is skipped
function textOf(el,max=90){const d=el.ownerDocument;let out='',pr=null,pe=null,n=0;const w=d.createTreeWalker(el,NodeFilter.SHOW_TEXT);let t;
 while((t=w.nextNode())&&n++<400&&out.length<max+40){const s=t.nodeValue;if(t.parentElement?.closest('script,style,noscript'))continue;
  if(!s.trim()){if(out&&!/\s$/.test(out))out+=' ';continue}
  const rg=d.createRange();rg.selectNodeContents(t);const rs=rg.getClientRects();if(!rs.length&&el.getClientRects().length)continue;
  const r0=rs[0],rl=rs[rs.length-1];
  if(pr&&r0&&t.parentElement!==pe&&!/\s$/.test(out)&&!/^\s/.test(s)&&(r0.left-pr.right>1.5||Math.abs(r0.top-pr.top)>4))out+=' ';
  out+=s;pr=rl||pr;pe=t.parentElement}
 return out.replace(/\s+/g,' ').trim().slice(0,max)}
const SVGK=/^(rect|circle|ellipse|line|polyline|polygon|path|text|image|use)$/;
const INLINE=/^(span|b|i|em|strong|small|sub|sup|u|s|abbr|time|kbd|var|q|cite|tspan|br|wbr|font)$/;
const SEM=/^(tr|td|th|li|p|h[1-6]|a|button|img|canvas|svg|table|figure|figcaption|input|select|textarea|summary|blockquote|pre|dt|dd|caption|video|iframe|label|code|mark)$/;
const NAMED=/(^|[\s_-])(tick|bar|tile|chip|pill|badge|tag|card|row|cell|dot|seg|stat|kpi|node|step|rung|track|lane)s?($|[\s_-])/;
const isSvg=el=>el.namespaceURI==='http://www.w3.org/2000/svg';
const cls=el=>(el.getAttribute('class')||'').toLowerCase();
const ownText=el=>[...el.childNodes].some(n=>n.nodeType===3&&n.nodeValue.trim());
function boxed(el){const s=el.ownerDocument.defaultView.getComputedStyle(el);
 const bg=s.backgroundColor,clear=!bg||bg==='transparent'||/rgba\(.*,\s*0\)$/.test(bg);
 return !clear||s.backgroundImage!=='none'||parseFloat(s.borderTopWidth)+parseFloat(s.borderLeftWidth)+parseFloat(s.borderBottomWidth)>0&&s.borderTopStyle+s.borderLeftStyle+s.borderBottomStyle!=='nonenonenone'||s.boxShadow!=='none'}
const area=r=>r.width*r.height;
const same=(a,b)=>Math.abs(a.left-b.left)<1.5&&Math.abs(a.top-b.top)<1.5&&Math.abs(a.right-b.right)<1.5&&Math.abs(a.bottom-b.bottom)<1.5;
// is el something a person would point at? (a wrapper, a bare inline span or a chart's background rect is not)
function meaningful(el){
 if(!el||el.nodeType!==1)return false;const t=el.localName,r=el.getBoundingClientRect();if(r.width<1&&r.height<1)return false;
 if(isSvg(el)){if(t==='svg')return true;
  if(SVGK.test(t)){if(t==='tspan')return false;const svg=el.ownerSVGElement;if(t==='rect'&&svg){const sr=svg.getBoundingClientRect();if(area(r)>.8*area(sr))return false}  // a chart's background
   return true}
  return t==='g'&&!!(el.querySelector(':scope>title')||el.getAttribute('aria-label')||[...el.attributes].some(a=>a.name.startsWith('data-')))}
 const s=el.ownerDocument.defaultView.getComputedStyle(el);if(s.display==='contents'||s.visibility==='hidden')return false;
 if(SEM.test(t))return true;
 if(NAMED.test(cls(el))||el.getAttribute('role')||el.getAttribute('aria-label'))return true;
 if(INLINE.test(t))return boxed(el);  // a pill is a span with a background
 if(boxed(el))return true;
 if(ownText(el)){  // a line of text: itself, unless it is a number or a label inside a small boxed thing (a tile)
  for(let a=el.parentElement,i=0;a&&i<3;a=a.parentElement,i++){if(boxed(a)||NAMED.test(cls(a)))return area(a.getBoundingClientRect())>90000}
  return true}
 return false}
// what it is, in one word a person would use
function kind(el){const t=el.localName,c=cls(el),r=el.getBoundingClientRect();
 if(isSvg(el)){if(t==='svg')return 'chart';if(t==='rect')return /tick/.test(c)||Math.min(r.width,r.height)<=3?'tick':'bar';
  if(t==='circle'||t==='ellipse')return 'point';if(t==='line')return Math.max(r.width,r.height)<=14||/tick/.test(c)?'tick':'line';
  if(t==='text')return 'label';if(t==='path'||t==='polyline')return /area|band/.test(c)?'band':'line';return t==='g'?'group':'mark'}
 const m=NAMED.exec(c);if(m){const k=m[2];return {pill:'chip',badge:'chip',tag:'chip',dot:'point',seg:'bar',kpi:'tile',stat:'tile',rung:'step',lane:'track'}[k]||k}
 const T={tr:'row',td:'cell',th:'cell',li:'item',p:'paragraph',a:'link',button:'button',img:'image',canvas:'chart',table:'table',figure:'figure',
  figcaption:'caption',pre:'code',code:'code',blockquote:'quote',input:'field',select:'field',textarea:'field',summary:'heading',label:'label',dt:'term',dd:'value',caption:'caption',video:'video',iframe:'frame',mark:'mark'};
 if(T[t])return T[t];if(/^h[1-6]$/.test(t))return 'heading';if(el.getAttribute('role'))return el.getAttribute('role');
 if(boxed(el)||!ownText(el)&&!el.children.length){if(Math.min(r.width,r.height)<=3)return 'tick';if(r.height<=18&&r.width>=3*r.height||r.width<=18&&r.height>=3*r.width)return 'bar';
  if(Math.max(r.width,r.height)<=18)return 'point';return area(r)<=90000?'tile':'card'}
 return ownText(el)?'text':'box'}
// the words around an element with none of its own (a bar: its row's), for the tag
function around(el,max=60){for(let a=el.parentElement,i=0;a&&i<6&&a.localName!=='body';a=a.parentElement,i++){const t=a.getAttribute('title')||a.getAttribute('aria-label')||textOf(a,max);if(t)return t.replace(/\s+/g,' ').trim().slice(0,max)}return ''}
// its own words: a figure mark has none, so its <title>, label or data-* value
function text(el,max=90){
 const svgT=x=>x.querySelector?.(':scope>title')?.textContent;
 let s=isSvg(el)&&el.localName!=='text'&&el.localName!=='svg'?svgT(el)||(el.parentElement&&el.parentElement.localName==='g'?svgT(el.parentElement):''):'';
 s=s||(el.localName==='svg'?'':textOf(el,max))||el.getAttribute('aria-label')||el.getAttribute('title')||el.getAttribute('alt')||'';
 if(!s&&el.localName!=='svg')s=over(el);  // a bar with its label drawn on top of it ("Champion · 1224")
 if(!s)for(const a of el.attributes)if(/^data-(label|name|title|id|key|v|value)$/.test(a.name)&&a.value){s=a.value;break}
 if(!s&&el.localName==='svg')s=svgT(el)||el.getAttribute('aria-label')||textOf(el,max);
 return String(s).replace(/\s+/g,' ').trim().slice(0,max)}
// the words drawn over an element that has none (text nodes near it whose middle falls inside its box)
function over(el){const r=el.getBoundingClientRect(),d=el.ownerDocument,rg=d.createRange();if(r.width<2||r.height<2)return '';
 for(let a=el.parentElement,i=0;a&&i<3&&a.localName!=='body';a=a.parentElement,i++){const w=d.createTreeWalker(a,NodeFilter.SHOW_TEXT),out=[];let t,n=0;
  while((t=w.nextNode())&&n++<300){if(!t.nodeValue.trim())continue;rg.selectNodeContents(t);const q=rg.getBoundingClientRect(),cx=q.left+q.width/2,cy=q.top+q.height/2;
   if(q.width&&cx>=r.left&&cx<=r.right&&cy>=r.top&&cy<=r.bottom)out.push(t.nodeValue.trim())}
  if(out.length)return out.join(' ')}
 return ''}
// the path from one element down to another: tag:nth-of-type steps (SVG tags too)
function path(from,el){const parts=[];
 while(el&&el!==from){let i=1,s=el;while((s=s.previousElementSibling))if(s.localName===el.localName)i++;
  parts.unshift(el.localName+`:nth-of-type(${i})`);el=el.parentElement}
 return el===from?parts.join('>'):null}
const CSS0=`.pk-box{position:fixed;z-index:2147482000;pointer-events:none;border:2px solid var(--pk,#f59f00);border-radius:3px;box-shadow:0 0 0 1px rgba(0,0,0,.35);
background:color-mix(in srgb,var(--pk,#f59f00) 12%,transparent);display:none;transition:all .06s ease-out}
.pk-tag{position:fixed;z-index:2147482001;pointer-events:none;display:none;max-width:min(420px,calc(100vw - 16px));padding:2px 7px;border-radius:4px;
font:500 11px/18px var(--mono,ui-monospace,Menlo,monospace);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
background:var(--text,var(--foreground,#131416));color:var(--surface,var(--page,var(--background,#fff)));box-shadow:0 1px 3px rgba(0,0,0,.25)}
.pk-tag i{font-style:normal;opacity:.6}`;
const st=document.createElement('style');st.textContent=CSS0;(document.head||document.documentElement).append(st);
function ARXPICK(o){
 const top=document,box=top.createElement('div'),tag=top.createElement('div');box.className='pk-box';tag.className='pk-tag';
 let on=false,cur=null,trail=[],last=null,via='pointer',raf=0,acc=0,kept=null;
 const D=()=>o.doc(),R=()=>(o.root&&o.root())||D().body,O=()=>(o.off?o.off():{x:0,y:0});
 const ok=el=>el&&el.isConnected&&R().contains(el)&&el!==R()&&!(o.skip&&o.skip(el))&&meaningful(el);
 // the smallest meaningful element at a point (viewport px of this window)
 function leaf(x,y){const f=O(),d=D();for(const el of d.elementsFromPoint(x-f.x,y-f.y)){if(o.skip&&o.skip(el))continue;
   for(let a=el;a&&a!==R()&&R().contains(a);a=a.parentElement)if(ok(a))return a;return null}return null}
 // the next one up that looks different (a wrapper the same size as its child is skipped)
 function up(el){const r=el.getBoundingClientRect();for(let a=el.parentElement;a&&a!==R()&&R().contains(a);a=a.parentElement)if(ok(a)&&!same(a.getBoundingClientRect(),r))return a;return null}
 // the meaningful elements directly under p: no other meaningful element between them and p
 function kids(p){const out=[],walk=n=>{for(const c of n.children){if(o.skip&&o.skip(c))continue;if(ok(c)&&!same(c.getBoundingClientRect(),p.getBoundingClientRect()))out.push(c);else walk(c)}};walk(p);return out}
 function set(el,how){if(el===cur)return;cur=el||null;via=how||via;kept=el?path(D().documentElement,el):null;draw();if(el&&how==='key'){const r=el.getBoundingClientRect(),f=O(),y=r.top+f.y;
  if(y<60||y+Math.min(r.height,200)>innerHeight-60)el.scrollIntoView({block:'center',behavior:'instant'})}}
 function draw(){if(!on||!cur){box.style.display=tag.style.display='none';return}
  if(!cur.isConnected){let again=null;try{again=kept&&D().documentElement.querySelector(':scope>'+kept)}catch(e){}again=again||(last&&leaf(last.x,last.y));cur=null;if(again&&ok(again))cur=again;if(!cur){box.style.display=tag.style.display='none';return}}
  const r=cur.getBoundingClientRect(),f=O(),L=r.left+f.x,T=r.top+f.y;
  Object.assign(box.style,{display:'block',left:L-2+'px',top:T-2+'px',width:r.width+4+'px',height:r.height+4+'px'});
  const k=kind(cur),t=text(cur,48),c=t?'':around(cur);tag.innerHTML='';tag.append(k);if(t||c){const i=top.createElement('i');i.textContent=t?' · ':' · in ';tag.append(i,t||c)}
  tag.style.display='block';const tw=tag.offsetWidth,th=tag.offsetHeight;
  tag.style.left=Math.max(8,Math.min(innerWidth-tw-8,L-2))+'px';tag.style.top=(T-th-6>4?T-th-6:Math.min(innerHeight-th-4,T+r.height+6))+'px'}
 const loop=()=>{if(!on)return;draw();raf=requestAnimationFrame(loop)};
 function grow(){if(!cur)return;const p=up(cur);if(p){trail.push(cur);set(p,via)}}
 function shrink(){if(!cur)return;let c=trail.pop();if(!c||!cur.contains(c)){const ks=kids(cur);c=last&&ks.find(k=>{const r=k.getBoundingClientRect(),f=O();return last.x-f.x>=r.left&&last.x-f.x<=r.right&&last.y-f.y>=r.top&&last.y-f.y<=r.bottom})||ks[0]}if(c)set(c,via)}
 function sib(el,dir){const p=up(el)||R(),ks=kids(p);let i=ks.indexOf(el);if(i<0)i=ks.findIndex(k=>k.contains(el));
  if(i>=0&&ks[i+dir])return ks[i+dir];return p===R()?el:sib(p,dir)}
 function first(){const f=O(),x=innerWidth/2,ys=[innerHeight*.3,innerHeight*.5,120];for(const y of ys){const el=leaf(x,y);if(el)return el}return kids(R())[0]||null}
 const api={
  on(el){if(on){if(el&&ok(el))set(el,'key');return}on=true;top.body.append(box,tag);trail=[];cur=null;last=null;
   if(el){let a=el;while(a&&!ok(a))a=a.parentElement;if(a)set(a,'key')}loop()},
  off(){on=false;cancelAnimationFrame(raf);cur=null;trail=[];box.remove();tag.remove()},
  active:()=>on,cur:()=>cur&&cur.isConnected?cur:null,
  point(x,y){if(!on)return;last={x,y};const el=leaf(x,y);if(!el){if(via==='pointer')set(null,'pointer');return}
   if(cur&&cur.isConnected&&(cur===el||cur.contains(el)))return;  // still inside the grown pick: keep it
   trail=[];set(el,'pointer')},
  hide(){set(null,'pointer')},
  tap(x,y,touch){last={x,y};const el=leaf(x,y);if(!el)return;
   if(touch&&!(cur&&cur.isConnected&&(cur===el||cur.contains(el)))){trail=[];set(el,'pointer');return}
   if(!(cur&&cur.isConnected&&(cur===el||cur.contains(el))))set(el,'pointer');o.pick(cur)},
  wheel(dy){acc+=dy;if(Math.abs(acc)<40)return;acc<0?grow():shrink();acc=0},
  grow,shrink,
  key(e){if(!on||e.metaKey||e.ctrlKey)return false;const k=e.key;
   const go=f=>{e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();f();return true};
   if(k==='Escape')return go(()=>o.exit&&o.exit());
   if(k==='Enter')return go(()=>{if(!cur||!cur.isConnected)set(first(),'key');else o.pick(cur)});
   if(e.altKey)return false;
   if(k===']'||k==='ArrowRight')return go(()=>cur?grow():set(first(),'key'));
   if(k==='['||k==='ArrowLeft')return go(()=>cur?shrink():set(first(),'key'));
   if(k==='j'||k==='ArrowDown')return go(()=>{trail=[];set(cur?sib(cur,1):first(),'key')});
   if(k==='k'||k==='ArrowUp')return go(()=>{trail=[];set(cur?sib(cur,-1):first(),'key')});
   return false}};
 return api}
ARXPICK.kind=kind;ARXPICK.around=around;ARXPICK.text=text;ARXPICK.path=path;ARXPICK.textOf=textOf;ARXPICK.meaningful=meaningful;
window.ARXPICK=ARXPICK;
})();

// Comment on anything, on every view: press C (or the Comment button) to pick an element (above), or choose Box, Arrow,
// Pen or Highlight in the same toolbar to mark a region; or select text outside comment mode. Stored through /api/comments in .research/comments.jsonl (see
// autoresearch/comments.py); every comment and reply asks the agent (`arx answer`), which replies in the thread.
// Anchor: {route, key, rel, sel, text, quote, rx, ry, px, py, shape}. route = location.hash, so a comment stays on its
// view. key = the nearest stable element (an id, a unique data-* attribute, an entity link such as #task/<id>, or the
// card holding exactly one entity link); rel = the path from it; sel = a document cssPath, the last resort.
// shape = {tool, d, bw, bh, fit, ox, oy}: SVG path data in px from the anchor's top-left (page origin ox, oy when the
// anchor is gone). Pins and shapes re-place after every dashboard render (S.afterRender), scroll and resize.
(()=>{
if(typeof S==='undefined'||window.__arxComments)return;window.__arxComments=1;  // the paper reader loads this file for ARXPICK only
const API='api/comments';
const host=document.createElement('div');host.id='arx-comments';host.className='cm-host';
// the toolbar in comment mode: Pick (the main path), then the drawing tools for a region rather than an element
const DRAW=[['box','Box','B'],['arrow','Arrow','A'],['pen','Pen','D'],['highlight','Highlight','H']];
host.innerHTML=`<svg class="cm-shapes" xmlns="http://www.w3.org/2000/svg"></svg><div class="cm-layer"></div><div class="cm-pins"></div><div class="cm-pops"></div>
<div class="cm-list"></div><div class="cm-chip"><button class="cm-btn on cmt">Comment</button><button class="cm-btn ask">Ask</button></div>
<div class="cm-fab"><div class="cm-tools"><button data-tool="pick" class="pk" title="Pick an element (P)">Pick</button><span class="cm-sep"></span>${DRAW.map(([k,n,key])=>`<button data-tool="${k}" title="${n} (${key})">${n}</button>`).join('')}</div><button class="cm-btn cm-lst" title="Comments">0</button><button class="cm-btn cm-mode">Comment<b>C</b></button></div>`;
const $c=s=>host.querySelector(s),pinsEl=$c('.cm-pins'),pops=$c('.cm-pops'),list=$c('.cm-list'),chip=$c('.cm-chip'),layer=$c('.cm-layer'),shapesEl=$c('.cm-shapes'),tools=$c('.cm-tools');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let mode=false,tool='pick',all=[],open=null,hot=null,draw=null,pending=null,agentOn=true;
const here=()=>location.hash.slice(1)||'overview';
// the person (people.js): one id per browser, a name they can change; every event carries both. at(html, thread): the
// thread's author names count as mentionable too, so a mention made before a rename still reads as one
const P=window.ARXP,me=()=>P?P.me().name:'',myId=()=>P?P.me().id:'',setMe=n=>P&&P.setName(n);
const at=(html,c)=>P?P.at(html,c?c.messages.map(m=>m.author).filter(Boolean):undefined):html,face=(m)=>m.agent?'<span class="px-face sm" style="--pc:var(--accent,#3b82f6)">AI</span>':P?P.face(m.by||m.author,m.author,'sm'):'';
// a thread is for you when it @mentions you or you are in it, and someone else wrote since you last read it: reading it at
// its latest message takes it out of For you until someone writes again
// read here: the thread version (last_t) this browser has already marked seen, kept even when the POST failed (a snapshot,
// a dropped connection), so one version is posted once and never again
const readHere={};
const unread=c=>{const s=Math.max((c.seen||{})[myId()]||0,readHere[c.id]||0);return c.last_t>s&&c.messages.at(-1).by!==myId()};
const forMe=c=>!c.resolved&&unread(c)&&((c.mentions||[]).includes(myId())||(c.people||[]).includes(myId()));

/* ---------- anchors: stable keys first, cssPath last */
const ENT=/^#[a-z]+\/./;
const uniq=sel=>{try{return document.querySelectorAll(sel).length===1}catch(e){return false}};
const hrefs=el=>new Set([...(el.matches('a[href]')?[el]:[]),...el.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')).filter(x=>ENT.test(x)));
const CARD=/^(ARTICLE|LI|TR)$/;
const sig=el=>el.tagName.toLowerCase()+(el.classList[0]?'.'+CSS.escape(el.classList[0]):'');
function keyOf(el){let fall=null;
 // every candidate must resolve back to this very element: an entity link that appears twice on the view is not a key
 const ok=(k,a)=>keyNode(k)===a?[k,a]:null;
 for(let a=el;a&&a.nodeType===1&&a!==document.body&&a!==host;a=a.parentElement){let hit=null;
  if(a.id&&!/^\d/.test(a.id)&&uniq('#'+CSS.escape(a.id)))return [{sel:'#'+CSS.escape(a.id)},a];
  if(a.tagName==='A'&&ENT.test(a.getAttribute('href')||'')){const href=a.getAttribute('href');
   if((hit=ok({href},a)))return hit;
   const ls=[...document.querySelectorAll('a[href]')].filter(x=>x.getAttribute('href')===href&&!host.contains(x));
   fall=fall||[{href,n:ls.indexOf(a)},a]}
  for(const at of a.attributes){if(at.name.startsWith('data-')){const s=`[${at.name}="${CSS.escape(at.value)}"]`;if(uniq(s))return [{sel:s},a]}}
  const hs=hrefs(a);
  // a card: holds exactly one entity link and is a list item (article, li, tr, .card...) or sits among other entities
  if(hs.size===1&&a.parentElement&&(CARD.test(a.tagName)||/card|job|row|item/.test(a.getAttribute("class")||"")||hrefs(a.parentElement).size>1)&&(hit=ok({href:[...hs][0],card:sig(a)},a)))return hit;
 }
 return fall||[null,null]}
function relPath(from,el){const parts=[];
 while(el&&el!==from){let i=1,s=el;while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
  parts.unshift(el.tagName.toLowerCase()+`:nth-of-type(${i})`);el=el.parentElement}
 return el===from?parts.join('>'):null}
function cssPath(el){const parts=[];while(el&&el.nodeType===1&&el!==document.body){
 if(el.id&&!/^\d/.test(el.id)){parts.unshift('#'+CSS.escape(el.id));break}
 let i=1,s=el;while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
 parts.unshift(el.tagName.toLowerCase()+`:nth-of-type(${i})`);el=el.parentElement}
 return parts.join('>')}
const textOf=ARXPICK.textOf;
const label=el=>{const t=textOf(el)||(el.getAttribute?.('aria-label')||el.getAttribute?.('title')||'').trim();
 return (t||el.tagName.toLowerCase()).slice(0,90)};
function anchorFor(el){const [key,node]=keyOf(el);const rel=node?relPath(node,el):null;
 return key&&rel!=null?{key,rel,sel:cssPath(el),text:label(el)}:{sel:cssPath(el),text:label(el)}}
function keyNode(k){
 if(k.sel){try{return document.querySelector(k.sel)}catch(e){return null}}
 const ls=[...document.querySelectorAll('a[href]')].filter(a=>a.getAttribute('href')===k.href&&!host.contains(a));
 if(!k.card)return ls[k.n||0]||null;
 for(const l of ls){const c=l.closest(k.card);if(c)return c}
 return null}
function resolve(a){
 if(a.key){const n=keyNode(a.key);if(n){if(!a.rel)return n;try{return n.querySelector(':scope>'+a.rel)||n}catch(e){return n}}}
 let el=null;try{el=a.sel&&document.querySelector(a.sel)}catch(e){}
 if(a.text&&(!el||squash(el.textContent)!==squash(a.text))){  // the element moved or the anchor came from the CLI: find it by its text
  const same=[...(document.querySelector('#main')?.querySelectorAll(el?el.tagName.toLowerCase():'h1,h2,h3,a,b,th,td,span,p')||[])].find(x=>squash(x.textContent)===squash(a.text));if(same)return same}
 return el}
const target=(x,y)=>{host.style.display='none';const el=document.elementFromPoint(x,y);host.style.display='';return el};
const isPage=el=>!el||el===document.documentElement||el===document.body||el.id==='app';

/* ---------- mode, tools, keys */
// the picker (ARXPICK above): a click or Enter anchors a comment to exactly the element it outlines
const picker=ARXPICK({doc:()=>document,root:()=>document.body,exit:()=>setMode(false),pick:el=>pickEl(el),
 skip:el=>host.contains(el)||isPage(el)||el.id==='main'||el.closest?.('.pk-box,.pk-tag,.kh-ov,.kh-l')});
function setTool(t,el){tool=t;tools.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.tool===t));
 layer.classList.toggle('pick',t==='pick');if(mode&&t==='pick')picker.on(el);else picker.off()}
function setMode(on,el){mode=on;$c('.cm-mode').classList.toggle('on',on);tools.classList.toggle('on',on);layer.classList.toggle('on',on);
 if(on)setTool('pick',el);else{picker.off();cancelDraw()}}
$c('.cm-mode').onclick=()=>setMode(!mode);
tools.querySelectorAll('button').forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
setTool('pick');
// a picked element: its stable key (anchorFor), what it is, its own words and the card around it
function pickEl(el){const r=el.getBoundingClientRect(),k=ARXPICK.kind(el),t=ARXPICK.text(el);
 const a={...anchorFor(el),what:k,text:t||k,ctx:(t?'':ARXPICK.around(el,80))||ctxOf(el,t),rx:0,ry:0,px:r1(r.left+scrollX),py:r1(r.top+scrollY)};
 setMode(false);compose(a,Math.min(r.right,innerWidth-20),Math.max(r.top,8))}
$c('.cm-lst').onclick=()=>{list.classList.toggle('on');drawList()};
const KEYS={p:'pick',b:'box',a:'arrow',d:'pen',h:'highlight'};
addEventListener('keydown',e=>{const t=e.composedPath()[0]||{};if(/INPUT|TEXTAREA|SELECT/.test(t.tagName)||t.isContentEditable)return;
 if(mode&&tool==='pick'&&picker.key(e))return;  // j k [ ] arrows Enter Esc move and choose the pick, before keys.js
 if(e.metaKey||e.ctrlKey||e.altKey)return;const k=e.key.toLowerCase();
 if(k==='c'&&!window.ARXK){e.preventDefault();e.stopPropagation();setMode(!mode);return}  // with keys.js, C is its (rebindable) comment key
 if(mode&&KEYS[k]){e.preventDefault();e.stopPropagation();setTool(KEYS[k]);return}  // only in comment mode: views keep their keys
 if(e.key==='Escape'&&(mode||open||pops.firstChild)){if(draw){cancelDraw();return}setMode(false);closePop()}},true);

/* ---------- drawing layer: pointer capture, no text selection */
const r1=n=>Math.round(n*10)/10;
function shapePath(t,pts){const a=pts[0],b=pts[pts.length-1];
 if(t==='box')return `M${r1(a.x)} ${r1(a.y)}H${r1(b.x)}V${r1(b.y)}H${r1(a.x)}Z`;
 if(t==='arrow'){const ang=Math.atan2(b.y-a.y,b.x-a.x),L=Math.min(14,Math.hypot(b.x-a.x,b.y-a.y)*.5),w=.5;
  const hd=s=>`${r1(b.x-L*Math.cos(ang+s*w))} ${r1(b.y-L*Math.sin(ang+s*w))}`;
  return `M${r1(a.x)} ${r1(a.y)}L${r1(b.x)} ${r1(b.y)}M${hd(1)}L${r1(b.x)} ${r1(b.y)}L${hd(-1)}`}
 return 'M'+pts.map(p=>`${r1(p.x)} ${r1(p.y)}`).join('L')}
function bbox(pts,t){const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y),pad=t==='highlight'?9:2;
 return {left:Math.min(...xs)-pad,top:Math.min(...ys)-pad,right:Math.max(...xs)+pad,bottom:Math.max(...ys)+pad}}
function cancelDraw(){if(!draw)return;try{layer.releasePointerCapture(draw.id)}catch(e){}draw=null;document.documentElement.style.userSelect='';shapesEl.querySelector('.live')?.remove();drawPins()}
layer.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();
 getSelection()?.removeAllRanges();chip.style.display='none';layer.setPointerCapture(e.pointerId);
 document.documentElement.style.userSelect='none';
 draw={id:e.pointerId,tool,pts:[{x:e.clientX,y:e.clientY}],moved:false}});
layer.addEventListener('pointermove',e=>{e.preventDefault();
 if(!draw){if(tool==='pick')picker.point(e.clientX,e.clientY);return}
 const p={x:e.clientX,y:e.clientY},a=draw.pts[0],last=draw.pts[draw.pts.length-1];
 if(Math.hypot(p.x-a.x,p.y-a.y)>4)draw.moved=true;
 if(draw.tool==='pen'||draw.tool==='highlight'){if(Math.hypot(p.x-last.x,p.y-last.y)>=2)draw.pts.push(p)}else draw.pts=[a,p];
 if(draw.tool!=='pick')renderDraft()});
function renderDraft(){if(!draw)return;const d=shapePath(draw.tool,draw.pts);
 shapesEl.querySelector('.live')?.remove();shapesEl.insertAdjacentHTML('beforeend',`<g class="draft live"><path class="v ${draw.tool}" d="${d}"/></g>`)}
// what a shape is about: an arrow -> the element under its tip (kept at the same spot inside it, the tail at the same
// offset); a box or pen mark -> the element it encloses best (highest IoU), stretched with it; a highlight -> the text
// range under the stroke, found again by its text on every render
const under=(x,y)=>{host.style.display='none';const els=document.elementsFromPoint(x,y);host.style.display='';return els.filter(e=>!isPage(e)&&!host.contains(e))};
const iou=(r,B)=>{const ix=Math.max(0,Math.min(r.right,B.right)-Math.max(r.left,B.left)),iy=Math.max(0,Math.min(r.bottom,B.bottom)-Math.max(r.top,B.top)),i=ix*iy;
 return i/Math.max(1,r.width*r.height+(B.right-B.left)*(B.bottom-B.top)-i)};
function bestFit(B){const w=B.right-B.left,ht=B.bottom-B.top,cx=B.left+w/2,cy=B.top+ht/2,seen=new Set();let best=null,bs=0;
 for(const [x,y] of [[cx,cy],[B.left+w/4,cy],[B.right-w/4,cy],[cx,B.top+ht/4],[cx,B.bottom-ht/4]])
  for(let el of under(x,y))for(;el&&!isPage(el)&&!seen.has(el);el=el.parentElement){seen.add(el);const v=iou(el.getBoundingClientRect(),B);if(v>bs){bs=v;best=el}}
 return best}
// the nearest enclosing element whose text says more than the element's own (the card or row it sits in)
const ctxOf=(el,text)=>{for(let a=el.parentElement,i=0;a&&!isPage(a)&&i<8;a=a.parentElement,i++){if(a.id==='main')break;const t=textOf(a,80);if(t&&t!==text)return t}return undefined};
function caret(x,y){host.style.display='none';let r=null;
 try{if(document.caretRangeFromPoint)r=document.caretRangeFromPoint(x,y);else if(document.caretPositionFromPoint){const c=document.caretPositionFromPoint(x,y);if(c){r=document.createRange();r.setStart(c.offsetNode,c.offset)}}}catch(e){}
 host.style.display='';return r&&r.startContainer.nodeType===3&&!host.contains(r.startContainer)?r:null}
// the text node after / before n inside the same block (a caret in the gap between two spans lands at the end of the
// left one: the stroke starts at the next node, never on the last letter of the text before it)
const textStep=(n,fwd)=>{const w=document.createTreeWalker(n.parentElement?.closest('p,li,td,th,a,div,section,article,h1,h2,h3,h4')||document.body,NodeFilter.SHOW_TEXT);w.currentNode=n;
 for(let t;(t=fwd?w.nextNode():w.previousNode());)if(t.nodeValue.trim())return t;return null};
function strokeRange(pts){const xs=pts.map(p=>p.x);
 const a=caret(Math.min(...xs)+1,pts[xs.indexOf(Math.min(...xs))].y),b=caret(Math.max(...xs)-1,pts[xs.indexOf(Math.max(...xs))].y);if(!a||!b)return null;
 const rg=document.createRange();let s=[a.startContainer,a.startOffset],e=[b.startContainer,b.startOffset];
 if(a.compareBoundaryPoints(Range.START_TO_START,b)>0)[s,e]=[e,s];
 if(s[0]!==e[0]){let n;if(!s[0].nodeValue.slice(s[1]).trim()&&(n=textStep(s[0],true)))s=[n,0];
  if(!e[0].nodeValue.slice(0,e[1]).trim()&&(n=textStep(e[0],false)))e=[n,n.nodeValue.length]}
 const word=/[\w%.,+\u2212-]/;  // grow both ends to whole words
 while(s[1]>0&&word.test(s[0].nodeValue[s[1]-1]))s[1]--;while(e[1]<e[0].nodeValue.length&&word.test(e[0].nodeValue[e[1]]))e[1]++;
 rg.setStart(...s);rg.setEnd(...e);return String(rg).trim()?rg:null}
const squash=t=>String(t||'').replace(/\s+/g,'');
// two text nodes read as separate words when they sit in different elements and apart on screen (as in textOf)
const apart=(p,t)=>{if(p.parentElement===t.parentElement)return false;const r=document.createRange();r.selectNodeContents(p);const a=[...r.getClientRects()].at(-1);
 r.selectNodeContents(t);const b=r.getClientRects()[0];return !!(a&&b)&&(b.left-a.right>1.5||Math.abs(b.top-a.top)>4)};
// the root's text with whitespace folded; sep: a space between nodes that are apart. map[i] = [text node, offset]
function flatText(root,sep=true){const map=[];let flat='',prev=null;const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let t;
 while((t=w.nextNode())&&flat.length<200000){const v=t.nodeValue;
  if(sep&&prev&&flat&&!flat.endsWith(' ')&&v&&!/^\s/.test(v)&&apart(prev,t)){flat+=' ';map.push([t,0])}
  for(let i=0;i<v.length;i++){const ch=/\s/.test(v[i])?' ':v[i];if(ch===' '&&(!flat||flat.endsWith(' ')))continue;flat+=ch;map.push([t,i])}
  if(v.trim())prev=t}
 return [flat,map]}
function findRange(root,quote,qn=0){const q=String(quote||'').replace(/\s+/g,' ').trim();if(!root||!q)return null;
 for(const sep of [true,false]){const [flat,map]=flatText(root,sep);  // quotes saved before the separators: matched as they were
  let at=-1,from=0;for(let k=0;k<=qn;k++){at=flat.indexOf(q,from);if(at<0)break;from=at+1}if(at<0)continue;
  const [sn,so]=map[at],[en,eo]=map[at+q.length-1];const r=document.createRange();r.setStart(sn,so);r.setEnd(en,eo+1);return r}
 return null}
// a range's text exactly as findRange will look for it: the flat text of its element between the range's ends
function rangeText(el,rg){const [flat,map]=flatText(el);let i=-1,j=-1;
 map.forEach(([n,o],k)=>{const p=document.createRange();p.setStart(n,o);p.setEnd(n,Math.min(n.nodeValue.length,o+1));
  if(rg.compareBoundaryPoints(Range.START_TO_START,p)<=0&&rg.compareBoundaryPoints(Range.END_TO_END,p)>=0){if(i<0)i=k;j=k}});
 return i<0?String(rg).replace(/\s+/g,' ').trim():flat.slice(i,j+1).trim()}
function quoteAnchor(rg){  // a text range -> {anchor fields}: the element holding it, the quote and which occurrence it is
 let el=rg.commonAncestorContainer;if(el.nodeType!==1)el=el.parentElement;const quote=rangeText(el,rg).slice(0,500);
 let qn=0;for(let k=0;k<50;k++){const r=findRange(el,quote,k);if(!r)break;if(r.compareBoundaryPoints(Range.START_TO_START,rg)<=0)qn=k;else break}
 return {...anchorFor(el),quote,qn,ctx:ctxOf(el,label(el))}}
function finish(e){if(!draw||e.pointerId!==draw.id)return;e.preventDefault();e.stopPropagation();
 const d=draw;draw=null;try{layer.releasePointerCapture(e.pointerId)}catch(err){}document.documentElement.style.userSelect='';
 shapesEl.querySelector('.live')?.remove();
 const a=d.pts[0],b=d.pts[d.pts.length-1];
 if(d.tool==='pick'){picker.tap(a.x,a.y,e.pointerType!=='mouse');return}  // picks through pickEl
 if(!d.moved){const el=target(a.x,a.y);if(!el||isPage(el)){drawPins();return}  // a click with a drawing tool: a comment on that element
  const r=el.getBoundingClientRect();
  compose({...anchorFor(el),ctx:ctxOf(el,label(el)),rx:(a.x-r.left)/Math.max(1,r.width),ry:(a.y-r.top)/Math.max(1,r.height),px:a.x+scrollX,py:a.y+scrollY},a.x,a.y);
  setMode(false);return}
 const B=bbox(d.pts,d.tool),at={x:(B.right+B.left)/2,y:Math.min(B.bottom,innerHeight-20)};
 let an,shape;
 if(d.tool==='arrow'){  // the tip names the smallest element within 3 px of it (a tick, a bar end), not the card behind
  const area=e=>{const q=e.getBoundingClientRect();return q.width*q.height};
  const el=[[0,0],[0,-3],[0,3],[-3,0],[3,0]].map(([dx,dy])=>under(b.x+dx,b.y+dy)[0]).filter(Boolean).sort((x,y)=>area(x)-area(y))[0]||null,tail=under(a.x,a.y)[0];
  const r=el?el.getBoundingClientRect():{left:0,top:0,width:innerWidth,height:innerHeight};
  const tx=(b.x-r.left)/Math.max(1,r.width),ty=(b.y-r.top)/Math.max(1,r.height);
  shape={tool:'arrow',mode:'tip',d:shapePath('arrow',d.pts.map(p=>({x:p.x-b.x,y:p.y-b.y}))),tx:r1(tx*1e4)/1e4,ty:r1(ty*1e4)/1e4,
   ax:r1(a.x-b.x),ay:r1(a.y-b.y),bw:r1(r.width),bh:r1(r.height),ox:r1(b.x+scrollX),oy:r1(b.y+scrollY)};
  an=el?{...anchorFor(el),what:sig(el),ctx:ctxOf(el,label(el)),from:tail&&tail!==el&&!tail.contains(el)?label(tail).slice(0,80):undefined}:{sel:'',text:'page'};
  Object.assign(an,{rx:tx,ry:ty,px:b.x+scrollX,py:b.y+scrollY})}
 else{const rg=d.tool==='highlight'?strokeRange(d.pts):null;
  const el=rg?(rg.commonAncestorContainer.nodeType===1?rg.commonAncestorContainer:rg.commonAncestorContainer.parentElement):bestFit(B);
  const r=el?el.getBoundingClientRect():{left:0,top:0,width:innerWidth,height:innerHeight};
  const rel=d.pts.map(p=>({x:p.x-r.left,y:p.y-r.top}));
  shape={tool:d.tool,d:shapePath(d.tool,rel),bw:r1(r.width),bh:r1(r.height),fit:!rg&&!!el,ox:r1(r.left+scrollX),oy:r1(r.top+scrollY),
   bx:r1(B.left-r.left),by:r1(B.top-r.top)};
  if(d.tool==='box'&&el){const xs=[a.x,b.x],ys=[a.y,b.y];  // a box keeps its edges' px distance to the element's edges
   shape.ins=[Math.min(...xs)-r.left,Math.min(...ys)-r.top,Math.max(...xs)-r.right,Math.max(...ys)-r.bottom].map(r1)}
  if(rg){shape.mode='text';an=quoteAnchor(rg)}
  else an=el?{...anchorFor(el),what:sig(el),ctx:ctxOf(el,label(el))}:{sel:'',text:'page'};
  Object.assign(an,{rx:(a.x-r.left)/Math.max(1,r.width),ry:(a.y-r.top)/Math.max(1,r.height),px:a.x+scrollX,py:a.y+scrollY})}
 compose({...an,shape},Math.min(B.right,innerWidth-20),at.y);
 setMode(false)}
layer.addEventListener('pointerup',finish);layer.addEventListener('pointercancel',e=>{if(draw&&e.pointerId===draw.id)cancelDraw()});
layer.addEventListener('lostpointercapture',e=>{if(draw&&e.pointerId===draw.id)cancelDraw()});
for(const ev of['click','dblclick','contextmenu','selectstart','dragstart'])layer.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation()});
// the layer covers the page in comment mode; pass wheel scrolling through
// (Alt+wheel while picking: a bigger or smaller pick)
layer.addEventListener('wheel',e=>{e.preventDefault();if(tool==='pick'&&e.altKey){picker.wheel(e.deltaY);return}
 const re=()=>tool==='pick'&&picker.point(e.clientX,e.clientY);let el=target(e.clientX,e.clientY);
 while(el&&!isPage(el)){const s=getComputedStyle(el);if(/(auto|scroll)/.test(s.overflowY+s.overflowX)&&(el.scrollHeight>el.clientHeight||el.scrollWidth>el.clientWidth)){el.scrollBy(e.deltaX,e.deltaY);re();return}el=el.parentElement}
 scrollBy(e.deltaX,e.deltaY);re()},{passive:false});

/* ---------- selected text -> one chip next to it: Comment (anchored to the quoted range) or Ask (questions.js qAsk) */
document.addEventListener('mouseup',e=>{if(mode||host.contains(e.target))return;setTimeout(()=>{const s=getSelection();
 if(!s||s.isCollapsed||!String(s).trim()||host.contains(s.anchorNode)||/INPUT|TEXTAREA/.test(document.activeElement?.tagName||'')){chip.style.display='none';return}
 const rg=s.getRangeAt(0).cloneRange(),r=rg.getBoundingClientRect(),quote=String(s).trim();
 chip.querySelector('.ask').style.display=typeof window.qAsk==='function'?'':'none';
 Object.assign(chip.style,{display:'flex',left:Math.max(8,Math.min(innerWidth-170,r.left))+'px',top:Math.min(innerHeight-40,r.bottom+6)+'px'});
 chip.querySelector('.cmt').onclick=()=>{const an=quoteAnchor(rg),el=resolve(an)||document.body,er=el.getBoundingClientRect();
  getSelection()?.removeAllRanges();chip.style.display='none';
  compose({...an,rx:(r.left-er.left)/Math.max(1,er.width),ry:(r.top-er.top)/Math.max(1,er.height),px:r.left+scrollX,py:r.top+scrollY},r.right,r.bottom)};
 chip.querySelector('.ask').onclick=()=>{chip.style.display='none';getSelection()?.removeAllRanges();window.qAsk(quote.slice(0,500))}},0)});

/* ---------- reply bodies: text with links, plus one sanitised inline SVG */
const SVG_OK=new Set(['svg','g','path','rect','circle','line','text','polyline']);
const ATTR_OK=/^(viewbox|width|height|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|d|points|fill|stroke|stroke-width|stroke-dasharray|stroke-linecap|stroke-linejoin|opacity|fill-opacity|stroke-opacity|transform|font-size|font-weight|font-family|text-anchor|dominant-baseline|xmlns|preserveaspectratio)$/i;
function cleanSvg(src){const t=document.createElement('template');t.innerHTML=src;const svg=t.content.querySelector('svg');if(!svg)return '';
 const walk=el=>{for(const a of [...el.attributes])if(!ATTR_OK.test(a.name)||/url\s*\(|javascript:|expression|&#|\\/i.test(a.value))el.removeAttribute(a.name);
  for(const c of [...el.childNodes]){if(c.nodeType===3)continue;if(c.nodeType!==1||!SVG_OK.has(c.localName)){c.remove();continue}walk(c)}};
 walk(svg);return `<div class="cm-fig">${svg.outerHTML}</div>`}
const linky=s=>h(s).replace(/(https?:\/\/[^\s<]+[^\s<.,;:)])|(^|[\s(])(#[a-z]+(?:\/[^\s<]*[^\s<.,;:)])?)/g,(m,url,pre,hash)=>url?`<a href="${url}" target="_blank" rel="noopener">${url}</a>`:`${pre}<a href="${hash}">${/^#answer\//.test(hash)?'Open the full answer':hash}</a>`);  // a long answer: its own view
// the figure first, then the words
const rich=b=>{const parts=String(b||'').split(/(<svg[\s\S]*?<\/svg>)/i);
 return parts.filter((x,i)=>i%2).map(cleanSvg).join('')+linky(parts.filter((x,i)=>!(i%2)).join('').replace(/\n{3,}/g,'\n\n').trim())};
// after a figure is on screen: greys and black/white become theme colours (readable in dark mode), text never under 11 px
const NEUTRAL=v=>{if(!v||/none|currentcolor|transparent/i.test(v))return null;const c=document.createElement('canvas').getContext('2d');c.fillStyle='#010203';c.fillStyle=v;
 const m=/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(c.fillStyle);if(!m)return null;const [r,g,b]=m.slice(1).map(x=>parseInt(x,16)),mx=Math.max(r,g,b),mn=Math.min(r,g,b);
 if(mx-mn>48)return null;const l=(mx+mn)/510;return l<.3||l>.85?'currentColor':'var(--muted)'};
function fitFigs(root){root.querySelectorAll('.cm-fig svg').forEach(svg=>{
 if(!svg.getAttribute('viewBox')){const w=parseFloat(svg.getAttribute('width')),ht=parseFloat(svg.getAttribute('height'));if(w&&ht)svg.setAttribute('viewBox',`0 0 ${w} ${ht}`)}
 svg.removeAttribute('width');svg.removeAttribute('height');
 for(const el of svg.querySelectorAll('*'))for(const k of ['fill','stroke']){const t=NEUTRAL(el.getAttribute(k));if(t)el.style[k]=t}
 const vb=svg.viewBox.baseVal,sc=vb&&vb.width?svg.getBoundingClientRect().width/vb.width:1;if(!sc)return;
 for(const t of svg.querySelectorAll('text')){const fs=parseFloat(t.getAttribute('font-size')||getComputedStyle(t).fontSize)||12;if(fs*sc<11)t.setAttribute('font-size',r1(11/sc))}})}

/* ---------- compose and threads */
// clear of the buttons, and left of the open comment list when there is room (on a phone it sits on top of the list)
function place(p,x,y){let mx=innerWidth-p.offsetWidth-12;
 if(list.classList.contains('on')){const L=list.getBoundingClientRect().left-p.offsetWidth-12;if(L>=12)mx=Math.min(mx,L)}
 p.style.left=Math.max(12,Math.min(mx,x+14))+'px';p.style.top=Math.max(12,Math.min(innerHeight-p.offsetHeight-60,y+14))+'px'}
function closePop(){pops.innerHTML='';open=null;if(pending){pending=null;drawPins()}}
const focusLater=ta=>{ta.focus({preventScroll:true});setTimeout(()=>{ta.focus({preventScroll:true});requestAnimationFrame(()=>{if(document.activeElement!==ta)ta.focus({preventScroll:true})})},0)};
const nameField=()=>me()?'<span class="cm-sp"></span>':'<input class="cm-name cm-sp" placeholder="Your name" maxlength="60">';
// while a post is in flight: fields locked, the button says so; on failure the popover says it was not sent
function busy(p,on,label){p.dataset.busy=on?'1':'';p.querySelectorAll('textarea,input,button').forEach(b=>b.disabled=on);
 const go=p.querySelector('.go');if(on){go.dataset.label=go.textContent;go.textContent=label}else if(go.dataset.label)go.textContent=go.dataset.label}
function failed(p){busy(p,false);const e=p.querySelector('.cm-err')||p.insertBefore(Object.assign(document.createElement('div'),{className:'cm-err'}),p.querySelector('.cm-row'));e.textContent='Not sent. Try again.'}
function needText(ta){ta.classList.remove('need');void ta.offsetWidth;ta.classList.add('need');ta.focus({preventScroll:true})}
function takeName(p){const n=p.querySelector('.cm-name');if(!n)return me()||'you';const v=n.value.trim();if(v)setMe(v);return v||'you'}
// a picked element (the picker): a kind word in `what` (bar, row, tile) and no shape or quote
const picked=a=>!!a.what&&!a.shape&&!a.quote&&!a.what.includes('.');
const shapeName={box:'Box',arrow:'Arrow',pen:'Drawing',highlight:'Highlight'};
const anchorText=a=>{const bare=a.what&&a.text&&a.what.split('.')[0]===a.text;  // an element with no text of its own: name its card
 if(picked(a))return a.what+' · '+(bare?a.ctx?'in '+a.ctx:'':a.text);
 return a.quote?'“'+a.quote.slice(0,120)+'”':(a.shape?shapeName[a.shape.tool]+' on ':'')+(bare&&a.ctx?a.ctx:a.text||'page')};
function compose(a,x,y){closePop();a.route=here();a.vw=innerWidth;const p=document.createElement('div');p.className='cm-pop';
 p.innerHTML=`<div class="cm-anchor">${h(anchorText(a))}</div><textarea placeholder="Comment"></textarea><div class="cm-row">${nameField()}<button class="cm-sm x">Cancel</button><button class="cm-sm pri go" title="⌘↵">Comment</button></div>`;
 pops.append(p);place(p,x,y);const ta=p.querySelector('textarea');focusLater(ta);P&&P.complete(ta);
 if(a.shape||a.quote||picked(a)){pending=a;drawPins()}
 const send=async()=>{if(p.dataset.busy)return;const body=ta.value.trim();if(!body)return needText(ta);const author=takeName(p);busy(p,true,'Sending…');
  const ev=await post({kind:'comment',anchor:a,body,author});if(!ev||!ev.id)return p.isConnected&&failed(p);
  if(p.isConnected){closePop();thread(ev.id)}};  // closed with Esc while sending: the pin shows, the popover stays shut
 p.querySelector('.go').onclick=send;p.querySelector('.x').onclick=closePop;
 p.querySelectorAll('textarea,input').forEach(f=>f.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))send();if(e.key==='Escape')closePop()})}

const mine=()=>all.filter(t=>t.route===here());
const anchorEl=c=>resolve(c.anchor||{});
// where an anchor sits now: its element's box, the shape's transform and, for a quote, the text range
function where(a){const el=resolve(a),s=a.shape||null;let r=el&&el.getBoundingClientRect();if(r&&!r.width&&!r.height)r=null;
 const g={el,r,rg:null,tx:0,ty:0,sx:1,sy:1};
 if(a.quote&&el&&(!s||s.mode==='text')){const rg=findRange(el,a.quote,a.qn||0)||findRange(el,a.quote,0);if(rg&&rg.getClientRects().length)g.rg=rg}
 if(s){if(s.mode==='tip'){if(r){g.tx=r.left+s.tx*r.width;g.ty=r.top+s.ty*r.height}else{g.tx=s.ox-scrollX;g.ty=s.oy-scrollY}}
  else{g.tx=s.ox-scrollX;g.ty=s.oy-scrollY;if(r){g.tx=r.left;g.ty=r.top;if(s.fit){g.sx=r.width/Math.max(1,s.bw);g.sy=r.height/Math.max(1,s.bh)}}}}
 // the card reflowed (a row of tiles stacked on a phone): one scale for both axes, never a tall thin box
 if(s&&s.fit&&!s.ins&&Math.max(g.sx/g.sy,g.sy/g.sx)>1.6)g.sx=g.sy=Math.min(g.sx,g.sy);
 // an arrow whose tail would leave the screen is drawn shorter, still pointing at the same spot
 if(s&&s.mode==='tip'){const ex=g.tx+(s.ax||0),lim=ex<4?(g.tx-4)/-(s.ax||1):ex>innerWidth-4?(innerWidth-4-g.tx)/(s.ax||1):1;g.sx=g.sy=Math.max(.2,Math.min(1,lim))}
 if(s&&s.ins&&r)g.box=boxRect(s,r);
 return g}
// a box kept at its px distance from the element's edges; when the element shrank under it (a phone), the distances
// scale with the element instead; never wider than the screen
function boxRect(s,r){const [l,t,rr,b]=s.ins;let q=[r.left+l,r.top+t,r.right+rr,r.bottom+b];
 if(q[2]-q[0]<12||q[3]-q[1]<12){const kx=r.width/Math.max(1,s.bw),ky=r.height/Math.max(1,s.bh);q=[r.left+l*kx,r.top+t*ky,r.right+rr*kx,r.bottom+b*ky]}
 q[0]=Math.max(q[0],Math.min(4,r.left));q[2]=Math.min(q[2],Math.max(innerWidth-4,r.right));return q}
// a pin sits with its point on the corner of what it marks (a quote's first line, a shape's top-left, an arrow's tail)
// and its body up and to the left of that point, so it never covers the text itself (to the right only at the screen edge)
function pos(c){const a=c.anchor||{},g=where(a),s=a.shape;
 if(g.rg){const q=g.rg.getClientRects()[0];return [q.left,q.top]}
 if(s&&s.mode==='tip')return [g.tx+(s.ax||0)*g.sx,g.ty+(s.ay||0)*g.sy];
 if(g.box)return [g.box[0],g.box[1]];
 if(s&&s.bx!=null&&(g.r||s.mode!=='text'))return [g.tx+s.bx*g.sx,g.ty+s.by*g.sy];
 if(g.r)return g.r.height<=48&&g.r.width<=360?[g.r.left,g.r.top]:[g.r.left+(a.rx??.5)*g.r.width,g.r.top+(a.ry??.5)*g.r.height];  // a word or a line: its corner
 return a.px!=null?[a.px-scrollX,a.py-scrollY]:null}
function shapeSvg(a,cl,id){const s=a.shape,g=where(a),cls=`${cl}${id&&(id===hot||id===open)?' hot':''}`;
 if(picked(a)){if(!g.r)return '';const q=g.r;  // the picked element's outline, shown while its thread is hovered, open or being written
  return `<g class="${cls} pk" data-id="${h(id||'')}"><rect class="v pk" x="${r1(q.left-2)}" y="${r1(q.top-2)}" width="${r1(q.width+4)}" height="${r1(q.height+4)}" rx="3"/></g>`}
 if(g.rg){const rs=[...g.rg.getClientRects()].filter(q=>q.width>.5);
  return `<g class="${cls} q" data-id="${h(id||'')}">${rs.map(q=>`<rect class="v q" x="${r1(q.left)}" y="${r1(q.top)}" width="${r1(q.width)}" height="${r1(q.height)}" rx="2"/>`).join('')}</g>`}
 if(!s||!s.d)return '';const d=h(s.d),t=h(s.tool);
 if(g.box){const [l,t2,rr,b]=g.box,bd=`M${r1(l)} ${r1(t2)}H${r1(rr)}V${r1(b)}H${r1(l)}Z`;
  return `<g class="${cls}" data-id="${h(id||'')}"><path class="hit box" d="${bd}"/><path class="v box" d="${bd}"/></g>`}
 return `<g class="${cls}" data-id="${h(id||'')}" transform="translate(${r1(g.tx)} ${r1(g.ty)}) scale(${r1(g.sx*1000)/1000} ${r1(g.sy*1000)/1000})"><path class="hit ${t}" d="${d}"/><path class="v ${t}" d="${d}"/></g>`}
// answer_agent comes with /api/comments: a queued item with no `arx answer` running waits for a person, not the agent
const working=c=>c.agent&&(c.agent.status==='running'||c.agent.status==='queued'&&agentOn);
const stranded=c=>c.waiting&&c.agent&&c.agent.status==='queued'&&!agentOn;
const klass=c=>c.resolved?'res':working(c)?'wait':c.messages.some(m=>m.agent)&&!c.waiting?'rep':'';
// the view under the pins has drawn (S.afterRender ran for this route): before that, "Reading the ledger…" has none of
// the anchors and every pin would fall back to its old page coordinates
let drawnFor=null;const ready=()=>drawnFor===location.hash;
function drawPins(){if(draw)return;const ts=ready()?mine():[],openN=mine().filter(t=>!t.resolved).length;
 $c('.cm-lst').textContent=openN?openN+' open':mine().length?mine().length+' resolved':all.length+' elsewhere';$c('.cm-lst').classList.toggle('none',!mine().length&&!all.length);
 pinsEl.innerHTML=ts.map((c,i)=>{const xy=pos(c);if(!xy)return '';const [x,y]=xy;
  return `<div class="cm-pin ${klass(c)}${x<28?' r':''}${c.id===hot?' hot':''}" data-id="${c.id}" style="left:${x}px;top:${y}px" title="${h(c.messages[0].body.slice(0,200))}">${i+1}</div>`}).join('');
 const live=shapesEl.querySelector('.live');
 shapesEl.innerHTML=ts.map(c=>shapeSvg(c.anchor||{},klass(c),c.id)).join('')+(pending&&(pending.shape||pending.quote||picked(pending))?shapeSvg(pending,'draft',''):'');if(live)shapesEl.append(live);
 pinsEl.querySelectorAll('.cm-pin').forEach(el=>el.onclick=()=>thread(el.dataset.id));
 if(open){const c=ts.find(t=>t.id===open),p=pops.firstChild;if(c&&p&&!p.contains(document.activeElement)){const [x,y]=pos(c)||[innerWidth-360,innerHeight-120];place(p,x,y)}}}
function setHot(id){if(hot===id)return;hot=id;host.querySelectorAll('[data-id]').forEach(e=>e.classList.toggle('hot',!!id&&e.dataset.id===id))}
for(const el of[pinsEl,shapesEl,list]){
 el.addEventListener('pointerover',e=>{const t=e.target.closest?.('[data-id]');if(t&&t.dataset.id)setHot(t.dataset.id)});
 el.addEventListener('pointerout',e=>{const t=e.relatedTarget?.closest?.('[data-id]');if(!t||t.dataset.id!==hot)setHot(null)})}
shapesEl.addEventListener('click',e=>{const t=e.target.closest?.('g[data-id]');if(t&&t.dataset.id)thread(t.dataset.id)});
const when=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
function thread(id){const c=all.find(t=>t.id===id);if(!c)return;
 if(c.route!==here()){location.hash='#'+c.route;setTimeout(()=>thread(id),400);return}
 const ta0=pops.querySelector('textarea'),draft=open===id&&ta0?ta0.value:'';
 closePop();open=id;const p=document.createElement('div');p.className='cm-pop';
 const msg=m=>`<div class="cm-m"><div class="cm-who">${face(m)}${h(m.agent?'Agent':m.author)} · ${when(m.t)}</div><div class="cm-msg ${m.agent?'agent':''}${m.error?' err':''}">${m.agent?rich(m.body):at(linky(m.body),c)}</div></div>`;
 const seenBy=P?P.seenFaces(Object.fromEntries(Object.entries(c.seen||{}).filter(([k,t])=>t>=c.last_t)),myId()):'';
 const ag=stranded(c)?`<div class="cm-m"><div class="cm-who">Agent</div><div class="cm-msg cm-idle">No agent running · <code>arx answer</code></div></div>`:working(c)?`<div class="cm-m"><div class="cm-who">Agent</div><div class="cm-msg agent cm-busy"><span class="cm-dot"></span>${h(c.agent.note||(c.agent.status==='queued'?'Queued':'Working'))}${c.agent.task?` <a href="#task/${encodeURIComponent(c.agent.task)}">task</a>`:''}</div></div>`:'';
 p.innerHTML=`<div class="cm-anchor">${mine().indexOf(c)+1} · ${h(anchorText(c.anchor||{}))}</div><div class="cm-msgs">${c.messages.map(msg).join('')}${ag}</div>${seenBy?`<div class="cm-seen" title="Read the latest message">Seen ${seenBy}</div>`:''}
 <textarea placeholder="Reply"></textarea><div class="cm-row">${nameField()}<button class="cm-sm ln" title="Copy a link to this thread">Link</button><button class="cm-sm rs">${c.resolved?'Reopen':'Resolve'}</button><button class="cm-sm pri go">Reply</button></div>`;
 if(p.querySelector('.cm-fig'))p.classList.add('wide');pops.append(p);fitFigs(p);const [x,y]=pos(c)||[innerWidth-360,innerHeight-120];place(p,x,y);const ta=p.querySelector('textarea');ta.value=draft;
 const ms=p.querySelector('.cm-msgs');ms.scrollTop=ms.scrollHeight;P&&P.complete(ta);
 if(myId()&&unread(c)&&readHere[id]!==c.last_t){readHere[id]=c.last_t;drawList();post({kind:'seen',parent:id},false)}  // you read it as it stands: once per version, no reload
 const send=async()=>{if(p.dataset.busy)return;const body=ta.value.trim();if(!body)return needText(ta);busy(p,true,'Sending…');
  const ev=await post({kind:'reply',parent:id,body,author:takeName(p)});if(!ev)return p.isConnected&&failed(p);
  if(p.isConnected&&open===id){ta.value='';thread(id)}};
 p.querySelector('.go').onclick=send;
 p.querySelector('.ln').onclick=async e=>{const b=e.currentTarget;let base=location.origin+location.pathname;
  try{const d=await (await fetch('api/share',{cache:'no-store'})).json();if(d.link)base=d.link}catch(_){}
  const url=base+(base.includes('?')?'&':'?')+'c='+encodeURIComponent(id)+'#'+c.route;
  try{await navigator.clipboard.writeText(url);b.textContent='Copied'}catch(_){prompt('Link',url)}setTimeout(()=>{b.textContent='Link'},1500)};
 p.querySelector('.rs').onclick=async()=>{if(p.dataset.busy)return;busy(p,true,'Reply');const ev=await post({kind:c.resolved?'reopen':'resolve',parent:id,author:me()||'you'});
  if(!ev)return p.isConnected&&failed(p);if(p.isConnected&&open===id)closePop()};
 p.querySelectorAll('textarea,input').forEach(f=>f.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))send();if(e.key==='Escape')closePop()})}
function drawList(){const you=all.filter(forMe);$c('.cm-lst').classList.toggle('you',!!you.length);$c('.cm-lst').dataset.you=you.length||'';
 if(!list.classList.contains('on'))return;const ts=[...you,...mine().filter(c=>!forMe(c)),...all.filter(t=>t.route!==here()&&!forMe(t))];
 const item=c=>{const i=mine().indexOf(c);return `<div class="cm-it ${klass(c)}${forMe(c)?' you':''}" data-id="${c.id}" ${forMe(c)?'title="For you: unread, and it mentions you or you are in it"':''}><span class="cm-n">${i>=0?i+1:'#'+h(c.route)}</span>${face(c.messages[0])}${at(h(c.messages[0].body.slice(0,140)),c)}<div class="cm-who">${h(anchorText(c.anchor||{}))} · ${c.messages.length-1} ${c.messages.length===2?'reply':'replies'}${c.resolved?' · resolved':stranded(c)?' · no agent running':!working(c)?'':c.agent.status==='running'?' · agent working':' · queued'}</div></div>`};
 list.innerHTML=`<div class="cm-me">${P?P.face(myId(),me()||'?'):''}<input class="cm-name" placeholder="Your name" maxlength="60" value="${h(me())}"></div>`+(you.length?`<div class="cm-sec">For you · ${you.length}</div>`:'')+(ts.length?ts.map(item).join(''):'<div class="cm-it">Press C</div>');
 const nf=list.querySelector('.cm-name');nf.onchange=()=>setMe(nf.value.trim());nf.onkeydown=e=>e.stopPropagation();
 list.querySelectorAll('.cm-it[data-id]').forEach(el=>el.onclick=()=>{const c=all.find(t=>t.id===el.dataset.id);
  if(c.route!==here())return thread(c.id);const n=anchorEl(c);if(n)n.scrollIntoView({block:'center'});setTimeout(()=>thread(c.id),300)})}

async function post(row,reload=true){let ev=null;row.by=myId();try{const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});if(r.ok)ev=await r.json()}catch(e){}if(reload)await load();return ev}
async function load(){try{const r=await fetch(API,{cache:'no-store'});if(!r.ok)return;const d=await r.json();all=d.threads||[];agentOn=!d.answer_agent||!!d.answer_agent.running;
 const p=pops.firstChild,reopen=open&&p&&!p.dataset.busy&&!p.contains(document.activeElement);drawPins();drawList();if(reopen)thread(open)}catch(e){}}
document.body.append(host);
addEventListener('scroll',drawPins,{passive:true,capture:true});addEventListener('resize',drawPins);
// for keys.js: comment on an element, step through this view's threads, reply in or resolve the open one (or the one
// anchored on the focused element)
const threadFor=el=>el&&mine().find(t=>{if(t.resolved)return false;const a=anchorEl(t);return a&&(el.contains(a)||a.contains(el))});
const target2=el=>open&&all.find(t=>t.id===open)||threadFor(el);
window.ARXC={
 comment(el){setMode(!mode,el)},  // pick mode, starting on the focused item when there is one (Enter comments on it)
 step(d){const ts=mine().filter(t=>!t.resolved);if(!ts.length)return false;const i=ts.findIndex(t=>t.id===open);thread(ts[((i<0?(d>0?-1:0):i)+d+ts.length)%ts.length].id);return true},
 reply(el){const c=target2(el);if(!c)return false;if(open!==c.id)thread(c.id);const ta=pops.querySelector('textarea');ta&&focusLater(ta);return true},
 resolve(el){const c=target2(el);if(!c||c.resolved)return false;post({kind:'resolve',parent:c.id,author:me()||'you'}).then(()=>{if(open===c.id)closePop()});return true},
 open:()=>open,has:el=>!!target2(el),count:()=>mine().filter(t=>!t.resolved).length,mode:()=>mode};
addEventListener('hashchange',()=>{closePop();setMode(false);chip.style.display='none';setTimeout(()=>{drawPins();drawList()},0)});
(S.afterRender=S.afterRender||[]).push(()=>{drawnFor=location.hash;drawPins()});
setInterval(()=>{if(!draw&&mine().length)drawPins()},1000);setInterval(()=>{if(!document.hidden)load()},4000);
// a shared thread link (?c=<id>): open that thread once the comments are in, then drop it from the address
const c0=new URLSearchParams(location.search).get('c');
load().then(()=>{if(c0&&all.some(t=>t.id===c0)){history.replaceState(null,'',location.pathname+location.hash);setTimeout(()=>thread(c0),600)}});
})();
