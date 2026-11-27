// Isolate each production widget so another widget's global CSS cannot hide a missing rule.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {parseArgs} from "node:util";
import { nativeTestBrowserPath, nativeTestPlaywright } from "./_hmb_native_editor_fixture.mjs";

const {values} = parseArgs({options:{"evidence-dir":{type:"string"}, "widget-dir":{type:"string"}}});
const widgetDir = path.resolve(values["widget-dir"] || fileURLToPath(new URL("../../widgets/",import.meta.url)));
const evidenceDir = values["evidence-dir"] && path.resolve(values["evidence-dir"]);
const channel = "aaaaaaaa-1111-4111-8111-000000000001";
const publisher = "bbbbbbbb-1111-4111-8111-000000000001";
const shot = { channel_uuid: channel, shot_uuid: "cccccccc-1111-4111-8111-000000000001", number: 1, name: "Check shot", revision: 1 };
const scope = {channel_uuid: channel, shot_uuid: shot.shot_uuid};
const catalog = {schema:"hmb-shot-routing-catalog", version:1, generation:1, metadata_sha256:"a".repeat(64),
  publisher_instance_uuid:publisher, channel_uuid:channel, shots:[{shot_uuid:shot.shot_uuid,number:shot.number,name:shot.name,revision:shot.revision}]};
const managed = {shot, shot_catalog:catalog};
const flags = {verified_shots:[scope], shot_edit_locks:[]};
const samples = [
  ["ImageAsset", "HMBImageAssetLibraryWidget", {shot_routing:{...catalog, active_shot_uuid:shot.shot_uuid}, ...flags}],
  ["VideoPicker", "HMBVideoPickerLibraryWidget_v032", {runtime_instance_id:"picker", state_writer:"python",
    shot_publisher_instance_uuid:publisher, channel_uuid:channel, shot_uuid:shot.shot_uuid,
    shot_selections:[shot],picker_shots:[{workspace_uuid:shot.shot_uuid,bound_shot_uuid:shot.shot_uuid,number:1,name:shot.name}], ...flags}],
  ["Sound", "HMBSoundLibraryWidget", {...managed, ...flags}],
  ["Prompt", "HMBPromptLibraryScopedBindingWidget", {multi_shot_enabled:true, shot,
    image_asset:{enabled:true,shot_catalog_routing:catalog,shot_catalog:[shot]}},
    {shot_edit_locks:[],completed_prompt_shots:[channel+"/"+shot.shot_uuid]}],
  ["Analysis", "HMBAnalysisAgentWidget", {...scope,shots:[{...shot, applied:true}]}],
  ["Agent", "HMBAgentLibraryWidget", {schema:"hmb-agent-shot-row", version:1, shot,
    selected:true, expanded:true, status:"succeeded", stage_completed:true}],
  ["Generator", "HMBSeedanceGenerationWidget", {schema:"hmb-seedance-shot-ui", schema_version:2, ...managed,
    execution_mode:"shot",requested_mode:"shot",execution_mode_revision:1,execution_mode_state_revision:1,
    execution_mode_instance:"a".repeat(32),draft:{render_completed:true}}],
  ["Finish Look", "HMBFinishLookLibraryWidget", {shot_manager:true, ...managed, ...flags}],
  ["Color LUT", "HMBColorLUTLibraryWidget", {...managed, web_upload:{phase:"complete",published_shot:scope},status:{phase:"idle"}}],
];

const browser = await nativeTestPlaywright().chromium.launch({executablePath:nativeTestBrowserPath(), headless:true});
const failures = [];
const captures = [];
try {
  for (const [name, file, value, options = {}] of samples) {
    const page = await browser.newPage({viewport:{width:1800,height:1350}});
    try {
      await page.route("**/*", route => route.abort());
      await page.setContent('<body style="background:#0b1020"><div class="react-flow__node" style="width:1700px;height:1250px"><div id="host" style="width:100%;min-height:300px"></div></div><div class="react-flow__node"><span id="sibling" data-hmb-shot-check="true">02</span></div></body>');
      const code = fs.readFileSync(path.join(widgetDir,file+".js")).toString("base64");
      const checked = await page.evaluate(async ({code, value, options}) => {
        const {default:mount} = await import("data:text/javascript;base64,"+code);
        const host = document.getElementById("host");
        mount(host,{value,ui_options:options,onChange(){}});
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const numbers = Array.from(host.querySelectorAll('[data-hmb-shot-check="true"]'))
          .filter(el => el.getClientRects().length);
        return numbers.map(el => {
          const style = getComputedStyle(el), glyph = getComputedStyle(el,"::before");
          const box = el.getBoundingClientRect();
          const sameLine = rect => rect.width>0 && rect.height>0 &&
            Math.min(rect.bottom,box.bottom)>Math.max(rect.top,box.top);
          const labels = [];
          const text = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
          while (text.nextNode()) {
            const node = text.currentNode;
            if (!node.textContent.includes("Check shot") || node.parentElement.closest("script,style")) continue;
            let rect;
            const option = node.parentElement.closest("option");
            if (option) {
              if (!option.selected) continue;
              rect = option.closest("select")?.getBoundingClientRect();
            } else {
              const range = document.createRange();
              range.selectNodeContents(node);
              rect = range.getBoundingClientRect();
            }
            if (rect && sameLine(rect)) labels.push(rect);
          }
          for (const field of host.querySelectorAll("input")) {
            const rect=field.getBoundingClientRect();
            if (field.value.includes("Check shot") && sameLine(rect)) labels.push(rect);
          }
          const label=labels.sort((a,b)=>Math.abs(a.left-box.right)-Math.abs(b.left-box.right))[0];
          if (!label) throw new Error("no visible same-row shot name or selected control next to "+el.outerHTML);
          if (box.right>label.left+0.5) throw new Error("number overlaps or follows its shot name ("+box.right+", "+label.left+")");
          const x=Math.max(0,Math.floor(box.left)-6), y=Math.max(0,Math.floor(Math.min(box.top,label.top))-4);
          const right=Math.min(innerWidth,Math.ceil(label.right)+6,x+Math.max(350,Math.ceil(label.left-x)+200));
          const bottom=Math.min(innerHeight,Math.ceil(Math.max(box.bottom,label.bottom))+4);
          return {
            clip:{x,y,width:right-x,height:bottom-y},
            box:{width:box.width,height:box.height},
            number:el.textContent.trim(), title:el.title || el.getAttribute("aria-label"),
            glyph:glyph.content, size:glyph.fontSize, green:glyph.color,
            flex:style.display.endsWith("flex"), background:style.backgroundColor, border:style.borderTopColor,
            width:parseFloat(style.minWidth),height:parseFloat(style.minHeight), opacity:style.opacity,
          };
        });
      },{code,value,options});
      assert.equal(await page.locator("#sibling").evaluate(el => getComputedStyle(el,"::before").content),
        "none", "mounting this library changed the check style of a sibling node");
      assert.ok(checked.length,"missing visible verified shot number");
      for(const {title,clip,box,...badge} of checked){
        assert.ok(title,"checked number has no accessible completion description");
        assert.deepEqual(box, {width:38,height:30}, "the badge outline must match in every library");
        assert.deepEqual(badge,{number:"01",glyph:'"✓"',size:"20px",green:"rgb(74, 222, 128)",
          flex:true,background:"rgb(18, 48, 29)",border:"rgb(74, 222, 128)",
          width:38,height:30,opacity:"1"});
      }
      if(evidenceDir){
        captures.push({name,bytes:await page.screenshot({clip:checked[0].clip})});
      }
      console.log("PASS "+name+" "+checked.map(row=>row.box.width+"×"+row.box.height).join(", "));
    } catch(error) {
      failures.push(name+" "+error.message);
    } finally { await page.close(); }
  }
  assert.ok(!failures.length, failures.join("\n"));
  const together = await browser.newPage();
  try {
    await together.route("**/*", route => route.abort());
    const records = samples.map(([name,file,value,options={}]) => ({
      name,value,options,source:fs.readFileSync(path.join(widgetDir,file+".js")).toString("base64"),
    }));
    const result = await together.evaluate(async records => {
      const rows = [];
      const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      for (const {name,source,value,options} of records) {
        const node = document.createElement("div"), host = document.createElement("div");
        node.className = "react-flow__node"; node.dataset.id = name;
        node.append(host); document.body.append(node);
        const {default:mount} = await import("data:text/javascript;base64,"+source);
        const props = {value,ui_options:options,onChange(){}};
        rows.push({name,host,node,props,handle:mount(host,props)});
      }
      await settle();
      const badges = () => rows.filter(({host}) =>
        Array.from(host.querySelectorAll('[data-hmb-shot-check="true"]')).some(el =>
          getComputedStyle(el,"::before").content === '"✓"')).map(row => row.name);
      const mounted = badges();
      const agent = rows.find(row => row.name === "Agent");
      agent.handle.update({...agent.props,value:{...agent.props.value,stage_completed:false}});
      await settle();
      const invalidated = badges();
      agent.handle.update(agent.props);
      await settle();
      const restored = badges();
      for (const row of rows.reverse()) { row.handle?.cleanup?.(); row.node.remove(); }
      return {mounted,invalidated,restored};
    },records);
    const all = records.map(record=>record.name);
    assert.deepEqual(result.mounted,all);
    assert.deepEqual(result.invalidated,all.filter(name=>name!=="Agent"));
    assert.deepEqual(result.restored,all);
    console.log("PASS 9 widgets mounted together; invalidating and restoring Agent preserved the other 8 checks");
  } finally { await together.close(); }
  if(evidenceDir){
    fs.mkdirSync(evidenceDir,{recursive:true});
    const sheet=await browser.newPage({viewport:{width:900,height:750},deviceScaleFactor:1});
    await sheet.setContent('<style>body{margin:0;background:#0b1020;color:#e5e7eb;font:600 15px system-ui}main{width:max-content;padding:12px}section{display:grid;grid-template-columns:110px auto;align-items:center;gap:12px;padding:5px 10px;border-bottom:1px solid #293244}img{display:block}</style><main></main>');
    await sheet.evaluate(async rows=>{
      const main=document.querySelector("main");
      for(const {name,data} of rows){
        const row=document.createElement("section"), label=document.createElement("span"), image=document.createElement("img");
        label.textContent=name;image.src="data:image/png;base64,"+data;
        row.append(label,image);main.append(row);await image.decode();
      }
    },captures.map(({name,bytes})=>({name,data:bytes.toString("base64")})));
    const output=path.join(evidenceDir,"shot-number-checks.png");
    await sheet.locator("main").screenshot({path:output});
    console.log(output);
  }
} finally { await browser.close(); }
