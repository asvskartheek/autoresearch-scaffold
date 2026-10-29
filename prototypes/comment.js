// Comment on anything: press C (or the button), click any element or select text, write. Pins are threaded and stored
// by serve.py in feedback.jsonl as {kind:'comment'|'reply'|'resolve', ...}. Injected into every prototype page.
(()=>{
if(window.__arxComments)return;window.__arxComments=1;
const proto=location.pathname.split('/').filter(Boolean)[0]||'hub';
const host=document.createElement('div');host.id='arx-comments';
host.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483646';
const root=host.attachShadow({mode:'open'});
root.innerHTML=`<style>
:host{all:initial}
*{box-sizing:border-box;font:13px/1.45 "IBM Plex Sans",Inter,system-ui,sans-serif}
.fab{position:fixed;right:16px;bottom:16px;pointer-events:auto;display:flex;gap:6px}
.btn{height:34px;padding:0 14px;border-radius:17px;border:1px solid #3a434b;background:#13171b;color:#eef1f3;cursor:pointer;font-weight:500;box-shadow:0 2px 10px rgba(0,0,0,.35)}
.btn.on{background:#f0b43c;color:#16181a;border-color:#f0b43c}
.btn b{font:600 11px ui-monospace,Menlo,monospace;opacity:.7;margin-left:6px}
.hl{position:fixed;border:2px solid #f0b43c;border-radius:4px;background:rgba(240,180,60,.08);pointer-events:none;display:none}
.pin{position:fixed;width:24px;height:24px;margin:-12px 0 0 -12px;border-radius:12px 12px 12px 2px;background:#f0b43c;color:#16181a;
 font:700 11px ui-monospace,Menlo,monospace;display:flex;align-items:center;justify-content:center;pointer-events:auto;cursor:pointer;border:2px solid #16181a}
.pin.res{background:#4cc38a;opacity:.6}.pin.rep{background:#5cb8cc}
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
.list .it{padding:8px 10px;border-bottom:1px solid #232a30;cursor:pointer}.list .it:hover{background:#1a1f24}
.list .n{font:700 11px ui-monospace,Menlo,monospace;color:#f0b43c;margin-right:6px}
.chip{position:fixed;pointer-events:auto;display:none}
</style>
<div class="hl"></div><div class="pins"></div><div class="pops"></div>
<div class="list"></div><div class="chip"><button class="btn on">Comment</button></div>
<div class="fab"><button class="btn lst" title="All comments on this page">0</button><button class="btn mode">Comment<b>C</b></button></div>`;
const $=s=>root.querySelector(s),hl=$('.hl'),pinsEl=$('.pins'),pops=$('.pops'),list=$('.list'),chip=$('.chip');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let mode=false,rows=[],open=null;

function cssPath(el){const parts=[];while(el&&el.nodeType===1&&el!==document.body){
 if(el.id&&!/^\d/.test(el.id)){parts.unshift('#'+CSS.escape(el.id));break}
 let i=1,s=el;while((s=s.previousElementSibling))if(s.tagName===el.tagName)i++;
 parts.unshift(el.tagName.toLowerCase()+`:nth-of-type(${i})`);el=el.parentElement}
 return parts.join('>')}
const label=el=>{const t=(el.innerText||el.textContent||el.getAttribute?.('aria-label')||'').trim().replace(/\s+/g,' ');
 return (t||el.tagName.toLowerCase()).slice(0,90)};
const target=(x,y)=>{host.style.display='none';const el=document.elementFromPoint(x,y);host.style.display='';return el};

function setMode(on){mode=on;$('.mode').classList.toggle('on',on);document.documentElement.style.cursor=on?'crosshair':'';if(!on)hl.style.display='none'}
$('.mode').onclick=()=>setMode(!mode);
$('.lst').onclick=()=>{list.style.display=list.style.display==='block'?'none':'block';drawList()};
addEventListener('keydown',e=>{const tag=(e.composedPath()[0]||{}).tagName;if(/INPUT|TEXTAREA|SELECT/.test(tag)||e.target.isContentEditable)return;
 if((e.key==='c'||e.key==='C')&&!e.metaKey&&!e.ctrlKey&&!e.altKey){e.preventDefault();e.stopPropagation();setMode(!mode)}
 if(e.key==='Escape'){setMode(false);closePop()}},true);
addEventListener('mousemove',e=>{if(!mode)return;const el=target(e.clientX,e.clientY);if(!el||el===document.documentElement||el===document.body){hl.style.display='none';return}
 const r=el.getBoundingClientRect();Object.assign(hl.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'})},true);
for(const ev of['mousedown','mouseup','click','pointerdown','pointerup','dblclick'])addEventListener(ev,e=>{
 if(!mode||e.composedPath().includes(host))return;e.preventDefault();e.stopPropagation();e.stopImmediatePropagation?.();
 if(ev!=='click')return;const el=target(e.clientX,e.clientY);if(!el)return;const r=el.getBoundingClientRect();
 compose({sel:cssPath(el),anchor:label(el),rx:(e.clientX-r.left)/Math.max(1,r.width),ry:(e.clientY-r.top)/Math.max(1,r.height),
  px:e.clientX+scrollX,py:e.clientY+scrollY},e.clientX,e.clientY);setMode(false)},true);
// selected text -> a "Comment" chip next to it
document.addEventListener('mouseup',e=>{if(mode||e.composedPath().includes(host))return;setTimeout(()=>{const s=getSelection();
 if(!s||s.isCollapsed||!String(s).trim()){chip.style.display='none';return}
 const r=s.getRangeAt(0).getBoundingClientRect();Object.assign(chip.style,{display:'block',left:Math.min(innerWidth-110,r.right+6)+'px',top:Math.max(6,r.top-40)+'px'});
 chip.onclick=()=>{const el=s.anchorNode.nodeType===1?s.anchorNode:s.anchorNode.parentElement,er=el.getBoundingClientRect();
  compose({sel:cssPath(el),anchor:'“'+String(s).trim().slice(0,120)+'”',quote:String(s).trim().slice(0,500),rx:(r.left-er.left)/Math.max(1,er.width),ry:(r.top-er.top)/Math.max(1,er.height),
   px:r.left+scrollX,py:r.top+scrollY},r.right,r.bottom);chip.style.display='none'}},0)});

function place(p,x,y){p.style.left=Math.max(12,Math.min(innerWidth-312,x+14))+'px';p.style.top=Math.max(12,Math.min(innerHeight-p.offsetHeight-12,y+14))+'px'}
function closePop(){pops.innerHTML='';open=null}
function compose(a,x,y){closePop();const p=document.createElement('div');p.className='pop';
 p.innerHTML=`<div class="anchor">${esc(a.anchor)}</div><textarea placeholder="Your feedback"></textarea><div class="row"><span class="sp">⌘↵</span><button class="sm x">Cancel</button><button class="sm pri go">Comment</button></div>`;
 pops.append(p);place(p,x,y);const ta=p.querySelector('textarea');ta.focus();
 const send=async()=>{const body=ta.value.trim();if(!body)return;await post({kind:'comment',id:'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,5),
  proto,path:location.pathname,hash:location.hash,...a,body,author:'you',vw:innerWidth});closePop()};
 p.querySelector('.go').onclick=send;p.querySelector('.x').onclick=closePop;
 ta.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))send();if(e.key==='Escape')closePop()}}

const threads=()=>rows.filter(r=>r.kind==='comment'&&r.proto===proto);
const replies=id=>rows.filter(r=>r.kind==='reply'&&r.parent===id);
const resolved=id=>rows.some(r=>r.kind==='resolve'&&r.parent===id);
function pos(c){let el=null;try{el=c.sel&&document.querySelector(c.sel)}catch{}
 if(el){const r=el.getBoundingClientRect();if(r.width||r.height)return [r.left+c.rx*r.width,r.top+c.ry*r.height]}
 return [c.px-scrollX,c.py-scrollY]}
function drawPins(){const ts=threads();$('.lst').textContent=ts.filter(t=>!resolved(t.id)).length+' open';
 pinsEl.innerHTML=ts.map((c,i)=>{const [x,y]=pos(c),rp=replies(c.id),cl=resolved(c.id)?'res':rp.some(r=>r.author==='claude')?'rep':'';
  return `<div class="pin ${cl}" data-id="${c.id}" style="left:${x}px;top:${y}px" title="${esc(c.body)}">${i+1}</div>`}).join('');
 pinsEl.querySelectorAll('.pin').forEach(el=>el.onclick=()=>thread(el.dataset.id));
 if(open){const c=ts.find(t=>t.id===open);const p=pops.firstChild;if(c&&p&&!p.contains(root.activeElement)){const [x,y]=pos(c);place(p,x,y)}}}
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
setInterval(drawPins,700);setInterval(load,4000);load();
})();
