// hills: the failure modes error analysis found. The list answers "which are open, how big, is anyone climbing";
// a hill's page reads as an explainer: the symptom, one example, how common it is, who fixed it, what was expected,
// and what to run next.

// one block keeps these helpers out of the shared global scope the other view files load into
{
// ---------- figures. A slice scores pass/fail (0..1, read as solved / n), seconds (score = minus seconds), or a mean.
const hNum=v=>{const t=Math.abs(v)>=10?Math.abs(v).toFixed(1):num(Math.abs(v),3);return (v<0?'−':'')+t};
const isRate=r=>r&&r.score>=0&&r.score<=1;
// a hill is timed when its measure (or its slice's metric) says the score is seconds
const timed=x=>/\bseconds?\b/i.test(x.measure||S.state.slices[x.target]?.metric||'');
const secsOf=v=>`${hNum(Math.abs(v))}&nbsp;s`;
const hVal=(v,U)=>U?secsOf(v):hNum(v);
function hFig(r,U){
 if(!r)return DASH;
 if(isRate(r))return `<b>${solved(r)}</b><span class="of">&nbsp;/&nbsp;${r.n}</span>`;
 if(U)return `<b>${hNum(Math.abs(r.score))}</b><span class="of">&nbsp;s</span>`;
 return `<b>${hNum(r.score)}</b><span class="of"> mean</span>`;
}
const hShare=x=>x.share&&x.share.of?x.share.count/x.share.of:null;
const H_ORDER={open:0,climbed:1,closed:2};
const exsOf=x=>x?x.examples||(x.example?[x.example]:[]):[];
function hillRuns(x){
 const L=S.state,T=L.leaderboard[x.target]||{},C=x.control?L.leaderboard[x.control]||{}:{},ch=L.champion;
 return Object.entries(T).map(([m,r])=>({m,r,c:C[m]})).sort((a,b)=>(b.m===ch)-(a.m===ch)||(better(a.r.score,b.r.score)?-1:better(b.r.score,a.r.score)?1:0));
}
// the best attempt: climbed_by when set and run, else the best-scoring non-champion run
function bestAttempt(x,runs){
 const ch=S.state.champion;
 return runs.find(o=>o.m===x.climbed_by&&o.m!==ch)||runs.find(o=>o.m!==ch)||null;
}
// what the hill is measured against: normally the champion against its best attempt; when the champion itself
// climbed the hill, the champion against the run where the hill was found
function hPair(x,runs){
 const ch=S.state.champion,now=runs.find(o=>o.m===ch);
 if(x.climbed_by&&x.climbed_by===ch&&now){const base=runs.find(o=>o.m===x.found_in&&o.m!==ch);if(base)return {sub:now,ref:base,refFound:true}}
 return {sub:bestAttempt(x,runs),ref:now,refFound:false};
}
// signed count / value change vs a reference, coloured good or bad; time reads as seconds faster (−) or slower (+)
function hDelta(r,base,U){
 if(!r||!base)return DASH;
 if(isRate(r)&&isRate(base)){const k=solved(r)-solved(base);return k===0?'<span class="faint">0</span>':`<span class="${better(k,0)?'pos':'neg'}">${k>0?'+':'−'}${Math.abs(k)}</span>`}
 const d=r.score-base.score;if(Math.abs(d)<1e-9)return '<span class="faint">0</span>';
 const shown=U?-d:d;
 return `<span class="${better(d,0)?'pos':'neg'}">${shown>0?'+':'−'}${hNum(Math.abs(d))}${U?'&nbsp;s':''}</span>`;
}
// per-example flips vs a reference: f fixed (reference wrong, this right), k broke
function hFlips(a,b){
 let f=0,k=0;if(!a||!b)return null;
 for(const id in a){if(!(id in b)||a[id]==null||b[id]==null)continue;const x=a[id]>=.5,y=b[id]>=.5;if(x&&!y)f++;if(!x&&y)k++}
 return {f,k};
}
const binary=D=>D&&Object.values(D.runs).every(r=>Object.values(r).every(v=>v==null||v===0||v===1));
const mLink=m=>S.state.models[m]?`<a class="ln" href="#model/${enc(m)}">${esc(m)}</a>`:esc(m);
const sLink=s=>`<a class="ln mono" href="#slices/${enc(s)}" title="${esc(s)}">${esc(short(s))}</a>`;

// ---------- list
VIEWS.hills=()=>{
 const L=S.state,ch=L.champion;
 const hs=Object.entries(L.hills).sort((a,b)=>(H_ORDER[a[1].status]??3)-(H_ORDER[b[1].status]??3)||(hShare(b[1])??-1)-(hShare(a[1])??-1)||b[1].created-a[1].created);
 const open=hs.filter(([,x])=>x.status==='open');
 const big=open.find(([,x])=>hShare(x)!=null);
 const climbing=open.filter(([,x])=>hillRuns(x).some(o=>o.m!==ch)).length;
 const finding=!hs.length?'':!open.length?`No open hills; ${plural(hs.length,'hill')} climbed or closed.`:
  `<b>${plural(open.length,'open hill')}</b>, ${climbing===open.length?(open.length===1?'with an attempt':'all with an attempt'):`${climbing} with an attempt`}.${big?` The biggest, <b>${esc(big[1].title)}</b>, explains ${pct(hShare(big[1]))} of the failures it was counted against.`:''}`;
 let h=page({title:'Hills',crumbs:[['Hills']],finding});
 if(!hs.length)return h+panel('',empty('No hills yet','Find a failure mode by error analysis, then open it.')+`<div class="hcmd">${cmd('arx hill open <name> --title "…" --target <dev slice> --control <control slice>')}</div>`);
 for(const [s,l] of [['open','Open'],['climbed','Climbed']]){
  const g=hs.filter(([,x])=>x.status===s);if(!g.length)continue;
  h+=`<section class="hgroup"><div class="hgh"><h2>${l}</h2><span class="meta">${g.length}</span></div><div class="hcards">${g.map(hCard).join('')}</div></section>`;
 }
 const rest=hs.filter(([,x])=>x.status!=='open'&&x.status!=='climbed');
 if(rest.length)h+=hClosed(rest);
 return h;
};
function hCard([k,x]){
 const L=S.state,ch=L.champion,runs=hillRuns(x),U=timed(x),sh=hShare(x);
 const now=runs.find(o=>o.m===ch),{sub,ref,refFound}=hPair(x,runs);
 const n=L.slices[x.target]?.n,att=runs.filter(o=>o.m!==ch).length;
 const bar=(r,mark,cls)=>r&&isRate(r)?meter(r.score,{mark,cls}):'';
 // two rows: the champion, then whoever it is measured against
 const second=refFound?ref:sub,secondRole=refFound?'found in':sub&&sub.m===x.climbed_by?'climbed it':'best attempt';
 const chRole=x.climbed_by===ch?'champion, climbed it':'champion';
 const row=(o,name,role,cls,mark)=>`<div class="hc-run"><span class="nm ${o?'':'faint'}" title="${esc(name||'')}">${esc(name)}${role?`<span class="rl">${role}</span>`:''}</span><span class="fig">${o?hFig(o.r,U):'<span class="faint">not run</span>'}</span>${bar(o?.r,mark,cls)}</div>`;
 return `<a class="card hcard ${esc(x.status)}" href="#hill/${enc(k)}">
  <div class="hc-top">${st(x.status)}${sh!=null?`<span class="hc-share" title="${x.share.count} of ${x.share.of} ${esc(x.share.of_what||'')}"><b>${pct(sh)}</b> of failures</span>`:''}</div>
  <h3>${esc(x.title)}</h3>
  <p class="hc-sym">${esc(x.symptom||firstLine(x.problem))||'<span class="faint">No symptom written yet</span>'}</p>
  <div class="hc-runs">
   ${row(now,ch||'No champion',ch?chRole:'',x.climbed_by===ch?'pos':'muted',null)}
   ${second?row(second,second.m,secondRole,refFound?'muted':x.climbed_by&&second.m===x.climbed_by?'pos':'',now&&isRate(now.r)&&!refFound?now.r.score:null):row(null,'No attempt yet','','',null)}
  </div>
  <div class="hc-foot"><span class="ell mono">${esc(short(x.target)||'no dev set')}</span><span>${n!=null?plural(n,'example'):''}${n!=null?' · ':''}${plural(att,'attempt')}</span></div></a>`;
}
// closed hills: a compact table; a reason they all share is said once above it
function hClosed(rest){
 const L=S.state,reasons=[...new Set(rest.map(([,x])=>x.reason||''))],one=reasons.length===1&&reasons[0];
 const sup=[...new Set(rest.flatMap(([,x])=>x.superseded_by||[]))];
 const lede=one?`<p class="hcl-why">${esc(one)}${sup.length?` Replaced by ${sup.map(s=>L.hills[s]?`<a class="ln" href="#hill/${enc(s)}">${esc(L.hills[s].title)}</a>`:esc(s)).join(', ')}.`:''}</p>`:'';
 const rows=rest.map(([k,x])=>{const sh=hShare(x),att=hillRuns(x).filter(o=>o.m!==L.champion).length;
  return `<tr class="click" onclick="location.hash='#hill/${enc(k)}'"><td><div class="two"><a href="#hill/${enc(k)}"><b>${esc(x.title)}</b></a><span class="sub ell" title="${esc(one?x.symptom||'':x.reason||x.symptom||'')}">${esc(one?x.symptom||firstLine(x.problem):x.reason||x.symptom||'')}</span></div></td>
   <td class="num fig">${sh!=null?pct(sh):DASH}</td><td class="num fig">${att}</td><td class="num hcl-d">${x.closed?stamp(x.closed):DASH}</td></tr>`});
 return `<section class="hgroup"><div class="hgh"><h2>${rest.every(([,x])=>x.status==='closed')?'Closed':'Closed and other'}</h2><span class="meta">${rest.length}</span></div>${panel('',lede+table([['Hill'],['Share','num'],['Attempts','num'],['Closed','num']],rows),{cls:'hcl'})}</section>`;
}

// ---------- detail
window.hillEx=(k,j)=>{const n=exsOf(S.state?.hills?.[k]).length;if(!n)return;S.ex={...S.ex,[k]:((j%n)+n)%n};render()};
// a click on a matrix cell picks that example; a second click on it clears the pick
window.hillCell=e=>{const c=e.target.closest('[data-id]');if(!c)return;const sl=c.closest('[data-slice]').dataset.slice,id=c.dataset.id;
 S.hsel=S.hsel&&S.hsel.slice===sl&&S.hsel.id===id?null:{slice:sl,id};render()};
window.hillCellClear=()=>{S.hsel=null;render()};
if(!window.__hillKeys){window.__hillKeys=true;addEventListener('keydown',e=>{
 if(route().r!=='hill'||e.altKey||e.metaKey||e.ctrlKey||e.shiftKey||e.defaultPrevented)return;
 if(/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)||e.target.isContentEditable)return;
 const d=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;if(!d)return;
 const k=route().arg;if(exsOf(S.state?.hills?.[k]).length<2)return;
 e.preventDefault();hillEx(k,(S.ex[k]||0)+d);
})}
// the finding line: the measured pair, on the dev set and the control
function hFinding(x,runs,D,U){
 const ch=S.state.champion,now=runs.find(o=>o.m===ch);
 if(!runs.length)return `No runs on the dev set yet.`;
 const {sub,ref,refFound}=hPair(x,runs),refName=refFound?`<b>${esc(ref.m)}</b>, where the hill was found`:'the champion';
 const say=r=>isRate(r)?`solves ${solved(r)} of ${r.n}`:U?`takes ${secsOf(r.score)} a question on average`:`scores ${hNum(r.score)}`;
 if(!sub)return now?`No attempt yet. The champion ${say(now.r)} on the dev set.`:'No attempt yet.';
 const m=`<b>${esc(sub.m)}</b>`;
 if(!ref)return `${m} ${say(sub.r)} on the dev set; the champion has no run to compare.`;
 let s;
 const fl=D&&binary(D.target)?hFlips(D.target.runs[sub.m],D.target.runs[ref.m]):null;
 if(fl)s=`${m} fixes ${fl.f} of ${sub.r.n} dev examples and breaks ${fl.k}, against ${refName}`;
 else if(isRate(sub.r)&&isRate(ref.r))s=`${m} solves ${solved(sub.r)} of ${sub.r.n} on the dev set, ${(k=>k===0?'level with':`${Math.abs(k)} ${k>0?'more':'fewer'} than`)(solved(sub.r)-solved(ref.r))} ${refName}`;
 else if(U){const d=Math.abs(sub.r.score)-Math.abs(ref.r.score);s=`${m} takes ${secsOf(sub.r.score)} a dev question on average, ${Math.abs(d)<1e-9?'level with':`${hNum(Math.abs(d))}&nbsp;s ${d<0?'faster':'slower'} than`} ${refName}`}
 else{const d=sub.r.score-ref.r.score;s=`${m} scores ${hNum(sub.r.score)} on the dev set against ${refName}’s ${hNum(ref.r.score)} (${d>0?'+':'−'}${hNum(Math.abs(d))})`}
 if(x.control){
  if(!sub.c||!ref.c)s+='. Control not run';
  else if(isRate(sub.c)&&isRate(ref.c)){const k=solved(sub.c)-solved(ref.c);s+=k===0?`. Control level, ${solved(sub.c)} of ${sub.c.n}`:`. Control ${k>0?'+':'−'}${Math.abs(k)}, ${solved(sub.c)} of ${sub.c.n}`}
  else s+=`. Control ${hNum(sub.c.score)} against ${hNum(ref.c.score)}`;
 }
 return s+'.';
}
VIEWS.hill=key=>{
 const L=S.state,x0=L.hills[key];
 if(!x0)return page({title:'Hill not found',crumbs:[['Hills','#hills'],[key]]})+panel('',empty(`No hill named ${esc(key)}`,'See <a class="ln" href="#hills">all hills</a>.'));
 const x={...x0,_key:key},runs=hillRuns(x),D=S.hill?.key===key?S.hill.data:null,U=timed(x);
 const acts=x.climbed_by?`<span class="hacts">${pill('climbed','climbed')}<span>by ${mLink(x.climbed_by)}</span></span>`:st(x.status);
 let h=page({title:x.title,crumbs:[['Hills','#hills'],[x.title]],finding:hFinding(x,runs,D,U),acts});
 if(x.symptom)h+=`<p class="hlede">${esc(x.symptom)}</p>`;
 if(x.reason)h+=`<p class="hreason">${esc(x.reason)}${x.superseded_by?.length?` Replaced by ${x.superseded_by.map(s=>L.hills[s]?`<a class="ln" href="#hill/${enc(s)}">${esc(L.hills[s].title)}</a>`:esc(s)).join(', ')}.`:''}</p>`;
 const closed=x.status==='closed';
 h+=`<div class="stack"><div class="hgrid">${hExample(x,key)}${hCommon(x)}</div>${hAttempts(x,runs,U)}${hMatrices(x,runs,D,U)}${closed?hExpect(x):`<div class="hgrid">${hExpect(x)}${hNext(x,key)}</div>`}</div>`;
 return h;
};
function hExample(x,key){
 const exs=exsOf(x),i=Math.min(S.ex?.[key]||0,Math.max(0,exs.length-1)),ex=exs[i]||{};
 if(!(ex.input||ex.wrong||ex.right))return panel('Example',empty('No example yet','Add one with <code>arx hill explain '+esc(key)+' --example-input … --example-wrong … --example-right …</code>'));
 const k=esc(key);
 const nav=exs.length>1?`<span class="exnav"><button class="iconbtn" type="button" data-k="${k}" onclick="hillEx(this.dataset.k,${i-1})" aria-label="Previous example" title="Previous (←)">${I('<path d="M15 6l-6 6 6 6"/>')}</button><span class="exn">${i+1} of ${exs.length}</span><button class="iconbtn" type="button" data-k="${k}" onclick="hillEx(this.dataset.k,${i+1})" aria-label="Next example" title="Next (→)">${I('<path d="M9 6l6 6-6 6"/>')}</button></span>`:'';
 return panel('Example',`<div class="hex">
  ${ex.input?`<p class="hq">${esc(ex.input)}</p>`:''}
  <dl class="hans">
   ${ex.wrong?`<div class="bad"><dt><svg class="mk" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>Model answered</dt><dd>${esc(ex.wrong)}</dd></div>`:''}
   ${ex.right?`<div class="good"><dt><svg class="mk" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 6.5l2.5 2.5 4.5-6"/></svg>Correct</dt><dd>${esc(ex.right)}</dd></div>`:''}
  </dl>
  ${ex.why?`<p class="hwhy"><span>Why</span>${esc(ex.why)}</p>`:''}</div>`,{right:nav,cls:'hexc'});
}
function hCommon(x){
 const sh=hShare(x);
 const found=x.found_in?`<p class="hfin">Found in ${mLink(x.found_in)}</p>`:'';
 if(sh==null)return panel('How common',empty('Not counted yet',`Count it with <code>arx hill explain ${esc(x._key)} --share COUNT/OF --share-of "…"</code>`)+found,{cls:'hcom'});
 return panel('How common',`<div class="hbig"><b>${pct(sh)}</b><span>of failures</span></div>
  ${meter(sh,{cls:'warn'})}
  <p class="hofw"><b>${x.share.count} of ${x.share.of}</b> ${esc(String(x.share.of_what||'analysed failures').replace(new RegExp('^of\\s+('+x.share.of+'\\s+)?','i'),''))}</p>${found}`,{cls:'hcom'});
}
// who fixed it: every run on the dev set, the champion first
function hAttempts(x,runs,U){
 const L=S.state,ch=L.champion,sl=L.slices[x.target]||{},ctl=x.control?L.slices[x.control]||{}:null,now=runs.find(o=>o.m===ch);
 const D=S.hill?.key===x._key?S.hill.data:null,T=D?.target,bin=binary(T),cr=T?.runs?.[ch];
 const meta=`${sl.n!=null?plural(sl.n,'example'):''}`;
 const right=[sLink(x.target),sl.hash?`<span class="hhash"><span class="id" title="Slice hash ${esc(sl.hash)}">#${esc(String(sl.hash).slice(0,8))}</span>${copyBtn(sl.hash)}</span>`:'',sl.url?`<a class="ln" href="${esc(sl.url)}" target="_blank" rel="noopener">Data ${ICON.ext}</a>`:''].filter(Boolean).join('');
 const about=(sl.description?`<p class="hdesc">${esc(sl.description)}</p>`:'')+(x.measure||sl.metric?`<p class="hmeas"><span>Scoring</span>${esc(x.measure||sl.metric)}</p>`:'');
 const body=about?`<div class="habout">${about}</div>`:'';
 if(!runs.length)return panel('Attempts on the dev set',body+empty('No runs on this dev set yet',''),{meta,right:`<span class="hright">${right}</span>`,cls:'hdev'});
 const rows=runs.map(o=>{
  const me=o.m===ch,fl=!me&&bin&&cr&&T.runs[o.m]?hFlips(T.runs[o.m],cr):null,mod=L.models[o.m]||{};
  const tag=me?pill('champion','champion'):o.m===x.climbed_by?pill('climbed it','climbed'):mod.status==='rejected'?`<span class="htag" title="${esc(mod.reason||'')}">rejected</span>`:'';
  const run=(r,f)=>r?.task?`<a class="hrun" href="#task/${enc(r.task)}" onclick="event.stopPropagation()" title="Open this run">${f}</a>`:f;
  return `<tr class="click${mod.status==='rejected'?' rej':''}" onclick="location.hash='#model/${enc(o.m)}'"><td class="hm"><div class="two"><a href="#model/${enc(o.m)}"><b>${esc(o.m)}</b></a>${mod.change?`<span class="sub ell" title="${esc(mod.change)}">${esc(mod.change)}</span>`:''}</div></td>
   <td class="htg">${tag}</td>
   <td class="num fig">${run(o.r,hFig(o.r,U))}</td><td class="hbar">${isRate(o.r)?meter(o.r.score,{mark:!me&&now&&isRate(now.r)?now.r.score:null,cls:me?'muted':''}):''}</td>
   ${now?`<td class="num fig">${me?DASH:hDelta(o.r,now.r,U)}</td>`:''}
   ${bin&&cr?`<td class="num fig hfl">${fl?`<span class="${fl.f?'pos':'faint'}">+${fl.f}</span><span class="faint"> / </span><span class="${fl.k?'neg':'faint'}">−${fl.k}</span>`:DASH}</td>`:''}
   ${ctl?`<td class="num fig">${o.c?run(o.c,hFig(o.c,false)):'<span class="faint">not run</span>'}</td>${now?`<td class="num fig hdc">${me||!o.c?DASH:hDelta(o.c,now.c,false)}</td>`:''}`:''}</tr>`});
 const head=[['Model'],[''],[U?'Mean time':'Solved','num'],['']];
 if(now)head.push(['<span title="Change against the champion on the dev set">Δ vs champion</span>','num']);
 if(bin&&cr)head.push(['<span title="Examples the champion got wrong and this got right / right and this got wrong">Fixed / broke</span>','num hfl']);
 if(ctl){head.push(['Control','num']);if(now)head.push(['<span title="Change against the champion on the control">Δ control</span>','num hdc'])}
 const foot=ctl?`<p class="hctl"><span>Control</span>${sLink(x.control)}${ctl.n!=null?` · ${plural(ctl.n,'example')}`:''}${ctl.description?` · ${esc(ctl.description)}`:''}</p>`:'';
 return panel('Attempts on the dev set',body+table(head,rows)+foot,{meta,right:`<span class="hright">${right}</span>`,cls:'hdev'});
}
// the signature: models × examples, hardest first. Marks: solved, wrong, fixed (vs champion), broke.
function hMatrices(x,runs,D,U){
 if(!runs.length)return '';
 if(!D)return panel('Per example',`<div class="hmx-load">Loading per-example results…</div>`);
 let h=hMatrix(x.control&&D.control?.ids?.length?'Per example, dev set':'Per example',D.target,runs,U);
 if(x.control&&D.control?.ids?.length)h+=hMatrix('Per example, control',D.control,runs,false,true);
 return h;
}
function hMatrix(title,M,runs,U,isCtl){
 const ch=S.state.champion;
 if(!M?.ids?.length)return panel(title,empty('No per-example rows','Rows appear once an eval on this slice finishes.'));
 const bin=binary(M),cr=M.runs[ch];
 // model order follows the attempts table, then anything else that ran this slice
 const ms=[...runs.map(o=>o.m).filter(m=>M.runs[m]),...Object.keys(M.runs).filter(m=>!runs.some(o=>o.m===m))].sort((a,b)=>(b===ch)-(a===ch));
 const ease=id=>{const v=ms.map(m=>M.runs[m][id]).filter(v=>v!=null);return v.length?v.reduce((a,b)=>a+(bin?(b>=.5):b),0)/v.length:-Infinity};
 const E=Object.fromEntries(M.ids.map(id=>[id,ease(id)]));
 const ids=[...M.ids].sort((a,b)=>E[a]-E[b]);
 const val=v=>U?secsOf(v).replace('&nbsp;',' '):hNum(v);
 const cls=(m,id)=>{
  const v=M.runs[m][id];if(v==null)return ['na','not run'];
  const c=cr?.[id];
  if(bin){const ok=v>=.5;if(m!==ch&&c!=null&&ok!==(c>=.5))return ok?['fx','fixed']:['bk','broke'];return ok?['s1','solved']:['s0','wrong']}
  if(m===ch||c==null)return ['s1',val(v)];
  const tol=Math.max(1e-9,.1*Math.abs(c));
  if(Math.abs(v-c)<=tol)return ['s1',`${val(v)}, level with the champion`];
  return better(v,c)?['fx',`${val(v)}, better than the champion’s ${val(c)}`]:['bk',`${val(v)}, worse than the champion’s ${val(c)}`];
 };
 const lg=bin?[['s1','solved'],['s0','wrong'],['fx','fixed'],['bk','broke'],['na','not run']]:cr?[['s1','level'],['fx','better'],['bk','worse'],['na','not run']]:[['s1','run'],['na','not run']];
 const legend=`<span class="hlg">${lg.map(([c,l])=>`<span><i class="c ${c}"></i>${l}</span>`).join('')}</span>`;
 const sel=S.hsel&&S.hsel.slice===M.slice&&M.ids.includes(S.hsel.id)?S.hsel.id:null;
 const rows=ms.map(m=>{
  const r=M.runs[m],me=m===ch,vals=ids.map(id=>r[id]).filter(v=>v!=null);
  const tot=bin?`<b>${vals.filter(v=>v>=.5).length}</b><span class="of">&nbsp;/&nbsp;${ids.length}</span>`:vals.length?`<b>${U?hNum(Math.abs(vals.reduce((a,b)=>a+b,0)/vals.length)):hNum(vals.reduce((a,b)=>a+b,0)/vals.length)}</b>${U?'<span class="of">&nbsp;s</span>':''}`:DASH;
  return `<div class="hmx-row${me?' champ':''}"><a class="hmx-m" href="#model/${enc(m)}" title="${esc(m)}">${esc(m)}</a><div class="hmx-cells">${ids.map(id=>{const [c,l]=cls(m,id);return `<i class="c ${c}${id===sel?' sel':''}" data-id="${esc(id)}" title="${esc(m)}: ${esc(l)}"></i>`}).join('')}</div><span class="hmx-t fig">${tot}</span></div>`;
 }).join('');
 const detail=sel?hCellDetail(M,ms,sel,cls,bin,U):`<p class="hmx-hint">Hardest examples on the left. Click a column to see one example across every model.</p>`;
 return panel(title,`<div class="hmx" data-slice="${esc(M.slice)}" onclick="hillCell(event)" style="--cols:${ids.length}">${rows}</div>${detail}`,
  {meta:`${plural(ids.length,'example')} × ${plural(ms.length,'model')}`,right:legend,cls:'hmxp'+(isCtl?' ctl':'')});
}
// one example across every model: its id, how many solved it, and who fixed or broke it
function hCellDetail(M,ms,id,cls,bin,U){
 const ch=S.state.champion,by={};
 for(const m of ms){const [c]=cls(m,id);(by[c]=by[c]||[]).push(m)}
 const ran=ms.filter(m=>M.runs[m][id]!=null).length,cv=M.runs[ch]?.[id];
 const names=a=>a.map(m=>`<a class="ln" href="#model/${enc(m)}">${esc(m)}</a>`).join(', ');
 const bits=[];
 if(bin){
  const ok=ms.filter(m=>M.runs[m][id]!=null&&M.runs[m][id]>=.5).length;
  bits.push(`Solved by <b>${ok} of ${ran}</b> models`);
  if(cv!=null)bits.push(`the champion got it <b>${cv>=.5?'right':'wrong'}</b>`);
 }else if(cv!=null)bits.push(`Champion ${U?secsOf(cv):hNum(cv)}`);
 if(by.fx?.length)bits.push(`<span class="pos">${bin?'fixed':'better'}</span> by ${names(by.fx)}`);
 if(by.bk?.length)bits.push(`<span class="neg">${bin?'broken':'worse'}</span> by ${names(by.bk)}`);
 return `<div class="hmx-sel"><span class="hsel-id"><span class="id">${esc(id)}</span>${copyBtn(id)}</span><p>${bits.join('; ')}.</p><button class="iconbtn" type="button" onclick="hillCellClear()" aria-label="Clear the selected example" title="Clear">${I('<path d="M6 6l12 12M18 6L6 18"/>',14)}</button></div>`;
}
function hExpect(x){
 const L=S.state,bits=[];
 if(x.goal)bits.push(`Goal <span class="mono">${esc(x.goal)}</span>`);
 if(x.created)bits.push(`Opened ${stamp(x.created)}`);
 if(x.closed)bits.push(`Closed ${stamp(x.closed)}`);
 const body=(x.problem?`<p class="hprob">${esc(x.problem)}</p>`:empty('Nothing declared before running',`Say what a change should move with <code>arx hill explain ${esc(x._key)} --problem "…"</code> before running it.`))+
  (bits.length?`<p class="hfound">${bits.join(' · ')}</p>`:'');
 return panel('Expected before running',body,{cls:'hexp'});
}
// what to run next: candidates on this hill with a rung still to run, each with its gate command
function hNext(x,key){
 const L=S.state,ch=L.champion;
 const cands=Object.entries(L.models).filter(([m,o])=>o.hill===key&&m!==ch&&(o.status==='candidate'||o.status==='planned'))
  .map(([m,o])=>({m,o,next:L.gates?.[m]?.next||[]})).filter(c=>c.next.length).sort((a,b)=>(b.o.created||0)-(a.o.created||0));
 const now=(L.leaderboard[x.target]||{})[ch];
 const pre=ch&&!now?`<p class="hn-none">The champion has no run on <span class="mono">${esc(short(x.target))}</span> yet; every candidate’s dev rung is paired against one.</p>`:'';
 let body;
 if(cands.length){
  const cap=3,shown=cands.slice(0,cap);
  body=pre+`<ul class="hnext">${shown.map(c=>`<li><div class="hn-top"><a class="ln" href="#model/${enc(c.m)}">${esc(c.m)}</a><span class="sub">${c.o.status==='planned'?'planned, ':''}needs ${c.next.map(n=>`<span class="mono" title="${esc(n.slice)}">${esc(short(n.slice))}</span>`).join(', ')}</span></div>${cmd('arx gate '+c.m)}</li>`).join('')}</ul>${cands.length>cap?`<p class="hn-more">${plural(cands.length-cap,'more candidate')} with runs to do: see <a class="ln" href="#models">Models</a>.</p>`:''}`;
 }else{
  body=pre+`<p class="hn-none">${x.status==='climbed'?'Nothing left to run on this hill.':'No candidate is climbing this hill. Register one from the champion:'}</p>${x.status==='climbed'?'':cmd(`arx model add <name> --parent ${ch||'<champion>'} --hill ${key} --change "…"`)}`;
 }
 return panel('Next',body,{meta:cands.length?plural(cands.length,'candidate'):'',cls:'hnx'});
}
}
