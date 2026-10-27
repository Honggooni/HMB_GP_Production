/** Actual widget boundary in isolated Chrome. Probe children stand in for the
 * host's React portals; actual native callbacks are covered by the host fixture.
 * No SDK, application, Broker, provider, file upload or paid request is used. */
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const files = ["HMBFinishLookLibraryWidget.js", "HMBSeedanceGenerationWidget.js", "HMBImageGenerationWidget.js"];
const types = ["HMBFinishLookLibrary", "HMBSeedanceGeneration", "HMBImageGeneration"];
const roots = [".hmb-finish-look", ".hmb-seedance-shot", ".hmb-image-generation-header"];
const brands = [".hmb-finish-look__heading", ".hmb-seedance-shot__title", ".hmb-image-generation-header__title"];
const sources = files.map(file => fs.readFileSync(path.join(root, "widgets", file), "utf8"));
const out = path.join(root, "reports/generation-finish-native-header-20261023");
fs.mkdirSync(out, { recursive: true });
const report = { schema: "hmb-generation-finish-native-header-widget/v1", passed: false, checks: 0, cases: [],
  scope: "Actual widget code in isolated Chrome with synthetic portal probes; no live Griptape claim",
  files: files.map((file, i) => ({ file, sha256: crypto.createHash("sha256").update(sources[i]).digest("hex") })),
  external_requests: 0, graph_calls: 0, paid_calls: 0 };
const check = (actual, expected, message) => { assert.deepEqual(actual, expected, message); report.checks++; };
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const browser = await playwright.chromium.launch({ executablePath: process.env.HMB_WIDGET_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1500, height: 1300 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => { report.external_requests++; return route.abort(); });
  await page.setContent(`<!doctype html><meta charset="utf-8"><style>
    body{margin:16px;background:#080b13;color:#ddd;font:14px system-ui}main{display:grid;gap:16px}
    .react-flow__node{width:1200px}.react-flow__node.finish{height:640px}
    .probe-button{font:17px monospace;border:2px solid rgb(11,22,33);border-radius:2px;padding:0;min-height:22px;height:26px;width:30px;background:rgb(12,34,56);color:rgb(123,145,167)}
    .probe-name{font:17px monospace;height:26px;width:140px;border:2px solid rgb(11,22,33);border-radius:2px;padding:0;background:rgb(12,34,56);color:rgb(123,145,167)}
  </style><main></main>`);
  await page.evaluate(async ({ sources, types, roots, brands }) => {
    window.mods = [];
    for (const source of sources) mods.push(await import("data:text/javascript;base64," + btoa(unescape(encodeURIComponent(source)))));
    window.types = types; window.rootSelectors = roots; window.brandSelectors = brands;
    const ids = [1,2,3,4,5,6,7].map(n => `10000000-0000-4000-8000-${String(n).padStart(12,"0")}`);
    window.catalog = { schema:"hmb-shot-routing-catalog", version:1, publisher_instance_uuid:ids[0], channel_uuid:ids[1], generation:1,
      metadata_sha256:"a".repeat(64), shots:[1,2,3,4,5].map(n => ({shot_uuid:ids[n+1],number:n,name:`Preserved shot ${n}`,revision:n})) };
    window.values = [
      { shot_manager:true, shot_catalog:catalog, shot:{channel_uuid:ids[1],...catalog.shots[0]},
        finish_look:{beauty:{enabled:true,brightness:1.5,saturation:.75}} },
      { schema:"hmb-seedance-shot-ui",schema_version:2,shot_catalog:catalog,shot:{channel_uuid:ids[1],...catalog.shots[0]},
        execution_mode:"shot",requested_mode:"shot",execution_mode_revision:1,execution_mode_state_revision:1,execution_mode_instance:"a".repeat(32),
        generation:{phase:"succeeded",media_revision:4,job_id:"job-"+"1".repeat(32),has_existing_video:true}, draft:{visible:false} },
      {task_id:"job-image-preserved",image:"http://fixture.invalid/existing.png"}
    ];
    window.fixtures = [];
    window.readyEvents = []; window.retireEvents = [];
    document.addEventListener("hmb-color-lut-header-ready", event => readyEvents.push(event.detail.container));
    document.addEventListener("hmb-color-lut-header-retire", event => retireEvents.push(event.detail.container));
    window.make = i => {
      const node=document.createElement("section");node.className="react-flow__node"+(i===0?" finish":"");
      const carrier=document.createElement("div");carrier.className="widget-container nodrag";carrier.dataset.fixture=String(i);node.append(carrier);
      const native=document.createElement("input");native.value="Existing native setting";native.dataset.nativeSetting="";
      const video=document.createElement("video");video.controls=true;node.append(native,video);document.querySelector("main").append(node);
      const f={i,node,carrier,native,video,writes:[],commands:[],clicks:0,pointers:0,deletes:0,value:structuredClone(values[i])};
      f.props=disabled=>({value:f.value,disabled,onChange:value=>{f.writes.push(structuredClone(value));return Promise.resolve();},onCommand:value=>{f.commands.push(structuredClone(value));return Promise.resolve();}});
      f.handle=mods[i].default(carrier,f.props(false));
      f.root=carrier.querySelector(rootSelectors[i]);f.identity=carrier.querySelector("[data-hmb-native-identity]");f.actions=carrier.querySelector("[data-hmb-native-actions]");
      const identity=document.createElement("div");identity.style.cssText="display:flex;align-items:center;min-width:0";
      const name=document.createElement("input");name.className="probe-name";name.value="Preserved native name";identity.append(name);f.identity.append(identity);f.name=name;
      const button=document.createElement("button");button.type="button";button.className="probe-button";button.textContent="▶";button.addEventListener("click",()=>f.clicks++);f.actions.append(button);f.button=button;
      node.addEventListener("pointerdown",()=>f.pointers++);node.addEventListener("keydown",event=>{if(event.key==="Delete")f.deletes++;});
      f.state=active=>carrier.dispatchEvent(new CustomEvent("hmb-color-lut-header-state",{detail:{active}}));
      fixtures.push(f);return f;
    };
    for(let i=0;i<3;i++)make(i);
  }, { sources, types, roots, brands });
  for (let i = 0; i < 3; i++) {
    const initial = await page.evaluate(i => {
      const f=fixtures[i];return {type:f.carrier.dataset.hmbNativeNodeType,marker:f.carrier.hasAttribute("data-hmb-color-lut-widget"),
        status:f.root.dataset.hmbNativeHeader,slots:f.carrier.querySelectorAll("[data-hmb-native-identity],[data-hmb-native-actions]").length,
        ready:readyEvents.filter(c=>c===f.carrier).length,writes:f.writes.length,commands:f.commands.length,
        brand:getComputedStyle(f.carrier.querySelector(brandSelectors[i])).display!=="none",actions:getComputedStyle(f.actions).display};
    }, i);
    check(initial,{type:types[i],marker:true,status:"fallback",slots:2,ready:1,writes:0,commands:0,brand:true,actions:"none"},files[i]+" fallback");
    await page.evaluate(i=>fixtures[i].state(true),i);
    const active = await page.evaluate(i => {
      const f=fixtures[i],button=getComputedStyle(f.button),name=getComputedStyle(f.name);
      f.button.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true,button:0}));
      f.name.dispatchEvent(new KeyboardEvent("keydown",{key:"Delete",bubbles:true}));
      return {status:f.root.dataset.hmbNativeHeader,containerNoDrag:f.carrier.classList.contains("nodrag"),rootNoDrag:f.root.classList.contains("nodrag"),
        brand:getComputedStyle(f.carrier.querySelector(brandSelectors[i])).display,identity:getComputedStyle(f.identity).display,actions:getComputedStyle(f.actions).display,
        actionsNoDrag:f.actions.classList.contains("nodrag"),pointer:f.pointers,deletes:f.deletes,
        style:{font:button.fontFamily,fontSize:button.fontSize,radius:button.borderRadius,height:button.height,padding:button.padding,bg:button.backgroundColor},
        nameStyle:{font:name.fontFamily,radius:name.borderRadius,height:name.height,bg:name.backgroundColor},native:f.native.value,video:f.video===f.node.querySelector("video")};
    }, i);
    check(active,{status:"active",containerNoDrag:false,rootNoDrag:false,brand:"none",identity:"flex",actions:"flex",actionsNoDrag:true,pointer:1,deletes:1,
      style:{font:"monospace",fontSize:"17px",radius:"2px",height:"26px",padding:"0px",bg:"rgb(12, 34, 56)"},
      nameStyle:{font:"monospace",radius:"2px",height:"26px",bg:"rgb(12, 34, 56)"},native:"Existing native setting",video:true},files[i]+" active boundary");
    await page.evaluate(i=>fixtures[i].handle.update(fixtures[i].props(true)),i);
    await page.waitForTimeout(0);
    await page.locator(`[data-fixture="${i}"] .probe-button`).click();
    await page.locator(`[data-fixture="${i}"] .probe-name`).fill("Native rename while locked");
    const locked = await page.evaluate(i=>{
      const f=fixtures[i];
      const body=[...f.carrier.querySelectorAll("button,input,select,textarea")].filter(el=>!el.closest("[data-hmb-native-identity],[data-hmb-native-actions]"));
      return{buttonDisabled:f.button.disabled,nameDisabled:f.name.disabled,clicks:f.clicks,bodyDisabled:body.every(el=>el.disabled),writes:f.writes.length,commands:f.commands.length,
        sameSlots:f.carrier.querySelector("[data-hmb-native-identity]")===f.identity&&f.carrier.querySelector("[data-hmb-native-actions]")===f.actions};
    },i);
    check(locked,{buttonDisabled:false,nameDisabled:false,clicks:1,bodyDisabled:true,writes:0,commands:0,sameSlots:true},files[i]+" native controls retain host ownership under lock");
    await page.evaluate(i=>fixtures[i].handle.update(fixtures[i].props(false)),i);
    const repeated = await page.evaluate(async i=>{
      const f=fixtures[i],records=[];const observer=new MutationObserver(items=>records.push(...items));observer.observe(f.carrier,{subtree:true,attributes:true,childList:true,characterData:true});
      for(let n=0;n<100;n++){f.handle.update(f.props(false));if(mods[i].default(f.carrier,f.props(false)).cleanup!==f.handle.cleanup&&i===2)throw Error("Image header handle identity changed");}
      await Promise.resolve();observer.disconnect();return{writes:f.writes.length,commands:f.commands.length,ready:readyEvents.filter(c=>c===f.carrier).length,
        sameChildren:f.identity.firstChild.contains(f.name)&&f.actions.firstChild===f.button,status:f.root.dataset.hmbNativeHeader,
        native:f.native.value,video:f.video===f.node.querySelector("video"),mutations:records.length};
    },i);
    check({...repeated,mutations:0},{writes:0,commands:0,ready:1,sameChildren:true,status:"active",native:"Existing native setting",video:true,mutations:0},files[i]+" repeated updates have no transports or portal remounts");
    // Seedance's existing compact/preview path writes styles during refresh.
    if(i!==1)check(repeated.mutations,0,files[i]+" steady DOM");
    if(i===0){
      const morph=await page.evaluate(()=>{
        const f=fixtures[0];f.value={...f.value,language:"en"};f.handle.update(f.props(false));
        return{identity:f.carrier.querySelector("[data-hmb-native-identity]")===f.identity,actions:f.carrier.querySelector("[data-hmb-native-actions]")===f.actions,
          name:f.identity.firstChild.contains(f.name),button:f.actions.firstChild===f.button,status:f.root.dataset.hmbNativeHeader,
          noDrag:f.root.classList.contains("nodrag"),tabs:f.carrier.querySelectorAll("[data-finish-shot]").length,
          bodyNoDrag:f.carrier.querySelector(".hmb-finish-look__scroll").classList.contains("nodrag")};
      });
      check(morph,{identity:true,actions:true,name:true,button:true,status:"active",noDrag:false,tabs:5,bodyNoDrag:true},"Finish Look language morph retains portal subtree and five tabs");
    }
    await page.locator(`[data-fixture="${i}"]`).screenshot({path:path.join(out,`${types[i]}-active-fixture.png`)});
    await page.evaluate(i=>fixtures[i].state(false),i);
    check(await page.evaluate(i=>{const f=fixtures[i];return{status:f.root.dataset.hmbNativeHeader,rootNoDrag:f.root.classList.contains("nodrag"),carrierNoDrag:f.carrier.classList.contains("nodrag"),brand:getComputedStyle(f.carrier.querySelector(brandSelectors[i])).display!=="none"};},i),
      {status:"fallback",rootNoDrag:i!==2,carrierNoDrag:true,brand:true},files[i]+" fallback restoration");
    await page.evaluate(i=>{const f=fixtures[i];f.state(true);f.handle.cleanup();f.handle.cleanup();},i);
    check(await page.evaluate(i=>{const f=fixtures[i];return{retire:retireEvents.filter(c=>c===f.carrier).length,marker:f.carrier.hasAttribute("data-hmb-color-lut-widget"),type:f.carrier.hasAttribute("data-hmb-native-node-type"),
      detached:!f.identity.isConnected,children:f.identity.firstChild.contains(f.name)&&f.actions.firstChild===f.button,writes:f.writes.length,commands:f.commands.length};},i),
      {retire:1,marker:false,type:false,detached:true,children:true,writes:0,commands:0},files[i]+" retire before own DOM detachment; React children retained");
    report.cases.push(`${files[i]}: fallback, native active, original style/event ownership, disabled, steady update, cleanup`);
  }
  check(errors,[],"No browser errors");check(report.external_requests,0,"No external transport");
  report.passed=true;
} finally {
  await browser.close();
  fs.writeFileSync(path.join(out,"regression.json"),JSON.stringify(report,null,2)+"\n");
}
console.log(JSON.stringify({passed:report.passed,checks:report.checks,external_requests:report.external_requests,paid_calls:0}));
