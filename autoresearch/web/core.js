// arx dashboard core: state, formatting, the shell, and the shared components every view uses.
// Views live in views/<name>.js and register themselves in VIEWS; they return HTML strings built from S.state.
// Shared API (keep views on it so the screens read as one product):
//   page({title, crumbs, finding, acts, back})  the title row; crumbs also feed the top bar
//   panel(title, body, {meta, right, flush, cls}) a card with its header
//   kpis([[label, value, sub, href?]])          the divided KPI strip
//   pill(text, cls) / st(status, label?)         status marks; ladder(gate, {compact}) the gate track
//   meter(frac, {mark, cls}) / ciBar(check) / lineChart(series, opts) / spark(ys)
//   empty(title, hint) / table(head, rows)
//   sv(slice, v) / sd(slice, delta)            a score or delta in its slice's units (count of n, ms, tok/s)
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
const secs=x=>x==null?'—':(x<10?x.toFixed(2):x.toFixed(1))+' s';
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
// a slice without its dataset ("gsm8k-test/random50" -> "random50"); kept whole when the rest is only a size ("cold/n24")
const short=s=>{const r=String(s||'').split('/').slice(1).join('/');return !r||/^n?\d+$/i.test(r)?s:r};
const plural=(n,w,ws)=>`${n} ${n===1?w:(ws||w+'s')}`;
const solved=r=>Math.round(r.score*r.n);
// a score in its slice's terms. 0/1 slice: "1,224 of 1,319" and deltas in pts. Continuous slice: its unit, and a
// "minus ms" metric (stored negated so higher is better) reads as the plain amount: sv -> "387 ms", sd(+1071) -> "−1,071 ms"
const sliceOf=s=>S.state?.slices?.[s]||{};
const isCont=s=>sliceOf(s).scale==='continuous';
const negSlice=s=>/^\s*minus\b/i.test(sliceOf(s).metric||'');
const unitOf=s=>sliceOf(s).unit||(/tokens?\s*\/\s*s/i.test(sliceOf(s).metric||'')?'tok/s':'');
const grp=x=>Math.abs(x)>=100?Math.round(x).toLocaleString('en-US'):(+x.toPrecision(3)).toLocaleString('en-US');
const sv=(s,v,n)=>{if(v==null||!isFinite(v))return '—';if(isCont(s)){const x=negSlice(s)?-v:v;return (grp(x)+' '+unitOf(s)).trim()}
 n=n??sliceOf(s).n;return n?`${Math.round(v*n).toLocaleString('en-US')} of ${n.toLocaleString('en-US')}`:pct(v)};
const sd=(s,d)=>{if(d==null||!isFinite(d))return '—';if(isCont(s)){const x=negSlice(s)?-d:d;return ((x>0?'+':x<0?'−':'')+grp(Math.abs(x))+' '+unitOf(s)).trim()}return pts(d)+' pts'};
const firstLine=t=>String(t||'').split(/(?<=\.)\s/)[0];

// ---------- ledger queries
// #view/arg?k=v: the view, its argument and its query (#learn?catchup=1). Another name for a view (#brief) reads as it
const ALIAS={brief:'learn'};
function route(){const h=location.hash.slice(1)||'overview',qi=h.indexOf('?'),p=qi<0?h:h.slice(0,qi);
 const [r0,...rest]=p.split('/'),r=ALIAS[r0]||r0||'overview';
 return {r,arg:decodeURIComponent(rest.join('/')),q:Object.fromEntries(new URLSearchParams(qi<0?'':h.slice(qi+1)))}}
const isLive=t=>t&&(t.status==='running'||t.status==='stalled');
const active=()=>S.state.tasks.filter(isLive);
const archived=()=>S.state.tasks.filter(t=>!isLive(t));
const byId=id=>S.state.tasks.find(t=>t.id===id);
// atomic jobs the sidebar counts: live, no live child, not an answer agent; silent for more than a day is dead
const DEAD_S=86400;
const quietFor=t=>now()-(t.heartbeat||t.updated||t.created||0);
const liveJobs=()=>{const live=active(),par=new Set(live.map(t=>t.parent).filter(Boolean));
 return live.filter(t=>!par.has(t.id)&&t.kind!=='answer'&&!(t.status==='stalled'&&quietFor(t)>DEAD_S))};
const kids=id=>S.state.tasks.filter(t=>t.parent===id).sort((a,b)=>(isLive(b)-isLive(a))||(b.created-a.created));
// every descendant, depth-first, with its depth; a guard stops cycles from bad parent ids
function tree(id,depth=0,seen=new Set([id])){return kids(id).filter(k=>!seen.has(k.id)&&seen.add(k.id)).flatMap(k=>[[k,depth],...tree(k.id,depth+1,seen)])}
function fullScore(m){const st=S.state;return st.leaderboard[st.config.primary_dataset+'/full']?.[m]}
const better=(a,b)=>S.state.config.higher_is_better===false?a<b:a>b;

// ---------- icons: 16px outline, 1.5 stroke
const I=(d,s=16)=>`<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICON={
 share:I('<circle cx="18" cy="5.5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="18.5" r="2.5"/><path d="M8.2 10.8l7.6-4M8.2 13.2l7.6 4"/>'),
 download:I('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>'),
 start:I('<path d="M5 20.5V4M5 4.5h11.5l-2.5 4 2.5 4H5"/>'),
 overview:I('<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>'),
 workbench:I('<path d="M4 12h3l2-6 4 12 2-6h5"/>'),
 models:I('<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M6 8.5v7M8.3 7l7.5 4M8.3 17l7.5-4"/>'),
 hills:I('<path d="M3 19l6-10 4 6 3-4 5 8z"/>'),
 slices:I('<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'),
 questions:I('<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>'),
 course:I('<path d="M3 8l9-5 9 5-9 5zM6 10v7c4 3 8 3 12 0v-7M21 8v8"/>'),
 learn:I('<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/>'),
 memory:I('<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 1 8.5 8.5H12z" fill="currentColor"/>'),
 goals:I('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="0.6" fill="currentColor"/>'),
 papers:I('<path d="M7 3.5h7l4.5 4.5v12a.5.5 0 0 1-.5.5H7a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5z"/><path d="M14 3.5V8h4.5M9.5 12.5h6M9.5 16h6"/>'),
 search:I('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',14),
 archive:I('<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v10h14V9M10 13h4"/>'),
 ext:I('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',13),
 back:I('<path d="M15 6l-6 6 6 6"/>',14),
 menu:I('<path d="M4 7h16M4 12h16M4 17h16"/>',18),
 sun:I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
 moon:I('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
 auto:I('<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor"/>'),
 copy:I('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',13)};
// the product's mark: a ladder (two rails, three rungs) in the accent
const MARK='<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="var(--accent)"/><path d="M8 18.5V5.5M16 18.5V5.5M8 15h8M8 11.5h8M8 8h8" stroke="var(--surface)" stroke-width="1.8" stroke-linecap="round"/></svg>';
const routeLabel=r=>({task:'Task',hill:'Hill',model:'Model',goal:'Goal'})[r]||ROUTES.find(([k])=>k===r)?.[1]||(VIEWS[r]?r[0].toUpperCase()+r.slice(1):'Not found');
const ROUTES=[['start','Start'],['overview','Overview'],['learn','Brief'],['course','101'],['memory','Memory'],['workbench','Workbench'],['goals','Goals'],['questions','Questions'],['models','Models'],['hills','Hills'],['papers','Papers'],['slices','Slices'],['archive','Archive']];
// the project this page serves: /p/<key>/ for a registered project, the server's own at /
const PKEY=(location.pathname.match(/^\/p\/([^/]+)/)||[])[1]&&decodeURIComponent(location.pathname.split('/')[2]);
// a model reads by its title; an untitled a+b+c+d id reads as its last two changes (…+c+d); the id stays in the URL
const mnt=k=>{const t=S.state?.models?.[k]?.title;if(t)return esc(t);const s=String(k||'—');return esc(s.split('+').length>3?'…+'+s.split('+').slice(-2).join('+'):s)};  // plain text, for attributes
const mn=k=>{const t=S.state?.models?.[k]?.title;if(t)return esc(t);const s=String(k||'—');return s.split('+').length>3?`<span title="${esc(s)}">…+${esc(s.split('+').slice(-2).join('+'))}</span>`:esc(s)};
const paperOf=key=>{const ps=S.state.papers||{};return ps[key]||Object.values(ps).find(p=>p.hill===key)};
const paperUrl=p=>'papers/'+enc(p.name);  // relative, so /p/<key>/ serves another project's papers
const goalPaper=g=>Object.values(S.state.papers||{}).find(p=>p.goal===g);

// ---------- shell
function renderNav(){
 const {r,arg}=route(),st=S.state;
 const navOn={task:st&&isLive(byId(arg))?'workbench':'archive',model:'models',hill:'hills',goal:'goals'}[r]||(VIEWS[r]?r:'');
 const jobs=st?liveJobs():[],stalled=jobs.filter(t=>t.status==='stalled').length,running=jobs.length-stalled;
 const waiting=st?Object.values(st.papers||{}).reduce((a,p)=>a+(p.waiting||0),0):0,asks=st?.questions?.needs_human||0;
 const counts=st?{workbench:jobs.length,goals:Object.values(st.goals||{}).filter(g=>g.status==='open').length,hills:Object.values(st.hills).filter(h=>h.status==='open').length,papers:waiting,questions:asks}:{};
 const tip={workbench:()=>plural(running,'job')+' running'+(stalled?', '+stalled+' stalled':''),goals:n=>plural(n,'open goal'),hills:n=>plural(n,'open hill'),papers:n=>plural(n,'comment')+' waiting for the agent',questions:n=>plural(n,'question')+' waiting on you'};
 const hot={papers:1,questions:1};
 // switching project keeps the view: #goals on one project lands on #goals of the next (detail routes fall back to their list)
 const keep=({task:'workbench',model:'models',hill:'hills',goal:'goals'})[r]||(VIEWS[r]?r:'');
 const pq=q=>{const n=q.waiting||0,a=q.asks||0;
  if(n||a)return `<span class="count hot" title="${[a&&plural(a,'question')+' waiting on you',n&&plural(n,'comment')+' waiting'].filter(Boolean).join(', ')}">${n+a}</span>`;
  if(q.stalled&&!q.running)return `<span class="count bad" title="${plural(q.stalled,'job')} stalled">${q.stalled}</span>`;
  return q.running?`<span class="count" title="${plural(q.running,'job')} running${q.stalled?', '+q.stalled+' stalled':''}">${q.running}</span>`:''};
 setHTML($('#nav'),`<a class="brand" href="#start">${MARK}<span>arx<span class="proj">${esc(st?.config?.name||'')}</span></span></a>`+
  ROUTES.map(([k,l])=>`<a class="nav ${navOn===k?'on':''}" href="#${k}" ${navOn===k?'aria-current="page"':''}>${ICON[k]}${l}${counts[k]?`<span class="count ${(k==='workbench'&&stalled)?'bad':hot[k]?'hot':''}" title="${tip[k](counts[k])}">${counts[k]}</span>`:''}</a>`).join('')+
  (S.projects.length>1?`<div class="grp">Projects</div>`+S.projects.map(q=>{const on=q.key===PKEY||(!PKEY&&q.default);return `<a class="nav proj ${on?'on':''}" href="/p/${enc(q.key)}/${keep?'#'+keep:''}" title="${esc(q.name)} · ${esc(q.root)}" ${on?'aria-current="true"':''}><span class="pdot ${q.error?'bad':q.running?'run':q.stalled?'bad':''}"></span><span class="ell">${esc(q.name)}</span>${pq(q)}</a>`}).join(''):'')+
  (st?`<div class="foot"><b title="${esc(st.champion||'')}">${st.champion?mn(st.champion):'No champion yet'}</b><span>${st.champion?'champion · ':''}${plural(Object.keys(st.models).length,'model')}</span></div>`:''));
}
const THEMES={light:'Light',dark:'Dark','':'System'};
function renderTop(){
 const t=document.documentElement.dataset.theme||'',next=t==='light'?'dark':t==='dark'?'':'light';
 const c=S.crumbs.length?S.crumbs:[[routeLabel(route().r)]];
 setHTML($('#top'),`<button class="iconbtn menu-btn" aria-label="Menu" onclick="$('#app').classList.toggle('nav-open')">${ICON.menu}</button>
 <nav class="crumbs" aria-label="Breadcrumb">${c.map(([l,h],i)=>i===c.length-1?`<b>${esc(l)}</b>`:`<a href="${h}">${esc(l)}</a><span class="sep">/</span>`).join('')}</nav>
 <div class="right">${hereFaces()}<span class="live" title="${S.ok?'Polling the ledger every 4s':'The dashboard server is not answering'}"><span class="dot ${S.ok?'':'off'}"></span>${S.ok?'Live':'Offline'}<span class="clk">${S.state&&S.ok?' · '+clock(S.state.now):''}</span></span>
 <button class="iconbtn" aria-label="Share" title="Share this view" onclick="shareMenu(this)">${ICON.share}</button><button class="iconbtn" aria-label="Theme: ${THEMES[t]}. Switch to ${THEMES[next]}" title="Theme: ${THEMES[t]} (click for ${THEMES[next]})" onclick="toggleTheme()">${t==='light'?ICON.sun:t==='dark'?ICON.moon:ICON.auto}</button></div>`);
}
// Share: a link to this view (it works on another machine once `arx share on` ran) and a one-file snapshot that opens
// on this same view (?view=<hash>, read by share.py). The popover stays on screen at any width, takes focus, keeps Tab
// inside it and gives focus back to the button on Escape or close; the snapshot shows its progress while it builds
async function shareMenu(btn){
 if(document.querySelector('.sh-pop')){closeShare();return}
 let d={};try{d=await (await fetch('api/share',{cache:'no-store'})).json()}catch(e){}
 const here=location.hash||'#overview',url=(d.link||location.origin+location.pathname)+here;
 const pop=document.createElement('div');pop.className='sh-pop';pop.setAttribute('role','dialog');pop.setAttribute('aria-label','Share');
 pop.innerHTML=`<div class="sh-row"><span class="sh-l">${d.link?'Anyone on your network with this link':'Only this machine'}</span></div>
  <div class="sh-url"><code>${esc(url)}</code>${copyBtn(url)}</div>
  ${d.link?'':`<div class="sh-row sub"><code>arx share on</code>${copyBtn('arx share on')}<span>for others</span></div>`}
  <div class="sh-row"><a class="btn sh-dl" href="api/export?view=${enc(here.slice(1))}" download onclick="return snapshot(event,this)">${ICON.download}Snapshot</a><span class="sh-st" aria-live="polite"></span></div>`;
 pop._btn=btn;document.body.append(pop);
 const r=btn.getBoundingClientRect(),w=pop.offsetWidth;
 pop.style.top=r.bottom+6+'px';pop.style.left=Math.max(8,Math.min(r.right-w,innerWidth-w-8))+'px';
 pop.querySelector('button,a')?.focus();
 pop.addEventListener('keydown',e=>{
  if(e.key==='Escape'){e.stopPropagation();closeShare();return}
  if(e.key!=='Tab')return;const f=[...pop.querySelectorAll('button,a[href]')];if(!f.length)return;
  const i=f.indexOf(document.activeElement);e.preventDefault();f[(i+(e.shiftKey?-1:1)+f.length)%f.length].focus()});
 setTimeout(()=>addEventListener('click',pop._off=e=>{if(!pop.contains(e.target))closeShare(false)}),0);
}
function closeShare(refocus=true){const p=document.querySelector('.sh-pop');if(!p)return;removeEventListener('click',p._off);p.remove();if(refocus)p._btn?.focus?.()}
// the export takes seconds on a big ledger: fetch it here so the popover can say so, then hand the file to the browser
async function snapshot(e,a){
 if(!window.fetch||!window.URL?.createObjectURL)return true;e.preventDefault();
 if(a.dataset.busy)return false;a.dataset.busy=1;
 const stx=a.parentNode.querySelector('.sh-st'),t0=Date.now(),say=t=>{if(stx)stx.textContent=t};
 const tick=setInterval(()=>say(`Building… ${Math.round((Date.now()-t0)/1000)} s`),500);say('Building…');
 try{
  const r=await fetch(a.getAttribute('href'),{cache:'no-store'});if(!r.ok)throw new Error(r.status);
  const b=await r.blob(),name=(/filename="?([^";]+)"?/.exec(r.headers.get('content-disposition')||'')||[])[1]||'arx-snapshot.html';
  const u=URL.createObjectURL(b),l=document.createElement('a');l.href=u;l.download=name;document.body.append(l);l.click();l.remove();
  setTimeout(()=>URL.revokeObjectURL(u),60000);
  say(`Saved ${name} · ${(b.size/1048576).toFixed(1)} MB`);
 }catch(err){say('The snapshot failed. Try again.')}
 finally{clearInterval(tick);delete a.dataset.busy}
 return false;
}
// who else has this project open: their faces, ringed when they are on this same view. The list rides on the 4 s state
// poll (/api/state `here`), so a move shows within a poll, not at the next 20 s heartbeat. Faces overlap by 3 px (each
// sits in its own link, so the overlap is set here; more clips the initials) and cap at 3 on a phone, 5 wider, then "+N"
function hereFaces(){
 if(!window.ARXP)return '';const me=ARXP.me().id,cur=location.hash.slice(1)||'overview';
 const hs=Array.isArray(S.state?.here)?S.state.here.filter(x=>x.id!==me):ARXP.here();if(!hs.length)return '';
 const cap=innerWidth<600?3:5,shown=hs.length>cap?cap:hs.length;
 return `<span class="px-here" style="flex:none" aria-label="${hs.length} more here">${hs.slice(0,shown).map((x,i)=>{const pp=(x.route||'').startsWith('papers/');return `<a href="${pp?esc(x.route):'#'+esc(x.route||'overview')}" style="display:inline-flex;position:relative;z-index:${shown-i}${i?';margin-left:-3px':''}" title="${esc(x.name)} · ${pp?'reading the paper '+esc(x.route.slice(7)):esc(routeLabel((x.route||'overview').split('/')[0]))}">${ARXP.face(x.id,x.name,x.route===cur?'on':'')}</a>`}).join('')}${hs.length>shown?`<span class="sub" style="margin-left:4px;font-size:12px" title="${esc(hs.slice(shown).map(x=>x.name).join(', '))}">+${hs.length-shown}</span>`:''}</span>`;
}
// light -> dark -> system (follow the OS) -> light
function toggleTheme(){
 const el=document.documentElement,t=el.dataset.theme||'',next=t==='light'?'dark':t==='dark'?'':'light';
 if(next)el.dataset.theme=next;else delete el.dataset.theme;
 try{next?localStorage.setItem('arx-theme',next):localStorage.removeItem('arx-theme')}catch(e){}renderTop();render();
}

addEventListener('storage',e=>{if(e.key!=='arx-theme')return;if(e.newValue)document.documentElement.dataset.theme=e.newValue;else delete document.documentElement.dataset.theme;renderTop()});
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
// line chart: an interactive chart from charts.js (crosshair, drag-zoom, 1-2-5 ticks); opts.id keeps it across polls
function lineChart(series,{h=180,y0=null,ref=null,refLabel='',pctAxis=false,xLabel='step',id=null,group=null,mode='compact'}={}){
 if(!series.some(s=>s.pts.some(p=>p[1]!=null&&isFinite(p[1]))))return empty('No points yet');
 const key=id||'lc-'+series.map(s=>s.name).join('|')+'-'+xLabel+'-'+(XC.mount.n=(XC.mount.n||0)+1);
 return XC.box(key,{group:group||key,mode,h,xLabel,ymin:y0,yfmt:pctAxis?'pct':'num',smooth:false,
  ref:ref!=null?{y:ref,label:refLabel}:null,series:series.map(s=>({name:s.name,color:s.color,pts:s.pts}))});
}
const spark=(y,color,h)=>XC.spark(y,color,h);
// task bits shared by workbench, task and model views
function kidRow([k,depth]){
 const pr=k.progress||{},sc=k.summary?.score??k.last?.running_score;
 // scores in the slice's units: "41 of 50" on a 0/1 slice, "387 ms · n 12" on a continuous one
 const n=k.summary?.n??pr.done,scv=sc==null?'':isCont(k.slice)?sv(k.slice,sc)+(n?' · n '+n.toLocaleString():''):sv(k.slice,sc,n||undefined);
 const v=isLive(k)?[pr.total?`${pr.done.toLocaleString()} of ${pr.total.toLocaleString()}`:'',isCont(k.slice)?(sc!=null?sv(k.slice,sc):''):(sc!=null&&pr.done?sv(k.slice,sc,pr.done)+' right':''),k.eta?left(k.eta.eta_s)+' left':''].filter(Boolean).join(' · ')
  :k.kind==='eval'&&sc!=null?scv:({done:'Done',completed:'Done',failed:'Failed',budget:'Out of time'})[k.status]||k.status;
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

// ---------- glossary: term('champion') marks a research word where a view prints it. Hover, focus or tap shows a tiny
// picture of the idea, one line and a link to its lesson (#course/<id>). Inside a link, a hover shows it and a click
// still follows the link; on a touch screen the first tap shows it and the second follows the link.
// Views: term(id) prints the word as written below; term(id, 'champions') prints your own wording.
const TG=(d)=>`<svg viewBox="0 0 120 44" width="120" height="44" aria-hidden="true">${d}</svg>`;
const TL='stroke="var(--grid)" stroke-width="1"',TA='fill="var(--accent)"',TF='fill="var(--faint)"',TT='stroke="var(--chart-3)" stroke-width="1.5" stroke-dasharray="3 2"';
const TERMS={
 goal:{w:'goal',d:'A target number on one frozen slice. The work is for it.',g:TG(`<rect x="6" y="18" width="108" height="8" rx="4" fill="var(--grid)"/><rect x="6" y="18" width="72" height="8" rx="4" ${TA}/><line x1="96" x2="96" y1="8" y2="36" ${TT}/><text x="98" y="10" font-size="9" fill="var(--chart-3)">target</text>`)},
 champion:{w:'champion',d:'The best model so far. Every candidate is measured against it.',g:TG(`<rect x="14" y="24" width="16" height="16" ${TF}/><rect x="40" y="10" width="16" height="30" ${TA}/><rect x="66" y="20" width="16" height="20" ${TF}/><rect x="92" y="28" width="16" height="12" ${TF}/><path d="M42 6l3-4 3 3 3-3 3 4z" fill="var(--chart-3)"/>`)},
 candidate:{w:'candidate',d:'One change to try. It must beat the champion on the same items.',g:TG(`<rect x="30" y="12" width="20" height="28" ${TA}/><rect x="66" y="6" width="20" height="34" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="3 2"/><text x="28" y="9" font-size="8" fill="var(--muted)">champ</text><text x="92" y="20" font-size="10" fill="var(--muted)">?</text>`)},
 hill:{w:'hill',d:'One way the champion fails, with its own slice to climb.',g:TG(`<path d="M6 40L44 12L62 26L80 14L114 40Z" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="1.5"/><path d="M44 12V2l10 4-10 4" fill="var(--chart-3)"/>`)},
 slice:{w:'slice',d:'A fixed set of test items, frozen so every score compares.',g:TG(Array.from({length:24},(_,i)=>`<rect x="${8+(i%12)*9}" y="${8+Math.floor(i/12)*16}" width="7" height="12" rx="1.5" ${i%3===0?TA:TF} opacity="${i%3===0?1:.35}"/>`).join(''))},
 'paired-delta':{w:'paired delta',d:'Both models on the same items; the mean of the per-item difference.',g:TG([[14,30,14],[34,30,18],[54,22,12],[74,28,28],[94,34,18]].map(([x,a,b])=>`<line x1="${x}" x2="${x+10}" y1="${a}" y2="${b}" stroke="var(--muted)" stroke-width="1"/><circle cx="${x}" cy="${a}" r="3" ${TF}/><circle cx="${x+10}" cy="${b}" r="3" ${TA}/>`).join(''))},
 interval:{w:'interval',d:'Where the true difference likely lies (90%). If it crosses zero, it may be noise.',g:TG(`<line x1="6" x2="114" y1="24" y2="24" ${TL}/><line x1="44" x2="44" y1="10" y2="38" stroke="var(--muted)" stroke-width="1"/><text x="40" y="8" font-size="8" fill="var(--muted)">0</text><rect x="30" y="20" width="62" height="8" rx="4" fill="var(--accent-soft)" stroke="var(--accent)"/><circle cx="62" cy="24" r="4" ${TA}/>`)},
 gate:{w:'gate',d:'The check a candidate must clear against the champion to move up.',g:TG(`<line x1="6" x2="114" y1="18" y2="18" ${TT}/><rect x="26" y="10" width="18" height="30" fill="var(--positive)"/><rect x="74" y="24" width="18" height="16" fill="var(--negative)" opacity=".8"/><text x="96" y="15" font-size="8" fill="var(--chart-3)">bar</text>`)},
 rung:{w:'rung',d:'One step of the ladder: a bigger slice, passed only after the smaller one.',g:TG(`<path d="M40 4v38M80 4v38" stroke="var(--muted)" stroke-width="2"/><path d="M40 36h40M40 26h40M40 6h40" stroke="var(--muted)" stroke-width="2"/><path d="M40 16h40" stroke="var(--accent)" stroke-width="4"/>`)},
 ladder:{w:'ladder',d:'Rungs from small to full: a cheap check first, the whole set last.',g:TG(`${[['dev',8,10],['50',36,14],['100',64,20],['full',92,26]].map(([l,x,w])=>`<rect x="${x}" y="${34-w}" width="20" height="${w}" rx="2" ${TA} opacity=".85"/><text x="${x}" y="42" font-size="8" fill="var(--muted)">${l}</text>`).join('')}`)},
 brief:{w:'Brief',d:'Cards that catch you up on what changed, by doing, not reading.',g:TG(`<rect x="34" y="12" width="52" height="30" rx="4" fill="var(--surface)" stroke="var(--muted)"/><rect x="30" y="8" width="52" height="30" rx="4" fill="var(--surface)" stroke="var(--muted)"/><rect x="26" y="4" width="52" height="30" rx="4" fill="var(--surface)" stroke="var(--accent)" stroke-width="1.5"/><path d="M34 22h22M34 27h14" stroke="var(--accent)" stroke-width="2"/>`)},
};
const term=(id,label)=>{const x=TERMS[id];if(!x)return esc(label??id);return `<span class="term" data-term="${id}" tabindex="0" role="button" aria-label="${esc(label??x.w)} lesson">${esc(label??x.w)}</span>`};
{
 let pop=null,cur=null,hideT=0,showT=0;
 const touch=matchMedia('(hover:none)').matches;
 const hide=()=>{clearTimeout(showT);if(pop){cur?.removeAttribute('aria-describedby');pop.remove();pop=null;cur=null}};
 const show=el=>{
  clearTimeout(hideT);if(cur===el)return;hide();const x=TERMS[el.dataset.term];if(!x)return;
  cur=el;pop=document.createElement('div');pop.className='term-pop';pop.setAttribute('role','tooltip');pop.id='arx-term-definition';el.setAttribute('aria-describedby',pop.id);
  pop.innerHTML=`${x.g}<b>${esc(x.w[0].toUpperCase()+x.w.slice(1))}</b><span>${esc(x.d)}</span><a href="#course/${enc(el.dataset.term)}">Lesson ${CHEVR}</a>`;
  pop.addEventListener('mouseenter',()=>clearTimeout(hideT));pop.addEventListener('mouseleave',()=>{hideT=setTimeout(hide,200)});
  pop.addEventListener('click',e=>{if(e.target.closest('a'))hide()});
  document.body.append(pop);
  const r=el.getBoundingClientRect(),w=pop.offsetWidth,h=pop.offsetHeight;
  pop.style.left=Math.max(8,Math.min(r.left+r.width/2-w/2,innerWidth-w-8))+'px';
  pop.style.top=(r.bottom+h+8>innerHeight&&r.top>h+8?r.top-h-6:r.bottom+6)+'px';
 };
 const CHEVR=I('<path d="M9 6l6 6-6 6"/>',12);
 addEventListener('mouseover',e=>{const el=e.target.closest?.('.term');if(!el||touch)return;clearTimeout(hideT);clearTimeout(showT);showT=setTimeout(()=>show(el),250)});
 addEventListener('mouseout',e=>{const el=e.target.closest?.('.term');if(!el||touch)return;clearTimeout(showT);hideT=setTimeout(hide,200)});
 addEventListener('focusin',e=>{const el=e.target.closest?.('.term');if(el)show(el);else if(pop&&!pop.contains(e.target))hide()});
 addEventListener('click',e=>{
  const el=e.target.closest?.('.term');
  if(!el){if(pop&&!pop.contains(e.target))hide();return}
  const inLink=el.closest('a[href]');
  if(inLink&&(!touch||cur===el)){hide();return}  // a link's own click
  e.preventDefault();e.stopPropagation();cur===el?hide():show(el);
 },true);
 addEventListener('keydown',e=>{if(e.key==='Escape'&&pop){hide();return}const el=e.target.closest?.('.term');if(el&&(e.key==='Enter'||e.key===' ')){e.preventDefault();location.hash='#course/'+enc(el.dataset.term);hide()}else if(el&&e.key==='Tab'&&!e.shiftKey&&pop){e.preventDefault();pop.querySelector('a')?.focus()}});
 addEventListener('hashchange',hide);addEventListener('scroll',()=>{if(pop&&!touch)hide()},{passive:true});
}
