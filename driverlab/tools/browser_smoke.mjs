// Optional browser QA: Node 22+, an isolated Chromium instance on port 9223,
// and the DriverLab server on port 8000. No third-party packages needed.
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const output=fileURLToPath(new URL('../artifacts/',import.meta.url));
await mkdir(output,{recursive:true});
const targets=await (await fetch('http://127.0.0.1:9223/json/list')).json();
const target=targets.find(t=>t.type==='page');
if(!target)throw Error('No isolated browser page found on port 9223');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let sequence=0;const pending=new Map(),errors=[],checks=[];
socket.addEventListener('message',e=>{const data=JSON.parse(e.data);if(data.id){const waiter=pending.get(data.id);if(waiter){clearTimeout(waiter.timeout);pending.delete(data.id);data.error?waiter.reject(Error(JSON.stringify(data.error))):waiter.resolve(data.result);}}else if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails);});
function send(method,params={}){const id=++sequence;return new Promise((resolve,reject)=>{const timeout=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},10000);pending.set(id,{resolve,reject,timeout});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(expression,timeout=12000){const started=Date.now();while(Date.now()-started<timeout){if(await evaluate(expression))return;await delay(150);}throw Error('Condition not reached: '+expression);}
async function click(selector){await until('!commandPending');await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);await until('!commandPending');await delay(300);}
async function check(label,expression){const success=await evaluate(expression);checks.push({label,success});if(!success)throw Error(label+' failed');}
async function screenshot(name){const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});await writeFile(output+name,Buffer.from(result.data,'base64'));}
try{
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'http://127.0.0.1:8000'});
  await until('typeof state !== "undefined" && state !== null');
  await check('Dashboard connected',`document.getElementById('connection-text').textContent==='本地服务已连接'`);
  await evaluate(`action({action:'reset',scenario:'normal',profile:'balanced'})`);await until('!commandPending');
  await click('[data-scenario="normal"]');await click('[data-speed="4"]');await delay(1000);await click('#toggle-run');
  await check('Pause works','state.running === false && state.time > 0');
  await screenshot('dashboard-desktop.png');
  await click('[data-tab="routes"]');
  await check('Three route alternatives',`document.querySelectorAll('.route-card').length===3`);
  await click('[data-profile="comfort"]');await check('Comfort preference applied',`state.profile==='comfort' && state.route.edges.includes('GH')`);
  await screenshot('routes-desktop.png');
  await click('[data-tab="behavior"]');
  await evaluate(`document.getElementById('behavior-select').value='active';document.getElementById('behavior-select').dispatchEvent(new Event('change'))`);
  await until(`state.behavior.style==='active' && !commandPending`);
  await check('Behavior samples analyzed','state.behavior.hard_brake>0');
  await click('[data-tab="overview"]');
  await evaluate(`action({action:'profile',profile:'balanced'})`);await until('!commandPending');
  await click('[data-scenario="congestion"]');
  await check('Congestion reroutes the distance-preferred journey',`!state.route.edges.includes('BC') && state.edges.find(e=>e.id==='BC').congestion===6`);
  await click('[data-scenario="closure"]');
  await check('Closed road excluded',`!state.route.edges.includes('BC') && state.edges.find(e=>e.id==='BC').closed`);
  await click('[data-scenario="brake"]');await until(`state.time>8`);
  await check('Brake scenario stops without collision',`state.vehicle.speed===0 && state.vehicle.lane===0 && !state.metrics.collision`);
  await screenshot('brake-desktop.png');
  await click('[data-scenario="avoid"]');await until('state.vehicle.lane===1');
  await check('Avoidance completes','!state.metrics.collision');
  await click('[data-scenario="sensor"]');await until('state.status==="DEGRADED" && state.vehicle.speed===0');
  await check('Sensor fault degrades safely','state.sensor.stale');
  await click('#sensor-toggle');await until('state.status==="CRUISE"');
  await click('[data-scenario="no_route"]');await check('No-route state explicit','state.status==="NO_ROUTE" && state.vehicle.speed===0');
  await click('[data-road="BC"][data-operation="restore"]');await until('state.vehicle.speed>0');
  await check('Road restoration resumes journey','state.route.edges.includes("BC")');
  await click('[data-tab="records"]');await until(`document.querySelectorAll('.run-item').length>0`);
  await check('Event log visible',`document.querySelectorAll('.event').length>0`);
  await click('[data-tab="overview"]');
  await click('[data-profile="balanced"]');
  // Reset to a clean, paused state before delivery.
  await evaluate(`action({action:'reset',scenario:'normal',profile:'balanced'})`);await until('!commandPending');
  await evaluate(`action({action:'speed',multiplier:1})`);await until('!commandPending');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await delay(500);
  await check('Mobile page has no horizontal document overflow','document.documentElement.scrollWidth<=window.innerWidth');
  await screenshot('dashboard-mobile.png');
  if(errors.length)throw Error('Browser exceptions: '+JSON.stringify(errors));
  await writeFile(output+'browser-checks.json',JSON.stringify({checks,errors},null,2));
  console.log(JSON.stringify({checks,errors,screenshots:output},null,2));
}finally{socket.close();}
