'use strict';
/* slices: what frozen eval sets exist, how big, which hill uses them, which have runs, and where their IDs live */
const slN=n=>n==null?'—':Number(n).toLocaleString();
const slOrder={full:0,random:1,control:2,dev:3,synthetic:4};
const slKindName={full:'Full',random:'Random',control:'Control',dev:'Development',synthetic:'Synthetic'};
// the hills that use a slice: as target or control, or named on the slice itself
function slHills(s){
 const st=S.state;
 return Object.entries(st.hills).filter(([k,h])=>h.target===s.name||h.control===s.name||s.hill===k)
  .map(([k,h])=>[k,h,h.target===s.name?'target':h.control===s.name?'control':'']);
}
const slRuns=s=>Object.keys(S.state.leaderboard[s.name]||{}).length;
// a slice scores 0/1 per example unless it says `scale: continuous`: then its figure is a mean in its unit, never a %
const slBin=s=>s?.scale!=='continuous';
const slVal=(v,s,n)=>v==null?'—':esc(sv(s.name,v,n));
// the champion on this slice: its run (from the baseline plan), or whether the slice still needs one
function slChamp(s){
 const st=S.state,b=st.baseline;if(!b)return DASH;
 // the pooled score the gate pairs against (leaderboard: every compatible run, per example); the baseline plan only
 // knows the latest run's own score, which is not the pooled number when runs repeat
 const lb=st.leaderboard?.[s.name]?.[st.champion],h0=b.have?.[s.name],h=lb?{task:lb.task,score:lb.score,n:lb.n,runs:lb.runs}:h0;
 if(h)return `<a class="sl-cs" href="#task/${enc(h.task)}" title="${h.runs>1?h.runs+' runs pooled · ':''}n ${slN(h.n)}">${slVal(h.score,s,h.n)}</a>${h.runs>1?`<small class="sl-pr">pooled, ${h.runs} runs</small>`:''}`;
 if(!(b.need||[]).includes(s.name))return DASH;
 return active().some(t=>t.kind==='eval'&&t.model===st.champion&&t.slice===s.name)?pill('Running','running'):pill('Not run','warn');
}
function slSet(k,v){S[k]=v;render()}
function slSortBy(k){const s=S.slSort||{k:'kind',d:1};S.slSort={k,d:s.k===k?-s.d:(k==='kind'||k==='name'?1:-1)};render()}
function slQuery(el){S.slQ=el.value;S.slCaret=el.selectionStart;S.slFocus=true;render()}
// the focused slice's runs, best first: model, score in the slice's units, when, and the eval it came from
function slRunRows(s,span){
 const st=S.state,lb=st.leaderboard[s.name]||{},rs=Object.entries(lb).sort((a,b)=>better(a[1].score,b[1].score)?-1:better(b[1].score,a[1].score)?1:0);
 const body=rs.length?`<ul class="sl-runl">${rs.map(([m,r])=>`<li><a class="sl-rm" href="#model/${enc(m)}" title="${esc(m)}">${mn(m)}${m===st.champion?' '+pill('champion','champion'):''}</a><span class="sl-rs">${r.task?`<a href="#task/${enc(r.task)}">${slVal(r.score,s,r.n)}</a>`:slVal(r.score,s,r.n)}</span><span class="faint sl-rt">${r.ended?stamp(r.ended):''}</span></li>`).join('')}</ul>`:'<span class="faint">No runs on this slice yet.</span>';
 return `<tr class="sl-on sl-runs-row"><td colspan="${span}">${body}<div class="sl-runf"><button class="btn" onclick="slArchive(${esc(JSON.stringify(s.name))})">Every eval on this slice in the archive</button>${rs.length?`<button class="btn" onclick="slBoard(${esc(JSON.stringify(s.name))})">Open on the leaderboard</button>`:''}</div></td></tr>`;
}
// the archive, searched for this slice
function slArchive(name){if(typeof ARC!=='undefined')ARC.q=name;S.archiveKind='eval';location.hash='archive'}
// open this slice on the overview leaderboard
function slBoard(name){const s=S.state.slices[name];S.lbDataset=s.dataset;S.lbSlice=name;S.ovLbAll=false;S.ovJump=true;location.hash='overview'}

// deep link: #slices/<slice name> highlights that row and scrolls to it once per arrival
addEventListener('hashchange',()=>{S.slJumped=null});
VIEWS.slices=(arg)=>{
 const st=S.state,focus=arg&&st.slices[arg]?arg:null;
 if(focus&&S.slJumped!==focus){S.slQ='';S.slKind='all';S.slUse='all';S.slOpen=S.slOpen||{};S.slOpen[st.slices[focus].dataset||focus.split('/')[0]]=true}
 const all=Object.values(st.slices),prim=st.config.primary_dataset;
 // every dataset a slice names, registered or not: a project that froze slices without `arx dataset add` still lists them
 const ds=[...new Set([...Object.keys(st.datasets),...all.map(s=>s.dataset||String(s.name).split('/')[0])])].sort((a,b)=>(b===prim)-(a===prim));
 const dsOf=s=>s.dataset||String(s.name).split('/')[0];
 const used=all.filter(s=>slHills(s).length),pinned=all.filter(s=>s.url),runs=all.filter(s=>slRuns(s));
 const nh=Object.keys(st.hills).length;
 const finding=all.length?`${plural(all.length,'frozen slice')} across ${plural(ds.length,'dataset')}. ${used.length} are a hill's target or control and ${runs.length} have runs. ${pinned.length===all.length?'Every slice is pinned on Hugging Face.':pinned.length?`${pinned.length} are pinned on Hugging Face; the rest are held by ID hash only.`:'None is pinned on Hugging Face yet; each is held by its ID hash.'}`
  :'No slices frozen yet. Register a dataset; it freezes its full and random slices for you.';
 let h=page({title:'Slices',crumbs:focus?[['Slices','#slices'],[short(focus),'#slices/'+enc(focus)]]:[['Slices','#slices']],finding});
 if(!all.length)return h+panel('Datasets',empty('No datasets',`<p>Register the full eval set by its IDs.</p>${cmd('arx dataset add <name> --ids-file ids.txt')}`));

 const kc=Object.entries(all.reduce((a,s)=>(a[s.kind]=(a[s.kind]||0)+1,a),{})).sort((a,b)=>b[1]-a[1]);
 const kSub=kc.slice(0,2).map(([k,n])=>`${n} ${esc(k)}`).join(' · ')+(kc.length>2?` · ${kc.slice(2).reduce((a,x)=>a+x[1],0)} other`:'');
 h+=`<div class="sl-kpis">${kpis([
  ['Slices',slN(all.length),kSub],
  ['Examples',slN(ds.reduce((a,d)=>a+(st.datasets[d]?.size??Math.max(0,...all.filter(s=>dsOf(s)===d).map(s=>s.n||0))),0)),`in ${plural(ds.length,'dataset')}`],
  ['Used by a hill',slN(used.length),`by ${plural(nh,'hill')}`,'#hills'],
  ['With runs',slN(runs.length),`of ${slN(all.length)} slices`],
 ])}</div>`;

 // toolbar: search, kind, use
 const q=(S.slQ||'').trim().toLowerCase(),kind=S.slKind||'all',use=S.slUse||'all';
 const match=s=>(kind==='all'||s.kind===kind)&&(use==='all'||(use==='runs'?slRuns(s):slHills(s).length))&&
  (!q||[s.name,s.description,s.metric,s.hash,...slHills(s).map(x=>x[1].title||x[0])].some(v=>String(v||'').toLowerCase().includes(q)));
 const hits=all.filter(match),filtering=q||kind!=='all'||use!=='all';
 const kinds=['all',...kc.map(x=>x[0]).sort((a,b)=>(slOrder[a]??9)-(slOrder[b]??9))];
 h+=`<div class="sl-bar"><label class="sl-q">${ICON.search||'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>'}<input id="sl-q" type="search" placeholder="Search slices, hashes, hills" aria-label="Search slices" value="${esc(S.slQ||'')}" oninput="slQuery(this)" onfocus="S.slFocus=true" onblur="S.slFocus=false"></label>
  <div class="seg" role="group" aria-label="Kind">${kinds.map(k=>`<button class="${kind===k?'on':''}" aria-pressed="${kind===k}" onclick="slSet('slKind','${k}')">${k==='all'?'All':esc(slKindName[k]||k)}<small>${k==='all'?all.length:kc.find(x=>x[0]===k)[1]}</small></button>`).join('')}</div>
  <div class="seg" role="group" aria-label="Use">${[['all','Any'],['runs','With runs'],['hill','On a hill']].map(([k,l])=>`<button class="${use===k?'on':''}" aria-pressed="${use===k}" onclick="slSet('slUse','${k}')">${l}</button>`).join('')}</div>
  ${filtering?`<span class="sl-cnt">${slN(hits.length)} of ${slN(all.length)}</span><button class="btn sl-clr" onclick="S.slQ='';S.slKind='all';S.slUse='all';render()">Clear</button>`:''}</div>`;

 const so=S.slSort||{k:'kind',d:1};
 const cmp={kind:(a,b)=>((slOrder[a.kind]??9)-(slOrder[b.kind]??9))||(b.n-a.n)||a.name.localeCompare(b.name),name:(a,b)=>a.name.localeCompare(b.name),n:(a,b)=>a.n-b.n,runs:(a,b)=>slRuns(a)-slRuns(b)}[so.k];
 const sh=(label,k,cls)=>[`<button class="sl-sort ${so.k===k?'on':''}" onclick="slSortBy('${k}')">${label}${so.k===k&&k!=='kind'?`<span class="sl-arr">${so.d<0?'↓':'↑'}</span>`:''}</button>`,cls];
 const CAP=8;S.slOpen=S.slOpen||{};
 const panels=ds.map(d=>{
  const x=st.datasets[d]||{},mine=all.filter(s=>dsOf(s)===d),sl=mine.filter(match).sort((a,b)=>so.d*cmp(a,b)||a.name.localeCompare(b.name));
  if(filtering&&!sl.length)return '';
  const anyPin=mine.some(s=>s.url),capped=sl.length>CAP+2&&!filtering,open=!capped||S.slOpen[d],shown=open?sl:sl.slice(0,CAP);
  const rows=shown.map(s=>{
   const hs=slHills(s),nr=slRuns(s),about=[slBin(s)?'':'Continuous score'+(s.unit?' in '+s.unit:''),s.description||s.metric||''].filter(Boolean).join(' · ');
   const hill=hs.length?hs.map(([k,hh,role])=>`<a class="sl-hill" href="#hill/${enc(k)}" title="${esc(hh.title||k)}${role?' · '+role:''}"><span class="st ${esc(hh.status||'')}"></span><span class="ell">${esc(hh.title||k)}</span>${role?`<span class="faint"> · ${role}</span>`:''}</a>`).join(''):DASH;
   return `<tr id="slice-${esc(s.name)}" class="${s.name===focus?'sl-on':''}"><td class="sl-id"><div class="two"><span class="row"><a class="ell mono sl-nm" href="#slices/${enc(s.name)}" title="${esc(s.name)}">${esc(short(s.name))}</a><span class="sl-show-s">${pill(s.kind||'—',s.kind==='full'?'acc':'')}</span></span>${about?`<span class="sub ell" title="${esc(about)}">${esc(about)}</span>`:''}</div></td>
    <td class="sl-hide-s sl-kind">${pill(s.kind||'—',s.kind==='full'?'acc':'')}</td><td class="num">${slN(s.n)}</td><td class="num sl-ch">${slChamp(s)}</td>
    <td class="sl-hide-s sl-hash"><span class="sl-hw"><span class="id">${esc(s.hash||'')}</span>${s.hash?copyBtn(s.hash):''}</span></td>
    <td class="sl-hl sl-hide-m">${hill}</td>
    <td class="num sl-runs sl-hide-s">${nr?`<a class="sl-go" href="#slices/${enc(s.name)}" title="Show the runs on this slice">${plural(nr,'model')}</a>`:'<span class="faint">None</span>'}</td>
    ${anyPin?`<td class="num sl-hide-s">${s.url?`<a class="ln" href="${esc(s.url)}" target="_blank" rel="noopener">Hugging Face ${ICON.ext}</a>`:'<span class="faint">ID hash</span>'}</td>`:''}</tr>`+(s.name===focus?slRunRows(s,anyPin?8:7):'')});
  const head=[sh('Slice','name',''),['Kind','sl-hide-s sl-kind'],sh('n','n','num sl-n'),[st.champion?`<span title="${mnt(st.champion)} · ${esc(st.champion)}">Champion</span>`:'Champion','num sl-ch'],['ID hash','sl-hide-s sl-hash'],['Hill','sl-hide-m sl-hl'],sh('Runs','runs','num sl-runs sl-hide-s'),...(anyPin?[['Stored','num sl-hide-s']]:[])];
  const more=capped?`<button class="btn sl-more" onclick="S.slOpen[${esc(JSON.stringify(d))}]=${open?'false':'true'};render()">${open?'Show fewer':`Show all ${sl.length} slices`}</button>`:'';
  const title=x.title&&x.title!==d?esc(x.title):'';
  return panel(`<span class="mono">${esc(d)}</span>`,sl.length?table(head,rows)+more:empty('No slices in this dataset',`<p>Freeze one from a list of IDs.</p>${cmd(`arx slice add ${d}/<name> --ids-file ids.txt`)}`),
   {cls:'section',meta:`${title?title+' · ':''}${x.size!=null?slN(x.size)+' examples · ':''}${filtering?`${sl.length} of ${plural(mine.length,'slice')}`:plural(mine.length,'slice')}${anyPin?'':' · held by ID hash'}`,right:x.url?`<a class="ln" href="${esc(x.url)}" target="_blank" rel="noopener">Dataset ${ICON.ext}</a>`:''});
 }).join('');
 h+=panels||panel('',empty('No slices match',`Nothing matches${q?` “${esc(S.slQ)}”`:''} with these filters.`));
 if(focus&&S.slJumped!==focus){S.slJumped=focus;setTimeout(()=>document.getElementById('slice-'+focus)?.scrollIntoView({block:'center'}),0)}
 if(S.slFocus)setTimeout(()=>{const i=document.getElementById('sl-q');if(i&&document.activeElement!==i){i.focus();const c=S.slCaret??i.value.length;try{i.setSelectionRange(c,c)}catch(e){}}},0);
 return h;
};
