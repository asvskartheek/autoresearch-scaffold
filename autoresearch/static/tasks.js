function vTask(id){
 const st=S.state,d=S.detail;
 const t=(d&&d.task.id===id)?d.task:st.tasks.find(x=>x.id===id);
 if(!t)return topbar('Not found');
 const isActive=t.status==='running'||t.status==='stalled';
 const pr=t.progress||{},sm=t.summary||{};
 let h=topbar(t.title)+`<a class="back" href="#${isActive?'workbench':'archive'}">← ${isActive?'Workbench':'Archive'}</a>`;
 h+=`<div class="card"><div class="hero"><div class="main"><div style="display:flex;gap:8px;flex-wrap:wrap"><span class="chip ${t.status}">${t.status}</span><span class="chip">${esc(t.kind)}</span>${t.model?`<a class="chip" href="#model/${encodeURIComponent(t.model)}">${esc(t.model)}</a>`:''}${t.slice?`<span class="chip">${esc(short(t.slice))} · ${st.slices[t.slice]?.n??''}</span>`:''}${t.agent?`<span class="chip">${esc(t.agent)}</span>`:''}${t.kind==='eval'&&t.status==='done'&&!t.complete?'<span class="chip fail">partial · not ranked</span>':''}</div>
  ${t.description?`<p class="desc" style="margin-top:12px">${esc(t.description)}</p>`:''}
  ${tkLinks(t.links)}</div>
  ${pr.total?ring(pr.done,pr.total):''}</div></div>`;
 const up=byId(t.parent),sub=tree(t.id);
 if(up||sub.length)h+=`<div class="card section"><h2>${sub.length?'Sub-tasks':'Part of'}<span class="r">${sub.length?sub.filter(([k])=>isLive(k)).length+' running · '+sub.length:''}</span></h2>${up?`<a class="kid" href="#task/${encodeURIComponent(up.id)}"><span class="sd ${up.status}"></span><span class="nm">↑ ${esc(up.title)}</span><span class="vl">${esc(up.status)}</span></a>`:''}<div class="kids" style="${up?'':'border:0;padding:0'}">${sub.slice(0,25).map(kidRow).join('')}${sub.length>25?`<div class="kid sub">+${sub.length-25} more</div>`:''}</div></div>`;
 // tiles
 const last=Object.entries(t.last||{}).filter(([k,v])=>typeof v==='number');
 const sc0=typeof sm.score==='number'?sm.score:(sm.n&&typeof sm.correct==='number'?sm.correct/sm.n:null),scored=sc0!=null&&sm.n;
 const tiles=t.kind==='eval'||scored?[['Score',pct(sc0??t.last?.running_score),sm.n?`${sm.correct??Math.round((sm.score||0)*sm.n)} / ${sm.n}`:'running'],['Cost / example',money(sm.cost),sm.cost_total!=null?money(sm.cost_total)+' total':sm.cost==null?'not recorded':''],['Latency p50',secs(sm.latency_p50),'p95 '+secs(sm.latency_p95)],['Errors',sm.errors??'—',sm.missing?sm.missing+' missing':'']]
  :[...last.slice(0,3).map(([k,v])=>[k,fmtv(v),'latest']),['Elapsed',dur(t.created,t.ended),'beat '+ago(t.heartbeat)]];
 if(t.eta)tiles.splice(tiles.length-1,1,['ETA',left(t.eta.eta_s),`${t.eta.per_min.toFixed(1)}/min · ~${clock(t.eta.finish_at)} · ${dur(t.created)} in`]);
 h+=`<div class="grid g4 section">${tiles.map(([k,v,s])=>`<div class="card tile"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${esc(s)}</div></div>`).join('')}</div>`;
 h+=tkTrack(t)+tkRecord(t);
 if(!d||d.task.id!==id)return h+'<div class="empty">Loading…</div>';
 // vs champion
 const vc=d.vs_champion;
 if(vc&&vc.delta!=null)h+=`<div class="card section"><h2>vs ${esc(vc.model)}<span class="r">same ${vc.n} ids</span></h2><div class="grid g4"><div class="tile"><div class="k">Δ</div><div class="v ${vc.delta>0?'pos':vc.delta<0?'neg':''}">${pts(vc.delta)}</div><div class="s">pts</div></div><div class="tile"><div class="k">90% CI</div><div class="v" style="font-size:20px">${pts(vc.lo)} … ${pts(vc.hi)}</div><div style="margin-top:6px">${ciBar({...vc,state:vc.lo>0?'pass':vc.hi<0?'fail':''})}</div></div><div class="tile"><div class="k">Wins / losses</div><div class="v">${vc.wins} / ${vc.losses}</div></div><div class="tile"><div class="k">Champion</div><div class="v">${pct(vc.base)}</div><div class="s"><a href="#task/${encodeURIComponent(vc.task)}" style="color:var(--blue)">run ↗</a></div></div></div></div>`;
 // charts: every numeric series
 const keys=[...new Set(d.metrics.flatMap(m=>Object.keys(m).filter(k=>k!=='t'&&k!=='step'&&typeof m[k]==='number')))];
 const palette=['var(--blue)','var(--green)','var(--purple)','var(--amber)','var(--red)'];
 if(keys.length){
  const champBase=vc?.base??null;
  h+=`<div class="charts section">${keys.map((k,i)=>`<div class="card"><h2>${esc(k)}<span class="r">${fmtv(d.metrics.filter(m=>typeof m[k]==='number').slice(-1)[0]?.[k])}</span></h2>${lineChart([{name:k,color:palette[i%palette.length],pts:d.metrics.filter(m=>typeof m[k]==='number').map(m=>[m.step,m[k]])}],{pctAxis:k.includes('score')||k.includes('acc'),ref:k==='running_score'?champBase:null,xLabel:t.kind==='eval'?'examples':'step'})}</div>`).join('')}</div>`;
 }
 // per-example strip for evals
 if(d.rows?.length){
  const rows=d.rows.slice().sort((a,b)=>String(a.id).localeCompare(String(b.id),undefined,{numeric:true}));
  h+=`<div class="card section"><h2>Examples<span class="r">${rows.length}</span></h2><div style="display:flex;flex-wrap:wrap;gap:3px">${rows.map(r=>`<span title="${esc(r.id)} · ${r.error?'error':fmtv(r.score)}" style="width:12px;height:12px;border-radius:3px;background:${r.error?'var(--red)':`color-mix(in srgb,var(--green) ${Math.round(15+85*(r.score||0))}%,var(--soft))`}"></span>`).join('')}</div></div>`;
 }
 h+=`<div class="grid g2 section"><div class="card"><h2>Log<span class="r">${d.events.length}</span></h2>${d.events.length?`<div class="events">${d.events.slice().reverse().map(e=>`<div class="ev ${e.level}"><span class="when">${clock(e.t)}</span><span class="msg">${esc(e.msg)}</span></div>`).join('')}</div>`:'<div class="empty">No notes</div>'}</div>
 <div class="card"><h2>Setup</h2><div class="kv" style="flex-direction:column;gap:6px"><div><span>id</span><b>${esc(t.id)}</b></div><div><span>started</span><b>${new Date(t.created*1000).toLocaleString()}</b></div>${t.ended?`<div><span>ended</span><b>${new Date(t.ended*1000).toLocaleString()}</b></div>`:''}<div><span>host</span><b>${esc(t.host||'')} · pid ${esc(t.pid||'')}</b></div>${t.slice_hash?`<div><span>eval set hash</span><b>${esc(t.slice_hash)}</b></div>`:''}</div>
 ${tkKv(t.config)}${t.command?`<details style="margin-top:14px"><summary>Command</summary><pre>${esc(t.command)}</pre></details>`:''}</div></div>`;
 return h;
}
function ring(done,total){const f=Math.min(1,done/total),r=52,c=2*Math.PI*r;return `<svg width="130" height="130" viewBox="0 0 130 130" style="flex:none"><circle cx="65" cy="65" r="${r}" fill="none" stroke="var(--soft)" stroke-width="11"/><circle cx="65" cy="65" r="${r}" fill="none" stroke="var(--green)" stroke-width="11" stroke-linecap="round" stroke-dasharray="${c*f} ${c}" transform="rotate(-90 65 65)"/><text x="65" y="66" text-anchor="middle" style="font-size:26px;font-weight:650;fill:var(--ink)">${done}</text><text x="65" y="86" text-anchor="middle">/ ${total}</text></svg>`}


// ---------- non-eval tasks: what the ledger knows about them
const tkLabel=k=>{const x=String(k).replace(/_/g,' ');return x.charAt(0).toUpperCase()+x.slice(1)};
const tkIsUrl=v=>/^https?:\/\//.test(v);
// links are often local file paths: shown as text, only real URLs are hyperlinks
function tkLinks(l){
 const e=Object.entries(l||{});if(!e.length)return '';
 return `<div class="tklinks">${e.map(([k,v])=>tkIsUrl(v)?`<div><a href="${esc(v)}" target="_blank" rel="noopener">${esc(k)} ↗</a></div>`:`<div><span class="sub">${esc(k)}</span><code title="${esc(v)}">${esc(v)}</code></div>`).join('')}</div>`;
}
// scalar values as label/value rows; nested things are summarised by count, never dumped
function tkVal(v){
 if(v==null||v==='')return null;
 if(typeof v==='boolean')return v?'yes':'no';
 if(typeof v==='number')return Number.isInteger(v)?String(v):num(v);
 if(Array.isArray(v))return v.every(x=>typeof x!=='object')?v.join(', '):v.length+' items';
 if(typeof v==='object')return Object.keys(v).length+' fields';
 return String(v);
}
function tkKv(o,skip=[]){
 const e=Object.entries(o||{}).filter(([k])=>!skip.includes(k)).map(([k,v])=>[k,tkVal(v)]).filter(([k,v])=>v!=null);
 return e.length?`<div class="tkkv">${e.map(([k,v])=>`<div><span>${esc(tkLabel(k))}</span><b title="${esc(v)}">${esc(v)}</b></div>`).join('')}</div>`:'';
}
function tkTrack(t){
 const st=S.state,r=(st.runs||[]).find(x=>x.id===t.id);if(!r)return '';
 const tr=(st.tracks||[]).find(x=>x.id===r.track);if(!tr)return '';
 const rs=st.runs.filter(x=>x.track===r.track&&x.n>=20).sort((a,b)=>b.score-a.score||a.t-b.t);
 const rank=rs.findIndex(x=>x.id===r.id)+1,best=rs[0];
 const isFront=tr.frontier.some(f=>f.id===r.id);
 const row=(x,i)=>`<tr class="click ${x.id===r.id?'me':''}" onclick="location.hash='task/${encodeURIComponent(x.id)}'"><td class="sub">${i}</td><td>${esc(x.variant||x.label)}</td><td class="num">${pct(x.score)}</td><td class="sub nw">${tkWhen(x.t)}</td></tr>`;
 return `<div class="card section"><h2>Place on its eval set<span class="r"><a href="#champions" style="color:var(--blue)">${esc(chTrack(tr.label))} ↗</a></span></h2>
  <p class="desc">${rank?`<b>#${rank}</b> of ${rs.length} runs`:'Not ranked (n under 20)'} on ${esc(chTrack(tr.label))}, n ${tr.n}${isFront?'; it beat every earlier run when it ran':''}.${best&&best.id!==r.id?` Best there: <a href="#task/${encodeURIComponent(best.id)}" style="color:var(--blue)">${esc(best.variant||best.label)} ${pct(best.score)}</a>, ${pts(best.score-r.score)} pts above this.`:rank===1?' Best on this slice.':''}</p>
  ${rs.length>1?`<table>${rs.slice(0,8).map((x,i)=>row(x,i+1)).join('')}${rank>8?row(r,rank):''}</table>`:''}</div>`;
}
function tkRecord(t){
 if(t.kind==='eval')return '';
 const sm=t.summary||{},cr=sm.catalog_record,notes=cr?.notes||[];
 const hidden=['catalog_record','source_record_sha256','source_observed_at','imported_from','sha256','cohort_hash','new_provider_calls','registered_slice'];
 if(cr||sm.correct!=null)hidden.push('n','correct','errors','score');
 if(cr)hidden.push('dataset','cohort','evidence','score','n','correct','errors','latency_p50','latency_p95','latency_mean','cost');
 let h='';
 if(cr)h+=`<div class="card section"><h2>Original run<span class="r">${esc(sm.imported_from||'imported')}</span></h2>${tkKv({model:cr.model,agent:cr.agent,cohort:cr.cohort_label,date:cr.date,dataset:cr.dataset,evidence:cr.evidence,latency_basis:cr.latency_kind,cost_basis:cr.cost_kind,cost_note:cr.cost_note})}${notes.length?`<ul class="tknotes">${notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul>`:''}${cr.path?`<div class="tklinks"><div><span class="sub">Source file</span><code title="${esc(cr.path)}">${esc(cr.path)}</code></div></div>`:''}</div>`;
 const kv=tkKv(sm,hidden);
 if(kv)h+=`<div class="card section"><h2>Summary</h2>${kv}</div>`;
 return h;
}
