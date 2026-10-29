'use strict';
// 101: one lesson per idea (autoresearch/course.py), each a figure to drag or click, a sentence and a check, built
// from this project's ledger. #course lists them, #course/<id> is a lesson, #course/review runs what is due.
// Every check answered is kept per person (api/course) and comes back for review 1, 3, 7 and 21 days later.
// The Brief uses COURSE for its catch-up primers and its due list.
const COURSE=(()=>{
const C={d:null,loading:null,at:0,ans:{},w:{},checks:{},pending:{},rev:null,viewer:null};
const me=()=>window.ARXP?ARXP.me().id:'anon';
function ensure(force){
 const who=me();if(C.viewer!==who){C.viewer=who;C.d=null;C.ans={};C.checks={};C.w={};C.rev=null;C.at=0}
 if(!force&&C.d&&Date.now()-C.at<60000)return Promise.resolve(C.d);
 if(C.loading)return C.loading;
 return C.loading=fetch(`api/course?viewer=${enc(me())}`,{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('HTTP '+r.status)))
  .then(d=>{if(C.viewer!==who)return null;C.d=d;C.at=Date.now();C.err=null;return d}).catch(e=>{C.err=String(e.message||e);return null}).finally(()=>{C.loading=null;if(/^(course|learn)$/.test(route().r))render(true)});
}
const lesson=id=>C.d?.lessons.find(x=>x.id===id);
const mem=id=>C.d?.memory?.[id];
// a lesson's state for a person: new, due (missed, or its review date came) or learned
const state=id=>{const m=mem(id);return !m?'new':m.is_due?'due':'learned'};
async function record(id,hit,how){
 try{const r=await fetch('api/course',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({viewer:me(),item:id,hit,how})});
  const d=await r.json();if(r.ok&&C.d){C.d.memory[id]=d.memory;C.d.due=Object.entries(C.d.memory).filter(([,m])=>m.is_due).sort((a,b)=>a[1].due-b[1].due).map(([k])=>k)}
  if(typeof L!=='undefined'&&L.b?.course&&C.d){L.b.course.memory=C.d.memory;L.b.course.due=C.d.due}
  return r.ok;
 }catch(e){C.err=String(e.message||e);return false}
}
const CW=()=>Math.round(Math.max(280,Math.min(620,($('#main .crs-fig')?.clientWidth||$('#main')?.clientWidth||innerWidth)-(innerWidth<=900?8:0))));
const amt=(u,x)=>lamt(u||'pts',x);
const W=id=>C.w[id]||(C.w[id]={});
const tick=(a,b,k)=>{const raw=(b-a)/k,m=10**Math.floor(Math.log10(raw||1));return [1,2,5,10].map(x=>x*m).find(x=>x>=raw)};
function axis(a,b,x,y,u){const s=tick(a,b,innerWidth<480?4:7);let g='';for(let q=Math.ceil(a/s)*s;q<=b+1e-9;q+=s){const v=+q.toPrecision(6);
 g+=`<line x1="${x(v)}" x2="${x(v)}" y1="${y-26}" y2="${y}" stroke="var(--grid)"/><text x="${x(v)}" y="${y+14}" text-anchor="middle">${v>0?'+':v<0?'−':''}${grp(Math.abs(v))}</text>`}
 return g+`<line x1="${x(0)}" x2="${x(0)}" y1="${y-32}" y2="${y+2}" stroke="var(--text)" stroke-width="1.5"/><text x="${x(0)}" y="${y-36}" text-anchor="middle" class="strong">0</text>`}
const svg=(w,h,s,lab)=>`<svg class="crs-svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(lab||'')}">${s}</svg>`;
const ex=f=>f.example?'<span class="crs-ex">example</span>':'';

// ---------- figures: each draws from the lesson's own numbers and its widget state; inputs carry data-w="<id>:<key>"
const FIG={
 goal(f,s,id){const v=s.v??f.have,w=CW(),L0=12,R=w-12,x=q=>L0+q/f.N*(R-L0),met=v>=f.need;
  return `${ex(f)}<div class="crs-big">${met?'Goal met':`${(f.need-v).toLocaleString()} more`}<span> of ${f.N.toLocaleString()} on ${esc(f.slice)}</span></div>`+
   svg(w,64,`<rect x="${L0}" y="24" width="${R-L0}" height="12" rx="3" fill="var(--active)"/><rect x="${L0}" y="24" width="${x(v)-L0}" height="12" rx="3" fill="${met?'var(--positive)':'var(--accent)'}"/>
   <line x1="${x(f.need)}" x2="${x(f.need)}" y1="14" y2="46" stroke="var(--text)" stroke-width="2"/><text x="${Math.min(R-30,x(f.need))}" y="10" text-anchor="middle" class="strong">goal ${f.need.toLocaleString()}</text>
   <line x1="${x(f.have)}" x2="${x(f.have)}" y1="22" y2="40" stroke="var(--text)" stroke-dasharray="2 2"/><text x="${Math.max(L0+20,x(f.have))}" y="58" text-anchor="middle">now ${f.have.toLocaleString()}</text>`,'goal')+
   `<label class="crs-rg"><span>champion</span><input type="range" data-w="${id}:v" min="0" max="${f.N}" value="${v}" aria-label="champion count"><output>${v.toLocaleString()}</output></label>`},
 bars(f,s,id){const rs=f.rows;if(!rs.length)return '<p class="muted">No runs on the full slice yet.</p>';const w=CW(),R=w-(w<420?90:130),vals=rs.map(r=>r.v),a=f.n?Math.max(0,Math.min(...vals)-.08):0,b=Math.max(...vals)||1,x=q=>(q-a)/(b-a)*R;
  const val=r=>f.n?`${Math.round(r.v*f.n).toLocaleString()} of ${f.n.toLocaleString()}`:grp(r.v);
  return `<div class="crs-rows">${rs.map((r,i)=>`<button class="crs-row${s.i===i?' on':''}" data-w="${id}:i" data-v="${i}"><span class="l">${esc(r.label)}${r.hl?' '+pill('champion','acc'):''}</span>${svg(w,18,`<rect x="0" y="3" width="${Math.max(2,x(r.v))}" height="12" rx="2" fill="${r.hl?'var(--positive)':'var(--control)'}"/><text x="${Math.max(2,x(r.v))+6}" y="13" class="mono">${val(r)}</text>`)}${s.i===i?`<span class="d">${esc(r.status)} · ${val(r)}</span>`:''}</button>`).join('')}</div><p class="crs-cap">${esc(f.slice)}${f.n?` · n = ${f.n.toLocaleString()}`:''}</p>`},
 list(f,s,id){if(!f.rows.length)return '';return `<div class="crs-rows${f.lineage?' lin':''}">${f.rows.map((r,i)=>`<button class="crs-row${s.i===i?' on':''}" data-w="${id}:i" data-v="${i}"><span class="l">${esc(r.label)} ${pill(r.status,r.status==='champion'?'acc':r.status==='rejected'?'neg':'')}${r.score?`<span class="mono muted">${esc(r.score)}</span>`:''}</span>${s.i===i||f.rows.length<=2?`<span class="d">${esc(r.detail||'')}${r.parent?` · from ${esc(r.parent)}`:''}</span>`:''}</button>`).join(f.lineage?'<i class="crs-up">↑</i>':'')}</div>`},
 slices(f,s,id){const w=CW(),R=w-(w<420?110:160);
  return `${(f.datasets||[]).map(d=>`<div class="crs-big">${d.n.toLocaleString()}<span> examples · ${esc(d.title)}</span></div>`).join('')}<div class="crs-rows">${f.rows.map((r,i)=>`<button class="crs-row${s.i===i?' on':''}" data-w="${id}:i" data-v="${i}"><span class="l">${esc(r.name)} <span class="muted">${esc(r.kind)}</span></span>${svg(w,18,`<rect x="0" y="3" width="${R}" height="12" rx="2" fill="var(--active)"/><rect x="0" y="3" width="${Math.max(2,r.n/f.N*R)}" height="12" rx="2" fill="${s.i===i?'var(--accent)':'var(--control)'}"/><text x="${R+6}" y="13" class="mono">${r.n.toLocaleString()} of ${f.N.toLocaleString()}</text>`)}</button>`).join('')}</div>`},
 paired(f,s,id){const n=f.n,fx=Math.min(n,s.fixed??f.fixed),br=Math.min(n-fx,s.broken??f.broken),d=100*(fx-br)/n,cap=Math.min(n,innerWidth<480?120:240),k=Math.max(1,Math.ceil(n/cap)),w=CW(),per=Math.floor(w/8);
  const sq=Array.from({length:Math.ceil(n/k)},(_,i)=>{const e=i*k,c=e<fx?'var(--positive)':e<fx+br?'var(--negative)':'var(--active)';return `<rect x="${(i%per)*8}" y="${Math.floor(i/per)*8}" width="6" height="6" rx="1" fill="${c}"/>`}).join('');
  const mx=n;
  return `${ex(f)}<div class="crs-big ${d>0?'pos':d<0?'neg':''}">${amt('pts',d)}<span> paired Δ</span></div>${svg(w,Math.ceil(Math.ceil(n/k)/per)*8,sq,'examples')}<p class="crs-cap">${n.toLocaleString()} examples${k>1?`, one square per ${k}`:''}</p>
   <label class="crs-rg pos"><span>fixed</span><input type="range" data-w="${id}:fixed" min="0" max="${mx}" value="${fx}"><output>${fx}</output></label>
   <label class="crs-rg neg"><span>broken</span><input type="range" data-w="${id}:broken" min="0" max="${n-fx}" value="${br}"><output>${br}</output></label>
   <pre class="crs-code">100 * (<b class="pos">${fx}</b> − <b class="neg">${br}</b>) / ${n.toLocaleString()} = ${amt('pts',d)}</pre>`},
 interval(f,s,id){const n=s.n??f.n,half=(f.hi-f.lo)/2*Math.sqrt(f.n/n),lo=f.delta-half,hi=f.delta+half,clear=lo>0||hi<0,w=CW(),L0=14,R=w-14;
  const e=Math.max(Math.abs(f.lo),Math.abs(f.hi),Math.abs(f.delta)*2)*1.1,x=q=>L0+(Math.max(-e,Math.min(e,q))+e)/(2*e)*(R-L0),col=clear?(f.delta>0?'var(--positive)':'var(--negative)'):'var(--muted)';
  const lg=Math.log,a=Math.max(4,f.n/20),b=f.n*20,pos=(lg(n)-lg(a))/(lg(b)-lg(a));
  return `${ex(f)}<div class="crs-big">${clear?'Clears zero':'Crosses zero'}<span> at n = ${Math.round(n).toLocaleString()}</span></div>`+svg(w,72,axis(-e,e,x,58,f.unit)+`<line x1="${x(lo)}" x2="${x(hi)}" y1="40" y2="40" stroke="${col}" stroke-width="10" stroke-linecap="round" opacity=".45"/><circle cx="${x(f.delta)}" cy="40" r="6" fill="${col}"/>`,'interval')+
   `<p class="crs-cap mono">${amt(f.unit,f.delta)} [${amt(f.unit,lo)}, ${amt(f.unit,hi)}]</p><label class="crs-rg"><span>n</span><input type="range" data-w="${id}:nf" min="0" max="1000" value="${Math.round(1000*pos)}"><output>${Math.round(a).toLocaleString()} – ${Math.round(b).toLocaleString()}</output></label>`},
 gate(f,s,id){const d=s.d??f.delta,e=Math.max(Math.abs(f.bar)*3,Math.abs(f.delta)*1.6,f.unit==='pts'?2:1),w=CW(),L0=14,R=w-14,x=q=>L0+(q+e)/(2*e)*(R-L0);
  const sign=f.better||1,ok=f.rule==='better'?sign*d>sign*f.bar:sign*d>=sign*f.bar,word=sign<0?(f.rule==='better'?'below':'at or below'):(f.rule==='better'?'above':'at or above');
  return `${ex(f)}<div class="crs-big ${ok?'pos':'neg'}">${ok?'Pass':'Fail'}<span> Δ ${amt(f.unit,d)} is ${ok?word:(sign<0?'above':'below')} the bar ${amt(f.unit,f.bar)}</span></div>`+
   svg(w,72,axis(-e,e,x,58,f.unit)+`<rect x="${f.bar>0?x(f.bar):L0}" y="22" width="${f.bar>0?R-x(f.bar):x(f.bar)-L0}" height="0" />
   <rect x="${sign<0?L0:x(f.bar)}" y="16" width="${sign<0?x(f.bar)-L0:R-x(f.bar)}" height="28" fill="var(--positive)" opacity=".08"/><line x1="${x(f.bar)}" x2="${x(f.bar)}" y1="14" y2="46" stroke="var(--warning)" stroke-width="2" stroke-dasharray="4 3"/><text x="${x(f.bar)}" y="10" text-anchor="middle" style="fill:var(--warning)">bar</text>
   <circle cx="${x(d)}" cy="30" r="7" fill="${ok?'var(--positive)':'var(--negative)'}"/>`,'gate')+
   `<label class="crs-rg"><span>Δ</span><input type="range" data-w="${id}:d" min="${-e}" max="${e}" step="${e/200}" value="${d}"><output>${amt(f.unit,d)}</output></label><p class="crs-cap">${esc(f.model)} · ${esc(f.slice)} · ${esc(f.rung)}</p>`},
 rung(f,s,id){const st=s.st||f.checks.map(()=>true),ok=st.every(Boolean);
  return `<div class="crs-big ${ok?'pos':'neg'}">${esc(f.rung)}<span> ${ok?'passes':'fails'}</span></div><div class="crs-checks">${f.checks.map((c,i)=>`<button class="crs-chk ${st[i]?'pos':'neg'}" data-w="${id}:st" data-v="${i}"><b>${st[i]?'✓':'✗'}</b>${esc(c.slice.replace(/^@hills?\./,'hill '))}<span>${c.rule==='better'?'better':'not worse by more than '+amt('pts',-100*c.bar).replace('+','')}</span></button>`).join('')}</div>`},
 ladder(f,s,id){const rs=f.rungs,fail=s.fail??-1,top=fail<0?rs.length:fail,at=Math.min(s.at??0,top),w=CW(),L0=24,R=w-24,x=i=>L0+(rs.length>1?i/(rs.length-1):0)*(R-L0);
  let g=`<line x1="${L0}" x2="${R}" y1="34" y2="34" stroke="var(--control)" stroke-width="2"/>`;
  rs.forEach((r,i)=>{const real=f.status[i],c=i===fail?'var(--negative)':i<at?'var(--positive)':real==='pass'?'var(--positive)':real==='fail'?'var(--negative)':'var(--surface)';
   g+=`<circle cx="${x(i)}" cy="34" r="9" fill="${c}" stroke="var(--control)" stroke-width="2"/><text x="${x(i)}" y="${i%2&&rs.length>4?62:16}" text-anchor="middle" class="strong">${esc(r.rung)}</text>`});
  g+=`<circle cx="${x(Math.min(at,rs.length-1))}" cy="34" r="4" fill="var(--text)"/>`;
  return svg(w,70,g,'ladder')+`<div class="crs-acts"><button class="btn" data-w="${id}:at" data-v="1" ${at>=top?'disabled':''}>Climb</button>${rs.map((r,i)=>`<button class="btn${fail===i?' on':''}" data-w="${id}:fail" data-v="${i}">Fail ${esc(r.rung)}</button>`).join('')}<button class="btn" data-w="${id}:reset">Reset</button></div>
   <p class="crs-cap">${at>=rs.length?'Promoted':fail>=0&&at>=fail?`Stopped at ${esc(rs[fail].rung)}`:`Next: ${esc(rs[at]?.rung||'')}`}${f.model?` · real: ${esc(f.model)}`:''}</p>`},
 share(f,s,id){if(!f.rows.length)return '<p class="muted">No hills yet.</p>';const w=CW(),R=w-(w<420?110:150);
  return `<div class="crs-rows">${f.rows.map((r,i)=>`<button class="crs-row${s.i===i?' on':''}" data-w="${id}:i" data-v="${i}"><span class="l">${esc(r.label)} ${pill(r.status,r.status==='climbed'?'pos':'warn')}</span>${r.of?svg(w,18,`<rect x="0" y="3" width="${R}" height="12" rx="2" fill="var(--active)"/><rect x="0" y="3" width="${r.count/r.of*R}" height="12" rx="2" fill="${r.status==='climbed'?'var(--positive)':'var(--warning)'}"/><text x="${R+6}" y="13" class="mono">${r.count} of ${r.of}</text>`):''}${s.i===i?`<span class="d">${esc(r.detail)}${r.target?` · on ${esc(r.target)}`:''}${r.of_what?` · counts ${esc(r.of_what)}`:''}</span>`:''}</button>`).join('')}</div>`},
 guess(f,s,id){const g=s.g??Math.round(f.N/2),done=s.shown,hit=Math.abs(g-f.truth)<=f.tol,w=CW(),L0=12,R=w-12,x=q=>L0+q/f.N*(R-L0);
  return `${ex(f)}<p class="crs-cap">How many of ${f.N.toLocaleString()} does the champion get right on ${esc(f.slice)}?</p>`+svg(w,46,`<line x1="${L0}" x2="${R}" y1="20" y2="20" stroke="var(--control)" stroke-width="2"/><circle cx="${x(g)}" cy="20" r="7" fill="var(--accent)"/>${done?`<line x1="${x(f.truth)}" x2="${x(f.truth)}" y1="8" y2="32" stroke="var(--text)" stroke-width="3"/><text x="${Math.min(R-30,Math.max(L0+30,x(f.truth)))}" y="44" text-anchor="middle" class="strong">${f.truth.toLocaleString()}</text>`:''}`,'guess')+
   `<label class="crs-rg"><span>guess</span><input type="range" data-w="${id}:g" min="0" max="${f.N}" value="${g}" ${done?'disabled':''}><output>${g.toLocaleString()}</output></label>
   <div class="crs-acts">${done?`<span class="vd ${hit?'ok':'no'}">${hit?'✓ Close':'✗ Off by '+Math.abs(g-f.truth).toLocaleString()}</span>`:`<button class="btn" data-w="${id}:shown">Reveal</button>`}</div>`},
 goals(f,s,id){return `<div class="crs-rows">${f.rows.map(r=>`<div class="crs-row"><span class="l">${esc(r.label)} ${pill(r.met?'met':r.status||'open',r.met?'pos':'warn')}</span>${r.N?`${meter(r.have/r.N,{mark:r.need/r.N})}<span class="d mono">${r.have.toLocaleString()} of ${r.N.toLocaleString()} · goal ${r.need.toLocaleString()} · on ${esc(r.slice)}</span>`:`<span class="d mono">${esc(r.kpi)} ${grp(r.value)} · target ${r.lower?'under':'over'} ${grp(r.target)} · on ${esc(r.slice)}</span>`}</div>`).join('')}</div>`},
};
const fig=x=>`<div class="crs-fig" data-fig="${esc(x.id)}">${(FIG[x.fig.kind]||(()=>''))(x.fig,W(x.id),x.id)}</div>`;
function redraw(id){const x=lesson(id),el=document.querySelector(`#main .crs-fig[data-fig="${CSS.escape(id)}"]`);if(!x||!el)return;
 const a=document.activeElement,k=a?.dataset?.w;el.outerHTML=fig(x);if(k)document.querySelector(`#main [data-w="${CSS.escape(k)}"]`)?.focus()}
document.addEventListener('input',e=>{const k=e.target.dataset?.w;if(!k||e.target.type!=='range')return;const [id,p]=k.split(':'),x=lesson(id);if(!x)return;const s=W(id);
 if(p==='nf'){const f=x.fig,a=Math.max(4,f.n/20),b=f.n*20;s.n=Math.exp(Math.log(a)+e.target.value/1000*(Math.log(b)-Math.log(a)))}else s[p]=+e.target.value;redraw(id)});
document.addEventListener('click',e=>{const b=e.target.closest('#main button[data-w]');if(!b)return;const [id,p]=b.dataset.w.split(':'),x=lesson(id);if(!x)return;const s=W(id),v=+b.dataset.v;
 if(p==='i')s.i=s.i===v?null:v;else if(p==='st'){s.st=s.st||x.fig.checks.map(()=>true);s.st[v]=!s.st[v]}else if(p==='at')s.at=(s.at||0)+1;
 else if(p==='fail')s.fail=s.fail===v?-1:v;else if(p==='reset'){s.at=0;s.fail=-1}else if(p==='shown')s.shown=true;redraw(id)});

// ---------- the check that ends a lesson (or opens a review): options in a stable shuffle, ✓ / ✗ and why
const which=(x,how)=>{const key=x.id+'|'+how;if(!x.checks.length)return null;return C.checks[key]||(C.checks[key]=x.checks[how==='review'?(mem(x.id)?.n||0)%x.checks.length:0])};
function checkHTML(x,how,key){
 const c=which(x,how);if(!c)return '';const a=C.ans[key],o=shuf(x.id+'#'+c.q,c.o);
 return `<div class="crs-check" data-key="${esc(key)}"><p class="crs-q">${esc(c.q)}</p><div class="opts" style="--n:${o.length>3?2:o.length}">${o.map((t,i)=>{let cl=a!=null?(t===c.a?' truth':t===a?' wrong':''):'';
  return `<button class="opt${cl}" data-cq="${esc(key)}" data-i="${i}" ${a!=null?'disabled':''}><kbd>${i+1}</kbd>${esc(t)}</button>`}).join('')}</div>
  ${a!=null?`<div class="crs-res"><span class="vd ${a===c.a?'ok':'no'}">${a===c.a?'✓ Right':'✗ Not quite'}</span>${c.why?`<span>${esc(c.why)}</span>`:''}</div>`:''}</div>`}
async function answer(key,i){const [id,how]=key.split('|'),x=lesson(id);if(!x||C.ans[key]!=null||C.pending[key])return;const c=which(x,how);if(!c)return;const o=shuf(x.id+'#'+c.q,c.o);if(i<0||i>=o.length)return;
 C.pending[key]=true;const ok=await record(id,o[i]===c.a,how);delete C.pending[key];
 if(ok){C.ans[key]=o[i];C.err=null}else C.err='Could not save your answer. Try again.';render(true)}
document.addEventListener('click',e=>{const b=e.target.closest('[data-cq]');if(!b)return;answer(b.dataset.cq,+b.dataset.i)});

// ---------- pages
const due=()=>(C.d?.due||[]).filter(id=>lesson(id));
const nextOf=id=>{const ids=C.d.lessons.map(x=>x.id),i=ids.indexOf(id);return ids[i+1]};
const when=m=>{if(!m)return '';const d=(m.due-Date.now()/1000);return m.is_due?'due now':'next in '+span(d)};
function listHTML(){
 const ls=C.d.lessons,dd=due(),grp_=g=>ls.filter(x=>x.group===g).map(x=>{const st=state(x.id);
  return `<a class="crs-tile ${st}" href="#course/${enc(x.id)}" data-item><span class="dot"></span><b>${esc(x.t)}</b><span class="muted">${st==='new'?'':esc(when(mem(x.id)))}</span></a>`}).join('');
 const learned=ls.filter(x=>state(x.id)!=='new').length;
 return page({title:'101',crumbs:[['101']],acts:dd.length?`<a class="btn primary" href="#course/review">Review ${dd.length} <kbd>space</kbd></a>`:`<a class="btn primary" href="#course/${enc((ls.find(x=>state(x.id)==='new')||ls[0]).id)}">Start <kbd>space</kbd></a>`})+
  `<div class="crs"><div class="crs-prog">${meter(learned/ls.length)}<span class="mono">${learned} of ${ls.length}</span></div>
  <h2 class="crs-h">Basics</h2><div class="crs-grid">${grp_('basics')}</div><h2 class="crs-h">This project</h2><div class="crs-grid">${grp_('project')}</div></div>`}
function lessonHTML(id,how){
 const x=lesson(id);if(!x)return page({title:'101',crumbs:[['101','#course'],['Not found']]})+empty('No lesson '+esc(id));
 const key=id+'|'+how,done=C.ans[key]!=null||!x.checks.length,dd=due().filter(k=>k!==id||!done);
 const nx=how==='review'?(dd[0]?'#course/review':'#course'):nextOf(id)?'#course/'+enc(nextOf(id)):'#course';
 const st=state(id),m=mem(id);
 const head=page({title:x.t,crumbs:[['101','#course'],[x.t]],acts:`<span class="crs-st ${st}">${st==='new'?'new':esc(when(m))}</span>`});
 // a review asks first (the memory test), then shows the figure; a lesson shows the figure first
 const body=how==='review'&&!done?checkHTML(x,how,key):`${fig(x)}<p class="crs-say">${esc(x.say)}</p>${checkHTML(x,how,key)}`;
 return head+`<div class="crs crs-one">${body}${C.err?`<p role="alert">${esc(C.err)}</p>`:''}<div class="actions">${done?`<a class="btn primary" href="${nx}" data-next data-how="${how}">${how==='review'?(dd[0]?'Next review':'Done'):'Next'} <kbd>space</kbd></a>`:''}<a class="btn" href="#course">All lessons</a></div></div>`}
VIEWS.course=arg=>{
 ensure();
 if(!C.d){ensure();return page({title:'101',crumbs:[['101']]})+(C.err?empty('Could not load the course',esc(C.err)):'<div class="crs"><div class="stage skel"></div></div>')}
 if(Date.now()-C.at>60000)ensure(true);
 if(!C.d.lessons.length)return page({title:'101',crumbs:[['101']]})+empty('No lessons available');
 if(!arg)return listHTML();
 if(arg==='review'){if(!C.rev)C.rev=due()[0]||null;return C.rev?lessonHTML(C.rev,'review'):listHTML()}
 return lessonHTML(arg,'lesson')};
addEventListener('hashchange',()=>{if(route().r==='course'&&route().arg==='review'){C.rev=due()[0]||null;for(const k of Object.keys(C.ans))if(k.endsWith('|review'))delete C.ans[k];for(const k of Object.keys(C.checks))if(k.endsWith('|review'))delete C.checks[k]}});
document.addEventListener('click',e=>{const a=e.target.closest('[data-next][data-how="review"]');if(!a||a.getAttribute('href')!=='#course/review')return;e.preventDefault();const old=C.rev;C.rev=due().find(id=>id!==old)||null;if(!C.rev){location.hash='#course';return}delete C.ans[C.rev+'|review'];delete C.checks[C.rev+'|review'];render(true)});
document.addEventListener('keydown',e=>{
 if(route().r!=='course'||e.metaKey||e.ctrlKey||e.altKey||e.defaultPrevented)return;const t=e.target;if(t&&(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(t.tagName)))return;
 const ck=document.querySelector('#main .crs-check');const n=+e.key;
 if(ck&&n>=1&&n<=9&&C.ans[ck.dataset.key]==null){answer(ck.dataset.key,n-1);e.preventDefault();return}
 if((e.key===' '||e.key==='Enter')&&!(t&&t.tagName==='BUTTON')){const a=document.querySelector('#main [data-next]')||(!route().arg&&document.querySelector('#main .acts .btn.primary'));if(a){a.click();e.preventDefault()}}
});
// a small version for the Brief: the figure, the sentence and one check, recorded as a primer
function primer(id){const x=lesson(id);if(!x)return '';return `${fig(x)}<p class="crs-say">${esc(x.say)}</p>${checkHTML(x,'primer',id+'|primer')}`}
const primed=id=>C.ans[id+'|primer']!=null;
return {ensure,lesson,state,mem,primer,primed,answer,record,data:()=>C.d};
})();
