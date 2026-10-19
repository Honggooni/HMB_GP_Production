import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import * as api from '../../widgets/HMBImageAssetLibraryWidget.js';

const require=createRequire(import.meta.url);
let playwright;try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const pixel='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j14sAAAAASUVORK5CYII=';
const state=api.hmbNormalizeImageAssetState({language:'en',edit_transport_schema:'hmb-image-asset-edit-v1',
  project_root:'C:/fixture/project',project_id:'fixture',project_uid:'fixture-project',project_cache_uid:'fixture-cache',
  manifest_signature:'manifest-one',folder_signature:'folders-one',scan_revision:7,
  folders:['CH','BG'],assets:Array.from({length:5000},(_,i)=>({asset_library_id:`asset-${i}`,asset_id:`ID-${i}`,
    source_uid:`project:source-${i}`,source_kind:'project',registered:i!==95,path:`C:/fixture/image-${i}.png`,
    image_name:`${i%7===0?'캐릭터':'Background'} ${i}`,relative_path:`${i%2?'CH':'BG'}/image-${i}.png`,
    image_main_type:i%2?'Character':'Background',image_sub_type:'Hero',thumbnail_url:pixel,media_signature:`media-${i}`,
    selected:i===1||i===87,selection_order:i===1?1:i===87?2:0}))});
const widget=fs.readFileSync(new URL('../../widgets/HMBImageAssetLibraryWidget.js',import.meta.url));
const bridge=fs.readFileSync(new URL('../../widgets/HMBImageAssetThumbnailPatchBridgeWidget.js',import.meta.url));
const html=`<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#101018}.react-flow__node{width:1220px;height:1020px}#widget{height:1000px}</style><div class="react-flow__node" data-id="fixture"><div id="bridge"></div><div id="widget"></div></div>
<script type="module">
import mount,* as api from '/widget.js';import bridgeMount from '/bridge.js';
window.api=api;window.requests=[];window.writes=[];window.metrics={pageApplyMs:[]};
window.boot=(full,version=1,mode='')=>{window.full=full;window.root=document.getElementById('widget');
window.idle={schema:'hmb-image-asset-thumbnail-bridge',version:1,operation:'idle',phase:'idle',runtime_instance_id:full.shot_routing.publisher_instance_uuid};if(version)window.idle.catalog_page_version=version;
window.bc=bridgeMount(document.getElementById('bridge'),{value:window.idle,onChange:value=>{if(value.operation==='catalog_page'){window.requests.push(value);if(mode==='throw')throw Error('fixture rejection');if(mode==='reject')return Promise.reject(Error('fixture rejection'));}}});
const start=performance.now();window.wc=mount(window.root,{value:JSON.stringify(full),onChange:value=>window.writes.push(JSON.parse(value))});window.metrics.fullInitialMountMs=performance.now()-start;};
window.response=(request,overrides={})=>{const full=window.full;const needle=request.query.trim().toLowerCase(),folder=request.folder.toLowerCase();
const matches=full.assets.filter(a=>a.source_kind===request.source_view&&(!folder||a.relative_path.toLowerCase().startsWith(folder+'/'))&&[a.asset_id,a.image_name,a.relative_path,a.image_main_type,a.image_sub_type].map(x=>String(x||'').trim().toLowerCase()).join('\\n').includes(needle));
const offset=Math.min(request.offset,matches.length?Math.floor((matches.length-1)/80)*80:0),ids=matches.slice(offset,offset+80).map(a=>a.asset_library_id);
const page={...full,assets:full.assets.filter(a=>a.selected||ids.includes(a.asset_library_id)),catalog_page:{version:1,session_id:request.session_id,sequence:request.sequence,query:request.query,folder:request.folder,source_view:request.source_view,offset,limit:80,total:matches.length,asset_library_ids:ids,folder_counts:{'':5000,CH:2500,BG:2500},...overrides}};
return{...request,phase:'result',outcome:'ready',catalog_page_version:1,state:page};};
window.answer=(request,overrides={})=>{const value=window.response(request,overrides),start=performance.now();window.bc.update({value,onChange:value=>{if(value.operation==='catalog_page')window.requests.push(value);}});window.metrics.pageApplyMs.push(performance.now()-start);};
window.updateFull=full=>{window.full=full;window.wc.update({value:JSON.stringify(full),onChange:value=>window.writes.push(JSON.parse(value))});};window.ready=true;
</script>`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?widget:req.url==='/bridge.js'?bridge:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
const output=path.resolve('reports/feature123-local804-20261016/search');fs.mkdirSync(output,{recursive:true});
try{
  browser=await playwright.chromium.launch({executablePath:process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:1080}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
  await page.evaluate(state=>window.boot(state),state);await page.waitForFunction(()=>window.requests.length===1);
  assert.equal(await page.locator('[data-asset-key]').count(),80);
  await page.evaluate(()=>window.answer(window.requests[0]));
  await page.waitForFunction(()=>window.root.__hmbImageAssetLatestState.catalog_page);
  assert.ok(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.length<=82));
  const clickSelection=async(id,selected)=>{
    const writes=await page.evaluate(()=>window.writes.length);
    await page.locator(`[data-asset-key="${id}"]`).click();
    await page.waitForFunction(n=>window.writes.length===n+1,writes);
    assert.equal(await page.evaluate(({id})=>Boolean(window.root.__hmbImageAssetLatestState.assets.find(a=>a.asset_library_id===id)?.selected),{id}),selected,`${id} exactly one toggle`);
    assert.equal(await page.evaluate(()=>window.writes.at(-1).schema),'hmb-image-asset-edit-v1','Selection uses compact catalog-free edit');
  };
  await clickSelection('asset-2',true);await clickSelection('asset-2',false);
  await page.locator('[data-assets-more]').click();await page.waitForFunction(()=>window.requests.at(-1).offset===80);
  await page.evaluate(()=>window.answer(window.requests.at(-1)));
  await page.waitForFunction(()=>window.root.__hmbImageAssetLatestState.catalog_page.offset===80);
  assert.equal(await page.locator('[data-asset-key]').first().getAttribute('data-asset-key'),'asset-80');
  await page.locator('[data-asset-key="asset-95"] [data-asset-add]').click();
  assert.equal(await page.locator('[data-registration-field="image_name"]').inputValue(),'Background 95');
  await page.locator('[data-registration-field="image_name"]').fill('Classified page asset');
  const registrationWrites=await page.evaluate(()=>window.writes.length);
  await page.locator('[data-registration-submit]').click();
  await page.waitForFunction(n=>window.writes.length===n+1,registrationWrites);
  assert.equal(await page.evaluate(()=>window.writes.at(-1).edits.asset_registration_request.asset_library_id),'asset-95');
  assert.equal(await page.evaluate(()=>window.writes.at(-1).edits.asset_registration_request.image_name),'Classified page asset');
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.find(a=>a.asset_library_id==='asset-95').registered),false,'Registration request does not invent backend approval');
  await clickSelection('asset-100',true);await clickSelection('asset-100',false);
  const trayWrites=await page.evaluate(()=>window.writes.length);
  await page.locator('[data-selected-key="asset-1"] [data-remove-selected]').click();
  await page.waitForFunction(n=>window.writes.length===n+1,trayWrites);
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.find(a=>a.asset_library_id==='asset-1')?.selected),false,'Selected tray removes off-page item once');
  await page.locator('[data-assets-previous]').click();await page.waitForFunction(()=>window.requests.at(-1).offset===0);
  await page.evaluate(()=>window.answer(window.requests.at(-1)));
  await page.waitForFunction(()=>window.root.__hmbImageAssetLatestState.catalog_page.offset===0);
  await clickSelection('asset-1',true);
  const originalSelected=await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.filter(a=>a.selected).map(a=>a.source_uid));
  const query=page.locator('[data-search]');await query.focus();
  await query.evaluate(el=>{window.compositionInput=el;el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));el.value='캐릭터';el.setSelectionRange(2,2);el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertCompositionText',data:'릭터',isComposing:true}));});
  await page.waitForFunction(()=>window.requests.at(-1).query==='캐릭터');
  await page.evaluate(()=>window.answer(window.requests.at(-1)));
  assert.equal(await query.evaluate(el=>el===window.compositionInput&&document.activeElement===el&&el.selectionStart===2),true,'Composition response preserved original input/caret');
  await query.evaluate(el=>el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'캐릭터'})));
  const before=await page.evaluate(()=>window.requests.length);
  for(const word of ['B','Ba','Back','Background'])await query.fill(word);
  await page.waitForFunction(n=>window.requests.length===n+1,before);
  assert.equal(await query.inputValue(),'Background');
  assert.equal(await page.locator('[data-asset-key]').count(),80,'Previous catalog remains paintable during search');
  await page.evaluate(()=>window.answer(window.requests.at(-1)));await page.waitForFunction(()=>window.root.__hmbImageAssetLatestState.catalog_page.query==='Background');
  assert.equal(await query.evaluate(el=>document.activeElement===el),true,'Search response preserved focus');
  // Newer search result arrives first; stale query cannot replace its card IDs/caret.
  await query.fill('캐릭터');await page.waitForFunction(()=>window.requests.at(-1).query==='캐릭터');
  const older=await page.evaluate(()=>window.requests.at(-1));
  await query.fill('ID-4999');await page.waitForFunction(()=>window.requests.at(-1).query==='ID-4999');
  const newer=await page.evaluate(()=>window.requests.at(-1));
  await page.evaluate(request=>window.answer(request),newer);
  await page.waitForFunction(()=>window.root.__hmbImageAssetLatestState.catalog_page.query==='ID-4999');
  const currentIDs=await page.locator('[data-asset-key]').evaluateAll(cards=>cards.map(x=>x.getAttribute('data-asset-key')));
  await page.evaluate(request=>window.answer(request),older);
  assert.deepEqual(await page.locator('[data-asset-key]').evaluateAll(cards=>cards.map(x=>x.getAttribute('data-asset-key'))),currentIDs);
  assert.deepEqual(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.filter(a=>a.selected).map(a=>a.source_uid)),originalSelected);
  // Full canonical metadata change with unchanged project/scan/count retires old request.
  await query.fill('OnlyRenamed');await page.waitForFunction(()=>window.requests.at(-1).query==='OnlyRenamed');
  const staleMetadata=await page.evaluate(()=>window.requests.at(-1));
  await page.evaluate(()=>{const full=structuredClone(window.full);full.assets[4000].image_name='OnlyRenamed';full.ui_edit_revision=100;window.updateFull(full);});
  await page.waitForFunction(request=>window.requests.at(-1).sequence>request.sequence,staleMetadata);
  const freshMetadata=await page.evaluate(()=>window.requests.at(-1));
  await page.evaluate(request=>window.answer(request),freshMetadata);
  await page.waitForFunction(()=>window.root.__hmbImageAssetLatestState.catalog_page?.sequence===window.requests.at(-1).sequence);
  assert.deepEqual(await page.locator('[data-asset-key]').evaluateAll(cards=>cards.map(x=>x.getAttribute('data-asset-key'))),['asset-4000']);
  await page.evaluate(request=>window.answer(request),staleMetadata);
  assert.deepEqual(await page.locator('[data-asset-key]').evaluateAll(cards=>cards.map(x=>x.getAttribute('data-asset-key'))),['asset-4000']);
  // A new canonical thumbnail beats a delayed page carrying the old thumbnail.
  await query.fill('ID-4000');await page.waitForFunction(()=>window.requests.at(-1).query==='ID-4000');
  const thumbnailRequest=await page.evaluate(()=>window.requests.at(-1));
  const delayed=await page.evaluate(request=>window.response(request),thumbnailRequest);
  await page.evaluate(()=>{const full=structuredClone(window.full);full.assets[4000].thumbnail_url='data:image/png;base64,new-thumbnail';full.thumbnail_revision=10;full.ui_edit_revision=101;window.updateFull(full);});
  await page.evaluate(result=>window.bc.update({value:result,onChange:value=>{if(value.operation==='catalog_page')window.requests.push(value);}}),delayed);
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.find(a=>a.asset_library_id==='asset-4000').thumbnail_url),'data:image/png;base64,new-thumbnail');
  // Full catalog import and project transition invalidate any old page response.
  await query.fill('ID-4998');await page.waitForFunction(()=>window.requests.at(-1).query==='ID-4998');const staleImport=await page.evaluate(()=>window.requests.at(-1));
  await page.evaluate(()=>{const full=structuredClone(window.full);full.assets.push({...full.assets[0],asset_library_id:'import-added',asset_id:'import',source_uid:'user:import-added',source_kind:'user',image_name:'Imported'});full.ui_edit_revision=102;window.updateFull(full);});
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetPageControl.pending?.request_id===window.requests.at(-1).request_id),true);
  await page.evaluate(request=>window.answer(request),staleImport);
  assert.notEqual(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.catalog_page?.sequence),staleImport.sequence);
  const beforeCleanup=await page.evaluate(()=>({writes:window.writes.length,requests:window.requests.length}));
  const browserMetrics=await page.evaluate(()=>window.metrics);
  await page.screenshot({path:path.join(output,'search-page-widget.png')});
  await page.evaluate(()=>{window.wc.cleanup();window.bc.cleanup();});
  await page.evaluate(request=>window.answer(request),staleImport);
  assert.equal(await page.locator('[data-asset-key]').count(),0);
  assert.deepEqual(await page.evaluate(()=>({writes:window.writes.length,requests:window.requests.length})),beforeCleanup);
  // New widget + old backend capability absent: legacy 5,000 catalog remains usable.
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
  await page.evaluate(state=>window.boot(state,0),state);
  assert.equal(await page.evaluate(()=>window.requests.length),0);
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.length),5000);
  await page.locator('[data-search]').fill('ID-4999');await page.waitForFunction(()=>document.querySelectorAll('[data-asset-key]').length===1);
  assert.equal(await page.locator('[data-asset-key]').getAttribute('data-asset-key'),'asset-4999');
  await page.evaluate(()=>{window.wc.cleanup();window.bc.cleanup();});
  for(const mode of ['throw','reject','timeout','rejected-result']){
    await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
    if(mode==='timeout')await page.evaluate(()=>{const native=window.setTimeout;window.restoreFixtureTimeout=()=>{window.setTimeout=native;delete window.restoreFixtureTimeout;};window.setTimeout=(fn,ms,...args)=>native(fn,ms===15000?40:ms,...args);});
    await page.evaluate(({state,mode})=>window.boot(state,1,mode),{state,mode});
    if(mode==='rejected-result')await page.evaluate(()=>window.bc.update({value:{...window.requests[0],phase:'result',outcome:'rejected'},onChange:()=>{}}));
    await page.waitForFunction(()=>window.root.__hmbImageAssetPageControl.disabledContext);
    if(mode==='timeout')await page.evaluate(()=>window.restoreFixtureTimeout());
    assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.length),5000,`${mode} falls back to full canonical catalog`);
    await page.locator('[data-search]').fill('ID-4999');await page.waitForFunction(()=>document.querySelectorAll('[data-asset-key]').length===1);
    assert.equal(await page.locator('[data-asset-key]').getAttribute('data-asset-key'),'asset-4999');
    assert.equal(await page.evaluate(()=>window.requests.length),1,`${mode} never loops automatic page retries`);
    await page.evaluate(()=>{window.bc.update({value:window.idle,onChange:value=>{if(value.operation==='catalog_page')window.requests.push(value);}});
      const full=structuredClone(window.full);full.project_root='C:/fixture/next-project';full.project_uid='next-project';full.project_cache_uid='next-cache';full.project_id='Next';full.ui_edit_revision=200;window.updateFull(full);});
    await page.waitForFunction(()=>window.requests.length===2);
    // The later valid request uses the product's 15-second deadline, even when
    // its response arrives after the earlier negative fixture's 40-ms deadline.
    if(mode==='timeout')await page.waitForTimeout(80);
    await page.evaluate(()=>window.answer(window.requests.at(-1)));
    await page.waitForFunction(()=>Boolean(window.root.__hmbImageAssetLatestState.catalog_page));
    assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.project_uid),'next-project',`${mode} new project resumes page mode`);
    await page.evaluate(()=>{window.wc.cleanup();window.bc.cleanup();});
  }
  assert.deepEqual(errors.filter(message=>!message.includes('ERR_INVALID_URL')),[]);
  fs.writeFileSync(path.join(output,'widget-result.json'),JSON.stringify({browser:'actual Chromium',canonicalRecords:5000,domWindow:80,visibleStateMax:82,latestOnly:true,
    initialAndDelegatedSelectionExactlyOnce:true,offPageTrayRemoval:true,unregisteredPageAssetClassification:true,compositionFocusCaret:true,
    metadataImportRetire:true,thumbnailMonotonic:true,cleanup:true,newWidgetOldBackendFallback:true,
    timeoutRejectLocalFallback:true,changedProjectPageRecovery:true,externalTransport:0,...browserMetrics},null,2));
  console.log('PASS ImageAsset actual Chromium pages: 5k/80 window, debounce, latest-only, focus/selection, metadata/import epochs, thumbnail continuity, cleanup, old-backend and reject/timeout local fallback.');
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
