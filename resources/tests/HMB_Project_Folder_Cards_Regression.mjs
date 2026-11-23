import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {nativeTestPlaywright,nativeTestBrowserPath} from "./_hmb_native_editor_fixture.mjs";

const sources = ["HMBImageAssetLibraryWidget", "HMBSoundLibraryWidget"].map(name =>
  fs.readFileSync(new URL("../../widgets/" + name + ".js",import.meta.url), "utf8"));
assert.equal(...sources.map(source=>source.split("// End standalone project folder dialog.")[0]));
const imageWidget = await import("data:text/javascript;base64," + Buffer.from(sources[0]).toString("base64"));
const exampleSite = "site-" + "a".repeat(32);
const settings = {site_settings:{write_site_id:exampleSite,revision:"current"}};
const baseAsset = {asset_library_id:"source",source_kind:"project",relative_path:"CH/Hero.png",asset_id:"Hero",registered:false};
const vendorAsset = {...baseAsset,relative_path:"site:" + exampleSite + "/CH/Hero.png"};
assert.equal(imageWidget.hmbImageAssetCanRegister(baseAsset, settings), false);
assert.equal(imageWidget.hmbImageAssetCanRegister(vendorAsset, {}), false);
assert.equal(imageWidget.hmbImageAssetCanRegister(vendorAsset, settings), true);
assert.equal(imageWidget.hmbImageAssetCanRegister({...vendorAsset,registered:true}, settings), false);
assert.equal(imageWidget.hmbCreateImageAssetRegistrationDraft(vendorAsset, {}, settings).site_settings_revision, "current");
assert.equal(imageWidget.hmbImageAssetCanRegister({...baseAsset,source_kind:"user",import_index:1}, settings), true);
const browser = await nativeTestPlaywright().chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
const errors=[];
try {
  for (const [index,media] of ["image","sound"].entries()) {
    const page=await browser.newPage({viewport:{width:1240,height:900}});
    page.setDefaultTimeout(6000); page.on("pageerror", error=>errors.push(error.message));
    await page.setContent('<style>body{background:#0e1420}main{width:1150px}#widget{height:770px}</style><main class="react-flow__node selected" data-id="Asset Library"><div id="widget"></div><div data-parameter-name="HMB_SITE_FOLDER_DRAFT"><button type="button" class="border-l"><svg class="lucide-folder"></svg></button><button title="Open in Explorer">Reveal</button><input></div></main>');
    await page.evaluate(async({src,media})=>{
      const mod=await import(src), image=media==="image",folder=image?"Ai_Ct_image":"Ai_Ct_audio";
      const ids=["site-"+"a".repeat(32),"site-"+"b".repeat(32)];
      const project=id=>"P:/projects/"+id+"/"+folder;
      const f=window.fixture={calls:[],files:[],native:0,profiles:{},media,id:"superwings12"};
      for (const id of ["superwings12","Katuri8"]) f.profiles[id]={revision:"r0",links:[],write_site_id:"hq",base_root:project(id)};
      let state={schema:image?"hmb-image-asset-library-state":"hmb-sound-library-ui",version:1,revision:0,project_id:"superwings12",project_uid:"superwings12",project_root:project("superwings12"),
        edit_transport_schema:"hmb-image-asset-edit-v1",manifest_signature:"manifest",folder_signature:"folders",catalog_root:"P:/projects",
        projects:["superwings12","Katuri8"].map(id=>({name:id,project_uid:id,project_id:id,path:project(id),project_root:project(id)})),
        shot:{shot_uuid:"shot-id",channel_uuid:"channel-id"},shot_catalog:{channel_uuid:"channel-id",shots:[{shot_uuid:"shot-id",number:1,name:"Shot 1"}]},
        assets:[],folders:[],tracks:[],site_settings:f.profiles.superwings12,language:"ko"};
      if(image)state=mod.hmbNormalizeImageAssetState(state);
      else { state.site_projects=state.projects; state.projects=state.projects.slice(0,1); }
      const update=(extra={})=>{
        state={...state,...extra,revision:(state.revision||0)+1,scan_revision:(state.scan_revision||0)+1,ui_edit_revision:(state.ui_edit_revision||0)+1};
        f.ctrl.update({value:state,onChange});
      };
      function onChange(wire){
        const payload=typeof wire==="string"?JSON.parse(wire):wire, cmd=payload.__hmb_sound_command;
        const req=cmd?.site_settings_request||payload.edits?.site_settings_request||payload.site_settings_request;
        if(!req)return;
        if(req.action==="save"&&f.hold){f.hold=false;return;}
        f.calls.push(structuredClone(req));
        const id=req.project_uid,profile=f.profiles[id],active=f.profiles.superwings12;
        if(req.action==="save"){
          if(req.expected_revision!==profile.revision)throw new Error("Missing or stale profile revision");
          const newLink=req.links.find(link=>link.id.startsWith("new-")),newId=ids.find(v=>!profile.links.some(link=>link.id===v));
          profile.links=req.links.map(link=>link===newLink?{...link,id:newId}:link);
          profile.write_site_id=req.write_site_id===newLink?.id?newId:req.write_site_id;
          profile.revision="r"+f.calls.length;
        }
        const receipt={request_id:req.request_id,project_uid:id,ok:true,...profile};
        setTimeout(()=>update({site_settings:structuredClone(active),site_settings_result:structuredClone(receipt),ack_command_id:cmd?.id||""}),10);
      }
      f.ctrl=mod.default(document.querySelector("#widget"),{value:state,onChange});
      document.querySelector(".border-l").onclick=()=>{f.native++;if(!f.nextPath)return;const path=f.nextPath;f.nextPath="";setTimeout(()=>update({site_picker_draft:{token:"native-"+f.native,project_uid:state.project_uid,path}}),10);};
    },{src:"data:text/javascript;base64,"+Buffer.from(sources[index]).toString("base64"),media});
    const button=page.getByRole("button",{name:"프로젝트 Add",exact:true}),dialog=page.getByRole("dialog",{name:"프로젝트 Add"});
    await button.click(); const cards=dialog.locator("[data-pf-site]"),add=dialog.locator("[data-pf-add]"),remove=dialog.locator("[data-pf-remove]");
    await add.waitFor();await page.waitForFunction(()=>!document.querySelector("[data-pf-add]")?.disabled);
    assert.equal(await cards.count(),1);assert.equal(await remove.isDisabled(),true);
    assert.deepEqual(await dialog.locator("footer button").allTextContents(),["추가","삭제"]);
    assert.deepEqual(await dialog.locator("select option").allTextContents(),["superwings12","Katuri8"]);
    const root=media==="image"?"Ai_Ct_image":"Ai_Ct_audio";
    await page.evaluate(root=>{fixture.nextPath="P:/projects/superwings12/"+root+"_Gang";},root);
    await add.click();await page.waitForFunction(()=>document.querySelectorAll("[data-pf-site]").length===2);
    assert.equal(await page.evaluate(()=>fixture.native),1);
    const first=cards.filter({hasText:root+"_Gang"});
    if(media==="image"){assert.equal(await first.getAttribute("aria-pressed"),"true");}
    await add.click();await dialog.locator("[data-pf-path]").fill("//studio/share/"+root+"_Two");await add.click();
    await page.waitForFunction(()=>document.querySelectorAll("[data-pf-site]").length===3);
    assert.equal(await first.count(),1);
    const screenshot=process.env.HMB_PROJECT_FOLDER_UI_SCREENSHOT_DIR;
    if(screenshot){fs.mkdirSync(screenshot,{recursive:true});await dialog.screenshot({path:path.join(screenshot,media+"-project-folders.png")});}
    await dialog.locator("select").selectOption("Katuri8");await page.waitForFunction(()=>!document.querySelector("[data-pf-add]")?.disabled);
    assert.equal(await cards.count(),1);assert.equal(await cards.first().getAttribute("title"),"P:/projects/Katuri8/"+root);
    await dialog.locator("select").selectOption("superwings12");await page.waitForFunction(()=>document.querySelectorAll("[data-pf-site]").length===3);
    await first.click(); await page.waitForFunction(()=>!document.querySelector("[data-pf-remove]")?.disabled);
    await remove.click();await page.waitForFunction(()=>document.querySelectorAll("[data-pf-site]").length===2);
    assert.equal(await first.count(),0);assert.ok((await cards.allTextContents()).some(name=>name.includes("_Two")));
    await dialog.locator("[data-pf-close]").click();
    await button.click(); await page.waitForFunction(()=>document.querySelectorAll("[data-pf-site]").length===2);
    const snapshots=await page.evaluate(()=>({calls:fixture.calls,profiles:fixture.profiles}));assert.equal(snapshots.profiles.Katuri8.revision,"r0");
    assert.equal(snapshots.profiles.superwings12.links.length,1);assert.equal(snapshots.profiles.superwings12.write_site_id,"hq");
    assert.equal(snapshots.calls.filter(command=>command.action==="save").length,media==="image"?4:3);
    assert.ok(snapshots.calls.filter(command=>command.action==="save").every(command=>command.expected_revision));
    await page.close();console.log(media+": header, base, two simultaneous links, native picker, UNC path, project switching, destination, unlink, reopen PASS");
  }
  assert.deepEqual(errors,[]);
}finally{await browser.close();}
