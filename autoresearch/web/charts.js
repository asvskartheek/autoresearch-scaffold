'use strict';
// charts: interactive line charts shared by every view (ported from prototypes/charts).
// A view returns HTML strings, so a chart is a placeholder: XC.box(id, spec) registers the spec and returns
// <div data-xc=id>; after each render XC.mount() draws into it, keeping the chart (zoom, hover) across the 4 s poll.
//   spec: {group, series:[{id,name,color,pts:[[x,y,t?]],faint,smooth}], h, mode:'full'|'compact'|'mini', xLabel, yLabel,
//          domain:[x0,x1], ymin, ymax, yfix (the axis is exactly ymin..ymax, e.g. 0-100%), ref:{y,label}, band:[[x,lo,hi]], zero, yfmt:'num'|'pct'|'pct100'|'s'|'signed'|'pts'|'gb'|'int'|'dmin',
//          xfmt:'num'|'time'|'clock', t0, logOk}
//   Group state (shared by every chart with the same group: synced crosshair, zoom, smoothing, log-y, hidden series):
//   XC.g(name, defaults) -> {w, log, x:'step'|'time', zoom, pin, hidden:Set, hl}
//   XC.bar(group, {smooth, log, x, metric:[[key,label]], cur}) the controls; XC.legend(group, items) toggles series.
//   lineChart()/spark() in core.js call through here.
const XC=(()=>{
const NS='http://www.w3.org/2000/svg';
const specs={},inst={},groups={};
const PAL=['var(--xc-1)','var(--xc-2)','var(--xc-3)','var(--xc-4)','var(--xc-5)','var(--xc-6)'];
const G=(name,d={})=>groups[name]||(groups[name]={w:d.w??0.6,log:!!d.log,x:d.x||'step',zoom:null,pin:null,hidden:new Set(d.hidden||[]),hl:null});

// ---------- ticks: 1-2-5 linear, decades (with 2 and 5 when the range is short) for log
function niceStep(span,n){const raw=span/Math.max(1,n),p=Math.pow(10,Math.floor(Math.log10(raw||1))),f=raw/p;return (f<=1?1:f<=2?2:f<=5?5:10)*p}
function linTicks(lo,hi,n=5){const s=niceStep(hi-lo,n),a=Math.ceil(lo/s-1e-9)*s,out=[];for(let v=a;v<=hi+s*1e-6&&out.length<40;v+=s)out.push(+v.toPrecision(12));return {ticks:out,step:s}}
function niceDomain(lo,hi,n=5){if(hi===lo){const d=Math.abs(hi)*.1||1;lo-=d;hi+=d}const s=niceStep(hi-lo,n)/2,pad=(hi-lo)*.04;return [Math.floor((lo-pad)/s)*s,Math.ceil((hi+pad)/s)*s]}
function logTicks(lo,hi){const a=Math.floor(Math.log10(lo)),b=Math.ceil(Math.log10(hi)),out=[],mult=(b-a)<=2?[1,2,5]:[1];
 for(let e=a;e<=b;e++)for(const m of mult){const v=m*Math.pow(10,e);if(v>=lo*.999&&v<=hi*1.001)out.push(v)}return out}
// numbers: ticks at the step's precision, values at 3 significant figures, tiny and huge as 1.2e-5
function fmt(v,step){if(v==null||!isFinite(v))return '–';const a=Math.abs(v);if(v===0)return '0';
 if(a<1e-3||a>=1e6){const e=Math.floor(Math.log10(a)),m=v/Math.pow(10,e);return (Math.abs(m-Math.round(m))<1e-9?Math.round(m):m.toFixed(1))+'e'+e}
 if(step!=null&&step>=1e-3){const d=Math.max(0,-Math.floor(Math.log10(step)+1e-9));return v.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})}
 return a>=1000?Math.round(v).toLocaleString():a>=100?v.toFixed(0):a>=10?v.toFixed(1):a>=1?v.toFixed(2):v.toPrecision(3)}
const logLbl=v=>{const e=Math.floor(Math.log10(v)+1e-9),m=Math.round(v/Math.pow(10,e));return e<-2||e>4?(m===1?'':m+'×')+'1e'+e:String(+v.toPrecision(2))};
const sgn=v=>(v>0?'+':v<0?'−':'±')+Math.abs(Math.round(v)).toLocaleString();
const hm=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
const hms=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
// a value in a spec's own terms; `step` is the tick step (null for a read-out)
function yv(f,v,step){if(v==null||!isFinite(v))return '–';
 switch(f){case 'pct':return step!=null?fmt(100*v,step*100)+'%':(100*v).toFixed(1)+'%';case 'pct100':return Math.round(v)+'%';
  case 's':return fmt(v,step)+' s';case 'signed':return sgn(v);case 'gb':return fmt(v,step)+' GB';
  case 'pts':{const x=100*v,a=Math.abs(x),sg=x>1e-9?'+':x<-1e-9?'−':'';return sg+(step!=null?fmt(a,step*100):a.toFixed(1))+(step!=null?'':' pts')}case 'int':return Math.round(v).toLocaleString();
  case 'dmin':{const a=Math.abs(v),sg=v>1e-9?'+':v<-1e-9?'−':'±';return a<2?sg+Math.round(a*60)+' s':sg+(a<10?a.toFixed(1):Math.round(a))+' min'}default:return fmt(v,step)}}
// x read-outs: steps, minutes since start, or a clock time
const xv=(spec,g,x,step)=>spec.xfmt==='clock'?hms(x):g.x==='time'||spec.xfmt==='time'?(x<120?Math.round(x)+' s':fmt(x/60,step!=null?step/60:null)+' min'):step==null&&Math.abs(x-Math.round(x))<1e-9?Math.round(x).toLocaleString():fmt(x,step);

// ---------- EMA debiased like TensorBoard, so early points are not dragged toward 0
function ema(pts,w){if(w<=0)return pts.slice();let acc=0,n=0;return pts.map(p=>{acc=acc*w+(1-w)*p[1];n++;return [p[0],acc/(1-Math.pow(w,n))]})}
function at(pts,x){if(!pts.length||x<pts[0][0]-1e-9)return null;let lo=0,hi=pts.length-1;while(lo<hi){const m=(lo+hi+1)>>1;if(pts[m][0]<=x+1e-9)lo=m;else hi=m-1}return lo}

// ---------- one chart: owns its root element; mount() moves the root into each new placeholder
class Chart{
 constructor(id){
  this.id=id;const r=this.root=document.createElement('div');r.className='xc-in';
  this.svg=document.createElementNS(NS,'svg');this.svg.setAttribute('tabindex','0');this.svg.setAttribute('role','img');r.appendChild(this.svg);
  this.tip=document.createElement('div');this.tip.className='xc-tip';r.appendChild(this.tip);
  this.rv=document.createElement('div');this.rv.className='xc-rv';r.appendChild(this.rv);
  const pos=e=>{const b=this.svg.getBoundingClientRect();return (e.clientX-b.left)*(this.W/b.width)};
  const inPlot=px=>this.X&&px>=this.L-8&&px<=this.W-this.R+8;
  const cx=px=>this.inv(Math.max(this.L,Math.min(this.W-this.R,px)));
  let drag=null;
  this.svg.addEventListener('pointerdown',e=>{const px=pos(e);if(!inPlot(px))return;drag={px,x:cx(px),moved:false,touch:e.pointerType==='touch'}});
  this.svg.addEventListener('pointermove',e=>{const px=pos(e),g=this.g();
   if(drag&&!drag.touch&&Math.abs(px-drag.px)>4){drag.moved=true;brush(this.spec.group,[drag.x,cx(px)])}
   if(!inPlot(px)){if(g.pin==null)hoverGroup(this.spec.group,null);return}
   if(g.pin==null||drag?.touch)hoverGroup(this.spec.group,cx(px),this)});
  this.svg.addEventListener('pointerup',e=>{const px=pos(e);if(!drag)return;const d=drag;drag=null;const g=this.g();
   if(d.moved){brush(this.spec.group,null);const a=Math.min(d.x,cx(px)),b=Math.max(d.x,cx(px));if(b-a>(this.x1-this.x0)/100){g.zoom=[a,b];g.pin=null;redraw(this.spec.group)}return}
   if(d.touch){hoverGroup(this.spec.group,cx(px),this);return}
   g.pin=g.pin==null?cx(px):null;hoverGroup(this.spec.group,g.pin??cx(px),this)});  // a click pins the crosshair
  this.svg.addEventListener('pointerleave',()=>{drag=null;brush(this.spec.group,null);if(this.g().pin==null)hoverGroup(this.spec.group,null)});
  this.svg.addEventListener('dblclick',e=>{e.preventDefault();const g=this.g();if(g.zoom){g.zoom=null;g.pin=null;redraw(this.spec.group)}});
  this.svg.addEventListener('keydown',e=>{const g=this.g();
   if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const st=(this.x1-this.x0)/100,b=g.pin??this.x0;g.pin=Math.max(this.x0,Math.min(this.x1,b+(e.key==='ArrowRight'?st:-st)*(e.shiftKey?10:1)));hoverGroup(this.spec.group,g.pin,this)}
   if(e.key==='Escape'){if(g.pin!=null){g.pin=null;hoverGroup(this.spec.group,null)}else if(g.zoom){g.zoom=null;redraw(this.spec.group)}}});
  if(window.ResizeObserver){let w=0;new ResizeObserver(()=>{const cw=this.root.clientWidth;if(cw&&Math.abs(cw-w)>1){w=cw;this.draw();this.rehover()}}).observe(r)}
 }
 g(){return G(this.spec.group||this.id)}
 update(spec,sig){this.spec=spec;if(sig!==this.sig||this.root.clientWidth!==this.lastW){this.sig=sig;this.draw()}this.rehover()}
 rehover(){const g=this.g();if(g.pin!=null)this.hover(g.pin,null)}
 xs(p){const g=this.g(),s=this.spec;return g.x==='time'&&s.xfmt!=='clock'&&p[2]!=null?p[2]-(s.t0||0):p[0]}
 series(){
  const s=this.spec,g=this.g(),log=g.log&&s.logOk!==false;
  return (s.series||[]).filter(r=>!g.hidden.has(r.id||r.name)).map((r,i)=>{
   let raw=r.pts.filter(p=>p[1]!=null&&isFinite(p[1])).map(p=>[this.xs(p),p[1]]);
   let sm=r.smooth===false||s.smooth===false?raw:ema(raw,g.w);
   if(log){const k=raw.map((p,i)=>p[1]>0&&sm[i][1]>0);raw=raw.filter((_,i)=>k[i]);sm=sm.filter((_,i)=>k[i])}
   return {id:r.id||r.name,name:r.name,color:r.color||PAL[i%PAL.length],faint:r.faint,raw,smooth:sm,smoothed:sm!==raw}}).filter(r=>r.raw.length)}
 draw(){
  const s=this.spec,g=this.g(),el=this.root,mode=s.mode||'full',mini=mode==='mini',compact=mode!=='full';
  this.lastW=el.clientWidth;
  const vis=this.vis=this.series(),log=g.log&&s.logOk!==false;
  const labels=mode==='full'&&el.clientWidth>=520&&vis.length>1&&vis.length<=6;
  const W=this.W=Math.max(120,el.clientWidth||600),H=this.H=s.h||(mini?72:compact?132:320);
  const L=this.L=mini?0:compact?44:60,R=this.R=mini?0:compact?10:(labels?132:18),T=this.T=mini?12:compact?6:10,B=this.B=mini?2:compact?22:40;
  const all=vis.flatMap(r=>r.raw.map(p=>p[0]));
  let x0,x1;
  if(g.zoom){[x0,x1]=g.zoom}
  else{x0=s.domain&&g.x!=='time'?s.domain[0]:Math.min(...all);x1=s.domain&&g.x!=='time'?s.domain[1]:Math.max(...all);if(!s.domain&&s.xfmt!=='clock'&&x0>0&&x0<(x1-x0)*.2)x0=0}
  if(!isFinite(x0)||!isFinite(x1)){x0=0;x1=1}if(x1<=x0)x1=x0+1;
  this.x0=x0;this.x1=x1;
  this.svg.setAttribute('viewBox',`0 0 ${W} ${H}`);this.svg.setAttribute('height',H);
  if(!vis.length){this.svg.innerHTML=mini?'':`<text x="${W/2}" y="${H/2}" text-anchor="middle">${log?'No positive values':'Nothing to draw'}</text>`;this.X=null;return}
  // y range from points in the x window; raw trimmed to its 0.5–99.5th percentile so one spike cannot flatten a curve
  const inX=p=>p[0]>=x0&&p[0]<=x1;
  const ys=vis.flatMap(r=>r.raw.filter(inX).map(p=>p[1])).sort((a,b)=>a-b);
  const q=f=>ys[Math.min(ys.length-1,Math.max(0,Math.round(f*(ys.length-1))))];
  let lo=ys.length>40?q(.005):ys[0],hi=ys.length>40?q(.995):ys[ys.length-1];
  for(const r of vis)for(const p of r.smooth)if(inX(p)){lo=Math.min(lo,p[1]);hi=Math.max(hi,p[1])}
  if(s.band)for(const b of s.band)if(b[0]>=x0&&b[0]<=x1){lo=Math.min(lo,b[1]);hi=Math.max(hi,b[2])}
  if(s.ref?.y!=null){lo=Math.min(lo,s.ref.y);hi=Math.max(hi,s.ref.y)}
  if(s.zero){lo=Math.min(lo,0);hi=Math.max(hi,0)}
  if(lo==null||!isFinite(lo)){lo=0;hi=1}
  let yt;
  if(log){lo=Math.pow(10,Math.floor(Math.log10(lo)*4)/4);hi=Math.pow(10,Math.ceil(Math.log10(hi)*4)/4);if(hi<=lo)hi=lo*10;yt=logTicks(lo,hi);this.ystep=null}
  else{[lo,hi]=niceDomain(lo,hi,compact?3:5);if(s.ymin!=null)lo=s.yfix?s.ymin:Math.max(lo,s.ymin);if(s.ymax!=null)hi=s.yfix?s.ymax:Math.min(hi,s.ymax);if(hi<=lo)hi=lo+1;
   const t=linTicks(lo,hi,mini?1:compact?3:5);yt=mini?[lo,hi]:t.ticks;this.ystep=t.step}
  const X=this.X=x=>L+(x-x0)/(x1-x0)*(W-L-R);this.inv=px=>x0+(px-L)/(W-L-R)*(x1-x0);
  const Y=this.Y=log?y=>T+(1-(Math.log10(y)-Math.log10(lo))/(Math.log10(hi)-Math.log10(lo)))*(H-T-B):y=>T+(1-(y-lo)/(hi-lo))*(H-T-B);
  const cy=y=>Math.max(T-6,Math.min(H-B+6,Y(log?Math.max(y,lo):y)));
  const f=s.yfmt||'num',uid=this.uid||(this.uid=Math.random().toString(36).slice(2));
  let o='';
  for(const v of yt)o+=`<line class="gl" x1="${L}" x2="${W-R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/>`+(mini?`<text x="0" y="${(Y(v)-3).toFixed(1)}">${esc(yv(f,v,this.ystep))}</text>`:`<text x="${L-8}" y="${(Y(v)+3.5).toFixed(1)}" text-anchor="end">${log?logLbl(v):esc(yv(f,v,this.ystep))}</text>`);
  if(!mini){o+=`<line class="base" x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}"/>`;
   // time axes tick in whole minutes (1-2-5 of minutes), clocks in seconds or minutes, steps in 1-2-5
   const nx=Math.max(2,Math.round((W-L-R)/(compact?80:110))),mins=s.xfmt!=='clock'&&(g.x==='time'||s.xfmt==='time');
   const clk=s.xfmt==='clock'?(x1-x0<900?1:60):1;
   const xt0=mins?linTicks(x0/60,x1/60,nx):linTicks(x0/clk,x1/clk,nx),xt={ticks:xt0.ticks.map(v=>v*(mins?60:clk)),step:xt0.step*(mins?60:clk)};
   const xl=s.xfmt==='clock'?v=>clk===1?hms(v):hm(v):mins?v=>fmt(v/60,xt0.step):v=>fmt(v,xt.step);
   // a clock never ticks below a second, and no two ticks share a label (a 1-second domain once read 22:09:27 ×4)
   if(s.xfmt==='clock'&&xt.step<clk)xt.ticks=xt.ticks.filter(v=>Math.abs(v/clk-Math.round(v/clk))<1e-6);
   let prevL=null;xt.ticks=xt.ticks.filter(v=>{const l=xl(v);if(l===prevL)return false;prevL=l;return true});
   for(const v of xt.ticks)o+=`<line class="base" x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${H-B}" y2="${H-B+4}"/><text x="${X(v).toFixed(1)}" y="${H-B+15}" text-anchor="middle">${xl(v)}</text>`;
   if(mode==='full'){const xlab=s.xfmt==='clock'?'time':g.x==='time'||s.xfmt==='time'?'minutes since start':s.xLabel||'step';
    o+=`<text class="axl" x="${(L+W-R)/2}" y="${H-4}" text-anchor="middle">${esc(xlab)}</text>`;
    if(s.yLabel)o+=`<text class="axl" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">${esc(s.yLabel)}</text>`}}
  if(s.zero&&lo<0&&hi>0)o+=`<line class="zl" x1="${L}" x2="${W-R}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}"/>`;
  o+=`<rect class="brush" x="0" y="${T}" width="0" height="${H-T-B}"/>`;
  o+=`<clipPath id="cp${uid}"><rect x="${L}" y="${T-6}" width="${W-L-R}" height="${H-T-B+12}"/></clipPath><g clip-path="url(#cp${uid})">`;
  const ox=(x1-x0)*.02,path=pts=>{let d='',on=false;for(const p of pts){if(p[0]<x0-ox||p[0]>x1+ox){on=false;continue}d+=(on?'L':'M')+X(p[0]).toFixed(1)+' '+cy(p[1]).toFixed(1);on=true}return d};
  if(s.band&&s.band.length>1&&g.x!=='time'){const b=s.band.filter(b=>b[0]>=x0-ox&&b[0]<=x1+ox);
   if(b.length>1)o+=`<path class="band" d="${b.map((p,i)=>(i?'L':'M')+X(p[0]).toFixed(1)+' '+cy(p[2]).toFixed(1)).join('')}${b.slice().reverse().map(p=>'L'+X(p[0]).toFixed(1)+' '+cy(p[1]).toFixed(1)).join('')}Z"/>`}
  if(s.ref?.y!=null)o+=`<line class="ref" x1="${L}" x2="${W-R}" y1="${Y(s.ref.y).toFixed(1)}" y2="${Y(s.ref.y).toFixed(1)}"/>${s.ref.label?`<text class="refl" x="${W-R-2}" y="${(Y(s.ref.y)-4).toFixed(1)}" text-anchor="end">${esc(s.ref.label)} ${esc(yv(f,s.ref.y))}</text>`:''}`;
  const ends=[],sw=mini?1.6:compact?1.5:2;
  for(const r of vis){const dim=g.hl&&g.hl!==r.id?' class="dim"':'';
   o+=`<g${dim}>`;
   if(r.smoothed)o+=`<path d="${path(r.raw)}" fill="none" stroke="${r.color}" stroke-opacity=".22" stroke-width="1" stroke-linejoin="round"/>`;
   o+=`<path d="${path(r.smooth)}" fill="none" stroke="${r.color}" stroke-width="${r.faint?1:sw}" stroke-opacity="${r.faint?.6:1}" stroke-linejoin="round" stroke-linecap="round"/>`;
   const inside=r.smooth.filter(inX),l=inside[inside.length-1];
   if(l&&!r.faint){o+=`<circle cx="${X(l[0]).toFixed(1)}" cy="${cy(l[1]).toFixed(1)}" r="${compact?2.5:3.5}" fill="${r.color}" stroke="var(--surface)" stroke-width="2"/>`;if(X(l[0])>=W-R-(W-L-R)*.12)ends.push({r,y:cy(l[1]),x:X(l[0])})}
   o+=`</g>`}
  o+=`</g>`;
  // direct labels at the right edge, pushed apart so they never overlap; a thin leader joins label to line end
  if(labels&&ends.length){ends.sort((a,b)=>a.y-b.y);const gap=15,ly=ends.map(e=>e.y);
   for(let i=1;i<ly.length;i++)ly[i]=Math.max(ly[i],ly[i-1]+gap);
   const over=ly[ly.length-1]-(H-B);if(over>0)for(let i=0;i<ly.length;i++)ly[i]-=over;
   for(let i=ly.length-2;i>=0;i--)ly[i]=Math.min(ly[i],ly[i+1]-gap);
   const lx=W-R+10;
   ends.forEach((e,i)=>{const dim=g.hl&&g.hl!==e.r.id?' class="dim"':'';
    o+=`<g${dim}><path d="M${e.x+5} ${e.y}L${lx-4} ${ly[i]}" stroke="var(--control)" fill="none"/><text class="lbl" x="${lx}" y="${ly[i]+4}">${esc(e.r.name.length>16?e.r.name.slice(0,15)+'…':e.r.name)}</text></g>`})}
  o+=`<g class="hov"></g>`;
  this.svg.setAttribute('aria-label',`${vis.map(r=>r.name).join(', ')}`);
  this.svg.innerHTML=o;this.hov=this.svg.querySelector('.hov');this.brushEl=this.svg.querySelector('.brush');
 }
 hover(x,src){
  if(!this.X||!this.hov)return [];
  const s=this.spec,g=this.g();
  if(x==null||x<this.x0||x>this.x1){this.hov.innerHTML='';this.tip.style.display='none';this.rv.textContent='';return []}
  const px=this.X(x);let o=`<line class="xh${g.pin!=null?' pin':''}" x1="${px.toFixed(1)}" x2="${px.toFixed(1)}" y1="${this.T}" y2="${this.H-this.B}"/>`;
  const rows=[],slack=(this.x1-this.x0)*.03;
  for(const r of this.vis){const i=at(r.smooth,x);if(i==null)continue;
   if(x>r.smooth[r.smooth.length-1][0]+slack)continue;  // a run that has ended says nothing rather than hold its last value
   const sp=r.smooth[i];
   o+=`<circle cx="${this.X(sp[0]).toFixed(1)}" cy="${Math.max(this.T,Math.min(this.H-this.B,this.Y(g.log&&s.logOk!==false?Math.max(sp[1],1e-300):sp[1]))).toFixed(1)}" r="3.5" fill="${r.color}" stroke="var(--surface)" stroke-width="2"/>`;
   rows.push({r,y:sp[1],raw:r.raw[i][1],x:sp[0]})}
  this.hov.innerHTML=o;
  const f=s.yfmt||'num',mode=s.mode||'full';
  if(src===this&&mode==='full'&&rows.length){
   const anySm=rows.some(q=>q.r.smoothed);
   this.tip.innerHTML=`<div class="h"><span>${esc(s.xLabel&&g.x!=='time'&&s.xfmt!=='clock'?s.xLabel+' ':'')}${esc(xv(s,g,rows[0].x))}</span>${anySm?'<span>smoothed · raw</span>':''}</div>`+rows.map(q=>`<div class="r"><i style="background:${q.r.color}"></i><span>${esc(q.r.name)}</span><b>${esc(yv(f,q.y))}${q.r.smoothed?`<s>${esc(yv(f,q.raw))}</s>`:''}</b></div>`).join('');
   this.tip.style.display='block';
   const w=this.root.clientWidth,sc=w/this.W,left=px*sc,tw=this.tip.offsetWidth;
   this.tip.style.left=Math.max(0,left+16+tw>w?left-16-tw:left+16)+'px';this.tip.style.top='6px';
  }else this.tip.style.display='none';
  // compact and mini charts read out at the crosshair in their corner
  this.rv.innerHTML=mode!=='full'&&rows.length?`<span>${esc(xv(s,g,rows[0].x))}</span> `+rows.filter(q=>!q.r.faint).slice(0,3).map(q=>`<b style="color:${q.r.color}">${esc(yv(f,q.y))}</b>`).join(' '):'';
  return rows;
 }
}

const members=group=>Object.values(inst).filter(c=>c.spec&&(c.spec.group||c.id)===group&&c.root.isConnected);
function hoverGroup(group,x,src){for(const c of members(group))c.hover(x,src||c)}
function brush(group,r){for(const c of members(group)){if(!c.brushEl||!c.X)continue;
 if(!r){c.brushEl.setAttribute('width',0);continue}const a=c.X(Math.min(...r)),b=c.X(Math.max(...r));c.brushEl.setAttribute('x',a);c.brushEl.setAttribute('width',Math.max(0,b-a))}}
function redraw(group){for(const c of members(group)){c.draw();c.rehover()}syncBars(group)}
// a cheap signature: redraw only when the data or the group's settings changed
const sigOf=(s,g)=>JSON.stringify([s.h,s.mode,s.domain,s.ref,g.w,g.log,g.x,g.zoom,[...g.hidden],g.hl,(s.series||[]).map(r=>[r.name,r.pts.length,r.pts[r.pts.length-1]]),s.band?.length]);

// ---------- placeholders and mounting
function box(id,spec){
 specs[id]=spec;const h=spec.h||(spec.mode==='mini'?72:spec.mode==='compact'?132:320);
 return `<div class="xc ${spec.mode||'full'}" data-xc="${esc(id)}" style="height:${h}px"></div>`;
}
function mount(){
 for(const el of document.querySelectorAll('[data-xc]')){
  const id=el.dataset.xc,spec=specs[id];if(!spec)continue;
  const c=inst[id]||(inst[id]=new Chart(id));
  if(c.root.parentNode!==el){el.textContent='';el.appendChild(c.root)}
  c.update(spec,sigOf(spec,G(spec.group||id)));
 }
 for(const [id,c] of Object.entries(inst))if(!c.root.isConnected&&!document.querySelector(`[data-xc="${CSS.escape(id)}"]`)){delete inst[id];delete specs[id]}
 for(const g of Object.keys(groups))syncBars(g);
 mount.n=0;
}

// ---------- controls: smoothing, log-y, x as step or time, reset zoom; legend chips toggle series
function bar(group,{smooth=true,log=true,x=false,reset=true}={},d){
 const g=G(group,d);
 return `<div class="xc-bar" data-xc-g="${esc(group)}">
 ${smooth?`<label class="xc-ctl">Smoothing<input type="range" min="0" max="0.99" step="0.01" value="${g.w}" data-xc-w aria-label="Smoothing"><output>${g.w.toFixed(2)}</output></label>`:''}
 ${log?`<span class="xc-seg" role="group" aria-label="Y scale"><button type="button" data-xc-act="lin" class="${g.log?'':'on'}">Linear</button><button type="button" data-xc-act="log" class="${g.log?'on':''}">Log</button></span>`:''}
 ${x?`<span class="xc-seg" role="group" aria-label="X axis"><button type="button" data-xc-act="step" class="${g.x==='step'?'on':''}">Step</button><button type="button" data-xc-act="time" class="${g.x==='time'?'on':''}">Time</button></span>`:''}
 ${reset?`<button type="button" class="xc-reset" data-xc-act="reset" ${g.zoom?'':'hidden'}>Reset zoom</button>`:''}</div>`;
}
// items: [{id, name, color, value, cls, title, fixed}]; a fixed item is the run on screen and cannot be hidden
function legend(group,items,d){
 const g=G(group,d);
 return `<div class="xc-leg" data-xc-g="${esc(group)}">${items.map(it=>`<button type="button" class="xc-chip ${g.hidden.has(it.id)?'off':''} ${it.cls||''}" data-xc-id="${esc(it.id)}" ${it.fixed?'data-xc-fixed':''} title="${esc(it.title||it.name)}"><i style="background:${it.color}"></i><span class="nm">${esc(it.name)}</span>${it.value!=null?`<span class="v">${esc(it.value)}</span>`:''}${it.tag||''}</button>`).join('')}</div>`;
}
function syncBars(group){
 const g=groups[group];if(!g)return;
 for(const b of document.querySelectorAll(`.xc-bar[data-xc-g="${CSS.escape(group)}"]`)){
  const r=b.querySelector('[data-xc-act="reset"]');if(r)r.hidden=!g.zoom;
  b.querySelectorAll('[data-xc-act]').forEach(x=>{const a=x.dataset.xcAct;if(a==='lin'||a==='log')x.classList.toggle('on',(a==='log')===g.log);if(a==='step'||a==='time')x.classList.toggle('on',a===g.x)})}
 for(const l of document.querySelectorAll(`.xc-leg[data-xc-g="${CSS.escape(group)}"] .xc-chip`))l.classList.toggle('off',g.hidden.has(l.dataset.xcId));
}
document.addEventListener('click',e=>{
 const a=e.target.closest('[data-xc-act]'),chip=e.target.closest('.xc-chip');
 const host=(a||chip)?.closest('[data-xc-g]');if(!host)return;
 const grp=host.dataset.xcG,g=G(grp);e.preventDefault();e.stopPropagation();
 if(a){const v=a.dataset.xcAct;if(v==='lin'||v==='log')g.log=v==='log';else if(v==='step'||v==='time'){g.x=v;g.zoom=null;g.pin=null}else if(v==='reset'){g.zoom=null;g.pin=null}}
 else if(chip&&!chip.hasAttribute('data-xc-fixed')){const id=chip.dataset.xcId;
  if(e.altKey||e.metaKey||e.shiftKey){const ids=[...host.querySelectorAll('.xc-chip:not([data-xc-fixed])')].map(c=>c.dataset.xcId);const solo=ids.every(i=>i===id||g.hidden.has(i))&&!g.hidden.has(id);g.hidden=new Set(solo?[]:ids.filter(i=>i!==id))}
  else g.hidden.has(id)?g.hidden.delete(id):g.hidden.add(id)}
 redraw(grp);
},true);
document.addEventListener('input',e=>{const r=e.target.closest('[data-xc-w]');if(!r)return;const grp=r.closest('[data-xc-g]').dataset.xcG,g=G(grp);
 g.w=+r.value;const o=r.parentNode.querySelector('output');if(o)o.textContent=g.w.toFixed(2);cancelAnimationFrame(G.raf);G.raf=requestAnimationFrame(()=>redraw(grp))});
document.addEventListener('pointerover',e=>{const c=e.target.closest('.xc-chip');const host=c?.closest('[data-xc-g]');if(!host)return;const g=G(host.dataset.xcG),id=g.hidden.has(c.dataset.xcId)?null:c.dataset.xcId;if(id!==g.hl){g.hl=id;redraw(host.dataset.xcG)}});
document.addEventListener('pointerout',e=>{const c=e.target.closest('.xc-chip');const host=c?.closest('[data-xc-g]');if(!host||c.contains(e.relatedTarget))return;const g=G(host.dataset.xcG);if(g.hl){g.hl=null;redraw(host.dataset.xcG)}});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;for(const [n,g] of Object.entries(groups)){if(g.pin!=null){g.pin=null;hoverGroup(n,null)}else if(g.zoom&&members(n).length){g.zoom=null;redraw(n)}}});

// ---------- a static sparkline (no interaction): for table cells and tiny read-outs
function spark(y,color='var(--chart-1)',h=32){
 if(!y||y.length<2)return '';const W=300,lo=Math.min(...y),hi=Math.max(...y),r=hi-lo||1;
 return `<svg viewBox="0 0 ${W} ${h}" width="100%" height="${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${y.map((v,i)=>(i?'L':'M')+(i/(y.length-1)*W).toFixed(1)+' '+(h-3-(v-lo)/r*(h-6)).toFixed(1)).join('')}" fill="none" stroke="${color}" stroke-width="1.75" vector-effect="non-scaling-stroke"/></svg>`;
}

// tokens: a six-run palette (validated for light on #fff and dark on #13171b) and the chart chrome
const css=`:root{--xc-1:#0582a3;--xc-2:#c2410c;--xc-3:#2f70bb;--xc-4:#a86f0c;--xc-5:#9d4edd;--xc-6:#1e7b4f;--xc-shade:rgba(27,108,128,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--xc-1:#2aa5c2;--xc-2:#e06a35;--xc-3:#5b8fe0;--xc-4:#bd8a1c;--xc-5:#b072e8;--xc-6:#4cc38a;--xc-shade:rgba(92,184,204,.12)}}
:root[data-theme="dark"]{--xc-1:#2aa5c2;--xc-2:#e06a35;--xc-3:#5b8fe0;--xc-4:#bd8a1c;--xc-5:#b072e8;--xc-6:#4cc38a;--xc-shade:rgba(92,184,204,.12)}
.xc{position:relative;min-width:0;touch-action:pan-y;user-select:none;-webkit-user-select:none}
.xc-in{position:relative;width:100%;height:100%}
.xc svg{display:block;width:100%;overflow:visible;cursor:crosshair}
.xc svg:focus{outline:none}.xc svg:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.xc text{font-size:11px;fill:var(--faint);font-family:var(--font)}
.xc.mini text{font:10px var(--mono)}
.xc .axl{fill:var(--muted);font-size:12px}
.xc .gl{stroke:var(--grid);stroke-width:1}.xc .base{stroke:var(--control);stroke-width:1}
.xc .zl{stroke:var(--faint);stroke-opacity:.5}
.xc .xh{stroke:var(--muted);stroke-width:1;stroke-dasharray:2 3}.xc .xh.pin{stroke:var(--text);stroke-dasharray:none}
.xc .lbl{font-size:12px;font-weight:500;fill:var(--text)}
.xc .dim{opacity:.18}
.xc .brush{fill:var(--xc-shade)}
.xc .band{fill:var(--chart-1);fill-opacity:.14}
.xc .ref{stroke:var(--chart-3);stroke-dasharray:4 4;stroke-width:1.5}.xc .refl{fill:var(--chart-3)}
.xc-tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-card);padding:8px 10px;font-size:12px;min-width:170px;box-shadow:0 6px 20px rgba(0,0,0,.08);z-index:5;display:none;max-width:340px}
.xc-tip .h{color:var(--muted);margin-bottom:4px;display:flex;justify-content:space-between;gap:12px}
.xc-tip .r{display:grid;grid-template-columns:10px 1fr auto;gap:8px;align-items:center;line-height:1.7}
.xc-tip .r i{width:8px;height:8px;border-radius:50%}
.xc-tip .r span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xc-tip .r b{font-family:var(--mono);font-weight:500;text-align:right;white-space:nowrap}
.xc-tip .r s{text-decoration:none;color:var(--faint);font-family:var(--mono);font-size:11px;margin-left:8px}
.xc-rv{position:absolute;right:0;top:-2px;font:11px var(--mono);color:var(--muted);pointer-events:none;white-space:nowrap;background:var(--surface);padding-left:4px}
.xc-rv:empty{display:none}.xc-rv b{font-weight:500}
.xc-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px}
.xc-ctl{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.xc-ctl input[type=range]{width:110px;accent-color:var(--accent)}
.xc-ctl output{font-family:var(--mono);font-size:12px;color:var(--text);min-width:32px}
.xc-seg{display:inline-flex;border:1px solid var(--control);border-radius:var(--radius-control);overflow:hidden;flex:none}
.xc-seg button,.xc-reset{all:unset;cursor:pointer;padding:4px 10px;font-size:13px;color:var(--muted)}
.xc-seg button+button{border-left:1px solid var(--control)}
.xc-seg button.on{background:var(--active);color:var(--text);font-weight:500}
.xc-reset{border:1px solid var(--control);border-radius:var(--radius-control)}.xc-reset:hover{color:var(--text)}
.xc-reset[hidden]{display:none}
.xc-leg{display:flex;flex-wrap:wrap;gap:6px}
.xc-chip{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:8px;height:28px;padding:0 10px;border:1px solid var(--border);border-radius:999px;font-size:13px;user-select:none;max-width:100%}
.xc-chip:hover{border-color:var(--control)}.xc-chip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.xc-chip[data-xc-fixed]{cursor:default}
.xc-chip i{width:14px;height:3px;border-radius:2px;flex:none}
.xc-chip .nm{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xc-chip .v{font-family:var(--mono);font-size:12px;color:var(--muted)}
.xc-chip.off{color:var(--faint)}.xc-chip.off i{background:var(--control)!important}.xc-chip.off .v{display:none}
@media (max-width:760px){.xc-ctl input[type=range]{width:90px}}`;
const st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
addEventListener('resize',()=>{cancelAnimationFrame(G.rz);G.rz=requestAnimationFrame(()=>{for(const c of Object.values(inst))if(c.root.isConnected){c.draw();c.rehover()}})});
(S.afterRender=S.afterRender||[]).push(mount);
return {box,mount,bar,legend,spark,g:G,PAL,ema,fmt,yv,groups};
})();
