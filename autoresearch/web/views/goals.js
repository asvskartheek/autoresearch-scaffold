'use strict';
// goals: the number the work is for. The list answers "what are we trying to reach, how far are we, and is the gap
// closing?": each goal's biggest element is the track from its starting champion (the baseline) to its target, filled
// to where the champion stands now. A goal's page adds every run on the goal slice over time, the hills that serve it
// and what to run next. Everything is computed from /api/state `goals` (core.py goal_status) and the eval tasks.

// one block keeps these helpers out of the shared global scope the other view files load into
{
// ---------- figures: a score KPI reads as a percentage and its gaps in points; latency in seconds; cost in dollars
const kpiOf=g=>g.kpi||'score';
const isScore=g=>kpiOf(g)==='score';
const isTime=g=>/^latency/.test(kpiOf(g));
const sgn=g=>g.higher_is_better===false?-1:1;
const KPI_NAME={score:'score',cost:'cost per question',latency_p50:'median latency',latency_p95:'p95 latency',latency_mean:'mean latency'};
const kpiName=g=>KPI_NAME[kpiOf(g)]||kpiOf(g);
const gv=function(g,v){
 if(v==null||!isFinite(v))return '—';
 if(isScore(g))return pct(v);
 if(isTime(g))return v.toFixed(1)+'&nbsp;s';
 if(kpiOf(g)==='cost')return money(v);
 return num(v);
}
// an unsigned amount of the KPI: points for a score, seconds, dollars
const gamt=function(g,d){
 d=Math.abs(d);
 if(isScore(g))return (100*d).toFixed(1)+'&nbsp;pts';
 if(isTime(g))return d.toFixed(1)+'&nbsp;s';
 if(kpiOf(g)==='cost')return money(d);
 return num(d);
}
// a change in the good direction gets a + ; colour says good or bad, grey for none
const gchg=function(g,d,signedGood=true){
 if(d==null)return DASH;
 const good=signedGood?d:sgn(g)*d;
 if(Math.abs(d)<1e-12)return '<span class="faint">0</span>';
 const shown=isScore(g)?pts(good)+'&nbsp;pts':(good>0?'+':'−')+gamt(g,d);
 return `<span class="${good>0?'pos':'neg'}">${shown}</span>`;
}
const cmpSym=g=>sgn(g)>0?'≥':'≤';
const mLink=k=>k?(S.state.models[k]?`<a class="ln" href="#model/${enc(k)}">${mn(k)}</a>`:mn(k)):'—';
const sLink=s=>`<a class="ln mono" href="#slices/${enc(s)}">${esc(s)}</a>`;
const hLink=k=>{const x=S.state.hills[k];return `<a class="ln" href="#hill/${enc(k)}">${esc(x?.title||k)}</a>`};
const kpiKey=g=>isScore(g)?'score':kpiOf(g);

// the baseline's value on the goal slice: the paired mean when the server paired it, else its latest run
const baseVal=function(g){
 if(g.vs_baseline?.base!=null)return g.vs_baseline.base;
 if(g.baseline&&g.baseline===g.model&&g.status!=='achieved')return g.value;  // the champion is still the baseline: same pooled figure
 const r=g.baseline&&(S.state.leaderboard[g.slice]||{})[g.baseline];
 const v=r?.[kpiKey(g)];return typeof v==='number'&&isFinite(v)?v:null;
}
// how far along the way from the baseline to the target the champion stands. rel: 0 at the baseline, 1 at the target.
// abs: the baseline already met the target, or it has no run, so the track is drawn on the KPI's own scale.
const prog=function(g){
 const v=g.value,t=g.target,b=baseVal(g),s=sgn(g);
 if(v==null)return {mode:'none',b};
 if(b==null||s*(t-b)<=0)return {mode:'abs',b,v,t};
 return {mode:'rel',b,v,t,p:s*(v-b)/(s*(t-b))};
}
// runs on the goal slice that finished with this KPI, oldest first; a run on another slice hash is a different slice
const slRuns=function(g){
 const k=kpiKey(g);
 return S.state.tasks.filter(t=>t.kind==='eval'&&t.slice===g.slice&&(t.status==='done'||t.status==='completed')
  &&(!g.slice_hash||!t.slice_hash||t.slice_hash===g.slice_hash)&&typeof t.summary?.[k]==='number'&&isFinite(t.summary[k])&&t.ended)
  .sort((a,b)=>a.ended-b.ended);
}
const HORD={open:0,climbed:1,closed:2};
const goalHills=g=>Object.entries(g.hills||{}).sort((a,b)=>(HORD[a[1]]??3)-(HORD[b[1]]??3));
const hillCounts=g=>{const c={};for(const [,s] of goalHills(g))c[s]=(c[s]||0)+1;return c};
const hillSum=g=>{const c=hillCounts(g),n=goalHills(g).length;if(!n)return 'no hills';return ['open','climbed','closed'].filter(s=>c[s]).map(s=>`${c[s]} ${s}`).concat(Object.keys(c).filter(s=>!['open','climbed','closed'].includes(s)).map(s=>`${c[s]} ${s}`)).join(' · ')};
const answers=g=>isScore(g)&&g.gap>0&&g.n?Math.ceil(g.gap*g.n-1e-9):null;
const ST_LABEL={open:'Open',achieved:'Achieved',abandoned:'Abandoned'};
const gst=g=>st(g.status,ST_LABEL[g.status]||g.status);
const ORDER={open:0,achieved:1,abandoned:2};
// open goals: met first (they wait on a command), then the furthest along
const rank=g=>g.status!=='open'?0:g.met?2:((p=>p.mode==='rel'?Math.max(-1,Math.min(1,p.p)):-1)(prog(g)));

// ---------- the track: baseline on the left, target on the right, filled to the champion now
const track=function(g,{big=false}={}){
 const P=prog(g),pc=f=>(100*Math.max(0,Math.min(1,f))).toFixed(1)+'%';
 if(P.mode==='none')return `<div class="gl-trk"><div class="gl-bar"></div><div class="gl-ends"><span>${g.model?`${mLink(g.model)} has no complete run on this slice`:'No champion yet'}</span><span>Target <b>${cmpSym(g)}&nbsp;${gv(g,g.target)}</b></span></div></div>`;
 if(P.mode==='rel'){
  const met=g.met,p=P.p,cls=met?'met':p<0?'back':'';
  return `<div class="gl-trk ${big?'big':''}" role="img" aria-label="${esc(`${Math.round(100*p)}% of the way from the baseline to the target`)}">
   <div class="gl-bar ${cls}"><i style="width:${pc(p)}"></i>${p>0&&p<1?`<b style="left:${pc(p)}"></b>`:''}</div>
   <div class="gl-ends"><span>Baseline <b>${gv(g,P.b)}</b>${big?`<span class="gl-bn"> · ${mLink(g.baseline)}</span>`:''}</span><span>Target <b>${cmpSym(g)}&nbsp;${gv(g,P.t)}</b></span></div></div>`;
 }
 // abs: the KPI's own scale from 0, the target as a tick; lower-is-better fills to the value and passes left of the tick
 const top=isScore(g)?1:Math.max(P.v,P.t,P.b??0)*1.15||1,f=P.v/top,m=P.t/top;
 const mp=(100*Math.max(0,Math.min(1,m))).toFixed(1);
 return `<div class="gl-trk abs ${big?'big':''}">
  <div class="gl-tgt"><span style="--m:${mp}">Target <b>${cmpSym(g)}&nbsp;${gv(g,P.t)}</b></span></div>
  <div class="gl-bar ${g.met?'met':''}"><i style="width:${pc(f)}"></i><b class="tgt" style="left:${pc(m)}"></b></div>
  <div class="gl-ends"><span>${P.b!=null?`Baseline <b>${gv(g,P.b)}</b>${big&&g.baseline?`<span class="gl-bn"> · ${mLink(g.baseline)}</span>`:''}${sgn(g)*(P.b-P.t)>=0?', already past the target':''}`:'Baseline not run on this slice'}</span><span>${isScore(g)?'100%':''}</span></div></div>`;
}
// "62% of the way", "met", "behind the baseline"
const wayText=function(g){
 const P=prog(g);
 if(g.status==='achieved')return 'Achieved';
 if(P.mode==='none')return '—';
 if(P.mode!=='rel')return '—';
 if(g.met)return '100%';
 if(P.p<0)return 'Behind baseline';
 return Math.round(100*P.p)+'%';
}
const gapFig=function(g){
 if(g.value==null)return {v:DASH,s:'no run yet'};
 if(g.met)return {v:'Met',s:`${gamt(g,g.gap)} past the target`};
 const a=answers(g);
 return {v:gamt(g,g.gap),s:a!=null?`${plural(a,'more answer')} of ${g.n.toLocaleString()}`:`to ${cmpSym(g)} ${gv(g,g.target)}`};
}
const vsFig=function(g){
 const v=g.vs_baseline,P=prog(g);
 if(v&&v.delta!=null)return {v:gchg(g,v.delta),s:`90% CI ${pts(v.lo)} to ${pts(v.hi)}`,wl:`better on ${v.wins}, worse on ${v.losses}`};
 if(g.baseline&&g.model&&g.baseline===g.model)return {v:'<span class="faint">0</span>',s:'the champion is still the baseline'};
 if(P.b!=null&&g.value!=null)return {v:gchg(g,g.value-P.b,false),s:'latest runs, unpaired'};
 return {v:DASH,s:g.baseline?'baseline not run on this slice':'no baseline'};
}
const paperBtn=g=>{const p=goalPaper(g.name);return p?`<a class="btn" href="${paperUrl(p)}">${ICON.papers}${g.status==='open'?'Draft paper':'Paper'}${p.waiting?`<span class="gl-wait">${p.waiting}</span>`:''}</a>`:''};

// ---------- list
VIEWS.goals=()=>{
 const L=S.state,gs=Object.values(L.goals||{}).sort((a,b)=>(ORDER[a.status]??3)-(ORDER[b.status]??3)||rank(b)-rank(a)||(b.created||0)-(a.created||0));
 const open=gs.filter(g=>g.status==='open'),done=gs.filter(g=>g.status==='achieved'),gone=gs.filter(g=>g.status!=='open'&&g.status!=='achieved');
 const met=open.filter(g=>g.met&&!g.slice_changed);
 const lead=open.filter(g=>!g.met&&prog(g).mode==='rel').sort((a,b)=>prog(b).p-prog(a).p)[0];
 const gl=g=>`<a href="#goal/${enc(g.name)}"><b>${esc(g.title)}</b></a>`;
 let finding='';
 if(gs.length){
  if(!open.length)finding=`No open goals. ${[done.length?`${done.length} achieved`:'',gone.length?`${gone.length} abandoned`:''].filter(Boolean).join(', ')}.`;
  else{
   finding=`<b>${plural(open.length,'open goal')}</b>. `;
   if(met.length)finding+=`${gl(met[0])} meets its target and waits to be recorded.`;
   else if(lead)finding+=`${open.length>1?'Furthest along: ':''}${gl(lead)}, ${Math.round(100*Math.max(0,prog(lead).p))}% of the way from its baseline, ${gamt(lead,lead.gap)} to go${answers(lead)!=null?` (${plural(answers(lead),'answer')})`:''}.`;
   else finding+=open.some(g=>g.value==null)?'The champion has no complete run on a goal slice yet.':'No goal has a baseline to measure progress from.';
  }
 }
 const acts=met.length?cmd('arx goal achieve '+met[0].name):'';
 let h=page({title:'Goals',crumbs:[['Goals','#goals']],finding,acts});
 if(!gs.length){
  const sl=L.config?.primary_dataset?L.config.primary_dataset+'/full':'<dataset>/full';
  return h+panel('',empty('No goals yet','A goal is one KPI target on one frozen slice; hills serve it and it gets the public paper.')+`<div class="gl-cmd">${cmd(`arx goal open <name> --title "…" --slice ${sl} --target 0.9`)}</div>`);
 }
 if(open.length)h+=`<section class="gl-grp"><div class="gl-gh"><h2>Open</h2><span class="meta">${open.length}</span></div><div class="gl-cards">${open.map(card).join('')}</div></section>`;
 if(done.length)h+=`<section class="gl-grp"><div class="gl-gh"><h2>Achieved</h2><span class="meta">${done.length}</span></div><div class="gl-cards">${done.map(card).join('')}</div></section>`;
 if(gone.length)h+=`<section class="gl-grp"><div class="gl-gh"><h2>Abandoned</h2><span class="meta">${gone.length}</span></div>${panel('',table([['Goal'],['Why it was abandoned'],['Best','num'],['Target','num']],gone.map(g=>`<tr class="click" onclick="if(!event.target.closest('a,button'))location.hash='goal/${enc(g.name)}'"><td><div class="two"><a href="#goal/${enc(g.name)}"><b>${esc(g.title)}</b></a><span class="sub mono">${esc(short(g.slice))}</span></div></td><td class="gl-why">${g.reason?esc(g.reason):'<span class="dash">No reason recorded</span>'}</td><td class="num">${gv(g,g.value)}</td><td class="num">${cmpSym(g)}&nbsp;${gv(g,g.target)}</td></tr>`)),{cls:'gl-ab'})}</section>`;
 return h;
};
const card=function(g){
 const gap=gapFig(g),vs=vsFig(g),hs=goalHills(g),way=wayText(g),ev=g.evidence;
 const who=g.status==='achieved'?`achieved by ${mLink(ev?.model||g.model)}${g.achieved?`, ${stamp(g.achieved)}`:''}`:g.model?`${mLink(g.model)}, champion${g.runs>1?` · ${g.runs} runs pooled`:''}`:'no champion';
 return `<section class="card gl-card ${esc(g.status)}">
  <div class="gl-top">${gst(g)}${g.slice_changed?pill('slice changed','neg'):''}${ev?.forced?pill('forced, target not met','warn'):''}<h3><a href="#goal/${enc(g.name)}">${esc(g.title)}</a></h3><span class="gl-r">${paperBtn(g)}</span></div>
  <p class="gl-meta">${sLink(g.slice)}<span>n ${Number(g.n||0).toLocaleString()}</span><span>${esc(kpiName(g))} ${cmpSym(g)} ${gv(g,g.target)}</span>${g.created?`<span>opened ${stamp(g.created)}</span>`:''}</p>
  <div class="gl-body">
   <div class="gl-now"><div class="gl-big">${gv(g,g.status==='achieved'&&ev?ev.value:g.value)}</div><div class="sub">${who}</div></div>
   <div class="gl-mid">${track(g)}</div>
   <dl class="gl-figs">
    <div><dt>To go</dt><dd>${g.status==='achieved'?'Met':gap.v}</dd><dd class="sub">${g.status==='achieved'?`${gamt(g,g.gap)} past it`:gap.s}</dd></div>
    <div><dt>Of the way</dt><dd>${way}</dd><dd class="sub">${prog(g).mode==='rel'?`from ${gv(g,prog(g).b)}`:prog(g).b!=null&&g.value!=null?'baseline already past it':'no baseline run'}</dd></div>
    <div><dt>vs baseline</dt><dd>${vs.v}</dd><dd class="sub" title="${esc((g.baseline?(S.state.models[g.baseline]?.title||g.baseline)+': ':'')+vs.s.replace(/&nbsp;/g,' '))}">${vs.s}</dd></div>
   </dl>
  </div>
  <div class="gl-foot"><span class="gl-hl">${hs.length?`Hills: ${hs.slice(0,4).map(([k,s])=>`${hLink(k)}<span class="faint"> ${esc(s)}</span>`).join(', ')}${hs.length>4?`, +${hs.length-4} more`:''}`:'<span class="faint">No hill serves this goal yet</span>'}</span><a class="more" href="#goal/${enc(g.name)}">Runs and next steps</a></div>
 </section>`;
}

// ---------- detail
const finding1=function(g){
 const P=prog(g),slice=`${sLink(g.slice)} (n ${Number(g.n||0).toLocaleString()})`;
 if(g.status==='abandoned')return `Abandoned${g.abandoned?` ${stamp(g.abandoned)}`:''} at ${gv(g,g.value)} against a target of ${cmpSym(g)} ${gv(g,g.target)} on ${slice}.`;
 if(g.status==='achieved'){const ev=g.evidence||{};return `Achieved${g.achieved?` ${stamp(g.achieved)}`:''} by <b>${mLink(ev.model)}</b> at <b>${gv(g,ev.value)}</b> on ${slice}${ev.forced?', forced without the target met':''}${g.vs_baseline?.delta!=null?`, ${gchg(g,g.vs_baseline.delta)} against the baseline ${mLink(g.baseline)}`:''}.`}
 if(g.value==null)return g.model?`The champion ${mLink(g.model)} has no complete run on ${slice} yet.`:`No champion yet; the goal measures the champion on ${slice}.`;
 let s=`${mLink(g.model)} holds <b>${gv(g,g.value)}</b> on ${slice}`;
 if(g.met)return s+`, past the target of ${cmpSym(g)} ${gv(g,g.target)}. Record it with <code>arx goal achieve ${esc(g.name)}</code>.`;
 const a=answers(g);
 s+=`: <b>${gamt(g,g.gap)}</b>${a!=null?` (${plural(a,'answer')})`:''} short of ${gv(g,g.target)}`;
 if(P.mode==='rel')s+=P.p<0?`, behind the baseline’s ${gv(g,P.b)}`:g.model===g.baseline?`, still the baseline`:`, ${Math.round(100*P.p)}% of the way from the baseline’s ${gv(g,P.b)}`;
 return s+'.';
}
VIEWS.goal=name=>{
 const L=S.state,g=(L.goals||{})[name];
 if(!g)return page({title:'Goal not found',crumbs:[['Goals','#goals'],[name]]})+panel('',empty(`No goal named ${esc(name)}`,'See <a class="ln" href="#goals">all goals</a>.'));
 const acts=`<span class="gl-acts">${gst(g)}${paperBtn(g)}</span>`;
 let h=page({title:g.title,crumbs:[['Goals','#goals'],[g.title,'#goal/'+enc(name)]],finding:g.error?`<span class="neg">${esc(g.error)}</span>`:finding1(g),acts});
 if(g.slice_changed)h+=`<div class="banner">The slice ${esc(g.slice)} changed since this goal opened, so it cannot be achieved. Open a new goal on the new slice.</div>`;
 if(g.problem)h+=`<p class="gl-lede">${esc(g.problem)}</p>`;
 h+=`<div class="stack">${hero(g)}${chart(g)}<div class="gl-two">${hillsPanel(g)}${g.status==='open'?nextPanel(g):record(g)}</div></div>`;
 return h;
};
const hero=function(g){
 const gap=gapFig(g),vs=vsFig(g),c=hillCounts(g),ev=g.evidence;
 const who=g.status==='achieved'?`${mLink(ev?.model)}, the model that achieved it`:g.model?`${mLink(g.model)}, the champion${g.runs>1?`, pooled over ${g.runs} runs`:''}`:'no champion';
 const head=`<div class="gl-hh"><div><div class="gl-hero">${gv(g,g.status==='achieved'?ev?.value:g.value)}</div><div class="sub">${who}${g.status==='achieved'?(ev?.task?` · <a class="ln" href="#task/${enc(ev.task)}">the run</a>`:''):g.task?` · <a class="ln" href="#task/${enc(g.task)}">latest run</a>`:''}</div></div>
  <div class="gl-hgap"><div class="gl-gv">${g.status==='achieved'||g.met?'Met':gap.v}</div><div class="sub">${g.status==='achieved'?'target reached':g.met?gap.s:'to go'+(answers(g)!=null?` · ${plural(answers(g),'more answer')}`:'')}</div></div></div>`;
 const strip=kpis([
  ['Of the way',wayText(g),prog(g).mode==='rel'?`from the baseline’s ${gv(g,prog(g).b)}`:prog(g).mode==='abs'&&prog(g).b!=null?'the baseline was already past it':'no baseline run'],
  ['vs baseline',vs.v,vs.s],
  ['Paired on',g.vs_baseline?.n?g.vs_baseline.n.toLocaleString():DASH,g.vs_baseline?.n?`questions; ${vs.wl}`:'needs a baseline run'],
  ['Hills',String(goalHills(g).length),goalHills(g).length?hillSum(g):'none serve it yet'],
 ]);
 return panel('Progress',head+track(g,{big:true})+`<div class="gl-strip">${strip}</div>`,{meta:`${esc(kpiName(g))} ${cmpSym(g)} ${gv(g,g.target)} on ${sLink(g.slice)}`,cls:'gl-prog'});
}

// ---------- runs on the goal slice over time: every run a dot, the champion's in the hue, the best so far as a step
const TSTEP=[3600,7200,10800,21600,43200,86400,172800,604800,2592000];
const offs=t=>-new Date(t*1000).getTimezoneOffset()*60;
const niceStep=function(range,maxN){const raw=range/maxN,p=Math.pow(10,Math.floor(Math.log10(raw||1)));for(const m of [1,2,2.5,5,10])if(m*p>=raw)return m*p;return 10*p}
const chart=function(g){
 const runs=slRuns(g),k=kpiKey(g),s=sgn(g),P=prog(g);
 const meta=runs.length?`${plural(runs.length,'finished run')} · ${plural(new Set(runs.map(r=>r.model)).size,'model')}`:'';
 if(!runs.length)return panel(`Runs on ${esc(g.slice)}`,empty('No finished runs on this slice yet',`The champion’s eval on the goal slice puts the first point here.${g.model?` <code>arx gate ${esc(g.model)}</code> names it.`:''}`),{meta});
 const W=Math.round(Math.max(320,Math.min(1100,(innerWidth<=900?innerWidth-34:innerWidth-228-8-48-42)))),H=innerWidth<=600?200:240;
 const Lm=52,R=16,T=26,B=26;
 const ys=runs.map(r=>r.summary[k]).concat([g.target]);if(P.b!=null)ys.push(P.b);
 let lo=Math.min(...ys),hi=Math.max(...ys);if(hi===lo){hi+=Math.abs(hi)*.05||.01;lo-=Math.abs(lo)*.05||.01}
 const stp=niceStep(hi-lo,4);lo=Math.floor(lo/stp)*stp;hi=Math.ceil(hi/stp)*stp;if(hi<=Math.max(...ys)+1e-12)hi+=stp;
 if(isScore(g)){lo=Math.max(0,lo);hi=Math.min(1,hi)}else lo=Math.max(0,lo);
 let x0=runs[0].ended,x1=Math.max(runs.at(-1).ended,g.created||0,g.achieved||0,g.abandoned||0);if(x1-x0<3600){x0-=1800;x1+=1800}
 const pad=(x1-x0)*.03;x0-=pad;x1+=pad;
 const X=x=>Lm+(x-x0)/(x1-x0)*(W-Lm-R),Y=y=>T+(1-(y-lo)/(hi-lo))*(H-T-B);
 const yl=v=>isScore(g)?(100*v).toFixed(Math.abs(Math.round(stp*1000)%10)?1:0)+'%':isTime(g)?(stp<1?v.toFixed(1):Math.round(v))+' s':kpiOf(g)==='cost'?'$'+v.toFixed(stp<.01?3:2):num(v,2);
 let o='';
 for(let v=lo;v<=hi+stp*1e-6;v+=stp)o+=`<line class="ax" x1="${Lm}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text x="${Lm-8}" y="${(Y(v)+3.5).toFixed(1)}" text-anchor="end">${yl(v)}</text>`;
 // x ticks on one round step that lands on local hours or days
 const maxN=W<480?3:W<760?4:6,span=x1-x0,step=TSTEP.find(t=>span/t<=maxN)||TSTEP.at(-1),off=offs(x0);
 const day=t=>new Date(t*1000).toLocaleDateString('en-GB',{day:'numeric',month:'short'});
 for(let t=Math.ceil((x0+off)/step)*step-off;t<=x1;t+=step){const x=X(t);if(x<Lm+14||x>W-R-14)continue;
  const lab=step>=86400||((t+offs(t))%86400===0)?day(t):clock(t);o+=`<text x="${x.toFixed(1)}" y="${H-6}" text-anchor="middle">${lab}</text>`}
 // reference lines: the target dashed in the reference colour, the baseline thin and grey; labels above their lines
 const ty=Y(g.target),by=P.b!=null?Y(P.b):null,close=by!=null&&Math.abs(ty-by)<16;
 o+=`<line x1="${Lm}" x2="${W-R}" y1="${ty.toFixed(1)}" y2="${ty.toFixed(1)}" stroke="var(--chart-3)" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${Lm+6}" y="${(ty-6).toFixed(1)}" style="fill:var(--chart-3)">Target ${cmpSym(g)} ${gv(g,g.target).replace('&nbsp;',' ')}</text>`;
 if(by!=null)o+=`<line x1="${Lm}" x2="${W-R}" y1="${by.toFixed(1)}" y2="${by.toFixed(1)}" stroke="var(--faint)" stroke-width="1"/><text x="${W-R-4}" y="${(close&&by>ty?by+14:by-6).toFixed(1)}" text-anchor="end">Baseline ${gv(g,P.b).replace('&nbsp;',' ')}</text>`;
 // when the goal opened (and closed): runs after the line are work toward it
 const marks=[[g.created,'Goal opened'],[g.achieved,'Achieved'],[g.abandoned,'Abandoned']].filter(([t])=>t&&t>=x0&&t<=x1);
 const grp=[];for(const [t,l] of marks.sort((a,b)=>a[0]-b[0])){const last=grp.at(-1);if(last&&X(t)-X(last[0])<90)last[1]+=', '+l.toLowerCase();else grp.push([t,l])}
 for(const [t,l] of grp){const x=X(t),end=x>W-R-140;o+=`<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${T-12}" y2="${H-B}" stroke="var(--control)" stroke-width="1" stroke-dasharray="3 3"/><text x="${(end?x-5:x+5).toFixed(1)}" y="${T-4}" text-anchor="${end?'end':'start'}">${l}</text>`}
 // best so far, as a step in the good direction
 let best=null,path='';
 runs.forEach((r,i)=>{const v=r.summary[k];if(best==null||s*(v-best)>0){path+=(path?`H${X(r.ended).toFixed(1)}V${Y(v).toFixed(1)}`:`M${X(r.ended).toFixed(1)} ${Y(v).toFixed(1)}`);best=v}});
 path+=`H${X(Math.min(x1,Math.max(runs.at(-1).ended,now()))).toFixed(1)}`;
 o+=`<path d="${path}" fill="none" stroke="var(--chart-1)" stroke-width="1.5" stroke-opacity=".55" stroke-linejoin="round"/>`;
 const champ=g.status==='achieved'?g.evidence?.model:g.model;
 for(const r of runs){const v=r.summary[k],me=r.model===champ,base=r.model===g.baseline&&!me,rej=S.state.models[r.model]?.status==='rejected';
  const tip=`${S.state.models[r.model]?.title||r.model} · ${gv(g,v).replace('&nbsp;',' ')} · ${stamp(r.ended)}`;
  o+=`<a href="#task/${enc(r.id)}"><circle class="gl-pt" cx="${X(r.ended).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="${me?4.5:4}" ${me?'fill="var(--chart-1)" stroke="var(--surface)" stroke-width="1.5"':base?'fill="var(--surface)" stroke="var(--muted)" stroke-width="1.5"':`fill="var(--faint)" fill-opacity="${rej?.45:.8}"`}><title>${esc(tip)}</title></circle></a>`}
 const sw=(svg,l)=>`<span class="gl-lg"><svg width="14" height="10" aria-hidden="true">${svg}</svg>${l}</span>`;
 const legend=[sw('<circle cx="7" cy="5" r="4" fill="var(--chart-1)"/>',g.status==='achieved'?'achieving model':'champion'),
  runs.some(r=>r.model===g.baseline&&r.model!==champ)?sw('<circle cx="7" cy="5" r="3.3" fill="var(--surface)" stroke="var(--muted)" stroke-width="1.5"/>','baseline'):P.b!=null?sw('<path d="M0 5H14" stroke="var(--faint)" stroke-width="1"/>','baseline'):'',
  runs.some(r=>r.model!==champ&&r.model!==g.baseline)?sw('<circle cx="7" cy="5" r="3.5" fill="var(--faint)"/>','other runs'):'',
  sw('<path d="M0 6H5V3H14" fill="none" stroke="var(--chart-1)" stroke-opacity=".55" stroke-width="1.5"/>','best so far')].join('');
 const since=g.created?runs.filter(r=>r.ended>=g.created):runs;
 const note=g.status==='open'&&g.created?(since.length?`${plural(since.length,'run')} since the goal opened ${ago(g.created)}${since.some(r=>s*(r.summary[k]-(g.value??-Infinity))>0)?'; one beat the champion and waits on the gate':''}.`:`No run on this slice since the goal opened ${ago(g.created)}.`):'';
 return panel(`Runs on ${esc(g.slice)}`,`<div class="gl-chart"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(`${runs.length} runs on ${g.slice} over time against the target`)}">${o}</svg></div>${note?`<p class="gl-note">${note}</p>`:''}`,{meta,right:`<span class="gl-lgs">${legend}</span>`,cls:'gl-runs'});
}

// ---------- hills that serve it
const hillsPanel=function(g){
 const L=S.state,hs=goalHills(g).sort((a,b)=>({open:0,climbed:1}[a[1]]??2)-({open:0,climbed:1}[b[1]]??2));
 if(!hs.length)return panel('Hills',empty('No hill serves this goal',`Open one from error analysis on the champion’s failures.`)+`<div class="gl-cmd">${cmd(`arx hill open <name> --goal ${g.name} --title "…" --target <dev slice>`)}</div>`,{cls:'gl-hills'});
 const cap=Math.max(5,hs.filter(([,s])=>s!=='closed').length),more=hs.slice(cap);
 const rows=hs.slice(0,cap).map(([k,s])=>{const x=L.hills[k]||{},sh=x.share&&x.share.of?x.share.count/x.share.of:null,p=paperOf(k);
  return `<tr class="click" onclick="if(!event.target.closest('a,button'))location.hash='hill/${enc(k)}'"><td><div class="two">${hLink(k)}<span class="sub">${x.target?`<span class="mono">${esc(short(x.target))}</span>`:'no dev set'}${p&&p.hill===k?` · <a class="ln" href="${paperUrl(p)}">notes</a>`:''}</span></div></td><td>${st(s)}</td><td class="num">${sh!=null?pct(sh):DASH}</td></tr>`});
 return panel('Hills',table([['Hill'],['Status'],['<span title="Share of the failures the hill was counted against">Share</span>','num']],rows)+(more.length?`<p class="gl-note">${plural(more.length,'more hill')}: ${more.map(([k])=>hLink(k)).join(', ')}.</p>`:''),{meta:hillSum(g),cls:'gl-hills'});
}
// ---------- what to run next on an open goal
const nextPanel=function(g){
 const L=S.state,items=[],hs=goalHills(g).map(([k])=>k),ch=L.champion;
 if(g.slice_changed)items.push([`The slice changed; open a new goal on it.`,`arx goal open <name> --title "${g.title}" --slice ${g.slice} --target ${g.target}`]);
 else if(g.met)items.push([`The champion meets the target. Record it; the paper reports the paired delta.`,`arx goal achieve ${g.name}`]);
 else if(g.value==null&&g.model)items.push([`The champion needs a run on ${esc(short(g.slice))}.`,`arx gate ${g.model}`]);
 if(!g.met&&!g.slice_changed){
  const cands=Object.entries(L.models).filter(([m,o])=>hs.includes(o.hill)&&m!==ch&&(o.status==='candidate'||o.status==='planned'))
   .map(([m,o])=>({m,o,next:L.gates?.[m]?.next||[]})).filter(c=>c.next.length).sort((a,b)=>(b.o.created||0)-(a.o.created||0));
  for(const c of cands.slice(0,3))items.push([`${mLink(c.m)} on ${hLink(c.o.hill)} needs ${c.next.map(n=>`<span class="mono">${esc(short(n.slice))}</span>`).join(', ')}.`,`arx gate ${c.m}`]);
  if(!cands.length){const oh=goalHills(g).find(([,s])=>s==='open');
   if(oh)items.push([`No candidate is climbing ${hLink(oh[0])}. Register one from the champion.`,`arx model add <name> --parent ${ch||'<champion>'} --hill ${oh[0]} --change "…"`]);
   else items.push([`No open hill serves this goal. Find the next failure mode and open one.`,`arx hill open <name> --goal ${g.name} --title "…" --target <dev slice>`]);}
 }
 if(!goalPaper(g.name))items.push([`No paper yet. Start the public paper from the worked example.`,`arx paper new --goal ${g.name}`]);
 items.push([`Check it from a shell.`,`arx goal status ${g.name}`]);
 return panel('Next',`<ul class="gl-next">${items.map(([t,c])=>`<li><p>${t}</p>${cmd(c)}</li>`).join('')}</ul>`,{cls:'gl-nx'});
}
// ---------- the record of an achieved or abandoned goal
const record=function(g){
 const ev=g.evidence;
 if(g.status==='achieved'&&ev){
  const kv=[['Model',mLink(ev.model)],['Run',ev.task?`<a class="ln mono" href="#task/${enc(ev.task)}">${esc(ev.task)}</a>${copyBtn(ev.task)}`:DASH],['Value',`${gv(g,ev.value)}${ev.runs>1?` <span class="sub">pooled over ${ev.runs} runs</span>`:''}`],['Slice',`${sLink(ev.slice||g.slice)} <span class="sub">n ${Number(ev.n||g.n).toLocaleString()}</span>`],
   ['vs baseline',ev.vs_baseline?.delta!=null?`${gchg(g,ev.vs_baseline.delta)} <span class="sub">90% CI ${pts(ev.vs_baseline.lo)} to ${pts(ev.vs_baseline.hi)}</span>`:DASH],['Achieved',g.achieved?stamp(g.achieved):DASH]];
  if(ev.forced)kv.push(['Forced','<span class="neg">target not met</span>']);
  if(ev.note)kv.push(['Note',esc(ev.note)]);
  return panel('Evidence',`<dl class="gl-kv">${kv.map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>${goalPaper(g.name)?'':`<div class="gl-cmd">${cmd('arx paper new --goal '+g.name)}</div>`}`,{cls:'gl-ev'});
 }
 if(g.status==='abandoned')return panel('Why it was abandoned',`<p class="gl-reason">${g.reason?esc(g.reason):'<span class="dash">No reason recorded</span>'}</p><p class="sub">${g.abandoned?`Abandoned ${stamp(g.abandoned)}. `:''}The negative result stays in the ledger and in its paper.</p>${goalPaper(g.name)?'':`<div class="gl-cmd">${cmd('arx paper new --goal '+g.name)}</div>`}`,{cls:'gl-ev'});
 return panel('Record',empty('Nothing recorded',''),{cls:'gl-ev'});
}
// the chart is sized to the sheet in pixels so its labels stay legible; redraw once a resize settles
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{if(route().r==='goal'&&S.state)render(true)},150)});
}
