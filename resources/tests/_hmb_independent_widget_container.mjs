// Use the registered files and live SDK parameter values with the 0.132 widget loader.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {nativeTestBrowserPath, nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const library = process.env.HMB_INDEPENDENT_LIBRARY;
const root = path.dirname(process.env.HMB_STOCK_EDITOR_0130_SOURCE);
const manifest = JSON.parse(fs.readFileSync(path.join(library, 'griptape-nodes-library.json'), 'utf8'));
const sdk = JSON.parse(fs.readFileSync(process.env.HMB_INDEPENDENT_SDK_DATA, 'utf8'));
const widgets = new Map(manifest.widgets.map(row => [row.name, path.resolve(library, row.path)]));
const hash = value => createHash('sha256').update(value).digest('hex');
assert.equal(widgets.size, 13);
assert.equal(new Set(sdk.widgets.map(row => row.name)).size, 13);
const stock = fs.readFileSync(process.env.HMB_STOCK_EDITOR_0130_SOURCE, 'utf8');
assert.equal(hash(stock), '547cd4cc14430531d96b865d2d45f1263f32b260f0108300acd0f6ed4cd4a1b4');
const reactStart = stock.indexOf('var Xa=n((e=>{'), reactEnd = stock.indexOf(',$a=/^(?:', reactStart);
const loaderStart = stock.indexOf('var yPt=[`ControlParameterInput`'), loaderEnd = stock.indexOf('},fX=Rt', loaderStart);
assert.ok(reactStart > 0 && reactEnd > reactStart && loaderStart > 0 && loaderEnd > loaderStart);
const runtime = `
import {a as e,t as n} from "./rolldown-runtime-DSDNlrLa.js";
import {t as wr} from "./react-Cwox1F5v.js";
import {di as kt,gi as Ut,hi as Jt} from "./EngineContext-D-bkzERZ.js";
${stock.slice(reactStart, reactEnd)};
const Z=kt(),fstore={liveValues:new Map,synced:new Map,clearNode(node){this.synced.delete(node)},
  registerSynced(node,keys){this.synced.set(node,keys);return ()=>this.synced.delete(node)}};
const rows=${JSON.stringify(sdk.widgets)}, nodeLookup = new Map();
for(const row of rows){
  if(!nodeLookup.has(row.node))nodeLookup.set(row.node,{data:{elements:[]}});
  const entries = Object.entries(row.synced || {});
  nodeLookup.get(row.node).data.elements.push(...entries.map(([name,value])=>({name,value,element_type:"Parameter"})));
}
const pn=()=>({store:()=>({getState:()=>fstore})}),rP={},dh=f=>f({edges:[]}),uh=f=>f({nodeLookup}),nh=f=>f,vXe=f=>f(fstore);
${stock.slice(loaderStart, loaderEnd + 1)};
window.mounted=[];window.changes=[];
function App(){
  const [broken,setBroken]=Y.useState(false);window.failOne=()=>setBroken(true);
  return Z.jsx("main",{className:"react-flow",children:rows.map((row,i)=>{
    const url=broken&&row.name==="HMBSeedanceGenerationWidget"?"/broken.js":"/observe/"+row.name;
    return Z.jsx("section",{className:"react-flow__node","data-id":row.node,"data-widget":row.name,children:
      Z.jsx(NPt,{nodeName:row.node,parameterName:row.parameter,ui_options:row.options,value:row.value,
        onChange:v=>window.changes.push(row.name),widgetUrl:url,widgetName:row.name,FallbackComponent:()=>null},url)},i)
  })})
}
Qa.createRoot(document.querySelector("#app")).render(Z.jsx(App,{}));`;

const browser = await nativeTestPlaywright().chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
try {
  const page = await browser.newPage({viewport:{width:1500,height:1000}});
  const errors = [], foreign = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', route => {
    const u = new URL(route.request().url());
    if (u.origin !== 'http://hmb.test') { foreign.push(u.hostname); return route.abort(); }
    const name = u.pathname.slice(1);
    const js = body => route.fulfill({contentType:'application/javascript',body});
    if (!name) return route.fulfill({contentType:'text/html',body:'<style>section{width:900px;position:relative}.widget-container{width:100%}</style><div id="app"></div><script type="module" src="/test.js"></script>'});
    if (name === 'test.js') return js(runtime);
    if (name === 'broken.js') return js('export default function(){throw Error("fixture: sibling mount failed")}');
    const [kind, id] = name.split('/');
    if (kind === 'observe' && widgets.has(id)) return js(`import mount from "/widget/${id}";export default function(container,props){const handle=mount(container,props);window.mounted.push([props.nodeName,props.parameterName,${JSON.stringify(id)}]);return handle;}`);
    if (kind === 'widget' && widgets.has(id)) return js(fs.readFileSync(widgets.get(id)));
    if (!name.includes('/') && name.endsWith('.js') && fs.existsSync(path.join(root,name))) return js(fs.readFileSync(path.join(root,name)));
    return route.fulfill({status:404});
  });
  await page.goto('http://hmb.test');
  await page.waitForFunction(expected => new Set(mounted.map(row=>row[2])).size===expected, widgets.size, {timeout:15000})
    .catch(async error=>{
      console.error({errors,missing:await page.evaluate(()=>Array.from(document.querySelectorAll('section[data-widget]'))
        .filter(el=>!window.mounted?.some(row=>row[2]===el.dataset.widget))
        .map(el=>[el.dataset.widget,el.innerText.slice(0,250)]))});
      throw error;
    });
  const rows = await page.locator('section[data-widget]').evaluateAll(sections=>sections.map(section=>({
    name:section.dataset.widget, mount:!!section.querySelector('.widget-container'),
    buttons:section.querySelectorAll('button, select, input, textarea').length,
    error:section.innerText.includes('Widget error'),
  })));
  assert.ok(rows.every(row=>row.mount && !row.error),JSON.stringify(rows));
  const language = page.locator('[data-widget=HMBFinishLookLibraryWidget] button[data-language-toggle]').first();
  const before = await language.innerText();
  await language.evaluate(el=>{window.healthyInstance=el.closest('.widget-container');});
  await page.evaluate(()=>window.failOne());
  await page.locator('[data-widget=HMBSeedanceGenerationWidget]',{hasText:'Widget error'}).first().waitFor();
  await language.click();
  assert.notEqual(await language.innerText(),before);
  assert.ok(await language.evaluate(el=>window.healthyInstance===el.closest('.widget-container')));
  assert.ok(await page.evaluate(()=>changes.includes('HMBFinishLookLibraryWidget')));
  assert.deepEqual(errors,[]);
  const proof = {passed:true, editor_sha256:hash(stock), registered_widgets:widgets.size,
    bindings:rows, mounted:await page.evaluate(()=>mounted), widget_sha256:Object.fromEntries(
      [...widgets].map(([name,file])=>[name,hash(fs.readFileSync(file))])),
    sibling_failure_isolated:true, uncaught_errors:errors, blocked_external_hosts:[...new Set(foreign)]};
  fs.writeFileSync(path.join(process.env.HMB_LIFECYCLE_REPORT_DIR,'widgets.json'),JSON.stringify(proof,null,2));
  console.log('13 registered HMB widget modules mounted in the native container; sibling failure isolation passed.');
} finally {
  await browser.close();
}
