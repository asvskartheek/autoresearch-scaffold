'use strict';
// Questions: the project as a tree of questions (seeded from goals, hills and models; see autoresearch/questions.py).
// Left: the outline, claims on hover. Right: the focused question, its claim and its evidence as paired-delta dots
// with CI and fixed/broke squares. "Ask" under any node, or from selected text on any view (the chip), sends a
// question to an agent (status agent, inbox kind=question).
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
const qSgn=v=>(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(1);
function qTag(e){return e.role||(e.slice||'').split('/').pop()}
function qCol(e){
 if(e.lo!=null&&e.hi!=null)return e.lo>0?'var(--positive)':e.hi<0?'var(--negative)':'var(--muted)';
 return e.delta>0?'var(--positive)':e.delta<0?'var(--negative)':'var(--muted)';
}
function qTipOf(e){
 if(e.kind==='missing')return `${e.model||e.task}\n${e.slice||''}\nNot run`;
 const head=`${e.label||e.model||''}\n${e.slice||e.what||''}${e.n?' · n '+qFmt(e.n):''}`;
 if(e.kind==='raw')return `${head}\n${qFmt(e.c)} of ${qFmt(e.n)}`+(e.what?`\n${e.what}`:'');
 return `${head}\n${qFmt(e.c)} vs ${qFmt(e.bc)} (${e.base})\n${qSgn(100*e.delta)} pts`+(e.lo!=null?` · 90% CI ${qSgn(100*e.lo)} to ${qSgn(100*e.hi)}`:'')+
  `\n${e.wins??0} fixed · ${e.losses??0} broke`;
}
function qSquares(e){
 if(e.kind!=='paired'||(!e.wins&&!e.losses))return '';
 const u=Math.max(1,Math.ceil((e.wins+e.losses)/28));
 return `<span title="${e.wins} fixed · ${e.losses} broke">`+'<i class="f"></i>'.repeat(Math.ceil(e.wins/u))+'<i class="b"></i>'.repeat(Math.ceil(e.losses/u))+'</span>';
}
function qEvidence(n){
 const ev=n.ev||[];if(!ev.length)return '';
 const dl=ev.filter(e=>e.kind==='paired'&&e.delta!=null);
 const R=Math.max(3,Math.ceil(Math.max(0,...dl.flatMap(e=>[Math.abs(100*e.delta),Math.abs(100*(e.lo??0)),Math.abs(100*(e.hi??0))]))*1.1));
 const x=v=>50+Math.max(-R,Math.min(R,v))/R*48;
 const rows=ev.map(e=>{
  let lane;
  if(e.kind==='missing')lane=`<div class="trk dashed"></div>`;
  else if(e.kind==='raw')lane=`<div class="trk"></div><div class="fill" style="width:${e.n?(100*e.c/e.n).toFixed(1):0}%"></div>`;
  else{const col=qCol(e),d=100*e.delta;
   lane=`<div class="z"></div>`+(e.lo!=null?`<div class="ci" style="left:${x(100*e.lo)}%;width:${Math.max(.5,x(100*e.hi)-x(100*e.lo))}%;background:${col}"></div>`:'')+`<div class="d" style="left:${x(d)}%;background:${col}"></div>`}
  const href=e.task?`#task/${enc(e.task)}`:e.model?`#model/${enc(e.model)}`:'';
  return `<${href?'a':'div'} class="q-lr"${href?` href="${href}"`:''} tabindex="0" data-qtip="${esc(qTipOf(e))}"><span class="tag">${esc(qTag(e))}</span><div class="lane">${lane}</div><div class="sq">${qSquares(e)}</div></${href?'a':'div'}>`;
 }).join('');
 const axis=dl.length?`<div class="q-lr axis"><span></span><div class="ax"><span>−${R}</span><span>0</span><span>+${R} pts</span></div><span></span></div>`:'';
 return `<div class="q-ev">${rows}${axis}</div>`;
}

// ---------- goal distance in units, with the champion succession as a sparkline
function qDistance(gk){
 const g=QS.data.goals?.[gk];if(!g||g.value==null)return '';
 let txt;
 if(g.kpi==='score'&&g.n){const need=Math.ceil(g.target*g.n-1e-9),have=Math.round(g.value*g.n);txt=g.met?`met · ${qFmt(have)} of ${qFmt(g.n)}`:`<b>${qFmt(need-have)}</b> more of ${qFmt(g.n)}`}
 else txt=g.met?'met':`<b>${num(Math.abs(g.gap))}</b> to go`;
 const ps=g.points.map(p=>p[1]);let svg='';
 if(ps.length>1){
  const W=90,H=22,all=[...ps,g.target],lo=Math.min(...all),hi=Math.max(...all),r=hi-lo||1;
  const X=i=>3+i/(ps.length-1)*(W-6),Y=v=>H-3-(v-lo)/r*(H-6);
  svg=`<svg width="${W}" height="${H}" aria-hidden="true"><line x1="0" x2="${W}" y1="${Y(g.target)}" y2="${Y(g.target)}" stroke="var(--chart-3)" stroke-dasharray="2 2"/><polyline points="${ps.map((v,i)=>X(i)+','+Y(v)).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="1.6"/><circle cx="${X(ps.length-1)}" cy="${Y(ps.at(-1))}" r="2.5" fill="var(--accent)"/></svg>`}
 const tip=g.points.map(p=>`${p[0]}: ${g.kpi==='score'&&g.n?qFmt(Math.round(p[1]*g.n))+' of '+qFmt(g.n):num(p[1])}`).join('\n')+`\ntarget ${g.kpi==='score'?pct(g.target):num(g.target)} on ${g.slice}`;
 return `<a class="q-dist" href="#goal/${enc(gk)}" data-qtip="${esc(tip)}">${svg}<span>${txt}</span></a>`;
}

// ---------- the focused question
function qPath(id,ix){const p=[];for(let x=ix.by[ix.by[id]?.parent];x;x=ix.by[x.parent])p.unshift(x);return p}
function qPanel(id,ix){
 const n=ix.by[id];if(!n)return empty('No question');
 const w=qWaiting(n),cls=w?'human':n.status;
 let h=`<div class="q-path">${qPath(id,ix).map(p=>`<a data-qgo="${esc(p.id)}">${esc(p.title)}</a><span>/</span>`).join('')}</div>`+
  `<div class="q-fq"><span class="q-sh">${qShape(n,18)}</span><h2>${esc(n.title)}</h2></div>`;
 if(n.status==='agent'){
  const L=n.live||{},pr=L.progress,f=pr&&pr.total?Math.min(1,(pr.done||0)/pr.total):null;
  const line=L.status==='failed'?('Agent failed'+(L.error?': '+L.error:'')):L.note||(L.status==='running'?'Agent working':'Queued for an agent');
  h+=`<div class="q-claim agent">${esc(line)}${L.task?` <a class="q-tl" href="#task/${enc(L.task)}">${esc(L.task)}</a>`:''}${f!=null?`<div class="pb"><i style="width:${(100*f).toFixed(1)}%"></i></div>`:''}</div>`;
 }else if(n.claim)h+=`<div class="q-claim ${cls}">${esc(n.claim)}</div>`;
 if(n.quote)h+=`<div class="q-quote"><mark>${esc(n.quote)}</mark></div>`;
 h+=qEvidence(n);
 if(w)h+=`<div class="q-acts">${(n.choices||[]).map((c,i)=>`<button class="btn ${i?'':'q-warn'}" data-qpick="${esc(c)}">${esc(c)}</button>`).join('')}</div>`+
  `<div class="q-form on"><input class="q-in" id="q-ans" aria-label="Your answer" placeholder="Your answer"><button class="btn primary" data-qact="answer">Answer</button></div>`;
 const ks=ix.kids[id]||[];
 if(ks.length)h+=`<div class="q-kids">${ks.map(k=>{const c=ix.by[k];return `<button class="q-kid" data-qgo="${esc(k)}" data-qnode="${esc(k)}"${c.claim?` data-qtip="${esc(c.claim)}"`:''}><span class="q-sh">${qShape(c)}</span><span>${esc(c.title)}</span></button>`}).join('')}</div>`;
 h+=`<div class="q-acts"><button class="btn primary" data-qact="branch">Ask</button><button class="btn ${QS.read?'on':''}" data-qact="read" aria-expanded="${QS.read}">Read</button>`+
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
 if(!QS.data)return page({title:'Questions'})+(QS.err?`<div class="banner">${esc(QS.err)}</div>`:empty('Reading the ledger…'));
 const ix=qIndex();
 if(!QS.closed)QS.closed=qDefaultClosed(ix.by,ix.kids);
 const focus=qFocus(ix,arg);
 if(!focus)return page({title:'Questions'})+empty('No questions yet','<span>arx q add "&lt;title&gt;"</span>');
 for(let x=ix.by[ix.by[focus].parent];x;x=ix.by[x.parent])QS.closed.delete(x.id);
 const hs=QS.data.nodes.filter(qWaiting);
 const need=hs.length?`<details class="q-need"><summary class="q-ib">${qShape('human',10)}${hs.length}</summary><div class="q-pop">${hs.map(n=>`<button data-qgo="${esc(n.id)}">${qShape('human',10)}<span>${esc(n.title)}</span></button>`).join('')}</div></details>`:'';
 const key=`<span class="q-ib key" tabindex="0" data-qtip="key"><svg width="14" height="14" viewBox="0 0 14 14" aria-label="Key"><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="7" cy="4.3" r=".9" fill="currentColor"/><path d="M7 6.5V10.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></span>`;
 const roots=ix.kids['']||[];
 return page({title:'Questions',acts:qDistance(qRootGoal(focus,ix))})+
  `<section class="card flush qv"><div class="q-col q-tree"><div class="q-bar">${need}${key}</div><ul class="q-t">${roots.map(r=>qRow(r,ix,focus)).join('')}</ul></div>`+
  `<div class="q-col q-panel" id="q-panel">${qPanel(focus,ix)}</div></section>`;
};

// ---------- interaction
function qGo(id){
 history.replaceState(null,'','#questions/'+enc(id));
 render(true);
 const p=document.getElementById('q-panel');if(p&&(p.getBoundingClientRect().top<0||innerWidth<=820))p.scrollIntoView({behavior:'smooth',block:'start'});
}
async function qAsk(title,parent,quote){
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
 if(pick||a?.dataset.qact==='answer'){
  const claim=pick?pick.dataset.qpick:$('#q-ans')?.value.trim();if(!claim)return;
  try{await qPost('answer',{id:qFocus(qIndex(),route().arg),claim:pick?`${qName()}: ${claim}.`:claim});await qLoad(true)}catch(err){alert(err.message)}
  return}
 if(!a)return;
 if(a.dataset.qact==='branch'){$('#q-bf').classList.add('on');$('#q-bin').focus();return}
 if(a.dataset.qact==='read'){QS.read=!QS.read;render(true);return}
 if(a.dataset.qact==='ask'){
  const v=$('#q-bin').value.trim();if(!v)return;a.disabled=true;
  try{const q=await qAsk(v,qFocus(qIndex(),route().arg));qGo(q.id)}catch(err){a.disabled=false;alert(err.message)}
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

// ---------- select text on any view: a small "Ask" chip; the question lands under the node the text is about
const qChip=(()=>{const d=document.createElement('div');d.className='q-chip';d.innerHTML=`<button class="q-chipb" type="button">${ICON.questions}<span>Ask</span></button><div class="q-askf"><input class="q-in" maxlength="120" aria-label="Question"><button class="btn primary" type="button">Ask</button></div><a class="q-done"></a>`;document.body.append(d);return d})();
let qSel=null;
function qParentFor(node){
 const own=node?.closest?.('[data-qnode]');if(own)return own.dataset.qnode;
 const {r,arg}=route();
 if(r==='questions')return arg||null;
 return {hill:'h:',model:'m:',goal:'g:'}[r]&&arg?{hill:'h:',model:'m:',goal:'g:'}[r]+arg:null;
}
function qChipHide(){qChip.className='q-chip';qSel=null}
function qChipCheck(){
 if(qChip.contains(document.activeElement))return;
 const s=getSelection();if(!s||s.isCollapsed||!s.rangeCount){if(!qChip.classList.contains('form'))qChipHide();return}
 const txt=s.toString().replace(/\s+/g,' ').trim(),an=s.anchorNode?.nodeType===3?s.anchorNode.parentElement:s.anchorNode;
 if(txt.length<3||!an||!$('#main').contains(an)||an.closest('input,textarea,[contenteditable],.q-form'))return;
 const rc=s.getRangeAt(0).getBoundingClientRect();
 qSel={quote:txt.slice(0,400),parent:qParentFor(an)};
 qChip.className='q-chip on';
 qChip.style.left=Math.max(8,Math.min(innerWidth-120,rc.left+scrollX))+'px';
 qChip.style.top=Math.max(8,rc.top+scrollY-34)+'px';
}
document.addEventListener('mouseup',()=>setTimeout(qChipCheck,0));
document.addEventListener('touchend',()=>setTimeout(qChipCheck,250));
document.addEventListener('mousedown',e=>{if(!qChip.contains(e.target))qChipHide()});
qChip.querySelector('.q-chipb').addEventListener('click',()=>{
 if(!qSel)return;const q=qSel.quote,inp=qChip.querySelector('input');
 inp.value=`Why "${q.length>60?q.slice(0,58)+'…':q}"?`;
 qChip.className='q-chip on form';
 qChip.style.left=Math.max(8,Math.min(innerWidth-Math.min(380,innerWidth-16)-8,parseFloat(qChip.style.left)))+'px';
 inp.focus();inp.select();
});
async function qChipSubmit(){
 const inp=qChip.querySelector('input'),v=inp.value.trim();if(!v||!qSel)return;
 const sel=qSel;
 try{
  const q=await qPost('ask',{title:v,parent:sel.parent,quote:sel.quote,route:location.hash});
  getSelection().removeAllRanges();
  const done=qChip.querySelector('.q-done');done.href='#questions/'+enc(q.id);done.textContent='Asked';
  qChip.className='q-chip on sent';QS.at=0;setTimeout(qChipHide,2500);
 }catch(err){alert(err.message)}
}
qChip.querySelector('.q-askf .btn').addEventListener('click',qChipSubmit);
qChip.querySelector('input').addEventListener('keydown',e=>{if(e.key==='Enter')qChipSubmit();if(e.key==='Escape')qChipHide()});
qChip.querySelector('.q-done').addEventListener('click',()=>setTimeout(qChipHide,0));
