import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {nativeTestPlaywright,nativeTestBrowserPath} from "./_hmb_native_editor_fixture.mjs";

const sources = ["HMBImageAssetLibraryWidget", "HMBSoundLibraryWidget"].map(name => {
  const relative="widgets/"+name+".js";
  const filename=process.env.HMB_PROJECT_FOLDER_INSTALL_DIR
    ? path.join(process.env.HMB_PROJECT_FOLDER_INSTALL_DIR,relative)
    : new URL("../../"+relative,import.meta.url);
  return fs.readFileSync(filename,"utf8");
});
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
const imported = {...baseAsset,source_kind:"user",import_index:1};
const defaultDraft = imageWidget.hmbCreateImageAssetRegistrationDraft(imported,{},settings);
assert.equal(defaultDraft.target_folder,"site:"+exampleSite+"/add");
assert.equal(defaultDraft.target_folder_confirmed,true);
assert.equal(imageWidget.hmbCreateImageAssetRegistrationDraft(vendorAsset,{},settings).target_folder,"site:"+exampleSite+"/CH");
assert.equal(imageWidget.hmbCreateImageAssetRegistrationDraft(imported,{},{}).target_folder,"add");
assert.equal(imageWidget.hmbCreateImageAssetRegistrationDraft(imported,{},{}).target_folder_confirmed,true);
const browser = await nativeTestPlaywright().chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
const errors=[];
// Use the local/CI editor stylesheet when available; the fallback is its exact Desktop reset.
const editorCSSPath=process.env.HMB_PROJECT_FOLDER_EDITOR_CSS||process.env.HMB_NATIVE_HEADER_EDITOR_CSS;
const hostCSS=editorCSSPath
  ? fs.readFileSync(editorCSSPath,"utf8")
  : "@layer base{*,:after,:before,::backdrop{box-sizing:border-box;border:0 solid;margin:0;padding:0}}";
async function assertCentered(dialog) {
  const bounds=await dialog.evaluate(el=>{
    const rect=el.getBoundingClientRect();
    return {x:rect.left+rect.width/2, y:rect.top+rect.height/2, screenX:innerWidth/2, screenY:innerHeight/2};
  });
  assert.ok(Math.abs(bounds.x-bounds.screenX)<=1 && Math.abs(bounds.y-bounds.screenY)<=1,
    "Project dialog must be centered inside the Desktop viewport: "+JSON.stringify(bounds));
}
try {
  for (const [index,media] of ["image","sound"].entries()) {
    const page=await browser.newPage({viewport:{width:1240,height:900}});
    page.setDefaultTimeout(6000); page.on("pageerror", error=>errors.push(error.message));
    await page.setContent('<style>body{background:#0e1420}.canvas{width:1150px;transform:translate(64px,38px) scale(.82);transform-origin:0 0}#widget{height:770px}</style><main class="canvas"><div style="width:1150px;position:relative" class="react-flow__node selected" data-id="Asset Library"><div id="widget"></div></div></main>');
    await page.addStyleTag({content:hostCSS});
    await page.evaluate(async({src,media})=>{
      const mod=await import(src), image=media==="image",folder=image?"Ai_Ct_image":"Ai_Ct_audio";
      const ids=["site-"+"a".repeat(32),"site-"+"b".repeat(32)];
      const project=id=>"P:/projects/"+id+"/"+folder;
      const lease="82b8fc99-9cb8-4a83-a41e-94d232f119d4";
      const f=window.fixture={calls:[],native:0,writes:0,otherCommands:[],profiles:{}};
      for (const id of ["superwings12","Katuri8"]) f.profiles[id]={revision:"r0",generation:0,links:[],write_site_id:"hq",selected_site_id:"",base_root:project(id)};
      // A new workflow may list catalog projects before the node has an active project or profile.
      let state={schema:image?"hmb-image-asset-library-state":"hmb-sound-library-ui",version:1,revision:0,project_id:"",project_uid:"",project_root:"",widget_runtime_lease:lease,
        edit_transport_schema:"hmb-image-asset-edit-v1",manifest_signature:"manifest",folder_signature:"folders",catalog_root:"P:/projects",
        projects:["superwings12","Katuri8"].map(id=>({name:id,project_uid:id,project_id:id,path:project(id),project_root:project(id)})),
        shot:{shot_uuid:"shot-id",channel_uuid:"channel-id"},shot_catalog:{channel_uuid:"channel-id",shots:[{shot_uuid:"shot-id",number:1,name:"Shot 1"}]},
        assets:[],folders:[],tracks:[],language:"ko"};
      if(image)state=mod.hmbNormalizeImageAssetState(state);
      const projects=state.projects;
      state.projects=[];
      if(!image)state.site_projects=[];
      const update=(extra={})=>{
        state={...state,...extra,revision:(state.revision||0)+1,scan_revision:(state.scan_revision||0)+1,ui_edit_revision:(state.ui_edit_revision||0)+1};
        f.ctrl.update({value:state,onChange});
      };
      f.deliverProjects=()=>update(image?{projects}:{site_projects:projects,projects:projects.slice(0,1)});
      f.replayProfiles=projection=>update({site_profiles:structuredClone(projection),site_settings_result:{}});
      function onChange(wire){
        const payload=typeof wire==="string"?JSON.parse(wire):wire, cmd=payload.__hmb_sound_command;
        const req=cmd?.site_settings_request||payload.edits?.site_settings_request||payload.site_settings_request;
        if(!req){f.otherCommands.push(cmd?.action||payload.action||payload.schema||"state");return;}
        f.calls.push(structuredClone(req));
        if(image && (payload.schema!=="hmb-image-asset-site-command-v1"||payload.widget_runtime_lease!==lease))
          throw new Error("Folder settings must use the live node lease with no active shot/project prerequisite");
        const id=req.project_uid,profile=f.profiles[id];
        if(!profile)throw new Error("Unknown project "+id);
        const deliver=(extra={})=>{
          const receipt={request_id:req.request_id,project_uid:id,ok:true,...structuredClone(profile),...extra};
          f.lastReceipt=receipt;
          update({site_profiles:structuredClone(f.profiles),site_settings_result:receipt,ack_command_id:cmd?.id||""});
        };
        if(req.action==="browse_add"){
          if(f.pendingPicker)throw new Error("More than one native dialog requested");
          f.native++;
          f.pendingPicker=true;
          f.finishBrowse=(chosenPath)=>{
            if(!f.pendingPicker)throw new Error("Unexpected native picker completion");
            f.pendingPicker=false;
            if(!chosenPath){deliver({cancelled:true});return;}
            const newId=ids.find(value=>!profile.links.some(link=>link.id===value));
            profile.links.push({id:newId,label:chosenPath.split(/[\\/]/).pop(),root:chosenPath});
            profile.selected_site_id=newId;
            profile.generation++;profile.revision="r"+(++f.writes);
            deliver({added_site_id:newId});
          };
          return;
        }
        if(req.action==="update_links"){
          if(req.expected_revision!==profile.revision)throw new Error("Missing or stale profile revision");
          profile.links=structuredClone(req.links);
          profile.write_site_id=req.write_site_id;
          if(!profile.links.some(link=>link.id===profile.selected_site_id))profile.selected_site_id=profile.links[0]?.id||"";
          profile.generation++;profile.revision="r"+(++f.writes);
          setTimeout(deliver,0);
          return;
        }
        if(req.action==="confirm"){
          f.confirm=(ok=true)=>{
            if(ok){
              assertSavedSelection();
              const selected=req.selected_site_id==="hq"?"":req.selected_site_id;
              if(profile.selected_site_id!==selected){
                profile.selected_site_id=selected;
                profile.generation++;f.writes++;
              }
            }
            deliver({ok,message:ok?"":"폴더 설정이 변경됐습니다."});
            f.confirm=null;
          };
          function assertSavedSelection(){
            if(req.expected_revision && req.expected_revision!==profile.revision)throw Error("Stale completion");
            if(req.selected_site_id&&req.selected_site_id!=="hq"&&!profile.links.some(link=>link.id===req.selected_site_id))throw Error("Unknown selected site");
          }
          return;
        }
        throw new Error("Dialog opening and project selection must not query or scan folders: "+req.action);
      }
      f.deliverStale=receipt=>update({site_settings_result:receipt});
      f.ctrl=mod.default(document.querySelector("#widget"),{value:state,onChange});
      f.remount=()=>{
        f.ctrl.cleanup();
        const old=document.querySelector("#widget"),fresh=old.cloneNode(false);old.replaceWith(fresh);
        state={...state,site_profiles:structuredClone(f.profiles),site_settings_result:{}};
        f.ctrl=mod.default(fresh,{value:state,onChange});
      };
    },{src:"data:text/javascript;base64,"+Buffer.from(sources[index]).toString("base64"),media});
    const button=page.getByRole("button",{name:"프로젝트 Add",exact:true}),dialog=page.getByRole("dialog",{name:"프로젝트 Add"});
    const initialCommands=await page.evaluate(()=>fixture.otherCommands.slice());
    await button.click(); await assertCentered(dialog);
    const cards=dialog.locator('[data-pf-site]:not([data-pf-site="hq"])'),add=dialog.locator("[data-pf-add]"),remove=dialog.locator("[data-pf-remove]");
    assert.equal(await add.isDisabled(),true,"An empty project catalog cannot own a registration");
    await page.evaluate(()=>fixture.deliverProjects());
    await page.waitForFunction(()=>document.querySelector("[data-pf-project]")?.options.length===2);
    assert.equal(await add.isEnabled(),true,"Add must be available before any profile or active project has arrived");
    await page.setViewportSize({width:856,height:612});
    await assertCentered(dialog);
    await page.setViewportSize({width:3356,height:1701});
    await assertCentered(dialog);
    await page.setViewportSize({width:1240,height:900});
    assert.equal(await cards.count(),0);assert.equal(await remove.isDisabled(),true);
    const done=dialog.locator("[data-pf-done]");
    assert.deepEqual(await dialog.locator("footer button").allTextContents(),["추가","삭제","완료"]);
    assert.deepEqual(await dialog.locator("select option").allTextContents(),["superwings12","Katuri8"]);
    const projects=dialog.locator("select");
    const baseCard=dialog.locator('[data-pf-site="hq"]');
    const selectedCard=dialog.locator('[data-pf-site]:not([data-pf-site="hq"])[aria-pressed="true"]');
    const baseWrite=dialog.locator('[data-pf-write-site="hq"]');
    async function checkBase() {
      assert.equal(await baseCard.count(),Number(media==="image"));
      assert.equal(await baseWrite.count(),Number(media==="image"));
      if(media==="image") assert.equal(await baseCard.textContent(),"📁기본 폴더");
    }
    await checkBase();
    assert.equal(await selectedCard.count(),0);
    await projects.selectOption("Katuri8");
    assert.equal(await add.isEnabled(),true);
    assert.deepEqual(await page.evaluate(()=>fixture.calls),[],"Opening or switching projects must not initiate work");
    assert.deepEqual(await page.evaluate(()=>fixture.otherCommands),initialCommands,"Project selection must not refresh a library");

    await add.dblclick();
    await page.waitForFunction(()=>fixture.pendingPicker===true);
    assert.equal(await page.evaluate(()=>fixture.native),1);
    const requested=await page.evaluate(()=>fixture.calls[0]);
    assert.equal(requested.action,"browse_add");
    assert.equal(requested.project_uid,"Katuri8");
    assert.ok(requested.request_id);
    assert.equal(requested.expected_revision,undefined);
    await page.evaluate(request=>{
      fixture.deliverStale({ok:true,...request,project_uid:"superwings12",...fixture.profiles.superwings12});
      fixture.deliverStale({ok:true,...request,request_id:"previous-request",...fixture.profiles.Katuri8});
    },requested);
    assert.equal(await add.isDisabled(),true,"A late receipt for a different project or request must not release the picker");
    await page.evaluate(()=>fixture.finishBrowse(null));
    await page.waitForFunction(()=>!document.querySelector("[data-pf-add]")?.disabled);
    assert.equal(await cards.count(),0);
    assert.equal(await selectedCard.count(),0);
    assert.equal(await page.evaluate(()=>fixture.writes),0);
    await projects.selectOption("superwings12");
    assert.deepEqual(await page.evaluate(()=>fixture.calls.map(x=>x.action)),["browse_add"]);
    const emptyProfiles=await page.evaluate(()=>structuredClone(fixture.profiles));
    const root=media==="image"?"Ai_Ct_image":"Ai_Ct_audio";
    await add.click();
    await page.waitForFunction(()=>fixture.pendingPicker);
    await page.evaluate(root=>fixture.finishBrowse("P:/projects/superwings12/"+root+"_Gang"),root);
    await cards.first().waitFor();
    // Host replay after remount or a duplicated receipt must never trigger another add.
    await page.evaluate(()=>fixture.deliverStale(structuredClone(fixture.lastReceipt)));
    assert.equal(await cards.count(),1);
    assert.equal(await page.evaluate(()=>fixture.writes),1);
    const first=cards.filter({hasText:root+"_Gang"});
    assert.equal(await first.getAttribute("aria-pressed"),"true","A confirmed new folder is selected immediately");
    await checkBase();
    assert.equal(await first.getAttribute("aria-pressed"),"true");
    await dialog.locator("[data-pf-close]").click();
    await page.evaluate(older=>fixture.replayProfiles(older),emptyProfiles);
    await button.click();await first.waitFor();
    assert.equal(await first.getAttribute("aria-pressed"),"true","A delayed empty snapshot after closing must not erase a confirmed Add");
    await add.click();
    await page.waitForFunction(()=>fixture.pendingPicker);
    await page.evaluate(root=>fixture.finishBrowse("//studio/share/"+root+"_Two"),root);
    await cards.nth(1).waitFor();
    assert.equal(await first.count(),1);
    const second=cards.filter({hasText:root+"_Two"});
    assert.equal(await second.getAttribute("aria-pressed"),"true");
    const screenshot=process.env.HMB_PROJECT_FOLDER_UI_SCREENSHOT_DIR;
    if(screenshot){
      fs.mkdirSync(screenshot,{recursive:true});
      await dialog.screenshot({path:path.join(screenshot,media+"-project-folders.png")});
      await page.screenshot({path:path.join(screenshot,media+"-project-folders-centered.png")});
    }
    await projects.selectOption("Katuri8");await page.waitForFunction(()=>!document.querySelector("[data-pf-add]")?.disabled);
    assert.equal(await cards.count(),0);
    await projects.selectOption("superwings12");await cards.nth(1).waitFor();
    const beforeClick=await page.evaluate(()=>fixture.writes);
    await first.click();
    assert.equal(await first.getAttribute("aria-pressed"),"true");
    assert.equal(await page.evaluate(()=>fixture.writes),beforeClick,"Clicking the card selects it without changing the Add destination");
    await done.dblclick();
    assert.equal(await done.isDisabled(),true);
    assert.equal(await dialog.isVisible(),true,"Done waits for the matching durable acknowledgement");
    const confirm=await page.evaluate(()=>fixture.calls.at(-1));
    assert.equal(confirm.action,"confirm");assert.equal(confirm.selected_site_id,await first.getAttribute("data-pf-site"));
    await page.evaluate(request=>fixture.deliverStale({...fixture.profiles.superwings12,request_id:"stale-"+request.request_id,project_uid:"superwings12",ok:true}),confirm);
    assert.equal(await dialog.isVisible(),true);assert.equal(await done.isDisabled(),true);
    await page.evaluate(()=>fixture.confirm(false));
    await page.waitForFunction(()=>!document.querySelector("[data-pf-done]")?.disabled);
    assert.match(await dialog.locator("[data-pf-status]").innerText(),/변경/);
    await done.click();
    await page.evaluate(()=>{
      const current=fixture.profiles.superwings12, req=fixture.calls.at(-1);
      const stale={...structuredClone(current),generation:current.generation+1,
        selected_site_id:req.selected_site_id,request_id:req.request_id,project_uid:req.project_uid,ok:true};
      current.generation+=2;
      fixture.replayProfiles(fixture.profiles);
      fixture.deliverStale(stale);
    });
    assert.equal(await dialog.isVisible(),true,"A stale Done receipt must not close over a newer saved selection with the same revision");
    assert.equal(await done.isEnabled(),true);
    await first.click();
    await done.click();await page.evaluate(()=>fixture.confirm());
    await dialog.waitFor({state:"detached"});
    await page.evaluate(()=>fixture.remount());
    await button.click();await first.waitFor();
    assert.equal(await first.getAttribute("aria-pressed"),"true","A fresh widget restores the selected folder from the confirmed profile");
    if(media==="image")assert.equal(await baseWrite.isChecked(),true);
    const writeSite=dialog.locator("[data-pf-write-site]");
    if (media==="image") {
      const siteId=await first.getAttribute("data-pf-site");
      await dialog.locator('[data-pf-write-site="'+siteId+'"]').click();
      await page.waitForFunction(id=>fixture.profiles.superwings12.write_site_id===id,siteId);
      await baseWrite.click();
      await page.waitForFunction(()=>fixture.profiles.superwings12.write_site_id==="hq");
      await baseCard.click();
      assert.equal(await remove.isDisabled(),true,"The baseline folder cannot be removed.");
      await first.click();
    } else assert.equal(await writeSite.count(),0);
    await page.waitForFunction(()=>!document.querySelector("[data-pf-remove]")?.disabled);
    await remove.click();await first.waitFor({state:"detached"});
    assert.equal(await first.count(),0);
    assert.equal(await second.getAttribute("aria-pressed"),"true","Removing the selected link selects the remaining linked folder");
    if(media==="image") assert.equal(await baseWrite.isChecked(),true);
    await dialog.locator("[data-pf-close]").click();
    await button.click(); await second.waitFor();
    await checkBase();
    await second.click();
    await remove.click();
    await second.waitFor({state:"detached"});
    assert.equal(await selectedCard.count(),0);
    assert.equal(await remove.isDisabled(),true);
    await page.evaluate(()=>fixture.replayProfiles({}));
    await dialog.locator("[data-pf-close]").click();await button.click();
    assert.equal(await cards.count(),0);
    await done.click();await page.evaluate(()=>fixture.confirm());await dialog.waitFor({state:"detached"});
    const snapshots=await page.evaluate(()=>({calls:fixture.calls,profiles:fixture.profiles}));assert.equal(snapshots.profiles.Katuri8.revision,"r0");
    assert.equal(snapshots.profiles.superwings12.links.length,0);assert.equal(snapshots.profiles.superwings12.write_site_id,"hq");
    assert.deepEqual(snapshots.calls.filter(command=>command.action==="browse_add").map(command=>command.project_uid),
      ["Katuri8","superwings12","superwings12"]);
    assert.equal(new Set(snapshots.calls.map(command=>command.request_id)).size,snapshots.calls.length);
    const updates=snapshots.calls.filter(command=>command.action==="update_links");
    assert.equal(updates.length,media==="image"?4:2);
    assert.ok(updates.every(command=>command.expected_revision));
    await page.close();console.log(media+": Desktop dialog centering, immediate browse without profile, cancel, project+request ownership, single confirmation, UNC, unlink and reopen PASS");
  }
  assert.deepEqual(errors,[]);
}finally{await browser.close();}
