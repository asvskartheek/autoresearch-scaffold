'use strict';
// Teaching methods on Brief cards (autoresearch/teach.py). learn.js draws predict cards; a card whose `method` is
// sketch, spot, prototype, code or explain is drawn here. Answers go to api/teach, which grades them and returns the
// card with its reveal. "Another way" skips to the next method that fits the card; the side panel shows how each
// method has gone for this person.
const TEACH=(()=>{
const ST={};const st=c=>ST[c.id]||(ST[c.id]={t0:performance.now()});
const NAMES={predict:'Predict',sketch:'Sketch',spot:'Spot the error',prototype:'Prototype',code:'Code',explain:'Explain back'};
const ICO={predict:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',sketch:'<path d="M4 18c3-6 6 2 9-4s4-6 7-8"/>',
 spot:'<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',prototype:'<path d="M4 12h16"/><circle cx="9" cy="12" r="3"/>',
 code:'<path d="M9 7l-5 5 5 5M15 7l5 5-5 5"/>',explain:'<path d="M5 6h14v9H9l-4 4z"/>'};
const ico=m=>`<svg viewBox="0 0 24 24" class="t-ico">${ICO[m]||''}</svg>`;
const amt=(u,x)=>lamt(u||'pts',x);

// ---------- sketch: drag the delta and the ends of its interval, or each bar (pointer or arrow keys)
// the axis is the card's own range in its own unit; the sketch opens on ±view and zooms between the range and a
// twentieth of it; after the reveal it widens to hold the truth, so both sit on one scale
const niceD=x=>{const m=10**Math.floor(Math.log10(x));return [10,5,2.5,2,1].map(k=>k*m).find(v=>v<=x+1e-12)||m},niceU=x=>{const m=10**Math.floor(Math.log10(x));return [1,2,2.5,5,10].map(k=>k*m).find(v=>v>=x-1e-12)};
const zFull=t=>Math.max(Math.abs(t.min),Math.abs(t.max));
function ciWin(t,s){const z=s.z??t.view??zFull(t);let a=Math.max(t.min,-z),b=Math.min(t.max,z);
 if(s.tv){const v=s.tv,k=s.sk||{},xs=[v.lo,v.hi,v.delta,k.lo,k.hi,t.bar].filter(q=>q!=null&&isFinite(q));const lo=Math.min(a,...xs),hi=Math.max(b,...xs),pad=(hi-lo)*.06;
  if(lo<a)a=lo-pad;if(hi>b)b=hi+pad}
 return [a,b]}
function zoom(c,dir){const s=st(c),t=c.task||s.tk,f=zFull(t),z=s.z??t.view??f;s.z=dir>0?Math.max(f/20,niceD(z/2)):Math.min(f,niceU(z*2));render(true)}
function sketchCI(c,s){
 const t=c.task||s.tk;s.tv=c.reveal?.viz||null;if(!s.sk){const [a0,b0]=ciWin(t,s);s.sk={delta:0,lo:-(b0-a0)*.08,hi:(b0-a0)*.08}}const k=s.sk;
 const W=LW(),H=92,Lx=16,R=W-16,[a,b]=ciWin(t,s),x=q=>Lx+(Math.max(a,Math.min(b,q))-a)/(b-a)*(R-Lx),span=b-a;
 const stp=nstep(span,W<420?5:9);let g='';
 for(let q=Math.ceil(a/stp)*stp;q<=b+1e-9;q+=stp){const qq=+q.toPrecision(6);g+=`<line x1="${x(qq)}" x2="${x(qq)}" y1="30" y2="60" stroke="var(--grid)"/><text x="${x(qq)}" y="76" text-anchor="middle">${qq>0?'+':qq<0?'−':''}${grp(Math.abs(qq))}</text>`}
 const tr=c.reveal?.viz;const truth=tr?`<line x1="${x(tr.lo)}" x2="${x(tr.hi)}" y1="56" y2="56" stroke="var(--text)" stroke-width="4" stroke-linecap="round" opacity=".5"/><circle cx="${x(tr.delta)}" cy="56" r="5" fill="var(--text)"/><text x="${R}" y="14" text-anchor="end" class="mono strong">${amt(t.unit,tr.delta)} [${amt(t.unit,tr.lo)}, ${amt(t.unit,tr.hi)}]</text>`:'';
 const bar=t.bar!=null&&t.bar>=a&&t.bar<=b?`<line x1="${x(t.bar)}" x2="${x(t.bar)}" y1="24" y2="64" stroke="var(--warning)" stroke-width="2" stroke-dasharray="4 3"/><text x="${x(t.bar)}" y="88" text-anchor="middle" style="fill:var(--warning)">bar ${amt(t.unit,t.bar)}</text>`:'';
 const lab=`${amt(t.unit,k.delta)} [${amt(t.unit,k.lo)}, ${amt(t.unit,k.hi)}]`;
 return `<svg class="lv t-sk" id="tsk" data-kind="ci" viewBox="0 0 ${W} ${H}" role="slider" tabindex="${c.pred?-1:0}" aria-label="your sketch: arrow keys move it, up and down widen the interval" aria-valuetext="${lab}">
  <text x="${Lx}" y="14" class="mono strong" style="fill:var(--accent)">${lab}</text>${g}
  <line x1="${x(0)}" x2="${x(0)}" y1="24" y2="64" stroke="var(--text)" stroke-width="1.5"/>${bar}
  <line x1="${x(k.lo)}" x2="${x(k.hi)}" y1="44" y2="44" stroke="var(--accent)" stroke-width="10" stroke-linecap="round" opacity=".3"/>
  <rect x="${x(k.lo)-4}" y="34" width="8" height="20" rx="3" fill="var(--accent)"/><rect x="${x(k.hi)-4}" y="34" width="8" height="20" rx="3" fill="var(--accent)"/>
  <circle cx="${x(k.delta)}" cy="44" r="8" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>${truth}</svg>
  ${c.pred?'':`<div class="t-zoom"><button class="btn" data-t="zout" aria-label="Zoom out" title="Zoom out (−)" ${b-a>=zFull(t)*1.99?'disabled':''}>−</button><button class="btn" data-t="zin" aria-label="Zoom in" title="Zoom in (+)" ${(s.z??t.view??zFull(t))<=zFull(t)/20+1e-9?'disabled':''}>+</button></div>`}`;
}
function sketchBars(c,s){
 const t=c.task||s.tk,W=LW(),rh=44,H=t.rows.length*rh+4,R=W-(W<420?96:120);
 if(!s.sb)s.sb=t.rows.map(()=>t.max/2);const tr=c.reveal?.viz?.rows?.filter(r=>r.v!=null&&r.hl!==3),row=s.row||0;
 const M=tr?Math.max(t.max,...tr.map(r=>r.v*1.05)):t.max;  // the truth stays on the sketch's scale, widened only to fit
 const fmt=(r,v)=>r.unit?(grp(v)+' '+r.unit):r.n?`${Math.round(v*r.n).toLocaleString()} of ${r.n.toLocaleString()}`:pct(v);
 return `<svg class="lv t-sk" id="tsk" data-kind="bars" viewBox="0 0 ${W} ${H}" role="slider" tabindex="${c.pred?-1:0}" aria-label="drag each bar: up and down pick a bar, left and right set it" aria-valuetext="${esc(t.rows[row]?.label||'')}: ${fmt(t.rows[row]||{},s.sb[row])}">${t.rows.map((r,i)=>{const y=i*rh,v=s.sb[i],w=v/M*R;
  const tv=tr&&tr[i]?tr[i].v/M*R:null;
  return `<text x="0" y="${y+12}" ${i===row&&!c.pred?'class="strong"':''}>${esc(r.label)}${r.tag?' · '+esc(r.tag):''}</text><rect x="0" y="${y+18}" width="${R}" height="16" rx="3" fill="var(--active)" data-row="${i}"/>
   <rect x="0" y="${y+18}" width="${Math.max(2,w)}" height="16" rx="3" fill="var(--accent)" opacity=".75" data-row="${i}" pointer-events="none"/>
   ${tv!=null?`<line x1="${tv}" x2="${tv}" y1="${y+14}" y2="${y+38}" stroke="var(--text)" stroke-width="3"/>`:''}
   <text x="${Math.min(R,w)+6}" y="${y+31}" class="mono" style="fill:var(--accent)">${fmt(r,v)}${tv!=null?`<tspan class="strong" style="fill:var(--text)"> · ${fmt(r,tr[i].v)}</tspan>`:''}</text>`}).join('')}</svg>`;
}
// redraw the sketch in place; keep keyboard focus on it
function redrawSketch(c,s){const g=document.getElementById('tsk');if(!g)return;const f=document.activeElement===g;
 g.outerHTML=(c.task||s.tk).kind==='bars'?sketchBars(c,s):sketchCI(c,s);if(f)document.getElementById('tsk')?.focus()}
// move one part of the CI sketch to v: the delta carries its interval, the ends stay on their side of the delta;
// everything stays on the axis
function setCI(t,s,which,v){const [a,b]=ciWin(t,s),k=s.sk;v=Math.max(a,Math.min(b,v));
 if(which==='delta'){const dl=k.delta-k.lo,dh=k.hi-k.delta;v=Math.max(a+dl,Math.min(b-dh,v));k.delta=v;k.lo=v-dl;k.hi=v+dh}
 else if(which==='lo')k.lo=Math.min(v,k.delta);else k.hi=Math.max(v,k.delta);k.moved=true}
function dragSketch(e,c){
 const svg0=e.target.closest('#tsk');if(!svg0||c.pred||e.button>0)return;const s=st(c),t=c.task||s.tk;
 // measure against the svg on the page now: each redraw replaces the element, and a detached one has no size
 const live=()=>document.getElementById('tsk')||svg0,vw=svg0.viewBox.baseVal.width;
 const toX=ev=>{const r=live().getBoundingClientRect();return r.width?(ev.clientX-r.left)/r.width*vw:null},toY=ev=>{const g=live(),r=g.getBoundingClientRect();return r.height?(ev.clientY-r.top)/r.height*g.viewBox.baseVal.height:null};
 const px0=toX(e);if(px0==null)return;let move;
 if(svg0.dataset.kind==='ci'){const Lx=16,R=vw-16,[a,b]=ciWin(t,s),val=px=>a+(px-Lx)/(R-Lx)*(b-a),pxOf=v=>Lx+(v-a)/(b-a)*(R-Lx),k=s.sk,step=nstep(b-a,200);
  const dist=p=>Math.abs(pxOf(k[p])-px0),near=['delta','lo','hi'].filter(p=>dist(p)<=12),dpx=pxOf(k.delta);
  // on a collapsed interval the side of the press picks the end, so lo and hi can always be pulled out again
  const which=near.includes('lo')&&px0<dpx-2?'lo':near.includes('hi')&&px0>dpx+2?'hi':near.includes('delta')?'delta':near[0]||['delta','lo','hi'].sort((p,q)=>dist(p)-dist(q))[0];
  const off=near.length?k[which]-val(px0):0;  // a grabbed handle keeps its offset from the pointer: it never jumps
  move=ev=>{const px=toX(ev);if(px==null)return;setCI(t,s,which,Math.round((val(px)+off)/step)*step);redrawSketch(c,s)};
  if(!near.length)move(e)}
 else{const R=vw-(vw<420?96:120),y0=toY(e);if(y0==null)return;const i=Math.max(0,Math.min(t.rows.length-1,Math.floor(y0/44)));s.row=i;
  const off=Math.abs(px0-s.sb[i]/t.max*R)<=12?s.sb[i]-px0/R*t.max:0;
  move=ev=>{const px=toX(ev);if(px==null)return;s.sb[i]=Math.max(0,Math.min(t.max,px/R*t.max+off));if(!t.rows[i].unit&&t.rows[i].n)s.sb[i]=Math.round(s.sb[i]*t.rows[i].n)/t.rows[i].n;s.sbm=true;redrawSketch(c,s)};
  if(!off)move(e)}
 const up=()=>{removeEventListener('pointermove',move);removeEventListener('pointerup',up);removeEventListener('pointercancel',up);render(true)};
 addEventListener('pointermove',move);addEventListener('pointerup',up);addEventListener('pointercancel',up);e.preventDefault();
}
// arrow keys: left and right move the delta (or the picked bar), up and down widen the interval (or pick a bar); shift ×10
function keySketch(e,c){
 const s=st(c),t=c.task||s.tk,big=e.shiftKey?10:1,k=e.key;
 if(t.kind==='bars'){if(!s.sb)return false;const i=s.row||0;
  if(k==='ArrowUp'||k==='ArrowDown'){s.row=Math.max(0,Math.min(t.rows.length-1,i+(k==='ArrowDown'?1:-1)))}
  else if(k==='ArrowLeft'||k==='ArrowRight'){const r=t.rows[i],stp=!r.unit&&r.n?Math.max(1/r.n,t.max/200):t.max/100;s.sb[i]=Math.max(0,Math.min(t.max,s.sb[i]+(k==='ArrowRight'?1:-1)*stp*big));s.sbm=true}
  else return false}
 else{if(!s.sk)return false;const [a,b]=ciWin(t,s),stp=nstep(b-a,100)*big,kk=s.sk;
  if(k==='ArrowLeft'||k==='ArrowRight')setCI(t,s,'delta',kk.delta+(k==='ArrowRight'?1:-1)*stp);
  else if(k==='ArrowUp'||k==='ArrowDown'){const w=Math.max(0,Math.min(kk.delta-kk.lo,kk.hi-kk.delta)+(k==='ArrowUp'?1:-1)*stp);kk.lo=Math.max(a,kk.delta-w);kk.hi=Math.min(b,kk.delta+w);kk.moved=true}
  else return false}
 redrawSketch(c,s);return true;
}

// ---------- spot: an example at the card's n with one number made inconsistent (the card's own figure is its answer)
function spotBody(c,s){
 const t=c.task||s.tk,v=t.viz,ans=c.reveal?.show?.wrong,u=v.unit||'pts';
 const opts=[['counts',`${v.wins.toLocaleString()} fixed · ${v.losses.toLocaleString()} broken`],['delta','Δ '+amt(u,v.delta)],['interval',`[${amt(u,v.lo)}, ${amt(u,v.hi)}]`]];
 return vizCI(v)+`<div class="opts t-spot" style="--n:3">${opts.map(([k,l],i)=>`<button class="opt${s.pick===k?' on':''}${ans?k===ans?' truth':s.pick===k?' wrong':'':''}" data-t="pick" data-v="${k}" ${c.pred?'disabled':''}><kbd>${i+1}</kbd>${esc(l)}</button>`).join('')}</div>`;
}

// ---------- prototype: drag n, the interval narrows as 1/√n
function protoSVG(t,n,mark){
 const W=LW(),H=96,Lx=16,R=W-16,half=(t.hi-t.lo)/2*Math.sqrt(t.n/n),lo=t.delta-half,hi=t.delta+half;
 const ext=Math.max(Math.abs(t.lo),Math.abs(t.hi),Math.abs(t.delta)*2,2)*1.15,x=q=>Lx+(q+ext)/(2*ext)*(R-Lx),clear=lo>0||hi<0;
 const col=clear?(t.delta>0?'var(--positive)':'var(--negative)'):'var(--muted)';
 let s=`<line x1="${x(0)}" x2="${x(0)}" y1="20" y2="70" stroke="var(--text)" stroke-width="1.5"/>`;
 s+=`<line x1="${x(Math.max(-ext,lo))}" x2="${x(Math.min(ext,hi))}" y1="46" y2="46" stroke="${col}" stroke-width="10" stroke-linecap="round" opacity=".4" style="transition:all .12s"/><circle cx="${x(t.delta)}" cy="46" r="6" fill="${col}"/>`;
 s+=`<text x="${Lx}" y="14" class="mono strong">n = ${Math.round(n).toLocaleString()}</text><text x="${R}" y="14" text-anchor="end" class="mono" style="fill:${col}">[${amt('pts',lo)}, ${amt('pts',hi)}]</text>`;
 if(mark)s+=`<text x="${Lx}" y="90" class="mono">measured at n = ${t.n.toLocaleString()}</text>`;
 return `<svg class="lv" id="tproto" viewBox="0 0 ${W} ${H}">${s}</svg>`;
}
const pLo=t=>Math.max(4,t.n/20),pHi=t=>t.n*60,toN=(t,f)=>Math.exp(Math.log(pLo(t))+f*(Math.log(pHi(t))-Math.log(pLo(t)))),toF=(t,n)=>(Math.log(n)-Math.log(pLo(t)))/(Math.log(pHi(t))-Math.log(pLo(t)));
function protoBody(c,s){
 const t=c.task||s.tk,need=c.reveal?.show?.need;if(!t)return '';
 if(s.n==null)s.n=t.n;
 return `<div id="tpw">${protoSVG(t,s.n,true)}</div><input type="range" class="t-range" id="tpn" min="0" max="1000" value="${Math.round(1000*toF(t,s.n))}" ${c.pred?'disabled':''} aria-label="n">
  ${need?`<div class="t-need">${protoSVG(t,need,false)}</div>`:''}`;
}

// ---------- code: one line, evaluated live on the card's own numbers
const codeVal=(t,e)=>{e=String(e||'').trim();if(!e||!/^[\d\s+\-*/().a-z_]*$/i.test(e))return null;const ids=e.match(/[a-z_]+/gi)||[];if(ids.some(i=>!(i in t.vars)))return null;
 try{const v=Function(...Object.keys(t.vars),'return ('+e+')')(...Object.values(t.vars));return isFinite(v)?v:null}catch(_){return null}};
function codeBody(c,s){
 const t=c.task||s.tk,sh=c.reveal?.show;if(!t)return '';const v=codeVal(t,s.code);
 return `<pre class="t-code"><span class="k">const</span> fixed = <b>${t.vars.fixed}</b>, broken = <b>${t.vars.broken}</b>, n = <b>${t.vars.n}</b>;
<span class="k">const</span> delta_pts = <input id="tcode" spellcheck="false" autocomplete="off" value="${esc(s.code||'')}" ${c.pred?'disabled':''} placeholder="…">;
<span class="c">// ${v==null?'= ?':'= '+(+v.toFixed(2))+' pts'}</span>${sh?`
<span class="c">// ${(sh.ok??(sh.got!=null&&Math.abs(sh.got-sh.value)<=Math.max(.05,Math.abs(sh.value)*.01)))?'✓':'✗'} ${esc(sh.line)} = ${sh.value} pts</span>${sh.card!=null&&c.reveal?.viz?`
<span class="c">// this card: 100 * (${c.reveal.viz.wins} - ${c.reveal.viz.losses}) / ${c.reveal.viz.n} = ${amt('pts',sh.card)}</span>`:''}`:''}</pre>`;
}

// ---------- explain: one sentence; the ideas it names light up after
function explainBody(c,s){
 const ideas=(c.task||s.tk)?.ideas||[],named=c.reveal?.show?.named;
 return `<textarea class="t-ex" id="tex" rows="3" placeholder="In one sentence" ${c.pred?'disabled':''}>${esc(s.ex||'')}</textarea>
  <div class="t-ideas">${ideas.map(i=>`<span class="tchip${named?named.includes(i)?' ok':' no':''}">${named?named.includes(i)?'✓ ':'✗ ':''}${esc(i)}</span>`).join('')}</div>`;
}

// the task stays with the card's state, so the reveal can still draw it (the server sends it only before an answer)
function body(c){const s=st(c);if(c.task&&(!s.tk||s.m!==c.method)){s.tk=c.task;s.m=c.method}const t=c.task||s.tk;if(!t||s.m!==c.method)return '';
 return c.method==='sketch'?(t.kind==='bars'?sketchBars(c,s):sketchCI(c,s)):c.method==='spot'?spotBody(c,s):
  c.method==='prototype'?protoBody(c,s):c.method==='code'?codeBody(c,s):c.method==='explain'?explainBody(c,s):''}
function strip(c){const ms=c.methods||[];return `<div class="t-strip">${ms.map(m=>`<span class="t-m${m===c.method?' on':''}" title="${esc(NAMES[m])}">${ico(m)}</span>`).join('')}<b>${esc(NAMES[c.method]||'')}</b></div>`}

function card(c){
 const s=st(c);const n=L.b.cards.length,i=L.cur,p=c.pred,rv=c.reveal;
 const t=c.task||s.tk,ex=t&&(t.example||t.viz?.example)?`Example at n = ${(t.n||t.viz?.n||t.vars?.n||0).toLocaleString()}: `:'';
 const q=c.method==='spot'?ex+'one number is wrong.':c.method==='prototype'?ex+'drag n to where its interval just clears zero.':c.method==='code'?ex+'the paired gain, in points.':c.q;
 const ready=c.method==='sketch'?!!(s.sk?.moved||s.sbm):c.method==='spot'?s.pick!=null:c.method==='code'?codeVal(c.task||s.tk,s.code)!=null:c.method==='explain'?(s.ex||'').trim().length>8:true;
 let reveal='';
 if(p&&rv){const verdict=p.hit==null?'<span class="vd open">Open</span>':p.hit?'<span class="vd ok">✓ Right</span>':'<span class="vd no">✗ Not quite</span>';
  const own=q!==c.q?`<p class="ctx t-own">${esc(c.q)}</p>`:'';  // the method asked about an example: the card's own question and answer follow
  reveal=`<div class="reveal">${own}<div class="verdict">${verdict}${rv.truth!=null?`<b>${c.type==='choice'?esc(rv.truth):lfmt(c,rv.truth)}</b>`:''}</div>${c.method==='sketch'?'':viz(rv.viz)}<p class="why">${esc(rv.why||'')}</p></div>`}
 return `<div class="kind">${pill(c.label,c.tone)}<span>${i+1} of ${n}</span>${c.t?`<span>${ago(c.t)}</span>`:''}${strip(c)}</div>
  <p class="q">${esc(q)}</p>${c.ctx&&c.method!=='spot'?`<p class="ctx">${esc(c.ctx)}</p>`:''}${body(c)}${reveal}
  <div class="actions">${p?`<button class="btn primary" data-l="next">${i===n-1?'Finish':'Next'} <kbd>space</kbd></button>`:`<button class="btn primary" data-t="go" ${ready?'':'disabled'}>Check <kbd>space</kbd></button>${(c.others??1)>0?'<button class="btn" data-t="skip" title="Learn this card another way">Another way</button>':''}`}
  ${i>0?'<button class="btn" data-l="prev">Back</button>':''}</div>`;
}

async function submit(c){
 if(c.pred)return;const s=st(c),m=c.method;
 const answer=m==='sketch'?(s.sk?{...s.sk}:{rows:s.sb}):m==='spot'?s.pick:m==='prototype'?Math.round(s.n):m==='code'?s.code:m==='explain'?s.ex:null;
 if(answer==null||answer==='')return;
 try{const r=await fetch('api/teach',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({viewer:viewer()||'anon',card:c.id,method:m,answer,ms:Math.round(performance.now()-s.t0)})});
  const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);
  const nc={...d.card,methods:c.methods,task:c.task};L.b.cards[L.cur]=nc;
  leaveCard({check:c.id,ok:d.attempt.hit==null?null:!!d.attempt.hit,alt_used:m});tStart(c.id);L.at=0;render(true);loadBrief(true);
 }catch(e){alert('Could not check it: '+(e.message||e))}
}
async function skip(c){
 try{const r=await fetch('api/teach',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({viewer:viewer()||'anon',card:c.id,method:c.method,skip:true,ms:Math.round(performance.now()-st(c).t0)})});
  const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);delete ST[c.id];
  L.b.cards[L.cur]={...c,method:d.method,task:d.task||undefined,others:d.others};render(true);
 }catch(e){alert('Could not switch: '+(e.message||e))}
}

// how each method has gone for this person: tries, right, skipped
function profile(){
 const pr=L.b?.teach?.profile;if(!pr)return '';const ms=Object.entries(pr.methods);const top=Math.max(1,...ms.map(([,s])=>s.n+s.skips));
 return `<div class="t-prof">${ms.map(([m,s])=>`<div class="t-pr" title="${esc(NAMES[m])}: ${s.hits} right of ${s.n}${s.skips?', '+s.skips+' skipped':''}">${ico(m)}<span class="t-bar"><i class="ok" style="width:${100*s.hits/top}%"></i><i class="no" style="width:${100*(s.n-s.hits)/top}%"></i><i class="sk" style="width:${100*s.skips/top}%"></i></span><span class="mono">${s.n?s.hits+'/'+s.n:'–'}</span></div>`).join('')}</div>`;
}

document.addEventListener('click',e=>{
 if(route().r!=='learn')return;const a=e.target.closest('#main [data-t]');if(!a)return;const c=L.b?.cards[L.cur];if(!c)return;
 const k=a.dataset.t;if(k==='zin'||k==='zout'){if(!c.pred)zoom(c,k==='zin'?1:-1)}else if(k==='go')submit(c);else if(k==='skip')skip(c);else if(k==='pick'&&!c.pred){st(c).pick=a.dataset.v;render(true)}
});
document.addEventListener('pointerdown',e=>{if(route().r!=='learn'||!e.target.closest)return;const c=L.b?.cards[L.cur];if(c&&c.method==='sketch')dragSketch(e,c)});
document.addEventListener('input',e=>{
 if(route().r!=='learn')return;const c=L.b?.cards[L.cur];if(!c||c.pred)return;const s=st(c);
 if(e.target.id==='tpn'){const t=c.task||s.tk;s.n=toN(t,e.target.value/1000);$('#tpw').innerHTML=protoSVG(t,s.n,true)}
 else if(e.target.id==='tcode'){s.code=e.target.value;const v=codeVal(c.task||s.tk,s.code),cm=$('#main .t-code .c');if(cm)cm.textContent='// '+(v==null?'= ?':'= '+(+v.toFixed(2))+' pts');const go=$('#main [data-t=go]');if(go)go.disabled=v==null}
 else if(e.target.id==='tex'){s.ex=e.target.value;const go=$('#main [data-t=go]');if(go)go.disabled=s.ex.trim().length<=8}
});
document.addEventListener('keydown',e=>{
 if(route().r!=='learn'||!L.b||e.metaKey||e.ctrlKey||e.altKey)return;const c=L.b.cards[L.cur];if(!c||c.pred)return;
 const tg=e.target;if(tg&&/^(TEXTAREA|INPUT|SELECT)$/.test(tg.tagName))return;
 if(c.method==='sketch'&&(c.task||st(c).tk)){if(/^Arrow/.test(e.key)&&keySketch(e,c))e.preventDefault();
  else if((e.key==='+'||e.key==='='||e.key==='-')&&(c.task||st(c).tk).kind==='ci'){zoom(c,e.key==='-'?-1:1);e.preventDefault()}return}
 if(c.method!=='spot')return;const n=+e.key,k=(c.task||st(c).tk)?.parts;if(k&&n>=1&&n<=k.length){st(c).pick=k[n-1];render(true);e.preventDefault()}
},true);
return {card,submit,profile,active:c=>!!(c&&c.method&&c.method!=='predict'&&(c.task||c.pred&&c.pred.method&&c.pred.method!=='predict'))};
})();
