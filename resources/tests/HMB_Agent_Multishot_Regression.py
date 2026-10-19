"""Offline per-Shot native Agent manager contracts; no engine/provider work."""
from __future__ import annotations
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("hmb_agent_multishot_target", ROOT / "HMBAgentLibrary.py")
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
Agent = module.HMBAgentLibrary

_original_connect = socket.socket.connect
def forbidden(*args, **kwargs):
    raise AssertionError("External I/O is forbidden")
def offline_connect(sock, address, *args, **kwargs):
    if isinstance(address, tuple) and str(address[0]).lower() in {"127.0.0.1","::1","localhost"}:
        return _original_connect(sock, address, *args, **kwargs)
    return forbidden()

def subscription(number):
    return {"schema":"hmb-shot-channel-subscription","version":1,"participant_kind":"agent","enabled":True,
            "channel_uuid":"channel", "shot_uuid":f"shot-{number}","shot_number":number,"shot_name":f"Renamed {number}"}

def manager():
    node = object.__new__(Agent)
    node.name = "Offline Agent manager"; node.metadata = {"library":"HMB_GP_Production","node_type":"HMBAgentLibrary"}
    node._hmb_node_deleted = False; node._hmb_lifecycle_generation = 1
    node._hmb_shot_manager_mode = True; node._hmb_active_slot_key = "__hmb_only__"
    node._hmb_shot_slots = {f"channel\x1fshot-{number}":{"values":{"model":f"model-{number}", "model_provider":f"provider-{number}","agent":None,"tools":[],"rulesets":[]}, "outputs":{},"result":{}} for number in range(1,6)}
    node._hmb_shot_results = {}; node._hmb_shot_execution_locks = {}; node._hmb_shot_result_lock = threading.RLock()
    node._hmb_shot_run_status = {}; node._hmb_shot_workers = {}; node._hmb_shot_local_tasks = set(); node._hmb_shot_action_ids = set()
    node._hmb_shot_catalog_snapshot = {"channel_uuid":"channel", "shots":[{"shot_uuid":f"shot-{n}","number":n,"name":f"Renamed {n}","revision":0} for n in range(1,6)]}
    node.parameter_values = {"prompt":"Only authored text","model":"Only model","agent":None}; node.parameter_output_values = {}
    node._hmb_persist_shot_store = Mock(); node._hmb_publish_shot_status = Mock(); node._refresh_agent_shot_route = Mock()
    node._hmb_capture_active_slot = Mock()
    prompt = SimpleNamespace(_hmb_node_deleted=False, _hmb_prompt_shot_document=lambda **kw: {"identity":kw})
    node._hmb_manager_prompt_owner = lambda **kw: prompt
    return node, prompt

class MultishotTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(socket,"create_connection",forbidden),patch.object(socket.socket,"connect",offline_connect),patch.object(urllib.request,"urlopen",forbidden)]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()

    def test_new_defaults_unified_manager_with_no_independent_mode(self):
        text = (ROOT/"HMBAgentLibrary.py").read_text(encoding="utf-8")
        constructor = text[text.index("    def __init__(self, **kwargs):",text.index("class HMBAgentLibrary")):text.index("    def _prepare_hmb_node_surface")]
        self.assertIn("self._hmb_initial_shot_autoclaim_pending = False",constructor)
        self.assertNotIn("only_mode",module._agent_widget_value())
        self.assertTrue(module._agent_widget_value()["shot_manager"])
        self.assertIn("self._hmb_shot_manager_mode = True",constructor)

    def test_native_accordion_reorders_same_objects_and_unchanged_echoes_do_no_ui_work(self):
        node,_=manager();parameters={};node.get_parameter_by_name=lambda name:parameters.get(name);node._hmb_shot_editor_expanded=True
        node._hmb_native_editor_collapsed=False;node._hmb_native_editor_visibility={}
        changes=[]
        def parameter(name,hidden=False):
            item=SimpleNamespace(name=name,ui_options={"hide":hidden},hide_property=hidden)
            def update(key,value):changes.append((name,key,value));item.ui_options[key]=value
            item.update_ui_options_key=update;parameters[name]=item;return item
        port=parameter("FLOW_IN");header=parameter(module._AGENT_WIDGET_PARAMETER)
        body=[parameter(name,name=="output_schema") for name in ("model_provider","model","prompt","output_schema")]
        rows=[parameter(module._AGENT_SHOT_ROW_PREFIX+str(number),True) for number in range(1,6)]
        node.root_ui_element=SimpleNamespace(children=[port,header,*body,*rows]);node._hmb_native_editor_elements=body
        node.parameter_values[module._AGENT_WIDGET_PARAMETER]={"shot":{"channel_uuid":"channel","shot_uuid":"shot-3"}}
        node._native_parameter_value=lambda name,default=None:node.parameter_values.get(name,default)
        node.set_parameter_value=Mock(side_effect=lambda name,value:node.parameter_values.update({name:copy.deepcopy(value)}))
        def reorder(names):node.root_ui_element.children[:]=[parameters[name] for name in names]
        node.reorder_elements=Mock(side_effect=reorder)
        node._hmb_layout_shot_editor()
        children=node.root_ui_element.children;self.assertEqual(children[children.index(rows[2])+1:children.index(rows[3])],body)
        self.assertIs(children[0],port);self.assertEqual(len({id(item) for item in children}),len(children))
        node.reorder_elements.reset_mock();node.set_parameter_value.reset_mock();changes.clear()
        for _ in range(100):node._hmb_layout_shot_editor()
        self.assertEqual(changes,[]);node.reorder_elements.assert_not_called();node.set_parameter_value.assert_not_called()
        node._hmb_shot_editor_expanded=False;node._hmb_layout_shot_editor()
        self.assertTrue(all(item.ui_options["hide"] for item in body))
        node._hmb_shot_editor_expanded=True;node._hmb_layout_shot_editor()
        self.assertEqual([item.ui_options["hide"] for item in body],[False,False,False,True])
        self.assertTrue(all(parameters[item.name] is item for item in body))

    def test_editor_collapse_and_identical_ui_echo_do_not_route_or_compile_prompt(self):
        node,_=manager();parameters={};node.get_parameter_by_name=lambda name:parameters.get(name);node._hmb_shot_editor_expanded=True;node._hmb_shot_context={}
        catalog={"schema":"hmb-shot-routing-catalog","version":1,"publisher_instance_uuid":"publisher","channel_uuid":"channel","generation":1,"metadata_sha256":"a"*64,"shots":copy.deepcopy(node._hmb_shot_catalog_snapshot["shots"])}
        node._hmb_shot_catalog_snapshot=catalog;shot={"channel_uuid":"channel",**catalog["shots"][0]}
        value=node._hmb_widget_value(shot,catalog);node.parameter_values[module._AGENT_WIDGET_PARAMETER]=value
        header=module.Parameter(name=module._AGENT_WIDGET_PARAMETER,default_value=value,ui_options={key:64 for key in ("height","min_height","max_height","widget_height","default_height","preferred_height","initial_height")})
        parameters[header.name]=header;node._native_parameter_value=lambda name,default=None:node.parameter_values.get(name,default)
        node._hmb_available_agent_shot_catalog=Mock(side_effect=AssertionError("presentation event performed graph discovery"))
        node._hmb_switch_native_slot=Mock();node._refresh_routed_prompt_preview=Mock();node._hmb_layout_shot_editor=Mock()
        collapsed=copy.deepcopy(value);collapsed["shot_editor_expanded"]=False
        def native_property_set(self,name,value,*args,**kwargs):
            parameter=self.get_parameter_by_name(name);normalized=self.before_value_set(parameter,value)
            self.parameter_values[name]=normalized;self.after_value_set(parameter,normalized)
        with patch.object(module._BaseAgent,"set_parameter_value",native_property_set),patch.object(module._BaseAgent,"after_value_set",lambda *args:None):
            node.set_parameter_value(module._AGENT_WIDGET_PARAMETER,collapsed)
        self.assertFalse(node._hmb_shot_editor_expanded);node._refresh_agent_shot_route.assert_not_called();node._refresh_routed_prompt_preview.assert_not_called()
        node._hmb_layout_shot_editor.assert_called_once();node._hmb_layout_shot_editor.reset_mock()
        node._hmb_persist_shot_store.reset_mock();node._hmb_switch_native_slot.reset_mock()
        with patch.object(module._BaseAgent,"set_parameter_value",native_property_set),patch.object(module._BaseAgent,"after_value_set",lambda *args:None):
            for _ in range(100):node.set_parameter_value(module._AGENT_WIDGET_PARAMETER,copy.deepcopy(collapsed))
        node._hmb_layout_shot_editor.assert_not_called();node._hmb_persist_shot_store.assert_not_called();node._hmb_switch_native_slot.assert_not_called()

    def test_row_replayed_select_nonce_cannot_toggle_twice(self):
        node,_=manager();node._hmb_shot_editor_expanded=True;node._hmb_layout_shot_editor=Mock()
        node._native_parameter_value=lambda name,default=None:{"shot":{"channel_uuid":"channel","shot_uuid":"shot-2"}}
        node.set_parameter_value=Mock();parameter=SimpleNamespace(name=module._AGENT_SHOT_ROW_PREFIX+"2")
        row={"shot":{"channel_uuid":"channel","shot_uuid":"shot-2"},"action":{"kind":"select","request_id":"f"*32}}
        node._hmb_handle_row_action(parameter,row);node._hmb_handle_row_action(parameter,copy.deepcopy(row))
        node.set_parameter_value.assert_called_once();self.assertFalse(node.set_parameter_value.call_args.args[1]["shot_editor_expanded"])
        self.assertEqual(node._hmb_row_action_ack["channel\x1fshot-2"],"f"*32)

    def test_row_explicit_expand_uses_exact_catalog_and_never_ingests_stale_native_values(self):
        node,_=manager();node._hmb_shot_editor_expanded=True;node._hmb_layout_shot_editor=Mock()
        node._native_parameter_value=lambda name,default=None:{"shot":{"channel_uuid":"channel","shot_uuid":"shot-2"}}
        node.set_parameter_value=Mock();parameter=SimpleNamespace(name=module._AGENT_SHOT_ROW_PREFIX+"2")
        row={"shot":{"channel_uuid":"channel","shot_uuid":"shot-2","name":"Stale label"},
            "prompt":"DO NOT INGEST", "model":"DO NOT INGEST", "action":{"kind":"select","request_id":"e"*32,"expanded":True}}
        original=copy.deepcopy(node.parameter_values);node._hmb_handle_row_action(parameter,row)
        applied=node.set_parameter_value.call_args.args[1]
        self.assertTrue(applied["shot_editor_expanded"]);self.assertEqual(applied["shot"]["name"],"Renamed 2")
        self.assertNotIn("prompt",applied);self.assertNotIn("model",applied);self.assertEqual(node.parameter_values,original)

    def test_native_row_failure_publishes_no_false_ack_or_model(self):
        node,_=manager();node._hmb_shot_editor_expanded=True;node._hmb_layout_shot_editor=Mock()
        node._native_parameter_value=lambda name,default=None:{"shot":{"channel_uuid":"channel","shot_uuid":"shot-2"}}
        node.set_parameter_value=Mock(side_effect=RuntimeError("rejected native switch"));parameter=SimpleNamespace(name=module._AGENT_SHOT_ROW_PREFIX+"2")
        row={"shot":{"channel_uuid":"channel","shot_uuid":"shot-2"},"action":{"kind":"select","request_id":"d"*32}}
        with self.assertRaisesRegex(RuntimeError,"rejected native switch"):node._hmb_handle_row_action(parameter,row)
        self.assertFalse(getattr(node,"_hmb_row_action_ack",{}));self.assertFalse(node._hmb_shot_workers)

    def test_row_refresh_is_read_only_even_when_canonical_editor_differs_from_pending_target(self):
        node,_=manager();node._hmb_layout_shot_editor=Mock();node._hmb_shot_editor_expanded=True
        node._native_parameter_value=lambda name,default=None:{"shot":{"channel_uuid":"channel","shot_uuid":"shot-1"}}
        node.set_parameter_value=Mock();original=copy.deepcopy(node.parameter_values)
        row={"shot":{"channel_uuid":"channel","shot_uuid":"shot-2"},"action":{"kind":"refresh","request_id":"c"*32}}
        node._hmb_handle_row_action(SimpleNamespace(name=module._AGENT_SHOT_ROW_PREFIX+"2"),row)
        node.set_parameter_value.assert_not_called();self.assertEqual(node.parameter_values,original)
        self.assertEqual(node._hmb_row_action_ack["channel\x1fshot-2"],"c"*32)
        node._hmb_layout_shot_editor.assert_called_once();self.assertFalse(node._hmb_shot_workers)

    def test_legacy_blank_export_does_not_claim_presentation_default_slots(self):
        node,_=manager();native={"values":{"prompt":"Original unbound input"},"children":{},"outputs":{"output":"Original result"},"result":{}}
        node._hmb_native_slot_snapshot=lambda:copy.deepcopy(native);node._hmb_shot_channel_subscription=lambda:subscription(4)
        node._hmb_legacy_saved_widget_value={"schema":"hmb-agent-ui","shot":{"channel_uuid":"","shot_uuid":"","number":1,"name":"Only"}}
        node.get_parameter_by_name=lambda name:None
        exported=node._hmb_export_agent_authoring_state()
        self.assertFalse(exported["active_subscription"]["enabled"]);self.assertEqual(exported["active_subscription"]["shot_uuid"],"")
        self.assertEqual(exported["slots"],{"__hmb_only__":native});self.assertEqual(exported["legacy_widget"],node._hmb_legacy_saved_widget_value)
        node._hmb_loaded_durable_shot_store=True;durable=node._hmb_export_agent_authoring_state()
        self.assertEqual(len(durable["slots"]),6);self.assertEqual(durable["slots"]["channel\x1fshot-4"]["values"]["model"],"model-4")

    def test_raw_saved_hook_preserves_blank_identity_before_sdk_normalizes_ui(self):
        node,_=manager();before=copy.deepcopy((node.parameter_values,node.parameter_output_values,node._hmb_shot_slots))
        raw={"schema":"hmb-agent-ui","shot":{"channel_uuid":"","shot_uuid":"","number":1,"name":"Only"}}
        node._hmb_capture_saved_parameter_value(module._AGENT_WIDGET_PARAMETER,raw)
        node._hmb_capture_saved_parameter_value(module._AGENT_WIDGET_PARAMETER,{"shot_manager":True,"shot":{"channel_uuid":"channel","shot_uuid":"shot-4"}})
        self.assertEqual(node._hmb_legacy_saved_widget_value,raw)
        raw["shot"]["name"]="Caller changed"
        self.assertEqual(node._hmb_legacy_saved_widget_value["shot"]["name"],"Only")
        node._hmb_capture_saved_parameter_value(module._AGENT_SHOT_STORE_PARAMETER,{"schema":module._AGENT_SHOT_STORE_SCHEMA,"version":1,"slots":{}})
        self.assertTrue(node._hmb_loaded_durable_shot_store)
        self.assertEqual((node.parameter_values,node.parameter_output_values,node._hmb_shot_slots),before)
        node._hmb_persist_shot_store.assert_not_called();node._refresh_agent_shot_route.assert_not_called()

    def test_rollback_restores_original_private_cache_without_native_or_ui_writes(self):
        node,_=manager();node._hmb_native_slot_snapshot=lambda:{"values":{"prompt":"authored"},"children":{},"outputs":{},"result":{}}
        node._hmb_shot_channel_subscription=lambda:subscription(3);node.get_parameter_by_name=lambda _name:None
        node._hmb_agent_migration_archives={"original":{"value":"preserve"}}
        node._hmb_legacy_saved_widget_value={"shot":{"channel_uuid":"","shot_uuid":"","name":"Only"}}
        node._hmb_loaded_durable_shot_store=False
        exported=node._hmb_export_agent_authoring_state();native_before=copy.deepcopy((node.parameter_values,node.parameter_output_values))
        original=copy.deepcopy(exported["private_cache"])
        node._hmb_shot_slots={};node._hmb_shot_results={};node._hmb_agent_migration_archives={};node._hmb_active_slot_key="wrong"
        node._hmb_legacy_saved_widget_value=None;node._hmb_loaded_durable_shot_store=True
        self.assertTrue(node._hmb_restore_agent_authoring_state(exported))
        self.assertEqual(node._hmb_shot_slots,original["slots"]);self.assertEqual(node._hmb_agent_migration_archives,original["archives"])
        self.assertEqual(node._hmb_active_slot_key,original["active_slot_key"])
        self.assertEqual(node._hmb_legacy_saved_widget_value,original["legacy_widget"]);self.assertFalse(node._hmb_loaded_durable_shot_store)
        self.assertEqual((node.parameter_values,node.parameter_output_values),native_before)
        node._hmb_persist_shot_store.assert_not_called();node._refresh_agent_shot_route.assert_not_called()
        corrupt=copy.deepcopy(exported);corrupt["private_cache"]["active_slot_key"]="forged"
        with self.assertRaises(RuntimeError):node._hmb_restore_agent_authoring_state(corrupt)
        self.assertEqual(node._hmb_active_slot_key,original["active_slot_key"])

    def test_manager_aprocess_never_runs_all_models(self):
        node,_ = manager(); node._hmb_aprocess_locked = Mock(side_effect=AssertionError("Manager launched native inference"))
        asyncio.run(node.aprocess())
        node._hmb_capture_active_slot.assert_called_once(); node._hmb_aprocess_locked.assert_not_called()

    def test_all_five_subscriptions_use_authoritative_names(self):
        node,_ = manager()
        self.assertEqual([row["shot_name"] for row in node._hmb_agent_shot_subscriptions()],[f"Renamed {n}" for n in range(1,6)])
        node._hmb_shot_manager_mode=False
        node._hmb_shot_channel_subscription=lambda:{"enabled":False}
        self.assertEqual(node._hmb_agent_shot_subscriptions(),[])

    def test_five_calls_each_run_one_frozen_model_and_result(self):
        node,prompt = manager(); calls=[]; facades=[]
        def factory(owner, prompt_owner, document, shot, slot, generator):
            self.assertIs(owner,node); self.assertIs(prompt_owner,prompt)
            number=shot["shot_number"]; text=f"Instruction {number}"
            result={"status":"succeeded","run_id":f"run-{number}","output_sha256":hashlib.sha256(text.encode()).hexdigest()}
            view=SimpleNamespace(parameter_values={},parameter_output_values={"output":text,"agent":{}},_hmb_shot_policy_identity={},
                                 _hmb_agent_reference_observation_snapshot=lambda:{"shot":number},_hmb_execution_result_snapshot=lambda:copy.deepcopy(result),
                                 _clear_hmb_runtime_policy=Mock())
            async def run():
                calls.append((number,slot["values"]["model"],slot["values"]["model_provider"]))
                await asyncio.sleep(0.01*(6-number))
            view._hmb_aprocess_locked=run;facades.append(view);return view
        async def run():
            with patch.object(module._HMBAgentShotExecution,"_from_owner",side_effect=factory):
                records=await asyncio.gather(*(node._hmb_run_agent_shot(channel_uuid="channel",shot_uuid=f"shot-{n}",prompt_owner=prompt) for n in range(1,6)))
            self.assertEqual(len(calls),5)
            self.assertEqual([record["text"] for record in records],[f"Instruction {n}" for n in range(1,6)])
        asyncio.run(run())
        self.assertEqual(sorted(calls),[(n,f"model-{n}",f"provider-{n}") for n in range(1,6)])
        self.assertEqual(node.parameter_values["prompt"],"Only authored text")
        result=node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-2")
        result["result"]["run_id"]="forged"
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-2")["result"]["run_id"],"run-2")
        self.assertTrue(all(view.parameter_values=={} and view.parameter_output_values=={} for view in facades))

    def test_same_shot_two_generators_keep_independent_request_tickets(self):
        node,prompt=manager();one=SimpleNamespace(is_cancellation_requested=False);two=SimpleNamespace(is_cancellation_requested=False)
        counter=[]
        def factory(owner,prompt_owner,document,shot,slot,generator):
            number=len(counter)+1;counter.append(number);text=f"Distinct request {number}"
            result={"status":"succeeded","run_id":f"request-{number}","output_sha256":hashlib.sha256(text.encode()).hexdigest()}
            view=SimpleNamespace(parameter_values={},parameter_output_values={"output":text,"agent":{}},_hmb_shot_policy_identity={},
                _hmb_agent_reference_observation_snapshot=lambda:{},_hmb_execution_result_snapshot=lambda:copy.deepcopy(result),_clear_hmb_runtime_policy=Mock())
            async def run():await asyncio.sleep(0)
            view._hmb_aprocess_locked=run;return view
        async def run():
            with patch.object(module._HMBAgentShotExecution,"_from_owner",side_effect=factory):
                return await asyncio.gather(node._hmb_run_agent_shot(channel_uuid="channel",shot_uuid="shot-1",prompt_owner=prompt,generator=one),node._hmb_run_agent_shot(channel_uuid="channel",shot_uuid="shot-1",prompt_owner=prompt,generator=two))
        first,second=asyncio.run(run())
        self.assertEqual(len(counter),2)
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=first["result"]["run_id"],generator=one),first)
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=second["result"]["run_id"],generator=two),second)
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1")["text"],second["text"])
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=first["result"]["run_id"],generator=two),{})
        self.assertFalse(node._hmb_release_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=first["result"]["run_id"],generator=two))
        self.assertTrue(node._hmb_release_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=first["result"]["run_id"],generator=one))
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=first["result"]["run_id"],generator=one),{})
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1",run_id=second["result"]["run_id"],generator=two),second)

    def test_completed_run_preserves_settings_edited_for_future_renders(self):
        node,prompt=manager();key="channel\x1fshot-1";seen=[]
        text="Frozen input output";result={"status":"succeeded","run_id":"edited-future","output_sha256":hashlib.sha256(text.encode()).hexdigest()}
        def factory(owner,prompt_owner,document,shot,slot,generator):
            async def run():
                seen.append(slot["values"]["model"])
                owner._hmb_shot_slots[key]["values"]["model"]="User next model"
                await asyncio.sleep(0)
            return SimpleNamespace(parameter_values={},parameter_output_values={"output":text,"agent":{}},_hmb_shot_policy_identity={},
                _hmb_agent_reference_observation_snapshot=lambda:{},_hmb_execution_result_snapshot=lambda:copy.deepcopy(result),_clear_hmb_runtime_policy=Mock(),_hmb_aprocess_locked=run)
        with patch.object(module._HMBAgentShotExecution,"_from_owner",side_effect=factory):
            record=asyncio.run(node._hmb_run_agent_shot(channel_uuid="channel",shot_uuid="shot-1",prompt_owner=prompt))
        self.assertEqual(seen,["model-1"])
        self.assertEqual(record["text"],text)
        self.assertEqual(node._hmb_shot_slots[key]["values"]["model"],"User next model")
        self.assertEqual(node._hmb_shot_slots[key]["values"]["agent"],None)

    def test_foreign_prompt_rejected_before_worker(self):
        node,_=manager()
        with patch.object(module._HMBAgentShotExecution,"_from_owner",side_effect=AssertionError("foreign prompt started")):
            with self.assertRaises(RuntimeError):asyncio.run(node._hmb_run_agent_shot(channel_uuid="channel",shot_uuid="shot-1",prompt_owner=object()))

    def test_failed_shot_clears_only_its_old_admission(self):
        node,prompt=manager();node._hmb_shot_results={"channel\x1fshot-1":{"text":"old"},"channel\x1fshot-2":{"text":"keep"}}
        async def failure():raise RuntimeError("offline model failure")
        view=SimpleNamespace(parameter_values={},parameter_output_values={},_hmb_aprocess_locked=failure,_clear_hmb_runtime_policy=Mock())
        with patch.object(module._HMBAgentShotExecution,"_from_owner",return_value=view):
            with self.assertRaises(RuntimeError):asyncio.run(node._hmb_run_agent_shot(channel_uuid="channel",shot_uuid="shot-1",prompt_owner=prompt))
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-1"),{})
        self.assertEqual(node._hmb_agent_shot_result(channel_uuid="channel",shot_uuid="shot-2"),{"text":"keep"})
        self.assertFalse(node._hmb_shot_execution_locks["channel\x1fshot-1"].locked())

    def test_shot_cancellation_ignores_only_run_but_honors_target_or_owner_delete(self):
        view=object.__new__(module._HMBAgentShotExecution)
        view._hmb_shot_cancelled=False
        view._hmb_shot_owner=SimpleNamespace(_hmb_node_deleted=False,is_cancellation_requested=True)
        view._hmb_shot_generator=SimpleNamespace(_hmb_node_deleted=False,is_cancellation_requested=False)
        self.assertFalse(view.is_cancellation_requested)
        view._hmb_shot_generator.is_cancellation_requested=True
        self.assertTrue(view.is_cancellation_requested)
        view._hmb_shot_generator.is_cancellation_requested=False
        view._hmb_shot_owner._hmb_node_deleted=True
        self.assertTrue(view.is_cancellation_requested)

    def test_legacy_independent_store_becomes_manager_without_discarding_data(self):
        node,_=manager();node._hmb_shot_manager_mode=False
        node._hmb_shot_channel_subscription=lambda:{"enabled":False}
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="channel",shot_uuid="shot-3"))
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="other",shot_uuid="shot-3"))
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="channel",shot_uuid="missing"))
        stored={"schema":module._AGENT_SHOT_STORE_SCHEMA,"version":1,"manager":False,"active":"__hmb_only__","slots":copy.deepcopy(node._hmb_shot_slots),"results":{}}
        node._hmb_shot_slots={};node._native_parameter_value=lambda name,default=None:stored
        node._hmb_restore_shot_store()
        self.assertTrue(node._hmb_shot_manager_enabled())
        self.assertEqual(node._hmb_shot_slots,stored["slots"])
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="channel",shot_uuid="shot-3"))
        node._hmb_shot_slots={"__hmb_only__":{}}
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="channel",shot_uuid="shot-3"))
        node._hmb_shot_slots=copy.deepcopy(stored["slots"])
        node._hmb_shot_channel_subscription=lambda:subscription(3)
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="channel",shot_uuid="shot-3"))
        node._hmb_shot_manager_mode=True
        self.assertFalse(node._hmb_shot_manager_paused_for(channel_uuid="channel",shot_uuid="shot-3"))

    def test_target_busy_is_independent_from_other_shots(self):
        node,_=manager();lock=threading.Lock();lock.acquire();node._hmb_shot_execution_locks["channel\x1fshot-2"]=lock
        one=SimpleNamespace(_hmb_shot_channel_subscription=lambda:subscription(1))
        two=SimpleNamespace(_hmb_shot_channel_subscription=lambda:subscription(2))
        self.assertFalse(node._hmb_web_rerender_busy(generator=one));self.assertTrue(node._hmb_web_rerender_busy(generator=two))
        lock.release()

    def test_store_restores_more_than_thirty_archived_shot_slots(self):
        node,_=manager()
        slots={f"old-channel-{n}\x1fold-shot-{n}":{"values":{"prompt":f"Keep {n}"}} for n in range(32)}
        slots["__hmb_only__"]={"values":{"prompt":"Keep Only"}}
        raw={"schema":module._AGENT_SHOT_STORE_SCHEMA,"version":1,"manager":True,"active":"old-channel-31\x1fold-shot-31","slots":slots,"results":{}}
        node._native_parameter_value=lambda name,default=None:raw
        node._hmb_restore_shot_store()
        self.assertEqual(node._hmb_shot_slots,slots)
        self.assertEqual(node._hmb_shot_slots["__hmb_only__"]["values"]["prompt"],"Keep Only")
        self.assertEqual(node._hmb_active_slot_key,"old-channel-31\x1fold-shot-31")

    def test_web_target_slot_full_revision_path_keeps_visible_controls(self):
        node,_=manager();node._hmb_ruleset_names=();node._hmb_lifecycle_is_live=lambda *args:True
        node._hmb_cancellation_requested=False
        generator=SimpleNamespace(_hmb_node_deleted=False,is_cancellation_requested=False,_hmb_shot_channel_subscription=lambda:subscription(3))
        cap=node._hmb_issue_web_rerender_authority(request_id="offline-web-target-three",generator=generator,owner_key="offline-owner")
        media={"schema":"hmb-agent-reference-media","version":1,"images":[],"videos":[]}
        settings={"model_id":"seedance-2.5"};parent="Original parent instruction";seen=[]
        original=module._HMBWebRerenderExecution._from_owner
        def factory(owner,prompt,media,settings,**kwargs):
            view=original(owner,prompt,media,settings,**kwargs)
            def native_once():
                seen.append((view.get_parameter_value("model"),view.get_parameter_value("model_provider")))
                view.parameter_output_values["output"]=json.dumps({"contract":module._WEB_RERENDER_OUTPUT_CONTRACT,"source_sha256":hashlib.sha256(parent.encode()).hexdigest(),"instruction":"Revised target three"})
                if False:yield None
            view._run_native_agent_once=native_once;view._secure_hmb_outputs=Mock(return_value=False)
            return view
        before=copy.deepcopy((node.parameter_values,node.parameter_output_values,node._hmb_shot_slots))
        with patch.object(module._HMBWebRerenderExecution,"_from_owner",side_effect=factory):
            record=asyncio.run(node._hmb_run_web_rerender(parent,media,settings,cap))
        self.assertEqual(record["text"],"Revised target three")
        self.assertEqual(seen,[("model-3","provider-3")])
        self.assertEqual((node.parameter_values,node.parameter_output_values,node._hmb_shot_slots),before)
        self.assertFalse(node._hmb_shot_execution_locks["channel\x1fshot-3"].locked())

    def test_web_slot_snapshot_failure_does_not_leak_its_lock(self):
        node,_=manager();node._hmb_lifecycle_is_live=lambda *args:True;node._hmb_active_slot_key="channel\x1fshot-3"
        node._hmb_capture_active_slot=Mock(side_effect=RuntimeError("offline copy failure"))
        generator=SimpleNamespace(_hmb_node_deleted=False,is_cancellation_requested=False,_hmb_shot_channel_subscription=lambda:subscription(3))
        cap=node._hmb_issue_web_rerender_authority(request_id="offline-web-copy-failure",generator=generator,owner_key="offline-owner")
        media={"schema":"hmb-agent-reference-media","version":1,"images":[],"videos":[]}
        with self.assertRaises(RuntimeError):
            asyncio.run(node._hmb_run_web_rerender("parent",media,{},cap))
        self.assertFalse(node._hmb_shot_execution_locks["channel\x1fshot-3"].locked())

    def test_web_facade_uses_target_slot_provider_not_visible_view(self):
        node,_=manager();node._hmb_ruleset_names=();node._hmb_lifecycle_is_live=lambda *args:True
        media={"schema":"hmb-agent-reference-media","version":1,"images":[],"videos":[]}
        settings={"model_id":"seedance-2.5"}
        view=module._HMBWebRerenderExecution._from_owner(node,"parent instruction",media,settings,native_settings=node._hmb_shot_slots["channel\x1fshot-3"]["values"])
        self.assertEqual(view.get_parameter_value("model"),"model-3")
        self.assertEqual(view.get_parameter_value("model_provider"),"provider-3")
        self.assertEqual(node.parameter_values["model"],"Only model")
        self.assertIs(view._hmb_web_owner,node)

if __name__=="__main__":unittest.main(verbosity=2)
