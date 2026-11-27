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
const widgetSource = name => fs.readFileSync(process.env.HMB_MODE_TEST_LIBRARY_ROOT
  ? path.join(process.env.HMB_MODE_TEST_LIBRARY_ROOT, "widgets", name)
  : new URL("../../widgets/" + name, import.meta.url), "utf8");
const source = widgetSource("HMBImageAssetLibraryWidget.js");
const promptSource = widgetSource("HMBPromptLibraryScopedBindingWidget.js");
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
      fixture.mountPrompt = mountPrompt;
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
      const prompt = document.querySelector("#prompt");
      const row = prompt.querySelector('[data-hmb-image-selection-pending="source-0"]');
      if (row?.querySelector('[data-field="label"]')?.value !== "Hero 0" || !row.querySelector('[data-field="owner"]') || !row.querySelector('[data-field="color_picks"]') || prompt.querySelector(".image-card h3").textContent.includes("Hero 0")
        || f.writes.length || f.promptWrites) {
        throw Error("The bound Prompt must show the selection once, in its slot, before the first host write.");
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
    await page.evaluate(() => {
      const f = selectionFixture, prompt = document.querySelector("#prompt");
      const original = [...f.canonical.shot_routing.shots[0].selected_source_uids];
      const routing = f.canonical.shot_routing;
      const shot = {...routing.shots[0], channel_uuid:routing.channel_uuid};
      const route = {publisher_instance_uuid:routing.publisher_instance_uuid, channel_uuid:routing.channel_uuid,
        generation:3, metadata_sha256:"b".repeat(64)};
      const confirmed = {shot, multi_shot_enabled:true, source_sync_revision:4,
        image_asset:{enabled:true, order_managed:true, shot_routing:route, shot_catalog_routing:route,
          shot_catalog:routing.shots.map(s => ({...s,channel_uuid:routing.channel_uuid})), ordered_source_uids:original},
        images:original.map((uid,i) => ({asset_source_uid:uid, asset_managed:true, present:true, slot:i+1,
          label:"Hero "+i, asset_verified:true, asset_source_kind:"project", image_main_type:"Character"}))};
      const saved = prompt.__hmbNativeUiContract.props;
      f.prompt.cleanup();
      f.prompt = f.mountPrompt(prompt,{value:JSON.stringify(confirmed),onChange:() => {
        throw Error("A mounted publisher must own a managed order edit.");
      }});
      const card = uid => f.container.querySelector('[data-shot-tray] [data-shot-source-uid="'+uid+'"]');
      const row = uid => prompt.querySelector('[data-hmb-image-selection-uid="'+uid+'"]');
      const drag = (source, target) => {
        const dataTransfer = new DataTransfer();
        for (const [node,event] of [[source,"dragstart"],[target,"dragover"],[target,"drop"],[source,"dragend"]]) {
          node.dispatchEvent(new DragEvent(event,{bubbles:true,cancelable:true,dataTransfer}));
        }
      };
      const check = order => {
        const displayed = [...prompt.querySelectorAll("[data-hmb-image-selection-uid]")];
        if (JSON.stringify(displayed.map(el => el.dataset.hmbImageSelectionUid)) !== JSON.stringify(order)
          || displayed.some((el,i) => Number(el.querySelector("[data-image-drag-handle]").textContent) !== i+1)
          || JSON.stringify(f.container.__hmbImageAssetLatestState.shot_routing.shots[0].selected_source_uids) !== JSON.stringify(order))
          throw Error("Shot, visible editable rows and slot numbers diverged.");
      };
      const [a,b,c] = original;
      for (let cycle=0; cycle<12; cycle++) {
        drag(card(a),card(c)); check([b,c,a]);
        row(a).querySelector(".move-image-up").click(); check([b,a,c]);
        row(b).querySelector(".move-image-down").click(); check([a,b,c]);
        drag(row(c).querySelector("[data-image-drag-handle]"),row(a)); check([c,a,b]);
        drag(card(c),card(b)); check([a,b,c]);
      }
      f.widget.hmbFlushImageAssetSelectionCommit(f.container);
      f.prompt.cleanup();
      f.prompt=f.mountPrompt(prompt,saved);
    });
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
      const selectedRow = () => prompt.querySelector('[data-hmb-image-selection-pending="source-2"]');
      if (!selectedRow()) throw Error("The original Shot should show its selected slot.");
      switchTo(shotIds[1]);
      if (selectedRow()) throw Error("Another Shot is displaying this Shot’s selected slot.");
      f.cards[2].click();
      await new Promise(resolve => setTimeout(resolve, 100));
      switchTo(shotIds[0]);
      if (selectedRow()) throw Error("A retained editor restored a stale selection after its source changed.");
    });
    await page.evaluate(() => {
      const f = selectionFixture, source = f.container;
      const cached = structuredClone(source.__hmbImageAssetLatestState);
      cached.scan_revision++;
      cached.error = "프로젝트 폴더 읽기가 지연되었습니다.";
      cached.shot_routing.shots[0].image_link_notices = [{uid:"old-file",label:"Disconnected",path:"old/asset.png"}];
      const apply = value => f.controller.update({value:JSON.stringify(value),onChange:f.onChange});
      f.controller.cleanup();
      f.controller = f.widget.default(source,{value:JSON.stringify(cached),onChange:f.onChange});
      source.querySelector("[data-shot-tray] [data-dismiss-shot-link]").click();
      source.querySelector('.asset-grid [data-asset-key="asset-2"]').click();
      f.widget.hmbFlushImageAssetSelectionCommit(source);
      const repaint = structuredClone(source.__hmbImageAssetLatestState);
      repaint.scan_revision++;
      apply(repaint);
      const prompt = document.querySelector("#prompt");
      if (prompt.querySelector('[data-hmb-image-selection-pending="source-2"] [data-field="label"]')?.value !== "Hero 2"
          || prompt.querySelector('.image-card h3 b')?.textContent !== '3 / 50'
          || source.querySelector("[data-dismiss-shot-link]")) {
        throw Error("A folder read warning cancelled a new selection after the old link notice was dismissed.");
      }
    });
    const eight = await page.evaluate(() => {
      const f = selectionFixture, prompt = document.querySelector("#prompt");
      const next = structuredClone(f.container.__hmbImageAssetLatestState);
      next.scan_revision++;
      next.assets = Array.from({length:8}, (_,i) => ({...next.assets[0], asset_id:"Hero"+i, image_name:"Hero "+i,
        source_uid:"source-"+i, asset_library_id:"asset-"+i, relative_path:"Hero"+i+".png",
        image_main_type:"Character", image_sub_type:"Full Appearance", source_type:"Character Appearance",
        selected:false, selection_order:0}));
      next.shot_routing.shots.forEach(shot=>{shot.selected_source_uids=[];shot.media_count=0;});
      f.controller.cleanup();
      f.controller=f.widget.default(f.container,{value:JSON.stringify(next),onChange:f.onChange});
      const startWrites=f.promptWrites, timings=[];
      for (let i=0;i<8;i++) {
        const start=performance.now();
        f.container.querySelector('.asset-grid [data-asset-key="asset-'+i+'"]').click();
        const row=prompt.querySelector('[data-hmb-image-selection-pending="source-'+i+'"]');
        if (row?.querySelector('[data-field="label"]')?.value!== "Hero "+i
          || row.querySelector('[data-field="image_main_type"]').value!== "Character"
          || row.querySelector('[data-field="image_sub_type"]').value!== "Full Appearance"
          || !row.querySelector('[data-field="owner"]') || !row.querySelector('[data-field="color_picks"]'))
          throw Error("Selecting a registered image did not immediately expose its normal controls at slot "+(i+1));
        timings.push(performance.now()-start);
      }
      const uid = () => [...prompt.querySelectorAll('.image-card [data-hmb-image-selection-pending]')].map(row=>row.dataset.hmbImageSelectionUid);
      const last=prompt.querySelector('[data-hmb-image-selection-pending="source-7"]');
      last.querySelector(".move-image-up").click();
      if (uid()[6]!=="source-7") throw Error("The eighth image did not move up.");
      const transfer=new DataTransfer(), first=prompt.querySelector('[data-hmb-image-selection-pending="source-0"]');
      for (const [el,type] of [[last.querySelector("[data-image-drag-handle]"),"dragstart"],[first,"dragover"],
        [first,"drop"],[last,"dragend"]]) el.dispatchEvent(new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:transfer}));
      return {timings,first:uid()[0],promptWrites:f.promptWrites-startWrites};
    });
    assert.equal(eight.first,'source-7');
    assert.equal(eight.promptWrites,0);
    console.log(JSON.stringify({format,eighth_click_to_full_editor_ms:eight.timings[7],order:eight.first}));
    await page.evaluate(() => {
      const f=selectionFixture;
      f.widget.hmbFlushImageAssetSelectionCommit(f.container);
      const value=f.container.__hmbImageAssetLatestState;
      const scope={channel_uuid:value.shot_routing.channel_uuid,shot_uuid:value.shot_routing.active_shot_uuid};
      const update=locked=>f.controller.update({onChange:f.onChange,value:JSON.stringify({
        schema:"hmb-image-shot-status",widget_runtime_lease:value.widget_runtime_lease,
        channel_uuid:scope.channel_uuid,shot_edit_locks:locked?[scope]:[],verified_shots:[scope]})});
      update(true);
      const panel=()=>f.container.querySelector(".shot-panel.active");
      if (!panel().querySelector("[data-shot-lock]") || !panel().querySelector('[data-hmb-shot-check="true"]')
          || !panel().querySelector("[data-shot-rename]").disabled || panel().querySelector("[data-shot-tab]").disabled
          || panel().querySelector('[data-selected-key][draggable="true"]'))
        throw Error("Locked Shot still allows edits or hides navigation/verified status");
      const checkHeader = () => {
        const host=f.container.querySelector("[data-hmb-native-actions]");
        host.closest(".hmb-image-assets").dataset.hmbNativeHeader="active";
        host.innerHTML='<div class="bg-green-600"><span class="leading-none">Resolved</span></div>'
          +'<div class="bg-blue-600"><span class="leading-none">Unresolved</span></div>'
          +'<div class="bg-orange-600"><span class="leading-none">Running</span></div>'
          +'<div class="bg-red-600"><span class="leading-none">Error</span></div><button class="bg-blue-600">Run</button>';
        if (![...host.children].every((el,i)=>(getComputedStyle(el).display==="none")===(i<2)))
          throw Error("Shot header hid an action/error or retained a node-wide status");
      };
      checkHeader();
      f.widget.hmbSetImageAssetLibraryCompact(f.container,true,{geometry:false});
      checkHeader();
      const compact = f.container.querySelector('[data-compact-shot-row]');
      const number=compact.querySelector('[data-hmb-shot-check="true"]');
      if (!number || number.textContent!=="01" || getComputedStyle(number,"::before").fontSize!=="20px"
          || !compact.querySelector("[data-shot-lock]")) throw Error("Compact Shot status lost during mode switch");
      update(false);
      if (compact.querySelector("[data-shot-lock]")) throw Error("Compact status did not update before any mode toggle");
      f.widget.hmbSetImageAssetLibraryCompact(f.container,false,{geometry:false});
      if (panel().querySelector("[data-shot-lock]") || panel().querySelector("[data-shot-rename]").disabled
          || !panel().querySelector('[data-hmb-shot-check="true"]')) throw Error("Release failed to restore Shot editing");
    });
    await page.evaluate(() => { selectionFixture.observer.disconnect(); selectionFixture.controller.cleanup(); selectionFixture.prompt.cleanup(); });
    await page.close();
  }
  assert.deepEqual(errors, []);
  assert.equal(remoteRequests, 0);
  console.log(`HMB ImageAsset selection continuity Chrome: PASS (${cases.length} compact host echo formats, stale/foreign echoes, current callbacks, retained cards/images, zero remote requests)`);
} finally { await browser.close(); }
