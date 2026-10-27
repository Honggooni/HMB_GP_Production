// Actual product widget in isolated Chromium; topology and host replies are
// synthetic. No running Griptape app, Engine, file, provider, or install changes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';

const require=createRequire(import.meta.url);
const {chromium}=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const source=fs.readFileSync(new URL('../../widgets/HMBImageBashWidget.js',import.meta.url),'utf8');
const html=`<!doctype html><meta charset=utf-8><style>body{background:#101420;color:white}.react-flow__node{width:800px;min-height:80px}#measurement{visibility:hidden}#opacity-parent{opacity:0}</style>
<div class=react-flow__nodes><div class=react-flow__node data-id="Library A"><div data-hmb-native-node-type=HMBImageAssetLibrary></div><section data-image-bash-panel=workspace-a></section></div>
<div class=react-flow__node data-id=Bash><div id=main></div><div id=measurement></div><div id=opacity-parent><div id=opacity-clone></div></div></div></div>
<script type=module>
import mount from '/widget.js';window.mount=mount;window.writes=[];window.handles=new Map();window.mode='normal';window.bound='';window.tokens=new Map([['Library A','instance-a']]);
window.dirty={layers:[{x:0,opacity:0,authored:'keep'}],apply:{png:'retained'},future:{zero:0,off:false,literal:''}};
window.layer=document.querySelector('.react-flow__nodes');window.bash=window.layer.querySelector('[data-id="Bash"]');
window.projection=()=>({schema:'hmb-image-bash-header-v1',sources:[...window.layer.children].filter(n=>n.dataset.id!=='Bash'&&n.querySelector('[data-image-bash-panel]')).map(n=>({id:n.dataset.id,label:n.dataset.id,workspace_id:n.querySelector('[data-image-bash-panel]').getAttribute('data-image-bash-panel')})),source_instances:Object.fromEntries(window.tokens),bound_source:window.bound,image_count:2,status:'dirty retained',locked:false});
window.props=(id,value)=>({value,onChange:payload=>{window.writes.push({id,payload:structuredClone(payload)});const c=payload.hmb_image_bash_command;
 if(c.operation==='bind')window.bound=c.source_node_name;if(c.operation==='unbind')window.bound='';
 const captured=window.projection();
 if(window.mode==='pending')return new Promise(resolve=>{window.release=()=>{window.render(captured);resolve();};});
 window.render();}});
window.render=(value=window.projection())=>{for(const [id,h]of window.handles)h.update(window.props(id,value));};
window.addCarrier=id=>{let e=document.getElementById(id);if(!e){e=document.createElement('div');e.id=id;window.bash.append(e);}const h=mount(e,window.props(id,window.projection()));window.handles.set(id,h);return h;};
window.addSource=(name,workspace,token)=>{const n=document.createElement('div');n.className='react-flow__node';n.dataset.id=name;n.innerHTML='<div data-hmb-native-node-type=HMBImageAssetLibrary></div>'+(workspace?'<section data-image-bash-panel="'+workspace+'"></section>':'');window.tokens.set(name,token);window.layer.append(n);return n;};
window.pause=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
window.addCarrier('main');window.addCarrier('measurement');window.addCarrier('opacity-clone');window.ready=true;
</script>`;
const server=http.createServer((request,response)=>{response.setHeader('Content-Type',request.url==='/widget.js'?'text/javascript':'text/html');response.end(request.url==='/widget.js'?source:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.ready);await page.evaluate(()=>window.pause());
 assert.deepEqual(await page.evaluate(()=>window.writes.map(v=>[v.id,v.payload.hmb_image_bash_command.operation])),[['main','refresh']]);
 const dirty=await page.evaluate(()=>JSON.stringify(window.dirty));
 const count=()=>page.evaluate(()=>window.writes.length);
 const options=()=>page.locator('#main [data-bash-source] option').allTextContents();
 assert.deepEqual(await options(),['이미지 라이브러리 연결','Library A']);
 // A real native wrapper removal, without a focus/pointer event, must retire
 // the stale option through one metadata-only command.
 let before=await count();await page.evaluate(()=>window.layer.querySelector('[data-id="Library A"]').remove());await page.evaluate(()=>window.pause());
 assert.deepEqual(await options(),['이미지 라이브러리 연결']);assert.equal(await count(),before+1);
 assert.equal(await page.evaluate(()=>document.activeElement.tagName),'BODY');
 before=await count();await page.evaluate(()=>window.addSource('Library B','workspace-b','instance-b'));await page.evaluate(()=>window.pause());
 assert.deepEqual(await options(),['이미지 라이브러리 연결','Library B']);assert.equal(await count(),before+1);
 // A source wrapper can precede its workspace. Adding that membership later
 // must update the choices without creating a new node or selecting it.
 await page.evaluate(()=>window.addSource('Library C','','instance-c'));await page.evaluate(()=>window.pause());
 assert.deepEqual(await options(),['이미지 라이브러리 연결','Library B']);before=await count();
 await page.evaluate(()=>{const n=window.layer.querySelector('[data-id="Library C"]');const row=document.createElement('section');row.setAttribute('data-image-bash-panel','workspace-c');n.append(row);});await page.evaluate(()=>window.pause());
 assert.deepEqual(await options(),['이미지 라이브러리 연결','Library B','Library C']);assert.equal(await count(),before+1);
 before=await count();await page.evaluate(()=>{const n=window.layer.querySelector('[data-id="Library B"]');for(let i=0;i<100;i++){const card=document.createElement('i');n.append(card);card.remove();}n.dataset.id='Library B';});await page.evaluate(()=>window.pause());
 assert.equal(await count(),before,'Thumbnail/card and same-value mutations do not republish choices');
 // Replacing the wrapper with the same displayed name is still a new object.
 before=await count();await page.evaluate(()=>{window.layer.querySelector('[data-id="Library B"]').remove();window.addSource('Library B','workspace-b','instance-b-new');});await page.evaluate(()=>window.pause());
 assert.equal(await count(),before+1);await page.locator('#main [data-bash-source]').selectOption('Library B');
 assert.equal(await page.evaluate(()=>window.writes.at(-1).payload.hmb_image_bash_command.source_instance_id),'instance-b-new');
 await page.locator('#main [data-bash-source]').selectOption('');
 assert.equal(await page.evaluate(()=>window.writes.at(-1).payload.hmb_image_bash_command.operation),'unbind');
 assert.equal(await page.evaluate(()=>window.writes.at(-1).payload.hmb_image_bash_command.source_instance_id),'instance-b-new');
 assert.equal(await page.evaluate(()=>window.writes.at(-1).payload.hmb_image_bash_command.workspace_id),'workspace-b');
 // Coalesce while one metadata request is pending, but never lose the later
 // topology event when the old host projection eventually arrives.
 await page.evaluate(()=>{window.mode='pending';document.querySelector('#main [data-bash-source]').dispatchEvent(new Event('pointerdown'));});await page.evaluate(()=>window.pause());
 before=await count();await page.evaluate(()=>window.layer.querySelector('[data-id="Library C"]').remove());await page.evaluate(()=>window.pause());
 assert.equal(await count(),before);await page.evaluate(()=>{window.mode='normal';window.release();});await page.evaluate(()=>window.pause());
 assert.equal(await count(),before+1);assert.deepEqual(await options(),['이미지 라이브러리 연결','Library B']);
 // A second visible carrier survives the first one's retirement. There must
 // still be just one sender for the native node and no stale callback owner.
 await page.evaluate(()=>window.addCarrier('survivor'));await page.evaluate(()=>window.pause());
 await page.evaluate(()=>{window.handles.get('main').cleanup();window.handles.delete('main');});before=await count();
 await page.evaluate(()=>window.addSource('Library D','workspace-d','instance-d'));await page.evaluate(()=>window.pause());
 assert.equal(await count(),before+1);assert.equal(await page.evaluate(()=>window.writes.at(-1).id),'survivor');
 assert.equal(await page.locator('#survivor [data-bash-source] option').count(),3);
 assert.equal(await page.evaluate(()=>window.writes.some(v=>v.id==='measurement'||v.id==='opacity-clone')),false);
 assert.equal(await page.evaluate(()=>JSON.stringify(window.dirty)),dirty);
 assert.ok(await page.evaluate(()=>window.writes.every(v=>['refresh','bind','unbind'].includes(v.payload.hmb_image_bash_command.operation))));
 // Dispose every owner before a queued topology frame: no observer, queued
 // refresh or detached owner may send a command after teardown.
 await page.evaluate(()=>{window.addSource('Retired','workspace-retired','instance-retired');for(const h of window.handles.values())h.cleanup();window.handles.clear();});before=await count();await page.evaluate(()=>window.pause());
 await page.evaluate(()=>window.addSource('After cleanup','workspace-after','instance-after'));await page.evaluate(()=>window.pause());
 assert.equal(await count(),before);assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:'PASS',scope:'offline Chromium actual product widget',
  source_delete_before_focus:true,source_create_workspace_mount:true,same_name_new_object_lease:true,
  unbind_carries_current_object_lease:true,
  irrelevant_mutations_no_refresh:true,pending_refresh_trailing_topology:true,shared_visible_owner_cleanup:true,
  measurement_opacity_clone_no_commands:true,dirty_scene_unchanged:true,provider_calls:0,live_application_calls:0}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
