'use strict';
// papers: the write-ups people comment on. Goal papers are the public result of a goal; internal notes explain a
// hill, a baseline or a component. The list answers "is anyone waiting on the agent, and where"; a row opens the
// reader (papers/<name>, relative so /p/<key>/ serves another project's papers).

// one block keeps these helpers out of the shared global scope the other view files load into
{
const G_LABEL={open:'Goal open',achieved:'Achieved',abandoned:'Abandoned'};
const G_ST={open:'open',achieved:'done',abandoned:'failed'};
// a paper reads by its title, else its hill's title, else its name
const pTitle=p=>p.title||S.state.hills?.[p.hill]?.title||p.name;
const pGo=p=>`location.href=${esc(JSON.stringify(paperUrl(p)))}`;
function pLinks(p){
 const L=S.state,g=p.goal&&(L.goals||{})[p.goal],h=p.hill&&L.hills?.[p.hill],out=[];
 if(p.goal)out.push(g?((g.title||p.goal)===pTitle(p)?`<a class="ln" href="#goal/${enc(p.goal)}" onclick="event.stopPropagation()">${st(G_ST[g.status]||g.status,G_LABEL[g.status]||g.status)}</a>`:`${st(G_ST[g.status]||g.status,G_LABEL[g.status]||g.status)}<a class="ln ell" href="#goal/${enc(p.goal)}" onclick="event.stopPropagation()">${esc(g.title||p.goal)}</a>`):`<span class="ell">Goal ${esc(p.goal)}</span>`);
 // a hill's own note is titled after the hill: then the line says only that the hill is open or climbed
 if(p.hill)out.push(h?(h.title===pTitle(p)?`<a class="ln" href="#hill/${enc(p.hill)}" onclick="event.stopPropagation()">${st(h.status,'Hill '+h.status)}</a>`:`<span class="pp-k">Hill</span><a class="ln ell" href="#hill/${enc(p.hill)}" onclick="event.stopPropagation()">${esc(h.title||p.hill)}</a>`):`<span class="pp-k">Hill</span><span class="ell">${esc(p.hill)}</span>`);
 return out.length?out.map(x=>`<span class="pp-ln">${x}</span>`).join(''):`<span class="id">${esc(p.name)}</span>`;
}
// is the paper still true: lint errors now (goal papers are also checked against the ledger) and what moved since
function pHealth(p){
 const h=p.health||{},out=[];
 if(h.stale?.length)out.push(`<span class="pill warn" title="${esc(h.stale.map(x=>x[0].toUpperCase()+x.slice(1)).join('. '))}">Out of date</span>`);
 if(h.errors)out.push(`<span class="pill neg" title="${esc(h.first||'')}">${esc(plural(h.errors,'check error'))}</span>`);
 return out.length?`<span class="pp-ln pp-h">${out.join('')}</span>`:'';
}
function pRow(p){
 const res=(p.comments||0)-(p.open||0);
 const com=p.comments?`<span class="fig"><b>${p.open}</b> open</span><span class="sub">${res} resolved</span>`:'<span class="faint">No comments</span>';
 return `<tr class="click${p.waiting?' wait':''}" onclick="${pGo(p)}">
  <td class="pp-t"><div class="two"><a href="${esc(paperUrl(p))}" onclick="event.stopPropagation()"><b>${esc(pTitle(p))}</b></a><span class="pp-lns">${pLinks(p)}${pHealth(p)}</span></div></td>
  <td class="num pp-c"><div class="two">${com}</div></td>
  <td class="num pp-w${p.waiting||p.owed?'':' none'}">${p.waiting?pill(plural(p.waiting,'waiting','waiting'),'acc'):''}${p.owed?pill(plural(p.owed,'edit owed','edits owed'),'warn'):''}${p.waiting||p.owed?'':DASH}</td>
  <td class="num pp-u"><span title="${esc(stamp(p.updated))}">${p.updated?ago(p.updated):DASH}</span></td></tr>`;
}
function pGroup(title,ps){
 const w=ps.reduce((a,p)=>a+(p.waiting||0),0);
 return `<section class="pgroup"><div class="pgh"><h2>${title}</h2><span class="meta">${ps.length}${w?` · ${w} waiting`:''}</span></div>
  ${panel('',table([['Paper'],['Comments','num'],['Agent','num'],['Updated','num']],ps.map(pRow)),{flush:true,cls:'ptbl'})}</section>`;
}
// one public paper per goal and one living paper per open or climbed hill: list the ones still missing, with the command
function pMissing(ps){
 const L=S.state,has=new Set(ps.flatMap(p=>[p.name,p.goal,p.hill].filter(Boolean)));
 const gs=Object.entries(L.goals||{}).filter(([k])=>!has.has(k)),hs=Object.entries(L.hills||{}).filter(([k,h])=>!has.has(k)&&(h.status==='open'||h.status==='climbed'));
 if(!gs.length&&!hs.length)return '';
 const row=(kind,k,o,c)=>`<div class="pm-r"><a class="ln ell" href="#${kind}/${enc(k)}"><b>${esc(o.title||k)}</b></a>${kind==='goal'?st(G_ST[o.status]||o.status,G_LABEL[o.status]||o.status):st(o.status,'Hill '+o.status)}${cmd(c)}</div>`;
 return `<section class="pgroup"><div class="pgh"><h2>No paper yet</h2><span class="meta">${gs.length+hs.length}</span></div>
  ${panel('',`<div class="pm">${gs.map(([k,g])=>row('goal',k,g,`arx paper new --goal ${k}`)).join('')}${hs.map(([k,h])=>row('hill',k,h,`arx paper new ${k}`)).join('')}</div>`)}</section>`;
}
VIEWS.papers=()=>{
 const ps=Object.values(S.state.papers||{}).sort((a,b)=>(b.waiting||0)-(a.waiting||0)||(b.owed||0)-(a.owed||0)||(b.updated||0)-(a.updated||0));
 if(!ps.length)return page({title:'Papers',crumbs:[['Papers']]})+panel('',empty('No papers yet','Start one from the worked example, then publish it; people comment here and the agent replies.')+
  `<div class="pp-cmds">${cmd('arx paper new <hill>')}${cmd('arx paper add <hill> --hill <hill> --file paper-<hill>.html')}${cmd('arx paper new --goal <goal>')}</div>`);
 const waiting=ps.reduce((a,p)=>a+(p.waiting||0),0),open=ps.reduce((a,p)=>a+(p.open||0),0),wp=ps.filter(p=>p.waiting);
 const finding=waiting?`<b>${plural(waiting,'comment')} ${waiting===1?'is':'are'} waiting for the agent</b> ${wp.length===1?`on <a class="ln" href="${esc(paperUrl(wp[0]))}">${esc(pTitle(wp[0]))}</a>`:`across ${wp.length} papers`}.`+
  `${open>waiting?` ${plural(open,'thread')} open in all.`:''}`
  :ps.some(p=>p.owed)?`<b>${plural(ps.reduce((a,p)=>a+(p.owed||0),0),'promised edit')} not yet published</b> on ${esc(pTitle(ps.find(p=>p.owed)))}.`
  :ps.some(p=>p.health?.stale?.length||p.health?.errors)?`<b>${plural(ps.filter(p=>p.health?.stale?.length||p.health?.errors).length,'paper')} out of date or failing the check.</b>`
  :open?`Nothing waiting for the agent; ${plural(open,'thread')} still open.`:`${plural(ps.length,'paper')}; every comment answered and resolved.`;
 const acts=waiting?cmd('arx paper poll'):'';
 const pub=ps.filter(p=>p.goal),int=ps.filter(p=>!p.goal);
 return page({title:'Papers',crumbs:[['Papers']],finding,acts})+
  (pub.length?pGroup('Goal papers',pub):'')+
  (int.length?pGroup('Internal notes',int):'')+pMissing(ps);
};
}
