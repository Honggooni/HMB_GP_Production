// Product widget, synthetic backend notice only. No CGT/provider/write call.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import * as product from '../../widgets/HMBImageAssetLibraryWidget.js';
import {nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const report=path.join(root,'reports/cgt-work-start-local-20261028');
fs.mkdirSync(report,{recursive:true});
const makeNotice=status=>({schema:'hmb-cgt-work-start-notice-v1',status,
  request_id:'private-request-id',updated_count:2,already_work_count:1,skipped_count:1,failed_count:1,
  token:'secret-token-do-not-display',task_id:'private-task-id-do-not-display',message:'private-server-body-do-not-display'});
for(const status of ['queued','running','completed','partial','failed','unknown']){
  const notice=makeNotice(status),safe=product.hmbNormalizeCgtWorkStartNotice(notice);
  assert.deepEqual(Object.keys(safe).sort(),['schema','status','request_id','updated_count','already_work_count','skipped_count','failed_count'].sort());
  for(const language of ['ko','en']){
    const text=product.hmbCgtWorkStartNoticeMessage(notice,language);
    assert.ok(text.length>12);assert.doesNotMatch(text,/secret-token|private-task|private-server|private-request/);
  }
}
for(const extra of [{schema:'other'},{status:'raw-secret-error'},{request_id:''},
  {request_id:'Bearer secret'},{updated_count:-1},{already_work_count:6},{skipped_count:NaN},{failed_count:'1'}]){
  const invalid={...makeNotice('failed'),...extra};
  assert.deepEqual(product.hmbNormalizeCgtWorkStartNotice(invalid),{});
  assert.equal(product.hmbCgtWorkStartNoticeMessage(invalid),'');
}
const browser=await nativeTestPlaywright().chromium.launch({headless:true,
  executablePath:process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
const receipt={schema:'hmb-cgt-work-start-notice-widget-v1',external_requests:0,live_cgt_calls:0,
  cgt_writes:0,paid_requests:0,cases:[],passed:false};
try{
  const page=await browser.newPage({viewport:{width:1280,height:1050}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
  await page.setContent('<div class="react-flow__node" data-id="Offline ImageAsset" style="width:1180px;height:950px"><div id="mount"></div></div>');
  await page.evaluate(async source=>{
    window.w=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
    window.mount=document.querySelector('#mount');window.calls=[];window.base=w.hmbNormalizeImageAssetState({});
    window.state=structuredClone(base);window.props=()=>({value:JSON.stringify(state),onChange:value=>calls.push(value)});
    window.controller=w.default(mount,props());
    window.update=value=>{state=w.hmbNormalizeImageAssetState({...base,...value});controller.update(props());};
    window.geometry=()=>{
      const names=['.hmb-image-assets','.toolbar-status','.toolbar','.asset-scroll'];
      return names.map(name=>{const rect=mount.querySelector(name).getBoundingClientRect();return {name,x:rect.x,y:rect.y,width:rect.width,height:rect.height};});
    };
  },fs.readFileSync(path.join(root,'widgets/HMBImageAssetLibraryWidget.js'),'utf8'));
  const geometry=await page.evaluate(()=>geometry());
  const callsBefore=await page.evaluate(()=>calls.length);
  for(const language of ['ko','en']){
    for(const status of ['queued','running','completed','partial','failed','unknown']){
      const notice=makeNotice(status);
      await page.evaluate(({notice,language})=>update({cgt_work_start_notice:notice,language}),{notice,language});
      const text=await page.locator('.toolbar-status strong').innerText();
      assert.equal(text,product.hmbCgtWorkStartNoticeMessage(notice,language));
      assert.doesNotMatch(await page.locator('#mount').innerText(),/secret-token|private-task|private-server|private-request/);
      assert.match(await page.locator('.toolbar-status strong').getAttribute('title'),/0\/50/);
      assert.deepEqual(await page.evaluate(()=>geometry()),geometry,'Notice changed existing geometry');
      receipt.cases.push({status,language,fixed_safe_copy:true,geometry_preserved:true});
    }
  }
  const notice=makeNotice('failed');
  await page.evaluate(notice=>update({cgt_work_start_notice:notice,error:'Existing catalog error'}),notice);
  assert.equal(await page.locator('.toolbar-status strong').innerText(),'Existing catalog error');
  assert.match(await page.locator('.toolbar-status strong').getAttribute('title'),/CGT/);
  await page.evaluate(notice=>update({cgt_work_start_notice:notice,scan_busy:true}),notice);
  assert.doesNotMatch(await page.locator('.toolbar-status strong').innerText(),/알림에 실패/);
  await page.evaluate(notice=>update({cgt_work_start_notice:notice,asset_registration_result:{ok:true,request_id:'registered',message:'Registered asset result'}}),notice);
  assert.equal(await page.locator('.toolbar-status strong').innerText(),'Registered asset result');
  receipt.cases.push({priority:'scan, existing error and registration result preserved; CGT hint remains in title'});
  await page.evaluate(notice=>update({cgt_work_start_notice:notice}),makeNotice('unknown'));
  await page.evaluate(()=>w.hmbOpenShotHierarchyDialog(mount,state,'',()=>{throw Error('Unexpected local commit');}));
  const beforeStatus=await page.locator('[data-hier-cgt-status]').innerText();
  assert.match(beforeStatus,/미확정/);
  await page.evaluate(notice=>update({cgt_work_start_notice:notice}),makeNotice('completed'));
  assert.match(await page.locator('[data-hier-cgt-status]').innerText(),/알림이 완료/);
  assert.doesNotMatch(await page.locator('[data-hier-cgt-status]').innerText(),/미확정/);
  await page.locator('[data-hier-cancel]').first().click();
  receipt.cases.push({popup:'existing CGT status paragraph updates; cancel remains local'});
  const saved=await page.evaluate(()=>JSON.stringify(state));
  await page.evaluate(saved=>{controller.cleanup();state=JSON.parse(saved);controller=w.default(mount,props());},saved);
  assert.match(await page.locator('.toolbar-status strong').innerText(),/알림이 완료/);
  assert.equal(await page.evaluate(()=>calls.length),callsBefore,'Notice update/reopen started a host operation');
  assert.deepEqual(errors,[]);
  assert.equal(receipt.external_requests,0);
  receipt.cases.push({saved_reopen:'notice retained without a callback or automatic CGT action'});
  await page.evaluate(()=>controller.cleanup());
  receipt.passed=true;
  console.log(JSON.stringify({...receipt,cases:receipt.cases.length}));
}finally{
  await browser.close();
  fs.writeFileSync(path.join(report,'work-start-notice-widget.json'),JSON.stringify(receipt,null,2)+'\n');
}
