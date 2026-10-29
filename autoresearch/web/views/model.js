'use strict';
// model: the header is the model itself (status, lineage, pre-declared change, ladder); the finding line is the gate
// verdict in plain words; then the next runs as copyable commands, the gate per rung and check, and the model's tasks.
// Everything sits in one block so no helper leaks into the global scope.
{
const STATE={pass:['pass','Passed'],fail:['fail','Failed'],need_run:['ghost','Not run yet'],need_baseline:['warn','Champion not run'],champion:['champion','Champion'],no_champion:['ghost','No champion'],needs_review:['warn','Needs review'],rejected:['rejected','Rejected'],historical:['ghost','Historical'],planned:['ghost','Planned']};
const statePill=s=>{const [c,l]=STATE[s]||['',String(s||'').replace(/_/g,' ')];return pill(l,c)};
// the real CLI: rows from any harness are recorded with `arx eval record`, then `arx gate` re-reads the ladder
const runCmd=n=>`arx eval record --model ${n.model} --slice ${n.slice} --rows <rows.jsonl>`;
const rule=c=>c.rule==='better'?(c.threshold?`Better by more than ${pts(c.threshold)} pts`:'Better than champion'):c.rule==='not_worse'?(c.threshold?`No worse than ${pts(c.threshold)} pts`:'No worse than champion'):c.rule==='manual'?'Signed off by hand':esc(c.rule);
const list=a=>a.length<2?a.join(''):a.slice(0,-1).join(', ')+' and '+a.at(-1);
const mlink=k=>`<a href="#model/${enc(k)}" title="${esc(k)}">${mn(k)}</a>`;
// a slice scores 0/1 per example unless it says `scale: continuous`: then a mean in its unit, never a %
const bin=sl=>sl?.scale!=='continuous';
const val=(v,sl)=>(Math.abs(v)>=10?v.toFixed(1):num(v,3))+(sl?.unit?' '+sl.unit:'');
const score=(v,sl)=>v==null?'—':bin(sl)?pct(v):esc(val(v,sl));
const diff=(d,sl)=>d==null?'—':bin(sl)?pts(d):(d>0?'+':d<0?'−':'')+esc(val(Math.abs(d),sl));
const unitOf=sl=>bin(sl)?' pts':'';

// the verdict in one or two plain sentences: ready, blocked (where and by how much), or what to run next
function verdict(name,m,g){
 if(m.status==='champion')return {text:`This is the champion${m.promoted?`, promoted ${stamp(m.promoted)}`:''}. Every candidate is paired against it on the same examples.`};
 if(m.status==='rejected')return {text:`Rejected. ${m.reason?esc(m.reason):'No reason was recorded.'}`,cls:'neg'};
 if(!g)return {text:m.status==='planned'?`Planned, not on the ladder yet. Register it as a candidate with <code>arx model add ${esc(name)}</code> when it is ready to run.`:`${esc(m.status[0].toUpperCase()+m.status.slice(1))} model, kept for the record and not on the ladder.${m.reason?' '+esc(m.reason):''}`};
 if(g.error)return {text:`The gate could not be read: ${esc(g.error)}`,cls:'neg'};
 const passed=g.rungs.filter(r=>r.status==='pass').map(r=>esc(r.rung));
 const noisy=g.rungs.flatMap(r=>r.checks.filter(c=>c.state==='pass'&&c.noisy).map(c=>esc(short(c.slice))));
 const tail=noisy.length?` The pass on ${list(noisy)} is within noise (its 90% interval crosses zero), so treat it as a lead, not a result.`:'';
 if(g.promotable)return {text:`Ready to promote: it passed every rung against ${mlink(g.champion)}.${tail}`,cls:'pos',ready:true};
 const fail=g.rungs.find(r=>r.status==='fail');
 if(fail){const c=fail.checks.find(c=>c.state==='fail');
  return {text:`Cannot be promoted: it failed the ${esc(fail.rung)} rung${c?`, scoring ${diff(c.delta,S.state.slices[c.slice])}${unitOf(S.state.slices[c.slice])} against the champion on ${esc(short(c.slice))} (n ${c.n}) where the rule is “${rule(c).toLowerCase()}”`:''}.${passed.length?` It had passed ${list(passed)}.`:''}`,cls:'neg',failed:true};}
 const pend=g.rungs.find(r=>r.status==='pending'),n=g.next?.[0];
 let t=passed.length?`Passed ${list(passed)}. `:'Has not passed a rung yet. ';
 if(n)t+=n.model!==name?`Next, the champion needs a run on ${esc(short(n.slice))} so the ${esc(pend?.rung||'next')} rung can be compared.`:`Next: run it on ${esc(short(n.slice))} for the ${esc(pend?.rung||'next')} rung.`;
 return {text:t+tail};
}

function gateTable(name,g){
 const L=S.state,rows=[];
 for(const r of g.rungs){
  const head=`<td class="md-rung" rowspan="${Math.max(1,r.checks.length)}"><span class="ladder"><span class="rg ${esc(r.status)}"><i></i><span>${esc(r.rung)}</span></span></span></td>`;
  if(!r.checks.length){rows.push(`<tr class="md-locked">${head}<td colspan="8" class="sub">${r.status==='locked'?'Opens once the rung above passes':'No checks on this rung'}</td></tr>`);continue}
  r.checks.forEach((c,i)=>{
   const n=c.n??L.slices[c.slice]?.n,ran=c.delta!=null,sl=L.slices[c.slice];
   const pooled=c.cand_runs>1||c.base_runs>1?` · runs ${c.cand_runs??1} / ${c.base_runs??1}`:'';
   const go=c.cand_task?`onclick="if(!event.target.closest('a,button'))location.hash='task/${enc(c.cand_task)}'"`:'';
   rows.push(`<tr class="${c.cand_task?'click':''} ${i===r.checks.length-1?'':'md-in'}" ${go}>${i?'':head}
    <td class="${i?"md-c1":""}"><div class="two"><a class="mono md-sl ln" href="#slices/${enc(c.slice)}">${esc(short(c.slice))}</a><span class="sub" ${pooled?'title="Complete runs pooled per example: this model / champion"':''}>${n!=null?'n '+n.toLocaleString():'n —'}${pooled}${bin(sl)?'':' · mean'}</span></div></td>
    <td class="sub md-rule">${rule(c)}</td>
    <td class="num">${ran?(c.cand_task?`<a href="#task/${enc(c.cand_task)}">${score(c.cand,sl)}</a>`:score(c.cand,sl)):DASH}</td>
    <td class="num">${ran?(c.base_task?`<a href="#task/${enc(c.base_task)}">${score(c.base,sl)}</a>`:score(c.base,sl)):DASH}</td>
    <td class="num"><span class="${!ran?'':c.delta>0?'pos':c.delta<0?'neg':'sub'}">${ran?diff(c.delta,sl):DASH}</span></td>
    <td class="md-ci">${ran?(bin(sl)?ciBar(c):'')+`<div class="sub md-cil">${diff(c.lo,sl)} to ${diff(c.hi,sl)}</div>`:DASH}</td>
    <td class="num">${c.wins!=null?`<span class="pos">${c.wins}</span> / <span class="${c.losses?'neg':''}">${c.losses}</span>`:DASH}</td>
    <td><span class="row">${statePill(c.state)}${c.noisy?pill('Noisy','noisy'):''}</span></td></tr>`);
  });
 }
 return `<div class="tbl md-gate"><table><thead><tr><th>Rung</th><th>Slice</th><th>Rule</th><th class="num">This model</th><th class="num">Champion</th><th class="num">Δ${g.rungs.every(r=>r.checks.every(c=>bin(L.slices[c.slice])))?' pts':''}</th><th>90% CI</th><th class="num">Wins / losses</th><th>Result</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

const nextRow=(lead,c)=>`<div class="md-next"><span class="md-lead">${lead}</span>${cmd(c)}</div>`;

VIEWS.model=(name)=>{
 const L=S.state,m=L.models[name];
 const crumbs=[['Models','#models'],[L.models[name]?.title||name,'#model/'+enc(name)]];
 if(!m)return page({title:name,crumbs,finding:'There is no model by this name in the ledger.'})+panel('',empty('Model not found',`<code>arx model add ${esc(name)}</code> registers it`));
 const g=L.gates[name],hill=m.hill?L.hills[m.hill]:null,v=verdict(name,m,g);
 const onLadder=g&&!g.error&&m.status!=='champion';
 const nx=onLadder?(g.next||[]):[];
 const acts=v.ready?cmd(`arx promote ${name}`):!g?"":`<span class="cmd md-gatecmd"><code>arx gate ${esc(name)}</code>${copyBtn('arx gate '+name)}</span>`;
 const titled=m.title&&m.title!==name;
 const h=[page({title:m.title||name,copy:titled?'':name,crumbs,finding:`<span class="${v.cls||''}">${v.text}</span>`,acts:acts+`<a class="btn" href="reference/${enc(name)}">Paper</a>`})];

 // the object header: status, lineage, hill, the pre-declared change, the reason, the ladder
 const f=fullScore(name),fullKey=L.config.primary_dataset+'/full',fsl=L.slices[fullKey];
 const meta=[st(m.status,m.status[0].toUpperCase()+m.status.slice(1))+(m.phase?' '+pill(m.phase):''),titled?`<span class="md-idc"><span class="mono md-id">${esc(name)}</span>${copyBtn(name)}</span>`:'',m.parent&&m.parent!==name?`<span>from ${mlink(m.parent)}</span>`:'',
  m.hill?`<span>hill <a class="ln" href="#hill/${enc(m.hill)}">${esc(hill?.title||m.hill)}</a></span>`:'',m.created?`<span>registered ${stamp(m.created)}</span>`:'',
  f?`<span>${f.task?`<a href="#task/${enc(f.task)}">${score(f.score,fsl)}</a>`:score(f.score,fsl)} on ${esc(short(fullKey))}, n ${f.n.toLocaleString()}</span>`:''].filter(Boolean).join('<span class="sep">·</span>');
 const lad=g&&!g.error?ladder(g):'';
 h.push(`<section class="card md-obj"><div class="md-top"><div class="md-meta">${meta}</div>${lad?`<div class="md-lad">${lad}</div>`:''}</div>
  <dl class="md-dl">
   <div><dt>Expected change</dt><dd>${m.change?esc(m.change):'<span class="dash">Not declared. State what this should move before running it, with <code>arx model add '+esc(name)+' --change "…"</code>.</span>'}</dd></div>
   ${m.reason&&m.status!=="rejected"&&g?`<div><dt>Note</dt><dd>${esc(m.reason)}</dd></div>`:""}
   ${m.links&&Object.keys(m.links).length?`<div><dt>Links</dt><dd class="md-links">${extLinks(m.links)}</dd></div>`:''}
  </dl></section>`);

 if(onLadder){
  const body=v.ready?nextRow('Every rung passed',`arx promote ${name}`)
   :nx.length?nx.map(n=>nextRow(n.model!==name?`Champion baseline on ${esc(short(n.slice))}`:`This model on ${esc(short(n.slice))}`,runCmd(n))).join('')+nextRow('Then re-check the ladder',`arx gate ${name}`)
   :v.failed?nextRow('Record the failure',`arx reject ${name} --reason "failed ${g.rungs.find(r=>r.status==='fail').rung}"`)
   :empty('Nothing to run',`<code>arx gate ${esc(name)}</code> re-reads the ladder`);
  h.push(panel(v.ready?'Promote':v.failed?'Close it out':'Next runs',body,{meta:nx.length?plural(nx.length,'run')+' before the next rung opens':'',cls:'section md-np'}));
  h.push(panel('Gate',gateTable(name,g),{meta:`paired against ${mlink(g.champion||'')} on the same examples`,cls:'section flush md-gp'}));
 }else if(m.status==='champion'&&g&&!g.error){
  h.push(panel('Ladder slices',table(['Rung','Slice',['n','num'],['Score','num']],g.rungs.flatMap(r=>r.checks.map((c,i)=>{const s=L.leaderboard[c.slice]?.[name],n=s?.n??L.slices[c.slice]?.n;
   return `<tr><td>${i?'':esc(r.rung)}</td><td><a class="mono md-sl ln" href="#slices/${enc(c.slice)}">${esc(short(c.slice))}</a></td><td class="num">${n!=null?n.toLocaleString():DASH}</td><td class="num">${s?(s.task?`<a href="#task/${enc(s.task)}">${score(s.score,L.slices[c.slice])}</a>`:score(s.score,L.slices[c.slice])):DASH}</td></tr>`}))),{meta:'the scores candidates are paired against',cls:'section'}));
 }

 const tasks=L.tasks.filter(t=>t.model===name).sort((a,b)=>(isLive(b)-isLive(a))||(b.updated-a.updated));
 h.push(panel('Tasks',tasks.length?`<div class="md-tasks">${tasks.slice(0,30).map(t=>kidRow([t,0])).join('')}</div>${tasks.length>30?`<a class="more" href="#archive">${tasks.length-30} more in the archive</a>`:''}`:empty('No tasks for this model',`Evals recorded with <code>arx eval record --model ${esc(name)}</code> show here`),{meta:tasks.length?plural(tasks.length,'task'):'',cls:'section'}));
 return h.join('');
};
}
