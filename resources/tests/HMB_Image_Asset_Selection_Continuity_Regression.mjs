import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const executablePath = process.env.HMB_IMAGE_ASSET_TEST_BROWSER || "C:/Program Files/Google/Chrome/Application/chrome.exe";
assert.ok(fs.existsSync(executablePath), "Selection continuity requires the real browser fixture.");
const source = fs.readFileSync(new URL("../../widgets/HMBImageAssetLibraryWidget.js", import.meta.url), "utf8");
const promptSource = fs.readFileSync(new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url), "utf8");
const browser = await playwright.chromium.launch({ executablePath, headless: true });
const cases = [], errors = [];
let remoteRequests = 0;
try {
  for (const format of ["string", "object"]) {
    const page = await browser.newPage({ viewport: { width: 1300, height: 1000 } });
    page.on("pageerror", (error) => errors.push(String(error)));
    await page.route("**/*", (route) => { remoteRequests++; return route.abort(); });
    await page.setContent('<style>.react-flow__node{width:1200px;height:850px}#widget{height:820px}</style><div class="react-flow"><div class="react-flow__node" data-id="SelectionContinuity"><div id="widget"></div></div><div class="react-flow__node" data-id="Prompt"><div id="prompt"></div></div></div>');
    await page.evaluate(async ({ uri, promptUri, format }) => {
      const widget = await import(uri);
      const canvas = document.createElement("canvas"); canvas.width = canvas.height = 12;
      canvas.getContext("2d").fillRect(0, 0, 12, 12);
      const png = canvas.toDataURL("image/png");
      const state = widget.hmbNormalizeImageAssetState({
        search: "Hero", edit_transport_schema: "hmb-image-asset-edit-v1", scan_revision: 7, ui_edit_revision: 4,
        catalog_root: "C:/fixture", project_root: "C:/fixture/Project", project_id: "Project",
        project_uid: `project-${format}`, project_cache_uid: `cache-${format}`,
        manifest_signature: "manifest-one", folder_signature: "folder-one",
        projects: [{ path: "C:/fixture/Project", name: "Project", project_id: "Project" }],
        assets: Array.from({ length: 3 }, (_, index) => ({ asset_library_id: `asset-${index}`,
          asset_id: `Hero${index}`, image_name: `Hero ${index}`, source_uid: `source-${index}`,
          source_kind: "project", registered: true, relative_path: `Hero${index}.png`,
          media_signature: `media-${index}`, thumbnail_url: png })),
      });
      const container = document.querySelector("#widget");
      const fixture = { widget, container, state, writes: [], format, removedImages: 0 };
      const {default:mountPrompt} = await import(promptUri);
      const {channel_uuid, publisher_instance_uuid, shots} = state.shot_routing;
      const shot = {...shots[0], channel_uuid};
      const other = {...shot, shot_uuid:"b602b5d3-117d-42ee-9444-e2952ca6db02", number:2, name:"Shot 2", selected_source_uids:[]};
      shots.push(other);
      const route = {publisher_instance_uuid, channel_uuid, generation:1, metadata_sha256:"a".repeat(64)};
      fixture.promptWrites = 0;
      fixture.prompt = mountPrompt(document.querySelector("#prompt"), {value:JSON.stringify({
        shot, multi_shot_enabled:true, image_asset:{enabled:true, shot_routing:route,
          shot_catalog_routing:route, shot_catalog:[shot,other]},
      }), onChange:() => { fixture.promptWrites++; }});
      fixture.view = () => ({
        cards: container.querySelectorAll(".asset-grid [data-asset-key]").length,
        project: container.querySelector("[data-project-select]")?.value || "",
        selected: container.querySelectorAll(".asset-grid .asset-card.selected").length,
        stateCards: container.__hmbImageAssetLatestState.assets.length,
      });
      fixture.onChange = (wire) => {
        fixture.writes.push(wire);
        fixture.before = fixture.view();
        fixture.canonical = structuredClone(container.__hmbImageAssetLatestState);
        fixture.controller.update({ value: format === "object" ? JSON.parse(wire) : wire, onChange: fixture.onChange });
        fixture.during = fixture.view();
        return Promise.resolve();
      };
      fixture.controller = widget.default(container, { value: JSON.stringify(state), onChange: fixture.onChange });
      fixture.root = container.querySelector(".hmb-image-assets");
      fixture.images = [...container.querySelectorAll(".asset-grid img")];
      fixture.cards = [...container.querySelectorAll(".asset-grid [data-asset-key]")];
      fixture.observer = new MutationObserver((records) => {
        for (const record of records) for (const removed of record.removedNodes) {
          if (removed.nodeType === 1) fixture.removedImages += (removed.matches("img") ? 1 : 0) + removed.querySelectorAll("img").length;
        }
      });
      fixture.observer.observe(container, { childList: true, subtree: true });
      window.selectionFixture = fixture;
    }, { uri: "data:text/javascript;base64," + Buffer.from(source).toString("base64"),
      promptUri:"data:text/javascript;base64," + Buffer.from(promptSource).toString("base64"), format });
    await page.waitForFunction(() => selectionFixture.images.every((image) => image.complete && image.naturalWidth > 0));
    const result = await page.evaluate(async () => {
      const f = selectionFixture;
      f.cards[0].click();
      const hint = document.querySelector("#prompt [data-hmb-selection-preview]")?.textContent;
      if (!hint?.includes("Hero 0") || f.writes.length || f.promptWrites) {
        throw Error("The bound Prompt must paint the selected name before the first host write.");
      }
      f.widget.hmbFlushImageAssetSelectionCommit(f.container);
      await Promise.resolve();
      const request = JSON.parse(f.writes[0]);
      f.controller.update({ value: JSON.stringify(f.canonical), onChange: f.onChange });
      await Promise.resolve();
      const after = f.view();
      return { format: f.format, schema: request.schema, before: f.before, during: f.during, after,
        sameRoot: f.root === f.container.querySelector(".hmb-image-assets"),
        sameCards: f.cards.every((card, index) => card === f.container.querySelectorAll(".asset-grid [data-asset-key]")[index]),
        sameImages: f.images.every((image, index) => image === f.container.querySelectorAll(".asset-grid img")[index]),
        removedImages: f.removedImages };
    });
    cases.push(result);
    console.log(JSON.stringify(result));
    assert.equal(result.schema, "hmb-image-asset-edit-v1");
    assert.deepEqual(result.during, result.before, "An optimistic compact request echo is an edit command, never an empty catalog.");
    assert.deepEqual(result.after, result.before, "The canonical response must preserve the already selected visible catalog.");
    assert.equal(result.sameRoot, true);
    assert.equal(result.sameCards, true);
    assert.equal(result.sameImages, true);
    assert.equal(result.removedImages, 0, "An acknowledgement must not disconnect loaded thumbnail elements.");
    const reordered = await page.evaluate(async () => {
      const f = selectionFixture;
      const firstWire = f.writes[0], firstCanonical = structuredClone(f.canonical);
      f.cards[1].click();
      f.widget.hmbFlushImageAssetSelectionCommit(f.container);
      f.controller.update({ value: JSON.stringify(f.canonical), onChange: f.onChange });
      let obsoleteWrites = 0;
      const obsoleteCallback = () => { obsoleteWrites++; };
      f.controller.update({ value: firstWire, onChange: obsoleteCallback });
      f.controller.update({ value: JSON.stringify(firstCanonical), onChange: obsoleteCallback });
      f.controller.update({ value: { schema: "hmb-image-asset-edit-v1", version: 1,
        scan_revision: 99999, ui_edit_revision: 99999, catalog_identity: { project_uid: "different-owner" },
        selected_source_uids: [], edits: {} }, onChange: obsoleteCallback });
      const afterLateEcho = f.view();
      f.cards[2].click();
      f.widget.hmbFlushImageAssetSelectionCommit(f.container);
      f.controller.update({ value: JSON.stringify(f.canonical), onChange: f.onChange });
      await Promise.resolve();
      return { afterLateEcho, final: f.view(), writes: f.writes.length, obsoleteWrites,
        removedImages: f.removedImages, sameImages: f.images.every((image, index) => image === f.container.querySelectorAll(".asset-grid img")[index]) };
    });
    assert.equal(reordered.afterLateEcho.selected, 2, "Older or foreign edit envelopes cannot roll back newer selection.");
    assert.equal(reordered.final.selected, 3);
    assert.equal(reordered.final.cards, 3);
    assert.equal(reordered.writes, 3, "The next click still uses the current host callback exactly once.");
    assert.equal(reordered.obsoleteWrites, 0);
    assert.equal(reordered.sameImages, true);
    assert.equal(reordered.removedImages, 0);
    cases[cases.length - 1].reordered = reordered;
    const immediate = await page.evaluate(() => {
      const f = selectionFixture, prompt = document.querySelector('#prompt');
      const heading = () => prompt.querySelector('.image-card h3 b')?.textContent;
      const writesBefore = f.writes.length;
      for (let repeat=0; repeat<30; repeat++) {
        f.container.querySelector('[data-selected-key="asset-2"] [data-remove-selected]').click();
        if (heading() !== '2 / 50' || prompt.querySelector('[data-hmb-image-selection-pending="source-2"]')) {
          throw Error(`Prompt did not remove image on click ${2*repeat+1}`);
        }
        f.container.querySelector('.asset-grid [data-asset-key="asset-2"]').click();
        if (heading() !== '3 / 50' || !prompt.querySelector('[data-hmb-image-selection-pending="source-2"]')) {
          throw Error(`Prompt did not add image on click ${2*repeat+2}`);
        }
      }
      const firstPaintWrites = f.writes.length - writesBefore;
      f.widget.hmbFlushImageAssetSelectionCommit(f.container);
      f.controller.update({value:JSON.stringify(f.canonical),onChange:f.onChange});
      return {firstPaintWrites, committed:f.writes.length - writesBefore, promptWrites:f.promptWrites,
        error:f.container.querySelector('[data-transport-status]')?.textContent};
    });
    assert.deepEqual(immediate,{firstPaintWrites:0,committed:1,promptWrites:0,error:''},
      'All 60 clicks repaint immediately before the retained selection is committed.');
    await page.evaluate(async () => {
      const f = selectionFixture, prompt = document.querySelector("#prompt");
      const shotIds = f.state.shot_routing.shots.map(shot => shot.shot_uuid);
      const switchTo = id => {
        const tab = prompt.querySelector('[data-prompt-shot="' + id + '"]');
        if (!tab) throw Error("The bound Shot tab is missing.");
        tab.click();
      };
      const hint = () => prompt.querySelector("[data-hmb-selection-preview]")?.textContent;
      if (!hint()?.includes("Hero 2")) throw Error("The original Shot should show its pending selection.");
      switchTo(shotIds[1]);
      if (hint()) throw Error("Another Shot is displaying this Shot’s pending selection.");
      f.cards[2].click();
      await new Promise(resolve => setTimeout(resolve, 100));
      switchTo(shotIds[0]);
      if (hint()) throw Error("A retained editor restored a stale selection after its source changed.");
    });
    await page.evaluate(() => { selectionFixture.observer.disconnect(); selectionFixture.controller.cleanup(); selectionFixture.prompt.cleanup(); });
    await page.close();
  }
  assert.deepEqual(errors, []);
  assert.equal(remoteRequests, 0);
  console.log(`HMB ImageAsset selection continuity Chrome: PASS (${cases.length} compact host echo formats, stale/foreign echoes, current callbacks, retained cards/images, zero remote requests)`);
} finally { await browser.close(); }
