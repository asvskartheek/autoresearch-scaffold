'use strict';
// Start: where a person lands on a project. It answers, top to bottom: what the project is trying to do (the open goals
// as distance on one figure, the champion), what runs now, what to do next (from the gates and the goals), what needs
// you (questions, threads, failed and abandoned jobs, goals nobody measured) and what changed (days as bars, then the
// latest events as rows), then a map of the dashboard. Built from /api/state; /api/questions, /api/comments and
// /api/brief are read beside it, never more than every 20-60 s. Counts wait for the full task list, so they never jump.
{
const KEY=PKEY||'home',LK='arx-visit:'+KEY,SK='arx-since:'+KEY;
const lget=k=>{try{return localStorage.getItem(k)}catch(e){return null}};
const lset=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
const sget=k=>{try{return sessionStorage.getItem(k)}catch(e){return null}};
const sset=(k,v)=>{try{sessionStorage.setItem(k,v)}catch(e){}};
// "since you last looked": the previous visit to this project in this browser, fixed for this tab (a reload keeps it)
const prevVisit=lget(LK);
let since=sget(SK);if(since==null){since=prevVisit||'';sset(SK,since)}
since=+since||null;
const stampNow=()=>lset(LK,String(Date.now()/1000));
stampNow();addEventListener('pagehide',stampNow);
window.START={first:prevVisit==null&&!since};

// extras, fetched beside the poll while Start is on screen
const X={q:null,qAt:0,c:null,cAt:0,b:null,bAt:0,busy:{}};
const get=async(k,url,ttl)=>{
 if(X.busy[k]||Date.now()-X[k+'At']<ttl)return;X.busy[k]=1;
 try{const r=await fetch(url,{cache:'no-store'});if(r.ok){X[k]=await r.json();X[k+'At']=Date.now();if(route().r==='start')render()}}
 catch(e){}finally{X.busy[k]=0}};
function fetchExtras(){
 const st=S.state,me=window.ARXP?ARXP.me().id:'';
 get('q','api/questions',st.questions?.needs_human?20000:60000);
 if(st.comments?.open)get('c','api/comments',20000);else X.c={threads:[]};
 const bs=+lget('arx-brief-seen:'+KEY)||0;
 get('b',`api/brief?since=${bs}&viewer=${enc(me||'anon')}`,60000);
}

// ---------- the ledger as Start counts it (the same rules as the Archive and the Workbench)
// the full task list is in (until then /api/state carries only a recent window, and any count would jump)
const ready=()=>!((S.state.tasks_total||0)>S.state.tasks.length);
const isTop=t=>!t.parent||!byId(t.parent);              // a job, as the Archive lists it; sub-tasks fold under it
const imported=t=>/^historical/.test(t.kind||'');        // records imported from before arx, not work done here
const bad=t=>t.status==='failed'||t.status==='budget';
// abandoned: a top job silent for over a day (the Workbench's "N abandoned")
const deadJobs=()=>active().filter(t=>t.status==='stalled'&&quietFor(t)>DEAD_S&&t.kind!=='answer'&&isTop(t));
// the window "what changed" covers: since your last visit when that is older than a week (up to 30 days), else 7 days
const win=()=>{const t1=now(),wk=t1-7*86400;return {t1,t0:since&&since<wk?Math.max(since,t1-30*86400):wk}};
const lastCh=t=>t.ended||t.updated||0;

const U=()=>window.GoalUnits;
// where the champion stands on the goal's rail: 0 at the baseline, 1 at the target, up to OVER past it (met with room)
const OVER=1.2;
function frac(g){
 const u=U(),P=u.prog(g);if(P.mode==='none')return null;
 let f;
 if(P.mode==='rel')f=P.p;
 else{const v=u.disp(g,g.value),t=u.disp(g,g.target);f=u.cmpSym(g)==='≥'?v/t:t/v}
 if(!isFinite(f))f=g.met?OVER:0;
 if(g.met)f=Math.max(1,f);
 return Math.max(0,Math.min(OVER,f));
}
const CHEV=I('<path d="M9 6l6 6-6 6"/>',14),TALK=I('<path d="M5 5.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4.5 3.5V16.5H5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/>');
const NEXT=I('<path d="M5 12h13M13 6l6 6-6 6"/>'),OKI=I('<path d="M5 12.5l4.5 4.5L19 7.5"/>',18);
const go=(href,label)=>`<a class="sx-go" href="${href}">${label}${CHEV}</a>`;
const pc=f=>(100*f/OVER).toFixed(1)+'%';

// (1) the goals on one figure: every rail runs from its baseline (left) to its target (the dashed line); a met goal
// with room to spare runs past the line
function goalsBlock(){
 const st=S.state,u=U(),gs=Object.values(st.goals||{}).filter(g=>g.status==='open');
 const champ=`<span class="sx-k">${term('champion','Champion')}</span>`+(st.champion?`<a class="sx-champ" href="#model/${enc(st.champion)}" data-item>${ICON.models}<b class="ell">${mn(st.champion)}</b></a>`:`<span class="sx-champ faint">None yet</span>`);
 if(!gs.length||!u)return panel(term('goal','Goal'),`<div class="sx-none">${Object.keys(st.goals||{}).length?'No open goal':'No goal yet'}</div><div class="sx-foot">${champ}</div>`,{right:go('#goals','Goals')});
 const rows=gs.sort((a,b)=>u.isMain(b)-u.isMain(a)).map(g=>{
  const f=frac(g),d=u.dist(g),P=u.prog(g);
  const ds=d&&u.ofP(g)&&d.short?`right${u.ofP(g)}`:d?.s;
  const fig=d?(d.short?`<b class="neg">${d.v}</b><span>${ds}</span>`:`<b class="pos">Met</b><span>${d.s}</span>`):`<b class="faint">—</b><span>not run</span>`;
  const nowv=g.value==null?'—':u.gu(g,g.value),tgt=`${u.cmpSym(g)}&nbsp;${u.gt(g)}${u.ofP(g)}`;
  const b0=P.mode==='rel'&&P.b!=null&&f!=null&&f/OVER>.25?`<em class="sx-b0 num">${u.gu(g,P.b)}</em>`:'';
  const tip=`Now ${nowv}${u.ofP(g)} · target ${tgt}${P.b!=null?' · baseline '+u.gu(g,P.b):''}`.replace(/&nbsp;/g,' ');
  const pos=f==null?0:f/OVER;
  return `<a class="sx-g ${u.isMain(g)?'':'sub'}" href="#goal/${enc(g.name)}" title="${esc(tip)}" data-item>
   <span class="sx-gt"><span class="ell">${esc(g.title||g.name)}<span class="faint sx-gs"> · ${esc(g.slice)}</span></span><span class="sx-tg num">${tgt}</span></span>
   <span class="sx-rail ${g.met?'met':''} ${f==null?'none':''}">${b0}${f!=null?`<i style="width:${pc(f)}"></i><b style="left:${pc(f)}" class="${pos<.12?'lo':pos>.88?'hi':''}"><span class="num">${nowv}</span></b>`:''}</span>
   <span class="sx-gd num">${fig}</span></a>`}).join('');
 const axis=`<div class="sx-axis sx-gax"><span>baseline</span><span class="sx-at">${term('goal','target')}</span></div>`;
 return panel(term('goal','Goal'),`<div class="sx-fig">${rows}<i class="sx-tline" aria-hidden="true"></i></div>${axis}<div class="sx-foot">${champ}</div>`,{right:go('#goals','Goals')});
}

// (2) live jobs: atomic, not an answer agent, not a detail of another task; evals carry their rolled-up progress.
// Jobs silent for over a day are not running: they are under Needs you, as abandoned
function nowBlock(){
 const jobs=liveJobs().filter(t=>!(t.detail_of||t.config?.detail_of)).sort((a,b)=>(a.status==='stalled')-(b.status==='stalled')||(b.created-a.created));
 if(!jobs.length)return panel('Now',`<div class="sx-none">${ICON.workbench}Nothing running</div>`,{right:go('#workbench','Workbench')});
 const row=t=>{const pr=t.progress||{},f=pr.total?pr.done/pr.total:null,sl=t.status==='stalled';
  const nm=t.kind==='eval'&&t.model?`${mn(t.model)}<span class="faint"> · ${esc(short(t.slice||''))}</span>`:esc(t.title);
  const v=sl?`<span class="neg">silent ${span(quietFor(t))}</span>`:pr.total?`${pr.done.toLocaleString()}<span class="faint"> / ${pr.total.toLocaleString()}</span>`:`<span class="faint">${dur(t.created)}</span>`;
  const eta=!sl&&t.eta?.eta_s!=null?`<span class="faint">${left(t.eta.eta_s)} left</span>`:'';
  return `<a class="sx-job ${sl?'stalled':''}" href="#task/${enc(t.id)}" title="${esc(t.title)}" data-item><span class="sd ${t.status}"></span><span class="sx-jn ell">${nm}</span><span class="sx-jv num">${v}${eta?' · '+eta:''}</span>${f!=null?meter(f,{cls:sl?'muted':''}):'<span class="sx-pulse"></span>'}</a>`};
 const cap=5;
 return panel('Now',`<div class="sx-jobs">${jobs.slice(0,cap).map(row).join('')}</div>${jobs.length>cap?`<a class="sx-more" href="#workbench">+${jobs.length-cap}</a>`:''}`,{meta:String(jobs.length),right:go('#workbench','Workbench')});
}

// (3) next: the concrete runs that move the research, from the gates (`arx gate`) and the goals. Each row says what
// to run and why; its copy button holds the command for whoever drives the agent
const rungOf=(g,slice)=>g?.rungs?.find(r=>(r.checks||[]).some(c=>c.slice===slice))?.rung;
function nextSteps(){
 const st=S.state,out=[],gates=st.gates||{},goals=Object.values(st.goals||{}).filter(g=>g.status==='open');
 // a new project: the eval set, then the model to beat, then the goal
 const sls=Object.keys(st.slices||{}),full=sls.find(x=>/\/full$/.test(x));
 if(!sls.length)out.push({h:'#slices',t:'Register the eval set: its full slice and random samples',c:'arx dataset add <name> --ids-file <ids.txt>'});
 if(!st.champion){
  const g=goals[0];
  out.push({h:g?`#goal/${enc(g.name)}`:'#models',t:`Name a ${term('champion')}: register the model to beat${g?` and run it on <b>${esc(short(g.slice))}</b>`:''}`,c:'arx model add <name> --champion'});
 }
 if(!goals.length)out.push({h:'#goals',t:`Open a ${term('goal')}: the target KPI on one slice`,c:`arx goal open <goal> --title "<title>" --slice ${full||'<slice>'} --target <target>`});
 for(const g of goals)if(g.value==null&&st.champion)
  out.push({h:`#goal/${enc(g.name)}`,t:`Measure the goal: run ${mn(st.champion)} on <b>${esc(g.slice)}</b>${st.config.baseline_cmd?'':' — no harness configured; record its output rows'}`,c:goalMeasureCmd(g)});
 // the champion's baseline (`arx baseline`): slices it has no run on, which the gates and hills compare against
 const bl=st.baseline,need=(st.champion&&bl?.model===st.champion?bl.need||[]:[])
  .filter(x=>!active().some(t=>t.kind==='eval'&&t.model===st.champion&&t.slice===x));
 const lab=x=>need.filter(y=>short(y)===short(x)).length>1?x:short(x);
 if(need.length){const nm=need.slice(0,2).map(x=>`<b>${esc(lab(x))}</b>`).join(', ')+(need.length>2?` and ${need.length-2} more`:'');
  out.push({h:'#overview',t:`Baseline ${term('champion')} ${mn(st.champion)} on ${plural(need.length,'slice')} it has no run on: ${nm}`,c:'arx baseline'})}
 // candidates nearest promotion first: most rungs passed
 const cands=Object.entries(gates).filter(([m,g])=>st.models[m]?.status==='candidate'&&!g.error)
  .map(([m,g])=>[m,g,(g.rungs||[]).filter(r=>r.status==='pass').length]).sort((a,b)=>b[2]-a[2]);
 // several cleared the gate: promote the one with the largest gain on the last rung's first check; the rest are
 // gated again against the new champion, so they are one row, not one each
 const gain=g=>g.rungs?.at(-1)?.checks?.[0]?.delta??0;
 const prom=cands.filter(([,g])=>g.promotable).sort((a,b)=>gain(b[1])-gain(a[1]));
 if(prom.length)out.push({h:`#model/${enc(prom[0][0])}`,t:`Promote ${distinctModel(prom[0][0])}: it cleared every ${term('rung')} of the ${term('gate')}${prom.length>1?` <span class="faint">· ${prom.length-1} more cleared it, with a smaller gain</span>`:''}`,c:`arx promote ${prom[0][0]}`});
 for(const [m,g] of cands){
  const nx=(g.next||[]).filter(n=>n.model===m);if(!nx.length)continue;
  const n=nx.find(n=>!n.running)||nx[0],rt=n.running&&byId(n.running),r=rungOf(g,n.slice);
  const sn=short(n.slice),where=`<b>${esc(sn)}</b>${r&&r!==sn?` (${esc(r)} ${term('rung')})`:r?' '+term('rung'):''}`;
  if(rt&&rt.status==='stalled')out.push({h:`#task/${enc(rt.id)}`,t:`Rerun ${distinctModel(m)} on ${where}: its run went silent ${span(quietFor(rt))} ago`,c:`arx gate ${m}`,bad:1});
  else if(!n.running)out.push({h:`#model/${enc(m)}`,t:`Run ${term('candidate')} ${distinctModel(m)} on ${where}`,c:`arx gate ${m}`});
 }
 return out;
}
function nextBlock(){
 const steps=nextSteps(),cap=4;
 const row=s=>`<div class="sx-nx ${s.bad?'bad':''}" data-item><a href="${s.h}">${NEXT}<span>${s.t}</span></a>${s.c?copyBtn(s.c).replace('title="Copy"',`title="Copy: ${esc(s.c)}"`):''}</div>`;
 const body=steps.length?`<div class="sx-nxs">${steps.slice(0,cap).map(row).join('')}</div>${steps.length>cap?`<a class="sx-more" href="#models">+${steps.length-cap}</a>`:''}`
  :`<div class="sx-none">Every ${term('candidate')} has its runs. Open a ${term('hill')} to try the next idea.</div>`;
 return panel('Next',body,{meta:steps.length?String(steps.length):'',right:go('#models','Models')});
}

// (4) what waits on you: flagged questions, threads with news for you, comments the agent failed to answer, jobs that
// failed or went silent, goals nobody has measured. One row per thing, or one row for a group of the same kind
function needsBlock(){
 const st=S.state,me=window.ARXP?ARXP.me().id:'',items=[],{t0}=win();
 const loading=!ready()||!X.q||!X.c;
 const qs=(X.q?.nodes||[]).filter(n=>n.needs_human&&(n.status==='open'||n.status==='agent'));
 qs.forEach(n=>items.push(['ask',`#questions/${enc(n.id)}`,ICON.questions,esc(n.title),'question']));
 if(st.questions?.needs_human&&!qs.length)items.push(['ask','#questions',ICON.questions,plural(st.questions.needs_human,'question'),'question']);
 const unread=c=>c.last_t>((c.seen||{})[me]||0)&&c.messages.at(-1)?.by!==me;
 const link=c=>`?c=${enc(c.id)}#${esc(c.route||'overview')}`,first=c=>esc(String(c.messages[0]?.body||'').slice(0,90));
 const ths=(X.c?.threads||[]).filter(c=>!c.resolved);
 const mine=ths.filter(c=>unread(c)&&((c.mentions||[]).includes(me)||(c.people||[]).includes(me)||c.messages.at(-1)?.agent&&c.messages.some(m=>m.by===me)));
 mine.forEach(c=>items.push(['talk',link(c),TALK,first(c),c.messages.at(-1)?.agent?'reply':'comment']));
 const failedAns=ths.filter(c=>!mine.includes(c)&&c.messages.at(-1)?.agent&&/^The agent failed/.test(c.messages.at(-1).body||''));
 if(failedAns.length===1)items.push(['bad',link(failedAns[0]),TALK,first(failedAns[0]),'no answer']);
 else if(failedAns.length)items.push(['bad',link(failedAns[0]),TALK,`${failedAns.length} comments the agent failed to answer`,'no answer']);
 const group=(ts,one,many,tag,href)=>{if(ts.length<=2)ts.forEach(t=>items.push(['bad',`#task/${enc(t.id)}`,ICON.workbench,esc(t.title),one(t)]));
  else items.push(['bad',href,ICON.workbench,many(ts.length),tag])};
 if(ready()){
  const dead=deadJobs().sort((a,b)=>quietFor(a)-quietFor(b));
  group(dead,t=>'silent '+span(quietFor(t)),n=>`${n} jobs went silent and were never closed`,'abandoned','#workbench');
  active().filter(t=>t.status==='stalled'&&quietFor(t)<=DEAD_S&&t.kind!=='answer')
   .forEach(t=>items.push(['bad',`#task/${enc(t.id)}`,ICON.workbench,esc(t.title),'silent '+span(quietFor(t))]));
  const failed=S.state.tasks.filter(t=>bad(t)&&t.kind!=='answer'&&!imported(t)&&isTop(t)&&lastCh(t)>t0).sort((a,b)=>lastCh(b)-lastCh(a));
  group(failed,t=>t.status==='budget'?'out of time':'failed',n=>`${n} jobs failed since ${since&&since<=t0+1?'you looked':stamp(t0).split(',')[0]}`,'failed','#archive');
 }
 for(const g of Object.values(st.goals||{}))if(g.status==='open'&&g.value==null)
  items.push(['bad',`#goal/${enc(g.name)}`,ICON.goals,`${esc(g.title||g.name)}: ${g.model||st.champion?`${mn(g.model||st.champion)} has no complete run on ${esc(g.slice)}`:'no champion to measure'}`,'unmeasured']);
 const body=items.length?`<div class="sx-needs">${items.map(([k,h,ic,txt,tag])=>`<a class="sx-need ${k}" href="${h}" data-item>${ic}<span class="ell">${txt}</span><span class="sx-tag">${tag}</span></a>`).join('')}</div>`
  :loading?`<div class="sx-none">Checking…</div>`:`<div class="sx-none ok">${OKI}Nothing waits on you</div>`;
 return panel('Needs you',body,{meta:loading?'…':items.length?String(items.length):'',cls:items.length?'sx-hot':''});
}

// (5) what changed: one bar per day (stacked by kind), counts by kind, the latest events as rows, the Brief
const KIND={win:['Champion','var(--positive)'],rej:['Rejected','var(--control)'],goal:['Goal','var(--chart-3)'],paper:['Paper','var(--chart-3)'],fail:['Failed','var(--negative)'],run:['Run','var(--chart-1)'],job:['Job','var(--faint)']};
function events(t0){
 const st=S.state,ev=[];
 st.tasks.forEach(t=>{const e=t.ended;if(!e||e<=t0||t.kind==='answer'||imported(t))return;
  if(bad(t)){if(isTop(t))ev.push([e,'fail',esc(t.title),'#task/'+enc(t.id)]);return}
  if(t.kind==='eval'){const sc=t.summary?.score;
   ev.push([e,'run',`${t.model?mn(t.model):esc(t.title)}${t.slice?` <span class="faint">on ${esc(short(t.slice))}</span>`:''}${sc!=null?` · <b class="num">${sv(t.slice,sc,isCont(t.slice)?undefined:t.summary?.n)}</b>`:''}`,'#task/'+enc(t.id)]);return}
  if(isTop(t))ev.push([e,'job',esc(t.title),'#task/'+enc(t.id)])});
 // a model counts once per kind: the champion markers a seed writes twice, a model rejected three times
 const once={};
 (st.decisions||[]).slice().sort((a,b)=>b.t-a.t).forEach(d=>{if(!(d.t>t0))return;
  const k=d.kind==='promote'||d.kind==='champion'?'win':d.kind==='rejected'?'rej':/^goal_/.test(d.kind)?'goal':null;if(!k)return;
  const id=k+':'+(d.model||d.goal);if(once[id])return;once[id]=1;
  if(k==='win')ev.push([d.t,k,`${mn(d.model)} became ${term('champion')}`,'#model/'+enc(d.model||'')]);
  else if(k==='rej')ev.push([d.t,k,`${mn(d.model)} rejected${d.reason?` <span class="faint">· ${esc(firstLine(d.reason)).slice(0,80)}</span>`:''}`,'#model/'+enc(d.model||'')]);
  else{const g=st.goals?.[d.goal];ev.push([d.t,k,`${d.kind==='goal_open'?'Goal opened':d.kind==='goal_achieved'?'Goal met':'Goal '+esc(d.kind.slice(5))}: ${esc(g?.title||d.goal||'')}`,'#goal/'+enc(d.goal||'')])}});
 Object.values(st.papers||{}).forEach(p=>{if(p.updated>t0)ev.push([p.updated,'paper',`Paper: ${esc(p.title||p.name)}`,paperUrl(p)])});
 return ev.sort((a,b)=>b[0]-a[0]);
}
function daysFig(ev,t0,t1){
 const D=86400,day0=new Date(t1*1000);day0.setHours(0,0,0,0);
 const nd=Math.min(30,Math.max(1,Math.ceil((t1-t0)/D))),start=day0.getTime()/1000-(nd-1)*D;
 const cols=Array.from({length:nd},(_,i)=>({t:start+i*D,c:{}}));
 ev.forEach(([t,k])=>{const i=Math.floor((t-start)/D);if(i>=0&&i<nd)cols[i].c[k]=(cols[i].c[k]||0)+1});
 const tot=c=>Object.values(c.c).reduce((a,b)=>a+b,0),mx=Math.max(1,...cols.map(tot));
 const lab=t=>new Date(t*1000).toLocaleDateString('en-GB',nd<=8?{weekday:'short'}:{day:'numeric'});
 return `<div class="sx-days" style="--nd:${nd}">${cols.map((c,i)=>{const n=tot(c);
  const tip=n?Object.keys(KIND).filter(k=>c.c[k]).map(k=>`${c.c[k]} ${KIND[k][0].toLowerCase()}`).join(', '):'nothing';
  return `<div class="sx-day" title="${esc(new Date(c.t*1000).toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'}))}: ${tip}"><div class="sx-dbar" style="height:${(100*n/mx).toFixed(1)}%">${Object.keys(KIND).filter(k=>c.c[k]).map(k=>`<i style="flex:${c.c[k]};background:${KIND[k][1]}"></i>`).join('')}</div><span>${nd<=8||i%Math.ceil(nd/8)===nd%Math.ceil(nd/8)-1||i===nd-1?lab(c.t):''}</span></div>`}).join('')}</div>`;
}
// the rows: the events that change the research first (champions, rejections, goals, papers, failures), runs after;
// at most two of a kind, so one busy kind cannot hide the rest
function pick(ev,cap=6){
 const rank={win:0,goal:0,rej:1,paper:1,fail:2,run:3,job:4},per={},out=[];
 for(const e of ev.slice().sort((a,b)=>rank[a[1]]-rank[b[1]]||b[0]-a[0])){if(out.length>=cap)break;if((per[e[1]]=(per[e[1]]||0)+1)>2)continue;out.push(e)}
 return out.sort((a,b)=>b[0]-a[0]);
}
function sinceBlock(){
 const {t0,t1}=win(),b=X.b,cards=b?.cards?.length;
 const brief=`<a class="sx-brief ${cards?'':'quiet'}" href="#learn" data-item>${ICON.learn}<b>${term('brief','Brief')}</b><span class="num">${b?plural(cards,'card'):'…'}</span></a><a class="btn sx-catch" href="#learn?catchup=1" data-item>Catch up</a>`;
 const head={meta:since?`since ${esc(stamp(since).split(',')[0])}`:'7 days'};
 if(!ready())return panel('What changed',`<div class="sx-none">Reading the ledger…</div><div class="sx-foot">${brief}</div>`,head);
 const ev=events(t0),n=k=>ev.filter(e=>e[1]===k).length,fresh=since?ev.filter(e=>e[0]>since).length:0;
 if(since)head.meta=fresh?`${fresh} new since ${esc(stamp(since).split(',')[0])}`:`nothing new since ${ago(since)}`;
 const tiles=[['run','Runs',n('run'),'#archive'],['win','Champions',n('win'),'#models'],['rej','Rejected',n('rej'),'#models'],['fail','Failed',n('fail'),'#archive'],['paper','Papers',n('paper'),'#papers'],['job','Other jobs',n('job'),'#archive']].filter(x=>x[2]);
 const rows=pick(ev).map(([t,k,l,h])=>`<a class="sx-ev ${k}" href="${esc(h)}" data-item><i style="background:${KIND[k][1]}"></i><span class="sx-el">${l}</span><span class="sx-ew">${since&&t>since?'<span class="sx-new">new</span>':''}${ago(t)}</span></a>`).join('');
 const body=ev.length?`<div class="sx-chg"><div>${daysFig(ev,t0,t1)}<div class="sx-tiles">${tiles.map(([k,l,c,h])=>`<a class="sx-tile ${k}" href="${h}" data-item><b class="num">${c.toLocaleString()}</b><span>${l}</span></a>`).join('')}</div></div><div class="sx-evs">${rows}</div></div>`
  :`<div class="sx-none">Nothing in the last 7 days</div>`;
 return panel('What changed',body+`<div class="sx-foot">${brief}</div>`,head);
}

// (6) the dashboard's map: each page with a live count, counted as that page counts it
function mapBlock(){
 const st=S.state,o=x=>Object.values(x||{}),ld=!ready();
 const nq=X.q?.nodes?.filter(n=>n.status==='open'||n.status==='agent').length,mineQ=st.questions?.needs_human||0;
 const ncand=o(st.models).filter(m=>m.status==='candidate').length;
 const C={learn:X.b?.cards?String(X.b.cards.length):'',workbench:String(liveJobs().length),
  goals:String(o(st.goals).filter(g=>g.status==='open').length),questions:nq!=null?String(nq):'',
  models:String(o(st.models).length),hills:String(o(st.hills).filter(h=>h.status==='open').length),papers:String(o(st.papers).length),
  slices:String(Object.keys(st.slices||{}).length),archive:ld?'…':archived().filter(isTop).length.toLocaleString()};
 const T={learn:'brief',goals:'goal',hills:'hill',slices:'slice'};
 const L={overview:`${term('champion')}, ${term('ladder')}`,learn:'cards to catch up',workbench:'running',goals:'open',
  questions:mineQ?`open · <b class="hot">${mineQ} for you</b>`:'open',models:`${ncand} ${term('candidate',ncand===1?'candidate':'candidates')}`,
  hills:'open',papers:'write-ups',slices:'frozen',archive:'finished jobs'};
 return panel('Map',`<div class="sx-map">${ROUTES.filter(([k])=>k!=='start').map(([k,l])=>`<a class="sx-pg" href="#${k}" data-item>${ICON[k]||''}<b>${T[k]?term(T[k],l):l}</b><span class="sx-pc num ell">${C[k]||''}</span><span class="sx-pl">${L[k]||''}</span></a>`).join('')}</div>`);
}

VIEWS.start=()=>{
 fetchExtras();
 const st=S.state;
 return page({title:st.config?.name||'Start',crumbs:[['Start']]})+
  `<div class="sx">
   <div class="sx-a">${goalsBlock()}</div>
   <div class="sx-b">${nowBlock()}</div>
   <div class="sx-n">${nextBlock()}</div>
   <div class="sx-c">${needsBlock()}</div>
   <div class="sx-d">${sinceBlock()}</div>
   <div class="sx-e">${mapBlock()}</div>
  </div>`;
};
}
