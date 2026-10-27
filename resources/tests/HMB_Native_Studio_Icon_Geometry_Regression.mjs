// Exact native workflow constructor/dimension/style/store functions + current
// HMB helper, with only SDK shape/icon-category dependencies stubbed. No app.
import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import vm from 'node:vm';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';
import {prepareNativeEditor} from './_hmb_native_editor_fixture.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url)),{original,patched}=prepareNativeEditor(root);
const between=(s,start,end)=>{const a=s.indexOf(start),b=s.indexOf(end,a+start.length);assert.ok(a>=0&&b>a,start);return s.slice(a,b)};
const helper=fs.readFileSync(path.join(root,'resources/editor/hmb-color-lut-native-header.js'),'utf8'),nativeGeometry=between(original,'function Sjr(','function Ejr('),nativeBaseStyle=between(original,'function vBt(','var yBt=');
const cold=between(patched,'function fkr(','function pkr('),stockCold=between(original,'function fkr(','function pkr(').replace('function fkr(','function stockFkr(');
const floor=between(patched,'(0,S.useEffect)(()=>{if(hmbIsNativeStudioType(e.node_type)&&O)return;','hmbUseNativeStudioCollapseState(e,O,k').replace(/,$/,';');
const context=vm.createContext({console});
vm.runInContext(`var S={useEffect:fn=>fn()};var dkr=t=>t.metadata.test_group?'GroupNode':'default';var $V=()=>null,cBt=()=>false,bEr=()=>false,Jwr=x=>x,Ywr=()=>false,xEr=()=>false,wEr=()=>false;var ckr=()=>false,skr=x=>Math.max(600,Number(x)||600);\n`+nativeBaseStyle+'\n'+nativeGeometry+'\n'+stockCold+'\n'+cold+'\n'+helper+`\nglobalThis.api={cold:fkr,stock:stockFkr,dimensions:hmbNativeStudioDimensions,style:hmbNativeStudioNodeStyle,constructed:hmbNativeStudioConstructedNode,store:wjr,floor:(e,O,me,ee)=>{${floor}}};`,context);
const api=context.api,clone=v=>JSON.parse(JSON.stringify(v));let checks=0;const equal=(a,b,message)=>{assert.deepEqual(clone(a),clone(b),message);checks++};
const types=['HMBColorLUTLibrary','HMBAgentLibrary','HMBFinishLookLibrary','HMBImageAssetLibrary','HMBImageBash','HMBImageGeneration','HMBSeedanceGeneration','HMBPromptLibrary','HMBVideoPickerLibrary'];
function fixture(type,collapsed=true,size=true){return{locked:false,metadata:{node_type:type,collapsed,position:{x:13,y:21},...(size?{size:{width:1400,height:1200}}:{}),hmb_native_studio_view:{version:1,view:'compact'},library_node_metadata:{category:'HMB',icon:'image'}},root_node_element:[{element_id:'in',name:'input_original',element_type:'Parameter',type:'str',mode_allowed_input:true,mode_allowed_property:true,default_value:'0 OFF',ui_options:{}},{element_id:'out',name:'output_original',element_type:'Parameter',type:'str',mode_allowed_output:true,default_value:'image.png / job-preserved',ui_options:{}},{element_id:'hidden',name:'hidden_bound_source',element_type:'Parameter',type:'str',mode_allowed_input:true,default_value:'original-source-uuid',ui_options:{hide:true}}],element_id_to_value:{out:'original.png / original.mov / job-preserved'}}}
for(const type of types)for(const hasSize of [false,true]){
 const engine=fixture(type,true,hasSize),before=clone(engine),node=api.cold('Original '+type,engine),stock=api.stock('Original '+type,engine);
 equal([node.width,node.height],[320,64],type+' cold constructor targets the icon geometry');
 equal(node.data.metadata,stock.data.metadata,'Cold icon construction preserves all native metadata including expanded size');
 equal(node.data.elements,stock.data.elements,'Every public/hidden element ID, mode, value and UI option remains original');
 equal(node.position,stock.position,'Icon geometry never moves the authored node');
 equal(node.data.hmb_native_studio_restore_view,{version:1,view:'compact'});
 const data={...node.data};delete data.hmb_native_studio_restore_view;equal(data,stock.data,'Only the presentation restore hint is added to native data');
 equal(engine,before,'Engine response is never mutated');
 equal(api.dimensions(type,true,false,1400,1200,engine.metadata.size),{newWidth:320,newHeight:64});
 equal(api.dimensions(type,true,true,1400,1200,engine.metadata.size),{newWidth:1400,newHeight:48},'Native rollup retains its original width');
 equal(api.dimensions(type,false,false,1400,1200,engine.metadata.size),{newWidth:1400,newHeight:1200},'Native expand restores its authored dimensions');
 const style=api.style(type,null,true,150,600,false,false);equal([style.width,style.height,style.minWidth,style.minHeight],[320,64,320,64]);
 const nodes=[{...node,measured:{width:320,height:64},results:{path:'original.png'},shot:{shot_uuid:'original-shot'},style:{width:320,height:64}},{id:'Unrelated',data:{node_type:'Other'}}];
 const restored=api.store(nodes,node.id,1400,1200);equal(restored[0].measured,{width:1400,height:1200});equal(restored[0].data.metadata,node.data.metadata);equal(restored[0].results,nodes[0].results);equal(restored[0].shot,nodes[0].shot);assert.equal(restored[1],nodes[1]);checks++;
 // A useEffect captured before the collapse may run after the 320x64 store
 // commit. The inner live-node check must reject that stale height floor.
 let floored={...node,height:64};api.floor({...node.data,collapsed:false},false,(_name,update)=>{floored=update(floored)},150);equal(floored.height,64,'A stale expanded effect cannot inflate a newly collapsed icon');
}
for(const type of ['ExampleNode','Note','DotNode'])for(const collapsed of [false,true])for(const hasSize of [false,true]){
 const engine=fixture(type,collapsed,hasSize);equal(api.cold('Other',engine),api.stock('Other',engine),type+' cold construction remains byte-equivalent');
 const node=api.stock('Other',engine);assert.equal(api.constructed(node),node,'Unrelated node construction retains object identity');checks++;
 const dim=context.Tjr(collapsed,false,1400,1200,engine.metadata.size);equal(api.dimensions(type,collapsed,false,1400,1200,engine.metadata.size),dim);
 equal(api.style(type,null,collapsed,150,600,false,false),context.Sjr(null,collapsed,150,600,false,false));
}
{
 const engine=fixture('HMBColorLUTLibrary');engine.metadata.test_group=true;engine.metadata.left_parameters=['left'];engine.metadata.right_parameters=['right'];equal(api.cold('Group',engine),api.stock('Group',engine),'The GroupNode constructor is untouched even for an artificial matching type');
}
const nativeAnchors=between(original,'function xAr(','function TAr(');equal(between(patched,'function xAr(','function TAr('),nativeAnchors,'SAr/xAr hidden handle rendering, connectability and IDs are unchanged');
equal(between(patched,'function Tjr(','function Ejr('),between(original,'function Tjr(','function Ejr('),'The stock dimensions function remains original; HMB uses an explicit adapter');
{
 const dom={isConnected:true,querySelectorAll:()=>[],style:{getPropertyValue:()=>'',getPropertyPriority:()=>''}};context.document={querySelector:()=>dom};context.CSS={escape:String};context.testDOM=dom;
 for(const type of types){
  vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,intent:true,expandedSize:null})',context);
  equal(api.dimensions(type,true,false,1400,1200,undefined,undefined,'Default'),{newWidth:320,newHeight:64});
  equal(api.dimensions(type,false,false,320,64,undefined,undefined,'Default'),{newWidth:1400,newHeight:1200},'No-size default node restores measured dimensions rather than the 320x64 capsule');
  const hint=vm.runInContext('hmbNativeStudioCollapseMetadata({id:"Default",data:{node_type:'+JSON.stringify(type)+'}},true,false).hmb_native_studio_expanded_size',context);
  equal(hint,{version:1,width:1400,height:1200},'Cold icon stores a separate presentation-size hint');
  context.savedSize=hint;vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,intent:null,expandedSize:hmbNativeStudioSavedSize(savedSize)})',context);
  equal(api.dimensions(type,false,false,320,64,undefined,undefined,'Default'),{newWidth:1400,newHeight:1200},'Cold icon restores its saved presentation size without changing metadata.size');
  vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,intent:null,expandedSize:null,rollupSize:null})',context);
  equal(api.dimensions(type,true,true,1400,1200,undefined,undefined,'Default'),{newWidth:1400,newHeight:48});
  const rollupHint=vm.runInContext('hmbNativeStudioCollapseMetadata({id:"Default",data:{node_type:'+JSON.stringify(type)+'}},true,true).hmb_native_studio_rollup_size',context);
  equal(rollupHint,{version:1,width:1400,height:1200},'Rollup stores its original measured height separately');
  context.savedSize=rollupHint;vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,intent:null,expandedSize:null,rolledUp:true,rollupSize:hmbNativeStudioSavedSize(savedSize)})',context);
  equal(api.dimensions(type,false,true,1400,48,undefined,undefined,'Default'),{newWidth:1400,newHeight:1200},'Cold unroll recovers height even when the native g.current ref is empty');
  api.dimensions(type,true,false,1400,48,undefined,undefined,'Default');
  equal(api.dimensions(type,false,false,320,64,undefined,undefined,'Default'),{newWidth:1400,newHeight:1200},'Arrow from a rollup never overwrites the full size with 48px');
 }
 delete context.document;
}
{
 const prefix='bn=(0,S.useCallback)(',end=',[C,b,x,yn,on,Zt,A,N.showHelperLines,Ve,Ue,Et,Dt,ze,ut])';
 const expression=between(patched,prefix,end).slice(prefix.length);
 vm.runInContext('globalThis.api.folded=hmbNativeStudioFolded;globalThis.api.suppress=hmbNativeStudioSuppressInitialSize;globalThis.api.collapsedMeasured=hmbNativeStudioCollapsedMeasuredNode;globalThis.api.collapsedMeasuredNodes=hmbNativeStudioCollapsedMeasuredNodes;',context);
 for(const type of ['HMBSeedanceGeneration','HMBImageGeneration','ExampleNode'])for(const missingDimensions of [false,true]){
  let nodes=[{id:'Owned',type:'default',...(missingDimensions?{}:{width:320,height:64}),position:{x:1,y:2},data:{node_type:type,collapsed:true,metadata:{}}}],saves=[];
  const onChanges=vm.runInNewContext('('+expression+')',{E:{current:null},N:{showHelperLines:false},w:{get current(){return nodes}},x:fn=>nodes=fn(nodes),yn:(id,metadata)=>saves.push({id,metadata}),Ct:{current:{}},C(){},console,hmbNativeGuardNodeDeletion:context.hmbNativeGuardNodeDeletion,hmbNativeStudioCollapsedWidth:320,hmbNativeStudioCollapsedHeight:64,hmbIsNativeStudioType:value=>types.includes(value),hmbNativeStudioSuppressInitialSize:api.suppress,hmbNativeStudioFolded:api.folded,hmbNativeStudioCollapsedMeasuredNode:api.collapsedMeasured,hmbNativeStudioCollapsedMeasuredNodes:api.collapsedMeasuredNodes});
  onChanges([{type:'dimensions',id:'Owned',dimensions:{width:72,height:181},resizing:false}]);
  equal([nodes[0].width,nodes[0].height],type==='ExampleNode'?[300,48]:[320,64],'Native dimension events retain the HMB icon geometry');
  equal(saves.length,type==='ExampleNode'?1:0,'An icon ResizeObserver event cannot become the initial authored size');
 }
 const dom={isConnected:true};context.document={querySelector:()=>dom};context.CSS={escape:String};context.testDOM=dom;
 vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,intent:false,expandedSize:{version:1,width:600,height:1200},geometryTarget:{newWidth:600,newHeight:1200}})',context);
 const noSize={id:'Owned',data:{node_type:'HMBSeedanceGeneration',collapsed:false,metadata:{}}};
 equal(api.suppress(noSize,{width:72,height:181}),true,'Intermediate icon/allocator dimensions are not persisted as initial size');
 equal(api.suppress(noSize,{width:600,height:1200}),false,'The settled pre-collapse target may initialize its default size');
 equal(api.suppress(noSize,{width:700,height:1300}),false,'Later expanded resize behavior remains available');
 vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch-1,intent:true,rolledUp:true,geometryTarget:{newWidth:320,newHeight:64}})',context);
 equal(api.folded(noSize),false,'A previous flow controller cannot mark the new flow folded');equal(api.suppress(noSize,{width:600,height:1200}),false,'A previous flow geometry target cannot block new-flow measurements');
 vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,animating:true})',context);
 const middle={id:'Owned',width:756,height:443,measured:{width:756,height:443},data:{node_type:'HMBPromptLibrary',collapsed:true}},middleNodes=[middle],ids=new Set(['Owned']);
 assert.equal(api.collapsedMeasured(middle),middle,'Native animated dimensions retain node identity');assert.equal(api.collapsedMeasuredNodes(middleNodes,ids),middleNodes,'A folded measurement during animation cannot enqueue another array');checks+=2;
 vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,animating:false})',context);
 const fixed=api.collapsedMeasuredNodes(middleNodes,ids);equal([fixed[0].width,fixed[0].height],[320,64],'Completion reconciles a remaining measurement once');assert.equal(api.collapsedMeasuredNodes(fixed,ids),fixed,'An already settled measurement retains array identity');checks++;
 vm.runInContext('globalThis.api.outgoing=hmbNativeStudioOutgoingMetadata;hmbNativeStudioCollapseControllers.set(testDOM,{epoch:hmbNativeStudioFlowEpoch,nodeType:"HMBSeedanceGeneration",intent:false,rolledUp:false,accent:"#2468ac",expandedSize:{version:1,width:600,height:1200}})',context);
 const outgoing=api.outgoing('Owned',{collapsed:true,rolledUp:true,size:{width:600,height:1200},shot:'preserved'});
 equal(outgoing.collapsed,false,'An old geometry metadata snapshot cannot persist a stale collapsed=true');equal(outgoing.rolledUp,false);equal(outgoing.size,{width:600,height:1200});equal(outgoing.shot,'preserved');equal(outgoing.hmb_native_studio_capsule_accent,'#2468ac','A geometry save retains the latest capsule accent');
 vm.runInContext('hmbNativeStudioResetCollapseIntents()',context);const originalMetadata={collapsed:true,size:{width:600,height:1200}};assert.equal(api.outgoing('Owned',originalMetadata),originalMetadata,'Old flow metadata remains untouched');checks++;
 delete context.document;
}
for(const [width,height,valid] of [[280,240,true],[1400,1200,true],[320,64,false],[320,48,false],[72,72,false]]){
 context.sizeCandidate={version:1,width,height};equal(!!vm.runInContext('hmbNativeStudioSavedSize(sizeCandidate)',context),valid,'Only expanded presentation dimensions are valid hints');
}
{
 const start=helper.indexOf('updateNode(data.node_name, live =>'),finish=helper.indexOf(': live);',start)+': live'.length;
 assert.ok(start>=0&&finish>start);const callback=helper.slice(start+'updateNode(data.node_name, '.length,finish);
 vm.runInContext('globalThis.makeQueued=(epoch,node,current,wanted,data)=>('+callback+');',context);
 const dom={isConnected:true},live={id:'Owned',data:{node_type:'HMBSeedanceGeneration',collapsed:true,results:'preserved'}};context.testDOM=dom;
 for(const invalidation of ['none','epoch','controller','intent','disconnected']){
  vm.runInContext('globalThis.record={epoch:hmbNativeStudioFlowEpoch,intent:false};hmbNativeStudioCollapseControllers.set(testDOM,record);globalThis.queued=makeQueued(hmbNativeStudioFlowEpoch,testDOM,record,false,{node_name:"Owned",node_type:"HMBSeedanceGeneration"});',context);
  if(invalidation==='epoch')vm.runInContext('hmbNativeStudioResetCollapseIntents()',context);
  if(invalidation==='controller')vm.runInContext('hmbNativeStudioCollapseControllers.set(testDOM,{intent:false})',context);
  if(invalidation==='intent')vm.runInContext('record.intent=true',context);
  dom.isConnected=invalidation!=='disconnected';
  const result=context.queued(live);equal(result.data.collapsed,invalidation==='none'?false:true,'Queued view updates reject '+invalidation+' invalidation');equal(result.data.results,'preserved');
 }
}
assert.ok(patched.includes('hmbNativeStudioConstructedNode(d)}function pkr()'));assert.ok(patched.includes('hmbNativeStudioDimensions(e.node_type,t,r,i,a,e.metadata?.size,o,e.node_name)'));assert.ok(patched.includes('hmbNativeStudioNodeStyle(e.node_type,fe,O,ee,600,xt,A)'));checks+=3;
// Native parameter-alter replies can arrive after the user changes the view.
// Keep the current HMB collapsed state just as native add/remove/rename do.
const alterPrefix='C=m(`AlterParameterDetailsResultSuccess`,',alterEnd='),E=m(`AlterParameterDetailsResultFailure`';
const alterExpression=source=>between(source,alterPrefix,alterEnd).slice(alterPrefix.length);
const metaPrefix='p=m(`SetNodeMetadataResultSuccess`,',metaEnd='),h=m(`SetNodeMetadataResultFailure`';
const metaExpression=source=>between(source,metaPrefix,metaEnd).slice(metaPrefix.length);
equal(metaExpression(patched),metaExpression(original),'The original metadata-success handler remains exact');
for(const type of [...types,'ExampleNode'])for(const collapsed of [false,true]){
 let current=[{id:'Owned',width:1400,height:1200,selected:true,position:{x:13,y:21},data:{node_name:'Owned',node_type:type,collapsed,metadata:{collapsed,size:{width:1400,height:1200}},elements:[{name:'original',value:'Task job-preserved'}]}}];
 const stale=clone(current[0]);stale.data.collapsed=!collapsed;stale.data.metadata.collapsed=!collapsed;
 let resolveReply;
 const alter=vm.runInNewContext('('+alterExpression(patched)+')',{w:{get current(){return current}},An:async()=>true,f:()=>new Promise(resolve=>{resolveReply=resolve}),x:fn=>{current=fn(current)},A(){},console,hmbIsNativeStudioType:value=>types.includes(value)});
 const pending=alter({},{node_name:'Owned',parameter_name:'PROJECT_ROOT',type:'str'});await new Promise(resolve=>setImmediate(resolve));
 resolveReply(stale);await pending;
 equal(current[0].data.collapsed,type==='ExampleNode'?!collapsed:collapsed,'A delayed refresh preserves only HMB current collapse state');
 equal([current[0].width,current[0].height],[1400,1200]);equal(current[0].data.elements,stale.data.elements);
 const metadataSuccess=vm.runInNewContext('('+metaExpression(patched)+')',{x:fn=>{current=fn(current)},T:{current:[]},pt(){},console});
 metadataSuccess({},{node_name:'Owned',metadata:{collapsed,rolledUp:false}});
 equal(current[0].data.metadata.collapsed,collapsed);equal(current[0].data.collapsed,type==='ExampleNode'?!collapsed:collapsed);
}
const evidence={status:'PASS',checks,node_types:types,cold_constructor:'exact installed fkr plus HMB final adapter',native_hidden_anchor_sha256:createHash('sha256').update(nativeAnchors).digest('hex'),candidate_sha256:createHash('sha256').update(patched).digest('hex'),metadata_size_preserved:true,stale_floor_protected:true,native_animation_measurement_owner_and_noop_array_tested:true,paid_calls:0,live_editor_actions:0,installed_changes:0};
const out=process.env.HMB_ICON_GEOMETRY_REPORT_DIR;if(out){fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'icon-native-geometry.json'),JSON.stringify(evidence,null,2))}console.log(JSON.stringify(evidence));
