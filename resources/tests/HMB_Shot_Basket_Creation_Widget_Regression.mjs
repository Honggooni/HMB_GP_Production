import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {nativeTestBrowserPath, nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const source = process.env.HMB_SHOT_BASKET_UI_SOURCE || fileURLToPath(new URL('../../resources/editor/hmb-shot-basket.js', import.meta.url));
const browser = await nativeTestPlaywright().chromium.launch({
  headless:true,
  executablePath:nativeTestBrowserPath(),
});
try {
  const page = await browser.newPage();
  await page.setContent('<div id="basket"></div>');
  let script = fs.readFileSync(source,'utf8');
  const candidatePath = process.env.HMB_HEADER_0130_CANDIDATE;
  let prefetch = false;
  if(candidatePath){
    const bundle=fs.readFileSync(candidatePath,'utf8');
    const start=bundle.indexOf('(() => {\n  // Full approved card bounds');
    const end=bundle.indexOf('\nlet hmbQueuedBasket',start);
    if(start>=0 && end>start){script=bundle.slice(start,end);prefetch=script.includes('prewarm:true, project_id:project');}
  }
  if(process.env.HMB_REQUIRE_CGT_PREPARATION==='1') assert.equal(prefetch,true,'Candidate must include CGT preparation');
  await page.addScriptTag({content:script});
  await page.evaluate(() => {
    window.operations = [];
    window.cgtPickerOpened = false;
    let bound = false;
    const context = {ready:true, empty:true, flowName:'Fixture flow', workflowName:'Fixture workflow'};
    const projects = [{project_id:'superwings12', name:'superwings12'}];
    const empty = {ok:true, status:'empty', projects, shots:[], flow_name:context.flowName};
    const created = {...empty, status:'ready', cgt_required:true, cgt_bound:false, nodes:{image:'Fixture ImageAsset'}};
    const shots = Array.from({length:5}, (_, index) => ({
      shot_uuid:`fixture-shot-${index+1}`, name:`e201s00${index+1}c001__`, number:index+1,
    }));
    const basket = window.__hmbMountShotBasket({
      host:document.querySelector('#basket'),
      context,
      async request(action, payload) {
        window.operations.push({action, payload});
        if(action==='status' && payload.prewarm===true) return new Promise(()=>{});
        if (action === 'create') {
          const image = document.createElement('div');
          image.className = 'react-flow__node';
          image.dataset.id = 'Fixture ImageAsset';
          image.innerHTML = '<button data-shot-add>ImageAsset Shot</button>';
          document.body.append(image);
          image.querySelector('button').addEventListener('hmb-basket-open-shot-hierarchy', event => {
            event.preventDefault();
            window.cgtPickerOpened = true;
            window.confirmCgt = () => {
              bound = true;
              event.detail.onClose();
            };
          });
          basket.setContext({...context, empty:false});
          return created;
        }
        if (action === 'status') {
          return bound ? {...created, cgt_bound:true, status:'preparing', shots} : empty;
        }
        throw new Error(`Unexpected action ${action}`);
      },
    });
    basket.open();
  });
  const dialog = page.getByRole('dialog', {name:'샷 바구니'});
  await dialog.getByRole('combobox', {name:'프로젝트'}).selectOption('superwings12');
  await dialog.getByRole('button', {name:'샷 바구니 들기'}).click();
  await page.waitForFunction(() => window.cgtPickerOpened);
  await page.evaluate(() => window.confirmCgt());
  await dialog.waitFor({state:'hidden',timeout:1500});
  assert.equal(await page.locator('[data-basket-view="sources"]').count(),0);
  assert.equal(await page.locator('[data-shot-add]').count(),1);
  const operations = await page.evaluate(() => window.operations);
  assert.deepEqual(operations.map(entry => entry.action), prefetch ? ['status','status','create','status'] : ['status','create','status']);
  if(prefetch){
    assert.equal(operations[1].payload.prewarm,true);
    assert.equal(operations[1].payload.project_id,'superwings12');
  }
  const creation=operations.find(entry=>entry.action==='create');
  assert.equal(creation.payload.cgt_setup,true);
  assert.equal(creation.payload.project_id,'superwings12');
  console.log('Shot Basket creates the CGT group and exits without opening or requesting media: PASS');
} finally {
  await browser.close();
}
