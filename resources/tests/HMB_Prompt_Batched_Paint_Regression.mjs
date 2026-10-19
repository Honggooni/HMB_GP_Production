// Bounded paint work with real Chromium controls and deterministic host geometry.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
const source=fs.readFileSync(new URL('../../widgets/HMBPromptLibraryScopedBindingWidget.js',import.meta.url),'utf8');
const css=source.match(/includeStyle \? `<style>\n([\s\S]*?)<\/style>` : ""/);
assert.ok(css);
assert.equal(crypto.createHash('sha256').update(css[1]).digest('hex'),'06c4e1eb664a9d1437733118a6b42f979acf2d51b5a0a56190f3fc181ef78c81','Approved palette, CSS, geometry and responsive design bytes remain unchanged.');
const instrumented=source.replace('export function normalizeState(input) {','export function normalizeState(input) { globalThis.__hmbPaintNormalizeCalls=(globalThis.__hmbPaintNormalizeCalls||0)+1;')+'\nexport {hmbMeasurePromptHostHeights,hmbApplyDashboardHostSizing,hmbStoreGroupHeight,hmbApplyExactGroupFlex};';
const widget=await import('data:text/javascript;base64,'+Buffer.from(instrumented).toString('base64'));
const saved={document:globalThis.document,window:globalThis.window};const events=[];
const make=(name,top,height,parent=null)=>{
 const values={};const element={name,parentElement:parent,className:'sdk-wrapper',dataset:{},clientHeight:height,offsetHeight:height,getAttribute(){return null;},getBoundingClientRect(){events.push('read:'+name);return {top,height:this.offsetHeight*2,bottom:top+this.offsetHeight*2};},classList:{add(){},remove(){}},querySelector(){return null;}};
 element.style=new Proxy(values,{set(owner,key,value){events.push('write:'+name+':'+String(key));owner[key]=value;return true;}});return element;
};
try{
 const shell=make('shell',40,1350);shell.className='react-flow__node';
 const outer=make('outer',380,0,shell),inner=make('inner',440,0,outer),host=make('host',500,0,inner);
 globalThis.document={body:{},documentElement:{}};
 globalThis.window={getComputedStyle(){events.push('computed:shell');return {paddingBottom:'8px',borderBottomWidth:'2px'};}};
 const measured=widget.hmbMeasurePromptHostHeights(host);
 assert.deepEqual([...measured.heights].map(([el,height])=>[el.name,height]),[['host',1102],['inner',1132],['outer',1162]]);
 assert.equal(events.filter(value=>value==='read:shell').length,2,'One scale/rect read pair for all wrappers.');
 assert.equal(events.filter(value=>value==='computed:shell').length,1);
 events.length=0;widget.hmbApplyDashboardHostSizing(host,{multi_shot_enabled:true});
 const firstWrite=events.findIndex(value=>value.startsWith('write:'));
 assert.ok(firstWrite>0);assert.equal(events.slice(firstWrite).some(value=>value.startsWith('read:')||value.startsWith('computed:')),false,'No host read after a sizing write in the same pass.');
 assert.equal(host.style.height,'1102px');assert.equal(inner.style.height,'1132px');assert.equal(outer.style.height,'1162px');
 const before=JSON.stringify(shell.style);shell.clientHeight=1600;shell.offsetHeight=1600;events.length=0;
 widget.hmbApplyDashboardHostSizing(host,{multi_shot_enabled:true});
 assert.equal(host.style.height,'1352px','The next pass must read a resized host afresh.');
 assert.equal(JSON.stringify(shell.style),before,'Sizing never changes the native node or canvas.');
 let storedWrites=0;host.dataset=new Proxy({},{set(owner,key,value){storedWrites++;owner[key]=value;return true;}});
 widget.hmbStoreGroupHeight(host,'imageSources',300);for(let i=0;i<30;i++)widget.hmbStoreGroupHeight(host,'imageSources',300);
 assert.equal(storedWrites,1,'Same stored height does not invalidate attribute-based styles.');
 const card=make('card',0,0);card.getAttribute=name=>name==='data-group-id'?'imageSources':null;
 widget.hmbApplyExactGroupFlex(card,300);events.length=0;for(let i=0;i<30;i++)widget.hmbApplyExactGroupFlex(card,300);
 assert.deepEqual(events,[],'Unchanged group dimensions do not rewrite inline styles.');
}finally{for(const [key,value]of Object.entries(saved)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
const state=widget.normalizeState({source_sync_revision:4,ui_edit_revision:7,images:Array.from({length:50},(_,index)=>({slot:index+1,label:'Image '+index,present:true})),videos:Array.from({length:10},(_,index)=>({slot:index+1,label:'Video '+index,present:true}))});
const retained={__hmbPromptCurrentSourceSyncRevision:4,__hmbPromptCurrentUiEditRevision:7,__hmbPromptLatestLocalUiEditRevision:7,__hmbPromptLatestLocalStateValue:JSON.stringify(state)};
globalThis.__hmbPaintNormalizeCalls=0;const parsed={};
assert.equal(widget.hmbConsumePendingPromptStateEcho(retained,{value:JSON.stringify(state)},state,parsed),false);
assert.equal(globalThis.__hmbPaintNormalizeCalls,2,'Same-revision comparison normalizes incoming and retained snapshots once each.');
assert.equal(parsed.state.images.length,50);assert.equal(parsed.state.videos.length,10);
const stale=structuredClone(state);stale.images[0].label='Delayed old ownership';
assert.equal(widget.hmbConsumePendingPromptStateEcho(retained,{value:JSON.stringify(stale)},state,{}),true);
assert.equal(retained.__hmbPromptLastConsumedEchoWasStale,true,'Bounded normalization preserves semantic stale-echo protection.');
delete globalThis.__hmbPaintNormalizeCalls;
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
let external=0;const errors=[];
try{
 const page=await browser.newPage();page.on('pageerror',error=>errors.push(error.message));await page.route('**/*',route=>{external++;return route.abort();});
 await page.setContent('<!doctype html><meta charset="utf-8"><div id="host"></div>');
 const result=await page.evaluate(async code=>{
  const widget=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(code))));
  const owner=document.querySelector('#host');
  const section=label=>{const el=document.createElement('section');el.innerHTML=`<h3>Sources</h3><div class="source-scrollbox"><div class="source-header">Header</div><div class="source-row image" data-source-key="stable-source"><input value="${label}"><select><option value="a">A</option><option value="b">B</option></select></div></div>`;return el;};
  const live=section('old');owner.append(live);const next=section('new'),row=live.querySelector('.source-row'),stagedInput=next.querySelector('input');
  if(!widget.hmbPatchPromptSourceSection(live,next))throw Error('Source patch did not apply');
  const adopted=live.querySelector('input')===stagedInput,retained=live.querySelector('.source-row')===row;
  const select=live.querySelector('select'),options=[...select.options];select.focus();
  const latest=section('latest');latest.querySelector('select').innerHTML='<option value="changed">Changed authoritative option</option>';
  widget.hmbPatchPromptSourceSection(live,latest);
  return {adopted,retained,label:live.querySelector('input').value,sameSelect:select===live.querySelector('select'),sameOptions:options.length===select.options.length&&options.every((option,index)=>select.options[index]===option),focused:document.activeElement===select};
 },source);
 assert.deepEqual(result,{adopted:true,retained:true,label:'latest',sameSelect:true,sameOptions:true,focused:true});
 assert.deepEqual(errors,[]);assert.equal(external,0);
}finally{await browser.close();}
console.log('HMB Prompt batched paint: PASS (shared host reads before writes, fresh resize geometry, idempotent dimensions, bounded normalization with stale ACK, staged-node adoption, focused native select/options retained, approved CSS unchanged; external 0)');
