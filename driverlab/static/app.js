'use strict';
const $ = id => document.getElementById(id);
const names = {READY:'待启动',CRUISE:'正常行驶',WARNING:'风险预警',BRAKE:'制动停车',AVOID:'换道避让',DEGRADED:'故障降级',NO_ROUTE:'无可行路线',ARRIVED:'已抵达',COLLISION:'发生碰撞'};
const profiles = {balanced:'距离优先',fast:'时间优先',comfort:'舒适优先'};
const scenarioNames = {normal:'正常导航',congestion:'中央街拥堵',closure:'道路封闭',brake:'急停 / 拒绝换道',avoid:'障碍 / 允许换道',sensor:'传感器中断',no_route:'无可行路线'};
let state=null, tab='overview', connected=false, commandPending=false, requestVersion=0, routeSignature='', toastTimer;
function esc(value){return String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function number(value,digits=1){return value===null||value===undefined?'—':Number(value).toFixed(digits);}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
async function request(url, options={}){
  const response=await fetch(url,{...options,signal:AbortSignal.timeout(5000)});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);
  return data;
}
async function action(data){
  if(commandPending)return;
  commandPending=true; requestVersion++;
  try{state=await request('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});setConnected(true);render();if(tab==='records')loadRuns();}
  catch(error){toast(error.message);}
  finally{commandPending=false;}
}
function setConnected(value){connected=value;$('connection-dot').classList.toggle('offline',!value);$('connection-text').textContent=value?'本地服务已连接':'连接中断 · 正在重试';document.body.classList.toggle('disconnected',!value);}
async function poll(){
  const version=requestVersion;
  try{if(!commandPending){const next=await request('/api/state');if(version===requestVersion){state=next;setConnected(true);render();}}}
  catch(error){setConnected(false);$('error-banner').hidden=false;$('error-banner').textContent='无法连接服务。请确认 python server.py 仍在运行；当前画面为最后一次成功读取的状态。';}
  finally{setTimeout(poll,250);}
}
function render(){
  if(!state)return;
  const s=state,v=s.vehicle;
  $('error-banner').hidden=!s.engine_error;
  if(s.engine_error)$('error-banner').textContent='仿真已暂停：'+s.engine_error;
  $('speed').textContent=number(v.speed);$('acceleration').textContent=`加速度 ${number(v.acceleration)} m/s²`;
  $('distance').textContent=s.route_available?number(s.route.distance,0):'—';$('eta').textContent=`预计路段通行时间 ${s.route_available?number(s.route.eta):'—'} s`;
  $('gap').textContent=number(v.gap);$('ttc').textContent=s.sensor.stale?'测距数据已过期':v.ttc!==null?`恒速假设 TTC ${number(v.ttc)} s`:'当前无接近中的前车';
  $('status').textContent=names[s.status]||s.status;$('sim-time').textContent=`仿真时间 ${number(s.time)} s`;
  $('toggle-run').textContent=s.running?'Ⅱ 暂停仿真':s.completed?'✓ 行程完成':'▶ 开始仿真';$('toggle-run').disabled=s.completed||s.metrics.collision;
  $('scenario-name').textContent=s.scenario_name;
  document.querySelectorAll('[data-scenario]').forEach(el=>el.classList.toggle('selected',el.dataset.scenario===s.scenario));
  document.querySelectorAll('[data-speed]').forEach(el=>el.classList.toggle('selected',Number(el.dataset.speed)===s.multiplier));
  $('gps-value').textContent=`x ${number(v.x)} · y ${number(v.y)} m`;$('speed-value').textContent=`${number(v.speed)} km/h`;
  $('sensor-age').textContent=`观测年龄 ${number(s.sensor.age)} s${s.sensor.stale?' · 已过期':''}`;
  $('sensor-toggle').textContent=s.sensor.online?'断开':'恢复';$('sensor-count').textContent=s.sensor.online?'3 / 3':'2 / 3';
  $('decision-title').textContent=names[s.status]||s.status;$('decision-reason').textContent=s.reason;
  $('max-decel').textContent=number(s.metrics.max_decel);$('collision').textContent=s.metrics.collision?'1':'0';
  if(!$('road-rows').children.length){
    $('road-rows').innerHTML=s.edges.map(e=>`<tr data-edge="${esc(e.id)}"><td>${esc(e.name)} <small>${esc(e.id)}</small></td><td>${number(e.length,0)} m</td><td class="road-speed"></td><td class="road-status"></td><td><button class="text-button" data-road="${e.id}" data-operation="congestion">拥堵</button><button class="text-button" data-road="${e.id}" data-operation="close">封闭</button><button class="text-button" data-road="${e.id}" data-operation="restore">恢复</button></td></tr>`).join('');
  }
  s.edges.forEach(e=>{const row=document.querySelector(`tr[data-edge="${e.id}"]`);row.querySelector('.road-speed').textContent=e.closed?'—':`${number(e.limit/e.congestion*3.6)} km/h`;const cell=row.querySelector('.road-status');cell.textContent=e.closed?'● 封闭':e.congestion>1?'● 拥堵':'● 畅通';cell.style.color=e.closed?'#da6c79':e.congestion>1?'#d6a24b':'#40ac98';});
  renderRoutes();renderBehavior();renderEvents();drawChart();drawMap();
}
function renderRoutes(){
  const signature=JSON.stringify([state.candidates,state.profile]);if(signature===routeSignature)return;routeSignature=signature;
  $('route-cards').innerHTML=Object.entries(profiles).map(([key,name],i)=>{const r=state.candidates[i];return `<article class="route-card ${key===state.profile?'selected':''}"><span class="badge">0${i+1} / DIJKSTRA</span><h2>${name}</h2><strong>${r?number(r.eta):'—'}<small>秒 / 预计通行</small></strong><p>${r?`${number(r.distance,0)} m · 综合代价 ${r.score}`:'当前无可行路线'}</p><div class="route-path">${r?r.edges.map(id=>esc(state.edges.find(e=>e.id===id).name)).join(' → '):'请恢复至少一条起终点间的通路。'}</div><p>${key==='balanced'?'权重：时间 0.20 / 距离 0.70 / 舒适 0.10':key==='fast'?'权重：时间 0.90 / 距离 0.05 / 舒适 0.05':'权重：时间 0.05 / 距离 0.05 / 舒适 0.90'}</p><button class="button ${key===state.profile?'primary':'ghost'}" data-profile="${key}">${key===state.profile?'✓ 当前偏好':'应用此偏好'}</button></article>`;}).join('');
}
function renderBehavior(){const b=state.behavior;$('behavior-select').value=b.style;$('behavior-metrics').innerHTML=[[b.samples,'样本数'],[b.rapid_accel,'急加速采样点'],[b.hard_brake,'急刹车采样点'],[(b.short_gap_ratio*100).toFixed(1)+'%','短时距采样比例']].map(([v,k])=>`<div><b>${esc(v)}</b><small>${k}</small></div>`).join('');$('behavior-result').textContent=`${b.label} · 规则评分 ${b.score} / 100`;$('behavior-rule').textContent=b.rule;}
function renderEvents(){$('run-id').textContent=state.run_id;$('event-list').innerHTML=state.events.map(e=>`<div class="event"><div><b>${esc(names[e.title]||e.title)}</b><small>${number(e.time)} s · ${esc(e.kind)}</small></div><p>${esc(e.detail)}</p></div>`).join('');}
async function loadRuns(){try{const runs=await request('/api/runs');$('run-list').innerHTML=runs.map(r=>`<div class="run-item"><b>${esc(scenarioNames[r.scenario]||r.scenario)}</b><p>${esc(profiles[r.profile])} · ${number(r.elapsed)} s · ${esc(names[r.status]||r.status)}</p><code>${esc(r.id)} / ${esc(r.created_at)} UTC</code></div>`).join('')||'<p>暂无记录</p>';}catch(e){toast(e.message);}}
function drawChart(){const h=state.history;const max=Math.max(60,...h.map(p=>p.speed));let grid='';for(let i=0;i<4;i++){const y=15+i*36;grid+=`<line x1="30" y1="${y}" x2="428" y2="${y}" stroke="#eef2f7"/><text x="2" y="${y+3}" fill="#a1afbf" font-size="9">${Math.round(max*(1-i/3))}</text>`;}const points=h.map((p,i)=>`${30+i/Math.max(h.length-1,1)*398},${123-p.speed/max*108}`).join(' ');$('speed-chart').innerHTML=`<defs><linearGradient id="chartfill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#6da8ed" stop-opacity=".2"/><stop offset="1" stop-color="#6da8ed" stop-opacity="0"/></linearGradient></defs>${grid}${h.length?`<polygon points="30,123 ${points} 428,123" fill="url(#chartfill)"/><polyline points="${points}" fill="none" stroke="#5594df" stroke-width="2"/>`:''}<text x="30" y="145" fill="#a1afbf" font-size="9">${h.length?number(h[0].time):'0'} s</text><text x="390" y="145" fill="#a1afbf" font-size="9">${number(state.time)} s</text>`;}
function drawMap(){
  if(!state||tab!=='overview')return;
  const canvas=$('road-map'),rect=canvas.getBoundingClientRect();if(!rect.width)return;
  const dpr=window.devicePixelRatio||1;canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.fillStyle='#172c40';ctx.fillRect(0,0,rect.width,rect.height);
  const scale=Math.min(rect.width/920,rect.height/530),ox=(rect.width-920*scale)/2,oy=(rect.height-530*scale)/2;
  ctx.translate(ox,oy);ctx.scale(scale,scale);
  ctx.strokeStyle='#233b50';ctx.lineWidth=.6;for(let x=0;x<940;x+=30){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,530);ctx.stroke();}for(let y=0;y<540;y+=30){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(920,y);ctx.stroke();}
  // Decorative urban blocks: not vehicles or live traffic measurements.
  [[335,130,70,65],[425,135,65,50],[520,130,65,68],[335,320,105,55],[475,330,110,55],[120,135,85,52],[705,355,90,65]].forEach(([x,y,w,h],i)=>{ctx.fillStyle=i>2?'#203d47':'#243d52';ctx.fillRect(x,y,w,h);ctx.strokeStyle='#2b4859';ctx.strokeRect(x+5,y+5,w-10,h-10);});
  ctx.font='11px "Microsoft YaHei",sans-serif';ctx.fillStyle='#486776';ctx.fillText('CAMPUS DISTRICT',102,118);ctx.fillText('GREEN PARK',389,364);ctx.fillText('TECHNOLOGY PARK',689,450);
  const selected=new Set(state.route?state.route.edges:[]);
  state.edges.forEach(e=>{const a=state.nodes[e.source],b=state.nodes[e.target];ctx.lineCap='round';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.lineWidth=31;ctx.strokeStyle='#405469';ctx.stroke();ctx.lineWidth=27;ctx.strokeStyle='#293f54';ctx.stroke();ctx.setLineDash([7,8]);ctx.lineWidth=1;ctx.strokeStyle='#617184';ctx.stroke();ctx.setLineDash([]);
    if(selected.has(e.id)||e.closed||e.congestion>1){ctx.lineWidth=5;ctx.strokeStyle=e.closed?'#ec7780':e.congestion>1?'#edb057':'#40cdd0';ctx.globalAlpha=e.closed?1:.83;ctx.stroke();ctx.globalAlpha=1;}
    ctx.fillStyle=e.closed?'#ed8a90':e.congestion>1?'#e8bc77':'#8da6bb';ctx.textAlign='center';ctx.font='11px "Microsoft YaHei",sans-serif';const mx=(a.x+b.x)/2,my=(a.y+b.y)/2;ctx.fillText(e.name,mx+(a.x===b.x?(a.x<460?-47:47):0),my+(a.y===b.y?-25:4));
    if(e.closed){ctx.fillStyle='#ed777e';ctx.fillRect(mx-8,my-8,16,16);ctx.fillStyle='#fff';ctx.fillRect(mx-5,my-1,10,2);}
  });
  Object.entries(state.nodes).forEach(([id,n])=>{ctx.beginPath();ctx.arc(n.x,n.y,6,0,Math.PI*2);ctx.fillStyle=id==='A'?'#42d3c2':id==='D'?'#8ba9fc':'#71879c';ctx.fill();if(id==='A'||id==='D'){ctx.fillStyle='#c8dceb';ctx.font='12px "Microsoft YaHei",sans-serif';ctx.textAlign='center';ctx.fillText(n.name,n.x,n.y+39);}else{ctx.fillStyle='#728a9f';ctx.font='9px sans-serif';ctx.fillText(id,n.x-18,n.y-18);}});
  function car(x,y,angle,color,lane,label){ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.translate(0,lane===undefined?0:-8+16*lane);ctx.shadowColor=color;ctx.shadowBlur=label==='EGO'?12:0;ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(-13,-6,26,12,3);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#1e3850';ctx.fillRect(1,-4,5,8);ctx.fillRect(-9,-4,4,8);ctx.restore();if(label){ctx.font='bold 9px sans-serif';ctx.textAlign='center';ctx.fillStyle=color;ctx.fillText(label,x,y-23);}}
  if(state.obstacle){const o=state.obstacle,e=state.edges.find(e=>e.id===o.edge),a=state.nodes[e.source],b=state.nodes[e.target],r=o.position/e.length;car(a.x+(b.x-a.x)*r,a.y+(b.y-a.y)*r,Math.atan2(b.y-a.y,b.x-a.x),'#ef8b83',o.lane,'STOP');}
  const v=state.vehicle;
  if(state.side_blocked&&state.obstacle&&v.edge===state.obstacle.edge){car(v.x+8,v.y,v.angle,'#8294b0',1,'');car(v.x-22,v.y,v.angle,'#8294b0',1,'');}
  car(v.x,v.y,v.angle,'#67efdc',v.lane+v.lane_progress,'EGO');
}
const tabText={overview:['驾驶总览','每一次决策，都看得见。','监测道路变化，理解驾驶偏好，在可重复的场景中验证响应。'],routes:['路径推荐','让路线，适合你的偏好。','同一张路网，不同目标；比较距离、时间与舒适性的取舍。'],behavior:['用户行为','从驾驶记录，理解行为。','用可解释规则分析模拟样本，不把自动控制日志当作用户习惯。'],records:['实验记录','每一次实验，都有记录。','追踪场景、输入事件与决策原因，支撑测试与课程答辩。']};
document.querySelectorAll('[data-tab]').forEach(el=>el.addEventListener('click',()=>{tab=el.dataset.tab;document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n===el));document.querySelectorAll('.tab').forEach(n=>n.classList.toggle('active',n.id==='tab-'+tab));const [title,headline,subtitle]=tabText[tab];$('page-title').textContent=title;$('headline').textContent=headline;$('subtitle').textContent=subtitle;if(tab==='records')loadRuns();drawMap();}));
$('toggle-run').addEventListener('click',()=>{if(state)action({action:state.running?'pause':'start'});});
$('reset').addEventListener('click',()=>action({action:'reset',scenario:state?.scenario||'normal'}));
$('sensor-toggle').addEventListener('click',()=>{if(state)action({action:'sensor',online:!state.sensor.online});});
$('behavior-select').addEventListener('change',e=>action({action:'behavior',style:e.target.value}));
$('refresh-runs').addEventListener('click',loadRuns);
document.addEventListener('click',e=>{const s=e.target.closest('[data-scenario]'),p=e.target.closest('[data-profile]'),r=e.target.closest('[data-road]'),speed=e.target.closest('[data-speed]');if(s)action({action:'scenario',scenario:s.dataset.scenario});if(p)action({action:'profile',profile:p.dataset.profile});if(r)action({action:'road',edge:r.dataset.road,operation:r.dataset.operation});if(speed)action({action:'speed',multiplier:Number(speed.dataset.speed)});});
window.addEventListener('resize',drawMap);
poll();
