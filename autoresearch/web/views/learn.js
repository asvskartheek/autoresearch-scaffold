'use strict';
// Brief: "since you last looked" as predict-then-reveal cards from the ledger (autoresearch/learn.py builds them),
// calibration from .research/predictions.jsonl, and understanding telemetry posted to api/understanding.
// The deck's `since` is fixed when the page opens; finishing the deck moves last-seen for the next visit.
const L={b:null,loading:false,err:null,at:0,cur:null,ui:{},since:null,mode:null,dlg:null,timer:{id:null,ms:0,t0:0},visits:{}};
const LK=()=>'arx-brief-seen:'+(PKEY||'home');
const lget=k=>{try{return localStorage.getItem(k)}catch(e){return null}};
const lset=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
// who is learning: the person id (people.js); the name is what the side panel shows
const viewer=()=>window.ARXP?ARXP.me().id:lget('arx-name')||'';
const viewerName=()=>window.ARXP?ARXP.me().name:lget('arx-name')||'';
// a card value: a count, a percentage (hill cards) or a signed delta in the card's unit
const lfmt=(c,v)=>v==null?'—':c.int?Math.round(v).toLocaleString():c.unit==='%'?(+v).toFixed(1)+'%':lamt(c.unit||'',+v);
// a stable shuffle per card, so options never sit in the same slot and do not jump between renders
function shuf(id,arr){let h=2166136261;for(const ch of id)h=Math.imul(h^ch.charCodeAt(0),16777619);const a=arr.slice();
 for(let i=a.length-1;i>0;i--){h=Math.imul(h^(h>>>13),1597334677)>>>0;const j=h%(i+1);[a[i],a[j]]=[a[j],a[i]]}return a}

function sinceFor(mode){
 const seen=+lget(LK())||0,t=Date.now()/1000;
 return mode==='last'?seen:mode==='day'?t-86400:mode==='week'?t-604800:0;
}
async function loadBrief(force){
 if(!force&&(L.loading||L.b&&Date.now()-L.at<30000))return;
 const seq=L.seq=(L.seq||0)+1;L.loading=true;  // a newer request (new viewer or window) wins over one in flight
 if(L.mode==null){L.mode=lget(LK())?'last':'all';L.since=sinceFor(L.mode)}
 try{
  const r=await fetch(`api/brief?since=${L.since}&viewer=${enc(viewer()||'anon')}`,{cache:'no-store'});
  if(!r.ok)throw new Error('HTTP '+r.status);
  const b=await r.json();if(seq!==L.seq)return;
  L.b=b;L.err=null;L.at=Date.now();
  if(L.cur==null){const i=L.b.cards.findIndex(c=>!c.pred);L.cur=i<0?L.b.cards.length:i}
  L.cur=Math.min(L.cur,L.b.cards.length);
 }catch(e){if(seq!==L.seq)return;L.err=String(e.message||e)}
 L.loading=false;if(route().r==='learn')render(true);
}

// ---------- telemetry: active time on each card (paused while the tab is hidden), posted when you leave it
function tStart(step){L.timer={id:step,ms:0,t0:document.hidden?0:performance.now()}}
function tTake(){const t=L.timer;if(t.t0)t.ms+=performance.now()-t.t0;t.t0=document.hidden?0:performance.now();const ms=t.ms;t.ms=0;return ms}
document.addEventListener('visibilitychange',()=>{const t=L.timer;if(!t.id)return;if(document.hidden){if(t.t0)t.ms+=performance.now()-t.t0;t.t0=0}else t.t0=performance.now()});
function sendU(ev){
 const body=JSON.stringify({viewer:viewer()||'anon',...ev});
 try{if(navigator.sendBeacon&&ev.beacon){navigator.sendBeacon('api/understanding',new Blob([body],{type:'application/json'}));return}}catch(e){}
 fetch('api/understanding',{method:'POST',headers:{'Content-Type':'application/json'},body}).catch(()=>{});
}
function leaveCard(extra={}){
 const t=L.timer;if(!t.id)return;const ms=tTake();
 if(ms>300||extra.check)sendU({doc:'brief',step:t.id,ms:Math.round(Math.min(ms,30*60000)),replays:Math.max(0,(L.visits[t.id]||1)-1),...extra});
}
addEventListener('pagehide',()=>leaveCard({beacon:true}));

// ---------- visuals
// an axis step near span/k on the 1-2-5 ladder
const nstep=(span,k)=>{const raw=span/k,mag=10**Math.floor(Math.log10(raw||1));return [1,2,5,10].map(m=>m*mag).find(m=>m>=raw)};
// a signed amount in a viz's unit: "+5.2 pts" (0/1 slice) or "−1,071 ms" (continuous); 0/1 values come in points
const lamt=(u,x)=>(x>0?'+':x<0?'−':'')+(u==='pts'?(+Math.abs(x).toFixed(2)).toString():grp(Math.abs(x)))+(u?' '+(u==='pts'&&Math.abs(x)===1?'pt':u):'');
function vizCI(v){
 const u=v.unit==null?'pts':v.unit,k=v.unit==null?100:1;  // older payloads carry fractions
 const d=k*v.delta,lo=k*v.lo,hi=k*v.hi,bar=v.bar!=null?k*v.bar:null,W=LW(),H=136,Lx=16,R=W-16;
 const ext=Math.max(Math.abs(lo),Math.abs(hi),Math.abs(bar||0)),pad=u==='pts'?1:ext*.12||1;
 const a=Math.min(u==='pts'?-2:-pad,lo-pad,bar??0),b=Math.max(u==='pts'?2:pad,hi+pad,bar??0),x=q=>Lx+(q-a)/(b-a)*(R-Lx),stp=nstep(b-a,W<420?5:9);
 let t='';for(let q=Math.ceil(a/stp)*stp;q<=b+1e-9;q+=stp){const qq=+q.toPrecision(6);t+=`<line x1="${x(qq)}" x2="${x(qq)}" y1="26" y2="62" stroke="var(--grid)"/><text x="${x(qq)}" y="78" text-anchor="middle">${qq>0?'+':qq<0?'−':''}${grp(Math.abs(qq))}</text>`}
 const good=v.better<0?hi<0:lo>0,bad=v.better<0?lo>0:hi<0,col=good?'var(--positive)':bad?'var(--negative)':'var(--muted)',cap=Math.floor((R-Lx-90)/7);
 const sq=(n,c,y)=>Array.from({length:Math.min(n,cap)},(_,i)=>`<rect x="${Lx+i*7}" y="${y}" width="5" height="9" rx="1" fill="${c}"/>`).join('');
 const row=(n,c,y,w)=>`${sq(n,c,y)}<text x="${Lx+Math.min(n,cap)*7+(n?6:0)}" y="${y+9}">${n.toLocaleString()} ${w}</text>`;
 return `<svg class="lv" viewBox="0 0 ${W} ${H}" role="img" aria-label="paired delta ${lamt(u,d)}, 90% interval ${lamt(u,lo)} to ${lamt(u,hi)}">
 <text x="${Lx}" y="12" class="mono strong">${lamt(u,d)} [${lamt(u,lo)}, ${lamt(u,hi)}]</text><text x="${R}" y="12" text-anchor="end">${v.example?'example · ':''}n = ${v.n.toLocaleString()}</text>${t}
 <line x1="${x(0)}" x2="${x(0)}" y1="22" y2="66" stroke="var(--text)" stroke-width="1.5"/>
 ${bar?`<line x1="${x(bar)}" x2="${x(bar)}" y1="22" y2="66" stroke="var(--warning)" stroke-width="2" stroke-dasharray="4 3"/><text x="${x(bar)}" y="92" text-anchor="middle" style="fill:var(--warning)">bar ${lamt(u,bar)}</text>`:''}
 <line x1="${x(lo)}" x2="${x(hi)}" y1="44" y2="44" stroke="${col}" stroke-width="8" stroke-linecap="round" opacity=".35"/>
 <circle cx="${x(d)}" cy="44" r="6" fill="${col}"/>
 ${row(v.wins,'var(--positive)',100,'fixed')}${row(v.losses,'var(--negative)',118,'broken')}</svg>`;
}
const LW=()=>Math.round(Math.max(300,Math.min(560,(document.querySelector('.lrn .stage')?.clientWidth||innerWidth)-(innerWidth<=900?32:48))));
// bars: a 0/1 row reads as a count ("166 of 185") and its length is the share; a continuous row reads in its unit
function vizBars(v){
 const rows=v.rows.filter(r=>r.v!=null);if(!rows.length)return '';
 const W=LW(),rh=42,H=rows.length*rh+4,Lx=0,R=W-(W<420?96:120),cont=rows.some(r=>r.unit!=null);  // label above each bar
 const vals=rows.map(r=>r.v).concat(v.ref!=null?[v.ref]:[]);
 const b=cont?Math.max(...vals)*1.05||1:1,a=cont?0:Math.max(0,Math.floor(Math.min(...vals)*10-1)/10),x=q=>Lx+(Math.max(a,q)-a)/(b-a)*(R-Lx);
 const lab=r=>{const tag=r.tag?' · '+r.tag:'',max=Math.max(8,Math.floor(W/6.8)-tag.length);return (r.label.length>max?r.label.slice(0,max-1)+'…':r.label)+tag};
 const val=r=>r.unit!=null?(grp(r.v)+' '+r.unit).trim():r.n?`${Math.round(r.v*r.n).toLocaleString()} of ${r.n.toLocaleString()}`:pct(r.v);
 let s='';rows.forEach((r,i)=>{const y=i*rh,c=r.hl===1?'var(--negative)':r.hl===2?'var(--positive)':r.hl===3?'var(--text)':'var(--control)';
  s+=`<text x="${Lx}" y="${y+12}" ${r.hl?'class="strong"':''}><title>${esc(r.label+(r.tag?' · '+r.tag:''))}</title>${esc(lab(r))}</text><rect x="${Lx}" y="${y+18}" width="${Math.max(1,x(r.v)-Lx)}" height="14" rx="2" fill="${c}" ${r.hl===3?'opacity=".25"':''}/><text x="${x(r.v)+6}" y="${y+30}" class="mono strong">${val(r)}</text>`});
 if(v.ref!=null)s+=`<line x1="${x(v.ref)}" x2="${x(v.ref)}" y1="14" y2="${H}" stroke="var(--text)" stroke-dasharray="3 3"/>`;
 return `<svg class="lv" viewBox="0 0 ${W} ${H}" role="img" aria-label="scores">${s}</svg>`;
}
function vizGoal(v){
 const W=LW(),H=108,Lx=16,R=W-16,a=v.lo,N=v.N,x=q=>Lx+(Math.max(a,q)-a)/(N-a)*(R-Lx),ch=v.have;
 let s=`<rect x="${Lx}" y="40" width="${R-Lx}" height="10" rx="2" fill="var(--active)"/><rect x="${Lx}" y="40" width="${x(ch)-Lx}" height="10" rx="2" fill="var(--accent)"/>`;
 if(v.need>ch)s+=`<rect x="${x(ch)}" y="40" width="${x(v.need)-x(ch)}" height="10" fill="var(--warning)" opacity=".35"/><text x="${(x(ch)+x(v.need))/2}" y="74" text-anchor="middle" style="fill:var(--warning);font-weight:500">${(v.need-ch).toLocaleString()} more</text>`;
 s+=`<line x1="${x(v.need)}" x2="${x(v.need)}" y1="30" y2="60" stroke="var(--text)" stroke-width="1.5"/><text x="${Math.min(R-30,x(v.need))}" y="${Math.abs(x(v.need)-x(ch))<70?90:24}" text-anchor="middle" class="strong">${v.need.toLocaleString()} goal</text>`;
 const past=v.traj.filter(p=>!p.champ);
 past.forEach(p=>s+=`<circle cx="${x(p.v)}" cy="45" r="3" fill="var(--muted)"><title>${esc(p.label)}: ${p.v.toLocaleString()}</title></circle>`);
 s+=`<circle cx="${x(ch)}" cy="45" r="5" fill="var(--text)"/><text x="${x(ch)}" y="24" text-anchor="middle" class="mono strong">${ch.toLocaleString()}</text>`;
 if(past.length)s+=`<text x="${Lx}" y="106" class="mono">${past.map(p=>p.v.toLocaleString()).join(' → ')} → ${ch.toLocaleString()}</text>`;
 s+=`<text x="${Lx}" y="74">${a.toLocaleString()}</text><text x="${R}" y="74" text-anchor="end">${N.toLocaleString()}</text>`;
 return `<svg class="lv" viewBox="0 0 ${W} ${H}" role="img" aria-label="champion ${ch} of ${N}, goal ${v.need}">${s}</svg>`;
}
const viz=v=>!v?'':v.kind==='ci'?vizCI(v):v.kind==='bars'?vizBars(v):v.kind==='goal'?vizGoal(v):'';
function numberLine(c,guess,truth){
 const W=LW(),H=76,Lx=16,R=W-16,x=v=>Lx+(v-c.min)/(c.max-c.min)*(R-Lx),span=c.max-c.min;
 const raw=span/(W<420?7:12),mag=10**Math.floor(Math.log10(raw)),stp=[1,2,5,10].map(m=>m*mag).find(m=>m>=raw);
 let s=`<line x1="${Lx}" x2="${R}" y1="36" y2="36" stroke="var(--control)" stroke-width="2"/>`;
 for(let v=Math.ceil(c.min/stp)*stp;v<=c.max+1e-9;v+=stp)s+=`<line x1="${x(v)}" x2="${x(v)}" y1="31" y2="41" stroke="var(--control)"/><text x="${x(v)}" y="58" text-anchor="middle">${c.unit==='pts'&&v>0?'+':''}${(+v.toFixed(2)).toLocaleString()}</text>`;
 if(c.unit==='pts')s+=`<line x1="${x(0)}" x2="${x(0)}" y1="24" y2="48" stroke="var(--text)"/>`;
 const g0=Math.max(c.min,guess-c.tol),g1=Math.min(c.max,guess+c.tol);
 s+=`<rect x="${x(g0)}" y="28" width="${Math.max(2,x(g1)-x(g0))}" height="16" rx="3" fill="var(--accent)" opacity=".18"/>`;
 s+=`<circle cx="${x(guess)}" cy="36" r="7" fill="var(--accent)"/><text x="${Math.min(R-24,Math.max(Lx+24,x(guess)))}" y="16" text-anchor="middle" class="mono" style="fill:var(--accent);font-weight:500">${lfmt(c,guess)}</text>`;
 if(truth!=null)s+=`<line x1="${x(truth)}" x2="${x(truth)}" y1="22" y2="50" stroke="var(--text)" stroke-width="3"/><text x="${Math.min(R-24,Math.max(Lx+24,x(truth)))}" y="72" text-anchor="middle" class="mono strong">${lfmt(c,truth)}</text>`;
 return `<svg class="nl" id="lnl" viewBox="0 0 ${W} ${H}" role="slider" aria-label="your guess" aria-valuemin="${c.min}" aria-valuemax="${c.max}" aria-valuenow="${guess}" tabindex="0">${s}</svg>`;
}
const snap=(c,v)=>{v=Math.round(v/c.step)*c.step;return Math.min(c.max,Math.max(c.min,+v.toFixed(2)))};

// ---------- the deck
function uiOf(c){if(!L.ui[c.id])L.ui[c.id]={choice:c.pred&&c.type==='choice'?c.pred.guess:null,guess:c.pred?c.pred.guess:c.start,conf:c.pred?Math.round(c.pred.conf*100):70};return L.ui[c.id]}
function cardHTML(c){
 if(typeof TEACH!=='undefined'&&TEACH.active(c))return TEACH.card(c);  // sketch, spot, prototype, code or explain
 const u=uiOf(c),p=c.pred,rv=c.reveal,open=c.open,truth=rv?rv.truth:null;
 let body='';
 if(c.type==='choice'){
  const opts=shuf(c.id,c.opts);
  body=`<div class="opts ${opts.length>2?'many':''}" style="--n:${opts.length}">${opts.map((o,i)=>{
   let cl=u.choice===o?' on':'';if(p&&truth!=null){if(o===truth)cl+=' truth';else if(u.choice===o)cl+=' wrong'}
   return `<button class="opt${cl}" data-l="pick" data-v="${esc(o)}" ${p?'disabled':''}><kbd>${i+1}</kbd>${esc(o)}</button>`}).join('')}</div>`;
 }else body=numberLine(c,u.guess,p?truth:null);
 body+=`<div class="conf"><label for="lcf">${c.type==='number'?'Sure it lands in the band':'Sure'}</label><input type="range" id="lcf" min="${Math.round(100*(c.cmin??.5))}" max="100" step="5" value="${u.conf}" ${p?'disabled':''}><output id="lcfo">${u.conf}%</output></div>`;
 let reveal='';
 if(p){
  const yours=c.type==='choice'?esc(p.guess):lfmt(c,p.guess);
  const verdict=truth==null?`<span class="vd open">Open</span>`:p.hit?`<span class="vd ok">✓ Right</span>`:`<span class="vd no">✗ Wrong</span>`;
  reveal=`<div class="reveal"><div class="verdict">${verdict}${truth!=null?`<b>${c.type==='choice'?esc(truth):lfmt(c,truth)}</b>`:''}<span class="you">you: ${yours} at ${Math.round(p.conf*100)}%</span></div>${viz(rv.viz)}<p class="why">${esc(rv.why||'')}</p></div>`;
 }
 const n=L.b.cards.length,i=L.cur,ready=c.type==='number'||u.choice!=null;
 const other=!p&&(c.others??((c.methods||[]).length-1))>0;  // the server counts the methods not yet skipped
 return `<div class="kind">${pill(c.label,c.tone)}<span>${i+1} of ${n}</span>${c.t?`<span>${ago(c.t)}</span>`:''}</div>
  <p class="q">${esc(c.q)}</p>${c.ctx?`<p class="ctx">${esc(c.ctx)}</p>`:''}${body}${reveal}
  <div class="actions">${p?`<button class="btn primary" data-l="next">${i===n-1?'Finish':'Next'} <kbd>space</kbd></button>`:`<button class="btn primary" data-l="commit" ${ready?'':'disabled'}>Reveal <kbd>space</kbd></button>${other?'<button class="btn" data-t="skip" title="Learn this card another way">Another way</button>':''}`}
  ${i>0?'<button class="btn" data-l="prev">Back</button>':''}${c.ev?`<a class="ev mono" href="${/^\d{4}-\d{6}-/.test(c.ev)?'#task/'+enc(c.ev):'#slices'}">${esc(c.ev)}</a>`:''}</div>`;
}
function doneHTML(){
 const st=S.state,live=(st.tasks||[]).filter(t=>isLive(t)&&t.kind==='eval'&&t.progress?.total);
 const open=L.b.open||[];
 const jobs=live.slice(0,6).map(t=>{const pr=t.progress,eta=t.eta?.eta_s;return `<a class="job" href="#task/${enc(t.id)}"><div class="l"><b>${esc(t.title)}</b><span class="m">${pr.done.toLocaleString()}/${pr.total.toLocaleString()}${eta!=null?' · '+left(eta)+' left':''}${t.status==='stalled'?' · stalled':''}</span></div>${meter(pr.done/pr.total,{cls:t.status==='stalled'?'bad':''})}</a>`}).join('');
 const skip=L.b.cards.map((c,k)=>c.pred?-1:k).filter(k=>k>=0);
 if(skip.length)return `<div class="done-h"><h2>${plural(skip.length,'card')} skipped</h2></div>
  <div class="actions"><button class="btn primary" data-l="go" data-i="${skip[0]}">Card ${skip[0]+1} <kbd>space</kbd></button></div>`;
 return `<div class="done-h"><h2>You're caught up</h2><span class="muted">${L.b.calibration.all_n??L.b.calibration.n} scored · ${open.length} open</span></div>
  ${jobs?`<div class="jobs">${jobs}</div>`:''}
  ${open.length?`<div class="pend">${open.map(r=>`<div>${pill('Open','warn')}<span class="pq">${esc(r.q||r.card)}</span><span class="mono">${esc(typeof r.guess==='number'?(+r.guess).toFixed(1):r.guess)} · ${Math.round(r.conf*100)}%</span></div>`).join('')}</div>`:''}
  <div class="actions">${L.b.cards.length?'<button class="btn" data-l="prev">Back</button>':''}</div>`;
}
function calChart(cal){
 const W=268,H=180,Lx=34,B=150,T=10,R=W-10,x=v=>Lx+v/100*(R-Lx),y=v=>B-v/100*(B-T);
 let s='';[0,50,100].forEach(v=>s+=`<line x1="${Lx}" x2="${R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${Lx-6}" y="${y(v)+4}" text-anchor="end">${v}</text>`);
 [0,50,100].forEach(v=>s+=`<text x="${x(v)}" y="${B+16}" text-anchor="middle">${v}</text>`);
 s+=`<line x1="${x(0)}" y1="${y(0)}" x2="${x(100)}" y2="${y(100)}" stroke="var(--control)" stroke-dasharray="4 4"/>`;
 s+=`<text x="${(Lx+R)/2}" y="${H-2}" text-anchor="middle">confidence</text><text x="10" y="${(T+B)/2}" text-anchor="middle" transform="rotate(-90 10 ${(T+B)/2})">hit rate</text>`;
 const pt=cal.bins.map(b=>({c:100*b.conf,h:100*b.hit,n:b.n}));
 if(pt.length>1)s+=`<polyline points="${pt.map(p=>x(p.c)+','+y(p.h)).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>`;
 pt.forEach(p=>s+=`<circle cx="${x(p.c)}" cy="${y(p.h)}" r="${3+Math.sqrt(p.n)*2}" fill="var(--accent)" opacity=".85"><title>${p.n} at ~${p.c.toFixed(0)}%: ${p.h.toFixed(0)}% right</title></circle>`);
 return `<svg class="cal" viewBox="0 0 ${W} ${H}" role="img" aria-label="calibration: stated confidence against hit rate">${s}</svg>`;
}
function knowHTML(){
 const b=L.b,cal=b.calibration,u=b.understanding||{docs:{}},ids=new Set(b.cards.map(c=>c.id));
 const bs=u.docs?.brief?.step_ms||{},catchMs=Object.entries(bs).filter(([k])=>ids.has(k)).reduce((a,[,v])=>a+v,0);
 const missed=(u.missed||[]).filter(m=>m.doc!=='brief').map(m=>{const id=m.doc.startsWith('concept:')?m.doc.slice(8):null,c=id&&b.concepts.find(x=>x.id===id);return c?{t:c.t,id}:{t:m.doc}});
 const uniq=[...new Map(missed.map(m=>[m.t,m])).values()];
 const v=viewerName();
 return `<div class="score"><div><b>${cal.all_hits??cal.hits}/${cal.all_n??cal.n}</b><span>right</span></div><div title="${plural(cal.n,'prediction')} with a stated confidence"><b>${cal.brier==null?'–':cal.brier.toFixed(2)}</b><span>Brier</span></div><div><b>${catchMs?span(catchMs/1000):'–'}</b><span>to catch up</span></div></div>
  ${calChart(cal)}${typeof TEACH!=='undefined'?TEACH.profile():''}
  ${uniq.length?`<div class="missed"><span class="muted">Missed</span>${uniq.map(m=>m.id?`<button class="chip" data-l="concept" data-id="${esc(m.id)}">${esc(m.t)}</button>`:`<span class="chip">${esc(m.t)}</span>`).join('')}</div>`:''}
  <div class="who"><span class="muted">${v?esc(v):'No name set'}</span><button class="linkbtn" data-l="name">${v?'Change':'Set your name'}</button></div>`;
}
function conceptMini(v){
 if(v.kind==='paired'){const tot=96,w=Math.max(v.wins?1:0,Math.round(v.wins/v.n*tot)),l=Math.max(v.losses?1:0,Math.round(v.losses/v.n*tot));let s='';
  for(let i=0;i<tot;i++){const c=i<w?'var(--positive)':i<w+l?'var(--negative)':'var(--active)';s+=`<rect x="${(i%16)*10}" y="${Math.floor(i/16)*10}" width="8" height="8" rx="1" fill="${c}"/>`}return `<svg viewBox="0 0 158 58">${s}</svg>`}
 if(v.kind==='ladder'){const r=v.rungs,k=r.length,st=k>1?140/(k-1):0;let s=`<line x1="14" x2="146" y1="30" y2="30" stroke="var(--control)" stroke-width="2"/>`;
  r.forEach((n,i)=>{const x=14+i*st*132/140;s+=`<circle cx="${x}" cy="30" r="6" fill="var(--surface)" stroke="var(--control)" stroke-width="2"/><text x="${x}" y="${k>3&&i%2?14:52}" text-anchor="middle">${esc(n.length>10?n.slice(0,9)+'…':n)}</text>`});return `<svg viewBox="0 0 160 58">${s}</svg>`}
 if(v.kind==='ci-mini'){const m=Math.max(.02,...v.rows.map(r=>Math.max(Math.abs(r[1]),Math.abs(r[2])))),x=q=>80+q/m*70;let s=`<line x1="80" x2="80" y1="2" y2="56" stroke="var(--text)"/>`;
  v.rows.forEach(([d,lo,hi],i)=>{const y=12+i*17,c=lo>0?'var(--positive)':hi<0?'var(--negative)':'var(--muted)';s+=`<line x1="${x(lo)}" x2="${x(hi)}" y1="${y}" y2="${y}" stroke="${c}" stroke-width="5" stroke-linecap="round" opacity=".4"/><circle cx="${x(d)}" cy="${y}" r="3.5" fill="${c}"/>`});
  if(v.example)s+=`<text x="158" y="54" text-anchor="end">example</text>`;return `<svg viewBox="0 0 160 58">${s}</svg>`}
 if(v.kind==='hill'){const sh=v.share,f=sh&&sh.of?sh.count/sh.of:null;
  return `<svg viewBox="0 0 160 58">${f!=null?`<rect x="4" y="30" width="152" height="10" rx="2" fill="var(--active)"/><rect x="4" y="30" width="${152*f}" height="10" rx="2" fill="${v.status==='climbed'?'var(--positive)':'var(--warning)'}"/><text x="4" y="22" class="strong">${sh.count} of ${sh.of}</text><text x="156" y="54" text-anchor="end">${v.status==='climbed'?'climbed':'open'}</text>`:`<text x="4" y="30" class="strong">${v.status==='climbed'?'climbed':'open'}</text>`}</svg>`}
 return '';
}
function conceptsHTML(){
 const u=L.b.understanding?.docs||{};let ok=0,tot=0;
 const cs=L.b.concepts.map(c=>{const res=u['concept:'+c.id]?.results||{};
  const dots=c.qs.map((_,i)=>{tot++;const r=res[c.id+'#'+i];if(r===true)ok++;return `<b class="${r===true?'ok':r===false?'no':''}"></b>`}).join('');
  return `<button class="concept" data-l="concept" data-id="${esc(c.id)}">${conceptMini(c.viz)}<span class="t"><span class="ell">${esc(c.t)}</span><i>${dots}</i></span></button>`}).join('');
 return `<section class="strip"><div class="hd"><h2>Concepts</h2><span class="muted">${ok} of ${tot}</span></div><div class="concepts">${cs}</div></section>`;
}

VIEWS.learn=()=>{
 loadBrief();
 const head=page({title:'Since you last looked',crumbs:[['Brief']],acts:`<div class="seg">${[['last','Last visit'],['day','24 h'],['week','7 d'],['all','All']].map(([k,l])=>`<button class="${L.mode===k?'on':''}" data-l="mode" data-v="${k}">${l}</button>`).join('')}</div>`});
 if(!L.b)return head+(L.err?empty('Could not load the brief',esc(L.err)):`<div class="lrn"><div class="stage skel"></div></div>`);
 const b=L.b,i=L.cur,c=b.cards[i];
 if(c&&L.timer.id!==c.id){leaveCard();tStart(c.id);L.visits[c.id]=(L.visits[c.id]||0)+1}
 if(!c&&L.timer.id){leaveCard();L.timer.id=null}
 if(!c&&b.cards.length&&i>=b.cards.length&&b.cards.every(x=>x.pred))lset(LK(),String(b.now));  // every card answered: next visit starts here
 const pips=b.cards.map((x,k)=>{const p=x.pred;const cl=k===i?'cur':!p?'':p.hit==null?'pend':p.hit?'hit':'miss';return `<button class="pip ${cl}" data-l="go" data-i="${k}" aria-label="card ${k+1}"></button>`}).join('');
 const since=b.since?`Since ${stamp(b.since)}`:'All time';
 const stage=!b.cards.length?`<div class="done-h"><h2>${b.since?'Nothing new since '+esc(stamp(b.since)):'Nothing to predict yet'}</h2>${b.empty?`<span class="muted">${esc(b.empty)}</span>`:''}</div>`:c?cardHTML(c):doneHTML();
 return head+`<div class="lrn"><div class="lhead"><span class="muted">${esc(since)} · ${plural(b.cards.length,'card')}</span><div class="pips">${pips}</div></div>
  <div class="layout"><section class="stage${b.cards.length?'':' blank'}" aria-live="polite">${stage}</section>
  <aside class="lside">${panel('How well you know this project',knowHTML())}</aside></div>${conceptsHTML()}</div>`;
};

// ---------- actions
async function commitCard(){
 const c=L.b.cards[L.cur];if(!c||c.pred)return;const u=uiOf(c);
 if(typeof TEACH!=='undefined'&&TEACH.active(c))return TEACH.submit(c);
 if(c.type==='choice'&&u.choice==null)return;
 if(!viewerName()){const n=(prompt('Your name, so your predictions are yours')||'').trim();if(!n)return;window.ARXP?ARXP.setName(n):lset('arx-name',n.slice(0,60))}
 const guess=c.type==='choice'?u.choice:u.guess;
 try{
  const r=await fetch('api/predictions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({viewer:viewer(),card:c.id,guess,conf:u.conf/100})});
  const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);
  L.b.cards[L.cur]=d.card;
  leaveCard({check:c.id,ok:d.prediction.hit==null?null:!!d.prediction.hit});tStart(c.id);
  L.at=0;render(true);loadBrief(true);
 }catch(e){alert('Could not save the prediction: '+(e.message||e))}
}
function go(k){if(!L.b)return;L.cur=Math.max(0,Math.min(L.b.cards.length,k));render(true)}
function setName(){const n=(prompt('Your name',viewerName())||'').trim();if(n){window.ARXP?ARXP.setName(n):lset('arx-name',n.slice(0,60));L.ui={};L.cur=null;loadBrief(true)}}

// concept dialog: one check at a time, options shuffled, a clear ✓ / ✗, results posted as understanding events
function dlgEl(){let d=document.getElementById('ldlg');if(!d){d=document.createElement('dialog');d.id='ldlg';d.className='ldlg';document.body.append(d);
 d.addEventListener('click',e=>{const a=e.target.closest('[data-d]');if(!a)return;const k=a.dataset.d;if(k==='close')d.close();else if(k==='ans')answerConcept(+a.dataset.i);else if(k==='next')advConcept()});
 d.addEventListener('close',()=>{L.dlg=null;render(true)})}return d}
function openConcept(id){const c=L.b.concepts.find(x=>x.id===id);if(!c||!c.qs.length)return;
 const res=L.b.understanding?.docs?.['concept:'+id]?.results||{};let qi=c.qs.findIndex((_,i)=>res[id+'#'+i]!==true);if(qi<0)qi=0;
 L.dlg={c,qi,ans:null,t0:performance.now()};drawDlg();dlgEl().showModal()}
function drawDlg(){
 const {c,qi,ans}=L.dlg,q=c.qs[qi],o=shuf(c.id+'#'+qi,q.o);
 dlgEl().innerHTML=`<div class="dh"><h2>${esc(c.t)}</h2><button class="btn" data-d="close">Close</button></div><div class="cv">${conceptMini(c.viz)}</div>
  <div class="cq"><p>${esc(q.q)}</p><div class="opts" style="--n:1">${o.map((x,i)=>{let cl='';if(ans!=null){if(x===q.a)cl=' truth';else if(x===ans)cl=' wrong'}
   return `<button class="opt${cl}" data-d="ans" data-i="${i}" ${ans!=null?'disabled':''}><kbd>${i+1}</kbd>${esc(x)}</button>`}).join('')}</div>
  <div class="actions">${ans!=null?(ans===q.a?'<span class="vd ok">✓ Right</span>':`<span class="vd no">✗ Wrong · ${esc(q.a)}</span>`):''}<span class="muted">${qi+1} of ${c.qs.length}</span>${ans!=null?`<button class="btn primary" data-d="next">${qi<c.qs.length-1?'Next':'Done'} <kbd>space</kbd></button>`:''}</div></div>`;
}
function answerConcept(i){const st=L.dlg;if(!st||st.ans!=null)return;const q=st.c.qs[st.qi],o=shuf(st.c.id+'#'+st.qi,q.o);if(i>=o.length)return;
 st.ans=o[i];const ok=st.ans===q.a,ms=Math.round(performance.now()-st.t0),check=st.c.id+'#'+st.qi;
 sendU({doc:'concept:'+st.c.id,step:st.qi,ms,check,ok});
 const d=L.b.understanding.docs['concept:'+st.c.id]||(L.b.understanding.docs['concept:'+st.c.id]={results:{}});d.results=d.results||{};d.results[check]=ok;
 L.b.understanding.missed=(L.b.understanding.missed||[]).filter(m=>!(m.doc==='concept:'+st.c.id&&m.check===check)).concat(ok?[]:[{doc:'concept:'+st.c.id,check}]);
 drawDlg()}
function advConcept(){const st=L.dlg;if(!st)return;if(st.qi<st.c.qs.length-1){st.qi++;st.ans=null;st.t0=performance.now();drawDlg()}else dlgEl().close()}

document.addEventListener('click',e=>{
 if(route().r!=='learn')return;const a=e.target.closest('#main [data-l]');if(!a)return;
 const k=a.dataset.l,c=L.b?.cards[L.cur];
 if(k==='pick'&&c&&!c.pred){uiOf(c).choice=a.dataset.v;render(true)}
 else if(k==='commit')commitCard();
 else if(k==='next')go(L.cur+1);
 else if(k==='prev')go(L.cur-1);
 else if(k==='go')go(+a.dataset.i);
 else if(k==='concept')openConcept(a.dataset.id);
 else if(k==='name')setName();
 else if(k==='mode'){L.mode=a.dataset.v;L.since=sinceFor(L.mode);L.cur=null;L.ui={};L.b=null;render(true);loadBrief(true)}
});
document.addEventListener('input',e=>{if(e.target.id!=='lcf'||!L.b)return;const c=L.b.cards[L.cur];if(!c)return;uiOf(c).conf=+e.target.value;const o=$('#lcfo');if(o)o.textContent=e.target.value+'%'});
// the number line: drag to guess; only the svg is redrawn while dragging
document.addEventListener('pointerdown',e=>{
 const nl=e.target.closest&&e.target.closest('#lnl');if(!nl||route().r!=='learn')return;const c=L.b?.cards[L.cur];if(!c||c.pred)return;
 const set=ev=>{const r=nl.getBoundingClientRect(),f=(ev.clientX-r.left)/r.width,a=16/(nl.viewBox.baseVal.width||560),b=1-a;uiOf(c).guess=snap(c,c.min+Math.min(1,Math.max(0,(f-a)/(b-a)))*(c.max-c.min));
  const cur=$('#lnl');if(cur){cur.outerHTML=numberLine(c,uiOf(c).guess,null)}};
 set(e);const mv=ev=>set(ev),up=()=>{removeEventListener('pointermove',mv);removeEventListener('pointerup',up);render(true)};
 addEventListener('pointermove',mv);addEventListener('pointerup',up);e.preventDefault();
});
document.addEventListener('keydown',e=>{
 if(route().r!=='learn'||!L.b||e.metaKey||e.ctrlKey||e.altKey)return;
 if(L.dlg){const n=+e.key;if(n>=1&&n<=4){answerConcept(n-1);e.preventDefault()}else if((e.key===' '||e.key==='Enter')&&L.dlg.ans!=null){advConcept();e.preventDefault()}return}
 const tg=e.target;if(tg&&(tg.isContentEditable||/^(TEXTAREA|SELECT)$/.test(tg.tagName)||tg.tagName==='INPUT'&&(tg.type!=='range'||/^Arrow|^(Home|End|PageUp|PageDown)$/.test(e.key))))return;  // the slider keeps its own arrow keys
 if(e.key==='['){go(L.cur-1);e.preventDefault();return}
 if(e.key===']'){go(L.cur+1);e.preventDefault();return}
 const c=L.b.cards[L.cur];
 if(!c){const k=L.b.cards.findIndex(x=>!x.pred);if(k>=0&&(e.key===' '||e.key==='Enter')){go(k);e.preventDefault()}return}
 const u=uiOf(c);
 if(e.key===' '||e.key==='Enter'){if(tg&&tg.tagName==='BUTTON'&&e.key==='Enter')return;e.preventDefault();c.pred?go(L.cur+1):commitCard();return}
 if(c.pred||typeof TEACH!=='undefined'&&TEACH.active(c))return;  // a method card takes its own keys (teach.js)
 const n=+e.key;
 if(c.type==='choice'&&n>=1&&n<=c.opts.length){u.choice=shuf(c.id,c.opts)[n-1];render(true);return}
 if(e.key==='ArrowUp'||e.key==='ArrowDown'){u.conf=Math.min(100,Math.max(Math.round(100*(c.cmin??.5)),u.conf+(e.key==='ArrowUp'?5:-5)));render(true);e.preventDefault();return}
 if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
  const dir=e.key==='ArrowRight'?1:-1;
  if(c.type==='number'){const st=c.step*(e.shiftKey?10:Math.max(1,Math.round((c.max-c.min)/c.step/200)));u.guess=snap(c,u.guess+dir*st)}
  else{const o=shuf(c.id,c.opts),j=o.indexOf(u.choice);u.choice=o[(j<0?0:j+dir+o.length)%o.length]}
  render(true);e.preventDefault()}
});
// charts are drawn in CSS pixels (viewBox = stage width), so redraw when the width changes
let lw0=0;addEventListener('resize',()=>{if(route().r!=='learn'||!L.b)return;const w=LW();if(Math.abs(w-lw0)>24){lw0=w;render(true)}});
addEventListener('hashchange',()=>{if(route().r!=='learn'&&L.timer.id){leaveCard();L.timer.id=null}});
