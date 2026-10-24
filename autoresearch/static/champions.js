// Champions: official champions only (promoted through every gate, full dataset included), one page per champion, and
// "Next champion": the candidates and how far each is through the pipeline. URL scheme: #champion/<model id>.
// A best-so-far run on one eval set is a lead (Overview record), never a champion. Data: state.timeline (server.py
// _timeline, official entries only) and state.gates.
const chLink=id=>`#champion/${encodeURIComponent(id)}`;
const chTrack=s=>!s||/None/.test(s)?'Unlabelled runs':String(s).replace(/\bSlice\b/g,'Eval set');
const chSpan=s=>s==null?'':s<60?Math.max(1,Math.round(s))+'s':s<3600?Math.round(s/60)+'m':s<86400?Math.round(s/3600)+'h':Math.round(s/86400)+'d';
const chKind=e=>e.seeded?'<span class="chip">baseline</span>':'<span class="chip pass" title="Passed every gate">official</span>';
const chDelta=e=>e.delta==null?'<span class="sub">first</span>':`<span class="${e.delta>0?'pos':e.delta<0?'neg':'sub'}"><b>${pts(e.delta)}</b> pts</span>`;
const chHeld=e=>e.current?'<span class="sub">holds today</span>':e.held_s!=null?chSpan(e.held_s):'<span class="sub">—</span>';

function chRow(e){
 const sub=e.prev_label?`over ${e.prev_label}${e.base_score!=null?' ('+pct(e.base_score)+')':''}`:'';
 return `<tr class="click" onclick="location.hash='champion/${encodeURIComponent(e.id)}'"><td class="sub chwhen">${e.t?stamp(e.t):'—'}</td>
  <td class="chname"><b class="clamp1" title="${esc(e.label)}">${esc(e.label)}</b>${sub?`<div class="sub clamp1" title="${esc(sub)}">${esc(sub)}</div>`:''}</td>
  <td class="num">${e.score!=null?`<b>${pct(e.score)}</b><div class="sub">n ${e.n}</div>`:'<span class="sub">no run</span>'}</td>
  <td class="num">${chDelta(e)}</td><td class="num">${chHeld(e)}</td><td>${chKind(e)}${e.current?' <span class="chip champion">current</span>':''}</td></tr>`;
}
// candidates still in the pipeline: each with its gates and where it stands
function chCandidates(){
 const st=S.state,cs=ovCandidates();
 if(!cs.length)return '<div class="empty">No candidate is in the pipeline.</div>';
 return `<div class="scroll"><table><tr><th>Candidate</th><th>Gates</th><th>Where it stands</th></tr>${cs.map(c=>`<tr class="click" onclick="location.hash='model/${encodeURIComponent(c.name)}'"><td><b class="clamp1">${esc(c.title)}</b><div class="sub clamp1">${esc(c.hill?st.hills[c.hill]?.title||c.hill:'')}</div></td><td>${ladderPills(c.gate)}</td><td>${c.gate.promotable?'<span class="chip pass">ready to promote</span>':c.stop?`<span class="chip ${c.stop.status==='fail'?'fail':'pending'}">${esc(c.stop.rung)}</span> <span class="sub">${esc(c.stop.why)}</span>`:'<span class="sub">no gate result yet</span>'}</td></tr>`).join('')}</table></div>`;
}
function vChampions(){
 const st=S.state,tl=st.timeline||[];
 let h=topbar('Champions');
 h+=`<div class="card section"><h2>Champions<span class="r">${tl.length?tl.length+' official':''}</span></h2>${tl.length?`<div class="scroll"><table class="chtl"><tr><th>When</th><th>Champion</th><th class="num">Score</th><th class="num">vs previous</th><th class="num">Held</th><th></th></tr>${tl.map(chRow).join('')}</table></div>`:'<div class="empty">No champion yet. A model becomes champion when it passes every gate, full dataset included.</div>'}</div>`;
 h+=`<div class="card section"><h2>Next champion</h2>${ovPipeline(true)}${chCandidates()}</div>`;
 return h;
}

// side-by-side row: this champion, the previous one and the change (lower is better for time, cost and errors)
function chCmp(label,a,b,fmt,lower,diffFmt){
 const d=a!=null&&b!=null?a-b:null,good=d==null||d===0?'':((lower?d<0:d>0)?'pos':'neg');
 return `<tr><td class="sub">${label}</td><td class="num"><b>${a!=null?fmt(a):'—'}</b></td><td class="num">${b!=null?fmt(b):'—'}</td><td class="num ${good}">${d==null?'—':(d>0?'+':d<0?'−':'')+(diffFmt||fmt)(Math.abs(d))}</td></tr>`;
}
function chNeighbour(label,e,more){
 if(!e)return '';
 return `<a class="chnb" href="${chLink(e.id)}"><span class="sub">${label}</span><b class="clamp1">${esc(e.variant||e.label||e.id)}</b><span class="sub">${e.score!=null?pct(e.score)+' · n '+e.n+' · ':''}${e.t?stamp(e.t):''}${more||''}</span></a>`;
}
function vChampion(name){
 const st=S.state,d=S.champ&&S.champ.key===name?S.champ.data:null;
 const back='<a class="back" href="#champions">← Champions</a>';
 if(!d){
  const known=(st.timeline||[]).some(e=>e.id===name||e.model===name);
  return topbar(known?name:'Champion not found')+back+`<div class="card empty">${known?'Loading':'No champion with this id. Open one from the Champions list.'}</div>`;
 }
 const e=d.entry,m=d.record||{},hill=d.hill,c=d.cand,b=d.base,pe=d.previous_entry,nx=d.next_entry,nt=d.notes||{};
 const title=e.label||e.variant||name;
 const slice=chTrack(e.track_label);
 let h=topbar(title)+back;
 // header and headline
 const head=e.delta!=null?`<div class="chbig ${e.delta>0?'pos':e.delta<0?'neg':''}">${pts(e.delta)}<small> pts</small></div><div class="sub">over ${esc(e.prev_label||e.prev_id)} · ${esc(slice)} · n ${e.n} · ${pct(e.base_score)} → ${pct(e.score)}</div>`
  :`<div class="chbig sub">${e.prev_id?'No shared run':'First'}</div><div class="sub">${e.prev_id?`${esc(e.prev_label||e.prev_id)} has no run on ${esc(slice)}, so there is no like-for-like number`:`Nothing came before it on ${esc(slice)}`}</div>`;
 h+=`<div class="card"><div class="hero"><div class="main">
  <div class="row" style="display:flex;gap:8px;flex-wrap:wrap">${chKind(e)}${d.current?'<span class="chip champion">current champion</span>':''}<span class="chip">${e.seeded?'seeded as baseline':'promoted '+ago(e.t)}</span>${d.hill_name&&hill?`<a class="chip" href="#hill/${encodeURIComponent(d.hill_name)}">${esc(hill.title||d.hill_name)}</a>`:''}</div>
  <h2>${esc(title)}</h2>${m.change?`<p class="desc">${esc(m.change)}</p>`:''}
  ${m.links?`<div class="links" style="margin-top:10px">${Object.entries(m.links).map(([k,v])=>`<a href="${esc(v)}" target="_blank" rel="noopener">${esc(k)} ↗</a>`).join('')}</div>`:''}</div>
  <div class="chhead">${head}</div></div></div>`;
 // what it did better than the previous champion
 h+=`<div class="card section"><h2>${e.prev_id?`Better than ${esc(e.prev_label||e.prev_id)}`:'Against the previous champion'}${e.prev_id?`<span class="r"><a href="${chLink(e.prev_id)}">previous champion →</a></span>`:''}</h2>`;
 if(c&&b){
  h+=`<div class="scroll"><table class="chcmp"><tr><th>${esc(slice)} · n ${c.n}${b.n!==c.n?' / '+b.n:''}</th><th class="num">${esc(c.variant||title)}</th><th class="num">${esc(b.variant||e.prev_label||'previous')}</th><th class="num">Change</th></tr>
   ${chCmp('Score',c.score,b.score,pct,false,x=>(100*x).toFixed(1)+' pts')}${chCmp('p50 latency',c.p50,b.p50,secs,true)}${chCmp('Cost per example',c.cost,b.cost,money,true)}${chCmp('Errors',c.errors,b.errors,x=>String(x),true)}
   <tr><td class="sub">Run</td><td class="num sub">${c.t?stamp(c.t):'—'}</td><td class="num sub">${b.t?stamp(b.t):'—'}</td><td></td></tr></table></div>`;
 }else if(c){
  h+=`<p class="sub">${e.prev_id?'The previous champion has no run on this eval set to compare with.':'There is no earlier champion to compare with.'}</p><div class="scroll"><table class="chcmp"><tr><th>${esc(slice)} · n ${c.n}</th><th class="num">${esc(title)}</th></tr>${[['Score',pct(c.score)],['p50 latency',secs(c.p50)],['Cost per example',money(c.cost)],['Errors',c.errors!=null?c.errors:'—']].map(([k,v])=>`<tr><td class="sub">${k}</td><td class="num"><b>${v}</b></td></tr>`).join('')}</table></div>`;
 }else h+='<p class="sub">No scored run is recorded for this champion.</p>';
 const rows=(d.vs_previous||[]).filter(r=>r.base_task);
 if(d.paired&&!rows.length){const r=d.paired;h+=`<div class="chpair"><span class="sub">Paired on ${r.n} shared examples</span>${ciBar(Object.assign({state:r.lo>0?'pass':r.hi<0?'fail':'pending',threshold:0},r))}<span class="num"><b class="${r.delta>0?'pos':r.delta<0?'neg':''}">${pts(r.delta)}</b> pts · 90% CI ${pts(r.lo)} to ${pts(r.hi)} · ${r.wins} gained / ${r.losses} lost</span></div>`}
 if(rows.length)h+=`<h3 class="chsub">Paired, example by example</h3><div class="scroll"><table><tr><th>Eval set</th><th class="num">n</th><th class="num">This</th><th class="num">Previous</th><th class="num">Δ pts</th><th>90% CI</th><th class="num">Gained / lost</th></tr>${rows.map(r=>`<tr class="click" onclick="location.hash='task/${encodeURIComponent(r.cand_task)}'"><td>${esc(short(r.slice))}<div class="sub">${esc(r.kind||'')}</div></td><td class="num">${r.n}</td><td class="num">${pct(r.cand)}</td><td class="num">${pct(r.base)}</td><td class="num ${r.delta>0?'pos':r.delta<0?'neg':''}"><b>${pts(r.delta)}</b></td><td>${ciBar(Object.assign({state:r.delta>0?'pass':'fail',threshold:0},r))}</td><td class="num">${r.wins} / ${r.losses}</td></tr>`).join('')}</table></div>`;
 if(c&&b&&!d.paired&&!rows.length)h+='<p class="sub chnote">Only aggregate scores were recorded for these two runs, so there is no per-example comparison or confidence interval.</p>';
 h+='</div>';
 // what changed, the hill, evidence and caveats
 const facts=[['Variant',e.variant],['Agent',nt.agent],['Cohort',nt.cohort_label],['Run date',nt.date],['Evidence',nt.evidence],['Experiment',nt.experiment_code],['Scored',nt.scored!=null?`${nt.correct??'?'} correct of ${nt.scored}`:null]].filter(x=>x[1]);
 h+=`<div class="card section"><h2>What changed</h2>${m.change?`<p class="desc">${esc(m.change)}</p>`:''}${m.reason&&m.status!=='champion'?`<p class="desc">${esc(m.reason)}</p>`:''}${!m.change&&!facts.length?'<p class="sub">No change description was recorded.</p>':''}
  ${facts.length?`<div class="chfacts">${facts.map(([k,v])=>`<div><span class="sub">${k}</span><b title="${esc(v)}">${esc(v)}</b></div>`).join('')}</div>`:''}
  ${nt.description&&nt.description!==m.change?`<p class="sub">${esc(nt.description)}</p>`:''}</div>`;
 if(hill)h+=`<div class="card section"><h2>Hill it targeted</h2><p class="desc"><a href="#hill/${encodeURIComponent(d.hill_name)}"><b>${esc(hill.title||d.hill_name)}</b></a>${hill.symptom?' — '+esc(hill.symptom):''}</p>${hill.problem?`<p class="sub">${esc(hill.problem)}</p>`:''}${hill.measure?`<p class="sub">Score 1 means: ${esc(hill.measure)}</p>`:''}</div>`;
 if((nt.notes||[]).length||nt.cost_note)h+=`<div class="card section"><h2>Recorded notes and caveats<span class="r">from the run's record</span></h2>${(nt.notes||[]).length?`<ul class="chlist">${nt.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul>`:''}${nt.cost_note?`<p class="sub">Cost: ${esc(nt.cost_note)}</p>`:''}</div>`;
 // neighbours on the timeline
 h+=`<div class="card section"><h2>In the line of champions<span class="r">${esc(slice)}</span></h2><div class="chnbs">${chNeighbour('Previous',pe&&pe.id?pe:null)}${chNeighbour('Next',nx,nx&&nx.delta!=null?' · '+pts(nx.delta)+' pts':'')}</div>
  <p class="sub" style="margin:12px 0 0">${nx?`Held ${e.held_s!=null?chSpan(e.held_s):'an unknown time'} until ${esc(nx.variant||nx.label)} took over.`:'Holds the title today.'}${!pe&&!e.prev_id?' It was the first.':''}</p></div>`;
 const g=d.gate;
 if(g&&g.rungs)h+=`<div class="card section"><h2>Gate passed</h2>${ladderPills(g)}</div>`;
 if((d.decisions||[]).length)h+=`<div class="card section"><h2>Decisions</h2><table>${d.decisions.map(x=>`<tr><td class="sub" style="width:120px">${x.t?stamp(x.t):''}</td><td><span class="chip ${x.kind==='rejected'?'rejected':x.kind==='promote'||x.kind==='champion'?'champion':''}">${esc(x.kind)}</span></td><td class="clamp2" title="${esc(x.reason||x.note||'')}">${esc(x.reason||x.note||(x.replaced?'replaced '+x.replaced:''))}</td></tr>`).join('')}</table></div>`;
 const ts=(d.tasks||[]).filter(t=>t.kind!=='historical_run');
 if(ts.length)h+=`<div class="card section"><h2>Tasks</h2><table>${ts.map(t=>`<tr class="click" onclick="location.hash='task/${encodeURIComponent(t.id)}'"><td><b>${esc(t.title)}</b><div class="sub">${esc(t.kind)}</div></td><td><span class="chip ${t.status}">${t.status}</span></td><td class="num">${t.score!=null?pct(t.score):''}</td></tr>`).join('')}</table></div>`;
 if(c)h+=`<p class="sub" style="margin-top:14px"><a href="#task/${encodeURIComponent(c.id)}">Open the run behind this champion →</a></p>`;
 return h;
}
