/* Posters: one picture per model and per hill that explains the idea and what happened.
   Three sources, in order: a stored file (api/poster/<kind>/<id>: svg, png, jpg, webp, or an html widget),
   a stored JSON spec (poster_spec on the state record, see docs/guides/posters.md), and a spec derived from the ledger.
   Specs are drawn by one template at any size.

   Entry points (return HTML strings)
     posterThumb(kind,id)            ~320x180 card for tables and grids; kind is 'model' or 'hill'
     posterBig(kind,id)              full-width interactive version for detail pages (hover/click a step, count/% toggle, stamp opens the why)
     posterAuto(kind,id,big=false)   the spec-drawn card (stored spec, else derived)
     pxDerive(kind,id)               the spec derived from the ledger, {derived:true}

   Reusable primitives (SVG fragments, to be placed inside one <svg>; colours are CSS variables so light/dark just work)
     pxVerdict(status)               -> 'champion'|'candidate'|'rejected'|'historical'   (maps retired/planned/open/climbed...)
     pxColor(verdict)                -> css colour string for a verdict
     pxMark(verdict,cx,cy,r)         verdict mark: tinted disc with a glyph (crown, dashed ring, cross, dash)
     pxTimeline(items,x,y,w,r=4)     dots in order; items [{verdict,tip?,href?}]; spacing shrinks to fit w
     pxSvg(inner,{w,h,label})        wrapper: <svg viewBox> with the card background
     pxCard(html,big)                wrapper div that fixes the 16:9 box; used for img/iframe/svg alike
   tip: [title,line,line] shown by the global hover tooltip (data-tip). href: a hash route such as 'model/x'. */
const PX_VERDICT={champion:'champion',candidate:'candidate',planned:'candidate',open:'candidate',rejected:'rejected',closed:'rejected',failed:'rejected',historical:'historical',retired:'historical',climbed:'champion'};
const pxVerdict=s=>PX_VERDICT[s]||'historical';
const PX_COLOR={champion:'var(--amber)',candidate:'var(--purple)',rejected:'var(--red)',historical:'var(--muted)'};
const pxColor=v=>PX_COLOR[pxVerdict(v)];
const pxTipAttr=t=>t?` data-tip='${esc(JSON.stringify([t[0]||'',t[1]||'',t[2]||'']))}'`:'';
const pxClip=(s,n)=>{s=String(s||'');return s.length>n?s.slice(0,n-1)+'…':s};

function pxMark(v,cx,cy,r){
 v=pxVerdict(v);const c=PX_COLOR[v],k=r*.42;
 const glyph={
  rejected:`<path d="M${cx-k} ${cy-k}L${cx+k} ${cy+k}M${cx+k} ${cy-k}L${cx-k} ${cy+k}" stroke="${c}" stroke-width="${r*.16}" stroke-linecap="round"/>`,
  historical:`<path d="M${cx-k} ${cy}H${cx+k}" stroke="${c}" stroke-width="${r*.16}" stroke-linecap="round"/>`,
  candidate:`<circle cx="${cx}" cy="${cy}" r="${k*.95}" fill="none" stroke="${c}" stroke-width="${r*.16}" stroke-dasharray="${r*.5} ${r*.28}"/>`,
  champion:`<path d="M${cx-k} ${cy+k*.7}L${cx-k*1.05} ${cy-k*.7}L${cx-k*.4} ${cy-k*.05}L${cx} ${cy-k}L${cx+k*.4} ${cy-k*.05}L${cx+k*1.05} ${cy-k*.7}L${cx+k} ${cy+k*.7}Z" fill="${c}"/>`}[v];
 return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="color-mix(in srgb,${c} 16%,transparent)" stroke="${c}" stroke-width="1.5"/>${glyph}`;
}
function pxTimeline(items,x,y,w,r=4){
 const n=items.length;if(!n)return '';const step=Math.min(r*3.2,(w-2*r)/Math.max(1,n-1));
 return `<path d="M${x+r} ${y}H${(x+r+step*(n-1)).toFixed(1)}" stroke="var(--border)" stroke-width="2"/>`+items.map((it,i)=>{
  const dot=`<circle cx="${(x+r+i*step).toFixed(1)}" cy="${y}" r="${r}" fill="${pxColor(it.verdict)}" stroke="var(--card)" stroke-width="1.5"/>`;
  return `<g${pxTipAttr(it.tip)}${it.href?` class="click" onclick="event.stopPropagation();location.hash='${esc(it.href)}'"`:''}>${dot}</g>`}).join('');
}
const pxSvg=(inner,{w=320,h=180,label=''}={})=>`<svg class="pxsvg" viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="${esc(label)}"><rect width="${w}" height="${h}" rx="12" fill="var(--card)"/>${inner}</svg>`;
const pxCard=(html,big)=>`<div class="pxcard${big?' big':''}">${html}</div>`;

// ---- icons: 24x24, stroked with currentColor
const PX_ICON={
 drawing:'<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M9 9.5v10"/><circle cx="15" cy="14.5" r="2"/>',
 crop:'<path d="M7 3v14h14M3 7h14v14"/>',
 zoom:'<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5M10.5 8v5M8 10.5h5"/>',
 ruler:'<rect x="2.5" y="8" width="19" height="8" rx="1.5"/><path d="M6.5 8v3M10 8v4.5M13.5 8v3M17 8v4.5"/>',
 compare:'<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
 tag:'<path d="M3.5 12.5v-8h8l9 9-8 8z"/><circle cx="8" cy="9" r="1.3"/>',
 link:'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
 graph:'<path d="M4 20V4M4 20h16M7.5 15l4-5 3 3 5-7"/>',
 filter:'<path d="M3.5 5h17l-6.5 8v6l-4-2v-4z"/>',
 vote:'<rect x="4" y="12" width="16" height="8" rx="1.5"/><path d="M9 12l-1-6 8-1.5 1.5 6M9.5 16h5"/>',
 brain:'<path d="M9 4.5a3 3 0 0 0-3 3 3 3 0 0 0-2 2.8 3 3 0 0 0 1.5 2.6A3.2 3.2 0 0 0 9 19.5c1 0 2-.5 3-1.5 1 1 2 1.5 3 1.5a3.2 3.2 0 0 0 3.5-3.6A3 3 0 0 0 20 12.3a3 3 0 0 0-2-2.8 3 3 0 0 0-3-3 3 3 0 0 0-3 1.5 3 3 0 0 0-3-1.5zM12 6v12"/>',
 check:'<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l3 3 5-6"/>',
 cross:'<circle cx="12" cy="12" r="8.5"/><path d="M9 9l6 6M15 9l-6 6"/>',
 search:'<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>',
 code:'<path d="M8.5 7l-5 5 5 5M15.5 7l5 5-5 5M13.5 5l-3 14"/>',
 legend:'<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="M12.5 9h5M7 14.5h3v3H7zM12.5 16h5"/>',
 layers:'<path d="M12 4l9 5-9 5-9-5zM3 13l9 5 9-5"/>',
 route:'<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8.2 18H15a3.5 3.5 0 0 0 0-7H9a3.5 3.5 0 0 1 0-7h6.8"/>',
 count:'<path d="M5 6v12M9.5 6v12M14 6v12M18.5 6v12M3.5 17l17-10"/>',
 shield:'<path d="M12 3.5l7.5 2.7v5.6c0 4.4-3.2 7.6-7.5 9-4.3-1.4-7.5-4.6-7.5-9V6.2z"/><path d="M8.7 12l2.4 2.4 4.2-4.6"/>',
 clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
 coin:'<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9.2c-.6-.8-1.5-1.2-2.5-1.2-1.4 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1 0-1.9-.4-2.5-1.2M12 6.2V8M12 16v1.8"/>',
 book:'<path d="M12 6.5C10 5 7 4.5 4 5v13c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5V5c-3-.5-6 0-8 1.5zM12 6.5v13"/>',
 wand:'<path d="M5 19L15 9M13.5 4.5l1 2.2 2.2 1-2.2 1-1 2.2-1-2.2-2.2-1 2.2-1zM18.5 12.5l.6 1.3 1.3.6-1.3.6-.6 1.3-.6-1.3-1.3-.6 1.3-.6z"/>',
 step:'<path d="M5 12h12M12.5 6.5L18 12l-5.5 5.5"/>'};
const pxIcon=n=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PX_ICON[n]||PX_ICON.step}</svg>`;
const PX_ARROW='<svg viewBox="0 0 24 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 6h19M16 1.5L21 6l-5 4.5"/></svg>';

// ---- verdict look
const PX_SPEC_COLOR={rejected:'var(--red)',passed:'var(--green)',champion:'var(--amber)',candidate:'var(--purple)',historical:'var(--muted)',open:'var(--blue)',climbed:'var(--green)'};
const PX_SPEC_WORD={rejected:'Rejected',passed:'Passed',champion:'Champion',candidate:'Candidate',historical:'Historical',open:'Open',climbed:'Climbed'};

// ---- a model's best run on the eval set (track) with the most examples, and what it is compared against there
function pxBest(k){
 const rs=(S.state.runs||[]).filter(r=>r.model===k);if(!rs.length)return null;
 const by={};rs.forEach(r=>(by[r.track]=by[r.track]||[]).push(r));
 const tr=Object.values(by).sort((a,b)=>Math.max(...b.map(r=>r.n))-Math.max(...a.map(r=>r.n)))[0];
 const best=tr.reduce((a,b)=>b.score>a.score?b:a);
 const T=(S.state.tracks||[]).find(t=>t.id===best.track);
 return Object.assign({count:rs.length,where:T?T.label:best.slice||best.dataset||''},best);
}
function pxRef(k,b){
 const st=S.state,m=st.models[k],on=id=>{const rs=(st.runs||[]).filter(r=>r.model===id&&r.track===b.track);return rs.length?rs.reduce((a,c)=>c.score>a.score?c:a):null};
 for(const [id,label] of [[m.parent,'Parent'],[st.champion,'Champion']])
  if(id&&id!==k){const r=on(id);if(r)return {label,id,score:r.score,n:r.n}}
 return null;
}
const pxRec=(kind,id)=>(kind==='hill'?S.state.hills:S.state.models)[id];

// ---- derive a spec from the ledger when nobody authored one
const pxCap=s=>s?s[0].toUpperCase()+s.slice(1):s;
function pxFit(s,n){s=pxCap(String(s||'').replace(/\s+/g,' ').trim());if(s.length<=n)return s;
 const cut=s.slice(0,n-1),sp=cut.lastIndexOf(' ');return (sp>n*.5?cut.slice(0,sp):cut).replace(/[\s,;:.-]+$/,'')+'…'}
const pxClauses=(s,n)=>String(s||'').split(/[.;,](?:\s+|$)/).map(x=>x.trim()).filter(x=>x.length>2).slice(0,n);
const PX_OUTCOME={rejected:['cross','Rejected'],champion:['check','Champion'],passed:['check','Passed'],candidate:['clock','Awaiting the gate'],historical:['book','Archived']};
const PX_RATIO=/(\d+)\s*\/\s*(\d+)\s*(?:to|->|-->|=>|→)\s*(\d+)\s*\/\s*(\d+)/i;
function pxDerive(kind,id){
 const st=S.state,rec=pxRec(kind,id);if(!rec)return null;
 if(kind==='hill'){
  const exs=rec.examples||(rec.example?[rec.example]:[]),ex=exs[0]||{},sym=/^duplicate/i.test(rec.symptom||'')||!rec.symptom?rec.problem:rec.symptom;
  let idea=ex.input&&ex.wrong?[{icon:'search',text:pxFit(ex.input,28),full:ex.input},{icon:'cross',text:pxFit('Says: '+ex.wrong,28),full:'Model answered: '+ex.wrong},
    ...(ex.right?[{icon:'check',text:pxFit('Truth: '+ex.right,28),full:'Correct answer: '+ex.right}]:[])]
   :pxClauses(sym,3).map(c=>({icon:'step',text:pxFit(c,28),full:c}));
  if(idea.length<2)idea=[{icon:'search',text:pxFit(rec.title||id,28),full:rec.title||id},{icon:'cross',text:'Fails today',full:'The champion fails here'}];
  const sh=rec.share,att=Object.values(st.models).filter(m=>m.hill===id).length;
  const done=rec.status==='climbed'||rec.status==='champion'||!!rec.climbed_by;
  return {v:1,derived:true,headline:pxFit(rec.title||id,70),idea,
   also:[...(sh&&sh.of?[{text:sh.count+' of '+sh.of+' failures',tone:'neutral'}]:[]),...(att?[{text:att+(att===1?' attempt':' attempts'),tone:'neutral'}]:[])],
   verdict:done?'climbed':'open',why:pxFit(pxClauses(rec.problem||sym,1)[0]||'',90),tags:[]};
 }
 const v=({champion:'champion',rejected:'rejected',candidate:'candidate',planned:'candidate'})[rec.status]||'historical',hill=st.hills[rec.hill];
 const cl=pxClauses(rec.change,3),oc=PX_OUTCOME[v];
 const idea=(cl.length?cl:[rec.title&&rec.title!==id?rec.title:'Change the model']).map(c=>({icon:'step',text:pxFit(c,28),full:c})).concat([{icon:oc[0],text:oc[1],full:oc[1]}]);
 let result=null;const b=pxBest(id);
 if(b){const ref=pxRef(id,b);
  result={label:pxFit(b.where||'Best run',40),after:{name:ref?'This':'Best run',value:Math.round(b.score*b.n),of:b.n}};
  if(ref)result.before={name:ref.label,value:Math.round(ref.score*ref.n),of:ref.n};
 }else{const q=PX_RATIO.exec(rec.reason||'');
  if(q&&+q[2]>0&&+q[4]>0&&+q[1]<=+q[2]&&+q[3]<=+q[4])result={label:'Reported in the notes',before:{name:'Before',value:+q[1],of:+q[2]},after:{name:'After',value:+q[3],of:+q[4]}};}
 const runs=b?b.count:0;
 return {v:1,derived:true,headline:pxFit(rec.title||id,70),idea,...(result?{result}:{}),
  also:[...(runs>1?[{text:runs+' runs',tone:'neutral'}]:[])],verdict:v,
  why:pxFit(pxClauses(rec.reason,1)[0]||'',90),tags:hill?[pxFit(hill.title,40)]:[]};
}
const pxSpecOf=(kind,id)=>{const r=pxRec(kind,id);return r&&r.poster&&r.poster_type==='json'&&r.poster_spec&&r.poster_spec.v===1?r.poster_spec:null};

// ---- the spec renderer (HTML; every size is in cqw so the thumbnail and the big page share one layout)
const pxNum=(x,pctMode)=>{const f=v=>String(+v.toFixed(1));return pctMode?f(100*x.value/x.of)+'%':f(x.value)+'/'+f(x.of)};
function pxResult(r,big){
 const a=r.after,b=r.before,pc=x=>Math.max(2,Math.min(100,100*x.value/x.of));
 const both=p=>`${b?`<span class="b">${esc(pxNum(b,p))}</span><span class="ar">→</span>`:''}<span class="a">${esc(pxNum(a,p))}</span>`;
 // thumbnails fall back to % when the counts would not fit
 const wide=[a,b].some(x=>x&&String(x.of).length>2);
 const nums=big?`<span class="pxv-c">${both(false)}</span><span class="pxv-p">${both(true)}</span>`:`<span>${both(wide)}</span>`;
 const bar=(x,cls)=>`<div class="pxbr ${cls}"><span class="pxbn">${esc(x.name)}</span><span class="pxbt"><i style="width:${pc(x).toFixed(1)}%"></i></span>${big?`<span class="pxbv"><span class="pxv-c">${esc(pxNum(x,false))}</span><span class="pxv-p">${esc(pxNum(x,true))}</span></span>`:''}</div>`;
 const dv=b?a.value/a.of-b.value/b.of:0,dp=Math.abs(dv)*100;
 return `<div class="pxrs"><div class="pxrl clamp1">${esc(r.label)}${big?`<span class="pxtg" role="group"><button type="button" class="pxc" onclick="pxMode(this,'count')">questions</button><button type="button" class="pxp" onclick="pxMode(this,'pct')">%</button></span>`:''}</div>
  <div class="pxrb"><div class="pxnum">${nums}</div><div class="pxbars">${b?bar(b,'was'):''}${bar(a,'now')}</div></div>${big&&b&&dp>1e-9?`<div class="pxdl ${dv>0?'up':'dn'}">${dv>0?'+':'−'}${dp.toFixed(dp%1?1:0)} points</div>`:''}</div>`;
}
function pxSpecHtml(spec,big,tipTitle){
 const v=PX_SPEC_COLOR[spec.verdict]?spec.verdict:'historical',idea=spec.idea||[],n=idea.length,tg=big?'button type="button"':'span';
 const stamp=`<${tg} class="pxstamp"${big?' onclick="pxWhy(this)" aria-label="Show the reason"':''}>${esc(PX_SPEC_WORD[v])}${spec.derived?'<small>auto</small>':''}</${big?'button':'span'}>`;
 const st=big?'button type="button"':'div',se=big?'button':'div';
 const flow=idea.map((s,i)=>`${i?`<span class="pxar">${PX_ARROW}</span>`:''}<${st} class="pxst"${big?` data-i="${i}" data-n="Step ${i+1} of ${n}" data-full="${esc(s.full||s.text)}" onmouseenter="pxHi(this,1)" onmouseleave="pxHi(this,0)" onclick="pxPin(this)"`:''}><span class="pxic">${pxIcon(s.icon)}</span><span class="pxsl">${esc(s.text)}</span></${se}>`).join('');
 const chips=(spec.also||[]).map(c=>`<span class="pxchip ${c.tone||'neutral'}">${esc(c.text)}</span>`).join('');
 const tags=(spec.tags||[]).map(t=>`<span class="pxtag">${esc(t)}</span>`).join('');
 const tip=big?'':pxTipAttr([tipTitle||spec.headline,spec.why||'',(spec.result&&spec.result.label)||'']);
 const inner=big?`<div class="pxtop"><div class="pxtags">${tags}${spec.derived?'<span class="pxauto" data-tip=\'["Drawn from the ledger","Nobody wrote a poster spec for this yet"]\'>auto</span>':''}</div>${stamp}</div>
   <div class="pxh">${esc(spec.headline)}</div><div class="pxflow">${flow}</div>
   <div class="pxbot">${spec.result?pxResult(spec.result,true):'<div></div>'}
    <div class="pxbox"><div class="pxbw" onclick="pxWhy(this)">${esc(spec.why||'')}</div><div class="pxbs"><b></b><span></span></div>${chips?`<div class="pxchips">${chips}</div>`:''}</div></div>`
  :`<div class="pxh">${esc(spec.headline)}</div><div class="pxflow">${flow}</div>
   <div class="pxbot">${spec.result?pxResult(spec.result,false):`<div class="pxwhy">${esc(spec.why||'')}</div>`}<div class="pxrr">${stamp}</div></div>`;
 return `<div class="pxs${big?' big':''}" style="--pv:${PX_SPEC_COLOR[v]}" data-mode="${big&&S.pxMode==='pct'?'pct':'count'}"${tip}><div class="pxi">${inner}</div></div>`;
}
// interaction (big poster only): attribute and class toggles, no redraw
function pxStep(p,el){const b=p.querySelector('.pxbs');b.querySelector('b').textContent=el.dataset.n;b.querySelector('span').textContent=el.dataset.full}
function pxHi(el,on){
 const p=el.closest('.pxs');if(!p||p.dataset.pin)return;
 if(on){p.dataset.hi=el.dataset.i;pxStep(p,el)}else delete p.dataset.hi;
 p.querySelectorAll('.pxst').forEach(x=>x.classList.toggle('on',!!on&&x===el));
}
function pxPin(el){
 const p=el.closest('.pxs'),was=p.dataset.pin===el.dataset.i;
 delete p.dataset.pin;p.querySelectorAll('.pxst').forEach(x=>x.classList.remove('on'));
 if(was){delete p.dataset.hi;return}
 p.dataset.pin=el.dataset.i;p.dataset.hi=el.dataset.i;el.classList.add('on');pxStep(p,el);
}
function pxMode(el,m){S.pxMode=m;el.closest('.pxs').dataset.mode=m}
function pxWhy(el){const p=el.closest('.pxs');p.classList.toggle('open');if(p.dataset.pin){delete p.dataset.pin;delete p.dataset.hi;p.querySelectorAll('.pxst').forEach(x=>x.classList.remove('on'))}}

function posterAuto(kind,id,big=false){
 const rec=pxRec(kind,id);if(!rec)return pxCard('',big);
 return pxSpecHtml(pxSpecOf(kind,id)||pxDerive(kind,id),big,rec.title||id);
}
function posterImg(kind,id,big){
 const rec=pxRec(kind,id),u=`api/poster/${kind}/${encodeURIComponent(id)}?v=${rec.poster_v||0}`;
 if(rec.poster_type==='html')
  return pxCard(`<iframe class="pxframe${big?'':' thumb'}" sandbox="allow-scripts" src="${u}" title="${esc(rec.title||id)}" loading="${big?'eager':'lazy'}" referrerpolicy="no-referrer"></iframe>`,big);
 return pxCard(`<img class="pximg" src="${u}" alt="${esc(rec.title||id)}" loading="lazy">`,big);
}
const pxFile=(kind,id)=>{const r=pxRec(kind,id);return !!(r&&r.poster&&r.poster_type!=='json')};
function posterThumb(kind,id){return pxFile(kind,id)?posterImg(kind,id,false):posterAuto(kind,id,false)}
function posterBig(kind,id){return pxFile(kind,id)?posterImg(kind,id,true):posterAuto(kind,id,true)}
