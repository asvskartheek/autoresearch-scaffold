/* overview: where does the research stand — who is champion, what is climbing, what is running, what to run next */
const ovPassed=g=>(g?.rungs||[]).filter(r=>r.status==='pass').length;
const ovFailedAt=g=>(g?.rungs||[]).find(r=>r.status==='fail')?.rung;
const ovN=n=>n==null?'—':Number(n).toLocaleString();
const ovList=a=>a.length<2?a.join(''):a.slice(0,-1).join(', ')+' and '+a.at(-1);
// the line under a model's name: its own short title, else the first sentence of its change
const ovAbout=(k,m)=>m?.title&&m.title!==k?m.title:firstLine(m?.change||'');
const ovRungs=()=>{const st=S.state;return (st.config.ladder||[]).map(r=>r.rung).filter(Boolean).length?st.config.ladder.map(r=>r.rung):(Object.values(st.gates).find(g=>g.rungs?.length)?.rungs||[]).map(r=>r.rung)};
const ovKind={full:'Full set',random:'Random sample',control:'Control',dev:'Development',synthetic:'Synthetic'};
// what a candidate needs next, as [label html, command to copy, cls]
function ovNextOf(k,g){
 const nx=g.next||[],f=ovFailedAt(g);
 if(g.promotable)return ['Promote',`arx promote ${k}`,'pos'];
 if(f)return [`Failed ${esc(f)}`,`arx reject ${k} --reason "failed the ${f} rung"`,'neg'];
 if(nx.length)return [`<span class="mono" title="${esc(nx.map(x=>short(x.slice)).join(', '))}">${esc(short(nx[0].slice))}</span>`,`arx gate ${k}`,''];
 return ['',`arx gate ${k}`,''];
}
function ovSortBy(k){const s=S.ovSort||{k:'score',d:-1};S.ovSort={k,d:s.k===k?-s.d:(k==='ended'||k==='score'?-1:1)};render()}
function ovPickSlice(name){S.lbSlice=name;S.ovLbAll=false;render()}

VIEWS.overview=()=>{
 const st=S.state,champ=st.champion,ds=Object.keys(st.datasets),hib=st.config.higher_is_better!==false;
 const prim=st.config.primary_dataset||ds[0],fullKey=prim+'/full';
 const cf=champ&&fullScore(champ);
 const cands=Object.entries(st.models).filter(([,m])=>m.status==='candidate')
  .map(([k,m])=>[k,m,st.gates[k]||{}])
  .sort((a,b)=>(b[2].promotable-a[2].promotable)||(!!ovFailedAt(a[2])-!!ovFailedAt(b[2]))||(ovPassed(b[2])-ovPassed(a[2]))||((b[1].created||0)-(a[1].created||0)));
 const live=active(),stalled=live.filter(t=>t.status==='stalled'),running=live.filter(t=>t.status!=='stalled');
 const hills=Object.values(st.hills),open=hills.filter(h=>h.status==='open').length,climbed=hills.filter(h=>h.status==='climbed').length;
 const promotable=cands.filter(c=>c[2].promotable),failed=cands.filter(c=>ovFailedAt(c[2])),onWay=cands.filter(c=>ovPassed(c[2])&&!ovFailedAt(c[2]));
 const lead=promotable[0]||cands.find(c=>!ovFailedAt(c[2]));

 // the finding: said the way a lead would say it in stand-up
 let finding,nextCmd='';
 if(!champ)finding='There is no champion yet. Register a baseline with <code>arx model add &lt;name&gt; --champion</code>; every candidate is gated against it.';
 else{
  const p=[`<b>${esc(champ)}</b> is champion${cf?` at ${pct(cf.score)} on ${esc(short(fullKey))} (${ovN(solved(cf))} of ${ovN(cf.n)})`:`, with no run on ${esc(short(fullKey))} yet`}.`];
  if(promotable.length)p.push(`<b>${esc(promotable[0][0])}</b> passed every rung and is ready to promote.`);
  else if(lead){
   const g=lead[2],done=(g.rungs||[]).filter(r=>r.status==='pass').map(r=>esc(r.rung)),nx=g.next?.[0];
   if(done.length)p.push(`<b>${esc(lead[0])}</b> is closest: it passed ${ovList(done)}${nx?` and needs a run on ${esc(short(nx.slice))}`:''}.`);
   else p.push(`No candidate has passed a rung yet${failed.length?`; ${failed.length} failed one`:''}. Next up is <b>${esc(lead[0])}</b>${nx?` on ${esc(short(nx.slice))}`:''}.`);
  }else if(cands.length)p.push(`All ${plural(cands.length,'candidate')} failed a rung; reject them or register a new one.`);
  else p.push('No candidate is climbing.');
  if(stalled.length)p.push(`<span class="neg">${stalled.length===1?'1 task has':stalled.length+' tasks have'} stopped reporting.</span>`);
  finding=p.join(' ');
  if(lead)nextCmd=ovNextOf(lead[0],lead[2])[1];
 }
 let h=page({title:'Overview',crumbs:[['Overview','#overview']],finding,
  acts:`${nextCmd?`<span class="ov-next-cmd" title="Run this next">${cmd(nextCmd)}</span>`:''}${champ?`<a class="btn" href="#model/${enc(champ)}">Open champion</a>`:''}`});

 // KPIs: the champion's score leads; the rest are counts of what is in motion
 const goal=st.config.goal;
 h+=`<div class="ov-kpis">${kpis([
  ['Champion',cf?pct(cf.score):DASH,champ?`<a href="#model/${enc(champ)}" class="ov-cn">${esc(champ)}</a>${cf?` · ${esc(short(fullKey))}, n ${ovN(cf.n)}`:''}${goal?.target!=null?` · target ${pct(goal.target)}`:''}`:'No champion yet'],
  ['Candidates',String(cands.length),promotable.length?`<span class="pos">${promotable.length} ready to promote</span>`:cands.length?`${onWay.length} passed a rung · ${failed.length} failed one`:'None registered','#models'],
  ['Running',String(live.length),stalled.length?`<span class="neg">${stalled.length} not reporting</span>`:live.length?'All reporting':'Nothing running','#workbench'],
  ['Open hills',String(open),`${climbed} climbed · ${hills.length} in all`,'#hills'],
 ])}</div>`;

 // the ladder: one column per rung, so each name is said once in the header and the track reads across
 const RUNGS=ovRungs(),CAP=6;
 const ladderRows=cands.slice(0,CAP).map(([k,m,g])=>{
  const by=Object.fromEntries((g.rungs||[]).map(r=>[r.rung,r.status]));
  const [lbl,c,cls]=ovNextOf(k,g),about=ovAbout(k,m);
  const word={pass:'passed',fail:'failed',pending:'next',locked:'locked',champion:'champion'};
  const cells=RUNGS.map((r,i)=>{const s=by[r]||'locked';return `<td class="ov-rg ${esc(s)} ${i&&by[RUNGS[i-1]]==='pass'?'in':''} ${i<RUNGS.length-1&&s==='pass'?'out':''} ${i?'':'first'} ${i===RUNGS.length-1?'last':''}"><i title="${esc(r)}: ${word[s]||esc(s)}"></i></td>`}).join('');
  return `<tr class="click" onclick="location.hash='model/${enc(k)}'"><td class="ov-id"><div class="two"><a class="ell ov-nm" href="#model/${enc(k)}" title="${esc(k)}">${esc(k)}</a>${about?`<span class="sub ell" title="${esc(m.change||about)}">${esc(about)}</span>`:''}</div></td>
   ${cells}<td class="ov-nx"><span class="ov-nxw"><span class="ell ${cls}">${lbl||DASH}</span>${copyBtn(c)}</span></td></tr>`;
 });
 const ladderCard=panel('Ladder',cands.length?`<div class="ov-ladtbl">${table(['Candidate',...RUNGS.map(r=>[`<span class="ov-rgh">${esc(r)}</span>`,'ov-rg']),['<span class="ov-nxh">Next run</span>','ov-nx']],ladderRows)}</div>`:
  empty('No candidates climbing',`<p>Register one, then ask the gate for its first run.</p>${cmd('arx model add <name> --hill <hill> --change "…"')}`),
  {meta:champ?`against ${esc(champ)}`:'',right:cands.length>CAP?`<a class="more" href="#models">View all ${cands.length}</a>`:''});

 // running now: stalled work grouped under one mark, so the warning is said once
 const RC=6;
 const trow=t=>{
  const pr=t.progress||{},f=pr.total?pr.done/pr.total:null,sl=t.stalled||t.status==='stalled';
  const nm=t.kind==='eval'&&t.model?t.model:t.title;
  const what=t.kind==='eval'&&t.slice?esc(short(t.slice)):esc(t.kind||'task');
  const meta=sl?`${what} · silent ${dur(t.heartbeat||t.updated||t.created)}`:t.note?esc(t.note.text??t.note.msg??''):`${what} · started ${ago(t.created)}${t.eta?` · ${left(t.eta.eta_s)} left`:''}`;
  return `<div class="ov-task"><a class="ov-tl" href="#task/${enc(t.id)}" title="${esc(t.title)}"><span class="ell">${esc(nm)}</span><span class="ov-tv">${pr.total?`${ovN(pr.done)}<span class="faint"> / ${ovN(pr.total)}</span>`:dur(t.created)}</span></a>
   ${f!=null?meter(f,{cls:sl?'muted':''}):''}<div class="ov-tm"><span class="ell">${meta}</span>${sl?copyBtn(`arx task finish ${t.id} --status failed`):''}</div></div>`;
 };
 const grp=(label,list,cls,n)=>list.length?`<div class="ov-grp ${cls}"><span>${label}</span><span class="faint">${list.length}</span></div>${list.slice(0,n).map(trow).join('')}`:'';
 const byNew=(a,b)=>b.created-a.created;
 const showRun=Math.min(running.length,RC),showSt=Math.max(0,RC-showRun);
 const runCard=panel('Running',live.length?`<div class="ov-run">${grp('Running',running.sort(byNew),'',showRun)}${grp('Not reporting for 10+ minutes',stalled.sort(byNew),'neg',showSt)}</div>`:
  empty('Nothing running',`<p>Start work as a task so it shows here.</p>${cmd('arx task start --title "…"')}`),
  {meta:live.length?plural(live.length,'task'):'',right:live.length>RC?`<a class="more" href="#workbench">View all ${live.length}</a>`:''});
 h+=`<div class="grid ov-row">${ladderCard}${runCard}</div>`;

 // leaderboard: dataset tabs, slice control, paired deltas vs the champion on the same slice
 if(!S.lbDataset||!st.datasets[S.lbDataset])S.lbDataset=prim;
 const sl=Object.values(st.slices).filter(s=>s.dataset===S.lbDataset);
 const order={full:0,random:1,control:2,dev:3,synthetic:4};
 sl.sort((a,b)=>((order[a.kind]??9)-(order[b.kind]??9))||(b.n-a.n)||a.name.localeCompare(b.name));
 if(!S.lbSlice||!sl.some(s=>s.name===S.lbSlice))S.lbSlice=(sl.find(s=>st.leaderboard[s.name])||sl[0])?.name;
 const entries=Object.entries(st.leaderboard[S.lbSlice]||{});
 const rank=new Map([...entries].sort((a,b)=>(hib?-1:1)*((a[1].score??-1)-(b[1].score??-1))).map(([m],i)=>[m,i+1]));
 const so=S.ovSort||{k:'score',d:-1},key={score:r=>r.score,delta:r=>r.score,errors:r=>r.errors??0,cost:r=>r.cost,p50:r=>r.latency_p50,p95:r=>r.latency_p95,n:r=>r.n,ended:r=>r.ended}[so.k]||(r=>r.score);
 const board=[...entries].sort((a,b)=>{const x=key(a[1]),y=key(b[1]);if(x==null&&y==null)return rank.get(a[0])-rank.get(b[0]);if(x==null)return 1;if(y==null)return -1;return so.d*(x-y)||rank.get(a[0])-rank.get(b[0])});
 const cs=st.leaderboard[S.lbSlice]?.[champ]?.score;
 const cur=sl.find(s=>s.name===S.lbSlice);
 const has=f=>entries.some(([,r])=>r[f]!=null);
 const hasCost=has('cost'),hasLat=has('latency_p50'),hasP95=has('latency_p95');
 const LB=10,shown=S.ovLbAll?board:board.slice(0,LB);
 const tabs=`<div class="tabs ov-tabs" role="tablist">${ds.map(d=>`<button role="tab" aria-selected="${d===S.lbDataset}" class="${d===S.lbDataset?'on':''}" onclick="S.lbDataset=${esc(JSON.stringify(d))};S.lbSlice=null;S.ovLbAll=false;render()">${esc(d)}<small>${ovN(st.datasets[d].size)}</small></button>`).join('')}</div>`;
 const opt=s=>`<option value="${esc(s.name)}" ${s.name===S.lbSlice?'selected':''}>${esc(short(s.name))} · n ${ovN(s.n)}${st.leaderboard[s.name]?` · ${plural(Object.keys(st.leaderboard[s.name]).length,'model')}`:' · no runs'}</option>`;
 const kinds=[...new Set(sl.map(s=>s.kind))];
 const sel=`<label class="ov-pickl"><span>Slice</span><select class="ov-sel" onchange="ovPickSlice(this.value)">${kinds.map(k=>`<optgroup label="${esc(ovKind[k]||k)}">${sl.filter(s=>s.kind===k).map(opt).join('')}</optgroup>`).join('')}</select></label><span class="faint ov-pickn">${plural(sl.length,'slice')}</span>`;
 const pick=sl.length>7?sel:`<div class="ov-pick-s">${sel}</div><div class="seg ov-hide-s" role="tablist" aria-label="Slice">${sl.map(s=>`<button role="tab" aria-selected="${s.name===S.lbSlice}" class="${s.name===S.lbSlice?'on':''}" onclick="ovPickSlice(${esc(JSON.stringify(s.name))})">${esc(short(s.name))}<small>${ovN(s.n)}</small></button>`).join('')}</div>`;
 const sh=(label,k,cls)=>[`<button class="ov-sort ${so.k===k?'on':''}" onclick="ovSortBy('${k}')" aria-label="Sort by ${esc(label.replace(/<span class="ov-show-s">[^<]*<\/span>/g,'').replace(/<[^>]+>/g,''))}">${label}${so.k===k?`<span class="ov-arr">${so.d<0?'↓':'↑'}</span>`:''}</button>`,cls];
 const rows=shown.map(([m,r])=>{
  const d=cs!=null&&r.score!=null?r.score-cs:null;
  const good=d!=null&&d!==0&&(hib?d>0:d<0)?'pos':'';
  const about=ovAbout(m,st.models[m]);
  return `<tr class="click" onclick="location.hash='task/${enc(r.task)}'"><td class="num faint ov-rank">${rank.get(m)}</td>
   <td class="ov-id"><div class="two"><span class="row"><a class="ell ov-nm" href="#model/${enc(m)}" onclick="event.stopPropagation()" title="${esc(about||m)}">${esc(m)}</a>${m===champ?`<span class="ov-hide-s">${pill('champion','champion')}</span>`:''}</span><span class="sub ell ov-show-s">${m===champ?'Champion · ':''}n ${ovN(r.n)}${r.errors?' · '+plural(r.errors,'error'):''}</span></div></td>
   <td class="ov-bar ov-hide-s">${meter(r.score,{cls:m===champ?'':'muted'})}</td>
   <td class="num"><b class="ov-sc">${pct(r.score)}</b></td>
   <td class="num ov-hide-s">${ovN(r.n)}</td>
   <td class="num ${good} ${d===0||d==null?'faint':''}">${d==null?DASH:d===0?'0.0':pts(d)}</td>
   <td class="num ov-hide-s ${r.errors?'':'faint'}">${ovN(r.errors??0)}</td>
   ${hasCost?`<td class="num ov-hide-m">${r.cost==null?DASH:money(r.cost)}</td>`:''}
   ${hasLat?`<td class="num ov-hide-m">${r.latency_p50==null?DASH:secs(r.latency_p50)}</td>`:''}${hasP95?`<td class="num ov-hide-m">${r.latency_p95==null?DASH:secs(r.latency_p95)}</td>`:''}
   <td class="num ov-hide-m faint">${ago(r.ended)}</td></tr>`});
 const head=[['<span class="sr">Rank</span>','num'],'Model',['<span class="sr">Score bar</span>','ov-bar ov-hide-s'],sh('Score','score','num'),sh('n','n','num ov-hide-s'),sh(`<span class="ov-hide-s">vs champion, pts</span><span class="ov-show-s">Δ pts</span>`,'delta','num'),sh('Errors','errors','num ov-hide-s'),
  ...(hasCost?[sh('Cost / example','cost','num ov-hide-m')]:[]),...(hasLat?[sh('p50','p50','num ov-hide-m')]:[]),...(hasP95?[sh('p95','p95','num ov-hide-m')]:[]),sh('Ran','ended','num ov-hide-m')];
 const meta=cur?`${esc(ovKind[cur.kind]||cur.kind)} · ${ovN(cur.n)} examples${cs==null&&champ&&board.length?' · no champion run here':''}`:'';
 h+=`<section class="card section ov-lb" id="ov-lb"><div class="ph"><h2>Leaderboard</h2><span class="meta">${meta}</span>${cur?`<span class="r"><a class="more" href="#slices/${enc(cur.name)}">View slice</a></span>`:''}</div>${tabs}<div class="ov-pick">${sl.length?pick:''}</div>
  ${board.length?table(head,rows)+(board.length>LB?`<button class="btn ov-all" onclick="S.ovLbAll=!S.ovLbAll;render()">${S.ovLbAll?'Show top '+LB:'Show all '+board.length+' models'}</button>`:'')
  :empty(sl.length?'No complete runs on this slice':'No slices in this dataset',sl.length?`<p>Ask the gate which model runs next.</p>${cmd('arx gate <model>')}`:`<p>Freeze one for this dataset.</p>${cmd(`arx slice add ${S.lbDataset}/<name> --ids-file ids.txt`)}`)}</section>`;
 if(S.ovJump){S.ovJump=false;setTimeout(()=>document.getElementById('ov-lb')?.scrollIntoView({block:'start'}),0)}
 return h;
};
