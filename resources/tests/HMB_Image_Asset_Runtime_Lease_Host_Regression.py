"""Actual retained SDK: live widget lease rejects retired replay and preserves import/copy.



Synthetic data only. No user workflow execution, real catalog scan or live app.

"""

from __future__ import annotations

import asyncio

import base64

from copy import deepcopy

import hashlib

from io import BytesIO

import json

import logging

import os

from pathlib import Path

import socket

import sys

import tempfile

from unittest import mock

from uuid import uuid4



ROOT=Path(__file__).resolve().parents[2]

OUT=Path(os.environ.get('HMB_RUNTIME_LEASE_REPORT_DIR',str(ROOT/'reports/regression-checks/HMB_Image_Asset_Runtime_Lease_Host_Regression')))

OUT.mkdir(parents=True,exist_ok=True)

INSTALLED=Path(os.environ.get('HMB_RUNTIME_LEASE_SOURCE_ROOT',str(ROOT)))

sys.path.insert(0,str(INSTALLED));sys.dont_write_bytecode=True



async def exercise(engine):

    import HMBImageAssetLibrary as product

    from griptape_nodes.node_library.library_registry import LibraryRegistry,LibrarySchema

    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest

    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest,DeleteNodeRequest

    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

    schema=LibrarySchema.model_validate_json((INSTALLED/'griptape-nodes-library.json').read_text('utf-8-sig'))

    library=LibraryRegistry.generate_new_library(schema)

    metadata=next(row.metadata for row in schema.nodes if row.class_name=='HMBImageAssetLibrary')

    library.register_lazy_node_type('HMBImageAssetLibrary',metadata,lambda:product.HMBImageAssetLibrary)

    engine.event_manager.initialize_queue();cases=[]

    def send(request,ok=True):

        request.broadcast_result=False

        result=engine.handle_request(request)

        assert result.succeeded()==ok,str(result.result_details)

        return result

    flow=send(EnsureWorkflowAndFlowRequest(flow_name='WidgetRuntimeLease'))

    def create(name):

        made=send(CreateNodeRequest(node_type='HMBImageAssetLibrary',specific_library_name=schema.name,

            node_name=name,override_parent_flow_name=flow.flow_name,initial_setup=True,create_error_proxy_on_failure=False))

        node=engine.node_manager.get_node_by_name(made.node_name)

        node._hmb_initial_catalog_scan_pending=False

        return node

    def setstate(node,value,initial=False,output=False,ok=True):

        return send(SetParameterValueRequest(node_name=node.name,parameter_name=product.WIDGET_STATE_PARAMETER,

            value=deepcopy(value),initial_setup=initial,is_output=output),ok)

    def current(node):return deepcopy(node._current_state())

    state=product._default_state()

    state['assets']=[dict(asset_library_id='import:'+name,source_uid='import:'+name,source_kind='user',

        asset_id=name,image_name=name,path='data:image/png;base64,AA==',selected=False,selection_order=0,

        import_index=index+1,connected=True,registered=False,media_ref_kind='url',media_signature='synthetic-'+name)

        for index,name in enumerate(('a','b'))]

    state['scan_revision']=1;state['ui_edit_revision']=4

    state['image_bash_workspace']={'workspace_id':str(uuid4()),'revision':2,

        'instances':[{'instance_id':str(uuid4()),'source_uid':'import:'+name} for name in ('a','b')]}

    state['image_bash_active']=True;state=product._normalize_state(state)

    old3=deepcopy(state);old3['ui_edit_revision']=5;old3['image_bash_workspace']['revision']=3

    old3['image_bash_workspace']['instances'].append({'instance_id':str(uuid4()),'source_uid':'import:b'})

    def compact(value):

        return {'schema':product.IMAGE_ASSET_EDIT_SCHEMA,'version':1,'ui_edit_revision':value['ui_edit_revision'],

            'widget_runtime_lease':value.get('widget_runtime_lease',''),

            'catalog_identity':{key:value[key] for key in ('catalog_root','project_root','project_uid','project_cache_uid','manifest_signature','folder_signature','scan_revision')},

            'selected_source_uids':[],'edits':{'shot_routing':deepcopy(value['shot_routing']),

                'image_bash_workspace':deepcopy(value['image_bash_workspace']),'image_bash_active':True}}

    try:

        with (mock.patch.object(product,'_discover_project_catalog',side_effect=AssertionError('No scan')),

              mock.patch.object(product,'_scan_project_assets',side_effect=AssertionError('No scan'))):

            node=create('LeaseReceiver')

            fresh=current(node);lease=node._hmb_widget_runtime_lease

            assert fresh['widget_runtime_lease']==lease

            assert node.get_parameter_value(product.THUMBNAIL_PATCH_PARAMETER)['widget_runtime_lease']==lease

            cases.append('offline_empty_authority_immediate')

            setstate(node,state,initial=True)

            setstate(node,state,initial=True,output=True)

            assert current(node)['image_bash_workspace']==state['image_bash_workspace']

            assert current(node)['widget_runtime_lease']==lease

            cases.append('legacy_initial_and_duplicate_output_restore')

            savedbridge={'schema':product.THUMBNAIL_BRIDGE_SCHEMA,'version':1,'operation':'cgt_confirm','phase':'request',

                'request_id':'saved-do-not-replay','runtime_instance_id':state['shot_routing']['publisher_instance_uuid'],

                'widget_runtime_lease':str(uuid4()),'hierarchy_request':{'must_not_execute':True}}

            for output in (False,True):

                send(SetParameterValueRequest(node_name=node.name,parameter_name=product.THUMBNAIL_PATCH_PARAMETER,

                    value=savedbridge,initial_setup=True,is_output=output))

                bridge=node.get_parameter_value(product.THUMBNAIL_PATCH_PARAMETER)

                assert bridge['operation']=='idle' and bridge['widget_runtime_lease']==lease

            cases.append('saved_bridge_commands_inert_both_native_slots')

            before=current(node)

            for label,value in [('missing_full',old3),('missing_compact',compact(old3)),

                    ('old_full',dict(old3,widget_runtime_lease=str(uuid4()))),('old_compact',dict(compact(old3),widget_runtime_lease=str(uuid4())))]:

                setstate(node,value,ok=False);assert current(node)==before;cases.append(label+'_reject_unchanged')

            setstate(node,old3,initial=True,ok=False);assert current(node)==before

            cases.append('manual_initial_overwrite_authored_rejected')

            live3=dict(old3,widget_runtime_lease=lease)

            copy_value=compact(live3)
            copy_value['edits'][product.IMAGE_BASH_WORKSPACE_EDIT_KEY]={
                'schema':product.IMAGE_BASH_WORKSPACE_EDIT_SCHEMA,'version':1,'operation_id':str(uuid4()),
                'operation':'copy','workspace_id':state['image_bash_workspace']['workspace_id'],
                'expected_revision':state['image_bash_workspace']['revision'],
                'instance_id':state['image_bash_workspace']['instances'][1]['instance_id'],
                'new_instance_id':live3['image_bash_workspace']['instances'][2]['instance_id']}
            setstate(node,copy_value)

            assert len(current(node)['image_bash_workspace']['instances'])==3

            assert current(node)['image_bash_workspace']['instances'][1]['source_uid']==current(node)['image_bash_workspace']['instances'][2]['source_uid']

            cases.append('intentional_copy_same_catalog_preserved')

            setstate(node,state,initial=True,ok=False);assert len(current(node)['image_bash_workspace']['instances'])==3

            cases.append('legacy_restore_cannot_rollback_live_edit')

            req={'schema':product.THUMBNAIL_BRIDGE_SCHEMA,'version':1,'operation':'widget_authority','phase':'request','request_id':'authority-1','runtime_instance_id':'old'}

            for staleoperation in ('cgt_catalog','cgt_confirm','catalog_page','hydrate','catalog_probe'):

                stale_request={'schema':product.THUMBNAIL_BRIDGE_SCHEMA,'version':1,'operation':staleoperation,'phase':'request',

                    'request_id':'retired','runtime_instance_id':state['shot_routing']['publisher_instance_uuid'],

                    'widget_runtime_lease':str(uuid4())}

                send(SetParameterValueRequest(node_name=node.name,parameter_name=product.THUMBNAIL_PATCH_PARAMETER,value=stale_request),False)

            cases.append('retired_bridge_commands_rejected_before_workers')

            for method in ('_consume_cgt_work_results','_consume_cgt_result','_consume_catalog_search_result','_consume_pending_catalog_probe_result','_consume_pending_import_thumbnail_result'):

                setattr(node,method,lambda:(_ for _ in ()).throw(AssertionError('Authority must not consume')))

            with mock.patch.object(engine.event_manager, "put_event", wraps=engine.event_manager.put_event) as publish:
                setter_result=send(SetParameterValueRequest(node_name=node.name,parameter_name=product.THUMBNAIL_PATCH_PARAMETER,value=req))

            result=node.get_parameter_value(product.THUMBNAIL_PATCH_PARAMETER)

            assert result['phase']=='result' and result['request_id']=='authority-1' and result['widget_runtime_lease']==lease
            assert setter_result.finalized_value == result
            views=[call.args[0].wrapped_event for call in publish.call_args_list
                   if getattr(getattr(getattr(call.args[0], "wrapped_event", None), "payload", None), "parameter_name", None)
                   == product.WIDGET_STATE_PARAMETER]
            assert any(view.workflow_id == node._event_workflow_id() and view.workflow_id for view in views)
            recovery = send(SetParameterValueRequest(node_name=node.name,
                parameter_name=product.THUMBNAIL_PATCH_PARAMETER,
                value=dict(req, request_id="authority-recovery", include_view=True))).finalized_value
            assert recovery["request_id"] == "authority-recovery"
            view = json.loads(recovery["canonical_view"])
            assert product._image_bash_widget_authority_scope(view) == recovery["canonical_scope"]

            assert current(node)['image_bash_workspace']==live3['image_bash_workspace']

            cases.append('readonly_authority_no_consumes_or_semantic_edit')

            def check_authority_failure(request_id, error):
                runtime = before["shot_routing"]["publisher_instance_uuid"]
                send(SetParameterValueRequest(
                    node_name=node.name, parameter_name=product.THUMBNAIL_PATCH_PARAMETER,
                    value=dict(req, request_id=request_id, runtime_instance_id=runtime),
                ))
                response = node.get_parameter_value(product.THUMBNAIL_PATCH_PARAMETER)
                assert response["authority_error"] == error
                assert response["request_id"] == request_id
                assert response["request_runtime_instance_id"] == runtime
                assert response["canonical_node_name"] == node.name
                assert "canonical_scope" not in response

            accepted = current(node)
            with mock.patch.object(node, "_current_state", return_value=dict(
                accepted, scan_revision=accepted["scan_revision"] + 1
            )):
                check_authority_failure("authority-scope-changing", "state_changed")
            with mock.patch.object(node, "_catalog_page_projection", return_value={
                "synthetic": "x" * product.MAX_IMAGE_BASH_AUTHORITY_VIEW_BYTES
            }):
                check_authority_failure("authority-oversized-view", "view_too_large")
            with mock.patch.object(node, "_catalog_page_projection", side_effect=RuntimeError("private fixture failure")):
                check_authority_failure("authority-view-unavailable", "unavailable")
                assert "private fixture failure" not in json.dumps(node.get_parameter_value(product.THUMBNAIL_PATCH_PARAMETER))
            assert current(node) == accepted
            cases.append("readonly_authority_safe_scoped_failure_ack")

            node.lock = True
            try:
                result = send(SetParameterValueRequest(
                    node_name=node.name, parameter_name=product.THUMBNAIL_PATCH_PARAMETER,
                    value=dict(req, request_id="authority-locked"),
                ), False)
                assert "locked" in str(result.result_details).lower()
            finally:
                node.lock = False
            assert current(node) == accepted
            cases.append("sdk_locked_authority_does_not_reach_product")

            for injected in ('state','edits','asset_library_ids'):

                send(SetParameterValueRequest(node_name=node.name,parameter_name=product.THUMBNAIL_PATCH_PARAMETER,value=dict(req,**{injected:{}})),False)

            cases.append('readonly_authority_rejects_extra_mutation_fields')

            send(DeleteNodeRequest(node_name=node.name));node=create('LeaseReceiver')

            assert node._hmb_widget_runtime_lease!=lease

            setstate(node,state,initial=True)

            setstate(node,live3,ok=False);assert len(current(node)['image_bash_workspace']['instances'])==2

            cases.append('same_name_recreate_rejects_retired_live_lease')

            rawsaved=dict(state,widget_runtime_lease=lease)

            second=create('SavedOldLease');setstate(second,rawsaved,initial=True)

            assert current(second)['widget_runtime_lease']==second._hmb_widget_runtime_lease!=lease

            cases.append('saved_old_lease_rebound_only_initial')

            legacy=create('PartialLegacy')

            partial={'schema':product.STATE_SCHEMA,'assets':deepcopy(state['assets']),

                'shot_routing':deepcopy(state['shot_routing']),'image_bash_workspace':deepcopy(state['image_bash_workspace'])}

            setstate(legacy,partial,initial=True);setstate(legacy,partial,initial=True,output=True)

            assert current(legacy)['image_bash_workspace']==state['image_bash_workspace']

            cases.append('partial_legacy_normalized_first_and_output_pair')

            contextual=create('ContextInitial')

            with engine.context_manager.node(contextual):

                send(SetParameterValueRequest(node_name=None,parameter_name=product.WIDGET_STATE_PARAMETER,value=state,initial_setup=True))

                send(SetParameterValueRequest(node_name=None,parameter_name=product.WIDGET_STATE_PARAMETER,value=state,initial_setup=True,is_output=True))

            assert current(contextual)['image_bash_workspace']==state['image_bash_workspace']

            cases.append('context_node_initial_and_output_pair')

            outputonly=create('OutputOnlyLive');setstate(outputonly,state,initial=True)

            outputedit=dict(old3,widget_runtime_lease=outputonly._hmb_widget_runtime_lease)

            setstate(outputonly,outputedit,output=True)

            assert outputonly._hmb_widget_live_authored is True

            setstate(outputonly,state,initial=True,ok=False)

            cases.append('is_output_live_edit_retires_initial_exception')

            from griptape_nodes.retained_mode.events.node_events import SerializeSelectedNodesToCommandsRequest,DeserializeSelectedNodesFromCommandsRequest

            serialized=send(SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[[legacy.name,'synthetic']],copy_to_clipboard=False))

            assert json.loads(serialized.serialized_selected_node_commands)

            for value in serialized.pickled_values.values():json.loads(value)

            pasted=send(DeserializeSelectedNodesFromCommandsRequest(deserialize_commands=serialized.serialized_selected_node_commands,pickled_values=serialized.pickled_values))

            pastednode=engine.node_manager.get_node_by_name(pasted.node_names[0])

            assert pastednode._hmb_widget_runtime_lease!=legacy._hmb_widget_runtime_lease

            assert current(pastednode)['image_bash_workspace']==state['image_bash_workspace']

            assert current(pastednode)['widget_runtime_lease']==pastednode._hmb_widget_runtime_lease

            cases.append('actual_selected_node_copy_paste_preserves_workspace_new_lease')

            from griptape_nodes.retained_mode.engine import engine_scope

            with engine_scope() as freshengine:

                freshengine.event_manager.initialize_queue()

                madeflow=freshengine.handle_request(EnsureWorkflowAndFlowRequest(flow_name='FirstPasteNoPriorAsset'))

                assert madeflow.succeeded(),madeflow.result_details

                assert not hasattr(freshengine.event_manager,'_hmb_asset_initial_value_admission')

                firstpaste=freshengine.handle_request(DeserializeSelectedNodesFromCommandsRequest(

                    deserialize_commands=serialized.serialized_selected_node_commands,pickled_values=serialized.pickled_values,broadcast_result=False))

                assert firstpaste.succeeded(),firstpaste.result_details

                firstnode=freshengine.node_manager.get_node_by_name(firstpaste.node_names[0])

                assert current(firstnode)['image_bash_workspace']==state['image_bash_workspace']

                assert current(firstnode)['widget_runtime_lease']==firstnode._hmb_widget_runtime_lease!=legacy._hmb_widget_runtime_lease

                assert hasattr(freshengine.event_manager,'_hmb_asset_initial_value_admission')

            cases.append('first_clipboard_paste_installs_boundary_inside_constructor')

            empty=create('InitialFalseEmpty');setstate(empty,state,ok=False)

            cases.append('pristine_initial_false_legacy_rejected')

            # Host paths may invoke after_value_set after a direct cache write.

            guard_before=product._normalize_state(product._parse_mapping(second._hmb_last_accepted_widget_state))

            try: second.after_value_set(second.get_parameter_by_name(product.WIDGET_STATE_PARAMETER),old3)

            except ValueError: pass

            else: raise AssertionError('After-only stale STATE must reject')

            assert current(second)==guard_before, [(k,guard_before.get(k),current(second).get(k)) for k in set(current(second))|set(guard_before) if current(second).get(k)!=guard_before.get(k)]

            cases.append('after_hook_only_stale_state_rejected')

            import ast,contextvars,inspect

            from types import SimpleNamespace

            from contextvars import copy_context

            bash_source=INSTALLED/'HMBImageBash.py'

            bash_tree=ast.parse(bash_source.read_text('utf-8-sig'))

            installer=next(n for n in bash_tree.body if isinstance(n,ast.FunctionDef) and n.name=='_install_bash_initial_value_admission')

            namespace={'Any':object,'inspect':inspect,'contextvars':contextvars,'_hmb_is_registered_node':lambda *_:False}

            exec(compile(ast.Module(body=[installer],type_ignores=[]),str(bash_source),'exec'),namespace)

            bash=SimpleNamespace(_install_bash_initial_value_admission=namespace['_install_bash_initial_value_admission'])

            mapping=engine.event_manager._request_type_to_manager

            manager=engine.event_manager

            def depth(handler):

                seen=set();count=0

                while callable(handler) and id(handler) not in seen:

                    seen.add(id(handler));count+=1

                    handler=inspect.getclosurevars(handler).nonlocals.get('original') if inspect.isfunction(handler) else None

                return count

            for order in ((product._install_asset_initial_value_admission,bash._install_bash_initial_value_admission),

                          (bash._install_bash_initial_value_admission,product._install_asset_initial_value_admission)):

                for _ in range(40):

                    for install in order:install(engine)

                assert depth(mapping[SetParameterValueRequest])<=3,depth(mapping[SetParameterValueRequest])

            cases.append('alternating_bash_asset_installers_bounded_3')

            saved_handler=mapping[SetParameterValueRequest]

            saved_asset=manager._hmb_asset_initial_value_admission

            saved_bash=manager._hmb_bash_initial_value_admission

            captured=[];sentinel=object()

            witness=create('ContextWitness')

            request=SetParameterValueRequest(node_name=witness.name,parameter_name=product.WIDGET_STATE_PARAMETER,value=state,initial_setup=True)

            def handler(req):

                captured.append(copy_context())

                witness._admit_widget_state(req.value)

                return sentinel

            try:

                mapping[SetParameterValueRequest]=handler

                product._install_asset_initial_value_admission(engine)

                installed=mapping[SetParameterValueRequest]

                assert installed(request) is sentinel

                assert manager._hmb_asset_initial_assignment_context.get() is None

                try:captured[0].run(witness._admit_widget_state,state)

                except ValueError:pass

                else:raise AssertionError('Copied initial context must expire')

                cases.append('copied_context_revoked_finally')

                product._install_asset_initial_value_admission(engine)

                assert mapping[SetParameterValueRequest] is installed

                cases.append('wrapper_reload_style_idempotence')

                class Special:

                    def __call__(self,req):return sentinel

                special=Special();mapping[SetParameterValueRequest]=special

                product._install_asset_initial_value_admission(engine)

                assert mapping[SetParameterValueRequest] is special

                def transparent(req):return special(req)

                transparent.__wrapped__=special

                mapping[SetParameterValueRequest]=transparent

                product._install_asset_initial_value_admission(engine)

                assert mapping[SetParameterValueRequest] is transparent

                cases.append('special_remote_callable_identity_preserved')

                class Foreign:

                    def handler(self,req):return sentinel

                foreign=Foreign().handler;mapping[SetParameterValueRequest]=foreign

                product._install_asset_initial_value_admission(engine)

                assert mapping[SetParameterValueRequest] is foreign

                cases.append('foreign_bound_handler_identity_preserved')

                async def async_handler(req):

                    assert manager._hmb_asset_initial_assignment_context.get()['active'] is True

                    return sentinel

                mapping[SetParameterValueRequest]=async_handler

                product._install_asset_initial_value_admission(engine)

                assert await mapping[SetParameterValueRequest](request) is sentinel

                assert manager._hmb_asset_initial_assignment_context.get() is None

                cases.append('foreign_async_handler_result_preserved')

                failure=RuntimeError('synthetic handler failure')

                def raising(req):raise failure

                mapping[SetParameterValueRequest]=raising

                product._install_asset_initial_value_admission(engine)

                try:mapping[SetParameterValueRequest](request)

                except RuntimeError as exc:assert exc is failure

                else:raise AssertionError('handler failure lost')

                assert manager._hmb_asset_initial_assignment_context.get() is None

                cases.append('foreign_handler_exception_preserved_context_reset')

            finally:

                mapping[SetParameterValueRequest]=saved_handler

                manager._hmb_asset_initial_value_admission=saved_asset

                manager._hmb_bash_initial_value_admission=saved_bash

        result={'status':'PASS','case_count':len(cases),'cases':cases,'source_path':product.__file__,

            'source_sha256':hashlib.sha256(Path(product.__file__).read_bytes()).hexdigest(),

            'no_real_catalog_reads':True,'actual_retained_SDK_hooks':True,'user_files_executed':0,'paid_calls':0,

            'bash_wrapper_source_sha256':hashlib.sha256(bash_source.read_bytes()).hexdigest(),

            'wrapper_composition_uses_exact_Bash_function_AST':True,

            'clipboard_values_all_JSON':True,

            'limitations':['Synthetic metadata-only unlinked Asset; no actualDesktop/nativeBridge inspection here.',

                'Existing Bash wrapper was exact source AST extraction because private engine has no Standard discovery record.']}

        (OUT/'RUNTIME-LEASE-BACKEND.json').write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))

    finally:LibraryRegistry.unregister_library(schema.name,event_manager=engine.event_manager)



if __name__=='__main__':

    previous=Path.cwd()

    with tempfile.TemporaryDirectory(prefix='stale-widget-private-',dir=OUT,ignore_cleanup_errors=True) as temporary:

        directory=Path(temporary);keys=('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY')

        env={key:str(directory/key) for key in keys}

        for value in env.values():Path(value).mkdir()

        with mock.patch.dict(os.environ,env),mock.patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')):

            os.chdir(directory);logging.disable(logging.CRITICAL)

            try:

                from griptape_nodes.retained_mode.engine import engine_scope

                with engine_scope() as engine:asyncio.run(exercise(engine))

            finally:os.chdir(previous);logging.shutdown()
