// Boot the vendor editor, including its real React router, in an isolated iframe.
// The parent implements the local Desktop bridge against one in-memory workflow.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {nativeTestBrowserPath, nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const stockPath=process.env.HMB_STOCK_EDITOR_0130_SOURCE;
const overlayPath=process.env.HMB_HEADER_0130_CANDIDATE;
const assets=path.dirname(stockPath);
const origin='http://127.0.0.1:12732';
const editorHtml=fs.readFileSync(path.join(assets,'..','index-editor.html'),'utf8');
assert.ok(editorHtml.includes(path.basename(stockPath)));
const sha=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const stockHash=sha(stockPath);
assert.equal(stockHash,'547cd4cc14430531d96b865d2d45f1263f32b260f0108300acd0f6ed4cd4a1b4');
const evidence=process.env.HMB_LIFECYCLE_REPORT_DIR;
if(evidence)fs.mkdirSync(evidence,{recursive:true});
const browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});

function parentBridge() {
  const origin=location.origin;
  window.calls=[];
  const workflow={workflow_id:'00000000-0000-4000-8000-000000000132',name:'workflow_1',display_name:'workflow_1',is_saved:false};
  let open=false;
  function result(type,args) {
    switch(type) {
      case 'ListOpenWorkflowsRequest': return {open_workflows:open?[workflow]:[]};
      case 'OpenWorkflowRequest': open=true;return {open_workflow:workflow};
      case 'ListAllWorkflowsRequest': return {workflows:{}};
      case 'GetTopLevelFlowRequest': return {flow_name:'main'};
      case 'GetWorkflowMetadataRequest': return {metadata:{}};
      case 'HMBShotBasketRequest': return {data:{status:'empty',flow_name:args.payload.flow_name,projects:[{project_id:'fixture-project'}],shots:[]}};
      case 'ListFlowsInWorkflowRequest': return {flow_names:['main']};
      case 'ListNodesInFlowRequest': return {node_names:[],nodes:[]};
      case 'ListConnectionsForFlowRequest': return {connections:[]};
      default:return {};
    }
  }
  addEventListener('message',({data,source,origin:sender})=>{
    if(sender!==origin||source!==document.querySelector('iframe')?.contentWindow||!data) return;
    const send=message=>source.postMessage(message,origin);
    if(data.type==='IFRAME_READY'){
      send({type:'IFRAME_READY_ACK',requestId:data.requestId,config:{parentOrigin:origin,apiBaseUrl:origin,wsUrl:'ws://127.0.0.1:12732/ws',sessionId:'fixture-session'},user:{id:'fixture'},isAuthenticated:true});
      send({type:'CONNECTION_STATE',isConnected:true});
      send({type:'SESSION_STATE',sessionId:'fixture-session',connectionState:'connected',isBeating:true,engineVersion:'0.106.0',engineReady:true,engineGeneration:1,engineRunId:'fixture-run',engineOs:'windows',responseTopic:'fixture-response'});
      send({type:'ENGINE_STATE',engines:[]});
    }else if(data.type==='API_REQUEST'){
      send({type:'API_RESPONSE',requestId:data.requestId,status:200,statusText:'OK',headers:{'content-type':'application/json'},body:'{}'});
    }else if(data.type==='WS_SEND'){
      const req=data.data?.payload;
      if(!req) return;
      const type=req.request_type, args=req.request??req.payload??{};
      calls.push({type,args,raw:req});
      send({type:'WS_EVENT',subscriptionId:req.request_id,eventType:'RequestSuccess',data:result(type,args),
        request:req,resultType:'success',openWorkflowId:req.open_workflow_id});
    }
  });
}

const page=await browser.newPage({viewport:{width:1300,height:850}});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
const external=new Set();
let serveOverlay=false;
await page.route('**/*',route=>{
  const url=new URL(route.request().url());
  if(url.origin!==origin){external.add(url.hostname);return route.abort();}
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:
    '<!doctype html><script>('+parentBridge.toString()+')()</script><iframe style="width:100%;height:96vh;border:0" src="/index-editor.html"></iframe>'});
  if(url.pathname==='/index-editor.html')return route.fulfill({contentType:'text/html',body:editorHtml});
  if(!url.pathname.startsWith('/assets/'))return route.fulfill({status:404,body:''});
  const name=path.basename(url.pathname),file=serveOverlay&&name===path.basename(stockPath)?overlayPath:path.join(assets,name);
  if(!fs.existsSync(file))return route.fulfill({status:404,body:''});
  const ext=path.extname(file),type={'.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'}[ext];
  return route.fulfill({path:file,contentType:type??'application/octet-stream'});
});
try{
  await page.goto(origin);
  const frame=page.frameLocator('iframe');
  const startup=frame.getByRole('dialog',{name:'HMB 로동마트'});
  await frame.getByRole('heading',{name:'Workflows',exact:true}).waitFor({timeout:12000});
  assert.equal(await startup.count(),0);
  assert.equal(await frame.getByRole('button',{name:'HMB 로동마트',exact:true}).count(),0);
  serveOverlay=true;
  await page.reload();
  await startup.waitFor({timeout:12000});
  if(evidence)await startup.screenshot({path:path.join(evidence,'rodong-startup-0132.png')});
  await startup.getByRole('button',{name:'로동 작업 계속'}).click();
  await frame.getByRole('button',{name:'HMB 로동마트',exact:true}).click();
  await startup.locator('.hmb-shot-basket-launcher button').click();
  const basket=frame.getByRole('dialog',{name:'샷 바구니'});
  await basket.waitFor({timeout:12000});
  await basket.getByText('fixture-project',{exact:true}).waitFor({state:'attached'});
  await basket.getByRole('combobox',{name:'프로젝트'}).selectOption('fixture-project');
  assert.equal(await basket.getByRole('button',{name:'샷 바구니 들기'}).isEnabled(),true);
  if(evidence)await basket.screenshot({path:path.join(evidence,'rodong-basket-0132.png')});
  await basket.getByRole('button',{name:'샷 바구니 닫기'}).click();
  await basket.waitFor({state:'hidden'});
  await frame.locator('.hmb-shot-basket-launcher button:visible').click();
  await basket.waitFor();
  await page.keyboard.press('Escape');
  await basket.waitFor({state:'hidden'});
  const calls=await page.evaluate(()=>window.calls);
  const prepared=calls.filter(row=>row.type==='HMBShotBasketRequest'&&row.args.action==='prepare');
  assert.equal(prepared.length,1);
  assert.equal(calls.filter(row=>row.type==='OpenWorkflowRequest').length,1);
  assert.equal(prepared[0].raw.open_workflow_id,'00000000-0000-4000-8000-000000000132');
  assert.equal(prepared[0].args.payload.flow_name,'main');
  assert.equal(prepared[0].args.payload.workflow_name,'workflow_1');
  assert.deepEqual(errors,[]);
  if(evidence)fs.writeFileSync(path.join(evidence,'rodong-launch-0132.json'),JSON.stringify({
    passed:true,stock_sha256:stockHash,candidate_sha256:sha(overlayPath),
    surface:'Complete Desktop Editor in Chromium with an in-memory parent and engine',
    stock_workflows_lacks_launcher:true,startup_continue:true,reopened_from_workflows:true,project_select:true,canvas_reopen_and_escape:true,
    open_workflow_requests:1,prepare_requests:1,prepare_workflow_id:prepared[0].raw.open_workflow_id,
    external_requests_sent:0,blocked_external_hosts:[...external],page_errors:errors,
  },null,2)+'\n');
  console.log('Desktop startup, continue, reopen, workflow creation and basket preparation/close: PASS');
}catch(error){
  console.error(await page.frames().at(-1).locator('body').innerText().catch(()=>''), errors,
    await page.evaluate(()=>[...new Set(window.calls.map(row=>row.type))]));
  console.error(await page.evaluate(()=>window.calls.slice(-1)));
  throw error;
}finally{await browser.close();}
