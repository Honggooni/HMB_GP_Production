"""Saved native text survives an unready readonly Prompt projection."""
from __future__ import annotations
import asyncio
from copy import deepcopy
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from HMB_Agent_Catalog_Presentation_Regression import surface, module, Agent, forbidden, offline_connect


class SavedPreview(unittest.TestCase):
    def setUp(self):
        self.guards = [patch.object(socket, "create_connection", forbidden),
            patch.object(socket.socket, "connect", offline_connect)]
        for guard in self.guards:
            guard.start()

    def tearDown(self):
        for guard in reversed(self.guards):
            guard.stop()

    def test_initial_setup_setter_preserves_saved_editor_until_exact_document_ready(self):
        node, source, _, _, writes, _, setter = surface()
        expected = deepcopy(node.parameter_values["prompt"])
        source._hmb_shot_manager_enabled = lambda: True
        source._hmb_prompt_shot_view = lambda **kwargs: {"visible_prompt": "Exact restored Shot document", "subscription": kwargs}
        node._hmb_manager_prompt_owner = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Legacy Prompt consolidation pending"))
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "Saved visible Prompt", initial_setup=True)
            self.assertTrue(node._hmb_prompt_preview_hydration_pending)
            for _ in range(5):
                node._refresh_routed_prompt_preview()
            self.assertEqual(node.parameter_values["prompt"], expected)
            self.assertNotIn("prompt", writes)
            self.assertFalse(getattr(node, "_hmb_rules_active", False))
            node._hmb_manager_prompt_owner = lambda **kwargs: source
            node._refresh_routed_prompt_preview()
        self.assertEqual(node.parameter_values["prompt"], "Exact restored Shot document")
        self.assertFalse(node._hmb_prompt_preview_hydration_pending)
        self.assertEqual(node._hmb_prompt_before_preview, expected)
        self.assertEqual(writes, ["prompt"])

    def test_real_removal_clears_pending_saved_preview(self):
        node, source, _, _, writes, _, setter = surface()
        node._hmb_capture_saved_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "Saved visible Prompt")
        node._hmb_manager_prompt_owner = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("No canonical source"))
        parameter = SimpleNamespace(name=module._AGENT_SHOT_PROMPT_INPUT_PARAMETER)
        node.get_parameter_by_name.__self__[parameter.name] = module.Parameter(name=parameter.name)
        node.parameter_values[parameter.name] = "Saved visible Prompt"
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None), \
                patch.object(module, "_is_direct_hmb_prompt_library_connection", return_value=False):
            node.after_incoming_connection_removed(source, SimpleNamespace(name="PROMPT_OUT"), parameter)
        self.assertFalse(node._hmb_prompt_preview_hydration_pending)
        self.assertEqual(node.parameter_values["prompt"], "")
        self.assertIn("prompt", writes)

    def test_ordinary_missing_source_retains_existing_explicit_clear_behavior(self):
        node, _, _, _, writes, _, setter = surface()
        node._hmb_manager_prompt_owner = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Missing"))
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node._refresh_routed_prompt_preview()
        self.assertEqual(node.parameter_values["prompt"], "")
        self.assertEqual(writes, ["prompt"])

    def test_output_and_non_string_saved_values_do_not_arm_hydration(self):
        node, _, *_ = surface()
        node._hmb_capture_saved_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "Saved", is_output=True)
        node._hmb_capture_saved_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, None)
        self.assertFalse(getattr(node, "_hmb_prompt_preview_hydration_pending", False))

    def test_empty_saved_hidden_default_preserves_native_only_and_five_shot_slots(self):
        for number in (None, 1, 2, 3, 4, 5):
            with self.subTest(shot=number):
                node, _, _, _, writes, _, setter = surface()
                if number is None:
                    node._hmb_shot_channel_subscription = lambda: {"enabled": False}
                else:
                    node._hmb_shot_channel_subscription = lambda n=number: {
                        "enabled": True, "channel_uuid": "channel", "shot_uuid": "shot-"+str(n),
                        "shot_number": n, "shot_name": "Shot "+str(n)}
                node._hmb_manager_prompt_owner = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Source hydration pending"))
                expected = deepcopy(node.parameter_values["prompt"])
                slots = deepcopy(node._hmb_shot_slots)
                outputs = deepcopy(node.parameter_output_values)
                with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                        patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
                    node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "", initial_setup=True)
                    self.assertTrue(node._hmb_prompt_preview_hydration_pending)
                    for _ in range(5): node._refresh_routed_prompt_preview()
                self.assertEqual(node.parameter_values["prompt"], expected)
                self.assertNotIn("prompt", writes)
                self.assertEqual(node._hmb_shot_slots, slots)
                self.assertEqual(node.parameter_output_values, outputs)

    def test_saved_empty_waits_for_exact_live_blank_and_rejects_sibling_blank(self):
        node, source, _, _, writes, _, setter = surface()
        source._hmb_shot_manager_enabled = lambda: True
        source._hmb_prompt_shot_view = lambda **kwargs: {"visible_prompt": "", "subscription": kwargs}
        node._hmb_manager_prompt_owner = lambda **kwargs: source
        expected = deepcopy(node.parameter_values["prompt"])
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            # Initial replay cannot turn even a ready display cache into an
            # authoring edit before all saved native values have been restored.
            node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "", initial_setup=True)
            self.assertEqual(node.parameter_values["prompt"], expected)
            self.assertNotIn("prompt", writes)
            source._hmb_prompt_shot_view = lambda **kwargs: {"visible_prompt": "", "subscription": {
                "channel_uuid": "channel", "shot_uuid": "shot-2"}}
            node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "")
            self.assertEqual(node.parameter_values["prompt"], expected)
            self.assertTrue(node._hmb_prompt_preview_hydration_pending)
            source._hmb_prompt_shot_view = lambda **kwargs: {"visible_prompt": "", "subscription": kwargs}
            node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "")
            self.assertEqual(node.parameter_values["prompt"], "")
            self.assertFalse(node._hmb_prompt_preview_hydration_pending)
        self.assertEqual(writes, ["prompt"])

    def test_equal_canonical_ack_and_registered_hydration_repair_root_once_without_native_writes(self):
        node, _, body, rows, writes, publications, setter = surface()
        header = node.get_parameter_by_name(module._AGENT_WIDGET_PARAMETER)
        node.root_ui_element.children[:] = [header, *rows, *body]
        before = deepcopy({name: node.parameter_values[name] for name in ("prompt", "model", "model_provider", "additional_context", "output_schema")})
        node._refresh_agent_shot_route.reset_mock()
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node._hmb_reconcile_shot_routing(deepcopy(node._hmb_shot_catalog_snapshot))
            ordered = list(node.root_ui_element.children)
            self.assertEqual(ordered[ordered.index(rows[0])+1:ordered.index(rows[1])], body)
            node.reorder_elements.assert_called_once()
            node.reorder_elements.reset_mock()
            writes.clear(); publications.clear()
            for _ in range(25):
                node._hmb_post_hydration_state_restore()
                node._hmb_reconcile_shot_routing(deepcopy(node._hmb_shot_catalog_snapshot))
            node._hmb_node_deleted = True
            node.root_ui_element.children[:] = [header, *rows, *body]
            node._hmb_post_hydration_state_restore()
        node.reorder_elements.assert_not_called()
        node._refresh_agent_shot_route.assert_not_called()
        self.assertEqual(writes, [])
        self.assertEqual(publications, [])
        self.assertEqual({name: node.parameter_values[name] for name in before}, before)

    def test_initial_saved_ui_and_store_place_body_without_granting_source_authority(self):
        node, source, body, rows, writes, _, setter = surface()
        header = node.get_parameter_by_name(module._AGENT_WIDGET_PARAMETER)
        saved = deepcopy(node.parameter_values[module._AGENT_WIDGET_PARAMETER])
        native_before = deepcopy({item.name: node.parameter_values.get(item.name) for item in body})
        slots_before = deepcopy(node._hmb_shot_slots)
        store = {"schema": module._AGENT_SHOT_STORE_SCHEMA, "version": 1,
            "slots": slots_before, "active": node._hmb_active_slot_key,
            "editor_expanded": True, "results": {}}
        node._hmb_shot_catalog_snapshot = {}
        node.root_ui_element.children[:] = [header, *rows, *body]
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None), \
                patch("_hmb_shot_routing.schedule_post_hydration_reconcile"), \
                patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=AssertionError("No live Source")) as worker:
            node.set_parameter_value(module._AGENT_WIDGET_PARAMETER, saved, initial_setup=True)
            ordered = list(node.root_ui_element.children)
            self.assertEqual(ordered[ordered.index(rows[0])+1:ordered.index(rows[1])], body)
            node.reorder_elements.assert_called_once()
            self.assertEqual(node._hmb_shot_catalog_snapshot, {})
            self.assertEqual(node._hmb_agent_shot_subscriptions(), [])
            with self.assertRaises(RuntimeError) as denied:
                asyncio.run(node._hmb_run_agent_shot(channel_uuid="channel", shot_uuid="shot-1", prompt_owner=source))
            self.assertEqual(str(denied.exception), module._HMB_TOPOLOGY_UNAVAILABLE_MESSAGE)
            worker.assert_not_called()
            node.reorder_elements.reset_mock(); writes.clear()
            for _ in range(25):
                node.set_parameter_value(module._AGENT_WIDGET_PARAMETER, deepcopy(saved), initial_setup=True)
                node.set_parameter_value(module._AGENT_SHOT_STORE_PARAMETER, deepcopy(store), initial_setup=True)
                # The registered next-turn callback can run before Source
                # discovery; it must not undo the restored presentation.
                node._hmb_post_hydration_state_restore()
            node.reorder_elements.assert_not_called()
            node._refresh_agent_shot_route.assert_not_called()
            self.assertFalse(any(name in native_before for name in writes))
            self.assertEqual({item.name: node.parameter_values.get(item.name) for item in body}, native_before)
            self.assertEqual(node._hmb_shot_slots, slots_before)
            collapsed_ui = deepcopy(saved); collapsed_ui["shot_editor_expanded"] = False
            node.set_parameter_value(module._AGENT_WIDGET_PARAMETER, collapsed_ui, initial_setup=True)
            self.assertFalse(node._hmb_shot_editor_expanded)
            self.assertTrue(all(item.ui_options["hide"] for item in body))
            store["editor_expanded"] = False
            node.set_parameter_value(module._AGENT_SHOT_STORE_PARAMETER, store, initial_setup=True)
            self.assertTrue(all(item.ui_options["hide"] for item in body))
            self.assertEqual(node._hmb_shot_catalog_snapshot, {})
            self.assertEqual(node._hmb_agent_shot_subscriptions(), [])
            # An empty or cross-channel saved catalog is no presentation proof.
            for invalid in ({}, {**saved["shot_catalog"], "channel_uuid": "foreign"}):
                node.root_ui_element.children[:] = [header, *rows, *body]
                value = deepcopy(saved); value["shot_catalog"] = invalid
                node.set_parameter_value(module._AGENT_WIDGET_PARAMETER, value, initial_setup=True)
                self.assertEqual(node.root_ui_element.children, [header, *rows, *body])
                self.assertEqual(node._hmb_agent_shot_subscriptions(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
