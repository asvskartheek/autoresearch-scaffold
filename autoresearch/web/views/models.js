// models: champion first, then candidates by how far up the ladder they are, then rejected with their reasons,
// then planned / historical / retired. A search box and a status filter narrow every group in place (no re-render,
// so typing keeps focus); lineage (parent -> child) closes the page. Everything sits in one block: no globals leak
// except the two handlers the inline events call (msSearch, msFilter).
{
const rungsOf=g=>{if(!g||g.error||!g.rungs)return null;const rs=g.rungs.filter(r=>r.status!=='skipped');return {done:rs.filter(r=>r.status==='pass').length,of:rs.length,fail:rs.find(r=>r.status==='fail'),pending:rs.find(r=>r.status==='pending')}};
const nextCell=(name,g)=>{
 if(!g||g.error)return g?.error?`<span class="neg">${esc(g.error)}</span>`:DASH;
 if(g.promotable)return cmd(`arx promote ${name}`);
 const r=rungsOf(g);
 if(r?.fail){const c=r.fail.checks.find(c=>c.state==='fail');return `<span class="neg">Fails ${esc(r.fail.rung)}</span>${c?`<span class="sub"> · ${esc(short(c.slice))} ${pts(c.delta)} pts</span>`:''}`}
 const n=g.next?.[0];if(!n)return DASH;
 return `<span class="sub">${n.model!==name?'Champion needs':'Needs'} a run on</span> <a class="ln ms-sl" href="#slices/${enc(n.slice)}">${esc(short(n.slice))}</a>${g.next.length>1?`<span class="faint"> +${g.next.length-1} more</span>`:''}`;
};
// a figure on the primary dataset's full set, and its difference to the champion on the same slice and n
function full(k){
 const L=S.state,f=fullScore(k),c=L.champion&&k!==L.champion?fullScore(L.champion):null;
 const v=f?(f.task?`<a href="#task/${enc(f.task)}">${pct(f.score)}</a>`:pct(f.score)):DASH;
 return {v,d:f&&c?`<span class="${f.score===c.score?'sub':better(f.score,c.score)?'pos':'neg'}">${pts(f.score-c.score)}</span>`:DASH};
}
const nameCell=(k,m,sub=true)=>`<div class="two"><span class="ms-id"><a class="ms-nm mono" href="#model/${enc(k)}">${esc(k)}</a>${copyBtn(k)}</span>${sub&&(m.title||m.change)?`<span class="sub ms-ch">${esc(m.title||firstLine(m.change))}</span>`:''}</div>`;
const parentCell=(k,p)=>p&&p!==k?`<a class="mono ms-par" href="#model/${enc(p)}">${esc(p)}</a>`:DASH;
const hillCell=h=>{const x=S.state.hills[h];return h?`<a class="ms-hill" href="#hill/${enc(h)}">${esc(x?.title||h)}</a>`:DASH};
const hay=(k,m)=>esc([k,m.title,m.change,m.reason,m.parent,m.hill,S.state.hills[m.hill]?.title,m.status].filter(Boolean).join(' ').toLowerCase());
const row=(k,m,cells)=>`<tr class="click" data-q="${hay(k,m)}" onclick="if(!event.target.closest('a,button'))location.hash='model/${enc(k)}'">${cells.join('')}</tr>`;

function lineage(models,gates){
 const keep=new Set(),want=Object.keys(models).filter(k=>['champion','candidate','rejected'].includes(models[k].status));
 for(let k of want){const seen=new Set();while(k&&models[k]&&!seen.has(k)){seen.add(k);keep.add(k);k=models[k].parent}}
 const par=k=>{const p=models[k].parent;return p&&p!==k&&keep.has(p)?p:null};
 const kidsOf=p=>[...keep].filter(k=>par(k)===p).sort((a,b)=>models[a].created-models[b].created);
 const out=[],seen=new Set(),walk=(k,d)=>{if(seen.has(k))return;seen.add(k);out.push([k,d]);kidsOf(k).forEach(c=>walk(c,d+1))};
 kidsOf(null).forEach(r=>walk(r,0));[...keep].filter(k=>!seen.has(k)).forEach(k=>walk(k,0));
 return out.map(([k,d])=>{const m=models[k],g=gates[k],r=rungsOf(g),climbing=m.status==='candidate'&&g&&!g.error;
  return `<a class="kid ms-lin" data-q="${hay(k,m)}" href="#model/${enc(k)}" style="--d:${Math.min(d,6)}">${d?'<span class="ms-elbow"></span>':''}<span class="sd ms-${esc(m.status)}"></span><span class="nm mono">${esc(k)}</span><span class="vl">${climbing?ladder(g,{compact:true})+(r?` <span class="ms-of">${r.done} of ${r.of}</span>`:''):esc(m.status)}</span></a>`}).join('');
}

// filter in place: hide rows whose text misses the query, hide groups the status filter excludes
function apply(){
 const q=(S.msQ||'').trim().toLowerCase(),f=S.msF||'all';
 let shown=0;
 document.querySelectorAll('#ms-root [data-grp]').forEach(p=>{
  let n=0;p.querySelectorAll('[data-q]').forEach(r=>{const hit=!q||r.dataset.q.includes(q);r.hidden=!hit;n+=hit});
  const lin=p.dataset.grp==='lineage';
  p.hidden=lin?(f!=='all'||(q&&!n)):((f!=='all'&&p.dataset.grp!==f)||(q&&!n));
  if(!lin&&!p.hidden)shown++;
 });
 document.querySelectorAll('#ms-root .seg button').forEach(b=>{const on=b.dataset.f===f;b.classList.toggle('on',on);b.setAttribute('aria-pressed',on)});
 const e=document.getElementById('ms-nomatch');if(e)e.hidden=shown>0;
}
window.msFilter=f=>{S.msF=f;apply()};
window.msSearch=el=>{S.msQ=el.value;apply()};

VIEWS.models=()=>{
 const L=S.state,models=L.models,gates=L.gates,champ=L.champion;
 const all=Object.entries(models),by=s=>all.filter(([,m])=>m.status===s);
 const prog=k=>{const r=rungsOf(gates[k]);return r?(gates[k].promotable?99:r.fail?-1:r.done):-2};
 const cands=by('candidate').sort((a,b)=>prog(b[0])-prog(a[0])||b[1].created-a[1].created);
 const rej=by('rejected').sort((a,b)=>b[1].created-a[1].created);
 const other=all.filter(([,m])=>!['champion','candidate','rejected'].includes(m.status)).sort((a,b)=>b[1].created-a[1].created);
 const fullKey=L.config.primary_dataset+'/full',fullN=L.slices[fullKey]?.n,cf=champ?fullScore(champ):null;
 const promotable=cands.filter(([k])=>gates[k]?.promotable),failing=cands.filter(([k])=>rungsOf(gates[k])?.fail);
 const lead=cands[0],lr=lead&&rungsOf(gates[lead[0]]);
 const mlink=k=>`<a class="mono" href="#model/${enc(k)}"><b>${esc(k)}</b></a>`;

 // finding: who holds the title, who is closest to taking it, what it needs next
 let finding;
 if(!champ)finding=`No champion yet. Register a baseline with <code>arx model add &lt;name&gt; --champion</code>; candidates climb against it.`;
 else{
  finding=`${mlink(champ)} is champion${cf?` at <b>${pct(cf.score)}</b> on ${esc(short(fullKey))} (n ${cf.n.toLocaleString()})`:''}. `;
  if(promotable.length)finding+=`${mlink(promotable[0][0])} has passed every rung and is ready to promote.`;
  else if(lr?.done)finding+=`Closest challenger: ${mlink(lead[0])}, ${lr.done} of ${lr.of} rungs passed${lr.pending?`; ${esc(lr.pending.rung)} is next`:''}.`;
  else if(cands.length)finding+=`${plural(cands.length,'candidate')} registered; none has passed a rung yet.`;
  else finding+=`No candidates are climbing.`;
 }
 const acts=promotable.length?cmd('arx promote '+promotable[0][0]):lead?`<a class="btn" href="#model/${enc(lead[0])}">Open ${esc(lead[0])}</a>`:'';
 const h=[page({title:'Models',crumbs:[['Models','#models']],finding,acts})];
 h.push(kpis([
  ['Champion',champ?`<span class="mono ms-kc">${esc(champ)}</span>`:DASH,cf?`${pct(cf.score)} on ${esc(short(fullKey))}, n ${cf.n.toLocaleString()}`:'',champ?`#model/${enc(champ)}`:null],
  ['Climbing',String(cands.length),cands.length?`${promotable.length} ready to promote · ${failing.length} failing a rung`:'none registered'],
  ['Rejected',String(rej.length),rej.length?'kept with their reasons':'none'],
  ['Planned or archived',String(other.length),other.length?[...new Set(other.map(([,m])=>m.status))].join(' · '):'none'],
 ]));

 const seg=[['all','All',all.length],['ladder','On the ladder',cands.length+(champ?1:0)],['rejected','Rejected',rej.length],['other','Planned or archived',other.length]];
 h.push(`<div id="ms-root"><div class="ms-bar"><input id="ms-q" class="ms-q" type="search" placeholder="Search models, hills, reasons" aria-label="Search models" autocomplete="off" value="${esc(S.msQ||'')}" oninput="msSearch(this)" onfocus="S.msFocus=1" onblur="S.msFocus=0"><div class="seg" role="group" aria-label="Status">${seg.map(([f,l,n])=>`<button type="button" data-f="${f}" onclick="msFilter('${f}')">${l}<small>${n}</small></button>`).join('')}</div></div>`);

 const lh=new Set([champ,...cands.map(([k])=>k)].filter(k=>models[k]?.hill).map(k=>models[k].hill)),oneHill=lh.size===1?[...lh][0]:null;
 const fullHead=[`Full set${fullN!=null?` <span class="faint">n ${fullN.toLocaleString()}</span>`:''}`,'num'];
 const champRow=champ&&models[champ]?[row(champ,models[champ],[`<td>${nameCell(champ,models[champ])}</td>`,`<td>${st('champion','Champion')}</td>`,...(oneHill!=null?[]:[`<td>${hillCell(models[champ].hill)}</td>`]),`<td>${ladder(gates[champ],{compact:true})||DASH}</td>`,`<td class="sub">${models[champ].promoted?'Since '+stamp(models[champ].promoted):'Baseline'}</td>`,`<td class="num">${full(champ).v}</td>`,`<td class="num">${DASH}</td>`])]:[];
 const candRows=cands.map(([k,m])=>{const f=full(k),r=rungsOf(gates[k]);
  return row(k,m,[`<td>${nameCell(k,m)}</td>`,`<td>${gates[k]?.promotable?st('pass','Ready'):r?.fail?st('fail','Failing'):st('running','Climbing')}${r?`<div class="sub">${r.done} of ${r.of} rungs</div>`:''}</td>`,...(oneHill!=null?[]:[`<td>${hillCell(m.hill)}</td>`]),`<td>${ladder(gates[k],{compact:true})||DASH}</td>`,`<td class="ms-next">${nextCell(k,gates[k])}</td>`,`<td class="num">${f.v}</td>`,`<td class="num">${f.d}</td>`])});
 h.push(panel('On the ladder',(champRow.length||candRows.length)?table(['Model','Status',...(oneHill!=null?[]:['Hill']),'Gate','Next step',fullHead,['Δ vs champion','num']],[...champRow,...candRows]):empty('No models yet','Register one with <code>arx model add &lt;name&gt;</code>'),{meta:(champ?`paired against ${mlink(champ)}`:'')+(oneHill?` · every candidate climbs ${hillCell(oneHill)}`:''),cls:'section ms-ladder" data-grp="ladder'}));

 h.push(panel('Rejected',rej.length?table(['Model','Why it was rejected','Parent',fullHead,['Δ pts vs champion','num']],rej.map(([k,m])=>{const f=full(k);
  return row(k,m,[`<td>${nameCell(k,m,false)}</td>`,`<td class="ms-why">${m.reason?esc(m.reason):'<span class="dash">No reason recorded</span>'}</td>`,`<td>${parentCell(k,m.parent)}</td>`,`<td class="num">${f.v}</td>`,`<td class="num">${f.d}</td>`])})):empty('Nothing rejected','<code>arx reject &lt;name&gt; --reason "…"</code> keeps a failed candidate in the ledger'),{meta:rej.length?plural(rej.length,'model'):'',cls:'section" data-grp="rejected'}));

 h.push(panel('Planned or archived',other.length?table(['Model','Status','Parent','Note'],other.map(([k,m])=>row(k,m,[`<td>${nameCell(k,m,false)}</td>`,`<td>${st(m.status)}</td>`,`<td>${parentCell(k,m.parent)}</td>`,`<td class="ms-why sub">${esc(m.reason||m.title||'')||DASH}</td>`]))):empty('None','<code>arx model add &lt;name&gt; --status planned</code> records an idea before it runs'),{meta:other.length?plural(other.length,'model'):'',cls:'section" data-grp="other'}));

 h.push(`<section class="card section ms-nomatch" id="ms-nomatch" hidden>${empty('No models match','Clear the search or choose another status')}</section>`);
 const lin=lineage(models,gates);
 h.push(panel('Lineage',lin||empty('No lineage yet','Pass <code>--parent</code> to <code>arx model add</code>'),{meta:'parent → child',cls:'section ms-tree" data-grp="lineage'}));
 h.push('</div>');
 // after the sheet is drawn: re-apply the filter and give the search box its focus back
 queueMicrotask(()=>{apply();const i=document.getElementById('ms-q');if(i&&S.msFocus){i.focus();const n=i.value.length;i.setSelectionRange(n,n)}});
 return h.join('');
};
}
