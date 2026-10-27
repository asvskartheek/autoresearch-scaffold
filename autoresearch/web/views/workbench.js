'use strict';
// Workbench: what is running right now, is any of it stuck, and when will it finish?
// Also defines the task helpers archive.js and task.js use (loaded after this file); they are prefixed wb*.

// ---------- words for times: one date format ("26 Oct, 04:53"), durations spelled out ("2 min", "1 h 39 min")
const wbClock=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
const wbDay=t=>{const d=new Date(t*1000),y=new Date(now()*1000).getFullYear();return d.toLocaleDateString('en-GB',{day:'numeric',month:'short',...(d.getFullYear()!==y?{year:'numeric'}:{})})};
const wbWhen=t=>t?`${wbDay(t)}, ${wbClock(t)}`:'—';
const wbSpan=s=>{if(s==null||!isFinite(s))return '—';s=Math.max(0,s);
 if(s<60)return Math.round(s)+' s';if(s<3600)return Math.round(s/60)+' min';
 if(s<86400){const h=Math.floor(s/3600),m=Math.round(s%3600/60);return m===60?(h+1)+' h':h+' h'+(m?' '+m+' min':'')}
 const d=Math.floor(s/86400),h=Math.round(s%86400/3600);return d+' d'+(h&&h<24?' '+h+' h':'')};
const wbAgo=t=>{if(!t)return '—';const d=now()-t;return d<10?'just now':wbSpan(d)+' ago'};
const wbKind=k=>{const s=String(k||'task').replace(/[_-]+/g,' ');return s[0].toUpperCase()+s.slice(1)};
// a finished status in one word; 'completed' is the same as done
const endLabel=t=>t.status==='completed'?'done':t.status;
const partialEval=t=>t.kind==='eval'&&(t.status==='done'||t.status==='completed')&&t.complete===false;
// [label, class] for a task's state, sentence case
const wbState=t=>partialEval(t)?['Partial','partial']:({done:['Done','done'],completed:['Done','done'],failed:['Failed','failed'],budget:['Out of time','budget'],stalled:['Stalled','stalled'],running:['Running','running']})[t.status]||[wbKind(t.status),t.status];
// elapsed against the time budget: [text, cls]; cls warns past 80% and goes red past the cap
function budgetLine(t){
 const el=(t.ended||now())-t.created;
 if(!t.budget_s)return [wbSpan(el),''];
 const f=el/t.budget_s;
 return [`${wbSpan(el)} of ${wbSpan(t.budget_s)}`,f>=1?'neg':f>=.8?'warn':''];
}
// span() now lives in core.js
const silent=t=>wbSpan(now()-t.heartbeat);
const fin=t=>t.eta&&t.status==='running'?t.eta.finish_at:null;
const wbFixCmd=t=>`arx task finish ${t.id} --status failed`;

function wbFacts(t){
 const pr=t.progress||{},stalled=t.status==='stalled',[bt,bc]=budgetLine(t);
 const f=pr.total?Math.min(1,pr.done/pr.total):null;
 const rows=[];
 if(f!=null)rows.push(`<div class="wb-prog"><div class="wb-pl"><span><b>${pr.done.toLocaleString()}</b> of ${pr.total.toLocaleString()}</span><span>${(100*f).toFixed(0)}%</span></div>${meter(f,{cls:stalled?'muted':''})}</div>`);
 const kv=[];
 if(!stalled)kv.push(['Finishes',t.eta?`in ${wbSpan(t.eta.eta_s)} <span class="faint">· ${wbClock(t.eta.finish_at)}</span>`:'<span class="faint">No estimate yet</span>']);
 kv.push(['Elapsed',`<span class="${bc}">${bt}</span>`]);
 kv.push(['Last heard',stalled?`<span class="neg">${wbAgo(t.heartbeat)}</span>`:wbAgo(t.heartbeat)]);
 const last=Object.entries(t.last||{}).filter(([k,v])=>typeof v==='number'&&k!==t.spark?.key).slice(0,2);
 for(const [k,v] of last)kv.push([esc(wbMetric(k)),fmtv(v)]);
 rows.push(`<dl class="wb-kv">${kv.map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`);
 if(t.spark?.y?.length>1){const y=t.spark.y,k=t.spark.key,isPct=/score|acc/.test(k)&&S.state.slices[t.slice]?.scale!=='continuous';
  rows.push(`<div class="wb-spark"><div class="wb-pl"><span>${esc(wbMetric(k))}</span><b>${isPct?pct(y.at(-1)):fmtv(y.at(-1))}</b></div>${spark(y,stalled?'var(--faint)':'var(--chart-1)',28)}</div>`)}
 return rows.join('');
}
// metric keys as words: running_score → Score so far, latency_s → Latency (s)
const wbMetric=k=>({running_score:'Score so far',score:'Score',latency_s:'Latency (s)',loss:'Loss',reward:'Reward',acc:'Accuracy',accuracy:'Accuracy',lr:'Learning rate'})[k]||wbKind(String(k).replace(/_s$/,' (s)'));

// one root task: identity, latest note, the live sub-task tree on the left; progress and timing on the right.
// The whole card opens the task (the title's link is stretched over it); "Open" is the keyboard stop.
function taskCard(t){
 const stalled=t.status==='stalled',sub=tree(t.id),live=sub.filter(([k])=>isLive(k));
 const shown=live.concat(sub.filter(([k])=>!isLive(k))).slice(0,Math.max(5,live.length));
 const href=`#task/${enc(t.id)}`;
 const meta=[esc(wbKind(t.kind)),t.agent&&`by ${esc(t.agent)}`,t.model&&`<a class="wb-in" href="#model/${enc(t.model)}" title="${esc(t.model)}">${mn(t.model)}</a>`,t.slice&&`<span title="${esc(t.slice)}">${esc(short(t.slice))}</span>`].filter(Boolean);
 const note=t.note?`<div class="note ${esc(t.note.level)}"><span class="msg" title="${esc(t.note.text??t.note.msg)}">${esc(t.note.text??t.note.msg)}</span><span class="when">${wbAgo(t.note.t)}</span></div>`:`<div class="note"><span class="msg faint">No notes yet</span></div>`;
 return `<article class="card wb-card ${stalled?'is-stalled':''}">
 <div class="wb-main">
  <div class="wb-head">${stalled?pill('Stalled','stalled'):st('running','Running')}<span class="wb-meta">${meta.join('<i>·</i>')}</span><a class="wb-open wb-in" href="${href}" aria-label="Open ${esc(t.title)}">Open<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></a></div>
  <h2 class="wb-t"><a href="${href}" tabindex="-1">${esc(t.title)}</a></h2>
  ${t.description?`<p class="wb-desc">${esc(t.description)}</p>`:''}
  ${note}
  ${stalled?`<div class="wb-fix"><span>If its process is gone, end it:</span>${cmd(wbFixCmd(t))}</div>`:''}
  ${sub.length?`<div class="wb-kids wb-in"><div class="wb-kh">${plural(sub.length,'sub-task')}${live.length?` · ${live.length} running`:''}</div>${shown.map(kidRow).join('')}${sub.length>shown.length?`<a class="kid more-k" href="${href}"><span class="nm">${sub.length-shown.length} more</span></a>`:''}</div>`:''}
 </div>
 <div class="wb-side">${wbFacts(t)}</div>
 </article>`;
}

VIEWS.workbench=()=>{
 // a running task whose parent is also running shows inside the parent's card, not as its own
 const roots=active().filter(t=>!isLive(byId(t.parent)));
 const stalled=roots.filter(t=>t.status==='stalled').sort((a,b)=>a.heartbeat-b.heartbeat);
 const running=roots.filter(t=>t.status==='running').sort((a,b)=>(fin(a)??1e12)-(fin(b)??1e12));
 const all=active(),nSt=all.filter(t=>t.status==='stalled').length,nRun=all.length-nSt;
 const ends=all.map(fin).filter(Boolean),last=ends.length?Math.max(...ends):null,next=ends.length?Math.min(...ends):null;
 const noEta=all.filter(t=>t.status==='running'&&!t.eta).length;
 const nested=all.length-roots.length;
 let finding;
 if(!all.length)finding='Nothing running.';
 else{
  const parts=[];
  if(nSt)parts.push(`<b class="neg">${plural(nSt,'task')} stalled</b>, the longest silent for ${stalled.length?silent(stalled[0]):'over 10 min'}`);
  if(nRun)parts.push(`${plural(nRun,'task')} running`+(last?(noEta?`; the ${ends.length} with an estimate finish by <b>${wbClock(last)}</b>`:`, all finished by about <b>${wbClock(last)}</b>`):', none with a finish estimate yet'));
  else parts.push('nothing else running');
  finding=parts.join('; ')+'.';
 }
 const h=page({title:'Workbench',crumbs:[['Workbench','#workbench']],finding});
 const strip=kpis([
  ['Stalled',`<span class="${nSt?'neg':''}">${nSt}</span>`,nSt?'silent for over 10 min':'all reporting'],
  ['Running',String(nRun),nested?`${roots.length-stalled.length} top-level, ${nested} nested`:plural(running.length,'top-level task')],
  ['Next to finish',next?wbSpan(next-now()):DASH,next?'at '+wbClock(next):'no estimate yet'],
  ['All finished by',last?wbClock(last):DASH,last?`${ends.length} of ${nRun} with an estimate`:'no estimate yet']]);
 const how='Start one with <code>arx task start --title …</code> or <code>arx.task(...)</code> in Python.';
 if(!all.length)return h+strip+`<section class="section">${panel('Running',empty('Nothing running',how))}</section>`;
 const grp=(title,list,cls)=>list.length?`<section class="section wb-grp ${cls}"><div class="wb-gh"><h2>${title}</h2><span class="sub">${list.length}</span></div><div class="wb-list">${list.map(taskCard).join('')}</div></section>`:'';
 return h+strip+grp('Stalled',stalled,'stalled')+grp('Running',running,'')+
  (!running.length?`<section class="section wb-grp"><div class="wb-gh"><h2>Running</h2><span class="sub">0</span></div>${panel('',empty('Nothing else running',how))}</section>`:'');
};
