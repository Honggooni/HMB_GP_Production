"""Page changes read prepared public Prompt views, never execution documents.

Runs with synthetic native controls, no provider or paid render. The existing
native switch and worker host regressions cover the installed SDK boundary.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from HMB_Agent_Catalog_Presentation_Regression import surface, module


def view_fixture():
    node, source, body, rows, writes, publications, setter = surface()
    source._hmb_shot_manager_enabled = lambda: True
    source._hmb_prompt_shot_document = Mock(side_effect=AssertionError("Page switch compiled execution document"))
    source._hmb_prompt_shot_view = Mock(side_effect=lambda **identity: {
        "subscription": identity, "revision": 1,
        "visible_prompt": f"Prepared {identity['shot_uuid']} literal {{braces}} OFF 0"})
    node._hmb_manager_prompt_owner = lambda **_: source
    return node, source, body, rows, writes, publications, setter


class AgentPageViewCache(unittest.TestCase):
    def test_five_pages_forward_reverse_repeat_never_build_execution_document(self):
        node, source, _, _, writes, _, setter = view_fixture()
        node._hmb_prompt_display_owner = lambda: source
        node._hmb_manager_prompt_owner = Mock(side_effect=AssertionError("Page switch scanned the flow"))
        original_slots = copy.deepcopy(node._hmb_shot_slots)
        original_results = copy.deepcopy(node._hmb_shot_results)
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            for number in [1, 2, 3, 4, 5, 4, 3, 2, 1] * 5:
                node.parameter_values[module._AGENT_WIDGET_PARAMETER]["shot"].update(
                    shot_uuid=f"shot-{number}", number=number)
                node._hmb_prompt_preview_active = False
                node._refresh_routed_prompt_preview()
                self.assertEqual(node.parameter_values["prompt"],
                    f"Prepared shot-{number} literal {{braces}} OFF 0")
        self.assertEqual(source._hmb_prompt_shot_view.call_count, 45)
        node._hmb_manager_prompt_owner.assert_not_called()
        source._hmb_prompt_shot_document.assert_not_called()
        self.assertEqual(node._hmb_shot_slots, original_slots)
        self.assertEqual(node._hmb_shot_results, original_results)
        self.assertTrue(all(name == "prompt" for name in writes))
        self.assertFalse(node._hmb_shot_workers)

    def test_cache_miss_retains_exact_saved_slot_then_recovers_without_fallback(self):
        node, source, _, _, writes, _, setter = view_fixture()
        saved = copy.deepcopy(node.parameter_values["prompt"])
        source._hmb_prompt_shot_view.return_value = None
        source._hmb_prompt_shot_view.side_effect = None
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            for _ in range(25):
                node._refresh_routed_prompt_preview()
            self.assertEqual(node.parameter_values["prompt"], saved)
            self.assertEqual(writes, [])
            self.assertTrue(node._hmb_prompt_preview_hydration_pending)
            source._hmb_prompt_shot_view.return_value = {
                "subscription": {"channel_uuid": "channel", "shot_uuid": "shot-1"},
                "visible_prompt": "New prepared source", "revision": 2}
            node._refresh_routed_prompt_preview()
        self.assertEqual(node.parameter_values["prompt"], "New prepared source")
        self.assertFalse(node._hmb_prompt_preview_hydration_pending)
        source._hmb_prompt_shot_document.assert_not_called()
        self.assertEqual(writes, ["prompt"])

    def test_foreign_or_missing_view_identity_cannot_change_selected_prompt(self):
        node, source, _, _, writes, _, setter = view_fixture()
        saved = node.parameter_values["prompt"]
        source._hmb_prompt_shot_view.side_effect = None
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            for identity in ({}, {"channel_uuid": "foreign", "shot_uuid": "shot-1"},
                    {"channel_uuid": "channel", "shot_uuid": "shot-2"}):
                source._hmb_prompt_shot_view.return_value = {
                    "subscription": identity, "visible_prompt": "Foreign visible page"}
                node._refresh_routed_prompt_preview()
                self.assertEqual(node.parameter_values["prompt"], saved)
        self.assertEqual(writes, [])
        source._hmb_prompt_shot_document.assert_not_called()

    def test_display_cache_failure_keeps_saved_form_and_is_never_an_execution_fallback(self):
        node, source, _, _, writes, _, setter = view_fixture()
        saved = node.parameter_values["prompt"]
        source._hmb_prompt_shot_view.side_effect = RuntimeError("Synthetic cache preparation still pending")
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node._refresh_routed_prompt_preview()
        self.assertEqual(node.parameter_values["prompt"], saved)
        self.assertTrue(node._hmb_prompt_preview_hydration_pending)
        self.assertEqual(writes, [])
        source._hmb_prompt_shot_document.assert_not_called()

    def test_hydrate_uses_same_prepared_view_and_requires_exact_connected_owner(self):
        node, source, _, _, _, _, setter = view_fixture()
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            self.assertTrue(node._hmb_hydrate_shot_prompt_from_source(source))
            self.assertEqual(node.parameter_values[module._AGENT_SHOT_PROMPT_INPUT_PARAMETER],
                "Prepared shot-1 literal {braces} OFF 0")
            self.assertEqual(node.parameter_values["prompt"], "Prepared shot-1 literal {braces} OFF 0")
            node._hmb_manager_prompt_owner = lambda **_: object()
            self.assertFalse(node._hmb_hydrate_shot_prompt_from_source(source))
        source._hmb_prompt_shot_document.assert_not_called()

    def test_hydrate_cold_cache_preserves_saved_text_and_does_not_build(self):
        node, source, _, _, writes, _, setter = view_fixture()
        saved = node.parameter_values["prompt"]
        source._hmb_prompt_shot_view.side_effect = None
        source._hmb_prompt_shot_view.return_value = {}
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            self.assertFalse(node._hmb_hydrate_shot_prompt_from_source(source))
        self.assertEqual(node.parameter_values["prompt"], saved)
        self.assertEqual(writes, [])
        source._hmb_prompt_shot_document.assert_not_called()

    def test_view_is_not_an_execution_authority(self):
        node, source, *_ = view_fixture()
        owner = object()
        setattr(node, module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, owner)
        value = node._hmb_prompt_manager_view(source)
        self.assertEqual(value["subscription"]["shot_uuid"], "shot-1")
        self.assertIs(getattr(node, module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE), owner)
        self.assertIsNone(getattr(node, module._FROZEN_PROMPT_SHOT_ATTRIBUTE, None))
        source._hmb_prompt_shot_document.assert_not_called()

    def test_page_only_store_is_durable_without_whole_store_ui_event(self):
        node, *_ = view_fixture()
        with node._hmb_editor_update(page_only=True):
            with node._hmb_editor_update():
                node._hmb_request_shot_store_persist()
        node._hmb_persist_shot_store.assert_called_once_with(emit_change=False)
        self.assertEqual(node._hmb_editor_page_only_depth, 0)
        node._hmb_persist_shot_store.reset_mock()
        with node._hmb_editor_update():
            node._hmb_request_shot_store_persist()
        node._hmb_persist_shot_store.assert_called_once_with()

    def test_page_only_scope_cannot_leak_to_following_run_or_edit_after_exception(self):
        node, *_ = view_fixture()
        with self.assertRaisesRegex(RuntimeError, "Synthetic page rejection"):
            with node._hmb_editor_update(page_only=True):
                raise RuntimeError("Synthetic page rejection")
        self.assertEqual(node._hmb_editor_page_only_depth, 0)
        self.assertEqual(node._hmb_editor_update_depth, 0)
        with node._hmb_editor_update():
            node._hmb_request_shot_store_persist()
        node._hmb_persist_shot_store.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
