import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const source = fs.readFileSync(new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url), "utf8");
const channel = "11111111-1111-4111-8111-111111111111";
const shots = Array.from({ length: 5 }, (_, index) => ({
  channel_uuid: channel, shot_uuid: `22222222-2222-4222-8222-${String(index + 1).padStart(12, "0")}`,
  number: index + 1, name: `asset_custom_${index + 1}`, selected_source_uids: [],
}));
const fixture = {
  multi_shot_enabled: true, shot: shots[0], images: [], videos: [],
  image_asset: { shot_catalog: shots, shot_catalog_routing: {
    publisher_instance_uuid: channel, channel_uuid: channel, generation: 1, metadata_sha256: "a".repeat(64),
  } },
};
const html = `<!doctype html><meta charset="utf-8"><div id="zoom" style="transform-origin:top left"><div id="shell" class="react-flow__node" style="width:1700px;height:1250px;overflow:hidden;position:relative"><div style="height:96px">Native node header</div><div id="legacy-parameter" style="height:1193px;min-height:1193px;max-height:1193px;overflow:hidden"><div id="host" style="width:100%;height:1133px"></div></div></div></div><script type="module">
import mount, * as widget from "/widget.js";
const NativeResizeObserver = window.ResizeObserver;
window.liveResizeObservers = 0;
window.ResizeObserver = class extends NativeResizeObserver {
  constructor(callback) { super(callback); window.liveResizeObservers += 1; this.live=true; }
  disconnect() { if(this.live) { window.liveResizeObservers -= 1; this.live=false; } super.disconnect(); }
};
window.widget = widget;
window.latest = ${JSON.stringify(fixture)};
window.changes = 0;
window.start = (raw) => {
  window.controller?.cleanup();
  const node = document.createElement('div'); node.id = 'host'; node.style.width = '100%';
  document.getElementById('host').replaceWith(node);
  window.host = node;
  window.latest = structuredClone(raw);
  window.props = (value) => ({ value: JSON.stringify(value), disabled: false, onChange(next) {
    window.latest = JSON.parse(next); window.changes += 1;
    window.controller.update(window.props(window.latest));
  } });
  window.controller = mount(node, window.props(window.latest));
};
window.start(window.latest);
window.ready = true;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(req.url === "/widget.js" ? source : html);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const browser = await playwright.chromium.launch({
  executablePath: process.env.HMB_PROMPT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true,
});
let externalRequests = 0;
const failures = [];
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 1700 }, hasTouch: true });
  page.setDefaultTimeout(8000);
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).hostname !== "127.0.0.1") { externalRequests += 1; return route.abort(); }
    return route.continue();
  });
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.ready);
  assert.deepEqual(await page.locator('#shell').evaluate(shell => ({
    width:parseFloat(shell.style.width),height:parseFloat(shell.style.height),
  })), {width:1800,height:1350}, 'A saved positive 1700×1250 node starts at the final 1800×1350 size.');
  if(process.env.HMB_PROMPT_START_SCREENSHOT)await page.screenshot({path:process.env.HMB_PROMPT_START_SCREENSHOT,fullPage:true});
  if(process.env.HMB_PROMPT_START_BOTTOM_SCREENSHOT){
    await page.locator('.center').evaluate(center=>{center.scrollTop=center.scrollHeight;});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.screenshot({path:process.env.HMB_PROMPT_START_BOTTOM_SCREENSHOT,fullPage:true});
    await page.locator('.center').evaluate(center=>{center.scrollTop=0;});
  }
  assert.equal(await page.locator("[data-prompt-shot]").count(), 5);
  assert.equal(await page.locator("[data-shot-selector]").count(), 0);
  assert.equal(await page.locator(".center").count(), 1);
  assert.equal(await page.locator(".group-card").count(), 4);
  assert.equal(await page.locator(".center.nowheel").count(), 1, "The bounded body keeps native scrolling instead of canvas zoom.");
  assert.deepEqual(await page.locator(".prompt-shot-row b").allTextContents(), shots.map((shot) => shot.name));
  const textKey = await page.locator("[data-text-key]").first().getAttribute("data-text-key");
  const controlCount = await page.locator("textarea, input, select").count();
  const choose = async (index) => {
    const row = page.locator(`[data-prompt-shot="${shots[index].shot_uuid}"]`);
    if (await row.getAttribute("aria-expanded") !== "true") await row.tap();
    await page.waitForFunction((uuid) => window.latest.shot?.shot_uuid === uuid, shots[index].shot_uuid);
  };
  for (let index = 0; index < shots.length; index += 1) {
    await choose(index);
    await page.locator(`[data-text-key="${textKey}"]`).fill(`Prompt_${index + 1} {literal}`);
    await page.waitForFunction(({ key, expected }) => window.latest.text?.[key] === expected,
      { key: textKey, expected: `Prompt_${index + 1} {literal}` });
  }
  for (let index = shots.length - 1; index >= 0; index -= 1) {
    await choose(index);
    const actual = await page.locator(`[data-text-key="${textKey}"]`).inputValue();
    assert.equal(actual, `Prompt_${index + 1} {literal}`);
    assert.equal(await page.locator(".group-card").count(), 4);
    assert.equal(await page.locator("textarea, input, select").count(), controlCount);
    assert.equal(await page.locator(".prompt-shot-row[aria-selected=true]").count(), 1);
    const selectedColor = await page.locator('.prompt-shot-row[aria-selected="true"]').evaluate((tab) => {
      const active = getComputedStyle(tab), number = getComputedStyle(tab.querySelector('.prompt-shot-number'));
      const inactive = getComputedStyle(document.querySelector('.prompt-shot-row[aria-selected="false"]'));
      return {border:active.borderTopWidth,background:active.backgroundImage,inactive:inactive.backgroundImage,
        numberBackground:number.backgroundColor,header:getComputedStyle(document.querySelector('.hmb-dashboard')).getPropertyValue('--hmb-shot-accent').trim(),
        accent:active.getPropertyValue('--row-accent').trim()};
    });
    assert.equal(selectedColor.border, '2px', 'The selected named tab has a clear colored boundary.');
    assert.notEqual(selectedColor.background, selectedColor.inactive);
    assert.notEqual(selectedColor.numberBackground, 'rgba(0, 0, 0, 0)');
    assert.equal(selectedColor.header, selectedColor.accent, 'The header and selected Shot use the same established palette.');
    assert.equal(await page.locator(".prompt-shot-content").getAttribute("data-shot-editor"), shots[index].shot_uuid);
    assert.equal(await page.locator(".prompt-shot-content").evaluate((body) => body.previousElementSibling?.getAttribute("data-prompt-shot")), shots[index].shot_uuid);
  }
  const repeatedTab = await page.evaluate(() => { const before = window.changes; document.querySelector('[data-prompt-shot]').click(); return window.changes-before; });
  assert.equal(repeatedTab, 0, "Clicking the active tab keeps its editor and does not publish a fold.");
  assert.equal(await page.locator(".group-card").count(), 4);
  const oldCollapsed = await page.evaluate(() => { const value=structuredClone(window.latest);value.ui.shot_editor_expanded=false;return value; });
  await page.evaluate((raw) => window.start(raw), oldCollapsed);
  assert.equal(await page.locator(".group-card").count(), 4, "A saved accordion fold cannot hide the new tab editor.");
  await choose(0);
  assert.equal(await page.locator(`[data-text-key="${textKey}"]`).inputValue(), "Prompt_1 {literal}");
  const saved = await page.evaluate(() => structuredClone(window.latest));
  await page.evaluate((raw) => window.start(raw), saved);
  await choose(3);
  assert.equal(await page.locator(`[data-text-key="${textKey}"]`).inputValue(), "Prompt_4 {literal}");
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

  // Catalog-only changes must retain the live editor DOM and handler, including
  // a newly appended/deleted UUID. The source is backend authority, not a global event.
  const continuity = await page.evaluate(() => {
    const input = window.host.querySelector('[data-text-key]');
    window.editorBefore = input;
    const next = structuredClone(window.latest);
    next.source_sync_revision = (next.source_sync_revision || 0) + 1;
    next.image_asset.shot_catalog[0].name = 'renamed_asset';
    window.latest = next;
    window.controller.update(window.props(next));
    return true;
  });
  assert.equal(continuity, true);
  await page.waitForFunction(() => document.querySelector('.prompt-shot-row b')?.textContent === 'renamed_asset');
  const sameEditor = await page.evaluate(() => window.editorBefore === window.host.querySelector('[data-text-key]'));
  assert.equal(sameEditor, true);
  await choose(0);
  assert.equal(await page.locator(`[data-text-key="${textKey}"]`).inputValue(), "Prompt_1 {literal}");

  const geometry = await page.evaluate(() => {
    const center = document.querySelector('.center');center.scrollTop=center.scrollHeight;
    const dashboard = document.querySelector('.hmb-dashboard').getBoundingClientRect();
    const last = document.querySelector('[data-group-id="videoText"]').getBoundingClientRect();
    return { dashboardBottom: dashboard.bottom, lastBottom: last.bottom,
      lastRowBottom: [...document.querySelectorAll('.prompt-shot-row')].at(-1).getBoundingClientRect().bottom,
      rowColors: [...document.querySelectorAll('.prompt-shot-row')].map((row) => getComputedStyle(row).getPropertyValue('--row-accent').trim()) };
  });
  assert.ok(geometry.lastBottom <= geometry.dashboardBottom + 1, JSON.stringify(geometry));
  assert.ok(geometry.lastRowBottom <= geometry.dashboardBottom + 1, JSON.stringify(geometry));
  assert.deepEqual(geometry.rowColors, ["#F472B6", "#3B82F6", "#10B981", "#8B5CF6", "#EAB308"]);
  for (const [width,height,scale] of [[1100,760,1],[760,540,.5],[980,860,1.5],[1700,1250,1]]) {
    const before = await page.evaluate(() => window.changes);
    await page.evaluate(({width,height,scale})=>{
      const shell=document.querySelector('#shell');shell.style.width=width+'px';shell.style.height=height+'px';
      document.querySelector('#zoom').style.transform='scale('+scale+')';
    },{width,height,scale});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))));
    const resized=await page.evaluate(()=>{
      const shell=document.querySelector('#shell'),dashboard=document.querySelector('.hmb-dashboard'),center=document.querySelector('.center');
      center.scrollTop=center.scrollHeight;
      const bounds=dashboard.getBoundingClientRect(),native=shell.getBoundingClientRect(),last=document.querySelector('[data-group-id="videoText"]').getBoundingClientRect();
      const tabs=[...document.querySelectorAll('[data-prompt-shot]')].map(tab=>tab.getBoundingClientRect());
      return{bottom:bounds.bottom,nodeBottom:native.bottom,lastBottom:last.bottom,lastTop:last.top,bodyTop:center.getBoundingClientRect().top,
        tabsTop:tabs.map(tab=>Math.round(tab.top)),tabBounds:tabs.map(tab=>({left:tab.left,right:tab.right})),left:bounds.left,right:bounds.right,
        height:parseFloat(shell.style.height),scrollable:center.scrollHeight>center.clientHeight,bodyCount:document.querySelectorAll('.center').length};
    });
    assert.equal(resized.height,height,"Responsive layout must retain the user-selected node height.");
    assert.ok(resized.bottom<=resized.nodeBottom+1,JSON.stringify({width,height,scale,...resized}));
    assert.ok(resized.lastBottom<=resized.bottom+1 && resized.lastTop>=resized.bodyTop-1,JSON.stringify(resized));
    assert.equal(new Set(resized.tabsTop).size,1,"Five named tabs remain together in the upper bar.");
    assert.ok(resized.tabBounds.every(tab=>tab.left>=resized.left-1&&tab.right<=resized.right+1));
    assert.equal(resized.bodyCount,1);assert.equal(resized.scrollable,true);
    assert.equal(await page.evaluate(()=>window.changes),before,"Node resize and canvas zoom are presentation-only.");
    if(width===1100 && process.env.HMB_PROMPT_NARROW_SCREENSHOT) await page.screenshot({path:process.env.HMB_PROMPT_NARROW_SCREENSHOT,fullPage:true});
  }
  const customSizeSurvives = await page.evaluate(() => {
    const shell=document.querySelector('#shell');shell.style.width='1120px';shell.style.height='780px';
    for(let index=0;index<10;index+=1)window.controller.update(window.props(structuredClone(window.latest)));
    return {width:parseFloat(shell.style.width),height:parseFloat(shell.style.height)};
  });
  assert.deepEqual(customSizeSurvives,{width:1120,height:780},'Repeated props cannot overwrite a session resize.');
  await choose(4);await choose(0);
  assert.deepEqual(await page.locator('#shell').evaluate(shell=>({width:parseFloat(shell.style.width),height:parseFloat(shell.style.height)})),
    {width:1120,height:780},'Changing the active Shot cannot restore startup dimensions.');
  const remountedSize=await page.evaluate(async()=>{
    window.start(structuredClone(window.latest));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const shell=document.querySelector('#shell');return {width:parseFloat(shell.style.width),height:parseFloat(shell.style.height)};
  });
  assert.deepEqual(remountedSize,{width:1120,height:780},'A widget remount on the same workflow shell keeps session resizing.');
  await page.evaluate(()=>{const shell=document.querySelector('#shell');shell.style.width='1700px';shell.style.height='1250px';});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const groupHandle=page.locator('[data-resize-group="videoText"]');
  await groupHandle.scrollIntoViewIfNeeded();
  const handleBox=await groupHandle.boundingBox();
  const beforeGroupResize=await page.evaluate(()=>window.changes);
  await page.mouse.move(handleBox.x+handleBox.width/2,handleBox.y+handleBox.height/2);
  await page.mouse.down();await page.mouse.move(handleBox.x+handleBox.width/2,handleBox.y+handleBox.height/2+30,{steps:3});await page.mouse.up();
  await page.waitForFunction(before=>window.changes>before,beforeGroupResize);
  assert.equal(await page.locator('#shell').evaluate(node=>parseFloat(node.style.height)),1250,
    "Resizing an inner group must not restore the old outer minimum height.");
  await page.locator(`[data-text-key="${textKey}"]`).focus();
  await page.locator(`[data-text-key="${textKey}"]`).evaluate((input) => {
    input.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "한" }));
    input.value = "한글 원문 {literal} 그대로";
    input.dispatchEvent(new InputEvent("input", { bubbles: true, data: "한글", isComposing: true }));
    input.setSelectionRange(3, 7);
    input.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "한글" }));
  });
  await choose(1);
  assert.equal(await page.locator(`[data-text-key="${textKey}"]`).inputValue(), "Prompt_2 {literal}");
  await choose(0);
  assert.equal(await page.locator(`[data-text-key="${textKey}"]`).inputValue(), "한글 원문 {literal} 그대로");
  await page.waitForFunction((key) => {
    const input = document.querySelector(`[data-text-key="${key}"]`);
    return document.activeElement === input && input.selectionStart === 3 && input.selectionEnd === 7;
  }, textKey);
  assert.equal(await page.evaluate(() => Boolean(window.host.__hmbPromptLibraryCompositionActive)), false);
  await choose(2);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const idle = await page.evaluate(async () => {
    const changes = window.changes;
    let bodyMutations = 0;
    const observer = new MutationObserver((records) => { bodyMutations += records.length; });
    observer.observe(window.host, { childList: true, subtree: true });
    for (let index = 0; index < 25; index += 1) window.controller.update(window.props(structuredClone(window.latest)));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    observer.disconnect();
    return { publications: window.changes - changes, bodyMutations };
  });
  assert.deepEqual(idle, { publications: 0, bodyMutations: 0 });
  // Exact repeated state may skip normalization only after canonical equality.
  // Callback/disabled changes and a locally edited draft must still be observed.
  const echoGuards = await page.evaluate(async () => {
    const value=JSON.stringify(window.latest), before=window.changes;
    for(let index=0;index<5;index+=1) window.controller.update(window.props(window.latest));
    const fresh=window.props(window.latest), native=fresh.onChange;
    let freshCalls=0;fresh.onChange=(next)=>{freshCalls+=1;native(next);};
    window.controller.update(fresh);
    const input=window.host.querySelector('[data-text-key]');
    input.value='Fresh callback {exact literal}';input.dispatchEvent(new InputEvent('input',{bubbles:true,data:'Fresh callback'}));
    window.controller.update({...fresh,value});
    const draftSurvived=input.value==='Fresh callback {exact literal}';
    input.dispatchEvent(new FocusEvent('blur',{bubbles:true}));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const body=window.host.querySelector('.center');
    window.controller.update({...window.props(window.latest),disabled:true});
    const disabled=window.host.querySelector('.hmb-dashboard').classList.contains('disabled')
      && [...window.host.querySelectorAll('[data-prompt-shot]')].every(tab=>tab.disabled);
    window.controller.update(window.props(window.latest));
    return {draftSurvived,freshCalls,disabled,enabled:![...window.host.querySelectorAll('[data-prompt-shot]')].some(tab=>tab.disabled),
      sameBody:body===window.host.querySelector('.center'),published:window.changes>before};
  });
  assert.equal(echoGuards.draftSurvived,true);assert.ok(echoGuards.freshCalls>=1);
  assert.equal(echoGuards.disabled,true);assert.equal(echoGuards.enabled,true);assert.equal(echoGuards.published,true);
  assert.equal(echoGuards.sameBody,true,'Host disabled changes retain the active editor DOM.');
  const sourceInvalidation=await page.evaluate(async()=>{
    const body=window.host.querySelector('.center');
    for(let index=0;index<5;index+=1)window.controller.update(window.props(window.latest));
    const next=structuredClone(window.latest);next.source_sync_revision+=1;
    next.image_asset.shot_catalog[2].name='source_renamed_after_cached_echo';window.latest=next;
    window.controller.update(window.props(next));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    return {name:window.host.querySelectorAll('.prompt-shot-row b')[2].textContent,sameBody:body===window.host.querySelector('.center')};
  });
  assert.deepEqual(sourceInvalidation,{name:'source_renamed_after_cached_echo',sameBody:true},'A newer backend source invalidates the identical-echo cache and retains the active editor.');
  const screenshot = process.env.HMB_PROMPT_MANAGER_SCREENSHOT;
  if (screenshot) await page.screenshot({ path: screenshot, fullPage: true });
  const cleanup = await page.evaluate(async()=>{
    const changes=window.changes;window.controller.cleanup();
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    return {observers:window.liveResizeObservers,children:window.host.children.length,publications:window.changes-changes};
  });
  assert.deepEqual(cleanup,{observers:0,children:0,publications:0},"Unmount disconnects the resize observer and leaves no delayed writes.");
  for (const [storedWidth,storedHeight,scale,manager] of [[980,620,.5,true],[2200,1800,1.5,true],[1040,900,.75,false],[0,0,1,true]]) {
    const initialSize=await page.evaluate(async({storedWidth,storedHeight,scale,manager})=>{
      window.controller?.cleanup();
      const previousShell=document.querySelector('#shell'),shell=document.createElement('div');
      shell.id='shell';shell.className='react-flow__node';shell.style.position='relative';
      shell.innerHTML='<div style="height:96px">Native node header</div><div id="legacy-parameter"><div id="host"></div></div>';
      previousShell.replaceWith(shell);
      shell.style.minWidth='0px';shell.style.minHeight='0px';shell.style.width=storedWidth+'px';shell.style.height=storedHeight+'px';
      document.querySelector('#zoom').style.transform='scale('+scale+')';
      const raw=structuredClone(window.latest);raw.multi_shot_enabled=manager;
      const wrapper=document.querySelector('#legacy-parameter');wrapper.style.height='1193px';wrapper.style.minHeight='1193px';wrapper.style.maxHeight='1193px';
      if(!manager){raw.ui.group_heights={imageSources:1700,imageText:900,videoSources:800,videoText:700};}
      const before=window.changes;window.start(raw);
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const center=document.querySelector('.center');center.scrollTop=center.scrollHeight;
      const node=shell.getBoundingClientRect(),dashboard=document.querySelector('.hmb-dashboard').getBoundingClientRect();
      const last=document.querySelector('[data-group-id="videoText"]').getBoundingClientRect();
      const result={width:parseFloat(shell.style.width),height:parseFloat(shell.style.height),minimum:parseFloat(shell.style.minHeight),
        cssWidth:shell.offsetWidth,cssHeight:shell.offsetHeight,visualWidth:node.width,visualHeight:node.height,
        lastVisible:last.bottom<=dashboard.bottom+1&&last.top>=center.getBoundingClientRect().top-1,
        dashboardWithinNode:dashboard.bottom<=node.bottom+1,wrapperWithinNode:wrapper.getBoundingClientRect().bottom<=node.bottom+1,
        dashboardWithinWrapper:dashboard.bottom<=wrapper.getBoundingClientRect().bottom+1,
        storedGroupsPreserved:JSON.stringify(window.latest.ui.group_heights)===JSON.stringify(raw.ui.group_heights),
        publications:window.changes-before};
      if(!manager){
        const hydrated=structuredClone(window.latest);hydrated.multi_shot_enabled=true;window.latest=hydrated;
        window.controller.update(window.props(hydrated));
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        result.afterHydrationHeight=parseFloat(shell.style.height);
        shell.style.width='1120px';shell.style.height='780px';
        for(let index=0;index<5;index+=1)window.controller.update(window.props(structuredClone(window.latest)));
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        result.hydratedUserResize={width:parseFloat(shell.style.width),height:parseFloat(shell.style.height)};
        result.publications=window.changes-before;
      }
      window.controller.cleanup();return result;
    },{storedWidth,storedHeight,scale,manager});
    assert.equal(initialSize.width,1800);assert.equal(initialSize.height,1350);
    if(manager)assert.equal(initialSize.minimum,240);
    else assert.ok(initialSize.minimum>=1193);
    assert.equal(initialSize.cssWidth,1800);assert.equal(initialSize.cssHeight,1350);
    assert.ok(Math.abs(initialSize.visualWidth-1800*scale)<1,JSON.stringify(initialSize));
    assert.ok(Math.abs(initialSize.visualHeight-1350*scale)<1,JSON.stringify(initialSize));
    assert.equal(initialSize.lastVisible,true,'The final VFX group remains reachable after cold-load normalization.');
    assert.equal(initialSize.dashboardWithinNode,true);
    assert.equal(initialSize.wrapperWithinNode,true);assert.equal(initialSize.dashboardWithinWrapper,true,'An old SDK widget-height wrapper cannot clip the final editor.');
    assert.equal(initialSize.storedGroupsPreserved,true,'Large stored group heights remain authored state and scroll internally.');
    assert.equal(initialSize.publications,0,'Startup geometry and zoom cause no property/engine publication.');
    if(!manager){
      assert.equal(initialSize.afterHydrationHeight,1350,'Legacy-to-manager hydration cannot replace the fixed startup dimensions.');
      assert.deepEqual(initialSize.hydratedUserResize,{width:1120,height:780},'Hydrated legacy nodes retain subsequent user resizing.');
    }
  }
  assert.equal(externalRequests, 0);
  assert.deepEqual(failures, []);
  console.log("HMB Prompt multi Shot browser: PASS (5 independent touch tabs and clear active colors, one editor, 1800×1350px restored/new defaults across zoom, subsequent custom sizes, 4 resize/zoom states with VFX reachable, Korean IME/caret, exact echo callback/disabled/draft/source guards, 25 identical props cause 0 publications/mutations; external requests 0)");
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
