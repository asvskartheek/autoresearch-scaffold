'use strict';
// Archive: what has finished, and how did it end? Search by title, model or slice; sort by any column.
let archiveShown=100;
const ARC_OK=new Set(['done','completed']);
const ARC={q:'',sort:'ended',dir:-1,res:'all',open:new Set()};
function archiveSet(k){S.archiveKind=k;archiveShown=100;render()}
function archiveMore(){archiveShown+=100;render()}
function archiveQ(v){ARC.q=v;archiveShown=100;render()}
function archiveRes(v){ARC.res=v;archiveShown=100;render()}
function archiveFold(id){ARC.open.has(id)?ARC.open.delete(id):ARC.open.add(id);render()}
function archiveSort(k){if(ARC.sort===k)ARC.dir=-ARC.dir;else{ARC.sort=k;ARC.dir=k==='title'||k==='model'||k==='state'?1:-1}render()}
{
const when=t=>t.ended||t.updated;
const took=t=>wbTook(t);
const score=t=>t.summary?.score??null;
const mt=t=>t.model?S.state.models[t.model]?.title||t.model:'';
// a continuous slice scores a mean (with its unit), not a share solved
const cont=t=>S.state.slices[t.slice]?.scale==='continuous';
const cv=(v,t)=>{const a=Math.abs(v),u=S.state.slices[t.slice]?.unit;return (v<0?'−':'')+(a>=10?a.toFixed(1):num(a,3))+(u?'&nbsp;'+esc(u):'')};
const KEYS={title:t=>String(t.title||'').toLowerCase(),model:t=>String(mt(t)||'~').toLowerCase(),state:t=>wbState(t)[0],score,took,ended:when};
const match=(t,q)=>!q||[t.title,t.model,mt(t),t.slice,t.id,t.agent].some(v=>v&&String(v).toLowerCase().includes(q));
const SEARCH=I('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',15);

// one row per job: a sub-task folds under its parent and opens from the parent's row
const isTop=t=>!t.parent||!byId(t.parent);
const resOf=t=>wbState(t)[0];
const desc=t=>tree(t.id).map(([k])=>k).filter(k=>!isLive(k));

// ---------- the session story: what was tried, what each change predicted, and what was found, on one time axis.
// A session is a run of activity (tasks, new models, decisions) with no gap over two hours; the newest comes first.
const GAP=2*3600;
const top=t=>!(t.parent&&byId(t.parent))&&!/^historical/.test(t.kind||'');
function sessions(){
 const st=S.state,ev=[];
 // research work defines a session (a model's runs, evals, trains); answers and chores only fill in around it
 const work=t=>t.model||/^(eval|train|experiment|data)$/.test(t.kind||'');
 for(const t of st.tasks)if(top(t)&&work(t))ev.push([t.created,isLive(t)?now():(t.ended||t.updated||t.created)]);
 for(const m of Object.values(st.models))if(m.created&&m.status!=='historical')ev.push([+m.created,+m.created]);
 for(const d of st.decisions||[])if(d.t&&d.model)ev.push([d.t,d.t]);
 ev.sort((a,b)=>a[0]-b[0]);
 const out=[];for(const [a,b] of ev){const x=out.at(-1);if(x&&a<=x[1]+GAP)x[1]=Math.max(x[1],b);else out.push([a,b])}
 return out.reverse();
}
function sessionOf([a,b]){
 const st=S.state,inS=x=>x>=a-1&&x<=b+1;
 const tasks=st.tasks.filter(t=>top(t)&&inS(t.created)).sort((x,y)=>x.created-y.created);
 const decs=(st.decisions||[]).filter(d=>d.model&&inS(d.t));
 const first=[...tasks.filter(t=>t.model).map(t=>[t.created,t.model]),
  ...Object.entries(st.models).filter(([,m])=>m.created&&m.status!=='historical'&&inS(+m.created)).map(([k,m])=>[+m.created,k]),
  ...decs.map(d=>[d.t,d.model])].sort((x,y)=>x[0]-y[0]);
 const ms=[];for(const [,m] of first)if(st.models[m]&&!ms.includes(m))ms.push(m);
 return {a,b,tasks,decs,ms};
}
// "… Pre-declared: X" → [what changed, what it should move]
const split=c=>{const s=String(c||''),i=s.search(/pre-?declared\s*:?/i);return i<0?[s,'']:[s.slice(0,i).trim().replace(/[.;,]$/,''),s.slice(i).replace(/^pre-?declared\s*:?\s*/i,'')]};
const evScore=t=>{const sm=t.summary||{};if(emptyEval(t))return 'no results';if(sm.score==null)return '';
 return S.state.slices[t.slice]?.scale==='continuous'?sv(t.slice,sm.score,sm.n):sm.n?`${Math.round(sm.score*sm.n).toLocaleString()}/${sm.n.toLocaleString()}`:pct(sm.score)};
const verdict=(m,ds)=>{const d=ds.filter(x=>x.model===m&&/^(rejected|promote|champion)$/.test(x.kind)).at(-1),M=S.state.models[m]||{};
 if(d)return [d.kind==='rejected'?'Rejected':'Promoted',d.kind==='rejected'?'neg':'pos',d.reason||M.reason||''];
 return [M.status==='champion'?'Champion':M.status?wbKind(M.status):'Model',M.status==='champion'?'champion':M.status==='rejected'?'neg':'ghost',''];
};
function story(){
 const ss=sessions();if(!ss.length)return '';
 const i=Math.min(S.arcSess||0,ss.length-1),X=sessionOf(ss[i]),{a,b}=X,w=Math.max(60,b-a);
 const at=x=>Math.max(0,Math.min(100,100*(x-a)/w));
 const st=S.state;
 // one lane per model in play; each eval a bar from start to end, packed into rows so labels never overlap
 // the track's width in px, to size each label in % of it
 const W=innerWidth,trackPx=Math.max(160,W-(W>1100?260:0)-(W>640?236:0)-(W>640?120:96)-64);
 const lane=(ts,lab,top0=0)=>{const rows=[];let h='';
  for(const t of ts){const x0=at(t.created),x1=Math.max(x0+.5,at(isLive(t)?now():t.ended||t.updated||t.created)),sc=t.kind==='eval'?evScore(t):'';
   const lw=lab&&t.kind==='eval'?100*((short(t.slice||'').length+sc.length+1)*7.2+10)/trackPx:0;
   let r=rows.findIndex(e=>e<=x0);if(r<0){r=rows.length;rows.push(0)}rows[r]=x1+lw+.5;
   const [sl,sc_]=wbState(t);
   h+=`<a class="arc-bar ${esc(sc_)}${isLive(t)?' live':''}" href="#task/${enc(t.id)}" style="left:${x0.toFixed(2)}%;width:${(x1-x0).toFixed(2)}%;top:${top0+r*22}px" title="${esc(t.title)} · ${esc(sl)}${sc?' · '+esc(sc):''}"></a>`
    +(lw?`<span class="arc-bl" style="left:calc(${x1.toFixed(2)}% + 4px);top:${top0+r*22}px">${esc(short(t.slice||''))} <b>${esc(sc)}</b></span>`:'');}
  return [h,Math.max(1,rows.length)]};
 const seen=new Set(),ticks=[0,.25,.5,.75,1].map(f=>{const c=wbClock(a+f*w);if(seen.has(c))return '';seen.add(c);return `<span style="left:${100*f}%">${c}</span>`}).join('');
 const lanes=X.ms.map(m=>{
  const M=st.models[m]||{},ts=X.tasks.filter(t=>t.model===m),[vl,vc]=verdict(m,X.decs);
  // created and decided marks sit on their own strip above the bars, so they never cover a label
  const marks=[...(M.created&&+M.created>=a-1?[`<i class="arc-mk new" style="left:${at(+M.created)}%" title="Created${M.change?': '+esc(split(M.change)[0]):''}"></i>`]:[]),
   ...X.decs.filter(d=>d.model===m&&/^(rejected|promote|champion)$/.test(d.kind)).map(d=>`<i class="arc-mk ${d.kind==='rejected'?'neg':'pos'}" style="left:${at(d.t)}%" title="${d.kind==='rejected'?'Rejected':'Promoted'} ${wbClock(d.t)}${d.reason?': '+esc(d.reason):''}"></i>`)].join(''),mt=marks?16:0,[h,n]=lane(ts,true,mt);
  return `<div class="arc-ln"><div class="arc-lh"><a class="ell" href="#model/${enc(m)}" title="${esc(m)}">${mn(m)}</a>${pill(vl,vc)}</div><div class="arc-tr" style="height:${mt+n*22}px">${h}${marks}</div></div>`}).join('');
 const other=X.tasks.filter(t=>!t.model||!st.models[t.model]);
 const kinds={};for(const t of other)kinds[t.kind||'other']=(kinds[t.kind||'other']||0)+1;
 const oLane=other.length?(()=>{const [h]=lane(other,false);return `<div class="arc-ln other"><div class="arc-lh"><span title="${esc(Object.entries(kinds).map(([k,n])=>n+' '+wbKind(k).toLowerCase()).join(', '))}">${plural(other.length,'other job')}</span></div><div class="arc-tr" style="height:22px">${h.replace(/top:\d+px/g,'top:0px')}</div></div>`})():'';
 // tried → predicted → found, one row per model that changed something or was decided on
 const tpf=X.ms.map(m=>{const M=st.models[m]||{},[tried,pred]=split(M.change),[vl,vc,why]=verdict(m,X.decs);
  if(!M.change&&!why)return '';
  const ev={};for(const t of X.tasks)if(t.model===m&&t.kind==='eval'&&t.slice&&evScore(t))ev[t.slice]=t;
  const g=st.gates?.[m],nx=M.status==='candidate'&&g?.next?.[0];
  const chips=Object.values(ev).slice(-6).map(t=>`<a class="arc-sc ${emptyEval(t)?'neg':''}" href="#task/${enc(t.id)}">${esc(short(t.slice))} <b>${esc(evScore(t))}</b></a>`).join('');
  return `<div class="arc-r"><div class="arc-t"><a href="#model/${enc(m)}" title="${esc(m)}"><b>${mn(m)}</b></a>${tried?`<p class="arc-cl" onclick="this.classList.toggle('open')">${esc(tried)}</p>`:''}</div>
   <div class="arc-p">${pred?`<p class="arc-cl" onclick="this.classList.toggle('open')">${esc(pred)}</p>`:'<span class="faint">—</span>'}</div>
   <div class="arc-f"><div class="arc-fv">${pill(vl,vc)}${chips}${nx?`<span class="arc-nx">next ${esc(short(nx.slice||nx.rung||''))}</span>`:''}</div>${why?`<p class="arc-cl" onclick="this.classList.toggle('open')">${esc(why)}</p>`:''}</div></div>`}).filter(Boolean).join('');
 const nEv=X.tasks.filter(t=>t.kind==='eval').length,nRej=X.decs.filter(d=>d.kind==='rejected').length,nPro=X.decs.filter(d=>d.kind==='promote'||d.kind==='champion').length;
 const meta=[plural(X.ms.length,'model'),plural(nEv,'eval'),nPro&&`${nPro} promoted`,nRej&&`${nRej} rejected`].filter(Boolean).join(' · ');
 const nav=`<span class="arc-sn"><button class="btn" ${i+1>=ss.length?'disabled':''} onclick="S.arcSess=${i+1};render()" aria-label="Older session">‹</button><span>${wbDay(a)}, ${wbClock(a)}–${wbClock(b)} <span class="faint">${span(b-a)}</span></span><button class="btn" ${i?'':'disabled'} onclick="S.arcSess=${i-1};render()" aria-label="Newer session">›</button></span>`;
 return panel(i?'Session':'Latest session',`<div class="arc-story">
  ${lanes||oLane?`<div class="arc-tl"><div class="arc-ln arc-ax"><div class="arc-lh"></div><div class="arc-tk">${ticks}</div></div>${lanes}${oLane}</div>`:''}
  ${tpf?`<div class="arc-tpf"><div class="arc-r arc-hd"><div>Tried</div><div>Predicted</div><div>Found</div></div>${tpf}</div>`:''}</div>`,{cls:'section arc-st',meta,right:nav});
}

VIEWS.archive=()=>{
 const every=archived(),all=every.filter(isTop);
 const loading=(S.state.tasks_total||0)>S.state.tasks.length;
 const counts={};for(const t of all){const k=t.kind||'other';counts[k]=(counts[k]||0)+1}
 const kinds=Object.keys(counts).sort((a,b)=>counts[b]-counts[a]);
 if(S.archiveKind!=='all'&&!counts[S.archiveKind])S.archiveKind='all';
 const q=ARC.q.trim().toLowerCase();
 const rcount={};for(const t of all){const r=resOf(t);rcount[r]=(rcount[r]||0)+1}
 if(ARC.res!=='all'&&!rcount[ARC.res])ARC.res='all';
 const inKind=all.filter(t=>(S.archiveKind==='all'||(t.kind||'other')===S.archiveKind)&&(ARC.res==='all'||resOf(t)===ARC.res));
 const key=KEYS[ARC.sort]||KEYS.ended;
 // a search hit on a sub-task shows its job, opened
 const hit=t=>match(t,q)||(q&&desc(t).some(k=>match(k,q)));
 const rows=inKind.filter(hit).sort((a,b)=>{const x=key(a),y=key(b);if(x==null&&y==null)return when(b)-when(a);if(x==null)return 1;if(y==null)return -1;return (x<y?-1:x>y?1:0)*ARC.dir||when(b)-when(a)});
 // the finding: how the tasks in view ended
 const by={};for(const t of rows){const s=wbState(t)[0].toLowerCase();by[s]=(by[s]||0)+1}
 const ends=Object.entries(by).sort((a,b)=>b[1]-a[1]).map(([s,n])=>`${n.toLocaleString()} ${s}`).join(', ');
 const latest=rows.reduce((m,t)=>Math.max(m,when(t)||0),0);
 const scope=(ARC.res==='all'?'':' '+esc(ARC.res.toLowerCase()))+(S.archiveKind==='all'?'':' '+esc(wbKind(S.archiveKind).toLowerCase()))+(rows.length===1?' job':' jobs');
 const finding=(!all.length?'Nothing has finished yet.':rows.length?`<b>${rows.length.toLocaleString()}</b>${scope}${q?` matching “${esc(ARC.q.trim())}”`:''}: ${ends}. The latest ended ${wbAgo(latest)}.`:`No${scope} match${q?` “${esc(ARC.q.trim())}”`:''}.`)+(loading?` <span class="faint">Loading ${(S.state.tasks_total-S.state.tasks.length).toLocaleString()} older tasks…</span>`:'');
 let h=page({title:'Archive',crumbs:[['Archive','#archive']],finding});
 if(!all.length)return h+panel('Finished tasks',empty('Nothing has finished yet','Tasks land here when they end. Start one with <code>arx task start</code> or <code>arx.task(...)</code>.'));
 // kind filter: a segmented control for a few kinds, a select for many
 const opts=[['all',all.length],...kinds.map(k=>[k,counts[k]])];
 const kindCtl=kinds.length<=5
  ?`<div class="seg arc-seg" role="group" aria-label="Kind">${opts.map(([k,n])=>`<button class="${k===S.archiveKind?'on':''}" aria-pressed="${k===S.archiveKind}" onclick="archiveSet('${esc(k)}')">${k==='all'?'All':esc(wbKind(k))}<small>${n.toLocaleString()}</small></button>`).join('')}</div>`
  :`<label class="arc-sel"><span class="sr">Kind</span><select onchange="archiveSet(this.value)">${opts.map(([k,n])=>`<option value="${esc(k)}" ${k===S.archiveKind?'selected':''}>${k==='all'?'All kinds':esc(wbKind(k))} (${n.toLocaleString()})</option>`).join('')}</select></label>`;
 const search=`<label class="arc-q">${SEARCH}<span class="sr">Search title, model or slice</span><input id="arc-q" type="search" placeholder="Title, model or slice" value="${esc(ARC.q)}" autocomplete="off" spellcheck="false" oninput="archiveQ(this.value)" onkeydown="if(event.key==='Escape'&&this.value){event.stopPropagation();archiveQ('')}"></label>`;
 const SORTS=[['ended',-1,'Newest first'],['ended',1,'Oldest first'],['score',-1,'Highest score'],['took',-1,'Longest'],['title',1,'Title A–Z']];
 const sortSel=`<label class="arc-sel arc-sortsel"><span class="sr">Sort</span><select onchange="const [k,d]=this.value.split(':');ARC.sort=k;ARC.dir=+d;render()">${SORTS.map(([k,d,l])=>`<option value="${k}:${d}" ${ARC.sort===k&&ARC.dir===d?'selected':''}>${l}</option>`).join('')}</select></label>`;
 const RES=Object.keys(rcount).sort((a,b)=>rcount[b]-rcount[a]);
 const resSel=`<label class="arc-sel"><span class="sr">Result</span><select onchange="archiveRes(this.value)"><option value="all">All results (${all.length.toLocaleString()})</option>${RES.map(r=>`<option value="${esc(r)}" ${r===ARC.res?'selected':''}>${esc(r)} (${rcount[r].toLocaleString()})</option>`).join('')}</select></label>`;
 const bar=`<div class="arc-tools">${search}${kindCtl}${resSel}${sortSel}</div>`;
 const vis=rows.slice(0,archiveShown);
 const row=(t,depth=0,open=false)=>{
  const [sl,sc]=wbState(t),ks=depth?[]:desc(t),nk=ks.length,tk=took(t),n=t.summary?.n,s=score(t),c=cont(t);
  const fold=nk?`<button class="arc-fold ${open?'on':''}" type="button" aria-expanded="${open}" onclick="event.stopPropagation();archiveFold('${esc(t.id)}')">${plural(nk,'sub-task')}</button>`:'';
  const sub=[esc(wbKind(t.kind||'other')),t.agent&&'by '+esc(t.agent),t.model&&`<span class="arc-mi">${mn(t.model)}</span>`].filter(Boolean).join(' · ');
  const href=`#task/${enc(t.id)}`;
  return `<tr class="click ${depth?'arc-kid':''}" onclick="if(!event.target.closest('a,button'))location.hash='${href}'">
  <td class="arc-task"><div class="two"${depth?' style="padding-left:20px"':''}><a href="${href}" class="ell"><b>${esc(t.title)}</b></a><span class="sub ell">${sub}${fold?' · '+fold:''}</span></div></td>
  <td class="arc-mod">${t.model?`<div class="two"><a class="ell arc-ml" href="#model/${enc(t.model)}" title="${esc(t.model)}">${mn(t.model)}</a><span class="sub ell" title="${esc(t.slice||'')}">${t.slice?esc(short(t.slice)):''}</span></div>`:DASH}</td>
  <td>${st(sc,sl)}${t.superseded_by?`<span class="arc-sup" title="A later run replaced it; gates and baselines skip it">superseded</span>`:''}</td>
  <td class="num">${s!=null?`<div class="two"><span>${c?cv(s,t):pct(s)}</span><span class="sub">${n?(c?`mean of ${n.toLocaleString()}`:`${Math.round(s*n).toLocaleString()} of ${n.toLocaleString()}`):''}</span></div>`:DASH}</td>
  <td class="num">${tk!=null?wbSpan(tk):t.ended?'<span class="faint" title="Rows recorded from another run">recorded</span>':DASH}</td>
  <td class="num"><div class="two"><span>${wbWhen(when(t))}</span><span class="sub">${wbAgo(when(t))}</span></div></td>
  <td class="arc-m"><div class="two"${depth?' style="padding-left:20px"':''}><a href="${href}" class="ell"><b>${esc(t.title)}</b></a><span class="sub ell">${[sl+(t.superseded_by?', superseded':''),s!=null?(c?cv(s,t):pct(s)+(n?` · ${Math.round(s*n)} of ${n}`:'')):'',t.model&&mn(t.model),tk!=null?wbSpan(tk):'',wbAgo(when(t))].filter(Boolean).join(' · ')}</span>${fold}</div></td></tr>`};
 const body=vis.map(t=>{const open=ARC.open.has(t.id)||(q&&!match(t,q));
  return row(t,0,open)+(open?desc(t).filter(k=>!q||match(t,q)||match(k,q)).sort((a,b)=>(a.created||0)-(b.created||0)).map(k=>row(k,1)).join(''):'')}).join('');
 const th=(k,label,cls='')=>{const on=ARC.sort===k,dir=ARC.dir>0?'ascending':'descending';
  return `<th class="${cls}" ${on?`aria-sort="${dir}"`:''}><button class="arc-sort ${on?'on':''}" onclick="archiveSort('${k}')">${label}<i aria-hidden="true">${on?(ARC.dir>0?'↑':'↓'):''}</i></button></th>`};
 const more=`<div class="arc-more"><span class="sub">${rows.length>vis.length?`1–${vis.length.toLocaleString()} of ${rows.length.toLocaleString()}`:plural(rows.length,'job')}</span>${rows.length>vis.length?`<button class="btn" onclick="archiveMore()">Show ${Math.min(100,rows.length-vis.length)} more</button>`:''}</div>`;
 const none=empty(q?`No tasks match “${esc(ARC.q.trim())}”`:`No ${ARC.res==='all'?'':esc(ARC.res.toLowerCase())+' '}${S.archiveKind==='all'?'':esc(wbKind(S.archiveKind).toLowerCase())+' '}jobs`,q?`<button class="btn arc-clear" onclick="archiveQ('')">Clear search</button>`:ARC.res!=='all'?`<button class="btn arc-clear" onclick="archiveRes('all')">All results</button>`:'');
 return h+story()+bar+`<section class="card flush arc">
 ${rows.length?`<table><thead><tr>${th('title','Task')}${th('model','Model and slice','arc-mod')}${th('state','Result')}${th('score','Score','num')}${th('took','Took','num')}${th('ended','Ended','num')}<th class="arc-m">Task</th></tr></thead><tbody>${body}</tbody></table>${more}`:none}</section>`;
};
}
