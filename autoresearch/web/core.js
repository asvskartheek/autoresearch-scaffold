// arx dashboard core: state, formatting, the shell, and the shared components every view uses.
// Views live in views/<name>.js and register themselves in VIEWS; they return HTML strings built from S.state.
// Shared API (keep views on it so the screens read as one product):
//   page({title, crumbs, finding, acts, back})  the title row; crumbs also feed the top bar
//   panel(title, body, {meta, right, flush, cls}) a card with its header
//   kpis([[label, value, sub, href?]])          the divided KPI strip
//   pill(text, cls) / st(status, label?)         status marks; ladder(gate, {compact}) the gate track
//   meter(frac, {mark, cls}) / ciBar(check) / lineChart(series, opts) / spark(ys)
//   empty(title, hint) / table(head, rows)
const S={projects:[],ex:{},state:null,detail:null,hill:null,ok:true,lbDataset:null,lbSlice:null,archiveKind:'all',crumbs:[]};
const VIEWS={};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc=encodeURIComponent;
const DASH='<span class="dash">—</span>';

// ---------- formatting: honest zeros, a grey dash for missing, a sign on every change
const pct=x=>x==null?'—':(100*x).toFixed(1)+'%';
const pts=x=>x==null?'—':(x>0?'+':x<0?'−':'')+Math.abs(100*x).toFixed(1);
const money=x=>x==null?'—':x===0?'$0':(x<0.01?'$'+x.toFixed(4):'$'+x.toFixed(3));
const secs=x=>x==null?'—':(x<10?x.toFixed(2):x.toFixed(1))+'s';
const now=()=>S.state?.now||Date.now()/1000;
// one format app-wide: "26 Oct, 04:53", "2 min", "1 h 39 min", "3 d 4 h", "5 min ago"
const span=s=>{if(s==null||!isFinite(s))return '—';s=Math.max(0,s);
 if(s<60)return Math.round(s)+' s';if(s<3600)return Math.round(s/60)+' min';
 if(s<86400){const h=Math.floor(s/3600),m=Math.round(s%3600/60);return m===60?(h+1)+' h':h+' h'+(m?' '+m+' min':'')}
 const d=Math.floor(s/86400),h=Math.round(s%86400/3600);return d+' d'+(h&&h<24?' '+h+' h':'')};
const ago=t=>{if(!t)return '—';const d=now()-t;return d<10?'just now':span(d)+' ago'};
const dur=(a,b)=>span((b||now())-a);
const left=s=>span(s);
const clock=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
const stamp=t=>{if(!t)return '—';const d=new Date(t*1000),y=new Date(now()*1000).getFullYear();return d.toLocaleDateString('en-GB',{day:'numeric',month:'short',...(d.getFullYear()!==y?{year:'numeric'}:{})})+', '+clock(t)};
const num=(v,p=3)=>v===0?'0':Math.abs(v)>=1000?v.toLocaleString(undefined,{maximumFractionDigits:0}):Math.abs(v)>=1?v.toFixed(p):Math.abs(v)<1e-3?v.toExponential(1):v.toPrecision(p);
const fmtv=v=>typeof v!=='number'?esc(v):num(v);
const short=s=>String(s||'').split('/').slice(1).join('/')||s;
const plural=(n,w,ws)=>`${n} ${n===1?w:(ws||w+'s')}`;
const solved=r=>Math.round(r.score*r.n);
const firstLine=t=>String(t||'').split(/(?<=\.)\s/)[0];

// ---------- ledger queries
function route(){const h=location.hash.slice(1)||'overview';const [r,...rest]=h.split('/');return {r,arg:decodeURIComponent(rest.join('/'))}}
const isLive=t=>t&&(t.status==='running'||t.status==='stalled');
const active=()=>S.state.tasks.filter(isLive);
const archived=()=>S.state.tasks.filter(t=>!isLive(t));
const byId=id=>S.state.tasks.find(t=>t.id===id);
const kids=id=>S.state.tasks.filter(t=>t.parent===id).sort((a,b)=>(isLive(b)-isLive(a))||(b.created-a.created));
// every descendant, depth-first, with its depth; a guard stops cycles from bad parent ids
function tree(id,depth=0,seen=new Set([id])){return kids(id).filter(k=>!seen.has(k.id)&&seen.add(k.id)).flatMap(k=>[[k,depth],...tree(k.id,depth+1,seen)])}
function fullScore(m){const st=S.state;return st.leaderboard[st.config.primary_dataset+'/full']?.[m]}
const better=(a,b)=>S.state.config.higher_is_better===false?a<b:a>b;

// ---------- icons: 16px outline, 1.5 stroke
const I=(d,s=16)=>`<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON={
 overview:I('<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>'),
 workbench:I('<path d="M4 12h3l2-6 4 12 2-6h5"/>'),
 models:I('<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M6 8.5v7M8.3 7l7.5 4M8.3 17l7.5-4"/>'),
 hills:I('<path d="M3 19l6-10 4 6 3-4 5 8z"/>'),
 slices:I('<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'),
 questions:I('<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>'),
 learn:I('<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/>'),
 goals:I('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="0.6" fill="currentColor"/>'),
 papers:I('<path d="M7 3.5h7l4.5 4.5v12a.5.5 0 0 1-.5.5H7a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5z"/><path d="M14 3.5V8h4.5M9.5 12.5h6M9.5 16h6"/>'),
 search:I('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',14),
 archive:I('<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v10h14V9M10 13h4"/>'),
 ext:I('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',13),
 back:I('<path d="M15 6l-6 6 6 6"/>',14),
 menu:I('<path d="M4 7h16M4 12h16M4 17h16"/>',18),
 sun:I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
 moon:I('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
 copy:I('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',13)};
// the product's mark: a ladder (two rails, three rungs) in the accent
const MARK='<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="var(--accent)"/><path d="M8 18.5V5.5M16 18.5V5.5M8 15h8M8 11.5h8M8 8h8" stroke="var(--surface)" stroke-width="1.8" stroke-linecap="round"/></svg>';
const ROUTES=[['overview','Overview'],['learn','Brief'],['workbench','Workbench'],['goals','Goals'],['questions','Questions'],['models','Models'],['hills','Hills'],['papers','Papers'],['slices','Slices'],['archive','Archive']];
// the project this page serves: /p/<key>/ for a registered project, the server's own at /
const PKEY=(location.pathname.match(/^\/p\/([^/]+)/)||[])[1]&&decodeURIComponent(location.pathname.split('/')[2]);
const mn=k=>esc(S.state?.models?.[k]?.title||k||'—');  // a model reads by its title; the id stays in the URL
const paperOf=key=>{const ps=S.state.papers||{};return ps[key]||Object.values(ps).find(p=>p.hill===key)};
const paperUrl=p=>'papers/'+enc(p.name);  // relative, so /p/<key>/ serves another project's papers
const goalPaper=g=>Object.values(S.state.papers||{}).find(p=>p.goal===g);

// ---------- shell
function renderNav(){
 const {r,arg}=route(),st=S.state;
 const navOn={task:st&&isLive(byId(arg))?'workbench':'archive',model:'models',hill:'hills',goal:'goals'}[r]||r;
 const stalled=st?active().filter(t=>t.status==='stalled').length:0;
 const waiting=st?Object.values(st.papers||{}).reduce((a,p)=>a+(p.waiting||0),0):0;
 const counts=st?{workbench:active().length,goals:Object.values(st.goals||{}).filter(g=>g.status==='open').length,hills:Object.values(st.hills).filter(h=>h.status==='open').length,papers:waiting}:{};
 const tip={workbench:n=>plural(n,'task')+' running'+(stalled?', '+stalled+' stalled':''),goals:n=>plural(n,'open goal'),hills:n=>plural(n,'open hill'),papers:n=>plural(n,'comment')+' waiting for the agent'};
 setHTML($('#nav'),`<a class="brand" href="#overview">${MARK}<span>arx<span class="proj">${esc(st?.config?.name||'')}</span></span></a>`+
  ROUTES.map(([k,l])=>`<a class="nav ${navOn===k?'on':''}" href="#${k}" ${navOn===k?'aria-current="page"':''}>${ICON[k]}${l}${counts[k]?`<span class="count ${(k==='workbench'&&stalled)?'bad':k==='papers'?'hot':''}" title="${tip[k](counts[k])}">${counts[k]}</span>`:''}</a>`).join('')+
  (S.projects.length>1?`<div class="grp">Projects</div>`+S.projects.map(q=>{const on=q.key===PKEY||(!PKEY&&q.default);return `<a class="nav proj ${on?'on':''}" href="/p/${enc(q.key)}/" title="${esc(q.name)} · ${esc(q.root)}" ${on?'aria-current="true"':''}><span class="pdot ${q.error?'bad':q.running?'run':''}"></span><span class="ell">${esc(q.name)}</span>${q.waiting?`<span class="count hot" title="${plural(q.waiting,'comment')} waiting">${q.waiting}</span>`:q.running?`<span class="count" title="${plural(q.running,'task')} running">${q.running}</span>`:''}</a>`}).join(''):'')+
  (st?`<div class="foot"><b>${esc(st.champion||'No champion yet')}</b><span>${st.champion?'champion · ':''}${plural(Object.keys(st.models).length,'model')}</span></div>`:''));
}
function renderTop(){
 const dark=document.documentElement.dataset.theme==='dark'||(!document.documentElement.dataset.theme&&matchMedia('(prefers-color-scheme: dark)').matches);
 const c=S.crumbs.length?S.crumbs:[[ROUTES.find(([k])=>k===route().r)?.[1]||'Overview']];
 setHTML($('#top'),`<button class="iconbtn menu-btn" aria-label="Menu" onclick="$('#app').classList.toggle('nav-open')">${ICON.menu}</button>
 <nav class="crumbs" aria-label="Breadcrumb">${c.map(([l,h],i)=>i===c.length-1?`<b>${esc(l)}</b>`:`<a href="${h}">${esc(l)}</a><span class="sep">/</span>`).join('')}</nav>
 <div class="right"><span class="live" title="${S.ok?'Polling the ledger every 4s':'The dashboard server is not answering'}"><span class="dot ${S.ok?'':'off'}"></span>${S.ok?'Live':'Offline'}<span class="clk">${S.state&&S.ok?' · '+clock(S.state.now):''}</span></span>
 <button class="iconbtn" aria-label="Toggle theme" onclick="toggleTheme()">${dark?ICON.sun:ICON.moon}</button></div>`);
}
function toggleTheme(){
 const el=document.documentElement,dark=el.dataset.theme==='dark'||(!el.dataset.theme&&matchMedia('(prefers-color-scheme: dark)').matches);
 el.dataset.theme=dark?'light':'dark';try{localStorage.setItem('arx-theme',el.dataset.theme)}catch(e){}renderTop();render();
}

addEventListener('storage',e=>{if(e.key==='arx-theme'&&e.newValue){document.documentElement.dataset.theme=e.newValue;renderTop()}});
// swap an element's HTML only when it changed, keeping open <details>, focus and caret across the 4s poll
function setHTML(el,html){
 if(el._html===html)return false;el._html=html;
 const key=d=>d.querySelector('summary')?.textContent||'';
 const open=new Set([...el.querySelectorAll('details[open]')].map(key));
 const f=document.activeElement,fk=f&&el.contains(f)?(f.id||f.getAttribute('href')||f.name):null;
 const caret=fk&&'selectionStart' in f?[f.selectionStart,f.selectionEnd]:null;
 el.innerHTML=html;
 el.querySelectorAll('details').forEach(d=>{if(open.has(key(d)))d.open=true});
 if(fk){const n=[...el.querySelectorAll('[id],[href],[name]')].find(n=>(n.id||n.getAttribute('href')||n.name)===fk);if(n){n.focus({preventScroll:true});if(caret)try{n.setSelectionRange(...caret)}catch(e){}}}
 return true;
}

// ---------- shared components
// title row. crumbs: [[label, href], ...] ending at this page; finding: the one line under the title (HTML).
function page({title,crumbs,finding,acts,copy}){
 S.crumbs=crumbs||[];
 return `<div class="title"><div class="tt"><h1>${esc(title)}${copy?' '+copyBtn(copy):''}</h1>${finding?`<p class="finding">${finding}</p>`:''}</div>${acts?`<div class="acts">${acts}</div>`:''}</div>`;
}
function panel(title,body,{meta='',right='',flush=false,cls='',id=''}={}){
 return `<section class="card ${flush?'flush':''} ${cls}"${id?` id="${id}"`:''}>${title||right?`<div class="ph">${title?`<h2>${title}</h2>`:''}${meta?`<span class="meta">${meta}</span>`:''}${right?`<span class="r">${right}</span>`:''}</div>`:''}${body}</section>`;
}
function kpis(items){
 return `<div class="kpis" style="--n:${items.length}">${items.map(([k,v,s,href])=>`<div class="kpi"><div class="k">${esc(k)}</div>${href?`<a class="v" href="${href}">${v}</a>`:`<div class="v">${v}</div>`}<div class="s">${s||'&nbsp;'}</div></div>`).join('')}</div>`;
}
const pill=(t,c='')=>`<span class="pill ${esc(c)}">${esc(t)}</span>`;
const st=(s,l)=>`<span class="st ${esc(s)}">${esc(l??s)}</span>`;
const empty=(t,hint='')=>`<div class="empty"><b>${t}</b>${hint}</div>`;
function table(head,rows){return `<div class="tbl"><table><thead><tr>${head.map(h=>Array.isArray(h)?`<th class="${h[1]||''}">${h[0]}</th>`:`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
// the gate ladder: each rung a node on one track; passed track segments turn green
function ladder(g,{compact=false}={}){
 if(!g||g.error||!g.rungs?.length)return '';
 return `<span class="ladder ${compact?'compact':''}" title="${esc(g.rungs.map(r=>r.rung+': '+r.status).join(' · '))}">${g.rungs.map((r,i)=>`${i?`<i class="tr ${g.rungs[i-1].status==='pass'?'pass':''}"></i>`:''}<span class="rg ${esc(r.status)}"><i></i><span>${esc(r.rung)}</span></span>`).join('')}</span>`;
}
const meter=(f,{mark=null,cls=''}={})=>`<div class="meter ${cls}"><i style="width:${(100*Math.max(0,Math.min(1,f||0))).toFixed(1)}%"></i>${mark!=null?`<b style="left:${(100*mark).toFixed(1)}%"></b>`:''}</div>`;
function ciBar(c){
 if(c.delta==null)return '';const span=Math.max(.05,Math.abs(c.lo),Math.abs(c.hi),Math.abs(c.threshold||0))*1.15;
 const P=v=>(50+v/span*50).toFixed(1)+'%';
 return `<div class="ci ${c.state||''}" title="Δ ${pts(c.delta)} pts, 90% CI ${pts(c.lo)} to ${pts(c.hi)}"><div class="axis"></div><div class="zero" style="left:${P(0)}"></div>${c.threshold?`<div class="thr" style="left:${P(c.threshold)}"></div>`:''}<div class="span" style="left:${P(c.lo)};width:calc(${P(c.hi)} - ${P(c.lo)})"></div><div class="pt" style="left:${P(c.delta)}"></div></div>`;
}
// line chart: few faint gridlines, no legend for one series, the last point marked and labelled
function lineChart(series,{w=560,h=180,y0=null,ref=null,refLabel='',pctAxis=false,xLabel='step'}={}){
 const all=series.flatMap(s=>s.pts).filter(p=>p[1]!=null&&isFinite(p[1]));
 if(!all.length)return empty('No points yet');
 const W=w,H=h,L=44,R=14,T=12,B=22;
 const xs=all.map(p=>p[0]),ys=all.map(p=>p[1]);if(ref!=null)ys.push(ref);
 let x0=Math.min(...xs),x1=Math.max(...xs);if(x1===x0)x1=x0+1;
 let lo=y0??Math.min(...ys),hi=Math.max(...ys);if(hi===lo){hi+=Math.abs(hi)*.1||1;lo-=Math.abs(lo)*.1||0}
 const pad=(hi-lo)*.08;if(y0==null)lo-=pad;hi+=pad;
 const X=x=>L+(x-x0)/(x1-x0)*(W-L-R),Y=y=>T+(1-(y-lo)/(hi-lo))*(H-T-B);
 const tl=v=>pctAxis?Math.round(v*100)+'%':num(v,2);
 let g=[0,1/3,2/3,1].map(f=>lo+f*(hi-lo)).map(v=>`<line class="ax" x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text x="${L-8}" y="${Y(v)+3.5}" text-anchor="end">${tl(v)}</text>`).join('');
 g+=`<text x="${L}" y="${H-5}">${Math.round(x0)}</text><text x="${W-R}" y="${H-5}" text-anchor="end">${Math.round(x1).toLocaleString()} ${esc(xLabel)}</text>`;
 if(ref!=null)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(ref)}" y2="${Y(ref)}" stroke="var(--chart-3)" stroke-dasharray="4 4" stroke-width="1.5"/>${refLabel?`<text x="${W-R}" y="${Y(ref)-5}" text-anchor="end" style="fill:var(--chart-3)">${esc(refLabel)}</text>`:''}`;
 for(const s of series){const p=s.pts.filter(p=>p[1]!=null&&isFinite(p[1]));if(!p.length)continue;
  g+=`<path d="${p.map((q,i)=>(i?'L':'M')+X(q[0]).toFixed(1)+' '+Y(q[1]).toFixed(1)).join('')}" fill="none" stroke="${s.color||'var(--chart-1)'}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  const l=p[p.length-1];g+=`<circle cx="${X(l[0])}" cy="${Y(l[1])}" r="3.5" fill="${s.color||'var(--chart-1)'}" stroke="var(--surface)" stroke-width="2"/>`}
 return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(series.map(s=>s.name).join(', '))} by ${esc(xLabel)}">${g}</svg>`;
}
function spark(y,color='var(--chart-1)',h=32){
 if(!y||y.length<2)return '';const W=300,lo=Math.min(...y),hi=Math.max(...y),r=hi-lo||1;
 return `<svg viewBox="0 0 ${W} ${h}" width="100%" height="${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${y.map((v,i)=>(i?'L':'M')+(i/(y.length-1)*W).toFixed(1)+' '+(h-3-(v-lo)/r*(h-6)).toFixed(1)).join('')}" fill="none" stroke="${color}" stroke-width="1.75" vector-effect="non-scaling-stroke"/></svg>`;
}
// task bits shared by workbench, task and model views
function kidRow([k,depth]){
 const pr=k.progress||{},sc=k.summary?.score??k.last?.running_score;
 const v=isLive(k)?[pr.total?`${pr.done.toLocaleString()} of ${pr.total.toLocaleString()}`:'',sc!=null?pct(sc):'',k.eta?left(k.eta.eta_s)+' left':''].filter(Boolean).join(' · ')
  :k.kind==='eval'&&sc!=null?`${pct(sc)} · n ${(k.summary?.n??pr.done).toLocaleString()}`:({done:'Done',completed:'Done',failed:'Failed',budget:'Out of time'})[k.status]||k.status;
 return `<a class="kid" href="#task/${enc(k.id)}" style="padding-left:${8+depth*16}px"><span class="sd ${k.status}"></span><span class="nm">${esc(k.title)}</span><span class="vl">${esc(v)}</span></a>`;
}
const noteLine=n=>n?`<div class="note ${n.level}"><span class="msg" title="${esc(n.text??n.msg)}">${esc(n.text??n.msg)}</span><span class="when">${ago(n.t)}</span></div>`:'';
const extLinks=links=>Object.entries(links||{}).map(([k,v])=>`<a class="ln" href="${esc(v)}" target="_blank" rel="noopener">${esc(k)} ${ICON.ext}</a>`).join('');
// copy: a 24px icon button that copies `text`; cmd(): a one-line command with its copy button, for "run this next"
function copyText(btn,text){
 const done=()=>{btn.classList.add('ok');btn.setAttribute('aria-label','Copied');setTimeout(()=>{btn.classList.remove('ok');btn.setAttribute('aria-label','Copy')},1400)};
 (navigator.clipboard?.writeText(text)||Promise.reject()).then(done,()=>{const a=document.createElement('textarea');a.value=text;document.body.append(a);a.select();try{document.execCommand('copy');done()}catch(e){}a.remove()});
}
const copyBtn=text=>`<button class="copy" type="button" aria-label="Copy" title="Copy" onclick="event.stopPropagation();event.preventDefault();copyText(this,${esc(JSON.stringify(String(text)))})">${ICON.copy}</button>`;
const cmd=text=>`<span class="cmd"><code>${esc(text)}</code>${copyBtn(text)}</span>`;
