// Real product header in isolated headless Chromium; no Desktop or live sources.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
import * as widget from '../../widgets/HMBImageBashWidget.js';

const preparation={schema:widget.HMB_IMAGE_BASH_PREPARATION_SCHEMA,phase:'preparing',ready:false,
 workspace_id:'workspace',workspace_revision:5,channel_uuid:'channel',node_instance_uuid:'bash-instance',
 requested_count:5,prepared_count:0,error:''};
const state={schema:widget.HMB_IMAGE_BASH_HEADER_SCHEMA,
 sources:[{id:'Assets',label:'HMB ImageAsset Library',workspace_id:'workspace',source_instance_id:'source-instance'}],
 bound_source:'Assets',image_count:2,status:'old retained state',locked:false,preparation,
 route:{connected:true,source_node_name:'Assets',target_node_name:'Bash',source_parameter:'IMAGE_BASH_IMAGES_OUT',context_source_parameter:'IMAGE_BASH_CONTEXT_OUT'},
 preserved:{zero:0,off:false,literal:''}};
assert.equal(widget.hmbImageBashPreparation({}).ready,true,'Legacy/blank header remains openable');
assert.equal(widget.hmbImageBashPreparation({...preparation,phase:'error',ready:true}).ready,false);
assert.equal(widget.hmbImageBashPreparation({...preparation,requested_count:-1}).requested_count,null);
assert.equal(widget.hmbImageBashPreparation({...preparation,workspace_revision:'5'}).workspace_revision,0);
const source=fs.readFileSync(new URL('../../widgets/HMBImageBashWidget.js',import.meta.url),'utf8');
const html=`<!doctype html><meta charset="utf-8"><style>body{background:#101420;color:white}.react-flow__node{width:800px}</style>
<div class="react-flow__nodes"><div class="react-flow__node" data-id="Bash"><div id="widget"></div><button id="native-open">Open HMBImageBash Editor</button></div></div>
<script type="module">import mount from '/widget.js';window.state=${JSON.stringify(state)};window.writes=[];
window.props=()=>({value:window.state,onChange:value=>window.writes.push(structuredClone(value))});
window.controller=mount(document.getElementById('widget'),window.props());window.header=document.querySelector('[data-hmb-image-bash-header]');
window.update=patch=>{window.state={...window.state,...patch};window.controller.update(window.props())};window.ready=true;</script>`;
const server=http.createServer((request,response)=>{response.setHeader('Content-Type',request.url==='/widget.js'?'text/javascript':'text/html');response.end(request.url==='/widget.js'?source:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await nativeTestPlaywright().chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
 const page=await browser.newPage({viewport:{width:1000,height:650}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
 assert.equal(await page.locator('[data-bash-count]').textContent(),'이미지 5 · 준비 중','Pending count must not use retained records count 2');
 assert.equal(await page.locator('[data-bash-status]').textContent(),'작업 준비 중 · 이미지 원본을 확인합니다');
 assert.equal(await page.locator('[data-hmb-image-bash-header]').getAttribute('aria-busy'),'true');
 assert.equal(await page.locator('[data-bash-count]').getAttribute('data-loading'),'true');
 assert.equal(await page.locator('[data-bash-retry]').isVisible(),false);
 await page.evaluate(()=>window.update({preparation:{...window.state.preparation,phase:'error',ready:false,error:'원본을 읽을 수 없습니다'}}));
 assert.equal(await page.locator('[data-bash-status]').textContent(),'원본을 읽을 수 없습니다');
 assert.equal(await page.locator('[data-bash-retry]').isVisible(),true);
 await page.locator('[data-bash-retry]').click();
 const request=await page.evaluate(()=>window.writes.at(-1));
 assert.deepEqual(request.preserved,{zero:0,off:false,literal:''});
 assert.equal(request.hmb_image_bash_command.operation,'retry_inputs');
 assert.equal(request.hmb_image_bash_command.source_instance_id,'source-instance');
 assert.equal(request.hmb_image_bash_command.workspace_id,'workspace');
 assert.equal(request.hmb_image_bash_command.source_node_name,'Assets');
 await page.evaluate(()=>window.update({status:'입력이 변경되었습니다 · 편집기에서 Apply 필요',preparation:{...window.state.preparation,phase:'ready',ready:true,prepared_count:5}}));
 assert.equal(await page.locator('[data-bash-count]').textContent(),'이미지 5');
 assert.equal(await page.locator('[data-hmb-image-bash-header]').getAttribute('aria-busy'),'false');
 assert.equal(await page.locator('[data-bash-retry]').isVisible(),false);
 assert.equal(await page.evaluate(()=>window.header===document.querySelector('[data-hmb-image-bash-header]')),true,'Ready updates preserve the mounted header');
 await page.evaluate(()=>window.update({image_count:0,bound_source:'',sources:[],route:{connected:false},preparation:{schema:'hmb-image-bash-preparation-v1',phase:'idle',ready:true,requested_count:null,prepared_count:0}}));
 assert.equal(await page.locator('[data-bash-count]').textContent(),'이미지 0');
 assert.equal(await page.locator('[data-bash-source]').isEnabled(),true,'Blank source selection remains usable');
 assert.equal(await page.locator('#native-open').isEnabled(),true,'Header does not intercept unrelated native controls');
 assert.equal(await page.locator('[data-hmb-image-bash-header]').evaluate(node=>node.getBoundingClientRect().height),64);
 assert.doesNotMatch(await page.locator('[data-hmb-image-bash-header]').textContent(),/%/);
 await page.evaluate(()=>window.controller.cleanup());assert.equal(await page.locator('[data-bash-retry]').count(),0);
 assert.deepEqual(errors,[]);
 console.log('HMB_IMAGE_BASH_READINESS_WIDGET=PASS (pending/current counts, busy/ready/error, scoped retry, stable mount, blank canvas, cleanup; isolated Chromium)');
}finally{await browser?.close();server.closeAllConnections?.();await new Promise(resolve=>server.close(resolve));}
