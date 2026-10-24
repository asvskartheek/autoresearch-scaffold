// hills: small clickable cards; each hill's page explains it with its example, share and runs
const firstLine=t=>String(t||'').split(/(?<=\.)\s/)[0];
const frac=r=>r?`${Math.round(r.score*r.n)} / ${r.n}`:'—';
function hillRuns(x){
 const st=S.state,T=st.leaderboard[x.target]||{},C=x.control?st.leaderboard[x.control]||{}:{};
 return Object.entries(T).map(([m,r])=>({m,r,c:C[m]})).sort((a,b)=>b.r.score-a.r.score);
}
function scoreBar(v,mark,cls=''){return `<div class="sbar ${cls}"><i style="width:${(100*(v||0)).toFixed(1)}%"></i>${mark!=null?`<b style="left:${(100*mark).toFixed(1)}%"></b>`:''}</div>`}
// ---- hill data: attempts are the models filed under the hill; their runs and verdicts come from the ledger
const hlVerdicts=['climbed','champion','candidate','historical','rejected'];
function hlAttempts(key){
 const st=S.state,runs=st.runs||[];
 return Object.entries(st.models).filter(([k,m])=>m.hill===key).map(([k,m])=>{
  const rs=runs.filter(r=>r.model===k).sort((a,b)=>(a.t||0)-(b.t||0));
  const ds=(st.decisions||[]).filter(d=>d.model===k||(d.model&&k.endsWith(d.model)));
  const best=rs.reduce((o,r)=>!o||r.score>o.score||(r.score===o.score&&r.n>o.n)?r:o,null);
  return {k,m,runs:rs,best,last:rs[rs.length-1]||null,decisions:ds,t:Math.max(m.created||0,...ds.map(d=>d.t||0),...rs.map(r=>r.t||0))};
 }).sort((a,b)=>b.m.created-a.m.created);
}
function hlSibling(key,x){
 const st=S.state;
 return Object.entries(st.hills).filter(([k,h])=>k!==key&&h.target&&h.target===x.target).map(([k,h])=>({k,h,n:Object.values(st.models).filter(m=>m.hill===k).length}));
}
function hlInfo(key,x){
 const at=hlAttempts(key),cnt={};at.forEach(a=>cnt[a.m.status]=(cnt[a.m.status]||0)+1);
 const best=at.reduce((o,a)=>a.best&&(!o||a.best.score>o.best.score)?a:o,null);
 const t=at.length?Math.max(...at.map(a=>a.t)):x.created||0;
 return {at,cnt,best,latest:at[0]||null,t,sib:hlSibling(key,x)};
}
const hlSlice=r=>short(r.slice||r.dataset||'');
// ---- hill-specific poster primitives (SVG fragments, same conventions as the px* ones in poster.js)
// a backdrop ridge across a chart box; the summit sits at the right third
function hlRidge(x,y,w,h){
 const P=[[0,1],[.18,.62],[.3,.74],[.55,.12],[.7,.4],[.82,.3],[1,1]].map(([a,b])=>`${(x+a*w).toFixed(1)} ${(y+b*h).toFixed(1)}`);
 return `<path d="M${P.join('L')}Z" fill="var(--soft)" stroke="var(--border)" stroke-width="1.2" stroke-linejoin="round"/>`;
}
// attempts as dots: x = order, y = score on the dev set, colour = verdict. items [{verdict,score,tip,href}]
function hlDots(items,x,y,w,h,lo,hi,base){
 const Y=v=>y+h-(Math.max(lo,Math.min(hi,v))-lo)/Math.max(1e-6,hi-lo)*h,n=items.length,step=n>1?(w-24)/(n-1):0,X=i=>(x+12+i*step).toFixed(1);
 const ticks=[lo,(lo+hi)/2,hi].map(v=>`<path d="M${x} ${Y(v).toFixed(1)}H${x+w}" stroke="var(--border)" stroke-dasharray="2 4"/><text x="${x-6}" y="${(Y(v)+3).toFixed(1)}" font-size="10" text-anchor="end" fill="var(--muted)">${Math.round(v*100)}%</text>`).join('');
 const bl=base!=null?`<path d="M${x} ${Y(base).toFixed(1)}H${x+w}" stroke="var(--amber)" stroke-width="1.5" stroke-dasharray="6 4"/><text x="${x+w}" y="${(Y(base)-5).toFixed(1)}" font-size="10" text-anchor="end" fill="var(--amber)">champion ${pct(base)}</text>`:'';
 const line=n>1?`<path d="M${items.map((it,i)=>`${X(i)} ${Y(it.score).toFixed(1)}`).join('L')}" fill="none" stroke="var(--muted)" stroke-width="1.2" opacity=".5"/>`:'';
 const dots=items.map((it,i)=>`<g class="click"${pxTipAttr(it.tip)}${it.href?` onclick="location.hash='${esc(it.href)}'"`:''}><circle cx="${X(i)}" cy="${Y(it.score).toFixed(1)}" r="14" fill="transparent"/><circle class="hldot" cx="${X(i)}" cy="${Y(it.score).toFixed(1)}" r="7" fill="${pxColor(it.verdict)}" stroke="var(--card)" stroke-width="2"/></g>`).join('');
 return ticks+bl+line+dots;
}
const hlMark=(st,r=9)=>`<svg class="hlmk" viewBox="0 0 ${2*r+2} ${2*r+2}" width="${2*r+2}" height="${2*r+2}" role="img" aria-label="${esc(st)}"><title>${esc(st)}</title>${pxMark(st,r+1,r+1,r)}</svg>`;
// the score an attempt is plotted at: its best run on the hill's dev set, else its best run anywhere
function hlScore(a,x){
 const on=a.runs.filter(r=>r.slice===x.target),pool=on.length?on:a.runs;
 const r=pool.reduce((o,r)=>!o||r.score>o.score?r:o,null);
 return r&&{...r,onTarget:!!on.length};
}
const hlOrdered=(key,x)=>hlInfo(key,x).at.slice().reverse();
const hlDup=(k,x)=>/^duplicate/i.test(x.symptom||'')&&hlSibling(k,x).some(o=>!/^duplicate/i.test(o.h.symptom||''));
function hlStrip(at,w=150){
 return `<svg class="hlstrip" viewBox="0 0 ${w} 12" width="${w}" height="12" role="img" aria-label="${at.length} attempts">${pxTimeline(at.map(a=>({verdict:a.m.status})),0,6,w,4)}</svg>`;
}
function hlCard(k,x,twins=[]){
 const I=hlInfo(k,x),at=I.at.slice().reverse(),b=I.best&&I.best.best;
 const sym=/^duplicate/i.test(x.symptom||'')?x.problem:(x.symptom||firstLine(x.problem));
 return `<a class="card hcard" href="#hill/${encodeURIComponent(k)}">
  ${posterThumb('hill',k)}
  <div class="hlb"><div class="hlt1">${hlMark(x.status,8)}<span class="t">${esc(x.title)}</span></div>
  <div class="sym">${esc(sym||'')}</div>
  <div class="hlfoot">${at.length?hlStrip(at.slice(-14)):'<span class="sub">no attempts</span>'}${b?`<span class="hlbest"><b>${pct(b.score)}</b><i class="sub">${esc(hlSlice(b))}</i></span>`:''}</div>
  ${twins.map(t=>`<div class="sub hltw">Also filed as ${esc(t.h.title)}</div>`).join('')}</div></a>`;
}
function vHills(){
 const st=S.state,hs=Object.entries(st.hills);
 if(!hs.length)return topbar('Hills')+'<div class="card empty">No hills yet. A hill is a named weakness of the champion, filed with <code>arx hill add</code>.</div>';
 const rank=([k,x])=>hlInfo(k,x).t,by=(a,b)=>rank(b)-rank(a);
 const shown=hs.filter(([k,x])=>!hlDup(k,x));
 const twinsOf=k=>hs.filter(([j,y])=>hlDup(j,y)&&hlSibling(j,y).some(o=>o.k===k)).map(([j,y])=>({k:j,h:y}));
 const open=shown.filter(([k,x])=>x.status!=='climbed').sort(by),done=shown.filter(([k,x])=>x.status==='climbed').sort(by);
 const grid=l=>`<div class="cards hills hlgrid">${l.map(([k,x])=>hlCard(k,x,twinsOf(k))).join('')}</div>`;
 return topbar('Hills')+grid(open)+(done.length?`<h2 class="hlh">Climbed<span class="sub">${done.length}</span></h2>${grid(done)}`:'');
}
const solved=r=>Math.round(r.score*r.n);
function delta(d,n){if(d==null)return '';const k=Math.round(d*n);return `<span class="${k>0?'pos':k<0?'neg':'sub'}">${k>0?'+':''}${k} solved</span>`}
// the hill's dev set: what it is, who solves how much of it, and which examples each attempt fixed or broke
function flips(a,b){let f=0,k=0;for(const id in a){if(!(id in b))continue;const x=a[id]>=.5,y=b[id]>=.5;if(x&&!y)f++;if(!x&&y)k++}return {f,k}}
function devSet(x,runs,now){
 const st=S.state,champ=st.champion,sl=st.slices[x.target]||{},ctl=x.control?st.slices[x.control]:null;
 const D=S.hill?.key===x._key?S.hill.data:null,T=D?.target,cr=T?.runs?.[champ];
 const nT=sl.n,nC=ctl?.n;
 const cell=r=>r?`<div class="sc"><div class="frac"><b>${solved(r)}</b> / ${r.n}</div>${scoreBar(r.score,null,'')}</div>`:'<span class="sub">not run</span>';
 let h=`<div class="card section"><h2>Dev set <span class="chip">${esc(short(x.target))}</span><span class="r hlcl">${[nT!=null?nT+' examples':'',sl.kind,sl.hash?'#'+String(sl.hash).slice(0,8):''].filter(Boolean).map(esc).join(' · ')}${sl.url?` · <a href="${esc(sl.url)}" target="_blank" rel="noopener" style="color:var(--blue)">data ↗</a>`:''}</span></h2>
  ${sl.description?`<p class="desc" style="margin:-6px 0 10px">${esc(sl.description)}</p>`:''}
  ${x.measure||sl.metric?`<p class="meas">${esc(x.measure||sl.metric)}</p>`:''}`;
 if(!runs.length)return h+`<div class="empty">Dev set ${esc(short(x.target))}${nT!=null?' ('+nT+' examples)':''}: no scored runs yet.</div></div>`;
 h+=`<div class="att head"><div>Model</div><div>Solved</div><div class="num">vs champion</div><div class="num">fixed · broke</div>${ctl?`<div class="ctl">Control<div class="sub">${esc(short(x.control))} · ${nC??'—'} examples</div></div>`:''}</div>`;
 h+=runs.map(o=>{const me=o.m===champ,d=now&&!me?o.r.score-now.r.score:null,fl=!me&&cr&&T.runs[o.m]?flips(T.runs[o.m],cr):null,cd=now?.c&&o.c&&!me?o.c.score-now.c.score:null;
  return `<a class="att" href="#model/${encodeURIComponent(o.m)}"><div class="nm"><b>${esc(o.m)}</b>${me?' <span class="chip champion">champion</span>':''}${st.models[o.m]?.change?`<div class="sub">${esc(st.models[o.m].change)}</div>`:''}</div>
  <div>${cell(o.r)}</div><div class="num">${me?'':delta(d,o.r.n)}</div>
  <div class="num">${fl?`<span class="pos">+${fl.f}</span> · <span class="neg">−${fl.k}</span>`:''}</div>
  ${ctl?`<div class="ctl">${o.c?`<span class="frac"><b>${solved(o.c)}</b> / ${o.c.n}</span> ${me?'':delta(cd,o.c.n)}`:'<span class="sub">not run</span>'}</div>`:''}</a>`}).join('');
 if(T&&T.ids.length){
  const ms=runs.map(o=>o.m).filter(m=>T.runs[m]);
  const ids=[...T.ids].sort((a,b)=>ms.filter(m=>T.runs[m][a]>=.5).length-ms.filter(m=>T.runs[m][b]>=.5).length);
  h+=`<div class="pex"><div class="pexh"><b>Per example</b><span class="lg"><i class="c s1"></i>solved<i class="c s0"></i>wrong<i class="c s1 fx"></i>fixed<i class="c s0 bk"></i>broke</span></div>
  ${ms.map(m=>{const r=T.runs[m],me=m===champ;return `<div class="prow"><div class="pl">${esc(m)}</div><div class="cells">${ids.map(id=>{const v=r[id];if(v==null)return `<i class="c na" title="${esc(id)} · not run"></i>`;const ok=v>=.5,c=!me&&cr&&id in cr?(ok&&cr[id]<.5?' fx':!ok&&cr[id]>=.5?' bk':''):'';return `<i class="c ${ok?'s1':'s0'}${c}" title="${esc(id)} · ${num(v,2)}"></i>`}).join('')}</div></div>`}).join('')}</div>`;
 }
 return h+'</div>';
}
// previous attempt (oldest first) that ran on an eval set this attempt also ran on
function hlDelta(list,i){
 const a=list[i];
 for(let j=i-1;j>=0;j--){
  for(const r of a.runs.slice().reverse()){
   const q=list[j].runs.filter(o=>o.track===r.track).pop();
   if(q)return {d:Math.round((r.score-q.score)*r.n),r,q,from:list[j]};
  }
 }
 return null;
}
function hlTile(list,i,x){
 const a=list[i],m=a.m,k=a.k,ml=encodeURIComponent(k),dl=hlDelta(list,i),sc=hlScore(a,x);
 const dec=a.decisions.filter(d=>d.kind!=='champion'||d.model===k);
 const rsn=m.reason||m.rejection_reason||'';
 const body=[m.change&&`<p>${esc(m.change)}</p>`,rsn&&`<p>${esc(rsn)}</p>`,
  a.runs.length&&`<div class="hlruns">${a.runs.map(r=>`<a href="#task/${encodeURIComponent(r.id)}" class="hlrun"><b>${pct(r.score)}</b> ${solved(r)} / ${r.n} <span class="sub">${esc(hlSlice(r))} · ${stamp(r.t)}</span></a>`).join('')}</div>`,
  dec.length&&`<div class="sub">${dec.map(d=>`${esc(d.kind)} ${stamp(d.t)}`).join(' · ')}</div>`].filter(Boolean).join('');
 return `<div class="hltile ${pxVerdict(m.status)}">
  <a class="hlpost" href="#model/${ml}">${posterThumb('model',k)}</a>
  <div class="hlmeta">${hlMark(m.status,9)}<a class="hlt" href="#model/${ml}">${esc(m.title||k)}</a></div>
  <div class="hlres">${sc?`<b>${pct(sc.score)}</b> <span class="sub">n ${sc.n}</span>`:'<span class="sub">no run</span>'}
   ${dl?`<span class="${dl.d>0?'pos':dl.d<0?'neg':'sub'}"${pxTipAttr(['vs '+(dl.from.m.title||dl.from.k),`${solved(dl.r)} / ${dl.r.n} against ${solved(dl.q)} / ${dl.q.n}`,hlSlice(dl.r)])}>${dl.d>0?'+':''}${dl.d} solved</span>`:''}</div>
  ${body?`<details class="hlmore"><summary>Details</summary>${body}</details>`:''}</div>`;
}
function attempts(key,x){
 const I=hlInfo(key,x),sib=I.sib.filter(o=>o.n),list=I.at.slice().reverse();
 if(!list.length)return `<div class="card section"><h2>Attempts</h2><div class="empty">No attempts yet${sib.length?`. ${sib.map(o=>`<a href="#hill/${encodeURIComponent(o.k)}">${esc(o.h.title)}</a> works on the same dev set and has ${o.n} ${o.n===1?'attempt':'attempts'}`).join('; ')}`:''}.</div></div>`;
 return `<div class="card section"><h2>Attempts<span class="r sub">${list.length}</span></h2><div class="hltiles">${list.map((a,i)=>hlTile(list,i,x)).join('')}</div></div>`;
}
// the attempts mountain under the hill poster: every attempt plotted by score on the dev set
function hlBig(key,x){
 const list=hlOrdered(key,x).map(a=>({a,sc:hlScore(a,x)})).filter(o=>o.sc);
 if(!list.length)return '';
 const W=640,H=360,champ=S.state.champion;
 const cr=(S.state.runs||[]).filter(q=>q.model===champ&&q.slice===x.target).sort((p,q)=>q.n-p.n)[0];
 const all=list.map(o=>o.sc.score).concat(cr?[cr.score]:[]);
 const lo=Math.max(0,Math.floor((Math.min(...all)-.08)*10)/10),hi=Math.min(1,Math.ceil((Math.max(...all)+.08)*10)/10);
 const items=list.map(o=>({verdict:o.a.m.status,score:o.sc.score,href:'model/'+encodeURIComponent(o.a.k),tip:[o.a.m.title||o.a.k,pct(o.sc.score)+' · n '+o.sc.n,hlSlice(o.sc)+(o.sc.onTarget?'':' (not the dev set)')]}));
 const inner=`<text x="20" y="28" font-size="15" font-weight="650" fill="var(--ink)">${esc(pxClip(x.title,60))}</text>
  <text x="20" y="46" font-size="11" fill="var(--muted)">${items.length} attempt${items.length===1?'':'s'} · score on ${esc(pxClip(short(x.target),40))}</text>
  ${hlRidge(52,60,W-76,H-90)}${hlDots(items,52,70,W-76,H-110,lo,hi,cr&&cr.score)}
  <text x="${W-20}" y="${H-12}" font-size="10" text-anchor="end" fill="var(--muted)">oldest to newest</text>`;
 return pxCard(pxSvg(inner,{w:W,h:H,label:x.title+' attempts'}),true);
}
function vHill(key){
 const st=S.state,champ=st.champion,x=st.hills[key]&&{...st.hills[key],_key:key};if(!x)return topbar('Not found');
 const runs=hillRuns(x),now=runs.find(o=>o.m===champ);
 const exs=x.examples||(x.example?[x.example]:[]),i=Math.min(S.ex?.[key]||0,Math.max(0,exs.length-1)),ex=exs[i]||{};
 const nT=st.slices[x.target]?.n,nC=x.control?st.slices[x.control]?.n:null;
 const cell=(r,base,n,mark)=>r?`<div class="sc"><div class="frac"><b>${solved(r)}</b> / ${r.n}</div>${scoreBar(r.score,mark,'')}</div>`:'<span class="sub">not run</span>';
 let h=topbar(x.title)+`<a class="back" href="#hills">← Hills</a>
 ${posterBig('hill',key)}
 <div class="hlmtn">${hlBig(key,x)}</div>
 <div class="hrow">${hlMark(x.status,9)}<span class="sub">${esc(x.status)}</span>${x.climbed_by?`<a class="chip pass" href="#model/${encodeURIComponent(x.climbed_by)}">climbed by ${esc(x.climbed_by)}</a>`:''}</div>
 ${(sy=>sy?`<p class="lede">${esc(sy)}</p>`:'')(/^duplicate/i.test(x.symptom||'')||!x.symptom?x.problem:x.symptom)}
 ${exs.length||x.share?`<div class="grid ${x.share?'hgrid':''}">
  ${exs.length?`<div class="card"><h2>Examples${exs.length>1?`<span class="r exnav">${exs.map((_,j)=>`<button class="${j===i?'on':''}" onclick="S.ex={...S.ex,['${esc(key)}']:${j}};render()">${j+1}</button>`).join('')}</span>`:''}</h2>
   ${ex.input||ex.wrong?`<div class="ex">
    ${ex.input?`<div class="exin"><div class="lbl">Question</div>${esc(ex.input)}</div>`:''}
    ${ex.wrong?`<div class="exo bad"><span>✗</span><div><div class="lbl">Model answered</div>${esc(ex.wrong)}</div></div>`:''}
    ${ex.right?`<div class="exo good"><span>✓</span><div><div class="lbl">Correct answer</div>${esc(ex.right)}</div></div>`:''}
    ${ex.why?`<div class="sub">${esc(ex.why)}</div>`:''}</div>`:'<div class="empty">No example</div>'}</div>`:''}
  ${x.share?`<div class="card"><h2>How common</h2><div class="big">${x.share.count}<small> of ${x.share.of}</small></div>
   <div class="ofw">${esc(x.share.of_what||'analysed failures')}</div>${scoreBar(x.share.count/x.share.of,null,'warn')}
   <div class="sub" style="margin-top:8px">${pct(x.share.count/x.share.of)} fall into this hill</div></div>`:''}
 </div>`:''}
 ${attempts(key,x)}
 ${devSet(x,runs,now)}
 ${x.problem||x.found_in?`<div class="card section"><details><summary>Pre-declared expectations</summary>${x.problem&&x.symptom&&!/^duplicate/i.test(x.symptom)?`<p class="desc">${esc(x.problem)}</p>`:''}${x.found_in?`<p class="sub">Found in ${esc(x.found_in)}</p>`:''}</details></div>`:''}`;
 return h;
}
