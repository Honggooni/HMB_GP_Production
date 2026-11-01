// Synthetic canonical-receiver fixture; no production files or services.
export async function setupImageAssetQueueFixture(page,main,bridge,kind){
  await page.evaluate(async({main,bridge,kind})=>{const imp=s=>import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(s)))),m=await imp(main),b=await imp(bridge),id=n=>`90000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
   document.body.innerHTML='<article class="react-flow__node" data-id="Instance Asset" style="width:1300px"><div id="asset"></div><div data-parameter-name="HMB_IMAGE_ASSET_THUMBNAIL_PATCH"><div id="carrier"></div></div></article>';
   const f={m,b,id,kind,node:document.querySelector('article'),main:document.getElementById('asset'),carrier:document.getElementById('carrier'),writes:[],requests:[],acks:[],badIntents:[],closed:false};
   f.server=m.hmbNormalizeImageAssetState({schema:'hmb-image-asset-library-state',widget_runtime_lease:id(1),edit_transport_schema:'hmb-image-asset-edit-v1',scan_revision:1,ui_edit_revision:4,
    shot_routing:{schema:'hmb-shot-routing',version:1,publisher_instance_uuid:id(2),channel_uuid:id(3),generation:1,active_shot_uuid:id(4),shots:[{shot_uuid:id(4),number:1,name:'Shot 1',revision:0,selected_source_uids:[]}]},
    image_bash_workspace:{workspace_id:id(5),revision:2,instances:[{instance_id:id(6),source_uid:'project:a'},{instance_id:id(7),source_uid:'project:b'}]},image_bash_active:true});
   f.initial=structuredClone(f.server);f.originalIds=f.server.image_bash_workspace.instances.map(x=>x.instance_id);
   f.props=value=>({value:value===undefined?JSON.stringify(f.server):value,nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_STATE',ui_options:{widget:'HMBImageAssetLibraryWidget',library:'HMB_GP_Production'},disabled:false,onChange:wire=>{
    if(f.failSend){f.failSend=false;throw Error('Refusing to send SetParameterValueRequest without a session: no sessionId');} const sent=JSON.parse(wire),edits=sent.edits||sent,intent=edits.image_bash_workspace_edit;f.writes.push(sent);
    const workspace=structuredClone(f.server.image_bash_workspace);
    if(!intent?.operation_id||intent.expected_revision!==workspace.revision||intent.workspace_id!==workspace.workspace_id)f.badIntents.push({operation:intent?.operation,expected:intent?.expected_revision,actual:workspace.revision});
    else if(intent.operation==='copy'){const index=workspace.instances.findIndex(x=>x.instance_id===intent.instance_id);if(index<0)throw Error('Invalid source instance');workspace.instances.splice(index+1,0,{...workspace.instances[index],instance_id:intent.new_instance_id});workspace.revision++;}
    else if(intent.operation==='remove'){const index=workspace.instances.findIndex(x=>x.instance_id===intent.instance_id);if(index<0)throw Error('Invalid removed instance');workspace.instances.splice(index,1);workspace.revision++;}
    else throw Error('Unexpected semantic operation in fixture');
    f.server=m.hmbNormalizeImageAssetState({...f.server,...edits,ui_edit_revision:sent.ui_edit_revision,scan_revision:f.server.scan_revision+1,image_bash_workspace:workspace,image_bash_workspace_edit:{},image_bash_workspace_request:{}});
    f.acks.push(structuredClone(f.server));queueMicrotask(()=>{if(!f.closed)f.mh.update(f.props(wire))});
   }});
   f.bridgeProps=value=>({value,nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_THUMBNAIL_PATCH',disabled:false,onChange:request=>{if(request.operation!=='widget_authority')return;f.requests.push(structuredClone(request));if(!f.rejectRead)queueMicrotask(()=>f.answer(request));if(f.rejectRead){const error=Error(f.rejectRead);if(f.rejectCode)error.code=f.rejectCode;return Promise.reject(error);}}});
   f.answer=(request=f.requests.at(-1),server=f.server)=>{f.bh.update(f.bridgeProps({...request,phase:'result',widget_runtime_lease:server.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:m.hmbImageAssetAuthorityScope(server),catalog_page_version:1}))};
   f.canonical=state=>f.mh.update(f.props(JSON.stringify(state)));
   f.copy=instance=>{const button=f.main.querySelector('[data-image-bash-duplicate="'+instance+'"]');if(!button)throw Error('Copy button absent');button.click()};
   f.remove=instance=>{const button=f.main.querySelector('[data-image-bash-remove="'+instance+'"]');if(!button)throw Error('Remove button absent');button.click()};
   f.rows=()=>f.main.__hmbImageAssetLatestState.image_bash_workspace.instances;
   f.close=()=>{if(f.closed)return;f.closed=true;f.mh.cleanup();f.bh.cleanup()};
   f.mh=m.default(f.main,f.props());f.bh=b.default(f.carrier,f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:f.server.shot_routing.publisher_instance_uuid,widget_runtime_lease:f.server.widget_runtime_lease,catalog_page_version:1}));f.answer();window.fixture=f;
  },{main,bridge,kind});await page.clock.runFor(40);

}
