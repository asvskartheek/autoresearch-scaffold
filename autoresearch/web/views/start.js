'use strict';
// Start: where a person lands on a project. Top to bottom: what the project is trying to do (the open goals as distance
// on one figure, the champion), what runs now, what needs you, what changed since you last looked (one way into the
// Brief) and a map of the dashboard. Built from /api/state; /api/questions, /api/comments and /api/brief are read only
// when they have something to add, and never more than every 20-60 s.
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
 if(st.comments?.open)get('c','api/comments',20000);else X.c=null;
 const bs=+lget('arx-brief-seen:'+KEY)||0;
 get('b',`api/brief?since=${bs}&viewer=${enc(me||'anon')}`,60000);
}

const U=()=>window.GoalUnits;
const clamp=f=>Math.max(0,Math.min(1,f));
// the share of the way from baseline to target, as the overview's goal track draws it
function frac(g){
 const u=U(),P=u.prog(g);if(g.met)return 1;
 if(P.mode==='rel')return clamp(P.p);
 if(P.mode==='abs'){const x=u.cmpSym(g)==='≥'?u.disp(g,g.value)/u.disp(g,g.target):u.disp(g,g.target)/u.disp(g,g.value);return isFinite(x)?clamp(x):0}
 return null;
}
const CHEV=I('<path d="M9 6l6 6-6 6"/>',14),TALK=I('<path d="M5 5.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4.5 3.5V16.5H5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/>');
const go=(href,label)=>`<a class="sx-go" href="${href}">${label}${CHEV}</a>`;

// (1) the goals on one figure: every track runs from its baseline (left) to its target (the dashed line, right)
function goalsBlock(){
 const st=S.state,u=U(),gs=Object.values(st.goals||{}).filter(g=>g.status==='open');
 const champ=st.champion?`<a class="sx-champ" href="#model/${enc(st.champion)}" title="Champion">${ICON.models}<span class="sx-k">Champion</span><b class="ell">${mn(st.champion)}</b></a>`:`<span class="sx-champ faint">${ICON.models}No champion yet</span>`;
 if(!gs.length||!u)return panel('Goal',`<div class="sx-none">${Object.keys(st.goals||{}).length?'No open goal':'No goal yet'}</div><div class="sx-foot">${champ}</div>`,{right:go('#goals','Goals')});
 const rows=gs.sort((a,b)=>u.isMain(b)-u.isMain(a)).map(g=>{
  const f=frac(g),d=u.dist(g);
  const fig=d?(d.short?`<b class="neg">${d.v}</b><span>${d.s}</span>`:`<b class="pos">Met</b><span>${d.s}</span>`):`<b class="faint">—</b><span>not run</span>`;
  const now=g.value==null?'—':u.gu(g,g.value);
  const tip=`Now ${now}${u.ofP(g)} · target ${u.cmpSym(g)} ${u.gt(g)}`.replace(/&nbsp;/g,' ');
  return `<a class="sx-g ${u.isMain(g)?'':'sub'}" href="#goal/${enc(g.name)}" title="${esc(tip)}">
   <span class="sx-gt ell">${esc(g.title||g.name)}</span>
   <span class="sx-rail ${g.met?'met':''} ${f==null?'none':''}">${f!=null?`<i style="width:${(100*f).toFixed(1)}%"></i><b style="left:${(100*f).toFixed(1)}%" class="${f<.1?'lo':f>.9?'hi':''}"><span class="num">${now}</span></b>`:''}</span>
   <span class="sx-gd num">${fig}</span></a>`}).join('');
 const axis=`<div class="sx-axis"><span>baseline</span><span>target</span></div>`;
 return panel('Goal',`<div class="sx-fig">${rows}<i class="sx-tline" aria-hidden="true"></i></div>${axis}<div class="sx-foot">${champ}</div>`,{right:go('#goals','Goals')});
}

// (2) live jobs: atomic, not an answer agent, not a detail of another task; evals carry their rolled-up progress
function nowBlock(){
 const jobs=liveJobs().filter(t=>!(t.detail_of||t.config?.detail_of)).sort((a,b)=>(a.status==='stalled')-(b.status==='stalled')||(b.created-a.created));
 if(!jobs.length)return panel('Now',`<div class="sx-none">${ICON.workbench}Nothing running</div>`,{right:go('#workbench','Workbench')});
 const row=t=>{const pr=t.progress||{},f=pr.total?pr.done/pr.total:null,sl=t.status==='stalled';
  const nm=t.kind==='eval'&&t.model?`${mn(t.model)}<span class="faint"> · ${esc(short(t.slice||''))}</span>`:esc(t.title);
  const v=sl?`<span class="neg">silent ${span(quietFor(t))}</span>`:pr.total?`${pr.done.toLocaleString()}<span class="faint"> / ${pr.total.toLocaleString()}</span>`:`<span class="faint">${dur(t.created)}</span>`;
  const eta=!sl&&t.eta?.eta_s!=null?`<span class="faint">${left(t.eta.eta_s)} left</span>`:'';
  return `<a class="sx-job ${sl?'stalled':''}" href="#task/${enc(t.id)}" title="${esc(t.title)}"><span class="sd ${t.status}"></span><span class="sx-jn ell">${nm}</span><span class="sx-jv num">${v}${eta?' · '+eta:''}</span>${f!=null?meter(f,{cls:sl?'muted':''}):'<span class="sx-pulse"></span>'}</a>`};
 const cap=5;
 return panel('Now',`<div class="sx-jobs">${jobs.slice(0,cap).map(row).join('')}</div>${jobs.length>cap?`<a class="sx-more" href="#workbench">+${jobs.length-cap}</a>`:''}`,{meta:String(jobs.length),right:go('#workbench','Workbench')});
}

// (3) what waits on you: flagged questions, threads with news for you, failed and silent jobs
function needsBlock(){
 const st=S.state,me=window.ARXP?ARXP.me().id:'',items=[];
 const qs=(X.q?.nodes||[]).filter(n=>n.needs_human&&(n.status==='open'||n.status==='agent'));
 qs.forEach(n=>items.push(['ask',`#questions/${enc(n.id)}`,ICON.questions,esc(n.title),'question']));
 if(st.questions?.needs_human&&!qs.length)items.push(['ask','#questions',ICON.questions,plural(st.questions.needs_human,'question'),'question']);
 const unread=c=>c.last_t>((c.seen||{})[me]||0)&&c.messages.at(-1)?.by!==me;
 (X.c?.threads||[]).filter(c=>!c.resolved&&unread(c)&&((c.mentions||[]).includes(me)||(c.people||[]).includes(me)||c.messages.at(-1)?.agent&&c.messages.some(m=>m.by===me)))
  .forEach(c=>items.push(['talk',`?c=${enc(c.id)}#${esc(c.route||'overview')}`,TALK,esc(String(c.messages[0]?.body||'').slice(0,90)),c.messages.at(-1)?.agent?'reply':'comment']));
 const t0=since||now()-3*86400;
 st.tasks.filter(t=>(t.status==='failed'||t.status==='budget')&&t.kind!=='answer'&&(t.ended||t.updated||0)>t0).slice(0,6)
  .forEach(t=>items.push(['bad',`#task/${enc(t.id)}`,ICON.workbench,esc(t.title),t.status==='budget'?'out of time':'failed']));
 active().filter(t=>t.status==='stalled'&&quietFor(t)<=DEAD_S&&t.kind!=='answer')
  .forEach(t=>items.push(['bad',`#task/${enc(t.id)}`,ICON.workbench,esc(t.title),'silent '+span(quietFor(t))]));
 const body=items.length?`<div class="sx-needs">${items.map(([k,h,ic,txt,tag])=>`<a class="sx-need ${k}" href="${h}">${ic}<span class="ell">${txt}</span><span class="sx-tag">${tag}</span></a>`).join('')}</div>`
  :`<div class="sx-none ok">${I('<path d="M5 12.5l4.5 4.5L19 7.5"/>',18)}Nothing waits on you</div>`;
 return panel('Needs you',body,{meta:items.length?String(items.length):'',cls:items.length?'sx-hot':''});
}

// (4) since you last looked: a time strip of what happened, counts by kind, and the Brief
function sinceBlock(){
 const st=S.state,t1=now(),t0=since||t1-7*86400,ev=[];
 st.tasks.forEach(t=>{const e=t.ended;if(!e||e<=t0||t.kind==='answer')return;
  if(t.status==='failed'||t.status==='budget')ev.push([e,'fail',t.title,'#task/'+enc(t.id)]);
  else if(t.kind==='eval')ev.push([e,'run',t.title,'#task/'+enc(t.id)]);
  else ev.push([e,'job',t.title,'#task/'+enc(t.id)])});
 (st.decisions||[]).forEach(d=>{if(!(d.t>t0))return;
  if(d.kind==='promote'||d.kind==='champion')ev.push([d.t,'win','Champion: '+mnt(d.model),'#model/'+enc(d.model||'')]);
  else if(d.kind==='rejected')ev.push([d.t,'rej','Rejected: '+mnt(d.model),'#model/'+enc(d.model||'')]);
  else if(/^goal_/.test(d.kind))ev.push([d.t,'goal',(d.kind==='goal_open'?'Goal opened: ':'Goal: ')+(d.goal||''),'#goal/'+enc(d.goal||'')])});
 Object.values(st.papers||{}).forEach(p=>{if(p.updated>t0)ev.push([p.updated,'paper','Paper: '+(p.title||p.name),paperUrl(p)])});
 const n=k=>ev.filter(e=>e[1]===k).length;
 const tiles=[['run','Runs',n('run'),'#archive'],['win','Promoted',n('win'),'#models'],['rej','Rejected',n('rej'),'#models'],['fail','Failed',n('fail'),'#archive'],['paper','Papers',n('paper'),'#papers'],['job','Other jobs',n('job'),'#archive']].filter(x=>x[2]);
 const W=600,X0=t=>(8+(t-t0)/Math.max(1,t1-t0)*(W-16)).toFixed(1);
 const lane={win:10,goal:10,paper:10,rej:20,run:30,job:30,fail:40};
 const day=86400,ticks=(t1-t0)/day<=31?Array.from({length:Math.floor((t1-t0)/day)},(_,i)=>`<line class="tk" x1="${X0(t1-(i+1)*day)}" x2="${X0(t1-(i+1)*day)}" y1="44" y2="49"/>`).join(''):'';
 const strip=ev.length?`<svg class="sx-strip" viewBox="0 0 ${W} 50" preserveAspectRatio="none" role="img" aria-label="${ev.length} events since ${esc(stamp(t0))}"><line x1="0" x2="${W}" y1="49" y2="49" class="ax"/>${ticks}${ev.map(([t,k,l,h])=>`<a href="${esc(h)}"><rect class="${k}" x="${X0(t)}" y="${lane[k]-4}" width="3" height="8" rx="1"><title>${esc(l)} · ${esc(stamp(t))}</title></rect></a>`).join('')}</svg>
  <div class="sx-axis"><span>${since?esc(stamp(t0)):'7 days ago'}</span><span>now</span></div>`:'';
 const b=X.b,cards=b?.cards?.length;
 const brief=`<a class="sx-brief ${cards?'':'quiet'}" href="#learn">${ICON.learn}<b>Brief</b><span class="num">${b?plural(cards,'card'):'…'}</span></a>`;
 const body=ev.length?`${strip}<div class="sx-tiles">${tiles.map(([k,l,c,h])=>`<a class="sx-tile ${k}" href="${h}"><b class="num">${c}</b><span>${l}</span></a>`).join('')}</div>`:`<div class="sx-none">Nothing new</div>`;
 return panel(since?'Since you looked':'Last 7 days',body+`<div class="sx-foot">${brief}</div>`,{meta:since?ago(since):''});
}

// (5) the dashboard's map: each page, one line, a live count
function mapBlock(){
 const st=S.state,o=x=>Object.values(x||{});
 const nq=X.q?.nodes?.filter(n=>n.status==='open'||n.status==='agent').length;
 const C={overview:'',learn:X.b?.cards?String(X.b.cards.length):'',workbench:String(liveJobs().length),
  goals:String(o(st.goals).filter(g=>g.status==='open').length),questions:nq!=null?String(nq):st.questions?.needs_human?String(st.questions.needs_human):'',
  models:String(o(st.models).length),hills:String(o(st.hills).filter(h=>h.status==='open').length),papers:String(o(st.papers).length),
  slices:String(Object.keys(st.slices||{}).length),archive:String(Math.max(0,(st.tasks_total||st.tasks.length)-active().length))};
 const L={overview:'Champion and ladder',learn:'Catch up, by doing',workbench:'Jobs running',goals:'Targets, in units',questions:'Open questions',
  models:'Every candidate',hills:'Problems being climbed',papers:'Write-ups',slices:'Frozen eval sets',archive:'Finished jobs'};
 return panel('Map',`<div class="sx-map">${ROUTES.filter(([k])=>k!=='start').map(([k,l])=>`<a class="sx-pg" href="#${k}">${ICON[k]||''}<b>${l}</b><span class="sx-pc num ell">${C[k]||''}</span><span class="sx-pl">${L[k]||''}</span></a>`).join('')}</div>`);
}

VIEWS.start=()=>{
 fetchExtras();
 const st=S.state;
 return page({title:st.config?.name||'Start',crumbs:[['Start']]})+
  `<div class="sx">
   <div class="sx-a">${goalsBlock()}</div>
   <div class="sx-b">${nowBlock()}</div>
   <div class="sx-c">${needsBlock()}</div>
   <div class="sx-d">${sinceBlock()}</div>
   <div class="sx-e">${mapBlock()}</div>
  </div>`;
};
}
