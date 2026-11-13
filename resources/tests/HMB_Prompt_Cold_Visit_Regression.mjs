// Measure a previously unopened 50-image Shot in the real widget and Chromium.
// Screen paint comes from compositor frames; edit uses a browser-generated input event.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const runtimeModules = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
function dependency(name) {
  try { return require(name); }
  catch { return require(path.join(runtimeModules, name)); }
}
const { chromium } = dependency('playwright');
const { decode } = dependency('jpeg-js');
const installedWidget = path.join(os.homedir(), 'Documents/GriptapeNodes/libraries/HMB_GP_Production/widgets/HMBPromptLibraryScopedBindingWidget.js');
const file = {
  before: process.env.HMB_PROMPT_COLD_BASELINE || installedWidget,
  after: process.env.HMB_PROMPT_COLD_CANDIDATE || new URL('../../widgets/HMBPromptLibraryScopedBindingWidget.js', import.meta.url),
};
const modes = process.env.HMB_PROMPT_COLD_MODE ? [process.env.HMB_PROMPT_COLD_MODE] : ['before', 'after'];
const sampleCount = Number(process.env.HMB_PROMPT_COLD_SAMPLES || 12);
assert.ok(modes.every(mode => Object.hasOwn(file, mode)));
assert.ok(Number.isInteger(sampleCount) && sampleCount >= 2);
const source = Object.fromEntries(modes.map(mode => [mode, fs.readFileSync(file[mode])]));
const hashes = Object.fromEntries(modes.map(mode => [mode, crypto.createHash('sha256').update(source[mode]).digest('hex')]));
const report = {
  schema: 'hmb-prompt-cold-visit-v1',
  fixture_sha256: crypto.createHash('sha256').update(fs.readFileSync(new URL(import.meta.url))).digest('hex'),
  reproduce: {
    command: 'node resources/tests/HMB_Prompt_Cold_Visit_Regression.mjs',
    mode: modes,
    baseline_env: 'HMB_PROMPT_COLD_BASELINE',
    candidate_env: 'HMB_PROMPT_COLD_CANDIDATE',
    samples_env: 'HMB_PROMPT_COLD_SAMPLES',
    source_paths: Object.fromEntries(modes.map(mode => [mode, String(file[mode])])),
  },
  source_sha256: hashes,
  external_requests: 0,
  paid_submissions: 0,
  samples_per_metric_per_variant: sampleCount,
  workload: { shots: 5, images_per_shot: 50, viewport_width: 1800, viewport_height: 1400 },
  scope: {
    paint: 'Click to first observed Chromium compositor frame displaying the actual target source input. Captured by CDP screencast; the captured frame is an observation bound, not a claim about unobserved frames.',
    edit: 'Separate cold visits. Record first hit-testable control, first browser-generated trusted InputEvent at capture, and completion of input handlers. The edit is then verified in the published state.',
    state: 'Synthetic saved Prompt widget state; each timing sample remounts a fresh widget on Shot 1 before selecting an unopened Shot 2.',
  },
  measurements: {},
  compatibility: {},
};
const server = http.createServer((request, response) => {
  const mode = request.url?.match(/^\/(before|after)\.js$/)?.[1];
  if (mode && source[mode]) {
    response.setHeader('Content-Type', 'text/javascript; charset=utf-8');
    response.end(source[mode]);
  } else {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden;background:#101522}#shell{width:1760px;height:1390px}#native-header{height:52px}</style><div class="react-flow__node" id="shell"><div id="native-header">Synthetic native header</div><div id="host"></div></div>');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));

function markerPainted(data, target) {
  const pixels = decode(Buffer.from(data, 'base64'), { useTArray: true }).data;
  let matching = 0;
  for (let i = 0; i < pixels.length; i += 8) {
    const [r, g, b] = [pixels[i], pixels[i + 1], pixels[i + 2]];
    const matchingPixel = target ? r < 45 && g > 220 && b >= 68 && b < 123
      : r > 230 && g < 45 && b >= 176 && b < 226;
    if (matchingPixel && ++matching > 80) return true;
  }
  return false;
}

function stats(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return {
    median_ms: sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2,
    p95_ms: sorted[Math.ceil(sorted.length * 0.95) - 1],
    min_ms: sorted[0],
    max_ms: sorted.at(-1),
  };
}

function setupWidget(mode) {
  return import(`/${mode}.js`).then(widget => {
    const host = document.querySelector('#host');
    const channel = '11111111-1111-4111-8111-111111111111';
    const shots = Array.from({ length: 5 }, (_, index) => ({
      channel_uuid: channel,
      shot_uuid: `22222222-2222-4222-8222-${String(index + 1).padStart(12, '0')}`,
      number: index + 1,
      name: `Cold Shot ${index + 1}`,
      selected_source_uids: [],
    }));
    const target = shots[1].shot_uuid;
    const base = widget.normalizeState({ multi_shot_enabled: true, shot: shots[0], source_sync_revision: 1,
      image_asset: { shot_catalog: shots, shot_catalog_routing: {
        publisher_instance_uuid: channel, channel_uuid: channel, generation: 1, metadata_sha256: 'a'.repeat(64),
      } },
    });
    const textKey = Object.keys(base.text)[0];
    const label = (shot, row) => `Shot ${shot} image ${row}`;
    const owner = (shot, row) => `Target ${shot}/${row} {literal}`;
    const sourceName = (shot, row) => `S${shot}_IMAGE_${String(row).padStart(2, '0')}`;
    for (const shot of shots) {
      widget.hmbSwitchPromptShot(base, shot.shot_uuid);
      base.images = Array.from({ length: 50 }, (_, index) => ({
        ...structuredClone(base.images[0]), slot: index + 1, token: `@image${index + 1}`,
        name: sourceName(shot.number, index + 1), label: label(shot.number, index + 1), owner: owner(shot.number, index + 1), surface_2d: false,
      }));
      base.text[textKey] = `Saved Shot ${shot.number} 한글 {literal} 0 OFF`;
      widget.hmbStorePromptShotDocument(base);
    }
    widget.hmbSwitchPromptShot(base, shots[0].shot_uuid);
    const marker = document.createElement('style');
    marker.textContent = [
      [shots[0].shot_uuid, label(1, 1), 'rgb(249,23,201)'],
      [target, label(2, 1), 'rgb(17,247,94)'],
    ].map(([uuid, name, color]) => `[data-shot-editor="${uuid}"] [data-kind="image"][data-index="0"] input[data-field="label"][value="${name}"] { background:${color}!important; color:#060606!important }`).join('\n');
    document.head.append(marker);
    let controller;
    let latest;
    let publications = 0;
    const props = value => ({ value: JSON.stringify(value), disabled: false, onChange(next) {
      latest = JSON.parse(next);
      publications++;
      controller.update(props(latest));
    } });
    const paintBoundary = () => new Promise(resolve => requestAnimationFrame(resolve));
    const startTab = uuid => host.querySelector(`[data-prompt-shot="${uuid}"]`);
    const rows = () => [...host.querySelectorAll('[data-kind="image"][data-index]')];
    const editControl = () => host.querySelector(`[data-shot-editor="${target}"] [data-kind="image"][data-index="0"] input[data-field="label"]`);
    const waitFor = async (test, description) => {
      const deadline = performance.now() + 3500;
      while (!test()) {
        if (performance.now() > deadline) throw Error(description);
        await paintBoundary();
      }
    };
    const expectShot = (number, firstLabel = label(number, 1)) => {
      if (latest.images.length !== 50 || rows().length !== 50) throw Error('Fifty images were not retained');
      for (let index = 0; index < 50; index++) {
        const image = latest.images[index];
        const expectedLabel = index === 0 ? firstLabel : label(number, index + 1);
        if (image.token !== `@image${index + 1}` || image.owner !== owner(number, index + 1)
          || rows()[index].querySelector('input[data-field="label"]').value !== expectedLabel) {
          throw Error(`Exact saved media/Target order changed in Shot ${number} at ${index + 1}: ${JSON.stringify({ token: image.token, owner: image.owner, label: rows()[index].querySelector('input[data-field="label"]').value, expectedLabel })}`);
        }
      }
      if (host.querySelector(`[data-text-key="${textKey}"]`).value !== `Saved Shot ${number} 한글 {literal} 0 OFF`) {
        throw Error('Shot text binding changed');
      }
    };
    const mount = async value => {
      controller?.cleanup();
      latest = structuredClone(value);
      publications = 0;
      controller = widget.default(host, props(latest));
      await waitFor(() => rows().length === 50, 'Initial rows did not become available');
      await paintBoundary();
      await paintBoundary();
    };
    const cold = async () => {
      await mount(base);
      if (host.querySelector(`[data-shot-editor="${target}"]`) || !startTab(target) || publications) {
        throw Error('Expected a cold target tab and an untouched saved baseline');
      }
    };
    const click = () => {
      const before = performance.now();
      startTab(target).click();
      return { click_epoch_ms: performance.timeOrigin + before, sync_ms: performance.now() - before,
        rows_after_handler: rows().length,
        first_target_options_after_handler: host.querySelector('[data-kind="image"][data-index="0"] select[data-field="owner"]')?.options.length ?? null };
    };
    const earlyEdit = async () => {
      const edit = `Edited cold Shot 2 한글 {literal} 0 OFF`;
      const timing = click();
      const possible = () => {
        const field = editControl();
        if (!field || field.readOnly || field.disabled) return false;
        const rect = field.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0
          && document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2) === field;
      };
      await waitFor(possible, 'First source label never became editable');
      const editableAt = performance.timeOrigin + performance.now();
      const field = editControl();
      const mountedWhenEditing = rows().length;
      let inputAt = null;
      let inputHandlerDoneAt = null;
      field.addEventListener('input', event => {
        if (event.isTrusted && field.value === edit) inputAt = performance.timeOrigin + performance.now();
      }, { once: true, capture: true });
      field.addEventListener('input', event => {
        if (event.isTrusted && field.value === edit) inputHandlerDoneAt = performance.timeOrigin + performance.now();
      }, { once: true });
      field.focus({ preventScroll: true });
      field.select();
      const accepted = document.execCommand('insertText', false, edit);
      if (!accepted || document.activeElement !== field || field.value !== edit || inputAt == null || inputHandlerDoneAt == null) throw Error('Real text edit did not work');
      field.blur();
      await waitFor(() => rows().length === 50 && latest.images[0]?.label === edit, 'First edit did not publish or rows did not complete');
      expectShot(2, edit);
      return { ...timing, click_to_editable_control_ms: editableAt - timing.click_epoch_ms,
        click_to_working_edit_ms: inputAt - timing.click_epoch_ms,
        click_to_input_handlers_complete_ms: inputHandlerDoneAt - timing.click_epoch_ms,
        mounted_rows_when_editing: mountedWhenEditing };
    };
    const compatibility = async () => {
      const saved = structuredClone(latest);
      await mount(saved);
      const edited = 'Edited cold Shot 2 한글 {literal} 0 OFF';
      expectShot(2, edited);
      for (const shot of [shots[0], shots[4], shots[1]]) {
        startTab(shot.shot_uuid).click();
        await waitFor(() => rows().length === 50 && latest.shot.shot_uuid === shot.shot_uuid, 'Existing Shot did not restore all images');
        expectShot(shot.number, shot.number === 2 ? edited : undefined);
      }
      const targetSelect = rows()[0].querySelector('select[data-field="owner"]');
      const selectedTarget = targetSelect.value;
      targetSelect.focus({ preventScroll: true });
      targetSelect.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }));
      const targetValues = [...targetSelect.options].map(option => option.value);
      const expectedTargets = widget.imageTargetChoicesForRow(latest.images[0], latest.images, latest);
      if (JSON.stringify(targetValues) !== JSON.stringify(expectedTargets) || targetSelect.value !== selectedTarget) {
        throw Error('Opening a source Target control changed the available options or its binding');
      }
      const standalone = structuredClone(saved);
      standalone.multi_shot_enabled = false;
      standalone.image_asset = {};
      delete standalone.shot_documents;
      await mount(standalone);
      expectShot(2, edited);
      const field = rows()[0].querySelector('input[data-field="label"]');
      field.focus();
      field.select();
      if (!document.execCommand('insertText', false, 'Standalone edit')) throw Error('Standalone input rejected edit');
      field.blur();
      await waitFor(() => latest.images[0].label === 'Standalone edit', 'Standalone edit did not publish');
      expectShot(2, 'Standalone edit');
      const standaloneTarget = rows()[0].querySelector('select[data-field="owner"]');
      standaloneTarget.focus({ preventScroll: true });
      const newTarget = owner(2, 50);
      if (![...standaloneTarget.options].some(option => option.value === newTarget)) throw Error('Standalone Target options did not initialize on focus');
      standaloneTarget.value = newTarget;
      standaloneTarget.dispatchEvent(new Event('change', { bubbles: true }));
      await waitFor(() => latest.images[0].owner === newTarget, 'Standalone Target binding did not publish');
      const standaloneSaved = structuredClone(latest);
      await mount(standaloneSaved);
      if (rows()[0].querySelector('select[data-field="owner"]').value !== newTarget || latest.images[49].token !== '@image50') {
        throw Error('Standalone save/reopen lost the changed Target or source order');
      }
      await cold();
      startTab(shots[1].shot_uuid).click();
      startTab(shots[2].shot_uuid).click();
      await waitFor(() => rows().length === 50 && latest.shot.shot_uuid === shots[2].shot_uuid, 'Rapid cold switches lost the selected Shot');
      expectShot(3);
      await paintBoundary();
      expectShot(3);
      startTab(shots[3].shot_uuid).click();
      controller.cleanup();
      const publicationsOnClose = publications;
      await paintBoundary();
      await paintBoundary();
      if (host.children.length) throw Error('Unmount leaked content');
      if (publications !== publicationsOnClose) throw Error('Unmount allowed stale pending navigation to publish');
      return { saved_shot_checks: 4, target_option_count: targetValues.length, standalone_rows: 50, standalone_edit: true, standalone_target_reopen: true, rapid_cold_switch: true, cleanup: true };
    };
    const keyboardRow = 12;
    const beginKeyboardTarget = async () => {
      await cold();
      startTab(target).click();
      await waitFor(() => rows().length === 50, 'Keyboard fixture could not reach source row');
      const row = rows()[keyboardRow];
      const focusable = [...row.querySelectorAll('input, select, textarea, button, [tabindex]')].filter(element =>
        element.tabIndex >= 0 && !element.disabled && element.offsetWidth > 0 && element.offsetHeight > 0
      );
      const targetIndex = focusable.indexOf(row.querySelector('select[data-field="owner"]'));
      if (targetIndex <= 0) throw Error('Could not identify the control immediately before Target');
      focusable[targetIndex - 1].focus({ preventScroll: true });
    };
    let expectedKeyboardTarget;
    let trustedKeyboardChange = false;
    const checkKeyboardFocus = () => {
      const select = rows()[keyboardRow].querySelector('select[data-field="owner"]');
      const options = [...select.options].map(option => option.value);
      const expected = widget.imageTargetChoicesForRow(latest.images[keyboardRow], latest.images, latest);
      if (document.activeElement !== select || JSON.stringify(options) !== JSON.stringify(expected)
        || select.value !== latest.images[keyboardRow].owner || select.value === options.at(-1)) {
        throw Error('Keyboard Tab did not populate and focus the exact Target menu');
      }
      expectedKeyboardTarget = options.at(-1);
      select.addEventListener('change', event => { trustedKeyboardChange = event.isTrusted; }, { capture: true, once: true });
    };
    const checkKeyboardSelection = async () => {
      await waitFor(() => trustedKeyboardChange && latest.images[keyboardRow].owner === expectedKeyboardTarget, 'Keyboard End did not publish its trusted Target change');
      if (latest.images[keyboardRow].token !== '@image13') throw Error('Keyboard Target edit changed the source slot');
      controller.cleanup();
      return true;
    };
    window.coldPromptTest = { cold, click, earlyEdit, compatibility, beginKeyboardTarget, checkKeyboardFocus, checkKeyboardSelection };
  });
}

let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.HMB_PROMPT_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' });
  report.chromium_version = browser.version();
  const contexts = {};
  const errors = [];
  for (const mode of modes) {
    const page = await browser.newPage({ viewport: { width: 1800, height: 1400 }, deviceScaleFactor: 1 });
    page.on('pageerror', error => errors.push(`${mode}: ${error.message}`));
    await page.route('**/*', route => {
      if (new URL(route.request().url()).hostname !== '127.0.0.1') {
        report.external_requests++;
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(setupWidget, mode);
    const session = await page.context().newCDPSession(page);
    contexts[mode] = { page, session };
    report.measurements[mode] = { paint_samples: [], edit_samples: [] };
  }

  for (let index = 0; index < sampleCount; index++) {
    const sampleModes = index % 2 ? [...modes].reverse() : modes;
    for (const mode of sampleModes) {
      const { page, session } = contexts[mode];
      await page.bringToFront();
      const frames = [];
      const frame = ({ data, metadata, sessionId }) => {
        void session.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
        if (metadata.timestamp) frames.push({ time_ms: metadata.timestamp * 1000, data });
      };
      session.on('Page.screencastFrame', frame);
      let click;
      try {
        await session.send('Page.startScreencast', { format: 'jpeg', quality: 88, maxWidth: 1050, maxHeight: 850, everyNthFrame: 1 });
        const remountStart = await page.evaluate(async () => {
          const start = performance.timeOrigin + performance.now();
          await window.coldPromptTest.cold();
          return start;
        });
        const awaitOldFrameUntil = Date.now() + 3500;
        let oldFrame = null;
        let cursor = 0;
        while (Date.now() < awaitOldFrameUntil && !oldFrame) {
          for (; cursor < frames.length; cursor++) {
            const next = frames[cursor];
            if (next.time_ms >= remountStart && markerPainted(next.data, false)) {
              oldFrame = next;
              break;
            }
          }
          if (!oldFrame) await new Promise(resolve => setTimeout(resolve, 8));
        }
        assert.ok(oldFrame, 'No compositor frame displayed the freshly mounted old Shot');
        click = await page.evaluate(() => window.coldPromptTest.click());
        let painted = null;
        let lastUnpainted = null;
        const deadline = Date.now() + 3500;
        while (Date.now() < deadline && !painted) {
          for (; cursor < frames.length; cursor++) {
            const next = frames[cursor];
            if (next.time_ms < click.click_epoch_ms) continue;
            if (markerPainted(next.data, true)) { painted = next; break; }
            lastUnpainted = next;
          }
          if (!painted) await new Promise(resolve => setTimeout(resolve, 8));
        }
        assert.ok(painted, 'No compositor frame displayed the new Shot image row');
        report.measurements[mode].paint_samples.push({ ...click,
          click_to_first_painted_row_ms: painted.time_ms - click.click_epoch_ms,
          previous_unpainted_after_click_ms: lastUnpainted ? lastUnpainted.time_ms - click.click_epoch_ms : null,
        });
      } finally {
        session.off('Page.screencastFrame', frame);
        await session.send('Page.stopScreencast');
      }
      await page.evaluate(() => window.coldPromptTest.cold());
      report.measurements[mode].edit_samples.push(await page.evaluate(() => window.coldPromptTest.earlyEdit()));
    }
  }

  for (const mode of modes) {
    const measurement = report.measurements[mode];
    measurement.first_painted_row = stats(measurement.paint_samples.map(sample => sample.click_to_first_painted_row_ms));
    measurement.first_working_edit = stats(measurement.edit_samples.map(sample => sample.click_to_working_edit_ms));
    measurement.first_editable_control = stats(measurement.edit_samples.map(sample => sample.click_to_editable_control_ms));
    measurement.first_edit_handlers_complete = stats(measurement.edit_samples.map(sample => sample.click_to_input_handlers_complete_ms));
    measurement.click_handler = stats(measurement.paint_samples.map(sample => sample.sync_ms));
    const { page } = contexts[mode];
    await page.bringToFront();
    report.compatibility[mode] = await page.evaluate(() => window.coldPromptTest.compatibility());
    await page.evaluate(() => window.coldPromptTest.beginKeyboardTarget());
    await page.keyboard.press('Tab');
    await page.evaluate(() => window.coldPromptTest.checkKeyboardFocus());
    await page.keyboard.press('End');
    report.compatibility[mode].keyboard_target_selection = await page.evaluate(() => window.coldPromptTest.checkKeyboardSelection());
  }
  assert.deepEqual(errors, []);
  assert.equal(report.external_requests, 0);
  // An already-installed candidate is an A/A functional check, not evidence
  // of a new speedup. Timing noise must not fabricate an improvement claim.
  if (modes.length === 2 && report.source_sha256.before !== report.source_sha256.after) {
    for (const key of ['first_painted_row', 'first_working_edit']) {
      assert.ok(report.measurements.after[key].median_ms < report.measurements.before[key].median_ms, `${key} median did not improve`);
    }
  }
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.failure = String(error.stack || error);
  throw error;
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
  const output = process.env.HMB_PROMPT_COLD_OUTPUT;
  if (output) {
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  }
  console.log(JSON.stringify({ ...report, measurements: Object.fromEntries(Object.entries(report.measurements).map(([mode, values]) => {
    const { paint_samples, edit_samples, ...summary } = values;
    return [mode, { ...summary, paint_count: paint_samples.length, edit_count: edit_samples.length }];
  })) }));
}
