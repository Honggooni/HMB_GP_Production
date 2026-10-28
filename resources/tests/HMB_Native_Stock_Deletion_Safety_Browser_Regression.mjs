import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright,readNativeEditorSource,regressionPython} from './_hmb_native_editor_fixture.mjs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const playwright=nativeTestPlaywright();
const root=fileURLToPath(new URL('../..',import.meta.url));
const names=['HMBAgentLibraryWidget.js','HMBColorLUTLibraryWidget.js','HMBFinishLookLibraryWidget.js','HMBImageAssetLibraryWidget.js','HMBImageBashWidget.js','HMBImageGenerationWidget.js','HMBPromptLibraryScopedBindingWidget.js','HMBSeedanceGenerationWidget.js','HMBVideoPickerLibraryWidget_v032.js'];
const sources=names.map(name=>fs.readFileSync(path.join(root,'widgets',name),'utf8'));
const block=text=>text.slice(text.indexOf('// HMB_NATIVE_STOCK_SAFETY_V1_BEGIN'),text.indexOf('// HMB_NATIVE_STOCK_SAFETY_V1_END')).replace(/\r\n?/g,'\n');
for(const text of sources){assert.ok(text.includes('return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation)'));assert.equal(block(text),block(sources[0]));}
const source=sources[0]+'\nexport {hmbAcquireNativeStockSafety,hmbNativeStockSafetyContract};';
const browser=await playwright.chromium.launch({executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const cases=[],errors=[],report={schema:'hmb-native-stock-deletion-safety/v1',passed:false,cases,paid_calls:0,live_app_calls:0,external_requests:0,source_sha256:names.map((name,i)=>({file:name,sha256:createHash('sha256').update(sources[i]).digest('hex')}))};
const sync=spawnSync(regressionPython(root),['-B',path.join(root,'tools/sync_hmb_native_stock_safety.py'),'--check'],{cwd:root,encoding:'utf8'});assert.equal(sync.status,0,sync.stdout+sync.stderr);
const stock=readNativeEditorSource(root);const start=stock.indexOf('bn=(0,S.useCallback)(e=>{let t=E.current,r=t?e.map'),end=stock.indexOf(',xn=(0,S.useCallback)',start);assert.ok(start>0&&end>start);const callback=stock.slice(start+3,end);
const fa=stock.indexOf('o=m(`DeleteNodeResultFailure`,'),fb=stock.indexOf(',s=m(`DeleteConnectionResultSuccess`',fa);assert.ok(fa>0&&fb>fa);const failure=stock.slice(fa+2,fb);
try{
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',r=>{report.external_requests++;return r.abort();});
 await page.setContent(`<main class="react-flow"><div class="react-flow__node selected" data-id="HMB_A"><button data-trash><svg class="lucide lucide-trash"></svg></button><div data-widget><button data-inner-trash><svg class="lucide lucide-trash"></svg></button><input data-input value="keep text"></div></div><div class="react-flow__node" data-id="Standard"><button data-standard-trash><svg class="lucide lucide-trash"></svg></button></div><div class="react-flow__node react-flow__node-GroupNode" data-id="Group"></div><div class="react-flow__panel"><button data-batch><svg class="lucide lucide-trash"></svg></button></div></main><div data-menu><button>Delete Node <span>Del</span></button></div><aside><button data-setting-delete><svg class="lucide lucide-trash"></svg>Delete secret</button></aside>`);
 await page.evaluate(async source=>{
  window.safety=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
  window.counts={native:0,inner:0,setting:0,keys:0};window.node=document.querySelector('[data-id=HMB_A]');window.container=node.querySelector('[data-widget]');container.setAttribute('data-hmb-native-node-type','HMBImageAssetLibrary');
  window.guardListeners={add:[],remove:[]};
  for(const [method,key]of [['addEventListener','add'],['removeEventListener','remove']]){const original=window[method];window[method]=function(type,listener,options){if(options===true&&['keydown','click','contextmenu'].includes(type))guardListeners[key].push(type);return Reflect.apply(original,this,[type,listener,options]);};}
  window.lease=safety.hmbAcquireNativeStockSafety(container);lease.refresh();
  for(const sel of ['[data-trash]','[data-standard-trash]','[data-batch]','[data-menu] button'])document.querySelector(sel).addEventListener('click',()=>{counts.native++;});
  document.querySelector('[data-inner-trash]').addEventListener('click',()=>counts.inner++);document.querySelector('[data-setting-delete]').addEventListener('click',()=>counts.setting++);window.addEventListener('keydown',()=>counts.keys++);
 },source);
 const check=async(name,fn)=>{await fn();cases.push(name);};
 await check('persistent_status_and_no_node_layout_mutation',async()=>{assert.equal(await page.locator('[data-hmb-native-safety-status]').count(),1);assert.equal(await page.locator('[data-id=HMB_A]').count(),1);assert.match(await page.locator('[data-hmb-native-safety-status]').getAttribute('aria-label'),/Override.*재시작/);assert.doesNotMatch(await page.locator('[data-hmb-native-safety-status]').textContent(),/적용 완료|업데이트 완료|설치 완료/);});
 for(const [name,sel]of [['native_trash','[data-trash]'],['trash_svg_target','[data-trash] svg'],['batch_trash','[data-batch]']])await check(name+'_captured_before_native_callback',async()=>{await page.locator(sel).click();assert.equal(await page.evaluate(()=>counts.native),0);assert.equal(await page.locator('[data-hmb-native-safety-notice]').count(),1);const notice=await page.locator('[data-hmb-native-safety-notice]').textContent();for(const phrase of ['Override','current/applied','작업 저장','Griptape 완전 종료','재시작','디스크 파일 상태','보장하지 않습니다','실패','로그','다른 삭제 경로'])assert.ok(notice.includes(phrase),phrase);assert.doesNotMatch(notice,/ZIP|Install_HMB|\.ps1|적용 완료|업데이트 완료|설치 완료|연결된 노드는 계속 보호/i);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('Delete_Backspace_and_repeats_are_blocked',async()=>{const result=await page.evaluate(()=>{for(const key of ['Delete','Backspace','Delete']){const e=new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true});window.dispatchEvent(e);if(!e.defaultPrevented)throw Error('Missing key capture');}return counts.keys;});assert.equal(result,0);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('input_text_deletion_kept',async()=>{await page.locator('[data-input]').focus();await page.keyboard.press('End');await page.keyboard.press('Backspace');assert.equal(await page.locator('[data-input]').inputValue(),'keep tex');assert.equal(await page.locator('[data-hmb-native-safety-notice]').count(),0);});
 await check('internal_asset_or_shot_delete_and_settings_untouched',async()=>{await page.locator('[data-inner-trash]').click();await page.locator('[data-setting-delete]').click();assert.deepEqual(await page.evaluate(()=>[counts.inner,counts.setting,counts.native]),[1,1,0]);});
 await check('unselected_HMB_context_menu_and_keyboard_button_activation_protected',async()=>{await page.evaluate(()=>node.classList.remove('selected'));await page.locator('[data-trash]').click({button:'right'});await page.locator('[data-menu] button').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>counts.native),0);assert.equal(await page.locator('[data-hmb-native-safety-notice]').count(),1);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('external_node_only_selection_normal_delete',async()=>{await page.evaluate(()=>{document.querySelector('[data-id=Standard]').classList.add('selected');});await page.locator('[data-standard-trash]').click();assert.equal(await page.evaluate(()=>counts.native),1);});
 await check('mixed_selection_is_all_or_none',async()=>{await page.evaluate(()=>node.classList.add('selected'));await page.locator('[data-batch]').click();assert.equal(await page.evaluate(()=>counts.native),1);assert.equal(await page.locator('[data-id]').count(),3);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('HMB_canvas_group_ownership_unknown_waits_for_native_restart',async()=>{await page.evaluate(()=>{for(const n of document.querySelectorAll('.selected'))n.classList.remove('selected');document.querySelector('[data-id=Group]').classList.add('selected');});await page.locator('[data-batch]').click();assert.equal(await page.evaluate(()=>counts.native),1);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('old_native_marker_without_version_cannot_bypass_safety',async()=>{await page.evaluate(()=>document.documentElement.setAttribute('data-hmb-native-deletion-guard','engine-preflight'));await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),1);assert.equal(await page.locator('[data-hmb-native-safety-status]').count(),1);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('old_native_protection_version_cannot_bypass_safety',async()=>{await page.evaluate(()=>document.documentElement.setAttribute('data-hmb-native-deletion-protection-version','1'));await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),1);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('native_marker_hands_off_without_replayed_delete',async()=>{await page.evaluate(()=>{document.documentElement.setAttribute('data-hmb-native-deletion-protection-version','2');});await page.waitForFunction(()=>!document.querySelector('[data-hmb-native-safety-status]'));await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),2);assert.equal(await page.locator('[data-hmb-native-safety-notice]').count(),0);});
 await check('marker_removed_hot_Git_reload_restores_failclosed',async()=>{await page.evaluate(()=>{document.documentElement.removeAttribute('data-hmb-native-deletion-guard');node.classList.add('selected');});await page.waitForSelector('[data-hmb-native-safety-status]');await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),2);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('leases_share_one_global_status_capture_and_cleanup_preserves_other_owner',async()=>{assert.deepEqual(await page.evaluate(()=>{window.second=safety.hmbAcquireNativeStockSafety(container);second.refresh();lease.cleanup();return[document.querySelectorAll('[data-hmb-native-safety-status]').length,document.__HMB_NATIVE_STOCK_SAFETY_V1__.owners.size,guardListeners.add.length,guardListeners.remove.length]}),[1,1,3,0]);await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),2);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('all_widgets_unmounted_by_stock_fold_keeps_outer_node_protected',async()=>{await page.evaluate(()=>{second.cleanup();container.remove();});await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),2);assert.equal(await page.locator('[data-hmb-native-safety-status]').count(),1);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('offscreen_or_hidden_outer_identity_without_widgets_still_protects_Delete',async()=>{assert.equal(await page.evaluate(()=>{node.style.display='none';const event=new KeyboardEvent('keydown',{key:'Delete',bubbles:true,cancelable:true});window.dispatchEvent(event);node.style.display='';return event.defaultPrevented;}),true);assert.equal(await page.evaluate(()=>counts.native),2);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('native_rename_while_widget_unmounted_preserves_same_outer_identity_protection',async()=>{await page.evaluate(()=>node.setAttribute('data-id','Renamed_HMB'));await page.locator('[data-trash]').click();assert.equal(await page.evaluate(()=>counts.native),2);await page.getByRole('button',{name:'확인',exact:true}).click();});
 await check('actual_outer_node_removed_releases_last_capture_observer_and_status',async()=>{await page.evaluate(()=>node.remove());await page.waitForFunction(()=>document.__HMB_NATIVE_STOCK_SAFETY_V1__===undefined);assert.equal(await page.locator('[data-hmb-native-safety-status]').count(),0);assert.deepEqual(await page.evaluate(()=>guardListeners.remove.slice().sort()),['click','contextmenu','keydown']);await page.locator('[data-standard-trash]').click();assert.equal(await page.evaluate(()=>counts.native),3);});
 await check('exact_pristine_stock_callback_reproduces_optimistic_remove_before_failure',async()=>{
  const actual=await page.evaluate(({callback,failure})=>{
   window.makeStock=()=>{
    const nodes=[{id:'ExactHMB',type:'CustomNode',data:{metadata:{library:'HMB_GP_Production'}}}],calls=[],clears=[];
    const env={console:{error(){}},S:{useCallback:fn=>fn},E:{current:null},w:{current:nodes},b:nodes,N:{showHelperLines:false},Ct:{current:{}},
     Xd:{send:(name,args)=>calls.push([name,args])},Dt:id=>clears.push(id),Et:()=>clears.push('pending-edits'),
     C:changes=>{for(const row of changes)if(row.type==='remove'){const i=nodes.findIndex(n=>n.id===row.id);if(i>=0)nodes.splice(i,1);}},
     x(){},yn(){},on(){},Zt(){},A(){},Ve(){},Ue(){},ze(){throw Error('Unexpected group')},ut(){throw Error('Unexpected dot')},m:(_name,fn)=>fn};
    return{nodes,calls,clears,handler:Function('env',`with(env){return (${callback});}`)(env),failure:Function('env',`with(env){return (${failure});}`)(env)};
   };
   const f=makeStock();f.handler([{type:'remove',id:'ExactHMB'}]);f.failure({result_details:'HMB_DELETE_CONNECTED'},{node_name:'ExactHMB'});
   return{removed:f.nodes.length===0,sent:f.calls[0][0],clears:f.clears};
  },{callback,failure});
  assert.deepEqual(actual,{removed:true,sent:'DeleteNodeRequest',clears:['ExactHMB','pending-edits']});
 });
 await check('capture_prevents_exact_stock_callback_and_cache_mutation_before_request',async()=>{
  await page.evaluate(()=>{
   window.exact=makeStock();window.exactNode=document.createElement('div');exactNode.className='react-flow__node selected';exactNode.setAttribute('data-id','ExactHMB');
   exactNode.innerHTML='<button data-exact-trash><svg class="lucide lucide-trash"></svg></button><div data-exact-widget></div>';document.querySelector('.react-flow').append(exactNode);
   exactNode.querySelector('button').addEventListener('click',()=>exact.handler([{type:'remove',id:'ExactHMB'}]));window.exactLease=safety.hmbAcquireNativeStockSafety(exactNode.querySelector('[data-exact-widget]'));exactLease.refresh();
  });
  await page.locator('[data-exact-trash]').click();assert.deepEqual(await page.evaluate(()=>({nodes:exact.nodes.length,calls:exact.calls.length,clears:exact.clears.length})),{nodes:1,calls:0,clears:0});
  await page.getByRole('button',{name:'확인',exact:true}).click();await page.evaluate(()=>{exactLease.cleanup();exactNode.remove();});await page.waitForFunction(()=>!document.__HMB_NATIVE_STOCK_SAFETY_V1__);
 });
 await check('nine_standalone_wrappers_preserve_props_handle_identity_final_flush_and_hot_mount',async()=>{
  const result=await page.evaluate(async sources=>{
   const results=[];
   for(let i=0;i<sources.length;i++){
    const mod=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(sources[i]+'\nexport {hmbNativeStockSafetyContract};'))));
    const outer=document.createElement('div');outer.className='react-flow__node';outer.setAttribute('data-id','Wrapper'+i);const container=document.createElement('div');outer.append(container);document.querySelector('.react-flow').append(outer);
    const original={value:{shots:[{name:'Kept shot',uuid:'kept-id'}],task:'job-kept',result:'kept-output'}},serialized=JSON.stringify(original);
    let updates=0,cleanups=0,exact=false;const base={update(next){updates++;exact=next===original;},cleanup(){cleanups++;}};
    const mount=()=>base,first=mod.hmbNativeStockSafetyContract(container,original,mount),again=mod.hmbNativeStockSafetyContract(container,original,mount);
    again.update(original);first.cleanup();first.cleanup();
    const retained=document.__HMB_NATIVE_STOCK_SAFETY_V1__?.owners.size===0;
    const rebound=mod.hmbNativeStockSafetyContract(container,original,mount);const hotOwners=document.__HMB_NATIVE_STOCK_SAFETY_V1__.owners.size;rebound.cleanup();outer.remove();
    await new Promise(resolve=>setTimeout(resolve,0));
    results.push({same:first===again,updates,cleanups,exact,retained,hotOwners,unchanged:JSON.stringify(original)===serialized,released:!document.__HMB_NATIVE_STOCK_SAFETY_V1__});
   }
   return results;
  },sources);
  assert.equal(result.length,9);for(const row of result)assert.deepEqual(row,{same:true,updates:1,cleanups:2,exact:true,retained:true,hotOwners:1,unchanged:true,released:true});
 });
 await check('measurement_widget_without_native_outer_node_does_not_create_a_status',async()=>{
  const result=await page.evaluate(()=>{const c=document.createElement('div');document.body.append(c);const l=safety.hmbAcquireNativeStockSafety(c);l.refresh();const count=document.querySelectorAll('[data-hmb-native-safety-status]').length;l.cleanup();c.remove();return{count,released:!document.__HMB_NATIVE_STOCK_SAFETY_V1__};});assert.deepEqual(result,{count:0,released:true});
 });
 assert.deepEqual(errors,[]);assert.equal(report.external_requests,0);report.passed=true;
}finally{await browser.close();report.errors=errors;const p=process.argv.indexOf('--evidence-path');if(p>=0){fs.mkdirSync(path.dirname(process.argv[p+1]),{recursive:true});fs.writeFileSync(process.argv[p+1],JSON.stringify(report,null,2));}console.log(JSON.stringify(report));}
