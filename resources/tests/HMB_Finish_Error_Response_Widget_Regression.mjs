// Offline browser-only error responses. No live Griptape, provider or server.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const report=path.join(root,'reports/local-v0838-error-audit-20261028');
fs.mkdirSync(report,{recursive:true});
const receipt={schema:'hmb-finish-error-response-browser-v1',external_requests:0,
  paid_calls:0,live_graph_actions:0,cases:[],passed:false};
const browser=await nativeTestPlaywright().chromium.launch({
  headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
try{
  const page=await browser.newPage({viewport:{width:1100,height:1000}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
  await page.setContent('<div id="mount" style="width:980px;height:850px"></div>');
  await page.evaluate(async source=>{
    window.widget=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
    window.runFailure=async(status,language)=>{
      const host=document.querySelector('#mount');
      const canonical=widget.hmbNormalizeFinishLookWidgetValue({language});
      canonical.finish_look.beauty.enabled=true;
      const original=structuredClone(canonical);
      let mode=status,revision=1;
      const calls=[];
      const clock={schema:'hmb-finish-ui-transport',version:1,session_id:'offline-session',
        revision,target_revisions:{__standalone__:revision},status:'state',
        client_id:'',client_epoch:'',request_id:'',sequence:0};
      let controller;
      const props={value:{...structuredClone(canonical),ui_transport:clock},onChange:payload=>{
        calls.push(structuredClone(payload));
        return Promise.resolve().then(()=>{
          const command=payload.ui_transport,reply=structuredClone(canonical);
          if(command.operation==='edit' && mode==='accepted'){
            Object.assign(canonical,widget.hmbFinishLookPublication(payload));
            Object.assign(reply,structuredClone(canonical));revision++;
          }
          reply.ui_transport={...clock,revision,target_revisions:{__standalone__:revision},
            status:command.operation==='refresh'?'refreshed':mode,
            client_id:command.client_id,client_epoch:'offline-client-lease',
            request_id:command.request_id,sequence:command.sequence};
          controller.update({...props,value:reply});
        });
      }};
      controller=widget.default(host,props);
      const edit=()=>{
        const toggle=host.querySelector('[data-enable="beauty"]');
        toggle.checked=false;toggle.dispatchEvent(new Event('change',{bubbles:true}));
      };
      edit();await new Promise(resolve=>setTimeout(resolve,40));
      const failure={
        status:host.querySelector('[data-status]').textContent,
        tone:host.querySelector('[data-status]').dataset.tone,
        current:widget.hmbFinishLookPublication(host.__hmbFinishLookLatestProps.value),
        draft:structuredClone(host.__hmbFinishLookUnappliedDraft?.at(-1)),
        operations:calls.map(row=>row.ui_transport.operation),
      };
      mode='accepted';edit();await new Promise(resolve=>setTimeout(resolve,40));
      const recovery={tone:host.querySelector('[data-status]').dataset.tone,
        enabled:host.__hmbFinishLookLatestProps.value.finish_look.beauty.enabled,
        original,failedEdits:calls.filter(row=>row.ui_transport.operation==='edit').length};
      controller.cleanup();
      return {failure,recovery,expected:widget.hmbFinishLookTransportFailureMessage(status,language)};
    };
  },fs.readFileSync(path.join(root,'widgets/HMBFinishLookLibraryWidget.js'),'utf8'));
  const patterns={
    conflict:[/충돌/,/state changed/],
    target_unavailable:[/선택한 샷.*사용할 수 없어/,/selected Shot is unavailable/],
    remote_locked:[/REMOTE 연결 중/,/locked by REMOTE/],
    stale_session:[/세션이 변경/,/session changed/],
    stale_client:[/편집 연결이 만료/,/connection expired/],
    stale_sequence:[/이전 요청/,/older than/],
    invalid_command:[/요청의 형식/,/request is invalid/],
  };
  for(const [status,patternsForStatus] of Object.entries(patterns)){
    for(const [index,language] of ['ko','en'].entries()){
      const result=await page.evaluate(({status,language})=>runFailure(status,language),{status,language});
      assert.match(result.failure.status,patternsForStatus[index],status+' '+language);
      assert.equal(result.failure.status,result.expected);
      assert.equal(result.failure.tone,'error');
      assert.deepEqual(result.failure.current,result.recovery.original,'Rejected edit changed canonical state');
      assert.equal(result.failure.draft.finish_look.beauty.enabled,false,'Rejected user draft was lost');
      assert.equal(result.failure.operations.filter(item=>item==='edit').length,1,'Rejected edit was resubmitted');
      if(['stale_session','stale_client'].includes(status)){
        assert.deepEqual(result.failure.operations,['refresh','edit','refresh'],
          'Expired transport must recover by read-only refresh while retaining the reason');
      }
      assert.equal(result.recovery.enabled,false,'Next accepted edit did not apply');
      assert.notEqual(result.recovery.tone,'error','Accepted edit retained an obsolete failure notice');
      receipt.cases.push({status,language,canonical_preserved:true,draft_preserved:true,
        rejected_edit_submissions:1,recovery:'accepted next edit clears reason'});
    }
  }
  assert.deepEqual(errors,[]);
  assert.equal(receipt.external_requests,0);
  receipt.passed=true;
  console.log(JSON.stringify({...receipt,cases:receipt.cases.length}));
}finally{
  await browser.close();
  fs.writeFileSync(path.join(report,'finish-error-response-browser.json'),JSON.stringify(receipt,null,2)+'\n');
}
