"""Explicit legacy five-Shot rebind after durable recovery; actual private SDK.

No user workflow is loaded. Models, render submission, broker and external
network boundaries are denied. Native authoring, topology and migration APIs
remain real; rebinding is an explicit per-editor UI action.
"""
from __future__ import annotations

import asyncio
import contextvars
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location("_hmb_manual_rebind_fixture",Path(__file__).with_name(
    "HMB_Workflow_Consolidation_Host_Regression.py"))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
OLD_CHANNEL="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OLD_SHOTS=[dict(row,shot_uuid=f"bbbbbbbb-bbbb-4bbb-8bbb-{index:012d}")
    for index,row in enumerate(base.SHOTS,1)]


def reject(callback,label):
    try:callback()
    except (ValueError,RuntimeError):return
    raise AssertionError("Unsafe manual rebind was admitted: "+label)


async def exercise(engine,directory):
    import _hmb_workflow_migration as migration
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    engine.event_manager.initialize_queue()
    library,advanced,images,prompts,agents,generators=base.register_library(engine)
    try:
        flow=engine.flow_manager.get_flow_by_name(base.send(engine,
            EnsureWorkflowAndFlowRequest(flow_name="PrivateManualLegacyFive")).flow_name)
        migration.mark_flow_migration_pending(engine,flow.name)
        def create(kind,name):
            result=base.send(engine,CreateNodeRequest(node_type=kind,specific_library_name="HMB_GP_Production",
                node_name=name,initial_setup=True,create_error_proxy_on_failure=False))
            return engine.node_manager.get_node_by_name(result.node_name)
        source=create("HMBImageAssetLibrary","Current source")
        source._hmb_initial_catalog_scan_pending=False
        state=images._default_state()
        state["shot_routing"].update(channel_uuid=base.CHANNEL,publisher_instance_uuid=base.PUBLISHER,
            generation=10,shots=deepcopy(base.SHOTS),active_shot_uuid=base.SHOTS[0]["shot_uuid"])
        source._publish_state(state)
        source._hmb_project_identity=lambda:{"project_id":"katuri8","project_name":"까투리8"}
        catalog=source._hmb_shot_routing_catalog()
        old_doc=dict(channel_uuid=OLD_CHANNEL,generation=1,shots=[
            {key:row[key] for key in ("shot_uuid","number","name","revision")} for row in OLD_SHOTS])
        old_catalog=dict(schema="hmb-shot-routing-catalog",version=1,publisher_instance_uuid=base.PUBLISHER,
            **old_doc,metadata_sha256=base.digest(old_doc))
        ps=[];ags=[];gens=[]
        for index,(old,current) in enumerate(zip(OLD_SHOTS,base.SHOTS),1):
            prompt=create("HMBPromptLibrary",f"Original Prompt {index}")
            value=prompt._hmb_prompt_merge_snapshot()["state"]
            value.update(multi_shot_enabled=False,shot=dict(old,channel_uuid=OLD_CHANNEL))
            value["text"]["PRESERVED_TEXT"]=f"Original input {index} literal OFF 0 {{{{SOURCE}}}}"
            prompt.set_parameter_value(prompts.WIDGET_PARAMETER_NAME,prompts._json_dumps(value),initial_setup=True)
            ps.append(prompt)
            agent=create("HMBAgentLibrary",f"Original Agent {index}")
            agent.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,agent._hmb_widget_value(
                shot=dict(old,channel_uuid=OLD_CHANNEL),shot_catalog=old_catalog,shot_manager=False),initial_setup=True)
            agent.set_parameter_value("additional_context",f"Original native settings {index}",initial_setup=True)
            agent.parameter_output_values["output"]=f"Original old result {index}"
            ags.append(agent)
            gen=create("HMBSeedanceGeneration",f"Current Generator {index}")
            for key,item in (("shot_channel_uuid",base.CHANNEL),("shot_uuid",current["shot_uuid"]),
                    ("shot_number",index),("shot_name",current["name"]),("resolution","480p"),
                    ("resume_generation_id","job-"+str(index)*32)):
                gen.set_parameter_value(key,item,initial_setup=True)
            gens.append(gen)
            for src,out,dst,inp in ((source,"SHOT_ASSET_OUT",prompt,"SHOT_ASSET_IN"),
                    (prompt,"PROMPT_OUT",agent,"SHOT_PROMPT_IN"),(agent,"output",gen,"prompt"),
                    (source,"SHOT_ASSET_OUT",gen,"SHOT_ASSET_IN")):
                base.send(engine,CreateConnectionRequest(source_node_name=src.name,source_parameter_name=out,
                    target_node_name=dst.name,target_parameter_name=inp,initial_setup=True))
        original={node.name:migration._raw_node_state(node) for node in flow.nodes.values()}
        generator_fields=("model_id","task","resolution","duration","ratio","generate_audio","output_format",
            "resume_generation_id","draft_job_id","execution_expires_after","priority","poll_interval_seconds",
            "generation_timeout_seconds")
        generator_controls={node.name:{key:deepcopy(node.get_parameter_value(key)) for key in generator_fields}
            for node in gens}
        old_edges=migration._edge_records(engine,set(flow.nodes))
        # The durable common-ledger offer must survive a disconnected editor
        # notice. Only the native UI notification fails; source capture,
        # recovery backup and the root offer/validation remain real.
        with mock.patch.object(ags[0],"_hmb_publish_manual_rebind",
                side_effect=ConnectionResetError(10054,"offline disconnected notice")) as failed_notice:
            outcome=await migration.migrate_flow(engine,flow.name,backup_root=directory/"backups")
        assert failed_notice.call_count==1,failed_notice.call_count
        assert not outcome["ok"] and outcome["code"]=="migration_conflict",outcome
        assert len(flow.nodes)==16 and migration._edge_records(engine,set(flow.nodes))==old_edges
        editors=ps+ags
        assert set(outcome["manual_rebind_editors"])=={node.name for node in editors},outcome
        transaction=migration._MANUAL_REBINDS[engine][flow.name]
        assert ags[0].name in transaction["nodes"]
        assert ags[0]._hmb_manual_rebind["required"] is True
        print("MANUAL_REBIND_DISCONNECTED_NOTICE_PASS root10leasespreserved",flush=True)
        backup=Path(outcome["backup_path"])
        assert backup.is_file()
        from griptape_nodes.serialization.values import decode_value
        recovered=decode_value(json.loads(backup.read_text(encoding="utf-8")))
        assert set(recovered["nodes"])==set(original)
        assert recovered["edges"]==old_edges
        assert all(recovered["nodes"][name]["raw"]==raw for name,raw in original.items())
        print("MANUAL_REBIND_RECOVERY_PASS original16nodes20edges5inputs5outputs",flush=True)
        def token(node):return transaction["nodes"][node.name]["digest"]
        # The root common seam validates source identity, backup and live graph;
        # each node's explicit UI handler additionally owns authoring CAS.
        p0=ps[0]
        reject(lambda:migration.validate_manual_rebind(p0,"0"*64,channel_uuid=base.CHANNEL,
            shot_uuid=base.SHOTS[0]["shot_uuid"]),"stale digest")
        reject(lambda:migration.validate_manual_rebind(p0,token(p0),channel_uuid=OLD_CHANNEL,
            shot_uuid=base.SHOTS[0]["shot_uuid"]),"foreign channel")
        reject(lambda:migration.validate_manual_rebind(p0,token(p0),channel_uuid=base.CHANNEL,
            shot_uuid=OLD_SHOTS[0]["shot_uuid"]),"old UUID with current number")
        saved=backup.read_bytes();backup.write_bytes(saved+b"\n")
        reject(lambda:migration.validate_manual_rebind(p0,token(p0),channel_uuid=base.CHANNEL,
            shot_uuid=base.SHOTS[0]["shot_uuid"]),"modified backup")
        backup.write_bytes(saved)
        moved=backup.with_suffix(".held");backup.rename(moved)
        try:reject(lambda:migration.validate_manual_rebind(p0,token(p0),channel_uuid=base.CHANNEL,
            shot_uuid=base.SHOTS[0]["shot_uuid"]),"missing backup")
        finally:moved.rename(backup)
        old_publisher=catalog["publisher_instance_uuid"]
        forged=deepcopy(catalog);forged["publisher_instance_uuid"]="dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        with mock.patch.object(source,"_hmb_shot_routing_catalog",return_value=forged):
            reject(lambda:migration.validate_manual_rebind(p0,token(p0),channel_uuid=base.CHANNEL,
                shot_uuid=base.SHOTS[0]["shot_uuid"]),"replaced publisher")
        assert catalog["publisher_instance_uuid"]==old_publisher
        with mock.patch.object(engine.flow_manager,"check_for_existing_running_flow",return_value=True):
            reject(lambda:migration.validate_manual_rebind(p0,token(p0),channel_uuid=base.CHANNEL,
                shot_uuid=base.SHOTS[0]["shot_uuid"]),"running flow")
        print("MANUAL_REBIND_NEGATIVE_PASS stale foreign oldUUID missing/modifiedbackup publisher running",flush=True)

        # Exercise the common confirmation ledger's race guard without making
        # native setters run on foreign threads. Only this concurrency probe's
        # read-only export boundary is supplied; registration/backup/catalog,
        # context ownership and atomic ledger remain the real implementation.
        contenders=ags[:2]
        entries=[transaction["nodes"][node.name] for node in contenders]
        saved_entries=[dict(entry) for entry in entries]
        fake_export={"active_subscription":dict(enabled=True,channel_uuid=base.CHANNEL,
            shot_uuid=base.SHOTS[0]["shot_uuid"],shot_number=1,shot_name=base.SHOTS[0]["name"])}
        barrier=threading.Barrier(2)
        real_validate=migration.validate_manual_rebind
        outcomes=[]
        def overlapping_validate(*args,**kwargs):
            result=real_validate(*args,**kwargs)
            barrier.wait(timeout=3)
            return result
        def confirm(node):
            try:outcomes.append((True,migration.confirm_manual_rebind(node,token(node))))
            except migration.MigrationConflict as error:outcomes.append((False,str(error)))
        with ExitStack() as race_guard:
            for node in contenders:
                race_guard.enter_context(mock.patch.object(node,"_hmb_export_agent_authoring_state",
                    return_value=deepcopy(fake_export)))
            race_guard.enter_context(mock.patch.object(migration,"validate_manual_rebind",overlapping_validate))
            threads=[threading.Thread(target=contextvars.copy_context().run,args=(confirm,node)) for node in contenders]
            for thread in threads:thread.start()
            for thread in threads:thread.join(5)
            assert not any(thread.is_alive() for thread in threads)
        assert len(outcomes)==2 and sum(ok for ok,_ in outcomes)==1,outcomes
        assert sum(bool(entry.get("confirmed")) for entry in entries)==1
        with migration._LOCK:
            for entry,saved_entry in zip(entries,saved_entries):entry.clear();entry.update(saved_entry)
        print("MANUAL_REBIND_CONCURRENT_CONFIRM_PASS exactlyOneOwner sameTarget atomicLedger",flush=True)

        def prompt_action(node,shot):
            value=deepcopy(node._current_state())
            value["shot"]=dict(shot,channel_uuid=base.CHANNEL)
            value["manual_rebind"]["confirmation"]={"channel_uuid":base.CHANNEL,"shot_uuid":shot["shot_uuid"]}
            value[prompts.UI_EDIT_REVISION_KEY]=int(value.get(prompts.UI_EDIT_REVISION_KEY) or 0)+1
            node.set_parameter_value(prompts.WIDGET_PARAMETER_NAME,prompts._json_dumps(value))
        def agent_action(node,shot,index):
            return node._hmb_apply_manual_rebind(dict(kind="manual_rebind",request_id=f"{index:032x}",
                channel_uuid=base.CHANNEL,shot_uuid=shot["shot_uuid"],expected_source_digest=token(node)))
        # An edit made after the readonly offer must fail before moving it into
        # another UUID. Re-offer the same preserved original after restoring it.
        changed=deepcopy(ps[4]._current_state())
        changed["text"]["PRESERVED_TEXT"]="A newer user edit"
        ps[4]._hmb_manual_rebind_state(changed)
        prompt_action(ps[4],base.SHOTS[4])
        assert not transaction["nodes"][ps[4].name].get("confirmed")
        changed["text"]["PRESERVED_TEXT"]=f"Original input 5 literal OFF 0 {{{{SOURCE}}}}"
        ps[4]._hmb_manual_rebind_state(changed)
        # Native authoring differs while the token stays unchanged.
        ags[4].set_parameter_value("additional_context","A newer Agent edit",initial_setup=True)
        reject(lambda:agent_action(ags[4],base.SHOTS[4],99),"newer Agent authoring")
        assert not transaction["nodes"][ags[4].name].get("confirmed")
        ags[4].set_parameter_value("additional_context","Original native settings 5",initial_setup=True)

        scheduled=[]
        with mock.patch.object(migration,"schedule_loaded_flow_migrations",side_effect=lambda _engine:scheduled.append(True)):
            for index,shot in enumerate(base.SHOTS):
                prompt_action(ps[index],shot)
                assert transaction["nodes"][ps[index].name].get("confirmed"),ps[index].name
                # Two original editors of one kind cannot choose one target;
                # node-specific Prompt CAS must not overwrite the chosen owner.
                if index==0:
                    reject(lambda:migration.validate_manual_rebind(ps[1],token(ps[1]),
                        channel_uuid=base.CHANNEL,shot_uuid=shot["shot_uuid"]),"target collision")
                agent_action(ags[index],shot,index+1)
                assert transaction["nodes"][ags[index].name].get("confirmed"),ags[index].name
                assert len(scheduled)==int(index==4)
            reject(lambda:migration.confirm_manual_rebind(ps[0],token(ps[0])),"duplicate confirm")
        assert migration.flow_migration_pending(engine,flow.name)
        assert len(flow.nodes)==16 and migration._edge_records(engine,set(flow.nodes))==old_edges
        for index,node in enumerate(ps,1):
            assert node._current_state()["text"]["PRESERVED_TEXT"]==f"Original input {index} literal OFF 0 {{{{SOURCE}}}}"
        for index,node in enumerate(ags,1):
            assert node._native_parameter_value("additional_context")==f"Original native settings {index}"
            assert not node.parameter_output_values.get("output"),"Old result was admitted under a new target UUID"
        completed=await migration.migrate_flow(engine,flow.name,backup_root=directory/"retry-backups")
        assert completed["ok"] and completed["code"]=="consolidated",completed
        assert len(flow.nodes)==8
        for node in gens:
            assert {key:node.get_parameter_value(key) for key in generator_fields}==generator_controls[node.name]
        manager=flow.nodes[completed["survivors"]["agent"]]
        prompt=flow.nodes[completed["survivors"]["prompt"]]
        for index,shot in enumerate(base.SHOTS,1):
            key=base.CHANNEL+"/"+shot["shot_uuid"]
            doc=json.loads(prompt._hmb_prompt_merge_snapshot()["materialized_documents"][key])
            assert doc["text"]["PRESERVED_TEXT"]==f"Original input {index} literal OFF 0 {{{{SOURCE}}}}"
            slot=manager._hmb_shot_slots[manager._hmb_slot_key(base.CHANNEL,shot["shot_uuid"])]
            assert slot["values"]["additional_context"]==f"Original native settings {index}"
            assert not slot["outputs"].get("output")
        exported=manager._hmb_export_agent_authoring_state()
        expected_keys={manager._hmb_slot_key(base.CHANNEL,shot["shot_uuid"]) for shot in base.SHOTS}
        assert expected_keys.issubset(exported["slots"]),set(exported["slots"])
        for index,shot in enumerate(base.SHOTS,1):
            slot=exported["slots"][manager._hmb_slot_key(base.CHANNEL,shot["shot_uuid"])]
            assert slot["values"]["additional_context"]==f"Original native settings {index}"
            assert not slot["outputs"].get("output")
        vaults={}
        def collect_vaults(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if str(key).startswith("manual-rebind:"):
                        assert key not in vaults or vaults[key]==item
                        vaults[key]=item
                    collect_vaults(item)
            elif isinstance(value,list):
                for item in value:collect_vaults(item)
        collect_vaults(exported["archives"])
        for index,original_agent in enumerate(ags,1):
            vault=vaults["manual-rebind:"+token(original_agent)]
            assert vault["source_node_name"]==original_agent.name
            assert vault["native_slot"]["values"]["additional_context"]==f"Original native settings {index}"
            assert vault["native_slot"]["outputs"]["output"]==f"Original old result {index}"
            assert vault["backup_path"]==str(backup)
        assert not migration._MANUAL_REBINDS.get(engine,{}).get(flow.name)
        assert manager._hmb_manual_rebind.get("status")=="cleared"
        assert "target_key" not in manager._hmb_manual_rebind
        print("MANUAL_REBIND_RETIREMENT_PASS exported5targetSlots original5SourceVaults ledgerRetired",flush=True)
        assert backup.read_bytes()==saved
        print("MANUAL_REBIND_FINAL_PASS explicit10confirmations oneRetry exact5authoredUUIDs GeneratorTasks480pPreserved",flush=True)
    finally:LibraryRegistry.unregister_library("HMB_GP_Production",event_manager=engine.event_manager)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-manual-rebind-sdk-") as temporary:
        folder=Path(temporary)
        env={key:str(folder/leaf) for key,leaf in (("XDG_CONFIG_HOME","config"),("XDG_DATA_HOME","data"),
            ("XDG_CACHE_HOME","cache"),("LOCALAPPDATA","local"),("APPDATA","app"),
            ("GTN_CONFIG_WORKSPACE_DIRECTORY","workspace"),("HMB_IMAGE_PROJECTS_ROOT","images"))}
        for path in env.values():Path(path).mkdir(parents=True,exist_ok=True)
        with mock.patch.dict(os.environ,env),ExitStack() as guard:
            from griptape_nodes.retained_mode.engine import engine_scope
            import _hmb_shot_routing as routing
            import _hmb_library_bootstrap as bootstrap
            import HMBImageAssetLibrary as images
            import HMBAgentLibrary as agents
            import HMBSeedanceGeneration as generators
            guard.enter_context(mock.patch.object(socket,"create_connection",base.no_network))
            guard.enter_context(mock.patch.object(bootstrap._Registration,"start_web_worker",lambda *a,**k:None))
            for name in ("schedule_post_registration_reconcile","schedule_post_hydration_reconcile"):
                guard.enter_context(mock.patch.object(routing,name,lambda *a,**k:False))
            guard.enter_context(mock.patch.object(images.HMBImageAssetLibrary,"_schedule_catalog_scan",lambda *a,**k:False))
            guard.enter_context(mock.patch.object(agents.HMBAgentLibrary,"process",base.no_execution))
            guard.enter_context(mock.patch.object(generators.HMBSeedanceGeneration,"_process_generation",base.no_execution))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                with asyncio.Runner() as runner:runner.run(exercise(engine,folder))
            assert base.EXECUTED==[] and base.NETWORK==[]
    print("HMB_LEGACY_MANUAL_REBIND_HOST=PASS (private actual SDK, exact ownership, durable backups, authoring CAS and no execution)")

if __name__=="__main__":main()
