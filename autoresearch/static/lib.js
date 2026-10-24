const S={ex:{},state:null,detail:null,ok:true,lbDataset:null,lbSlice:null,archiveKind:'all'};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>x==null?'—':(100*x).toFixed(1)+'%';
const pts=x=>x==null?'—':((x>0?'+':'')+(100*x).toFixed(1));
const money=x=>x==null?'—':(x<0.01?'$'+x.toFixed(4):'$'+x.toFixed(3));
const secs=x=>x==null?'—':(x<10?x.toFixed(2):x.toFixed(1))+'s';
const ago=t=>{if(!t)return '—';const d=(S.state?.now||Date.now()/1000)-t;if(d<60)return Math.max(0,Math.round(d))+'s ago';if(d<3600)return Math.round(d/60)+'m ago';if(d<86400)return Math.round(d/3600)+'h ago';return Math.round(d/86400)+'d ago'};
const dur=(a,b)=>{const d=(b||S.state?.now||Date.now()/1000)-a;return d<60?Math.round(d)+'s':d<3600?Math.round(d/60)+'m':(d/3600).toFixed(1)+'h'};
const left=s=>s<60?Math.round(s)+'s':s<3600?Math.round(s/60)+'m':Math.floor(s/3600)+'h '+Math.round(s%3600/60)+'m';
const clock=t=>new Date(t*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
const num=(v,p=3)=>v===0?'0':Math.abs(v)>=1000?v.toFixed(0):Math.abs(v)>=1?v.toFixed(p):Math.abs(v)<1e-3?v.toExponential(1):v.toPrecision(p);
const fmtv=v=>typeof v!=='number'?esc(v):num(v);
const short=s=>String(s||'').split('/').slice(1).join('/')||s;
const ICON={
 over:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
 wb:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7h16M4 12h10M4 17h6"/><circle cx="18" cy="16" r="3"/></svg>',
 models:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M6 8.5v7M8.3 7l7.5 4M8.3 17l7.5-4"/></svg>',
 hills:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 19l6-10 4 6 3-4 5 8z"/></svg>',
 slices:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>',
 champs:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M7 4h10v5a5 5 0 01-10 0zM7 6H4v2a3 3 0 003 3M17 6h3v2a3 3 0 01-3 3M12 14v4M8 20h8"/></svg>',
 archive:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v10h14V9M10 13h4"/></svg>'};
const ROUTES=[['goals','Goals','over'],['overview','Overview','over'],['workbench','Workbench','wb'],['champions','Champions','champs'],['models','Models','models'],['hills','Hills','hills'],['slices','Eval sets','slices'],['archive','Archive','archive']];

function route(){const h=location.hash.slice(1)||'overview';const [r,...rest]=h.split('/');return {r,arg:decodeURIComponent(rest.join('/'))}}
const active=()=>S.state.tasks.filter(t=>t.status==='running'||t.status==='stalled');
const archived=()=>S.state.tasks.filter(t=>t.status!=='running'&&t.status!=='stalled');
const isLive=t=>t&&(t.status==='running'||t.status==='stalled');
const byId=id=>S.state.tasks.find(t=>t.id===id);
const kids=id=>S.state.tasks.filter(t=>t.parent===id).sort((a,b)=>(isLive(b)-isLive(a))||(b.created-a.created));
// every descendant, depth-first, with its depth; a guard stops cycles from bad parent ids
function tree(id,depth=0,seen=new Set([id])){return kids(id).filter(k=>!seen.has(k.id)&&seen.add(k.id)).flatMap(k=>[[k,depth],...tree(k.id,depth+1,seen)])}

function renderNav(){
 const {r}=route();const st=S.state;
 const navOn={task:active().some(t=>t.id===route().arg)?'workbench':'archive',model:'models',hill:'hills',champion:'champions'}[r]||r;
 const counts={workbench:st?active().length:0,hills:st?Object.values(st.hills).filter(h=>h.status==='open').length:0};
 $('#nav').innerHTML=`<div class="brand"><svg width="26" height="26" viewBox="0 0 26 26" fill="none" stroke="#fff" stroke-width="1.6"><rect x="1" y="1" width="24" height="24" rx="7" opacity=".5"/><path d="M6 17l4.5-6 3.5 4 6-8"/></svg>Observatory</div>`+
 ROUTES.map(([k,l,i])=>`<a href="#${k}" class="${navOn===k?'on':''}">${ICON[i]}${l}${counts[k]?`<span class="count">${counts[k]}</span>`:''}</a>`).join('')+
 (st?`<div class="foot"><b>${esc(st.config.name)}</b>${Object.keys(st.models).length} models · ${Object.keys(st.hills).length} hills</div>`:'');
}
function topbar(title){if(S.state)document.title=`${S.state.config.name||'Project'} · Observatory`;return `<header class="top"><div><h1>${esc(title)}</h1>${S.state?`<div class="sub" title="${esc(S.state.project?.root||'')}">${esc(S.state.config.name||'')}</div>`:''}</div><div class="live"><span class="dot ${S.ok?'':'off'}"></span>${S.ok?clock(S.state.now):'Offline'}</div></header>`}

// ---------- charts
function lineChart(series,{h=180,y0=null,ref=null,pctAxis=false,xLabel='step',dots=false}={}){
 // series: [{name,color,pts:[[x,y]...]}]
 const all=series.flatMap(s=>s.pts).filter(p=>p[1]!=null&&isFinite(p[1]));
 if(all.length<1)return '<div class="empty">No points yet</div>';
 const W=520,H=h,L=50,R=12,T=10,B=24;
 let xs=all.map(p=>p[0]),ys=all.map(p=>p[1]);if(ref!=null)ys.push(ref);
 let x0=Math.min(...xs),x1=Math.max(...xs);if(x1===x0)x1=x0+1;
 let lo=y0??Math.min(...ys),hi=Math.max(...ys);if(hi===lo){hi+=Math.abs(hi)*.1||1;lo-=Math.abs(lo)*.1||0}
 const pad=(hi-lo)*.06;if(y0==null)lo-=pad;hi+=pad;
 const X=x=>L+(x-x0)/(x1-x0)*(W-L-R),Y=y=>T+(1-(y-lo)/(hi-lo))*(H-T-B);
 const ticks=[0,.25,.5,.75,1].map(f=>lo+f*(hi-lo));
 const tl=v=>pctAxis?Math.round(v*100)+'%':num(v,2);
 let g=ticks.map(v=>`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--border)"/><text x="${L-6}" y="${Y(v)+3.5}" text-anchor="end">${tl(v)}</text>`).join('');
 g+=`<text x="${L}" y="${H-6}">${Math.round(x0)}</text><text x="${W-R}" y="${H-6}" text-anchor="end">${Math.round(x1)} ${xLabel}</text>`;
 if(ref!=null)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(ref)}" y2="${Y(ref)}" stroke="var(--amber)" stroke-dasharray="4 4"/>`;
 for(const s of series){const p=s.pts.filter(p=>p[1]!=null&&isFinite(p[1]));if(!p.length)continue;
  if(!s.dots)g+=`<path d="${p.map((q,i)=>(i?'L':'M')+X(q[0]).toFixed(1)+' '+Y(q[1]).toFixed(1)).join('')}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round"/>`;
  for(const q of (p.length<=40||s.dots?p:[p[p.length-1]]))g+=`<circle cx="${X(q[0])}" cy="${Y(q[1])}" r="${s.dots?3:3.5}" opacity="${s.dots?.75:1}" fill="${s.color}"/>`}
 return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">${g}</svg>`;
}
function spark(y,color='var(--blue)'){
 if(!y||y.length<2)return '';const W=300,H=36,lo=Math.min(...y),hi=Math.max(...y),r=hi-lo||1;
 return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="36" preserveAspectRatio="none"><path d="${y.map((v,i)=>(i?'L':'M')+(i/(y.length-1)*W).toFixed(1)+' '+(H-3-(v-lo)/r*(H-6)).toFixed(1)).join('')}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}
function ciBar(c){
 if(c.delta==null)return '';const span=Math.max(.05,Math.abs(c.lo),Math.abs(c.hi),Math.abs(c.threshold||0))*1.15;
 const P=v=>(50+v/span*50).toFixed(1)+'%';
 return `<div class="ci ${c.state}"><div class="axis"></div><div class="zero" style="left:${P(0)}"></div>${c.threshold?`<div class="thr" style="left:${P(c.threshold)}"></div>`:''}<div class="span" style="left:${P(c.lo)};width:calc(${P(c.hi)} - ${P(c.lo)})"></div><div class="pt" style="left:${P(c.delta)}"></div></div>`;
}

// ---------- shared bits
const ladderPills=g=>!g||g.error?'':`<div class="ladder">${g.rungs.map(r=>`<span class="rung ${r.status}">${esc(r.rung)}</span>`).join('')}</div>`;
function fullScore(m){const st=S.state,ds=st.config.primary_dataset;return st.leaderboard[ds+'/full']?.[m]}
function kidRow([k,depth]){
 const pr=k.progress||{},sc=k.summary?.score??k.last?.running_score;
 const v=isLive(k)?[pr.total?`${pr.done}/${pr.total}`:'',sc!=null?pct(sc):'',k.eta?left(k.eta.eta_s):''].filter(Boolean).join(' · ')
  :k.kind==='eval'&&sc!=null?`${pct(sc)} · n ${k.summary?.n??pr.done}`:k.status;
 return `<a class="kid" href="#task/${encodeURIComponent(k.id)}" style="padding-left:${6+depth*16}px"><span class="sd ${k.status}"></span><span class="nm">${esc(k.title)}</span><span class="vl">${esc(v)}</span></a>`;
}
function noteLine(n){return n?`<div class="note ${n.level}"><span class="msg">${esc(n.msg)}</span><span class="when">${ago(n.t)}</span></div>`:''}
function taskCard(t){
 const pr=t.progress||{},f=pr.total?Math.min(1,pr.done/pr.total):null;
 const last=Object.entries(t.last||{}).filter(([k,v])=>typeof v==='number').slice(0,3);
 const sub=tree(t.id),live=sub.filter(([k])=>isLive(k)).length,shown=sub.filter(([k])=>isLive(k)).concat(sub.filter(([k])=>!isLive(k))).slice(0,Math.max(6,live));
 return `<div class="card wb ${t.status}" onclick="if(!event.target.closest('a'))location.hash='task/${encodeURIComponent(t.id)}'">
  <div class="row"><span class="chip ${t.status}">${t.status}</span><span class="chip">${esc(t.kind)}</span>${t.agent?`<span class="chip">${esc(t.agent)}</span>`:''}</div>
  <div class="t">${esc(t.title)}</div>
  ${t.model||t.slice?`<div class="sub">${[t.model,short(t.slice)].filter(Boolean).map(esc).join(' · ')}</div>`:''}
  ${t.description?`<div class="desc">${esc(t.description)}</div>`:''}
  ${noteLine(t.note)}
  ${t.spark?spark(t.spark.y,t.status==='stalled'?'var(--red)':'var(--blue)'):''}
  ${last.length?`<div class="kv">${last.map(([k,v])=>`<div><span>${esc(k)}</span><b>${fmtv(v)}</b></div>`).join('')}</div>`:''}
  ${f!=null?`<div class="prog"><i style="width:${(f*100).toFixed(1)}%"></i></div>`:''}
  ${sub.length?`<div class="kids"><div class="sub" style="margin-bottom:4px">${live} running · ${sub.length} sub-tasks</div>${shown.map(kidRow).join('')}${sub.length>shown.length?`<a class="kid sub" href="#task/${encodeURIComponent(t.id)}">+${sub.length-shown.length} more</a>`:''}</div>`:''}
  <div class="meta"><span>${pr.total?`${pr.done} / ${pr.total}`:''}${t.eta?` · ETA ${left(t.eta.eta_s)}`:''}</span><span>${dur(t.created)}${t.budget_s?' / '+left(t.budget_s):''} · beat ${ago(t.heartbeat)}</span></div></div>`;
}

// ---------- views
