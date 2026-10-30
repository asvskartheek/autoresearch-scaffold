// Comment on anything: press C (or the button), then pin (click), box, arrow, pen or highlight on top of the page, or
// select text outside comment mode. Pins are threaded and stored by serve.py in feedback.jsonl as
// {kind:'comment'|'reply'|'resolve', ...}; a drawn comment also carries shape:{tool,d,bw,bh,fit,ox,oy}, where d is SVG
// path data in px from the anchor element's top-left (or from page origin ox,oy when the anchor is gone). Old rows
// have no shape. Injected into every prototype page.
(()=>{
if(window.__arxComments)return;window.__arxComments=1;
const proto=location.pathname.split('/').filter(Boolean)[0]||'hub';
const host=document.createElement('div');host.id='arx-comments';
host.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483646';
const root=host.attachShadow({mode:'open'});
const TOOLS=[['pin','Pin','P'],['box','Box','B'],['arrow','Arrow','A'],['pen','Pen','D'],['highlight','Highlight','H']];
root.innerHTML=`<style>
:host{all:initial}
*{box-sizing:border-box;font:13px/1.45 "IBM Plex Sans",Inter,system-ui,sans-serif}
.fab{position:fixed;right:16px;bottom:16px;pointer-events:auto;display:flex;gap:6px;align-items:center}
.btn{height:34px;padding:0 14px;border-radius:17px;border:1px solid #3a434b;background:#13171b;color:#eef1f3;cursor:pointer;font-weight:500;box-shadow:0 2px 10px rgba(0,0,0,.35)}
.btn.on{background:#f0b43c;color:#16181a;border-color:#f0b43c}
.btn b{font:600 11px ui-monospace,Menlo,monospace;opacity:.7;margin-left:6px}
.tools{display:none;height:34px;padding:3px;border-radius:17px;border:1px solid #3a434b;background:#13171b;box-shadow:0 2px 10px rgba(0,0,0,.35);gap:2px}
.tools.on{display:flex}
.tools button{height:26px;padding:0 10px;border-radius:13px;border:0;background:transparent;color:#c9d0d6;cursor:pointer}
.tools button:hover{background:#1f262c}
.tools button.on{background:#f0b43c;color:#16181a;font-weight:600}
.tools b{font:600 10px ui-monospace,Menlo,monospace;opacity:.6;margin-left:5px}
.layer{position:fixed;inset:0;pointer-events:none;cursor:crosshair;user-select:none;-webkit-user-select:none;touch-action:none}
.layer.on{pointer-events:auto}
.shapes{position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;overflow:visible}
.shapes g{--c:#f0b43c;transition:opacity .15s}
.shapes g.rep{--c:#5cb8cc}.shapes g.res{--c:#4cc38a;opacity:.3}.shapes g.hot{opacity:1}
.shapes path{fill:none;stroke:var(--c);vector-effect:non-scaling-stroke;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
.shapes .v{stroke-width:2.5}.shapes .v.highlight{stroke-width:18;stroke-opacity:.35;stroke-linecap:butt}
.shapes g.hot .v{stroke-width:4}.shapes g.hot .v.highlight{stroke-width:20;stroke-opacity:.5}
.shapes .hit{stroke:transparent;stroke-width:14;pointer-events:stroke;cursor:pointer}
.shapes .hit.highlight{stroke-width:20}
.shapes g.draft .v{stroke-dasharray:6 4}.shapes g.draft .v.highlight{stroke-dasharray:none}
.hl{position:fixed;border:2px solid #f0b43c;border-radius:4px;background:rgba(240,180,60,.08);pointer-events:none;display:none}
.pin{position:fixed;width:24px;height:24px;margin:-12px 0 0 -12px;border-radius:12px 12px 12px 2px;background:#f0b43c;color:#16181a;
 font:700 11px ui-monospace,Menlo,monospace;display:flex;align-items:center;justify-content:center;pointer-events:auto;cursor:pointer;border:2px solid #16181a;transition:transform .12s}
.pin.res{background:#4cc38a;opacity:.6}.pin.rep{background:#5cb8cc}
.pin.hot{transform:scale(1.25);opacity:1;box-shadow:0 0 0 3px rgba(240,180,60,.45)}
.pop{position:fixed;width:300px;max-width:calc(100vw - 24px);background:#13171b;color:#eef1f3;border:1px solid #3a434b;border-radius:8px;
 box-shadow:0 8px 30px rgba(0,0,0,.45);pointer-events:auto;padding:10px;display:flex;flex-direction:column;gap:8px}
.anchor{font-size:11px;color:#8c959d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border-left:2px solid #f0b43c;padding-left:6px}
textarea{width:100%;min-height:70px;resize:vertical;background:#0c0f12;color:#eef1f3;border:1px solid #3a434b;border-radius:6px;padding:8px}
textarea:focus{outline:2px solid #f0b43c;border-color:transparent}
.row{display:flex;justify-content:flex-end;gap:6px;align-items:center}
.row .sp{flex:1;font-size:11px;color:#8c959d}
.sm{height:28px;padding:0 10px;border-radius:6px;border:1px solid #3a434b;background:#1a1f24;color:#eef1f3;cursor:pointer}
.sm.pri{background:#f0b43c;border-color:#f0b43c;color:#16181a;font-weight:600}
.msg{padding:6px 8px;background:#1a1f24;border-radius:6px;white-space:pre-wrap}
.msg.claude{background:#14303a}
.who{font-size:11px;color:#8c959d;margin-bottom:2px}
.list{position:fixed;right:16px;bottom:60px;width:320px;max-height:60vh;overflow:auto;pointer-events:auto;background:#13171b;color:#eef1f3;
 border:1px solid #3a434b;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.45);display:none}
.list .it{padding:8px 10px;border-bottom:1px solid #232a30;cursor:pointer}.list .it:hover,.list .it.hot{background:#1a1f24}
.list .n{font:700 11px ui-monospace,Menlo,monospace;color:#f0b43c;margin-right:6px}
.chip{position:fixed;pointer-events:auto;display:none}
</style>
<svg class="shapes" xmlns="http://www.w3.org/2000/svg"></svg><div class="hl"></div><div class="layer"></div><div class="pins"></div><div class="pops"></div>
<div class="list"></div><div class="chip"><button class="btn on">Comment</button></div>
<div class="fab"><div class="tools">${TOOLS.map(([k,n,key])=>`<button data-tool="${k}" title="${n} (${key})">${n}<b>${key}</b></button>`).join('')}</div><button class="btn lst" title="All comments on this page">0</button><button class="btn mode">Comment<b>C</b></button></div>`;
const $=s=>root.querySelector(s),hl=$('.hl'),pinsEl=$('.pins'),pops=$('.pops'),list=$('.list'),chip=$('.chip'),layer=$('.layer'),shapesEl=$('.shapes'),tools=$('.tools');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let mode=false,tool='pin',rows=[],open=null,hot=null,draw=null,pending=null;

function cssPath(el){const parts=[];while(el&&el.nodeType===1&&el!==document.body){
 if(el.id&&!/^\d/.test(el.id)){parts.unshift('#'+CSS.escape(el.id));break}
 let i=1,s=el;while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
 parts.unshift(el.tagName.toLowerCase()+`:nth-of-type(${i})`);el=el.parentElement}
 return parts.join('>')}
const label=el=>{const t=(el.innerText||el.textContent||el.getAttribute?.('aria-label')||'').trim().replace(/\s+/g,' ');
 return (t||el.tagName.toLowerCase()).slice(0,90)};
const target=(x,y)=>{host.style.display='none';const el=document.elementFromPoint(x,y);host.style.display='';return el};
const isPage=el=>!el||el===document.documentElement||el===document.body;

function setTool(t){tool=t;tools.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.tool===t));if(t!=='pin')hl.style.display='none'}
function setMode(on){mode=on;$('.mode').classList.toggle('on',on);tools.classList.toggle('on',on);layer.classList.toggle('on',on);
 if(!on){hl.style.display='none';cancelDraw()}}
$('.mode').onclick=()=>setMode(!mode);
tools.querySelectorAll('button').forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
setTool('pin');
$('.lst').onclick=()=>{list.style.display=list.style.display==='block'?'none':'block';drawList()};
const KEYS={p:'pin',b:'box',a:'arrow',d:'pen',h:'highlight'};
addEventListener('keydown',e=>{const tag=(e.composedPath()[0]||{}).tagName;if(/INPUT|TEXTAREA|SELECT/.test(tag)||e.target.isContentEditable)return;
 if(e.metaKey||e.ctrlKey||e.altKey)return;const k=e.key.toLowerCase();
 if(k==='c'){e.preventDefault();e.stopPropagation();setMode(!mode);return}
 // tool keys only in comment mode, so pages keep their own shortcuts (story uses P for pause)
 if(mode&&KEYS[k]){e.preventDefault();e.stopPropagation();setTool(KEYS[k]);return}
 if(e.key==='Escape'){if(draw){cancelDraw();return}setMode(false);closePop()}},true);

/* ---------- drawing layer: pointer capture, no text selection ---------- */
const r1=n=>Math.round(n*10)/10;
function shapePath(t,pts){const a=pts[0],b=pts[pts.length-1];
 if(t==='box')return `M${r1(a.x)} ${r1(a.y)}H${r1(b.x)}V${r1(b.y)}H${r1(a.x)}Z`;
 if(t==='arrow'){const ang=Math.atan2(b.y-a.y,b.x-a.x),L=Math.min(14,Math.hypot(b.x-a.x,b.y-a.y)*.5),w=.5;
  const h=s=>`${r1(b.x-L*Math.cos(ang+s*w))} ${r1(b.y-L*Math.sin(ang+s*w))}`;
  return `M${r1(a.x)} ${r1(a.y)}L${r1(b.x)} ${r1(b.y)}M${h(1)}L${r1(b.x)} ${r1(b.y)}L${h(-1)}`}
 return 'M'+pts.map(p=>`${r1(p.x)} ${r1(p.y)}`).join('L')}
function bbox(pts){const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y),pad=tool==='highlight'?9:2;
 return {left:Math.min(...xs)-pad,top:Math.min(...ys)-pad,right:Math.max(...xs)+pad,bottom:Math.max(...ys)+pad}}
function cancelDraw(){if(!draw)return;try{layer.releasePointerCapture(draw.id)}catch{}draw=null;document.documentElement.style.userSelect='';drawPins()}
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
 const d=draw;draw=null;try{layer.releasePointerCapture(e.pointerId)}catch{}document.documentElement.style.userSelect='';
 shapesEl.querySelector('.live')?.remove();
 const a=d.pts[0];
 if(d.tool==='pin'||!d.moved){const el=target(a.x,a.y);if(isPage(el)&&d.tool!=='pin'){drawPins();return}
  if(!el)return;const r=el.getBoundingClientRect();
  compose({sel:cssPath(el),anchor:label(el),rx:(a.x-r.left)/Math.max(1,r.width),ry:(a.y-r.top)/Math.max(1,r.height),px:a.x+scrollX,py:a.y+scrollY},a.x,a.y);
  setMode(false);return}
 const B=bbox(d.pts),el0=target(a.x,a.y);
 // anchor: the element under the start point, widened to the nearest ancestor that contains the whole shape
 let el=el0,fit=false;
 while(el&&!isPage(el)){const r=el.getBoundingClientRect();if(r.left<=B.left&&r.top<=B.top&&r.right>=B.right&&r.bottom>=B.bottom){fit=true;break}el=el.parentElement}
 if(!fit)el=isPage(el0)?null:el0;
 const r=el?el.getBoundingClientRect():{left:0,top:0,width:innerWidth,height:innerHeight};
 const rel=d.pts.map(p=>({x:p.x-r.left,y:p.y-r.top}));
 const shape={tool:d.tool,d:shapePath(d.tool,rel),bw:r1(r.width),bh:r1(r.height),fit,ox:r1(r.left+scrollX),oy:r1(r.top+scrollY)};
 const name={box:'Box',arrow:'Arrow',pen:'Drawing',highlight:'Highlight'}[d.tool];
 compose({sel:el?cssPath(el):'',anchor:name+' on '+(el?label(el):'page'),rx:(a.x-r.left)/Math.max(1,r.width),ry:(a.y-r.top)/Math.max(1,r.height),
  px:a.x+scrollX,py:a.y+scrollY,shape},Math.min(B.right,innerWidth-20),Math.min(B.bottom,innerHeight-20));
 setMode(false)}
layer.addEventListener('pointerup',finish);layer.addEventListener('pointercancel',e=>{if(draw&&e.pointerId===draw.id)cancelDraw()});
layer.addEventListener('lostpointercapture',e=>{if(draw&&e.pointerId===draw.id)cancelDraw()});
for(const ev of['click','dblclick','contextmenu','selectstart','dragstart'])layer.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation()});
// the layer covers the page in comment mode; pass wheel scrolling to the scrollable element underneath
layer.addEventListener('wheel',e=>{let el=target(e.clientX,e.clientY);
 while(el&&!isPage(el)){const s=getComputedStyle(el);if(/(auto|scroll)/.test(s.overflowY+s.overflowX)&&(el.scrollHeight>el.clientHeight||el.scrollWidth>el.clientWidth)){el.scrollBy(e.deltaX,e.deltaY);e.preventDefault();return}el=el.parentElement}},{passive:false});

// selected text -> a "Comment" chip next to it
document.addEventListener('mouseup',e=>{if(mode||e.composedPath().includes(host))return;setTimeout(()=>{const s=getSelection();
 if(!s||s.isCollapsed||!String(s).trim()){chip.style.display='none';return}
 const r=s.getRangeAt(0).getBoundingClientRect();Object.assign(chip.style,{display:'block',left:Math.min(innerWidth-110,r.right+6)+'px',top:Math.max(6,r.top-40)+'px'});
 chip.onclick=()=>{const el=s.anchorNode.nodeType===1?s.anchorNode:s.anchorNode.parentElement,er=el.getBoundingClientRect();
  compose({sel:cssPath(el),anchor:'“'+String(s).trim().slice(0,120)+'”',quote:String(s).trim().slice(0,500),rx:(r.left-er.left)/Math.max(1,er.width),ry:(r.top-er.top)/Math.max(1,er.height),
   px:r.left+scrollX,py:r.top+scrollY},r.right,r.bottom);chip.style.display='none'}},0)});

function place(p,x,y){p.style.left=Math.max(12,Math.min(innerWidth-312,x+14))+'px';p.style.top=Math.max(12,Math.min(innerHeight-p.offsetHeight-12,y+14))+'px'}
function closePop(){pops.innerHTML='';open=null;if(pending){pending=null;drawPins()}}
// focus after the pointer sequence has ended, so the trailing mouseup/click cannot steal it
const focusLater=ta=>{ta.focus({preventScroll:true});setTimeout(()=>{ta.focus({preventScroll:true});requestAnimationFrame(()=>{if(root.activeElement!==ta)ta.focus({preventScroll:true})})},0)};
function compose(a,x,y){closePop();const p=document.createElement('div');p.className='pop';
 p.innerHTML=`<div class="anchor">${esc(a.anchor)}</div><textarea placeholder="Your feedback"></textarea><div class="row"><span class="sp">⌘↵</span><button class="sm x">Cancel</button><button class="sm pri go">Comment</button></div>`;
 pops.append(p);place(p,x,y);const ta=p.querySelector('textarea');focusLater(ta);
 if(a.shape){pending=a;drawPins()}
 const send=async()=>{const body=ta.value.trim();if(!body)return;
  const row={kind:'comment',id:'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,5),proto,path:location.pathname,hash:location.hash,...a,body,author:'you',vw:innerWidth};
  rows.push(row);closePop();await post(row)};
 p.querySelector('.go').onclick=send;p.querySelector('.x').onclick=closePop;
 ta.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))send();if(e.key==='Escape')closePop()}}

const threads=()=>rows.filter(r=>r.kind==='comment'&&r.proto===proto);
const replies=id=>rows.filter(r=>r.kind==='reply'&&r.parent===id);
const resolved=id=>rows.some(r=>r.kind==='resolve'&&r.parent===id);
const anchorEl=c=>{let el=null;try{el=c.sel&&document.querySelector(c.sel)}catch{}return el};
function pos(c){const el=anchorEl(c);
 if(el){const r=el.getBoundingClientRect();if(r.width||r.height)return [r.left+c.rx*r.width,r.top+c.ry*r.height]}
 return [c.px-scrollX,c.py-scrollY]}
function shapeSvg(c,cl){const s=c.shape;if(!s||!s.d)return '';const el=anchorEl(c);let tx=s.ox-scrollX,ty=s.oy-scrollY,sx=1,sy=1;
 if(el){const r=el.getBoundingClientRect();if(r.width||r.height){tx=r.left;ty=r.top;if(s.fit){sx=r.width/Math.max(1,s.bw);sy=r.height/Math.max(1,s.bh)}}}
 const d=esc(s.d),t=esc(s.tool);
 return `<g class="${cl}${c.id&&c.id===hot?' hot':''}" data-id="${esc(c.id||'')}" transform="translate(${r1(tx)} ${r1(ty)}) scale(${sx} ${sy})"><path class="hit ${t}" d="${d}"/><path class="v ${t}" d="${d}"/></g>`}
const klass=c=>resolved(c.id)?'res':replies(c.id).some(r=>r.author==='claude')?'rep':'';
function drawPins(){const ts=threads();$('.lst').textContent=ts.filter(t=>!resolved(t.id)).length+' open';
 pinsEl.innerHTML=ts.map((c,i)=>{const [x,y]=pos(c);
  return `<div class="pin ${klass(c)}${c.id===hot?' hot':''}" data-id="${c.id}" style="left:${x}px;top:${y}px" title="${esc(c.body)}">${i+1}</div>`}).join('');
 const live=shapesEl.querySelector('.live');
 shapesEl.innerHTML=ts.map(c=>shapeSvg(c,klass(c))).join('')+(pending?shapeSvg(pending,'draft'):'');if(live)shapesEl.append(live);
 pinsEl.querySelectorAll('.pin').forEach(el=>el.onclick=()=>thread(el.dataset.id));
 if(open){const c=ts.find(t=>t.id===open);const p=pops.firstChild;if(c&&p&&!p.contains(root.activeElement)){const [x,y]=pos(c);place(p,x,y)}}}
// hovering a shape lights its pin and the other way round
function setHot(id){if(hot===id)return;hot=id;root.querySelectorAll('[data-id]').forEach(e=>e.classList.toggle('hot',!!id&&e.dataset.id===id))}
for(const el of[pinsEl,shapesEl,list]){
 el.addEventListener('pointerover',e=>{const t=e.target.closest?.('[data-id]');if(t&&t.dataset.id)setHot(t.dataset.id)});
 el.addEventListener('pointerout',e=>{const t=e.relatedTarget?.closest?.('[data-id]');if(!t||t.dataset.id!==hot)setHot(null)})}
shapesEl.addEventListener('click',e=>{const t=e.target.closest?.('g[data-id]');if(t&&t.dataset.id)thread(t.dataset.id)});
function thread(id){const ts=threads(),c=ts.find(t=>t.id===id);if(!c)return;closePop();open=id;const p=document.createElement('div');p.className='pop';
 const msg=r=>`<div><div class="who">${r.author==='claude'?'Claude':'You'} · ${new Date(r.t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})}</div><div class="msg ${r.author==='claude'?'claude':''}">${esc(r.body)}</div></div>`;
 p.innerHTML=`<div class="anchor">${ts.indexOf(c)+1} · ${esc(c.anchor)}</div>${[c,...replies(id)].map(msg).join('')}
 <textarea placeholder="Reply"></textarea><div class="row"><span class="sp">${resolved(id)?'Resolved':''}</span><button class="sm rs">${resolved(id)?'Reopen':'Resolve'}</button><button class="sm pri go">Reply</button></div>`;
 pops.append(p);const [x,y]=pos(c);place(p,x,y);const ta=p.querySelector('textarea');
 p.querySelector('.go').onclick=async()=>{const body=ta.value.trim();if(!body)return;await post({kind:'reply',parent:id,proto,body,author:'you'});thread(id)};
 p.querySelector('.rs').onclick=async()=>{await post({kind:resolved(id)?'reopen':'resolve',parent:id,proto,author:'you'});closePop()};
 ta.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))p.querySelector('.go').click();if(e.key==='Escape')closePop()}}
function drawList(){if(list.style.display!=='block')return;const ts=threads();
 list.innerHTML=ts.length?ts.map((c,i)=>`<div class="it" data-id="${c.id}"><span class="n">${i+1}</span>${esc(c.body)}<div class="who">${esc(c.anchor)} · ${replies(c.id).length} replies${resolved(c.id)?' · resolved':''}</div></div>`).join(''):'<div class="it">No comments yet. Press C.</div>';
 list.querySelectorAll('.it[data-id]').forEach(el=>el.onclick=()=>{const c=ts.find(t=>t.id===el.dataset.id);
  try{document.querySelector(c.sel)?.scrollIntoView({block:'center'})}catch{}setTimeout(()=>thread(c.id),300)})}

async function post(row){await fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});await load()}
async function load(){try{const all=await (await fetch('/feedback',{cache:'no-store'})).json();
 // a reopen after a resolve cancels it
 const rs=new Map();for(const r of all)if(r.kind==='resolve'||r.kind==='reopen')rs.set(r.parent,r.kind);
 rows=all.filter(r=>r.kind!=='resolve'&&r.kind!=='reopen').concat([...rs].filter(([,k])=>k==='resolve').map(([p])=>({kind:'resolve',parent:p})));
 const was=pops.firstChild&&open&&!pops.firstChild.contains(root.activeElement);drawPins();drawList();if(was)thread(open)}catch{}}
(document.body||document.documentElement).append(host);
addEventListener('scroll',drawPins,true);addEventListener('resize',drawPins);
setInterval(()=>{if(!draw)drawPins()},700);setInterval(load,4000);load();
})();
