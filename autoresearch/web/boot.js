// never swap the DOM under a pressed pointer or a live text selection; catch up on pointerup
let pdown=false,pending=false;
addEventListener('pointerdown',()=>{pdown=true},true);
addEventListener('pointerup',()=>{pdown=false;if(pending)setTimeout(render,0)},true);
addEventListener('pointercancel',()=>{pdown=false;if(pending)render()},true);
const busy=()=>{const g=getSelection();return pdown||(g&&!g.isCollapsed&&$('#main').contains(g.anchorNode))};

// before the first state lands: the shell, the route's crumb and "Reading the ledger…", painted at once
function placeholder(){
 const {r,arg}=route();
 S.crumbs=r==='hill'&&arg?[['Hills','#hills'],[arg]]:r==='model'&&arg?[['Models','#models'],[mnt(arg)]]:r==='goal'&&arg?[['Goals','#goals'],[arg]]:[[routeLabel(r)]];
 setHTML($('#main'),S.ok?`<div class="title"><div class="tt"><h1>${esc(S.crumbs.at(-1)[0])}</h1><p class="finding">Reading the ledger…</p></div></div>`:`<div class="banner">The dashboard server is not answering. Run <code>arx up</code> in the project.</div>`);
 renderNav();renderTop();
 document.title=S.crumbs.at(-1)[0]+' · arx';
}
// a task deep link outside the poll's window waits for its detail rather than flashing "Task not found"
const waitsDetail=()=>{const {r,arg}=route();return r==='task'&&arg&&!byId(arg)&&S.detail?.task?.id!==arg&&S.detailFor===arg};
function render(force){
 if(!S.state||waitsDetail()){placeholder();return}
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
 if(r==='task'&&arg){S.detailFor=arg;try{const d=await fetch('api/task/'+enc(arg),{cache:'no-store'});S.detail=d.ok?await d.json():null}finally{S.detailFor=null}}
}
// /api/state carries live tasks and the newest finished ones; the full list (archive, history charts) comes from
// /api/tasks, fetched only when a task starts, ends or is superseded, and merged under each poll's fresh window
let tasksBusy=false;
function mergeTasks(){
 const st=S.state;if(!st||!S.allTasks||!S.win)return;
 const win=new Set(S.win.map(t=>t.id));
 const rest=S.allTasks.filter(t=>!win.has(t.id));
 if(rest.some(isLive))S.tasksRev=null;  // was live when fetched, now outside the window: it ended; refetch
 st.tasks=S.win.concat(rest).sort((a,b)=>(b.updated||0)-(a.updated||0));
}
async function loadTasks(){
 if(tasksBusy)return;tasksBusy=true;
 try{const d=await (await fetch('api/tasks',{cache:'no-store'})).json();S.allTasks=d.tasks;S.tasksRev=d.rev;if(S.state){mergeTasks();render()}}
 catch(e){}finally{tasksBusy=false}
}
// the sidebar's project list loads beside the state, never in front of it
function loadProjects(){
 S.pt=Date.now();
 const pre=window.ARX_PRE?.projects;if(pre)window.ARX_PRE.projects=null;
 (pre||fetch('/api/projects',{cache:'no-store'})).then(r=>r.json()).then(j=>{S.projects=j;S.state&&!waitsDetail()?renderNav():placeholder()}).catch(()=>{});
}
// one poll in flight; a request made meanwhile runs once after it lands
let inflight=null,again=false;
function tick(){
 if(inflight){again=true;return inflight}
 if(!S.pt||Date.now()-S.pt>15000)loadProjects();
 inflight=(async()=>{
  const det=loadDetail().catch(()=>{});  // in parallel with the state
  try{
   const pre=window.ARX_PRE?.state;if(pre)window.ARX_PRE.state=null;
   const st=await (await (pre||fetch('api/state',{cache:'no-store'}))).json();
   S.state=st;S.win=st.tasks;S.ok=true;mergeTasks();
   if(st.tasks_total>st.tasks.length&&st.tasks_rev!==S.tasksRev)loadTasks();
  }catch(e){S.ok=false}
  render();
  await det;render();
 })().finally(()=>{inflight=null;if(again){again=false;tick()}});
 return inflight;
}
// route change: paint at once from cached state; fetch only the detail the new route needs
addEventListener('hashchange',async()=>{
 const {r,arg}=route();
 S.detail=null;$('#app').classList.remove('nav-open');scrollTo(0,0);
 const p=(r==='hill'||r==='task')&&arg?loadDetail().catch(()=>{}):null;
 render(true);if(p){await p;render(true)}
});
addEventListener('keydown',e=>{if(e.key==='Escape')$('#app').classList.remove('nav-open')});
// a person's first visit to a project lands on Start (views/start.js keeps the visits); after that a bare URL is the Overview
if(!location.hash&&window.START?.first)history.replaceState(null,'','#start');
placeholder();tick();setInterval(()=>{if(!document.hidden)tick()},4000);
if(window.ARXP){ARXP.on(()=>{if(S.state)renderTop()});ARXP.start('api/people',()=>location.hash.slice(1)||'overview')}
