"""Actual native Agent recovery controls; synthetic ledger boundary only.

The companion legacy workflow host suite verifies real backup/ledger authority.
Here each of five native editors exercises input/output preservation, CAS,
target collisions, rollback and exact-own-UUID confirmation without a model.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"resources/tests")]
import HMB_Seedance_Execution_Mode_Host_Regression as harness


async def exercise(engine,_phase,out):
    agents=importlib.import_module("HMBAgentLibrary")
    seedance=importlib.import_module("HMBSeedanceGeneration")
    routing=importlib.import_module("_hmb_shot_routing")
    migration=importlib.import_module("_hmb_workflow_migration")
    root_confirm=migration.confirm_manual_rebind
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest,RunWorkflowWithCurrentStateRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
    schema=harness.register(engine,{"HMBAgentLibrary":agents})
    engine.event_manager.initialize_queue()
    harness.send(engine,EnsureWorkflowAndFlowRequest(flow_name="AgentManualRecovery"))
    catalog=harness.catalog(seedance)

    def make(number,tag,*,own=False):
        created=harness.send(engine,CreateNodeRequest(node_type="HMBAgentLibrary",specific_library_name=schema.name,
            node_name=f"Legacy native {tag} {number}",initial_setup=True,create_error_proxy_on_failure=False))
        node=engine.node_manager.get_node_by_name(created.node_name)
        channel="" if tag=="saved-unbound" else harness.CHANNEL if own else "old-channel-"+str(number)
        uuid="" if tag=="saved-unbound" else harness.SHOTS[number-1]["shot_uuid"] if own else "old-shot-"+str(number)
        node._hmb_legacy_saved_widget_value={"shot_manager":False,"shot":{"channel_uuid":channel,"shot_uuid":uuid,"number":number,"name":"Original legacy "+str(number)}}
        node.set_parameter_value("prompt","Original own input "+str(number),initial_setup=True)
        node.set_parameter_value("additional_context",{"literal":"{{KEEP}}","zero":0,"off":False},initial_setup=True)
        node.set_parameter_value("agent_memory",{"runs":[],"explicit_zero":0,"explicit_off":False},initial_setup=True)
        node.set_parameter_value("output","Original final output "+str(number),initial_setup=True)
        node.parameter_output_values["output"]="Original final output "+str(number)
        node._hmb_active_slot_key=node._hmb_slot_key(channel,uuid)
        node._hmb_shot_slots[node._hmb_active_slot_key]=node._hmb_native_slot_snapshot()
        exported=node._hmb_export_agent_authoring_state()
        original=node._hmb_native_slot_snapshot()
        info=dict(required=True,reason="Original backup preserved",backup_path="isolated-backup.json",
            source_node_name=node.name,publisher_node_name="Synthetic publisher",expected_source_digest=exported["digest"])
        assert node._hmb_prepare_manual_rebind(catalog,info)
        return node,original,info

    def action(number,info,request=1):
        return dict(kind="manual_rebind",request_id=f"{request:032x}",channel_uuid=harness.CHANNEL,
            shot_uuid=harness.SHOTS[number-1]["shot_uuid"],expected_source_digest=info["expected_source_digest"])

    def assert_authored(node,original):
        now=node._hmb_native_slot_snapshot()
        assert now["values"]==original["values"] and now["children"]==original["children"], {
            key:(original["values"].get(key),now["values"].get(key)) for key in original["values"]
            if original["values"].get(key)!=now["values"].get(key)}

    with ExitStack() as guards:
        for name in ("schedule_post_registration_reconcile","schedule_post_hydration_reconcile"):
            guards.enter_context(mock.patch.object(routing,name,lambda *a,**k:False))
        guards.enter_context(mock.patch.object(agents.HMBAgentLibrary,"_run_native_agent_once",harness.deny))
        guards.enter_context(mock.patch.object(migration,"validate_manual_rebind",lambda *a,**k:dict(ok=True)))
        guards.enter_context(mock.patch.object(migration,"confirm_manual_rebind",lambda *a,**k:dict(ok=True)))
        for number in range(1,6):
            node,original,info=make(number,"success")
            assert_authored(node,original)
            assert node.parameter_output_values["output"]==original["outputs"]["output"]
            try:node._hmb_assert_rebind_execution_ready()
            except RuntimeError as exc:assert "REBIND REQUIRED" in str(exc)
            else:raise AssertionError("pending recovery executed")
            assert node.parameter_output_values["output"]==original["outputs"]["output"]
            assert node._hmb_apply_manual_rebind(action(number,info))["ok"]
            key=node._hmb_slot_key(harness.CHANNEL,harness.SHOTS[number-1]["shot_uuid"])
            assert_authored(node,original)
            assert node._hmb_shot_slots[key]["values"]==original["values"]
            assert node._hmb_shot_slots[key]["outputs"]["output"]==""
            assert node.parameter_output_values["output"]=="" and not node._hmb_execution_result
            assert not node._hmb_shot_results and not node._hmb_shot_request_records
            exported=node._hmb_export_agent_authoring_state()
            assert set(exported["slots"])=={key} and exported["active_subscription"]["shot_uuid"]==harness.SHOTS[number-1]["shot_uuid"]
            archive=node._hmb_agent_migration_archives["manual-rebind:"+info["expected_source_digest"]]
            assert archive["native_slot"]["outputs"]==original["outputs"]
            assert archive["original_slots"]
            node._hmb_clear_manual_rebind("migration completed")
            assert node.get_parameter_value(agents._AGENT_WIDGET_PARAMETER)["manual_rebind"]["required"] is False
            harness.record(f"native_legacy_inputs_and_outputs_preserved_until_explicit_choice_shot_{number}")

            node,original,info=make(number,"edited")
            node.set_parameter_value("additional_context","User edited after backup")
            try:node._hmb_apply_manual_rebind(action(number,info))
            except RuntimeError:pass
            else:raise AssertionError("changed source bypassed CAS")
            assert node.get_parameter_value("additional_context")=="User edited after backup"
            assert node.parameter_output_values["output"]==original["outputs"]["output"]
            harness.record(f"native_authoring_edit_rejected_without_overwrite_shot_{number}")

            node,original,info=make(number,"occupied")
            key=node._hmb_slot_key(harness.CHANNEL,harness.SHOTS[number-1]["shot_uuid"])
            occupied={"values":{"prompt":"Existing target data"},"children":{},"outputs":{"output":"Keep"},"result":{}}
            node._hmb_shot_slots[key]=deepcopy(occupied)
            try:node._hmb_apply_manual_rebind(action(number,info))
            except RuntimeError:pass
            else:raise AssertionError("occupied target overwritten")
            assert node._hmb_shot_slots[key]==occupied
            assert_authored(node,original)
            harness.record(f"different_authored_target_rejected_shot_{number}")

            node,original,info=make(number,"rollback")
            oldslots=deepcopy(node._hmb_shot_slots);oldactive=node._hmb_active_slot_key
            with mock.patch.object(migration,"confirm_manual_rebind",return_value=dict(ok=False)):
                try:node._hmb_apply_manual_rebind(action(number,info))
                except RuntimeError:pass
                else:raise AssertionError("failed confirmation changed native state")
            assert node._hmb_active_slot_key==oldactive and node._hmb_shot_slots==oldslots
            assert_authored(node,original)
            assert node.parameter_output_values["output"]==original["outputs"]["output"]
            harness.record(f"failed_confirmation_rolls_back_original_native_inputs_outputs_shot_{number}")

            node,original,info=make(number,"own-uuid",own=True)
            assert node._hmb_apply_manual_rebind(action(number,info))["ok"]
            assert_authored(node,original)
            assert node._hmb_shot_channel_subscription()["shot_uuid"]==harness.SHOTS[number-1]["shot_uuid"]
            assert node.parameter_output_values["output"]==""
            harness.record(f"exact_original_uuid_confirmation_preserves_own_authored_values_shot_{number}")

            with mock.patch.object(agents.HMBAgentLibrary,"_hmb_publish_manual_rebind",
                    side_effect=ConnectionResetError(10054,"Synthetic notice disconnect")):
                node,original,info=make(number,"notice-disconnected")
            assert node._hmb_manual_rebind["required"] is True
            durable=node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER]
            assert durable["manual_rebind"]["expected_source_digest"]==info["expected_source_digest"]
            assert durable["manual_rebind"]["source_slot"]==original
            assert_authored(node,original)
            assert node.parameter_output_values["output"]==original["outputs"]["output"]
            assert node._hmb_apply_manual_rebind(action(number,info))["ok"]
            harness.record(f"prepare_notice_10054_preserves_durable_recovery_authority_shot_{number}")

            node,original,info=make(number,"confirmed-disconnected")
            committed=[]
            native_base=agents.HMBAgentLibrary.__mro__[1]
            native_set=native_base.set_parameter_value
            def confirm_after_local_state(staged,token):
                assert token==info["expected_source_digest"]
                durable=staged.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER]
                assert durable["manual_rebind"]["status"]=="confirmed"
                assert staged.parameter_output_values["output"]==""
                assert staged.parameter_values[agents._AGENT_EXECUTION_RESULT_PARAMETER]=={}
                committed.append(token)
                return dict(ok=True)
            def transport_disconnect(self,*args,**kwargs):
                if committed:raise ConnectionResetError(10054,"Synthetic post-confirm disconnect")
                return native_set(self,*args,**kwargs)
            with mock.patch.object(migration,"confirm_manual_rebind",confirm_after_local_state),\
                    mock.patch.object(native_base,"set_parameter_value",transport_disconnect),\
                    mock.patch.object(node,"_hmb_layout_shot_editor",side_effect=ConnectionResetError(10054,"Synthetic layout disconnect")):
                assert node._hmb_apply_manual_rebind(action(number,info))["ok"]
            assert committed==[info["expected_source_digest"]]
            assert node._hmb_manual_rebind["status"]=="confirmed" and node._hmb_manual_rebind["required"] is False
            assert node._hmb_shot_channel_subscription()["shot_uuid"]==harness.SHOTS[number-1]["shot_uuid"]
            assert node.parameter_output_values["output"]==""
            assert node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER]["manual_rebind"]["status"]=="confirmed"
            assert_authored(node,original)
            harness.record(f"post_confirm_10054_never_rolls_back_recorded_target_shot_{number}")

            node,original,info=make(number,"closed-loop-confirm")
            class ClosingLoop:
                def is_closed(self):return False
                def is_running(self):return True
                def call_soon_threadsafe(self,*args,**kwargs):
                    raise RuntimeError("Event loop is closed")
            class OfflineEngine:pass
            offline_engine=OfflineEngine()
            offline_engine.event_manager=type("Events",(),{"event_loop":ClosingLoop()})()
            offline_flow=type("Flow",(),{"name":"synthetic-closed-loop-"+str(number)})()
            entry=dict(kind="agent",confirmed=False)
            transaction=dict(nodes={node.name:entry},backup_path="synthetic-preserved-backup")
            with mock.patch.object(migration,"_manual_rebind_context",return_value=(offline_engine,offline_flow,transaction,entry)),\
                    mock.patch.object(migration,"confirm_manual_rebind",root_confirm):
                outcome=node._hmb_apply_manual_rebind(action(number,info))
            assert outcome["ok"] is True and outcome["migration_retry_scheduled"] is False
            assert entry["confirmed"] is True
            assert entry["target"]==(harness.CHANNEL,harness.SHOTS[number-1]["shot_uuid"])
            assert not migration.flow_migration_pending(offline_engine,offline_flow.name)
            assert node._hmb_manual_rebind["status"]=="confirmed"
            assert node.parameter_output_values["output"]==""
            assert_authored(node,original)
            assert node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER]["manual_rebind"]["status"]=="confirmed"
            harness.record(f"real_root_scheduler_loop_close_after_confirm_keeps_native_and_ledger_consistent_shot_{number}")

        pending=[]
        for number in range(1,6):
            node,original,info=make(number,"saved-unbound")
            assert node._hmb_export_agent_authoring_state()["active_subscription"]["enabled"] is False
            pending.append((node.name,deepcopy(original)))
        serialized=harness.send(engine,SerializeFlowToCommandsRequest(flow_name="AgentManualRecovery")).serialized_flow_commands
        saved=out/"synthetic-pending-rebind.py"
        await harness.asend(engine,SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
            file_name=saved.stem,file_path=str(saved),display_name="Offline pending recovery"))
        await harness.asend(engine,ClearAllObjectStateRequest(i_know_what_im_doing=True))
        traces=[]
        native_refresh=agents.HMBAgentLibrary._refresh_routed_prompt_preview
        native_set=agents.HMBAgentLibrary.set_parameter_value
        def trace_refresh(self):
            trace={"node":self.name,"kind":"refresh","manual":bool(getattr(self,"_hmb_manual_rebind",{}).get("required")),
                "pending":bool(getattr(self,"_hmb_manual_rebind_hydration_pending",False)),"prompt_before":bool(self.parameter_values.get("prompt"))}
            result=native_refresh(self)
            trace["prompt_after"]=bool(self.parameter_values.get("prompt"))
            if "saved-unbound" in self.name:traces.append(trace)
            return result
        def trace_set(self,name,value,*args,**kwargs):
            result=native_set(self,name,value,*args,**kwargs)
            if "saved-unbound" in self.name and str(name) in {"prompt",agents._AGENT_WIDGET_PARAMETER,agents._AGENT_SHOT_STORE_PARAMETER}:
                traces.append(dict(node=self.name,kind="set",name=str(name),initial=bool(kwargs.get("initial_setup")),
                    raw_type=type(value).__name__,raw_manual=bool(isinstance(value,dict) and value.get("manual_rebind",{}).get("required")),
                    manual=bool(getattr(self,"_hmb_manual_rebind",{}).get("required")),pending=bool(getattr(self,"_hmb_manual_rebind_hydration_pending",False)),
                    prompt_after=bool(self.parameter_values.get("prompt"))))
            return result
        with mock.patch.object(agents.HMBAgentLibrary,"_refresh_routed_prompt_preview",trace_refresh),mock.patch.object(agents.HMBAgentLibrary,"set_parameter_value",trace_set):
            await harness.asend(engine,RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
        (out/"reopen-traces.json").write_text(json.dumps(traces,indent=2),encoding="utf-8")
        for name,original in pending:
            node=engine.node_manager.get_node_by_name(name)
            assert node._hmb_manual_rebind["required"] is True
            document=node._hmb_export_agent_authoring_state()
            assert document["active_subscription"]["enabled"] is False
            assert document["active_slot_key"]=="__hmb_only__"
            assert_authored(node,original)
            assert node.parameter_output_values["output"]==original["outputs"]["output"]
            harness.record("actual_saved_pending_unbound_editor_reopen_never_auto_binds_"+name.rsplit(" ",1)[1])


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",type=Path,default=ROOT/"reports/critical-agent-isolation-20261020/manual-api")
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    harness.PRODUCTS=("HMBAgentLibrary.py","widgets/HMBAgentLibraryWidget.js","_hmb_workflow_migration.py")
    harness.exercise=exercise;harness.run_phase("manual",args.out.resolve())
    report=json.loads((args.out/"manual-result.json").read_text("utf-8"))
    print(json.dumps(dict(passed=report["passed"],cases=len(report["cases"]),paid_calls=0)))
    assert report["passed"]


if __name__=="__main__":main()
