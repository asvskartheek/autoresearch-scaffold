'use strict';
// model: the header is the model itself (status, lineage, pre-declared change, ladder); the finding line is the gate
// verdict in plain words; then the next runs as copyable commands, the gate per rung and check, and the model's tasks.
// Everything sits in one block so no helper leaks into the global scope.
{
const errors=c=>(c.base_errors||0)+(c.cand_errors||0);
const STATE={pass:['pass','Passed'],fail:['fail','Failed'],need_run:['ghost','Not run yet'],need_baseline:['warn','Champion not run'],champion:['champion','Champion'],no_champion:['ghost','No champion'],needs_review:['warn','Needs review'],rejected:['rejected','Rejected'],historical:['ghost','Historical'],planned:['ghost','Planned']};
const statePill=s=>{const [c,l]=STATE[s]||['',String(s||'').replace(/_/g,' ')];return pill(l,c)};
// the real CLI: rows from any harness are recorded with `arx eval record`, then `arx gate` re-reads the ladder
const runCmd=n=>`arx eval record --model ${n.model} --slice ${n.slice} --rows <rows.jsonl>`;
// a threshold is in the slice's score units: "2.0 pts" on 0/1 slices, "0.05 MB" on continuous ones
const mag=(k,t)=>esc(sd(k,Math.abs(t)).replace(/^[+−]/,''));
const rule=c=>c.rule==='better'?(c.threshold?`Better by more than ${mag(c.slice,c.threshold)}`:'Better than champion'):c.rule==='not_worse'?(c.threshold?`Worse by at most ${mag(c.slice,c.threshold)}`:'No worse than champion'):c.rule==='manual'?'Signed off by hand':esc(c.rule);
const list=a=>a.length<2?a.join(''):a.slice(0,-1).join(', ')+' and '+a.at(-1);
// a slice name that may break only after its / and - parts on a phone, never mid-word
const slw=k=>esc(short(k)).replace(/([\/-])/g,'$1<wbr>');
const mlink=k=>`<a href="#model/${enc(k)}" title="${esc(k)}">${mn(k)}</a>`;
// figures in the slice's own units (core sv/sd): a count of n on 0/1 slices, "387 ms" on continuous ones, never a %
const bin=k=>!isCont(k);
// a count pooled over repeated runs is not whole: 28.5 of 30 reads as such, never rounded to a count its Δ contradicts
const score=(v,k,n)=>{if(v==null)return '—';n=n??sliceOf(k).n;
 if(!isCont(k)&&n){const x=v*n;if(Math.abs(x-Math.round(x))>1e-6)return esc(`${(+x.toFixed(1)).toLocaleString('en-US')} of ${n.toLocaleString('en-US')}`)}
 return esc(sv(k,v,n))};
const diff=(d,k)=>d==null?'—':esc(sd(k,d));
// a paired CI low to high, read in the direction the numbers are shown (negated slices flip it)
const ciText=(c,k)=>{const [x,y]=negSlice(k)?[c.hi,c.lo]:[c.lo,c.hi];return `${diff(x,k).replace(/ \S+$/,'')} to ${diff(y,k)}`};
// a delta in words: "5.2 pts below" on 0/1 slices, "1,071 ms faster than" / "7.6 MB more than" on continuous ones
// a delta that rounds to zero reads "level with"
const vsWords=(k,d)=>{const t=diff(Math.abs(d),k).replace(/^[+−]/,'');if(!d||/^0(\.0+)?(\s|$)/.test(t))return 'level with';if(!isCont(k))return `${t} ${d<0?'below':'above'}`;const x=negSlice(k)?-d:d,time=/^(ms|s|secs?|seconds?|min)$/i.test(unitOf(k));return `${t} ${time?(x<0?'faster':'slower'):(x<0?'less':'more')} than`};

// a rejected model has no live gate: walk the ladder again from its own runs against the champion now, so the page
// shows which check failed, by how much and against what rule. Each check is the paired statistic /api/task gives an
// eval (its rows against the champion's pooled rows), the same one the gate uses.
const refSlices=(ref,m)=>{const L=S.state,H=L.hills||{},h=H[m.hill];
 if(ref==='@hill.target')return h?.target?[h.target]:[];
 if(ref==='@hill.control')return h?.control?[h.control]:[];
 if(ref==='@hills.climbed')return Object.entries(H).filter(([k,x])=>x.status==='climbed'&&k!==m.hill&&x.target).map(([,x])=>x.target);
 const full=`${L.config.primary_dataset}/${ref}`;return L.slices[ref]?[ref]:L.slices[full]?[full]:[]};
function rewalk(name,m){
 const L=S.state,ch=L.champion,lb=L.leaderboard||{};if(!ch||!(L.config.ladder||[]).length)return null;
 const C=S.mdRej?.name===name&&S.mdRej.ch===ch?S.mdRej:(S.mdRej={name,ch,vs:{},want:new Set()});
 let wait=false;
 const rungs=L.config.ladder.map(r=>{
  const checks=(r.checks||[]).filter(c=>!c.manual).flatMap(k=>refSlices(k.slice,m).map(sl=>{
   const c={slice:sl,rule:k.rule,threshold:k.rule==='better'?(k.margin||0):-(k.tolerance||0),n:L.slices[sl]?.n};
   const own=lb[sl]?.[name],base=lb[sl]?.[ch];
   if(!own)return {...c,state:'need_run'};
   if(!base)return {...c,state:'need_baseline'};
   const vs=C.vs[own.task];
   if(vs===undefined){wait=true;if(!C.want.has(own.task)){C.want.add(own.task);
    fetch('api/task/'+enc(own.task),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(d=>{C.vs[own.task]=d?.vs_champion||null;render()}).catch(()=>{C.vs[own.task]=null;render()})}
    return {...c,state:'need_run'}}
   if(!vs||vs.delta==null)return {...c,state:'need_baseline'};
   const ok=k.rule==='better'?vs.delta>c.threshold:vs.delta>=c.threshold;
   return {...c,...vs,state:ok?'pass':'fail',noisy:vs.lo<0&&0<vs.hi,cand_task:own.task,base_task:vs.task,base_runs:vs.runs,
    cand_runs:L.tasks.filter(t=>t.kind==='eval'&&t.model===name&&t.slice===sl&&t.status==='done').length||1}}));
  const st=new Set(checks.map(c=>c.state));
  return {rung:r.rung,checks,status:!checks.length?'locked':st.has('fail')?'fail':[...st].every(x=>x==='pass')?'pass':'locked'}});
 return {champion:ch,rungs,next:[],wait};
}
// the verdict in one or two plain sentences: ready, blocked (where and by how much), or what to run next
function verdict(name,m,g){
 if(m.status==='champion')return {text:`This is the champion${m.promoted?`, promoted ${stamp(m.promoted)}`:''}. Every candidate is paired against it on the same examples.`};
 if(m.status==='rejected'){
  // the figure below carries the evidence; the line names the check that failed, by how much, against what rule
  const w=rewalk(name,m),fr=w?.rungs.find(r=>r.status==='fail'),c=fr?.checks.find(c=>c.state==='fail');
  if(c)return {text:`Rejected: fails the ${esc(fr.rung)} rung on ${esc(short(c.slice))}, ${score(c.cand,c.slice,c.n)} against the champion’s ${score(c.base,c.slice,c.n)}, ${vsWords(c.slice,c.delta)} where the rule is “${(r=>r[0].toLowerCase()+r.slice(1))(rule(c))}”.`,cls:'neg',rej:w};
  return {text:w?.wait?'Rejected.':w&&w.rungs.some(r=>r.status==='pass')?'Rejected by hand: no check it ran fails against the champion now.':'Rejected.',cls:'neg',rej:w};
 }
 if(!g)return {text:m.status==='planned'?`Planned, not on the ladder yet. Register it as a candidate with <code>arx model add ${esc(name)}</code> when it is ready to run.`:`${esc(m.status[0].toUpperCase()+m.status.slice(1))} model, kept for the record and not on the ladder.${m.reason?' '+reasonHTML(m.reason):''}`};
 if(g.error)return {text:`The gate could not be read: ${esc(g.error)}`,cls:'neg'};
 if(!g.champion&&!S.state.champion)return {text:`No champion yet, so there is nothing to pair this model against. Make a baseline champion first, then re-check the ladder.`,nochamp:true};
 const passed=g.rungs.filter(r=>r.status==='pass').map(r=>esc(r.rung));
 const noisy=g.rungs.flatMap(r=>r.checks.filter(c=>c.state==='pass'&&c.noisy).map(c=>esc(short(c.slice))));
 const tail=noisy.length?` The pass on ${list(noisy)} is within noise (its 90% interval crosses zero), so treat it as a lead, not a result.`:'';
 if(g.promotable)return {text:`Ready to promote: it passed every rung against ${mlink(g.champion)}.${tail}`,cls:'pos',ready:true};
 const fail=g.rungs.find(r=>r.status==='fail');
 if(fail){const c=fail.checks.find(c=>c.state==='fail');
  if(c&&isCont(c.slice)&&errors(c))return {text:`Failed a gate check. ${c.cand_errors||0} candidate and ${c.base_errors||0} champion examples errored and scored 0.`,cls:'warn',evidenceReview:true};
  return {text:`Cannot be promoted: it failed the ${esc(fail.rung)} rung${c?`, ${vsWords(c.slice,c.delta)} the champion on ${esc(short(c.slice))} (n ${c.n}) where the rule is “${(r=>r[0].toLowerCase()+r.slice(1))(rule(c))}”`:''}.${passed.length?` It had passed ${list(passed)}.`:''}`,cls:'neg',failed:true};}
 // in progress: the ladder itself is the verdict; one chip says who runs what next (people skip the sentence)
 // a next run already in progress shows as one live chip per task (a union pass covers several slices); the Next chip
 // names the first run nobody has started
 const live=[...new Map((g.next||[]).map(n=>[n,runTask(n)]).filter(([,t])=>t).map(([n,t])=>[t.id,[n,t]])).values()];
 const n=(g.next||[]).find(n=>!runTask(n));
 const rn=live.map(([n,t])=>{const pr=t.progress||{},sl=t.status==='stalled';return `<a class="md-nx md-run" href="#task/${enc(t.id)}" title="${esc(t.title||'Open the running task')}"><span class="md-nxa">${sl?'Silent':'Running'}</span>${esc(n.model!==name?'champion':'this model')} on <span class="mono">${esc(short(t.slice||n.slice))}</span>${pr.total?`<span class="num">${Number(pr.done||0).toLocaleString()}<span class="faint"> / ${Number(pr.total).toLocaleString()}</span></span>`:''}</a>`}).join('');
 const nx=n?`<span class="md-nx" title="${esc(n.model!==name?'The champion needs this run before the rung can be compared':'This model runs next')}"><span class="md-nxa">Next</span>${esc(n.model!==name?'champion':'this model')} on <span class="mono">${esc(short(n.slice))}</span></span>`:'';
 return {text:`<span class="md-vz">${ladder(g)}${rn}${nx}${noisy.length?pill('Noisy on '+noisy.map(x=>x).join(', '),'noisy'):''}</span>`,viz:true};
}

function gateTable(name,g,base='Matched champion'){
 const L=S.state,rows=[];
 // the next run behind a check that has not run yet, when it is already in progress
 const live=c=>(g.next||[]).find(n=>n.slice===c.slice&&(c.state==='need_run'?n.model===name:n.model!==name)&&runTask(n));
 for(const r of g.rungs){
  const head=`<td class="md-rung" rowspan="${Math.max(1,r.checks.length)}"><span class="ladder"><span class="rg ${esc(r.status)}"><i></i><span>${esc(r.rung)}</span></span></span></td>`;
  if(!r.checks.length){rows.push(`<tr class="md-locked">${head}<td colspan="8" class="sub">${r.status==='locked'?'Opens once the rung above passes':'No checks on this rung'}</td></tr>`);continue}
  r.checks.forEach((c,i)=>{
   const n=c.n??L.slices[c.slice]?.n,ran=c.delta!=null;
   const errorNote=errors(c)?` · ${c.cand_errors||0} / ${c.base_errors||0} errors, scored 0`:'';
   const pooled=c.cand_runs>1||c.base_runs>1?` · runs ${c.cand_runs??1} / ${c.base_runs??1}`:'';
   const go=c.cand_task?`onclick="if(!event.target.closest('a,button,details'))location.hash='task/${enc(c.cand_task)}'"`:'';
   rows.push(`<tr class="${c.cand_task?'click':''} ${i===r.checks.length-1?'':'md-in'}" ${go}>${i?'':head}
    <td class="${i?"md-c1":""}"><div class="two"><a class="mono md-sl ln" href="#slices/${enc(c.slice)}">${slw(c.slice)}</a><span class="sub" ${pooled?'title="Complete runs pooled per example: this model / champion"':''}>${n!=null?'n '+n.toLocaleString():'n —'}${pooled}${bin(c.slice)?'':' · mean'}${errorNote}</span><details class="md-mobile-evidence"><summary>Rule and compared values</summary><div>${rule(c)}</div><div>This model: ${score(c.cand,c.slice,c.n)}</div><div>Matched champion: ${score(c.base,c.slice,c.n)}</div>${c.base_task?`<a href="#task/${enc(c.base_task)}">Champion run / setup</a>`:''}</details></div></td>
    <td class="sub md-rule md-hm">${rule(c)}</td>
    <td class="num md-hs">${ran?(c.cand_task?`<a href="#task/${enc(c.cand_task)}">${score(c.cand,c.slice,c.n)}</a>`:score(c.cand,c.slice,c.n)):DASH}</td>
    <td class="num md-hs">${ran?(c.base_task?`<a href="#task/${enc(c.base_task)}">${score(c.base,c.slice,c.n)}</a>`:score(c.base,c.slice,c.n)):DASH}</td>
    <td class="num"><span class="${!ran?'':c.delta>0?'pos':c.delta<0?'neg':'sub'}">${ran?diff(c.delta,c.slice):DASH}</span></td>
    <td class="md-ci">${ran?(bin(c.slice)?ciBar(c):'')+`<div class="sub md-cil">${ciText(c,c.slice)}</div>`:DASH}</td>
    <td class="num md-hw">${c.wins!=null?`<span class="pos">${c.wins}</span> / <span class="${c.losses?'neg':''}">${c.losses}</span>`:DASH}</td>
    <td class="md-res"><span class="row">${(c.state==='need_run'||c.state==='need_baseline')&&live(c)?runChip(live(c)):statePill(c.state)}${c.noisy?pill('Noisy','noisy'):''}</span></td></tr>`);
  });
 }
 return `<div class="tbl md-gate"><table><thead><tr><th>${term('rung','Rung')}</th><th>${term('slice','Slice')}</th><th class="md-hm">Rule</th><th class="num md-hs">This model</th><th class="num md-hs">${base}</th><th class="num">${term('paired-delta','Δ')}</th><th>${term('interval','90% CI')}</th><th class="num md-hw">Wins / losses</th><th class="md-res">Result</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

// a champion's promotion evidence: the gate it passed, stored on the promote decision; for older promotions, the
// same paired statistic recomputed on its hill's target and control rows against the champion it replaced
function hillRows(hill){
 if(S.hill?.key===hill)return S.hill.data;
 if(S.mdHill?.key===hill)return S.mdHill.data;
 if(S.mdHill?.key!==hill+'\u0000loading'){S.mdHill={key:hill+'\u0000loading'};
  fetch('api/hill/'+enc(hill),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(d=>{S.mdHill={key:hill,data:d};render()}).catch(()=>{S.mdHill={key:hill,data:null}})}
 return undefined;
}
function promotion(name,m){
 const L=S.state,pd=(L.decisions||[]).filter(d=>d.kind==='promote'&&d.model===name).at(-1);
 if(!pd)return m.promoted?panel('Promotion evidence',empty('Promotion record not in view','The dashboard reads the last 50 decisions; the paper keeps the evidence.'),{cls:'section'}):'';
 const was=pd.replaced,meta=`paired against ${was?mlink(was):'the previous champion'} on the same examples · promoted ${stamp(pd.t)}`;
 if(pd.gate?.rungs)return panel('Promotion evidence',gateTable(name,pd.gate,'Was champion'),{meta,cls:'section flush md-gp'});
 const hill=m.hill&&L.hills[m.hill];
 if(!was||!hill)return panel('Promotion evidence',empty('No paired record','This promotion predates stored gates and has no hill to recompute it from.'),{meta,cls:'section'});
 const D=hillRows(m.hill);
 if(D===undefined)return panel('Promotion evidence',`<div class="sub">Reading per-example rows…</div>`,{meta,cls:'section'});
 const rows=['target','control'].map(role=>{const R=D?.[role];if(!R)return '';
  const p=pairedRows?.(name+'\u0000'+was+'\u0000'+R.slice,R.runs[name],R.runs[was]);
  const k=R.slice,noisy=p&&p.lo<0&&0<p.hi;
  return `<tr><td><div class="two"><a class="mono md-sl ln" href="#slices/${enc(k)}">${slw(k)}</a><span class="sub">${role==='target'?'hill target':'control'}${p?' · n '+p.n.toLocaleString():''}</span></div></td>
   <td class="num">${p?score(p.cand,k,p.n):DASH}</td><td class="num">${p?score(p.base,k,p.n):DASH}</td>
   <td class="num"><span class="${!p||noisy?'sub':p.delta>0?'pos':p.delta<0?'neg':'sub'}">${p?diff(p.delta,k):DASH}</span></td>
   <td class="md-ci">${p?(bin(k)?ciBar(p):'')+`<div class="sub md-cil">${ciText(p,k)}</div>`:'<span class="sub">no paired rows</span>'}</td>
   <td class="num">${p?`<span class="pos">${p.wins}</span> / <span class="${p.losses?'neg':''}">${p.losses}</span>`:DASH}</td>
   <td>${noisy?pill('Noisy','noisy'):''}</td></tr>`}).join('');
 if(!rows)return '';
 return panel('Promotion evidence',`<div class="tbl md-gate"><table><thead><tr><th>Slice</th><th class="num">This model</th><th class="num">Was champion</th><th class="num">Δ</th><th>90% CI</th><th class="num">Wins / losses</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`,
  {meta:meta+' · recomputed from the hill’s rows',cls:'section flush md-gp'});
}

// with no champion: promote the newest earlier baseline kept on record, else register one
const champCmd=name=>{const b=Object.entries(S.state.models).filter(([k,o])=>k!==name&&(o.status==='historical'||o.status==='retired')).sort((a,b)=>(b[1].created||0)-(a[1].created||0))[0];
 return b?`arx promote ${b[0]} --force`:'arx model add <baseline> --champion'};
const nextRow=(lead,c)=>`<div class="md-next"><span class="md-lead">${lead}</span>${cmd(c)}</div>`;
// the next runs: one row per run still to start, with its command; runs already in progress are one row per task,
// the slices it covers and its live progress instead of a command
function nxRows(name,nx){
 const who=n=>n.model!==name?'Champion baseline on':'This model on',sl=a=>a.map(n=>esc(short(n.slice))).join(', ');
 const by=new Map();for(const n of nx){const t=runTask(n);if(t)by.set(t.id,[...(by.get(t.id)||[]),n])}
 return [...by.values()].map(a=>`<div class="md-next"><span class="md-lead">${who(a[0])} ${sl(a)}</span>${runChip(a[0])}</div>`).join('')
  +nx.filter(n=>runTask(n)?.status==='stalled').map(n=>nextRow('Close the stalled attempt, then rerun the same measurement',`arx task finish ${runTask(n).id} --status failed`)).join('')
  +nx.filter(n=>!runTask(n)).map(n=>nextRow(`${who(n)} ${sl([n])}`,runCmd(n))).join('');
}

// a model's plain-text label (page title, crumb, tab): its title, else the tail of a long +-chained id
const label=k=>{const t=S.state.models[k]?.title;if(t)return t;const s=String(k||'—'),p=s.split('+');return p.length>3?'…+'+p.slice(-2).join('+'):s};

VIEWS.model=(name)=>{
 const L=S.state,m=L.models[name];
 const crumbs=[['Models','#models'],[label(name),'#model/'+enc(name)]];
 if(!m)return page({title:name,crumbs,finding:'There is no model by this name in the ledger.'})+panel('',empty('Model not found',`<code>arx model add ${esc(name)}</code> registers it`));
 const g=L.gates[name],hill=m.hill?L.hills[m.hill]:null,v=verdict(name,m,g);
 const onLadder=g&&!g.error&&m.status!=='champion';
 const nx=onLadder?(g.next||[]):[];
 const acts=v.ready?cmd(`arx promote ${name}`):!g?"":`<span class="cmd md-gatecmd"><code>arx gate ${esc(name)}</code>${copyBtn('arx gate '+name)}</span>`;
 const titled=m.title&&m.title!==name;
 const h=[page({title:label(name),copy:titled?'':name,crumbs,finding:`<span class="${v.cls||''}">${v.text}</span>`,acts:acts+`<a class="btn" href="reference/${enc(name)}">Paper</a>`})];

 // the object header: status, lineage, hill, the pre-declared change, the reason, the ladder
 const f=fullScore(name),fullKey=L.config.primary_dataset+'/full';
 const meta=[st(m.status,m.status[0].toUpperCase()+m.status.slice(1))+(m.phase?' '+pill(m.phase):''),titled||label(name)!==name?`<span class="md-idc"><span class="mono md-id">${esc(name)}</span>${copyBtn(name)}</span>`:'',m.parent&&m.parent!==name?`<span title="The model this one was built from">built on ${mlink(m.parent)}${L.models[m.parent]?.status==='champion'?' (champion)':''}</span>`:'',
  m.hill?`<span>hill <a class="ln" href="#hill/${enc(m.hill)}">${esc(hill?.title||m.hill)}</a></span>`:'',m.created?`<span>registered ${stamp(m.created)}</span>`:'',
  f?`<span>${f.task?`<a href="#task/${enc(f.task)}">${score(f.score,fullKey,f.n)}</a>`:score(f.score,fullKey,f.n)} on ${esc(short(fullKey))}, n ${f.n.toLocaleString()}</span>`:''].filter(Boolean).join('<span class="sep">·</span>');
 const lad=v.rej?ladder(v.rej):g&&!g.error&&!v.viz?ladder(g):'';  // a candidate's ladder already leads the page
 h.push(`<section class="card md-obj"><div class="md-top"><div class="md-meta">${meta}</div>${lad?`<div class="md-lad">${lad}</div>`:''}</div>
  <dl class="md-dl">
   <div><dt>Expected change</dt><dd>${m.change?reasonHTML(m.change):'<span class="dash">Not declared. State what this should move before running it, with <code>arx model add '+esc(name)+' --change "…"</code>.</span>'}</dd></div>
   ${m.reason&&m.status!=="rejected"&&g?`<div><dt>Note</dt><dd>${reasonHTML(m.reason)}</dd></div>`:""}
   ${m.reason&&m.status==="rejected"?`<div><dt>Why, as recorded</dt><dd>${reasonHTML(m.reason)}</dd></div>`:""}
   ${m.links&&Object.keys(m.links).length?`<div><dt>Links</dt><dd class="md-links">${extLinks(m.links)}</dd></div>`:''}
  </dl></section>`);

 if(onLadder){
  const body=v.ready?nextRow('Every rung passed',`arx promote ${name}`)
   :nx.length?nxRows(name,nx)+nextRow('Then re-check the ladder',`arx gate ${name}`)
   :v.nochamp?nextRow('Make a baseline champion',champCmd(name))+nextRow('Then re-check the ladder',`arx gate ${name}`)
   :v.evidenceReview?nextRow('Inspect comparison errors and rerun the affected measurement',`arx gate ${name}`)
   :v.failed?nextRow('Record the failure',`arx reject ${name} --reason "failed ${g.rungs.find(r=>r.status==='fail').rung}"`)
   :empty('Nothing to run',`<code>arx gate ${esc(name)}</code> re-reads the ladder`);
  h.push(panel(v.ready?'Promote':v.failed?'Close it out':v.nochamp?'Next':'Next runs',body,{meta:nx.length?plural(nx.length,'run')+' before the next rung opens'+(nx.some(runTask)?` · ${nx.filter(runTask).length} started`:''):'',cls:'section md-np'}));
  h.push(panel(term('gate','Gate'),gateTable(name,g),{meta:g.champion?`paired against ${mlink(g.champion)} on the same examples`:'no champion to pair against yet',cls:'section flush md-gp'}));
 }else if(m.status==='champion'&&g&&!g.error){
  h.push(promotion(name,m));
  h.push(panel('Ladder slices',table(['Rung','Slice',['n','num'],['Score','num']],g.rungs.flatMap(r=>r.checks.map((c,i)=>{const s=L.leaderboard[c.slice]?.[name],n=s?.n??L.slices[c.slice]?.n;
   return `<tr><td>${i?'':esc(r.rung)}</td><td><a class="mono md-sl ln" href="#slices/${enc(c.slice)}">${slw(c.slice)}</a></td><td class="num">${n!=null?n.toLocaleString():DASH}</td><td class="num">${s?(s.task?`<a href="#task/${enc(s.task)}">${score(s.score,c.slice,s.n)}</a>`:score(s.score,c.slice,s.n)):DASH}</td></tr>`}))),{meta:'the scores candidates are paired against',cls:'section'}));
 }

 if(v.rej)h.push(panel(`${term('gate','Gate')}, walked again`,v.rej.wait&&!v.rej.rungs.some(r=>r.checks.some(c=>c.delta!=null))?'<div class="sub">Reading its runs…</div>':gateTable(name,v.rej),{meta:`its runs paired against ${mlink(v.rej.champion)}, the champion now, on the same examples`,cls:'section flush md-gp'}));

 const tasks=L.tasks.filter(t=>t.model===name&&!t.detail_of).sort((a,b)=>(isLive(b)-isLive(a))||(b.updated-a.updated));
 h.push(panel('Tasks',tasks.length?`<div class="md-tasks">${tasks.slice(0,30).map(t=>kidRow([t,0])).join('')}</div>${tasks.length>30?`<a class="more" href="#archive">${tasks.length-30} more in the archive</a>`:''}`:empty('No tasks for this model',`Evals recorded with <code>arx eval record --model ${esc(name)}</code> show here`),{meta:tasks.length?plural(tasks.length,'task'):'',cls:'section'}));
 return h.join('');
};
}
