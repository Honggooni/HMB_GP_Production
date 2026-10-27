// Actual installed React, JSX runtime, native header, and native action code.
// Only the SDK transport/store boundary is synthetic. Never loads the live app.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {prepareNativeEditor,readNativeEditorCSS,nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {original,patched,evidence:manifest}=prepareNativeEditor(root);
const sha=value=>createHash('sha256').update(value).digest('hex');
const between=(source,start,end)=>{
 const a=source.indexOf(start);assert.ok(a>=0,'Missing native source anchor '+start);
 const b=source.indexOf(end,a+start.length);assert.ok(b>a,'Missing native end anchor '+end);
 return source.slice(a,b);
};
// This prefix contains installed React 19.3.0 and ReactDOM, before app/router
// startup. No editor telemetry, live WebSocket, or application boot is loaded.
const alias=original.indexOf('S=u(p(),1),C=h(),w=x(),T=u(y())');assert.ok(alias>0);
const runtime=original.slice(0,original.indexOf(',E=`modulepreload`',alias))+';';
const jsxRuntime=between(original,'var Wn=s(','function Gn(');
const header=between(patched,'var D$t=({node_name:',',O$t=')+';';
const nativeCarrier='var '+between(patched,'YTr=({widgetUrl:','},XTr=')+'};';
const nativeResize=between(patched,'(0,R.jsx)(sie,{isVisible:','})')+'})';
const originalResize=between(original,'(0,R.jsx)(sie,{isVisible:','})')+'})';
const nativeResizerSource=between(original,'function sie({nodeId:','var cie=e=>e.domNode');
assert.ok(nativeResizerSource.indexOf('cl.map(')<nativeResizerSource.indexOf('sl.map('),'Fixture preserves actual native line-before-corner control DOM order');
assert.equal(nativeResize.replace('(t||hmbNativeFrameActive)','t'),originalResize,'Only the native visibility gate changes; every resize callback and minimum size remains original');
assert.equal(manifest.anchors.color_lut_native_frame_observer,1);
assert.equal(manifest.anchors.color_lut_resize_without_selection,1);
assert.ok(patched.includes('let hmbNativeFrameActive=hmbUseColorLUTFrameActive(e.node_type,e.node_name);'),'Actual Ejr calls the scoped active-frame hook');
const editorCSS=readNativeEditorCSS(root);
const nativeResizeCSS=(editorCSS.match(/[^{}]*\.react-flow__resize-control[^{}]*\{[^{}]*\}/g)||[]).join('\n');
assert.ok(nativeResizeCSS.includes('cursor:nwse-resize')&&nativeResizeCSS.includes('cursor:nesw-resize'),'Installed native resize cursor styles are present');
const hook=fs.readFileSync(path.join(root,'resources/editor/hmb-color-lut-native-header.js'),'utf8');
const selectionHelpers='var '+between(original,'NOr=e=>',';function IOr(')+';';
const actionCallbacks=between(original,'Ge=(0,S.useCallback)(async()=>{await _q',',tt=(0,S.useCallback)');
const resolveHelper='var '+between(original,'_q=(e,t=!1)',',vq=')+';';
const lockHelper='var '+between(original,'UBt=(e,t)=>',',WBt=')+';';
const actionNames=between(original,'var kQ=[',';function AQ(')+';';
assert.equal(sha(original),manifest.source_sha256);
assert.equal(sha(patched),manifest.candidate_sha256);
assert.equal(sha(hook),manifest.helper_sha256);
assert.ok(header.includes('hmbColorLUTHeaderPortals')&&header.includes('Ae=(0,S.useCallback)'));
assert.ok(header.includes('onMouseDown:Ce')&&header.includes('onMouseDown:we')&&header.includes('m()'));
assert.ok(nativeCarrier.includes('hmbIsNativeStudioWidget(t)?i:void 0'),'Disabled-only updates must reach the approved HMB widget allowlist');

const stubs=String.raw`
window.nativeStore={nodeResolutionState:{},involvedNodes:new Set(),resolvingNodes:new Set(),nodeErrors:{},flowRunning:false};
window.nodes=['LUT A','LUT B','Other'].map((name,i)=>({id:name,data:{node_name:name,node_type:i<2?'HMBColorLUTLibrary':'ExampleNode',locked:false}}));
window.selected=['LUT A'];window.sdk=[];window.failLock=false;window.failRun=false;window.cleanMode=false;window.headerItems=['run'];
window.expanded={};window.rolledUp={};window.animatedSize={};window.showWidget={'LUT A':true,'LUT B':true};window.showMeasurement={'LUT A':true,'LUT B':true};window.measurementModes={'LUT A':'visibility','LUT B':'visibility'};window.measurementEpochs={};window.headerEpochs={};window.widgetValues={};window.widgetHandles={};window.widgetUpdates={};window.nativeRenders={};window.epochs={};window.stateEvents=[];window.nativeDoubleClicks=[];
window.resizeProps={};window.resizeCallbacks={};window.resizeEvents=[];window.resizeRenders={};
var icon=name=>props=>(0,R.jsx)('svg',{'data-native-icon':name,width:16,height:16,'aria-hidden':true});
var XA=icon('lock'),ZA=icon('unlock'),lL=icon('run'),QN=icon('reset'),uT=icon('startFlow'),VC=icon('copy'),DE=icon('duplicate'),wz=icon('delete'),SO=icon('group'),IP=icon('settings'),ZM=icon('rename'),bx=icon('collapsed'),_x=icon('expanded'),Zye=icon('unresolved');
var VZ=()=>((0,R.jsx)('span',{'data-native-type-icon':true})),fW=props=>(0,R.jsx)('button',{...props,type:'button'});
var eq=props=>(0,R.jsx)('span',{className:'native-tooltip',children:props.children}),tq=props=>props.children,nq=props=>(0,R.jsx)('span',{hidden:true,children:props.children});
var OQ=props=>(0,R.jsx)('span',{'data-native-resolution':true,children:props.resolutionState||'running'}),EQ=props=>(0,R.jsx)('span',{'data-native-error':props.nodeName,children:String(props.error)});
var KZ=()=>({settings:{nodeHeaderItems:window.headerItems}}),qZ=()=>({openModal:()=>{}}),IQ=()=>false,MQ=()=> 'colorful';
var wQ=selector=>selector({renameRequestedNodeId:null,setRenameRequestedNodeId:()=>{}});wQ.getState=()=>({selectedNodes:window.selected.map(id=>({node:{id}}))});
var PQ=()=>({icon:null,backgroundStyle:{backgroundColor:'rgb(91, 33, 130)'},textColorClass:'native-text',inputStyle:{},buttonClass:'native-enabled',buttonStyle:{color:'rgb(255, 255, 255)'},disabledButtonClass:'native-disabled'});
var _Qt=()=>window.cleanMode,uJ=state=>state.flowRunning,dJ=selector=>selector(window.nativeStore),fJ=selector=>selector,T$t=error=>error;
var AQ=()=>({}),jQ=()=>'',FQ=fn=>fn?event=>{if(!event.target.closest('button,input,a,select,textarea,.nodrag'))fn();}:undefined;
var lUt=async()=>{},ig={success:()=>{},error:()=>{}},QV={},rq=()=>null,pBt=()=>null;
var sJ=()=>({subscribeToEvent:()=>{}}),Wq=async()=>({flow_name:'Synthetic Scratch'}),$Bt=()=>{},nVt=async()=>{},BBt=async()=>{},hu=(changes,nodes)=>nodes.filter(node=>!changes.some(change=>change.id===node.id));
window.geometryRefreshes=[];const refreshNativeGeometry=name=>window.geometryRefreshes.push(name);var FEr=()=>refreshNativeGeometry;
var Xd={request:async(type,payload)=>{window.sdk.push({type,payload:structuredClone(payload)});
 if(type==='BatchSetNodeLockStateRequest'&&window.failLock)throw new Error('Synthetic lock rejection');
 if(type==='ResolveNodeRequest'&&window.failRun)throw new Error('Synthetic resolve rejection');return {succeeded:true};}};
window.getNodes=()=>window.nodes;window.setNodes=update=>{window.nodes=typeof update==='function'?update(window.nodes):update;window.rerender();};
`;

const fixture=String.raw`
function useOriginalActions(e){
 const C=window.getNodes,w=window.setNodes,T=()=>{},D=window.cleanMode;
 const [optimistic,p]=(0,S.useState)(null);
 const ORIGINAL_NATIVE_ACTION_CALLBACKS;
 return {handlePlayClick:Ge,handleStartFromNodeClick:Ke,handleLockToggle:Ye,onReset:et,locked:optimistic===null?e.locked:optimistic};
}
var GTr=new Map([['fixture:color-lut',(element,props)=>{
 const scope=element.closest('[data-measurement-carrier]')?'measurement':'visible';
 element.setAttribute('data-hmb-native-node-type',props.nativeNodeType);
 const handle=mount(element,props);window.widgetHandles[props.nodeName+'-'+scope]=handle;
 element.addEventListener('hmb-color-lut-header-state',event=>window.stateEvents.push({name:props.nodeName,scope,active:event.detail.active}));
 return {update(next){window.widgetUpdates[props.nodeName]=(window.widgetUpdates[props.nodeName]||0)+1;handle.update(next);},cleanup(){handle.cleanup();}};
}]]),JTr=(_url,error)=>({message:String(error)});
const OriginalNativeHeader=D$t;
D$t=function NativeHeaderCounter(props){window.nativeRenders[props.node_name]=(window.nativeRenders[props.node_name]||0)+1;return OriginalNativeHeader(props);};
const ResizeFixtureContext=(0,S.createContext)('');
// sie is the only resize component substitute: the real component depends on
// the live ReactFlow store. It records the untouched native props, while the
// actual Ejr JSX visibility expression, active hook and installed CSS execute.
var sie=props=>{
 const name=(0,S.useContext)(ResizeFixtureContext);window.resizeProps[name]=props;
 window.resizeRenders[name]=(window.resizeRenders[name]||0)+1;
 if(!props.isVisible)return null;
 return (0,R.jsxs)(R.Fragment,{children:[...['top','right','bottom','left'].map(position=>(0,R.jsx)('div',{
  className:'react-flow__resize-control line nodrag '+position,'data-resize-node':name,'data-resize-position':position},position)),
 ...['top left','top right','bottom left','bottom right'].map(position=>(0,R.jsx)('div',{
  className:'react-flow__resize-control handle nodrag '+position,'data-resize-node':name,'data-resize-position':position,
  onPointerDown:event=>props.onResizeStart(event),onPointerUp:event=>{props.onResize(event,{width:880,height:900});props.onResizeEnd(event);}},position)),
 ]});
};
function NodeRow({data}){
 const name=data.node_name,actions=useOriginalActions(data),isLUT=hmbIsNativeStudioType(data.node_type);
 const hmbNativeFrameActive=hmbUseColorLUTFrameActive(data.node_type,name),t=window.selected.includes(name),O=window.expanded[name]===false,
  yt=O||window.rolledUp[name]===true,fe=window.animatedSize[name]||null,ee=640;
 const handlers=(0,S.useMemo)(()=>({lt:(event,size)=>window.resizeEvents.push({name,kind:'resize',size}),re:value=>window.resizeEvents.push({name,kind:'resizing',value})}),[name]);
 const {lt,re}=handlers;window.resizeCallbacks[name]=handlers;
 const value=window.widgetValues[name]||(window.widgetValues[name]=hmbColorLUTState({}));
 const onChange=value=>{window.sdk.push({type:'SetParameterValueRequest',payload:{node_name:name,parameter_name:'HMB_COLOR_LUT_UI_STATE'}});window.widgetValues[name]=value;window.rerender();};
 const widgetProps={widgetUrl:'fixture:color-lut',widgetName:'HMBColorLUTLibraryWidget',nodeName:name,parameterName:'HMB_COLOR_LUT_UI_STATE',
  nativeNodeType:data.node_type,
  disabled:data.locked||window.nativeStore.resolvingNodes.has(name),value,onChange,FallbackComponent:()=>null};
 return (0,R.jsx)('article',{className:'react-flow__node','data-id':name,'data-node-type':data.node_type,children:(0,R.jsxs)('div',{'data-native-node-frame':name,className:'bg-card',children:[
  (0,R.jsx)(ResizeFixtureContext.Provider,{value:name,children:ORIGINAL_NATIVE_RESIZE_ELEMENT}),
  // The installed nAr allocator mounts a real second YTr to measure geometry.
  // Keep it first in DOM as well as mounting it after the visible widget in
  // lifecycle tests, so neither discovery order nor ready events can own icons.
  isLUT&&window.showMeasurement[name]&&(0,R.jsx)('div',{'data-measurement-carrier':name,
   style:{visibility:window.measurementModes[name]==='visibility'?'hidden':'visible',display:window.measurementModes[name]==='display'?'none':'block',opacity:window.measurementModes[name]==='opacity'?0:1,position:'absolute',left:0,top:0,width:'880px',pointerEvents:'none'},
   children:(0,R.jsx)(YTr,widgetProps,name+'-measurement-'+(window.measurementEpochs[name]||0))}),
  (0,R.jsx)('div',{'data-native-host':name,children:(0,R.jsx)(D$t,{node_name:name,node_type:data.node_type,node_category:'HMB',...actions,
   onDoubleClick:()=>window.nativeDoubleClicks.push(name),hmbHostExpanded:!yt},name+'-header-'+(window.headerEpochs[name]||0))}),
  isLUT&&window.showWidget[name]&&(0,R.jsx)('div',{'data-visible-carrier':name,
   children:(0,R.jsx)(YTr,widgetProps,name+'-'+(window.epochs[name]||0))}),
  (0,R.jsx)('div',{'data-port':name+'-input',className:'react-flow__handle'}),
  (0,R.jsx)('div',{'data-port':name+'-output',className:'react-flow__handle'}),
 ]})});
}
function App(){return (0,R.jsxs)(R.Fragment,{children:[...window.nodes.map(node=>(0,R.jsx)(NodeRow,{data:node.data},node.id)),
 (0,R.jsx)('svg',{'data-wire':'A-to-B','data-source':'LUT A-output','data-target':'LUT B-input'})]});}
const appRoot=w.createRoot(document.getElementById('app'));
window.rerender=()=>appRoot.render((0,R.jsx)(App,{}));window.rerender();window.ready=true;
`.replace('const ORIGINAL_NATIVE_ACTION_CALLBACKS;','const '+actionCallbacks+';').replace('ORIGINAL_NATIVE_RESIZE_ELEMENT',nativeResize);

const moduleSource="import mount,{hmbColorLUTState} from '/widget.js';\n"+runtime+'\n'+jsxRuntime+'\n'+stubs+'\n'
 +selectionHelpers+'\n'+resolveHelper+'\n'+lockHelper+'\n'+actionNames+'\n'+hook+'\n'+header+'\n'+nativeCarrier+'\n'+fixture;
const html=`<!doctype html><meta charset="utf-8"><title>Synthetic native React header fixture</title><style>
body{margin:8px;background:#101420;color:white;font:14px system-ui}#app{display:flex;align-items:flex-start;gap:18px}.react-flow__node{flex:0 0 880px;min-width:0;border:1px solid #506079;position:relative}[data-native-node-frame]{position:relative}[data-native-host]>div{min-height:48px;display:flex;align-items:center;justify-content:space-between;background:#552575}.native-tooltip{display:inline-flex}.native-tooltip>button{height:32px;width:32px;padding:0;background:#192131;color:white;border:0;border-radius:6px;display:inline-grid;place-items:center}.native-tooltip>button.bg-white{background:white;color:black}.native-tooltip>button:disabled{opacity:.4}.native-text{color:white}[data-native-host] input{color:white}.widget-container{height:850px}.hmb-native-header-identity>div{display:flex;gap:6px;align-items:center}.hmb-native-header-identity span{white-space:nowrap}.hmb-native-header-actions>div,.hmb-native-header-actions>div>div{display:flex;gap:3px}.react-flow__handle{width:8px;height:8px;background:cyan;position:absolute;bottom:0}[data-port$=output]{right:0}svg[data-wire]{position:absolute;width:1px;height:1px;pointer-events:none}
${nativeResizeCSS}
</style><div id="app" class="react-flow"></div><script type="module" src="/fixture.js"></script>`;
const widgetSource=fs.readFileSync(path.join(root,'widgets/HMBColorLUTLibraryWidget.js'),'utf8');
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?moduleSource:req.url==='/widget.js'?widgetSource:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const playwright=nativeTestPlaywright();
let browser,checks=0;
try{
 browser=await playwright.chromium.launch({executablePath:process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:2000,height:1200}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(7000);
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 await page.waitForFunction(()=>window.ready&&document.querySelectorAll('[data-visible-carrier] .hmb-color-lut[data-hmb-native-header="active"]').length===2);
 const node=name=>page.locator(`.react-flow__node[data-id="${name}"]`);
 const visible=name=>node(name).locator('[data-visible-carrier]');
 const measurement=name=>node(name).locator('[data-measurement-carrier]');
 const actions=name=>visible(name).locator('[data-hmb-native-actions]');
 const button=(name,icon)=>actions(name).locator(`button:has([data-native-icon="${icon}"])`);
 const frames=async(count=3)=>page.evaluate(count=>new Promise(resolve=>{let elapsed=0;const step=()=>++elapsed>=count?resolve():requestAnimationFrame(step);requestAnimationFrame(step);}),count);
 const assertMeasurementIsolation=async(label)=>{
  for(const name of ['LUT A','LUT B']){
   assert.equal(await visible(name).locator('.hmb-color-lut').getAttribute('data-hmb-native-header'),'active',label+': visible widget keeps portal ownership');
   assert.equal(await actions(name).locator('button').count(),3,label+': all three actual native actions stay in the visible slot');
   if(await measurement(name).count()){
    assert.notEqual(await measurement(name).locator('.hmb-color-lut').getAttribute('data-hmb-native-header'),'active',label+': hidden measurement clone never activates');
    assert.equal(await measurement(name).locator('[data-hmb-native-actions] button,[data-hmb-native-identity] button').count(),0,label+': hidden clone has no native controls');
    assert.equal(await measurement(name).locator('.widget-container').evaluate(element=>element.classList.contains('nodrag')),true,label+': hidden carrier retains no-drag protection');
    assert.equal(await measurement(name).locator('.hmb-color-lut').evaluate(element=>element.classList.contains('nodrag')),true,label+': hidden widget retains no-drag protection');
    checks+=4;
   }
   checks+=2;
  }
  assert.equal(await page.evaluate(()=>window.stateEvents.some(event=>event.scope==='measurement'&&event.active)),false,label+': no hidden clone received an active notification');checks++;
 };
 await page.waitForFunction(()=>document.querySelectorAll('[data-measurement-carrier] .hmb-color-lut').length===2);
 assert.equal(await measurement('LUT A').locator('.widget-container').evaluate(element=>getComputedStyle(element).visibility),'hidden');
 assert.equal(await measurement('LUT A').locator('.widget-container').evaluate(element=>element.getClientRects().length>0),true,'Fixture models the allocator clone with real geometry despite inherited visibility:hidden');checks+=2;
 await assertMeasurementIsolation('Cold mount with two actual YTr instances per node');
 assert.equal(await node('LUT A').getAttribute('data-hmb-color-lut-native-layout'),'active','Unified frame is scoped to the visible LUT node');
 assert.equal(await node('Other').getAttribute('data-hmb-color-lut-native-layout'),null,'Other node frames retain native appearance');
 assert.equal(await page.locator('#hmb-color-lut-unified-frame-v1').count(),1,'Frame stylesheet is installed once');
 assert.equal(await page.evaluate(()=>window.geometryRefreshes.includes('LUT A')&&window.geometryRefreshes.includes('LUT B')),true,'Native geometry refresher runs for both inset handle owners');checks+=4;
 await page.waitForFunction(()=>window.resizeProps['LUT A']?.isVisible&&window.resizeProps['LUT B']?.isVisible);
 assert.equal(await page.evaluate(()=>window.resizeProps.Other.isVisible),false,'An unselected unrelated node keeps its original invisible resize gate');checks++;
 await page.evaluate(()=>{window.selected=[];window.rerender();});await frames();
 assert.equal(await page.evaluate(()=>window.resizeProps['LUT A'].isVisible&&window.resizeProps['LUT B'].isVisible),true,'Both active Color LUT frames expose native resize controls without selection');checks++;
 const resizeStyles=await node('LUT A').locator('.react-flow__resize-control').evaluateAll(elements=>elements.map(element=>{
  const style=getComputedStyle(element);return {position:element.dataset.resizePosition,opacity:style.opacity,pointerEvents:style.pointerEvents,
   cursor:style.cursor,display:style.display,visibility:style.visibility};
 }));
 assert.equal(resizeStyles.length,8);
 const expectedCursors={'top left':'nwse-resize','top right':'nesw-resize','bottom left':'nesw-resize','bottom right':'nwse-resize',top:'ns-resize',right:'ew-resize',bottom:'ns-resize',left:'ew-resize'};
 for(const style of resizeStyles){
  assert.equal(style.opacity,'0','Unified resize chrome stays transparent at '+style.position);
  assert.equal(style.pointerEvents,'auto','Transparent resize controls remain hit-testable at '+style.position);
  assert.equal(style.cursor,expectedCursors[style.position],'Installed native edge/corner cursor remains unchanged');
  assert.notEqual(style.display,'none');assert.equal(style.visibility,'visible');checks+=5;
 }
 const resizeHitTargets=await node('LUT A').locator('.react-flow__resize-control').evaluateAll(elements=>elements.map(element=>{
  const rect=element.getBoundingClientRect(),point={x:rect.x+rect.width/2,y:rect.y+rect.height/2},hit=document.elementFromPoint(point.x,point.y);
  return {position:element.dataset.resizePosition,width:rect.width,height:rect.height,hit:hit===element||element.contains(hit),
   target:hit?.getAttribute('data-resize-position'),point};
 }));
 assert.ok(resizeHitTargets.every(row=>row.hit),'All four edge centers and all four corners remain pointer targets despite transparent chrome '+JSON.stringify(resizeHitTargets));
 assert.ok(resizeHitTargets.filter(row=>row.position.includes(' ')).every(row=>row.width>=16&&row.height>=16),'Transparent corner hit boxes retain the intended 16px minimum');
 assert.ok(resizeHitTargets.filter(row=>['left','right'].includes(row.position)).every(row=>row.width>=10),'Vertical edge hit boxes retain 10px width');
 assert.ok(resizeHitTargets.filter(row=>['top','bottom'].includes(row.position)).every(row=>row.height>=10),'Horizontal edge hit boxes retain 10px height');
 assert.equal(await node('LUT A').locator('[data-native-node-frame]').evaluate(element=>getComputedStyle(element).overflow),'visible','Rounded frame does not clip native resize pointer areas');checks+=5;
 assert.equal(await page.evaluate(()=>Object.entries(window.resizeProps).every(([name,props])=>props.onResize===window.resizeCallbacks[name].lt&&props.minHeight===640&&props.minWidth===600)),true,'Actual JSX passes the original resize callback and dimensions');checks+=2;
 const beforeResizeSdk=await page.evaluate(()=>window.sdk.length);
 await node('LUT A').locator('[data-resize-position="bottom right"]').dispatchEvent('pointerdown');
 await node('LUT A').locator('[data-resize-position="bottom right"]').dispatchEvent('pointerup');
 assert.deepEqual(await page.evaluate(()=>window.resizeEvents),[{name:'LUT A',kind:'resizing',value:true},{name:'LUT A',kind:'resize',size:{width:880,height:900}},{name:'LUT A',kind:'resizing',value:false}]);
 assert.equal(await page.evaluate(()=>window.sdk.length),beforeResizeSdk,'Native resize callback boundary never executes Run/Reset/property commands');checks+=2;
 await page.evaluate(()=>{window.animatedSize['LUT A']={width:900,height:640};window.rerender();});await frames();
 assert.equal(await page.evaluate(()=>window.resizeProps['LUT A'].isVisible),false,'Native animatedSize guard remains authoritative during a collapse animation');
 assert.equal(await page.evaluate(()=>window.resizeProps['LUT B'].isVisible),true);checks+=2;
 await page.evaluate(()=>{delete window.animatedSize['LUT A'];window.rolledUp['LUT A']=true;window.rerender();});await frames();
 assert.equal(await page.evaluate(()=>window.resizeProps['LUT A'].isVisible),false,'A rolled-up Color LUT keeps native resize disabled');
 assert.equal(await node('LUT A').getAttribute('data-hmb-color-lut-native-layout'),null);checks+=2;
 await page.evaluate(()=>{window.rolledUp['LUT A']=false;window.selected=['Other'];window.rerender();});await frames();
 assert.equal(await page.evaluate(()=>window.resizeProps.Other.isVisible),true,'An unrelated selected node retains its original resize behavior');
 assert.equal(await node('Other').locator('.react-flow__resize-control').first().evaluate(element=>getComputedStyle(element).opacity),'1','Unified transparent styling never applies to unrelated nodes');checks+=2;
 await page.evaluate(()=>{window.selected=['LUT A'];window.rerender();});await frames();
 // Remount only D$t: both actual widget instances already exist, and neither
 // emits a new ready event. Initial discovery must skip the first hidden one.
 const beforeHeaderDiscovery=await page.evaluate(()=>window.sdk.length);
 await page.evaluate(()=>{window.headerEpochs['LUT A']=(window.headerEpochs['LUT A']||0)+1;window.rerender();});
 await page.waitForFunction(()=>document.querySelector('[data-visible-carrier="LUT A"] .hmb-color-lut')?.dataset.hmbNativeHeader==='active');await frames();
 await assertMeasurementIsolation('Native header remount discovers the visible second carrier without a ready event');
 assert.equal(await page.evaluate(()=>window.sdk.length),beforeHeaderDiscovery,'Carrier discovery does not issue an SDK request');checks++;
 assert.deepEqual(errors,[],'Actual installed React/header code mounts without runtime errors');
 assert.equal(await actions('LUT A').locator('button').count(),3);
 assert.equal(await actions('LUT B').locator('button').count(),3);
 assert.equal(await node('Other').locator('[data-native-icon="run"]').count(),1);
 assert.equal(await node('Other').locator('[data-native-icon="reset"]').count(),0,'Non-LUT header preserves the original global header choice');
 assert.equal(await node('LUT A').locator('[data-native-host]>div').evaluate(element=>getComputedStyle(element).display),'none');
 assert.equal(await visible('LUT A').locator('[data-hmb-native-identity]').innerText(),'LUT A (HMBColorLUTLibrary)');
 assert.equal(await visible('LUT A').locator('.widget-container').evaluate(element=>element.classList.contains('nodrag')),false);
 assert.equal(await visible('LUT A').locator('.cl-head').evaluate(element=>element.classList.contains('nodrag')),false);
 assert.equal(await visible('LUT A').locator('.cl-work').evaluate(element=>element.classList.contains('nodrag')),true,'Body controls retain the native no-drag surface');
 const portsBefore=await page.locator('[data-port]').evaluateAll(elements=>elements.map(element=>element.dataset.port));
 checks+=11;
 await button('LUT A','run').click();await page.waitForFunction(()=>window.sdk.some(item=>item.type==='ResolveNodeRequest'));
 assert.deepEqual(await page.evaluate(()=>window.sdk.filter(item=>item.type==='ResolveNodeRequest')),[{type:'ResolveNodeRequest',payload:{node_name:'LUT A',debug_mode:false}}]);
 assert.equal(await page.evaluate(()=>window.sdk.filter(item=>/StartFlow|export|upload/i.test(item.type)).length),0);
 await button('LUT B','run').click();await page.waitForFunction(()=>window.sdk.filter(item=>item.type==='ResolveNodeRequest').length===2);
 assert.equal(await page.evaluate(()=>window.sdk.at(-1).payload.node_name),'LUT B','Each portal retains its own native callback owner');checks+=3;
 await button('LUT A','reset').click();await page.waitForFunction(()=>window.sdk.some(item=>item.type==='ResetNodeToDefaultsRequest'));
 assert.deepEqual(await page.evaluate(()=>window.sdk.filter(item=>item.type==='ResetNodeToDefaultsRequest')),[{type:'ResetNodeToDefaultsRequest',payload:{node_name:'LUT A'}}]);checks++;
 await page.evaluate(()=>{window.selected=['LUT A','LUT B','Other'];});
 await button('LUT A','lock').click();await page.waitForFunction(()=>window.nodes.slice(0,2).every(node=>node.data.locked));
 assert.deepEqual(await page.evaluate(()=>window.sdk.filter(item=>item.type==='BatchSetNodeLockStateRequest').at(-1)),
  {type:'BatchSetNodeLockStateRequest',payload:{node_names:['LUT A','LUT B','Other'],lock:true}});
 await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier] [data-language-toggle]').disabled);
 assert.equal(await button('LUT A','run').isDisabled(),true);
 assert.equal(await button('LUT A','unlock').isEnabled(),true,'Native unlock must not be disabled by the LUT widget guard');
 const beforeBlocked=await page.evaluate(()=>window.sdk.length);
 await visible('LUT A').locator('[data-language-toggle]').dispatchEvent('click');
 assert.equal(await page.evaluate(()=>window.sdk.length),beforeBlocked,'LUT property commands remain blocked while locked');
 await visible('LUT A').locator('[data-hmb-native-identity] button[title="Rename node"]').click();
 const nativeRename=visible('LUT A').locator('[data-hmb-native-identity] input');
 assert.equal(await nativeRename.isEnabled(),true,'The original native rename input remains governed by the native header, not the LUT body lock');
 await nativeRename.fill('Temporary scratch name');await nativeRename.press('Escape');
 assert.equal(await visible('LUT A').locator('[data-hmb-native-identity]').innerText(),'LUT A (HMBColorLUTLibrary)');
 await button('LUT A','unlock').click();await page.waitForFunction(()=>window.nodes.every(node=>!node.data.locked));
 await page.waitForFunction(()=>!document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier] [data-language-toggle]').disabled);
 assert.equal(await button('LUT A','run').isEnabled(),true);checks+=8;
 await page.evaluate(()=>{window.selected=['LUT B'];window.failLock=true;});
 const beforeRejected=await page.evaluate(()=>window.sdk.filter(item=>item.type==='BatchSetNodeLockStateRequest').length);
 await button('LUT B','lock').click();
 await page.waitForFunction(count=>window.sdk.filter(item=>item.type==='BatchSetNodeLockStateRequest').length>count,beforeRejected);
 await page.waitForFunction(()=>!window.nodes.find(node=>node.id==='LUT B').data.locked);
 assert.equal(await button('LUT B','run').isEnabled(),true,'Native optimistic lock rollback reaches its original button');
 await page.evaluate(()=>{window.failLock=false;window.selected=['LUT A'];window.nativeStore.flowRunning=true;window.nativeStore.involvedNodes=new Set(['LUT A']);window.nativeStore.resolvingNodes=new Set(['LUT A']);window.nativeStore.nodeResolutionState={'LUT A':'RESOLVING'};window.rerender();});
 assert.equal(await button('LUT A','run').isDisabled(),true);
 assert.equal(await button('LUT B','run').isEnabled(),true,'A different uninvolved node is not gated by this node running');
 assert.equal(await actions('LUT A').locator('[data-native-resolution]').innerText(),'RESOLVING');checks+=4;
 await page.evaluate(()=>{window.nativeStore.flowRunning=false;window.nativeStore.involvedNodes=new Set();window.nativeStore.resolvingNodes=new Set();window.rerender();});
 await frames();
 await page.evaluate(()=>{window.portalButtons=Object.fromEntries(['LUT A','LUT B'].map(name=>[name,document.querySelector(`.react-flow__node[data-id="${name}"] [data-visible-carrier] [data-hmb-native-actions] button`)]));window.cloneGeometryBefore=window.geometryRefreshes.length;});
 // Resize causes nAr to retire/recreate its hidden measurement instance. Use
 // actual YTr cleanup/mount in both orders and leave the visible widget intact.
 await page.evaluate(()=>{window.showMeasurement['LUT A']=false;window.rerender();});
 await page.waitForFunction(()=>!document.querySelector('[data-measurement-carrier="LUT A"]'));await frames();
 await assertMeasurementIsolation('Retiring a hidden measurement instance');
 await page.evaluate(()=>{window.showMeasurement['LUT A']=true;window.measurementEpochs['LUT A']=(window.measurementEpochs['LUT A']||0)+1;window.rerender();});
 await page.waitForFunction(()=>document.querySelector('[data-measurement-carrier="LUT A"] .hmb-color-lut'));await frames();
 await assertMeasurementIsolation('Hidden ready event after visible portal activation');
 await page.setViewportSize({width:1600,height:1000});
 await page.evaluate(()=>{window.measurementEpochs['LUT B']=(window.measurementEpochs['LUT B']||0)+1;window.rerender();});await frames();
 await assertMeasurementIsolation('Resize then second-node measurement remount');
 await page.evaluate(()=>{window.measurementModes['LUT A']='display';window.measurementEpochs['LUT A']=(window.measurementEpochs['LUT A']||0)+1;window.rerender();});await frames();
 assert.equal(await measurement('LUT A').locator('.widget-container').evaluate(element=>element.getClientRects().length),0,'Display-hidden clone exercises the no-layout-rect guard');checks++;
 await assertMeasurementIsolation('Display-none clone mount');
 await page.evaluate(()=>{window.measurementModes['LUT A']='visibility';window.measurementEpochs['LUT A']=(window.measurementEpochs['LUT A']||0)+1;window.rerender();});
 await page.setViewportSize({width:2000,height:1200});await frames();
 await assertMeasurementIsolation('Measurement remount then resize');
 assert.equal(await page.evaluate(()=>['LUT A','LUT B'].every(name=>window.portalButtons[name]===document.querySelector(`.react-flow__node[data-id="${name}"] [data-visible-carrier] [data-hmb-native-actions] button`))),true,'Measurement lifecycle never replaces the original visible React button elements');checks++;
 assert.equal(await page.evaluate(()=>window.geometryRefreshes.length),await page.evaluate(()=>window.cloneGeometryBefore),'Hidden clone lifecycle never invalidates visible native handle geometry');checks++;
 const beforeSteady=await page.evaluate(()=>({...window.nativeRenders}));
 const resizeBeforeSteady=await page.evaluate(()=>({renders:{...window.resizeRenders},geometry:window.geometryRefreshes.length}));
 await page.evaluate(()=>new Promise(resolve=>{let frames=0;const step=()=>++frames>=20?resolve():requestAnimationFrame(step);requestAnimationFrame(step);}));
 assert.deepEqual(await page.evaluate(()=>window.nativeRenders),beforeSteady,'Portal activation has no recurring observer/render loop');checks++;
 assert.deepEqual(await page.evaluate(()=>({renders:{...window.resizeRenders},geometry:window.geometryRefreshes.length})),resizeBeforeSteady,'Frame observer and native geometry refresh settle without a resize/render loop');checks++;
 // Native collapsed-parameter footers have opacity:0, while their children
 // retain visibility:visible and real rects. They must never own a portal.
 await page.evaluate(()=>{window.measurementModes['LUT A']='opacity';window.measurementEpochs['LUT A']=(window.measurementEpochs['LUT A']||0)+1;window.rerender();});
 await frames();
 assert.equal(await measurement('LUT A').evaluate(element=>getComputedStyle(element).opacity),'0');
 assert.equal(await measurement('LUT A').locator('.widget-container').evaluate(element=>getComputedStyle(element).visibility),'visible');
 assert.equal(await measurement('LUT A').locator('.widget-container').evaluate(element=>element.getClientRects().length>0),true);checks+=3;
 await assertMeasurementIsolation('Opacity-zero native footer clone');
 await page.evaluate(()=>{window.headerEpochs['LUT A']=(window.headerEpochs['LUT A']||0)+1;window.rerender();});
 await frames();
 await assertMeasurementIsolation('Native header rediscovery beside opacity-zero footer');
 assert.equal(await actions('LUT A').locator('button').count(),3,'The visible widget keeps all three native actions');checks++;
 await page.evaluate(()=>{window.measurementModes['LUT A']='visibility';window.measurementEpochs['LUT A']++;window.rerender();});
 await frames();
 await page.evaluate(()=>{window.expanded['LUT A']=false;window.rerender();});
 await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier] .hmb-color-lut').dataset.hmbNativeHeader==='fallback');
 await frames();
 assert.equal(await page.evaluate(()=>window.resizeProps['LUT A'].isVisible),false,'Collapsed node preserves the native no-resize gate even when selected');
 assert.equal(await node('LUT A').getAttribute('data-hmb-color-lut-native-layout'),null,'Collapse retires only this frame marker');
 assert.equal(await page.evaluate(()=>window.resizeProps['LUT B'].isVisible),true,'Collapsing A leaves unselected B resizable');checks+=3;
 assert.equal(await actions('LUT A').locator('button').count(),0);
 assert.equal(await visible('LUT A').locator('.widget-container').evaluate(element=>element.classList.contains('nodrag')),true);
 assert.equal(await node('LUT A').locator('[data-native-host] [data-native-icon="run"]').count(),1);
 assert.equal(await node('LUT A').locator('[data-native-host] [data-native-icon="reset"]').count(),0,'Collapsed/fallback host preserves global header choices');
 assert.equal(await actions('LUT B').locator('button').count(),3);checks+=5;
 await page.evaluate(()=>{window.expanded['LUT A']=true;window.rerender();});
 await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier] .hmb-color-lut').dataset.hmbNativeHeader==='active');
 await page.evaluate(()=>{window.epochs['LUT A']=(window.epochs['LUT A']||0)+1;window.rerender();});
 await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier] .hmb-color-lut')?.dataset.hmbNativeHeader==='active');
 assert.equal(await actions('LUT A').locator('button').count(),3);
 assert.equal(await actions('LUT B').locator('button').count(),3);
 await assertMeasurementIsolation('Visible YTr remount while measurement clone remains');
 assert.deepEqual(await page.locator('[data-port]').evaluateAll(elements=>elements.map(element=>element.dataset.port)),portsBefore);
 assert.equal(await page.locator('[data-wire="A-to-B"]').getAttribute('data-source'),'LUT A-output');checks+=4;
 await page.evaluate(()=>{window.showWidget['LUT A']=false;window.rerender();});
 await page.waitForFunction(()=>!document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier]'));
 await frames();
 assert.equal(await node('LUT A').locator('[data-native-host] [data-native-icon="run"]').count(),1);
 assert.notEqual(await node('LUT A').locator('[data-native-host]>div').evaluate(element=>getComputedStyle(element).display),'none','Hidden measurement alone cannot hide the native fallback header');
 assert.notEqual(await measurement('LUT A').locator('.hmb-color-lut').getAttribute('data-hmb-native-header'),'active','Hidden clone stays inactive when its visible owner retires');checks+=2;
 assert.equal(await actions('LUT B').locator('button').count(),3);
 await page.evaluate(()=>{window.showWidget['LUT A']=true;window.rerender();});
 await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="LUT A"] [data-visible-carrier] .hmb-color-lut')?.dataset.hmbNativeHeader==='active');
 await assertMeasurementIsolation('Visible widget returns beside surviving measurement clone');
 await button('LUT A','run').click();await page.waitForFunction(()=>window.sdk.filter(item=>item.type==='ResolveNodeRequest').length===3);
 assert.equal(await page.evaluate(()=>window.sdk.filter(item=>item.type==='ResolveNodeRequest').at(-1).payload.node_name),'LUT A');
 assert.deepEqual(errors,[]);checks+=4;
 // The LUT widget supplies the same stable slots as each product widget's own
 // boundary regression. This loop tests the actual native host allowlist and
 // callbacks for every node type, without claiming their product body is LUT.
 const studioTypes=['HMBAgentLibrary','HMBFinishLookLibrary','HMBImageAssetLibrary','HMBImageBash',
  'HMBImageGeneration','HMBSeedanceGeneration','HMBPromptLibrary','HMBVideoPickerLibrary'];
 for(const type of studioTypes){
  await page.evaluate(type=>{window.nodes.find(n=>n.id==='LUT B').data.node_type=type;
   window.epochs['LUT B']=(window.epochs['LUT B']||0)+1;window.headerEpochs['LUT B']=(window.headerEpochs['LUT B']||0)+1;window.rerender();},type);
  await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="LUT B"]')?.getAttribute('data-hmb-color-lut-native-layout')==='active'
   &&document.querySelectorAll('.react-flow__node[data-id="LUT B"] [data-visible-carrier] [data-hmb-native-actions] button').length===3);
  assert.equal(await actions('LUT B').locator('button').count(),3,type+': native Lock/Reset/Run ownership');
  assert.equal(await page.evaluate(()=>window.resizeProps['LUT B'].isVisible),true,type+': unselected resize');
  await button('LUT B','lock').click();
  await page.waitForFunction(()=>window.nodes.find(n=>n.id==='LUT B').data.locked===true);
  await button('LUT B','unlock').click();
  await page.waitForFunction(()=>window.nodes.find(n=>n.id==='LUT B').data.locked===false);
  const before=await page.evaluate(()=>window.sdk.filter(item=>item.type==='ResolveNodeRequest').length);
  await button('LUT B','run').click();
  await page.waitForFunction(before=>window.sdk.filter(item=>item.type==='ResolveNodeRequest').length===before+1,before);
  assert.equal(await page.evaluate(()=>window.sdk.filter(item=>item.type==='ResolveNodeRequest').at(-1).payload.node_name),'LUT B');
  checks+=5;
 }
 assert.deepEqual(errors,[],'Every supported native host type remounts and portals without React errors');checks++;
 const evidence={status:'PASS',checks,actual_installed_react:true,actual_native_header:true,actual_native_action_callbacks:true,actual_ytr_visible_and_hidden_measurement_instances:true,
  native_host_allowlist_types:studioTypes,product_body_in_allowlist_loop:'LUT slot adapter; separate product widget regressions required',
  actual_native_resize_jsx:true,actual_frame_active_hook:true,actual_installed_resize_css:true,
  sdk_transport:'synthetic recorded boundary',native_icons:'synthetic SVG markers; actual assets require live-app verification',reactflow_node_wrapper:'synthetic wrapper; selection/drag require live-app verification',
  resize_component:'synthetic sie boundary because native ReactFlow store is absent; actual native JSX props, active hook, CSS, hit tests and callbacks verified',
  source_sha256:sha(original),candidate_sha256:sha(patched),native_header_sha256:sha(header),native_callbacks_sha256:sha(actionCallbacks),
  paid_requests:0,live_engine_requests:0,installed_files_changed:0};
 if(process.env.HMB_NATIVE_HEADER_REPORT_DIR){const report=process.env.HMB_NATIVE_HEADER_REPORT_DIR;fs.mkdirSync(report,{recursive:true});
  fs.writeFileSync(path.join(report,'native-header-react-fixture.json'),JSON.stringify(evidence,null,2));await page.screenshot({path:path.join(report,'native-header-react-fixture.png')});}
 console.log(JSON.stringify(evidence));
}finally{
 await browser?.close();await new Promise(resolve=>server.close(resolve));
}
