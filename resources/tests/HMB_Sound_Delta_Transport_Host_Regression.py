from __future__ import annotations

"""Actual retained SDK: UI deltas cannot become saved or routed sound data.

Uses disposable engine scopes and synthetic audio only; no running desktop,
model/provider request, real project scan or user workflow is touched.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock

import HMB_Sound_Library_Regression as fixture

target = fixture.target


class SoundDeltaTransport(fixture.SoundNodeRegression):
    def setUp(self):
        super().setUp()
        # Unlike the shared authoring fixture, exercise the real SDK publisher.
        del self.node.publish_update_to_parameter

    def publish(self, **kwargs):
        with mock.patch.object(self.engine.event_manager, "put_event") as events:
            self.node._publish(notify=False, **kwargs)
        projected = []
        for call in events.call_args_list:
            payload = call.args[0].wrapped_event.payload
            if type(payload).__name__ == "ParameterValueUpdateEvent" and payload.parameter_name == target.UI:
                projected.append(copy.deepcopy(payload.value))
            elif type(payload).__name__ == "AlterElementEvent" and payload.element_details.get("parameter_name") == target.UI:
                projected.append(copy.deepcopy(payload.element_details["value"]))
        self.assertIn(len(projected), (1, 2), "Native publish must emit its value update")
        self._last_display_count = len(projected)
        self.assertTrue(all(value == projected[0] for value in projected))
        return projected[0]

    def retained(self):
        value = self.node.get_parameter_value(target.UI)
        output = self.node.parameter_output_values[target.UI]
        for snapshot in (value, output):
            self.assertEqual(snapshot.get("schema"), "hmb-sound-library-ui")
            self.assertNotIn("__hmb_sound_command", snapshot)
            self.assertNotIn("__hmb_sound_transport", snapshot)
            self.assertEqual(snapshot["assets"], value["assets"])
            self.assertEqual(snapshot["tracks"], value["tracks"])
        return copy.deepcopy(value)

    def native_command(self, command):
        result = self.engine.handle_request(fixture.SetParameterValueRequest(
            node_name=self.node.name, parameter_name=target.UI,
            value={"__hmb_sound_command": command}))
        self.assertTrue(result.succeeded(), "SDK property command must complete")
        return self.retained()

    def test_wire_only_delta_and_complete_downstream_outputs(self):
        first = self.publish(full=True)
        self.assertEqual(first["__hmb_sound_transport"]["mode"], "full")
        self.node._state_sound["status"] = "fixture status update"
        delta = self.publish()
        self.assertEqual(self._last_display_count, 2, "A changed value exercises both native display-event paths")
        self.assertEqual(delta["schema"], "hmb-sound-ui-patch")
        self.assertEqual(delta["values"], {"status": "fixture status update"})
        self.assertNotIn("assets", delta)
        self.assertEqual(delta["__hmb_sound_transport"]["base_sequence"], first["__hmb_sound_transport"]["sequence"])
        retained = self.retained()
        self.assertEqual(len(retained["assets"]), 1)
        for name in target.OUTPUTS:
            output = self.node.parameter_output_values[name]
            self.assertEqual(output, self.node._snapshot())
            self.assertNotIn("preview_url", output["tracks"][0])
        command = {"id": "explicit-copy", "action": "duplicate", "instance_id": self.track["instance_id"]}
        self.native_command(command)
        self.assertEqual(len(self.node._state_sound["tracks"]), 2)
        self.assertNotEqual(*[row["instance_id"] for row in self.node._state_sound["tracks"]])

    def test_duplicate_retry_noop_and_malformed_envelope_never_saved(self):
        self.publish(full=True)
        for command in (
            {"id": "repeat-copy", "action": "duplicate", "instance_id": self.track["instance_id"]},
            {"id": "repeat-cancel", "action": "cancel"},
            {"id": "repeat-noop-add", "action": "add", "relative_path": "Dialogue/voice.wav"},
            {"id": "repeat-invalid", "action": "unknown-fixture-action"},
        ):
            first = self.native_command(command)
            repeat = self.native_command(command)
            self.assertEqual(first["tracks"], repeat["tracks"])
            self.assertEqual(first["revision"], repeat["revision"])
        for malformed in (None, [], "{broken", {"id": 8}, {"id": ""}):
            self.native_command(malformed)
        self.assertEqual(len(self.node._state_sound["tracks"]), 2)
        self.assertEqual(self.node._state_sound["error_code"], "SOUND_COMMAND_INVALID")
        result = self.engine.handle_request(fixture.SerializeFlowToCommandsRequest(flow_name=self.flow.name))
        self.assertTrue(result.succeeded(), "Serialize must retain a usable sound state")
        serialized = result.serialized_flow_commands
        for value in serialized.unique_parameter_uuid_to_values.values():
            if isinstance(value, dict):
                self.assertNotIn("__hmb_sound_command", value)
                self.assertNotIn("__hmb_sound_transport", value)
                self.assertNotEqual(value.get("schema"), "hmb-sound-ui-patch")

    def test_readonly_recovery_preserves_revision_ack_busy_and_outputs(self):
        from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
        from griptape_nodes.retained_mode.runtime.binding import NO_WORKFLOW

        self.publish(full=True)
        self.node._state_sound.update(busy=True, ack_command_id="authored-command", status="Preparing fixture")
        published = self.publish()
        before = copy.deepcopy(self.node._state_sound)
        outputs = {name: copy.deepcopy(self.node.parameter_output_values[name]) for name in target.OUTPUTS}
        state_before = self.retained()
        request = PayloadRegistry.get_type("HMBGetSoundUISnapshotRequest")
        with mock.patch.object(target, "set_output", side_effect=AssertionError("UI recovery must not edit outputs")), \
             mock.patch.object(target, "scan_sound_project", side_effect=AssertionError("UI recovery must not scan media")), \
             mock.patch.object(self.node, "_publish", side_effect=AssertionError("UI recovery must not publish")), \
             mock.patch.object(self.engine.event_manager, "put_event") as events:
            workflow = self.engine.current_workflow()
            result = workflow.handle_request(request(node_name=self.node.name, expected_stream_id=self.node._ui_stream,
                broadcast_result=False))
            scope = {"workflow_name": self.engine.workflow_registry.get(workflow.workflow_id).name,
                     "flow_name": self.flow.name, "expected_stream_id": self.node._ui_stream}

            def from_editor(**changes):
                with self.engine.bind_workflow(NO_WORKFLOW):
                    return self.engine.event_manager.handle_request(
                        request(node_name=self.node.name, broadcast_result=False, **(scope | changes)),
                    ).get_result()

            recovered = from_editor()
            self.assertTrue(recovered.succeeded(), recovered.result_details)
            self.assertFalse(recovered.altered_workflow_state)
            self.assertEqual(recovered.snapshot, result.snapshot)
            for changes in ({"flow_name": "other-flow"}, {"workflow_name": "other-workflow"},
                            {"expected_stream_id": "retired-stream"}, {"workflow_name": "", "flow_name": ""}):
                with self.subTest(changes=changes):
                    pending = from_editor(**changes)
                    self.assertTrue(pending.succeeded(), pending.result_details)
                    self.assertFalse(pending.altered_workflow_state)
                    self.assertEqual(pending.snapshot, {})
        events.assert_not_called()
        self.assertTrue(result.succeeded(), result.result_details)
        self.assertFalse(result.altered_workflow_state)
        full = result.snapshot
        metadata = full.pop("__hmb_sound_transport")
        self.assertEqual(metadata, {key: value for key, value in {**published["__hmb_sound_transport"], "mode": "full"}.items()
                                   if key != "base_sequence"})
        self.assertEqual(full, state_before)
        self.assertEqual(self.node._state_sound, before)
        self.assertEqual(outputs, {name: self.node.parameter_output_values[name] for name in target.OUTPUTS})
        self.assertEqual(self.retained(), state_before)

    def test_cache_invalidates_inplace_asset_change_and_endpoint_change(self):
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        manager = mock.Mock(static_server_base_url="http://127.0.0.1:1111")
        with mock.patch.object(GriptapeNodes, "StaticFilesManager", return_value=manager) as resolve:
            first = self.publish(full=True)
            cached_assets = self.node._ui_catalog_cache[2]
            self.publish()
            self.assertIs(self.node._ui_catalog_cache[2], cached_assets)
            self.assertEqual(resolve.call_count, 2, "Resolve the manager once per publish, not once per asset")
            self.node._state_sound["assets"][0]["mtime_ns"] += 1
            changed = self.publish()
            self.assertEqual(changed["__hmb_sound_transport"]["mode"], "full")
            self.assertNotEqual(first["__hmb_sound_transport"]["catalog_key"], changed["__hmb_sound_transport"]["catalog_key"])
            manager.static_server_base_url = "http://127.0.0.1:2222"
            endpoint = self.publish()
            self.assertEqual(endpoint["__hmb_sound_transport"]["mode"], "full")
            self.assertTrue(endpoint["assets"][0]["preview_url"].startswith(manager.static_server_base_url))

    def test_concurrent_read_cannot_receive_transient_projection(self):
        self.publish(full=True)
        full = self.retained()
        sentinel = {"schema": "hmb-sound-ui-patch"}
        token = self.node._ui_projection.set((full, sentinel))
        seen = []
        try:
            self.assertIs(self.node.get_display_value_for_output(target.UI, full), sentinel)
            thread = threading.Thread(target=lambda: seen.append(self.node.get_display_value_for_output(target.UI, full)))
            thread.start(); thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(seen, [full])
        finally:
            self.node._ui_projection.reset(token)
        self.assertEqual(self.node.get_display_value_for_output(target.UI, full), full)

    def test_native_serialization_reopens_full_in_fresh_engine_process(self):
        self.publish(full=True)
        self.native_command({"id": "save-copy", "action": "duplicate", "instance_id": self.track["instance_id"]})
        self.native_command({"id": "save-edit", "action": "edit", "instance_id": self.track["instance_id"],
                             "changes": {"transcript": "authored fixture words", "gain_db": -3, "enabled": False}})
        result = self.engine.handle_request(fixture.SerializeFlowToCommandsRequest(flow_name=self.flow.name))
        self.assertTrue(result.succeeded(), "Actual SDK serialization required")
        serialized = result.serialized_flow_commands
        values = serialized.unique_parameter_uuid_to_values
        saved = {}
        for commands in serialized.set_parameter_value_commands.values():
            for indirect in commands:
                request = indirect.set_parameter_value_command
                if request.parameter_name == target.UI:
                    saved["output" if request.is_output else "property"] = values[indirect.unique_value_uuid]
        self.assertEqual(saved["property"], saved["output"])
        path = self.root / "serialized_sound_fixture.json"
        path.write_text(json.dumps(saved), encoding="utf-8")
        process = subprocess.run([sys.executable, __file__, "--restore", str(path)], text=True,
                                 capture_output=True, timeout=45)
        self.assertEqual(process.returncode, 0, "Fresh SDK process failed: " + process.stderr[-1500:])
        self.assertIn("fresh_sdk_restore_pass", process.stdout)


def restore(path):
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

    saved = json.loads(Path(path).read_text("utf-8"))
    case = fixture.SoundNodeRegression("runTest")
    try:
        case.setUp()
        for output in (False, True):
            result = case.engine.handle_request(fixture.SetParameterValueRequest(
                node_name=case.node.name, parameter_name=target.UI, initial_setup=True,
                is_output=output, value=saved["output" if output else "property"]))
            assert result.succeeded(), "Fresh SDK hydration failed"
        assert case.node._state_sound["tracks"] == fixture.helper.normalize_sound_snapshot({
            "schema": fixture.helper.SCHEMA, "version": 1, **{key: saved["property"][key]
            for key in ("project_id", "project_root", "project_uid", "channel_uuid", "revision", "tracks")}})["tracks"]
        assert len(case.node._state_sound["assets"]) == len(saved["property"]["assets"])
        assert "__hmb_sound_command" not in case.node.get_parameter_value(target.UI)
        assert "__hmb_sound_transport" not in case.node.get_parameter_value(target.UI)
        request = PayloadRegistry.get_type("HMBGetSoundUISnapshotRequest")
        result = case.engine.current_workflow().handle_request(request(node_name=case.node.name, broadcast_result=False))
        assert result.succeeded() and result.altered_workflow_state is False, result.result_details
        assert result.snapshot["__hmb_sound_transport"]["sequence"] == 0
        assert result.snapshot["tracks"][0]["transcript"] == "authored fixture words"
        assert result.snapshot["tracks"][0]["gain_db"] == -3 and result.snapshot["tracks"][0]["enabled"] is False
        assert case.node._ui_sequence == 0 and case.node._ui_previous is None and case.node._ui_catalog_cache is None
        print("fresh_sdk_restore_pass")
    finally:
        case.doCleanups()


def load_tests(loader, _standard, _pattern):
    return unittest.TestSuite(SoundDeltaTransport(name) for name in SoundDeltaTransport.__dict__ if name.startswith("test_"))


if __name__ == "__main__":
    if not fixture.NATIVE:
        raise SystemExit("Installed retained SDK is required; not a passing skip")
    if len(sys.argv) == 3 and sys.argv[1] == "--restore":
        restore(sys.argv[2])
    else:
        unittest.main(verbosity=2)
