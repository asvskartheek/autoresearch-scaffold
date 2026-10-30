'use strict';
/* overview: where the research stands, at a glance: the goals as distance to target, the ladder, what runs, the board */
// A concrete measurement command names the requested slice, even outside the gate ladder.
const goalMeasureCmd=g=>{
 const quote=x=>"'"+String(x).replaceAll("'", "'\"'\"'")+"'";
 const template=S.state.config.baseline_cmd;
 return template?template.replaceAll('{model}',quote(g.model||S.state.champion)).replaceAll('{slice}',quote(g.slice)):
 `arx eval record --model ${quote(g.model||S.state.champion)} --slice ${quote(g.slice)} --rows <rows.jsonl>`;
};
const distinctModel=k=>{const title=S.state.models[k]?.title;return mn(k)+(title&&Object.values(S.state.models).filter(m=>m.title===title).length>1?` <span class="sub">(${esc(k)})</span>`:'')};
const boardHarnessMismatch=(a,b)=>a?.baseline_contract!=null&&b?.baseline_contract!=null&&JSON.stringify(a.baseline_contract)!==JSON.stringify(b.baseline_contract);
const ovPassed=g=>(g?.rungs||[]).filter(r=>r.status==='pass').length;
const ovFailedAt=g=>(g?.rungs||[]).find(r=>r.status==='fail')?.rung;
const ovN=n=>n==null?'—':Number(n).toLocaleString();
// the line under a model's name (the name is its title): its id when the title differs, else its change
const ovAbout=(k,m)=>m?.title&&m.title!==k?k:firstLine(m?.change||'');
// a slice scores 0/1 per example unless it says otherwise (scale: continuous, optional unit): then no %, no solved / n
const ovBin=sl=>sl?.scale!=='continuous';
const ovVal=(v,sl)=>v==null?'—':(Math.abs(v)>=10?v.toFixed(1):num(v,3))+(sl?.unit?' '+sl.unit:'');
const ovScore=(v,sl)=>ovBin(sl)?pct(v):esc(ovVal(v,sl));
const ovDelta=(d,sl)=>d==null?'—':ovBin(sl)?pts(d):(d>0?'+':d<0?'−':'')+esc(ovVal(Math.abs(d),sl));
const ovRunning=(m,s)=>active().some(t=>t.kind==='eval'&&t.model===m&&t.slice===s);
// a gate's next run that is already running (the server sets n.running to its task): the live task, and a chip with
// its progress that links to it. Shared by the model, hill and goal views, which load after this file.
// Keep stalled attempts visible; their unfinished scope requires recovery.
const runTask=n=>{if(!n?.running)return null;const t=S.state.tasks.find(t=>t.id===n.running)||{id:n.running};return t};
const runChip=n=>{const t=runTask(n);if(!t)return '';const pr=t.progress||{},sl=t.status==='stalled';
 return `<a class="runchip" href="#task/${enc(t.id)}" onclick="event.stopPropagation()" title="${esc(t.title||'Open the running task')}"><span class="st ${sl?'stalled':'running'}">${sl?'silent '+span(now()-(t.heartbeat||t.updated||t.created)):'running'}</span>${pr.total?`<span class="num">${ovN(pr.done)}<span class="faint"> / ${ovN(pr.total)}</span></span>`:''}</a>`};
// a candidate the champion was built on (in its lineage), or whose every +-part the champion already carries
// (po4+verify under po4+verify+inv+…): superseded, so it is not climbing and never a next step.
// Shared by the goal view, which loads after this file.
const superseded=k=>{const st=S.state,ch=st?.champion;if(!ch||k===ch)return false;
 for(let c=st.models[ch]?.parent,seen=new Set([ch]);c&&!seen.has(c);seen.add(c),c=st.models[c]?.parent)if(c===k)return true;
 const a=String(k).split('+'),C=new Set(String(ch).split('+'));return a.length>1&&a.every(x=>C.has(x))};
const ovRungs=()=>{const st=S.state;return (st.config.ladder||[]).map(r=>r.rung).filter(Boolean).length?st.config.ladder.map(r=>r.rung):(Object.values(st.gates).find(g=>g.rungs?.length)?.rungs||[]).map(r=>r.rung)};
// a task silent for more than a day is dead: not running, not a live card, one line
const ovDead=t=>t.status==='stalled'&&now()-(t.heartbeat||t.updated||t.created)>86400;
const ovTask=t=>{
 const pr=t.progress||{},f=pr.total?pr.done/pr.total:null,sl=t.status==='stalled';
 const nm=t.kind==='eval'&&t.model?`${mn(t.model)}${t.slice?`<span class="faint"> · ${esc(short(t.slice))}</span>`:''}`:esc(t.title);
 const v=sl?`<span class="neg">silent ${span(now()-(t.heartbeat||t.updated||t.created))}</span>`:pr.total?`${ovN(pr.done)}<span class="faint"> / ${ovN(pr.total)}</span>`:dur(t.created);
 return `<a class="ov-task ${sl?'stalled':''}" href="#task/${enc(t.id)}" title="${esc(t.title)}"><span class="ov-tl"><span class="ell">${nm}</span><span class="ov-tv">${v}</span></span>${f!=null?meter(f,{cls:sl?'muted':''}):''}</a>`;
};
// one open goal: where the champion stands on the way from the baseline to the target, in the goal's units
const ovGoal=g=>{
 const U=window.GoalUnits,P=U.prog(g),d=U.dist(g),met=g.met;
 const {f,mark}=U.bar(g);  // the goal page's encoding: a met ≤ goal shows its headroom left of the target tick
 const fig=d?(d.short?`<b class="neg">${d.v}</b> <span class="faint">${d.s}</span>`:`<b class="pos">Met</b> <span class="faint">${d.s}</span>`):'<span class="faint">not run yet</span>';
 const now=g.value==null?DASH:`${U.gu(g,g.value)}${U.ofP(g)}`;
 const base=P.b!=null&&P.mode==='rel'?`<span>Baseline ${U.gu(g,P.b)}</span>`:'<span></span>';
 return `<a class="ov-goal ${U.isMain(g)?'':'ov-sub'}" href="#goal/${enc(g.name)}">
  <span class="ov-gh"><span class="ell ov-gt">${esc(g.title||g.name)}</span><span class="ov-gd num">${fig}</span></span>
  <span class="ov-gb"><span class="ov-trk ${met?'met':''}"><i style="width:${(100*f).toFixed(1)}%"></i>${mark!=null?`<b style="left:${(100*mark).toFixed(1)}%"></b>`:''}</span>${ovSpark(g)}</span>
  <span class="ov-ge num">${base}<span>Now <b>${now}</b></span><span>Target ${U.cmpSym(g)}&nbsp;${U.gt(g)}</span></span></a>`;
};
// the best run on the goal slice over time, as a step, with the target dashed
const ovSpark=g=>{
 const U=window.GoalUnits,k=U.kpiKey(g),s=U.sgn(g),runs=U.slRuns(g);
 if(runs.length<2)return '';
 const D=v=>U.disp(g,v),W=160,H=32,ys=runs.map(r=>D(r.summary[k])).concat([D(g.target)]);
 if(!ys.every(isFinite))return '';
 const lo=Math.min(...ys),hi=Math.max(...ys),sp=(hi-lo)||1,x0=runs[0].ended,xs=(runs.at(-1).ended-x0)||1;
 const X=t=>2+(t-x0)/xs*(W-4),Y=v=>H-3-(D(v)-lo)/sp*(H-6);
 let best=null,p='';runs.forEach(r=>{const v=r.summary[k];if(best==null||s*(v-best)>0){p+=p?`H${X(r.ended).toFixed(1)}V${Y(v).toFixed(1)}`:`M${X(r.ended).toFixed(1)} ${Y(v).toFixed(1)}`;best=v}});p+=`H${W-2}`;
 return `<svg class="ov-spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="best run on ${esc(g.slice)} over time"><line x1="0" x2="${W}" y1="${Y(g.target).toFixed(1)}" y2="${Y(g.target).toFixed(1)}" stroke="var(--chart-3)" stroke-dasharray="3 3"/><path d="${p}" fill="none" stroke="var(--chart-1)" stroke-width="1.6"/></svg>`;
};
const ovKind={full:'Full set',random:'Random sample',control:'Control',dev:'Development',synthetic:'Synthetic'};
// what a candidate needs next, as [label html, command to copy, cls]
function ovNextOf(k,g){
 const nx=g.next||[],f=ovFailedAt(g);
 if(g.promotable)return ['Promote',`arx promote ${k}`,'pos'];
 if(f)return [`Failed ${esc(f)}`,`arx reject ${k} --reason "failed the ${f} rung"`,'neg'];
 const r=nx.find(runTask);
 if(r)return [runChip(r),`arx gate ${k}`,''];
 // who runs next, as on the model page chip: the champion's baseline or this candidate
 if(nx.length)return [`<span title="${esc(nx.map(x=>(x.model!==k?'champion':'this model')+' on '+short(x.slice)).join(', '))}"><span class="faint">${nx[0].model!==k?'champion':'this'} on </span><span class="mono">${esc(short(nx[0].slice))}</span></span>`,`arx gate ${k}`,''];
 if(!g.champion&&!S.state.champion)return ['<span class="faint">needs a champion</span>','',''];
 return ['',`arx gate ${k}`,''];
}
// what tells one model from others shown under the same name: the parts of its id the others do not share
// (thinking4b-numeric32768-v1 vs thinking4b-numeric8192-v1 reads numeric32768)
function ovTell(k,others){
 const T=x=>String(x).split(/([-_+.])/),a=T(k),bs=others.map(T);
 let i=0;while(i<a.length&&bs.every(b=>b[i]===a[i]))i++;
 let j=0;while(j<a.length-i&&bs.every(b=>b.length-j>i&&b[b.length-1-j]===a[a.length-1-j]))j++;
 return a.slice(i,a.length-j).join('').replace(/^[-_+.]+|[-_+.]+$/g,'')||k;
}
function ovSortBy(k){const s=S.ovSort||{k:'score',d:-1};S.ovSort={k,d:s.k===k?-s.d:(k==='ended'||k==='score'?-1:1)};render()}
function ovPickSlice(name){S.lbSlice=name;S.ovLbAll=false;render()}

VIEWS.overview=()=>{
 // datasets: the configured ones plus any a frozen slice names (a project whose research.json lists none still has slices)
 const st=S.state,champ=st.champion,ds=[...new Set([...Object.keys(st.datasets||{}),...Object.values(st.slices).map(s=>s.dataset).filter(Boolean)])],hib=st.config.higher_is_better!==false;
 const prim=st.config.primary_dataset||ds[0],fullKey=prim+'/full';
 const cf=champ&&fullScore(champ);
 const allC=Object.entries(st.models).filter(([,m])=>m.status==='candidate'),sup=allC.filter(([k])=>superseded(k)).length;
 const cands=allC.filter(([k])=>!superseded(k))
  .map(([k,m])=>[k,m,st.gates[k]||{}])
  .sort((a,b)=>(b[2].promotable-a[2].promotable)||(!!ovFailedAt(a[2])-!!ovFailedAt(b[2]))||(ovPassed(b[2])-ovPassed(a[2]))||((b[1].created||0)-(a[1].created||0)));
 // research work only: answer agents are not research, and a task silent for over a day is dead, not running
 // a harness sub-task whose count its eval already shows (detail_of) is the same job, listed once
 const work=active().filter(t=>t.kind!=='answer'&&!t.detail_of);
 const dead=work.filter(ovDead),stalled=work.filter(t=>t.status==='stalled'&&!ovDead(t)),running=work.filter(t=>t.status!=='stalled');
 const hills=Object.values(st.hills),open=hills.filter(h=>h.status==='open').length,climbed=hills.filter(h=>h.status==='climbed').length;
 const promotable=cands.filter(c=>c[2].promotable),failed=cands.filter(c=>ovFailedAt(c[2])),onWay=cands.filter(c=>ovPassed(c[2])&&!ovFailedAt(c[2]));
 const bl=st.baseline;
 let h=page({title:'Overview',crumbs:[['Overview','#overview']],finding:champ?'':'No champion yet.',
  acts:champ?`<a class="btn" href="#model/${enc(champ)}">Open champion</a>`:''});

 // with no run on the full slice, the champion reads by the first main goal it has a value on
 const GU=window.GoalUnits,gs=GU?Object.values(st.goals||{}).filter(g=>g.status==='open').sort((a,b)=>GU.isMain(b)-GU.isMain(a)||(a.created||0)-(b.created||0)):[];
 const cg=!cf&&champ&&gs.find(g=>GU.isMain(g)&&g.model===champ&&g.value!=null);
 h+=`<div class="ov-kpis">${kpis([
  ['Champion',cf?sv(fullKey,cf.score,cf.n):cg?`${GU.gu(cg,cg.value)}${GU.ofP(cg)}`:DASH,champ?`<a href="#model/${enc(champ)}" class="ov-cn" title="${mnt(champ)}">${mn(champ)}</a>${cf?` · ${esc(short(fullKey))}`:cg?` · ${esc(short(cg.slice))}`:''}`:'No champion yet'],
  ['Candidates',String(cands.length),(promotable.length?`<span class="pos">${promotable.length} ready to promote</span>`:cands.length?`${onWay.length} passed a rung · ${failed.length} failed`:'None')+(sup?` · ${sup} superseded`:''),'#models'],
  ['Running',String(running.length),stalled.length?`<span class="neg">${stalled.length} stalled</span>`:running.length?'All reporting':'Nothing running','#workbench'],
  ['Open hills',String(open),`${climbed} climbed`,'#hills'],
 ])}</div>`;

 // goals first: each open goal as its distance to target, in units, with the best run on its slice over time
 if(gs.length)h+=panel(term('goal','Goals'),`<div class="ov-gl">${gs.map(ovGoal).join('')}</div>`,{cls:'section ov-goals',right:'<a class="more" href="#goals">View goals</a>'});

 // the ladder: one column per rung, so each name is said once in the header and the track reads across
 const RUNGS=ovRungs(),CAP=6,seen=cands.slice(0,CAP).map(([k])=>mnt(k));
 const ladderRows=cands.slice(0,CAP).map(([k,m,g],i)=>{
  const twin=cands.slice(0,CAP).filter(([o],j)=>j!==i&&seen[j]===seen[i]).map(([o])=>o),tag=twin.length?ovTell(k,twin):'';
  const by=Object.fromEntries((g.rungs||[]).map(r=>[r.rung,r.status]));
  const [lbl,,cls]=ovNextOf(k,g);
  const word={pass:'passed',fail:'failed',pending:'next',locked:'locked',champion:'champion'};
  const cells=RUNGS.map((r,i)=>{const s=by[r]||'locked';return `<td class="ov-rg ${esc(s)} ${i&&by[RUNGS[i-1]]==='pass'?'in':''} ${i<RUNGS.length-1&&s==='pass'?'out':''} ${i?'':'first'} ${i===RUNGS.length-1?'last':''}"><i title="${esc(r)}: ${word[s]||esc(s)}"></i></td>`}).join('');
  return `<tr class="click" onclick="location.hash='model/${enc(k)}'"><td class="ov-id"><span class="ov-nmr"><a class="${m.title?'ell ':'ov-pid mono '}ov-nm" href="#model/${enc(k)}" title="${esc(m.change||k)}">${m.title?mn(k):esc(k).replace(/\+/g,'+<wbr>')}</a>${tag?`<span class="mono ov-tell" title="${esc(k)}">${esc(tag)}</span>`:''}</span></td>
   ${cells}<td class="ov-nx"><span class="ell ${cls}">${lbl||DASH}</span></td></tr>`;
 });
 const lg=`<div class="ov-lg">${[['pass','passed'],['fail','failed'],['pending','next'],['locked','locked']].map(([c,l])=>`<span class="ov-rg ${c}"><i></i>${l}</span>`).join('')}${sup?`<a class="faint" href="#models">${sup} superseded by the champion</a>`:''}</div>`;
 const ladderCard=panel(term('ladder','Ladder'),cands.length?`<div class="ov-ladtbl">${table([term('candidate','Candidate'),...RUNGS.map(r=>[`<span class="ov-rgh">${esc(r)}</span>`,'ov-rg']),['<span class="ov-nxh">Next</span>','ov-nx']],ladderRows)}</div>${lg}`:
  empty('No candidates climbing',''),
  {meta:champ?`each candidate vs ${st.models[champ]?.title?`champion ${mn(champ)}`:`<a class="ln" href="#model/${enc(champ)}" title="${esc(champ)}">the champion</a>`}`:'',right:cands.length>CAP?`<a class="more" href="#models">All ${cands.length}</a>`:''});

 // running now: one compact row each; stalled rows marked; work dead for over a day is one line, not a card
 const RC=6,byNew=(a,b)=>b.created-a.created;
 const trows=[...running.sort(byNew),...stalled.sort(byNew)].slice(0,RC).map(ovTask).join('');
 const deadLine=dead.length?`<a class="ov-dead" href="#workbench">${plural(dead.length,'task')} silent for over a day</a>`:'';
 const runCard=panel('Running',running.length||stalled.length?`<div class="ov-run">${trows}</div>${deadLine}`:empty('Nothing running','')+deadLine,
  {meta:running.length+stalled.length>RC?`${RC} of ${running.length+stalled.length}`:'',right:'<a class="more" href="#workbench">Workbench</a>'});
 h+=`<div class="grid ov-row">${ladderCard}${runCard}</div>`;

 // the champion's baseline: the slices it has no run on yet, as chips
 if(champ&&bl?.need?.length){
  const nr=Object.keys(bl.roles).length;
  h+=panel(`${term('champion','Champion')} baseline`,`<div class="ov-bchips">${bl.need.map(s=>`<a class="ov-bchip ${ovRunning(champ,s)?'run':''}" href="#slices/${enc(s)}" title="${esc(s)}">${esc(short(s))}<span class="faint"> ${ovN(st.slices[s]?.n)}</span></a>`).join('')}</div>`,
   {meta:`${bl.need.length} of ${plural(nr,'slice')} not run`,cls:'section ov-base'});
 }

 // leaderboard: dataset tabs, slice control, paired deltas vs the champion on the same slice
 if(!S.lbDataset||!ds.includes(S.lbDataset))S.lbDataset=ds.includes(prim)?prim:ds[0];
 const sl=Object.values(st.slices).filter(s=>s.dataset===S.lbDataset);
 const order={full:0,random:1,control:2,dev:3,synthetic:4};
 sl.sort((a,b)=>((order[a.kind]??9)-(order[b.kind]??9))||(b.n-a.n)||a.name.localeCompare(b.name));
 if(!S.lbSlice||!sl.some(s=>s.name===S.lbSlice))S.lbSlice=(sl.find(s=>st.leaderboard[s.name])||sl[0])?.name;
 const entries=Object.entries(st.leaderboard[S.lbSlice]||{});
 const rank=new Map([...entries].sort((a,b)=>(hib?-1:1)*((a[1].score??-1)-(b[1].score??-1))).map(([m],i)=>[m,i+1]));
 const so=S.ovSort||{k:'score',d:-1},key={score:r=>r.score,delta:r=>r.score,errors:r=>r.errors??0,cost:r=>r.cost,p50:r=>r.latency_p50,p95:r=>r.latency_p95,n:r=>r.n,ended:r=>r.ended}[so.k]||(r=>r.score);
 const board=[...entries].sort((a,b)=>{const x=key(a[1]),y=key(b[1]);if(x==null&&y==null)return rank.get(a[0])-rank.get(b[0]);if(x==null)return 1;if(y==null)return -1;return so.d*(x-y)||rank.get(a[0])-rank.get(b[0])});
 const cs=st.leaderboard[S.lbSlice]?.[champ]?.score;
 const cur=sl.find(s=>s.name===S.lbSlice),bin=ovBin(cur);
 const has=f=>entries.some(([,r])=>r[f]!=null);
 const hasCost=has('cost'),hasLat=has('latency_p50'),hasP95=has('latency_p95');
 const LB=10,shown=S.ovLbAll?board:board.slice(0,LB);
 const tabs=`<div class="tabs ov-tabs" role="tablist">${ds.map(d=>`<button role="tab" aria-selected="${d===S.lbDataset}" class="${d===S.lbDataset?'on':''}" onclick="S.lbDataset=${esc(JSON.stringify(d))};S.lbSlice=null;S.ovLbAll=false;render()">${esc(d)}<small>${ovN(st.datasets[d]?.size??Object.values(st.slices).filter(s=>s.dataset===d).reduce((a,s)=>Math.max(a,s.n||0),0))}</small></button>`).join('')}</div>`;
 const opt=s=>`<option value="${esc(s.name)}" ${s.name===S.lbSlice?'selected':''}>${esc(short(s.name))} · n ${ovN(s.n)}${st.leaderboard[s.name]?` · ${plural(Object.keys(st.leaderboard[s.name]).length,'model')}`:' · no runs'}</option>`;
 const kinds=[...new Set(sl.map(s=>s.kind))];
 const sel=`<label class="ov-pickl"><span>${term('slice','Slice')}</span><select class="ov-sel" onchange="ovPickSlice(this.value)">${kinds.map(k=>`<optgroup label="${esc(ovKind[k]||k)}">${sl.filter(s=>s.kind===k).map(opt).join('')}</optgroup>`).join('')}</select></label><span class="faint ov-pickn">${plural(sl.length,'slice')}</span>`;
 const pick=sl.length>7?sel:`<div class="ov-pick-s">${sel}</div><div class="seg ov-hide-s" role="tablist" aria-label="Slice">${sl.map(s=>`<button role="tab" aria-selected="${s.name===S.lbSlice}" class="${s.name===S.lbSlice?'on':''}" onclick="ovPickSlice(${esc(JSON.stringify(s.name))})">${esc(short(s.name))}<small>${ovN(s.n)}</small></button>`).join('')}</div>`;
 const sh=(label,k,cls)=>[`<button class="ov-sort ${so.k===k?'on':''}" onclick="ovSortBy('${k}')" aria-label="Sort by ${esc(label.replace(/<span class="ov-show-s">[^<]*<\/span>/g,'').replace(/<[^>]+>/g,''))}">${label}${so.k===k?`<span class="ov-arr">${so.d<0?'↓':'↑'}</span>`:''}</button>`,cls];
 const rows=shown.map(([m,r])=>{
  const mismatch=boardHarnessMismatch(r,st.leaderboard[S.lbSlice]?.[champ]);
  const d=!mismatch&&cs!=null&&r.score!=null?r.score-cs:null;
  const good=d!=null&&d!==0&&(hib?d>0:d<0)?'pos':'';
  const about=ovAbout(m,st.models[m]),rej=st.models[m]?.status==='rejected';
  return `<tr class="click${rej?' ov-rej':''}" title="${rej?esc('Rejected: '+firstLine(st.models[m].reason||'')):''}" onclick="location.hash='task/${enc(r.task)}'"><td class="num faint ov-rank">${rank.get(m)}</td>
   <td class="ov-id"><div class="two"><span class="row"><a class="ell ov-nm" href="#model/${enc(m)}" onclick="event.stopPropagation()" title="${esc(m)}">${mn(m)}</a>${m===champ?`<span class="ov-hide-s">${pill('champion','champion')}</span>`:rej?pill('rejected','rejected'):''}</span><span class="sub ell ov-show-s">${m===champ?'Champion · ':''}n ${ovN(r.n)}${r.errors?' · '+plural(r.errors,'error'):''}</span></div></td>
   ${bin?`<td class="ov-bar ov-hide-s">${meter(r.score,{cls:m===champ?'':'muted'})}</td>`:''}
   <td class="num"><b class="ov-sc">${cur?sv(cur.name,r.score,r.n):ovScore(r.score,cur)}</b></td>
   <td class="num ov-hide-s">${ovN(r.n)}</td>
   <td class="num ${good} ${d===0||d==null?'faint':''}">${mismatch?'Different harness':d==null?DASH:d===0?'0':cur?sd(cur.name,d):ovDelta(d,cur)}</td>
   <td class="num ov-hide-s ${r.errors?'':'faint'}">${ovN(r.errors??0)}</td>
   ${hasCost?`<td class="num ov-hide-m">${r.cost==null?DASH:money(r.cost)}</td>`:''}
   ${hasLat?`<td class="num ov-hide-m">${r.latency_p50==null?DASH:secs(r.latency_p50)}</td>`:''}${hasP95?`<td class="num ov-hide-m">${r.latency_p95==null?DASH:secs(r.latency_p95)}</td>`:''}
   <td class="num ov-hide-m faint">${ago(r.ended)}</td></tr>`});
 const head=[['<span class="sr">Rank</span>','num'],'Model',...(bin?[['<span class="sr">Score bar</span>','ov-bar ov-hide-s']]:[]),sh(bin?'Correct':'Mean','score','num'),sh('n','n','num ov-hide-s'),sh(`<span class="ov-hide-s">vs champion</span><span class="ov-show-s">Δ</span>`,'delta','num'),sh('Errors','errors','num ov-hide-s'),
  ...(hasCost?[sh('Cost / example','cost','num ov-hide-m')]:[]),...(hasLat?[sh('p50','p50','num ov-hide-m')]:[]),...(hasP95?[sh('p95','p95','num ov-hide-m')]:[]),sh('Ran','ended','num ov-hide-m')];
 const meta=cur?`${esc(ovKind[cur.kind]||cur.kind)} · ${ovN(cur.n)} examples${cs==null&&champ&&board.length?' · no champion run here':''}`:'';
 h+=`<section class="card section ov-lb" id="ov-lb"><div class="ph"><h2>Leaderboard</h2><span class="meta">${meta}</span>${cur?`<span class="r"><a class="more" href="#slices/${enc(cur.name)}">View slice</a></span>`:''}</div>${tabs}<div class="ov-pick">${sl.length?pick:''}</div>
  ${board.length?table(head,rows)+(board.length>LB?`<button class="btn ov-all" onclick="S.ovLbAll=!S.ovLbAll;render()">${S.ovLbAll?'Show top '+LB:'Show all '+board.length+' models'}</button>`:'')
  :empty(sl.length?'No complete runs on this slice':'No slices in this dataset','')}</section>`;
 if(S.ovJump){S.ovJump=false;setTimeout(()=>document.getElementById('ov-lb')?.scrollIntoView({block:'start'}),0)}
 return h;
};
