'use strict';
// Task detail: how is this job doing / how did it end, and what did it find?
// The finding line is the outcome in numbers; the Log is the notes, in order; Details holds ids, times and the command.
const isScoreKey=k=>/score|acc/.test(k);
{
const tone=vc=>vc.lo>0?'pos':vc.hi<0?'neg':'';
const sig=vc=>vc.lo>0?'better beyond noise':vc.hi<0?'worse beyond noise':'within noise';
const hillOf=t=>{const st=S.state,m=st.models[t.model];if(m?.hill&&st.hills[m.hill])return m.hill;
 return Object.entries(st.hills).find(([,h])=>t.slice&&(h.target===t.slice||h.control===t.slice))?.[0]||null};
const isUrl=v=>/^https?:\/\//.test(String(v));
// continuous slices (`scale: continuous`, optional `unit`) score a mean, not a share solved; a slice whose metric is
// seconds scores minus seconds and reads as time. CUR is the slice of the task on screen.
let CUR=null;
const slOf=t=>t.slice?S.state.slices[t.slice]||null:null;
const isCont=sl=>sl?.scale==='continuous';
const timedSl=sl=>/\bseconds?\b/i.test(sl?.metric||'');
const cNum=v=>{const a=Math.abs(v);return (v<0?'−':'')+(a>=10?a.toFixed(1):a>=1e-3?String(+a.toPrecision(3)):num(a,3))};
const cVal=(v,sl)=>v==null?DASH:timedSl(sl)?cNum(Math.abs(v))+'&nbsp;s':cNum(v)+(sl?.unit?'&nbsp;'+esc(sl.unit):'');
const cDelta=(d,sl)=>timedSl(sl)?`${cNum(Math.abs(d))}&nbsp;s ${d>0?'faster':'slower'}`:(d>0?'+':d<0?'−':'')+cNum(Math.abs(d))+(sl?.unit?'&nbsp;'+esc(sl.unit):'');
// a score, and a change in score against the champion, in the slice's own terms
const scoreOf=(v,sl)=>v==null?DASH:isCont(sl)?cVal(v,sl):pct(v);
const deltaOf=(d,sl)=>isCont(sl)?cDelta(d,sl):pts(d)+' pts';
const mval=(k,v)=>v==null?DASH:isScoreKey(k)?scoreOf(v,CUR):/_s$/.test(k)?secs(v):fmtv(v);
// the champion side of vs_champion: its score is pooled per example over every complete run it has on the slice
const pooled=vc=>vc.runs>1?`, champion pooled over ${vc.runs} runs`:'';
// a long local path shows its last three parts; the full path is in the tooltip and on the copy button
const tail=p=>{const a=String(p).split('/');return a.length>4?'…/'+a.slice(-3).join('/'):String(p)};

// ---------- the finding: what happened, in numbers. Never the last note (that lives in the Log).
function finding(t,d){
 const pr=t.progress||{},sm=t.summary||{},vc=d?.vs_champion,sl=t.slice?esc(short(t.slice)):'';
 const prog=pr.total?`${pr.done.toLocaleString()} of ${pr.total.toLocaleString()}${t.kind==='eval'?' examples':''}`:'';
 const budget=t.budget_s?` of a ${wbSpan(t.budget_s)} budget`:'';
 const sub=tree(t.id).map(([k])=>k),subTxt=sub.length?(()=>{const bad=sub.filter(k=>!ARC_OK.has(k.status)&&!isLive(k)).length,live=sub.filter(isLive).length;
  return `; ${plural(sub.length,'sub-task')}${live?`, ${live} still running`:bad?`, ${bad} did not finish cleanly`:', all done'}`})():'';
 if(t.status==='stalled')return `<b class="neg">Stalled: silent for ${silent(t)}</b>${prog?`, stopped at ${prog} (${(100*pr.done/pr.total).toFixed(0)}%)`:''}.`;
 if(t.status==='running'){
  const run=t.last?.running_score;
  const bits=[prog&&`<b>${prog}</b> done (${(100*pr.done/pr.total).toFixed(0)}%)`,run!=null&&`scoring ${scoreOf(run,slOf(t))} so far${sl?' on '+sl:''}`,t.eta&&(t.health?.state==='over'?`<b class="warn">will not finish in its budget</b>: the estimate is ${wbClock(t.eta.finish_at)}, the budget ends at ${wbClock(t.created+t.budget_s)}`:`finishes in about ${wbSpan(t.eta.eta_s)}, at ${wbClock(t.eta.finish_at)}`)].filter(Boolean);
  return (bits.length?bits.join(', ')+'. ':'')+`Running for ${wbSpan(now()-t.created)}${budget}${subTxt}.`;
 }
 const took=t.ended?wbSpan(t.ended-t.created):null;
 if(t.kind==='eval'&&sm.score!=null){
  const S_=slOf(t),c=isCont(S_);
  const verb=c&&timedSl(S_)?'took':'scored',av=c&&timedSl(S_)?' a question':'';
  let s=`${partialEval(t)?`<b class="warn">Partial run</b>: ${verb}`:verb[0].toUpperCase()+verb.slice(1)} <b>${scoreOf(sm.score,S_)}</b>${sm.n?(c?`${av} on average over ${sm.n.toLocaleString()}`:` (${Math.round(sm.score*sm.n).toLocaleString()} of ${sm.n.toLocaleString()})`):''}${sl?` on ${sl}`:''}${took?` in ${took}`:''}`;
  if(vc&&vc.delta!=null)s+=`; <b class="${tone(vc)}">${deltaOf(vc.delta,S_)}</b> against the champion ${mn(vc.model)} on the same ${vc.n} examples${pooled(vc)}, ${sig(vc)}`;
  return s+'.';
 }
 const lead={done:'Done',completed:'Done',failed:'<b class="neg">Failed</b>',budget:'<b class="neg">Stopped by its time budget</b>'}[t.status]||esc(wbKind(t.status));
 const inside=t.budget_s&&t.ended?(t.ended-t.created<=t.budget_s?`, inside its ${wbSpan(t.budget_s)} budget`:`, over its ${wbSpan(t.budget_s)} budget`):'';
 const nums=Object.entries(t.last||{}).filter(([,v])=>typeof v==='number').slice(0,2).map(([k,v])=>`${wbMetric(k).toLowerCase()} ${isScoreKey(k)?pct(v):fmtv(v)}`);
 const sc=sm.score!=null?`scored ${scoreOf(sm.score,slOf(t))}${sm.n?` on ${sm.n.toLocaleString()}`:''}`:'';
 const extra=[sc,...(sc?[]:nums.map(x=>'final '+x))].filter(Boolean);
 return `${lead}${took?(t.status==='failed'?' after ':' in ')+took:''}${t.status==='budget'?'':inside}${extra.length?'; '+extra.join(', '):''}${subTxt}.`;
}

// ---------- KPIs only when there are figures to show; a task with only a duration gets no strip
function kpiStrip(t,d){
 const pr=t.progress||{},sm=t.summary||{},vc=d?.vs_champion,live=isLive(t),[bt,bc]=budgetLine(t);
 const items=[];
 if(t.kind==='eval'&&(sm.n||pr.total)){
  const sc=sm.score??t.last?.running_score,n=sm.n??pr.done,sl=slOf(t),c=isCont(sl);
  const mt=c&&timedSl(sl);
  items.push([live?(mt?'Mean time so far':c?'Mean so far':'Score so far'):(mt?'Mean time':c?'Mean score':'Score'),scoreOf(sc,sl),sc!=null?(c?`over ${n.toLocaleString()}`:`${Math.round(sc*n).toLocaleString()} of ${n.toLocaleString()}`):'']);
  if(vc&&vc.delta!=null)items.push(['Against the champion',c?`<span class="${tone(vc)}">${cDelta(vc.delta,sl)}</span>`:`<span class="${tone(vc)}">${pts(vc.delta)}</span><small>pts</small>`,c?`90% interval ${cNum(vc.lo)} to ${cNum(vc.hi)}`:`90% interval ${pts(vc.lo)} to ${pts(vc.hi)}`]);
  if(live)items.push(['Progress',pr.total?`${pr.done.toLocaleString()}<small>of ${pr.total.toLocaleString()}</small>`:DASH,pr.total?(100*pr.done/pr.total).toFixed(0)+'%':'']);
  if(sm.cost!=null)items.push(['Cost per example',money(sm.cost),sm.cost_total!=null?money(sm.cost_total)+' in all':'']);
  const lat=sm.latency_p50??t.last?.latency_s;
  if(lat!=null)items.push(['Latency, median',secs(lat),sm.latency_p95!=null?'95th percentile '+secs(sm.latency_p95):live?'latest example':'']);
  if(!live)items.push(['Errors',`<span class="${sm.errors?'neg':''}">${sm.errors??DASH}</span>`,sm.missing?`${sm.missing} examples missing`:'none missing']);
 }else{
  if(pr.total)items.push(['Progress',`${pr.done.toLocaleString()}<small>of ${pr.total.toLocaleString()}</small>`,(100*pr.done/pr.total).toFixed(0)+'%']);
  const last=Object.entries(t.last||{}).filter(([,v])=>typeof v==='number').slice(0,2);
  for(const [k,v] of last)items.push([wbMetric(k),mval(k,v),live?'latest':'final']);
  if(!items.length)return '';
 }
 if(t.status==='running')items.push(['Finishes',t.eta?`<span class="${t.health?.state==='over'?'warn':''}">in ${wbSpan(t.eta.eta_s)}</span>`:DASH,t.eta?`at ${wbClock(t.eta.finish_at)}, ${t.eta.per_min<10?t.eta.per_min.toFixed(1):Math.round(t.eta.per_min)} a minute`:'no rate yet']);
 items.push([live?'Elapsed':'Took',`<span class="${bc}">${wbSpan((t.ended||now())-t.created)}</span>`,t.budget_s?`of a ${wbSpan(t.budget_s)} budget`:'no budget set']);
 return `<div class="section">${kpis(items.slice(0,6))}</div>`;
}

function vsChamp(vc,t){
 if(!vc||vc.delta==null)return '';
 const state=vc.lo>0?'pass':vc.hi<0?'fail':'',sl=slOf(t),c=isCont(sl),f=c?cNum:pts;
 // ciBar titles its interval in points; a continuous slice gets its own units
 const bar=ciBar({...vc,state}).replace(/title="[^"]*"/,`title="${c?`Change ${cDelta(vc.delta,sl).replace(/&nbsp;/g,' ')}, 90% interval ${cNum(vc.lo)} to ${cNum(vc.hi)}`:`Change ${pts(vc.delta)} pts, 90% interval ${pts(vc.lo)} to ${pts(vc.hi)}`}"`);
 const base=vc.runs>1?`Champion's score, ${vc.runs} runs pooled`:`Champion's score`;
 return `<div class="section">${panel(`Against the champion, ${mn(vc.model)}`,`<div class="tk-vc">
  <div class="tk-vcd"><span class="tk-big ${tone(vc)}">${c?cDelta(vc.delta,sl):pts(vc.delta)}</span><span class="sub">${c?'':'pts, '}${sig(vc)}</span></div>
  <div class="tk-vcb">${bar}<div class="tk-ax"><span>${f(vc.lo)}</span><span class="sub">90% interval</span><span>${f(vc.hi)}</span></div></div>
  <dl class="tk-kv"><div><dt>Wins / losses</dt><dd>${vc.wins} / ${vc.losses}</dd></div><div><dt>${base}</dt><dd><a class="ln" href="#task/${enc(vc.task)}" title="${vc.runs>1?'Its latest run':'Its run'}">${scoreOf(vc.base,sl)}</a></dd></div></dl></div>`,
  {cls:'tk-vcp',meta:`paired on the same ${vc.n} examples${pooled(vc)}`,right:`<a class="more" href="#task/${enc(vc.task)}">${vc.runs>1?"Champion's latest run":"Champion's run"}</a>`})}</div>`;
}

// ---------- curves: a main chart you pick, small multiples for the rest, all on one crosshair and zoom; other runs of
// the same kind (evals: the same slice) overlay from a legend you toggle; GPU readings (`sys` rows) in their own row
const PRIO=['reward','running_score','score','accuracy','mean_token_accuracy','loss','kl','entropy','grad_norm','learning_rate'];
const MINOR=/(^|\/|_)(min|max|std)(_|\/|$)|clip_ratio|^epoch$|^total_flos$|^train_|_per_second$|^num_tokens$|terminated/;
const SYS=new Set(['gpu_util','gpu_mem_gb','gpu_mem_total_gb','gpus']);
S.tkMetric=S.tkMetric||{};S.xcRuns=S.xcRuns||{};
const yfOf=k=>isScoreKey(k)&&!isCont(CUR)?'pct':/latency|_s$/.test(k)?'s':'num';
function keysOf(rows){
 const n={},first={};
 rows.forEach((m,i)=>{for(const [k,v] of Object.entries(m))if(k!=='t'&&k!=='step'&&k!=='sys'&&typeof v==='number'&&isFinite(v)){n[k]=(n[k]||0)+1;if(!(k in first))first[k]=i}});
 const ks=Object.keys(n).filter(k=>n[k]>=2&&!SYS.has(k));
 const flat=ks.filter(k=>{const y=rows.map(m=>m[k]).filter(v=>typeof v==='number');return Math.max(...y)-Math.min(...y)<=1e-12*Math.max(1,Math.abs(y[0]))});
 const live=ks.filter(k=>!flat.includes(k)).sort((a,b)=>{const pa=PRIO.indexOf(a),pb=PRIO.indexOf(b);return (pa<0?99:pa)-(pb<0?99:pb)||first[a]-first[b]});
 return {main:live.filter(k=>!MINOR.test(k)),minor:live.filter(k=>MINOR.test(k)),flat};
}
// other runs to overlay: the newest five of the same kind (evals: the newest run of each model on the same slice)
function peers(t){
 let ps=S.state.tasks.filter(x=>x.id!==t.id&&x.kind===t.kind&&(t.kind!=='eval'||x.slice===t.slice)&&!x.superseded_by).sort((a,b)=>b.created-a.created);
 if(t.kind==='eval'){const seen=new Set([t.model]);ps=ps.filter(x=>x.model&&!seen.has(x.model)&&seen.add(x.model));const c=S.state.champion;ps.sort((a,b)=>(b.model===c)-(a.model===c))}
 return ps.slice(0,5);
}
function wantRuns(ids){
 const need=ids.filter(i=>{const c=S.xcRuns[i];return !c||(isLive(byId(i))&&Date.now()-c.at>8000)});
 if(!need.length||S.xcBusy)return;S.xcBusy=true;
 fetch('api/vitals/series?ids='+need.map(enc).join(','),{cache:'no-store'}).then(r=>r.json()).then(d=>{for(const i of need)S.xcRuns[i]={at:Date.now(),d:d[i]||null}}).catch(()=>{}).finally(()=>{S.xcBusy=false;render()});
}
function curves(t,d){
 const rows=d.metrics.filter(m=>!m.sys),sys=d.metrics.filter(m=>m.sys&&typeof m.gpu_util==='number');
 const {main,minor,flat}=keysOf(rows);
 if(!main.length&&!minor.length&&!sys.length)return '';
 const grp='tk-'+t.id,ev=t.kind==='eval',T=isCont(CUR)&&timedSl(CUR);
 const ps=peers(t);wantRuns(ps.map(x=>x.id));
 const g=XC.g(grp,{w:ev?0:.6,hidden:ps.map(x=>x.id)});
 const runs=[{id:t.id,name:t.model?S.state.models[t.model]?.title||t.model:'This run',rows,t0:t.created,color:XC.PAL[0]},
  ...ps.map((x,i)=>({id:x.id,name:x.model?S.state.models[x.model]?.title||x.model:x.title,title:x.title,t0:x.created,rows:(S.xcRuns[x.id]?.d?.metrics)||[],color:XC.PAL[(i+1)%XC.PAL.length]}))];
 const all=[...main,...minor];
 let cur=S.tkMetric[t.id];if(!all.includes(cur))cur=all[0];
 const flip=k=>T&&isScoreKey(k);
 const ser=k=>runs.map(r=>({id:r.id,name:r.name,color:r.color,smooth:!ev&&!/running_score/.test(k),pts:r.rows.filter(m=>typeof m[k]==='number').map(m=>[m.step,flip(k)?-m[k]:m[k],m.t])}));
 const total=t.progress?.total,dom=isLive(t)&&total&&g.x==='step'?[0,total]:null;
 const base=d.vs_champion?.base??null;
 const spec=(k,mode,h)=>({group:grp,mode,h,xLabel:ev?'examples':'step',yLabel:mode==='full'?nm(k):null,yfmt:flip(k)?'s':yfOf(k),t0:t.created,domain:dom,series:ser(k),
  ref:k==='running_score'&&base!=null?{y:flip(k)?-base:base,label:'champion'}:null});
 const nm=k=>flip(k)?(k==='running_score'?'Mean time so far':'Mean time'):wbMetric(k);
 const lastOf=k=>{const y=rows.map(m=>m[k]).filter(v=>typeof v==='number');return y.length?mval(k,flip(k)?-y.at(-1):y.at(-1)):DASH};
 const sm=k=>`<div class="tk-sm"><div class="tk-smh"><button type="button" class="tk-pick" data-k="${esc(k)}" onclick="S.tkMetric[${esc(JSON.stringify(t.id))}]=this.dataset.k;render();scrollTo({top:document.querySelector('.tk-curves')?.offsetTop-60||0,behavior:'smooth'})" title="Make this the main chart">${esc(nm(k))}</button><b>${lastOf(k)}</b></div>${XC.box(`tk-${t.id}-${k}`,spec(k,'compact',120))}</div>`;
 const legend=ps.length?XC.legend(grp,runs.map((r,i)=>{const y=r.rows.map(m=>m[cur]).filter(v=>typeof v==='number');
  return {id:r.id,name:r.name,title:r.title||r.name,color:r.color,fixed:i===0,value:y.length?XC.yv(flip(cur)?'s':yfOf(cur),flip(cur)?-y.at(-1):y.at(-1)):null,cls:y.length?'':'na'}})):'';
 const opts=all.length>1?`<select class="tk-msel" aria-label="Metric" onchange="S.tkMetric[${esc(JSON.stringify(t.id))}]=this.value;render()">${all.map(k=>`<option value="${esc(k)}" ${k===cur?'selected':''}>${esc(nm(k))}</option>`).join('')}</select>`:'';
 let h=`<div class="section tk-curves">${panel(esc(nm(cur)),`<div class="tk-ctl">${opts}${XC.bar(grp,{smooth:!ev,log:true,x:true})}</div>${legend}${XC.box(`tk-${t.id}-main`,spec(cur,'full',innerWidth<600?240:320))}`,
  {right:`<span class="sub">${isLive(t)?'latest':'last'}</span> <b class="tk-lv">${lastOf(cur)}</b>`})}`;
 const rest=main.filter(k=>k!==cur),more=minor.filter(k=>k!==cur);
 if(rest.length)h+=`<div class="tk-multi">${rest.map(sm).join('')}</div>`;
 if(more.length)h+=`<details class="tk-moredet"><summary>${plural(more.length,'more metric')}</summary><div class="tk-multi">${more.map(sm).join('')}</div></details>`;
 if(flat.length)h+=`<p class="tk-flat"><span>Flat</span>${flat.map(k=>`<span>${esc(nm(k))} <b>${lastOf(k)}</b></span>`).join('')}</p>`;
 if(sys.length){const tot=sys.at(-1).gpu_mem_total_gb;
  const sp=(k,f,ref)=>({group:grp,mode:'compact',h:120,xLabel:ev?'examples':'step',yfmt:f,t0:t.created,domain:dom,ymin:0,ymax:k==='gpu_util'?100:null,logOk:false,ref,
   series:[{id:t.id,name:k==='gpu_util'?'GPU utilisation':'GPU memory',color:'var(--chart-2)',smooth:false,pts:sys.filter(m=>typeof m[k]==='number').map(m=>[m.step,m[k],m.t])}]});
  h+=`<div class="tk-multi tk-sys">
   <div class="tk-sm"><div class="tk-smh"><span>GPU utilisation</span><b>${Math.round(sys.at(-1).gpu_util)}%</b></div>${XC.box(`tk-${t.id}-gpu`,sp('gpu_util','pct100'))}</div>
   ${typeof sys.at(-1).gpu_mem_gb==='number'?`<div class="tk-sm"><div class="tk-smh"><span>GPU memory</span><b>${sys.at(-1).gpu_mem_gb.toFixed(1)}${tot?` of ${tot.toFixed(0)}`:''} GB</b></div>${XC.box(`tk-${t.id}-gmem`,sp('gpu_mem_gb','num',tot?{y:tot,label:'total'}:null))}</div>`:''}</div>`}
 return h+`</div>`;
}
// the finish estimate over the run: each point is where the rate over the last 5 minutes put the finish
function etaCard(t){
 const e=t.eta;if(!e?.hist?.length||t.status!=='running')return '';
 const h0=e.hist[0][1];
 return `<div class="section">${panel('Finish estimate',XC.box(`tk-${t.id}-eta`,{group:'tk-eta-'+t.id,mode:'compact',h:120,xfmt:'clock',yfmt:'dmin',smooth:false,logOk:false,zero:true,
  series:[{name:'Moved by',pts:e.hist.map(([x,f])=>[x,(f-h0)/60])}]}),{right:`<b class="tk-lv">${wbClock(e.finish_at)}</b> <span class="sub">${e.drift_s>=0?'+':'−'}${wbSpan(Math.abs(e.drift_s))} in 5 min</span>`})}</div>`;
}

function examples(rows){
 if(!rows?.length)return '';
 const r=rows.slice().sort((a,b)=>String(a.id).localeCompare(String(b.id),undefined,{numeric:true}));
 const err=r.filter(x=>x.error).length,c=isCont(CUR);
 // pass/fail fills by score; a continuous slice fills by where the score sits between its lowest and highest
 let fill=x=>Math.max(0,Math.min(1,x.score||0)),legend;
 if(c){const v=r.filter(x=>!x.error&&typeof x.score==='number').map(x=>x.score),lo=Math.min(...v),hi=Math.max(...v),T=timedSl(CUR);
  fill=x=>hi>lo?(x.score-lo)/(hi-lo):1;
  legend=`<span><i class="k0"></i>${T?'slowest':'lowest'}${v.length?' '+cVal(lo,CUR):''}</span><span><i class="k1"></i>${T?'fastest':'highest'}${v.length?' '+cVal(hi,CUR):''}</span><span><i class="ke"></i>${err} errors</span>`}
 else{const ok=r.filter(x=>!x.error&&x.score>=1).length;legend=`<span><i class="k1"></i>${ok} right</span><span><i class="k0"></i>${r.length-ok-err} wrong</span><span><i class="ke"></i>${err} errors</span>`}
 return `<div class="section">${panel('Examples',`<div class="tk-strip">${r.map(x=>`<span class="${x.error?'e':''}" style="${x.error?'':`--s:${Math.round(100*fill(x))}%`}" title="${esc(x.id)} · ${x.error?'error':c?cVal(x.score,CUR).replace('&nbsp;',' '):fmtv(x.score)}"></span>`).join('')}</div>
 <div class="tk-legend">${legend}</div>`,{meta:`${r.length} examples, in id order`})}</div>`;
}

function subTasks(t){
 const sub=tree(t.id);
 if(!sub.length)return '';
 const live=sub.filter(([k])=>isLive(k)).length;
 return `<div class="section">${panel('Sub-tasks',sub.map(kidRow).join(''),{meta:`${sub.length}${live?` · ${live===sub.length?'all':live} running`:''}`})}</div>`;
}

// ---------- the log: the notes, oldest first, grouped by day; the latest dozen unless asked for all
function log(t,d){
 const ev=d.events,cap=S.tkLogAll?ev.length:12,shown=ev.slice(-cap),hidden=ev.length-shown.length;
 if(!ev.length)return t.kind==='eval'?'':`<div class="section">${panel('Log',`<p class="tk-none">No notes were written for this task.</p>`)}</div>`;
 let day='',items='';
 for(const e of shown){
  const dd=wbDay(e.t);if(dd!==day){day=dd;items+=`<li class="tk-day">${dd}</li>`}
  const lv=e.level==='error'?'<span class="pill neg">Error</span>':e.level==='warn'||e.level==='warning'?'<span class="pill warn">Warning</span>':'';
  items+=`<li class="tk-e ${esc(e.level)}"><time datetime="${new Date(e.t*1000).toISOString()}" title="${esc(wbWhen(e.t))}, ${esc(wbAgo(e.t))}">${wbClock(e.t)}</time><p>${lv}${esc(e.text??e.msg)}</p></li>`;
 }
 return `<div class="section">${panel('Log',`${hidden?`<button class="btn tk-all" onclick="S.tkLogAll=true;render()">Show ${plural(hidden,'earlier note')}</button>`:''}<ol class="tk-log">${items}</ol>`,{meta:plural(ev.length,'note')})}</div>`;
}

// ---------- the command line as it was run: arx for the entry point, one flag per line, values quoted
const q=v=>/^[\w.,\/:@%+=-]+$/.test(v)?v:`'${v.replace(/'/g,`'\\''`)}'`;
function parseCmd(c){
 let s=String(c).trim();
 // the recorded argv[0] is a path to the arx entry point (…/__main__.py, …/bin/arx, -c); name it arx
 const m=s.match(/^(.*?(?:__main__\.py|\/arx)|arx|-c)\s+(task|eval|run|init|serve|up|gate|hill|model|slice|dataset|reject|promote|status|sync)\b/);
 if(m)s='arx '+s.slice(m[0].length-m[2].length);
 const parts=s.split(/\s(?=--[a-z][\w-]*)/);
 const head=parts.shift(),flags=parts.map(p=>{const i=p.indexOf(' ');return i<0?[p,null]:[p.slice(0,i),p.slice(i+1).trim()]});
 return {head,flags};
}
const cmdText=({head,flags})=>[head,...flags.map(([f,v])=>'  '+f+(v!=null?' '+q(v):''))].join(' \\\n');
const cmdHtml=({head,flags})=>[`<span class="tk-ch">${esc(head)}</span>`,...flags.map(([f,v])=>`  <span class="tk-cf">${esc(f)}</span>${v!=null?' '+esc(q(v)):''}`)].join(' <span class="tk-cf">\\</span>\n');

// config: flattened to key → value rows; hashes and paths in mono, the rest in the text face
function flat(o,p='',out=[]){for(const [k,v] of Object.entries(o||{})){const key=p?p+'.'+k:k;if(v&&typeof v==='object'&&!Array.isArray(v))flat(v,key,out);else out.push([key,v])}return out}
const fmtVal=v=>{if(v==null)return DASH;if(Array.isArray(v))v=v.join(', ');const s=String(v);
 return /^[0-9a-f]{12,}$/i.test(s)||/^[\w.~-]*\/[\w./-]+$/.test(s)?`<span class="tk-mono">${esc(s)}</span>`:esc(typeof v==='number'?v.toLocaleString(undefined,{maximumFractionDigits:6}):s)};

// rows of a label/value list; in two columns the first and last row of each column lose their outer rule and padding
const dlRows=(kv,cols)=>{const r=Math.ceil(kv.length/2);return kv.map(([k,v],i)=>`<div class="${cols&&(i===r)?'top':''} ${cols&&(i===r-1)?'end':''}"><dt>${k}</dt><dd>${v}</dd></div>`).join('')};
function details(t,d){
 const st=S.state,par=byId(t.parent),hill=hillOf(t),sl=t.slice&&st.slices[t.slice];
 const kv=[['Task id',`<span class="tk-mono">${esc(t.id)}</span>${copyBtn(t.id)}`],
  ['Started',wbWhen(t.created)],
  [t.ended?'Ended':'Last heard',t.ended?wbWhen(t.ended):`${wbAgo(t.heartbeat)} <span class="faint">(${wbClock(t.heartbeat)})</span>`],
  [t.ended?'Took':'Elapsed',`${wbSpan((t.ended||now())-t.created)}${t.budget_s?` <span class="faint">of a ${wbSpan(t.budget_s)} budget</span>`:''}`]];
 if(t.model)kv.push(['Model',`<a class="ln" href="#model/${enc(t.model)}">${mn(t.model)}</a>${st.models[t.model]?.title&&st.models[t.model].title!==t.model?` <span class="tk-mono faint">${esc(t.model)}</span>`:''}`]);
 if(t.superseded_by){const by=byId(t.superseded_by);kv.push(['Superseded by',`<a class="ln" href="#task/${enc(t.superseded_by)}">${esc(by?.title||t.superseded_by)}</a> <span class="faint">gates and baselines skip this run</span>`])}
 if(t.slice)kv.push(['Slice',`<a class="ln" href="#slices/${enc(t.slice)}">${esc(t.slice)}</a>${sl?.n?` <span class="faint">${sl.n.toLocaleString()} examples</span>`:''}`]);
 if(t.slice_hash)kv.push(['Slice hash',`<span class="tk-mono">${esc(t.slice_hash)}</span>${copyBtn(t.slice_hash)}${sl?.hash&&sl.hash!==t.slice_hash?` <span class="warn">the slice has changed since (now ${esc(sl.hash)})</span>`:''}`]);
 if(hill)kv.push(['Hill',`<a class="ln" href="#hill/${enc(hill)}">${esc(st.hills[hill].title||hill)}</a>`]);
 if(par)kv.push(['Part of',`<a class="ln" href="#task/${enc(par.id)}">${esc(par.title)}</a>`]);
 if(t.agent)kv.push(['Agent',esc(t.agent)]);
 if(t.host)kv.push(['Machine',`${esc(t.host)}${t.pid?` <span class="faint">process ${esc(t.pid)}</span>`:''}`]);
 for(const [k,v] of Object.entries(t.links||{}))kv.push([esc(k),isUrl(v)?`<a class="ln" href="${esc(v)}" target="_blank" rel="noopener">${esc(v.replace(/^https?:\/\//,''))} ${ICON.ext}</a>`:`<span class="tk-mono" title="${esc(v)}">${esc(tail(v))}</span>${copyBtn(v)}`]);
 const gate=t.model&&st.gates[t.model]&&!st.gates[t.model].error&&st.models[t.model]?.status==='candidate';
 if(gate)kv.push(['Next run',`<span class="tk-cmdline">${cmd('arx gate '+t.model)}</span>`]);
 const pc=t.command?parseCmd(t.command):null;
 const cfg=flat(t.config),capC=S.tkCfgAll?cfg.length:12;
 if(pc&&pc.flags.length<2)kv.push(['Command',`<span class="tk-mono">${esc(cmdText(pc))}</span>${copyBtn(cmdText(pc))}`]);
 const cmdBlock=pc&&pc.flags.length>=2?`<div class="tk-sub"><div class="tk-sh"><h3>Command line</h3>${copyBtn(cmdText(pc))}</div><pre class="tk-cmd">${cmdHtml(pc)}</pre></div>`:'';
 const cfgCard=cfg.length?`<div class="section">${panel('Config',`<dl class="tk-dl tk-cfg cols" style="--rows:${Math.ceil(Math.min(capC,cfg.length)/2)}">${dlRows(cfg.slice(0,capC).map(([k,v])=>[esc(k),fmtVal(v)]),true)}</dl>${cfg.length>capC?`<button class="btn tk-more" onclick="S.tkCfgAll=true;render()">Show all ${cfg.length}</button>`:''}`,{meta:plural(cfg.length,'value')})}</div>`:'';
 return `<div class="section">${panel('Details',`<div class="tk-det ${cmdBlock?'two':''}"><dl class="tk-dl ${cmdBlock?'':'cols'}" style="--rows:${Math.ceil(kv.length/2)}">${dlRows(kv,!cmdBlock)}</dl>${cmdBlock?`<div class="tk-right">${cmdBlock}</div>`:''}</div>`)}</div>`+cfgCard;
}

// previous / next among the parent's sub-tasks, in start order
function siblings(t){
 if(!t.parent)return '';
 const sib=S.state.tasks.filter(x=>x.parent===t.parent).sort((a,b)=>a.created-b.created),i=sib.findIndex(x=>x.id===t.id);
 if(sib.length<2||i<0)return '';
 const a=(x,inner)=>x?`<a class="btn tk-nav" href="#task/${enc(x.id)}" title="${esc(x.title)}">${inner}</a>`:`<span class="btn tk-nav" aria-disabled="true">${inner}</span>`;
 const L='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>',R='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
 return `<span class="sub tk-pos">${i+1} of ${sib.length}</span>${a(sib[i-1],L+'Previous')}${a(sib[i+1],'Next'+R)}`;
}

VIEWS.task=(id)=>{
 if(S.tkLogFor!==id){S.tkLogFor=id;S.tkLogAll=false;S.tkCfgAll=false}
 const sx=S.state,d=S.detail&&S.detail.task?.id===id?S.detail:null;
 const t0=byId(id),t=d?{...t0,...d.task,...(t0?.eta!==undefined?{eta:t0.eta,health:t0.health}:{})}:t0;
 CUR=t?slOf(t):null;
 if(!t)return page({title:'Task not found',crumbs:[['Archive','#archive'],['Not found']],finding:`No task <span class="id">${esc(id)}</span> in this ledger.`})+panel('',empty('Nothing to show','<a class="ln" href="#archive">Back to the archive</a>'));
 const live=isLive(t),par=byId(t.parent),hill=hillOf(t);
 const crumbs=[[live?'Workbench':'Archive',live?'#workbench':'#archive'],...(par?[[par.title,'#task/'+enc(par.id)]]:[]),[t.title]];
 const [sl,sc]=wbState(t);
 const meta=[esc(wbKind(t.kind)),t.agent&&`by ${esc(t.agent)}`,
  t.model&&`<a class="ln" href="#model/${enc(t.model)}" title="${esc(t.model)}">${mn(t.model)}</a>`,
  t.slice&&`<a class="ln" href="#slices/${enc(t.slice)}" title="${esc(t.slice)}">${esc(short(t.slice))}</a>`,
  hill&&`hill <a class="ln" href="#hill/${enc(hill)}">${esc(sx.hills[hill].title||hill)}</a>`,
  par&&`part of <a class="ln" href="#task/${enc(par.id)}">${esc(par.title)}</a>`,
  ...Object.entries(t.links||{}).filter(([,v])=>isUrl(v)).map(([k,v])=>`<a class="ln" href="${esc(v)}" target="_blank" rel="noopener">${esc(k)} ${ICON.ext}</a>`)].filter(Boolean);
 let h=page({title:t.title,crumbs,finding:finding(t,d),acts:siblings(t)});
 h+=`<div class="tk-meta">${t.status==='running'?st('running','Running'):pill(sl,sc)}${t.superseded_by?pill('Superseded','ghost'):''}<span class="tk-mi">${meta.map(m=>`<span>${m}</span>`).join('')}</span></div>`;
 if(t.description)h+=`<p class="tk-desc">${esc(t.description)}</p>`;
 if(t.status==='stalled')h+=`<div class="tk-fix"><span>No heartbeat for ${silent(t)}. If its process is gone, end it:</span>${cmd(wbFixCmd(t))}</div>`;
 h+=kpiStrip(t,d);
 const pr=t.progress||{};
 if(live&&pr.total)h+=`<div class="tk-prog">${meter(pr.done/pr.total,{cls:t.status==='stalled'?'muted':''})}</div>`;
 if(!d)return h+`<div class="section">${panel('Log','<div class="skel" style="height:96px"></div>')}</div>`+`<div class="section">${panel('Details','<div class="skel" style="height:160px"></div>')}</div>`;
 h+=vsChamp(d.vs_champion,t)+etaCard(t)+curves(t,d)+examples(d.rows)+log(t,d)+subTasks(t)+details(t,d);
 return h;
};
}
