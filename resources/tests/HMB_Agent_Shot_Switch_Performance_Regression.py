"""Offline native Shot switching, typed authoring and exact preview contracts."""
from __future__ import annotations

import asyncio
import copy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
from HMB_Agent_Multishot_Regression import module, manager, subscription


def native_fixture():
    node, _ = manager()
    values = {"model_provider": "provider-a", "model": "shared-model", "agent": None,
              "include_details": False, "output_schema": None, "additional_context": "",
              "agent_memory": {}, "prompt": "Original", "tools": [], "rulesets": [],
              "output": "Original result", "logs": ""}
    node.parameter_values = copy.deepcopy(values)
    node.parameter_output_values = {"output": "Original result", "logs": "", "agent": None}
    parameters = {name: SimpleNamespace(name=name, children=[], hide=False, hide_property=False)
                  for name in (*values, module._AGENT_SHOT_STORE_PARAMETER)}
    node.get_parameter_by_name = lambda name: parameters.get(name)
    node._native_parameter_value = lambda name, default=None: node.parameter_values.get(name, default)
    node._hmb_active_slot_key = "channel\x1fshot-1"
    node._hmb_slot_switching = False
    node._hmb_execution_result_snapshot = lambda: {"status": "succeeded"}
    node._refresh_hmb_execution_result_messages = Mock()
    node._hmb_notify_shot_preview = Mock()
    node._hmb_slot_native_list_value = lambda name: node.parameter_values.get(name, [])
    node._hmb_capture_active_slot = module.HMBAgentLibrary._hmb_capture_active_slot.__get__(node)
    node._hmb_shot_slots = {node._hmb_active_slot_key: node._hmb_native_slot_snapshot()}
    node._hmb_shot_slots["__hmb_default_settings__"] = copy.deepcopy(node._hmb_shot_slots[node._hmb_active_slot_key])
    node._hmb_shot_slots["channel\x1fshot-2"] = copy.deepcopy(node._hmb_shot_slots[node._hmb_active_slot_key])
    calls = []

    def native_set(owner, name, value, *args, **kwargs):
        calls.append((name, copy.deepcopy(value)))
        owner.parameter_values[name] = copy.deepcopy(value)
        # Stateful Standard provider callback: desired model may have equaled
        # its pre-switch value, yet must be restored after provider defaults.
        if name == "model_provider":
            owner.parameter_values["model"] = "provider-default"
            owner.parameter_values["include_details"] = True
            owner.parameter_values["agent_memory"] = {"provider-default": True}

    node.set_parameter_list_value = Mock(side_effect=lambda name, value: native_set(node, name, value))
    return node, parameters, calls, native_set


class ShotSwitchPerformanceTests(unittest.TestCase):
    def test_typed_comparison_preserves_zero_false_none_and_nested_list_order(self):
        equal = module._hmb_native_values_equal
        for left, right in ((False, 0), (None, ""), ([], ()), ({"value": False}, {"value": 0}),
                            ({"nested": [{"off": False}]}, {"nested": [{"off": 0}]}),
                            ({False: "value"}, {0: "value"}), ([1, 2], [2, 1])):
            self.assertFalse(equal(left, right), (left, right))
        self.assertTrue(equal({"zero": 0, "off": False, "empty": None},
                              {"empty": None, "off": False, "zero": 0}))
        opaque = object()
        self.assertTrue(equal(opaque, opaque))
        self.assertFalse(equal(opaque, object()))

    def test_unchanged_native_settings_skip_hooks_and_persist_exactly_once(self):
        node, parameters, calls, native_set = native_fixture()
        slot = node._hmb_shot_slots["channel\x1fshot-2"]
        slot["values"]["prompt"] = "Other Shot"
        before = {name: id(item) for name, item in parameters.items()}
        with patch.object(module._BaseAgent, "set_parameter_value", native_set):
            node._hmb_switch_native_slot("channel", "shot-2")
        self.assertEqual(calls, [("prompt", "Other Shot")])
        node._hmb_persist_shot_store.assert_called_once()
        node._hmb_notify_shot_preview.assert_not_called()
        self.assertEqual(before, {name: id(item) for name, item in parameters.items()})
        self.assertEqual(node._hmb_shot_slots["channel\x1fshot-1"]["values"]["prompt"], "Original")
        self.assertEqual(node.parameter_output_values["output"], "Original result")

    def test_provider_change_restores_dependent_values_after_callback(self):
        node, _, calls, native_set = native_fixture()
        slot = node._hmb_shot_slots["channel\x1fshot-2"]
        slot["values"]["model_provider"] = "provider-b"
        with patch.object(module._BaseAgent, "set_parameter_value", native_set):
            node._hmb_switch_native_slot("channel", "shot-2")
        self.assertEqual([name for name, _ in calls], ["model_provider", "model", "include_details", "agent_memory"])
        self.assertEqual(node.parameter_values["model"], "shared-model")
        self.assertIs(node.parameter_values["include_details"], False)
        self.assertEqual(node.parameter_values["agent_memory"], {})

    def test_nested_off_zero_schema_and_child_ids_are_not_collapsed(self):
        node, parameters, calls, native_set = native_fixture()
        child = SimpleNamespace(name="tools_saved_uid", element_id="durable-child-uid", hide=True, hide_property=True)
        parameters["tools"].children = [child]
        parameters[child.name] = child
        node.parameter_values[child.name] = {"enabled": False}
        slot = node._hmb_shot_slots["channel\x1fshot-2"]
        slot["values"]["agent_memory"] = {"items": [{"enabled": 0}]}
        slot["values"]["output_schema"] = {"properties": {"value": {"default": False}}}
        slot["children"] = {child.name: {"enabled": 0}}
        with patch.object(module._BaseAgent, "set_parameter_value", native_set):
            node._hmb_switch_native_slot("channel", "shot-2")
        self.assertIs(parameters[child.name], child)
        self.assertEqual(child.element_id, "durable-child-uid")
        self.assertFalse(child.hide)
        self.assertIs(type(node.parameter_values[child.name]["enabled"]), int)
        self.assertIs(node.parameter_values["output_schema"]["properties"]["value"]["default"], False)
        self.assertEqual([name for name, _ in calls], ["output_schema", "agent_memory", child.name])

    def test_nested_selection_batch_flushes_final_store_layout_and_ack_once(self):
        node, _ = manager()
        node._hmb_layout_shot_editor = Mock()
        node._hmb_notify_shot_preview = Mock()
        node._hmb_shot_editor_expanded = True
        node._native_parameter_value = lambda *_: {"shot": {"channel_uuid": "channel", "shot_uuid": "shot-1"}}
        def set_header(name, value):
            with node._hmb_editor_update():
                for _ in range(4):
                    node._hmb_request_shot_store_persist()
                    node._hmb_request_editor_layout()
        node.set_parameter_value = Mock(side_effect=set_header)
        node._hmb_handle_row_action(SimpleNamespace(name=module._AGENT_SHOT_ROW_PREFIX + "2"),
            {"shot": {"channel_uuid": "channel", "shot_uuid": "shot-2"},
             "action": {"kind": "select", "request_id": "a" * 32, "expanded": True}})
        node._hmb_persist_shot_store.assert_called_once()
        node._hmb_layout_shot_editor.assert_called_once()
        self.assertEqual(node._hmb_row_action_ack["channel\x1fshot-2"], "a" * 32)

    def test_synchronous_output_fanout_during_switch_reads_frozen_exact_slots(self):
        node, _, _, native_set = native_fixture()
        node._hmb_shot_slots["channel\x1fshot-2"]["outputs"]["output"] = "Second result"
        observations = []
        def publish(owner, name, value, *args, **kwargs):
            native_set(owner, name, value, *args, **kwargs)
            if name == "output":
                observations.append((owner._hmb_active_slot_key, owner.parameter_values["output"],
                    owner._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-1")["text"],
                    owner._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-2")["text"]))
        with patch.object(module._BaseAgent, "set_parameter_value", publish):
            node._hmb_switch_native_slot("channel", "shot-2")
        self.assertEqual(observations, [("channel\x1fshot-1", "Second result", "Original result", "Second result")])

    def test_pre_mutation_identity_rejection_is_bounded_and_preserves_success_ack(self):
        node, _ = manager()
        node._hmb_layout_shot_editor = Mock()
        node._hmb_row_action_ack = {"channel\x1fshot-1": "b" * 32}
        node.set_parameter_value = Mock()
        before = copy.deepcopy((node.parameter_values, node._hmb_shot_slots, node._hmb_active_slot_key))
        parameter = SimpleNamespace(name=module._AGENT_SHOT_ROW_PREFIX + "2")
        row = {"shot": {"channel_uuid": "stale-channel", "shot_uuid": "shot-2"},
               "action": {"kind": "run_selected", "request_id": "c" * 32}}
        with self.assertRaisesRegex(RuntimeError, "identity is unavailable"):
            node._hmb_handle_row_action(parameter, row)
        self.assertEqual(node._hmb_row_action_rejections, {parameter.name:
            {"rejected_request_id": "c" * 32, "error_code": "SHOT_IDENTITY_UNAVAILABLE"}})
        self.assertEqual(node._hmb_row_action_ack, {"channel\x1fshot-1": "b" * 32})
        self.assertEqual(before, (node.parameter_values, node._hmb_shot_slots, node._hmb_active_slot_key))
        node.set_parameter_value.assert_not_called()
        self.assertFalse(node._hmb_shot_workers)
        row["shot"]["channel_uuid"] = "channel"
        row["action"] = {"kind": "refresh", "request_id": "d" * 32}
        node._hmb_handle_row_action(parameter, row)
        self.assertEqual(node._hmb_row_action_rejections, {})

    def test_exact_preview_prefers_result_and_never_reads_other_or_visible_slots(self):
        node, _ = manager()
        node.parameter_output_values["output"] = "Another visible Shot"
        slot = node._hmb_shot_slots["channel\x1fshot-2"]
        slot["outputs"] = {"output": "Exact saved slot"}
        record = {"text": "Exact result", "shot": subscription(2), "private": "not public"}
        node._hmb_shot_results["channel\x1fshot-2"] = record
        value = node._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-2")
        self.assertEqual(value, {"text": "Exact result", "shot": {"channel_uuid": "channel",
            "shot_uuid": "shot-2", "shot_number": 2, "shot_name": "Renamed 2"}})
        value["shot"]["shot_name"] = "Caller changed"
        self.assertEqual(record["shot"]["shot_name"], "Renamed 2")
        record["text"] = ""
        self.assertEqual(node._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-2")["text"], "")
        record["shot"] = subscription(3)
        self.assertEqual(node._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-2")["text"], "Exact saved slot")
        slot["outputs"] = {}
        self.assertEqual(node._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-2")["text"], "")
        del node._hmb_shot_slots["channel\x1fshot-2"]
        self.assertIsNone(node._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-2"))
        self.assertIsNone(node._hmb_agent_shot_preview(channel_uuid="foreign", shot_uuid="shot-1"))

    def test_inactive_worker_notifies_only_its_exact_public_preview(self):
        node, prompt = manager()
        node._hmb_notify_shot_preview = Mock()
        text = "Inactive final text"
        result = {"status": "succeeded", "run_id": "synthetic-inactive", "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
        async def run():
            await asyncio.sleep(0)
        view = SimpleNamespace(parameter_values={}, parameter_output_values={"output": text, "logs": "", "agent": {}},
            _hmb_shot_policy_identity={}, _hmb_agent_reference_observation_snapshot=lambda: {},
            _hmb_execution_result_snapshot=lambda: result, _clear_hmb_runtime_policy=Mock(), _hmb_aprocess_locked=run)
        with patch.object(module._HMBAgentShotExecution, "_from_owner", return_value=view):
            asyncio.run(node._hmb_run_agent_shot(channel_uuid="channel", shot_uuid="shot-3", prompt_owner=prompt))
        node._hmb_notify_shot_preview.assert_called_once_with(channel_uuid="channel", shot_uuid="shot-3")
        self.assertEqual(node.parameter_values["prompt"], "Only authored text")
        self.assertEqual(node._hmb_agent_shot_preview(channel_uuid="channel", shot_uuid="shot-3")["text"], text)

    def test_preview_notification_uses_output_index_and_skips_forcing_unchanged_targets(self):
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        node, _ = manager()
        output = SimpleNamespace(name="output")
        node.get_parameter_by_name = lambda name: output if name == "output" else None
        failed = SimpleNamespace(_hmb_refresh_managed_prompt_projection=Mock(side_effect=RuntimeError("deleted target")))
        target = SimpleNamespace(_hmb_refresh_managed_prompt_projection=Mock())
        def edge(receiver, source=node, target_name="prompt"):
            return SimpleNamespace(source_node=source, source_parameter=output, target_node=receiver,
                                   target_parameter=SimpleNamespace(name=target_name))
        connections = SimpleNamespace(get_outgoing_connections_from_parameter=Mock(return_value=[
            edge(failed), edge(target), edge(target), edge(target, source=object()), edge(target, target_name="agent")]))
        with patch.object(GriptapeNodes, "FlowManager", return_value=SimpleNamespace(get_connections=lambda: connections)):
            node._hmb_notify_shot_preview(channel_uuid="channel", shot_uuid="shot-2")
        connections.get_outgoing_connections_from_parameter.assert_called_once_with(node, output)
        target._hmb_refresh_managed_prompt_projection.assert_called_once_with(
            source_node=node, channel_uuid="channel", shot_uuid="shot-2", force=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
