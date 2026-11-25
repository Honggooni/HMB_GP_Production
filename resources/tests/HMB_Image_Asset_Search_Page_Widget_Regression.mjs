import { listenBrowserSafeLoopback } from "./_hmb_browser_loopback.mjs";
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const require=createRequire(import.meta.url);
const libraryRoot=process.env.HMB_IMAGE_ASSET_TEST_ROOT
  ? pathToFileURL(path.resolve(process.env.HMB_IMAGE_ASSET_TEST_ROOT)+path.sep)
  : new URL('../../',import.meta.url);
const widgetPath=new URL('widgets/HMBImageAssetLibraryWidget.js',libraryRoot);
const api=await import(widgetPath);
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
const widget=fs.readFileSync(widgetPath);
const bridge=fs.readFileSync(new URL('widgets/HMBImageAssetThumbnailPatchBridgeWidget.js',libraryRoot));
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
await listenBrowserSafeLoopback(server);
let browser;
const output=path.resolve('reports/feature123-local804-20261016/search');fs.mkdirSync(output,{recursive:true});
try{
  browser=await playwright.chromium.launch({executablePath:process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:1080}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
  await page.evaluate(state=>window.boot(state),state);
  assert.equal(await page.locator('[data-asset-key]').count(),0);
  assert.equal(await page.locator('[data-folder-prompt]').count(),1);
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.length),5000);
  assert.equal(await page.locator('[data-selected-key]').count(),2);
  const openRoot = () => page.locator('[data-folder-key][data-source-view="project"][data-folder-path=""]').first().click();
  await openRoot();await page.waitForFunction(()=>window.requests.length===1);
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
  await page.evaluate(()=>{
    window.wc.update({value:JSON.stringify(window.full),onChange(value){
      if(JSON.parse(value).edits?.asset_registration_request?.request_id) throw Error('Registration transport unavailable');
    }});
  });
  await page.locator('[data-registration-submit]').click();
  await page.waitForFunction(()=>document.querySelector('[data-registration-status]')?.textContent.includes('unavailable'));
  assert.equal(await page.locator('[data-registration-field="image_name"]').inputValue(),'Classified page asset');
  await page.evaluate(()=>window.updateFull(window.full));
  const registrationWrites=await page.evaluate(()=>window.writes.length);
  await page.locator('[data-registration-submit]').click();
  await page.waitForFunction(n=>window.writes.length===n+1,registrationWrites);
  assert.equal(await page.evaluate(()=>window.writes.at(-1).edits.asset_registration_request.asset_library_id),'asset-95');
  assert.equal(await page.evaluate(()=>window.writes.at(-1).edits.asset_registration_request.image_name),'Classified page asset');
  assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.find(a=>a.asset_library_id==='asset-95').registered),false,'Registration request does not invent backend approval');
  assert.ok(await page.locator('[data-registration-submit]').isDisabled());
  await page.evaluate(()=>{
    const full=structuredClone(window.full),edit=window.writes.at(-1);
    full.ui_edit_revision=edit.ui_edit_revision;
    full.asset_registration_result={request_id:edit.edits.asset_registration_request.request_id,ok:true,asset_library_id:'asset-95',message:'Registered'};
    window.updateFull(full);
  });
  await page.waitForFunction(()=>!document.querySelector('[data-registration-submit]'));
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
    await openRoot();
    if(mode==='rejected-result')await page.evaluate(()=>window.bc.update({value:{...window.requests[0],phase:'result',outcome:'rejected'},onChange:()=>{}}));
    await page.waitForFunction(()=>window.root.__hmbImageAssetPageControl.disabledContext);
    if(mode==='timeout')await page.evaluate(()=>window.restoreFixtureTimeout());
    assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.assets.length),5000,`${mode} falls back to full canonical catalog`);
    await page.locator('[data-search]').fill('ID-4999');await page.waitForFunction(()=>document.querySelectorAll('[data-asset-key]').length===1);
    assert.equal(await page.locator('[data-asset-key]').getAttribute('data-asset-key'),'asset-4999');
    assert.equal(await page.evaluate(()=>window.requests.length),1,`${mode} never loops automatic page retries`);
    await page.evaluate(()=>{window.bc.update({value:window.idle,onChange:value=>{if(value.operation==='catalog_page')window.requests.push(value);}});
      const full=structuredClone(window.full);full.project_root='C:/fixture/next-project';full.project_uid='next-project';full.project_cache_uid='next-cache';full.project_id='Next';full.ui_edit_revision=200;window.updateFull(full);});
    await openRoot();
    await page.waitForFunction(()=>window.requests.length===2);
    // The later valid request uses the product's 15-second deadline, even when
    // its response arrives after the earlier negative fixture's 40-ms deadline.
    if(mode==='timeout')await page.waitForTimeout(80);
    await page.evaluate(()=>window.answer(window.requests.at(-1)));
    await page.waitForFunction(()=>Boolean(window.root.__hmbImageAssetLatestState.catalog_page));
    assert.equal(await page.evaluate(()=>window.root.__hmbImageAssetLatestState.project_uid),'next-project',`${mode} new project resumes page mode`);
    await page.evaluate(()=>{window.wc.cleanup();window.bc.cleanup();});
  }
  for (const writer of ['hq', 'site-' + 'a'.repeat(32)]) {
    const client = await browser.newPage({viewport:{width:1280,height:1080}});
    client.on('pageerror', error => errors.push(error.message));
    await client.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await client.goto(`http://127.0.0.1:${server.address().port}`);
    await client.waitForFunction(() => window.ready);
    const vendor = writer !== 'hq';
    const secondSite = 'site-' + 'b'.repeat(32);
    const prefix = vendor ? `site:${writer}/` : '';
    const folders = ['BG', 'BG/e201', 'BG/e202', 'BG/e202/Tone', 'BG_lighting', 'CH', 'user_imports'].map(folder => prefix + folder);
    folders.push(vendor ? 'HQOnly' : `site:${'site-' + 'a'.repeat(32)}/VendorOnly`);
    if (vendor) folders.push(`site:${secondSite}/SecondOnly`);
    const row = {...state.assets[95], asset_library_id:'dingo', source_uid:'import:dingo', source_kind:'user', import_index:1,
      image_name:'Dingo', asset_id:'Dingo', path:'{inputs}/images/Dingo.jpg', relative_path:'', registered:false};
    const clientState = api.hmbNormalizeImageAssetState({...state, folders, assets:[row], selected_source_view:'user',
      shot_routing:undefined, site_settings:{write_site_id:writer,revision:'test',
        links:vendor ? [{id:writer,label:'Partner'},{id:secondSite,label:'Second partner'}] : []}});
    await client.evaluate(value => window.boot(value,0),clientState);
    await client.locator('[data-asset-key="dingo"] [data-asset-add]').click();
    const submit = client.locator('[data-registration-submit]');
    const destination = client.locator('[data-registration-destination]');
    const chooser = client.locator('[data-registration-folder]');
    const control = action => chooser.locator(`[data-registration-folder-action="${action}"]`);
    const folder = path => chooser.locator(`[data-registration-folder-path="${prefix}${path}"]`);
    const rows = () => chooser.locator('[data-registration-folder-path]:not(.passport-folder-here) span:first-child').allTextContents();
    assert.equal(await submit.isEnabled(),true);
    assert.match(await control('open').textContent(),/add/);
    if (vendor) {
      assert.deepEqual(await destination.locator('option').allTextContents(),['Select a save location','Default folder','Partner','Second partner']);
      assert.equal(await destination.inputValue(),writer);
      await control('open').click();
      await folder('add').click();
      assert.match(await control('open').textContent(),/Partner \/ add/);
      assert.equal(await submit.isEnabled(),true);
      await destination.selectOption('hq');
      assert.deepEqual(await rows(),['HQOnly','add']);
      assert.equal(await submit.isDisabled(),true);
      await destination.selectOption(secondSite);
      assert.deepEqual(await rows(),['SecondOnly','add']);
      await destination.selectOption(writer);
    } else {
      assert.equal(await destination.count(),0);
      await control('open').click();
    }
    assert.equal(await submit.isDisabled(),true);
    assert.deepEqual(await rows(),['BG','BG_lighting','CH','add']);
    await folder('BG').click();
    assert.deepEqual(await rows(),['e201','e202']);
    await chooser.getByRole('button',{name:'Save in this folder'}).click();
    assert.match(await control('open').textContent(),/BG/);
    assert.equal(await submit.isEnabled(),true);
    await control('open').click();
    await folder('BG').click();
    await folder('BG/e202').click();
    assert.deepEqual(await rows(),['Tone']);
    await control('back').click();
    assert.deepEqual(await rows(),['e201','e202']);
    await control('close').click();
    assert.match(await control('open').textContent(),/BG/);
    await control('open').click();
    await folder('BG').click();
    await folder('BG/e202').click();
    await folder('BG/e202/Tone').click();
    assert.match(await control('open').textContent(),/BG\/e202\/Tone/);
    const registrationRequests = () => client.evaluate(() => window.writes.map(v => (v.edits || v).asset_registration_request).filter(v => v?.request_id));
    assert.deepEqual(await registrationRequests(),[]);
    assert.equal(await client.evaluate(() => window.requests.length),0,'Folder navigation uses the loaded catalog');
    await submit.click();
    const requests = await registrationRequests();
    assert.equal(requests.length,1);
    assert.equal(requests[0].target_folder,prefix+'BG/e202/Tone');
    assert.equal(requests[0].target_site_id,vendor ? writer : undefined);
    await client.close();
  }

  const editor = await browser.newPage({viewport:{width:1280,height:1080}});
  editor.on('pageerror', error => errors.push(error.message));
  await editor.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
  await editor.goto(`http://127.0.0.1:${server.address().port}`);
  await editor.waitForFunction(() => window.ready);
  const ownerRow = {...state.assets[1], relative_path:'CH/owned.png', registration_revision:'test-owner-revision'};
  const otherRow = {...state.assets[2], relative_path:'CH/other.png'};
  await editor.evaluate(value => window.boot(value,0), api.hmbNormalizeImageAssetState({...state,
    assets:[ownerRow,otherRow], shot_routing:undefined}));
  await editor.locator('[data-folder-key][data-source-view="project"][data-folder-path=""]').first().click();
  assert.equal(await editor.locator('[data-asset-edit]').count(),1);
  await editor.locator('[data-asset-edit]').click();
  await editor.getByRole('dialog',{name:'Edit registration'}).waitFor();
  const remove = editor.locator('[data-registration-delete]');
  await remove.click();
  assert.equal(await remove.textContent(),'Confirm removal');
  assert.equal(await editor.evaluate(() => window.writes.filter(v => (v.edits || v).asset_registration_request?.request_id).length),0);
  await remove.click();
  const removal = await editor.evaluate(() => window.writes.map(v => (v.edits || v).asset_registration_request).find(v => v?.request_id));
  assert.equal(removal.action,'delete');
  assert.equal(removal.registration_revision,'test-owner-revision');
  assert.equal(removal.asset_library_id,ownerRow.asset_library_id);
  await editor.close();

  // Five workstations have five independent drafts and receipt owners. A
  // delayed server commit or another writer's ACK cannot resubmit or close
  // this client's pending Add.
  const clients = await Promise.all(Array.from({length:5}, async (_,i) => {
    const client = await browser.newPage({viewport:{width:1280,height:1080}});
    client.on('pageerror', error => errors.push(error.message));
    await client.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await client.goto(`http://127.0.0.1:${server.address().port}`);
    await client.waitForFunction(() => window.ready);
    await client.clock.install();
    const file = `Writer-${i}.png`;
    const row = {...state.assets[95],asset_library_id:`writer-${i}`,source_uid:`project:writer-${i}`,
      asset_id:`Writer-${i}`,image_name:`Writer ${i}`,path:`C:/fixture/project/CH/${file}`,relative_path:`CH/${file}`};
    const clientState = api.hmbNormalizeImageAssetState({...state, assets:[row], shot_routing:undefined});
    await client.evaluate(value => window.boot(value,0),clientState);
    await client.locator('[data-folder-key][data-source-view="project"][data-folder-path=""]').first().click();
    await client.locator('[data-asset-add]').click();
    assert.equal(await client.locator('[data-registration-destination], [data-registration-folder]').count(),0);
    return client;
  }));
  const requests = await Promise.all(clients.map(async client => {
    await client.locator('[data-registration-submit]').click();
    await client.locator('[data-registration-submit]').dispatchEvent('click');
    const request = await client.evaluate(() => window.writes.map(v => (v.edits || v).asset_registration_request).filter(v => v?.request_id));
    assert.equal(request.length,1);
    return request[0];
  }));
  assert.equal(new Set(requests.map(v => v.request_id)).size,5);
  await Promise.all(clients.map(async (client,i) => {
    await client.clock.fastForward(16000);
    assert.match(await client.locator('[data-registration-status]').textContent(),/waiting for registration/i);
    const sendReceipt = receipt => client.evaluate(ticket => {
      const full = structuredClone(window.full);
      full.ui_edit_revision = window.writes.at(-1).ui_edit_revision;
      full.asset_registration_result = {request_id:ticket.request_id,asset_library_id:ticket.asset_library_id,ok:true};
      window.updateFull(full);
    },receipt);
    await sendReceipt(requests[(i+1)%clients.length]);
    assert.ok(await client.locator('[data-registration-submit]').isDisabled(),'Foreign ACK must leave the pending draft open.');
    await sendReceipt(requests[i]);
    await client.waitForFunction(() => !document.querySelector('[data-registration-submit]'));
    assert.equal(await client.evaluate(() => window.writes.filter(v => (v.edits || v).asset_registration_request?.request_id).length),1);
    await client.close();
  }));
  assert.deepEqual(errors.filter(message=>!message.includes('ERR_INVALID_URL')),[]);
  fs.writeFileSync(path.join(output,'widget-result.json'),JSON.stringify({browser:'actual Chromium',canonicalRecords:5000,domWindow:80,visibleStateMax:82,latestOnly:true,
    initialAndDelegatedSelectionExactlyOnce:true,offPageTrayRemoval:true,unregisteredPageAssetClassification:true,compositionFocusCaret:true,
    metadataImportRetire:true,thumbnailMonotonic:true,cleanup:true,newWidgetOldBackendFallback:true,
    timeoutRejectLocalFallback:true,changedProjectPageRecovery:true,concurrentIndependentAddClients:clients.length,externalTransport:0,...browserMetrics},null,2));
  console.log('PASS ImageAsset actual Chromium pages: 5k/80 window, debounce, latest-only, focus/selection, metadata/import epochs, thumbnail continuity, cleanup, old-backend and reject/timeout local fallback.');
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
