// Slices page: one collapsible section per dataset, a compact table per section.
const SL={q:'',tiny:false,open:{}};
const slWhen=t=>t?new Date(t*1000).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'';
const slHashNamed=s=>/^(slice\d+-)?[0-9a-f]{8,}$/.test(s.name.split('/').slice(1).join('/'))||/^slice\d+-[0-9a-f]{6,}$/.test(s.name.split('/').slice(1).join('/'));
function slSet(k,v){SL[k]=v;render();if(k==='q'){const i=$('#sl-q');if(i){i.focus();i.setSelectionRange(v.length,v.length)}}}
function slRuns(s){
 const rs=S.state.runs||[];
 return rs.filter(r=>r.slice===s.name||(s.hash&&r.track===s.dataset+'|'+s.hash));
}
function slLabel(s,runs){
 const raw=s.name.split('/').slice(1).join('/')||s.name;
 let nm=raw;
 if(/^pending-/.test(raw))nm=raw.replace(/^pending-/,'').replace(/[_-]+/g,' ')+' (pending)';
 else if(slHashNamed(s)){
  const c=runs.map(r=>r.dev_label||r.cohort).find(x=>x&&!/^(Slice|Eval set) · \d+$/.test(x));
  nm=c?c.replace(/^Slice\b/,'Eval set'):'Eval set · '+s.n;
 }
 return {nm,raw};
}
function slDesc(s,nm){const d=(s.description||'').replace(/;?\s*exact historical question membership\.?/i,'').trim();return d&&d!==nm&&!/^(Slice|Eval set) · \d+$/.test(d)?d:''}
function slBuild(){
 const st=S.state,out={};
 for(const s of Object.values(st.slices||{})){
  const runs=slRuns(s),{nm,raw}=slLabel(s,runs),sc=runs.filter(r=>r.score!=null);
  const best=sc.length?sc.reduce((a,b)=>b.score>a.score?b:a):null;
  (out[s.dataset]=out[s.dataset]||[]).push({s,runs,nm,raw,best,last:Math.max(0,...runs.map(r=>r.t||0)),tiny:slHashNamed(s)&&s.n<20});
 }
 for(const k of Object.keys(out))out[k].sort((a,b)=>(b.runs.length>0)-(a.runs.length>0)||b.last-a.last||b.s.n-a.s.n);
 return out;
}
function slTable(rows){
 return `<div class="scroll"><table class="slt"><tr><th>Eval set</th><th>Kind</th><th class="num">n</th><th>Hash</th><th class="num">Runs</th><th class="num">Best</th><th>Last run</th></tr>${rows.map(({s,runs,nm,raw,best,last})=>{
  const hill=S.state.hills[s.hill]?.title;
  return `<tr><td class="slnm"><b data-tip='${esc(JSON.stringify([raw,s.description||'',hill?'Hill: '+hill:'']))}'>${esc(nm)}</b>${nm!==raw&&!/^pending/.test(raw)&&nm!=='Eval set · '+s.n?`<span class="sub"> · ${esc(raw)}</span>`:''}${slDesc(s,nm)?`<div class="sub clamp2">${esc(slDesc(s,nm))}</div>`:''}</td>
  <td><span class="chip">${esc(s.kind)}</span></td><td class="num">${s.n}</td><td class="sub"><code>${esc(s.hash||'')}</code></td>
  <td class="num">${runs.length||'<span class="sub">0</span>'}</td>
  <td class="num">${best?`<span data-tip='${esc(JSON.stringify([pct(best.score)+' · n '+best.n,best.variant||best.label||'',slWhen(best.t)]))}'>${pct(best.score)}</span>`:''}</td>
  <td class="sub">${last?slWhen(last):''}</td></tr>`}).join('')}</table></div>`;
}
function vSlices(){
 const st=S.state,by=slBuild(),q=SL.q.trim().toLowerCase();
 const goal=st.config.final_target?.dataset||st.config.primary_dataset;
 const names=[...new Set([...Object.keys(st.datasets),...Object.keys(by)])];
 const nrun=d=>(by[d]||[]).reduce((a,x)=>a+x.runs.length,0);
 names.sort((a,b)=>(b===goal)-(a===goal)||nrun(b)-nrun(a)||a.localeCompare(b));
 const total=Object.values(st.slices||{}).length;
 if(!total&&!names.length)return topbar('Eval sets')+'<div class="card empty">No datasets or eval sets yet</div>';
 const hid=Object.values(by).flat().filter(x=>x.tiny).length;
 let h=topbar('Eval sets')+`<div class="filters"><input id="sl-q" class="search" type="search" placeholder="Search eval sets" value="${esc(SL.q)}" oninput="slSet('q',this.value)">${hid?`<label class="sub"><input type="checkbox" ${SL.tiny?'checked':''} onchange="slSet('tiny',this.checked)"> Show ${hid} tiny hash-named eval sets</label>`:''}<span class="sub">${total} slices · ${names.length} datasets</span></div>`;
 let any=false;
 for(const d of names){
  const x=st.datasets[d]||{},all=by[d]||[];
  const rows=all.filter(r=>(SL.tiny||!r.tiny)&&(!q||[r.nm,r.raw,r.s.description,r.s.hash,r.s.kind,d,x.title].some(v=>String(v||'').toLowerCase().includes(q))));
  if(q&&!rows.length)continue;any=true;
  const open=q?true:(SL.open[d.replace(/[^\w-]/g,'')]??(d===goal));
  h+=`<details class="card section sld" ${open?'open':''} ontoggle="if(!${!!q})SL.open['${d.replace(/[^\w-]/g,'')}']=this.open"><summary><span class="sldt" title="${esc(x.title||d)}">${esc(x.title||d)}</span><span class="sub">${x.size!=null?x.size+' examples · ':''}${all.length} eval sets · ${nrun(d)} runs</span>${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener" class="slu" onclick="event.stopPropagation()">dataset ↗</a>`:''}${d===goal?'<span class="chip">goal</span>':''}</summary>
   ${rows.length?slTable(rows):`<div class="empty">${all.length?`${all.length} tiny eval sets hidden`:'No eval sets'}</div>`}</details>`;
 }
 if(!any)h+='<div class="card empty">No eval set matches</div>';
 return h;
}
