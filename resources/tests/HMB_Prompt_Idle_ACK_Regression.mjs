// Actual widget with synthetic delayed source ACKs in isolated Chromium.
// No live editor, engine, source media, provider or paid generation is used.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
let chromium;
try { ({chromium}=require('playwright')); }
catch { ({chromium}=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'))); }
const source = fs.readFileSync(process.env.HMB_PROMPT_ACK_SOURCE || new URL('../../widgets/HMBPromptLibraryScopedBindingWidget.js',import.meta.url),'utf8');
const server=http.createServer((req,res)=>{
  res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');
  res.end(req.url==='/widget.js'?source+'\nexport { hmbCopyPromptElementAttributes };':
    '<style>body{margin:0}.react-flow__node{width:1600px;height:1450px;position:relative}#host{height:1300px}</style><div class="react-flow__node" data-id="Synthetic Prompt"><div id="host"></div></div>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,executablePath:process.env.HMB_PROMPT_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try {
  const page=await browser.newPage({viewport:{width:1800,height:1700}});
  const errors=[];page.on('pageerror',e=>errors.push(e.stack||e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const result=await page.evaluate(async()=>{
    const w=await import('/widget.js');
    const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const wait=ms=>new Promise(r=>setTimeout(r,ms));
    const check=(ok,message)=>{if(!ok)throw Error(message);};
    const shots=Array.from({length:5},(_,i)=>({shot_uuid:`shot-${i+1}`,channel_uuid:'channel',name:`shot_${i+1}`,number:i+1,selected_source_uids:[]}));
    let latest=w.normalizeState({multi_shot_enabled:true,shot:shots[0],image_asset:{shot_catalog:shots,shot_catalog_routing:{publisher_instance_uuid:'publisher',channel_uuid:'channel',generation:1,metadata_sha256:'a'.repeat(64)}}});
    const key=Object.keys(latest.text)[0],expected=new Map();
    for(const shot of shots){
      w.hmbSwitchPromptShot(latest,shot.shot_uuid);
      latest.text[key]=`샷 ${shot.number} {literal} OFF 0`;
      latest.images[0].label=`image_${shot.number}`;
      latest.videos[0].keep_out=`keep_${shot.number}`;
      expected.set(shot.shot_uuid,latest.text[key]);w.hmbStorePromptShotDocument(latest);
    }
    w.hmbSwitchPromptShot(latest,shots[0].shot_uuid);
    latest.source_sync_revision=1007;latest.ui_edit_revision=1002;
    const host=document.querySelector('#host'),publications=[],timers=new Set();
    let controller,disposed=false;
    const deliver=(state,delay=5)=>{
      const timer=setTimeout(()=>{timers.delete(timer);if(disposed)return;latest=state;controller.update(props(latest));},delay);timers.add(timer);
    };
    const props=value=>({value:JSON.stringify(value),disabled:false,onChange(raw){
      const incoming=JSON.parse(raw);publications.push({source:incoming.source_sync_revision,ui:incoming.ui_edit_revision,shot:incoming.shot.shot_uuid,text:incoming.text[key]});
      if(publications.length>24)throw Error('Idle ACK loop reproduced');
      // This deliberately models a host source correction following every UI
      // publication. The equal acknowledged UI generation must end the cycle.
      deliver({...incoming,source_sync_revision:incoming.source_sync_revision+1});
    }});
    controller=w.default(host,props(latest));await frame();await frame();
    const select=async index=>{host.querySelector(`[data-prompt-shot="${shots[index].shot_uuid}"]`).click();await frame();await frame();};

    await select(1);await wait(1150);
    check(publications.length===1,`Source ACK self-published ${publications.length} times`);
    check(latest.ui_edit_revision===1003,'One user page move must advance UI only once');
    const stable=JSON.stringify(latest);await wait(550);check(JSON.stringify(latest)===stable,'Idle clocks/state changed after ACK');

    // New source at the SAME UI generation while text is still unsubmitted
    // must retain the draft and publish the real edit exactly once.
    const field=host.querySelector(`[data-text-key="${key}"]`);
    field.focus();field.value='새 실제 입력 {literal} OFF';field.dispatchEvent(new Event('input',{bubbles:true}));
    const beforeEdit=publications.length,oldUi=latest.ui_edit_revision;
    deliver({...latest,source_sync_revision:latest.source_sync_revision+1,text:{...latest.text,[key]:'source must not replace local text'}});
    await wait(1150);
    check(publications.length===beforeEdit+1,'Pending authored text caused multiple or missing publications');
    check(latest.text[key]===field.value && latest.text[key]==='새 실제 입력 {literal} OFF','Concurrent source erased the real draft');
    check(latest.ui_edit_revision===oldUi+1,'Real text edit must own one new UI generation');
    expected.set(shots[1].shot_uuid,latest.text[key]);

    // A genuinely crossed source/older-UI snapshot still merges, but repair
    // does not invent another authored UI generation or perpetuate the ACK.
    const beforeMerge=publications.length,mergeUi=latest.ui_edit_revision;
    deliver({...latest,source_sync_revision:latest.source_sync_revision+1,ui_edit_revision:mergeUi-1,
      text:{...latest.text,[key]:'stale crossed text'}});
    await wait(1150);
    check(publications.length===beforeMerge+1,'Crossed merge did not settle after one repair');
    check(latest.ui_edit_revision===mergeUi,'Automatic repair advanced authored UI revision');
    check(latest.text[key]===expected.get(shots[1].shot_uuid),'Crossed source restored stale text');
    const mergedStable=JSON.stringify(latest);await wait(550);check(JSON.stringify(latest)===mergedStable,'Merged clocks did not become idle');

    // A pending automatic repair is not a new dirty draft. A newer correct
    // source ACK arriving before its debounce cancels that obsolete repair.
    const beforeSuperseded=publications.length,ackUi=latest.ui_edit_revision;
    const good={...latest,source_sync_revision:latest.source_sync_revision+2};
    deliver({...latest,source_sync_revision:latest.source_sync_revision+1,ui_edit_revision:ackUi-1});
    deliver(good,45);await wait(600);
    check(publications.length===beforeSuperseded,'An acknowledged automatic repair remained dirty and re-published');
    check(latest.ui_edit_revision===ackUi,'A superseded repair invented a user edit');

    const synthetic={querySelector(){return null;},querySelectorAll(){return [];},contains(){return false;}},dedup=[];
    const repair=w.normalizeState({source_sync_revision:51,ui_edit_revision:32,text:{[key]:'exact blank/OFF 0'}});
    const sink={onChange(value){dedup.push(JSON.parse(value));}};
    w.hmbEmitLocalPromptState(synthetic,sink,repair,null,{reconcileOnly:true});
    w.hmbEmitLocalPromptState(synthetic,sink,repair,null,{reconcileOnly:true});
    check(dedup.length===1 && dedup[0].ui_edit_revision===32,'The same automatic repair was submitted twice or increased UI clock');
    w.hmbEmitLocalPromptState(synthetic,sink,repair);
    check(dedup.length===2 && dedup[1].ui_edit_revision===33,'Repair dedup suppressed a later real user edit');
    clearTimeout(synthetic.__hmbPromptPendingLocalTimer);

    // Every inactive saved document and visible prepared control is retained.
    for(const index of [4,0,3,2,1,0,4,2,3,1]){
      await select(index);await wait(15);
      check(host.querySelector(`[data-text-key="${key}"]`).value===expected.get(shots[index].shot_uuid),`Five-shot literal text was lost: ${index+1} actual=${host.querySelector(`[data-text-key="${key}"]`).value} expected=${expected.get(shots[index].shot_uuid)} history=${JSON.stringify(publications)}`);
      check(latest.images[0].label===`image_${index+1}`,'Per-shot image label changed');
      check(latest.videos[0].keep_out===`keep_${index+1}`,'Per-shot OFF/keep-out changed');
    }
    check(Object.keys(latest.shot_documents).filter(k=>k.startsWith('channel/')).length===5,'Saved five-document map changed');

    // Imperative sizing/isolation attributes are owned independently from the
    // authoring template; a morph must not remove and recreate them.
    const root=host.querySelector('.hmb-dashboard'),clip=host.querySelector('.hmb-dashboard-clip');
    const rootStyle=root.getAttribute('style'),clipStyle=clip.getAttribute('style');
    const staged=document.createElement('div');staged.className=root.className;
    w.hmbCopyPromptElementAttributes(root,staged,true);
    check(root.getAttribute('style')===rootStyle,'Template removed runtime dashboard size');
    staged.className=clip.className;w.hmbCopyPromptElementAttributes(clip,staged,true);
    check(clip.getAttribute('style')===clipStyle,'Template removed runtime clip size');
    const input=document.createElement('input');input.className='source-select nodrag nopan nowheel';input.setAttribute('data-hmb-base-disabled','0');
    const next=document.createElement('input');next.className='source-select';next.disabled=true;
    w.hmbCopyPromptElementAttributes(input,next);
    check(['nodrag','nopan','nowheel'].every(c=>input.classList.contains(c)),'Control lost native gesture isolation');
    check(input.getAttribute('data-hmb-base-disabled')==='1','A genuinely disabled authoritative control was enabled');
    next.disabled=false;w.hmbCopyPromptElementAttributes(input,next);
    check(input.getAttribute('data-hmb-base-disabled')==='0','A genuinely enabled authoritative control stayed disabled');

    // Real teardown cancels pending publication and all synthetic delayed ACKs.
    const beforeCleanup=publications.length;
    const currentField=host.querySelector(`[data-text-key="${key}"]`);currentField.value='unload must not publish';currentField.dispatchEvent(new Event('input',{bubbles:true}));
    controller.cleanup();disposed=true;for(const t of timers)clearTimeout(t);await wait(350);
    check(publications.length===beforeCleanup,'Deleted lifecycle published a pending draft');
    return {checks:['same-UI source ACK settles','idle clocks stable','dirty draft preserved','real edit increments once','crossed merge keeps UI clock','repair settles','new ACK cancels obsolete automatic repair','exact repair dedup keeps later user edit','five documents and literals preserved','root/clip sizing retained','gesture classes retained','disabled authority retained','cleanup cancels publication'],publications:publications.length};
  });
  assert.deepEqual(errors,[]);
  const report={scope:'Isolated Chromium actual widget + delayed synthetic ACK; no live editor/engine/provider',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),...result};
  const out=process.env.HMB_PROMPT_ACK_REPORT_DIR||path.resolve('reports/usability-performance-audit-20261023');fs.mkdirSync(out,{recursive:true});
  fs.writeFileSync(path.join(out,'prompt-idle-ack-regression.json'),JSON.stringify(report,null,2)+'\n');
  console.log(`HMB Prompt idle ACK: PASS (${result.checks.length} behavioral checks)`);
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
