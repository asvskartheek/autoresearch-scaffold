function render(){
 if(!S.state){$('#main').innerHTML=S.ok?`<div class="title"><div class="tt"><h1>${esc(ROUTES.find(([k])=>k===route().r)?.[1]||'arx')}</h1><p class="finding">Reading the ledger…</p></div></div>`:`<div class="banner">The dashboard server is not answering. Run <code>arx up</code> in the project.</div>`;renderTop();return}
 const {r,arg}=route();
 const y=scrollY,open=[...document.querySelectorAll('#main details')].map(d=>d.open);
 const v=VIEWS[r]||VIEWS.overview;
 S.crumbs=[];
 let html;try{html=v(arg)}catch(e){console.error(e);html=`<div class="banner">This view failed to draw: ${esc(e.message)}</div>`}
 $('#main').innerHTML=(S.ok?'':`<div class="banner">Lost the dashboard server; showing the last state from ${clock(S.state.now)}.</div>`)+html;
 document.querySelectorAll('#main details').forEach((d,i)=>{if(open[i])d.open=true});
 renderNav();renderTop();
 document.title=(S.crumbs.at(-1)?.[0]||'arx')+' · '+(S.state.config?.name||'arx');
 scrollTo(0,y);
}
async function tick(){
 try{
  const s=await fetch('api/state',{cache:'no-store'});S.state=await s.json();S.ok=true;
  const {r,arg}=route();
  if(r==='hill'&&arg){const d=await fetch('api/hill/'+enc(arg),{cache:'no-store'});S.hill=d.ok?{key:arg,data:await d.json()}:null}
  if(r==='task'&&arg){const d=await fetch('api/task/'+enc(arg),{cache:'no-store'});S.detail=d.ok?await d.json():null}
 }catch(e){S.ok=false}
 render();
}
addEventListener('hashchange',()=>{S.detail=null;$('#app').classList.remove('nav-open');scrollTo(0,0);tick()});
addEventListener('keydown',e=>{if(e.key==='Escape')$('#app').classList.remove('nav-open')});
renderTop();tick();setInterval(tick,4000);
