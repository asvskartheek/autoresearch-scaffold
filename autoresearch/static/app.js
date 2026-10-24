function render(){
 if(!S.state)return;renderNav();
 const {r,arg}=route();
 const v={goals:vGoals,overview:vOverview,workbench:vWorkbench,archive:vArchive,models:vModels,champions:vChampions,hills:vHills,slices:vSlices}[r];
 const y=scrollY,open=[...document.querySelectorAll('#main details')].map(d=>d.open);
 $('#main').innerHTML=v?v():r==='task'?vTask(arg):r==='model'?vModel(arg):r==='champion'?vChampion(arg):r==='hill'?vHill(arg):vOverview();
 document.querySelectorAll('#main details').forEach((d,i)=>{if(open[i])d.open=true});
 scrollTo(0,y);
}
const tip=document.createElement('div');tip.style.cssText='position:fixed;z-index:9;pointer-events:none;display:none;background:var(--card,#222);color:var(--ink);border:1px solid var(--border);border-radius:10px;padding:8px 11px;font-size:12.5px;line-height:1.45;box-shadow:0 6px 24px rgba(0,0,0,.35);max-width:320px';document.body.appendChild(tip);
document.addEventListener('mousemove',e=>{const el=e.target.closest&&e.target.closest('[data-tip]');if(!el){tip.style.display='none';return}const [a,b,c]=JSON.parse(el.dataset.tip);tip.innerHTML=`<b>${esc(a)}</b><br>${esc(b)}<br><span style="opacity:.65">${esc(c)}</span>`;tip.style.display='block';tip.style.left=Math.min(e.clientX+14,innerWidth-340)+'px';tip.style.top=(e.clientY+14)+'px'});
async function tick(){
 let sig='';
 try{
  const s=await fetch('api/state',{cache:'no-store'}),st=await s.json();S.ok=true;S.state=st;sig=JSON.stringify(st,(k,v)=>k==='now'?0:v);
  const {r,arg}=route();
  const get=async u=>{const d=await fetch(u,{cache:'no-store'});return d.ok?await d.json():null};
  if(r==='hill'&&arg){const d=await get('api/hill/'+encodeURIComponent(arg));S.hill=d?{key:arg,data:d}:null;sig+=JSON.stringify(d)}
  if(r==='champion'&&arg){const d=await get('api/champion/'+encodeURIComponent(arg));S.champ=d?{key:arg,data:d}:null;sig+=JSON.stringify(d)}
  if(r==='goals'){S.goals=await get('api/goals');sig+=JSON.stringify(S.goals)}
  if(r==='task'&&arg){S.detail=await get('api/task/'+encodeURIComponent(arg));sig+=JSON.stringify(S.detail)}
 }catch(e){S.ok=false;sig='off'}
 // an unchanged ledger is not redrawn, so a hovered chart point or an open menu is not wiped every few seconds
 if(sig===S.sig)return;S.sig=sig;render();
}
addEventListener('hashchange',()=>{S.detail=null;S.sig=null;scrollTo(0,0);tick()});
tick();setInterval(tick,4000);
