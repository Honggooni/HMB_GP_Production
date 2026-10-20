"""Catalog presentation must not hydrate the active native Agent form."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from HMB_Agent_Multishot_Regression import forbidden, manager, module, offline_connect

Agent = module.HMBAgentLibrary


def catalog(generation, rows=None):
    rows = copy.deepcopy(rows or [{"shot_uuid": f"shot-{n}", "number": n,
        "name": f"Renamed {n}", "revision": 0} for n in range(1, 6)])
    rows.sort(key=lambda item: item["number"])
    document = {"channel_uuid": "channel", "generation": generation, "shots": rows}
    return {"schema": "hmb-shot-routing-catalog", "version": 1,
        "publisher_instance_uuid": "publisher", **document,
        "metadata_sha256": hashlib.sha256(json.dumps(document, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def surface():
    node, source = manager()
    parameters = {}
    node.get_parameter_by_name = parameters.get
    node._native_parameter_value = lambda name, default=None: node.parameter_values.get(name, default)
    # The graph-free fixture substitutes only physical edge discovery; actual
    # UUID view validation and execution-document separation remain real.
    node._hmb_prompt_display_owner = lambda: node._hmb_manager_prompt_owner(
        **{key: node._hmb_shot_channel_subscription()[key] for key in ("channel_uuid", "shot_uuid")})
    node._hmb_shot_catalog_snapshot = catalog(1)
    node._hmb_shot_editor_expanded = True
    node._hmb_native_editor_collapsed = False
    node._hmb_native_editor_visibility = {}
    node._hmb_shot_context = {}
    node._hmb_active_slot_key = node._hmb_slot_key("channel", "shot-1")
    node._hmb_available_agent_shot_catalog = lambda snapshot: copy.deepcopy(snapshot)
    node._hmb_switch_native_slot = Mock()
    shot = {"channel_uuid": "channel", **node._hmb_shot_catalog_snapshot["shots"][0]}
    value = node._hmb_widget_value(shot, node._hmb_shot_catalog_snapshot)
    node.parameter_values[module._AGENT_WIDGET_PARAMETER] = value
    height_options = {key: 64 for key in ("height", "min_height", "max_height", "widget_height",
        "default_height", "preferred_height", "initial_height")}
    header = module.Parameter(name=module._AGENT_WIDGET_PARAMETER, default_value=value, ui_options=height_options)
    body = [module.Parameter(name=name, ui_options={"hide": False})
        for name in ("prompt", "model", "model_provider", "additional_context", "output_schema", "output")]
    for name, value in (("prompt", "Authored text {literal} RGB(1, 2, 3) OFF 0"),
            ("model", "Dynamic native model"), ("model_provider", "Dynamic native provider"),
            ("additional_context", "Authored context"), ("output_schema", {"zero": 0, "off": False})):
        node.parameter_values[name] = copy.deepcopy(value)
    rows = [module.Parameter(name=module._AGENT_SHOT_ROW_PREFIX + str(n), default_value={},
        ui_options={"hide": False}) for n in range(1, 6)]
    for parameter in [header, *body, *rows]:
        parameters[parameter.name] = parameter
    node._hmb_native_editor_elements = body
    node.root_ui_element = SimpleNamespace(children=[header, rows[0], *body, *rows[1:]])
    def reorder(names):
        node.root_ui_element.children[:] = [parameters[name] for name in names]
    node.reorder_elements = Mock(side_effect=reorder)
    publications = []
    writes = []
    def native_set(self, name, value, *args, **kwargs):
        parameter = parameters.get(name)
        if parameter is None:
            self.parameter_values[name] = copy.deepcopy(value)
            return
        normalized = value if kwargs.get("initial_setup") else self.before_value_set(parameter, value)
        self.parameter_values[name] = copy.deepcopy(normalized)
        writes.append(name)
        if not kwargs.get("initial_setup"):
            self.after_value_set(parameter, normalized)
            if kwargs.get("emit_change", True):
                publications.append(name)
    return node, source, body, rows, writes, publications, native_set


class CatalogPresentationTests(unittest.TestCase):
    def setUp(self):
        self._io_guards = [patch.object(socket, "create_connection", forbidden),
            patch.object(socket.socket, "connect", offline_connect), patch.object(urllib.request, "urlopen", forbidden)]
        for guard in self._io_guards:
            guard.start()

    def tearDown(self):
        for guard in reversed(self._io_guards):
            guard.stop()

    def test_sibling_catalog_changes_publish_only_changed_rows_and_preserve_native_form(self):
        node, _, body, rows, writes, publications, setter = surface()
        node._refresh_routed_prompt_preview = Mock(side_effect=AssertionError("Sibling metadata rehydrated native Prompt"))
        original_values = {key: copy.deepcopy(value) for key, value in node.parameter_values.items()
            if not key.startswith("HMB_")}
        original_slots = copy.deepcopy(node._hmb_shot_slots)
        original_body = list(body)
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node._hmb_layout_shot_editor()
            node.reorder_elements.reset_mock()
            writes.clear(); publications.clear()
            node._hmb_reconcile_shot_routing(catalog(2))
            self.assertEqual(publications, [], "Watermark ACK republished the native form")
            self.assertFalse(node._hmb_ui_preview_required)
            renamed = copy.deepcopy(catalog(2)["shots"])
            renamed[1].update(name="Changed sibling", revision=1)
            node._hmb_reconcile_shot_routing(catalog(3, renamed))
            self.assertEqual(publications, [rows[1].name])
            publications.clear()
            renamed[1]["number"], renamed[2]["number"] = 3, 2
            node._hmb_reconcile_shot_routing(catalog(4, renamed))
            self.assertCountEqual(publications, [rows[1].name, rows[2].name])
            publications.clear()
            shortened = [row for row in renamed if row["shot_uuid"] != "shot-5"]
            node._hmb_reconcile_shot_routing(catalog(5, shortened))
            replacement = shortened + [{"shot_uuid": "new-shot-5", "number": 5,
                "name": "Renamed 5", "revision": 0}]
            node._hmb_reconcile_shot_routing(catalog(6, replacement))
            self.assertEqual(node.parameter_values[rows[4].name]["shot"]["shot_uuid"], "new-shot-5")
        node._refresh_routed_prompt_preview.assert_not_called()
        self.assertEqual({key: node.parameter_values[key] for key in original_values}, original_values)
        self.assertEqual(node._hmb_shot_slots, original_slots)
        self.assertTrue(all(a is b for a, b in zip(body, original_body)))
        self.assertIs(node.root_ui_element.children[2], body[0])
        node.reorder_elements.assert_not_called()
        self.assertNotIn(module._AGENT_WIDGET_PARAMETER, publications)
        self.assertTrue(all(name.startswith(module._AGENT_SHOT_ROW_PREFIX) for name in publications))
        self.assertEqual(node.parameter_values[module._AGENT_WIDGET_PARAMETER]["shot_catalog"], catalog(6, replacement))

    def test_selected_uuid_change_still_refreshes_preview_and_selects_own_slot(self):
        node, _, _, _, _, publications, setter = surface()
        node._refresh_routed_prompt_preview = Mock()
        next_value = node._hmb_widget_value({"channel_uuid": "channel", **catalog(1)["shots"][2]}, catalog(1))
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node.set_parameter_value(module._AGENT_WIDGET_PARAMETER, next_value)
        self.assertTrue(node._hmb_ui_preview_required)
        node._refresh_routed_prompt_preview.assert_called_once()
        node._hmb_switch_native_slot.assert_called_once_with("channel", "shot-3")
        self.assertIn(module._AGENT_WIDGET_PARAMETER, publications)

    def test_same_selected_document_ack_preserves_manual_edit_but_real_change_projects_once(self):
        node, source, _, _, writes, publications, setter = surface()
        node._hmb_prompt_preview_active = True
        node._hmb_prompt_preview_value = "Confirmed selected document"
        node._hmb_prompt_before_preview = "Original editable value"
        source._hmb_shot_manager_enabled = lambda: True
        source._hmb_prompt_shot_document = Mock(side_effect=AssertionError("Display compiled execution document"))
        source._hmb_prompt_shot_view = Mock(return_value={"visible_prompt": "Confirmed selected document",
            "subscription": {"channel_uuid": "channel", "shot_uuid": "shot-1"}})
        node._hmb_manager_prompt_owner = lambda **kwargs: source
        node.parameter_values[module._AGENT_SHOT_PROMPT_INPUT_PARAMETER] = "Other visible Prompt Shot"
        before = copy.deepcopy(node.parameter_values["prompt"])
        with patch.object(module._BaseAgent, "set_parameter_value", setter), \
                patch.object(module._BaseAgent, "after_value_set", lambda *args: None):
            node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "Other visible Prompt Shot")
            self.assertEqual(node.parameter_values["prompt"], before)
            self.assertEqual(publications, [])
            self.assertEqual(writes, [])
            source._hmb_prompt_shot_view.return_value = {"visible_prompt": "New selected document RGB(1, 2, 3) OFF 0",
                "subscription": {"channel_uuid": "channel", "shot_uuid": "shot-1"}}
            node.set_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "Other visible Prompt Shot")
        self.assertEqual(node.parameter_values["prompt"], "New selected document RGB(1, 2, 3) OFF 0")
        self.assertEqual(publications, ["prompt"])
        self.assertEqual(writes, ["prompt"])
        source._hmb_prompt_shot_view.assert_called_with(channel_uuid="channel", shot_uuid="shot-1")
        source._hmb_prompt_shot_document.assert_not_called()

    def _late_deleted_worker(self, *, raises=False):
        node, source = manager()
        key = node._hmb_slot_key("channel", "shot-1")
        original_slots = copy.deepcopy(node._hmb_shot_slots)
        node._hmb_publish_shot_failure = Mock()
        started, release = asyncio.Event(), asyncio.Event()
        text = "Late result"
        async def execute():
            started.set()
            await release.wait()
            if raises:
                raise RuntimeError("Late old-instance failure")
        execution = SimpleNamespace(_hmb_aprocess_locked=execute,
            _hmb_execution_result_snapshot=lambda: {"status": "succeeded", "run_id": "late-run",
                "output_sha256": hashlib.sha256(text.encode()).hexdigest()},
            parameter_values={}, parameter_output_values={"output": text},
            _hmb_agent_reference_observation_snapshot=lambda: {}, _hmb_shot_policy_identity={},
            _clear_hmb_runtime_policy=Mock())
        async def run():
            with patch.object(module._HMBAgentShotExecution, "_from_owner", return_value=execution):
                task = asyncio.create_task(node._hmb_run_agent_shot(channel_uuid="channel", shot_uuid="shot-1",
                    prompt_owner=source, generator=SimpleNamespace(is_cancellation_requested=False)))
                await started.wait()
                replacement, _ = manager()
                replacement.name = node.name
                replacement_before = copy.deepcopy(replacement._hmb_shot_slots)
                node._hmb_node_deleted = True
                node._hmb_lifecycle_generation += 1
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(replacement._hmb_shot_slots, replacement_before)
                self.assertFalse(replacement._hmb_shot_results)
        asyncio.run(run())
        self.assertEqual(node._hmb_shot_slots, original_slots)
        self.assertFalse(node._hmb_shot_results)
        self.assertFalse(getattr(node, "_hmb_shot_request_records", {}))
        self.assertNotIn(key, node._hmb_shot_workers)
        node._hmb_publish_shot_failure.assert_not_called()
        self.assertFalse(node._hmb_shot_execution_locks[key].locked())

    def test_late_deleted_worker_cannot_return_result_or_ticket_to_replacement(self):
        self._late_deleted_worker()

    def test_late_deleted_worker_error_cannot_publish_into_replacement(self):
        self._late_deleted_worker(raises=True)

    def test_old_removal_cannot_clear_a_current_canonical_replacement_prompt(self):
        node, _, _, _, _, _, _ = surface()
        old_source = SimpleNamespace(name="Deleted Prompt instance")
        replacement = SimpleNamespace(name="Replacement Prompt instance", _hmb_node_deleted=False)
        node._hmb_shot_context = {"channel_uuid": "channel", "shot_uuid": "shot-1"}
        before_context = copy.deepcopy(node._hmb_shot_context)
        node.set_parameter_value = Mock()
        node._set_native_prompt_preview = Mock()
        node._hmb_hydrate_shot_prompt_from_source = Mock(return_value=True)
        def verify(actual):
            self.assertIs(actual, node)
            setattr(actual, module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, replacement)
            return True
        with patch.object(module, "_is_direct_hmb_prompt_library_connection", side_effect=verify):
            node.after_incoming_connection_removed(old_source, SimpleNamespace(name="PROMPT_OUT"),
                SimpleNamespace(name=module._AGENT_SHOT_PROMPT_INPUT_PARAMETER))
        node._hmb_hydrate_shot_prompt_from_source.assert_called_once_with(replacement, "PROMPT_OUT")
        node.set_parameter_value.assert_not_called()
        node._set_native_prompt_preview.assert_not_called()
        self.assertEqual(node._hmb_shot_context, before_context)
        self.assertIs(getattr(node, module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE), replacement)

    def test_missing_or_ambiguous_replacement_still_clears_the_removed_prompt(self):
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous):
                node, _, _, _, _, _, _ = surface()
                node.set_parameter_value = Mock()
                node._set_native_prompt_preview = Mock()
                node._hmb_hydrate_shot_prompt_from_source = Mock()
                with patch.object(module, "_is_direct_hmb_prompt_library_connection",
                        **({"side_effect": RuntimeError("Ambiguous topology")} if ambiguous else {"return_value": False})):
                    node.after_incoming_connection_removed(SimpleNamespace(), SimpleNamespace(name="PROMPT_OUT"),
                        SimpleNamespace(name=module._AGENT_SHOT_PROMPT_INPUT_PARAMETER))
                node.set_parameter_value.assert_called_once_with(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, "")
                node._set_native_prompt_preview.assert_called_once_with("", enabled=False)
                node._hmb_hydrate_shot_prompt_from_source.assert_not_called()
                self.assertIsNone(getattr(node, module._VERIFIED_PROMPT_SOURCE_ATTRIBUTE))

    def test_blank_new_manager_discovers_existing_catalog_without_legacy_autoclaim(self):
        node, _ = manager()
        node._hmb_initial_shot_autoclaim_pending = False
        node._refresh_routed_prompt_preview = Mock()
        node._hmb_post_registration_shot_discovery()
        node._refresh_agent_shot_route.assert_called_once_with()
        node._refresh_routed_prompt_preview.assert_called_once_with()
        self.assertFalse(node._hmb_initial_shot_autoclaim_pending)
        # Discovery reuses the verified same-flow router. It never guesses a
        # Shot or copies native settings from the deleted node itself.
        self.assertEqual(node.parameter_values["prompt"], "Only authored text")
        for deleted, manager_enabled, pending, expected in (
                (True, True, False, False), (False, False, False, False),
                (False, False, True, True)):
            with self.subTest(deleted=deleted, manager=manager_enabled, pending=pending):
                node._hmb_node_deleted = deleted
                node._hmb_shot_manager_mode = manager_enabled
                node._hmb_initial_shot_autoclaim_pending = pending
                node._refresh_agent_shot_route.reset_mock()
                node._refresh_routed_prompt_preview.reset_mock()
                node._hmb_post_registration_shot_discovery()
                self.assertEqual(node._refresh_agent_shot_route.called, expected)
                self.assertEqual(node._refresh_routed_prompt_preview.called, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
