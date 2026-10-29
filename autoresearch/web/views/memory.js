'use strict';
// What you know: the learner memory (autoresearch/memory.py, GET api/memory) for the person in this browser, across
// every project. Each concept is a ring: the arc is its strength now (mastery × recall), the colour its state.
// Due ones lead and link to the Brief of the project they live in.
{
const M={d:null,at:0,busy:false,err:null,who:null};
const me=()=>window.ARXP?ARXP.me().id:'';
async function load(force){
 if(M.busy||(!force&&M.d&&M.who===me()&&Date.now()-M.at<20000))return;
 M.busy=true;const who=me();
 try{const r=await fetch('api/memory?viewer='+enc(who),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);M.d=await r.json();M.who=who;M.err=null;M.at=Date.now()}
 catch(e){M.err=String(e.message||e)}
 M.busy=false;if(route().r==='memory')render(true);
}
const ST={known:'Known',shaky:'Shaky',due:'Due',untested:'Seen, not tested'};
const COL={known:'var(--positive)',shaky:'var(--negative)',due:'var(--warning)',untested:'var(--faint)'};
const NAMES={predict:'Predict',sketch:'Sketch',spot:'Spot the error',prototype:'Prototype',code:'Code',explain:'Explain back'};
// a ring: the track, the strength arc, hits of n in the middle
function ring(k,r){
 const c=2*Math.PI*r,f=Math.max(0,Math.min(1,k.strength||0)),col=COL[k.state]||COL.untested,sz=2*r+10;
 return `<svg class="mk-ring" width="${sz}" height="${sz}" viewBox="0 0 ${sz} ${sz}" aria-hidden="true">
  <circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="var(--active)" stroke-width="5"/>
  ${k.n?`<circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="${col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${(f*c).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${sz/2} ${sz/2})"/>`:`<circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="${col}" stroke-width="1.5" stroke-dasharray="3 3"/>`}
  <text x="${sz/2}" y="${sz/2+4}" text-anchor="middle" class="mono">${k.n?`${k.hits}/${k.n}`:'·'}</text></svg>`;
}
const when=t=>{if(!t)return '';const d=t-M.d.now;return Math.abs(d)<3600?'now':d>0?'in '+span(d):span(-d)+' ago'};
const tip=k=>[k.title||k.id,ST[k.state],k.n?`${k.hits} of ${k.n} right`:'',k.strength!=null?`strength ${Math.round(100*k.strength)}%`:'',k.due?`review ${when(k.due)}`:'',k.last_seen?`seen ${when(k.last_seen)}`:''].filter(Boolean).join(' · ');
const brief=k=>(k.project&&k.project!==M.d.project?`/p/${enc(k.project)}/`:'')+'#learn';
function node(k,r){
 const kind=k.kind==='model'?'model':k.kind==='hill'?'hill':k.kind==='goal'?'goal':'';
 return `<a class="mk-node ${k.state}" href="${brief(k)}" title="${esc(tip(k))}">${ring(k,r)}<span class="mk-l">${kind?`<i class="mk-kind">${kind}</i>`:''}${esc(k.title||k.id)}</span></a>`;
}
function dueHTML(ks){
 if(!ks.length)return '';
 return `<div class="mk-due">${ks.map(k=>`<a class="mk-chip" href="${brief(k)}" title="${esc(tip(k))}">${ring(k,9)}<span class="ell">${esc(k.title||k.id)}</span><span class="faint">${esc(k.project||'')}</span></a>`).join('')}</div>`;
}
function mapHTML(ks){
 const gen=ks.filter(k=>!k.project),by={};
 ks.filter(k=>k.project).forEach(k=>(by[k.project]=by[k.project]||[]).push(k));
 const order={hill:0,goal:1,model:2};
 const groups=Object.entries(by).sort(([a],[b])=>(b===M.d.project)-(a===M.d.project)||a.localeCompare(b));
 return `<div class="mk-gen">${gen.map(k=>node(k,26)).join('')}</div>`+
  groups.map(([p,xs])=>`<div class="mk-proj${p===M.d.project?' here':''}"><a class="mk-ph" href="/p/${enc(p)}/#memory">${esc(p)}</a>
   <div class="mk-row">${xs.sort((a,b)=>(order[a.kind]??3)-(order[b.kind]??3)||(a.title||'').localeCompare(b.title||'')).map(k=>node(k,15)).join('')}</div></div>`).join('');
}
function methodsHTML(ms){
 const rows=Object.entries(ms).sort((a,b)=>(b[1].n+b[1].skips)-(a[1].n+a[1].skips));
 if(!rows.length)return '';
 const top=Math.max(...rows.map(([,s])=>s.n+s.skips));
 return `<div class="mk-meth">${rows.map(([m,s])=>{const w=x=>(100*x/top).toFixed(1)+'%';
  return `<div class="mk-mr" title="${esc(`${NAMES[m]||m}: ${s.hits} of ${s.n} right, ${s.skips} skipped`)}"><span>${esc(NAMES[m]||m)}</span>
   <div class="mk-bar"><i class="h" style="width:${w(s.hits)}"></i><i class="m" style="width:${w(s.n-s.hits)}"></i><i class="s" style="width:${w(s.skips)}"></i></div>
   <span class="mono">${s.hits}/${s.n}</span></div>`}).join('')}</div>`;
}
// 30 days, one column a day: a dot per graded answer (right / wrong), a faint dot for everything else
function daysHTML(tl){
 const now=M.d.now,day=86400,cols=30,W=320,cw=W/cols,days=Array.from({length:cols},()=>({h:0,m:0,o:0}));
 tl.forEach(e=>{const i=cols-1-Math.floor((now-e.t)/day);if(i<0||i>=cols)return;const d=days[i];e.hit==null?d.o++:e.hit?d.h++:d.m++});
 const H=Math.max(36,Math.min(96,6*Math.max(1,...days.map(d=>d.h+d.m+Math.min(4,d.o)))+16));
 const dots=days.map((d,i)=>{let y=H-12,out='';const put=(n,c,o)=>{for(let j=0;j<n;j++){out+=`<circle cx="${(i+.5)*cw}" cy="${y}" r="2.4" fill="${c}" opacity="${o}"/>`;y-=6}};
  put(d.h,'var(--positive)',1);put(d.m,'var(--negative)',1);put(Math.min(4,d.o),'var(--muted)',.45);return out}).join('');
 return `<svg class="mk-days" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="30 days of activity"><line x1="0" x2="${W}" y1="${H-6}" y2="${H-6}" stroke="var(--grid)"/>${dots}
  <text x="0" y="${H}" class="faint">30 d ago</text><text x="${W}" y="${H}" text-anchor="end" class="faint">today</text></svg>`;
}
VIEWS.memory=()=>{
 load();
 const head=t=>page({title:'What you know',crumbs:[['Memory']],finding:t});
 if(!M.d)return head('')+(M.err?empty('Could not load memory',esc(M.err)):'<div class="mk skel"></div>');
 const d=M.d,ks=d.concepts||[];
 if(!d.person||!ks.length)return head('')+panel('',empty('Nothing remembered yet','Answer a card in the Brief and it lands here.')+`<div class="mk-cta"><a class="btn primary" href="#learn">Open the Brief</a></div>`);
 const due=ks.filter(k=>k.state==='due').sort((a,b)=>a.due-b.due),n=s=>ks.filter(k=>k.state===s).length;
 const legend=`<span class="mk-leg">${['known','shaky','due','untested'].map(s=>`<span><i style="background:${COL[s]}"></i>${ST[s]} ${n(s)}</span>`).join('')}</span>`;
 return head(due.length?`<b>${plural(due.length,'concept')} due</b>`:'Nothing due')+
  `<div class="mk">${due.length?panel('Due now',dueHTML(due)):''}
  ${panel('Concepts',mapHTML(ks),{right:legend})}
  <div class="mk-two">${panel('Methods',methodsHTML(d.methods)||empty('No answers yet'))}${panel('Last 30 days',daysHTML(d.timeline||[]))}</div></div>`;
};
}
