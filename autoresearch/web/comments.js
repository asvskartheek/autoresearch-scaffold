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
<div class="cm-list"></div><div class="cm-chip"><button class="cm-btn on">Comment</button></div>
<div class="cm-fab"><div class="cm-tools">${TOOLS.map(([k,n,key])=>`<button data-tool="${k}" title="${n} (${key})">${n}<b>${key}</b></button>`).join('')}</div><button class="cm-btn cm-lst" title="Comments">0</button><button class="cm-btn cm-mode">Comment<b>C</b></button></div>`;
const $c=s=>host.querySelector(s),hl=$c('.cm-hl'),pinsEl=$c('.cm-pins'),pops=$c('.cm-pops'),list=$c('.cm-list'),chip=$c('.cm-chip'),layer=$c('.cm-layer'),shapesEl=$c('.cm-shapes'),tools=$c('.cm-tools');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let mode=false,tool='pin',all=[],open=null,hot=null,draw=null,pending=null;
const here=()=>location.hash.slice(1)||'overview';
const me=()=>{try{return localStorage.getItem('arx-name')||''}catch(e){return ''}};
const setMe=n=>{try{localStorage.setItem('arx-name',n)}catch(e){}};

/* ---------- anchors: stable keys first, cssPath last */
const ENT=/^#[a-z]+\/./;
const uniq=sel=>{try{return document.querySelectorAll(sel).length===1}catch(e){return false}};
const hrefs=el=>new Set([...(el.matches('a[href]')?[el]:[]),...el.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')).filter(x=>ENT.test(x)));
const CARD=/^(ARTICLE|LI|TR)$/;
const sig=el=>el.tagName.toLowerCase()+(el.classList[0]?'.'+CSS.escape(el.classList[0]):'');
function keyOf(el){
 for(let a=el;a&&a.nodeType===1&&a!==document.body&&a!==host;a=a.parentElement){
  if(a.id&&!/^\d/.test(a.id)&&uniq('#'+CSS.escape(a.id)))return [{sel:'#'+CSS.escape(a.id)},a];
  if(a.tagName==='A'&&ENT.test(a.getAttribute('href')||''))return [{href:a.getAttribute('href')},a];
  for(const at of a.attributes){if(at.name.startsWith('data-')){const s=`[${at.name}="${CSS.escape(at.value)}"]`;if(uniq(s))return [{sel:s},a]}}
  const hs=hrefs(a);
  // a card: holds exactly one entity link and is a list item (article, li, tr, .card...) or sits among other entities
  if(hs.size===1&&a.parentElement&&(CARD.test(a.tagName)||/card|job|row|item/.test(a.getAttribute("class")||"")||hrefs(a.parentElement).size>1))return [{href:[...hs][0],card:sig(a)},a];
 }
 return [null,null]}
function relPath(from,el){const parts=[];
 while(el&&el!==from){let i=1,s=el;while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
  parts.unshift(el.tagName.toLowerCase()+`:nth-of-type(${i})`);el=el.parentElement}
 return el===from?parts.join('>'):null}
function cssPath(el){const parts=[];while(el&&el.nodeType===1&&el!==document.body){
 if(el.id&&!/^\d/.test(el.id)){parts.unshift('#'+CSS.escape(el.id));break}
 let i=1,s=el;while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
 parts.unshift(el.tagName.toLowerCase()+`:nth-of-type(${i})`);el=el.parentElement}
 return parts.join('>')}
const label=el=>{const t=(el.innerText||el.textContent||el.getAttribute?.('aria-label')||'').trim().replace(/\s+/g,' ');
 return (t||el.tagName.toLowerCase()).slice(0,90)};
function anchorFor(el){const [key,node]=keyOf(el);const rel=node?relPath(node,el):null;
 return key&&rel!=null?{key,rel,sel:cssPath(el),text:label(el)}:{sel:cssPath(el),text:label(el)}}
function keyNode(k){
 if(k.sel){try{return document.querySelector(k.sel)}catch(e){return null}}
 const ls=[...document.querySelectorAll('a[href]')].filter(a=>a.getAttribute('href')===k.href&&!host.contains(a));
 if(!k.card)return ls[0]||null;
 for(const l of ls){const c=l.closest(k.card);if(c)return c}
 return null}
function resolve(a){
 if(a.key){const n=keyNode(a.key);if(n){if(!a.rel)return n;try{return n.querySelector(':scope>'+a.rel)||n}catch(e){return n}}}
 let el=null;try{el=a.sel&&document.querySelector(a.sel)}catch(e){}
 if(a.text&&(!el||label(el)!==a.text)){  // the element moved or the anchor came from the CLI: find it by its text
  const same=[...(document.querySelector('#main')?.querySelectorAll(el?el.tagName.toLowerCase():'h1,h2,h3,a,b,th,td,span,p')||[])].find(x=>label(x)===a.text);if(same)return same}
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
function finish(e){if(!draw||e.pointerId!==draw.id)return;e.preventDefault();e.stopPropagation();
 const d=draw;draw=null;try{layer.releasePointerCapture(e.pointerId)}catch(err){}document.documentElement.style.userSelect='';
 shapesEl.querySelector('.live')?.remove();
 const a=d.pts[0];
 if(d.tool==='pin'||!d.moved){const el=target(a.x,a.y);if(isPage(el)&&d.tool!=='pin'){drawPins();return}
  if(!el||isPage(el)){setMode(false);return}const r=el.getBoundingClientRect();
  compose({...anchorFor(el),rx:(a.x-r.left)/Math.max(1,r.width),ry:(a.y-r.top)/Math.max(1,r.height),px:a.x+scrollX,py:a.y+scrollY},a.x,a.y);
  setMode(false);return}
 const B=bbox(d.pts,d.tool),el0=target(a.x,a.y);
 // anchor: the element under the start point, widened to the nearest ancestor that contains the whole shape
 let el=el0,fit=false;
 while(el&&!isPage(el)){const r=el.getBoundingClientRect();if(r.left<=B.left&&r.top<=B.top&&r.right>=B.right&&r.bottom>=B.bottom){fit=true;break}el=el.parentElement}
 if(!fit)el=isPage(el0)?null:el0;
 const r=el?el.getBoundingClientRect():{left:0,top:0,width:innerWidth,height:innerHeight};
 const rel=d.pts.map(p=>({x:p.x-r.left,y:p.y-r.top}));
 const shape={tool:d.tool,d:shapePath(d.tool,rel),bw:r1(r.width),bh:r1(r.height),fit,ox:r1(r.left+scrollX),oy:r1(r.top+scrollY)};
 const an=el?anchorFor(el):{sel:'',text:'page'};
 compose({...an,rx:(a.x-r.left)/Math.max(1,r.width),ry:(a.y-r.top)/Math.max(1,r.height),px:a.x+scrollX,py:a.y+scrollY,shape},
  Math.min(B.right,innerWidth-20),Math.min(B.bottom,innerHeight-20));
 setMode(false)}
layer.addEventListener('pointerup',finish);layer.addEventListener('pointercancel',e=>{if(draw&&e.pointerId===draw.id)cancelDraw()});
layer.addEventListener('lostpointercapture',e=>{if(draw&&e.pointerId===draw.id)cancelDraw()});
for(const ev of['click','dblclick','contextmenu','selectstart','dragstart'])layer.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation()});
// the layer covers the page in comment mode; pass wheel scrolling through
layer.addEventListener('wheel',e=>{let el=target(e.clientX,e.clientY);
 while(el&&!isPage(el)){const s=getComputedStyle(el);if(/(auto|scroll)/.test(s.overflowY+s.overflowX)&&(el.scrollHeight>el.clientHeight||el.scrollWidth>el.clientWidth)){el.scrollBy(e.deltaX,e.deltaY);e.preventDefault();return}el=el.parentElement}
 scrollBy(e.deltaX,e.deltaY);e.preventDefault()},{passive:false});

/* ---------- selected text -> a "Comment" chip next to it */
document.addEventListener('mouseup',e=>{if(mode||host.contains(e.target))return;setTimeout(()=>{const s=getSelection();
 if(!s||s.isCollapsed||!String(s).trim()||host.contains(s.anchorNode)){chip.style.display='none';return}
 const r=s.getRangeAt(0).getBoundingClientRect(),quote=String(s).trim();
 const el=s.anchorNode.nodeType===1?s.anchorNode:s.anchorNode.parentElement;
 Object.assign(chip.style,{display:'block',left:Math.min(innerWidth-110,r.left)+'px',top:Math.min(innerHeight-40,r.bottom+6)+'px'});
 chip.onclick=()=>{const er=el.getBoundingClientRect();
  compose({...anchorFor(el),quote:quote.slice(0,500),rx:(r.left-er.left)/Math.max(1,er.width),ry:(r.top-er.top)/Math.max(1,er.height),
   px:r.left+scrollX,py:r.top+scrollY},r.right,r.bottom);chip.style.display='none'}},0)});

/* ---------- reply bodies: text with links, plus one sanitised inline SVG */
const SVG_OK=new Set(['svg','g','path','rect','circle','line','text','polyline']);
const ATTR_OK=/^(viewbox|width|height|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|d|points|fill|stroke|stroke-width|stroke-dasharray|stroke-linecap|stroke-linejoin|opacity|fill-opacity|stroke-opacity|transform|font-size|font-weight|font-family|text-anchor|dominant-baseline|xmlns|preserveaspectratio)$/i;
function cleanSvg(src){const t=document.createElement('template');t.innerHTML=src;const svg=t.content.querySelector('svg');if(!svg)return '';
 const walk=el=>{for(const a of [...el.attributes])if(!ATTR_OK.test(a.name)||/url\s*\(|javascript:|expression|&#|\\/i.test(a.value))el.removeAttribute(a.name);
  for(const c of [...el.childNodes]){if(c.nodeType===3)continue;if(c.nodeType!==1||!SVG_OK.has(c.localName)){c.remove();continue}walk(c)}};
 walk(svg);return `<div class="cm-fig">${svg.outerHTML}</div>`}
const linky=s=>h(s).replace(/(https?:\/\/[^\s<]+[^\s<.,;:)])|(^|[\s(])(#[a-z]+(?:\/[^\s<]*[^\s<.,;:)])?)/g,(m,url,pre,hash)=>url?`<a href="${url}" target="_blank" rel="noopener">${url}</a>`:`${pre}<a href="${hash}">${hash}</a>`);
const rich=b=>String(b||'').split(/(<svg[\s\S]*?<\/svg>)/i).map((x,i)=>i%2?cleanSvg(x):linky(x)).join('');

/* ---------- compose and threads */
function place(p,x,y){p.style.left=Math.max(12,Math.min(innerWidth-332,x+14))+'px';p.style.top=Math.max(12,Math.min(innerHeight-p.offsetHeight-60,y+14))+'px'}  // clear of the buttons
function closePop(){pops.innerHTML='';open=null;if(pending){pending=null;drawPins()}}
const focusLater=ta=>{ta.focus({preventScroll:true});setTimeout(()=>{ta.focus({preventScroll:true});requestAnimationFrame(()=>{if(document.activeElement!==ta)ta.focus({preventScroll:true})})},0)};
const nameField=()=>me()?'':'<input class="cm-name" placeholder="Your name" maxlength="60">';
function takeName(p){const n=p.querySelector('.cm-name');if(!n)return me()||'you';const v=n.value.trim();if(v)setMe(v);return v||'you'}
const shapeName={box:'Box',arrow:'Arrow',pen:'Drawing',highlight:'Highlight'};
const anchorText=a=>a.quote?'“'+a.quote.slice(0,120)+'”':(a.shape?shapeName[a.shape.tool]+' on ':'')+(a.text||'page');
function compose(a,x,y){closePop();a.route=here();a.vw=innerWidth;const p=document.createElement('div');p.className='cm-pop';
 p.innerHTML=`<div class="cm-anchor">${h(anchorText(a))}</div>${nameField()}<textarea placeholder="Comment"></textarea><div class="cm-row"><span class="cm-sp">⌘↵</span><button class="cm-sm x">Cancel</button><button class="cm-sm pri go">Comment</button></div>`;
 pops.append(p);place(p,x,y);const ta=p.querySelector('textarea');focusLater(p.querySelector('.cm-name')||ta);
 if(a.shape){pending=a;drawPins()}
 const send=async()=>{const body=ta.value.trim();if(!body)return;const author=takeName(p);
  const ev=await post({kind:'comment',anchor:a,body,author});closePop();if(ev&&ev.id)thread(ev.id)};
 p.querySelector('.go').onclick=send;p.querySelector('.x').onclick=closePop;
 p.querySelectorAll('textarea,input').forEach(f=>f.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))send();if(e.key==='Escape')closePop()})}

const mine=()=>all.filter(t=>t.route===here());
const anchorEl=c=>resolve(c.anchor||{});
function pos(c){const a=c.anchor||{},el=anchorEl(c);
 if(el){const r=el.getBoundingClientRect();if(r.width||r.height)return [r.left+(a.rx??.5)*r.width,r.top+(a.ry??.5)*r.height]}
 return a.px!=null?[a.px-scrollX,a.py-scrollY]:null}
function shapeSvg(a,cl,id){const s=a.shape;if(!s||!s.d)return '';const el=resolve(a);let tx=s.ox-scrollX,ty=s.oy-scrollY,sx=1,sy=1;
 if(el){const r=el.getBoundingClientRect();if(r.width||r.height){tx=r.left;ty=r.top;if(s.fit){sx=r.width/Math.max(1,s.bw);sy=r.height/Math.max(1,s.bh)}}}
 const d=h(s.d),t=h(s.tool);
 return `<g class="${cl}${id&&id===hot?' hot':''}" data-id="${h(id||'')}" transform="translate(${r1(tx)} ${r1(ty)}) scale(${r1(sx*1000)/1000} ${r1(sy*1000)/1000})"><path class="hit ${t}" d="${d}"/><path class="v ${t}" d="${d}"/></g>`}
const working=c=>c.agent&&(c.agent.status==='queued'||c.agent.status==='running');
const klass=c=>c.resolved?'res':working(c)?'wait':c.messages.some(m=>m.agent)&&!c.waiting?'rep':'';
function drawPins(){if(draw)return;const ts=mine(),openN=ts.filter(t=>!t.resolved).length;
 $c('.cm-lst').textContent=openN?openN+' open':ts.length?String(ts.length):'All';$c('.cm-lst').classList.toggle('none',!ts.length&&!all.length);
 pinsEl.innerHTML=ts.map((c,i)=>{const xy=pos(c);if(!xy)return '';const [x,y]=xy;
  return `<div class="cm-pin ${klass(c)}${c.id===hot?' hot':''}" data-id="${c.id}" style="left:${x}px;top:${y}px" title="${h(c.messages[0].body.slice(0,200))}">${i+1}</div>`}).join('');
 const live=shapesEl.querySelector('.live');
 shapesEl.innerHTML=ts.map(c=>shapeSvg(c.anchor||{},klass(c),c.id)).join('')+(pending?shapeSvg(pending,'draft',''):'');if(live)shapesEl.append(live);
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
 const msg=m=>`<div class="cm-m"><div class="cm-who">${h(m.agent?'Agent':m.author)} · ${when(m.t)}</div><div class="cm-msg ${m.agent?'agent':''}${m.error?' err':''}">${m.agent?rich(m.body):linky(m.body)}</div></div>`;
 const ag=working(c)?`<div class="cm-m"><div class="cm-who">Agent</div><div class="cm-msg agent cm-busy"><span class="cm-dot"></span>${h(c.agent.note||(c.agent.status==='queued'?'Queued':'Working'))}${c.agent.task?` <a href="#task/${encodeURIComponent(c.agent.task)}">task</a>`:''}</div></div>`:'';
 p.innerHTML=`<div class="cm-anchor">${mine().indexOf(c)+1} · ${h(anchorText(c.anchor||{}))}</div><div class="cm-msgs">${c.messages.map(msg).join('')}${ag}</div>
 ${nameField()}<textarea placeholder="Reply"></textarea><div class="cm-row"><span class="cm-sp">${c.resolved?'Resolved':''}</span><button class="cm-sm rs">${c.resolved?'Reopen':'Resolve'}</button><button class="cm-sm pri go">Reply</button></div>`;
 pops.append(p);const [x,y]=pos(c)||[innerWidth-360,innerHeight-120];place(p,x,y);const ta=p.querySelector('textarea');ta.value=draft;
 const ms=p.querySelector('.cm-msgs');ms.scrollTop=ms.scrollHeight;
 const send=async()=>{const body=ta.value.trim();if(!body)return;await post({kind:'reply',parent:id,body,author:takeName(p)});ta.value='';thread(id)};
 p.querySelector('.go').onclick=send;
 p.querySelector('.rs').onclick=async()=>{await post({kind:c.resolved?'reopen':'resolve',parent:id,author:me()||'you'});closePop()};
 p.querySelectorAll('textarea,input').forEach(f=>f.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))send();if(e.key==='Escape')closePop()})}
function drawList(){if(!list.classList.contains('on'))return;const ts=[...mine(),...all.filter(t=>t.route!==here())];
 const item=c=>{const i=mine().indexOf(c);return `<div class="cm-it ${klass(c)}" data-id="${c.id}"><span class="cm-n">${i>=0?i+1:'#'+h(c.route)}</span>${h(c.messages[0].body.slice(0,140))}<div class="cm-who">${h(anchorText(c.anchor||{}))} · ${c.messages.length-1} ${c.messages.length===2?'reply':'replies'}${c.resolved?' · resolved':working(c)?' · agent working':''}</div></div>`};
 list.innerHTML=`<div class="cm-me"><input class="cm-name" placeholder="Your name" maxlength="60" value="${h(me())}"></div>`+(ts.length?ts.map(item).join(''):'<div class="cm-it">Press C</div>');
 const nf=list.querySelector('.cm-name');nf.onchange=()=>setMe(nf.value.trim());nf.onkeydown=e=>e.stopPropagation();
 list.querySelectorAll('.cm-it[data-id]').forEach(el=>el.onclick=()=>{const c=all.find(t=>t.id===el.dataset.id);
  if(c.route!==here())return thread(c.id);const n=anchorEl(c);if(n)n.scrollIntoView({block:'center'});setTimeout(()=>thread(c.id),300)})}

async function post(row){let ev=null;try{const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});if(r.ok)ev=await r.json()}catch(e){}await load();return ev}
async function load(){try{const r=await fetch(API,{cache:'no-store'});if(!r.ok)return;all=(await r.json()).threads||[];
 const p=pops.firstChild,reopen=open&&p&&!p.contains(document.activeElement);drawPins();drawList();if(reopen)thread(open)}catch(e){}}
document.body.append(host);
addEventListener('scroll',drawPins,{passive:true,capture:true});addEventListener('resize',drawPins);
addEventListener('hashchange',()=>{closePop();setMode(false);chip.style.display='none';setTimeout(()=>{drawPins();drawList()},0)});
(S.afterRender=S.afterRender||[]).push(drawPins);
setInterval(()=>{if(!draw&&mine().length)drawPins()},1000);setInterval(()=>{if(!document.hidden)load()},4000);load();
})();
