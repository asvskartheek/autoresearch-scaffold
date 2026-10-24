// Overview: goal, headline tiles, pipeline (gate diagram), research record (one chart), latest activity.
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const stamp=t=>{const d=new Date(t*1000);return `${MON[d.getMonth()]} ${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`};
const FAM=['var(--blue)','var(--green)','var(--purple)','var(--amber)','var(--red)','var(--muted)'];
const famColor=(label,fams)=>FAM[fams.indexOf(label)%FAM.length];
const MIN_N=20;
const ovGoal=()=>{const g=S.state.config.final_target;return g&&typeof g==='object'?g:null};
const ovTrackName=t=>(String(t.label||'').replace(/^[^·]*·\s*/,'')||t.id).replace(/^Slice\b/,'Eval set');
const ovBest=rs=>rs.reduce((b,r)=>!b||r.score>b.score?r:b,null);
const ovRuns=id=>(S.state.runs||[]).filter(r=>r.track===id);
function ovTracks(){return (S.state.tracks||[]).filter(t=>t.n>=MIN_N)}
function ovStats(t){const rs=ovRuns(t.id);return {rs,best:ovBest(rs),last:rs.length?rs[rs.length-1]:null}}
// the track a goal is measured on: the goal dataset's track with the most variants among those with n>=50
function ovGoalTrack(){
 const g=ovGoal();if(!g)return null;
 const c=(S.state.tracks||[]).filter(t=>t.dataset===g.dataset&&t.n>=50).sort((a,b)=>b.variants-a.variants||b.n-a.n);
 return c[0]||null;
}
function ovGoalCard(){
 const g=ovGoal();if(!g)return '';
 const T=ovGoalTrack(),b=T&&ovStats(T).best;
 const acc=g.accuracy_min,lat=g.latency_p50_max_seconds;
 const meter=(label,txt,ttxt,gap,ok,frac,mark)=>`<div class="ovm"><div class="ovmh"><span class="k">${label}</span><span class="ovmv">${txt}</span></div>
  <div class="ovbar"><i class="${ok?'ok':''}" style="width:${Math.max(0,Math.min(100,frac*100)).toFixed(1)}%"></i>${mark!=null?`<u style="left:${(mark*100).toFixed(1)}%"></u>`:''}</div>
  <div class="ovmf"><span>${ttxt}</span><b class="${ok?'pos':'neg'}">${gap}</b></div></div>`;
 const parts=[];
 if(acc!=null)parts.push(meter('Accuracy',b?pct(b.score):'no run','Goal ≥ '+pct(acc),b?(b.score>=acc?'goal met':pts(b.score-acc)+' pts to goal'):'',b&&b.score>=acc,b?b.score:0,acc));
 if(lat!=null){const ok=b&&b.p50!=null&&b.p50<=lat,mx=Math.max(lat*1.6,b?.p50||0);
  parts.push(meter('End-to-end p50',b&&b.p50!=null?secs(b.p50):'no run','Goal ≤ '+secs(lat),b&&b.p50!=null?(ok?secs(lat-b.p50)+' inside':secs(b.p50-lat)+' over'):'',ok,b&&b.p50!=null?b.p50/mx:0,lat/mx))}
 return `<div class="card ovgoal"><div class="ovgh"><div><div class="k">Goal · ${esc(g.dataset||'')}</div><div class="ovgt" title="${esc(S.state.config.solver_goal||'')}">${esc(S.state.config.solver_goal||g.evidence||'')}</div></div>
  ${b?`<div class="ovgb sub" title="${esc(b.variant)}">Best lead: <a href="#task/${encodeURIComponent(b.id)}"><b>${esc(b.variant)}</b></a><br>${esc(ovTrackName(T))} · n ${T.n} · ${T.variants} variants · ${T.runs} runs</div>`:`<div class="ovgb sub">No comparable run on ${esc(g.dataset||'the goal dataset')} yet</div>`}</div>
  <div class="ovms">${parts.join('')}</div></div>`;
}
function ovTiles(){
 const st=S.state,champ=st.champion,runs=st.runs||[];
 const GT=ovGoalTrack(),T=GT||[...ovTracks()].sort((a,b)=>((b.n>=50)-(a.n>=50))||b.variants-a.variants||b.n-a.n)[0],b=T&&ovStats(T).best,g=ovGoal();
 const cr=runs.filter(r=>r.model===champ&&r.n>=MIN_N).sort((a,b)=>b.n-a.n||b.score-a.score)[0],cf=!cr&&champ?fullScore(champ):null;
 const cn=champ&&(st.models[champ]?.title||champ),hills=Object.values(st.hills);
 const nOpen=hills.filter(h=>h.status==='open').length,nUp=hills.filter(h=>h.status==='climbed').length,act=active(),stall=act.filter(t=>t.status==='stalled').length;
 const crT=cr&&(st.tracks||[]).find(t=>t.id===cr.track);
 const vs=g&&g.accuracy_min!=null&&T===GT&&b;
 return `<div class="grid g4 ovtiles">
  <a class="card tile" href="${champ?'#champion/'+encodeURIComponent(champ):'#champions'}"><div class="k">Champion</div><div class="v wrap" title="${esc(champ||'')}">${esc(cn||'None yet')}</div><div class="s">${cr?`${pct(cr.score)} on ${esc(crT?ovTrackName(crT):short(cr.slice||''))} · n ${cr.n}`:cf?`${pct(cf.score)} on ${esc(short(st.config.primary_dataset+'/full'))} · n ${cf.n}`:champ?'no scored run on record':'a model must pass every gate'}</div></a>
  <div class="card tile"><div class="k">${vs?'Best lead vs goal':'Best lead'}</div><div class="v">${b?pct(b.score):'—'}</div><div class="s">${b?`${esc(ovTrackName(T))} · n ${T.n}${vs?`<div class="${b.score>=g.accuracy_min?'pos':'neg'}">${b.score>=g.accuracy_min?'goal met':pts(b.score-g.accuracy_min)+' pts to '+pct(g.accuracy_min)}</div>`:''}`:'no scored runs yet'}</div></div>
  <div class="card tile"><div class="k">Recorded</div><div class="v">${runs.length} <small>runs</small></div><div class="s">${nOpen} hills open · ${nUp} climbed · ${Object.keys(st.models).length} models</div></div>
  <div class="card tile"><div class="k">Running now</div><div class="v">${act.length}</div><div class="s">${stall?`<span class="neg">${stall} stalled</span>`:''}${act[0]?`<div class="clamp2">${esc(act[0].title)}</div>`:'idle'}</div></div></div>`;
}

// ---- pipeline: the gates a model must pass to become champion
// candidates = models in the ladder, furthest first; stop = the first gate that is not passed and why
function ovWhy(c){
 if(!c)return '';
 if(c.state==='needs_review')return 'needs sign-off';
 if(c.state==='need_run')return 'needs a run on '+ovSetName(c.slice);
 if(c.state==='need_baseline')return 'champion needs a run on '+ovSetName(c.slice);
 if(c.state==='fail')return 'not better on '+ovSetName(c.slice);
 return c.state||'';
}
const ovSetName=s=>{const raw=String(s||'').split('/').slice(1).join('/')||String(s||'');return raw.length>24?raw.slice(0,22)+'…':raw};
function ovCandidates(){
 const st=S.state;
 return Object.entries(st.models).filter(([k,m])=>m.status==='candidate'&&st.gates[k]&&!st.gates[k].error&&(st.gates[k].rungs||[]).length)
  .map(([k,m])=>{const g=st.gates[k],rs=g.rungs,i=rs.findIndex(r=>r.status!=='pass'&&r.status!=='skipped'&&r.status!=='champion');
   const r=i>=0?rs[i]:null,chk=r&&(r.checks||[]).find(c=>c.state!=='pass'&&c.state!=='champion');
   return {name:k,title:m.title||k,hill:m.hill,gate:g,passed:rs.filter(r=>r.status==='pass').length,stop:r?{rung:r.rung,status:r.status,why:r.status==='locked'?'after the gate before':ovWhy(chk)||r.status}:null}})
  .sort((a,b)=>b.passed-a.passed);
}
// eval sets that measure one gate and have results: the ones named by the gate's checks, by the gate's name, or resolved for a candidate
function ovGateSets(rung,i,cands){
 const st=S.state,names=new Set();
 for(const c of rung.checks||[])if(c.slice&&!c.slice.startsWith('@'))names.add(c.slice);
 for(const s of Object.keys(st.slices))if(s.split('/').pop().toLowerCase()===String(rung.rung).toLowerCase())names.add(s);
 for(const c of cands)for(const k of ((c.gate.rungs||[])[i]?.checks)||[])if(k.slice)names.add(k.slice);
 return [...names].filter(s=>st.leaderboard[s]&&Object.keys(st.leaderboard[s]).length).sort((a,b)=>(st.slices[b]?.n||0)-(st.slices[a]?.n||0));
}
function ovGateNode(rung,i,cands,last){
 const st=S.state,champ=st.champion,hi=st.config.higher_is_better!==false,sign=hi?1:-1;
 const cfg=(st.config.ladder||[])[i]||{checks:[]},better=(cfg.checks||[]).find(c=>c.rule==='better'),margin=better?.margin||0;
 const manual=(cfg.checks||[]).some(c=>c.manual);
 const sets=ovGateSets(rung,i,cands),set=sets.find(s=>st.leaderboard[s][champ])||sets[0];
 const lb=set?st.leaderboard[set]:{},cr=lb[champ];
 const ch=Object.entries(lb).filter(([m,r])=>m!==champ&&r.score!=null).sort((a,b)=>sign*(b[1].score-a[1].score))[0];
 const cg=cands[0]&&(cands[0].gate.rungs||[])[i];
 let st_='',cls='';
 if(cg&&cg.status==='pass'){st_='Passed';cls='pos'}
 else if(cg&&cg.status==='fail'){st_='Failed: '+(ovWhy((cg.checks||[]).find(c=>c.state==='fail'))||'not better');cls='neg'}
 else if(cg&&cg.status==='pending'){st_=(ovWhy((cg.checks||[]).find(c=>c.state!=='pass'&&c.state!=='champion'))||'pending').replace(/^./,x=>x.toUpperCase());cls='warn'}
 else if(cg&&cg.status==='locked'){st_='Waits for the gate before'}
 else if(!set){st_=manual?'Needs sign-off':'No eval data';cls='sub'}
 else if(ch&&cr){const d=sign*(ch[1].score-cr.score);st_=d>=margin&&margin>0?'Lead clears +'+(100*margin).toFixed(0)+' pts':margin>0?'Needs +'+(100*margin).toFixed(0)+' pts, lead has '+pts(d):d>0?'Lead ahead '+pts(d)+' pts':'No lead ahead';cls=d>=margin&&d>0?'pos':'warn'}
 else st_='Needs a champion run';
 if(!st_)st_='Waiting';
 const rows=set?`<div class="ovgr"><span>Champion</span><b>${cr?pct(cr.score):'no run'}</b></div><div class="ovgr" ${ch?`data-tip='${esc(JSON.stringify([st.models[ch[0]]?.title||ch[0],pct(ch[1].score)+' · n '+(ch[1].n??'?')]))}'`:''}><span>Best</span><b>${ch?pct(ch[1].score):'no run'}</b></div><div class="ovgset sub clamp1" title="${esc(set)}">${esc(ovSetName(set))}${st.slices[set]?.n?' · n '+st.slices[set].n:''}</div>`
  :`<div class="ovgr"><span>Champion</span><b class="sub">—</b></div><div class="ovgr"><span>Best</span><b class="sub">—</b></div><div class="ovgset sub">no eval set with results</div>`;
 return `<div class="ovgate ${cg?cg.status:''}"><div class="ovgn"><i>${i+1}</i><span class="clamp1" title="${esc(rung.rung)}">${esc(rung.rung)}</span></div>${rows}<div class="ovgs ${cls}">${esc(st_)}</div></div>`;
}
function ovPipeline(inner){
 const st=S.state,ladder=st.config.ladder||[],champ=st.champion,cands=ovCandidates();
 if(!ladder.length)return inner?'':'<div class="card section"><h2>Pipeline</h2><div class="empty">No gates defined. Add a ladder to research.json.</div></div>';
 const cn=champ&&(st.models[champ]?.title||champ),top=cands[0];
 const fin=`<div class="ovgate end"><div class="ovgn"><i>★</i><span>Champion</span></div><div class="ovgr"><b class="clamp2" title="${esc(champ||'')}">${esc(cn||'None yet')}</b></div><div class="ovgset sub">${top?(top.gate.promotable?'next one is ready to promote':'next: '+esc(top.title)):'no candidate in the pipeline'}</div></div>`;
 const flow=`<div class="ovflow">${ladder.map((r,i)=>ovGateNode(r,i,cands)+'<span class="ovarr">›</span>').join('')}${fin}</div>`;
 const head=top&&top.stop?`<div class="ovnext"><span class="chip pending">blocked</span> <b class="clamp1">${esc(top.title)}</b> <span class="sub">at ${esc(top.stop.rung)}: ${esc(top.stop.why)}</span></div>`:'';
 return inner?flow+head:`<div class="card section"><h2>Pipeline<span class="r">${ladder.length} gates to champion</span></h2>${flow}${head}</div>`;
}
function ovEvents(){
 const st=S.state,ev=[],runs=Object.fromEntries((st.runs||[]).map(r=>[r.id,r])),skip=/^historical|^migration$/;
 for(const t of st.tasks||[]){if(skip.test(t.kind)||isLive(t))continue;const when=t.ended||t.updated||t.created;
  ev.push({t:when,k:t.status,txt:t.title,sub:(t.summary?.score!=null?pct(t.summary.score)+' · ':'')+t.kind+' '+t.status,href:'task/'+encodeURIComponent(t.id)})}
 for(const d of st.decisions||[]){if(d.kind==='champion'&&/seeded/.test(d.note||''))continue;
  ev.push({t:d.t,k:d.kind,txt:(d.kind==='champion'?'New champion ':d.kind==='rejected'?'Rejected ':d.kind+' ')+(st.models[d.model]?.title||d.model),sub:d.note||'',href:'model/'+encodeURIComponent(d.model)})}
 for(const t of st.tracks||[])t.frontier.forEach(f=>{const r=runs[f.id];if(r&&f.prev!=null&&t.n>=MIN_N)ev.push({t:r.t,k:'lead',txt:'New lead '+pct(r.score)+' on '+ovTrackName(t),sub:r.variant+' · n '+r.n,href:'task/'+encodeURIComponent(r.id)})});
 return ev.filter(e=>e.t).sort((a,b)=>b.t-a.t).slice(0,8);
}
function ovActivity(){
 const ev=ovEvents();
 return `<div class="card section"><h2>Latest activity</h2>${ev.length?ev.map(e=>`<a class="ovev" href="#${e.href}"><span class="chip ${e.k==='lead'||e.k==='champion'?'champion':/^(rejected|failed|abandoned|cancelled|budget)$/.test(e.k)?'rejected':'done'}">${esc(e.k)}</span><span class="ovet"><span class="clamp1" title="${esc(e.txt)}">${esc(e.txt)}</span><span class="sub clamp1">${esc(e.sub)}</span></span><span class="sub">${ago(e.t)}</span></a>`).join(''):'<div class="empty">Nothing has finished yet</div>'}</div>`;
}

// ---- research record
function ovChart(runs,front,goal){
 const W=760,H=320,L=46,R=16,T=14,B=44,n=runs.length;
 const sc=runs.map(r=>r.score),mn=Math.min(...sc),mx=Math.max(...sc,goal??0);
 const lo=Math.max(0,Math.floor((mn-.08)*20)/20),hi=Math.min(1,Math.ceil((mx+.03)*20)/20),span=Math.max(hi-lo,.1);
 const X=i=>L+(n<2?.5:i/(n-1))*(W-L-R),Y=v=>T+(1-(v-lo)/span)*(H-T-B);
 const fams=[...new Set(runs.map(r=>r.label))],step=span>.4?.1:.05;
 let g='';for(let v=Math.ceil(lo/step-1e-9)*step;v<=hi+1e-9;v+=step)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--border)"/><text x="${L-7}" y="${(Y(v)+3.5).toFixed(1)}" text-anchor="end">${Math.round(v*100)}%</text>`;
 const nt=Math.min(n,5),ticks=[...new Set(Array.from({length:nt},(_,k)=>Math.round(k*(n-1)/Math.max(1,nt-1))))];
 g+=ticks.map(i=>{const a=i===0&&ticks.length>1?'start':i===n-1&&ticks.length>1?'end':'middle';return `<text x="${X(i).toFixed(1)}" y="${H-24}" text-anchor="${a}">#${i+1}</text><text x="${X(i).toFixed(1)}" y="${H-9}" text-anchor="${a}" style="opacity:.65">(${stamp(runs[i].t)})</text>`}).join('');
 if(goal!=null)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(goal).toFixed(1)}" y2="${Y(goal).toFixed(1)}" stroke="var(--amber)" stroke-width="1.5" stroke-dasharray="6 4"/><text x="${W-R}" y="${(Y(goal)-5).toFixed(1)}" text-anchor="end" style="fill:var(--amber)">goal ${Math.round(goal*100)}%</text>`;
 const fi=runs.map((r,i)=>[r,i]).filter(([r])=>front.has(r.id));let best=null;const line=[];
 fi.forEach(([r,i],k)=>{if(k)line.push(`L${X(i).toFixed(1)} ${Y(best).toFixed(1)}`);best=r.score;line.push(`${k?'L':'M'}${X(i).toFixed(1)} ${Y(r.score).toFixed(1)}`)});
 if(fi.length)line.push(`L${X(n-1).toFixed(1)} ${Y(best).toFixed(1)}`);
 g+=`<path d="${line.join('')}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linejoin="round" opacity=".85"/>`;
 g+=runs.map((r,i)=>{const nb=front.has(r.id),cx=X(i).toFixed(1),cy=Y(r.score).toFixed(1),tip=esc(JSON.stringify([`#${i+1} · ${r.variant}`,`${pct(r.score)} · n ${r.n}${r.p50!=null?' · p50 '+secs(r.p50):''}${r.cost!=null?' · '+money(r.cost)+'/ex':''}`,stamp(r.t)+(nb?' · new best':'')+' · click to open']));
  return `<g class="ovpt" data-tip="${tip}" onclick="location.hash='task/${encodeURIComponent(r.id)}'">${nb?`<circle cx="${cx}" cy="${cy}" r="10" fill="none" stroke="var(--ink)" stroke-width="1.8"/>`:''}<circle class="d" cx="${cx}" cy="${cy}" r="${nb?5.5:4.5}" fill="${famColor(r.label,fams)}"/><circle cx="${cx}" cy="${cy}" r="12" fill="transparent"/></g>`}).join('');
 return `<svg class="ovchart" viewBox="0 0 ${W} ${H}" width="100%" role="img">${g}</svg>
  <div class="ovleg">${fams.slice(0,8).map(f=>`<span><i style="background:${famColor(f,fams)}"></i>${esc(f)}</span>`).join('')}${fams.length>8?`<span>+${fams.length-8} more</span>`:''}<span><i class="ln"></i>best so far</span><span><i class="ring"></i>new best</span>${goal!=null?'<span><i class="gl"></i>goal</span>':''}</div>`;
}

function ovRecord(){
 const all=ovTracks().filter(t=>t.runs>=2||t.id===S.track),g=ovGoal();
 if(!all.length)return '';
 const main=ovGoalTrack()||[...all].sort((a,b)=>b.runs-a.runs||b.n-a.n)[0];
 if(!S.track||!all.some(t=>t.id===S.track))S.track=main.id;
 const T=all.find(t=>t.id===S.track),runs=ovRuns(T.id),front=new Set(T.frontier.map(f=>f.id));
 const goal=g&&g.dataset===T.dataset&&g.accuracy_min!=null?g.accuracy_min:null;
 const dss=[...new Set(all.map(t=>t.dataset))].sort((a,b)=>(b===main.dataset)-(a===main.dataset)||a.localeCompare(b));
 const nm=t=>/^Eval set · \d+$/.test(ovTrackName(t))?'Unnamed':ovTrackName(t);
 const opt=t=>`<option value="${esc(t.id)}" ${t.id===T.id?'selected':''}>${esc(nm(t))} · n ${t.n} · ${t.runs} runs${t.id===main.id?' (goal)':''}</option>`;
 const sel=all.length>1?`<select class="ovsel" onchange="S.track=this.value;render()">${dss.map(d=>`<optgroup label="${esc(d)}">${all.filter(t=>t.dataset===d).sort((a,b)=>(b.id===main.id)-(a.id===main.id)||b.runs-a.runs).map(opt).join('')}</optgroup>`).join('')}</select>`:'';
 return `<div class="card section"><h2>Best score over experiments<span class="r">${sel}</span></h2>
  <p class="sub ovsub">${esc(T.dataset)} · ${esc(ovTrackName(T))} · n ${T.n} · ${T.runs} runs · best ${pct(ovBest(runs)?.score)} · ${stamp(T.first)} to ${stamp(T.last)}</p>
  ${ovChart(runs,front,goal)}</div>`;
}

function vOverview(){
 const st=S.state,champ=st.champion,ds=Object.keys(st.datasets);
 let h=topbar('Overview')+ovGoalCard()+ovTiles()+ovPipeline()+ovRecord()+ovActivity();
 if((st.tracks||[]).length||!ds.length)return h;
 // no comparable runs: the per-eval-set leaderboard
 if(!S.lbDataset||!st.datasets[S.lbDataset])S.lbDataset=st.config.primary_dataset||ds[0];
 const sl=Object.values(st.slices).filter(s=>s.dataset===S.lbDataset);
 const order={full:0,random:1,control:2,dev:3,synthetic:4};
 sl.sort((a,b)=>(order[a.kind]-order[b.kind])||(b.n-a.n));
 if(!S.lbSlice||!sl.some(s=>s.name===S.lbSlice))S.lbSlice=sl[0]?.name;
 const board=Object.entries(st.leaderboard[S.lbSlice]||{}).sort((a,b)=>(st.config.higher_is_better===false?1:-1)*((a[1].score??-1)-(b[1].score??-1)));
 const cs=board.find(([m])=>m===champ)?.[1]?.score;
 h+=`<div class="card section"><div class="tabs">${ds.map(d=>`<button class="${d===S.lbDataset?'on':''}" onclick="S.lbDataset='${esc(d)}';S.lbSlice=null;render()">${esc(st.datasets[d].title||d)}<small>${st.datasets[d].size}</small></button>`).join('')}</div>
  <div class="seg">${sl.map(s=>`<button class="${s.name===S.lbSlice?'on':''}" onclick="S.lbSlice='${esc(s.name)}';render()">${esc(short(s.name))} <span class="sub">${s.n}</span></button>`).join('')}</div>
  ${board.length?`<div class="scroll"><table><tr><th>#</th><th>Model</th><th style="width:34%">Score</th><th class="num">Δ champion</th><th class="num">Errors</th><th class="num">Cost / ex</th><th class="num">p50</th><th class="num">p95</th></tr>
  ${board.map(([m,r],i)=>`<tr class="click" onclick="location.hash='task/${encodeURIComponent(r.task)}'"><td class="sub">${i+1}</td><td><b>${esc(m)}</b> ${m===champ?'<span class="chip champion">champion</span>':''}<div class="sub">${ago(r.ended)}</div></td>
   <td><div style="display:flex;gap:12px;align-items:center"><div class="bar" style="flex:1"><i class="${m===champ?'champ':''}" style="width:${Math.max(0,Math.min(100,(r.score||0)*100))}%"></i></div><b class="num">${pct(r.score)}</b></div></td>
   <td class="num ${cs!=null&&m!==champ?(r.score>cs?'pos':r.score<cs?'neg':''):''}">${cs!=null&&m!==champ?pts(r.score-cs):''}</td><td class="num">${r.errors||0}</td><td class="num">${money(r.cost)}</td><td class="num">${secs(r.latency_p50)}</td><td class="num">${secs(r.latency_p95)}</td></tr>`).join('')}</table></div>`:'<div class="empty">No complete runs on this eval set</div>'}</div>`;
 return h;
}
