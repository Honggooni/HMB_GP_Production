// Installed React/native header/VZ/collapse functions, actual Asset/Picker
// bodies; SDK, ReactFlow store/animation and icon lookup are isolated stubs.
// No running editor, installed files, provider or paid generation is used.
import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {prepareNativeEditor,readNativeEditorCSS,nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url)),{original,patched}=prepareNativeEditor(root);
const between=(text,start,end)=>{const a=text.indexOf(start),b=text.indexOf(end,a+start.length);assert.ok(a>=0&&b>a,start);return text.slice(a,b)};
const alias=original.indexOf('S=u(p(),1),C=h(),w=x(),T=u(y())'),runtime=original.slice(0,original.indexOf(',E=`modulepreload`',alias))+';';
const jsx=between(original,'var Wn=s(','function Gn('),helper=fs.readFileSync(path.join(root,'resources/editor/hmb-color-lut-native-header.js'),'utf8');
const header=between(patched,'var D$t=({node_name:',',O$t=')+';',icon='var '+between(original,'VZ=S.memo(',"VZ.displayName=`IconRenderer`;")+"VZ.displayName=`IconRenderer`;";
const collapse=between(patched,'function ejr(','function tjr('),geometry=between(original,'function Sjr(','function Ejr('),baseStyle=between(original,'function vBt(','var yBt='),anchors=between(original,'function xAr(','function TAr(');
const arrow=between(original,'let ve=(0,S.useCallback)',',be=(0,S.useCallback)').replace('let ve=','const ve=')+';';
const floor=between(patched,'(0,S.useEffect)(()=>{if(hmbIsNativeStudioType(e.node_type)&&O)return;','hmbUseNativeStudioCollapseState(e,O,k').replace(/,$/,';');
const fullEjr=between(patched,'function Ejr(','var Djr=S.memo(Ejr)');
const alterPrefix='C=m(`AlterParameterDetailsResultSuccess`,',alterExpression=between(patched,alterPrefix,'),E=m(`AlterParameterDetailsResultFailure`').slice(alterPrefix.length);
const metadataPrefix='p=m(`SetNodeMetadataResultSuccess`,',metadataExpression=between(patched,metadataPrefix,'),h=m(`SetNodeMetadataResultFailure`').slice(metadataPrefix.length);
const nativeAnimation=between(original,'function MAr(){','function NAr(').replace('function MAr(){','MAr=function(){')+';';
const nativeQueue=between(original,'function pu(e,t){let r=[],i=new Map,a=[]','function bu(e){return{id:e.id,type:`remove`}')+'\n'+between(original,'function Du(e){let[t,r]=(0,S.useState)(BigInt(0))','var Pu=e=>').replace('function Nu(){','Nu=function(){')+';';
const nativeStoreUpdater=between(original,'function au(e){let{setNodes:t,setEdges:r','function ou(){return typeof window')
 .replace('function au(e){','function HmbFixtureStoreUpdater(e){').replace('Pl(ru,Al)','Pl(hmbFixtureStoreMethods)')
 .replaceAll('d.current=iu','d.current=hmbFixtureStoreDefaults').replaceAll('useRef)(iu)','useRef)(hmbFixtureStoreDefaults)')
 .replaceAll('of nu','of hmbFixtureNodePropKeys').replaceAll('nu.map','hmbFixtureNodePropKeys.map');
const nativeChangesPrefix='bn=(0,S.useCallback)(',nativeChangesEnd=',[C,b,x,yn,on,Zt,A,N.showHelperLines,Ve,Ue,Et,Dt,ze,ut])';
const nativeChanges=between(patched,nativeChangesPrefix,nativeChangesEnd).slice(nativeChangesPrefix.length);
const css=readNativeEditorCSS(root);
const types=['HMBColorLUTLibrary','HMBAgentLibrary','HMBFinishLookLibrary','HMBImageAssetLibrary','HMBImageBash','HMBImageGeneration','HMBSeedanceGeneration','HMBPromptLibrary','HMBVideoPickerLibrary'];
const stubs=String.raw`
window.sdk=[];window.forbidden=0;window.geometry=[];window.animations=[];window.pendingRender=false;window.theme='dark';window.store=[];
window.rr=()=>{if(!window.renderApp||window.pendingRender)return;window.pendingRender=true;queueMicrotask(()=>{window.pendingRender=false;window.renderApp()})};
const setNodes=fn=>{window.store=typeof fn==='function'?fn(window.store):fn;window.rr()};
const getNodes=()=>window.store,updateNode=(name,fn)=>setNodes(nodes=>nodes.map(n=>n.id===name?fn(n):n));
var Nu=()=>({getNodes,setNodes,updateNode}),md=()=>name=>window.geometry.push(name),FEr=()=>refresh;
const refresh=name=>window.geometry.push(name);var KZ=()=>({settings:{nodeHeaderItems:['lock','reset','run'],nodeAnimationEnabled:false}});
var MAr=()=>({snapToFinal(){},animatePush(_a,_b,done,targets){window.animations.push([...targets.values()]);done()},rollUpEnabled:true,falloffRadius:1500});
var Xd={request:async(type,payload)=>{window.sdk.push({type,payload:structuredClone(payload)});if(type!=='SetNodeMetadataRequest'){window.forbidden++;throw Error('Forbidden synthetic command '+type)}while(window.nativeActiveTweens)await new Promise(resolve=>requestAnimationFrame(resolve));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));setNodes(nodes=>nodes.map(n=>n.id===payload.node_name?{...n,data:{...n.data,metadata:{...n.data.metadata,...payload.metadata}}}:n));return {}}};
var FAr=()=>({displacedPositions:new Map}),JAr=(_n,map)=>map,QAr=(_n,map)=>map,WBt=async()=>{};
const named=n=>p=>(0,R.jsx)('svg',{'data-action-icon':n,width:16,height:16});
var XA=named('lock'),ZA=named('unlock'),lL=named('run'),QN=named('reset'),uT=named('start'),VC=named('copy'),DE=named('duplicate'),wz=named('delete'),SO=named('group'),IP=named('settings'),ZM=named('rename'),bx=named('collapsed'),_x=named('expanded'),Zye=named('unresolved');
var fW=p=>(0,R.jsx)('button',{...p,type:'button'}),eq=p=>(0,R.jsx)('span',{children:p.children}),tq=p=>p.children,nq=p=>(0,R.jsx)('span',{hidden:true,children:p.children});
var OQ=()=>null,EQ=()=>null,qZ=()=>({openModal(){}}),IQ=()=>false,MQ=()=> 'colorful';
var wQ=fn=>fn({renameRequestedNodeId:null,setRenameRequestedNodeId(){}});wQ.getState=()=>({selectedNodes:[]});
var PQ=(_category,icon)=>({icon:icon||'image',backgroundStyle:{backgroundColor:'rgb(91, 33, 130)'},textColorClass:'',inputStyle:{},buttonClass:'',buttonStyle:{},disabledButtonClass:''});
var _Qt=()=>false,uJ=()=>false,dJ=fn=>fn({nodeResolutionState:{},involvedNodes:new Set,resolvingNodes:new Set,nodeErrors:{}}),fJ=fn=>fn,T$t=()=>null;
var AQ=()=>({}),jQ=()=>'',FQ=fn=>fn?event=>{if(!event.target.closest('button,input,a,select,textarea,.nodrag'))fn()}:undefined;
var lUt=async()=>{},ig={success(){},error(){}},QV={},rq=()=>null,pBt=()=>null,kQ=['lock','reset','run'];
var FZ=()=>({resolvedTheme:window.theme}),iW=(...values)=>values.filter(Boolean).join(' '),BZ=n=>n;
var zZ=({name,className})=>(0,R.jsx)('svg',{'data-actual-icon':name,className,viewBox:'0 0 16 16',children:(0,R.jsx)('path',{d:'M2 2h12v12H2z'})});
var skr=x=>Math.max(600,Number(x)||600);
var d8=({param})=>(0,R.jsx)('i',{'data-preserved-handle':param.parameter_name,'data-is-connectable':String(param.ui_options?.isConnectable),'data-mode':param.modes.join(','),style:{position:'absolute',width:1,height:1}});
`;
const app=String.raw`
import mountAsset from '/asset.js';import mountPicker from '/picker.js';
const ownSurface={HMBColorLUTLibrary:'cl-head',HMBAgentLibrary:'agent-topbar',HMBFinishLookLibrary:'hmb-finish-look__topbar',HMBImageBash:'hmb-image-bash-header__row',HMBImageGeneration:'hmb-image-generation-header__row',HMBSeedanceGeneration:'hmb-seedance-shot__row',HMBPromptLibrary:'topbar'};
const uid=n=>'aaaaaaaa-aaaa-4aaa-8aaa-'+String(n).padStart(12,'0');
window.values={};window.controllers={};window.bodyCommands=[];window.carrierEpoch={};
window.beginWorkflowLoad=()=>hmbNativeStudioResetCollapseIntents();
window.overwriteCollapsedProp=collapsed=>setNodes(nodes=>nodes.map(node=>({...node,data:{...node.data,collapsed,metadata:{...node.data.metadata,collapsed}}})));
function Carrier({data}){const ref=(0,S.useRef)(null);(0,S.useLayoutEffect)(()=>{
 const c=ref.current,type=data.node_type;let controller;
 if(type==='HMBImageAssetLibrary'||type==='HMBVideoPickerLibrary'){
  const mount=type==='HMBImageAssetLibrary'?mountAsset:mountPicker;
  controller=mount(c,{nodeName:data.node_name,value:window.values[data.node_name],onChange:value=>{window.bodyCommands.push({type,value});return Promise.resolve()}});
 }else{
  c.dataset.hmbColorLutWidget='true';c.dataset.hmbNativeNodeType=type;
  c.innerHTML='<header class="'+ownSurface[type]+' synthetic-studio-header"><div data-hmb-native-identity></div><div data-hmb-native-actions></div><span data-header-blank>Blank header area</span><button data-header-control>Control</button></header><p>Preserved input and output body</p>';
  c.dispatchEvent(new CustomEvent('hmb-color-lut-header-ready',{bubbles:true,detail:{container:c}}));
 }
 window.controllers[data.node_name]=controller;
 return()=>{controller?.cleanup();c.dispatchEvent(new CustomEvent('hmb-color-lut-header-retire',{bubbles:true,detail:{container:c}}))};
 },[data.node_name,data.node_type]);return(0,R.jsx)('div',{ref,'data-body-carrier':data.node_name});}
function Row({node}){const e=node.data,[O,k]=(0,S.useState)(e.collapsed||false),[A,j]=(0,S.useState)(e.metadata?.rolledUp||false),ee=150,me=updateNode;
 const {doCollapse:de,animatedSize:fe}=ejr(e.node_name,{getDimensions:(t,r,i,a,o)=>hmbNativeStudioDimensions(e.node_type,t,r,i,a,e.metadata.size,o),onBeforeAnimate:(t,r)=>{if(!r){if(t&&window.hideBodyBeforeAnimation)document.querySelectorAll('[data-body-carrier]').forEach(body=>body.style.display='none');setNodes(nodes=>Cjr(nodes,e.node_name,t))}},applyFinalState:(t,r)=>setNodes(nodes=>wjr(nodes,e.node_name,t,r)),getParentId:n=>n.parentId},{fallbackWidth:600,fallbackHeight:ee});
 ORIGINAL_FLOOR
 (0,S.useEffect)(()=>{e.collapsed!==void 0&&e.collapsed!==O&&k(e.collapsed)},[e.collapsed]);
 (0,S.useEffect)(()=>{j(!!e.metadata?.rolledUp)},[e.metadata?.rolledUp]);
 ORIGINAL_ARROW
 const hmbNativeFrameActive=hmbUseColorLUTFrameActive(e.node_type,e.node_name),style=hmbNativeStudioNodeStyle(e.node_type,fe,O,ee,600,false,A);
 const inputs=e.elements.filter(p=>(p.modes||[]).includes('input')),outputs=e.elements.filter(p=>(p.modes||[]).includes('output'));
 return(0,R.jsx)('article',{className:'react-flow__node','data-id':node.id,style:{position:'relative',width:node.width,height:node.height},children:(0,R.jsxs)('div',{'data-node-frame':true,style,children:[
  (0,R.jsxs)('div',{className:'relative',children:[(0,R.jsx)(D$t,{node_name:e.node_name,node_type:e.node_type,node_icon:e.node_icon,node_category:'HMB',collapsed:O,onToggleCollapse:ve,onDoubleClick:ye,hmbHostExpanded:!O&&!A,hmbHostRestoreView:e.hmb_native_studio_restore_view,handlePlayClick:()=>window.forbidden++,handleLockToggle:()=>window.forbidden++,onReset:()=>window.forbidden++}),
  (0,R.jsx)(SAr,{collapsed:O||A,allFlattenedElements:e.elements,controlElements:[],connectedInputs:inputs.map(p=>p.name),connectedOutputs:outputs.map(p=>p.name),data:e,optimisticLocked:null,handleElementChange(){},handleParameterAlter(){}})]}),
  !O&&!A&&(0,R.jsx)(Carrier,{data:e},node.id+'-body-'+(window.carrierEpoch[node.id]||0))]})});
}
const root=w.createRoot(document.querySelector('#app'));window.renderApp=()=>root.render((0,R.jsxs)(Au,{children:[(0,R.jsx)(HmbFixtureStoreUpdater,{nodes:window.store}),window.store.map(node=>(0,R.jsx)(Row,{node},node.id))]}));
window.load=(type,view='expanded',collapsed=false,icon='image',hasSize=true)=>{
 const name='Synthetic '+type;window.store=[{id:name,width:collapsed?320:1400,height:collapsed?64:1200,style:{width:collapsed?320:1400,height:collapsed?64:1200},measured:{width:collapsed?320:1400,height:collapsed?64:1200},data:{node_name:name,node_type:type,node_icon:icon,collapsed,metadata:{synthetic_diagnostic:true,...(hasSize?{size:{width:1400,height:1200}}:{}),...(collapsed?{collapsed:true,hmb_native_studio_view:{version:1,view}}:{})},...(collapsed?{hmb_native_studio_restore_view:{version:1,view}}:{}),elements:[{id:'input-original',name:'input_original',type:'str',modes:['input'],value:'0 OFF'},{id:'output-original',name:'output_original',type:'str',modes:['output'],value:'Task job-preserved / image.png / video.mov'}],shot:{shot_uuid:'preserved-shot',number:2},results:{job:'job-preserved',path:'original.png'}}}];
 window.values[name]=type==='HMBImageAssetLibrary'?{project_root:'C:/fixture/project',project_id:'project',assets:[]}:type==='HMBVideoPickerLibrary'?{language:'ko',runtime_instance_id:'icon-header-test',state_revision:1,picker_shots:[{workspace_uuid:uid(1),number:1,name:'Shot 1',video_asset_uids:[],selected_video_uids:[]}],active_picker_shot_uuid:uid(1),videos:[]}:{};
 window.sdk=[];window.bodyCommands=[];window.carrierEpoch={};window.renderApp();return name;
};window.ready=true;
`.replace('ORIGINAL_FLOOR',floor).replace('ORIGINAL_ARROW',arrow);
const fullEjrStubs=String.raw`
const subscribeToEvent=()=>()=>{};
const emptyEdges=[];var Skr=()=>({duplicateNodes(){}}),vjr=()=>({enabled:false,onMouseEnter(){},onMouseLeave(){}}),yjr=[],vd=()=>emptyEdges,IEr=()=>{},sJ=()=>({subscribeToEvent}),mq=()=>{},DOr=()=>({weight:1,rowKind:'fill',rowClass:'',contentClass:''});
var hjr=()=>({}),pjr=()=>'',mjr=()=>({}),gjr=()=>({}),LQ=()=>({draggingHandle:null,setDraggingHandle(){}}),AOr=()=>'',HZ=fn=>fn({colorTheme:'colorful'}),oq=()=>'';
var sjr=()=>null,Nkr=()=>null,sie=()=>null,sAr=()=>null,ckr=()=>false;
var nAr=({collapsed,nodeName})=>collapsed?null:(0,R.jsx)(Carrier,{data:getNodes().find(node=>node.id===nodeName).data});
`;
const controlledStoreStubs=String.raw`
window.fixtureStoreCommits=0;window.fixtureDimensionEvents=0;window.nativeActiveTweens=0;window.nativeFoldIntermediateSamples=[];
const hmbFixtureSubscribers=new Set(),hmbFixtureNodePropKeys=['nodes'],hmbFixtureStoreDefaults={};
const hmbFixtureStore={nodes:[],edges:[],nodeLookup:new Map,parentLookup:new Map,edgeLookup:new Map,hasDefaultNodes:false,onNodesChangeMiddlewareMap:new Map,panZoom:null};let hmbFixtureStoreVersion=0;
const hmbFixtureStoreApi={getState:()=>hmbFixtureStore,setState:patch=>{Object.assign(hmbFixtureStore,patch);hmbFixtureStoreVersion++;for(const notify of hmbFixtureSubscribers)notify()}};
hmbFixtureStore.setNodes=nodes=>{if(++window.fixtureStoreCommits>1000)throw Error('Controlled native fixture exceeded its store commit budget');hmbFixtureStore.nodeLookup=new Map(nodes.map(node=>[node.id,{...node,internals:{userNode:node}}]));hmbFixtureStoreApi.setState({nodes})};
for(const name of ['setEdges','setMinZoom','setMaxZoom','setTranslateExtent','setNodeExtent','reset','setDefaultNodesAndEdges'])hmbFixtureStore[name]=()=>{};
const hmbFixtureStoreMethods=state=>({setNodes:state.setNodes,setEdges:state.setEdges,setMinZoom:state.setMinZoom,setMaxZoom:state.setMaxZoom,setTranslateExtent:state.setTranslateExtent,setNodeExtent:state.setNodeExtent,reset:state.reset,setDefaultNodesAndEdges:state.setDefaultNodesAndEdges});
var Fl=()=>hmbFixtureStoreApi,Pl=selector=>{S.useSyncExternalStore(notify=>{hmbFixtureSubscribers.add(notify);return()=>hmbFixtureSubscribers.delete(notify)},()=>hmbFixtureStoreVersion);return selector(hmbFixtureStore)},fu=()=>({}),Mu=state=>!!state.panZoom;
var Cu=value=>!!value?.id,wu=value=>!!value?.id,Eu=S.useLayoutEffect,kAr=()=>x=>x,NAr=value=>value.toW>value.fromW||value.toH>value.fromH,AAr=0,jAr=()=>0;
var vo=callback=>{let stopped=false,time=0;window.nativeActiveTweens++;const stop=()=>{if(stopped)return;stopped=true;window.nativeActiveTweens--};const tick=()=>{if(stopped)return;callback(time);time+=20;if(!stopped)requestAnimationFrame(tick)};requestAnimationFrame(tick);return{stop}};
const makeNativeDimensionChanges=(E,N,w,x,yn,Ct,C)=>NATIVE_CHANGES;
hmbFixtureStore.onNodesChange=makeNativeDimensionChanges({current:null},{showHelperLines:false},{get current(){return window.store}},setNodes,()=>{}, {current:{}},changes=>{if(changes.length)setNodes(nodes=>hu(changes,nodes))});
const hmbFixtureResizeObserver=new ResizeObserver(entries=>{for(const entry of entries){const node=window.store.find(node=>node.id===entry.target.dataset.id);if(!node)continue;const dimensions={width:entry.target.offsetWidth,height:entry.target.offsetHeight};if(window.nativeActiveTweens&&node.data.collapsed&&dimensions.width>321&&dimensions.height>65)window.nativeFoldIntermediateSamples.push({type:node.data.node_type,...dimensions});if(node.measured?.width===dimensions.width&&node.measured?.height===dimensions.height)continue;window.fixtureDimensionEvents++;hmbFixtureStore.onNodesChange([{type:'dimensions',id:node.id,dimensions}])}});
window.observeNativeFixtureNode=node=>hmbFixtureResizeObserver.observe(node);
KZ=()=>({settings:{nodeHeaderItems:['lock','reset','run'],nodeAnimationEnabled:true,nodeAnimationDurationMs:120,nodeAnimationEasing:'linear',nodeRollUpDurationMs:120,nodeRollUpEasing:'linear'}});
`.replace('NATIVE_CHANGES','('+nativeChanges+')');
const fullNative=process.env.HMB_ICON_FULL_EJR!=='0';
const delayedNativeRefresh=`
const makeNativeAlter=(w,An,f,x,A,hmbIsNativeStudioType)=>(${alterExpression});
const makeNativeMetadata=(x,T,pt)=>(${metadataExpression});
window.beginNativeStaleRefresh=()=>{
 const old=structuredClone(window.store[0]);delete old.style;delete old.measured;let resolveReply;
 const alter=makeNativeAlter({get current(){return window.store}},async()=>true,()=>new Promise(resolve=>resolveReply=resolve),setNodes,refresh,hmbIsNativeStudioType);
 const pending=alter({},{node_name:old.id,parameter_name:'PROJECT_ROOT',type:'str'});
 window.completeNativeStaleRefresh=async()=>{resolveReply(old);await pending;makeNativeMetadata(setNodes,{current:[]},()=>{})({},{node_name:old.id,metadata:{...old.data.metadata,collapsed:false,rolledUp:false}});await new Promise(resolve=>requestAnimationFrame(resolve));setNodes(nodes=>nodes.map(node=>{const bounds=document.querySelector('.react-flow__node[data-id="'+CSS.escape(node.id)+'"]').getBoundingClientRect();return{...node,measured:{width:bounds.width,height:bounds.height}}}));};
};
`;
const hostApp=fullNative?app.replace(/function Row\(\{node\}\)\{[\s\S]*?\nconst root=/,`function Row({node}){const ref=S.useRef(null);S.useLayoutEffect(()=>{window.observeNativeFixtureNode(ref.current)},[]);const legacyMin=node.data.node_type==='HMBPromptLibrary'?{minWidth:760,minHeight:240}:node.data.node_type==='HMBVideoPickerLibrary'?{minWidth:1040,minHeight:1040}:{};return(0,R.jsx)('article',{ref,className:'react-flow__node','data-id':node.id,style:{position:'relative',width:node.width,height:node.height,...legacyMin},children:(0,R.jsx)(Ejr,{data:node.data,selected:false})});}\nconst root=`):app;
const code=runtime+'\n'+jsx+'\n'+stubs+'\n'+baseStyle+'\n'+geometry+'\n'+anchors+'\n'+helper+'\n'+icon+'\n'+header+'\n'+collapse+'\n'+nativeQueue+'\n'+nativeStoreUpdater+'\n'+controlledStoreStubs+'\n'+nativeAnimation+'\n'+(fullNative?fullEjrStubs+'\n'+fullEjr+'\n'+delayedNativeRefresh:'')+'\n'+hostApp;
if(process.env.HMB_ICON_HEADER_DEBUG_SOURCE)fs.writeFileSync(process.env.HMB_ICON_HEADER_DEBUG_SOURCE,code);
const html='<!doctype html><meta charset="utf-8"><style>'+css+'\nbody{margin:12px;background:#111;color:#eee}.react-flow__node{flex:0 0 auto}.synthetic-studio-header{height:64px;display:flex;align-items:center;gap:12px;background:#142236}.synthetic-studio-header [data-hmb-native-identity]{flex:1;min-width:0}.synthetic-studio-header [data-hmb-native-actions]{display:flex}.synthetic-studio-header [data-hmb-native-actions]>div{display:flex}#app{display:flex;align-items:flex-start;gap:40px} [data-node-frame]>.relative{position:relative}</style><main id="app"></main><script type="module" src="/app.js"></script>';
const server=http.createServer((req,res)=>{let value=html,mime='text/html';if(req.url==='/app.js'){value=code;mime='text/javascript'}else if(req.url==='/asset.js'){value=fs.readFileSync(path.join(root,'widgets/HMBImageAssetLibraryWidget.js'),'utf8');mime='text/javascript'}else if(req.url==='/picker.js'){value=fs.readFileSync(path.join(root,'widgets/HMBVideoPickerLibraryWidget_v032.js'),'utf8');mime='text/javascript'}else if(req.url==='/fixture-icon.svg'){value='<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="pink"/></svg>';mime='image/svg+xml'}res.setHeader('Content-Type',mime);res.end(value)});await new Promise(r=>server.listen(0,'127.0.0.1',r));
const pw=nativeTestPlaywright();let browser;const report={scope:'Exact native React/Ejr/D$t/ejr/MAr/SAr/nodeQueue/StoreUpdater with actual browser ResizeObserver and Asset/Picker bodies; isolated store API/RAF clock/SDK/icon lookup and seven other bodies; SDK replies after animation completion',checks:0,cases:[],paid_calls:0,live_editor_actions:0};
try{
 browser=await pw.chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage({viewport:{width:1900,height:1500}}),errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('ICON fixture pageerror: '+e.message+' / '+e.stack)});page.setDefaultTimeout(8000);const origin=`http://127.0.0.1:${server.address().port}`;await page.route('**/*',r=>r.request().url().startsWith(origin)?r.continue():r.abort());await page.goto(origin);await page.waitForFunction(()=>window.ready);
 const settle=async()=>{await page.waitForFunction(()=>window.nativeActiveTweens===0);return page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(r))))))};
 for(const type of types){
  const name=await page.evaluate(t=>window.load(t,'expanded',false,'image',!['HMBSeedanceGeneration','HMBImageGeneration'].includes(t)),type);await page.waitForFunction(()=>document.querySelector('[data-hmb-color-lut-native-layout=active]'));await settle();
  const before=await page.evaluate(()=>structuredClone(window.store[0].data)),node=page.locator('.react-flow__node'),beforeMinimum=await node.evaluate(el=>el.style.minHeight);
  if(!['HMBImageAssetLibrary','HMBVideoPickerLibrary'].includes(type)){
   await node.locator('[data-header-control]').dblclick();assert.notEqual(await page.evaluate(()=>window.store[0].data.metadata.rolledUp),true,type+' header controls never toggle compact');report.checks++;
  }
  const arrow=node.locator('[data-hmb-native-identity] button').first();assert.equal(await arrow.count(),1);
  await arrow.click();await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();await settle();
  const folded=await page.evaluate(()=>{const n=window.store[0],el=document.querySelector('[data-hmb-native-icon-header]'),b=el.getBoundingClientRect();return{width:n.width,height:n.height,measured:n.measured,dom:[b.width,b.height],body:!!document.querySelector('[data-body-carrier]'),text:el.innerText,buttons:el.querySelectorAll('button').length,icon:!!el.querySelector('[data-hmb-soft-link-icon="02"]'),ports:[...document.querySelectorAll('[data-preserved-handle]')].map(e=>[e.dataset.preservedHandle,e.dataset.isConnectable]),data:n.data}});
  assert.deepEqual([folded.width,folded.height,folded.measured.width,folded.measured.height,...folded.dom],[320,64,320,64,320,64],type+' all capsule geometry sources agree');assert.equal(folded.body,false);assert.equal(folded.text,'Double Click to Unlock');assert.equal(folded.buttons,0);assert.equal(folded.icon,true);assert.deepEqual(folded.ports,[['input_original','false'],['output_original','false']]);assert.deepEqual(folded.data.elements,before.elements);assert.deepEqual(folded.data.shot,before.shot);assert.deepEqual(folded.data.results,before.results);assert.deepEqual(folded.data.metadata.size,before.metadata.size);assert.equal(await node.getAttribute('data-hmb-color-lut-native-layout'),null);report.checks+=11;
  const appearance=await node.locator('[data-hmb-native-icon-header]').evaluate(el=>{const s=getComputedStyle(el),disc=el.querySelector('[data-hmb-capsule-disc]'),label=el.querySelector('[data-hmb-capsule-label]'),d=disc.getBoundingClientRect(),l=getComputedStyle(label);return{radius:s.borderRadius,disc:[d.width,d.height],discRadius:getComputedStyle(disc).borderRadius,font:l.fontSize,nowrap:l.whiteSpace,overflow:label.scrollWidth>label.clientWidth,nodrag:!!el.closest('.nodrag'),role:el.getAttribute('role')}});assert.deepEqual(appearance,{radius:'999px',disc:[52,52],discRadius:'50%',font:'17px',nowrap:'nowrap',overflow:false,nodrag:false,role:'button'},type+' selected capsule fits one line and retains native drag surface');report.checks++;
  if(fullNative){assert.deepEqual(await node.evaluate(el=>{const b=el.getBoundingClientRect();return[b.width,b.height]}),[320,64],type+' outer native geometry overrides retained widget minimum only while a capsule');report.checks++;}
  const sdkBeforeSingle=await page.evaluate(()=>window.sdk.length);await page.getByRole('button',{name:'Expand '+name,exact:true}).click();await settle();assert.equal(await node.locator('[data-hmb-native-icon-header]').count(),1,type+' single click selects but never expands');assert.equal(await page.evaluate(()=>window.sdk.length),sdkBeforeSingle,type+' single click does not call native collapse metadata');report.checks+=2;
  assert.deepEqual(await node.locator('[data-hmb-native-icon-header]').evaluate(el=>{let reached=false;const parent=el.closest('.react-flow__node'),listen=()=>reached=true;parent.addEventListener('pointerdown',listen,{once:true});const event=new PointerEvent('pointerdown',{bubbles:true,cancelable:true,button:0,pointerId:1});el.dispatchEvent(event);parent.removeEventListener('pointerdown',listen);return[reached,event.defaultPrevented]}),[true,false],type+' capsule pointerdown remains available for native graph dragging');report.checks++;
  if(fullNative){await page.evaluate(()=>window.overwriteCollapsedProp(false));await settle();assert.equal(await page.evaluate(()=>window.store[0].data.collapsed),true,type+' stale full props cannot undo explicit collapse');assert.equal(await node.getAttribute('data-hmb-native-collapse-intent'),'true');report.checks+=2;}
  if(fullNative)await page.evaluate(()=>window.beginNativeStaleRefresh());
  await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(()=>document.querySelector('[data-hmb-color-lut-native-layout=active]'));await settle();
  assert.deepEqual(await page.evaluate(()=>[window.store[0].width,window.store[0].height]),[1400,1200],type+' restores the measured pre-icon size even without authored metadata.size');report.checks++;
  if(fullNative&&['HMBPromptLibrary','HMBVideoPickerLibrary'].includes(type)){assert.equal(await node.getAttribute('data-hmb-native-icon-layout'),null);assert.equal(await node.evaluate(el=>el.style.minHeight),beforeMinimum);report.checks+=2;}
  if(fullNative){await page.evaluate(()=>window.completeNativeStaleRefresh());await settle();assert.equal(await page.evaluate(()=>window.store[0].data.collapsed),false,type+' late native refresh retains current expansion');assert.equal(await page.locator('[data-hmb-native-icon-header]').count(),0,type+' late native reply cannot recreate the icon');assert.equal(await page.locator('[data-body-carrier]').count(),1,type+' exact native Ejr body remains mounted');report.checks+=3;}
  if(fullNative)for(let late=0;late<2;late++){await page.evaluate(()=>window.overwriteCollapsedProp(true));await settle();assert.equal(await page.evaluate(()=>window.store[0].data.collapsed),false,type+' repeated stale full node data cannot undo explicit expansion');assert.equal(await node.getAttribute('data-hmb-native-collapse-local'),'false');assert.equal(await page.locator('[data-hmb-native-icon-header]').count(),0);report.checks+=3;}
  assert.equal(await page.evaluate(()=>window.store[0].data.collapsed),false);assert.deepEqual(await page.evaluate(()=>window.store[0].data.elements),before.elements);report.checks+=2;
  if(!['HMBImageAssetLibrary','HMBVideoPickerLibrary'].includes(type)){
   const stable=await page.evaluate(()=>({node:structuredClone(window.store[0]),sdk:window.sdk.length}));
   for(const surface of [node.locator('[data-header-blank]'),node.locator('[data-hmb-native-identity] span.truncate').first()]){
    await surface.dblclick();await settle();assert.equal(await node.locator('[data-hmb-native-icon-header]').count(),0,type+' only the arrow folds to a capsule');assert.deepEqual(await page.evaluate(()=>window.store[0]),stable.node,type+' a header without an existing compact view does nothing');assert.equal(await page.evaluate(()=>window.sdk.length),stable.sdk,type+' inactive header double click does not send metadata');report.checks+=3;
   }
   if(['HMBSeedanceGeneration','HMBImageGeneration'].includes(type)){
    await node.locator('[data-hmb-native-identity] button').first().click();await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();
    const savedDefault=await page.evaluate(()=>structuredClone(window.store[0]));assert.equal(savedDefault.data.metadata.size,undefined);assert.deepEqual(savedDefault.data.metadata.hmb_native_studio_expanded_size,{version:1,width:1400,height:1200});report.checks+=2;
    await page.evaluate(()=>{window.store=[];window.renderApp()});await page.waitForFunction(()=>!document.querySelector('.react-flow__node'));
    await page.evaluate(saved=>{window.beginWorkflowLoad();window.store=[saved];window.renderApp()},savedDefault);await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();
    await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(()=>document.querySelector('[data-hmb-color-lut-native-layout=active]'));await settle();
    assert.deepEqual(await page.evaluate(()=>[window.store[0].width,window.store[0].height]),[1400,1200],type+' default-size icon survives cold reopen');report.checks++;
   }
  }else{
   const rootSel=type==='HMBImageAssetLibrary'?'.hmb-image-assets':'.hmbvp';const view=()=>page.locator(rootSel).evaluate((e,type)=>type==='HMBImageAssetLibrary'?e.dataset.libraryCompact==='true':e.dataset.pickerView==='compact',type);
   const initialView=await view();
   for(const wanted of [!initialView,initialView]){await node.locator('[data-hmb-native-identity] span.truncate').first().dblclick();await page.waitForTimeout(70);assert.equal(await view(),wanted,type+' native identity toggles existing compact exactly once');report.checks++;}
   if(!await view()){await node.locator('[data-hmb-native-identity] span.truncate').first().dblclick();await page.waitForTimeout(70)}assert.equal(await view(),true,type+' native identity dblclick reaches existing compact');
   await page.evaluate(()=>window.hideBodyBeforeAnimation=true);
   await node.locator('[data-hmb-native-identity] button').first().click();await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();const saved=await page.evaluate(()=>structuredClone(window.store[0]));assert.equal(saved.data.metadata.hmb_native_studio_view?.view,'compact',JSON.stringify(await page.evaluate(()=>({sdk:window.sdk,metadata:window.store[0].data.metadata,attrs:[...document.querySelector('.react-flow__node').attributes].map(a=>[a.name,a.value])}))));
   await page.evaluate(()=>window.hideBodyBeforeAnimation=false);
   await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(sel=>document.querySelector(sel),rootSel);await settle();assert.equal(await view(),true,type+' compact survives complete body unmount');report.checks+=3;
   // Fresh DOM node models a cold-open: no old WeakMap or widget registry owner.
   await page.evaluate(()=>{window.store=[];window.renderApp()});await page.waitForFunction(()=>!document.querySelector('.react-flow__node'));
   await page.evaluate(saved=>{window.beginWorkflowLoad();saved.data.hmb_native_studio_restore_view=saved.data.metadata.hmb_native_studio_view;window.store=[saved];window.renderApp()},saved);await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();
   await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(sel=>document.querySelector(sel),rootSel);await settle();assert.equal(await view(),true,type+' saved icon restores original compact on fresh DOM');report.checks++;
   await node.locator('[data-hmb-native-identity] span.truncate').first().dblclick();await page.waitForTimeout(70);assert.equal(await view(),false);
   await node.locator('[data-hmb-native-identity] button').first().click();await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();const expandedSaved=await page.evaluate(()=>structuredClone(window.store[0]));assert.equal(expandedSaved.data.metadata.hmb_native_studio_view.view,'expanded');
   await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(sel=>document.querySelector(sel),rootSel);await settle();assert.equal(await view(),false,type+' expanded survives icon body remount');report.checks+=3;
   await page.evaluate(()=>{window.store=[];window.renderApp()});await page.waitForFunction(()=>!document.querySelector('.react-flow__node'));
   await page.evaluate(saved=>{saved.data.hmb_native_studio_restore_view=saved.data.metadata.hmb_native_studio_view;window.store=[saved];window.renderApp()},expandedSaved);await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();
   await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(sel=>document.querySelector(sel),rootSel);await settle();assert.equal(await view(),false,type+' expanded cold icon restores even when default view is compact');report.checks++;
   // ReactFlow can reuse this DOM node shell when another saved workflow
   // contains the same node ID. Its previous view memory must not win.
   await page.evaluate(saved=>{window.beginWorkflowLoad();saved.data.hmb_native_studio_restore_view=saved.data.metadata.hmb_native_studio_view;window.store=[saved];window.renderApp()},saved);await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();
   await page.getByRole('button',{name:'Expand '+name,exact:true}).dblclick();await page.waitForFunction(sel=>document.querySelector(sel),rootSel);await settle();assert.equal(await view(),true,type+' saved compact hint restores after reusing the existing DOM shell');report.checks++;
  }
  assert.equal(await page.evaluate(()=>window.forbidden),0);assert.equal(await page.evaluate(()=>window.sdk.every(c=>c.type==='SetNodeMetadataRequest')),true);report.checks+=2;report.cases.push({type,status:'PASS'});
  await page.evaluate(()=>{window.store=[];window.renderApp()});await page.waitForFunction(()=>!document.querySelector('.react-flow__node'));
 }
 await page.evaluate(()=>window.load('HMBColorLUTLibrary','expanded',true,'/fixture-icon.svg'));await page.waitForFunction(()=>document.querySelector('[data-hmb-soft-link-icon="02"]'));assert.equal(await page.locator('[data-hmb-native-icon-header] img').count(),0);assert.deepEqual(await page.locator('[data-hmb-soft-link-icon] rect').evaluateAll(els=>els.map(el=>[el.getAttribute('x'),el.getAttribute('y'),el.getAttribute('width'),el.getAttribute('height'),el.getAttribute('rx')])),[['8','22','30','20','10'],['26','22','30','20','10']]);report.checks+=2;
 await page.getByRole('button',{name:'Expand Synthetic HMBColorLUTLibrary',exact:true}).press('Enter');await page.waitForFunction(()=>!document.querySelector('[data-hmb-native-icon-header]'));report.checks++;
 await page.evaluate(()=>{window.store=[];window.renderApp()});await page.waitForFunction(()=>!document.querySelector('.react-flow__node'));
 await page.evaluate(()=>window.load('HMBColorLUTLibrary','expanded',true,{light:'sun',dark:'moon'}));await page.waitForFunction(()=>document.querySelector('[data-hmb-soft-link-icon="02"]'));assert.equal(await page.locator('[data-hmb-native-icon-header] [data-actual-icon]').count(),0);report.checks++;
 await page.getByRole('button',{name:'Expand Synthetic HMBColorLUTLibrary',exact:true}).press('Space');await page.waitForFunction(()=>!document.querySelector('[data-hmb-native-icon-header]'));report.checks++;
 await page.evaluate(()=>{window.store=[];window.renderApp()});await page.waitForFunction(()=>!document.querySelector('.react-flow__node'));
 await page.evaluate(()=>{window.load('HMBColorLUTLibrary','expanded',true);window.store[0].data.locked=true;window.renderApp()});await page.waitForFunction(()=>document.querySelector('[data-hmb-native-icon-header]'));await settle();const lockedMetadataCalls=await page.evaluate(()=>window.sdk.length);await page.getByRole('button',{name:'Expand Synthetic HMBColorLUTLibrary',exact:true}).dblclick();await page.waitForFunction(()=>!document.querySelector('[data-hmb-native-icon-header]'));assert.equal(await page.evaluate(()=>window.store[0].data.locked),true,'Unlock restores presentation without altering actual lock');assert.equal((await page.evaluate(()=>window.sdk.length))-lockedMetadataCalls,1,'Double click calls the original native expansion transaction exactly once');assert.equal(await page.evaluate(()=>window.forbidden),0);report.checks+=3;
 await settle();report.controlled_animation=await page.evaluate(()=>({native_store_commits:window.fixtureStoreCommits,dimension_events:window.fixtureDimensionEvents,pending_tweens:window.nativeActiveTweens,intermediate_native_fold_types:[...new Set(window.nativeFoldIntermediateSamples.map(sample=>sample.type))]}));assert.ok(report.controlled_animation.native_store_commits>0&&report.controlled_animation.native_store_commits<1000);assert.ok(report.controlled_animation.dimension_events>0);assert.equal(report.controlled_animation.pending_tweens,0);assert.ok(report.controlled_animation.intermediate_native_fold_types.includes('HMBPromptLibrary'),'Actual ResizeObserver sees native Prompt animation dimensions instead of fixed capsule counterwrites');report.checks+=4;
 assert.deepEqual(errors,[]);report.checks++;report.status='PASS';report.exact_native_Ejr=fullNative;report.exact_native_MAr=true;report.exact_native_nodeQueue_and_StoreUpdater=true;report.actual_browser_ResizeObserver=true;report.delayed_native_refresh_tested=fullNative;report.candidate_sha256=createHash('sha256').update(patched).digest('hex');
 const out=process.env.HMB_ICON_HEADER_REPORT_DIR;if(out){fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'icon-header-react-fixture.json'),JSON.stringify(report,null,2));await page.screenshot({path:path.join(out,'icon-header-react-fixture-SYNTHETIC.png')})}console.log(JSON.stringify(report));
}finally{await browser?.close();await new Promise(r=>server.close(r))}
