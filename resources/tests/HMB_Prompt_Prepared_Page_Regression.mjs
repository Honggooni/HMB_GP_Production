// Actual Chromium widget regression. Local synthetic callbacks only; no engine,
// provider, workflow file or billable generation endpoint is contacted.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
const original = fs.readFileSync(new URL('../../widgets/HMBPromptLibraryScopedBindingWidget.js', import.meta.url), 'utf8');
const imageRows = Number(process.env.HMB_PROMPT_PREPARED_IMAGES || 4);
assert.ok([4, 50].includes(imageRows));
let source = original;
for (const [name, declaration] of [
  ['normalize', 'export function normalizeState(input) {'],
  ['render', 'function render(state, includeStyle = true) {'],
  ['tree_patch', 'export function hmbPatchPromptDashboard(container, markup) {'],
  ['fit', 'function hmbFitGroupHeightsToCenter(container, state, measuredHosts = null) {'],
]) {
  assert.ok(source.includes(declaration), declaration);
  source = source.replace(declaration, `${declaration}\nif (globalThis.__pageProbe) { globalThis.__pageProbe.${name}++; ${name === 'normalize' ? 'globalThis.__pageStacks.push(new Error().stack);' : ''} }`);
}
source += '\nexport {hmbReadStoredSourceScroll};';
const server = http.createServer((request, response) => {
  response.setHeader('Content-Type', request.url === '/widget.js' ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8');
  response.end(request.url === '/widget.js' ? source : '<!doctype html><meta charset="utf-8"><div class="react-flow__node" id="shell" style="height:1350px;width:1800px"><div style="height:96px">Synthetic native header</div><div id="host"></div></div>');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await playwright.chromium.launch({headless: true, executablePath: process.env.HMB_PROMPT_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
const receipt = {schema: 'hmb-prompt-prepared-pages-v1', source_sha256: crypto.createHash('sha256').update(original).digest('hex'), external_requests: 0, paid_submissions: 0};
try {
  const page = await browser.newPage({viewport: {width: 1900, height: 1500}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1') { receipt.external_requests++; return route.abort(); }
    return route.continue();
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  receipt.result = await page.evaluate(async (imageRows) => {
    const widget = await import('/widget.js');
    const legacy={dataset:{hmbImageSourceScrollTop:'210',hmbVideoSourceScrollTop:'320',hmbManagerBodyScrollTop:'430'}};
    const scrollKeys=['imageSources','videoSources','managerBody'];
    if(JSON.stringify(scrollKeys.map(key=>widget.hmbReadStoredSourceScroll(legacy,key)))!=='[210,320,430]')throw Error('Legacy dataset scroll was discarded');
    legacy.__hmbPromptLibraryScrollMemory={imageSources:0,videoSources:17,managerBody:0};
    if(JSON.stringify(scrollKeys.map(key=>widget.hmbReadStoredSourceScroll(legacy,key)))!=='[0,17,0]')throw Error('Explicit zero scroll leaked a previous page dataset');
    const channel = '11111111-1111-4111-8111-111111111111';
    const shots = Array.from({length: 5}, (_, index) => ({channel_uuid: channel, shot_uuid: `22222222-2222-4222-8222-${String(index + 1).padStart(12, '0')}`, number: index + 1, name: `Prepared asset ${index + 1}`, selected_source_uids: []}));
    let latest = widget.normalizeState({multi_shot_enabled: true, shot: shots[0], source_sync_revision: 1, image_asset: {shot_catalog: shots, shot_catalog_routing: {publisher_instance_uuid: channel, channel_uuid: channel, generation: 1, metadata_sha256: 'a'.repeat(64)}}});
    const key = Object.keys(latest.text)[0];
    const expected = new Map();
    for (const shot of shots) {
      widget.hmbSwitchPromptShot(latest, shot.shot_uuid);
      latest.images[0].label = `Image ${shot.number}`;
      latest.images[0].owner = `Target ${shot.number} {literal}`;
      latest.images[0].surface_2d = false;
      const first = latest.images[0];
      latest.images = Array.from({length: imageRows}, (_, index) => ({...structuredClone(first),
        slot: index + 1, token: `@image${index + 1}`, name: `IMAGE_${String(index + 1).padStart(2, '0')}`,
        label: index ? `Image ${shot.number}/${index + 1}` : first.label,
        owner: index ? `Target ${shot.number}/${index + 1} {literal}` : first.owner}));
      latest.text[key] = `Original ${shot.number} 한글 {literal} 0 OFF`;
      expected.set(shot.shot_uuid, latest.text[key]);
      widget.hmbStorePromptShotDocument(latest);
    }
    widget.hmbSwitchPromptShot(latest, shots[0].shot_uuid);
    const host = document.querySelector('#host');
    let controller;
    let publications = 0;
    const props = value => ({value: JSON.stringify(value), disabled: false, onChange(next) { latest = JSON.parse(next); publications++; controller.update(props(latest)); }});
    const frames = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const select = async index => {
      host.querySelector(`[data-prompt-shot="${shots[index].shot_uuid}"]`).click();
      await frames(); await frames();
    };
    controller = widget.default(host, props(latest));
    await frames();
    const references = new Map();
    for (let index = 0; index < 5; index++) {
      await select(index);
      references.set(shots[index].shot_uuid, {center: host.querySelector('.center'), text: host.querySelector(`[data-text-key="${key}"]`), row: host.querySelector('.source-row.image')});
    }
    const add = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function (...args) { if (globalThis.__pageProbe) globalThis.__pageProbe.listeners++; return add.apply(this, args); };
    globalThis.__pageProbe = {normalize: 0, render: 0, tree_patch: 0, fit: 0, listeners: 0};
    globalThis.__pageStacks = [];
    const durations = [];
    for (let index = 0; index < 40; index++) {
      const shot = shots[(index * 3 + 1) % 5];
      const started = performance.now();
      host.querySelector(`[data-prompt-shot="${shot.shot_uuid}"]`).click();
      durations.push(performance.now() - started);
      const originalView = references.get(shot.shot_uuid);
      if (host.querySelector('.center') !== originalView.center || host.querySelector(`[data-text-key="${key}"]`) !== originalView.text || host.querySelector('.source-row.image') !== originalView.row) throw Error('A prepared view/control was recreated during navigation');
      if (originalView.text.value !== expected.get(shot.shot_uuid)) throw Error('Cross-shot literal text changed');
      if (host.querySelectorAll('.center').length !== 1 || host.querySelectorAll('[data-group-id]').length !== 4) throw Error('Visible editor structure duplicated');
    }
    await frames(); await frames();
    for (const index of [4, 3, 2, 1, 0, 1, 2, 3, 4, 0]) await select(index);
    const pure = {...globalThis.__pageProbe};
    if (Object.values(pure).some(Boolean)) throw Error(`Pure navigation performed expensive work: ${JSON.stringify(pure)} ${JSON.stringify(globalThis.__pageStacks)}`);
    globalThis.__pageProbe = null;
    EventTarget.prototype.addEventListener = add;
    // Edit and immediately leave each page before the typing debounce fires.
    // Detached old controls must not publish into a different UUID.
    for (let index = 0; index < 5; index++) {
      await select(index);
      const text = host.querySelector(`[data-text-key="${key}"]`);
      const value = `Edited ${index + 1}: 한글 0 OFF {literal}`;
      expected.set(shots[index].shot_uuid, value);
      text.value = value;
      text.dispatchEvent(new Event('input', {bubbles: true}));
      await select((index + 1) % 5);
      text.value = 'FORBIDDEN STALE DETACHED VALUE';
      text.dispatchEvent(new Event('input', {bubbles: true}));
      text.dispatchEvent(new FocusEvent('blur'));
    }
    for (let index = 0; index < 5; index++) {
      await select(index);
      if (host.querySelector(`[data-text-key="${key}"]`).value !== expected.get(shots[index].shot_uuid)) throw Error('Dirty text was lost or copied to another shot');
    }
    // A received newer document replaces only that page, keeping other pages.
    await select(0);
    const next = structuredClone(latest);
    const targetKey = `${channel}/${shots[3].shot_uuid}`;
    const changed = JSON.parse(next.shot_documents[targetKey]);
    changed.text[key] = 'Authoritative source refresh for shot 4';
    expected.set(shots[3].shot_uuid, changed.text[key]);
    next.shot_documents[targetKey] = JSON.stringify(changed);
    next.source_sync_revision++;
    next.image_asset.shot_catalog_routing.generation++;
    next.image_asset.shot_catalog_routing.metadata_sha256 = 'b'.repeat(64);
    latest = next;
    controller.update(props(next));
    await frames(); await frames();
    await select(3);
    if (host.querySelector(`[data-text-key="${key}"]`).value !== expected.get(shots[3].shot_uuid)) throw Error('Changed inactive page reused stale controls');
    const saved = structuredClone(latest);
    controller.cleanup();
    controller = widget.default(host, props(saved));
    await frames();
    for (let index = 4; index >= 0; index--) {
      await select(index);
      if (host.querySelector(`[data-text-key="${key}"]`).value !== expected.get(shots[index].shot_uuid)) throw Error('Save/reopen lost a shot document');
      if (latest.images[0].owner !== `Target ${index + 1} {literal}`) throw Error('Save/reopen lost per-shot Target binding');
    }
    // A removed slot is not an excuse to reuse its page for a different UUID.
    const removed = structuredClone(latest);
    removed.image_asset.shot_catalog = removed.image_asset.shot_catalog.filter(shot => shot.shot_uuid !== shots[2].shot_uuid);
    removed.source_sync_revision++;
    removed.image_asset.shot_catalog_routing.generation++;
    removed.image_asset.shot_catalog_routing.metadata_sha256 = 'c'.repeat(64);
    latest = removed;
    controller.update(props(removed)); await frames(); await frames();
    if (host.querySelector(`[data-prompt-shot="${shots[2].shot_uuid}"]`)) throw Error('Deleted catalog slot remained visible');
    const replacement = {...shots[2], shot_uuid: '33333333-3333-4333-8333-000000000003', name: 'New UUID at number 3'};
    const replaced = structuredClone(latest);
    replaced.image_asset.shot_catalog = [...replaced.image_asset.shot_catalog, replacement].sort((a, b) => a.number - b.number);
    replaced.source_sync_revision++;
    replaced.image_asset.shot_catalog_routing.generation++;
    replaced.image_asset.shot_catalog_routing.metadata_sha256 = 'd'.repeat(64);
    latest = replaced;
    controller.update(props(replaced)); await frames(); await frames();
    host.querySelector(`[data-prompt-shot="${replacement.shot_uuid}"]`).click(); await frames(); await frames();
    if (host.querySelector(`[data-text-key="${key}"]`).value === expected.get(shots[2].shot_uuid)
      || latest.images[0].owner === 'Target 3 {literal}') throw Error('New UUID inherited a removed shot page');
    // Returning the exact old UUID restores its archived document, not the
    // replacement. Source generation must be newer than the temporary catalog.
    const restored = structuredClone(saved);
    restored.source_sync_revision = latest.source_sync_revision + 1;
    restored.ui_edit_revision = latest.ui_edit_revision + 1;
    restored.image_asset.shot_catalog_routing.generation = latest.image_asset.shot_catalog_routing.generation + 1;
    restored.image_asset.shot_catalog_routing.metadata_sha256 = 'e'.repeat(64);
    latest = restored;
    controller.update(props(restored)); await frames(); await frames();
    await select(2);
    if (host.querySelector(`[data-text-key="${key}"]`).value !== expected.get(shots[2].shot_uuid)) throw Error('Exact UUID restoration lost its document');
    // Prepared-page interaction regression: nonzero per-shot scroll and restored
    // focus/caret survive switches, including a rapid unacknowledged burst.
    const expectedScroll = new Map();
    for (let index=0;index<5;index++) {
      await select(index);
      const center=host.querySelector('.group-card[data-group-id="imageSources"] .source-scrollbox');
      for(const [key,value] of [['height','120px'],['min-height','120px'],['max-height','120px'],['overflow-y','auto'],['flex','0 0 120px']])center.style.setProperty(key,value,'important');
      await frames();
      center.scrollTop=index===2 ? 0 : 200+index*170;
      center.dispatchEvent(new Event('scroll'));
      expectedScroll.set(shots[index].shot_uuid,center.scrollTop);
      if(index!==2 && center.scrollTop<=0)throw Error('Scroll fixture did not overflow '+JSON.stringify({height:center.clientHeight,scroll:center.scrollHeight,overflow:getComputedStyle(center).overflowY,html:center.outerHTML.slice(0,300)}));
    }
    for(const index of [4,2,0,3,1,4,0]) {
      await select(index);
      const actual=host.querySelector('.group-card[data-group-id="imageSources"] .source-scrollbox').scrollTop;
      if(Math.abs(actual-expectedScroll.get(shots[index].shot_uuid))>1)throw Error(`Nonzero shot scroll lost ${index}: ${actual} expected ${expectedScroll.get(shots[index].shot_uuid)}`);
    }
    for(let index=0;index<40;index++)host.querySelector(`[data-prompt-shot="${shots[(index*3+1)%5].shot_uuid}"]`).click();
    await frames();await frames();
    const afterBurst=host.querySelector('.group-card[data-group-id="imageSources"] .source-scrollbox').scrollTop;
    if(Math.abs(afterBurst-expectedScroll.get(latest.shot.shot_uuid))>1)throw Error('Rapid switch lost selected shot scroll');
    const beforeLateAck=structuredClone(latest);
    for(const index of [2,4,2,0,2,1])host.querySelector(`[data-prompt-shot="${shots[index].shot_uuid}"]`).click();
    controller.update(props(beforeLateAck));
    await frames();await frames();
    if(latest.shot.shot_uuid!==shots[1].shot_uuid || host.querySelector(`[data-prompt-shot="${shots[1].shot_uuid}"]`).getAttribute('aria-selected')!=='true')throw Error('Stale ACK changed the selected page');
    const afterLateAck=host.querySelector('.group-card[data-group-id="imageSources"] .source-scrollbox').scrollTop;
    if(Math.abs(afterLateAck-expectedScroll.get(shots[1].shot_uuid))>1)throw Error('Stale ACK or deferred callback changed the new page scroll');
    const selectWithPointer = async (index) => {
      const button=host.querySelector(`[data-prompt-shot="${shots[index].shot_uuid}"]`);
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0}));button.click();await frames();await frames();
    };
    for(let index=0;index<5;index++) {
      await selectWithPointer(index);
      const field=host.querySelector(`[data-text-key="${key}"]`);
      field.focus({preventScroll:true});field.setSelectionRange(index+1,index+3);
      await selectWithPointer((index+1)%5);
    }
    for(const index of [4,2,0,3,1]) {
      await selectWithPointer(index);
      const field=host.querySelector(`[data-text-key="${key}"]`);
      if(document.activeElement!==field || field.selectionStart!==index+1 || field.selectionEnd!==index+3)throw Error('Per-shot focus or caret lost '+index);
      if(field.value!==expected.get(shots[index].shot_uuid))throw Error('Focus restore changed authored text');
    }
    const finalSaved=JSON.parse(JSON.stringify(latest));
    controller.cleanup();
    controller=widget.default(host,props(finalSaved));await frames();await frames();
    for(let index=0;index<5;index++){
      await select(index);
      if(host.querySelector(`[data-text-key="${key}"]`).value!==expected.get(shots[index].shot_uuid))throw Error('Reconstruction after mixed scroll lost authored text');
      if(latest.images[0].owner!==`Target ${index+1} {literal}`)throw Error('Reconstruction after mixed scroll lost binding');
      const box=host.querySelector('.group-card[data-group-id="imageSources"] .source-scrollbox');
      for(const [key,value] of [['height','120px'],['min-height','120px'],['max-height','120px'],['overflow-y','auto'],['flex','0 0 120px']])box.style.setProperty(key,value,'important');
      await frames();box.scrollTop=index%2 ? 0 : 90+index*70;box.dispatchEvent(new Event('scroll'));expectedScroll.set(shots[index].shot_uuid,box.scrollTop);
    }
    for(const index of [3,4,1,0,2]){
      await select(index);
      if(Math.abs(host.querySelector('.group-card[data-group-id="imageSources"] .source-scrollbox').scrollTop-expectedScroll.get(shots[index].shot_uuid))>1)throw Error('Reconstructed zero/nonzero page scroll leaked');
    }
    const max = Math.max(...durations);
    host.querySelector(`[data-prompt-shot="${shots[1].shot_uuid}"]`).click();
    controller.cleanup();
    const cleanupPublications=publications;
    await frames();await frames();
    if(publications!==cleanupPublications)throw Error('Cleanup allowed a deferred navigation publication');
    if (host.children.length || host.__hmbPromptLibraryApplyProps || host.__hmbPromptLibraryLifecycle) throw Error('Cleanup left a cached page or lifecycle behind');
    return {shots: 5, image_rows_per_shot: imageRows, burst_selections: 40, acknowledged_selections: 10, pure_navigation_work: pure, max_click_ms: max, per_shot_dirty_edit: 5, save_reopen_checks: 5, deleted_replaced_restored_uuid: true, publications, scroll_checks:17, rapid_scroll_switches:46, focus_caret_checks:5, legacy_scroll_checks:6, stale_scroll_ack_checks:1, post_scroll_save_reopen_checks:5, deferred_cleanup_checks:1, passed: true};
  }, imageRows);
  assert.deepEqual(errors, []);
  assert.equal(receipt.external_requests, 0);
  receipt.passed = true;
} catch (error) {
  receipt.passed = false;
  receipt.failure = String(error.stack || error);
  throw error;
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
  const output = new URL(`../../reports/slot-switch-optimization-20261020/prompt-prepared-pages${imageRows === 50 ? '-50' : ''}.json`, import.meta.url);
  fs.mkdirSync(path.dirname(fileURLToPath(output)), {recursive: true});
  fs.writeFileSync(output, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
}
