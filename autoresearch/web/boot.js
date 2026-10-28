// never swap the DOM under a pressed pointer or a live text selection; catch up on pointerup
let pdown=false,pending=false;
addEventListener('pointerdown',()=>{pdown=true},true);
addEventListener('pointerup',()=>{pdown=false;if(pending)setTimeout(render,0)},true);
addEventListener('pointercancel',()=>{pdown=false;if(pending)render()},true);
const busy=()=>{const g=getSelection();return pdown||(g&&!g.isCollapsed&&$('#main').contains(g.anchorNode))};

function render(force){
 if(!S.state){setHTML($('#main'),S.ok?`<div class="title"><div class="tt"><h1>${esc(ROUTES.find(([k])=>k===route().r)?.[1]||'arx')}</h1><p class="finding">Reading the ledger…</p></div></div>`:`<div class="banner">The dashboard server is not answering. Run <code>arx up</code> in the project.</div>`);renderTop();return}
 if(force!==true&&busy()){pending=true;return}
 pending=false;
 const {r,arg}=route();
 const v=VIEWS[r]||VIEWS.overview;
 S.crumbs=[];
 let html;try{html=v(arg)}catch(e){console.error(e);html=`<div class="banner">This view failed to draw: ${esc(e.message)}</div>`}
 const y=scrollY;
 if(setHTML($('#main'),(S.ok?'':`<div class="banner">Lost the dashboard server; showing the last state from ${clock(S.state.now)}.</div>`)+html)&&force!==true)scrollTo(0,y);
 renderNav();renderTop();
 document.title=(S.crumbs.at(-1)?.[0]||'arx')+' · '+(S.state.config?.name||'arx');
 S.afterRender?.forEach(f=>{try{f()}catch(e){console.error(e)}});
}
async function loadDetail(){
 const {r,arg}=route();
 if(r==='hill'&&arg){const d=await fetch('api/hill/'+enc(arg),{cache:'no-store'});S.hill=d.ok?{key:arg,data:await d.json()}:null}
 if(r==='task'&&arg){const d=await fetch('api/task/'+enc(arg),{cache:'no-store'});S.detail=d.ok?await d.json():null}
}
// one poll in flight; a request made meanwhile runs once after it lands
let inflight=null,again=false;
function tick(){
 if(inflight){again=true;return inflight}
 inflight=(async()=>{try{
  const s=await fetch('api/state',{cache:'no-store'});S.state=await s.json();S.ok=true;
  if(!S.pt||Date.now()-S.pt>15000){S.pt=Date.now();try{S.projects=await (await fetch('/api/projects',{cache:'no-store'})).json()}catch(e){}}
  await loadDetail();
 }catch(e){S.ok=false}
 render()})().finally(()=>{inflight=null;if(again){again=false;tick()}});
 return inflight;
}
// route change: paint at once from cached state; fetch only the detail the new route needs
addEventListener('hashchange',async()=>{
 const {r,arg}=route();
 S.detail=null;$('#app').classList.remove('nav-open');scrollTo(0,0);render(true);
 if((r==='hill'||r==='task')&&arg){try{await loadDetail()}catch(e){}render(true)}
});
addEventListener('keydown',e=>{if(e.key==='Escape')$('#app').classList.remove('nav-open')});
renderTop();tick();setInterval(()=>{if(!document.hidden)tick()},4000);
