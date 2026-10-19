"""Saved Agent store hydration must precede the first live callback.

Uses the clean CI SDK setter's real initial_setup contract (no before/after
hooks); no after_deserialize repair, model, graph, or network is involved.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("hmb_agent_store_hydration_target", ROOT / "HMBAgentLibrary.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Agent = module.HMBAgentLibrary
STORE = module._AGENT_SHOT_STORE_PARAMETER


def saved_store():
    def slot(label):
        return {"values": {"prompt": "Authored " + label, "model": "model-" + label,
            "model_provider": "provider-" + label, "tools": [], "rulesets": []},
            "children": {}, "outputs": {"output": "Previous " + label, "logs": "", "agent": None},
            "result": {"status": "succeeded", "run_id": "saved-" + label}}
    slots = {"__hmb_only__": slot("independent"), "__hmb_default_settings__": slot("default")}
    slots.update({"channel\x1fshot-" + str(number): slot(str(number)) for number in range(1, 4)})
    return {"schema": module._AGENT_SHOT_STORE_SCHEMA, "version": 1, "manager": True,
        "editor_expanded": True, "active": "channel\x1fshot-2", "slots": slots,
        "results": {"channel\x1fshot-1": {"run_id": "preserved-result"}},
        "migration_archives": {"Legacy Agent": {"preserved": "Archived independent settings"}}}


def node_fixture():
    node = object.__new__(Agent)
    node.name = "Synthetic saved Agent"
    node.parameters = {}
    node.parameter_values = {}
    node.parameter_output_values = {}
    node._hmb_node_deleted = False
    node._hmb_shot_store_syncing = False
    node._hmb_slot_switching = False
    node._hmb_shot_slots = {}
    node._hmb_active_slot_key = "__hmb_only__"
    node._hmb_shot_results = {}
    node._hmb_agent_migration_archives = {}
    node._hmb_shot_manager_mode = True
    node._hmb_shot_editor_expanded = True
    node._hmb_shot_context = {}
    for name in (STORE, "additional_context"):
        node.add_parameter(module.Parameter(name=name, default_value={}, type="dict"))
    node._native_parameter_value = lambda name, default=None: node.parameter_values.get(name, default)
    node.after_deserialize = Mock(side_effect=AssertionError("No deserialization repair is permitted"))
    node._refresh_agent_shot_route = Mock(side_effect=AssertionError("Hydration must not route"))
    node._refresh_routed_prompt_preview = Mock(side_effect=AssertionError("Hydration must not compile"))
    return node


class AgentStoreHydrationTests(unittest.TestCase):
    def test_initial_store_restores_private_slots_and_active_without_after_hook(self):
        node = node_fixture()
        raw = saved_store()
        after = Mock(wraps=node.after_value_set)
        with patch.object(node, "after_value_set", after):
            node.set_parameter_value(STORE, copy.deepcopy(raw), initial_setup=True)
        after.assert_not_called()
        self.assertEqual(node._hmb_shot_slots, raw["slots"])
        self.assertEqual(node._hmb_active_slot_key, raw["active"])
        self.assertEqual(node._hmb_shot_results, raw["results"])
        self.assertEqual(node._hmb_agent_migration_archives, raw["migration_archives"])
        self.assertEqual(node.parameter_values[STORE], raw)
        node.after_deserialize.assert_not_called()
        self.assertIsNot(node._hmb_shot_slots, raw["slots"])

    def test_first_live_native_write_does_not_replace_five_slots_with_only(self):
        node = node_fixture()
        raw = saved_store()
        node.set_parameter_value(STORE, copy.deepcopy(raw), initial_setup=True)
        # The active native fields are loaded as normal saved properties after
        # the durable store. Its first live callback then captures that body.
        node._hmb_native_slot_snapshot = Mock(return_value=copy.deepcopy(raw["slots"][raw["active"]]))
        node.set_parameter_value("additional_context", "First live source/native callback")
        self.assertEqual(node.parameter_values[STORE], raw)
        self.assertEqual(node._hmb_shot_slots, raw["slots"])
        self.assertEqual(node._hmb_active_slot_key, raw["active"])
        node._hmb_native_slot_snapshot.assert_called_once()

    def test_presentation_persist_before_any_deserialize_repair_keeps_all_slots(self):
        node = node_fixture()
        raw = saved_store()
        node.set_parameter_value(STORE, copy.deepcopy(raw), initial_setup=True)
        for _ in range(20):
            node._hmb_persist_shot_store()
        self.assertEqual(node.parameter_values[STORE], raw)
        self.assertEqual(len(node._hmb_shot_slots), 5)

    def test_authoritative_initial_store_replaces_old_cache_for_undo(self):
        node = node_fixture()
        one = saved_store()
        node.set_parameter_value(STORE, copy.deepcopy(one), initial_setup=True)
        two = copy.deepcopy(one)
        two["active"] = "channel\x1fshot-3"
        two["slots"]["channel\x1fshot-1"]["values"]["prompt"] = "Restored undo text"
        del two["slots"]["__hmb_default_settings__"]
        node.set_parameter_value(STORE, copy.deepcopy(two), initial_setup=True)
        self.assertEqual(node._hmb_shot_slots, two["slots"])
        self.assertEqual(node._hmb_active_slot_key, two["active"])
        self.assertEqual(node.parameter_values[STORE], two)

    def test_invalid_store_does_not_replace_valid_private_cache(self):
        node = node_fixture()
        raw = saved_store()
        node.set_parameter_value(STORE, copy.deepcopy(raw), initial_setup=True)
        node.set_parameter_value(STORE, {"schema": "other", "version": 1, "slots": {}}, initial_setup=True)
        self.assertEqual(node._hmb_shot_slots, raw["slots"])
        self.assertEqual(node._hmb_active_slot_key, raw["active"])

    def test_failed_sdk_assignment_does_not_restore_unaccepted_store(self):
        node = node_fixture()
        with patch.object(module._BaseAgent, "set_parameter_value", side_effect=ValueError("SDK rejected input")):
            with self.assertRaisesRegex(ValueError, "SDK rejected input"):
                node.set_parameter_value(STORE, saved_store(), initial_setup=True)
        self.assertEqual(node._hmb_shot_slots, {})
        self.assertEqual(node._hmb_active_slot_key, "__hmb_only__")


if __name__ == "__main__":
    unittest.main(verbosity=2)
