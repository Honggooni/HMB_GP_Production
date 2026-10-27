// Installed React/ReactDOM and product helper; a local synthetic SDK owns all
// topology and callbacks. No running editor, account, media or provider access.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import {prepareNativeEditor,nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';
const root = fileURLToPath(new URL("../../", import.meta.url));
const {original,patched}=prepareNativeEditor(root);
const helper = fs.readFileSync(path.join(root, "resources/editor/hmb-color-lut-native-header.js"), "utf8");
const alias = original.indexOf("S=u(p(),1),C=h(),w=x(),T=u(y())");
const runtime = original.slice(0, original.indexOf(",E=`modulepreload`", alias)) + ";";
const jsxStart = original.indexOf("var Wn=s("), jsxEnd = original.indexOf("function Gn(", jsxStart);
const jsx = original.slice(jsxStart, jsxEnd);
assert.match(patched, /hmbLibrary:e\.metadata\?\.library/);
assert.match(patched, /hmbNativeActions=hmbNativeConnectionActions\(e,hmbLibrary,/);
assert.match(patched, /hmbConnectionNode:d\|\|E\[0\]\?\.node,hmbClose:\(\)=>c\(!1\)/);
assert.match(patched, /hmbNativeConnectionMenu\(e,ve\)\}var rzr=/);
assert.match(patched, /children:\[hmbConnectionManager,\(0,R\.jsx\)\(N0r/);
const app = String.raw`
var H8='native-menu-item',U8='menu-icon',W8='menu-label';
window.sdk=[];window.actions=[];window.notices=[];window.held=[];window.deferNext=false;window.failNext=false;window.dirty=0;
var kq={getState:()=>({setDirty:value=>{if(value)window.dirty++}})};
var ig={warning:(...v)=>window.notices.push(v),error:(...v)=>window.notices.push(v)},vg=e=>e?.message||String(e);
window.inventory=new Map();
const initial=name=>({node_name:name,detached:false,state_token:'token-'+name+'-0',can_disconnect:true,can_reconnect:false,details:'',connections:[
{kind:'wire',peer_name:'Video peer',source_node_name:'Video peer',target_node_name:name,source_parameter_name:'video',target_parameter_name:'input',shots:[]},
{kind:'remote',peer_name:'Prompt peer',source_node_name:name,target_node_name:'Prompt peer',source_parameter_name:'',target_parameter_name:'',shots:[{channel_uuid:'channel-kept',shot_uuid:'shot-kept',number:2,name:'Original Shot Name'}]}]});
var Xd={request:async(type,payload)=>{
 window.sdk.push({type,payload:structuredClone(payload)});
 if(type==='HMBCheckNodeDeletionRequest')return {can_delete:false,hmb_node_names:payload.node_names,blocked:{[payload.node_names[0]==='Standard Group'?'Actual HMB Child':payload.node_names[0]]:['peer']}};
 if(window.deferNext){window.deferNext=false;await new Promise(resolve=>window.held.push(resolve));}
 if(window.failNext){window.failNext=false;throw Error('Synthetic stale state token');}
 if(!window.inventory.has(payload.node_name))window.inventory.set(payload.node_name,initial(payload.node_name));
 const previous=window.inventory.get(payload.node_name);
 if(type==='HMBManageNodeConnectionsRequest'){
  if(payload.expected_state_token!==previous.state_token)throw Error('Synthetic stale state token');
  const detached=payload.operation==='disconnect';
  window.inventory.set(payload.node_name,{...initial(payload.node_name),detached,connections:initial(payload.node_name).connections,
   state_token:previous.state_token+'-next',can_disconnect:!detached,can_reconnect:detached,can_forget_missing:false});
 }else if(type!=='HMBGetNodeConnectionsRequest')throw Error('Forbidden synthetic request '+type);
 return structuredClone(window.inventory.get(payload.node_name));
}};
const names=['HMBColorLUTLibrary','HMBAgentLibrary','HMBFinishLookLibrary','HMBImageAssetLibrary','HMBImageBash','HMBImageGeneration','HMBSeedanceGeneration','HMBPromptLibrary','HMBVideoPickerLibrary','FutureArbitraryTool'];
window.nativeItems=(0,R.jsx)('div',{'data-native-menu-original':true,children:['Copy','Duplicate','Reset','Delete'].map(label=>(0,R.jsx)('button',{onClick:()=>window.actions.push(label),children:label},label))});
function Shell(){
 const manager=hmbUseNativeConnectionManager();
 const [menu,setMenu]=(0,S.useState)(null);
 const controls=name=>(0,R.jsx)('div',{'data-original-actions':name,style:{display:'flex',gap:12},children:['lock','reset','run'].map(action=>(0,R.jsx)('button',{onClick:()=>window.actions.push(name+':'+action),children:action},action))});
 return (0,R.jsxs)(R.Fragment,{children:[manager,...names.map(name=>(0,R.jsxs)('div',{'data-node':name,style:{display:'flex',alignItems:'center',gap:20,margin:4},children:[
  (0,R.jsx)('span',{style:{width:220},children:name}),hmbNativeConnectionActions(name,'HMB_GP_Production',controls(name),'native-button',{color:'#aabbcc'})]},name)),
  (0,R.jsx)('div',{'data-non-hmb':true,children:hmbNativeConnectionActions('ordinary','Elsewhere',controls('ordinary'),'native-button',{})}),
  (0,R.jsx)('div',{'data-native-capsule-owner':true,onContextMenu:event=>{event.preventDefault();setMenu(true);},children:hmbNativeStudioCollapsedHeader('Capsule','image',{},()=>window.actions.push('capsule-expand'),false,false)}),
  menu?hmbNativeConnectionMenu({hmbConnectionNode:{id:'Capsule',data:{metadata:{library:'HMB_GP_Production'}}},hmbClose:()=>setMenu(null)},window.nativeItems):null,
  (0,R.jsx)('div',{'data-non-hmb-menu':true,children:hmbNativeConnectionMenu({hmbConnectionNode:{id:'ordinary',data:{metadata:{library:'Elsewhere'}}}},window.nativeItems)})]});
}
window.root=w.createRoot(document.getElementById('app'));window.mount=()=>window.root.render((0,R.jsx)(Shell,{}));window.mount();
window.open=hmbNativeOpenConnections;window.reset=hmbNativeStudioResetCollapseIntents;window.deleteNotice=hmbNativeConnectionDeletionNotice;
window.snapshotValidation=(value,name)=>{try{return !!hmbNativeConnectionSnapshot(value,name)}catch{return false}};
`;
const module = runtime + "\n" + jsx + "\n" + helper + "\n" + app;
const html = '<!doctype html><meta charset="utf-8"><title>Isolated HMB connection manager</title><style>body{background:#172031;color:#eee;font:14px sans-serif}button{cursor:pointer}button:disabled{opacity:.45;cursor:default}.native-menu-item{display:flex;gap:12;padding:9px}.hmb-native-capsule{margin:15px}</style><div id="app"></div><script type="module" src="/fixture.js"></script>';
const server = http.createServer((req, res) => { res.setHeader("Content-Type", req.url === "/fixture.js" ? "text/javascript" : "text/html"); res.end(req.url === "/fixture.js" ? module : html); });
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const { chromium } = nativeTestPlaywright();
let browser, checks = 5;
try {
  browser = await chromium.launch({ executablePath: process.env.HMB_IMAGE_ASSET_TEST_BROWSER || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 960 } });
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.locator('[data-hmb-connection-manager-button="FutureArbitraryTool"]').waitFor();
  assert.equal(await page.locator("[data-hmb-connection-manager-button]").count(), 10); checks++;
  assert.equal(await page.locator("[data-non-hmb] [data-hmb-connection-manager-button]").count(), 0); checks++;
  assert.equal(await page.evaluate(() => window.sdk.length), 0, "Headers never read connection data until opened"); checks++;
  const geometry = await page.locator('[data-hmb-connection-manager-button="FutureArbitraryTool"]').evaluate(element => ({ width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height, color: getComputedStyle(element).color, next: element.nextElementSibling?.textContent }));
  assert.deepEqual(geometry, { width: 24, height: 24, color: "rgb(170, 187, 204)", next: "lock" }); checks++;
  for (const name of ["HMBColorLUTLibrary", "FutureArbitraryTool"]) {
    await page.locator(`[data-hmb-connection-manager-button="${name}"]`).click();
    await page.locator(`[data-hmb-connection-manager="${name}"] article`).first().waitFor();
    assert.equal(await page.locator('[data-hmb-connection-manager] article').count(), 2); checks++;
    assert.match(await page.locator('[data-hmb-connection-manager]').innerText(), /REMOTE[\s\S]*02 · Original Shot Name/); checks++;
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('role')), 'dialog'); checks++;
    if (name === "HMBColorLUTLibrary") {
      await page.setViewportSize({ width: 800, height: 600 });
      const bounds = await page.getByRole('dialog').boundingBox();
      assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= 800 && bounds.y + bounds.height <= 600, 'The centered modal and its controls fit a smaller editor viewport'); checks++;
      if (process.env.HMB_CONNECTION_MANAGER_SCREENSHOT) await page.screenshot({ path: process.env.HMB_CONNECTION_MANAGER_SCREENSHOT });
      await page.setViewportSize({ width: 1200, height: 960 });
    }
    await page.getByRole("button", { name: "연결 해제", exact: true }).click();
    await page.getByRole("button", { name: "다시 연결", exact: true }).waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelector('[data-hmb-connection-manager] button:last-child')?.disabled === false);
    assert.equal(await page.locator('[data-hmb-connections-detached="true"]').count(), 1, 'Detached recipes are visibly distinguished from live connections'); checks++;
    assert.equal(await page.locator('[data-hmb-connection-manager] article').count(), 2, 'The saved peer and Shot recipe stays visible for reconnection'); checks++;
    await page.getByRole("button", { name: "다시 연결", exact: true }).click();
    await page.locator('[data-hmb-connection-manager] article').first().waitFor();
    const request = await page.evaluate(() => window.sdk.filter(row => row.type === 'HMBManageNodeConnectionsRequest').at(-1));
    assert.equal(request.payload.operation, 'reconnect'); assert.match(request.payload.expected_state_token, /-next$/); checks += 2;
    await page.getByRole("button", { name: "연결 관리 닫기" }).click();
    assert.equal(await page.locator('[data-hmb-connection-manager]').count(), 0); checks++;
  }
  await page.evaluate(() => { window.deferNext = true; });
  await page.locator('[data-hmb-connection-manager-button="HMBPromptLibrary"]').click();
  await page.waitForFunction(() => window.held.length === 1);
  await page.evaluate(() => window.open('HMBAgentLibrary'));
  await page.locator('[data-hmb-connection-manager="HMBAgentLibrary"] article').first().waitFor();
  await page.evaluate(() => window.held.shift()());
  await page.waitForTimeout(40);
  assert.equal(await page.locator('[data-hmb-connection-manager]').getAttribute('data-hmb-connection-manager'), 'HMBAgentLibrary', 'Late previous-node snapshots never replace the current modal'); checks++;
  await page.evaluate(() => { window.deferNext = true; });
  const before = await page.evaluate(() => window.sdk.filter(row => row.type === 'HMBManageNodeConnectionsRequest').length);
  await page.getByRole("button", { name: "연결 해제", exact: true }).dblclick({ delay: 50 });
  await page.waitForFunction(() => window.held.length === 1);
  assert.equal(await page.evaluate(() => window.sdk.filter(row => row.type === 'HMBManageNodeConnectionsRequest').length), before + 1); checks++;
  await page.getByRole("button", { name: "연결 관리 닫기" }).click();
  const dirtyBeforeClosedCommit = await page.evaluate(() => window.dirty);
  await page.evaluate(() => window.held.shift()());
  await page.waitForTimeout(40);
  assert.equal(await page.locator('[data-hmb-connection-manager]').count(), 0, 'A completed mutation cannot reopen a closed modal'); checks++;
  assert.equal(await page.evaluate(() => window.dirty), dirtyBeforeClosedCommit + 1, 'A committed operation still marks the workflow dirty after dialog dismissal'); checks++;
  await page.locator('[data-hmb-connection-manager-button="HMBImageBash"]').click();
  await page.locator('[data-hmb-connection-manager] article').first().waitFor();
  await page.evaluate(() => { window.failNext = true; });
  await page.getByRole("button", { name: "연결 해제", exact: true }).click();
  await page.getByRole('alert').waitFor();
  assert.equal(await page.getByRole("button", { name: "연결 해제", exact: true }).isDisabled(), true); checks++;
  assert.equal(await page.getByRole("button", { name: "다시 연결", exact: true }).isDisabled(), true); checks++;
  await page.getByRole("button", { name: "새로고침", exact: true }).click();
  await page.locator('[data-hmb-connection-manager] article').first().waitFor();
  await page.evaluate(() => window.reset());
  await page.waitForFunction(() => !document.querySelector('[data-hmb-connection-manager]'));
  assert.equal(await page.locator('[data-hmb-connection-manager]').count(), 0); checks++;
  await page.evaluate(() => window.inventory.set('Orphan Peer', { node_name:'Orphan Peer',detached:false,state_token:'missing-peer-token',can_disconnect:false,can_reconnect:false,can_forget_missing:true,connections:[],details:'상대가 삭제되었습니다.' }));
  await page.evaluate(() => window.open('Orphan Peer'));
  await page.getByRole('button', {name:'삭제된 연결 기록 정리',exact:true}).waitFor();
  assert.match(await page.locator('[data-hmb-forget-missing-description]').innerText(), /연결 검색이 다시 허용됩니다[\s\S]*입력·결과는 유지되며 새 실행은 하지 않습니다/); checks++;
  assert.equal(await page.getByRole('button',{name:'연결 해제',exact:true}).isDisabled(),true); checks++;
  assert.equal(await page.getByRole('button',{name:'다시 연결',exact:true}).isDisabled(),true); checks++;
  const beforeForgetDirty=await page.evaluate(()=>window.dirty);
  await page.getByRole('button',{name:'삭제된 연결 기록 정리',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('[data-hmb-forget-missing-description]'));
  const forget=await page.evaluate(()=>window.sdk.filter(row=>row.type==='HMBManageNodeConnectionsRequest').at(-1));
  assert.deepEqual(forget.payload,{node_name:'Orphan Peer',operation:'forget_missing',expected_state_token:'missing-peer-token'}); checks++;
  assert.equal(await page.evaluate(()=>window.dirty),beforeForgetDirty+1); checks++;
  assert.equal(await page.getByRole('button',{name:'삭제된 연결 기록 정리',exact:true}).count(),0); checks++;
  assert.equal(await page.evaluate(()=>document.activeElement === document.querySelector('[data-hmb-connection-manager]')),true,'Removing the cleanup action keeps keyboard focus in its dialog'); checks++;
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.querySelector('[data-hmb-connection-manager]'));
  await page.locator('[data-hmb-native-capsule]').click({ button: 'right' });
  await page.locator('[data-hmb-context-connections]').waitFor();
  assert.equal(await page.locator('[data-native-menu-original] button').count(), 8, 'The capsule menu retains Copy, Duplicate, Reset and Delete'); checks++;
  assert.equal(await page.evaluate(() => window.actions.includes('capsule-expand')), false); checks++;
  assert.equal(await page.locator('[data-non-hmb-menu] [data-hmb-context-connections]').count(), 0); checks++;
  await page.locator('[data-hmb-context-connections]').click();
  await page.locator('[data-hmb-connection-manager="Capsule"] article').first().waitFor();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('[data-hmb-connection-manager]').count(), 0); checks++;
  await page.evaluate(() => window.deleteNotice({ node_name: 'Blocked Node' }, '[HMB_DELETE_CONNECTED] connected'));
  assert.equal(await page.evaluate(() => window.notices.at(-1)[1].action.label), '연결 관리'); checks++;
  await page.evaluate(() => window.notices.at(-1)[1].action.onClick());
  await page.locator('[data-hmb-connection-manager="Blocked Node"] article').first().waitFor();
  await page.keyboard.press('Escape');
  await page.evaluate(() => { window.deleteNotice({ node_name: 'Standard Group' }, '[HMB_DELETE_CONNECTED] connected'); window.notices.at(-1)[1].action.onClick(); });
  await page.locator('[data-hmb-connection-manager="Actual HMB Child"] article').first().waitFor();
  assert.equal(await page.evaluate(() => window.sdk.some(row => row.type==='HMBGetNodeConnectionsRequest' && row.payload.node_name==='Standard Group')), false, 'A refused standard group opens its actual HMB child'); checks++;
  assert.equal(await page.evaluate(() => window.snapshotValidation({ node_name: 'Other' }, 'Blocked Node')), false); checks++;
  await page.evaluate(() => { window.deleteNotice({ node_name: 'Previous Flow' }, '[HMB_DELETE_CONNECTED] connected'); window.reset(); });
  const beforeStaleAction = await page.evaluate(() => window.sdk.length);
  await page.evaluate(() => window.notices.at(-1)[1].action.onClick());
  await page.waitForTimeout(30);
  assert.equal(await page.evaluate(() => window.sdk.length), beforeStaleAction, 'A previous-workflow notification cannot query a same-named node in the new workflow'); checks++;
  const idle = await page.evaluate(() => window.sdk.length);
  await page.waitForTimeout(120);
  assert.equal(await page.evaluate(() => window.sdk.length), idle, 'The modal never polls in the background'); checks++;
  await page.evaluate(() => window.root.unmount());
  await page.evaluate(() => window.open('Unmounted'));
  await page.waitForTimeout(50);
  assert.equal(await page.evaluate(() => window.sdk.length), idle, 'Unmount removes the public open listener'); checks++;
  assert.deepEqual(errors, []); checks++;
  console.log(JSON.stringify({ status: 'PASS', checks, identity: 'metadata.library, including an unknown future type', runtime: 'installed React/ReactDOM', sdk: 'synthetic state-token protected requests', original_context_items_preserved: true, live_editor_actions: 0, paid_calls: 0 }));
} finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
