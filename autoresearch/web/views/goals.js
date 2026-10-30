'use strict';
// goals: the number the work is for. The list answers "what are we trying to reach, how far are we, and is the gap
// closing?": each goal's biggest element is the track from its starting champion (the baseline) to its target, filled
// to where the champion stands now. A goal's page adds every run on the goal slice over time, the hills that serve it
// and what to run next. Everything is computed from /api/state `goals` (core.py goal_status) and the eval tasks.

// one block keeps these helpers out of the shared global scope the other view files load into
{
// ---------- figures, always in the goal's units: a 0/1 score as answers of N ("1,224 of 1,319", "43 more"), a
// continuous score in its slice's unit ("1,458 ms", a "minus ms" metric shown as the plain amount), latency in
// seconds, throughput in tok/s, cost in dollars. Never a bare percentage.
const kpiOf=g=>g.kpi||'score';
const isScore=g=>kpiOf(g)==='score';
const isTime=g=>/^latency/.test(kpiOf(g));
const isTput=g=>/tokens?_per_s|tok_?s\b|throughput/i.test(kpiOf(g));
const cont=g=>isScore(g)&&(g.scale==='continuous'||isCont(g.slice));
const neg=g=>cont(g)&&/^\s*minus\b/i.test(g.metric||sliceOf(g.slice).metric||'');
const sgn=g=>g.higher_is_better===false?-1:1;
const dsg=g=>neg(g)?-1:1;  // the sign a stored value takes when shown
const unitG=g=>cont(g)?(g.unit||unitOf(g.slice)||''):isTime(g)?'s':isTput(g)?'tok/s':'';
const KPI_NAME={score:'score',cost:'cost per question',latency_p50:'median latency',latency_p95:'p95 latency',latency_mean:'mean latency'};
const kpiName=g=>cont(g)?'':isTput(g)?'throughput':KPI_NAME[kpiOf(g)]||kpiOf(g);
const kpiPre=g=>{const k=kpiName(g);return k?esc(k)+' ':''};
// ---------- units: N answers of n on a 0/1 slice
const N=v=>Number(v).toLocaleString('en-US');
const byN=g=>isScore(g)&&!cont(g)&&g.n>0;
const cnt=(g,v)=>Math.round(v*g.n)+0;
const tcnt=g=>Math.ceil(g.target*g.n-1e-9)+0;  // rounded up, so rounding can't meet it; +0 turns -0 into 0
const withU=(x,u)=>u?`${x}&nbsp;${u}`:x;
// an unsigned amount in the goal's units
const gamt=function(g,d){
 d=Math.abs(d);
 if(byN(g))return N(Math.round(d*g.n));
 if(isScore(g)&&!cont(g))return (100*d).toFixed(1)+'&nbsp;pts';
 if(kpiOf(g)==='cost')return money(d);
 return withU(grp(d),unitG(g));
}
// a value as shown
const gv=function(g,v){
 if(v==null||!isFinite(v))return '—';
 if(isScore(g)&&!cont(g))return pct(v);
 if(kpiOf(g)==='cost')return money(v);
 return withU(grp(dsg(g)*v)+'',unitG(g));
}
const gu=(g,v)=>v==null||!isFinite(v)?'—':byN(g)?N(cnt(g,v)):gv(g,v);
const gt=g=>byN(g)?N(tcnt(g)):gv(g,g.target);
const ofN=g=>byN(g)?`<span class="gl-of"> of ${N(g.n)}</span>`:'';
const ofP=g=>byN(g)?` of ${N(g.n)}`:'';
// the comparator as read: a "minus ms" goal stored as score >= -1000 reads "≤ 1,000 ms"
const cmpSym=g=>sgn(g)*dsg(g)>0?'≥':'≤';
// a signed change as shown (a drop in ms reads "−458 ms"), coloured by whether it helps the goal.
// signedGood: d is already in the good direction (a paired delta); otherwise d is a raw change of the stored value
// no change, still in the goal's unit ("0 ms", "0 s"); answers of n and pts stay a bare 0
const zero=g=>`<span class="faint">${byN(g)||(isScore(g)&&!cont(g))?'0':kpiOf(g)==='cost'?money(0):withU('0',unitG(g))}</span>`;
const gsigned=(g,x)=>(x>0?'+':x<0?'−':'')+gamt(g,x);
const gchg=function(g,d,signedGood=true){
 if(d==null||!isFinite(d))return DASH;
 const good=signedGood?d:sgn(g)*d,x=dsg(g)*(signedGood?sgn(g)*d:d);
 if(Math.abs(d)<1e-12||(byN(g)&&!Math.round(Math.abs(d)*g.n)))return zero(g);
 return `<span class="${good>0?'pos':'neg'}">${gsigned(g,x)}</span>`;
}
// a paired CI (good-direction bounds) in the same terms as gchg: "+50 to +88", "−1,200 to −300 ms"
const gci=function(g,lo,hi){
 if(lo==null||hi==null)return '';
 const f=v=>dsg(g)*sgn(g)*v,[a,b]=[f(lo),f(hi)].sort((x,y)=>x-y);
 return `90% CI ${gsigned(g,a)} to ${gsigned(g,b)}`;
}
const mLink=k=>k?(S.state.models[k]?`<a class="ln" href="#model/${enc(k)}">${mn(k)}</a>`:mn(k)):'—';
const sLink=s=>`<a class="ln mono" href="#slices/${enc(s)}">${esc(s)}</a>`;
const hLink=k=>{const x=S.state.hills[k];return `<a class="ln" href="#hill/${enc(k)}">${esc(x?.title||k)}</a>`};
const kpiKey=g=>isScore(g)?'score':kpiOf(g);
// how far is left, in the KPI's units: {v:'43 more', s:'of 1,319'}, {v:'458 ms', s:'to cut'} or {v:'Met', s:'12 spare'}
const dist=function(g){
 if(g.value==null)return null;
 if(byN(g)){const d=tcnt(g)-cnt(g,g.value);return d>0?{v:`${N(d)} more`,s:`of ${N(g.n)}`,short:true}:{v:'Met',s:d?`${N(-d)} spare`:'at the line'}}
 const d=sgn(g)*(g.target-g.value);
 return d>1e-12?{v:gamt(g,d),s:cmpSym(g)==='≤'?'to cut':'to go',short:true}:{v:'Met',s:Math.abs(d)>1e-12?`${gamt(g,-d)} headroom`:'at the line'};
}
const distLine=g=>{const d=dist(g);return d?(d.short?`<span class="neg">${d.v}</span> ${d.s}`:`<span class="pos">${d.v}</span>, ${d.s}`):'<span class="faint">not measured</span>'};
// what the champion gained since the baseline, in units
const gained=function(g){
 const P=prog(g);if(P.b==null||g.value==null)return null;
 if(byN(g)){const d=cnt(g,g.value)-cnt(g,P.b);return {v:d?`<span class="${d>0?'pos':'neg'}">${d>0?'+':'−'}${N(Math.abs(d))}</span>`:'<span class="faint">0</span>',s:`from ${N(cnt(g,P.b))}`}}
 const good=sgn(g)*(g.value-P.b);
 if(Math.abs(good)<1e-12)return {v:zero(g),s:`from ${gv(g,P.b)}`};
 const timed=isTime(g)||/^(ms|s|sec|seconds?|min)$/i.test(unitG(g));
 const w=timed?(good>0?'faster':'slower'):kpiOf(g)==='cost'?(good>0?'cheaper':'dearer'):(good>0?'better':'worse');
 return {v:`<span class="${good>0?'pos':'neg'}">${gamt(g,good)} ${w}</span>`,s:`from ${gv(g,P.b)}`};
}
const ROLE={guard:'guard',sub:'sub-goal'};
const kidsOf=(name,gs)=>gs.filter(x=>x.parent===name);
const famLine=g=>{const L=S.state.goals||{},par=g.parent&&L[g.parent];return par?`<span>${esc(ROLE[g.role]||'part')} of <a class="ln" href="#goal/${enc(g.parent)}">${esc(par.title)}</a></span>`:''};
const conChips=g=>(g.constraints||[]).map(c=>`<span class="gl-con">${esc(c)}</span>`).join('');

// the baseline's value on the goal slice: the paired mean when the server paired it, else its latest run
const baseVal=function(g){
 if(g.vs_baseline?.base!=null)return g.vs_baseline.base;
 if(g.baseline&&g.baseline===g.model&&g.status!=='achieved')return g.value;  // the champion is still the baseline: same pooled figure
 if(isScore(g))return null;  // a score is only compared paired (vs_baseline); an unmatched run never stands in
 const v=g.baseline&&(S.state.leaderboard[g.slice]||{})[g.baseline]?.[kpiKey(g)];return typeof v==='number'&&isFinite(v)?v:null;  // cost, latency: latest runs
}
const comparisonNote=g=>g.status==='open'&&!g.model?'no champion yet':g.status==='open'&&g.value==null?'no run on this slice yet':({same_model:'starting point: same model',different_harness:'no matching comparison under the current harness',missing_measurement:'champion measurement missing',missing_baseline:'baseline has no complete run on this slice',paired:'paired on identical examples',unpaired:'latest runs, unpaired'}[g.comparison_state]||(g.baseline===g.model?'starting point: same model':'no compatible paired comparison'));
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
const ST_LABEL={open:'Open',achieved:'Achieved',abandoned:'Abandoned'};
const gst=g=>st(g.status,ST_LABEL[g.status]||g.status);
const ORDER={open:0,achieved:1,abandoned:2};
// open goals: met first (they wait on a command), then the furthest along
// a guard (must not regress) or sub-goal serves a main goal: it never leads the list or the headline
const isMain=g=>!g.role||g.role==='main';
const rank=g=>g.status!=='open'?0:g.met?2:((p=>p.mode==='rel'?Math.max(-1,Math.min(1,p.p)):-1)(prog(g)));

// ---------- one encoding for every goal bar (goal page, map, Overview, Start): rel fills from the baseline (0) to the
// target (1); abs draws the KPI's own scale from 0 with the target as a tick (mark), so 13 s under a 45 s line shows
// its headroom instead of a full bar
const bar=function(g){
 const P=prog(g),cl=x=>Math.max(0,Math.min(1,x));
 if(P.mode==='rel')return {f:g.met?1:cl(P.p),mark:null};
 if(P.mode!=='abs')return {f:0,mark:null};
 const D=v=>byN(g)?v:dsg(g)*v,top=byN(g)?1:Math.max(D(P.v),D(P.t),P.b!=null?D(P.b):0)*1.15||1;
 return {f:cl(D(P.v)/top),mark:cl(D(P.t)/top)};
}
// ---------- the track: baseline on the left, target on the right, filled to the champion now
const track=function(g,{big=false}={}){
 const P=prog(g),pc=f=>(100*Math.max(0,Math.min(1,f))).toFixed(1)+'%';
 if(P.mode==='none')return `<div class="gl-trk"><div class="gl-bar"></div><div class="gl-ends"><span>${g.model?`${mLink(g.model)} has no complete run on this slice`:'No champion yet'}</span><span>Target <b>${cmpSym(g)}&nbsp;${gt(g)}</b></span></div></div>`;
 if(P.mode==='rel'){
  const met=g.met,p=P.p,cls=met?'met':p<0?'back':'';
  return `<div class="gl-trk ${big?'big':''}" role="img" aria-label="${esc(`${Math.round(100*p)}% of the way from the baseline to the target`)}">
   <div class="gl-bar ${cls}"><i style="width:${pc(p)}"></i>${p>0&&p<1?`<b style="left:${pc(p)}"></b>`:''}</div>
   <div class="gl-ends"><span>Baseline <b>${gu(g,P.b)}</b>${big?`<span class="gl-bn"> · ${mLink(g.baseline)}</span>`:''}</span><span>Target <b>${cmpSym(g)}&nbsp;${gt(g)}</b>${ofP(g)}</span></div></div>`;
 }
 // abs: the KPI's own scale from 0, the target as a tick; lower-is-better fills to the value and passes left of the tick
 const {f,mark:m}=bar(g),mp=(100*m).toFixed(1);
 return `<div class="gl-trk abs ${big?'big':''}">
  <div class="gl-tgt"><span style="--m:${mp}">Target <b>${cmpSym(g)}&nbsp;${gt(g)}</b></span></div>
  <div class="gl-bar ${g.met?'met':''}"><i style="width:${pc(f)}"></i><b class="tgt" style="left:${pc(m)}"></b></div>
  <div class="gl-ends"><span>${P.b!=null?`Baseline <b>${gu(g,P.b)}</b>${big&&g.baseline?`<span class="gl-bn"> · ${mLink(g.baseline)}</span>`:''}${sgn(g)*(P.b-P.t)>=0?', already past the target':''}`:esc(comparisonNote(g))}</span><span>${byN(g)?N(g.n):''}</span></div></div>`;
}
// "62% of the way", "met", "behind the baseline"
const gapFig=function(g){
 const d=dist(g);
 if(!d)return {v:DASH,s:'no run yet'};
 return d;
}
const gainFig=g=>gained(g)||{v:DASH,s:g.baseline?comparisonNote(g):'no baseline'};
const vsFig=function(g){
 const v=g.vs_baseline,P=prog(g);
 if(v&&v.delta!=null)return {v:gchg(g,v.delta),s:`${byN(g)?`of ${N(g.n)} · `:''}${gci(g,v.lo,v.hi)}`,wl:`better on ${v.wins}, worse on ${v.losses}`};
 if(g.value==null)return {v:DASH,s:'no run yet'};
 if(g.baseline&&g.model&&g.baseline===g.model)return {v:zero(g),s:'the champion is still the baseline'};
 if(P.b!=null&&g.value!=null)return {v:gchg(g,g.value-P.b,false),s:'latest runs, unpaired'};
 return {v:DASH,s:g.baseline?comparisonNote(g):'no baseline'};
}
const paperBtn=g=>(g.model?`<a class="btn" href="reference/${enc(g.model)}">Model paper</a>`:'')+(g=>{const p=goalPaper(g.name);return p?`<a class="btn" href="${paperUrl(p)}">${ICON.papers}${g.status==='open'?'Draft paper':'Paper'}${p.waiting?`<span class="gl-wait">${p.waiting}</span>`:''}</a>`:''})(g);

// ---------- list
VIEWS.goals=()=>{
 const L=S.state,gs=Object.values(L.goals||{}).sort((a,b)=>(ORDER[a.status]??3)-(ORDER[b.status]??3)||isMain(b)-isMain(a)||rank(b)-rank(a)||(b.created||0)-(a.created||0));
 const open=gs.filter(g=>g.status==='open'),done=gs.filter(g=>g.status==='achieved'),gone=gs.filter(g=>g.status!=='open'&&g.status!=='achieved');
 const mains=open.filter(isMain),met=mains.filter(g=>g.met&&!g.slice_changed);
 const lead=mains.filter(g=>!g.met&&prog(g).mode==='rel').sort((a,b)=>prog(b).p-prog(a).p)[0]||mains.find(g=>!g.met&&dist(g));
 const gl=g=>`<a href="#goal/${enc(g.name)}"><b>${esc(g.title)}</b></a>`;
 let finding='';
 if(gs.length){
  if(!open.length)finding=`No open goals. ${[done.length?`${done.length} achieved`:'',gone.length?`${gone.length} abandoned`:''].filter(Boolean).join(', ')}.`;
  else{
   finding=`<b>${open.length} open ${term('goal',open.length===1?'goal':'goals')}</b>. `;
   if(met.length)finding+=`${gl(met[0])} meets its target and waits to be recorded.`;
   else if(lead){const d=dist(lead);finding+=`${mains.length>1?'Furthest along: ':''}${gl(lead)}, ${d.v} ${d.s}.`}
   else finding+=open.some(g=>g.value==null)?'The champion has no complete run on a goal slice yet.':'No goal has a baseline to measure progress from.';
  }
 }
 const acts=met.length?cmd('arx goal achieve '+met[0].name):'';
 let h=page({title:'Goals',crumbs:[['Goals','#goals']],finding,acts})+intake();
 if(!gs.length)return h;
 const linked=gs.some(g=>g.parent&&L.goals[g.parent]);
 if(linked||open.length>1)h+=goalMap(gs.filter(g=>g.status==='open'||kidsOf(g.name,gs).some(k=>k.status==='open')));
 if(open.length)h+=`<section class="gl-grp"><div class="gl-gh"><h2>Open</h2><span class="meta">${open.length}</span></div><div class="gl-cards">${open.map(card).join('')}</div></section>`;
 if(done.length)h+=`<section class="gl-grp"><div class="gl-gh"><h2>Achieved</h2><span class="meta">${done.length}</span></div><div class="gl-cards">${done.map(card).join('')}</div></section>`;
 if(gone.length)h+=`<section class="gl-grp"><div class="gl-gh"><h2>Abandoned</h2><span class="meta">${gone.length}</span></div>${panel('',table([['Goal'],['Why it was abandoned'],['Best','num'],['Target','num']],gone.map(g=>`<tr class="click" onclick="if(!event.target.closest('a,button'))location.hash='goal/${enc(g.name)}'"><td><div class="two"><a href="#goal/${enc(g.name)}"><b>${esc(g.title)}</b></a><span class="sub mono">${esc(g.slice)}</span></div></td><td class="gl-why">${g.reason?esc(g.reason):'<span class="dash">No reason recorded</span>'}</td><td class="num">${gu(g,g.value)}${ofP(g)}</td><td class="num">${cmpSym(g)}&nbsp;${gt(g)}${ofP(g)}</td></tr>`)),{cls:'gl-ab'})}</section>`;
 return h;
};
const card=function(g){
 const gap=gapFig(g),vs=vsFig(g),hs=goalHills(g),gn=gainFig(g),ev=g.evidence;
 const who=g.status==='achieved'?`achieved by ${mLink(ev?.model||g.model)}${g.achieved?`, ${stamp(g.achieved)}`:''}`:g.model?`${mLink(g.model)}, champion${g.runs>1?` · ${g.runs} runs pooled`:''}`:'no champion';
 return `<section class="card gl-card ${esc(g.status)}">
  <div class="gl-top">${gst(g)}${g.role&&g.role!=='main'?pill(ROLE[g.role]||g.role,g.role==='guard'?'ghost':'acc'):''}${g.slice_changed?pill('slice changed','neg'):''}${ev?.forced?pill('forced, target not met','warn'):''}<h3><a href="#goal/${enc(g.name)}">${esc(g.title)}</a></h3><span class="gl-r">${paperBtn(g)}</span></div>
  <p class="gl-meta">${famLine(g)}${sLink(g.slice)}<span>${kpiPre(g)}${cmpSym(g)} ${gt(g)}${byN(g)?` of ${N(g.n)}`:''}</span>${conChips(g)}${g.created?`<span>opened ${stamp(g.created)}</span>`:''}</p>
  <div class="gl-body">
   <div class="gl-now"><div class="gl-big">${gu(g,g.status==='achieved'&&ev?ev.value:g.value)}${g.value!=null?ofN(g):''}</div><div class="sub">${who}</div></div>
   <div class="gl-mid">${track(g)}</div>
   <dl class="gl-figs">
    <div><dt>To go</dt><dd>${g.status==='achieved'?'Met':gap.v}</dd><dd class="sub">${gap.s}</dd></div>
    <div><dt>Since baseline</dt><dd>${gn.v}</dd><dd class="sub">${gn.s}</dd></div>
    <div><dt>vs baseline</dt><dd>${vs.v}</dd><dd class="sub" title="${esc((g.baseline?(S.state.models[g.baseline]?.title||g.baseline)+': ':'')+vs.s.replace(/&nbsp;/g,' '))}">${vs.s}</dd></div>
   </dl>
  </div>
  <div class="gl-foot"><span class="gl-hl">${hs.length?`Hills: ${hs.slice(0,4).map(([k,s])=>`${hLink(k)}<span class="faint"> ${esc(s)}</span>`).join(', ')}${hs.length>4?`, +${hs.length-4} more`:''}`:'<span class="faint">No hill serves this goal yet</span>'}</span><a class="more" href="#goal/${enc(g.name)}">Runs and next steps</a></div>
 </section>`;
}

// ---------- the map: each main goal with its guards and sub-goals under it
const mapNode=function(g,gs,depth=0){
 const d=dist(g),P=prog(g),kids=kidsOf(g.name,gs);
 const B=bar(g),f=g.status==='achieved'&&B.mark==null?1:B.f;
 const fig=g.status==='abandoned'?'<span class="faint">abandoned</span>':g.status==='achieved'?'<span class="pos">Achieved</span>':d?(d.short?`<span class="neg">${d.v}</span> <span class="faint">${d.s}</span>`:`<span class="pos">Met</span> <span class="faint">${d.s}</span>`):'<span class="faint">not measured</span>';
 const grp=(r,l)=>{const k=kids.filter(x=>(x.role||'sub')===r);return k.length?`<div class="gm-lvl"><div class="gm-lab">${l}</div>${k.map(x=>mapNode(x,gs,depth+1)).join('')}</div>`:''};
 return `<div class="gm-tree${depth?'':' root'}"><a class="gm-node ${esc(g.role||'main')} ${esc(g.status)}" href="#goal/${enc(g.name)}"><span class="gm-t">${esc(g.title)}</span><span class="gm-d num">${fig}</span><span class="gm-bar ${g.met||g.status==='achieved'?'met':''} ${g.value==null?'none':''}"><i style="width:${(100*f).toFixed(1)}%"></i>${B.mark!=null?`<b style="left:${(100*B.mark).toFixed(1)}%"></b>`:''}</span><span class="gm-m mono">${kpiPre(g)}${cmpSym(g)} ${gt(g)}${byN(g)?` of ${N(g.n)}`:''}</span></a>${depth<3?grp('guard','Guards')+grp('sub','Sub-goals')+grp('main','Under it'):''}</div>`;
}
const goalMap=function(gs,{title='Map',focus=null}={}){
 const names=new Set(gs.map(g=>g.name)),roots=gs.filter(g=>!g.parent||!names.has(g.parent));
 return panel(title,`<div class="gm">${roots.map(r=>mapNode(r,gs)).join('')}</div>`,{cls:'gm-panel'+(focus?' focus':''),meta:`${plural(gs.length,'goal')}`});
}
const family=function(g){
 const all=Object.values(S.state.goals||{});let root=g,seen=new Set([g.name]);
 while(root.parent&&S.state.goals[root.parent]&&!seen.has(root.parent)){seen.add(root.parent);root=S.state.goals[root.parent]}
 const inTree=[],walk=n=>{inTree.push(n);kidsOf(n.name,all).forEach(walk)};walk(root);
 return inTree.length>1?goalMap(inTree,{focus:g.name}).replace(`href="#goal/${enc(g.name)}"`,`href="#goal/${enc(g.name)}" aria-current="page"`):'';
}

// ---------- detail
const finding1=function(g){
 const P=prog(g),slice=`${sLink(g.slice)} (n ${N(g.n||0)})`;
 if(g.status==='abandoned')return `Abandoned${g.abandoned?` ${stamp(g.abandoned)}`:''} at ${gu(g,g.value)} against a target of ${cmpSym(g)} ${gt(g)} on ${slice}.`;
 if(g.status==='achieved'){const ev=g.evidence||{};return `Achieved${g.achieved?` ${stamp(g.achieved)}`:''} by <b>${mLink(ev.model)}</b> at <b>${gu(g,ev.value)}</b>${ofP(g)} on ${slice}${ev.forced?', forced without the target met':''}${g.vs_baseline?.delta!=null?`, ${gchg(g,g.vs_baseline.delta)} against the baseline ${mLink(g.baseline)}`:''}.`}
 if(g.value==null)return g.model?`The champion ${mLink(g.model)} has no complete run on ${slice} yet.`:`No champion yet; the goal measures the champion on ${slice}.`;
 let s=`${mLink(g.model)} holds <b>${gu(g,g.value)}</b>${ofP(g)} on ${sLink(g.slice)}`;
 if(g.met)return s+`, past the target of ${cmpSym(g)} ${gt(g)}. Record it with <code>arx goal achieve ${esc(g.name)}</code>.`;
 const d=dist(g);
 s+=`: <b>${d.v}</b> ${d.s}${byN(g)?` to reach ${gt(g)}`:''}`;
 if(P.mode==='rel'&&P.p<0)s+=`, behind the baseline’s ${gu(g,P.b)}`;
 else if(P.mode==='rel'&&g.model===g.baseline)s+=`, still the baseline`;
 return s+'.';
}
VIEWS.goal=name=>{
 const L=S.state,g=(L.goals||{})[name];
 if(!g)return page({title:'Goal not found',crumbs:[['Goals','#goals'],[name]]})+panel('',empty(`No goal named ${esc(name)}`,'See <a class="ln" href="#goals">all goals</a>.'));
 const acts=`<span class="gl-acts">${g.role&&g.role!=='main'?pill(ROLE[g.role]||g.role,g.role==='guard'?'ghost':'acc'):''}${gst(g)}${paperBtn(g)}</span>`;
 let h=page({title:g.title,crumbs:[['Goals','#goals'],[g.title,'#goal/'+enc(name)]],finding:g.error?`<span class="neg">${esc(g.error)}</span>`:finding1(g),acts});
 if(g.slice_changed)h+=`<div class="banner">The slice ${esc(g.slice)} changed since this goal opened, so it cannot be achieved. Open a new goal on the new slice.</div>`;
 if(g.problem)h+=`<p class="gl-lede">${esc(g.problem)}</p>`;
 if(g.constraints?.length)h+=`<p class="gl-cons">${conChips(g)}</p>`;
 h+=`<div class="stack">${hero(g)}${laterEvidence(g)}${family(g)}${chart(g)}<div class="gl-two">${hillsPanel(g)}${g.status==='open'?nextPanel(g):record(g)}</div></div>`;
 return h;
};
const laterEvidence=g=>{
 const c=g.current_observation;
 if(!c||(c.task===g.task&&c.runs===g.runs))return '';
 return panel('Later observations',`<p>${mLink(c.model)} now pools ${byN(g)&&c.value!=null?N(Number((c.value*g.n).toFixed(2))):gu(g,c.value)}${ofP(g)} across ${N(c.runs)} runs. ${c.met?'This pooled measurement meets':'This pooled measurement does not meet'} the target. The achievement above retains its recorded evidence.</p>${c.task?`<a class="ln" href="#task/${enc(c.task)}">Latest observed run</a>`:''}`);
};
const hero=function(g){
 const gap=gapFig(g),vs=vsFig(g),gn=gainFig(g),ev=g.evidence;
 const who=g.status==='achieved'?`${mLink(ev?.model)}, the model that achieved it`:g.model?`${mLink(g.model)}, the champion${g.runs>1?`, pooled over ${g.runs} runs`:''}`:'no champion';
 const head=`<div class="gl-hh"><div><div class="gl-hero">${gu(g,g.status==='achieved'?ev?.value:g.value)}${ofN(g)}</div><div class="sub">${who}${g.status==='achieved'?(ev?.task?` · <a class="ln" href="#task/${enc(ev.task)}">the run</a>`:''):g.task?` · <a class="ln" href="#task/${enc(g.task)}">latest run</a>`:''}</div></div>
  <div class="gl-hgap"><div class="gl-gv">${g.status==='achieved'?'Met':gap.v}</div><div class="sub">${g.status==='achieved'?'target reached':gap.s}</div></div></div>`;
 const strip=kpis([
  ['Since baseline',gn.v,gn.s],
  ['vs baseline',vs.v,vs.s],
  ['Paired on',g.vs_baseline?.n?N(g.vs_baseline.n):DASH,g.vs_baseline?.n?`questions; ${vs.wl}`:comparisonNote(g)],
  ['Hills',String(goalHills(g).length),goalHills(g).length?hillSum(g):'none serve it yet'],
 ]);
 return panel('Progress',head+track(g,{big:true})+`<div class="gl-strip">${strip}</div>`,{meta:`${kpiPre(g)}${cmpSym(g)} ${gt(g)}${byN(g)?` of ${N(g.n)}`:''} on ${sLink(g.slice)}`,cls:'gl-prog'});
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
 // plotted in the units the page reads in: answers of n, or the slice's unit with a "minus ms" metric turned positive
 const D=v=>byN(g)?v*g.n:dsg(g)*v;
 const ys=runs.map(r=>D(r.summary[k])).concat([D(g.target)]);if(P.b!=null)ys.push(D(P.b));
 if(!ys.every(isFinite))return panel(`Runs on ${esc(g.slice)}`,empty('These runs have no plottable values',''),{meta});
 let lo=Math.min(...ys),hi=Math.max(...ys);if(hi===lo){hi+=Math.abs(hi)*.05||1;lo-=Math.abs(lo)*.05||1}
 const stp=byN(g)?Math.max(1,niceStep(hi-lo,4)):niceStep(hi-lo,4);lo=Math.floor(lo/stp)*stp;hi=Math.ceil(hi/stp)*stp;if(hi<=Math.max(...ys)+1e-12)hi+=stp;
 if(Math.min(...ys)>=0)lo=Math.max(0,lo);if(byN(g))hi=Math.min(Math.max(g.n,Math.max(...ys)),hi);
 let x0=runs[0].ended,x1=Math.max(runs.at(-1).ended,g.created||0,g.achieved||0,g.abandoned||0);if(x1-x0<3600){x0-=1800;x1+=1800}
 const pad=(x1-x0)*.03;x0-=pad;x1+=pad;
 const X=x=>Lm+(x-x0)/(x1-x0)*(W-Lm-R),Y=y=>T+(1-(y-lo)/(hi-lo))*(H-T-B);
 const yl=v=>{v=Math.abs(v)<stp*1e-6?0:v;return byN(g)?N(Math.round(v)):kpiOf(g)==='cost'?'$'+v.toFixed(stp<.01?3:2):(grp(v)+' '+unitG(g)).trim()};
 let o='';
 for(let v=lo;v<=hi+stp*1e-6;v+=stp)o+=`<line class="ax" x1="${Lm}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text x="${Lm-8}" y="${(Y(v)+3.5).toFixed(1)}" text-anchor="end">${yl(v)}</text>`;
 // x ticks on one round step that lands on local hours or days
 const maxN=W<480?3:W<760?4:6,span=x1-x0,step=TSTEP.find(t=>span/t<=maxN)||TSTEP.at(-1),off=offs(x0);
 const day=t=>new Date(t*1000).toLocaleDateString('en-GB',{day:'numeric',month:'short'});
 for(let t=Math.ceil((x0+off)/step)*step-off;t<=x1;t+=step){const x=X(t);if(x<Lm+14||x>W-R-14)continue;
  const lab=step>=86400||((t+offs(t))%86400===0)?day(t):clock(t);o+=`<text x="${x.toFixed(1)}" y="${H-6}" text-anchor="middle">${lab}</text>`}
 // reference lines: the target dashed in the reference colour, the baseline thin and grey; labels above their lines
 // a label sits above its line, or below it when the line runs along the top where the goal-opened mark is written
 const ty=Y(D(g.target)),by=P.b!=null?Y(D(P.b)):null,close=by!=null&&Math.abs(ty-by)<16,ly=y=>y-6<T+8?y+14:y-6;
 const plain=h=>h.replace(/&nbsp;/g,' ');
 o+=`<line x1="${Lm}" x2="${W-R}" y1="${ty.toFixed(1)}" y2="${ty.toFixed(1)}" stroke="var(--chart-3)" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${Lm+6}" y="${ly(ty).toFixed(1)}" style="fill:var(--chart-3)">Target ${cmpSym(g)} ${plain(gt(g))}</text>`;
 if(by!=null)o+=`<line x1="${Lm}" x2="${W-R}" y1="${by.toFixed(1)}" y2="${by.toFixed(1)}" stroke="var(--faint)" stroke-width="1"/><text x="${W-R-4}" y="${(close?(by>ty?by+14:by-6):ly(by)).toFixed(1)}" text-anchor="end">Baseline ${plain(gu(g,P.b))}</text>`;
 // when the goal opened (and closed): runs after the line are work toward it
 const marks=[[g.created,'Goal opened'],[g.achieved,'Achieved'],[g.abandoned,'Abandoned']].filter(([t])=>t&&t>=x0&&t<=x1);
 const mk=[];for(const [t,l] of marks.sort((a,b)=>a[0]-b[0])){const last=mk.at(-1);if(last&&X(t)-X(last[0])<90)last[1]+=', '+l.toLowerCase();else mk.push([t,l])}
 for(const [t,l] of mk){const x=X(t),end=x>W-R-140;o+=`<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${T-12}" y2="${H-B}" stroke="var(--control)" stroke-width="1" stroke-dasharray="3 3"/><text x="${(end?x-5:x+5).toFixed(1)}" y="${T-4}" text-anchor="${end?'end':'start'}">${l}</text>`}
 // best so far, as a step in the good direction
 let best=null,path='';
 runs.forEach((r,i)=>{const v=r.summary[k];if(best==null||s*(v-best)>0){path+=(path?`H${X(r.ended).toFixed(1)}V${Y(D(v)).toFixed(1)}`:`M${X(r.ended).toFixed(1)} ${Y(D(v)).toFixed(1)}`);best=v}});
 path+=`H${X(Math.min(x1,Math.max(runs.at(-1).ended,now()))).toFixed(1)}`;
 o+=`<path d="${path}" fill="none" stroke="var(--chart-1)" stroke-width="1.5" stroke-opacity=".55" stroke-linejoin="round"/>`;
 const champ=g.status==='achieved'?g.evidence?.model:g.model;
 for(const r of runs){const v=r.summary[k],me=r.model===champ,base=r.model===g.baseline&&!me,rej=S.state.models[r.model]?.status==='rejected';
  const tip=`${mnt(r.model)} · ${plain(gu(g,v)+ofP(g))} · ${stamp(r.ended)}`;
  o+=`<a href="#task/${enc(r.id)}"><circle class="gl-pt" cx="${X(r.ended).toFixed(1)}" cy="${Y(D(v)).toFixed(1)}" r="${me?4.5:4}" ${me?'fill="var(--chart-1)" stroke="var(--surface)" stroke-width="1.5"':base?'fill="var(--surface)" stroke="var(--muted)" stroke-width="1.5"':`fill="var(--faint)" fill-opacity="${rej?.45:.8}"`}><title>${esc(tip)}</title></circle></a>`}
 const sw=(svg,l)=>`<span class="gl-lg"><svg width="14" height="10" aria-hidden="true">${svg}</svg>${l}</span>`;
 const legend=[sw('<circle cx="7" cy="5" r="4" fill="var(--chart-1)"/>',g.status==='achieved'?'achieving model':'champion'),
  runs.some(r=>r.model===g.baseline&&r.model!==champ)?sw('<circle cx="7" cy="5" r="3.3" fill="var(--surface)" stroke="var(--muted)" stroke-width="1.5"/>','baseline'):P.b!=null?sw('<path d="M0 5H14" stroke="var(--faint)" stroke-width="1"/>','baseline'):'',
  runs.some(r=>r.model!==champ&&r.model!==g.baseline)?sw('<circle cx="7" cy="5" r="3.5" fill="var(--faint)"/>','other runs'):'',
  sw('<path d="M0 6H5V3H14" fill="none" stroke="var(--chart-1)" stroke-opacity=".55" stroke-width="1.5"/>','best so far')].join('');
 const since=g.created?runs.filter(r=>r.ended>=g.created):runs;
 // a run above the champion is news only with its model's standing: rejected, failed a rung, ready, or still on the gate
 const top=since.filter(r=>r.model!==champ&&s*(r.summary[k]-(g.value??-Infinity))>0).sort((a,b)=>s*(b.summary[k]-a.summary[k]))[0];
 const standing=m=>{const o=S.state.models[m]||{},gt=S.state.gates?.[m],f=gt?.rungs?.find(r=>r.status==='fail');
  return o.status==='rejected'?'<span class="neg">was rejected</span>':o.status!=='candidate'?`is ${esc(o.status||'not on the ladder')}`:f?`<span class="neg">failed the ${esc(f.rung)} rung</span>`:gt?.promotable?'<span class="pos">is ready to promote</span>':'waits on the gate'};
 const note=g.status==='open'&&g.created?(since.length?`${plural(since.length,'run')} since the goal opened ${ago(g.created)}${top?`; the best, ${mLink(top.model)} at ${gu(g,top.summary[k])}${ofP(g)}, ${standing(top.model)}`:''}.`:`No run on this slice since the goal opened ${ago(g.created)}.`):'';
 return panel(`Runs on ${esc(g.slice)}`,`<div class="gl-chart"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(`${runs.length} runs on ${g.slice} over time against the target`)}">${o}</svg></div>${note?`<p class="gl-note">${note}</p>`:''}`,{meta,right:`<span class="gl-lgs">${legend}</span>`,cls:'gl-runs'});
}

// ---------- hills that serve it
const hillsPanel=function(g){
 const L=S.state,hs=goalHills(g).sort((a,b)=>({open:0,climbed:1}[a[1]]??2)-({open:0,climbed:1}[b[1]]??2));
 if(!hs.length)return panel('Hills',empty('No hill serves this goal',`Open one from error analysis on the champion’s failures.`)+`<div class="gl-cmd">${cmd(`arx hill open <name> --goal ${g.name} --title "…" --target <dev slice>`)}</div>`,{cls:'gl-hills'});
 const cap=Math.max(5,hs.filter(([,s])=>s!=='closed').length),more=hs.slice(cap);
 const rows=hs.slice(0,cap).map(([k,s])=>{const x=L.hills[k]||{},sh=x.share&&x.share.of?x.share.count/x.share.of:null,p=paperOf(k);
  const ow=sh!=null?String(x.share.of_what||'').replace(new RegExp('^of\\s+('+x.share.of+'\\s+)?','i'),'').trim():'';
  return `<tr class="click" onclick="if(!event.target.closest('a,button'))location.hash='hill/${enc(k)}'"><td><div class="two">${hLink(k)}<span class="sub">${x.target?`<span class="mono">${esc(short(x.target))}</span>`:'no dev set'}${p&&p.hill===k?` · <a class="ln" href="${paperUrl(p)}">notes</a>`:''}</span></div></td><td>${st(s)}</td><td class="num gl-sh">${sh!=null?`<div class="two"><span>${N(x.share.count)} <span class="faint">of ${N(x.share.of)}</span></span>${ow?`<span class="sub ell" title="${esc(ow)}">${esc(ow)}</span>`:''}</div>`:DASH}</td></tr>`});
 return panel(term('hill','Hills'),table([['Hill'],['Status'],['Share','num']],rows)+(more.length?`<p class="gl-note">${plural(more.length,'more hill')}: ${more.map(([k])=>hLink(k)).join(', ')}.</p>`:''),{meta:hillSum(g),cls:'gl-hills'});
}
// ---------- what to run next on an open goal
const nextPanel=function(g){
 const L=S.state,items=[],hs=goalHills(g).map(([k])=>k),ch=L.champion;
 if(g.slice_changed)items.push([`The slice changed; open a new goal on it.`,`arx goal open <name> --title "${g.title}" --slice ${g.slice} --target ${g.target}`]);
 else if(g.met)items.push([`The champion meets the target. Record it; the paper reports the paired delta.`,`arx goal achieve ${g.name}`]);
 else if(g.value==null&&g.model)items.push([`The champion needs a run on ${esc(short(g.slice))}.`,goalMeasureCmd(g)]);
 if(!g.met&&!g.slice_changed){
  // the candidates nearest the goal first (most rungs passed), never one the champion already supersedes
  const passed=m=>(L.gates?.[m]?.rungs||[]).filter(r=>r.status==='pass').length;
  const cands=Object.entries(L.models).filter(([m,o])=>hs.includes(o.hill)&&m!==ch&&(o.status==='candidate'||o.status==='planned')&&!superseded(m))
   .map(([m,o])=>({m,o,next:L.gates?.[m]?.next||[]})).sort((a,b)=>passed(b.m)-passed(a.m)||(b.o.created||0)-(a.o.created||0));
  // a next run already in progress: what it covers and its live chip, in place of a command
  const ms=a=>a.map(n=>`<span class="mono">${esc(short(n.slice))}</span>`).join(', ');
  const rung=m=>(L.gates?.[m]?.rungs||[]).find(r=>r.status==='pending')?.rung;
  for(const c of cands.slice(0,3)){
   const gate=L.gates?.[c.m];
   if(gate?.promotable){items.push([`${mLink(c.m)} passed every rung and is ready for promotion review.`,`arx promote ${c.m}`]);continue}
   if(gate?.rungs?.some(r=>r.status==='fail')){items.push([`${mLink(c.m)} failed a gate check. Inspect its comparison before closing or revising it.`,`arx gate ${c.m}`]);continue}
   if(!c.next.length){items.push([`${mLink(c.m)} is registered; inspect its gate and declared change.`,`arx gate ${c.m}`]);continue}
   const run=c.next.find(runTask),rest=c.next.filter(n=>!runTask(n));
   // a run the gate still counts as started, whose task went silent for over a day: dead, so it is run again
   const dead=c.next.find(n=>n.running&&byId(n.running)?.status==='stalled');
   const dt=dead&&byId(dead.running),at=rung(c.m)?` (${esc(rung(c.m))} rung)`:'';
   items.push(dead?[`${mLink(c.m)}${at}: its run on <span class="mono">${esc(short(dead.slice))}</span> went silent${dt?` ${ago(dt.heartbeat||dt.updated||dt.created)}`:''}${dt?.progress?.total?` at <a class="ln" href="#task/${enc(dt.id)}">${N(dt.progress.done||0)} of ${N(dt.progress.total)}</a>`:''}. Fail it, then run it again.`,dt?`arx task finish ${dt.id} --status failed`:`arx gate ${c.m}`]
    :run?[`${mLink(c.m)} on ${hLink(c.o.hill)} is running on <span class="mono">${esc(short(runTask(run).slice||run.slice))}</span>${rest.length?`, then needs ${rest.map(n=>(n.model!==c.m?'champion on ':'')+ms([n])).join(', ')}`:''}.`,null,runChip(run)]
    :[`${mLink(c.m)}${at} on ${hLink(c.o.hill)} needs ${ms(c.next)}.`,`arx gate ${c.m}`]);}
  if(!cands.length){const oh=goalHills(g).find(([,s])=>s==='open');
   if(oh)items.push([`No candidate is climbing ${hLink(oh[0])}. Register one from the champion.`,`arx model add <name> --parent ${ch||'<champion>'} --hill ${oh[0]} --change "…"`]);
   else items.push([`No open hill serves this goal. Find the next failure mode and open one.`,`arx hill open <name> --goal ${g.name} --title "…" --target <dev slice>`]);}
 }
 if(!goalPaper(g.name))items.push([`No paper yet. Start the public paper from the worked example.`,`arx paper new --goal ${g.name}`]);
 items.push([`Check it from a shell.`,`arx goal status ${g.name}`]);
 return panel('Next',`<ul class="gl-next">${items.map(([t,c,chip])=>`<li><p>${t}</p>${chip||cmd(c)}</li>`).join('')}</ul>`,{cls:'gl-nx'});
}
// ---------- the record of an achieved or abandoned goal
const record=function(g){
 const ev=g.evidence;
 if(g.status==='achieved'&&ev){
  const kv=[['Model',mLink(ev.model)],['Run',ev.task?`<a class="ln mono" href="#task/${enc(ev.task)}">${esc(ev.task)}</a>${copyBtn(ev.task)}`:DASH],['Value',`${gu(g,ev.value)}${ofP(g)}${ev.runs>1?` <span class="sub">pooled over ${ev.runs} runs</span>`:''}`],['Slice',`${sLink(ev.slice||g.slice)} <span class="sub">n ${Number(ev.n||g.n).toLocaleString()}</span>`],
   ['vs baseline',ev.vs_baseline?.delta!=null?`${gchg(g,ev.vs_baseline.delta)}${ofP(g)} <span class="sub">${gci(g,ev.vs_baseline.lo,ev.vs_baseline.hi)}</span>`:DASH],['Achieved',g.achieved?stamp(g.achieved):DASH]];
  if(ev.forced)kv.push(['Forced','<span class="neg">target not met</span>']);
  if(ev.note)kv.push(['Note',esc(ev.note)]);
  return panel('Evidence',`<dl class="gl-kv">${kv.map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>${goalPaper(g.name)?'':`<div class="gl-cmd">${cmd('arx paper new --goal '+g.name)}</div>`}`,{cls:'gl-ev'});
 }
 if(g.status==='abandoned')return panel('Why it was abandoned',`<p class="gl-reason">${g.reason?esc(g.reason):'<span class="dash">No reason recorded</span>'}</p><p class="sub">${g.abandoned?`Abandoned ${stamp(g.abandoned)}. `:''}The negative result stays in the ledger and in its paper.</p>${goalPaper(g.name)?'':`<div class="gl-cmd">${cmd('arx paper new --goal '+g.name)}</div>`}`,{cls:'gl-ev'});
 return panel('Record',empty('Nothing recorded',''),{cls:'gl-ev'});
}
// ---------- goal intake: the ask in your own words -> an agent's proposal (intake.py) -> answer, edit, open
const IN={draft:'',ed:{},ans:{},err:{},busy:{}};
const LOWER=['cost','latency_p50','latency_p95','latency_mean'];
const KPI_OPTS=[['score','Correct answers'],['latency_p50','Median seconds'],['latency_p95','p95 seconds'],['cost','Cost per answer']];
const ipost=(verb,body)=>fetch('api/intake/'+verb,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
 .then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.statusText);return j});
const why=t=>t?`<span class="gi-why" tabindex="0" aria-label="Why">?<span class="tip">${esc(t)}</span></span>`:'';
const items=()=>(S.state.intake||[]);
const itemOf=id=>items().find(i=>i.id===id);
// the card as the person has edited it; a new proposal from the agent starts it over
const edOf=function(i){
 const P=i.proposal;if(!P)return null;
 const e=IN.ed[i.id];
 if(e&&e.t===P.t)return e.g;
 IN.ed[i.id]={t:P.t,g:JSON.parse(JSON.stringify(P.goal))};return IN.ed[i.id].g;
}
// a proposed goal read like a ledger goal, so dist() and the units helpers apply; `now` from the champion's latest run
const asGoal=function(pg){
 const L=S.state,sl=L.slices?.[pg.slice],n=sl?.n||pg.n||0,kpi=pg.kpi||'score';
 const g={kpi,n,slice:pg.slice,scale:sl?.scale,unit:sl?.unit,metric:sl?.metric,higher_is_better:!LOWER.includes(kpi)};
 g.target=kpi==='score'&&!cont(g)?(pg.count!=null&&n?pg.count/n:pg.target):Number(pg.target);
 const r=L.champion&&(L.leaderboard?.[pg.slice]||{})[L.champion],v=r?.[kpi==='score'?'score':kpi];
 g.value=typeof v==='number'&&isFinite(v)?v:null;g.model=L.champion;g.task=r?.task;
 return g;
}
const sameAs=function(pg){
 const g=asGoal(pg);
 return Object.values(S.state.goals||{}).find(x=>x.status==='open'&&x.slice===pg.slice&&(x.kpi||'score')===g.kpi&&(byN(g)?tcnt(x)===tcnt(g):Math.abs(x.target-g.target)<1e-9));
}
// the champion's best-so-far on the slice, as a small step line under the target
const ispark=function(pg){
 const g=asGoal(pg),k=kpiKey(g),s=sgn(g);
 const runs=S.state.tasks.filter(t=>t.kind==='eval'&&t.slice===pg.slice&&(t.status==='done'||t.status==='completed')&&typeof t.summary?.[k]==='number'&&t.ended).sort((a,b)=>a.ended-b.ended);
 if(runs.length<2||g.target==null||!isFinite(g.target))return '';
 const W=120,H=28,ys=runs.map(r=>r.summary[k]).concat([g.target]),lo=Math.min(...ys),hi=Math.max(...ys),sp=(hi-lo)||1;
 const X=t=>2+(t-runs[0].ended)/((runs.at(-1).ended-runs[0].ended)||1)*(W-4),Y=v=>H-3-(v-lo)/sp*(H-6);
 let best=null,d='';runs.forEach(r=>{const v=r.summary[k];if(best==null||s*(v-best)>0){d+=d?`H${X(r.ended).toFixed(1)}V${Y(v).toFixed(1)}`:`M${X(r.ended).toFixed(1)} ${Y(v).toFixed(1)}`;best=v}});d+=`H${W-2}`;
 return `<svg class="gi-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="best run on this slice over time"><line x1="0" x2="${W}" y1="${Y(g.target).toFixed(1)}" y2="${Y(g.target).toFixed(1)}" stroke="var(--chart-3)" stroke-dasharray="3 3"/><path d="${d}" fill="none" stroke="var(--chart-1)" stroke-width="1.6"/></svg>`;
}
const nowCell=function(pg){
 const g=asGoal(pg);
 if(pg.missing_slice)return pill('slice not in the ledger','warn');
 if(g.value==null)return `<span class="faint">${g.model?`${mn(g.model)} has no run here`:'no champion'}</span>`;
 return `<span class="gi-big num">${gu(g,g.value)}</span>${byN(g)?`<span class="num faint">of ${N(g.n)}</span>`:''}<span class="num">${distLine(g)}</span>${ispark(pg)}`;
}
const tgtCell=function(i,pg){
 const g=asGoal(pg),id=esc(i.id),val=byN(g)?(pg.count!=null?N(pg.count):''):pg.target!=null&&isFinite(pg.target)?String(dsg(g)*pg.target):'';
 const unit=byN(g)?`of ${N(g.n)} correct`:cont(g)?unitG(g):/^latency/.test(g.kpi)?'s':'$ per answer';
 return `<span class="gi-big num">${cmpSym(g)} <input id="gi-${id}-target" class="gi-in gi-num" inputmode="decimal" value="${esc(val)}" onchange="Intake.target('${id}',this.value)" onkeydown="if(event.key==='Enter')this.blur()"></span><span class="num faint">${unit}</span>`;
}
const card1=function(i){
 const pg=edOf(i),id=esc(i.id),same=sameAs(pg),W=pg.why||{},err=IN.err[i.id];
 const slices=Object.values(S.state.slices||{}).sort((a,b)=>(a.kind==='full'?0:1)-(b.kind==='full'?0:1)||a.name.localeCompare(b.name));
 const slOpts=(pg.missing_slice?[`<option selected>${esc(pg.slice)} · not in the ledger</option>`]:[]).concat(slices.map(s=>`<option value="${esc(s.name)}"${s.name===pg.slice?' selected':''}>${esc(s.name)} · ${N(s.n)}</option>`)).join('');
 const row=(k,v)=>`<div class="k">${k}</div><div class="v">${v}</div>`;
 return `<div class="gi-card">
  <div class="gi-head"><input id="gi-${id}-title" class="gi-in gi-title" value="${esc(pg.title)}" aria-label="Title" oninput="Intake.set('${id}','title',this.value)"><input id="gi-${id}-name" class="gi-in gi-name mono" value="${esc(pg.name)}" aria-label="Name" oninput="Intake.set('${id}','name',this.value)">${same?pill('already open','acc'):''}</div>
  <div class="gi-fields">
   ${row('KPI',`<select id="gi-${id}-kpi" class="gi-in" onchange="Intake.kpi('${id}',this.value)">${KPI_OPTS.map(([v,l])=>`<option value="${v}"${v===pg.kpi?' selected':''}>${l}</option>`).join('')}</select>`)}
   ${row('Judged on',`<select id="gi-${id}-slice" class="gi-in mono" onchange="Intake.slice('${id}',this.value)">${slOpts}</select>${why(W.slice)}`)}
   ${row('Target',tgtCell(i,pg)+why(W.target))}
   ${row('Now',nowCell(pg)+why(W.now))}
   ${pg.against?row('Against',`<span>${esc(pg.against)}</span>${why(W.against)}`):''}
   ${row('Constraints',`${(pg.constraints||[]).map((c,k)=>`<span class="gi-con">${esc(c)}<button type="button" aria-label="Remove" onclick="Intake.uncon('${id}',${k})">×</button></span>`).join('')}<input id="gi-${id}-con" class="gi-in gi-add" placeholder="+ add" size="8" onkeydown="Intake.con(event,'${id}',this)">${why(W.constraints)}`)}
  </div>
  <div class="gi-foot">${err?`<span class="neg gi-err">${esc(err)}</span>`:'<span></span>'}<button class="btn primary" type="button" ${IN.busy[i.id]||pg.missing_slice?'disabled':''} onclick="Intake.open('${id}')">${same?`Use ${esc(same.name)}`:'Open goal'}</button></div>
 </div>`;
}
const relCard=function(i,r,k){
 const g=asGoal(r),main=i.opened?.[0],added=(i.opened||[]).includes(r.name)||!!S.state.goals?.[r.name]&&S.state.goals[r.name].parent===main;
 const can=main&&!r.missing_slice&&!added&&!IN.busy[i.id];
 const fig=r.missing_slice?pill('slice not in the ledger','warn'):g.value==null?'<span class="faint">not measured</span>':distLine(g);
 return `<div class="gi-sug ${added?'added':''}"><div class="t"><span>${esc(r.title)}</span>${pill(ROLE[r.role]||r.role,r.role==='guard'?'ghost':'acc')}${why(r.why?.target||Object.values(r.why||{})[0])}</div>
  <div class="d mono">${kpiPre(g)}${cmpSym(g)} ${byN(g)?N(r.count??tcnt(g)):gv(g,g.target)}${byN(g)?` of ${N(g.n)}`:''} · ${esc(r.slice)}</div>
  <div class="row"><span class="d num">${fig}</span><button class="btn" type="button" ${can?'':'disabled'} onclick="Intake.add('${esc(i.id)}',${k})">${added?'✓ Added':'Add'}</button></div></div>`;
}
// no `arx answer` worker for this project: a queued ask waits for one, so say so instead of "Queued" forever.
// A missing answer_agent (an older server) is unknown, not "not running".
const noAgent=()=>S.state.answer_agent?.running===false;
const isWorking=i=>i.status==='running'||(i.status==='queued'&&!noAgent());
const statusLine=function(i,P){
 const t=i.task&&byId(i.task),round=i.round||0;
 if(i.status==='queued'&&noAgent())return `<div class="gi-st warn"><span class="gi-dot off"></span>No agent running · ${cmd('arx answer')}</div>`;
 if(i.status==='queued')return `<div class="gi-st"><span class="gi-dot"></span>Queued</div>`;
 if(i.status==='running')return `<div class="gi-st"><span class="gi-dot live"></span>${t?`<a class="ln" href="#task/${enc(t.id)}">Agent working</a>${t.note?`<span class="faint"> · ${esc(t.note.text??t.note.msg)}</span>`:''}`:'Agent working'}</div>`;
 if(i.status==='failed')return `<div class="gi-st neg">${esc(i.error||'The agent failed')}<button class="btn" type="button" onclick="Intake.retry('${esc(i.id)}')">Retry</button></div>`;
 if(!P||P.round!==round)return `<div class="gi-st">${i.status==='done'?'No proposal came back':'Waiting for the agent'}<button class="btn" type="button" onclick="Intake.retry('${esc(i.id)}')">Retry</button></div>`;
 return '';
}
const itemCard=function(i){
 // with no agent, the last proposal stays editable (and keeps its local edits) while the answers wait in the queue
 const P=i.proposal,id=esc(i.id),working=isWorking(i),cur=P&&!working&&(P.round===(i.round||0)||(i.status==='queued'&&noAgent()));
 const ans={...(i.answers||{}),...(IN.ans[i.id]||{})},main=i.opened?.[0],mg=main&&S.state.goals?.[main];
 let h=`<div class="gi-said"><span>${esc(i.ask)}</span></div>`;
 const asked=new Set((P?.questions||[]).map(q=>q.id)),said=(i.answered||[]).filter(a=>!asked.has(a.id));
 if(said.length)h+=`<div class="gi-said-a">${said.map(a=>`<span><span class="faint">${esc(a.text)}</span> ${esc(a.label)}</span>`).join('')}</div>`;
 h+=statusLine(i,P);
 if(P?.note&&(cur||working))h+=`<p class="gi-note">${esc(P.note)}</p>`;
 if(P?.questions?.length&&!main)h+=`<div class="gi-qs">${P.questions.map((q,k)=>`<div class="gi-q"><div class="gi-qt"><span class="faint">${k+1} of ${P.questions.length}</span> ${esc(q.text)}</div><div class="gi-opts">${q.options.map((o,j)=>`<button type="button" class="gi-opt ${ans[q.id]===o.value?'on':''}" ${working?'disabled':''} onclick="Intake.pick('${id}',${k},${j})">${esc(o.label)}${o.sub?`<small>${esc(o.sub)}</small>`:''}</button>`).join('')}</div></div>`).join('')}</div>`;
 if(cur&&!main)h+=card1(i);
 if(main)h+=`<div class="gi-done">${pill('opened','pos')}<a class="ln" href="#goal/${enc(main)}"><b>${esc(mg?.title||main)}</b></a>${mg?`<span class="num">${distLine(mg)}</span>`:''}</div>`;
 if(P&&!working&&P.related?.length&&(cur||main))h+=`<div class="gi-rel"><h3>Related goals</h3><div class="gi-sugs">${P.related.map((r,k)=>relCard(i,r,k)).join('')}</div></div>`;
 if(IN.err[i.id]&&main)h+=`<p class="neg gi-err">${esc(IN.err[i.id])}</p>`;
 return `<section class="card gi-item${working?' working':''}" id="gi-${id}"><button class="iconbtn gi-x" type="button" aria-label="Dismiss" title="Dismiss" onclick="Intake.dismiss('${id}')">×</button>${h}</section>`;
}
const intake=function(){
 const box=`<form class="gi-ask" onsubmit="event.preventDefault();Intake.submit()"><textarea id="gi-ask" rows="2" placeholder="New goal, in your own words" oninput="Intake.draft(this.value)" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();Intake.submit()}">${esc(IN.draft)}</textarea><button class="btn primary" type="submit" ${IN.busy.ask?'disabled':''}>Go</button></form>${IN.err.ask?`<p class="neg gi-err">${esc(IN.err.ask)}</p>`:''}`;
 return `<div class="gi">${panel('New goal',box,{cls:'gi-new'})}${items().map(itemCard).join('')}</div>`;
}
const act=async function(id,fn){
 IN.busy[id]=true;IN.err[id]='';render(true);
 try{await fn()}catch(e){IN.err[id]=e.message}
 IN.busy[id]=false;await tick();render(true);
}
window.Intake={
 draft:v=>{IN.draft=v},
 submit:()=>{const ask=IN.draft.trim();if(!ask)return;act('ask',async()=>{await ipost('new',{ask});IN.draft=''})},
 set:(id,f,v)=>{const i=itemOf(id);if(i)edOf(i)[f]=v},
 kpi:(id,v)=>{const i=itemOf(id),g=edOf(i),old=asGoal(g);g.kpi=v;
  // a new KPI starts from the champion now: a few more answers, or a tenth faster or cheaper
  const now=asGoal(g);
  if(v==='score'&&old.kpi!=='score'){const n=now.n;g.count=n?Math.min(n,(now.value!=null?cnt(now,now.value):Math.floor(.9*n))+Math.ceil(.03*n)):null}
  if(v!=='score'&&old.kpi==='score'||g.target==null)g.target=now.value!=null?+(now.value*.9).toFixed(v==='cost'?4:1):null
  render(true)},
 slice:(id,v)=>{const i=itemOf(id),g=edOf(i),a=asGoal(g),n=S.state.slices?.[v]?.n;
  g.slice=v;delete g.missing_slice;g.n=n;
  const b=asGoal(g);
  // the same share of the new slice, rounded once ("1,280 of 1,319" -> "97 of 100"); the title follows the count
  if(byN(a)&&byN(b)&&g.count!=null){const old=g.count;g.count=Math.max(1,Math.min(n,Math.round(old/a.n*n)));
   if(g.title&&old!==g.count)g.title=String(g.title).replace(N(old),N(g.count)).replace(new RegExp('\\b'+old+'\\b'),N(g.count))}
  else if(!byN(b))delete g.count;
  render(true)},
 target:(id,v)=>{const i=itemOf(id),g=edOf(i),x=parseFloat(String(v).replace(/[, ]/g,''));
  const a=asGoal(g);
  if(isFinite(x)){if(byN(a)){g.count=Math.max(1,Math.min(a.n||x,Math.round(x)))}else g.target=dsg(a)*x;
   if(g.why)g.why.target=byN(a)?`Set by hand: ${N(g.count)} of ${N(a.n)}.`:`Set by hand: ${x}${unitG(a)?' '+unitG(a):''}.`}
  render(true)},
 con:(e,id,el)=>{if(e.key!=='Enter')return;e.preventDefault();const v=el.value.trim();if(!v)return;const g=edOf(itemOf(id));(g.constraints=g.constraints||[]).push(v);el.value='';render(true);setTimeout(()=>document.getElementById(`gi-${id}-con`)?.focus())},
 uncon:(id,k)=>{const g=edOf(itemOf(id));g.constraints.splice(k,1);render(true)},
 pick:(id,k,j)=>{const i=itemOf(id),Q=i?.proposal?.questions?.[k],o=Q?.options?.[j];if(!o)return;IN.ans[id]={...(IN.ans[id]||{}),[Q.id]:o.value};
  const all={...(i.answers||{}),...IN.ans[id]},qs=i.proposal?.questions||[];
  if(qs.every(x=>all[x.id]!=null))act(id,async()=>{await ipost('answer',{id,answers:IN.ans[id]});delete IN.ans[id]});else render(true)},
 open:id=>{const i=itemOf(id),g=edOf(i),same=sameAs(g);
  act(id,()=>ipost('open',{id,goal:same?{use:same.name}:{...g,role:'main'}}))},
 add:(id,k)=>{const i=itemOf(id),r=i.proposal.related[k];act(id,()=>ipost('open',{id,goal:{...r,parent:i.opened[0]}}))},
 retry:id=>act(id,()=>ipost('retry',{id})),
 dismiss:id=>act(id,()=>ipost('dismiss',{id})),
};
// the Overview draws each open goal with these, so a goal reads the same on both pages
window.GoalUnits={bar,gu,gt,gv,ofP,dist,prog,cmpSym,kpiPre,byN,isMain,slRuns,kpiKey,sgn,disp:(g,v)=>byN(g)?v*g.n:dsg(g)*v};
// the chart is sized to the sheet in pixels so its labels stay legible; redraw once a resize settles
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{if(route().r==='goal'&&S.state)render(true)},150)});
}
