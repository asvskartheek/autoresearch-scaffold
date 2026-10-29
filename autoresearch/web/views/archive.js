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
const took=t=>t.ended?t.ended-t.created:null;
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
 const bar=`<div class="arc-bar">${search}${kindCtl}${resSel}${sortSel}</div>`;
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
  <td class="num">${tk!=null?wbSpan(tk):DASH}</td>
  <td class="num"><div class="two"><span>${wbWhen(when(t))}</span><span class="sub">${wbAgo(when(t))}</span></div></td>
  <td class="arc-m"><div class="two"${depth?' style="padding-left:20px"':''}><a href="${href}" class="ell"><b>${esc(t.title)}</b></a><span class="sub ell">${[sl+(t.superseded_by?', superseded':''),s!=null?(c?cv(s,t):pct(s)+(n?` · ${Math.round(s*n)} of ${n}`:'')):'',t.model&&mn(t.model),tk!=null?wbSpan(tk):'',wbAgo(when(t))].filter(Boolean).join(' · ')}</span>${fold}</div></td></tr>`};
 const body=vis.map(t=>{const open=ARC.open.has(t.id)||(q&&!match(t,q));
  return row(t,0,open)+(open?desc(t).filter(k=>!q||match(t,q)||match(k,q)).sort((a,b)=>(a.created||0)-(b.created||0)).map(k=>row(k,1)).join(''):'')}).join('');
 const th=(k,label,cls='')=>{const on=ARC.sort===k,dir=ARC.dir>0?'ascending':'descending';
  return `<th class="${cls}" ${on?`aria-sort="${dir}"`:''}><button class="arc-sort ${on?'on':''}" onclick="archiveSort('${k}')">${label}<i aria-hidden="true">${on?(ARC.dir>0?'↑':'↓'):''}</i></button></th>`};
 const more=`<div class="arc-more"><span class="sub">${rows.length>vis.length?`1–${vis.length.toLocaleString()} of ${rows.length.toLocaleString()}`:plural(rows.length,'job')}</span>${rows.length>vis.length?`<button class="btn" onclick="archiveMore()">Show ${Math.min(100,rows.length-vis.length)} more</button>`:''}</div>`;
 const none=empty(q?`No tasks match “${esc(ARC.q.trim())}”`:`No ${ARC.res==='all'?'':esc(ARC.res.toLowerCase())+' '}${S.archiveKind==='all'?'':esc(wbKind(S.archiveKind).toLowerCase())+' '}jobs`,q?`<button class="btn arc-clear" onclick="archiveQ('')">Clear search</button>`:ARC.res!=='all'?`<button class="btn arc-clear" onclick="archiveRes('all')">All results</button>`:'');
 return h+bar+`<section class="card flush arc">
 ${rows.length?`<table><thead><tr>${th('title','Task')}${th('model','Model and slice','arc-mod')}${th('state','Result')}${th('score','Score','num')}${th('took','Took','num')}${th('ended','Ended','num')}<th class="arc-m">Task</th></tr></thead><tbody>${body}</tbody></table>${more}`:none}</section>`;
};
}
