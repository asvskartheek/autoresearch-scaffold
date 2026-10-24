// every research project (one goal each) with a running dashboard; the current one first
function vGoals(){
 const g=S.goals||[];
 return topbar('Goals')+(g.length?`<div class="cards gl">${g.map(x=>`<a class="card glcard${x.current?' on':''}" href="${x.current?'#overview':`http://${location.hostname}:${x.port}/`}">
  <div class="t">${esc(x.name)}</div>${x.goal?`<div class="sub clamp2">${esc(x.goal)}</div>`:''}
  <div class="glfoot"><span>${x.champion?'Champion · '+esc(x.champion):'No champion yet'}</span><span class="sub">${x.models} models${x.current?' · this dashboard':''}</span></div></a>`).join('')}</div>`:'<div class="card empty">No other dashboards running</div>');
}
