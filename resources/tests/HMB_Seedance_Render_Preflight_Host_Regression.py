"""Installed SDK: readiness reads a five-Shot graph and changes no render state."""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",str(Path.home()/"Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
from HMB_Seedance_Render_Preflight_Regression import CHANNEL,SHOTS,PROJECT,digest,media_snapshot,subscription
ATTEMPTS=[]
def denied(*args,**kwargs):
    import traceback
    caller=traceback.extract_stack(limit=3)[-2];ATTEMPTS.append((Path(caller.filename).name,caller.name,caller.lineno));raise AssertionError("Inspection must never execute, upload, submit, write or reconcile")

async def exercise(engine):
    import HMBSeedanceGeneration as seedance
    import HMBImageAssetLibrary as images
    import HMBVideoPickerLibrary as pickers
    import HMBPromptLibrary as prompts
    import HMBAgentLibrary as agents
    import HMBFinishLookLibrary as finishes
    import _hmb_shot_routing as routing
    from griptape_nodes.node_library.library_registry import LibraryRegistry,LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    schema=LibrarySchema.model_validate_json((ROOT/"griptape-nodes-library.json").read_text(encoding="utf-8-sig"));library=LibraryRegistry.generate_new_library(schema)
    classes={cls.__name__:cls for cls in [seedance.HMBSeedanceGeneration,images.HMBImageAssetLibrary,pickers.HMBVideoPickerLibrary,prompts.HMBPromptLibrary,agents.HMBAgentLibrary,finishes.HMBFinishLookLibrary]}
    for definition in schema.nodes:
        if definition.class_name in classes:library.register_lazy_node_type(definition.class_name,definition.metadata,lambda cls=classes[definition.class_name]:cls)
    engine.event_manager.initialize_queue();ensured=engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="OfflineReadOnlyPreflight"));assert ensured.succeeded()
    flow=engine.flow_manager.get_flow_by_name(ensured.flow_name)
    def register(node):
        node.metadata.update(library=schema.name,node_type=type(node).__name__);flow.add_node(node);engine.object_manager.add_object_by_name(node.name,node);engine.node_manager._name_to_parent_flow_name[node.name]=flow.name;return node
    with ExitStack() as setup:
        for name in ["schedule_post_registration_reconcile","schedule_post_hydration_reconcile"]:setup.enter_context(mock.patch.object(routing,name,lambda *a,**k:False))
        # This fixture supplies its own cached Picker document; suppress only
        # constructor background probing before the measured read-only call.
        setup.enter_context(mock.patch.object(pickers.HMBVideoPickerLibrary,"_schedule_video_removal_output_sync",lambda *a,**k:None))
        setup.enter_context(mock.patch.object(prompts.HMBPromptLibrary,"_schedule_prompt_sync",lambda *a,**k:None))
        source=register(images.HMBImageAssetLibrary(name="Read-only exact Image"));real_catalog=source._hmb_shot_routing_catalog;real_snapshot=source._hmb_shot_routing_snapshot
        source._hmb_initial_catalog_scan_pending=False;source._hmb_hydration_adopted=True
        snap=media_snapshot(count=0);catalog_doc={"channel_uuid":CHANNEL,"generation":1,"shots":deepcopy(SHOTS)}
        catalog={"schema":"hmb-shot-routing-catalog","version":1,"publisher_instance_uuid":snap["publisher_instance_uuid"],**catalog_doc,"metadata_sha256":digest(catalog_doc)}
        source._hmb_shot_routing_catalog=lambda:deepcopy(catalog);source._hmb_shot_routing_snapshot=lambda *a,**kw:deepcopy(snap)
        source._hmb_project_identity=lambda:deepcopy(PROJECT);source._hmb_shot_channel_subscription=lambda:subscription(kind="image_asset")
        picker=register(pickers.HMBVideoPickerLibrary(name="Read-only exact Picker"));picker._hmb_shot_channel_subscription=lambda:subscription(kind="video_picker")
        picker_snap=media_snapshot("video_picker",count=0);picker._hmb_shot_routing_snapshot=lambda *a,**kw:deepcopy(picker_snap)
        prompt=register(prompts.HMBPromptLibrary(name="Read-only Prompt manager"));agent=register(agents.HMBAgentLibrary(name="Read-only Agent manager"));finish=register(finishes.HMBFinishLookLibrary(name="Read-only Finish manager"))
        gens=[]
        for n,shot in enumerate(SHOTS,1):
            node=register(seedance.HMBSeedanceGeneration(name=f"Opaque Generator {9-n}"));gens.append(node)
            for name,value in [("model_id",seedance.MODEL_NAME_SEEDANCE_2_5),("resolution","480p"),("duration",4),("output_format","mov"),("output_file",f"read_only_{n}.mov"),("shot_channel_uuid",CHANNEL),("shot_uuid",shot["shot_uuid"]),("shot_number",n),("shot_name",shot["name"]),("shot_selector",shot["name"])]:node.set_parameter_value(name,value,initial_setup=True)
        result=routing.reconcile_shot_routing(source,_allow_unready_cleanup=True);assert result["ok"],result
        for node in list(flow.nodes.values()):routing._mark_authoritative(node)
        # Selected cached-media documents are deterministic boundaries. No
        # real file or model-bound media preparation is part of inspection.
        snap=media_snapshot();picker_snap=media_snapshot("video_picker")
        await asyncio.sleep(.2)  # Finish constructor/setup publication before measuring inspection.
        # The native graph is completely prepared before measuring inspection.
        def authored():
            return {node.name:{"inputs":deepcopy({k:v for k,v in dict(node.parameter_values).items() if k!=seedance.SEEDANCE_PREFLIGHT_PARAMETER}),"outputs":deepcopy({k:v for k,v in dict(node.parameter_output_values).items() if k!=seedance.SEEDANCE_PREFLIGHT_PARAMETER}),"children":[item.element_id for item in node.root_ui_element.children]} for node in flow.nodes.values()}
        before=authored();edges_before={node.name:[(item.source_node_name,item.source_parameter_name,item.target_parameter_name) for item in gens[0]._project_incoming_connections(node)] for node in flow.nodes.values()}
        with ExitStack() as guard:
            guard.enter_context(mock.patch.object(routing,"reconcile_shot_routing",denied))
            guard.enter_context(mock.patch.object(seedance.HMBSeedanceGeneration,"_get_parameters",denied))
            guard.enter_context(mock.patch.object(seedance.HMBSeedanceGeneration,"_process_generation",denied))
            guard.enter_context(mock.patch.object(seedance.HMBSeedanceGeneration,"_prepare_media_reference",denied))
            guard.enter_context(mock.patch.object(seedance._HMBAIBrokerBridge,"create_generation",denied,create=True))
            guard.enter_context(mock.patch.object(agents.HMBAgentLibrary,"_hmb_run_agent_shot",denied))
            guard.enter_context(mock.patch.object(prompts.HMBPromptLibrary,"_schedule_prompt_sync",denied))
            report=gens[2]._hmb_render_preflight_report();assert report["ok"],report
            assert authored()==before
            assert [row["name"] for row in report["rows"]]==[shot["name"] for shot in SHOTS]
            assert all(row["media"]=={"images":1,"videos":1,"audio":0} for row in report["rows"]),report
            assert all(row["connections"]["Prompt → Agent"]=="UUID 일치" for row in report["rows"])
            assert all(row["output"] and not any(item["code"]=="output_missing" for item in row["issues"]) for row in report["rows"])
            parameter=gens[2].get_parameter_by_name(seedance.SEEDANCE_PREFLIGHT_PARAMETER)
            assert parameter.serializable is False and parameter.ui_options["hide_handles"] is True
            request={"schema":seedance.SEEDANCE_PREFLIGHT_SCHEMA,"version":1,"action":"inspect","request_id":"a"*32}
            response=engine.handle_request(SetParameterValueRequest(node_name=gens[2].name,parameter_name=parameter.name,value=request,initial_setup=False,broadcast_result=False));assert response.succeeded()
            for _ in range(20):
                await asyncio.sleep(.01)
                published=gens[2].get_parameter_value(parameter.name)
                if published.get("phase")=="complete":break
            assert published["request_id"]=="a"*32 and published["ok"],published
            # Actual SDK request dispatch: a late old inspect/cancel must not
            # retire the newer UI session command, even before either runs.
            for action,nonce,sequence in [("inspect","c",2),("inspect","b",1),("cancel","b",1)]:
                request.update(action=action,request_id=nonce*32,client_session="f"*32,sequence=sequence)
                response=engine.handle_request(SetParameterValueRequest(node_name=gens[2].name,parameter_name=parameter.name,value=deepcopy(request),initial_setup=False,broadcast_result=False));assert response.succeeded()
            for _ in range(20):
                await asyncio.sleep(.01);published=gens[2].get_parameter_value(parameter.name)
                if published.get("phase")=="complete":break
            assert published["request_id"]=="c"*32 and published["ok"],published
            after=authored()
            assert after==before,{name:{section:[key for key in set(after[name][section])|set(old[section]) if after[name][section].get(key)!=old[section].get(key)] if section!="children" else (after[name][section],old[section]) for section in old if after[name][section]!=old[section]} for name,old in before.items() if after[name]!=old}
            assert {node.name:[(item.source_node_name,item.source_parameter_name,item.target_parameter_name) for item in gens[0]._project_incoming_connections(node)] for node in flow.nodes.values()}==edges_before
            # Real ImageAsset cached getters may report "preparing". Neither
            # a cold cache nor its media-free catalog may publish or scan.
            guard.enter_context(mock.patch.object(images,"_build_shot_routing_snapshot",denied))
            guard.enter_context(mock.patch.object(source,"publish_update_to_parameter",denied))
            real_catalog()
            try:real_snapshot(cached_only=True)
            except ValueError:pass
            assert authored()==before
        assert not ATTEMPTS,ATTEMPTS
        print("HMB_SEEDANCE_RENDER_PREFLIGHT_HOST=PASS (actual SDK5 UUID/name rows; Image/Picker/Prompt/Agent/Finish routes; native file destination; nonserialized control; real command before/after; cold cached getter; inputs/outputs/elements/edges unchanged; Agent/upload/submit/network zero)")

def main():
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-preflight-sdk-") as directory:
        base=Path(directory)
        env={name:str(base/leaf) for name,leaf in [("XDG_CONFIG_HOME","config"),("XDG_DATA_HOME","data"),("XDG_CACHE_HOME","cache"),("LOCALAPPDATA","local"),("APPDATA","app"),("GTN_CONFIG_WORKSPACE_DIRECTORY","workspace")]}
        with mock.patch.dict(os.environ,env),mock.patch.object(socket,"create_connection",denied):
            os.chdir(base);logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:asyncio.run(exercise(engine))
            finally:os.chdir(previous)

if __name__=="__main__":main()
