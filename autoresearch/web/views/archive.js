// Archive: what has finished, and how did it end? Search by title, model or slice; sort by any column.
let archiveShown=100;
const ARC_OK=new Set(['done','completed']);
const ARC={q:'',sort:'ended',dir:-1};
function archiveSet(k){S.archiveKind=k;archiveShown=100;render()}
function archiveMore(){archiveShown+=100;render()}
function archiveQ(v){ARC.q=v;archiveShown=100;render()}
function archiveSort(k){if(ARC.sort===k)ARC.dir=-ARC.dir;else{ARC.sort=k;ARC.dir=k==='title'||k==='model'||k==='state'?1:-1}render()}
{
const when=t=>t.ended||t.updated;
const took=t=>t.ended?t.ended-t.created:null;
const score=t=>t.summary?.score??null;
const KEYS={title:t=>String(t.title||'').toLowerCase(),model:t=>String(t.model||'~').toLowerCase(),state:t=>wbState(t)[0],score,took,ended:when};
const match=(t,q)=>!q||[t.title,t.model,t.slice,t.id,t.agent].some(v=>v&&String(v).toLowerCase().includes(q));
// keep the search box's focus and caret across the 4s redraw: read them before the new HTML lands, put them back after
function keepFocus(){
 const el=document.activeElement;if(el?.id!=='arc-q')return;
 const a=el.selectionStart,b=el.selectionEnd;
 queueMicrotask(()=>{const n=document.getElementById('arc-q');if(n){n.focus();try{n.setSelectionRange(a,b)}catch(e){}}});
}
const SEARCH=I('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',15);

VIEWS.archive=()=>{
 keepFocus();
 const all=archived();
 const counts={};for(const t of all){const k=t.kind||'other';counts[k]=(counts[k]||0)+1}
 const kinds=Object.keys(counts).sort((a,b)=>counts[b]-counts[a]);
 if(S.archiveKind!=='all'&&!counts[S.archiveKind])S.archiveKind='all';
 const q=ARC.q.trim().toLowerCase();
 const inKind=all.filter(t=>S.archiveKind==='all'||(t.kind||'other')===S.archiveKind);
 const key=KEYS[ARC.sort]||KEYS.ended;
 const rows=inKind.filter(t=>match(t,q)).sort((a,b)=>{const x=key(a),y=key(b);if(x==null&&y==null)return when(b)-when(a);if(x==null)return 1;if(y==null)return -1;return (x<y?-1:x>y?1:0)*ARC.dir||when(b)-when(a)});
 // the finding: how the tasks in view ended
 const by={};for(const t of rows){const s=wbState(t)[0].toLowerCase();by[s]=(by[s]||0)+1}
 const ends=Object.entries(by).sort((a,b)=>b[1]-a[1]).map(([s,n])=>`${n.toLocaleString()} ${s}`).join(', ');
 const latest=rows.reduce((m,t)=>Math.max(m,when(t)||0),0);
 const scope=(S.archiveKind==='all'?'':' '+esc(wbKind(S.archiveKind).toLowerCase()))+(rows.length===1?' task':' tasks');
 const finding=!all.length?'Nothing has finished yet.':rows.length?`<b>${rows.length.toLocaleString()}</b>${scope}${q?` matching “${esc(ARC.q.trim())}”`:''}: ${ends}. The latest ended ${wbAgo(latest)}.`:`No${scope} match “${esc(ARC.q.trim())}”.`;
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
 const bar=`<div class="arc-bar">${search}${kindCtl}${sortSel}</div>`;
 const vis=rows.slice(0,archiveShown);
 const body=vis.map(t=>{
  const [sl,sc]=wbState(t),nk=kids(t.id).length,tk=took(t),n=t.summary?.n,s=score(t);
  const sub=[esc(wbKind(t.kind||'other')),t.agent&&'by '+esc(t.agent),nk&&plural(nk,'sub-task')].filter(Boolean).join(' · ');
  const href=`#task/${enc(t.id)}`;
  return `<tr class="click" onclick="if(!event.target.closest('a'))location.hash='${href}'">
  <td class="arc-task"><div class="two"><a href="${href}" class="ell"><b>${esc(t.title)}</b></a><span class="sub ell">${sub}</span></div></td>
  <td class="arc-mod">${t.model?`<div class="two"><a class="ell arc-ml" href="#model/${enc(t.model)}">${esc(t.model)}</a><span class="sub ell" title="${esc(t.slice||'')}">${t.slice?esc(short(t.slice)):''}</span></div>`:DASH}</td>
  <td>${st(sc,sl)}</td>
  <td class="num">${s!=null?`<div class="two"><span>${pct(s)}</span><span class="sub">${n?`${Math.round(s*n).toLocaleString()} of ${n.toLocaleString()}`:''}</span></div>`:DASH}</td>
  <td class="num">${tk!=null?wbSpan(tk):DASH}</td>
  <td class="num"><div class="two"><span>${wbWhen(when(t))}</span><span class="sub">${wbAgo(when(t))}</span></div></td>
  <td class="arc-m"><div class="two"><a href="${href}" class="ell"><b>${esc(t.title)}</b></a><span class="sub ell">${[sl,s!=null?pct(s)+(n?` · ${Math.round(s*n)} of ${n}`:''):'',t.model&&esc(t.model),tk!=null?wbSpan(tk):'',wbAgo(when(t))].filter(Boolean).join(' · ')}</span></div></td></tr>`}).join('');
 const th=(k,label,cls='')=>{const on=ARC.sort===k,dir=ARC.dir>0?'ascending':'descending';
  return `<th class="${cls}" ${on?`aria-sort="${dir}"`:''}><button class="arc-sort ${on?'on':''}" onclick="archiveSort('${k}')">${label}<i aria-hidden="true">${on?(ARC.dir>0?'↑':'↓'):''}</i></button></th>`};
 const more=`<div class="arc-more"><span class="sub">${rows.length>vis.length?`1–${vis.length.toLocaleString()} of ${rows.length.toLocaleString()}`:plural(rows.length,'task')}</span>${rows.length>vis.length?`<button class="btn" onclick="archiveMore()">Show ${Math.min(100,rows.length-vis.length)} more</button>`:''}</div>`;
 const none=empty(q?`No tasks match “${esc(ARC.q.trim())}”`:`No ${esc(wbKind(S.archiveKind).toLowerCase())} tasks finished`,q?`<button class="btn arc-clear" onclick="archiveQ('')">Clear search</button>`:'');
 return h+bar+`<section class="card flush arc">
 ${rows.length?`<table><thead><tr>${th('title','Task')}${th('model','Model and slice','arc-mod')}${th('state','Result')}${th('score','Score','num')}${th('took','Took','num')}${th('ended','Ended','num')}<th class="arc-m">Task</th></tr></thead><tbody>${body}</tbody></table>${more}`:none}</section>`;
};
}
