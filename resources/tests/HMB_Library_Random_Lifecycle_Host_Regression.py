"""Seeded actual-SDK lifecycle stress; synthetic state, no render or user graph.

The established twenty-case fixture supplies unchanged construction and media
boundaries. Its final unregister is delayed only by this harness so additional
native requests can exercise the same registered, authored graph.
"""
from __future__ import annotations
import asyncio
import difflib
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import socket
import statistics
import sys
import tempfile
import time
import traceback
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('_hmb_established_lifecycle_fixture', Path(__file__).with_name('HMB_Library_Lifecycle_Order_Host_Regression.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
RESULTS = []

def summary(values):
    ordered = sorted(values)
    return dict(count=len(ordered), median_ms=round(statistics.median(ordered)*1000, 3) if ordered else 0,
        p95_ms=round(ordered[min(len(ordered)-1, int(len(ordered)*.95))]*1000, 3) if ordered else 0,
        maximum_ms=round(max(ordered)*1000, 3) if ordered else 0)

async def seed_scenario(engine, modules, project_state, seed, count):
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest, SerializeNodeToCommandsRequest, DeserializeNodeFromCommandsRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.serialization.values import decode_value
    rng = random.Random(seed)
    order = list(base.KINDS)
    rng.shuffle(order)
    captured = {}
    original_assert_graph = base.assert_graph
    original_unregister = LibraryRegistry.unregister_library
    deferred_cleanup = []
    def capture(*args, **kwargs):
        result = original_assert_graph(*args, **kwargs)
        captured.update(flow=args[1], nodes=args[2], shots=args[3])
        return result
    with mock.patch.object(base, 'assert_graph', capture), mock.patch.object(LibraryRegistry, 'unregister_library', side_effect=lambda *a,**k:deferred_cleanup.append((a,k))):
        await base.scenario(engine, modules, project_state, tuple(order), f'RandomSeed{seed}')
    flow, nodes = captured['flow'], captured['nodes']
    images, pickers, prompts, agents, finishes, generators = (modules[k] for k in base.KINDS)
    timings = {}
    native_timings = {}
    checkpoint_timings = []
    actions = []
    lag = []
    stop = asyncio.Event()
    async def heartbeat():
        loop = asyncio.get_running_loop()
        while not stop.is_set():
            start = loop.time()
            await asyncio.sleep(.01)
            lag.append(max(0.0, loop.time()-start-.01))
    pulse = asyncio.create_task(heartbeat())
    request_count = 0
    observer_guard=ExitStack()
    preview_records=[]
    if os.environ.get('HMB_RANDOM_PREVIEW_DIAGNOSTICS')=='1':
        def text_identity(value):
            text=str(value or '')
            return dict(length=len(text),sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())
        def preview_state(owner):
            return dict(node=owner.name,instance=id(owner),selected=owner._hmb_shot_channel_subscription(),
                live_catalog_count=len((getattr(owner,'_hmb_shot_catalog_snapshot',{}) or {}).get('shots',[])),
                preview_active=bool(getattr(owner,'_hmb_prompt_preview_active',False)),
                cached=text_identity(getattr(owner,'_hmb_prompt_preview_value','')),
                native=text_identity(owner._native_parameter_value('prompt','')),
                routed=text_identity(owner._native_parameter_value('SHOT_PROMPT_IN','')),
                hydration_pending=bool(getattr(owner,'_hmb_prompt_preview_hydration_pending',False)),
                verified_source_instance=id(getattr(owner,agents._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,None)))
        def image_work_state(owner):
            work=getattr(owner,'_hmb_selection_resolution_work',{}) or {}
            ready=work.get('ready')
            return dict(node=owner.name,instance=id(owner),deleted=bool(getattr(owner,'_hmb_node_deleted',False)),
                ready=bool(ready),ready_identity=ready[0] if ready else None,ready_epoch=ready[1] if ready else None,
                active=bool(work.get('active')),epoch=work.get('epoch'),cache_count=len(getattr(owner,'_hmb_resolution_cache',{}) or {}),
                cache_identity=getattr(owner,'_hmb_resolution_cache_identity',''))
        def observe_method(cls,name,*,state=False,document=False):
            original=getattr(cls,name)
            def observed(owner,*args,**kwargs):
                if name=='set_parameter_value' and str(args[0] if args else '')!=agents._AGENT_SHOT_PROMPT_INPUT_PARAMETER:
                    return original(owner,*args,**kwargs)
                record=dict(action_index=len(actions),method=name,owner=owner.name,instance=id(owner),
                    stack=[f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' for frame in traceback.extract_stack(limit=7)[:-1]])
                if state:record['before']=preview_state(owner)
                if cls is images.HMBImageAssetLibrary:
                    record['image_before']=image_work_state(owner)
                    record['kwargs']=kwargs
                if name=='_sync_prompt_output_from_state':record['output_before']=text_identity(owner.parameter_output_values.get('PROMPT_OUT',''))
                if name=='set_parameter_value':record['incoming']=text_identity(args[1] if len(args)>1 else kwargs.get('value'))
                try:
                    result=original(owner,*args,**kwargs)
                except BaseException as exc:
                    record['exception']=dict(type=type(exc).__name__,
                        image_preparing=getattr(exc,'hmb_image_asset_selection_preparing',False) is True,
                        picker_preparing=getattr(exc,'hmb_picker_media_preparing',False) is True)
                    raise
                else:
                    if document:record['visible']=text_identity(result.get('visible_prompt',''))
                    elif name=='_hmb_manager_prompt_owner':record['source_instance']=id(result)
                    else:record['returned']=result if isinstance(result,(bool,type(None))) else type(result).__name__
                    return result
                finally:
                    if state:record['after']=preview_state(owner)
                    if cls is images.HMBImageAssetLibrary:record['image_after']=image_work_state(owner)
                    if name=='_sync_prompt_output_from_state':record['output_after']=text_identity(owner.parameter_output_values.get('PROMPT_OUT',''))
                    preview_records.append(record)
            observer_guard.enter_context(mock.patch.object(cls,name,observed))
        for method in ('_refresh_routed_prompt_preview','_hmb_hydrate_shot_prompt_from_source',
                       'after_incoming_connection','after_incoming_connection_removed','_hmb_manager_prompt_owner','set_parameter_value'):
            observe_method(agents.HMBAgentLibrary,method,state=True)
        observe_method(prompts.HMBPromptLibrary,'_hmb_prompt_shot_document',document=True)
        observe_method(prompts.HMBPromptLibrary,'_sync_prompt_output_from_state')
        for method in ('_consume_selection_resolution','_defer_project_selection_resolution','_sync_output','_reconcile_hmb_shot_routing'):
            observe_method(images.HMBImageAssetLibrary,method)
    def send(request):
        nonlocal request_count
        request_count += 1
        start=time.perf_counter()
        try:return base.send(engine, request)
        finally:native_timings.setdefault(type(request).__name__,[]).append(time.perf_counter()-start)
    async def asend(request):
        nonlocal request_count
        request_count += 1
        start=time.perf_counter()
        try:return await base.asend(engine, request)
        finally:native_timings.setdefault(type(request).__name__,[]).append(time.perf_counter()-start)
    def current_shots():
        return nodes[base.KINDS[0]]._hmb_shot_routing_snapshot(cached_only=True)['shots']
    def graph_ready():
        try:
            original_assert_graph(engine, flow, nodes, current_shots())
            return True
        except (AssertionError, KeyError, ValueError):
            return False
    expected_agent = {shot['shot_uuid']:deepcopy(nodes[base.KINDS[3]]._hmb_shot_slots[nodes[base.KINDS[3]]._hmb_slot_key(base.CHANNEL,shot['shot_uuid'])]['values']) for shot in current_shots()}
    expected_finish = {shot['shot_uuid']:deepcopy(nodes[base.KINDS[4]]._hmb_finish_look_shot_snapshot_for(channel_uuid=base.CHANNEL,shot_uuid=shot['shot_uuid'])['finish_look_state']) for shot in current_shots()}
    expected_binding = {node.name:node._hmb_shot_channel_subscription()['shot_uuid'] for node in nodes[base.KINDS[5]]}
    # Establish actual user color edits, distinguishable from Picker's Red
    # automatic baseline. Explicit live disconnect restores prior manual
    # context; the contract preserves user differences, not automatic colors.
    prompt=nodes[base.KINDS[2]]
    for shot in current_shots():
        value=prompts._select_prompt_shot_document(prompt._current_state(),dict(shot,channel_uuid=base.CHANNEL))
        value=base.prompt_rows_from_state(prompt,value)[0]
        for row in value['images']:
            if row.get('asset_source_uid'):row['color_picks']=['Blue']
        value[prompts.UI_EDIT_REVISION_KEY]=max(int(value.get(prompts.UI_EDIT_REVISION_KEY) or 0),int(prompt._current_state().get(prompts.UI_EDIT_REVISION_KEY) or 0))+1
        send(SetParameterValueRequest(node_name=prompt.name,parameter_name=prompts.WIDGET_PARAMETER_NAME,value=prompts._json_dumps(value)))
    await asyncio.sleep(.15)
    async def verify(*, subset_uuid=None, subset_uids=None):
        checkpoint_start=time.perf_counter()
        prompt, agent, finish = (nodes[k] for k in base.KINDS[2:5])
        await base.settle(graph_ready, seconds=4)
        assert len(flow.nodes)==10,('registered_node_growth',len(flow.nodes))
        assert len(base.edges(engine, flow)) == 23
        actual_binding={node.name:node._hmb_shot_channel_subscription()['shot_uuid'] for node in nodes[base.KINDS[5]]}
        if actual_binding!=expected_binding:
            print('RANDOM_GENERATOR_BINDING_CHANGED '+json.dumps(dict(seed=seed,expected=expected_binding,actual=actual_binding,
                subscriptions={node.name:node._hmb_shot_channel_subscription() for node in nodes[base.KINDS[5]]},
                source_shots=[{key:shot[key] for key in ('shot_uuid','number','name')} for shot in current_shots()])),flush=True)
        for node in nodes[base.KINDS[5]]:
            assert node._hmb_shot_channel_subscription()['shot_uuid'] == expected_binding[node.name],('generator_UUID_reassigned',node.name,expected_binding[node.name],node._hmb_shot_channel_subscription()['shot_uuid'])
        for shot in current_shots():
            for retry in range(300):
                try:
                    doc = prompt._hmb_prompt_shot_document(channel_uuid=base.CHANNEL,shot_uuid=shot['shot_uuid'])
                    projected, media, _ = base.prompt_rows(prompt,prompts,dict(shot,channel_uuid=base.CHANNEL))
                    break
                except ValueError as exc:
                    if not (getattr(exc,'hmb_image_asset_selection_preparing',False) is True or getattr(exc,'hmb_picker_media_preparing',False) is True):
                        raise
                    if retry == 299: raise
                    await asyncio.sleep(.01)
            rows = [row for row in projected['images'] if row.get('asset_source_uid')]
            uids = subset_uids if shot['shot_uuid']==subset_uuid else shot['selected_source_uids']
            assert [row['asset_source_uid'] for row in rows] == uids
            assert len(media) == len(rows) and doc['image_media'] == media
            assert all(row['image_main_type']=='Character' and row['image_sub_type']=='Full Appearance' for row in rows)
            if not all(row['color_picks']==['Blue'] for row in rows):
                picker=nodes[base.KINDS[1]]
                print('RANDOM_PROJECTION_FAILURE '+json.dumps(dict(seed=seed,shot=shot['shot_uuid'],picker_subscription=picker._hmb_shot_channel_subscription(),
                    colors=[row['color_picks'] for row in rows],document_has_Blue='Blue' in doc['machine_prompt'])),flush=True)
                authoring_probe('at_projection_failure')
                raise AssertionError(('color_pick_changed',seed,shot['shot_uuid'],[row['color_picks'] for row in rows]))
            assert f"Authored {shot['shot_uuid']} {{literal}} RGB(12, 34, 56) OFF 0" in doc['machine_prompt']
            key = agent._hmb_slot_key(base.CHANNEL,shot['shot_uuid'])
            for name in ('additional_context','output_schema'):
                assert agent._hmb_shot_slots[key]['values'][name] == expected_agent[shot['shot_uuid']][name]
            assert finish._hmb_finish_look_shot_snapshot_for(channel_uuid=base.CHANNEL,shot_uuid=shot['shot_uuid'])['finish_look_state'] == expected_finish[shot['shot_uuid']]
        selected_agent=agent._hmb_shot_channel_subscription()
        def native_layout_ready():
            current=list(agent.root_ui_element.children)
            body=list(agent._hmb_native_editor_elements)
            selected_row=agent.get_parameter_by_name(agents._AGENT_SHOT_ROW_PREFIX+str(selected_agent['shot_number']))
            if selected_row not in current:return False
            offset=current.index(selected_row)+1
            return current[offset:offset+len(body)]==body and all(sum(item is element for item in current)==1 for element in body)
        try:
            await base.settle(native_layout_ready,seconds=4)
        except AssertionError:
            print('RANDOM_AGENT_LAYOUT_UNHYDRATED '+json.dumps(dict(seed=seed,active=selected_agent,
                root_order=[str(getattr(item,'name','')) for item in agent.root_ui_element.children],
                body=[str(getattr(item,'name','')) for item in agent._hmb_native_editor_elements])),flush=True)
            raise
        # Standard's public prompt Parameter officially strips outer whitespace.
        # This is presentation only; machine-prompt literal equality above is
        # never normalized or relaxed.
        expected_visible=prompt._hmb_prompt_shot_document(channel_uuid=base.CHANNEL,shot_uuid=selected_agent['shot_uuid'])['visible_prompt'].strip()
        try:
            await base.settle(lambda:str(agent._native_parameter_value('prompt','') or '')==expected_visible,seconds=4)
        except AssertionError:
            actual=agent._native_parameter_value('prompt','')
            print('RANDOM_AGENT_PREVIEW_UNHYDRATED '+json.dumps(dict(seed=seed,active=selected_agent['shot_uuid'],
                actual_type=type(actual).__name__,actual_length=len(str(actual or '')),expected_length=len(expected_visible),
                differences=[dict(operation=tag,actual=str(actual or '')[a:b][:160],expected=expected_visible[c:d][:160]) for tag,a,b,c,d in difflib.SequenceMatcher(None,str(actual or ''),expected_visible).get_opcodes() if tag!='equal'],
                preview_active=bool(getattr(agent,'_hmb_prompt_preview_active',False)),
                cached_preview_length=len(str(getattr(agent,'_hmb_prompt_preview_value','') or '')))),flush=True)
            raise
        checkpoint_timings.append(time.perf_counter()-checkpoint_start)
    def source_edit(route):
        source=nodes[base.KINDS[0]]
        state=source._current_state()
        route['generation']=max(route['generation'],state['shot_routing']['generation'])+1
        edit=dict(schema=images.IMAGE_ASSET_EDIT_SCHEMA,version=1,scan_revision=state['scan_revision'],ui_edit_revision=state[images.UI_EDIT_REVISION_KEY]+1,
            catalog_identity={key:state[key] for key in ('catalog_root','project_root','project_uid','project_cache_uid','manifest_signature','folder_signature','scan_revision')},
            selected_source_uids=[row['source_uid'] for row in sorted(state['assets'],key=lambda row:row['selection_order']) if row['selected']],edits={'shot_routing':route})
        send(SetParameterValueRequest(node_name=source.name,parameter_name=images.WIDGET_STATE_PARAMETER,value=json.dumps(edit)))
    def authoring_probe(stage):
        if os.environ.get('HMB_RANDOM_DIAGNOSTICS')!='1':return
        prompt=nodes[base.KINDS[2]]
        exported=prompt._hmb_prompt_merge_snapshot()
        def stripped(value):
            if isinstance(value,str):value=json.loads(value)
            return dict(shot=value.get('shot'),ui=value.get(prompts.UI_EDIT_REVISION_KEY),source=value.get(prompts.SOURCE_SYNC_REVISION_KEY),
                colors=[(row.get('asset_source_uid'),row.get('color_picks')) for row in value.get('images',[]) if row.get('asset_source_uid')])
        print('RANDOM_AUTHORING_PROBE '+json.dumps(dict(stage=stage,state=stripped(exported['state']),raw=stripped(exported['raw_widget']),
            documents={key:stripped(value) for key,value in exported['materialized_documents'].items()})),flush=True)
        print('RANDOM_GENERATOR_PROBE '+json.dumps(dict(stage=stage,
            subscriptions={node.name:node._hmb_shot_channel_subscription() for node in nodes[base.KINDS[5]]})),flush=True)
    async def replace(kind):
        candidate = rng.choice(nodes[kind]) if kind==base.KINDS[5] else nodes[kind]
        pool={}
        serialized=send(SerializeNodeToCommandsRequest(node_name=candidate.name,unique_parameter_uuid_to_values=pool,serialize_all_parameter_values=True))
        if kind==base.KINDS[0]:authoring_probe('before_asset_delete')
        await asend(DeleteNodeRequest(node_name=candidate.name))
        if kind==base.KINDS[0]:authoring_probe('after_asset_delete')
        assert candidate._hmb_node_deleted is True and candidate.name not in flow.nodes
        if kind==base.KINDS[3] and os.environ.get('HMB_RANDOM_DIAGNOSTICS')=='1':
            cls=agents.HMBAgentLibrary
            original_layout=cls._hmb_layout_shot_editor
            original_set=cls.set_parameter_value
            original_reorder=cls.reorder_elements
            def structure(owner):
                raw=owner._native_parameter_value(agents._AGENT_WIDGET_PARAMETER,{})
                raw=raw if isinstance(raw,dict) else {}
                live=getattr(owner,'_hmb_shot_catalog_snapshot',{}) or {}
                saved=raw.get('shot_catalog',{}) or {}
                return dict(name=owner.name,raw_shot=raw.get('shot'),
                    live_catalog_count=len(live.get('shots',[])),saved_catalog_count=len(saved.get('shots',[])),
                    rows=[(number,owner._native_parameter_value(agents._AGENT_SHOT_ROW_PREFIX+str(number),{})) for number in range(1,6)],
                    root_order=[str(getattr(item,'name','')) for item in getattr(getattr(owner,'root_ui_element',None),'children',[])],
                    body=[str(getattr(item,'name','')) for item in getattr(owner,'_hmb_native_editor_elements',[])])
            def trace_layout(owner,*args,**kwargs):
                record=dict(kind='layout',before=structure(owner),kwarg_names=list(kwargs),
                    restored_catalog_count=len((kwargs.get('restored_catalog') or {}).get('shots',[])),
                    stack=[f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' for frame in traceback.extract_stack(limit=7)[:-1]])
                result=original_layout(owner,*args,**kwargs)
                record['after']=structure(owner)
                print('RANDOM_AGENT_HYDRATION_TRACE '+json.dumps(record),flush=True)
                return result
            def trace_set(owner,name,value,*args,**kwargs):
                observed=str(name) in (agents._AGENT_WIDGET_PARAMETER,agents._AGENT_SHOT_STORE_PARAMETER)
                if observed:print('RANDOM_AGENT_HYDRATION_TRACE '+json.dumps(dict(kind='set_before',parameter=str(name),kwargs=kwargs,structure=structure(owner))),flush=True)
                result=original_set(owner,name,value,*args,**kwargs)
                if observed:print('RANDOM_AGENT_HYDRATION_TRACE '+json.dumps(dict(kind='set_after',parameter=str(name),structure=structure(owner))),flush=True)
                return result
            def trace_root(owner,*args,**kwargs):
                record=dict(kind='reorder',before=structure(owner),requested=args,
                    stack=[f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' for frame in traceback.extract_stack(limit=8)[:-1]])
                result=original_reorder(owner,*args,**kwargs)
                record['after']=structure(owner)
                print('RANDOM_AGENT_HYDRATION_TRACE '+json.dumps(record),flush=True)
                return result
            observer_guard.enter_context(mock.patch.object(cls,'_hmb_layout_shot_editor',trace_layout))
            observer_guard.enter_context(mock.patch.object(cls,'set_parameter_value',trace_set))
            observer_guard.enter_context(mock.patch.object(cls,'reorder_elements',trace_root))
        commands=deepcopy(serialized.serialized_node_commands)
        commands.create_node_command.node_name=candidate.name
        commands.create_node_command.override_parent_flow_name=flow.name
        result=await asend(DeserializeNodeFromCommandsRequest(serialized_node_commands=commands))
        replacement=engine.node_manager.get_node_by_name(result.node_name)
        for indirect in serialized.set_parameter_value_commands:
            request=deepcopy(indirect.set_parameter_value_command)
            request.node_name=replacement.name
            request.value=decode_value(deepcopy(pool[indirect.unique_value_uuid]))
            request.initial_setup=True
            send(request)
        if kind==base.KINDS[5]:nodes[kind][nodes[kind].index(candidate)]=replacement
        else:nodes[kind]=replacement
        assert replacement is not candidate
        await base.settle(graph_ready,seconds=4)
        if kind==base.KINDS[0]:authoring_probe('after_asset_restore')
    operation_choices = ['rename','reorder','deselect','prompt_select','agent_select','finish_select','reconnect','foreign']
    planned = [('replace',kind) for kind in base.KINDS]
    planned += [('reconnect',None)]*10
    planned += [(rng.choice(operation_choices + ['replace']*2),None) for _ in range(count-len(planned))]
    rng.shuffle(planned)
    checkpoint_count=0
    try:
        await verify();checkpoint_count+=1
        for index,(operation,kind) in enumerate(planned):
            if os.environ.get('HMB_RANDOM_STOP_AFTER') and index>=int(os.environ['HMB_RANDOM_STOP_AFTER']):break
            start=time.perf_counter()
            try:
                shots=current_shots()
                if operation=='replace':
                    kind=kind or rng.choice(base.KINDS)
                    await replace(kind)
                elif operation=='reconnect':
                    edge=rng.choice(sorted(base.edges(engine,flow)))
                    fields=dict(source_node_name=edge[0],source_parameter_name=edge[1],target_node_name=edge[2],target_parameter_name=edge[3])
                    await asend(DeleteConnectionRequest(**fields))
                    if edge not in base.edges(engine,flow):send(CreateConnectionRequest(**fields))
                elif operation=='rename':
                    # Flush the preceding action's asynchronous preview before
                    # measuring catalog-only writes. Reordering selected media
                    # legitimately updates its visible Prompt/Agent preview.
                    await asyncio.sleep(.15)
                    source=nodes[base.KINDS[0]];route=deepcopy(source._current_state()['shot_routing'])
                    active=nodes[base.KINDS[3]]._hmb_shot_channel_subscription()['shot_uuid']
                    other=[shot for shot in route['shots'] if shot['shot_uuid']!=active]
                    left,right=rng.sample(other,2)
                    left['number'],right['number']=right['number'],left['number']
                    left['name']=f'Seed{seed} revision{index}'
                    left['revision']+=1;right['revision']+=1
                    route['shots'].sort(key=lambda row:row['number'])
                    agent=nodes[base.KINDS[3]]
                    before={name:deepcopy(agent._native_parameter_value(name,None)) for name in ('model_provider','provider','model','prompt','additional_context','tools','rulesets','output_schema')}
                    active_doc_before=nodes[base.KINDS[2]]._hmb_prompt_shot_document(channel_uuid=base.CHANNEL,shot_uuid=active)
                    body_writes=[];native=agents.HMBAgentLibrary.__mro__[1];setter=native.set_parameter_value
                    reorder_records=[];native_reorder=agent.reorder_elements
                    def ui_order():
                        return [(str(getattr(item,'name','')),str(getattr(item,'element_id','')),id(item)) for item in agent.root_ui_element.children]
                    order_before=ui_order()
                    def traced_reorder(*args,**kwargs):
                        record=dict(before=ui_order(),requested=args,
                            stack=[f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' for frame in traceback.extract_stack(limit=12)[:-1]])
                        result=native_reorder(*args,**kwargs)
                        record['after']=ui_order();reorder_records.append(record)
                        return result
                    def record(owner,name,*args,**kwargs):
                        if owner is agent and name in before:body_writes.append(name)
                        return setter(owner,name,*args,**kwargs)
                    with mock.patch.object(native,'set_parameter_value',record),mock.patch.object(agent,'reorder_elements',side_effect=traced_reorder) as reorder:
                        source_edit(route)
                        try:
                            await base.settle(lambda:agent._hmb_shot_catalog_snapshot['generation']>=route['generation'],seconds=4)
                        except AssertionError:
                            live=source._current_state()
                            routing=__import__('_hmb_shot_routing')
                            pending=routing._POST_REGISTRATION_PENDING.get(source)
                            print('RANDOM_CATALOG_DELIVERY_FAILURE '+json.dumps(dict(seed=seed,index=index,
                                requested_generation=route['generation'],source_generation=live['shot_routing']['generation'],
                                source_ui_revision=live.get(images.UI_EDIT_REVISION_KEY),
                                source_accepted_revisions=getattr(source,'_hmb_last_accepted_widget_revisions',None),
                                agent_catalog=getattr(agent,'_hmb_shot_catalog_snapshot',{}),
                                hydration_adopted=bool(getattr(source,'_hmb_hydration_adopted',False)),
                                reserved_catalog_identity=getattr(source,'_hmb_reserved_shot_catalog_identity',''),
                                reconciled_catalog_identity=getattr(source,'_hmb_last_reconciled_shot_catalog_identity',''),
                                source_pending={name:getattr(pending,name,None) for name in ('generation','phase','fingerprint','owner_token')},
                                authority_fingerprints={node.name:dict(current=routing._subscription_fingerprint(node),
                                    accepted=routing._AUTHORITATIVE_FINGERPRINTS.get(node)) for node in [source,agent,nodes[base.KINDS[2]],nodes[base.KINDS[4]]]},
                                current_catalog=source._hmb_shot_routing_catalog(),
                                route_status={node.name:getattr(node,'_hmb_shot_route_status',{}) for node in [source,agent,nodes[base.KINDS[2]]]},
                                edges=len(base.edges(engine,flow)))),flush=True)
                            raise
                        await asyncio.sleep(.03)
                        if body_writes or reorder.call_count:
                            after_prompt=agent._native_parameter_value('prompt',None)
                            left_text,right_text=str(before['prompt']),str(after_prompt)
                            differences=[dict(operation=tag,before=left_text[a:b][:160],after=right_text[c:d][:160])
                                for tag,a,b,c,d in difflib.SequenceMatcher(None,left_text,right_text).get_opcodes() if tag!='equal']
                            active_doc_after=nodes[base.KINDS[2]]._hmb_prompt_shot_document(channel_uuid=base.CHANNEL,shot_uuid=active)
                            print('RANDOM_AGENT_PREVIEW_CHANGE '+json.dumps(dict(seed=seed,index=index,active=active,
                                native_before_matches_current_document=before['prompt']==active_doc_before['visible_prompt'].strip(),
                                native_after_matches_current_document=after_prompt==active_doc_after['visible_prompt'].strip(),
                                canonical_visible_changed=active_doc_before['visible_prompt']!=active_doc_after['visible_prompt'],
                                differences=differences,root_before=order_before,root_after=ui_order(),reorders=reorder_records)),flush=True)
                        assert body_writes==[] and reorder.call_count==0,(body_writes,reorder.call_count,active,
                            {name:before[name]==agent._native_parameter_value(name,None) for name in before})
                    assert before=={name:agent._native_parameter_value(name,None) for name in before}
                elif operation in ('reorder','deselect'):
                    route=deepcopy(nodes[base.KINDS[0]]._current_state()['shot_routing'])
                    shot=rng.choice(route['shots']);old_uids=list(shot['selected_source_uids'])
                    if operation=='reorder':shot['selected_source_uids'].reverse();shot['revision']+=1;source_edit(route)
                    else:
                        shot['selected_source_uids']=old_uids[:1];shot['revision']+=1;source_edit(route)
                        await verify(subset_uuid=shot['shot_uuid'],subset_uids=old_uids[:1]);checkpoint_count+=1
                        route=deepcopy(nodes[base.KINDS[0]]._current_state()['shot_routing'])
                        restore=next(row for row in route['shots'] if row['shot_uuid']==shot['shot_uuid'])
                        restore['selected_source_uids']=old_uids;restore['revision']+=1;source_edit(route)
                elif operation=='prompt_select':
                    prompt=nodes[base.KINDS[2]];shot=rng.choice(shots)
                    value=prompts._select_prompt_shot_document(prompt._current_state(),dict(shot,channel_uuid=base.CHANNEL))
                    value[prompts.UI_EDIT_REVISION_KEY]=max(int(value.get(prompts.UI_EDIT_REVISION_KEY) or 0),int(prompt._current_state().get(prompts.UI_EDIT_REVISION_KEY) or 0))+1
                    send(SetParameterValueRequest(node_name=prompt.name,parameter_name=prompts.WIDGET_PARAMETER_NAME,value=prompts._json_dumps(value)))
                elif operation=='agent_select':
                    agent=nodes[base.KINDS[3]];shot=rng.choice(shots)
                    send(SetParameterValueRequest(node_name=agent.name,parameter_name=agents._AGENT_WIDGET_PARAMETER,value=agent._hmb_widget_value(dict(shot,channel_uuid=base.CHANNEL),nodes[base.KINDS[0]]._hmb_shot_routing_catalog(),shot_manager=True)))
                elif operation=='finish_select':
                    finish=nodes[base.KINDS[4]];value=deepcopy(finish._widget_state)
                    value['shot']=dict(rng.choice(shots),channel_uuid=base.CHANNEL)
                    send(SetParameterValueRequest(node_name=finish.name,parameter_name=finishes.WIDGET_PARAMETER_NAME,value=value))
                elif operation=='foreign':
                    prompt=nodes[base.KINDS[2]];before=deepcopy(prompt.get_parameter_value(prompts.WIDGET_PARAMETER_NAME))
                    for channel,shot in [('99999999-9999-4999-8999-999999999999',shots[0]['shot_uuid']),(base.CHANNEL,'99999999-9999-4999-8999-999999999999')]:
                        try:prompt._hmb_prompt_shot_document(channel_uuid=channel,shot_uuid=shot)
                        except (ValueError,RuntimeError):pass
                        else:raise AssertionError('Foreign channel/shot was accepted')
                    assert before==prompt.get_parameter_value(prompts.WIDGET_PARAMETER_NAME)
                await verify();checkpoint_count+=1
                elapsed=time.perf_counter()-start
                timings.setdefault(operation,[]).append(elapsed)
                actions.append(dict(index=index,operation=operation,kind=kind,ms=round(elapsed*1000,3)))
                if (index+1)%10==0:
                    print('RANDOM_LIFECYCLE_PROGRESS '+json.dumps(dict(seed=seed,completed=index+1,native_action_requests=request_count,checkpoint_count=checkpoint_count)),flush=True)
            except BaseException:
                print('RANDOM_LIFECYCLE_FAILURE '+json.dumps(dict(seed=seed,index=index,operation=operation,kind=kind,last_completed_actions=actions[-5:])),flush=True)
                raise
        await asyncio.sleep(.15)
        assert not base.ATTEMPTS
        record=dict(seed=seed,passed=True,creation_order=order,logical_actions=len(actions),native_action_requests=request_count,
            checkpoints=checkpoint_count,exact_shot_UUIDs=5,exact_documents=5,retained_edges=23,
            action_timings_including_checkpoints={key:summary(value) for key,value in timings.items()},
            native_request_timings={key:summary(value) for key,value in native_timings.items()},
            checkpoint_timings=summary(checkpoint_timings),event_loop_lag_including_assertion_work=summary(lag),actions=actions,
            execution_calls=0,external_network_calls=0,paid_calls=0,user_workflow_calls=0)
        RESULTS.append(record)
        print('RANDOM_LIFECYCLE_SEED_PASS '+json.dumps({key:value for key,value in record.items() if key!='actions'}),flush=True)
    finally:
        stop.set();await pulse
        observer_guard.close()
        for record in preview_records:
            print('RANDOM_AGENT_PREVIEW_TRACE '+json.dumps(record),flush=True)
        for args,kwargs in deferred_cleanup:original_unregister(*args,**kwargs)

def main():
    try:from griptape_nodes.retained_mode.engine import engine_scope
    except ImportError:
        print('HMB_LIBRARY_RANDOM_LIFECYCLE_HOST=SKIP (installed SDK required)');return
    seeds=[int(value) for value in os.environ.get('HMB_RANDOM_SEEDS','41,1701,8303').split(',')]
    count=int(os.environ.get('HMB_RANDOM_ACTIONS','100'))
    assert count>=16
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix='hmb-random-lifecycle-sdk-') as temp:
        folder=Path(temp)
        env={key:str(folder/leaf) for key,leaf in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('LOCALAPPDATA','local'),('APPDATA','app'),('GTN_ENGINE_CONFIG_DIR','engine'),('GTN_ENGINE_DATA_DIR','engine-data'),('GTN_ENGINE_STATE_DIR','engine-state'),('GTN_CONFIG_WORKSPACE_DIRECTORY','workspace'),('HMB_IMAGE_PROJECTS_ROOT','Projects'))}
        for value in env.values():Path(value).mkdir(parents=True,exist_ok=True)
        with mock.patch.dict(os.environ,env),ExitStack() as guard:
            os.chdir(folder)
            try:
                modules={name:__import__(name) for name in base.KINDS}
                import _hmb_library_bootstrap as bootstrap
                for module in modules.values():guard.enter_context(mock.patch.object(getattr(module,module.__name__),'process',base.deny))
                guard.enter_context(mock.patch.object(modules[base.KINDS[0]].HMBImageAssetLibrary,'_schedule_catalog_scan',lambda *a,**k:False))
                guard.enter_context(mock.patch.object(bootstrap._Registration,'start_web_worker',lambda *a,**k:None))
                guard.enter_context(mock.patch.object(socket,'create_connection',base.deny))
                logging.disable(logging.CRITICAL)
                project_state=base.create_project(modules[base.KINDS[0]],folder)
                for seed in seeds:
                    with engine_scope() as engine:
                        with asyncio.Runner() as runner:runner.run(seed_scenario(engine,modules,project_state,seed,count))
                assert not base.ATTEMPTS
                print('HMB_LIBRARY_RANDOM_LIFECYCLE_HOST=PASS '+json.dumps(dict(seeds=RESULTS,logical_actions=sum(row['logical_actions'] for row in RESULTS),execution_calls=0,paid_calls=0)),flush=True)
            finally:
                logging.shutdown();os.chdir(previous)

if __name__=='__main__':main()
