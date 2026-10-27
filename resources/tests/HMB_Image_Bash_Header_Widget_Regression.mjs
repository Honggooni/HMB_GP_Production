// Product widget in offline Chromium. Host callbacks/routes are synthetic;
// this never opens or changes the running Griptape application/workflow.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import {nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';
import * as widget from '../../widgets/HMBImageBashWidget.js';

const schema=widget.HMB_IMAGE_BASH_HEADER_SCHEMA;
const route={connected:true,source_node_name:'Library A',target_node_name:'BashNode',
 source_parameter:'IMAGE_BASH_IMAGES_OUT',context_source_parameter:'IMAGE_BASH_CONTEXT_OUT'};
const state={schema,sources:[{id:'Library A',label:'A <img id="injected" src=x onerror="window.injection=true">',workspace_id:'workspace-a'},
 {id:'Library B',label:'B & "별도 라이브러리"',workspace_id:'workspace-b'}],bound_source:'Library A',image_count:2,
 status:'Apply 필요 <script>bad()</script>',locked:false,route,extra_backend_field:{keep:[0,false,'']}};
assert.equal(widget.hmbImageBashHeaderState().locked,false,'Refresh remains available before the first source projection');
assert.equal(widget.hmbImageBashHeaderState({value:JSON.stringify(state)}).image_count,2);
assert.equal(widget.hmbImageBashHeaderState({...state,image_count:-4}).image_count,0);
assert.equal(widget.hmbImageBashHeaderState({...state,sources:[...state.sources,state.sources[0],{id:'bad',workspace_id:''}]}).sources.length,2);
assert.match(widget.hmbRenderImageBashHeader(state),/HMBImageBash/);
assert.doesNotMatch(widget.hmbRenderImageBashHeader(state),/<span[^>]*__remote|<button[^>]*data-bash-refresh/);
assert.match(widget.hmbRenderImageBashHeader(state),/A &lt;img/);
assert.doesNotMatch(widget.hmbRenderImageBashHeader(state),/<script>|<img/);
const element=(id,label)=>({getAttribute:name=>({'data-id':id,'aria-label':label}[name]??null)});
const imageId='Library A-IMAGE_BASH_IMAGES_OUT-BashNode-input_images-native-uuid';
const contextId='Library A-IMAGE_BASH_CONTEXT_OUT-BashNode-image_bash_context-native-uuid';
assert.equal(widget.hmbImageBashEdgeMatches(element(imageId,'Edge from Library A to BashNode'),route),true);
assert.equal(widget.hmbImageBashEdgeMatches(element(imageId,'Edge from Another to BashNode'),route),false);
assert.equal(widget.hmbImageBashEdgeMatches(element(imageId.replace('-input_images-','-input_images_0-'),'Edge from Library A to BashNode'),route),false);
assert.equal(widget.hmbImageBashEdgeMatches(element(contextId,'Edge from Library A to BashNode'),route,'context'),true);
assert.equal(widget.hmbImageBashEdgeMatches(element(contextId,'Edge from Library A to BashNode'),{...route,connected:false},'context'),false);
assert.equal(widget.hmbImageBashHeaderRoute({...route,source_parameter:'Other'}).connected,false);

const playwright=nativeTestPlaywright();
const widgetSource=fs.readFileSync(new URL('../../widgets/HMBImageBashWidget.js',import.meta.url),'utf8');
const encodedState=JSON.stringify(state).replaceAll('<','\\u003c');
const html=`<!doctype html><meta charset="utf-8"><title>Offline HMB Image Bash header fixture</title>
<style>body{background:#101420;color:white}.react-flow__node{width:900px;min-height:210px}.react-flow__handle{background:rgb(100,100,100);border:1px solid rgb(90,90,90)}.react-flow__edge-path{stroke:rgb(22,33,44)}.react-flow__edge{display:inline}</style>
<div id="flow"><svg class="react-flow__edges" width="900" height="120">
<g class="react-flow__edge" id="image-edge" data-hmb-image-bash-image-edge="previous" data-id="${imageId}" aria-label="Edge from Library A to BashNode"><path class="react-flow__edge-path" d="M0 20L500 20"/></g>
<g class="react-flow__edge" id="context-edge" data-id="${contextId}" aria-label="Edge from Library A to BashNode"><path class="react-flow__edge-path" d="M0 30L500 30"/></g>
<g class="react-flow__edge" id="wrong-label" data-id="${imageId}-other" aria-label="Edge from Foreign to BashNode"><path class="react-flow__edge-path" d="M0 40L500 40"/></g>
<g class="react-flow__edge" id="wrong-handle" data-id="Library A-IMAGE_BASH_IMAGES_OUT-BashNode-input_images_0-uuid" aria-label="Edge from Library A to BashNode"><path class="react-flow__edge-path" d="M0 50L500 50"/></g>
<g class="react-flow__edge" id="foreign-edge" data-id="Library A-OTHER-BashNode-other-uuid" aria-label="Edge from Library A to BashNode"><path class="react-flow__edge-path" d="M0 60L500 60"/></g>
</svg><div class="react-flow__nodes"><div class="react-flow__node" data-id="BashNode" data-hmb-image-bash="prior" id="node" style="width:900px;min-height:210px">
<header id="native-header"><button id="native-run">Native Run</button></header>
<span class="react-flow__handle" data-handleid="input_images" id="parent-handle"></span><span class="react-flow__handle" data-handleid="input_images_0" id="child-handle"></span><span class="react-flow__handle" data-handleid="image_bash_context" id="context-handle"></span>
<div id="widget" style="height:77px;min-height:33px;color:rgb(8,9,10)"></div><div id="second-widget"></div><button id="stock-editor-button">Open Image Bash Editor</button></div>
<div class="react-flow__node" data-id="OtherNode"><span class="react-flow__handle" data-handleid="input_images" id="foreign-handle"></span></div></div></div>
<script type="module">
import mount from '/widget.js';window.mount=mount;window.current=${encodedState};window.writes=[];window.autoEcho=true;window.mode='normal';window.token='initial';
window.props=(value=window.current,token=window.token,disabled=false)=>({value,disabled,onChange:payload=>{
 window.writes.push({token,payload:structuredClone(payload)});
 if(window.mode==='throw')throw new Error('offline callback rejection');
 if(window.mode==='pending')return new Promise((resolve,reject)=>{window.pendingReject=reject;});
 if(window.autoEcho){const command=payload.hmb_image_bash_command;const next=structuredClone(payload);delete next.hmb_image_bash_command;
  if(command.operation==='bind')next.bound_source=command.source_node_name;if(command.operation==='unbind')next.bound_source='';
  next.route={...next.route,connected:Boolean(next.bound_source),source_node_name:next.bound_source};next.status='backend accepted';window.render(next,token,disabled);}
}});
window.render=(value=window.current,token=window.token,disabled=false)=>{window.current=structuredClone(value);window.token=token;window.controller=mount(document.getElementById('widget'),window.props(value,token,disabled));};
window.render();window.initialSelect=document.querySelector('[data-bash-source]');window.initialHandle=window.controller;window.ready=true;
</script>`;
const server=http.createServer((request,response)=>{
 response.setHeader('Content-Type',request.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');
 response.end(request.url==='/widget.js'?widgetSource:html);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
 browser=await playwright.chromium.launch({executablePath:process.env.HMB_IMAGE_BASH_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1000,height:700}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(7000);
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
 await page.waitForFunction(()=>window.writes.length===1);
 assert.equal((await page.evaluate(()=>window.writes))[0].payload.hmb_image_bash_command.operation,'refresh','Visible first mount requests a post-hydration projection once');
 await page.waitForTimeout(35);
 assert.equal(await page.evaluate(()=>window.writes.length),1,'Synchronous refresh echoes must not cause a refresh loop');
 const select=page.locator('[data-bash-source]');
 const requestRefresh=async()=>{await select.dispatchEvent('pointerdown');await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));};
 assert.equal(await page.locator('[data-bash-refresh]').count(),0);
 assert.equal(await page.locator('.hmb-image-bash-header__remote').count(),0);
 const stroke=id=>page.locator('#'+id+' path').evaluate(node=>getComputedStyle(node).stroke);
 assert.equal(await page.locator('#injected').count(),0);assert.equal(await page.evaluate(()=>Boolean(window.injection)),false);
 assert.equal(await select.locator('option').count(),3);
 assert.equal(await select.inputValue(),'Library A');
 await select.evaluate(element=>{
  window.nativeSelectWrites={value:0,disabled:0};
  for(const key of ['value','disabled']){
   const original=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,key);
   Object.defineProperty(element,key,{configurable:true,get(){return original.get.call(this);},set(value){window.nativeSelectWrites[key]++;original.set.call(this,value);}});
  }
 });
 await select.click();
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 assert.deepEqual(await page.evaluate(()=>window.nativeSelectWrites),{value:0,disabled:0},'An unchanged background catalog echo never rewrites the native selection or disabled property');
 if(await page.evaluate(()=>CSS.supports('selector(:open)')))assert.equal(await select.evaluate(element=>element.matches(':open')),true,'Native popup stays open across an unchanged background catalog echo');
 await page.keyboard.press('Escape');
 const portal=await page.evaluate(()=>{
  const carrier=document.getElementById('widget'),identity=carrier.querySelector('[data-hmb-native-identity]'),actions=carrier.querySelector('[data-hmb-native-actions]');
  identity.append(Object.assign(document.createElement('input'),{value:'Native title'}));
  actions.append(Object.assign(document.createElement('button'),{textContent:'Native unlock'}));
  window.nativeSlots=[identity,actions];
  carrier.dispatchEvent(new CustomEvent('hmb-color-lut-header-state',{detail:{active:true}}));
  return {active:carrier.querySelector('[data-hmb-image-bash-header]').getAttribute('data-hmb-native-header'),
   draggable:!carrier.classList.contains('nodrag'),actionsVisible:getComputedStyle(actions).display};
 });
 assert.deepEqual(portal,{active:'active',draggable:true,actionsVisible:'flex'});
 assert.equal(await page.locator('[data-bash-count]').textContent(),'이미지 2');
 assert.equal(await page.locator('[data-hmb-image-bash-header]').evaluate(node=>node.getBoundingClientRect().height),64);
 assert.equal(await page.locator('#widget').evaluate(node=>node.getBoundingClientRect().height),64);
 assert.equal(await page.locator('#parent-handle').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(239, 68, 68)');
 for(const id of ['child-handle','context-handle','foreign-handle'])assert.equal(await page.locator('#'+id).evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(100, 100, 100)');
 assert.equal(await stroke('image-edge'),'rgb(239, 68, 68)');
 assert.equal(await page.locator('#context-edge').evaluate(node=>getComputedStyle(node).display),'none');
 for(const id of ['wrong-label','wrong-handle','foreign-edge'])assert.equal(await stroke(id),'rgb(22, 33, 44)');
 assert.equal(await page.locator('#native-header').isVisible(),true);assert.equal(await page.locator('#stock-editor-button').isVisible(),true);
 assert.equal(await page.locator('#node').getAttribute('style'),'width:900px;min-height:210px');
 const autoRefresh=await page.evaluate(async()=>{
  const pause=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const create=(id,visibility='visible')=>{const carrier=document.createElement('div');carrier.id=id;carrier.style.visibility=visibility;document.getElementById('node').append(carrier);return carrier;};
  const results={hidden:[],late:[],cancelled:[],disabled:[],rejected:[]};
  const initial=structuredClone(window.current);
  const hidden=create('hidden-measurement','hidden');
  const hiddenHandle=window.mount(hidden,{value:initial,onChange:value=>results.hidden.push(value)});
  await pause();hiddenHandle.update({value:initial,onChange:value=>results.hidden.push(value)});await pause();
  hiddenHandle.cleanup();hidden.remove();
  const late=create('late-callback');const lateHandle=window.mount(late,{value:initial});await pause();
  lateHandle.update({value:initial,onChange:value=>results.late.push(value)});await pause();
  for(let index=0;index<6;index++)lateHandle.update({value:initial,onChange:value=>results.late.push(value)});
  await pause();lateHandle.cleanup();late.remove();
  const cancelled=create('cancelled-mount');const cancelledHandle=window.mount(cancelled,{value:initial,onChange:value=>results.cancelled.push(value)});
  cancelledHandle.cleanup();cancelled.remove();await pause();
  const disabled=create('disabled-mount');const disabledHandle=window.mount(disabled,{value:initial,disabled:true,onChange:value=>results.disabled.push(value)});
  await pause();disabledHandle.update({value:initial,disabled:false,onChange:value=>results.disabled.push(value)});await pause();
  disabledHandle.cleanup();disabled.remove();
  const rejected=create('rejected-mount');const rejectionProps={value:initial,onChange:value=>{results.rejected.push(value);return Promise.reject(new Error('initial refresh rejected'));}};
  const rejectedHandle=window.mount(rejected,rejectionProps);await pause();
  for(let index=0;index<6;index++)rejectedHandle.update(rejectionProps);
  await pause();rejectedHandle.cleanup();rejected.remove();
  return results;
 });
 assert.equal(autoRefresh.hidden.length,0,'Hidden measurement copies never request refresh');
 assert.equal(autoRefresh.cancelled.length,0,'Cleanup cancels the scheduled initial refresh');
 assert.equal(autoRefresh.late.length,1,'A callback delivered by update triggers only one initial refresh');
 assert.equal(autoRefresh.disabled.length,1,'Native disabled state defers initial refresh until enabled');
 assert.equal(autoRefresh.rejected.length,1,'A rejected initial refresh must not retry on every host update');
 for(const commands of Object.values(autoRefresh))assert.ok(commands.every(value=>value.hmb_image_bash_command.operation==='refresh'),'Initial mount never binds or runs');
 await page.evaluate(()=>{window.autoEcho=false;window.render({});});
 assert.equal(await select.isDisabled(),false);assert.equal(await select.locator('option').count(),1);
 await requestRefresh();assert.equal((await page.evaluate(()=>window.writes)).at(-1).payload.schema,schema);
 await page.evaluate(state=>{window.autoEcho=true;window.render(state);},state);

 await select.selectOption('Library B');
 let writes=await page.evaluate(()=>window.writes);
 assert.equal(writes.at(-1).payload.hmb_image_bash_command.operation,'bind');
 assert.equal(writes.at(-1).payload.hmb_image_bash_command.source_node_name,'Library B');
 assert.equal(writes.at(-1).payload.hmb_image_bash_command.workspace_id,'workspace-b');
 assert.deepEqual(writes.at(-1).payload.extra_backend_field,{keep:[0,false,'']});
 assert.equal(writes.at(-1).payload.route.source_node_name,'Library A','Commands preserve the latest authoritative route until backend acknowledgement');
 assert.equal(await select.inputValue(),'Library B');
 await select.selectOption('');
 writes=await page.evaluate(()=>window.writes);
 assert.equal(writes.at(-1).payload.hmb_image_bash_command.operation,'unbind');
 assert.equal(writes.at(-1).payload.hmb_image_bash_command.source_node_name,'');
 assert.equal(writes.at(-1).payload.hmb_image_bash_command.workspace_id,'workspace-b');
 await requestRefresh();assert.equal((await page.evaluate(()=>window.writes)).at(-1).payload.hmb_image_bash_command.operation,'refresh');

 await page.evaluate(()=>{for(let index=0;index<30;index++)window.render(window.current,'latest');});
 assert.equal(await page.evaluate(()=>window.initialSelect===document.querySelector('[data-bash-source]')&&window.initialHandle===window.controller),true);
 assert.equal(await page.evaluate(()=>window.nativeSlots.every(slot=>slot.isConnected)&&window.nativeSlots[0].querySelector('input').value==='Native title'&&window.nativeSlots[1].textContent==='Native unlock'),true,'Native React portal parents and children survive retained header updates');
 const before=await page.evaluate(()=>window.writes.length);
 await requestRefresh();await requestRefresh();
 assert.equal(await page.evaluate(()=>window.writes.length),before+2,'Repeated factory updates must not multiply event handlers');
 writes=await page.evaluate(()=>window.writes);
 assert.deepEqual(writes.slice(-2).map(row=>row.token),['latest','latest'],'The latest callback owns commands');
 assert.equal(new Set(writes.map(row=>row.payload.hmb_image_bash_command.request_id)).size,writes.length);

 await page.evaluate(()=>window.render({...window.current,locked:true}));
 assert.equal(await select.isDisabled(),true);
 assert.equal(await page.locator('[data-hmb-native-actions] button').isEnabled(),true,'Body lock does not disable the native unlock control');
 const lockedCount=await page.evaluate(()=>window.writes.length);
 await page.evaluate(()=>{document.querySelector('[data-bash-source]').dispatchEvent(new Event('change'));document.querySelector('[data-bash-source]').dispatchEvent(new Event('pointerdown'));});
 assert.equal(await page.evaluate(()=>window.writes.length),lockedCount);
 await page.evaluate(()=>window.render({...window.current,locked:false},'native-disabled',true));
 assert.equal(await select.isDisabled(),true);

 await page.evaluate(()=>{window.render({...window.current,locked:false});window.mode='throw';});
 await requestRefresh();assert.match(await page.locator('[data-bash-status]').textContent(),/offline callback rejection/);
 await page.evaluate(()=>{window.mode='pending';window.autoEcho=false;window.render({...window.current,status:'ready'});});
 await requestRefresh();assert.equal(await select.isDisabled(),false,'Background catalog refresh never disables the native popup');
 const pendingCount=await page.evaluate(()=>window.writes.length);await requestRefresh();
 assert.equal(await page.evaluate(()=>window.writes.length),pendingCount,'In-flight background refresh is coalesced');
 await page.evaluate(()=>{window.render({...window.current,status:'new authoritative state'});window.pendingReject(new Error('stale rejection'));window.mode='normal';});
 await page.waitForTimeout(30);
 assert.equal(await page.locator('[data-bash-status]').textContent(),'new authoritative state');

 // Exact route markers track native SVG replacement and in-place endpoint
 // updates. Foreign edges with similar IDs or the wrong label stay untouched.
 await page.evaluate(route=>window.render({...window.current,bound_source:'Library A',route}),route);
 await page.evaluate(imageId=>{const edge=document.getElementById('image-edge').cloneNode(true);edge.id='late-image';edge.setAttribute('data-id',imageId+'-late');edge.removeAttribute('data-hmb-image-bash-image-edge');document.querySelector('.react-flow__edges').append(edge);},imageId);
 await page.waitForFunction(()=>document.getElementById('late-image').getAttribute('data-hmb-image-bash-image-edge')==='true');
 assert.equal(await stroke('late-image'),'rgb(239, 68, 68)');
 await page.locator('#late-image').evaluate(node=>node.setAttribute('aria-label','Edge from Wrong to BashNode'));
 await page.waitForFunction(()=>!document.getElementById('late-image').hasAttribute('data-hmb-image-bash-image-edge'));
 assert.equal(await stroke('late-image'),'rgb(22, 33, 44)');
 await page.evaluate(()=>window.render({...window.current,route:{...window.current.route,connected:false}}));
 assert.equal(await page.locator('#context-edge').evaluate(node=>getComputedStyle(node).display),'inline');
 assert.equal(await page.locator('#image-edge').getAttribute('data-hmb-image-bash-image-edge'),'previous');
 assert.equal(await stroke('image-edge'),'rgb(22, 33, 44)');

 // Two native carriers share scope/edge ownership. Retiring one must not
 // remove the still-mounted carrier's colors or hide native controls.
 await page.evaluate(route=>{window.render({...window.current,route});window.second=window.mount(document.getElementById('second-widget'),window.props());window.controller.cleanup();},route);
 assert.equal(await page.locator('#node').getAttribute('data-hmb-image-bash'),'true');
 assert.equal(await stroke('image-edge'),'rgb(239, 68, 68)');
 assert.equal(await page.locator('#context-edge').evaluate(node=>getComputedStyle(node).display),'none');
 await page.evaluate(()=>window.second.cleanup());
 assert.equal(await page.locator('#node').getAttribute('data-hmb-image-bash'),'prior');
 assert.equal(await page.locator('#image-edge').getAttribute('data-hmb-image-bash-image-edge'),'previous');
 assert.equal(await page.locator('#context-edge').getAttribute('data-hmb-image-bash-context-edge'),null);
 assert.equal(await page.locator('#widget').evaluate(node=>node.style.height),'77px');
 assert.equal(await page.locator('#widget').evaluate(node=>node.style.minHeight),'33px');
 assert.equal(await page.locator('#widget').evaluate(node=>node.style.color),'rgb(8, 9, 10)');
 assert.equal(await page.locator('#widget').evaluate(node=>node.style.maxHeight),'');
 assert.equal(await page.locator('#widget').evaluate(node=>node.classList.contains('nodrag')),false);
 assert.equal(await page.locator('[data-hmb-image-bash-header]').count(),0);
 assert.equal(await page.locator('#native-run').isVisible(),true);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:'PASS',scope:'offline Chromium product widget',persistent_64px_header:true,
  bind_unbind_refresh:true,latest_callback_unique_commands:true,locked_guard:true,escaping:true,
  exact_route_edges_only:true,mutation_reconcile:true,shared_carrier_cleanup:true,
  one_visible_post_hydration_refresh:true,measurement_no_commands:true,live_griptape_verified:false}));
} finally {
 await browser?.close();await new Promise(resolve=>server.close(resolve));
}
