"""Private installed SDK: refuse racing snapshots, then save/reopen/add nodes.

No original workflow, desktop, Provider, Broker or render is touched. The native
load/serialization handlers remain real; barriers only expose the proven race.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import ExitStack
import contextvars
import hashlib
import importlib
import json
from pathlib import Path
import sys
import threading
import traceback
from unittest import mock
import weakref

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"resources/tests")]
import HMB_Seedance_Execution_Mode_Host_Regression as harness


def snapshot(engine):
    context=engine.context_manager
    return {"workflow":context.get_current_workflow_name() if context.has_current_workflow() else None,
        "flow":context.get_current_flow().name if context.has_current_flow() else None,
        "flows":len(context._workflow_stack[-1]._flow_stack) if context.has_current_workflow() else 0,
        "nodes":tuple(sorted(engine.node_manager._name_to_parent_flow_name))}


async def settle():
    # SDK post hooks are detached; give release notifications their own turns.
    for _ in range(8):await asyncio.sleep(.01)


async def exercise(engine,_phase,out):
    t=importlib.import_module("HMBSeedanceGeneration")
    images=importlib.import_module("HMBImageAssetLibrary")
    finishes=importlib.import_module("HMBFinishLookLibrary")
    luts=importlib.import_module("HMBColorLUTLibrary")
    routing=importlib.import_module("_hmb_shot_routing")
    bootstrap=importlib.import_module("_hmb_library_bootstrap")
    migration=importlib.import_module("_hmb_workflow_migration")
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
    from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowWithCurrentStateRequest,SaveWorkflowFileFromSerializedFlowRequest
    schema=harness.register(engine,{"HMBSeedanceGeneration":t,"HMBImageAssetLibrary":images,
        "HMBFinishLookLibrary":finishes,"HMBColorLUTLibrary":luts})
    library=LibraryRegistry.get_library_for_node_type(node_type="HMBSeedanceGeneration",specific_library_name=schema.name)
    engine.event_manager.initialize_queue()
    registration=bootstrap._Registration(engine,engine.event_manager)
    class Owner:pass
    owner=Owner();registration.owners[owner]=weakref.ref(library)
    manager=engine.event_manager
    manager.add_pre_dispatch_hook(registration.hook)
    for kind in bootstrap._LOAD_TYPES:
        manager.add_post_dispatch_hook(kind,registration.load_post_hook);registration.load_post_types.append(kind)
    for kind in bootstrap._SERIALIZE_TYPES:
        manager.add_post_dispatch_hook(kind,registration.snapshot_post_hook);registration.snapshot_post_types.append(kind)
    try:
        with ExitStack() as guards:
            guards.enter_context(mock.patch.object(registration,"start_web_worker",lambda:None))
            guards.enter_context(mock.patch.object(migration,"schedule_loaded_flow_migrations",lambda *a:None))
            for name in ("schedule_post_registration_reconcile","schedule_post_hydration_reconcile"):
                guards.enter_context(mock.patch.object(routing,name,lambda *a,**k:False))
            guards.enter_context(mock.patch.object(t._HMBAIBrokerBridge,"_request_json",harness.deny))
            guards.enter_context(mock.patch.object(t.HMBSeedanceGeneration,"_process_generation",harness.deny))
            flow_name=harness.send(engine,EnsureWorkflowAndFlowRequest(flow_name="SnapshotGuardSDK")).flow_name
            created=harness.send(engine,CreateNodeRequest(node_type="HMBImageAssetLibrary",specific_library_name=schema.name,
                node_name="Context Source",initial_setup=True,create_error_proxy_on_failure=False))
            source=engine.node_manager.get_node_by_name(created.node_name)
            source._hmb_initial_catalog_scan_pending=False
            original=out/"synthetic-context-workflow.py"
            serialized=harness.send(engine,SerializeFlowToCommandsRequest(flow_name=flow_name)).serialized_flow_commands
            await harness.asend(engine,SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
                file_name=original.stem,file_path=str(original),display_name="Private snapshot guard fixture"))
            await settle()
            assert not registration.snapshot_requests
            await harness.asend(engine,ClearAllObjectStateRequest(i_know_what_im_doing=True))

            # Reproduce the saved-file Node scope where an external snapshot
            # previously could enter and steal the loader's shared Flow scope.
            entered=threading.Event();finished=threading.Event();results=[]
            loader_thread=threading.get_ident();captured=contextvars.copy_context()
            original_push_node=engine.context_manager.push_node;fired=False
            def push_node(node):
                nonlocal fired
                result=original_push_node(node)
                file_scope=any(frame.filename=="<string>" for frame in traceback.extract_stack())
                if not fired and threading.get_ident()==loader_thread and file_scope:
                    fired=True;entered.set();assert finished.wait(15),"External snapshot did not finish"
                return result
            never_written=out/"must-not-write-while-loading.py"
            def external_snapshot():
                try:
                    assert entered.wait(15)
                    before=snapshot(engine)
                    result=engine.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_name,broadcast_result=False))
                    save_result=engine.handle_request(SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
                        file_name=never_written.stem,file_path=str(never_written),display_name="Must refuse",broadcast_result=False))
                    results.append((result.succeeded(),save_result.succeeded(),before==snapshot(engine)))
                    assert not result.succeeded() and not save_result.succeeded()
                    assert "not queued" in str(result.result_details)
                finally:finished.set()
            worker=threading.Thread(target=captured.run,args=(external_snapshot,))
            worker.start()
            with mock.patch.object(engine.context_manager,"push_node",push_node):
                loaded=await engine.ahandle_request(RunWorkflowWithCurrentStateRequest(file_path=str(original),broadcast_result=False))
            worker.join(20);assert not worker.is_alive()
            assert loaded.succeeded(),str(loaded.result_details)
            await settle()
            assert results==[(False,False,True)] and not never_written.exists()
            assert snapshot(engine)["flows"]==1 and not registration.load_requests
            harness.record("load_then_external_serialize_and_save_refused_without_scope_or_file_change")

            source=engine.node_manager.get_node_by_name("Context Source")
            source._hmb_initial_catalog_scan_pending=False
            ready=threading.Event();release=threading.Event();first_results=[]
            original_getter=source._get_raw_parameter_value;paused=False
            def pause_serializer(name):
                nonlocal paused
                if not paused and threading.get_ident()!=loader_thread:
                    paused=True;ready.set();assert release.wait(20)
                return original_getter(name)
            captured=contextvars.copy_context()
            def first_serialize():
                first_results.append(engine.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_name,broadcast_result=False)))
            active=threading.Thread(target=captured.run,args=(first_serialize,))
            before=snapshot(engine);original_digest=hashlib.sha256(original.read_bytes()).hexdigest()
            with mock.patch.object(source,"_get_raw_parameter_value",pause_serializer):
                active.start()
                assert await asyncio.to_thread(ready.wait,15)
                # Different async owner: serialization is refused immediately.
                second=engine.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_name,broadcast_result=False))
                reverse=await engine.ahandle_request(RunWorkflowWithCurrentStateRequest(file_path=str(original),broadcast_result=False))
                assert not second.succeeded() and not reverse.succeeded()
                assert "not queued" in str(second.result_details)
                release.set()
                await asyncio.to_thread(active.join,20)
            assert not active.is_alive() and first_results[0].succeeded()
            await settle()
            assert snapshot(engine)==before and not registration.snapshot_requests
            assert not registration.snapshot_refused_loads
            assert hashlib.sha256(original.read_bytes()).hexdigest()==original_digest
            harness.record("concurrent_serialize_and_reverse_load_refused_first_serializer_completes_context_preserved")

            # A busy refusal is temporary. Normal native save and cold graph
            # restore remain available after the exact request posts release.
            new_saved=out/"after-busy-native-save.py"
            final_commands=harness.send(engine,SerializeFlowToCommandsRequest(flow_name=flow_name)).serialized_flow_commands
            await harness.asend(engine,SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=final_commands,
                file_name=new_saved.stem,file_path=str(new_saved),display_name="Save after refusal"))
            await settle()
            await harness.asend(engine,ClearAllObjectStateRequest(i_know_what_im_doing=True))
            reopened=await engine.ahandle_request(RunWorkflowWithCurrentStateRequest(file_path=str(new_saved),broadcast_result=False))
            assert reopened.succeeded(),str(reopened.result_details)
            await settle()
            assert snapshot(engine)["flows"]==1
            harness.record("native_save_and_file_reopen_after_busy_releases_remain_normal")
            for node_type,name in (("HMBSeedanceGeneration","Generator after reopen"),
                                  ("HMBFinishLookLibrary","Finish after reopen"),
                                  ("HMBColorLUTLibrary","LUT after reopen")):
                created=harness.send(engine,CreateNodeRequest(node_type=node_type,specific_library_name=schema.name,
                    node_name=name,create_error_proxy_on_failure=False))
                assert engine.node_manager.get_node_by_name(created.node_name) is not None
            harness.record("public_create_generator_finish_and_lut_after_reopen_has_valid_current_flow",added_nodes=3)
    finally:
        registration.active=False
        manager.remove_pre_dispatch_hook(registration.hook)
        for kind in registration.load_post_types:manager.remove_post_dispatch_hook(kind,registration.load_post_hook)
        for kind in registration.snapshot_post_types:manager.remove_post_dispatch_hook(kind,registration.snapshot_post_hook)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",type=Path,default=ROOT/"reports/generator-create-context-20261020/guard-native-sdk")
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    harness.PRODUCTS=("_hmb_library_bootstrap.py",)
    harness.exercise=exercise
    harness.run_phase("snapshot-guard",out)
    result=json.loads((out/"snapshot-guard-result.json").read_text("utf-8"))
    print(json.dumps({"passed":result["passed"],"cases":len(result["cases"]),"paid_calls":0}))
    assert result["passed"]


if __name__=="__main__":main()
