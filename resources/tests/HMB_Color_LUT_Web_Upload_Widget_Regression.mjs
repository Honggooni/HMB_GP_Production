// Production-controller upload gating, immediate invalidation and persistent UI.
// Loopback fixture only: no Broker request, provider render or media upload.
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { hmbColorLUTState, hmbColorLUTCommand, hmbRenderColorLUTWidget } from "../../widgets/HMBColorLUTLibraryWidget.js";

const catalog = { schema: "hmb-shot-routing-catalog", version: 1, publisher_instance_uuid: "asset-owner", channel_uuid: "channel-one",
  generation: 1, metadata_sha256: "a".repeat(64), shots: [1,2,3,4,5].map(number => ({ shot_uuid: `shot-${number}`, number, name: `e201s00${number}c001__`, revision: 1 })) };
const value = { shot_catalog: catalog, shot: { channel_uuid: "channel-one", shot_uuid: "shot-1" }, settings: { enabled: true, precision_version: 2 },
  web_upload: { enabled: true, phase: "ready", reason: "본인 소유 샷 보정 영상 준비됨" } };
assert.equal(hmbColorLUTState(value).web_upload.enabled, true);
assert.equal(hmbColorLUTState({ ...value, shot: {} }).web_upload.enabled, false, "Only cannot enable a web upload");
assert.equal(hmbColorLUTCommand("upload_web", value).action, "upload_web");
assert.match(hmbRenderColorLUTWidget(value), /data-action="save_profile"[\s\S]*cl-web-upload[\s\S]*data-action="upload_web"/);
assert.match(hmbRenderColorLUTWidget(value), /data-action="upload_web" type="button" disabled/);

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); } catch {} }
const executablePath = process.env.HMB_COLOR_LUT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!playwright || !fs.existsSync(executablePath)) {
  console.log("Color LUT upload widget contract: PASS; browser interaction not run (optional runtime unavailable)");
  process.exit(0);
}
const source = fs.readFileSync(fileURLToPath(new URL("../../widgets/HMBColorLUTLibraryWidget.js", import.meta.url)));
const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0}#widget{width:1180px;height:920px}</style><div id="widget"></div><script type="module">
import mount from '/widget.js';window.publications=[];window.commands=[];window.state=${JSON.stringify(value)};
window.props=()=>({value:window.state,onChange:v=>window.publications.push(v),onCommand:v=>window.commands.push(JSON.parse(v))});
window.controller=mount(document.getElementById('widget'),window.props());window.ready=true;</script>`;
const server = http.createServer((req,res) => { res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");res.end(req.url === "/widget.js" ? source : html); });
await new Promise(resolve => server.listen(0,"127.0.0.1",resolve));
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless:true, args:["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({viewport:{width:1250,height:1000}});
  const errors=[]; page.on("pageerror", error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(()=>window.ready);
  const button=page.locator('[data-action="upload_web"]');
  assert.equal(await button.isEnabled(),true);
  const canvas=await page.locator('[data-preview]').evaluate(el => (window.originalCanvas=el,true));
  await button.click();
  assert.equal(await button.isDisabled(),true);
  assert.equal(await page.evaluate(()=>window.commands.length),1);
  assert.equal(await page.evaluate(()=>window.commands[0].action),"upload_web");
  await page.evaluate(()=>{window.state={...window.state,revision:50,web_upload:{enabled:false,phase:'complete',reason:'웹 업로드 완료'}};window.controller.update(window.props());});
  assert.equal(await button.isDisabled(),true);
  assert.match(await button.textContent(),/완료/);
  await page.evaluate(()=>{window.state={...window.state,revision:51,web_upload:{enabled:true,phase:'ready',reason:'준비됨'}};window.controller.update(window.props());});
  assert.equal(await button.isEnabled(),true);
  await page.locator('[data-adjust="exposure"]').evaluate(el=>{el.value='2';el.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await button.isDisabled(),true,"Unflushed grade edit invalidates immediately");
  await page.evaluate(()=>{window.state={...window.state,revision:100,shot:{},web_upload:{enabled:true,phase:'ready',reason:'forged Only'}};window.controller.update(window.props());});
  assert.equal(await button.isDisabled(),true,"Only stays disabled even with an enabled browser payload");
  assert.equal(await page.locator('[data-preview]').evaluate(el=>el===window.originalCanvas),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:"PASS",enabledOnlyForBoundShot:true,oneClickOneCommand:true,immediateGradeInvalidation:true,completedDisabled:true,retainedCanvas:true,realBrowser:true}));
} finally { if(browser)await browser.close();await new Promise(resolve=>server.close(resolve)); }
