'use strict';
// Comment on anything, on every view: press C (or the button), then Pin (click), Box, Arrow, Pen or Highlight on top of
// the page, or select text outside comment mode. Stored through /api/comments in .research/comments.jsonl (see
// autoresearch/comments.py); every comment and reply asks the agent (`arx answer`), which replies in the thread.
// Anchor: {route, key, rel, sel, text, quote, rx, ry, px, py, shape}. route = location.hash, so a comment stays on its
// view. key = the nearest stable element (an id, a unique data-* attribute, an entity link such as #task/<id>, or the
// card holding exactly one entity link); rel = the path from it; sel = a document cssPath, the last resort.
// shape = {tool, d, bw, bh, fit, ox, oy}: SVG path data in px from the anchor's top-left (page origin ox, oy when the
// anchor is gone). Pins and shapes re-place after every dashboard render (S.afterRender), scroll and resize.
(()=>{
if(window.__arxComments)return;window.__arxComments=1;
const API='api/comments';
const host=document.createElement('div');host.id='arx-comments';host.className='cm-host';
const TOOLS=[['pin','Pin','P'],['box','Box','B'],['arrow','Arrow','A'],['pen','Pen','D'],['highlight','Highlight','H']];
host.innerHTML=`<svg class="cm-shapes" xmlns="http://www.w3.org/2000/svg"></svg><div class="cm-hl"></div><div class="cm-layer"></div><div class="cm-pins"></div><div class="cm-pops"></div>
<div class="cm-list"></div><div class="cm-chip"><button class="cm-btn on cmt">Comment</button><button class="cm-btn ask">Ask</button></div>
<div class="cm-fab"><div class="cm-tools">${TOOLS.map(([k,n,key])=>`<button data-tool="${k}" title="${n} (${key})">${n}<b>${key}</b></button>`).join('')}</div><button class="cm-btn cm-lst" title="Comments">0</button><button class="cm-btn cm-mode">Comment<b>C</b></button></div>`;
const $c=s=>host.querySelector(s),hl=$c('.cm-hl'),pinsEl=$c('.cm-pins'),pops=$c('.cm-pops'),list=$c('.cm-list'),chip=$c('.cm-chip'),layer=$c('.cm-layer'),shapesEl=$c('.cm-shapes'),tools=$c('.cm-tools');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let mode=false,tool='pin',all=[],open=null,hot=null,draw=null,pending=null,agentOn=true;
const here=()=>location.hash.slice(1)||'overview';
// the person (people.js): one id per browser, a name they can change; every event carries both
const P=window.ARXP,me=()=>P?P.me().name:'',myId=()=>P?P.me().id:'',setMe=n=>P&&P.setName(n);
const at=html=>P?P.at(html):html,face=(m)=>m.agent?'<span class="px-face sm" style="--pc:var(--accent,#3b82f6)">AI</span>':P?P.face(m.by||m.author,m.author,'sm'):'';
// a thread is for you when it @mentions you, or you are in it and someone else wrote since you last read it
// read here: the thread version (last_t) this browser has already marked seen, kept even when the POST failed (a snapshot,
// a dropped connection), so one version is posted once and never again
const readHere={};
const unread=c=>{const s=Math.max((c.seen||{})[myId()]||0,readHere[c.id]||0);return c.last_t>s&&c.messages.at(-1).by!==myId()};
const forMe=c=>!c.resolved&&((c.mentions||[]).includes(myId())||(c.people||[]).includes(myId())&&unread(c));

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
// the element's text as it reads on screen: text nodes in different elements that sit apart get a space between them
// ("+1" and "90% CI" are two spans with a margin, never "+190% CI"); hidden text is skipped
function textOf(el,max=90){let out='',pr=null,pe=null,n=0;const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let t;
 while((t=w.nextNode())&&n++<400&&out.length<max+40){const s=t.nodeValue;if(!s.trim()){if(out&&!/\s$/.test(out))out+=' ';continue}
  const rg=document.createRange();rg.selectNodeContents(t);const rs=rg.getClientRects();if(!rs.length&&el.getClientRects().length)continue;
  const r0=rs[0],rl=rs[rs.length-1];
  if(pr&&r0&&t.parentElement!==pe&&!/\s$/.test(out)&&!/^\s/.test(s)&&(r0.left-pr.right>1.5||Math.abs(r0.top-pr.top)>4))out+=' ';
  out+=s;pr=rl||pr;pe=t.parentElement}
 return out.replace(/\s+/g,' ').trim().slice(0,max)}
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
function setTool(t){tool=t;tools.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.tool===t));if(t!=='pin')hl.style.display='none'}
function setMode(on){mode=on;$c('.cm-mode').classList.toggle('on',on);tools.classList.toggle('on',on);layer.classList.toggle('on',on);
 if(!on){hl.style.display='none';cancelDraw()}}
$c('.cm-mode').onclick=()=>setMode(!mode);
tools.querySelectorAll('button').forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
setTool('pin');
$c('.cm-lst').onclick=()=>{list.classList.toggle('on');drawList()};
const KEYS={p:'pin',b:'box',a:'arrow',d:'pen',h:'highlight'};
addEventListener('keydown',e=>{const t=e.composedPath()[0]||{};if(/INPUT|TEXTAREA|SELECT/.test(t.tagName)||t.isContentEditable)return;
 if(e.metaKey||e.ctrlKey||e.altKey)return;const k=e.key.toLowerCase();
 if(k==='c'){e.preventDefault();e.stopPropagation();setMode(!mode);return}
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
 draw={id:e.pointerId,tool,pts:[{x:e.clientX,y:e.clientY}],moved:false};hl.style.display='none'});
layer.addEventListener('pointermove',e=>{e.preventDefault();
 if(!draw){if(tool!=='pin')return;const el=target(e.clientX,e.clientY);if(isPage(el)){hl.style.display='none';return}
  const r=el.getBoundingClientRect();Object.assign(hl.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});return}
 const p={x:e.clientX,y:e.clientY},a=draw.pts[0],last=draw.pts[draw.pts.length-1];
 if(Math.hypot(p.x-a.x,p.y-a.y)>4)draw.moved=true;
 if(draw.tool==='pen'||draw.tool==='highlight'){if(Math.hypot(p.x-last.x,p.y-last.y)>=2)draw.pts.push(p)}else draw.pts=[a,p];
 if(draw.tool!=='pin')renderDraft()});
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
function strokeRange(pts){const xs=pts.map(p=>p.x),y0=pts[0].y,y1=pts[pts.length-1].y;
 const a=caret(Math.min(...xs)+1,pts[xs.indexOf(Math.min(...xs))].y),b=caret(Math.max(...xs)-1,pts[xs.indexOf(Math.max(...xs))].y);if(!a||!b)return null;
 const rg=document.createRange();let s=[a.startContainer,a.startOffset],e=[b.startContainer,b.startOffset];
 if(a.compareBoundaryPoints(Range.START_TO_START,b)>0)[s,e]=[e,s];
 const word=/[\w%.,+\u2212-]/;  // grow both ends to whole words
 while(s[1]>0&&word.test(s[0].nodeValue[s[1]-1]))s[1]--;while(e[1]<e[0].nodeValue.length&&word.test(e[0].nodeValue[e[1]]))e[1]++;
 rg.setStart(...s);rg.setEnd(...e);return String(rg).trim()?rg:null}
const squash=t=>String(t||'').replace(/\s+/g,'');
function flatText(root){const map=[];let flat='';const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let t;
 while((t=w.nextNode())&&flat.length<200000){const v=t.nodeValue;for(let i=0;i<v.length;i++){const ch=/\s/.test(v[i])?' ':v[i];if(ch===' '&&(!flat||flat.endsWith(' ')))continue;flat+=ch;map.push([t,i])}}
 return [flat,map]}
function findRange(root,quote,qn=0){const q=String(quote||'').replace(/\s+/g,' ').trim();if(!root||!q)return null;const [flat,map]=flatText(root);
 let at=-1,from=0;for(let k=0;k<=qn;k++){at=flat.indexOf(q,from);if(at<0)return null;from=at+1}
 const [sn,so]=map[at],[en,eo]=map[at+q.length-1];const r=document.createRange();r.setStart(sn,so);r.setEnd(en,eo+1);return r}
function quoteAnchor(rg){  // a text range -> {anchor fields}: the element holding it, the quote and which occurrence it is
 let el=rg.commonAncestorContainer;if(el.nodeType!==1)el=el.parentElement;const quote=String(rg).replace(/\s+/g,' ').trim().slice(0,500);
 let qn=0;for(let k=0;k<50;k++){const r=findRange(el,quote,k);if(!r)break;if(r.compareBoundaryPoints(Range.START_TO_START,rg)<=0)qn=k;else break}
 return {...anchorFor(el),quote,qn,ctx:ctxOf(el,label(el))}}
function finish(e){if(!draw||e.pointerId!==draw.id)return;e.preventDefault();e.stopPropagation();
 const d=draw;draw=null;try{layer.releasePointerCapture(e.pointerId)}catch(err){}document.documentElement.style.userSelect='';
 shapesEl.querySelector('.live')?.remove();
 const a=d.pts[0],b=d.pts[d.pts.length-1];
 if(d.tool==='pin'||!d.moved){const el=target(a.x,a.y);if(isPage(el)&&d.tool!=='pin'){drawPins();return}
  if(!el||isPage(el)){setMode(false);return}const r=el.getBoundingClientRect();
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
layer.addEventListener('wheel',e=>{let el=target(e.clientX,e.clientY);
 while(el&&!isPage(el)){const s=getComputedStyle(el);if(/(auto|scroll)/.test(s.overflowY+s.overflowX)&&(el.scrollHeight>el.clientHeight||el.scrollWidth>el.clientWidth)){el.scrollBy(e.deltaX,e.deltaY);e.preventDefault();return}el=el.parentElement}
 scrollBy(e.deltaX,e.deltaY);e.preventDefault()},{passive:false});

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
const linky=s=>h(s).replace(/(https?:\/\/[^\s<]+[^\s<.,;:)])|(^|[\s(])(#[a-z]+(?:\/[^\s<]*[^\s<.,;:)])?)/g,(m,url,pre,hash)=>url?`<a href="${url}" target="_blank" rel="noopener">${url}</a>`:`${pre}<a href="${hash}">${hash}</a>`);
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
function place(p,x,y){p.style.left=Math.max(12,Math.min(innerWidth-p.offsetWidth-12,x+14))+'px';p.style.top=Math.max(12,Math.min(innerHeight-p.offsetHeight-60,y+14))+'px'}  // clear of the buttons
function closePop(){pops.innerHTML='';open=null;if(pending){pending=null;drawPins()}}
const focusLater=ta=>{ta.focus({preventScroll:true});setTimeout(()=>{ta.focus({preventScroll:true});requestAnimationFrame(()=>{if(document.activeElement!==ta)ta.focus({preventScroll:true})})},0)};
const nameField=()=>me()?'<span class="cm-sp"></span>':'<input class="cm-name cm-sp" placeholder="Your name" maxlength="60">';
// while a post is in flight: fields locked, the button says so; on failure the popover says it was not sent
function busy(p,on,label){p.dataset.busy=on?'1':'';p.querySelectorAll('textarea,input,button').forEach(b=>b.disabled=on);
 const go=p.querySelector('.go');if(on){go.dataset.label=go.textContent;go.textContent=label}else if(go.dataset.label)go.textContent=go.dataset.label}
function failed(p){busy(p,false);const e=p.querySelector('.cm-err')||p.insertBefore(Object.assign(document.createElement('div'),{className:'cm-err'}),p.querySelector('.cm-row'));e.textContent='Not sent. Try again.'}
function needText(ta){ta.classList.remove('need');void ta.offsetWidth;ta.classList.add('need');ta.focus({preventScroll:true})}
function takeName(p){const n=p.querySelector('.cm-name');if(!n)return me()||'you';const v=n.value.trim();if(v)setMe(v);return v||'you'}
const shapeName={box:'Box',arrow:'Arrow',pen:'Drawing',highlight:'Highlight'};
const anchorText=a=>{const bare=a.what&&a.text&&a.what.split('.')[0]===a.text;  // an element with no text of its own: name its card
 return a.quote?'“'+a.quote.slice(0,120)+'”':(a.shape?shapeName[a.shape.tool]+' on ':'')+(bare&&a.ctx?a.ctx:a.text||'page')};
function compose(a,x,y){closePop();a.route=here();a.vw=innerWidth;const p=document.createElement('div');p.className='cm-pop';
 p.innerHTML=`<div class="cm-anchor">${h(anchorText(a))}</div><textarea placeholder="Comment"></textarea><div class="cm-row">${nameField()}<button class="cm-sm x">Cancel</button><button class="cm-sm pri go" title="⌘↵">Comment</button></div>`;
 pops.append(p);place(p,x,y);const ta=p.querySelector('textarea');focusLater(ta);P&&P.complete(ta);
 if(a.shape||a.quote){pending=a;drawPins()}
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
 return g}
// a pin sits with its point on the corner of what it marks (a quote's first line, a shape's top-left, an arrow's tail),
// so it never covers the text itself
function pos(c){const a=c.anchor||{},g=where(a),s=a.shape;
 if(g.rg){const q=g.rg.getClientRects()[0];return [q.left,q.top]}
 if(s&&s.mode==='tip')return [g.tx+(s.ax||0),g.ty+(s.ay||0)];
 if(s&&s.ins&&g.r)return [g.r.left+s.ins[0],g.r.top+s.ins[1]];
 if(s&&s.bx!=null&&(g.r||s.mode!=='text'))return [g.tx+s.bx*g.sx,g.ty+s.by*g.sy];
 if(g.r)return g.r.height<=48&&g.r.width<=360?[g.r.left,g.r.top]:[g.r.left+(a.rx??.5)*g.r.width,g.r.top+(a.ry??.5)*g.r.height];  // a word or a line: its corner
 return a.px!=null?[a.px-scrollX,a.py-scrollY]:null}
function shapeSvg(a,cl,id){const s=a.shape,g=where(a),cls=`${cl}${id&&id===hot?' hot':''}`;
 if(g.rg){const rs=[...g.rg.getClientRects()].filter(q=>q.width>.5);
  return `<g class="${cls} q" data-id="${h(id||'')}">${rs.map(q=>`<rect class="v q" x="${r1(q.left)}" y="${r1(q.top)}" width="${r1(q.width)}" height="${r1(q.height)}" rx="2"/>`).join('')}</g>`}
 if(!s||!s.d)return '';const d=h(s.d),t=h(s.tool);
 if(s.ins&&g.r){const [l,t2,rr,b]=s.ins,q=g.r,bd=`M${r1(q.left+l)} ${r1(q.top+t2)}H${r1(q.right+rr)}V${r1(q.bottom+b)}H${r1(q.left+l)}Z`;
  return `<g class="${cls}" data-id="${h(id||'')}"><path class="hit box" d="${bd}"/><path class="v box" d="${bd}"/></g>`}
 return `<g class="${cls}" data-id="${h(id||'')}" transform="translate(${r1(g.tx)} ${r1(g.ty)}) scale(${r1(g.sx*1000)/1000} ${r1(g.sy*1000)/1000})"><path class="hit ${t}" d="${d}"/><path class="v ${t}" d="${d}"/></g>`}
// answer_agent comes with /api/comments: a queued item with no `arx answer` running waits for a person, not the agent
const working=c=>c.agent&&(c.agent.status==='running'||c.agent.status==='queued'&&agentOn);
const stranded=c=>c.waiting&&c.agent&&c.agent.status==='queued'&&!agentOn;
const klass=c=>c.resolved?'res':working(c)?'wait':c.messages.some(m=>m.agent)&&!c.waiting?'rep':'';
function drawPins(){if(draw)return;const ts=mine(),openN=ts.filter(t=>!t.resolved).length;
 $c('.cm-lst').textContent=openN?openN+' open':ts.length?ts.length+' resolved':all.length+' elsewhere';$c('.cm-lst').classList.toggle('none',!ts.length&&!all.length);
 pinsEl.innerHTML=ts.map((c,i)=>{const xy=pos(c);if(!xy)return '';const [x,y]=xy;
  return `<div class="cm-pin ${klass(c)}${c.id===hot?' hot':''}" data-id="${c.id}" style="left:${x}px;top:${y}px" title="${h(c.messages[0].body.slice(0,200))}">${i+1}</div>`}).join('');
 const live=shapesEl.querySelector('.live');
 shapesEl.innerHTML=ts.map(c=>shapeSvg(c.anchor||{},klass(c),c.id)).join('')+(pending&&(pending.shape||pending.quote)?shapeSvg(pending,'draft',''):'');if(live)shapesEl.append(live);
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
 const msg=m=>`<div class="cm-m"><div class="cm-who">${face(m)}${h(m.agent?'Agent':m.author)} · ${when(m.t)}</div><div class="cm-msg ${m.agent?'agent':''}${m.error?' err':''}">${m.agent?rich(m.body):at(linky(m.body))}</div></div>`;
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
 const item=c=>{const i=mine().indexOf(c);return `<div class="cm-it ${klass(c)}${forMe(c)?' you':''}" data-id="${c.id}" ${forMe(c)?'title="For you: it mentions you, or there is a reply you have not read"':''}><span class="cm-n">${i>=0?i+1:'#'+h(c.route)}</span>${face(c.messages[0])}${at(h(c.messages[0].body.slice(0,140)))}<div class="cm-who">${h(anchorText(c.anchor||{}))} · ${c.messages.length-1} ${c.messages.length===2?'reply':'replies'}${c.resolved?' · resolved':stranded(c)?' · no agent running':!working(c)?'':c.agent.status==='running'?' · agent working':' · queued'}</div></div>`};
 list.innerHTML=`<div class="cm-me">${P?P.face(myId(),me()||'?'):''}<input class="cm-name" placeholder="Your name" maxlength="60" value="${h(me())}"></div>`+(you.length?`<div class="cm-sec">For you · ${you.length}</div>`:'')+(ts.length?ts.map(item).join(''):'<div class="cm-it">Press C</div>');
 const nf=list.querySelector('.cm-name');nf.onchange=()=>setMe(nf.value.trim());nf.onkeydown=e=>e.stopPropagation();
 list.querySelectorAll('.cm-it[data-id]').forEach(el=>el.onclick=()=>{const c=all.find(t=>t.id===el.dataset.id);
  if(c.route!==here())return thread(c.id);const n=anchorEl(c);if(n)n.scrollIntoView({block:'center'});setTimeout(()=>thread(c.id),300)})}

async function post(row,reload=true){let ev=null;row.by=myId();try{const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});if(r.ok)ev=await r.json()}catch(e){}if(reload)await load();return ev}
async function load(){try{const r=await fetch(API,{cache:'no-store'});if(!r.ok)return;const d=await r.json();all=d.threads||[];agentOn=!d.answer_agent||!!d.answer_agent.running;
 const p=pops.firstChild,reopen=open&&p&&!p.dataset.busy&&!p.contains(document.activeElement);drawPins();drawList();if(reopen)thread(open)}catch(e){}}
document.body.append(host);
addEventListener('scroll',drawPins,{passive:true,capture:true});addEventListener('resize',drawPins);
addEventListener('hashchange',()=>{closePop();setMode(false);chip.style.display='none';setTimeout(()=>{drawPins();drawList()},0)});
(S.afterRender=S.afterRender||[]).push(drawPins);
setInterval(()=>{if(!draw&&mine().length)drawPins()},1000);setInterval(()=>{if(!document.hidden)load()},4000);
// a shared thread link (?c=<id>): open that thread once the comments are in, then drop it from the address
const c0=new URLSearchParams(location.search).get('c');
load().then(()=>{if(c0&&all.some(t=>t.id===c0)){history.replaceState(null,'',location.pathname+location.hash);setTimeout(()=>thread(c0),600)}});
})();
