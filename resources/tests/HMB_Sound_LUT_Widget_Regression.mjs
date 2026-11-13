// Audio Mix controls, local MOV export and immutable authored command capture.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { hmbColorLUTState, hmbColorLUTCommand, hmbRenderColorLUTWidget } from "../../widgets/HMBColorLUTLibraryWidget.js";

assert.deepEqual(hmbColorLUTState().audio_mix, {enabled:false,original_audio:"preserve",source:"current"});
assert.deepEqual(hmbColorLUTState({audio_mix:{enabled:"true",original_audio:"invalid"}}).audio_mix, {enabled:false,original_audio:"preserve",source:"current"});
const value = {schema_version:1, revision:1, source:{path:"C:/synthetic/completed.mov",name:"completed.mov"},
  sound:{connected:true,revision:"a".repeat(64)}, output:{codec:"prores"}, audio_mix:{enabled:false,original_audio:"preserve",source:"current"}};
assert.match(hmbRenderColorLUTWidget(value), /data-audio-enable/);
assert.match(hmbRenderColorLUTWidget(value), /data-export-local/);
const captured = hmbColorLUTCommand("export", value);
value.audio_mix.enabled = true;
assert.equal(captured.state.audio_mix.enabled, false);
assert.equal(captured.state.sound.revision, "a".repeat(64));
assert.equal("tracks" in captured.state.sound, false, "Browser carries presentation only; execution owns sound paths.");
value.audio_mix.enabled = false;

const require = createRequire(import.meta.url);
let playwright;
try { playwright=require("playwright"); }
catch { try { playwright=require(path.join(os.homedir(),".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); } catch {} }
const executablePath=process.env.HMB_COLOR_LUT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if(!playwright || !fs.existsSync(executablePath)) {
  console.log("Sound LUT widget state/command contract: PASS; real browser not_run (runtime unavailable)");
  process.exit(0);
}
const source=fs.readFileSync(new URL("../../widgets/HMBColorLUTLibraryWidget.js",import.meta.url));
const html=`<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#090e15}#widget{width:1180px;height:1000px}</style><div id="widget"></div><script type="module">
import mount from '/widget.js';window.commands=[];window.edits=[];window.state=${JSON.stringify(value)};
window.props=()=>({value:window.state,onChange:v=>window.edits.push(v),onCommand:v=>window.commands.push(JSON.parse(v))});
window.controller=mount(document.getElementById('widget'),window.props());window.ready=true;</script>`;
const origin="http://127.0.0.1:55000";
let browser;
try {
  browser=await playwright.chromium.launch({executablePath,headless:true,args:["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"]});
  const page=await browser.newPage({viewport:{width:1240,height:1100}}), errors=[];
  let external=0;
  page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/*",route=>{
    const url=new URL(route.request().url());
    if(url.origin===origin && url.pathname==="/")return route.fulfill({contentType:"text/html; charset=utf-8",body:html});
    if(url.origin===origin && url.pathname==="/widget.js")return route.fulfill({contentType:"text/javascript; charset=utf-8",body:source});
    external++;
    return route.abort();
  });
  await page.goto(origin);
  await page.waitForFunction(()=>window.ready);
  const local=page.locator("[data-export-local]"), mix=page.locator("[data-audio-enable]"), original=page.locator("[data-original-audio]");
  const details=page.locator("[data-audio-details]");
  const statusFits=()=>page.locator(".hmb-color-lut").evaluate(root=>{
    const status=root.querySelector(".cl-status").getBoundingClientRect();
    return status.bottom<=root.getBoundingClientRect().top+root.clientHeight;
  });
  assert.equal(await mix.isChecked(),false);
  assert.equal(await details.isHidden(),true,"Off hides Sound settings while leaving the Audio Mix switch available.");
  assert.equal(await statusFits(),true,"Default widget height keeps output and status in view.");
  assert.equal(await original.isDisabled(),true);
  assert.equal(await local.isEnabled(),true,"A local MOV needs no upload-project selection.");
  assert.equal(await page.locator('[data-action="export"]').isDisabled(),true,"Upload remains gated by its project.");
  await mix.check();
  assert.equal(await details.isVisible(),true);
  assert.equal(await statusFits(),true,"Audio settings fit with output and status at the default height.");
  await original.selectOption("mute");
  assert.deepEqual(await page.evaluate(()=>window.edits.at(-1).audio_mix),{enabled:true,original_audio:"mute",source:"current"});
  await local.click();
  assert.equal(await page.evaluate(()=>window.commands.at(-1).action),"export");
  assert.deepEqual(await page.evaluate(()=>window.commands.at(-1).state.audio_mix),{enabled:true,original_audio:"mute",source:"current"});
  assert.match(await page.locator('[data-action="upload_web"]').textContent(),/원본/);
  await page.evaluate(()=>{window.state={...window.state,revision:100,audio_mix:{enabled:true,original_audio:'preserve'},sound:{connected:false,revision:''}};window.controller.update(window.props());});
  assert.equal(await local.isDisabled(),true,"Missing sound source must block an enabled mix.");
  await mix.uncheck();
  assert.equal(await details.isHidden(),true);
  assert.equal(await local.isEnabled(),true,"Disabling Audio Mix restores ordinary local export.");
  await page.evaluate(()=>{
    const shot={channel_uuid:'channel-a',shot_uuid:'shot-a',number:1,name:'Shot A'};
    window.state={...window.state,revision:200,shot,
      shot_catalog:{schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'asset-owner',channel_uuid:shot.channel_uuid,generation:1,metadata_sha256:'a'.repeat(64),shots:[{...shot,revision:1}]},
      source:{path:'C:/synthetic/completed.mov',shot_uuid:shot.shot_uuid,channel_uuid:shot.channel_uuid},
      sound:{connected:true,revision:'b'.repeat(64)},audio_mix:{enabled:true,original_audio:'preserve',source:'current'}};
    window.controller.update(window.props());
  });
  await page.locator('[data-audio-source]').selectOption('rendered');
  await local.click();
  assert.equal(await page.evaluate(()=>window.commands.at(-1).state.audio_mix.source),'rendered','The completed-plan choice belongs to the immutable export click.');
  await page.locator('[data-audio-source]').selectOption('current');
  assert.equal(await page.evaluate(()=>window.edits.at(-1).audio_mix.source),'current');
  assert.deepEqual(errors,[]);
  assert.equal(external,0);
  const screenshot=process.env.HMB_SOUND_LUT_SCREENSHOT;
  if(screenshot)await page.screenshot({path:screenshot,fullPage:true});
  console.log(JSON.stringify({result:"PASS",audioDefaultOff:true,outputVisibleOnAndOff:true,localMOVWithoutProject:true,preserveMute:true,soundAuthorityPresentationOnly:true,exactCommandCapture:true,missingSoundGate:true,realBrowser:true,externalRequests:external}));
} finally { if(browser)await browser.close(); }
