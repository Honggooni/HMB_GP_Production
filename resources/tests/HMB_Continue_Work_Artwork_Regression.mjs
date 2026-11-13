import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {nativeTestBrowserPath,nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';
const dir=path.resolve(process.env.HMB_CONTINUE_ART_REPORT||'reports/local-v0870-continue-art-20261112');
const baseline=fs.readFileSync(path.join(dir,'baseline-ready.js'),'utf8');
const basket=fs.readFileSync(path.join(dir,'basket-candidate.js'),'utf8');
const art=fs.readFileSync(path.join(dir,'continue-art.js'),'utf8');
const selected=[3,6,9,12,14,16,21,22,27,29];
const browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
const results={selected,checks:[],timings:{baseline:[],decorated:[]}};
async function fixture({decorated=true,index=0,viewport={width:1280,height:800},storage=false,broken=false}={}){
 const page=await browser.newPage({viewport,deviceScaleFactor:2});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('https://hmb-fixture.local/**',r=>r.fulfill({body:'<!doctype html><html><body style="margin:0;background:#151a25"><div id="host"></div></body></html>',contentType:'text/html'}));
 await page.goto('https://hmb-fixture.local/');
 await page.evaluate(({index,storage})=>{Math.random=()=> (index+.2)/10;if(storage)Object.defineProperty(window,'localStorage',{get(){throw new Error('denied')}});},{index,storage});
 if(decorated)await page.addScriptTag({content:broken?art.replace(/data:image\/webp;base64,[A-Za-z0-9+/=]+/g,'data:image/webp;base64,AA=='):art});
 await page.addScriptTag({content:decorated?basket:baseline});
 const time=await page.evaluate(async()=>{
  window.dismissed=0;window.entered=0;
  window.mount=()=>window.__hmbMountRodongMartStartup({host:document.querySelector('#host'),onDismiss:()=>{window.dismissed++;window.cleanup();},onEnter:async()=>{window.entered++;return false;}});
  const start=performance.now();window.cleanup=window.mount();
  const interactive=performance.now()-start;
  const href=document.querySelector('.hmb-continue-picture image')?.getAttribute('href');
  let decoded=null;
  if(href){const img=new Image();img.src=href;try{await img.decode();decoded=performance.now()-start;}catch{}}
  await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  return {interactive,decoded,paintOpportunity:performance.now()-start};
 });
 const bounds=await page.locator('.hmb-mart-continue').boundingBox();
 return {page,errors,time,bounds};
}
try{
 const previews=[];
 for(let index=0;index<selected.length;index++){
  const f=await fixture({index});const button=f.page.getByRole('button',{name:'기존 작업 계속',exact:true});
  assert.equal(await button.getAttribute('data-hmb-continue-artwork'),String(selected[index]));
  assert.equal(await button.locator('svg').getAttribute('preserveAspectRatio'),'xMidYMid slice');
  assert.equal(await button.locator('.hmb-continue-label').evaluate(el=>getComputedStyle(el).opacity),'0');
  await button.hover();await f.page.waitForTimeout(150);
  assert.equal(await button.locator('.hmb-continue-label').evaluate(el=>getComputedStyle(el).opacity),'1');
  const label=await button.locator('.hmb-continue-label').boundingBox();
  assert.ok(label.x>=f.bounds.x && label.x+label.width<=f.bounds.x+f.bounds.width+.1);
  assert.ok(f.time.decoded!==null,'WebP sheet decoded');
  await f.page.evaluate(()=>{const id=document.querySelector('.hmb-mart-continue').dataset.hmbContinueArtwork;window.cleanup();Math.random=()=>.999;window.cleanup=window.mount();if(document.querySelector('.hmb-mart-continue').dataset.hmbContinueArtwork!==id)throw Error('remount changed artwork');});
  await button.hover();await f.page.waitForTimeout(150);
  const png=await button.screenshot();previews.push({id:selected[index],data:png.toString('base64')});
  if(index===0)await f.page.screenshot({path:path.join(dir,'startup-preview.png')});
  await button.click({position:{x:4,y:4}});assert.equal(await f.page.evaluate(()=>window.dismissed),1);
  assert.deepEqual(f.errors,[]);results.timings.decorated.push(f.time);await f.page.close();
 }
 results.checks.push('exact 10 selections, full-bleed art, hover label, single-art remount, full-button pointer click');
 for(const viewport of [{width:1920,height:1080},{width:1280,height:800},{width:800,height:600},{width:390,height:700}]){
  const b=await fixture({decorated:false,viewport});const f=await fixture({viewport});
  assert.deepEqual(f.bounds,b.bounds,'Original continue-button dimensions and position');
  await f.page.getByRole('button',{name:'기존 작업 계속',exact:true}).focus();await f.page.keyboard.press('Enter');
  assert.equal(await f.page.evaluate(()=>window.dismissed),1);assert.deepEqual(f.errors,[]);
  await b.page.close();await f.page.close();
 }
 results.checks.push('unchanged geometry at 4 viewport sizes; Enter accessibility');
 for(const options of [{storage:true},{broken:true}]){
  const f=await fixture(options);await f.page.keyboard.press('Escape');assert.equal(await f.page.evaluate(()=>window.dismissed),1);assert.deepEqual(f.errors,[]);await f.page.close();
 }
 results.checks.push('blocked storage and failed image leave continue/Escape operational');
 const f=await fixture();await f.page.evaluate(()=>{window.cleanup();window.evalSource=undefined;});
 await f.page.addScriptTag({content:art});await f.page.evaluate(()=>{window.cleanup=window.mount();});
 assert.notEqual(await f.page.locator('.hmb-mart-continue').getAttribute('data-hmb-continue-artwork'),'3');
 await f.page.close();results.checks.push('next launch avoids immediate repeat');
 for(let i=0;i<10;i++){const b=await fixture({decorated:false,index:i});results.timings.baseline.push(b.time);await b.page.close();}
 const sheet=await browser.newPage({viewport:{width:1000,height:620},deviceScaleFactor:2});
 await sheet.setContent('<body style="margin:0;padding:20px;background:#101827;color:white;font:15px system-ui;display:grid;grid-template-columns:repeat(5,1fr);gap:14px">'+previews.map(p=>`<div style="text-align:center"><div style="margin-bottom:8px">${String(p.id).padStart(2,'0')}</div><img style="width:144px;height:202px;object-fit:contain" src="data:image/png;base64,${p.data}"></div>`).join('')+'</body>');
 await sheet.screenshot({path:path.join(dir,'all-ten-preview.png')});await sheet.close();
 results.status='PASS';fs.writeFileSync(path.join(dir,'browser-verification.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify(results,null,2));
}finally{await browser.close();}
