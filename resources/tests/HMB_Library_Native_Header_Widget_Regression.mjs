// Actual product widgets and installed React portal runtime in isolated Chrome.
// Header discovery/actions and SDK callbacks are synthetic; the actual native
// callbacks/hidden-measurement allocator are covered by the companion host test.
// No live editor, installation, server, model or paid generation is contacted.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readNativeEditorSource,nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const files=['HMBImageAssetLibraryWidget.js','HMBVideoPickerLibraryWidget_v032.js',
 'HMBAgentLibraryWidget.js','HMBPromptLibraryScopedBindingWidget.js','HMBFinishLookLibraryWidget.js',
 'HMBSeedanceGenerationWidget.js','HMBImageGenerationWidget.js'];
const sources=files.map(file=>fs.readFileSync(path.join(root,'widgets',file),'utf8'));
const original=readNativeEditorSource(root);
const alias=original.indexOf('S=u(p(),1),C=h(),w=x(),T=u(y())');assert.ok(alias>0);
const runtime=original.slice(0,original.indexOf(',E=`modulepreload`',alias))+';';
const jsxStart=original.indexOf('var Wn=s('),jsxEnd=original.indexOf('function Gn(',jsxStart);
assert.ok(jsxStart>0&&jsxEnd>jsxStart);
const runtimeModule=runtime+'\n'+original.slice(jsxStart,jsxEnd)+'\nwindow.react={S,T,R,w};window.runtimeReady=true;';
const server=http.createServer((req,res)=>{
 res.setHeader('Content-Type',req.url==='/runtime.js'?'text/javascript':'text/html');
 res.end(req.url==='/runtime.js'?runtimeModule:'<!doctype html><meta charset="utf-8"><style>body{margin:10px;background:#111725}.react-flow__node{position:relative;width:1800px;min-height:700px}.native-probe-button{font:italic 11px Georgia;color:rgb(1,2,3);background:rgb(231,232,233);border:1px solid rgb(21,22,23);border-radius:3px;box-shadow:none;padding:2px;min-height:18px}.native-probe-title{font:13px Arial;color:#fff;white-space:nowrap}[data-hmb-native-actions]>div{display:flex;gap:4px}</style><main></main><div id="react"></div><script type="module" src="/runtime.js"></script>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const playwright=nativeTestPlaywright();
const report={schema:'hmb-library-native-header-widget-v1',scope:'Actual product widgets and installed React; synthetic header discovery/action/SDK boundary',
 checks:0,cases:[],sources:files.map((file,index)=>({file,sha256:createHash('sha256').update(sources[index]).digest('hex')})),
 live_editor_actions:0,installed_files_changed:0,provider_calls:0,paid_calls:0};
let browser;
try {
 browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(let kind=0;kind<files.length;kind++){
  const page=await browser.newPage({viewport:{width:1950,height:1500}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(7000);
  const origin=`http://127.0.0.1:${server.address().port}`;
  await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
  await page.goto(origin);await page.waitForFunction(()=>window.runtimeReady);
  await page.evaluate(async({code,kind})=>{
   window.kind=kind;window.widget=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(code+(code.includes('function hmbNativeUiContract(')?'\nexport {hmbNativeUiContract};':'')))));
   window.types=['HMBImageAssetLibrary','HMBVideoPickerLibrary','HMBAgentLibrary','HMBPromptLibrary','HMBFinishLookLibrary','HMBSeedanceGeneration','HMBImageGeneration'];
   window.roots=['.hmb-image-assets','.hmbvp','.hmb-agent-dashboard','.hmb-dashboard','.hmb-finish-look','.hmb-seedance-shot','.hmb-image-generation-header'];
   window.heads=['.top','.top','.agent-topbar','.topbar','.hmb-finish-look__topbar','.hmb-seedance-shot__row','.hmb-image-generation-header__row'];
   window.brands=['.heading','.brand','.agent-heading','.title','.hmb-finish-look__heading','.hmb-seedance-shot__title','.hmb-image-generation-header__title'];
   window.expectedNames=['HMB ImageAsset Library','HMB VideoPicker','HMB Agent','HMBPrompt'];
   window.channel='11111111-1111-4111-8111-111111111111';
   window.shots=Array.from({length:5},(_,index)=>({channel_uuid:channel,shot_uuid:`22222222-2222-4222-8222-${String(index+1).padStart(12,'0')}`,number:index+1,name:`Original ${index+1}`,revision:index+1,selected_source_uids:[]}));
   window.catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:channel,channel_uuid:channel,generation:1,metadata_sha256:'a'.repeat(64),shots};
   if(kind===0){
    window.value=widget.hmbNormalizeImageAssetState({project_root:'C:/fixture/superwings12',project_id:'superwings12',selected_source_view:'user',assets:[]});
    while(value.shot_routing.shots.length<5)widget.hmbAddImageAssetShot(value);
    value.shot_routing.shots.forEach((shot,i)=>{shot.name=`Original ${i+1}`;shot.name_is_custom=true;});
    widget.hmbCreateImageBashWorkspace(value);value.image_bash_active=false;
   }else if(kind===1){
    window.value={language:'ko',runtime_instance_id:'native-header-fixture',state_revision:1,channel_uuid:channel,shot_publisher_instance_uuid:channel,
     active_picker_shot_uuid:shots[0].shot_uuid,shot_selections:shots,picker_shots:shots.map(shot=>({workspace_uuid:shot.shot_uuid,bound_shot_uuid:shot.shot_uuid,number:shot.number,name:shot.name,video_asset_uids:[],selected_video_uids:[]})),videos:[]};
   }else if(kind===2){window.value={schema:'hmb-agent-ui',schema_version:2,shot_manager:true,shot_editor_expanded:true,shot:shots[0],shot_catalog:catalog};
   }else if(kind===4){window.value={shot_manager:true,shot_catalog:catalog,shot:shots[0],finish_look:{beauty:{enabled:true,brightness:1.5,saturation:.75}}};
   }else if(kind===5){window.value={schema:'hmb-seedance-shot-ui',schema_version:2,shot_catalog:catalog,shot:shots[0],execution_mode:'shot',requested_mode:'shot',execution_mode_revision:1,execution_mode_state_revision:1,execution_mode_instance:'a'.repeat(32),generation:{phase:'succeeded',media_revision:4,job_id:'job-'+ '1'.repeat(32),has_existing_video:true},draft:{visible:false}};
   }else if(kind===6){window.value={task_id:'job-image-preserved',image:'http://fixture.invalid/existing.png'};
   }else{
    window.value=widget.normalizeState({multi_shot_enabled:true,shot:shots[0],source_sync_revision:1,image_asset:{shot_catalog:shots,shot_catalog_routing:catalog}});
    const key=Object.keys(value.text)[0];window.promptKey=key;
    for(const shot of shots){widget.hmbSwitchPromptShot(value,shot.shot_uuid);value.text[key]=`Original ${shot.number} literal 0 OFF`;widget.hmbStorePromptShotDocument(value);}
    widget.hmbSwitchPromptShot(value,shots[0].shot_uuid);
   }
   window.initial=structuredClone(value);window.calls=[];window.events=[];window.nativeCalls=[];
   document.addEventListener('hmb-color-lut-header-ready',event=>events.push({kind:'ready',container:event.detail.container}));
   document.addEventListener('hmb-color-lut-header-retire',event=>events.push({kind:'retire',container:event.detail.container}));
   window.make=(name,value)=>{
    const shell=document.createElement('article');shell.className='react-flow__node';shell.dataset.id=name;
    const container=document.createElement('div');container.dataset.parameterName=kind===2?'HMB_AGENT_UI':kind===3?'HMB_PROMPT_UI':'FIXTURE_STATE';shell.append(container);document.querySelector('main').append(shell);
    const fixture={name,shell,container,value,disabled:false,pointers:0};shell.addEventListener('pointerdown',()=>fixture.pointers++);
    fixture.props=()=>({value:fixture.value,disabled:fixture.disabled,nodeName:name,onChange:next=>{calls.push({name,next});return Promise.resolve();}});
    fixture.handle=widget.default(container,fixture.props());return fixture;
   };
   window.a=make('Source A',structuredClone(value));window.b=make('Source B',structuredClone(value));
   window.fallbackHeights=[a,b].map(f=>f.container.querySelector(heads[kind]).getBoundingClientRect().height);
   window.fallbackContainerDrags=[a,b].map(f=>f.container.classList.contains('nodrag'));
   window.originalBodies=[a,b].map(f=>f.container.querySelector(roots[kind]));
   window.setActive=(f,active)=>f.container.dispatchEvent(new CustomEvent('hmb-color-lut-header-state',{detail:{active}}));
   window.slots=[a,b].map(f=>['identity','actions'].map(name=>f.container.querySelector(`[data-hmb-native-${name}]`)));
   window.nativeRoot=react.w.createRoot(document.querySelector('#react'));
   const {S,T,R}=react;
   window.portalView=()=>S.createElement(S.Fragment,null,...[a,b].flatMap((f,i)=>[
    T.createPortal(S.createElement('div',{className:'native-probe-title',onDoubleClick:()=>nativeCalls.push(f.name+':rename')},f.name),slots[i][0],f.name+'-identity'),
    T.createPortal(S.createElement('div',null,...['unlock','reset','run'].map(action=>S.createElement('button',{key:action,type:'button',className:'native-probe-button','data-native-action':action,
     onClick:()=>nativeCalls.push(f.name+':'+action)},action))),slots[i][1],f.name+'-actions')
   ]));
   nativeRoot.render(portalView());[a,b].forEach(f=>setActive(f,true));
  },{code:sources[kind],kind});
  await page.waitForFunction(()=>document.querySelectorAll('[data-native-action]').length===6);
  const initial=await page.evaluate(()=>({types:[a,b].map(f=>f.container.getAttribute('data-hmb-native-node-type')),
   counts:[a,b].map(f=>f.container.querySelectorAll('[data-hmb-native-identity],[data-hmb-native-actions]').length),
   ready:[a,b].map(f=>events.filter(e=>e.kind==='ready'&&e.container===f.container).length),
   active:[a,b].map(f=>f.container.querySelector(roots[kind]).getAttribute('data-hmb-native-header')),
   heights:[a,b].map(f=>f.container.querySelector(heads[kind]).getBoundingClientRect().height),fallbackHeights,
   brands:[a,b].map(f=>getComputedStyle(f.container.querySelector(brands[kind])).display),
   nodrag:[a,b].map(f=>Boolean(f.container.querySelector('[data-hmb-native-identity]').closest('.nodrag'))),
   inputUnchanged:JSON.stringify(value)===JSON.stringify(initial),
   style:(()=>{const s=getComputedStyle(a.container.querySelector('[data-native-action]'));return{font:s.fontFamily,color:s.color,background:s.backgroundColor,radius:s.borderRadius};})()}));
  assert.deepEqual(initial.types,[['HMBImageAssetLibrary','HMBVideoPickerLibrary','HMBAgentLibrary','HMBPromptLibrary','HMBFinishLookLibrary','HMBSeedanceGeneration','HMBImageGeneration'][kind]].flatMap(x=>[x,x]));
  assert.deepEqual(initial.counts,[2,2]);assert.ok(initial.ready.every(n=>n>=1));
  assert.deepEqual(initial.active,['active','active']);if(kind<4)assert.deepEqual(initial.heights,initial.fallbackHeights);else assert.ok(initial.heights.every((h,i)=>Math.abs(h-initial.fallbackHeights[i])<=2));
  assert.deepEqual(initial.brands,['none','none']);assert.deepEqual(initial.nodrag,[false,false]);assert.equal(initial.inputUnchanged,true);
  assert.deepEqual(initial.style,{font:'Georgia',color:'rgb(1, 2, 3)',background:'rgb(231, 232, 233)',radius:'3px'});report.checks+=9;
  await page.evaluate(()=>{
   window.originalNative=a.container.querySelector('[data-native-action="unlock"]');
   window.beforeCalls=calls.length;window.beforePointers=a.pointers;
   a.container.querySelector('[data-hmb-native-identity]').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0}));
   a.container.querySelector('[data-hmb-native-identity]>div').dispatchEvent(new MouseEvent('dblclick',{bubbles:true,button:0}));
   a.container.querySelector('[data-native-action="unlock"]').click();
  });
  assert.equal(await page.evaluate(()=>a.pointers>beforePointers),true,files[kind]+' lets the native title pointer reach the node');
  assert.deepEqual(await page.evaluate(()=>nativeCalls),['Source A:rename','Source A:unlock']);
  assert.equal(await page.evaluate(()=>calls.length),await page.evaluate(()=>beforeCalls));report.checks+=3;
  const retained=await page.evaluate(async()=>{
   const bodyBefore=JSON.stringify(initial),otherName=b.container.querySelector('[data-hmb-native-identity]').textContent;
   for(let number=1;number<=5;number++){
    const next=structuredClone(a.value);
    if(kind===0){next.shot_routing.active_shot_uuid=next.shot_routing.shots[number-1].shot_uuid;next.language=number%2?'en':'ko';}
    else if(kind===1){next.active_picker_shot_uuid=shots[number-1].shot_uuid;next.language=number%2?'en':'ko';}
    else if([2,4,5].includes(kind)){next.shot=shots[number-1];if(kind===4)next.language=number%2?'en':'ko';}
    else if(kind===6){next.task_id='job-image-preserved';}
    else {widget.hmbSwitchPromptShot(next,shots[number-1].shot_uuid);next.language=number%2?'en':'ko';}
    a.value=next;a.handle.update(a.props());await new Promise(resolve=>requestAnimationFrame(resolve));
    if(a.container.querySelector('[data-hmb-native-identity]')!==slots[0][0]||a.container.querySelector('[data-hmb-native-actions]')!==slots[0][1]||a.container.querySelector('[data-native-action="unlock"]')!==originalNative)return false;
   }
   return originalNative.isConnected&&JSON.stringify(initial)===bodyBefore&&b.container.querySelector('[data-hmb-native-identity]').textContent===otherName;
  });assert.equal(retained,true,files[kind]+' retains portal targets/children during five shots, language changes and host echoes');report.checks++;
  if(kind===0||kind===1){
   const mode=await page.evaluate(()=>{
    for(const expanded of [true,false,true,false]){
     if(kind===0)widget.hmbSetImageAssetLibraryCompact(a.container,!expanded,{geometry:false});
     else widget.hmbSetVideoPickerHybridView(a.container,expanded);
     if(a.container.querySelector('[data-hmb-native-actions]')!==slots[0][1]||a.container.querySelector('[data-native-action="unlock"]')!==originalNative)return false;
    }
    return originalNative.isConnected;
   });assert.equal(mode,true,'Compact/expanded keeps the exact React portal target and action');report.checks++;
  }
  await page.evaluate(()=>{a.disabled=true;a.handle.update(a.props());});
  const locked=await page.evaluate(()=>{
   const native=a.container.querySelector('[data-native-action="unlock"]'),c=a.container.__hmbNativeUiContract;
   let blocked=false;if(c){try{c.wrap().onChange({schema:'forged-write'});}catch{blocked=true;}}
   const editable=[...(c?.originals||[])].filter(([el,old])=>'disabled'in el&&!old.disabled);
   const n=nativeCalls.length,w=calls.length;native.click();
   editable[0]?.[0].dispatchEvent(new Event('change',{bubbles:true,cancelable:true}));
   return{nativeEnabled:!native.disabled,nativeDelivered:nativeCalls.length===n+1,blocked,bodyLocked:editable.every(([el])=>el.disabled),bodyControls:editable.length,hasAuthoringAdapter:Boolean(c),noBodyWrite:calls.length===w};
  });assert.equal(locked.nativeEnabled,true);assert.equal(locked.nativeDelivered,true);if(kind!==6){assert.equal(locked.blocked,true);assert.equal(locked.hasAuthoringAdapter,true);assert.ok(locked.bodyControls>0);}else assert.equal(locked.hasAuthoringAdapter,false);assert.equal(locked.bodyLocked,true);assert.equal(locked.noBodyWrite,true);report.checks+=6;
  await page.evaluate(()=>{a.disabled=false;a.handle.update(a.props());setActive(a,false);});
  const fallback=await page.evaluate(()=>({mode:a.container.querySelector(roots[kind]).getAttribute('data-hmb-native-header'),brand:getComputedStyle(a.container.querySelector(brands[kind])).display,
   rootDrag:a.container.classList.contains('nodrag'),originalRootDrag:fallbackContainerDrags[0],other:b.container.querySelector(roots[kind]).getAttribute('data-hmb-native-header'),
   same:a.container.querySelector('[data-native-action="unlock"]')===originalNative}));
  assert.equal(fallback.mode,'fallback');assert.notEqual(fallback.brand,'none');assert.equal(fallback.rootDrag,fallback.originalRootDrag);assert.equal(fallback.other,'active');assert.equal(fallback.same,true);report.checks+=5;
  if(kind===2){
   const row=await page.evaluate(()=>{const c=document.createElement('div');a.shell.append(c);const h=widget.default(c,{value:{schema:'hmb-agent-shot-row',version:1,shot:shots[0],selected:true,expanded:true},onChange(){}});
    const result={slots:c.querySelectorAll('[data-hmb-native-identity],[data-hmb-native-actions]').length,tag:c.hasAttribute('data-hmb-color-lut-widget')};h.cleanup();c.remove();return result;});
   assert.deepEqual(row,{slots:0,tag:false});report.checks++;
  }
  const clean=await page.evaluate(async()=>{
   // Widget teardown may detach the whole root; React still owns and removes
   // its own descendants from the exact old portal containers afterwards.
   a.handle.cleanup();b.handle.cleanup();nativeRoot.unmount();await Promise.resolve();
   return{retired:[a,b].every(f=>events.some(e=>e.kind==='retire'&&e.container===f.container)),
    tagsRemoved:[a,b].every(f=>!f.container.hasAttribute('data-hmb-color-lut-widget')&&!f.container.hasAttribute('data-hmb-native-node-type'))};
  });assert.deepEqual(clean,{retired:true,tagsRemoved:true});report.checks++;
  assert.deepEqual(errors,[],files[kind]+' has no React portal teardown/DOM exceptions');report.checks++;
  report.cases.push({file:files[kind],initial,locked,fallback});await page.close();
 }
 report.status='PASS';
 const output=process.env.HMB_LIBRARY_NATIVE_HEADER_REPORT_DIR;
 if(output){fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'library-native-header-widget.json'),JSON.stringify(report,null,2));}
 console.log(JSON.stringify({status:report.status,checks:report.checks,widgets:files.length,scope:report.scope,paid_calls:0,live_editor_actions:0}));
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
