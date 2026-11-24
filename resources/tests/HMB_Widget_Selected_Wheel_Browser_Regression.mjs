// The fixture mounts every registered visual widget and uses the reviewed Editor's
// actual React Flow wheel filter. The observer stands in for its D3 zoom callback.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {nativeTestBrowserPath, nativeTestPlaywright, readNativeEditorSource} from './_hmb_native_editor_fixture.mjs';

const root = fileURLToPath(new URL('../..', import.meta.url));
function argument(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
}
const library = argument('--library-root') || root;
const manifest = JSON.parse(fs.readFileSync(path.join(library, 'griptape-nodes-library.json')));
const hidden = new Set(['HMBImageAssetThumbnailPatchBridgeWidget', 'HMBVideoPickerCommandBridgeWidget']);
const widgets = manifest.widgets.filter(widget => !hidden.has(widget.name));
const explicitEditor = process.env.HMB_STOCK_EDITOR_0130_SOURCE || process.env.HMB_NATIVE_HEADER_EDITOR_SOURCE;
const stock = explicitEditor ? fs.readFileSync(explicitEditor, 'utf8') : readNativeEditorSource(root);
const hostClass = stock.match(/className:`(widget-container [^`]*\bnowheel)`/)?.[1];
const filter = stock.match(/function (\w+)\(\{noWheelClassName:\w+,preventScrolling:\w+,d3ZoomHandler:\w+\}\)\{.*?\}\}(?=function )/s);
const closest = stock.match(/([\w$]+)=\(e,t\)=>e\.target\.closest\(`\.\$\{t\}`\)/)
  || stock.match(/([\w$]+)=\(e,t\)=>\{if\(!t\)return!1;let n=e\.target;return n instanceof Element&&!!n\.closest\(`\.\$\{t\}`\)\}/);
const delta = stock.match(/([\w$]+)=e=>\{let t=e\.ctrlKey&&([\w$]+)\(\)\?10:1;return-e\.deltaY\*\(e\.deltaMode===1\?\.05:e\.deltaMode\?1:\.002\)\*t\}/);
assert.ok(hostClass && filter && closest && delta && filter[0].includes(closest[1] + '('),
  'Unrecognized stock wheel contract. Check the new Editor source before accepting these results.');
const native = `const ${closest[0]};const ${delta[2]}=()=>false;const ${delta[0]};${filter[0]}
  return {filter:${filter[1]},delta:${delta[1]}}`;
const cases = {};
const errors = [];
const report = {editor_sha256: createHash('sha256').update(stock).digest('hex'), widget_sha256:{}, cases, errors, mounted_controls:{},
  paid_calls: 0, external_requests: 0, passed: false};
const browser = await nativeTestPlaywright().chromium.launch({executablePath: nativeTestBrowserPath(), headless: true});

function fixture(name) {
  return `<style>
    body{margin:0}.react-flow__node{width:1460px}.widget-container{height:1544px}
    .stock-fields{display:flex;gap:12px;height:80px}.stock-fields textarea{width:200px;height:60px;overflow:auto}
    .stock-fields input{align-self:start}aside{position:fixed;right:0;top:0;z-index:100}
    #first{outline:1px dotted rgb(109,126,145);outline-offset:1px}
    aside textarea{width:40px;height:30px}
  </style>
  <main class="react-flow"><div class="react-flow__renderer"><div class="react-flow__pane">
  <div class="react-flow__viewport"><section class="react-flow__node" data-id="${name}">
    <div class="stock-fields">
      <textarea id="first" class="nodrag nowheel"></textarea><textarea id="second" class="nodrag nowheel"></textarea>
      <textarea id="empty" class="nodrag nowheel"></textarea>
      <input type="number" id="number" class="nodrag nowheel" value="3"><span id="blank">Node background</span>
    </div><div class="${hostClass}"></div>
  </section><section class="react-flow__node" data-id="Standard"><textarea id="standard" class="nowheel"></textarea></section>
  </div></div></div></main><aside><textarea class="nowheel" id="inspector"></textarea></aside>`;
}

// These selectors are part of the actual mounted widgets. Populate their content
// only to overflow the visible area; production listeners are never replaced.
const localSelectors = {
  HMBImageAssetLibraryWidget: '.asset-scroll',
  HMBVideoPickerLibraryWidget: '.outliner-scroll,.compact-shot-assets',
  HMBPromptLibraryScopedBindingWidget: 'textarea:not(:disabled)',
  HMBAnalysisAgentWidget: '[data-guidance]',
};

async function installFixture(page, widget) {
  const bytes = fs.readFileSync(path.join(library, widget.path));
  report.widget_sha256[widget.path] = createHash('sha256').update(bytes).digest('hex');
  await page.setContent(fixture(widget.name));
  await page.evaluate(async ({native, source, name}) => {
    const editor = Function(native)();
    const canvas = document.querySelector('.react-flow__pane');
    window.calls = [];
    window.middleDowns = 0;
    canvas.addEventListener('pointerdown', e => { if (e.button === 1) window.middleDowns++; });
    canvas.addEventListener('wheel', editor.filter({noWheelClassName:'nowheel', preventScrolling:true,
      d3ZoomHandler(event) {
        window.calls.push({delta:editor.delta(event), x:event.clientX, y:event.clientY,
          dx:event.deltaX, dy:event.deltaY, mode:event.deltaMode, ctrl:event.ctrlKey, shift:event.shiftKey, alt:event.altKey});
      }}), {passive:false});
    // Native message fields also stop propagation at the parameter's capture
    // boundary. An unselected wheel must still get to React Flow exactly once.
    document.querySelector('.stock-fields').addEventListener('wheel', e => e.stopPropagation(), true);
    document.querySelector('#first').value = document.querySelector('#second').value = 'Line\n'.repeat(80);
    const url = URL.createObjectURL(new Blob([source], {type:'text/javascript'}));
    let module;
    try { module = await import(url); } finally { URL.revokeObjectURL(url); }
    const host = document.querySelector('.widget-container');
    const value = name === 'HMBAnalysisAgentWidget'
      ? {shot_uuid:'qa-shot', shots:[{shot_uuid:'qa-shot',number:1}], slot:{kind:'video'}, source:{}, sources:[]}
      : {multi_shot_enabled:true};
    if (name === 'HMBPromptLibraryScopedBindingWidget') {
      value.images = Array.from({length:16}, (_,i) => ({
        slot:i+1, present:true, manual:true, label:'Image '+(i+1), image_main_type:'Character',
        image_sub_type:'Full Appearance',
        asset_managed:true, asset_source_uid:'qa-row-'+i, asset_verified:i === 1, asset_source_kind:'project',
        frame_range_intent:{version:1,enabled:true,start_frame:1,end_frame:120,ranges:[]},
      }));
      value.image_asset = {enabled:true,order_managed:true,selected_assets:16,
        ordered_source_uids:value.images.map(row => row.asset_source_uid)};
    }
    window.controller = module.default(host, {nodeName:name, value, onChange(){}});
    window.wheel = (element, init={}) => {
      window.calls.length = 0;
      element.dispatchEvent(new WheelEvent('wheel', {bubbles:true,cancelable:true,deltaY:100,...init}));
      return [...window.calls];
    };
    window.press = (element, button=0) =>
      element.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,pointerType:'mouse',isPrimary:true,button}));
    window.scrollHighlightIs = element => {
      const marked = document.querySelectorAll('[data-hmb-active-scroll]');
      if (!element) return marked.length === 0;
      const style = getComputedStyle(element);
      return marked.length === 1 && marked[0] === element &&
        style.outlineStyle === 'solid' && style.outlineWidth === '2px' &&
        style.outlineColor === 'rgb(77, 216, 255)' && style.outlineOffset === '-2px';
    };
    window.afterPaint = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }, {native, source:bytes.toString('utf8'), name:widget.name});
}

async function verifyPromptImageViewport(page, record) {
  const list = page.locator('[data-scroll-id="imageSources"]');
  const row = list.locator('.source-row.image').first();
  const name = row.locator('[data-field="label"]');
  const main = row.locator('[data-field="image_main_type"]');
  const highlighted = () => list.evaluate(el => scrollHighlightIs(el));
  const reset = async () => {
    await page.locator('#blank').click();
    await list.evaluate(el => { el.scrollTop = 0; });
  };
  await reset();
  await name.click();
  record('prompt_name_first_click_keeps_focus_and_selects_table',
    await highlighted() && await name.evaluate(el => el === document.activeElement));
  await page.keyboard.insertText('한글');
  record('prompt_name_accepts_korean_edit', (await name.inputValue()).includes('한글'));
  const fields = ['image_main_type','image_sub_type','owner','binding_video_slots','color_picks'];
  for (const field of fields) {
    await reset();
    const control = row.locator('select[data-field="'+field+'"]').first();
    await control.click();
    const opened = await control.evaluate(el => el === document.activeElement && el.matches(':open'));
    await page.keyboard.press('Enter');
    record('prompt_'+field+'_first_click_opens_and_selects_table', opened && await highlighted());
  }
  await main.click();
  await page.keyboard.press('Enter');
  const originalValue = await main.inputValue();
  await main.hover();
  await page.evaluate(() => { window.calls.length = 0; });
  await page.mouse.wheel(0,120);
  await page.evaluate(() => afterPaint());
  record('prompt_wheel_over_select_scrolls_table_with_value_preserved',
    await list.evaluate(el => el.scrollTop > 0 && window.calls.length === 0) && await main.inputValue() === originalValue);
  await reset();
  const lockedType = list.locator('.source-row.image select[data-field="image_main_type"]:disabled').first();
  await lockedType.click({force:true});
  record('prompt_readonly_asset_type_selects_table_keeps_binding', await highlighted() && await lockedType.isDisabled());
  const screenshot = argument('--prompt-screenshot');
  if (screenshot) await list.screenshot({path:screenshot});
  const frameGeometry = () => list.evaluate(el => {
    const frame = document.querySelector('[data-hmb-scroll-frame]');
    if (!frame || getComputedStyle(frame).pointerEvents !== 'none') return false;
    const target = el.getBoundingClientRect(), paint = frame.getBoundingClientRect();
    return ['left','right','top','bottom'].every(edge => Math.abs(target[edge]-paint[edge]) <= 1);
  });
  await list.evaluate(el => { el.scrollTop = el.scrollHeight; });
  await page.evaluate(() => afterPaint());
  record('prompt_frame_follows_viewport_at_end_of_list', await frameGeometry());
  await list.evaluate(el => { el.closest('.react-flow__viewport').style.transform = 'translate(8px,12px) scale(.7)'; });
  await page.evaluate(() => afterPaint());
  record('prompt_frame_follows_canvas_pan_and_zoom', await frameGeometry());
  await list.evaluate(el => { el.closest('.react-flow__viewport').style.removeProperty('transform'); });
  await reset();
  const track = row.locator('[data-frame-track]');
  await track.scrollIntoViewIfNeeded();
  const box = await track.boundingBox();
  const y = box.y + box.height/2;
  await page.mouse.move(box.x + box.width*.25,y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width*.55,y,{steps:4});
  await page.mouse.up();
  record('prompt_range_single_drag_edits_with_whole_table_selected',
    await highlighted() && await track.locator('[data-frame-range-index]').count() === 1);
  await page.locator('#blank').click();
  record('prompt_background_clears_table_enables_zoom',
    await name.evaluate(el => scrollHighlightIs(null) && wheel(el).length === 1));
}

// Computed outlines can pass even when positioned thumbnails paint over them.
// Sample the rendered pixels along all four sides under actual Chromium compositing.
async function visibleEdges(page, surface) {
  const png = await surface.screenshot();
  return page.evaluate(async bytes => {
    const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(bytes), c => c.charCodeAt(0))], {type:'image/png'}));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0);
    const {width:w, height:h} = canvas;
    const data = ctx.getImageData(0, 0, w, h).data;
    const cyan = (x,y) => {
      const i = 4 * (y*w + x);
      return data[i] < 115 && data[i+1] >= 180 && data[i+2] >= 215;
    };
    return ['top','bottom','left','right'].map(edge => {
      const horizontal = edge === 'top' || edge === 'bottom';
      let matched = 0, total = 0;
      for (let p=8; p < (horizontal ? w : h) - 8; p++) {
        total++;
        if ([0,1,2].some(d => horizontal ? cyan(p, edge === 'top' ? d : h-1-d) : cyan(edge === 'left' ? d : w-1-d,p))) matched++;
      }
      return matched / total;
    });
  }, png.toString('base64'));
}

async function verifyPaint(page, widget, record) {
  const isGrid = widget.name === 'HMBImageAssetLibraryWidget';
  const surface = page.locator(isGrid ? '.asset-scroll' : '#first').first();
  if (isGrid) {
    await surface.evaluate(el => {
      // Intersect all viewport edges with opaque positioned card layers.
      el.style.cssText += ';height:150px;flex:none;padding:0;scrollbar-gutter:auto;overflow:auto;width:360px';
      el.innerHTML = '<div class="asset-card" style="height:490px;background:#304050;position:relative;z-index:4;contain:paint"></div>';
      el.scrollTop = 149;
    });
  }
  await surface.evaluate(el => { press(el.firstElementChild || el); });
  await page.evaluate(() => afterPaint());
  const edges = await visibleEdges(page, surface);
  (report.paint_edges ||= {})[widget.name] = edges;
  record('four_edges_visible_in_pixels', edges.every(fraction => fraction >= .98));
  if (isGrid) {
    const retained = await surface.evaluate(async original => {
      const frame = document.querySelector('[data-hmb-scroll-frame]');
      if (!frame) return false;
      const duplicate = frame.cloneNode(true);
      frame.replaceWith(duplicate);
      await afterPaint();
      if (document.querySelectorAll('[data-hmb-scroll-frame]').length !== 1 || frame.previousElementSibling !== original) return false;
      original.dataset.hmbWheelKey = 'grid-project-A-shot-A';
      press(document.querySelector('#blank')); press(original);
      const next = original.cloneNode(true);
      original.replaceWith(next);
      await afterPaint();
      const same = scrollHighlightIs(next) && wheel(next).length === 0;
      next.dataset.hmbWheelKey = 'grid-project-B-shot-B';
      await afterPaint();
      return same && scrollHighlightIs(null) && wheel(next).length === 1;
    });
    record('refresh_keeps_same_grid_only', retained);
  }
  await page.evaluate(() => press(document.querySelector('#blank')));
}

async function verifyWidget(page, widget, result) {
  const record = (name, passed) => { result[name] = Boolean(passed); };
  await verifyPaint(page, widget, record);
  const checks = await page.evaluate(async () => {
    const host = document.querySelector('.widget-container');
    const first = document.querySelector('#first'), second = document.querySelector('#second');
    const number = document.querySelector('#number'), blank = document.querySelector('#blank');
    const custom = {deltaMode:1,deltaX:2,deltaY:3,clientX:119,clientY:17,shiftKey:true,ctrlKey:true,altKey:true};
    const event = wheel(first,custom);
    const forwarded = event.length === 1 && event[0].x === 119 && event[0].y === 17 &&
      event[0].dx === 2 && event[0].dy === 3 && event[0].mode === 1 && event[0].shift && event[0].ctrl && event[0].alt;
    const downs = wheel(host), ups = wheel(host,{deltaY:-100});
    const background = downs.length === 1 && downs[0].delta < 0 && ups.length === 1 && ups[0].delta > 0;
    const controls = [...host.querySelectorAll('button,input,select,textarea,[contenteditable="true"],.nowheel')]
      .filter(el => el.getBoundingClientRect().height > 0);
    const blocked = controls.filter(el => wheel(el).length !== 1)
      .map(el => el.tagName.toLowerCase() + '.' + el.className);
    const numeric = wheel(number).length === 1 && number.value === '3';
    const hoverUnmarked = scrollHighlightIs(null);
    const nativeOutline = el => [getComputedStyle(el).outline,getComputedStyle(el).outlineOffset].join(' ');
    const originalOutline = nativeOutline(first);
    const box = el => {
      const {x,y,width,height} = el.getBoundingClientRect();
      return [x,y,width,height,el.clientWidth,el.clientHeight,el.scrollWidth,el.scrollHeight].join(',');
    };
    const geometry = box(first);
    press(first);
    const onlyFirst = wheel(first).length === 0 && wheel(second).length === 1;
    const markedFirst = scrollHighlightIs(first) && geometry === box(first);
    const duplicate = first.cloneNode(true);
    duplicate.removeAttribute('id');
    first.after(duplicate);
    await afterPaint();
    const duplicateUnmarked = scrollHighlightIs(first) && wheel(duplicate).length === 1;
    duplicate.remove();
    press(second,1);
    const middle = window.middleDowns === 1 && wheel(first).length === 0 && wheel(second).length === 1;
    press(second);
    const transfer = wheel(first).length === 1 && wheel(second).length === 0;
    const moved = scrollHighlightIs(second) && nativeOutline(first) === originalOutline;
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    const escape = wheel(second).length === 1;
    const escapeCleared = scrollHighlightIs(null);
    press(first);
    press(blank);
    const outside = wheel(first).length === 1;
    const outsideCleared = scrollHighlightIs(null) && nativeOutline(first) === originalOutline;
    const empty = document.querySelector('#empty');
    press(empty);
    const emptyIsUnmarked = scrollHighlightIs(null) && wheel(empty).length === 1;
    empty.value = 'More lines\n'.repeat(100);
    empty.dispatchEvent(new Event('input', {bubbles:true}));
    await afterPaint();
    const highlightOnOverflow = scrollHighlightIs(empty) && wheel(empty).length === 0;
    empty.value = '';
    empty.dispatchEvent(new Event('input', {bubbles:true}));
    await afterPaint();
    const highlightOffNoOverflow = scrollHighlightIs(null) && wheel(empty).length === 1;
    press(first);
    const replacement = document.createElement('textarea');
    replacement.id = first.id;
    replacement.className = first.className;
    first.replaceWith(replacement);
    const detached = wheel(replacement).length === 1;
    const detachedCleared = scrollHighlightIs(null) && !first.hasAttribute('data-hmb-active-scroll');
    const isolation = wheel(document.querySelector('#standard')).length === 0 &&
      wheel(document.querySelector('#inspector')).length === 0;
    return {checks:{background, every_visible_control_zooms:blocked.length === 0, unselected_delta_and_anchor:forwarded, number_unchanged:numeric, only_selected:onlyFirst,
      middle_pan:middle, transfer, escape, click_outside:outside, replaced_owner:detached, other_surfaces:isolation,
      hover_without_highlight:hoverUnmarked, selected_viewport_outline_without_reflow:markedFirst,
      cloned_sibling_cannot_inherit_outline:duplicateUnmarked,
      outline_transfers_and_native_style_restored:moved, escape_clears_outline:escapeCleared,
      outside_click_clears_outline:outsideCleared, empty_textarea_unmarked:emptyIsUnmarked,
      editing_updates_scroll_outline:highlightOnOverflow && highlightOffNoOverflow,
      replaced_owner_clears_outline:detachedCleared},
      controls:controls.length, blocked};
  });
  Object.assign(result, checks.checks);
  report.mounted_controls[widget.name] = {count:checks.controls, blocked:checks.blocked};
  if (widget.name === 'HMBPromptLibraryScopedBindingWidget') await verifyPromptImageViewport(page, record);
  const selector = localSelectors[widget.name];
  if (selector) {
    const prepared = await page.evaluate(selector => {
      const field = [...document.querySelector('.widget-container').querySelectorAll(selector)]
        .find(el => el.getBoundingClientRect().height > 0);
      if (!field) return false;
      field.dataset.fixtureScroll = 'true';
      Object.assign(field.style,{overflow:'auto',width:'280px',height:'75px',minHeight:'0',maxHeight:'75px'});
      if (field.tagName === 'TEXTAREA') field.value = 'A rendered reference\n'.repeat(100);
      else {
        const content = document.createElement('div');
        content.style.cssText = 'height:1200px;width:180px;flex:none;grid-column:1/-1';
        field.append(content);
      }
      return field.scrollHeight > field.clientHeight && field.clientHeight > 0;
    }, selector);
    record('widget_viewport_mounted', prepared);
    if (prepared) {
      const field = page.locator('[data-fixture-scroll]');
      const checkWheel = async () => {
        await page.evaluate(() => { window.calls.length = 0; });
        await page.mouse.wheel(0,100);
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        return field.evaluate(el => ({n:window.calls.length, top:el.scrollTop}));
      };
      await field.hover({position:{x:8,y:8},force:true});
      const unselected = await checkWheel();
      record('widget_hover_zooms', unselected.n === 1 && unselected.top === 0);
      await page.mouse.click(...await field.evaluate(el => {const r=el.getBoundingClientRect();return [r.x+8,r.y+8];}));
      const selected = await checkWheel();
      record('widget_click_scrolls', selected.n === 0 && selected.top > 0);
      record('widget_highlight_matches_scrolling_viewport', await field.evaluate(el => scrollHighlightIs(el)));
      await field.evaluate(el => { el.scrollTop = el.scrollHeight; });
      const atEnd = await checkWheel();
      record('widget_scroll_end_contained', atEnd.n === 0);
      await page.keyboard.press('Escape');
      const released = await checkWheel();
      record('widget_escape_zooms', released.n === 1);
      record('widget_escape_removes_highlight', await field.evaluate(() => scrollHighlightIs(null)));
    }
  }
  if (widget.name === 'HMBVideoPickerLibraryWidget') {
    const horizontal = await page.evaluate(() => {
      const host = document.querySelector('.widget-container');
      const strip = [...host.querySelectorAll('.compact-shot-assets,.video-assets-body')]
        .find(el => el.getBoundingClientRect().height > 0);
      if (!strip) return {problem:'absent strip'};
      strip.classList.remove('empty');
      const card = document.createElement('div');
      card.style.cssText = 'width:1200px;min-width:1200px;height:18px;flex:none';
      Object.assign(strip.style, {overflowX:'auto',overflowY:'hidden',display:'block',height:'100px',width:'240px'});
      strip.replaceChildren(card);
      if (strip.scrollWidth <= strip.clientWidth || strip.scrollHeight > strip.clientHeight+1)
        return {problem:'strip geometry', strip:strip.className, dimensions:[strip.clientWidth,strip.scrollWidth,strip.clientHeight,strip.scrollHeight]};
      const unselected = wheel(card).length === 1 && strip.scrollLeft === 0;
      press(card);
      const captured = wheel(card).length;
      const selected = captured === 0 && strip.scrollLeft > 0;
      return {unselected, selected, captured, left:strip.scrollLeft, strip:strip.className, highlight:scrollHighlightIs(strip)};
    });
    report.picker_horizontal = horizontal;
    record('picker_horizontal_card_wheel', horizontal.unselected && horizontal.selected);
    record('picker_horizontal_highlights_strip', horizontal.highlight);
  }
  if (widget.name === 'HMBAgentLibraryWidget') {
    const peer = widgets.find(item => item.name === 'HMBPromptLibraryScopedBindingWidget');
    const transfer = await page.evaluate(async source => {
      const node = document.createElement('section');
      node.className = 'react-flow__node'; node.dataset.id = 'Peer Prompt';
      node.innerHTML = '<textarea class="nowheel" style="height:45px;overflow:auto"></textarea><div class="widget-container nodrag nowheel"></div>';
      document.querySelector('.react-flow__viewport').append(node);
      const url = URL.createObjectURL(new Blob([source], {type:'text/javascript'}));
      const mod = await import(url);
      URL.revokeObjectURL(url);
      const peerMount = mod.default(node.querySelector('.widget-container'), {nodeName:'Peer Prompt',value:{multi_shot_enabled:true},onChange(){}});
      const current = document.querySelector('#second'), other = node.querySelector('textarea');
      other.value = 'Peer\n'.repeat(50);
      press(current);
      const initial = wheel(current).length === 0 && wheel(other).length === 1 && scrollHighlightIs(current);
      press(other);
      const transferred = wheel(current).length === 1 && wheel(other).length === 0 && scrollHighlightIs(other);
      peerMount.cleanup(); node.remove();
      return initial && transferred && wheel(current).length === 1 && scrollHighlightIs(null);
    }, fs.readFileSync(path.join(library,peer.path),'utf8'));
    record('selection_between_libraries_and_peer_unmount', transfer);
  }
  if (widget.name === 'HMBSoundLibraryWidget') {
    // A folder button that repaints its list is the reason the shared router
    // reacquires the same viewport after a click. Keep that cue shot-local.
    await page.evaluate(() => {
      const parent = document.createElement('section');
      parent.dataset.shotUuid = 'original-shot';
      parent.style.cssText = 'position:fixed;left:800px;top:4px;z-index:100';
      document.querySelector('.react-flow__node').append(parent);
      let clicks = 0;
      const render = () => {
        const list = document.createElement('div');
        list.className = 'fixture-repaint-list';
        list.style.cssText = 'height:64px;width:160px;overflow:auto;background:#111';
        list.innerHTML = '<button data-group-path="folder">Folder</button><div style="height:400px"></div>';
        list.firstElementChild.addEventListener('click', () => {
          if (++clicks === 2) parent.dataset.shotUuid = 'other-shot';
          render();
        });
        parent.replaceChildren(list);
      };
      render();
    });
    const button = page.locator('.fixture-repaint-list button');
    await button.click();
    await page.evaluate(() => afterPaint());
    record('same_shot_repaint_restores_viewport_outline', await button.evaluate(el =>
      scrollHighlightIs(el.parentElement) && wheel(el).length === 0));
    await button.click();
    await page.evaluate(() => afterPaint());
    record('another_shot_cannot_inherit_outline', await button.evaluate(el =>
      scrollHighlightIs(null) && wheel(el).length === 1));
  }
  const restored = await page.evaluate(() => {
    const host = document.querySelector('.widget-container');
    const field = document.querySelector('#second');
    press(field);
    const before = scrollHighlightIs(field);
    window.controller.cleanup();
    return {gestures:host.classList.contains('nowheel') && wheel(field).length === 0, outline:before && scrollHighlightIs(null)};
  });
  record('unmount_releases_gestures', restored.gestures);
  record('unmount_releases_outline', restored.outline);
}

try {
  for (const widget of widgets) {
    const result = cases[widget.name] = {};
    const page = await browser.newPage({viewport:{width:1500,height:1600}});
    await page.route('**/*', route => { report.external_requests++; return route.abort(); });
    page.on('pageerror', error => errors.push(`${widget.name}: ${error.message}`));
    try { await installFixture(page, widget); await verifyWidget(page, widget, result); }
    catch (error) { errors.push(`${widget.name}: ${error.message}`); }
    finally { await page.close(); }
  }
  const failed = Object.entries(cases).flatMap(([widget, checks]) =>
    Object.entries(checks).filter(([,passed]) => !passed).map(([name]) => `${widget}.${name}`));
  assert.deepEqual([...errors, ...failed], []);
  assert.ok(widgets.length && report.external_requests === 0);
  report.passed = true;
} finally {
  await browser.close();
  const output = argument('--evidence-path');
  if (output) {
    fs.mkdirSync(path.dirname(output), {recursive:true});
    fs.writeFileSync(output, JSON.stringify(report,null,2));
  }
  console.log(JSON.stringify(report));
}
