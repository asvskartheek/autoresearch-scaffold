// Models: every model the ledger knows (94 in a mature project), grouped by status and filterable by hill.
const MD_ORDER=['champion','candidate','retired','rejected','historical'];
const mdRank=s=>{const i=MD_ORDER.indexOf(s);return i<0?MD_ORDER.length:i};
const mdBest=pxBest;
// a card: poster first, then one line of title, verdict, best result and hill; reasons live on the model page
function mdRow([k,m]){
 const b=mdBest(k),st=S.state,hill=st.hills[m.hill],t=m.title||k;
 return `<a class="mdcard" href="#model/${encodeURIComponent(k)}">${posterThumb('model',k)}
  <div class="mdt clamp1" title="${esc(t)}">${esc(t)}</div>
  <div class="mdm"><span class="chip ${m.status}">${esc(m.status)}</span>${b?`<b data-tip='${esc(JSON.stringify([t,pct(b.score)+' on n '+b.n,b.where]))}'>${pct(b.score)}</b><span class="sub">n ${b.n}</span>`:'<span class="sub">no run</span>'}${hill?`<span class="sub mdh clamp1" title="${esc(hill.title)}">${esc(hill.title)}</span>`:''}</div></a>`;
}
function vModels(){
 const st=S.state,all=Object.entries(st.models).sort((a,b)=>(mdRank(a[1].status)-mdRank(b[1].status))||((b[1].created||0)-(a[1].created||0)));
 if(!all.length)return topbar('Models')+'<div class="card empty">No models yet. <code>arx model</code> registers the first.</div>';
 const cnt={};all.forEach(([k,m])=>cnt[m.status]=(cnt[m.status]||0)+1);
 const stats=Object.keys(cnt).sort((a,b)=>mdRank(a)-mdRank(b));
 const hills=[...new Set(all.map(([k,m])=>m.hill).filter(Boolean))],hf=S.mh&&hills.includes(S.mh)?S.mh:'';
 const f=S.mf&&cnt[S.mf]?S.mf:'all',inHill=hf?all.filter(([k,m])=>m.hill===hf):all,ms=f==='all'?inHill:inHill.filter(([k,m])=>m.status===f);
 let h=topbar('Models')+`<div class="card section"><div class="tabs">${[['all',inHill.length],...stats.map(s=>[s,inHill.filter(([k,m])=>m.status===s).length])].map(([s,n])=>`<button class="${s===f?'on':''}" onclick="S.mf='${s}';render()">${s}<small>${n}</small></button>`).join('')}</div>
  ${hills.length?`<div class="filters"><select onchange="S.mh=this.value;render()" aria-label="Hill"><option value="">All hills</option>${hills.map(x=>`<option value="${esc(x)}"${x===hf?' selected':''}>${esc(clip(st.hills[x]?.title||x,60))}</option>`).join('')}</select></div>`:''}`;
 if(!ms.length)h+='<div class="empty">No models match</div>';
 else if(f==='all'){
  const gr={};ms.forEach(x=>(gr[x[1].status]=gr[x[1].status]||[]).push(x));
  h+=Object.keys(gr).sort((a,b)=>mdRank(a)-mdRank(b)).map(s=>`<details class="mdgrp"${gr[s].length<=24||s!=='historical'?' open':''}><summary><span class="chip ${s}">${esc(s)}</span><span class="sub">${gr[s].length} model${gr[s].length>1?'s':''}</span></summary><div class="mdgrid">${gr[s].map(mdRow).join('')}</div></details>`).join('');
 }else h+=`<div class="mdgrid">${ms.map(mdRow).join('')}</div>`;
 return h+'</div>';
}
const clip=(s,n)=>{s=String(s||'');return s.length>n?s.slice(0,n-1)+'…':s};

// ancestors (nearest first) and direct children; a cycle in bad parent ids ends the walk
function mdLineage(name){
 const ms=S.state.models,up=[],seen=new Set([name]);
 for(let p=ms[name]?.parent;p&&!seen.has(p);p=ms[p]?.parent){seen.add(p);up.push(p)}
 return {up,down:Object.keys(ms).filter(k=>ms[k].parent===name&&k!==name)};
}
function mdLine(k,note){
 const m=S.state.models[k];
 return `<a class="mdln" href="#model/${encodeURIComponent(k)}"><span class="chip ${m?m.status:''}">${esc(m?m.status:'unknown')}</span><b class="clamp1" title="${esc(m?.title||k)}">${esc(m?.title||k)}</b>${note?`<span class="sub">${esc(note)}</span>`:''}</a>`;
}
function vModel(name){
 const st=S.state,m=st.models[name];if(!m)return topbar('Model not found')+'<a class="back" href="#models">← Models</a><div class="card empty">No model with this id.</div>';
 const g=st.gates[name],hill=st.hills[m.hill],lin=mdLineage(name),tl=(st.timeline||[]).find(e=>e.kind==='official'&&e.id===name);
 const evs=st.tasks.filter(t=>t.model===name&&t.kind!=='historical_run').slice(0,30);
 const decs=(st.decisions||[]).filter(d=>d.model===name);
 const bst=mdBest(name),why=[m.change&&['Change',m.change],m.reason&&[m.status==='rejected'?'Why rejected':'Note',m.reason]].filter(Boolean);
 let h=topbar(m.title||name)+`<a class="back" href="#models">← Models</a><div class="card mdhero">${posterBig('model',name)}
  <div class="mdfacts"><div class="row" style="display:flex;gap:8px;flex-wrap:wrap"><span class="chip ${m.status}">${esc(m.status)}</span>${tl?`<a class="chip champion" href="${chLink(name)}">champion page →</a>`:''}${m.parent?`<a class="chip" href="#model/${encodeURIComponent(m.parent)}" title="${esc(m.parent)}">from ${esc(clip(st.models[m.parent]?.title||m.parent,40))}</a>`:''}${hill?`<a class="chip" href="#hill/${encodeURIComponent(m.hill)}" title="${esc(hill.title)}">${esc(clip(hill.title,50))}</a>`:''}</div>
  <h2 class="clamp1" title="${esc(m.title||name)}">${esc(m.title||name)}</h2>${m.title&&m.title!==name?`<div class="sub clamp1" title="${esc(name)}">${esc(name)}</div>`:''}
  <div class="kv mdkv">${bst?`<div><span>Best result</span><b>${pct(bst.score)}</b></div><div><span>n</span><b>${bst.n}</b></div><div><span>Runs</span><b>${bst.count}</b></div>`:'<div><span>Runs</span><b>0</b></div>'}</div>
  ${bst?`<div class="sub clamp1" title="${esc(bst.where)}">${esc(bst.where)}</div>`:''}
  ${g?ladderPills(g):''}
  ${m.links?`<div class="links" style="margin-top:10px">${Object.entries(m.links).map(([k,v])=>`<a href="${esc(v)}" target="_blank" rel="noopener">${esc(k)} ↗</a>`).join('')}</div>`:''}
  ${why.length?`<details class="mdwhy"><summary>${m.status==='rejected'&&m.reason?'Why rejected':'Details'}</summary>${why.map(([a,t])=>`<p class="desc">${esc(t)}</p>`).join('')}</details>`:''}</div></div>`;
 const rr=(st.runs||[]).filter(r=>r.model===name).reverse();
 if(rr.length){
  const T=Object.fromEntries((st.tracks||[]).map(t=>[t.id,t.label]));
  h+=`<div class="card section"><h2>Runs<span class="r">${rr.length}</span></h2><div class="scroll"><table><tr><th>Run</th><th>Eval set</th><th class="num">Score</th><th class="num">n</th><th class="num">p50</th><th class="num">When</th></tr>${rr.map(r=>`<tr class="click" onclick="location.hash='task/${encodeURIComponent(r.id)}'"><td><b class="clamp1" title="${esc(r.variant||r.label)}">${esc(r.variant||r.label)}</b>${r.evidence?`<div class="sub">${esc(r.evidence)}</div>`:''}</td><td class="sub"><span class="clamp1" title="${esc(T[r.track]||r.slice||'')}">${esc(T[r.track]||r.slice||'—')}</span></td><td class="num"><b>${pct(r.score)}</b></td><td class="num">${r.n}</td><td class="num">${secs(r.p50)}</td><td class="num sub">${r.t?stamp(r.t):'—'}</td></tr>`).join('')}</table></div></div>`;
 }else h+='<div class="card section"><h2>Runs</h2><div class="empty">No scored run recorded for this model</div></div>';
 h+=`<div class="card section"><h2>Lineage</h2>${lin.up.length||lin.down.length?`<div class="mdlin">${lin.up.slice().reverse().map((k,i)=>mdLine(k,i===0&&lin.up.length>1?'oldest known ancestor':'')).join('')}<div class="mdln cur"><span class="chip ${m.status}">${esc(m.status)}</span><b>${esc(m.title||name)}</b><span class="sub">this model</span></div>${lin.down.slice(0,12).map(k=>mdLine(k,'child')).join('')}${lin.down.length>12?`<span class="sub">+${lin.down.length-12} more children</span>`:''}</div>`:'<div class="empty">No parent and no children</div>'}</div>`;
 if(hill)h+=`<div class="card section"><h2>Hill</h2><p class="desc"><a href="#hill/${encodeURIComponent(m.hill)}"><b>${esc(hill.title)}</b></a>${hill.symptom?' — '+esc(hill.symptom):''}</p>${hill.problem?`<p class="sub">${esc(hill.problem)}</p>`:''}</div>`;
 if(g&&!g.error){
  h+=`<div class="card section"><h2>Gate<span class="r">vs ${esc(g.champion||'—')}</span></h2><div class="scroll"><table><tr><th>Rung</th><th>Eval set</th><th>Rule</th><th class="num">${esc(name)}</th><th class="num">Champion</th><th class="num">Δ pts</th><th>90% CI</th><th class="num">W / L</th><th>State</th></tr>`;
  for(const r of g.rungs){
   if(!r.checks.length){h+=`<tr><td><span class="rung ${r.status}">${esc(r.rung)}</span></td><td colspan="8" class="sub">${r.status}</td></tr>`;continue}
   r.checks.forEach((c,i)=>{h+=`<tr ${c.cand_task?`class="click" onclick="location.hash='task/${encodeURIComponent(c.cand_task)}'"`:''}><td>${i?'':`<span class="rung ${r.status}">${esc(r.rung)}</span>`}</td><td style="white-space:nowrap">${esc(short(c.slice))}<div class="sub">n ${c.n??st.slices[c.slice]?.n??''}</div></td><td class="sub" style="white-space:nowrap">${c.rule==='better'?'better':'≥ '+pts(c.threshold)}</td><td class="num">${pct(c.cand)}</td><td class="num">${pct(c.base)}</td><td class="num ${c.delta>0?'pos':c.delta<0?'neg':''}">${pts(c.delta)}</td><td>${ciBar(c)}</td><td class="num">${c.wins!=null?c.wins+' / '+c.losses:''}</td><td><span class="chip ${c.state}">${c.state.replace('_',' ')}</span>${c.noisy?' <span class="chip">noisy</span>':''}</td></tr>`});
  }
  h+=`</table></div>${g.next?.length?`<pre>${g.next.map(n=>`# ${n.model} on ${n.slice}`).join('\n')}</pre>`:''}</div>`;
 }
 if(decs.length)h+=`<div class="card section"><h2>Decisions</h2><table>${decs.map(d=>`<tr><td class="sub" style="width:120px">${d.t?stamp(d.t):''}</td><td><span class="chip ${d.kind==='rejected'?'rejected':d.kind==='promote'||d.kind==='champion'?'champion':''}">${esc(d.kind)}</span></td><td>${esc(d.reason||d.note||(d.replaced?'replaced '+d.replaced:''))}</td></tr>`).join('')}</table></div>`;
 if(evs.length)h+=`<div class="card section"><h2>Tasks</h2><table>${evs.map(t=>`<tr class="click" onclick="location.hash='task/${encodeURIComponent(t.id)}'"><td><b>${esc(t.title)}</b><div class="sub">${esc(t.kind)} · ${ago(t.updated)}</div></td><td><span class="chip ${t.status}">${t.status}</span></td><td class="num">${t.summary?.score!=null?pct(t.summary.score):''}</td></tr>`).join('')}</table></div>`;
 return h;
}
