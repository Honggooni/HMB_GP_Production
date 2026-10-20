"""Read-only readiness uses native validators; never prepares or submits media."""
from __future__ import annotations
import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec=importlib.util.spec_from_file_location("preflight_seedance_target",ROOT/"HMBSeedanceGeneration.py")
t=importlib.util.module_from_spec(spec);sys.modules[spec.name]=t;spec.loader.exec_module(t)
CHANNEL="11111111-1111-4111-8111-111111111111"
SHOTS=[{"shot_uuid":f"33333333-3333-4333-8333-{n:012d}","number":n,"name":f"Authored asset {n}","revision":n} for n in range(1,6)]
PROJECT={"project_id":"katuri8","project_name":"까투리8"}

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def media_snapshot(kind="image_asset",count=1):
    picker=kind=="video_picker";records_key="ordered_videos" if picker else "ordered_assets"
    media={f"{n}-{j}":f"https://media.invalid/{n}-{j}.{'mp4' if picker else 'png'}" for n in range(1,6) for j in range(count)}
    shots=[{**shot,"selected_source_uids":[f"{shot['number']}-{j}" for j in range(count)],**({"picker_payload":{}} if picker else {})} for shot in SHOTS]
    doc={"channel_uuid":CHANNEL,"generation":1,"shots":shots,records_key:[{"source_uid":uid,"metadata":{}} for uid in media]}
    if not picker:doc["project_id"]=PROJECT["project_id"]
    return {"schema":"hmb-picker-shot-routing-snapshot" if picker else "hmb-shot-routing-snapshot","version":1,
        "publisher_instance_uuid":"22222222-2222-4222-8222-222222222222",**doc,"metadata_sha256":digest(doc),
        "media_sha256":digest({"media_descriptors":[{"source_uid":uid,"media_value_sha256":hashlib.sha256(value.encode()).hexdigest()} for uid,value in media.items()]}),"media_by_source_uid":media}

def subscription(number=1,kind="seedance"):
    shot=SHOTS[number-1]
    return {"schema":"hmb-shot-channel-subscription","version":1,"participant_kind":kind,"enabled":True,
        "channel_uuid":CHANNEL,"shot_uuid":shot["shot_uuid"],"shot_number":number,"shot_name":shot["name"]}

def graph():
    catalog_doc={"channel_uuid":CHANNEL,"generation":1,"shots":deepcopy(SHOTS)}
    catalog={"schema":"hmb-shot-routing-catalog","version":1,"publisher_instance_uuid":"22222222-2222-4222-8222-222222222222",**catalog_doc,"metadata_sha256":digest(catalog_doc)}
    source=SimpleNamespace(name="Exact Image",metadata={"node_type":"HMBImageAssetLibrary"},snapshot=media_snapshot())
    source._hmb_shot_routing_catalog=lambda:deepcopy(catalog)
    source._hmb_shot_routing_snapshot=Mock(side_effect=lambda *a,**kw:deepcopy(source.snapshot))
    source._hmb_project_identity=lambda:deepcopy(PROJECT)
    source._hmb_shot_channel_subscription=lambda:subscription(kind="image_asset")
    nodes=[source];edges={};gens=[]
    for n in range(1,6):
        node=object.__new__(t.HMBSeedanceGeneration);node.name=f"Generator opaque {9-n}";node.metadata={"node_type":"HMBSeedanceGeneration"}
        node.values={"model_id":t.MODEL_NAME_SEEDANCE_2_5,"prompt":"PRIVATE AUTHORED PROMPT MUST NEVER APPEAR", "resolution":"480p","duration":4,"ratio":"16:9","output_format":"mov","output_file":f"opaque_result_{n}.mov"}
        node.subscription=subscription(n);node.get_parameter_value=lambda name,node=node:node.values.get(name)
        node._hmb_shot_channel_subscription=lambda node=node:deepcopy(node.subscription)
        node._get_list_input=lambda name,node=node:list(node.values.get(name,[]))
        node._list_input_is_authoritative=lambda name:True
        node._capture_imageasset_project_selection=lambda:{"project":deepcopy(PROJECT)}
        node._project_incoming_connections=lambda target:edges.get(target.name,[])
        node._get_parameters=Mock(side_effect=AssertionError("mutating params"));node._reconcile_shared_shot_routing=Mock(side_effect=AssertionError("graph mutation"))
        node._process_generation=Mock(side_effect=AssertionError("render"));node._prepare_media_reference=Mock(side_effect=AssertionError("upload"))
        nodes.append(node);gens.append(node)
        edges[node.name]=[SimpleNamespace(source_node_name=source.name,source_parameter_name="SHOT_ASSET_OUT",target_parameter_name="SHOT_ASSET_IN")]
    return nodes,gens,source,edges

class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.nodes,self.gens,self.source,self.edges=graph()
        self.patches=[patch.object(t._shot_routing,"_same_flow_nodes",lambda node:("exact-flow",list(reversed(self.nodes)))),
            patch.object(t.HMBSeedanceGeneration,"_hmb_preflight_kind",staticmethod(lambda node:node.metadata.get("node_type",""))),
            patch.object(socket,"create_connection",side_effect=AssertionError("network"))]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
    def test_five_canonical_uuid_names_order_and_no_authored_or_render_changes(self):
        before=[deepcopy(node.values) for node in self.gens]
        report=self.gens[3]._hmb_render_preflight_report()
        self.assertTrue(report["ok"],report);self.assertEqual([row["name"] for row in report["rows"]],[shot["name"] for shot in SHOTS])
        self.assertEqual([row["generator"] for row in report["rows"]],[node.name for node in self.gens])
        self.assertNotIn("PRIVATE AUTHORED",json.dumps(report));self.assertNotIn("https://media",json.dumps(report))
        self.assertEqual(before,[node.values for node in self.gens]);self.source._hmb_shot_routing_snapshot.assert_called_once_with(CHANNEL,cached_only=True)
        for node in self.gens:
            node._get_parameters.assert_not_called();node._reconcile_shared_shot_routing.assert_not_called();node._process_generation.assert_not_called();node._prepare_media_reference.assert_not_called()
    def test_missing_and_duplicate_generators_never_infer_from_names(self):
        self.nodes.remove(self.gens[1]);self.gens[3].subscription=subscription(3)
        rows=self.gens[0]._hmb_render_preflight_report()["rows"]
        self.assertEqual([item["code"] for item in rows[1]["issues"]],["generator_missing"])
        self.assertEqual([item["code"] for item in rows[2]["issues"]],["generator_duplicate"])
        self.assertEqual([item["code"] for item in rows[3]["issues"]],["generator_missing"])
    def test_native_limits_path_collision_and_stale_name_are_reported(self):
        self.source.snapshot=media_snapshot(count=31)
        self.gens[1].values["output_file"]=self.gens[0].values["output_file"]
        self.gens[2].subscription["shot_name"]="Stale shot name"
        report=self.gens[0]._hmb_render_preflight_report();self.assertFalse(report["ok"])
        self.assertIn("output_duplicate",[i["code"] for i in report["rows"][0]["issues"]])
        self.assertIn("settings_invalid",[i["code"] for i in report["rows"][0]["issues"]])
        self.assertIn("shot_identity",[i["code"] for i in report["rows"][2]["issues"]])
    def test_cache_not_ready_is_unverified_not_empty_media_failure(self):
        self.source._hmb_shot_routing_snapshot.side_effect=ValueError("cache preparing")
        report=self.gens[0]._hmb_render_preflight_report();self.assertTrue(report["ok"],report)
        self.assertEqual(report["rows"][0]["status"],"warning")
    def test_cross_flow_physical_source_and_project_mix_fail_locally(self):
        self.edges[self.gens[0].name][0].source_node_name="foreign unregistered Image"
        self.gens[1]._capture_imageasset_project_selection=lambda:{"project":{"project_id":"superwings12","project_name":"슈퍼윙즈12"}}
        report=self.gens[0]._hmb_render_preflight_report();self.assertFalse(report["ok"])
        self.assertIn("source_route",[i["code"] for i in report["rows"][0]["issues"]])
        self.assertIn("project_mixed",[i["code"] for i in report["rows"][1]["issues"]])
    def test_only_editing_and_extension_stay_independent_and_use_native_validation(self):
        node=self.gens[0];node.subscription.update(enabled=False,channel_uuid="",shot_uuid="",shot_name="Only")
        self.nodes[:]=[node];node.values.update(task=t.TASK_VIDEO_EDITING,duration=-1,ratio="adaptive",VIDEO_REFERENCES=["PRIVATE VIDEO URL"])
        self.edges.clear();before=deepcopy(node.values)
        for task in [t.TASK_VIDEO_EDITING,t.TASK_VIDEO_EXTENSION]:
            node.values["task"]=task;report=node._hmb_render_preflight_report();self.assertTrue(report["ok"],report)
        self.assertEqual(node.values["resolution"],before["resolution"]);node.values["VIDEO_REFERENCES"]=[]
        self.assertFalse(node._hmb_render_preflight_report()["ok"])
    @staticmethod
    def _real_only_project_fixture():
        # Reuse its registered graph and actual project capture instead of the
        # older convenient preflight fixture's unconditional PROJECT return.
        name="preflight_registered_only_project_fixture"
        if name not in sys.modules:
            spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name("HMB_Seedance_Only_Project_Selection_Regression.py"))
            module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
        return sys.modules[name]
    @staticmethod
    def _real_only_preflight_node(fixture,task):
        node=fixture.Node(fixture.values_for(task))
        # Draft transport fixtures intentionally keep their execution snapshot
        # in values; this inspector reads native authoring parameters instead.
        # Hydrate the same literal inputs into that native read surface.
        node.parameter_values.update(deepcopy(node.values))
        node.parameter_values[fixture.t.VIDEO_REFERENCES_PARAMETER]=deepcopy(node.values["video_references"])
        node.parameter_values["output_file"]="only-project-required-preflight.mp4"
        return node
    def test_only_real_capture_requires_project_and_keeps_manual_inputs(self):
        fixture=self._real_only_project_fixture()
        for task in (fixture.t.TASK_REFERENCE_TO_VIDEO,fixture.t.TASK_VIDEO_EDITING,fixture.t.TASK_VIDEO_EXTENSION):
            with self.subTest(task=task):
                node=self._real_only_preflight_node(fixture,task);registered=fixture.Graph(node)
                node.select(fixture.ONLY_PROJECT_UNSELECTED)
                before=deepcopy(node.parameter_values)
                with registered.context(),patch.object(fixture.t._shot_routing,"_same_flow_nodes",lambda current:("fixture-flow",list(registered.nodes.values()))),patch.object(node,"_prepare_media_reference",side_effect=AssertionError("preflight uploaded media")),patch.object(node,"_process_generation",side_effect=AssertionError("preflight rendered")),patch.object(node,"_ensure_broker_connected",side_effect=AssertionError("preflight authenticated")):
                    with self.assertRaises(fixture.t._ProjectSelectionRequired):
                        node._capture_imageasset_project_selection()
                    report=node._hmb_render_preflight_report()
                    self.assertFalse(report["ok"],report)
                    self.assertEqual(report["scope"],"only")
                    self.assertIn("project_unverified",[item["code"] for item in report["rows"][0]["issues"]])
                    self.assertEqual(node.parameter_values,before)
                    for project_id,project_name in fixture.CANONICAL_PROJECTS.items():
                        node.select(project_name)
                        if project_id not in {"superwings12", "katuri8"}:
                            inactive_before=deepcopy(node.parameter_values)
                            with self.assertRaisesRegex(ValueError,"not active"):
                                node._capture_imageasset_project_selection()
                            inactive_report=node._hmb_render_preflight_report()
                            self.assertFalse(inactive_report["ok"],inactive_report)
                            self.assertIn("project_unverified",[item["code"] for item in inactive_report["rows"][0]["issues"]])
                            self.assertEqual(node.parameter_values,inactive_before)
                            continue
                        selected=node._capture_imageasset_project_selection()
                        self.assertEqual(selected["schema"],fixture.ONLY_PROJECT_SELECTION_SCHEMA)
                        self.assertEqual(selected["project"],{"project_id":project_id,"project_name":project_name})
                        self.assertEqual(selected["selection_source"],"only_explicit")
                        self.assertEqual(selected["sources"],[]);self.assertEqual(selected["edges"],[])
                        explicit_before=deepcopy(node.parameter_values)
                        valid_report=node._hmb_render_preflight_report()
                        self.assertTrue(valid_report["ok"],valid_report)
                        self.assertEqual(valid_report["rows"][0]["project"],project_name)
                        self.assertEqual(node.parameter_values,explicit_before)
                    node.select(fixture.ONLY_PROJECT_UNSELECTED)
                self.assertEqual(node.parameter_values,before)
        while fixture.base.TEMPORARIES:fixture.base.TEMPORARIES.pop().cleanup()
    def test_only_does_not_hide_invalid_or_conflicting_project(self):
        fixture=self._real_only_project_fixture()
        for mode in ("unknown_selector","connected_project_conflict"):
            with self.subTest(mode=mode):
                node=self._real_only_preflight_node(fixture,fixture.t.TASK_VIDEO_EDITING);registered=fixture.Graph(node)
                if mode=="unknown_selector":node.select("unknown-project")
                else:registered.direct(project="katuri8");node.select("superwings12")
                before=deepcopy(node.parameter_values)
                with registered.context(),patch.object(fixture.t._shot_routing,"_same_flow_nodes",lambda current:("fixture-flow",list(registered.nodes.values()))):
                    with self.assertRaises(ValueError):node._capture_imageasset_project_selection()
                    report=node._hmb_render_preflight_report()
                self.assertFalse(report["ok"],report)
                self.assertIn("project_unverified",[item["code"] for item in report["rows"][0]["issues"]])
                self.assertNotIn("settings_invalid",[item["code"] for item in report["rows"][0]["issues"]])
                self.assertEqual(node.parameter_values,before)
        while fixture.base.TEMPORARIES:fixture.base.TEMPORARIES.pop().cleanup()
    def test_resume_and_final_sparse_skip_missing_sources_without_state_change(self):
        node=self.gens[0];self.nodes[:]=[node];self.edges.clear()
        node.values.update(resume_generation_id="job-"+"a"*32,model_id="unsupported sparse model",prompt="",duration=0)
        before=deepcopy(node.values);self.assertTrue(node._hmb_render_preflight_report()["ok"]);self.assertEqual(before,node.values)
        node.values.update(resume_generation_id="",model_id=t.MODEL_NAME_SEEDANCE_2_5,draft_action=t.DRAFT_ACTION_FINAL,draft_job_id="job-"+"b"*32)
        before=deepcopy(node.values);report=node._hmb_render_preflight_report();self.assertTrue(report["ok"],report);self.assertEqual(before,node.values)
    def test_preview_effective_copy_does_not_promote_authored_resolution(self):
        self.gens[0].values.update(draft_action=t.DRAFT_ACTION_PREVIEW,resolution="720p")
        report=self.gens[0]._hmb_render_preflight_report();self.assertEqual(report["rows"][0]["resolution"],"480p")
        self.assertEqual(self.gens[0].values["resolution"],"720p")
    def test_orphan_uuid_and_broken_optional_participant_are_isolated(self):
        self.gens[4].subscription["shot_uuid"]="99999999-9999-4999-8999-999999999999"
        report=self.gens[0]._hmb_render_preflight_report()
        self.assertIn("orphan_generator",[item["code"] for item in report["issues"]])
        self.assertEqual(report["rows"][0]["status"],"ready")
        self.assertEqual(report["rows"][4]["status"],"error")
    def test_async_command_cancel_replay_and_changed_selection_never_publish_old_report(self):
        async def exercise():
            node=self.gens[0];node._hmb_preflight_epoch=0;node._hmb_preflight_task=None;node._hmb_preflight_command_ids=set();node._hmb_node_deleted=False;node._hmb_preflight_active_request_id="";node._hmb_preflight_client_sequences={};node._hmb_preflight_active_client_session=""
            node._hmb_publish_preflight=Mock();node._hmb_render_preflight_report=Mock(side_effect=lambda:{"phase":"complete","rows":[{}],"ok":True})
            command={"action":"inspect","request_id":"a"*32};node._hmb_handle_preflight_command(command);node._hmb_handle_preflight_command(command)
            node._hmb_handle_preflight_command({"action":"cancel","request_id":"a"*32});await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_publish_preflight.call_count,1);self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["phase"],"cancelled");node._hmb_render_preflight_report.assert_not_called()
            node._hmb_publish_preflight.reset_mock();node._hmb_handle_preflight_command({"action":"inspect","request_id":"b"*32});node.subscription=subscription(2)
            await asyncio.sleep(0);await asyncio.sleep(0)
            published=node._hmb_publish_preflight.call_args.args[0];self.assertEqual(published["phase"],"stale");self.assertFalse(published["ok"]);self.assertEqual(published["rows"],[])
            node._hmb_publish_preflight.reset_mock();session="f"*32
            node._hmb_handle_preflight_command({"action":"inspect","request_id":"c"*32,"client_session":session,"sequence":1});node._hmb_handle_preflight_command({"action":"inspect","request_id":"d"*32,"client_session":session,"sequence":2})
            epoch=node._hmb_preflight_epoch;node._hmb_handle_preflight_command({"action":"cancel","request_id":"c"*32});node._hmb_handle_preflight_command({"action":"inspect","request_id":"c"*32,"client_session":session,"sequence":1})
            self.assertEqual(node._hmb_preflight_epoch,epoch);await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_publish_preflight.call_count,1);self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["request_id"],"d"*32)
            # A not-yet-seen older UI command must also be rejected after B.
            node._hmb_publish_preflight.reset_mock();node._hmb_handle_preflight_command({"action":"inspect","request_id":"e"*32,"client_session":session,"sequence":4})
            epoch=node._hmb_preflight_epoch;node._hmb_handle_preflight_command({"action":"inspect","request_id":"0"*32,"client_session":session,"sequence":3})
            self.assertEqual(node._hmb_preflight_epoch,epoch);await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_publish_preflight.call_count,1);self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["request_id"],"e"*32)
            # Long-lived nodes permit fresh widget sessions; the bounded
            # history never evicts or cancels the current in-flight owner.
            for index in range(70):
                command={"action":"inspect","request_id":f"{index+100:032x}","client_session":f"{index+200:032x}","sequence":1}
                node._hmb_handle_preflight_command(command);await asyncio.sleep(0);await asyncio.sleep(0)
                self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["request_id"],command["request_id"])
            self.assertEqual(len(node._hmb_preflight_client_sequences),64)
            command={"action":"inspect","request_id":"1"*32,"client_session":"2"*32,"sequence":1};node._hmb_handle_preflight_command(command)
            epoch=node._hmb_preflight_epoch;node._hmb_handle_preflight_command({"action":"inspect","request_id":"3"*32,"client_session":"4"*32,"sequence":1})
            self.assertEqual(node._hmb_preflight_epoch,epoch);await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["request_id"],command["request_id"])
        asyncio.run(exercise())
    def test_engine_loop_unavailable_does_not_lease_a_later_widget_session(self):
        node=self.gens[0];node._hmb_preflight_epoch=0;node._hmb_preflight_task=None;node._hmb_preflight_command_ids=set();node._hmb_node_deleted=False
        node._hmb_preflight_active_request_id="";node._hmb_preflight_client_sequences={};node._hmb_preflight_active_client_session=""
        node._hmb_publish_preflight=Mock();node._hmb_render_preflight_report=Mock(return_value={"phase":"complete","rows":[],"ok":True})
        node._hmb_handle_preflight_command({"action":"inspect","request_id":"1"*32,"client_session":"2"*32,"sequence":1})
        self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["issues"][0]["code"],"event_loop_unavailable")
        self.assertEqual(node._hmb_preflight_active_request_id,"");self.assertEqual(node._hmb_preflight_active_client_session,"")
        async def retry():
            node._hmb_handle_preflight_command({"action":"inspect","request_id":"3"*32,"client_session":"4"*32,"sequence":1})
            await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_publish_preflight.call_args.args[0]["request_id"],"3"*32)
            self.assertTrue(node._hmb_publish_preflight.call_args.args[0]["ok"])
        asyncio.run(retry())
    def test_publisher_failure_and_reentrant_new_request_release_only_their_own_epoch(self):
        node=self.gens[0];node._hmb_preflight_epoch=0;node._hmb_preflight_task=None;node._hmb_preflight_command_ids=set();node._hmb_node_deleted=False
        node._hmb_preflight_active_request_id="";node._hmb_preflight_client_sequences={};node._hmb_preflight_active_client_session=""
        node._hmb_publish_preflight=Mock(side_effect=RuntimeError("display disconnected"));node._hmb_render_preflight_report=Mock(side_effect=lambda:{"phase":"complete","rows":[],"ok":True})
        command=lambda nonce,session,seq:{"action":"inspect","request_id":nonce*32,"client_session":session*32,"sequence":seq}
        with self.assertRaises(RuntimeError):node._hmb_handle_preflight_command(command("1","2",1))
        self.assertEqual(node._hmb_preflight_active_request_id,"")
        async def exercise():
            node._hmb_handle_preflight_command(command("3","4",1));await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_preflight_active_request_id,"")
            published=[]
            def publish(value):
                published.append(value["request_id"])
                if value["request_id"]=="5"*32:
                    node._hmb_handle_preflight_command(command("6","7",2))
                    self.assertEqual(node._hmb_preflight_active_request_id,"6"*32)
            node._hmb_publish_preflight=publish;node._hmb_handle_preflight_command(command("5","7",1))
            await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(node._hmb_preflight_active_request_id,"6"*32)
            await asyncio.sleep(0);await asyncio.sleep(0)
            self.assertEqual(published,["5"*32,"6"*32]);self.assertEqual(node._hmb_preflight_active_request_id,"")
        asyncio.run(exercise())

if __name__=="__main__":unittest.main(verbosity=2)
