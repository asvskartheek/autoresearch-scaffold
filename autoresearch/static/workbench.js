// Workbench (live tasks) and Archive (everything that ended).
const AR={kind:'all',status:'all',model:'all',q:'',open:{}};
const tkWhen=t=>t?new Date(t*1000).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'';
const tkDay=t=>t?new Date(t*1000).toLocaleDateString([],{weekday:'short',month:'short',day:'numeric',year:'numeric'}):'Undated';
const tkHist=t=>t.kind==='historical_run'||t.kind==='historical_aggregate'||t.kind==='historical_catalog';
const tkModel=t=>t.summary?.catalog_record?.model||t.model||'';
const tkN=t=>t.summary?.n??null;
// when it happened: imports carry the original run date, everything else the time it ended
function tkTime(t){
 const d=t.summary?.catalog_record?.date;
 if(d){const x=Date.parse(d.replace(' ','T'));if(x)return x/1000}
 return t.ended||t.updated||t.created;
}

function vWorkbench(){
 // a running task whose parent is also running shows inside the parent's card, not as its own
 const a=active().filter(t=>!isLive(byId(t.parent))),live=a.filter(t=>t.status==='running'),dead=a.filter(t=>t.status==='stalled');
 const done=archived().filter(t=>t.ended).sort((x,y)=>y.ended-x.ended)[0];
 const empty=`<div class="card empty"><b>Nothing running</b>${done?`<div class="sub" style="margin-top:6px">Last finished: <a href="#task/${encodeURIComponent(done.id)}" style="color:var(--blue)">${esc(done.title)}</a> · ${esc(done.status)} ${ago(done.ended)}</div>`:''}</div>`;
 return topbar('Workbench')+(live.length?`<div class="cards">${live.map(taskCard).join('')}</div>`:empty)+
 (dead.length?`<div class="card section"><h2>Stalled<span class="r">${dead.length}</span></h2><table>${dead.map(t=>`<tr class="click" onclick="location.hash='task/${encodeURIComponent(t.id)}'"><td><b>${esc(t.title)}</b><div class="sub">${esc(t.kind)}${t.agent?' · '+esc(t.agent):''} · no heartbeat for ${dur(t.heartbeat)}</div><div class="sub">If it is dead, close it with <code>arx task resume ${esc(t.id)}</code> or <code>arx sweep</code>; if it is working, make it call <code>t.log()</code> again.</div></td><td class="num sub">beat ${ago(t.heartbeat)}</td></tr>`).join('')}</table></div>`:'');
}

function arSet(k,v){AR[k]=v;render();if(k==='q'){const i=$('#ar-q');if(i){i.focus();i.setSelectionRange(v.length,v.length)}}}
function arRow(t){
 const sc=t.summary?.score,n=tkN(t),hist=tkHist(t);
 const sub=[t.kind,hist?null:t.agent].filter(Boolean).join(' · ');
 return `<tr class="click" onclick="location.hash='task/${encodeURIComponent(t.id)}'"><td class="sub nw">${tkWhen(tkTime(t))}</td><td class="artt"><b>${esc(t.title)}</b><div class="sub">${esc(sub)}</div></td><td class="armd">${esc(tkModel(t))}</td><td class="armd">${esc(short(t.slice)||'')}</td><td><span class="chip ${t.status}">${esc(t.status)}</span>${t.kind==='eval'&&t.status==='done'&&!t.complete?' <span class="chip fail">partial</span>':''}</td><td class="num">${typeof sc==='number'?pct(sc):''}</td><td class="num sub">${n!=null&&typeof sc==='number'?'n '+n:''}</td></tr>`;
}
function arTable(rows){return `<div class="scroll"><table class="art"><tr><th>When</th><th>Task</th><th>Model</th><th>Eval set</th><th>Status</th><th class="num">Score</th><th class="num">n</th></tr>${rows.map(arRow).join('')}</table></div>`}
function arBatch(t){
 const p=byId(t.parent);
 return t.kind==='historical_aggregate'?'Historical aggregates':t.kind==='historical_catalog'?'Historical catalog':(p?p.title:'Historical runs');
}
function vArchive(){
 const all=archived(),q=AR.q.trim().toLowerCase();
 const opts=(f)=>{const c={};all.forEach(t=>{const v=f(t);if(v)c[v]=(c[v]||0)+1});return Object.entries(c).sort((a,b)=>b[1]-a[1])};
 const sel=(k,label,o)=>`<select onchange="arSet('${k}',this.value)"><option value="all">${label}</option>${o.map(([v,c])=>`<option value="${esc(v)}" ${AR[k]===v?'selected':''}>${esc(v.length>48?v.slice(0,47)+'…':v)} (${c})</option>`).join('')}</select>`;
 const rows=all.filter(t=>(AR.kind==='all'||t.kind===AR.kind)&&(AR.status==='all'||t.status===AR.status)&&(AR.model==='all'||tkModel(t)===AR.model)&&
  (!q||[t.title,t.description,tkModel(t),t.slice,t.agent,t.kind,t.summary?.catalog_record?.agent].some(v=>String(v||'').toLowerCase().includes(q))));
 const real=rows.filter(t=>!tkHist(t)).sort((a,b)=>tkTime(b)-tkTime(a)),hist=rows.filter(tkHist);
 const days=[];for(const t of real){const d=tkDay(tkTime(t));if(!days.length||days[days.length-1][0]!==d)days.push([d,[]]);days[days.length-1][1].push(t)}
 const batches={};hist.forEach(t=>{(batches[arBatch(t)]=batches[arBatch(t)]||[]).push(t)});
 let h=topbar('Archive')+`<div class="filters"><input id="ar-q" class="search" type="search" placeholder="Search tasks" value="${esc(AR.q)}" oninput="arSet('q',this.value)">${sel('kind','All kinds',opts(t=>t.kind))}${sel('status','All statuses',opts(t=>t.status))}${sel('model','All models',opts(tkModel).slice(0,60))}<span class="sub">${rows.length} of ${all.length}</span></div>`;
 if(!rows.length)return h+`<div class="card empty">${all.length?'No task matches':'Nothing has finished yet'}</div>`;
 h+=days.map(([d,ts])=>`<div class="card section"><h2>${esc(d)}<span class="r">${ts.length}</span></h2>${arTable(ts)}</div>`).join('');
 h+=Object.entries(batches).map(([b,ts])=>{ts.sort((x,y)=>tkTime(y)-tkTime(x));const k=b.replace(/[^\w ]/g,'');const sc=ts.filter(t=>typeof t.summary?.score==='number').length;
  return `<details class="card section sld" ${(AR.open[k]||q)?'open':''} ontoggle="AR.open['${k}']=this.open"><summary><span class="sldt">${esc(b)}</span><span class="sub">imported history · ${ts.length} tasks · ${sc} scored</span></summary>${arTable(ts)}</details>`}).join('');
 return h;
}
