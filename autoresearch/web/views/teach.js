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

// ---------- sketch: drag the delta and the ends of its interval, or each bar
function sketchCI(c,s){
 const t=c.task||s.tk,W=LW(),H=92,Lx=16,R=W-16,a=t.min,b=t.max,x=q=>Lx+(q-a)/(b-a)*(R-Lx),span=b-a;
 if(!s.sk)s.sk={delta:0,lo:-span*.08,hi:span*.08};const k=s.sk;
 const stp=nstep(span,W<420?5:9);let g='';
 for(let q=Math.ceil(a/stp)*stp;q<=b+1e-9;q+=stp){const qq=+q.toPrecision(6);g+=`<line x1="${x(qq)}" x2="${x(qq)}" y1="30" y2="60" stroke="var(--grid)"/><text x="${x(qq)}" y="76" text-anchor="middle">${qq>0?'+':qq<0?'−':''}${grp(Math.abs(qq))}</text>`}
 const tr=c.reveal?.viz;const truth=tr?`<line x1="${x(tr.lo)}" x2="${x(tr.hi)}" y1="56" y2="56" stroke="var(--text)" stroke-width="4" stroke-linecap="round" opacity=".5"/><circle cx="${x(tr.delta)}" cy="56" r="5" fill="var(--text)"/>`:'';
 return `<svg class="lv t-sk" id="tsk" data-kind="ci" viewBox="0 0 ${W} ${H}" role="slider" aria-label="your sketch: delta ${amt(t.unit,k.delta)}, interval ${amt(t.unit,k.lo)} to ${amt(t.unit,k.hi)}">
  <text x="${Lx}" y="14" class="mono strong" style="fill:var(--accent)">${amt(t.unit,k.delta)} [${amt(t.unit,k.lo)}, ${amt(t.unit,k.hi)}]</text>${g}
  <line x1="${x(0)}" x2="${x(0)}" y1="24" y2="64" stroke="var(--text)" stroke-width="1.5"/>
  <line x1="${x(k.lo)}" x2="${x(k.hi)}" y1="44" y2="44" stroke="var(--accent)" stroke-width="10" stroke-linecap="round" opacity=".3"/>
  <rect x="${x(k.lo)-4}" y="34" width="8" height="20" rx="3" fill="var(--accent)"/><rect x="${x(k.hi)-4}" y="34" width="8" height="20" rx="3" fill="var(--accent)"/>
  <circle cx="${x(k.delta)}" cy="44" r="8" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>${truth}</svg>`;
}
function sketchBars(c,s){
 const t=c.task||s.tk,W=LW(),rh=44,H=t.rows.length*rh+4,R=W-(W<420?96:120);
 if(!s.sb)s.sb=t.rows.map(()=>t.max/2);const tr=c.reveal?.viz?.rows?.filter(r=>r.v!=null);
 const fmt=(r,v)=>r.unit?(grp(v)+' '+r.unit):r.n?`${Math.round(v*r.n).toLocaleString()} of ${r.n.toLocaleString()}`:pct(v);
 return `<svg class="lv t-sk" id="tsk" data-kind="bars" viewBox="0 0 ${W} ${H}" role="group" aria-label="drag each bar">${t.rows.map((r,i)=>{const y=i*rh,v=s.sb[i],w=v/t.max*R;
  const tv=tr&&tr[i]?tr[i].v/t.max*R:null;
  return `<text x="0" y="${y+12}">${esc(r.label)}${r.tag?' · '+esc(r.tag):''}</text><rect x="0" y="${y+18}" width="${R}" height="16" rx="3" fill="var(--active)" data-row="${i}"/>
   <rect x="0" y="${y+18}" width="${Math.max(2,w)}" height="16" rx="3" fill="var(--accent)" opacity=".75" data-row="${i}" pointer-events="none"/>
   ${tv!=null?`<line x1="${tv}" x2="${tv}" y1="${y+14}" y2="${y+38}" stroke="var(--text)" stroke-width="3"/>`:''}
   <text x="${Math.min(R,w)+6}" y="${y+31}" class="mono strong">${fmt(r,v)}</text>`}).join('')}</svg>`;
}
function dragSketch(e,c){
 const svg=e.target.closest('#tsk');if(!svg||c.pred)return;const s=st(c),t=c.task||s.tk;
 const vb=svg.viewBox.baseVal,toX=ev=>{const r=svg.getBoundingClientRect();return (ev.clientX-r.left)/r.width*vb.width},toY=ev=>{const r=svg.getBoundingClientRect();return (ev.clientY-r.top)/r.height*vb.height};
 let move;
 if(svg.dataset.kind==='ci'){const Lx=16,R=vb.width-16,val=px=>t.min+(px-Lx)/(R-Lx)*(t.max-t.min),k=s.sk,v0=val(toX(e));
  const which=['delta','lo','hi'].sort((p,q)=>Math.abs(k[p]-v0)-Math.abs(k[q]-v0))[0],step=(t.max-t.min)/200;
  move=ev=>{let v=Math.round(val(toX(ev))/step)*step;v=Math.max(t.min,Math.min(t.max,v));
   if(which==='delta'){const dl=k.delta-k.lo,dh=k.hi-k.delta;k.delta=v;k.lo=v-dl;k.hi=v+dh}else if(which==='lo')k.lo=Math.min(v,k.delta);else k.hi=Math.max(v,k.delta);
   svg.outerHTML=sketchCI(c,s)}}
 else{const R=vb.width-(vb.width<420?96:120),i=Math.max(0,Math.min(t.rows.length-1,Math.floor(toY(e)/44)));
  move=ev=>{s.sb[i]=Math.max(0,Math.min(t.max,toX(ev)/R*t.max));if(!t.rows[i].unit&&t.rows[i].n)s.sb[i]=Math.round(s.sb[i]*t.rows[i].n)/t.rows[i].n;$('#tsk').outerHTML=sketchBars(c,s)}}
 move(e);const up=()=>{removeEventListener('pointermove',move);removeEventListener('pointerup',up)};addEventListener('pointermove',move);addEventListener('pointerup',up);e.preventDefault();
}

// ---------- spot: the real figure with one number made inconsistent
function spotBars(rows,wrong){
 const W=LW(),rh=42,H=rows.length*rh+4,R=W-(W<420?96:120),cont=rows.some(r=>r.unit!=null),b=cont?Math.max(...rows.map(r=>Math.max(r.v,r.shown??0)))*1.05:1,x=q=>Math.max(0,q)/b*R;
 const val=(r,v)=>r.unit!=null?(grp(v)+' '+r.unit):r.n?`${Math.round(v*r.n).toLocaleString()} of ${r.n.toLocaleString()}`:pct(v);
 return `<svg class="lv" viewBox="0 0 ${W} ${H}">${rows.map((r,i)=>{const y=i*rh,bad=wrong!=null&&+wrong===i;
  return `<text x="0" y="${y+12}">${esc(r.label)}${r.tag?' · '+esc(r.tag):''}</text><rect x="0" y="${y+18}" width="${Math.max(1,x(r.v))}" height="14" rx="2" fill="var(--control)"/><text x="${x(r.v)+6}" y="${y+30}" class="mono strong" ${bad?'style="fill:var(--negative);text-decoration:line-through"':''}>${val(r,r.shown??r.v)}</text>`}).join('')}</svg>`;
}
function spotBody(c,s){
 const t=c.task||s.tk,v=t.viz,ans=c.reveal?.show?.wrong;
 if(v.kind==='ci'){const u=v.unit||'pts',opts=[['counts',`${v.wins.toLocaleString()} fixed · ${v.losses.toLocaleString()} broken`],['delta','Δ '+amt(u,v.delta)],['interval',`[${amt(u,v.lo)}, ${amt(u,v.hi)}]`]];
  return vizCI(v)+`<div class="opts t-spot" style="--n:3">${opts.map(([k,l],i)=>`<button class="opt${s.pick===k?' on':''}${ans?k===ans?' truth':s.pick===k?' wrong':'':''}" data-t="pick" data-v="${k}" ${c.pred?'disabled':''}><kbd>${i+1}</kbd>${esc(l)}</button>`).join('')}</div>`}
 return spotBars(v.rows,ans)+`<div class="opts t-spot" style="--n:${Math.min(4,v.rows.length)}">${v.rows.map((r,i)=>`<button class="opt${s.pick===String(i)?' on':''}${ans!=null?String(i)===ans?' truth':s.pick===String(i)?' wrong':'':''}" data-t="pick" data-v="${i}" ${c.pred?'disabled':''}><kbd>${i+1}</kbd>${esc(r.label)}${r.tag?' · '+esc(r.tag):''}</button>`).join('')}</div>`;
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
<span class="c">// ${sh.got!=null&&Math.abs(sh.got-sh.value)<=Math.max(.05,Math.abs(sh.value)*.01)?'✓':'✗'} ${esc(sh.line)} = ${sh.value} pts</span>`:''}</pre>`;
}

// ---------- explain: one sentence; the ideas it names light up after
function explainBody(c,s){
 const ideas=(c.task||s.tk)?.ideas||[],named=c.reveal?.show?.named;
 return `<textarea class="t-ex" id="tex" rows="3" placeholder="In one sentence" ${c.pred?'disabled':''}>${esc(s.ex||'')}</textarea>
  <div class="t-ideas">${ideas.map(i=>`<span class="chip${named?named.includes(i)?' ok':' no':''}">${esc(i)}</span>`).join('')}</div>`;
}

// the task stays with the card's state, so the reveal can still draw it (the server sends it only before an answer)
function body(c){const s=st(c);if(c.task&&(!s.tk||s.m!==c.method)){s.tk=c.task;s.m=c.method}const t=c.task||s.tk;if(!t||s.m!==c.method)return '';
 return c.method==='sketch'?(t.kind==='bars'?sketchBars(c,s):sketchCI(c,s)):c.method==='spot'?spotBody(c,s):
  c.method==='prototype'?protoBody(c,s):c.method==='code'?codeBody(c,s):c.method==='explain'?explainBody(c,s):''}
function strip(c){const ms=c.methods||[];return `<div class="t-strip">${ms.map(m=>`<span class="t-m${m===c.method?' on':''}" title="${esc(NAMES[m])}">${ico(m)}</span>`).join('')}<b>${esc(NAMES[c.method]||'')}</b></div>`}

function card(c){
 const s=st(c);const n=L.b.cards.length,i=L.cur,p=c.pred,rv=c.reveal;
 const q=c.method==='spot'?'One number is wrong.':c.method==='prototype'?'Drag n to where the interval just clears zero.':c.method==='code'?'The paired gain, in points:':c.q;
 const ready=c.method==='spot'?s.pick!=null:c.method==='code'?codeVal(c.task||s.tk,s.code)!=null:c.method==='explain'?(s.ex||'').trim().length>8:true;
 let reveal='';
 if(p&&rv){const verdict=p.hit==null?'<span class="vd open">Open</span>':p.hit?'<span class="vd ok">✓ Right</span>':'<span class="vd no">✗ Not quite</span>';
  reveal=`<div class="reveal"><div class="verdict">${verdict}${c.truth!=null||rv.truth!=null?`<b>${c.type==='choice'?esc(rv.truth):lfmt(c,rv.truth)}</b>`:''}</div>${viz(rv.viz)}<p class="why">${esc(rv.why||'')}</p></div>`}
 return `<div class="kind">${pill(c.label,c.tone)}<span>${i+1} of ${n}</span>${c.t?`<span>${ago(c.t)}</span>`:''}${strip(c)}</div>
  <p class="q">${esc(q)}</p>${c.ctx&&c.method!=='spot'?`<p class="ctx">${esc(c.ctx)}</p>`:''}${body(c)}${reveal}
  <div class="actions">${p?`<button class="btn primary" data-l="next">${i===n-1?'Finish':'Next'} <kbd>space</kbd></button>`:`<button class="btn primary" data-t="go" ${ready?'':'disabled'}>Check <kbd>space</kbd></button><button class="btn" data-t="skip" title="Learn this card another way">Another way</button>`}
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
  L.b.cards[L.cur]={...c,method:d.method,task:d.task||undefined};render(true);
 }catch(e){alert('Could not switch: '+(e.message||e))}
}

// how each method has gone for this person: tries, right, skipped
function profile(){
 const pr=L.b?.teach?.profile;if(!pr)return '';const ms=Object.entries(pr.methods);const top=Math.max(1,...ms.map(([,s])=>s.n+s.skips));
 return `<div class="t-prof">${ms.map(([m,s])=>`<div class="t-pr" title="${esc(NAMES[m])}: ${s.hits} right of ${s.n}${s.skips?', '+s.skips+' skipped':''}">${ico(m)}<span class="t-bar"><i class="ok" style="width:${100*s.hits/top}%"></i><i class="no" style="width:${100*(s.n-s.hits)/top}%"></i><i class="sk" style="width:${100*s.skips/top}%"></i></span><span class="mono">${s.n?s.hits+'/'+s.n:'–'}</span></div>`).join('')}</div>`;
}

document.addEventListener('click',e=>{
 if(route().r!=='learn')return;const a=e.target.closest('#main [data-t]');if(!a)return;const c=L.b?.cards[L.cur];if(!c)return;
 const k=a.dataset.t;if(k==='go')submit(c);else if(k==='skip')skip(c);else if(k==='pick'&&!c.pred){st(c).pick=a.dataset.v;render(true)}
});
document.addEventListener('pointerdown',e=>{if(route().r!=='learn'||!e.target.closest)return;const c=L.b?.cards[L.cur];if(c&&c.method==='sketch')dragSketch(e,c)});
document.addEventListener('input',e=>{
 if(route().r!=='learn')return;const c=L.b?.cards[L.cur];if(!c||c.pred)return;const s=st(c);
 if(e.target.id==='tpn'){const t=c.task||s.tk;s.n=toN(t,e.target.value/1000);$('#tpw').innerHTML=protoSVG(t,s.n,true)}
 else if(e.target.id==='tcode'){s.code=e.target.value;const v=codeVal(c.task||s.tk,s.code),cm=$('#main .t-code .c');if(cm)cm.textContent='// '+(v==null?'= ?':'= '+(+v.toFixed(2))+' pts');const go=$('#main [data-t=go]');if(go)go.disabled=v==null}
 else if(e.target.id==='tex'){s.ex=e.target.value;const go=$('#main [data-t=go]');if(go)go.disabled=s.ex.trim().length<=8}
});
document.addEventListener('keydown',e=>{
 if(route().r!=='learn'||!L.b||e.metaKey||e.ctrlKey||e.altKey)return;const c=L.b.cards[L.cur];if(!c||c.pred||c.method!=='spot')return;
 const tg=e.target;if(tg&&/^(TEXTAREA|INPUT)$/.test(tg.tagName))return;const n=+e.key,k=(c.task||st(c).tk)?.parts;if(k&&n>=1&&n<=k.length){st(c).pick=k[n-1];render(true);e.preventDefault()}
},true);
return {card,submit,profile,active:c=>!!(c&&c.method&&c.method!=='predict'&&(c.task||c.pred&&c.pred.method&&c.pred.method!=='predict'))};
})();
