// Exercise the HMB widget without loading any Griptape editor code or making requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {nativeTestBrowserPath, nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const source = fs.readFileSync(new URL('../../widgets/HMBImageBashWidget.js', import.meta.url), 'utf8');
const browser = await nativeTestPlaywright().chromium.launch({headless:true, executablePath:nativeTestBrowserPath()});
try {
  const page = await browser.newPage({viewport:{width:1400,height:900}});
  const external = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => { external.push(route.request().url()); return route.abort(); });
  await page.setContent('<div id="widget" class="nodrag"></div>');
  await page.evaluate(async code => {
    const {default:mount} = await import('data:text/javascript;base64,' + btoa(unescape(encodeURIComponent(code))));
    const solid = color => {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 2;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = color; ctx.fillRect(0, 0, 2, 2);
      return canvas.toDataURL('image/png');
    };
    const red = solid('#ff0000'), blue = solid('#0000ff');
    const layer = (id, type, src, order, x) => ({id, type, src, order, x, y:1, width:2, height:2,
      scaleX:1, scaleY:1, visible:true, opacity:1, name:id, preserved_tag:`tag:${id}`});
    const legacy = {value:red, name:'Saved scene', meta:{created_at:'old-commit', custom:'retained',
      hmb_canvas:{width:4, height:2, background_color:'#ffffff'},
      input_images:[{id:'asset',url:red}], konva_json:{extra:'retained', images:[layer('asset','image',red,1,1),
        layer('brush','brush',blue,2,3)], lines:[]},
      hmb_image_bash:{editor_snapshot_id:'snapshot-original', source_bindings:[{source_uid:'source-1', input_id:'asset'}]}}};
    window.input = legacy;
    window.payloads = [];
    window.props = value => ({parameterName:'bash_image', value, onChange:payload => payloads.push(payload)});
    window.authority = (phase, snapshot) => ({schema:'hmb-image-bash-header-v1',
      preparation:{phase,editor_snapshot_id:snapshot}});
    window.widget = mount(document.querySelector('#widget'), props({...legacy,
      HMB_IMAGE_BASH_UI:authority('preparing','snapshot-original')}));
  }, source);
  const open = page.getByRole('button', {name:'HMB Image Bash 편집기 열기'});
  const apply = page.getByRole('button', {name:'Apply PNG'});
  assert.equal(await open.isDisabled(),true);
  await page.evaluate(() => widget.update(props({...input,HMB_IMAGE_BASH_UI:authority('ready','snapshot-original')})));
  await open.click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', {name:'brush',exact:true}).click();
  await dialog.getByText('불투명도 %').locator('input').fill('50');
  await dialog.getByText('불투명도 %').locator('input').press('Tab');
  await apply.click();
  const result = await page.evaluate(async () => {
    const payload = payloads[0];
    const image = new Image(); image.src = payload.value; await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = 4; canvas.height = 2;
    const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
    const commit = payload.meta.created_at;
    const saved = structuredClone(payload);
    saved.meta.hmb_image_bash.editor_snapshot_id = 'snapshot-saved';
    saved.meta.hmb_image_bash.apply = {editor_commit:commit,output_path:'fixture.png'};
    widget.update(props(saved));
    window.saved = saved;
    return {size:[image.width,image.height], left:[...ctx.getImageData(0,0,1,1).data], right:[...ctx.getImageData(3,0,1,1).data],
      input, payload};
  });
  assert.deepEqual(result.size,[4,2]);
  assert.deepEqual(result.left,[255,0,0,255]);
  // Canvas blend/PNG round trips differ by one 8-bit step across Chromium
  // raster backends. Limit tolerance to the two half-blended channels;
  // saturated blue, alpha, neutral balance and authored opacity stay exact.
  assert.equal(result.right.length,4);
  assert.equal(result.right[0],result.right[1]);
  assert.ok(Number.isInteger(result.right[0]) && Math.abs(result.right[0]-127)<=1,
    `50% blue over white red/green channel is outside one LSB: ${result.right}`);
  assert.deepEqual(result.right.slice(2),[255,255]);
  assert.equal(result.payload.meta.konva_json.images[1].opacity,0.5);
  assert.deepEqual(result.payload.meta.hmb_image_bash.source_bindings,result.input.meta.hmb_image_bash.source_bindings);
  assert.equal(result.payload.meta.konva_json.images[1].preserved_tag,'tag:brush');
  assert.equal(result.payload.meta.konva_json.extra,'retained');
  assert.equal(result.payload.meta.custom,'retained');
  assert.equal(result.payload.meta.hmb_editor,'hmb-image-bash-editor-v1');
  assert.equal(Object.hasOwn(result.payload,'HMB_IMAGE_BASH_UI'),false);
  await dialog.getByText('PNG 저장 완료').waitFor();
  await dialog.getByRole('button',{name:'닫기',exact:true}).last().click();
  await open.click();
  await dialog.getByRole('button',{name:'brush',exact:true}).click();
  assert.equal(await dialog.getByText('불투명도 %').locator('input').inputValue(),'50');
  await page.evaluate(() => widget.update(props({...saved,meta:{...saved.meta,
    hmb_image_bash:{...saved.meta.hmb_image_bash,editor_snapshot_id:'other-workspace'}}})));
  await dialog.getByText('연결 또는 장면이 바뀌었습니다. 편집기를 다시 열어 주세요.').waitFor();
  assert.equal(await apply.isDisabled(),true);
  assert.deepEqual(await page.evaluate(() => payloads.length),1);
  assert.deepEqual(external,[]);
  assert.deepEqual(errors,[]);
  console.log('HMB-owned widget: saved image/brush layers, PNG color/alpha, Apply acknowledgement, reopen and stale scope PASS');
} finally {
  await browser.close();
}
