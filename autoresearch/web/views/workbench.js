'use strict';
// Workbench: what is running right now, is any of it stuck, and when will it finish?
// Atomic jobs only: a running task with running sub-tasks is context ("in …"), never a card. A long job gets 2-4 live
// panels picked server-side (vitals.py) by its kind and the metrics it logs; a short one is a row. Stalled jobs first.
// Also defines the task helpers archive.js and task.js use (loaded after this file); they are prefixed wb*.

// ---------- words for times: one date format ("26 Oct, 04:53"), durations spelled out ("2 min", "1 h 39 min")
const wbClock=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
const wbDay=t=>{const d=new Date(t*1000),y=new Date(now()*1000).getFullYear();return d.toLocaleDateString('en-GB',{day:'numeric',month:'short',...(d.getFullYear()!==y?{year:'numeric'}:{})})};
const wbWhen=t=>t?`${wbDay(t)}, ${wbClock(t)}`:'—';
const wbSpan=s=>span(s);
const wbAgo=t=>ago(t);
const wbKind=k=>{const s=String(k||'task').replace(/[_-]+/g,' ');return s[0].toUpperCase()+s.slice(1)};
const endLabel=t=>t.status==='completed'?'done':t.status;
// an eval that finished with no scored rows: it measured nothing, whatever its status says
const emptyEval=t=>t.kind==='eval'&&!isLive(t)&&t.ended&&t.summary&&!t.summary.n&&(t.summary.missing>0||t.summary.score==null)&&t.status!=='failed';
// how long a finished job ran: an eval recorded from another pass (its rows copied in a moment) has no run time of its
// own, so it reads its harness's wall time when it has one, else null ("recorded")
const wbTook=t=>!t.ended?null:t.ended-t.created>=2||t.kind!=='eval'?t.ended-t.created:(t.summary?.wall_s??null);
const partialEval=t=>t.kind==='eval'&&(t.complete===false||t.summary?.missing>0||(t.progress?.total>0&&(t.summary?.n??t.progress.done??0)<t.progress.total));
// Observed work ends at the last heartbeat when a process has gone silent.
const wbObservedEnd=t=>t.ended||(t.status==='running'?now():Math.max(t.created||0,t.heartbeat||t.updated||t.created||0));
const wbResultSummary=t=>t.result_summary||t.summary?.benchmark_report?.conclusion||(Array.isArray(t.summary?.throughput)?`${t.summary.throughput.length} measured throughput rows`:'');
// [label, class] for a task's state, sentence case
const wbState=t=>emptyEval(t)?['No results','failed']:partialEval(t)&&!isLive(t)?[t.status==='failed'?'Failed · partial':t.status==='budget'?'Out of time · partial':'Partial','partial']:({done:['Done','done'],completed:['Done','done'],failed:['Failed','failed'],budget:['Out of time','budget'],stalled:['Stalled','stalled'],running:['Running','running']})[t.status]||[wbKind(t.status),t.status];
// a duration next to a budget: to the second under 10 min ("1 min 15 s of a 1 min 15 s budget"), else as span()
const wbSpanB=s=>{const r=Math.round(s);return r>=60&&r<600&&r%60?`${Math.floor(r/60)} min ${r%60} s`:wbSpan(s)};
// the budget worth showing: evals get a 1 h deadline by default, which only matters once half of it is used
const wbBudget=t=>!t.budget_s?null:t.kind==='eval'&&t.budget_s===3600&&((t.ended||now())-t.created)<1800?null:t.budget_s;
// elapsed against the time budget: [text, cls]; a live job warns past 80% and goes red past the cap; a finished one is
// red only when its budget stopped it
function budgetLine(t){
 const el=(t.ended||now())-t.created;
 if(!t.budget_s)return [wbSpan(el),''];
 const f=el/t.budget_s;
 return [`${wbSpanB(el)} of ${wbSpanB(t.budget_s)}`,t.ended?(t.status==='budget'?'neg':''):f>=1?'neg':f>=.8?'warn':''];
}
const silent=t=>wbSpan(now()-t.heartbeat);
// when a job stops: its predicted finish, or the end of its time budget if that comes first
const bEnd=t=>t.budget_s?t.created+t.budget_s:null;
const fin=t=>t.eta&&t.status==='running'?Math.min(t.eta.finish_at,bEnd(t)??Infinity):null;
const wbFixCmd=t=>`arx task finish ${t.id} --status failed`;
// failures a viewer has opened (per browser, per project); an unopened failure stays on the Workbench for a day
const SEEN_K='arx-seen-failed:'+location.pathname;
const wbSeen=()=>{try{return new Set(JSON.parse(localStorage.getItem(SEEN_K)||'[]'))}catch(e){return new Set()}};
const wbMarkSeen=id=>{try{const s=wbSeen();if(s.has(id))return;s.add(id);localStorage.setItem(SEEN_K,JSON.stringify([...s].slice(-300)))}catch(e){}};
// metric keys as words: running_score → Score so far, latency_s → Latency (s), rewards/correctness/mean → Correctness
const wbMetric=k=>({running_score:'Score so far',score:'Score',latency_s:'Latency',latency_p50:'Latency, median',latency_p95:'Latency, 95th percentile',latency_mean:'Latency, mean',errors:'Errors',missing:'Missing',loss:'Loss',reward:'Reward',acc:'Accuracy',accuracy:'Accuracy',lr:'Learning rate',learning_rate:'Learning rate',grad_norm:'Gradient norm',kl:'KL to reference',entropy:'Entropy',mean_token_accuracy:'Token accuracy',reward_std:'Reward spread',gpu_util:'GPU utilisation',gpu_mem_gb:'GPU memory (GB)'})[k]
 ||(/^rewards\/([^/]+)\/mean$/.test(k)?wbKind(k.split('/')[1]):wbKind(String(k).replace(/_per_(s|sec|second)$/,' per second').replace(/_per_(min|minute)$/,' per minute').replace(/_s$/,'').replace(/\//g,' · ')));

// a logged metric's format, from its name: seconds for latencies and *_s, a whole count for errors and other counts,
// else a plain number (scores are read in the task view against the slice's own scale)
const wbTimeKey=k=>/(^|_)latency(_|$)|(^|_)(p50|p95|wall)(_s)?$|_s$|_sec(onds)?$|_time$|_runtime$/.test(k)&&!/_per_/.test(k);
const wbCountKey=k=>/^(errors?|missing|n|count|observed|done|total|steps?|examples|retries|timeouts?)$|_count$|^num_(?!tokens)|_errors$/.test(k);
const wbFmt=k=>wbTimeKey(k)?'s':wbCountKey(k)?'int':'num';
{
const UNIT={eval:'examples',train:'steps',data:'items',experiment:'repeats'};
// a harness sub-task that only counts for its eval (server marks it detail_of) is part of that eval's card, never its own
const detail=t=>t.detail_of&&isLive(byId(t.detail_of));
const jobs=()=>active().filter(t=>!detail(t)&&!S.state.tasks.some(k=>k.parent===t.id&&isLive(k)&&!detail(k)));
// the live sub-task an eval's numbers come from, if any
const kidOf=t=>t.kind==='eval'?(byId(t.progress_from)||S.state.tasks.find(k=>k.detail_of===t.id&&isLive(k))):null;
const binary=t=>S.state.slices?.[t.slice]?.scale!=='continuous';
// the champion's score on this eval's slice, when it has one: the line the running score is read against
function champRef(t){
 const c=S.state.champion;if(!c||c===t.model)return null;
 const r=S.state.leaderboard?.[t.slice]?.[c];
 // a union slice has no champion run of its own: the server pools the champion's runs on the slices it is made of
 return typeof r?.score==='number'?{y:r.score,label:'champion'}:t.champ_ref?{y:t.champ_ref.y,label:t.champ_ref.runs>1?`champion, ${t.champ_ref.runs} runs`:'champion'}:null;
}
// an eval's panels, completed from its harness sub-task: the sub-task's score becomes the eval's "Score so far"
function evVitals(t){
 const own=t.vitals||[],k=kidOf(t);
 if(t.kind!=='eval')return own;
 const fix=p=>p.id!=='main'?p:{...p,ref:p.ref||champRef(t)};
 if(!k?.vitals?.length)return own.map(fix);
 const kv=k.vitals,out=[];
 let m=own.find(p=>p.id==='main');
 const km=kv.find(p=>p.id==='main');
 if(!m&&km){
  const pts=km.series?.[0]?.pts||[],ys=pts.map(q=>q[1]),unit=binary(t)&&ys.length&&ys.every(y=>y>=0&&y<=1);
  m={...km,title:'Score so far',smooth:false,fmt:unit?'pct':km.fmt,yfmt:unit?'pct':km.yfmt,n:t.progress?.done||km.n,
   ymin:unit?0:km.ymin,ymax:unit?1:km.ymax,series:(km.series||[]).map(s=>({...s,name:'Score'}))};
 }
 if(m)out.push(fix(m));
 for(const p of [...own,...kv])if(p.id!=='main'&&!out.some(q=>q.id===p.id))out.push(p);
 return out.slice(0,4);
}
const n0=x=>Math.round(x).toLocaleString();
const sgn=d=>(d>0?'+':d<0?'−':'±')+n0(Math.abs(d));
const val=(f,v)=>XC.yv(f,v);
function hp(t){
 const h=t.health||{state:t.status==='stalled'?'stalled':'ok'};
 return ({ok:['Healthy','ok'],quiet:[`Quiet ${span(h.silent_s)}`,'warn'],slipping:[`Slipping ${span(h.by_s)}`,'warn'],over:[`Over budget by ${span(h.by_s)}`,'warn'],stalled:[`Silent ${span(h.silent_s??now()-t.heartbeat)}`,'bad']})[h.state]||['Healthy','ok'];
}
function etaTxt(t){
 if(t.status==='stalled')return `<small>no estimate</small>—`;
 if(t.eta&&bEnd(t)&&t.eta.finish_at>bEnd(t))return `<small>budget ends</small><span class="warn">${wbClock(bEnd(t))}</span>`;
 if(t.eta)return `<small>${span(t.eta.eta_s)} left</small>${wbClock(t.eta.finish_at)}`;
 return `<small>estimating</small>—`;
}
function title(t){
 if(t.kind==='eval'&&t.model)return `${mn(t.model)}${t.slice?` <span class="on">on ${esc(short(t.slice))}</span>`:''}`;
 if(t.kind==='train'&&t.model)return `${esc(t.title)} <span class="on">→ ${mn(t.model)}</span>`;
 return esc(t.title);
}
function head(t,short){
 const pr=t.progress||{},[hl,hc]=hp(t),par=byId(t.parent),f=pr.total?Math.min(1,pr.done/pr.total):null;
 const cnt=pr.total?`<span class="wb-cnt"><b>${n0(pr.done)}</b> of ${n0(pr.total)} ${UNIT[t.kind]||''}</span>`:'';
 return `<div class="wb-hl"><span class="wb-kind">${esc(wbKind(t.kind))}</span><h2 class="wb-ttl"><a href="#task/${enc(t.id)}">${title(t)}</a></h2>${par?`<a class="wb-par wb-in" href="#task/${enc(par.id)}" title="${esc(par.title)}">in ${esc(par.title)}</a>`:''}
 ${short?`${f!=null?`<span class="wb-mini">${meter(f)}</span>`:''}${cnt}<span class="wb-vs">${rowValue(t)}</span>`:cnt}<span class="wb-eta">${etaTxt(t)}</span><span class="wb-hp ${hc}">${esc(hl)}</span></div>`;
}
// a short job's one or two vital signs
function rowValue(t){
 const l=t.last||{},bits=[];
 if(typeof l.running_score==='number')bits.push(pct(l.running_score));
 else{const k=Object.keys(l).find(k=>typeof l[k]==='number'&&!/^(t|step|epoch)$/.test(k));if(k)bits.push(`${esc(wbMetric(k).toLowerCase())} ${XC.yv(wbFmt(k),l[k])}`)}
 if((t.health?.silent_s||0)>=60&&t.progress?.total)bits.push(`no progress for ${span(t.health.silent_s)}`);
 else if(t.eta)bits.push(`${t.eta.per_min>=60?n0(t.eta.per_min/60)+' a second':t.eta.per_min>=10?n0(t.eta.per_min)+' a minute':t.eta.per_min.toFixed(1)+' a minute'}`);
 return bits.join(' · ');
}
const smoothLast=(pts,w)=>{const s=XC.ema(pts,w);return s.length?s[s.length-1][1]:null};
// one panel: label, the big number, a live chart
function pn(t,p,lead){
 const grp=`wb-${t.id}`+(p.x?'-'+p.x:''),ser=p.series?.[0]?.pts||[];
 const sm=p.smooth===true,w=XC.g(grp,{w:.6}).w;
 let big='',sub='',lb=p.title,extra='';
 const f=p.fmt==='num'&&p.key?wbFmt(p.key):p.fmt,quiet=Math.max(t.health?.silent_s??0,t.status==='stalled'?now()-t.heartbeat:0);
 if(p.id==='eta'){lb='Done by';const left=p.value-now(),d=p.drift_s||0;
  big=t.status==='stalled'?`<span class="neg">none</span><small>last said ${wbClock(p.value)}</small>`:`${wbClock(p.value)}<small>${left>0?`in ${span(left)}`:'any moment'}</small>`;
  sub=Math.abs(d)<60?'steady':`${span(Math.abs(d))} ${d<0?'sooner':'later'} than 5 min ago`}
 else if(p.id==='gpu'){big=`${Math.round(p.value)}%${p.mem?.[0]!=null?`<small>${p.mem[0].toFixed(1)} of ${p.mem[1]?.toFixed(0)} GB</small>`:''}`;sub=p.gpus>1?`${p.gpus} GPUs`:'';
  if(p.mem?.[1])extra=`<div class="wb-mem">${meter(p.mem[0]/p.mem[1],{cls:'mem'})}</div>`}
 else if(p.id==='pair'){const dl=p.delta??p.value/(p.n||1);big=`<span class="${dl>0?'pos':dl<0?'neg':''}">${sd(t.slice,dl)}</span><small>90% CI ${pts(p.ci[0])} to ${pts(p.ci[1])}</small>`;sub=`${p.won} won · ${p.lost} lost`}
 else if(p.id==='lat'){big=`${p.value.toFixed(1)} s<small>95th ${p.p95.toFixed(1)} s</small>`;sub='median'}
 else if((p.id==='tps'||p.id==='rate')&&quiet>=60){big=`<span class="neg">none</span><small>no progress for ${span(quiet)}</small>`}
 else if(p.id==='tps'){big=`${n0(p.value)}${p.step_time?`<small>${p.step_time.toFixed(1)} s a step</small>`:''}`}
 else if(p.id==='rate'){big=`${p.value<10?p.value.toFixed(1):n0(p.value)}<small>a minute</small>`}
 else if(t.kind==='eval'&&p.id==='main'){const b=p.band?.at(-1),n=p.n;
  big=f==='pct'?`${n0(p.value*n)} of ${n0(n)}<small>${pct(p.value)}${b?` · 90% CI ${(100*b[1]).toFixed(1)}–${(100*b[2]).toFixed(1)}`:''}</small>`:`${val(f,p.value)}<small>over ${n0(n)}</small>`}
 else{lb=wbMetric(p.key||p.title);const v=sm?smoothLast(ser,w):p.value;big=`${val(f,v)}${sm&&ser.length?`<small>raw ${val(f,p.value)}</small>`:''}`;sub=ser.length?`step ${n0(ser.at(-1)[0])}`:''}
 const eh=p.id==='eta'&&(t.eta||kidOf(t)?.eta)?.hist;
 if(eh?.length>1)p={...p,yfmt:'num',ymin:0,series:[{name:'Minutes left',pts:eh.map(([x,f])=>[x,Math.max(0,(f-x)/60)])}]};
 const ch=XC.box(`wb-${t.id}-${p.id}`,{group:grp,mode:'mini',h:lead?150:52,yfmt:p.yfmt||f,xfmt:p.x==='clock'?'clock':p.x==='time'?'time':'num',
  domain:p.domain||null,ymin:p.ymin,ymax:p.ymax,yfix:p.yfix,zero:p.zero,band:p.band,ref:p.ref,smooth:sm,logOk:false,
  series:(p.series||[]).map((s,i)=>({name:s.name,pts:s.pts,faint:s.faint,color:p.id==='gpu'||p.id==='sec'?'var(--chart-2)':s.faint?'var(--chart-3)':'var(--chart-1)'}))});
 return `<div class="wb-pn ${lead?'lead':''}"><div class="wb-lb"><span>${esc(lb)}</span><span>${esc(sub)}</span></div><div class="wb-big">${big}</div>${ch}${extra}</div>`;
}
function card(t){
 const stalled=t.status==='stalled',pr=t.progress||{},ps=evVitals(t);
 const note=t.note?`<div class="note ${esc(t.note.level)}"><span class="msg" title="${esc(t.note.text??t.note.msg)}">${esc(t.note.text??t.note.msg)}</span><span class="when">${wbAgo(t.note.t)}</span></div>`:'';
 const lay=ps.length<=1?'n1':ps.length===2?'n2':ps.length===3?'n3':'n4';
 return `<article class="wb-job long ${stalled?'stalled':''}">${head(t,false)}
 ${pr.total?`<div class="wb-bar">${meter(pr.done/pr.total,{cls:stalled?'neg':''})}</div>`:''}
 ${stalled?`<div class="wb-fix wb-in">${cmd(wbFixCmd(t))}</div>`:''}
 ${note?`<div class="wb-note">${note}</div>`:''}
 ${ps.length?`<div class="wb-vit ${lay} wb-in">${ps.map((p,i)=>pn(t,p,i===0)).join('')}</div>`:''}</article>`;
}
const row=t=>`<article class="wb-job short ${t.status==='stalled'?'stalled':''}">${head(t,true)}${t.status==='stalled'?`<div class="wb-fix wb-in">${cmd(wbFixCmd(t))}</div>`:''}</article>`;
// finished leaf jobs, newest first: what just landed. An eval is one job even when its harness logs a sub-card
// (e.g. "live: …" rolling numbers): the eval shows, its sub-card does not.
function strip(skip=new Set()){
 const evalKid=t=>t.parent&&byId(t.parent)?.kind==='eval';
 const done=S.state.tasks.filter(t=>!isLive(t)&&t.ended&&!skip.has(t.id)&&!evalKid(t)&&(t.kind==='eval'||!S.state.tasks.some(k=>k.parent===t.id))).sort((a,b)=>b.ended-a.ended).slice(0,30);
 // repeats of one job (three "Answer a question request" in a row) are one chip with a count
 const grp=[];for(const t of done){const g=grp.at(-1),ok=t.status==='done'||t.status==='completed';
  if(g&&t.kind!=='eval'&&g.t.kind===t.kind&&g.t.title===t.title&&g.ok===ok)g.n++;else grp.push({t,n:1,ok})}
 if(!grp.length)return '';
 return `<div class="wb-strip">${grp.slice(0,6).map(({t,n,ok})=>{const sm=t.summary||{};
  const res=t.kind==='eval'&&sm.score!=null?(S.state.slices[t.slice]?.scale==='continuous'?fmtv(sm.score):`${n0(sm.score*(sm.n||0))} of ${n0(sm.n||0)}`):emptyEval(t)?'no results':wbTook(t)!=null?span(wbTook(t)):'recorded';
  return `<a class="wb-chip" href="#task/${enc(t.id)}" title="${esc(t.title)}${n>1?` · ${n} in a row, the latest opens`:''}"><span class="${ok&&!emptyEval(t)?'pos':'neg'}">${ok&&!emptyEval(t)?'✓':'✕'}</span><span class="nm">${t.kind==='eval'&&t.model?mn(t.model)+(t.slice?` <span class="mono sub">${esc(short(t.slice))}</span>`:''):esc(t.title)}${n>1?` <b class="wb-x">×${n}</b>`:''}</span><span class="res">${esc(res)}</span><span class="at">${ago(t.ended)}</span></a>`}).join('')}</div>`;
}

// recent failures nobody has opened yet: a red row with the error, until opened or a day old
const failedJobs=()=>{const seen=wbSeen();return S.state.tasks.filter(t=>t.status==='failed'&&t.ended&&now()-t.ended<86400&&!seen.has(t.id)&&!S.state.tasks.some(k=>k.parent===t.id)).sort((a,b)=>b.ended-a.ended)};
const failRow=t=>{const e=t.note?.text??t.note?.msg??'';
 return `<article class="wb-job short failed"><div class="wb-hl"><span class="wb-kind">${esc(wbKind(t.kind))}</span><h2 class="wb-ttl"><a href="#task/${enc(t.id)}">${title(t)}</a></h2><span class="wb-err" title="${esc(e)}">${esc(e)}</span><span class="wb-eta"><small>failed</small>${ago(t.ended)}</span><span class="wb-hp bad">Failed</span></div></article>`};

// stalled for over a day: abandoned. One line for all of them, with one command that closes them all
const isDead=t=>t.status==='stalled'&&(t.dead||now()-(t.heartbeat||t.created)>86400);
function deadGroup(ds){
 if(!ds.length)return '';
 const sil=ds.map(t=>now()-(t.heartbeat||t.created)),lo=Math.min(...sil),hi=Math.max(...sil);
 const c=`for t in ${ds.map(t=>t.id).join(' ')}; do arx task finish $t --status failed; done`;
 return `<details class="wb-job short wb-dead"><summary class="wb-hl"><span class="wb-hp bad">${ds.length} abandoned</span><span class="wb-dn">${ds.map(t=>title(t)).join(', ')}</span><span class="wb-eta"><small>silent</small>${span(lo)}${hi-lo>3600?' – '+span(hi):''}</span></summary>
 <div class="wb-fix">${cmd(c)}</div><ul class="wb-dl">${ds.map(t=>`<li><a href="#task/${enc(t.id)}">${title(t)}</a><span>${span(now()-(t.heartbeat||t.created))}</span></li>`).join('')}</ul></details>`;
}

VIEWS.workbench=()=>{
 const every=jobs(),dead=every.filter(isDead),all=every.filter(t=>!isDead(t));
 const stalled=all.filter(t=>t.status==='stalled').sort((a,b)=>a.heartbeat-b.heartbeat);
 const run=all.filter(t=>t.status==='running').sort((a,b)=>a.created-b.created);  // arrival order: calm, no reshuffling
 const isLong=t=>t.long||kidOf(t)?.long,long=run.filter(isLong),shortJ=run.filter(t=>!isLong(t));
 const ends=run.map(fin).filter(Boolean),last=ends.length?Math.max(...ends):null;
 const parts=[];
 if(stalled.length)parts.push(`<b class="neg">${stalled.length} stalled</b>`);
 if(run.length)parts.push(`<b>${run.length} running</b>`+(last?`, ${ends.length<run.length?`${ends.length} with an estimate `:'all '}done by <b>${wbClock(last)}</b>`:''));
 const failed=failedJobs();
 if(failed.length)parts.unshift(`<b class="neg">${failed.length} failed</b>`);
 if(dead.length)parts.push(`${dead.length} abandoned`);
 const h=page({title:'Workbench',crumbs:[['Workbench','#workbench']],finding:parts.length?parts.join(' · '):'Nothing running.'});
 const list=[...failed.map(failRow),...stalled.map(t=>isLong(t)?card(t):row(t)),...long.map(card),...shortJ.map(row),deadGroup(dead)].filter(Boolean);
 return h+strip(new Set(failed.map(t=>t.id)))+(list.length?`<div class="wb-jobs section">${list.join('')}</div>`:`<section class="section">${panel('',empty('Nothing running','Start one with <code>arx task start --title …</code> or <code>arx.task(...)</code> in Python.'))}</section>`);
};
}
