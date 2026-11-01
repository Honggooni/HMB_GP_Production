// Actual widget modules, isolated transport, controlled canonical receiver.
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import crypto from 'node:crypto';import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
import {setupImageAssetQueueFixture} from './fixtures/image_asset_queue_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const product=process.env.HMB_QUEUE_PRODUCT_ROOT||root,out=process.env.HMB_QUEUE_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Image_Asset_Queued_Instance_Edit_Regression');fs.mkdirSync(out,{recursive:true});
const main=fs.readFileSync(path.join(product,'widgets/HMBImageAssetLibraryWidget.js'),'utf8'),bridge=fs.readFileSync(path.join(product,'widgets/HMBImageAssetThumbnailPatchBridgeWidget.js'),'utf8');
const result={status:'RUNNING',cases:{},external_requests:0,actual_Desktop:false,paid_calls:0,scope:'Real widget bytes; isolated simulated transport and virtual time, not measured Desktop latency.'};
const browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
const snapshot=page=>page.evaluate(()=>({writes:fixture.writes.length,rows:fixture.closed?[]:fixture.rows().map(x=>x.instance_id),bad:fixture.badIntents,queue:fixture.main.__hmbImageAssetBashEditQueue?.snapshot()}));
try{
 for(const kind of ['rapid_twenty','copy_delete','repeat_copy_remove','session_failure','busy_recover','busy_auto_recover','bounded_read_failure','unknown_ack','foreign_owner','dispose']){
  const context=await browser.newContext({viewport:{width:1450,height:950}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',r=>{if(r.request().url()==='http://127.0.0.1/instance-edit')return r.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'});result.external_requests++;return r.abort()});
  await page.clock.install({time:new Date(0)});await page.goto('http://127.0.0.1/instance-edit');await page.clock.pauseAt(new Date(1000));
  await setupImageAssetQueueFixture(page,main,bridge,kind);
  await page.evaluate(()=>{fixture.copy(fixture.originalIds[0]);fixture.copy(fixture.originalIds[0]);});
  await page.clock.runFor(200);assert.equal((await snapshot(page)).writes,0,'collect before send');
  if(kind==='session_failure')await page.evaluate(()=>fixture.failSend=true);
  if(kind.startsWith('busy_'))await page.evaluate(()=>{fixture.main.__hmbNativeUiContract.props.disabled=true});
  if(kind==='bounded_read_failure')await page.evaluate(()=>fixture.rejectRead='No sessionId while reconnecting');
  if(kind==='foreign_owner')await page.evaluate(()=>{const parent=document.createElement('aside');document.body.appendChild(parent);parent.appendChild(fixture.node)});
  if(kind==='dispose')await page.evaluate(()=>fixture.close());
  await page.clock.runFor(80);
  if(['busy_recover','busy_auto_recover','bounded_read_failure','foreign_owner','dispose'].includes(kind)){
   assert.equal((await snapshot(page)).writes,0);
   if(kind==='busy_recover'){
    await page.evaluate(()=>{fixture.main.__hmbNativeUiContract.props.disabled=false;fixture.main.__hmbImageAssetBashEditQueue.recover()});await page.clock.runFor(60);assert.equal((await snapshot(page)).writes,1);
   }
   if(kind==='busy_auto_recover'){
    await page.evaluate(()=>{fixture.main.__hmbNativeUiContract.props.disabled=false});await page.clock.runFor(600);assert.equal((await snapshot(page)).writes,1,'bounded automatic recovery after busy clears');
   }
   if(kind==='bounded_read_failure'){
    await page.clock.runFor(20000);const count=await page.evaluate(()=>fixture.requests.length);assert.equal((await snapshot(page)).writes,0);assert(count<=5,'initial read plus at most three recovery reads');
    await page.clock.runFor(20000);assert.equal(await page.evaluate(()=>fixture.requests.length),count,'no infinite retry polling');
   }
  }else if(kind==='session_failure'){
   let s=await snapshot(page);assert.equal(s.writes,0);assert.match(s.queue.stopped,/sessionId/);assert.equal(s.rows.length,2);
   await page.evaluate(()=>fixture.rejectRead='Still disconnected');
   await page.clock.runFor(2000);assert.equal((await snapshot(page)).writes,0,'no write without fresh confirmed connection');
   await page.evaluate(()=>{fixture.rejectRead=null;fixture.main.__hmbImageAssetBashEditQueue.recover()});await page.clock.runFor(60);assert.equal((await snapshot(page)).writes,1,'proven-unsent guard is retried after confirmation');
   for(let i=0;i<2;i++){await page.evaluate(()=>fixture.canonical(fixture.server));await page.clock.runFor(40)}
   assert.equal((await snapshot(page)).rows.length,4,'both click intents preserved');
  }else{
   assert.equal((await snapshot(page)).writes,1,'only one in flight');
   if(kind==='unknown_ack'){
    await page.clock.runFor(11000);let s=await snapshot(page);assert.equal(s.writes,1);assert(s.queue.active&&s.queue.stopped);
    await page.evaluate(()=>{fixture.canonical(fixture.server);fixture.main.__hmbImageAssetBashEditQueue.recover()});await page.clock.runFor(80);
    assert.equal((await snapshot(page)).writes,2);
   }else if(kind==='rapid_twenty'){
    await page.evaluate(()=>{for(let i=0;i<18;i++)fixture.copy(fixture.originalIds[0])});
    await page.clock.runFor(1000);assert.equal((await snapshot(page)).writes,1,'void callback and optimistic echoes cannot release queue');
    for(let i=0;i<20;i++){await page.evaluate(()=>fixture.canonical(fixture.server));await page.clock.runFor(40);}
    let s=await snapshot(page);assert.equal(s.writes,20);assert.equal(s.rows.length,22);assert.equal(new Set(s.rows).size,22);assert.equal(s.queue.pending,0);assert.equal(s.queue.active,false);assert.deepEqual(s.bad,[]);
   }else if(kind==='repeat_copy_remove'){
    // Clear the initially queued second copy, then repeat Copy -> immediate
    // removal of its optimistic clone ten times with delayed acknowledgements.
    await page.evaluate(()=>fixture.main.__hmbImageAssetBashEditQueue.cancel());
    for(let i=0;i<10;i++){
     if(i){await page.evaluate(()=>fixture.copy(fixture.originalIds[0]));await page.clock.runFor(260)}
     await page.evaluate(()=>{const copy=fixture.rows().find(x=>!fixture.originalIds.includes(x.instance_id));fixture.remove(copy.instance_id)});
     for(let j=0;j<2;j++){await page.evaluate(()=>fixture.canonical(fixture.server));await page.clock.runFor(40)}
     assert.equal((await snapshot(page)).rows.length,2);
    }
    let s=await snapshot(page);assert.equal(s.writes,20);assert.deepEqual(s.bad,[]);
   }else if(kind==='copy_delete'){
    await page.evaluate(()=>{const clone=fixture.rows().find(x=>!fixture.originalIds.includes(x.instance_id));fixture.remove(clone.instance_id)});
    for(let i=0;i<3;i++){await page.evaluate(()=>fixture.canonical(fixture.server));await page.clock.runFor(40);}
    let s=await snapshot(page);assert.equal(s.writes,3);assert.equal(s.rows.length,3);assert.deepEqual(s.bad,[]);
   }
  }
  result.cases[kind]={status:'PASS',...(kind==='dispose'?{disposed:true}:await snapshot(page))};assert.deepEqual(errors,[]);
  await page.evaluate(()=>fixture.close());await context.close();
 }
 result.status='PASS';
}catch(error){result.status='FAILED';result.error=String(error);throw error;}
finally{await browser.close();result.main_sha256=crypto.createHash('sha256').update(main).digest('hex');fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
