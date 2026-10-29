'use strict';
// Questions: the project as a tree of questions (seeded from goals, hills and models; see autoresearch/questions.py).
// Left: the outline, claims on hover. Right: the focused question, its claim and its evidence as paired-delta dots
// with CI and fixed/broke squares. "Ask" under any node, or window.qAsk(text) from selected text on any view (the
// comments chip's Ask button), sends a question to an agent (status agent, inbox kind=question).
const QS={data:null,at:0,busy:false,closed:null,read:false,notes:{},fresh:new Set(),err:null};
const qName=()=>{try{return localStorage.getItem('arx-name')||'you'}catch(e){return 'you'}};

function qLoad(force){
 if(QS.busy&&!force)return QS.busy;
 if(!force&&QS.data&&Date.now()-QS.at<5000)return Promise.resolve();
 const p=fetch('api/questions',{cache:'no-store'}).then(r=>r.json()).then(d=>{QS.data=d;QS.at=Date.now();QS.err=null})
  .catch(e=>{QS.err=String(e)}).finally(()=>{if(QS.busy===p)QS.busy=false;if(route().r==='questions')render()});
 return QS.busy=p;
}
async function qPost(verb,body){
 const r=await fetch('api/questions/'+verb,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({by:qName(),...body})});
 const d=await r.json().catch(()=>({error:'bad response'}));
 if(!r.ok||d.error)throw new Error(d.error||r.status);
 return d;
}

// ---------- marks: open ring, answered disc, dead crossed square, agent spinner (or progress ring), you = amber diamond
function qShape(n,sz=14){
 const c=sz/2,r=sz/2-1.5,box=`width="${sz}" height="${sz}" viewBox="0 0 ${sz} ${sz}" aria-hidden="true"`;
 const s=typeof n==='string'?n:n.status,human=typeof n==='object'&&n.needs_human&&s!=='answered'&&s!=='dead';
 if(human||s==='human')return `<svg ${box}><path d="M${c} 1L${sz-1} ${c}L${c} ${sz-1}L1 ${c}Z" fill="var(--chart-3)"/></svg>`;
 if(s==='agent'){
  const pr=typeof n==='object'&&n.live?.progress,f=pr&&pr.total?Math.min(1,(pr.done||0)/pr.total):null;
  if(f!=null){const L=2*Math.PI*r;return `<svg ${box}><circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="var(--control)" stroke-width="2"/><circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-dasharray="${(f*L).toFixed(2)} ${L.toFixed(2)}" transform="rotate(-90 ${c} ${c})"/></svg>`}
  return `<svg ${box}><circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="var(--rule)" stroke-width="2"/><path class="q-spin" d="M${c} ${c-r}A${r} ${r} 0 0 1 ${c+r} ${c}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"/></svg>`}
 if(s==='answered')return `<svg ${box}><circle cx="${c}" cy="${c}" r="${r}" fill="var(--positive)"/></svg>`;
 if(s==='dead')return `<svg ${box}><rect x="2" y="2" width="${sz-4}" height="${sz-4}" rx="1.5" fill="none" stroke="var(--negative)" stroke-width="1.6"/><path d="M5 5L${sz-5} ${sz-5}M${sz-5} 5L5 ${sz-5}" stroke="var(--negative)" stroke-width="1.6"/></svg>`;
 return `<svg ${box}><circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="var(--accent)" stroke-width="1.8"/></svg>`;
}
const qWaiting=n=>n.needs_human&&(n.status==='open'||n.status==='agent');

// ---------- the tree
function qIndex(){
 const d=QS.data,by={},kids={};
 for(const n of d.nodes){by[n.id]=n;(kids[n.parent||'']??=[]).push(n.id)}
 return {by,kids};
}
function qCount(id,kids){let a=0;for(const k of kids[id]||[])a+=1+qCount(k,kids);return a}
function qDefaultClosed(by,kids){
 // settled branches start folded; open work stays visible
 const s=new Set();for(const n of Object.values(by))if(kids[n.id]?.length&&(n.status==='answered'||n.status==='dead'||n.seed==='group'))s.add(n.id);return s;
}
function qRow(id,ix,focus){
 const n=ix.by[id],k=ix.kids[id]||[],cl=QS.closed.has(id),on=id===focus;
 return `<li><div class="q-row ${on?'on':''} ${cl?'closed':''} ${n.status==='dead'?'dead':''} ${QS.fresh.has(id)?'fresh':''}" data-qgo="${esc(id)}" data-qnode="${esc(id)}" tabindex="0"${n.claim&&!on?` data-qtip="${esc(n.claim)}"`:''}>`+
  `<button class="q-car ${k.length?'':'none'}" data-qcar="${esc(id)}" aria-label="Toggle" tabindex="-1"><svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 3.5L5 6.5L8 3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>`+
  `<span class="q-sh">${qShape(n)}</span><span class="q-tx"><span class="q-q">${esc(n.title)}</span>${on&&n.claim?`<span class="q-cl">${esc(n.claim)}</span>`:''}</span>`+
  `${k.length&&cl?`<span class="q-ct">${qCount(id,ix.kids)}</span>`:''}</div>`+
  (k.length&&!cl?`<ul class="q-t">${k.map(c=>qRow(c,ix,focus)).join('')}</ul>`:'')+`</li>`;
}

// ---------- evidence: one lane per run
const qFmt=n=>n==null?'—':Number(n).toLocaleString('en-US');
function qTag(e){return e.role||(e.slice||'').split('/').pop()}
function qCol(e){
 if(e.lo!=null&&e.hi!=null)return e.lo>0?'var(--positive)':e.hi<0?'var(--negative)':'var(--muted)';
 return e.delta>0?'var(--positive)':e.delta<0?'var(--negative)':'var(--muted)';
}
// a model's readable label as plain text (mnt() without the HTML escaping; data-qtip is escaped once by esc())
const qM=k=>{if(!k)return '';const t=S.state?.models?.[k]?.title;if(t)return t;const s=String(k);return s.split('+').length>3?'…+'+s.split('+').slice(-2).join('+'):s};
const qCI=e=>e.lo==null?'':isCont(e.slice)?`90% CI ${sd(e.slice,e.lo)} to ${sd(e.slice,e.hi)}`:`90% CI ${pts(e.lo)} to ${pts(e.hi)} pts`;
function qVal(e){
 if(e.kind==='missing')return 'Not run';
 if(e.kind==='paired')return e.delta==null?'—':sd(e.slice,e.delta);
 if(e.c==null||!e.n)return '—';
 return e.slice&&isCont(e.slice)?sv(e.slice,e.c/e.n):`${qFmt(e.c)} of ${qFmt(e.n)}`;
}
function qTipOf(e){
 if(e.kind==='missing')return `${qM(e.model)||e.task}\n${e.slice||''}\nNot run`;
 const head=`${e.label||qM(e.model)}\n${e.slice||e.what||''}${e.n?' · n '+qFmt(e.n):''}`;
 if(e.kind==='raw')return `${head}\n${qVal(e)}`+(e.what?`\n${e.what}`:'');
 const cont=isCont(e.slice);
 return `${head}\n${cont?sv(e.slice,e.c/e.n):qFmt(e.c)} vs ${cont?sv(e.slice,e.bc/e.n):qFmt(e.bc)} (${qM(e.base)})\n${qVal(e)}`+(e.lo!=null?` · ${qCI(e)}`:'')+
  `\n${e.wins??0} fixed · ${e.losses??0} broke`;
}
function qSquares(e){
 if(e.kind!=='paired'||(!e.wins&&!e.losses))return '';
 const u=Math.max(1,Math.ceil((e.wins+e.losses)/28));
 return `<span class="sqs" title="${e.wins} fixed · ${e.losses} broke">`+'<i class="f"></i>'.repeat(Math.ceil(e.wins/u))+'<i class="b"></i>'.repeat(Math.ceil(e.losses/u))+'</span>';
}
function qEvidence(n){
 // one lane per run: role, the delta (or count) as a dot with its CI, the value in the slice's units, and under it
 // the slice, n and CI in words, so nothing needs a hover. 0/1 lanes share one pts axis; continuous lanes scale alone.
 const ev=n.ev||[];if(!ev.length)return '';
 const isPts=e=>e.kind==='paired'&&e.delta!=null&&!isCont(e.slice);
 const span=e=>Math.max(...[e.delta,e.lo,e.hi].filter(v=>v!=null).map(Math.abs),0);
 const R=Math.max(3,Math.ceil(Math.max(0,...ev.filter(isPts).map(e=>100*span(e)))*1.1));
 const rows=ev.map(e=>{
  let lane='';
  if(e.kind==='raw')lane=`<div class="trk"></div><div class="fill" style="width:${e.n&&e.c!=null&&!(e.slice&&isCont(e.slice))?Math.max(0,Math.min(100,100*e.c/e.n)).toFixed(1):0}%"></div>`;
  else if(e.kind==='paired'&&e.delta!=null){
   const col=qCol(e),k=isPts(e)?100:1,r=isPts(e)?R:(span(e)*1.15||1),x=v=>50+Math.max(-r,Math.min(r,k*v))/r*48;
   lane=`<div class="z"></div>`+(e.lo!=null?`<div class="ci" style="left:${x(e.lo)}%;width:${Math.max(.5,x(e.hi)-x(e.lo))}%;background:${col}"></div>`:'')+`<div class="d" style="left:${x(e.delta)}%;background:${col}"></div>`}
  const href=e.task?`#task/${enc(e.task)}`:e.model?`#model/${enc(e.model)}`:'';
  const cap=[e.kind==='raw'&&e.role==='errors'?(e.what||e.label):e.slice,e.n?'n '+qFmt(e.n):'',e.kind==='paired'&&e.base?'vs '+qM(e.base):'',qCI(e)].filter(Boolean).map(esc).join(' · ');
  const tag=e.role==='errors'?'errors':qTag(e);
  return `<${href?'a':'div'} class="q-lr ${e.kind}"${href?` href="${href}"`:''} data-qtip="${esc(qTipOf(e))}"><span class="tag">${esc(tag)}</span><div class="lane">${lane}</div><b class="val">${esc(qVal(e))}</b><span class="cap">${cap}${qSquares(e)}</span></${href?'a':'div'}>`;
 }).join('');
 const axis=ev.some(isPts)?`<div class="q-lr axis"><span></span><div class="ax"><span>−${R}</span><span>0</span><span>+${R} pts</span></div><span></span></div>`:'';
 return `<div class="q-ev">${rows}${axis}</div>`;
}

// ---------- goal distance in units, with the champion succession as a sparkline
function qDistance(gk){
 // the numbers come as text in the goal's units (questions.py _goal_text): "43 more of 1,319", "458 ms to go"
 const g=QS.data.goals?.[gk];if(!g||g.value==null)return '';
 const gap=String(g.gap_txt||''),m=gap.match(/^([\d,.]+)\s*(.*)$/);
 const txt=g.met?`met · ${esc(g.value_txt||'')}`:m?`<b>${esc(m[1])}</b> ${esc(m[2])}`:esc(gap);
 const ps=g.points.map(p=>p[1]);let svg='';
 if(ps.length>1){
  const W=90,H=22,all=[...ps,g.target],lo=Math.min(...all),hi=Math.max(...all),r=hi-lo||1;
  const X=i=>3+i/(ps.length-1)*(W-6),Y=v=>H-3-(v-lo)/r*(H-6);
  svg=`<svg width="${W}" height="${H}" aria-hidden="true"><line x1="0" x2="${W}" y1="${Y(g.target)}" y2="${Y(g.target)}" stroke="var(--chart-3)" stroke-dasharray="2 2"/><polyline points="${ps.map((v,i)=>X(i)+','+Y(v)).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="1.6"/><circle cx="${X(ps.length-1)}" cy="${Y(ps.at(-1))}" r="2.5" fill="var(--accent)"/></svg>`}
 const tip=g.points.map(p=>p[2]||p[0]).join('\n')+`\ntarget ${g.target_txt||num(g.target)} on ${g.slice}`;
 return `<a class="q-dist" href="#goal/${enc(gk)}" data-qtip="${esc(tip)}">${svg}<span>${txt}</span></a>`;
}

// ---------- the focused question
function qPath(id,ix){const p=[];for(let x=ix.by[ix.by[id]?.parent];x;x=ix.by[x.parent])p.unshift(x);return p}
function qPanel(id,ix){
 const n=ix.by[id];if(!n)return empty('No question');
 const w=qWaiting(n),cls=w?'human':n.status;
 const path=qPath(id,ix);
 let h=(path.length?`<div class="q-path">${path.map(p=>`<a data-qgo="${esc(p.id)}">${esc(p.title)}</a>`).join('<span>/</span>')}</div>`:'')+
  `<div class="q-fq"><span class="q-sh">${qShape(n,18)}</span><h2>${esc(n.title)}</h2></div>`;
 if(n.status==='agent'){
  const L=n.live||{},pr=L.progress,f=pr&&pr.total?Math.min(1,(pr.done||0)/pr.total):null;
  const line=L.status==='failed'?('Agent failed'+(L.error?': '+L.error:'')):L.note||(L.status==='running'?'Agent working':'Queued for an agent');
  h+=`<div class="q-claim agent">${esc(line)}${L.task?` <a class="q-tl" href="#task/${enc(L.task)}">${esc(L.task)}</a>`:''}${f!=null?`<div class="pb"><i style="width:${(100*f).toFixed(1)}%"></i></div>`:''}</div>`;
 }else if(n.claim)h+=`<div class="q-claim ${cls}">${esc(n.claim)}${n.settled_by&&!['agent','you'].includes(n.settled_by)?`<span class="q-by">${esc(n.settled_by)}</span>`:''}</div>`;
 if(n.quote)h+=`<div class="q-quote"><mark>${esc(n.quote)}</mark></div>`;
 h+=qEvidence(n);
 const live=n.status==='open'||n.status==='agent';
 if(w&&n.choices?.length)h+=`<div class="q-acts">${n.choices.map((c,i)=>`<button class="btn ${i?'':'q-warn'}" data-qpick="${esc(c)}">${esc(c)}</button>`).join('')}</div>`;
 if(live)h+=`<div class="q-form ${w?'on':''}" id="q-af"><input class="q-in" id="q-ans" aria-label="Your answer" placeholder="Your answer"><button class="btn primary" data-qact="answer">Answer</button><button class="btn" data-qact="dead">Dead end</button></div>`;
 const ks=ix.kids[id]||[];
 if(ks.length)h+=`<div class="q-kids">${ks.map(k=>{const c=ix.by[k];return `<button class="q-kid" data-qgo="${esc(k)}" data-qnode="${esc(k)}"${c.claim?` data-qtip="${esc(c.claim)}"`:''}><span class="q-sh">${qShape(c)}</span><span>${esc(c.title)}</span></button>`}).join('')}</div>`;
 h+=`<div class="q-acts"><button class="btn primary" data-qact="branch">Ask</button>`+
  (live&&!w?`<button class="btn" data-qact="settle">Answer</button>`:'')+(live?`<button class="btn ${n.needs_human?'on':''}" data-qact="flag" aria-pressed="${!!n.needs_human}">Needs you</button>`:`<button class="btn" data-qact="reopen">Reopen</button>`)+
  `<button class="btn ${QS.read?'on':''}" data-qact="read" aria-expanded="${QS.read}">Read</button>`+
  `${n.model?`<a class="btn" href="#model/${enc(n.model)}">Model</a>`:n.hill?`<a class="btn" href="#hill/${enc(n.hill)}">Hill</a>`:n.goal?`<a class="btn" href="#goal/${enc(n.goal)}">Goal</a>`:''}</div>`+
  `<div class="q-form" id="q-bf"><input class="q-in" id="q-bin" aria-label="Question" maxlength="120"><button class="btn primary" data-qact="ask">Ask</button></div>`;
 if(QS.read)h+=qRead(id,ix);
 return h;
}
function qRead(id,ix){
 const r=QS.notes[id];
 if(!r){qNotes(id);return `<div class="q-read"><div class="body"><div class="q-note faint">Reading the ledger…</div></div></div>`}
 if(!r.length)return `<div class="q-read"><div class="body"><div class="q-note faint">No notes</div></div></div>`;
 return `<div class="q-read"><div class="body">${r.map(x=>`<div class="q-note" data-qnode="${esc(x.node)}"><div class="meta"><a data-qgo="${esc(x.node)}">${esc(ix.by[x.node]?.title||x.node)}</a><span class="faint">${x.t?ago(x.t):''}</span></div><p>${esc(x.text)}</p></div>`).join('')}</div></div>`;
}
function qNotes(id){
 if(QS.notes[id]!==undefined)return;QS.notes[id]=null;
 fetch('api/questions/notes?id='+enc(id),{cache:'no-store'}).then(r=>r.json()).then(d=>{QS.notes[id]=d.notes||[];render()}).catch(()=>{QS.notes[id]=[]});
}
function qFocus(ix,arg){
 if(arg&&ix.by[arg])return arg;
 // the open goal with the most work under it
 const roots=ix.kids['']||[],goals=roots.filter(k=>ix.by[k].status==='open'&&ix.by[k].goal);
 return goals.sort((a,b)=>qCount(b,ix.kids)-qCount(a,ix.kids))[0]||roots[0];
}
function qRootGoal(id,ix){for(let x=ix.by[id];x;x=ix.by[x.parent])if(x.goal)return x.goal;return Object.keys(QS.data.goals||{}).find(k=>QS.data.goals[k].status==='open')}

VIEWS.questions=arg=>{
 qLoad();
 if(!QS.data)return page({title:'Questions',crumbs:[['Questions']]})+(QS.err?`<div class="banner">${esc(QS.err)}</div>`:empty('Reading the ledger…'));
 const ix=qIndex();
 if(!QS.closed)QS.closed=qDefaultClosed(ix.by,ix.kids);
 const focus=qFocus(ix,arg);
 if(!focus)return page({title:'Questions',crumbs:[['Questions']]})+empty('No questions yet','<span>arx q add "&lt;title&gt;"</span>');
 for(let x=ix.by[ix.by[focus].parent];x;x=ix.by[x.parent])QS.closed.delete(x.id);
 // a deep link on a narrow screen: the panel sits under the tree, so bring it into view once per link
 if(arg&&QS.deep!==arg){QS.deep=arg;if(innerWidth<=820)setTimeout(()=>document.getElementById('q-panel')?.scrollIntoView({block:'start'}),0)}
 const hs=QS.data.nodes.filter(qWaiting);
 const need=hs.length?`<details class="q-need"><summary class="q-ib">${qShape('human',10)}${hs.length}</summary><div class="q-pop">${hs.map(n=>`<button data-qgo="${esc(n.id)}">${qShape('human',10)}<span>${esc(n.title)}</span></button>`).join('')}</div></details>`:'';
 const key=`<span class="q-ib key" tabindex="0" data-qtip="key"><svg width="14" height="14" viewBox="0 0 14 14" aria-label="Key"><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="7" cy="4.3" r=".9" fill="currentColor"/><path d="M7 6.5V10.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></span>`;
 const roots=ix.kids['']||[];
 return page({title:'Questions',crumbs:[['Questions']],acts:qDistance(qRootGoal(focus,ix))})+
  `<section class="card flush qv"><div class="q-col q-tree"><div class="q-bar">${need}${key}</div><ul class="q-t">${roots.map(r=>qRow(r,ix,focus)).join('')}</ul></div>`+
  `<div class="q-col q-panel" id="q-panel">${qPanel(focus,ix)}</div></section>`;
};

// ---------- interaction
function qGo(id){
 QS.deep=id;
 history.replaceState(null,'','#questions/'+enc(id));
 render(true);
 const p=document.getElementById('q-panel');if(p&&(p.getBoundingClientRect().top<0||innerWidth<=820))p.scrollIntoView({behavior:'smooth',block:'start'});
}
async function qAskPost(title,parent,quote){
 const q=await qPost('ask',{title,parent,quote,route:location.hash});
 QS.fresh.add(q.id);setTimeout(()=>QS.fresh.delete(q.id),1500);
 QS.closed?.delete(parent);
 await qLoad(true);
 return q;
}
document.addEventListener('click',async e=>{
 if(!e.target.closest('.qv'))return;
 const car=e.target.closest('[data-qcar]');
 if(car){e.stopPropagation();const id=car.dataset.qcar;QS.closed.has(id)?QS.closed.delete(id):QS.closed.add(id);render(true);return}
 const g=e.target.closest('[data-qgo]');
 if(g){e.preventDefault();g.closest('details')?.removeAttribute('open');qGo(g.dataset.qgo);return}
 const a=e.target.closest('[data-qact]');
 const pick=e.target.closest('[data-qpick]');
 const act=a?.dataset.qact,id=()=>qFocus(qIndex(),route().arg);
 if(pick||act==='answer'||act==='dead'){
  // the claim is the answer itself; who gave it is stored as settled_by and shown beside it
  const v=pick?pick.dataset.qpick:$('#q-ans')?.value.trim();if(!v)return;
  const claim=/[.?!]$/.test(v)?v:v+'.';
  try{await qPost(act==='dead'?'dead':'answer',{id:id(),claim});await qLoad(true)}catch(err){alert(err.message)}
  return}
 if(!a)return;
 if(act==='settle'){$('#q-af').classList.toggle('on');$('#q-ans')?.focus();return}
 if(act==='reopen'||act==='flag'){
  const n=qIndex().by[id()];
  try{await qPost(act,{id:id(),on:act==='flag'?!n?.needs_human:undefined});await qLoad(true)}catch(err){alert(err.message)}
  return}
 if(a.dataset.qact==='branch'){$('#q-bf').classList.add('on');$('#q-bin').focus();return}
 if(a.dataset.qact==='read'){QS.read=!QS.read;render(true);return}
 if(a.dataset.qact==='ask'){
  const v=$('#q-bin').value.trim();if(!v)return;a.disabled=true;
  try{const q=await qAskPost(v,qFocus(qIndex(),route().arg));qGo(q.id)}catch(err){a.disabled=false;alert(err.message)}
 }
});
document.addEventListener('keydown',e=>{
 if(e.key==='Enter'&&e.target.id==='q-bin')document.querySelector('[data-qact="ask"]')?.click();
 if(e.key==='Enter'&&e.target.id==='q-ans')document.querySelector('[data-qact="answer"]')?.click();
 if((e.key==='Enter'||e.key===' ')&&e.target.classList?.contains('q-row')){e.preventDefault();qGo(e.target.dataset.qgo)}
});

// ---------- tooltip: claims in the tree, exact numbers on evidence, the key
const qTipEl=(()=>{const t=document.createElement('div');t.className='q-tip';t.setAttribute('role','tooltip');document.body.append(t);return t})();
function qLegend(){return `<div class="lg">${[['open','Open'],['answered','Answered'],['dead','Dead end'],['agent','Agent'],['human','You']].map(([s,l])=>`${qShape(s,12)}<span>${l}</span>`).join('')}</div>`}
function qTipShow(el){
 const t=el.dataset.qtip;if(!t)return;
 if(t==='key')qTipEl.innerHTML=qLegend();else qTipEl.textContent=t;
 qTipEl.classList.add('on');
 const rc=el.getBoundingClientRect(),w=qTipEl.offsetWidth,hh=qTipEl.offsetHeight;
 let top=rc.bottom+6;if(top+hh>innerHeight-8)top=rc.top-hh-6;
 qTipEl.style.left=Math.max(8,Math.min(innerWidth-w-8,rc.left+(el.classList.contains('q-row')?28:0)))+'px';qTipEl.style.top=top+'px';
}
const qTipHide=()=>qTipEl.classList.remove('on');
document.addEventListener('mouseover',e=>{const el=e.target.closest?.('[data-qtip]');el?qTipShow(el):qTipHide()});
document.addEventListener('focusin',e=>{const el=e.target.closest?.('[data-qtip]');el?qTipShow(el):qTipHide()});
addEventListener('scroll',qTipHide,true);
addEventListener('hashchange',()=>{qTipHide();if(route().r==='questions')qLoad(true)});

// ---------- ask from selected text: comments.js's selection chip calls window.qAsk(text); a small ask box opens next to
// where the text was, prefilled with whole words, and the question lands under the node the text is about
const qChip=(()=>{const d=document.createElement('div');d.className='q-chip';d.innerHTML=`<div class="q-askf"><input class="q-in" maxlength="120" aria-label="Question"><button class="btn primary" type="button">Ask</button></div><a class="q-done"></a>`;document.body.append(d);return d})();
let qSel=null,qLast=null;
function qParentFor(node){
 const own=node?.closest?.('[data-qnode]');if(own)return own.dataset.qnode;
 const {r,arg}=route();
 if(r==='questions')return arg||null;
 return {hill:'h:',model:'m:',goal:'g:'}[r]&&arg?{hill:'h:',model:'m:',goal:'g:'}[r]+arg:null;
}
// remember the last selection's place; the chip clears the selection before calling qAsk
document.addEventListener('selectionchange',()=>{
 const s=getSelection();if(!s||s.isCollapsed||!s.rangeCount)return;
 const an=s.anchorNode?.nodeType===3?s.anchorNode.parentElement:s.anchorNode;
 if(!an||qChip.contains(an))return;
 qLast={rect:s.getRangeAt(0).getBoundingClientRect(),node:an};
});
function qHide(){qChip.className='q-chip';qSel=null}
function qWords(t,max=60){
 t=String(t||'').replace(/\s+/g,' ').trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}%)]+$/gu,'');
 if(t.length<=max)return t;
 const cut=t.slice(0,max+1).replace(/\s+\S*$/,'');return (cut||t.slice(0,max)).replace(/[\s,;:.-]+$/,'')+'…';
}
window.qAsk=text=>{
 const quote=String(text||'').replace(/\s+/g,' ').trim().slice(0,400);if(!quote)return;
 const rc=qLast?.rect,node=qLast?.node;
 qSel={quote,parent:qParentFor(node&&document.contains(node)?node:null)};
 const inp=qChip.querySelector('input'),w=Math.min(380,innerWidth-16);
 inp.value=`Why "${qWords(quote)}"?`;
 qChip.className='q-chip on form';
 qChip.style.left=Math.max(8,Math.min(innerWidth-w-8,(rc?rc.left:innerWidth/2-w/2)+scrollX))+'px';
 qChip.style.top=Math.max(8,(rc?rc.bottom+8:120)+scrollY)+'px';
 inp.focus();inp.select();
};
document.addEventListener('mousedown',e=>{if(!qChip.contains(e.target)&&!e.target.closest?.('.ask'))qHide()});
async function qChipSubmit(){
 const inp=qChip.querySelector('input'),v=inp.value.trim();if(!v||!qSel)return;
 const sel=qSel;
 try{
  const q=await qPost('ask',{title:v,parent:sel.parent,quote:sel.quote,route:location.hash});
  const done=qChip.querySelector('.q-done');done.href='#questions/'+enc(q.id);done.textContent='Asked';
  qChip.className='q-chip on sent';QS.at=0;setTimeout(qHide,2500);
 }catch(err){alert(err.message)}
}
qChip.querySelector('.q-askf .btn').addEventListener('click',qChipSubmit);
qChip.querySelector('input').addEventListener('keydown',e=>{if(e.key==='Enter')qChipSubmit();if(e.key==='Escape')qHide()});
qChip.querySelector('.q-done').addEventListener('click',()=>setTimeout(qHide,0));
