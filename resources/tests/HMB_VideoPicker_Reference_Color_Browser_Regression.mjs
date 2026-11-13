import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import {nativeTestPlaywright, nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';

const source = fs.readFileSync(new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js', import.meta.url), 'utf8');
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const names = ['FireflyAa', 'FireflyAa1', 'crowd:FireflyAa', 'fireflyAa'];
const rows = names.map(name => ({name, full_path: `|CHARACTERS|${name}:Root`, maya_uuid: 'SHARED-REFERENCE-UUID', reference_node: `${name}RN`}));
const base = {language:'ko', runtime_instance_id:'reference-colors', state_revision:10, state_writer:'python',
  scene_path:'C:/references.mb', scene_request_path:'C:/references.mb', active_slot_count:1,
  native_read_ready:true, status:'OUTLINER_READY', scene_stage:'OUTLINER_READY', outliner_nodes:rows,
  selected_outliner_path:rows[1].full_path, selected_outliner_uuid:rows[1].maya_uuid,
  slot_assignments:[{video_slot:1, bindings:[]}]};
assert.equal(picker.hmbPickerSelectedOutlinerNode(base).full_path, rows[1].full_path);
assert.equal(picker.hmbPickerSelectedOutlinerNode({...base, selected_outliner_path:'|missing'}), null);
const palettes = picker.hmbNormalizePickerMarkerCatalog(null).options;
for (const color of palettes) {
  let state = structuredClone(base);
  for (const row of rows) {
    state = picker.hmbPickerSelectOutlinerPath(state, row.full_path);
    state = picker.hmbPickerApplyColorToSelection(state, color);
  }
  assert.deepEqual(state.slot_assignments[0].bindings.map(b=>b.full_dag_path), rows.map(r=>r.full_path));
  assert.deepEqual(state.slot_assignments[0].bindings.map(b=>b.color), rows.map(()=>color));
  const cleared = picker.hmbPickerClearOutlinerColor(state, rows[1].full_path);
  assert.equal(cleared.slot_assignments[0].bindings.length, 3);
}

const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1600px;min-height:1100px}</style><div id="widget"></div><script type="module">
import mount from '/widget.js';
window.sent=[];window.props=value=>({value,onChange:next=>window.sent.push(next)});
window.mount=value=>{window.controller=mount(document.getElementById('widget'),window.props(value));};window.ready=true;
</script>`;
const server = http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser = await nativeTestPlaywright().chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
  const page = await browser.newPage({viewport:{width:1700,height:1250}});
  const origin = `http://127.0.0.1:${server.address().port}`;
  await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin);await page.waitForFunction(()=>window.ready);
  await page.evaluate(state=>window.mount(state),base);
  if (await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded')
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
  await page.waitForSelector('.hmbvp[data-picker-view="expanded"]');
  const state = await page.evaluate(({rows,palettes})=>{
    const host=document.getElementById('widget');
    const select=path=>Array.from(host.querySelectorAll('[data-group-path]')).find(el=>el.dataset.groupPath===path).click();
    const assign=color=>host.querySelector(`[data-color="${color}"]`).click();
    const colors=()=>Array.from(host.querySelectorAll('.outliner-row')).map(el=>el.querySelector('.assigned-chip')?.title||'');
    const result=[];
    for (const color of palettes) {
      for (const row of rows) {select(row.full_path);assign(color);}
      result.push({color,colors:colors()});
    }
    select(rows[1].full_path);assign('Blue');
    Array.from(host.querySelectorAll('[data-clear-color-path]')).find(el=>el.dataset.clearColorPath===rows[2].full_path).click();
    return {result,afterClear:colors()};
  },{rows,palettes});
  for (const row of state.result) assert.deepEqual(row.colors, rows.map(()=>row.color));
  assert.deepEqual(state.afterClear,[palettes.at(-1),'Blue','',palettes.at(-1)]);
  await page.waitForFunction(()=>window.sent.length>0);
  const saved = await page.evaluate(()=>structuredClone(window.sent.at(-1)));
  assert.equal(saved.slot_assignments[0].bindings.length,3);
  await page.reload();await page.waitForFunction(()=>window.ready);
  // Publication omits the unchanged READ catalog. The host supplies it again
  // when reopening; persisted assignments must not collapse on that remount.
  await page.evaluate(value=>window.mount(value),{...saved,outliner_nodes:rows});
  if (await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded')
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
  await page.waitForSelector('.outliner-row', {timeout:5000});
  const reopened=await page.locator('.outliner-row').evaluateAll(els=>els.map(el=>el.querySelector('.assigned-chip')?.title||''));
  assert.deepEqual(reopened,state.afterClear);
  if(process.env.HMB_PICKER_COLOR_SCREENSHOT) await page.screenshot({path:process.env.HMB_PICKER_COLOR_SCREENSHOT});
  assert.deepEqual(errors,[]);
  console.log('Repeated reference browser: PASS (16 repeated colors, independent recolor/clear, reload, no page errors)');
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
