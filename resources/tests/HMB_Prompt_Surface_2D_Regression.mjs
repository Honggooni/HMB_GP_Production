import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const root = process.env.HMB_TEST_LIBRARY_ROOT
  ? pathToFileURL(`${process.env.HMB_TEST_LIBRARY_ROOT.replaceAll("\\", "/")}/`)
  : new URL("../../", import.meta.url);
const widgetUrl = new URL("widgets/HMBPromptLibraryScopedBindingWidget.js", root);
const widget = await import(widgetUrl);
const code = fs.readFileSync(widgetUrl, "utf8");
const fixture = () => widget.normalizeState({
  images: [
    { present: true, label: "Hero", asset_source_uid: "hero", image_main_type: "Character", image_sub_type: "Full Appearance", owner: "Hero", color_picks: ["Red", "Green", "Blue"], binding_video_slots: [1, 2, 3] },
    { present: true, label: "Partner", asset_source_uid: "partner", image_main_type: "Character", image_sub_type: "", owner: "Partner" },
    { present: true, label: "Forest", image_main_type: "Environment / Background", image_sub_type: "Main Background", owner: "Forest" },
    { present: true, label: "Look", image_main_type: "Look Reference", image_sub_type: "Lighting / Atmosphere", owner: "Global Look" },
  ],
  videos: [1, 2, 3].map((slot) => ({ present: true, label: `Video ${slot}`, video_main_type: "Maya Preview / Playblast", video_sub_type: "Original Preview" })),
  ui: { language: "ko", group_heights: { imageSources: 500 } },
});

const initial = fixture();
assert.ok(initial.images.every((image) => image.surface_2d === false));
const before = structuredClone(initial.images[0]);
assert.equal(widget.hmbSetImageSurface2D(initial.images[0], true), true);
assert.deepEqual(initial.images[0], { ...before, surface_2d: true });
assert.equal(widget.hmbSetImageSurface2D(initial.images[0], true), false);
assert.equal(widget.hmbSetImageSurface2D(initial.images[2], true), false);
for (let i = 0; i < 40; i++) {
  const restored = widget.normalizeState(JSON.parse(JSON.stringify(initial)));
  assert.equal(restored.images[0].surface_2d, true);
  assert.deepEqual(restored.images[0].color_picks, ["Red", "Green", "Blue"]);
}
const reordered = fixture();
widget.hmbSetImageSurface2D(reordered.images[0], true);
widget.moveImageRowWithoutReset(reordered, 0, 1);
assert.equal(reordered.images[1].asset_source_uid, "hero");
assert.equal(reordered.images[1].surface_2d, true);
assert.equal(reordered.images[0].surface_2d, false);
const source = structuredClone(reordered);
source.source_sync_revision = 10;
reordered.ui_edit_revision = 8;
source.images.reverse();
source.images.forEach((image) => { image.surface_2d = false; });
const merged = widget.hmbMergePromptRevisionAxes(source, reordered);
assert.equal(merged.images.find((image) => image.asset_source_uid === "hero").surface_2d, true);
for (const raw of ["true", "false", 1, null]) {
  const row = { ...before, surface_2d: raw };
  widget.normalizeImageTaxonomy(row);
  assert.equal(row.surface_2d, false);
}
const changedType = { ...before, surface_2d: true, image_main_type: "Look Reference" };
widget.normalizeImageTaxonomy(changedType);
assert.equal(changedType.surface_2d, false);
assert.match(code, /surface_2d: "2D표현"/);
assert.match(code, /"surface_2d", "2DSurface"/);
assert.match(code, /grid-template-columns:minmax\(0,1fr\) 4\.5rem/);
console.log("HMB 2DSurface widget state, identity, three color picks and language regression: PASS");

if (process.argv.includes("--browser")) {
  const require = createRequire(import.meta.url);
  const { chromium } = require("playwright");
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.HMB_TEST_BROWSER_CHANNEL ? { channel: process.env.HMB_TEST_BROWSER_CHANNEL } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 2100, height: 1450 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setContent('<html><body style="margin:0;background:#080b15"><div id="host" style="width:2060px;height:1400px;margin:20px"></div></body></html>');
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
    await page.evaluate(async ({ moduleUrl, state }) => {
      const mod = await import(moduleUrl);
      window.surfaceModule = mod;
      window.surfaceState = state;
      window.surfaceChanges = [];
      window.surfaceProps = {
        value: JSON.stringify(state), disabled: false,
        onChange(value) {
          window.surfaceState = JSON.parse(value);
          window.surfaceChanges.push(window.surfaceState);
          window.surfaceController?.update({ ...window.surfaceProps, value });
        },
      };
      window.surfaceController = mod.default(document.getElementById("host"), window.surfaceProps);
    }, { moduleUrl, state: fixture() });
    const first = page.locator('.source-row.image[data-index="0"]');
    const check = first.locator('.image-surface-checkbox');
    await page.waitForFunction(() => document.querySelectorAll('.image-surface-checkbox').length >= 4);
    assert.equal(await page.locator('.image-surface-heading').innerText(), "2D표현");
    assert.equal(await check.isEnabled(), true);
    assert.equal(await page.locator('.source-row.image[data-index="2"] .image-surface-checkbox').isDisabled(), true);
    assert.equal(await page.locator('.image-surface-checkbox:checked').count(), 0);
    if (process.env.HMB_SURFACE_BASELINE_ROOT) {
      const baselineCode = fs.readFileSync(path.join(process.env.HMB_SURFACE_BASELINE_ROOT,
        'widgets', 'HMBPromptLibraryScopedBindingWidget.js'), 'utf8');
      const baselinePage = await browser.newPage({ viewport: { width: 2100, height: 1450 } });
      try {
        await baselinePage.setContent('<html><body style="margin:0;background:#080b15"><div id="host" style="width:2060px;height:1400px;margin:20px"></div></body></html>');
        await baselinePage.evaluate(async ({ code, state }) => {
          const mod = await import(code);
          mod.default(document.getElementById('host'), { value: JSON.stringify(state), disabled: false, onChange() {} });
        }, { code: `data:text/javascript;base64,${Buffer.from(baselineCode).toString('base64')}`, state: fixture() });
        const selectors = ['.topbar', '.image-header', '.source-row.image .image-index-cell',
          '.source-row.image .image-name-cell', '.source-row.image .image-main-type-cell',
          '.source-row.image .binding-scope-cell', '.source-row.image .image-target-cell',
          '.source-row.image .image-actions-cell', '.source-row.image .frame-binding-row',
          '[data-group-id="imageText"]', '[data-group-id="videoSources"]', '[data-group-id="videoText"]'];
        const measure = async (targetPage) => targetPage.evaluate(async (selectors) => {
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return selectors.map((selector) => {
            const rect = document.querySelector(selector).getBoundingClientRect();
            return [rect.x, rect.y, rect.width, rect.height].map((value) => Math.round(value * 10) / 10);
          });
        }, selectors);
        assert.deepEqual(await measure(page), await measure(baselinePage), 'Unrelated UI geometry must match the installed pre-patch widget.');
        console.log('HMB 2DSurface unchanged UI geometry vs installed baseline: 12 regions PASS');
      } finally { await baselinePage.close(); }
    }
    const output = process.env.HMB_SURFACE_SCREENSHOT_DIR;
    if (output) {
      fs.mkdirSync(output, { recursive: true });
      await page.screenshot({ path: path.join(output, "prompt-surface-default-off.png") });
    }
    await check.check();
    await page.waitForFunction(() => window.surfaceState.images[0].surface_2d === true);
    await check.uncheck();
    await page.waitForFunction(() => window.surfaceState.images[0].surface_2d === false);
    await check.check();
    await page.waitForFunction(() => window.surfaceState.images[0].surface_2d === true);
    await first.locator('[data-field="image_sub_type"]').selectOption("Head / Face");
    assert.equal(await check.isChecked(), true);
    assert.equal(await first.locator('[data-field="color_picks"]').count(), 3);
    const geometry = await page.evaluate(() => {
      const rect = (selector) => {
        const r = document.querySelector(selector).getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, right: r.right };
      };
      return {
        heading: rect('.image-surface-heading'),
        control: rect('.source-row.image .image-surface-control'),
        colors: rect('.source-row.image .image-video-color-controls'),
        actions: rect('.source-row.image .image-actions-cell'),
      };
    });
    assert.ok(Math.abs(geometry.heading.x - geometry.control.x) < 1);
    assert.ok(geometry.colors.right < geometry.control.x);
    assert.ok(geometry.control.right <= geometry.actions.x);
    if (output) {
      await page.screenshot({ path: path.join(output, "prompt-surface-ko.png") });
    }
    await page.locator('[data-language-toggle]').click();
    await page.waitForFunction(() => document.querySelector('.image-surface-heading')?.textContent === "2DSurface");
    await first.locator('[data-field="image_main_type"]').selectOption("Environment / Background");
    await page.waitForFunction(() => window.surfaceState.images[0].surface_2d === false);
    assert.equal(await check.isDisabled(), true);
    await first.locator('[data-field="image_main_type"]').selectOption("Character");
    assert.equal(await check.isEnabled(), true);
    assert.equal(await check.isChecked(), false);
    for (const width of [1800, 1250, 930, 760]) {
      await page.setViewportSize({ width: width + 40, height: 1450 });
      await page.locator('#host').evaluate((element, value) => { element.style.width = `${value}px`; }, width);
      assert.ok((await check.boundingBox()).width >= 15);
    }
    assert.deepEqual(errors, []);
    console.log("HMB 2DSurface real browser checkbox, echo, language, type change, column geometry and resize regression: PASS");
  } finally {
    await browser.close();
  }
}
