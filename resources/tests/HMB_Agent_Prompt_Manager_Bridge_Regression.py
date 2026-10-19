"""One Prompt manager to independent native Agents: frozen paired-data bridge.

Host graph lookup is fixture-only. No SDK graph, policy DAT, media I/O, network,
model or Broker submission is used; the installed-host companion covers DAG work.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec=importlib.util.spec_from_file_location("hmb_agent_prompt_manager_bridge_target",ROOT/"HMBAgentLibrary.py")
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
import _hmb_shot_routing as routing
Agent=module.HMBAgentLibrary

def sha(value):return hashlib.sha256(value.encode()).hexdigest()
def subscription(number,kind="agent"):
    return {"schema":"hmb-shot-channel-subscription","version":1,"participant_kind":kind,"enabled":True,
            "channel_uuid":"channel","shot_uuid":f"shot-{number}","shot_number":number,"shot_name":f"Renamed {number}"}
def document(number):
    visible=f"Visible instruction {number}";machine=f"HMB original opaque machine {number}"
    return {"schema":"hmb-prompt-shot-document","version":1,"subscription":subscription(number,"prompt"),
            "visible_prompt":visible,"machine_prompt":machine,
            "paired_snapshot":{"schema":"hmb-prompt-paired-snapshot","version":1,"generation":number,
                               "visible_sha256":sha(visible),"machine_sha256":sha(machine),"machine_prompt":machine},
            "shot_context":{"shot":number},"reference_media":{"schema":"hmb-agent-reference-media","version":1,
                            "images":[{"token":"@image1","source":f"offline/image-{number}.png"}],"videos":[]},
            "generation_context":{"duration_seconds":number+3,"generate_audio":False,"priority":0},
            "project_identity":{"project_id":"katuri8","project_name":"까투리8"}}
class RegisteredPrompt:
    def __init__(self):
        self.metadata={"library":"HMB_GP_Production","node_type":"HMBPromptLibrary"}
        self._hmb_node_deleted=False;self._hmb_shot_route_status={"ok":True,"code":"ready"}
        self.active_shot=1;self.documents={number:document(number) for number in range(1,6)}
        self.parameter_output_values={"PROMPT_OUT":self.documents[1]["visible_prompt"]}
        self.parameter_values={"PROMPT_OUT":self.documents[1]["visible_prompt"]}
    def _hmb_shot_manager_enabled(self):return True
    def _hmb_prompt_shot_document(self,*,channel_uuid,shot_uuid):
        assert channel_uuid=="channel"
        return copy.deepcopy(self.documents[int(shot_uuid.rsplit("-",1)[1])])
    def _hmb_shot_channel_subscription(self):return subscription(self.active_shot,"prompt")

def make_agent(number,source):
    node=object.__new__(Agent);node.name=f"Native Agent {number}";node._hmb_node_deleted=False
    node._hmb_shot_route_status={"ok":True,"code":"ready"};node._hmb_shot_channel_subscription=lambda:subscription(number)
    node._hmb_rules_active=False;node._hmb_native_prompt_read_active=False;node._hmb_runtime_prompt=""
    node.parameter_values={"prompt":f"Authored Only {number}","SHOT_PROMPT_IN":source.documents[1]["visible_prompt"],"model":f"native-model-{number}"}
    node.parameter_output_values={"output":f"Previous {number}"};node._native_parameter_value=lambda name,default="":node.parameter_values.get(name,default)
    setattr(node,module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,source)
    return node

class BridgeContracts(unittest.TestCase):
    def setUp(self):
        self.source=RegisteredPrompt();self.nodes=[make_agent(number,self.source) for number in range(1,6)]
        self.edges={id(node):self.source for node in self.nodes}
        def verify(node):
            owner=self.edges.get(id(node));setattr(node,module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,owner)
            return type(owner) is RegisteredPrompt and owner.metadata=={"library":"HMB_GP_Production","node_type":"HMBPromptLibrary"}
        self.verify=Mock(side_effect=verify)
        self.patches=[patch.object(module,"_is_direct_hmb_prompt_library_connection",self.verify),
                      patch.object(routing,"resolve_shot_prompt_owner",side_effect=lambda node,**kw:self.edges.get(id(node))),
                      patch.object(socket,"create_connection",side_effect=AssertionError("external networking")),
                      patch.object(urllib.request,"urlopen",side_effect=AssertionError("external HTTP"))]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()

    def test_five_individual_agents_capture_own_shot_not_prompt_active_editor(self):
        before=copy.deepcopy((self.source.parameter_values,self.source.parameter_output_values))
        for number,node in enumerate(self.nodes,1):
            binding=node._assert_exact_prompt_shot_route()
            self.assertEqual(binding,subscription(number))
            self.assertEqual(node.get_parameter_value("SHOT_PROMPT_IN"),f"Visible instruction {number}")
            self.assertEqual(module._paired_machine_prompt(node,node.get_parameter_value("SHOT_PROMPT_IN")),f"HMB original opaque machine {number}")
            self.assertEqual(node._hmb_selected_project()["project_id"],"katuri8")
            self.assertIs(getattr(node,module._REGISTERED_PROMPT_OWNER_ATTRIBUTE),self.source)
            self.assertEqual(node.parameter_values["model"],f"native-model-{number}")
        self.assertEqual((self.source.parameter_values,self.source.parameter_output_values),before)

    def test_current_editor_changes_do_not_replace_running_pair_media_or_settings(self):
        node=self.nodes[2];node._assert_exact_prompt_shot_route();view=getattr(node,module._FROZEN_PROMPT_SHOT_ATTRIBUTE)
        original=copy.deepcopy(self.source.documents[3]);self.source.active_shot=5
        self.source.documents[3]["machine_prompt"]="Changed while running"
        self.source.documents[3]["reference_media"]["images"][0]["source"]="other.png"
        self.source.documents[3]["generation_context"]["duration_seconds"]=99
        machine=module._paired_machine_prompt(node,view.visible_prompt)
        self.assertEqual(machine,original["machine_prompt"])
        self.assertEqual(view._hmb_agent_reference_media(machine),original["reference_media"])
        self.assertEqual(view._hmb_agent_generation_context(machine),original["generation_context"])
        returned=view._hmb_agent_reference_media(machine);returned["images"].clear()
        self.assertEqual(len(view._hmb_agent_reference_media(machine)["images"]),1)

    def test_corrupt_pair_and_foreign_uuid_block_before_native_work(self):
        for change in (lambda doc:doc["paired_snapshot"].update(machine_sha256="0"*64),
                       lambda doc:doc["subscription"].update(shot_uuid="foreign")):
            self.source.documents[2]=document(2);change(self.source.documents[2])
            with self.assertRaises(RuntimeError):self.nodes[1]._assert_exact_prompt_shot_route()
            self.assertIs(getattr(self.nodes[1],module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE),self.source)
            self.assertIsNone(getattr(self.nodes[1],module._FROZEN_PROMPT_SHOT_ATTRIBUTE,None))

    def test_revalidate_retained_source_then_keep_original_frozen_data(self):
        node=self.nodes[1];node._assert_exact_prompt_shot_route();view=getattr(node,module._FROZEN_PROMPT_SHOT_ATTRIBUTE)
        node._hmb_revalidate_prompt_manager_owner();self.assertIs(getattr(node,module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE),view)
        self.edges[id(node)]=RegisteredPrompt()
        with self.assertRaises(RuntimeError):node._hmb_revalidate_prompt_manager_owner()
        self.assertIs(getattr(node,module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE),view)

    def test_hydration_and_preview_use_individual_uuid_without_editing_prompt_manager(self):
        node=self.nodes[3];node.set_parameter_value=Mock(side_effect=lambda name,value:node.parameter_values.update({name:value}))
        node._set_native_prompt_preview=Mock();self.assertTrue(node._hmb_hydrate_shot_prompt_from_source(self.source))
        node.set_parameter_value.assert_called_with("SHOT_PROMPT_IN","Visible instruction 4")
        node._refresh_routed_prompt_preview()
        node._set_native_prompt_preview.assert_called_with("Visible instruction 4",enabled=True)
        self.assertEqual(self.source.active_shot,1)
        self.assertEqual(self.source.parameter_output_values["PROMPT_OUT"],"Visible instruction 1")

    def test_catalog_offers_manager_shots_without_stealing_other_agents(self):
        node=self.nodes[2]
        other=SimpleNamespace(_hmb_shot_channel_subscription=lambda:subscription(2),_hmb_node_deleted=False)
        snapshot={"channel_uuid":"channel","shots":[{"shot_uuid":f"shot-{n}","number":n,"name":f"Renamed {n}","revision":0} for n in range(1,6)]}
        with patch.object(routing,"_same_flow_nodes",return_value=("flow",[node,self.source,other])):
            catalog=node._hmb_available_agent_shot_catalog(snapshot)
        self.assertEqual([row["number"] for row in catalog["shots"]],[1,3,4,5])
        self.assertEqual(self.source.active_shot,1)

    def test_cleanup_discards_frozen_owner_pair_and_keeps_native_authored_values(self):
        node=self.nodes[4];node._assert_exact_prompt_shot_route();before=copy.deepcopy(node.parameter_values)
        node._clear_hmb_runtime_policy()
        self.assertIsNone(getattr(node,module._REGISTERED_PROMPT_OWNER_ATTRIBUTE))
        self.assertIsNone(getattr(node,module._FROZEN_PROMPT_SHOT_ATTRIBUTE))
        self.assertIsNone(getattr(node,module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE))
        self.assertEqual(node.parameter_values,before)

    def test_ordinary_legacy_prompt_path_has_no_manager_document_read(self):
        node=self.nodes[0];source=SimpleNamespace(_hmb_shot_channel_subscription=lambda:subscription(1,"prompt"),_hmb_shot_route_status={"ok":True,"code":"ready"})
        setattr(node,module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,source)
        self.assertEqual(node._assert_exact_prompt_shot_route(),subscription(1))
        self.assertIsNone(getattr(node,module._FROZEN_PROMPT_SHOT_ATTRIBUTE,None))
        self.verify.assert_not_called()

if __name__=="__main__":unittest.main(verbosity=2)
