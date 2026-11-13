// UI-only full/delta transport: ordered replay, lost replies, two mounts and real audio.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {hmbReduceSoundTransport as reduce,hmbSoundState} from '../../widgets/HMBSoundLibraryWidget.js';

const track={instance_id:'clip',source_uid:'source-0',relative_path:'SFX/tone.wav',name:'Fixture',role:'SFX',purpose:'both',channel_uuid:'',shot_uuid:'',preview_url:'/tone.wav',media_signature:'fixture',duration_seconds:30,in_seconds:0,out_seconds:null,start_seconds:0,gain_db:0,enabled:true};
const assets=Array.from({length:5000},(_,i)=>({source_uid:`source-${i}`,relative_path:`SFX/source-${i}.wav`,name:`Sound ${i}`,role:'SFX',extension:'.wav',preview_url:'/tone.wav'}));
const state=hmbSoundState({schema:'hmb-sound-library-ui',version:1,revision:1,project_id:'fixture',project_uid:'project',project_root:'C:/fixture/Ai_Ct_audio',channel_uuid:'',shot:{channel_uuid:'',shot_uuid:'',name:'Only'},shot_catalog:{},assets,tracks:[track],status:'Ready'});
const meta=(sequence,mode='full',extra={})=>({schema:'hmb-sound-ui-transport',version:1,stream_id:'stream-1',catalog_key:'catalog-1',sequence,mode,...extra});
const full=(sequence,value=state,extra={})=>({...value,__hmb_sound_transport:meta(sequence,'full',extra)});
const delta=(sequence,base,values={},extra={})=>({schema:'hmb-sound-ui-patch',version:1,__hmb_sound_transport:meta(sequence,'delta',{base_sequence:base,...extra}),values,removed:[]});
let current=reduce(hmbSoundState({}),null,full(1));
assert.equal(current.kind,'full');
assert.equal(current.state.assets.length,5000);
let next=reduce(current.state,current.transport,delta(2,1,{status:'Changed'}));
assert.equal(next.kind,'delta');assert.equal(next.state.status,'Changed');assert.equal(next.state.assets.length,5000);
assert.equal(reduce(next.state,next.transport,delta(2,1,{status:'duplicate'})).kind,'ignored');
assert.equal(reduce(next.state,next.transport,delta(4,3,{tracks:[]})).needsSync,true,'A lost predecessor must not remove tracks');
assert.equal(reduce(next.state,next.transport,{__hmb_sound_command:{id:'echo',action:'remove'}}).kind,'ignored');
assert.equal(reduce(next.state,next.transport,structuredClone(next.state)).needsSync,false,'Actual native finalized_value echo must not create a sync loop');
assert.equal(reduce(next.state,next.transport,{...next.state,revision:0}).needsSync,true,'Unordered raw result cannot rewind state; it requests a sequenced full snapshot');
assert.equal(reduce(next.state,next.transport,delta(3,2,{assets:[]})).needsSync,true);
assert.equal(reduce(next.state,next.transport,delta(3,2,{unknown:1})).needsSync,true);
assert.equal(reduce(next.state,next.transport,delta(3,2,{}, {catalog_key:'other'})).needsSync,true);
assert.equal(reduce(hmbSoundState({}),null,delta(3,2)).needsSync,true,'A new mount cannot render a delta as a full document');
const restarted=reduce(next.state,next.transport,full(1,state,{stream_id:'stream-2'}));
assert.equal(restarted.kind,'full');assert.equal(reduce(restarted.state,restarted.transport,full(99)).kind,'ignored','Retired publisher cannot overwrite new stream');
const first=reduce(hmbSoundState({}),null,state);
assert.equal(first.kind,'full');assert.equal(reduce(first.state,first.transport,delta(9,8)).needsSync,true);
const gapA=reduce(next.state,next.transport,full(8,{...state,status:'Recovered'}));
assert.equal(gapA.state.status,'Recovered');assert.equal(reduce(gapA.state,gapA.transport,delta(9,8,{busy:true})).state.busy,true);
assert.equal(reduce(next.state,next.transport,full(2,next.state),true).kind,'full','Same-sequence authoritative read can complete recovery');
assert.equal(reduce(next.state,next.transport,full(1,state),true).kind,'ignored','Delayed read cannot rewind a newer delta');
assert.equal(reduce(hmbSoundState({}),null,full(0),true).kind,'full','Pre-publish read may begin at sequence zero');
assert.equal(reduce(hmbSoundState({}),null,full(0)).kind,'ignored','Ordinary events still require a published sequence');

const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const executablePath=process.env.HMB_COLOR_LUT_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
assert.ok(fs.existsSync(executablePath),'Actual browser required; unavailable is not a passing skip');
const source=fs.readFileSync(new URL('../../widgets/HMBSoundLibraryWidget.js',import.meta.url));
const nativeBundle=process.env.HMB_SOUND_TEST_EDITOR_BUNDLE;
const nativeSource=fs.readFileSync(nativeBundle||new URL('../editor/hmb-color-lut-native-header.js',import.meta.url),'utf8');
const nativeRead=nativeSource.slice(nativeSource.indexOf('function hmbBindNativeSoundSnapshot('),nativeSource.indexOf('function hmbUseColorLUTNativeHeader('));
assert.ok(nativeRead.includes('HMBGetSoundUISnapshotRequest'));
if(nativeBundle)assert.ok(nativeSource.includes('getSessionId(){return this.sessionId}'),'Pinned editor client has a native session getter');
const wav=Buffer.alloc(44+48000*2*30);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVE',8);wav.write('fmt ',12);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(48000,24);wav.writeUInt32LE(96000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
const html=`<!doctype html><html data-hmb-native-deletion-guard="engine-preflight" data-hmb-native-deletion-protection-version="2"><body style="margin:0;display:flex"><div class="react-flow__node" data-id="a" style="width:800px;height:850px"><div id="a" style="height:850px"></div></div><div class="react-flow__node" data-id="b" style="width:800px;height:850px"><div id="b" style="height:850px"></div></div><script type="module">
import mount from '/widget.js';
window.state=${JSON.stringify(state)};window.seq=1;window.stream='stream-1';window.requests=[];window.reads=[];window.owners={};window.bridges={};window.disabled=false;window.autoSync=true;window.fastTimers=false;window.session='session-A';
const nativeTimeout=window.setTimeout.bind(window);window.setTimeout=(fn,ms,...args)=>nativeTimeout(fn,window.fastTimers&&[1500,3000,4500,12000].includes(ms)?Math.ceil(ms/30):ms,...args);
window.full=()=>({...window.state,__hmb_sound_transport:{schema:'hmb-sound-ui-transport',version:1,stream_id:window.stream,catalog_key:'catalog-1',sequence:window.seq,mode:'full'}});
window.props=(id,value)=>({value,disabled:window.disabled,onChange:request=>window.requests.push({id,value:request})});
let hmbNativeStudioFlowEpoch=1;window.nextFlow=()=>hmbNativeStudioFlowEpoch++;
const Xd={getSessionId:()=>window.session,request:(type,request,options)=>{
  window.reads.push({type,request,options});
  if(window.rejectSync)return Promise.reject(new Error('fixture unavailable'));
  if(!window.autoSync)return new Promise(()=>{});
  const reply={node_name:window.wrongOwner?'foreign':request.node_name,altered_workflow_state:window.dirtyReply===true,snapshot:window.full()};
  if(window.holdRead)return new Promise(resolve=>{window.completeRead=()=>resolve(reply);});
  return Promise.resolve(reply);
}};
const Id=Xd;
${nativeRead}
window.bindRead=id=>{window.bridges[id]?.();const owner=window.owners[id];window.bridges[id]=hmbBindNativeSoundSnapshot(document.getElementById(id),id,()=>window.owners[id]===owner);};
window.delta=(values={},skip=[])=>{const base=window.seq++;window.state={...window.state,...values};const payload={schema:'hmb-sound-ui-patch',version:1,__hmb_sound_transport:{schema:'hmb-sound-ui-transport',version:1,stream_id:window.stream,catalog_key:'catalog-1',sequence:window.seq,base_sequence:base,mode:'delta'},values,removed:[]};for(const [id,owner]of Object.entries(window.owners))if(!skip.includes(id))owner.update(window.props(id,payload));return payload;};
for(const id of ['a','b']){window.owners[id]=mount(document.getElementById(id),window.props(id,window.full()));window.bindRead(id);}
window.ready=true;</script></body></html>`;
const server=http.createServer((req,res)=>{if(req.url==='/tone.wav'){res.setHeader('Content-Type','audio/wav');res.setHeader('Content-Length',wav.length);res.end(wav);}else{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript':'text/html');res.end(req.url==='/widget.js'?source:html);}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await playwright.chromium.launch({executablePath,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1640,height:950}});page.setDefaultTimeout(8000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
 assert.equal(await page.locator('#a [data-asset]').count(),80,'Large catalog keeps original bounded rendering');
 await page.locator('#b [data-preview-track="clip"]').click();
 await page.waitForFunction(()=>{const a=document.querySelector('#b audio');return !a.paused&&a.readyState>=2&&a.currentTime>.01;});
 await page.evaluate(()=>{window.audio=document.querySelector('#b audio');window.audio.currentTime=2;});
 await page.waitForFunction(()=>!window.audio.seeking&&window.audio.currentTime>=2);
 await page.evaluate(()=>{window.delta({status:'lost by B'},['b']);window.delta({status:'Recovered by read-only full'});});
 await page.waitForFunction(()=>document.querySelector('#b [role=status]').textContent==='Recovered by read-only full');
 assert.equal(await page.evaluate(()=>window.reads.length),1,'One lost event requests one full snapshot only for the affected widget');
 assert.deepEqual(await page.evaluate(()=>window.reads[0]),{type:'HMBGetSoundUISnapshotRequest',request:{node_name:'b',expected_stream_id:'stream-1'},options:{timeoutMs:5000}});
 assert.equal(await page.evaluate(()=>window.requests.length),0,'Recovery must not use the native property writer');
 assert.equal(await page.evaluate(()=>window.audio===document.querySelector('#b audio')&&!window.audio.paused&&window.audio.currentTime>=2),true);
 await page.waitForTimeout(100);
 assert.equal(await page.evaluate(()=>window.reads.length),1,'Successful read must not create a synchronization loop');
 await page.locator('#a [data-detail="clip"]').click();await page.locator('#a [data-duplicate="clip"]').click();
 const command=await page.evaluate(()=>window.requests.at(-1).value);
 assert.deepEqual(Object.keys(command),['__hmb_sound_command']);assert.ok(JSON.stringify(command).length<512,'5000-asset catalog must not be sent upstream with an edit');
 assert.equal(command.__hmb_sound_command.action,'duplicate');
 await page.evaluate(()=>{window.seq++;for(const [id,owner]of Object.entries(window.owners))owner.update(window.props(id,window.full()));});
 assert.equal(await page.locator('#a [data-duplicate="clip"]').isDisabled(),true,'Unrelated full refresh does not acknowledge an in-flight edit');
 await page.evaluate(()=>{const id=window.requests.at(-1).value.__hmb_sound_command.id;window.delta({revision:2,ack_command_id:id,tracks:[...window.state.tracks,{...window.state.tracks[0],instance_id:'copy'}]});for(const [key,owner]of Object.entries(window.owners))owner.update(window.props(key,structuredClone(window.state)));});
 assert.equal(await page.locator('#a [data-instance]').count(),2);assert.equal(await page.locator('#b [data-instance]').count(),2);
 assert.equal(await page.locator('#a [data-duplicate="clip"]').isDisabled(),false);
 // A locked widget can recover through the same read-only path.
 await page.evaluate(()=>{window.disabled=true;window.delta({status:'locked gap'},['a']);window.delta({status:'locked read succeeded'});});
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent==='locked read succeeded');
 assert.equal(await page.locator('#a [data-duplicate="clip"]').isDisabled(),true);
 const beforeLocked=await page.evaluate(()=>window.reads.length);
 // An unavailable session/backend stops at the retry limit. Unlock can retry.
 await page.evaluate(()=>{window.disabled=true;window.fastTimers=true;window.rejectSync=true;window.delta({status:'one omitted'},['a']);window.lastGap=window.delta({status:'locked recovered'});});
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent.includes('새로고침으로 다시 확인'));
 assert.equal(await page.evaluate(()=>window.reads.length),beforeLocked+3);
 assert.equal(await page.locator('#a [data-duplicate="clip"]').isDisabled(),true);
 assert.equal(await page.evaluate(()=>window.reads.at(-1).type),'HMBGetSoundUISnapshotRequest');
 await page.evaluate(()=>{window.disabled=false;window.rejectSync=false;for(const [id,owner]of Object.entries(window.owners))owner.update(window.props(id,window.lastGap));});
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent==='locked recovered');
 assert.equal(await page.evaluate(()=>window.reads.length),beforeLocked+4);
 // Lost authoring acknowledgement is queried, never resubmitted; a full
 // same-revision state permits a visible uncertain outcome rather than deadlock.
 await page.evaluate(()=>{window.disabled=false;window.fastTimers=true;window.delta({status:'ready for dropped command'});});
 await page.locator('#a [data-duplicate="clip"]').click();
 const beforeTimeout=await page.evaluate(()=>({writes:window.requests.length,reads:window.reads.length}));
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent.includes('변경 완료를 확인하지 못했습니다'));
 assert.equal(await page.evaluate(()=>window.requests.length),beforeTimeout.writes);
 assert.equal(await page.evaluate(()=>window.reads.length),beforeTimeout.reads+1);
 assert.equal(await page.locator('#a [data-duplicate="clip"]').isDisabled(),false);
 assert.equal(await page.locator('#a [data-instance]').count(),2,'Uncertain command is not replayed or assumed successful');
 // A read issued before a newer observed gap cannot falsely complete recovery.
 await page.evaluate(async()=>{const {default:mount}=await import('/widget.js');window.owners.a.cleanup();window.owners.a=mount(document.getElementById('a'),window.props('a',window.full()));window.bindRead('a');});
 await page.evaluate(()=>{window.fastTimers=false;window.holdRead=true;window.delta({status:'first missing'},['a']);window.delta({status:'held older reply'});});
 await page.waitForFunction(()=>typeof window.completeRead==='function');
 await page.evaluate(async()=>{window.delta({status:'another missing'},['a']);window.delta({status:'latest after delayed reply'});window.holdRead=false;window.completeRead();delete window.completeRead;await Promise.resolve();});
 assert.match(await page.locator('#a [role=status]').textContent(),/다시 연결하는 중/);
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent==='latest after delayed reply');
 // After a same-node publisher restart, the first full may be lost. The
 // valid new-stream gap targets that new lifetime, not the retired stream.
 await page.evaluate(()=>{window.retiredFull=window.full();window.stream='stream-2';window.seq=1;window.owners.b.update(window.props('b',window.full()));window.delta({status:'new stream recovered'});});
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent==='new stream recovered');
 assert.equal(await page.evaluate(()=>window.reads.at(-1).request.expected_stream_id),'stream-2');
 await page.evaluate(()=>window.owners.a.update(window.props('a',window.retiredFull)));
 assert.equal(await page.locator('#a [role=status]').textContent(),'new stream recovered');
 assert.equal(await page.evaluate(()=>window.requests.length),beforeTimeout.writes,'No additional property writes for either recovery race');
 // Test exact editor bridge fences directly. The callback target and requested
 // node remain local to the mounted native owner under every response race.
 const fences=await page.evaluate(async()=>{
   const result={};let delivered=0;const target=document.getElementById('a');
   const read=()=>target.dispatchEvent(new CustomEvent('hmb-sound-read-snapshot',{detail:{node_name:'b',expectedStreamId:window.stream,receive:()=>{delivered++;}}}));
   let before=window.reads.length;
   window.session='';read();await Promise.resolve();result.unboundSession=window.reads.length===before;
   window.session='session-A';window.wrongOwner=true;read();await Promise.resolve();result.wrongOwner=delivered===0;
   window.wrongOwner=false;window.dirtyReply=true;read();await Promise.resolve();result.dirtyReply=delivered===0;
   window.dirtyReply=false;window.holdRead=true;read();window.nextFlow();window.completeRead();await Promise.resolve();result.flowEpoch=delivered===0;
   read();window.session='session-B';window.completeRead();await Promise.resolve();result.changedSession=delivered===0;
   read();window.bridges.a();window.completeRead();await Promise.resolve();result.retiredOwner=delivered===0;
   window.holdRead=false;delete window.completeRead;window.bindRead('a');read();await Promise.resolve();
   result.exactNode=delivered===1&&window.reads.at(-1).request.node_name==='a';
   return result;
 });
 assert.ok(Object.values(fences).every(Boolean),JSON.stringify(fences));
 // New mount receives a patch only. A missing server response stops after
 // three read requests; cleanup cancels every pending retry.
 await page.evaluate(()=>{window.owners.a.cleanup();window.bridges.a();delete window.owners.a;window.autoSync=false;window.fastTimers=true;window.reads=[];window.requests=[];});
 await page.evaluate(async()=>{const {default:mount}=await import('/widget.js');const gap={schema:'hmb-sound-ui-patch',version:1,__hmb_sound_transport:{schema:'hmb-sound-ui-transport',version:1,stream_id:window.stream,catalog_key:'catalog-1',sequence:window.seq,base_sequence:window.seq-1,mode:'delta'},values:{status:'must not render'},removed:[]};window.owners.a=mount(document.getElementById('a'),window.props('a',gap));window.bindRead('a');});
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent.includes('새로고침으로 다시 확인'));
 assert.equal(await page.evaluate(()=>window.reads.length),3);
 assert.equal(await page.locator('#a [data-action=refresh]').isDisabled(),false);
 assert.equal(await page.evaluate(()=>window.requests.length),0);
 await page.evaluate(()=>{window.autoSync=true;});await page.locator('#a [data-action=refresh]').click();
 await page.waitForFunction(()=>document.querySelectorAll('#a [data-instance]').length===2);
 assert.equal(await page.evaluate(()=>window.reads.length),4);
 await page.evaluate(()=>{window.autoSync=false;window.delta({},['a']);window.delta({status:'cleanup while retry pending'});});
 await page.waitForFunction(()=>window.reads.length===5);
 await page.evaluate(()=>{window.owners.a.cleanup();window.owners.b.cleanup();window.bridges.a();window.bridges.b();window.countAtCleanup=window.reads.length;});
 await page.waitForTimeout(400);
 assert.equal(await page.evaluate(()=>window.reads.length),await page.evaluate(()=>window.countAtCleanup));
 assert.equal(await page.locator('audio').count(),0);assert.deepEqual(errors,[]);
 // An older editor without the new read bridge must never fall back to a write.
 await page.evaluate(async()=>{const {default:mount}=await import('/widget.js');window.requests=[];window.reads=[];window.owners.a=mount(document.getElementById('a'),window.props('a',{schema:'hmb-sound-ui-patch',version:1,__hmb_sound_transport:{schema:'hmb-sound-ui-transport',version:1,stream_id:window.stream,catalog_key:'catalog-1',sequence:window.seq,base_sequence:window.seq-1,mode:'delta'},values:{},removed:[]}));});
 await page.waitForFunction(()=>document.querySelector('#a [role=status]').textContent.includes('새로고침으로 다시 확인'));
 assert.deepEqual(await page.evaluate(()=>[window.requests.length,window.reads.length]),[0,0]);
 await page.evaluate(()=>window.owners.a.cleanup());
 console.log(JSON.stringify({pass:true,pureReducer:true,actualChrome:true,twoMounts:true,nativeFullEcho:true,localAudioPreserved:true,boundedRecovery:3,commandBytes:JSON.stringify(command).length,assets:5000,cleanupNoRetry:true,nativeReadonlyBridge:true,lockedReadonlyRecovery:true,propertyWritesAfterRead:0,noBridgeNoWrite:true,observedSequenceFloor:true,missedNewStreamFull:true,compiledEditor:!!nativeBundle,bridgeFences:fences}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
