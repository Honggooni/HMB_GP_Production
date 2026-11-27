// Production-controller upload gating, immediate invalidation and persistent UI.
// Loopback fixture only: no Broker request, provider render or media upload.
import { listenBrowserSafeLoopback } from "./_hmb_browser_loopback.mjs";
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
const manual = { ...value, shot: {}, project_id: "superwings12", manual_project: { id: "superwings12", name: "슈퍼윙즈12" },
  upload_group_status: "confirmed", upload_group: { id: "grp-fixture", name: "서울" },
  manual_episode: "e202",
  manual_project_display_name: "superwings12",
  upload_projects: [{ id: "superwings12", name: "슈퍼윙즈12", display_name: "superwings12" },
    { id: "katuri8", name: "까투리8", display_name: "Katuri8" }],
  source: { path: "C:/synthetic/11-12.mp4", name: "11-12.mp4" }, result: {} };
assert.equal(hmbColorLUTState(manual).web_upload.enabled, true, "Only with explicit server project can upload original before final export");
assert.match(hmbRenderColorLUTWidget(manual), /data-group type="text" readonly value="서울"/);
assert.match(hmbRenderColorLUTWidget({ ...manual, upload_group:{id:"grp-fixture",name:""} }), /data-group type="text" readonly value="소속 그룹 · 이름 확인 중"/);
assert.match(hmbRenderColorLUTWidget({ ...manual, upload_group_status: "unavailable" }), /data-group type="text" readonly value="그룹 조회 불가"/);
assert.match(hmbRenderColorLUTWidget({ ...manual, language: "en", upload_group_status: "unassigned" }), /data-group type="text" readonly value="Unclassified"/);
assert.match(hmbRenderColorLUTWidget({ ...manual, upload_group: {}, upload_group_status: "legacy" }), /data-group type="text" readonly value="서버 자동 배정"/);
assert.match(hmbRenderColorLUTWidget(manual), /<option value="katuri8">Katuri8<\/option>/);
assert.match(hmbRenderColorLUTWidget({ ...value, project: { name: "까투리8" }, project_id: "bound-uid",
  project_display_name: "Katuri8" }), /<option value="bound-uid">Katuri8<\/option>/);
const mybox = { ...manual, project_id: "my-box", manual_project: { id: "my-box", name: "My Box" },
  manual_episode: "",
  upload_projects: [...manual.upload_projects, { id: "my-box", name: "My Box" }] };
assert.equal(hmbColorLUTState(mybox).web_upload.enabled, true);
assert.equal(hmbColorLUTState({ ...manual, upload_projects: [] }).web_upload.enabled, false);
assert.equal(hmbColorLUTCommand("upload_web", value).action, "upload_web");
assert.match(hmbRenderColorLUTWidget(value), /data-reset[\s\S]*cl-web-upload[\s\S]*data-action="upload_web"/);
assert.match(hmbRenderColorLUTWidget(value), /data-action="upload_web" type="button" disabled/);
const localFFV1 = { ...manual, manual_project: {}, upload_projects: [],
  output: { codec: 'ffv1', manual_output_enabled: true, path: 'C:/synthetic/local-final.mkv' } };
assert.match(hmbRenderColorLUTWidget(localFFV1), /data-action="export"[^>]*aria-label="최종 영상 출력">최종 영상 출력<\/button>/);
assert.match(hmbRenderColorLUTWidget({...manual,manual_project:{},upload_projects:[]}), /data-action="export"[^>]*disabled[^>]*aria-label="최종출력 &amp; 웹 업로드">최종출력 &amp; 웹 업로드<\/button>/);

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
await listenBrowserSafeLoopback(server);
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless:true, args:["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({viewport:{width:1250,height:1000}});
  const errors=[]; page.on("pageerror", error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(()=>window.ready);
  const button=page.locator('[data-action="upload_web"]');
  assert.equal(await button.isEnabled(),true);
  const badge=page.locator('[data-lut-shot-number]');
  assert.equal(await badge.getAttribute('data-hmb-shot-check'),'false');
  const checks=await page.evaluate(()=>{
    const original=state, proof={channel_uuid:'channel-one',shot_uuid:'shot-1'};
    const marks=[];
    const view=(shot,publication,phase='complete',status='idle')=>{
      window.state={...original,revision:marks.length+1,shot,status:{phase:status},web_upload:{enabled:true,phase,published_shot:publication}};
      controller.update(props());
      const badge=document.querySelector('[data-lut-shot-number]');
      marks.push([badge.hidden,badge.textContent,badge.dataset.hmbShotCheck,getComputedStyle(badge,'::before').content]);
    };
    view(original.shot,proof);view(original.shot,{...proof,shot_uuid:'shot-2'});view(original.shot,proof,'uploading');
    view(original.shot,proof,'complete','error');view({},proof);view(original.shot,null,'ready');
    return marks;
  });
  assert.deepEqual(checks,[[false,'01','true','"✓"'],[false,'01','false','none'],[false,'01','false','none'],
    [false,'01','false','none'],[true,'','false','none'],[false,'01','false','none']]);
  const canvas=await page.locator('[data-preview]').evaluate(el => (window.originalCanvas=el,true));
  await button.click();
  assert.equal(await button.isDisabled(),true);
  assert.equal(await page.evaluate(()=>window.commands.length),1);
  assert.equal(await page.evaluate(()=>window.commands[0].action),"upload_web");
  await page.evaluate(()=>{window.state={...window.state,revision:48,web_upload:{enabled:true,phase:'unknown',reason:'상태 확인 필요'}};window.controller.update(window.props());});
  assert.equal(await button.textContent(), "업로드 상태 확인");
  await button.click();
  assert.equal(await page.evaluate(()=>window.commands.at(-1).check_only), true);
  await page.evaluate(()=>{window.state={...window.state,revision:49,web_upload:{enabled:true,phase:'absent',reason:'완료된 업로드 기록을 찾지 못했습니다.'}};window.controller.update(window.props());});
  assert.equal(await button.textContent(), "다시 업로드");
  await page.evaluate(()=>{window.state={...window.state,revision:50,web_upload:{enabled:false,phase:'complete',reason:'웹 업로드 완료'}};window.controller.update(window.props());});
  assert.equal(await button.isDisabled(),true);
  assert.match(await button.textContent(),/완료/);
  await page.evaluate(()=>{window.state={...window.state,revision:51,web_upload:{enabled:true,phase:'ready',reason:'준비됨'}};window.controller.update(window.props());});
  assert.equal(await button.isEnabled(),true);
  await page.locator('[data-adjust="exposure"]').evaluate(el=>{el.value='2';el.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await button.isDisabled(),true,"Unflushed grade edit invalidates immediately");
  await page.evaluate(()=>{window.state={...window.state,revision:100,shot:{},web_upload:{enabled:true,phase:'ready',reason:'forged Only'}};window.controller.update(window.props());});
  assert.equal(await button.isDisabled(),true,"Only stays disabled even with an enabled browser payload");
  await page.evaluate((manual) => { window.state = { ...manual, revision: 110 }; window.controller.update(window.props()); }, manual);
  assert.equal(await button.isEnabled(), true);
  const outputButton = page.locator('[data-action="export"]');
  assert.equal(await outputButton.textContent(), "최종출력 & 웹 업로드");
  await page.evaluate(() => { window.state={...window.state,revision:111,web_upload:{enabled:false,phase:'offline',reason:'브로커가 응답하지 않습니다.'}}; window.controller.update(window.props()); });
  assert.equal(await button.isDisabled(), true);
  assert.equal(await outputButton.isDisabled(), true);
  assert.equal(await page.locator('[data-export-local]').isEnabled(), true);
  await page.evaluate((manual) => { window.state={...manual,revision:112}; window.controller.update(window.props()); }, manual);
  await outputButton.click();
  assert.equal(await page.evaluate(() => window.commands.at(-1).action), "export_upload");
  for (const [index, language] of ['ko','en'].entries()) {
    await page.evaluate(({manual,language,revision})=>{window.state={...manual,language,revision};window.controller.update(window.props());},
      {manual,language,revision:112+index});
    assert.equal(await outputButton.textContent(),language==='ko'?'최종출력 & 웹 업로드':'Final export & web upload');
    for (const width of [430, 760, 1185, 1800]) {
      await page.locator('#widget').evaluate((el, width) => el.style.width = `${width}px`, width);
      const boxes = await page.locator('.cl-project').evaluate(panel =>
        [...panel.querySelectorAll('[data-group], [data-project], [data-episode]')].map(el => {
          const {width,top,right,left}=el.getBoundingClientRect();
          return {width,top,right,left};
        }));
      const [groupBox,projectBox,episodeBox]=boxes;
      assert.ok(Math.abs(groupBox.width-episodeBox.width)<1 && Math.abs(2*groupBox.width-projectBox.width)<1,
        `Group/project/episode keep the 25/50/25 proportions at ${width}/${language}`);
      assert.ok(Math.abs(groupBox.top-projectBox.top)<1 && Math.abs(projectBox.top-episodeBox.top)<1 &&
        groupBox.right<projectBox.left && projectBox.right<episodeBox.left, 'Destination fields follow reading order on one row');
      const fit = await outputButton.evaluate(el => ({ width: el.clientWidth, content: el.scrollWidth, wrap: getComputedStyle(el).whiteSpace,
        outerWidth:el.getBoundingClientRect().width,paddingLeft:getComputedStyle(el).paddingLeft,paddingRight:getComputedStyle(el).paddingRight,
        right:el.getBoundingClientRect().right,rowRight:el.closest('.cl-output-controls').getBoundingClientRect().right }));
      assert.equal(fit.content <= fit.width, true, `Long output label fits at ${width}/${language}`);
      assert.ok(fit.right<=fit.rowRight+1,`Output action stays inside its row at ${width}/${language}`);
      assert.ok(fit.outerWidth>=180,`Final output action preserves the approved wider button at ${width}/${language}`);
      assert.equal(fit.paddingLeft,'20px');assert.equal(fit.paddingRight,'20px');
      assert.equal(fit.wrap, 'nowrap');
    }
  }
  await page.evaluate(manual=>{window.state={...manual,manual_project:{},upload_projects:[],revision:115};window.controller.update(window.props());},manual);
  assert.equal(await outputButton.textContent(),'최종출력 & 웹 업로드','Missing destination never silently changes a web-compatible action to local-only export');
  assert.equal(await outputButton.isDisabled(),true);
  const count=await page.evaluate(()=>window.commands.length);
  await outputButton.dispatchEvent('click');
  assert.equal(await page.evaluate(()=>window.commands.length),count,'Disabled/programmatic click cannot submit a different local export');
  await page.evaluate(local=>{window.state={...local,revision:116};window.controller.update(window.props());},localFFV1);
  assert.equal(await outputButton.textContent(),'최종 영상 출력');
  assert.equal(await outputButton.isEnabled(),true,'FFV1 remains a local export without a project');
  assert.match(await outputButton.getAttribute('title'),/FFV1.*로컬.*무손실/);
  await outputButton.click();
  assert.deepEqual(await page.evaluate(()=>{const command=window.commands.at(-1);return {action:command.action,output:command.state.output,source:command.state.source.path};}),
    {action:'export',output:localFFV1.output,source:localFFV1.source.path},'FFV1 keeps the local export action, authored path and source');
  await page.evaluate(local=>{window.state={...local,language:'en',revision:118};window.controller.update(window.props());},localFFV1);
  assert.equal(await outputButton.textContent(),'Export final video');
  assert.match(await outputButton.getAttribute('title'),/FFV1.*lossless.*locally/);
  await page.evaluate(manual=>{window.state={...manual,revision:119};window.controller.update(window.props());},manual);
  if (process.env.HMB_LUT_UPLOAD_UI_CAPTURE) {
    await page.locator('#widget').evaluate(el => el.style.width = '760px');
    await page.locator('.cl-output').screenshot({path:process.env.HMB_LUT_UPLOAD_UI_CAPTURE});
  }
  assert.equal(await page.locator('[data-project]').isEnabled(), true);
  const group = page.getByRole('textbox', {name:'그룹',exact:true});
  assert.equal(await group.inputValue(), '서울');
  assert.equal(await group.isEditable(), false);
  assert.equal(await page.locator('[data-source]').textContent(), "11-12.mp4");
  await page.locator('[data-project]').selectOption("katuri8");
  const selection = await page.evaluate(() => window.commands.filter(c => c.action === 'select_upload_project').at(-1));
  assert.equal(selection.project_id, "katuri8");
  assert.equal(selection.state.source.path, manual.source.path);
  assert.equal(await button.isDisabled(), true, "Destination change requires fresh server readiness");
  await page.evaluate((manual) => { window.state = { ...manual, revision: 120, project_id: 'katuri8', manual_project: { id: 'katuri8', name: '까투리8' }, manual_episode: '' }; window.controller.update(window.props()); }, manual);
  assert.equal(await button.isVisible(), false);
  assert.equal(await outputButton.isVisible(), false);
  await page.evaluate(() => {
    window.state = { ...window.state, revision: 126, upload_episodes: ['e201', 'e203'] };
    window.controller.update(window.props());
  });
  const episode = page.locator('[data-episode]');
  assert.equal(await episode.isEnabled(), true);
  assert.deepEqual(await episode.locator('option').evaluateAll(rows => rows.slice(1).map(row => row.value)), ['e201','e203']);
  await episode.selectOption('e203');
  assert.equal(await page.evaluate(() => window.commands.findLast(c => c.action === 'select_upload_episode')?.episode), 'e203');
  await page.evaluate(() => {
    window.state = { ...window.state, revision: 128, manual_episode: 'e203' };
    window.controller.update(window.props());
  });
  assert.equal(await episode.inputValue(), 'e203');
  assert.equal(await button.isVisible(), true);
  assert.equal(await outputButton.isVisible(), true);
  await button.click();
  assert.equal(await page.evaluate(() => window.commands.filter(c => c.action === 'upload_web' && !c.check_only).length), 2);
  assert.equal(await episode.evaluate(el => el.tagName), 'SELECT');
  assert.equal(await page.locator('[data-episode-choice], [data-profile-name], [data-apply-profile], [data-action="save_profile"], [data-action="delete_profile"]').count(), 0);
  await page.evaluate(() => {
    window.state = { ...window.state, revision: 129, upload_episodes: ['e201'], upload_episodes_status: 'partial' };
    window.controller.update(window.props());
  });
  assert.equal(await episode.inputValue(), 'e203', "An incomplete list preserves a saved episode");
  await episode.selectOption('e201');
  assert.deepEqual(await page.evaluate(() => {
    const {action, project_id, episode} = window.commands.findLast(c => c.action === 'select_upload_episode');
    return {action, project_id, episode};
  }), {action:'select_upload_episode', project_id:'katuri8', episode:'e201'});
  await page.evaluate((mybox) => { window.state = { ...mybox, revision: 130 }; window.controller.update(window.props()); }, mybox);
  assert.equal(await page.locator('[data-project]').inputValue(), 'my-box');
  assert.equal(await group.inputValue(), '개인');
  assert.equal(await episode.isDisabled(), true);
  assert.equal(await page.locator('[data-project] option').allTextContents().then(rows => rows.includes('My Box')), true);
  assert.equal(await button.isEnabled(), true);
  await page.evaluate((value) => { window.state = { ...value, upload_group_status:'confirmed', upload_group:{id:'grp-other',name:'광주'}, revision: 150 }; window.controller.update(window.props()); }, value);
  assert.equal(await group.inputValue(), '광주');
  assert.equal(await page.locator('[data-project]').isDisabled(), true, "Bound destination remains automatic");
  assert.equal(await episode.isDisabled(), true);
  const admin = {...manual, upload_group_selectable:true, upload_group_status:'unassigned',
    upload_groups:[{id:'ungrouped',name:''},{id:'grp-seoul',name:'서울'},{id:'grp-gwangju',name:'광주'}], upload_group:{id:'ungrouped',name:''}};
  const owner = 'a'.repeat(64);
  const restored = hmbColorLUTState({...admin,manual_group_id:'grp-seoul',manual_group_owner:owner});
  assert.equal(restored.manual_group_id,'grp-seoul');
  assert.equal(restored.manual_group_owner,owner,'Account-scoped group restoration survives widget round-trips');
  await page.evaluate(data=>{window.state={...data,revision:160};window.controller.update(window.props());},admin);
  const groups = page.getByRole('combobox',{name:'그룹',exact:true});
  assert.deepEqual(await groups.locator('option').allTextContents(),['미분류','서울','광주']);
  assert.equal(await groups.inputValue(),'ungrouped');
  assert.equal(await button.isEnabled(),true);
  await groups.selectOption('grp-seoul');
  assert.equal(await page.evaluate(()=>window.commands.at(-1).group_id),'grp-seoul');
  assert.equal(await page.evaluate(()=>window.commands.at(-1).action),'select_upload_group');
  assert.equal(await button.isVisible(),false,'Changing groups immediately retires the previous destination');
  await page.evaluate(admin=>{window.state={...admin,revision:164,upload_group_status:'confirmed',upload_group:{id:'grp-seoul',name:'서울'},
    upload_destination_readonly:true};window.controller.update(window.props());},admin);
  assert.equal(await groups.inputValue(),'grp-seoul');
  assert.equal(await button.isDisabled(),true);
  assert.equal(await outputButton.isDisabled(),true);
  assert.match(await page.locator('[data-upload-reason]').textContent(),/조회 전용/);
  const sent=await page.evaluate(()=>window.commands.length);
  await button.dispatchEvent('click');await outputButton.dispatchEvent('click');
  assert.equal(await page.evaluate(()=>window.commands.length),sent);
  await page.locator('[data-project]').selectOption('katuri8');
  assert.equal(await page.evaluate(()=>window.commands.at(-1).group_id),'grp-seoul');
  await page.evaluate(()=>{window.state={...window.state,revision:167,manual_episode:'',upload_episodes:['e202']};window.controller.update(window.props());});
  await episode.selectOption('e202');
  assert.equal(await page.evaluate(()=>window.commands.at(-1).group_id),'grp-seoul');
  for (const [index, [control, action]] of [[button,'upload_web'], [outputButton,'export_upload']].entries()) {
    await page.evaluate(({admin, index}) => {
      window.state = {...admin, revision:168+index, upload_group:{id:'grp-seoul',name:'서울'},
        upload_destination_readonly:false, manual_group_id:'grp-seoul', manual_project:{id:'katuri8',name:'까투리8'},
        project_id:'katuri8', upload_episodes:['e202'], manual_episode:'e202'};
      window.controller.update(window.props());
    }, {admin,index});
    assert.equal(await control.isEnabled(),true);
    await control.click();
    const destination = await page.evaluate(() => {
      const command = window.commands.at(-1);
      const state = command.state;
      return [command.action, state.upload_group.id, state.manual_project.id, state.manual_episode];
    });
    assert.deepEqual(destination,[action,'grp-seoul','katuri8','e202']);
  }
  await page.evaluate(({admin,mybox})=>{window.state={...admin,...mybox,revision:170,upload_group_selectable:true,upload_destination_readonly:true};window.controller.update(window.props());},{admin,mybox});
  assert.equal(await group.inputValue(),'개인');
  assert.equal(await button.isEnabled(),true,'My Box stays private and writable');
  assert.equal(await outputButton.isEnabled(),true);
  // Native select changes must repaint the action before any host echo.
  await page.evaluate(local=>{window.state={...local,output:{...local.output,codec:'hevc10'},revision:200};window.controller.update(window.props());},localFFV1);
  assert.equal(await outputButton.isDisabled(),true);
  const codec=page.locator('[data-codec]');
  await codec.selectOption('ffv1');
  assert.equal(await outputButton.textContent(),'최종 영상 출력');
  assert.equal(await outputButton.isEnabled(),true,'FFV1 selection updates the local action immediately, without host.update');
  await outputButton.click();
  assert.equal(await page.evaluate(()=>window.commands.at(-1).action),'export');
  await codec.selectOption('hevc10');
  assert.equal(await outputButton.textContent(),'최종출력 & 웹 업로드');
  assert.equal(await outputButton.isDisabled(),true,'HEVC selection immediately restores missing-project gating');
  await codec.selectOption('prores');
  assert.equal(await outputButton.textContent(),'최종출력 & 웹 업로드');
  assert.equal(await outputButton.isDisabled(),true);
  await page.evaluate(manual=>{window.state={...manual,revision:220};window.controller.update(window.props());},manual);
  await codec.selectOption('ffv1');
  assert.equal(await outputButton.textContent(),'최종 영상 출력');
  await codec.selectOption('hevc10');
  assert.equal(await outputButton.textContent(),'최종출력 & 웹 업로드');
  assert.equal(await outputButton.isEnabled(),true,'HEVC immediately keeps the selected project');
  await outputButton.click();
  assert.equal(await page.evaluate(()=>window.commands.at(-1).action),'export_upload');
  await codec.selectOption('prores');
  await outputButton.click();
  assert.equal(await page.evaluate(()=>window.commands.at(-1).action),'export_upload');
  assert.equal(await page.locator('[data-preview]').evaluate(el=>el===window.originalCanvas),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:"PASS",boundAutomaticProject:true,onlyExplicitProject:true,filenamePreserved:true,oneClickOneCommand:true,immediateGradeInvalidation:true,immediateCodecSwitchWithoutHostEcho:true,completedDisabled:true,webExportLabelFixed:true,localFFV1Preserved:true,retainedCanvas:true,realBrowser:true}));
} finally { if(browser)await browser.close();await new Promise(resolve=>server.close(resolve)); }
