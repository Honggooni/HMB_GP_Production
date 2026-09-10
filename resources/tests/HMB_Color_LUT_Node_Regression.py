from __future__ import annotations

"""Deterministic host-independent tests for shot/state/export lifecycle races."""

import copy
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBColorLUTLibrary as target
import _hmb_shot_routing as routing


class ControlledThread:
    pending: list["ControlledThread"] = []

    def __init__(self, target=None, args=(), kwargs=None, **_unused):
        self.target, self.args, self.kwargs = target, args, kwargs or {}
        self.running = False

    def start(self):
        self.running = True
        self.pending.append(self)

    def is_alive(self):
        return self.running

    def join(self, timeout=None):
        return None

    def run(self):
        if self in self.pending:
            self.pending.remove(self)
        try:
            self.target(*self.args, **self.kwargs)
        finally:
            self.running = False


SHOT_A = dict(channel_uuid="channel-1", shot_uuid="shot-a", number=1, name="Shot A")
SHOT_B = dict(channel_uuid="channel-1", shot_uuid="shot-b", number=2, name="Shot B")


class ColorLUTNodeRegression(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb_lut_node_")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        ControlledThread.pending = []
        self.patches = [
            mock.patch.object(target, "_profiles_path", return_value=self.root / "profiles.json"),
            mock.patch.object(target, "_workflow_data_directory", return_value=self.root / "workflow" / "data"),
            mock.patch.object(target, "_media_url", side_effect=lambda p: "http://local.test/" + Path(p).name),
            mock.patch.object(target, "probe_source", side_effect=self.probe),
            mock.patch.object(target, "threading", types.SimpleNamespace(RLock=threading.RLock, Event=threading.Event, Thread=ControlledThread)),
            mock.patch.object(target.HMBColorLUTLibrary, "_reconcile"),
            mock.patch.object(routing, "schedule_post_registration_reconcile"),
            mock.patch.object(routing, "prepare_node_deletion"),
            mock.patch.object(routing, "release_node_lifecycle"),
            mock.patch.object(routing, "schedule_post_deletion_reconcile"),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.node = target.HMBColorLUTLibrary(name="Color LUT test")
        self.node.publish_update_to_parameter = mock.Mock()

    def media(self, name):
        path = self.root / name
        if not path.exists():
            path.write_bytes(b"test source; media decode is mocked")
        return str(path)

    def probe(self, path):
        media = Path(path)
        if not media.is_file():
            raise ValueError("Missing source")
        return dict(path=str(media), width=96, height=64, duration=.5, frame_rate=12, pixel_format="yuv420p")

    def drain(self):
        while ControlledThread.pending:
            ControlledThread.pending[0].run()

    def apply(self, **changes):
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state.update(changes)
        state["revision"] = self.node._hmb_color_lut_state["revision"] + 1
        self.node._apply_ui(state)

    def select(self, shot=SHOT_A):
        self.apply(shot=copy.deepcopy(shot))

    def source(self, name="original.mp4", generation="g1", shot=SHOT_A):
        return dict(path=self.media(name), completed=True, generation_id=generation, result_revision=generation,
                    shot_uuid=shot["shot_uuid"], channel_uuid=shot["channel_uuid"])

    def load(self, **changes):
        self.node._queue_source(self.source(**changes))
        self.drain()

    def successful_export(self, source, destination, settings, **kwargs):
        destination = Path(destination)
        if destination.exists():
            raise ValueError("Output already exists; not overwritten")
        if kwargs.get("cancel_event") is not None and kwargs["cancel_event"].is_set():
            raise ValueError("Cancelled")
        destination.write_bytes(b"graded result")
        return dict(path=str(destination), source_path=source, settings=copy.deepcopy(settings))

    def export(self, request_id="export-1", authored=None):
        command = {"id": request_id, "action": "export"}
        if authored is not None:
            command["state"] = authored
        self.node._command(command)
        self.drain()

    def test_source_workers_cannot_hydrate_wrong_shot_or_older_generation(self):
        self.select()
        self.node._queue_source(self.source(generation="g1"))
        started = []
        def newer_source_arrives_during_probe(path):
            started.append(path)
            if len(started) == 1:
                self.node._queue_source(self.source(name="second.mp4", generation="g2"))
                # The running source probe coalesces the latest snapshot without
                # starting one heavyweight FFmpeg probe per incoming event.
                self.assertEqual(ControlledThread.pending, [])
            return self.probe(path)
        with mock.patch.object(target, "probe_source", side_effect=newer_source_arrives_during_probe):
            self.drain()
        self.assertEqual(len(started), 2)
        self.assertEqual(self.node._hmb_color_lut_state["source"]["generation_id"], "g2")
        self.node._queue_source(self.source(name="wrong.mp4", shot=SHOT_B))
        self.assertEqual(ControlledThread.pending, [])
        self.assertEqual(self.node._hmb_color_lut_state["source"]["generation_id"], "g2")

    def test_first_compact_widget_edit_keeps_backend_source_provenance(self):
        self.select()
        self.load()
        self.node._hydrated = False
        compact = copy.deepcopy(self.node._hmb_color_lut_state)
        compact.pop("shot_states")
        compact["source"].pop("completed", None)
        compact["source"].pop("generation_id", None)
        compact["settings"]["enabled"] = True
        compact["settings"]["contrast"] = 2
        compact["revision"] += 1
        self.node._apply_ui(compact)
        self.assertTrue(self.node._hmb_color_lut_state["source"]["completed"])
        self.assertEqual(self.node._hmb_color_lut_state["settings"]["contrast"], 2)
        self.assertEqual(self.node._hmb_color_lut_state["source"]["fps"], 12)

    def test_switch_clears_old_shot_output_and_restores_own_result(self):
        self.select()
        self.load()
        with mock.patch.object(target, "export_video", side_effect=self.successful_export):
            self.export()
        first = copy.deepcopy(self.node._hmb_color_lut_state["result"])
        first_url = self.node.parameter_output_values["video_url"]
        self.select(SHOT_B)
        self.assertEqual(self.node.parameter_output_values.get("video_url", ""), "")
        self.assertFalse(self.node._hmb_color_lut_state["result"])
        self.select(SHOT_A)
        self.load()
        self.assertEqual(self.node._hmb_color_lut_state["result"]["path"], first["path"])
        self.assertEqual(self.node.parameter_output_values.get("video_url", ""), first_url)

    def test_same_shot_replacement_does_not_publish_older_source_export(self):
        self.select()
        self.load()
        old_source = self.node._hmb_color_lut_state["source"]["path"]
        def replacement_during_export(source, destination, settings, **kwargs):
            self.node._queue_source(self.source(name="replacement.mp4", generation="g2"))
            # Complete the new-source loader while the old export is still active.
            ControlledThread.pending[-1].run()
            return self.successful_export(source, destination, settings, **kwargs)
        with mock.patch.object(target, "export_video", side_effect=replacement_during_export):
            self.export()
        self.assertEqual(self.node._hmb_color_lut_state["source"]["generation_id"], "g2")
        self.assertNotEqual(self.node._hmb_color_lut_state["result"].get("source_path"), old_source)
        self.assertEqual(self.node.parameter_output_values.get("video_url", ""), "")

    def test_new_source_invalidates_existing_result_and_url(self):
        self.select()
        self.load()
        with mock.patch.object(target, "export_video", side_effect=self.successful_export):
            self.export()
        self.node._queue_source(self.source(name="replacement.mp4", generation="g2"))
        self.assertFalse(self.node._hmb_color_lut_state["result"])
        self.assertEqual(self.node.parameter_output_values.get("video_url", ""), "")
        self.drain()

    def test_active_shot_result_and_settings_survive_hydration(self):
        self.select()
        self.load()
        self.apply(settings={"enabled": True, "temperature": 2, "shadows": -1})
        with mock.patch.object(target, "export_video", side_effect=self.successful_export):
            self.export()
        saved = copy.deepcopy(self.node._hmb_color_lut_state)
        reloaded = target.HMBColorLUTLibrary(name="Reloaded LUT")
        reloaded._apply_ui(saved)
        reloaded._queue_source(saved["source"])
        self.drain()
        self.assertEqual(reloaded._hmb_color_lut_state["settings"], saved["settings"])
        self.assertEqual(reloaded._hmb_color_lut_state["result"].get("path"), saved["result"]["path"])
        self.assertEqual(reloaded.parameter_output_values.get("video_url", ""), saved["result"]["url"])

    def test_command_captures_unflushed_grade_and_persists_it(self):
        self.select()
        self.load()
        authored = copy.deepcopy(self.node._hmb_color_lut_state)
        authored["settings"] = {"enabled": True, "exposure": 2, "contrast": -1}
        # A UI-supplied source must not redirect the captured original source.
        authored["source"] = {"path": self.media("forged.mp4")}
        expected_source = self.node._hmb_color_lut_state["source"]["path"]
        with mock.patch.object(target, "export_video", side_effect=self.successful_export) as encode:
            self.export(authored=authored)
        self.assertEqual(encode.call_args.args[0], expected_source)
        self.assertEqual(encode.call_args.args[2]["exposure"], 2)
        self.assertEqual(self.node._hmb_color_lut_state["settings"]["exposure"], 2)
        key = target._selection_key(self.node._hmb_color_lut_state)
        self.assertEqual(self.node._hmb_color_lut_state["shot_states"][key]["settings"]["exposure"], 2)

    def test_profile_save_is_persistent_and_per_project(self):
        self.node._hmb_follow_image_asset_project({"id": "project-1", "name": "Actual Asset Project"})
        authored = copy.deepcopy(self.node._hmb_color_lut_state)
        authored["settings"] = {"enabled": True, "temperature": 3}
        authored["preset_name"] = "Film A"
        self.node._command({"id": "save-1", "action": "save_profile", "state": authored})
        profiles = target._read_profiles()
        self.assertEqual(profiles[0]["name"], "Film A")
        self.assertEqual(profiles[0]["settings"]["temperature"], 3)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(self.node._hmb_color_lut_state["settings"]["temperature"], 3)
        self.node._hmb_follow_image_asset_project({"id": "project-2", "name": "Other Asset Project"})
        self.assertEqual(self.node._hmb_color_lut_state["settings"], target.default_settings())
        self.node._hmb_follow_image_asset_project({"id": "project-1", "name": "Actual Asset Project"})
        self.assertEqual(self.node._hmb_color_lut_state["settings"]["temperature"], 3)

    def test_fine_precision_survives_presets_shots_reload_and_export(self):
        self.select()
        self.load()
        settings = {**target.default_settings(), "enabled":True, "exposure":.25, "temperature":-.75,
                    "contrast":1.25, "saturation":-1.75, "shadows":2.25, "highlights":-2.75}
        authored = {**copy.deepcopy(self.node._hmb_color_lut_state), "settings":settings, "preset_name":"Fine quarter"}
        self.node._command({"id":"fine-preset", "action":"save_profile", "state":authored})
        self.assertEqual(target._read_profiles()[0]["settings"], settings)
        self.select(SHOT_B)
        self.select(SHOT_A)
        self.assertEqual(self.node._hmb_color_lut_state["settings"], settings)
        saved = json.loads(json.dumps(self.node._hmb_color_lut_state))
        restored = target.HMBColorLUTLibrary(name="Fine restored")
        restored._apply_ui(saved)
        self.assertEqual(restored._hmb_color_lut_state["settings"], settings)
        self.load()
        with mock.patch.object(target, "export_video", side_effect=self.successful_export) as encoder:
            self.export(request_id="fine-export", authored=authored)
        self.assertEqual(encoder.call_args.args[2], settings)
        result = self.node._hmb_color_lut_state["result"]
        archive = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(archive["settings"], settings)
        cube = Path(result["lut_path"]).read_text(encoding="utf-8")
        cube_settings = json.loads(next(line.removeprefix("# Settings: ") for line in cube.splitlines() if line.startswith("# Settings: ")))
        self.assertEqual(cube_settings, settings)

    def test_export_automatically_archives_cube_and_metadata_in_workflow_data(self):
        self.node._hmb_follow_image_asset_project({"id": "asset/project", "name": "Show A", "root": "D:/Show A"})
        self.select()
        self.load()
        authored = copy.deepcopy(self.node._hmb_color_lut_state)
        authored["preset_name"] = "Morning"
        authored["settings"] = {"enabled": True, "exposure": 2}
        with mock.patch.object(target, "export_video", side_effect=self.successful_export):
            self.export(authored=authored)
        result = self.node._hmb_color_lut_state["result"]
        self.assertEqual(Path(result["lut_path"]).parent, self.root / "workflow" / "data")
        self.assertTrue(Path(result["lut_path"]).is_file())
        record = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(record["project_id"], "asset/project")
        self.assertEqual(record["preset_name"], "Morning")
        self.assertEqual(record["shot"], SHOT_A)
        self.assertEqual(record["settings"]["exposure"], 2)
        self.assertEqual(record["source_path"], self.node._hmb_color_lut_state["source"]["path"])
        self.assertEqual(len(list((self.root / "workflow" / "data").iterdir())), 2)

    def test_project_is_authoritative_and_allows_multiple_personal_presets(self):
        self.node._hmb_follow_image_asset_project({"id": "show-a", "name": "Show A"})
        self.apply(project_id="spoofed")
        self.assertEqual(self.node._hmb_color_lut_state["project_id"], "show-a")
        for i, name in enumerate(("Morning", "Night")):
            authored = {**copy.deepcopy(self.node._hmb_color_lut_state), "preset_name": name}
            authored["settings"]["exposure"] = i
            self.node._command({"id": str(i), "action": "save_profile", "state": authored})
        self.assertEqual([p["name"] for p in target._read_profiles()], ["Morning", "Night"])

    def test_duplicate_commands_do_not_run_upstream_or_encode_twice(self):
        self.select()
        generator = types.SimpleNamespace(_hmb_generated_video_source_snapshot=mock.Mock(return_value=self.source()),
                                          process=mock.Mock(side_effect=AssertionError("Upstream execution forbidden")))
        self.assertTrue(self.node._hmb_hydrate_color_lut_from_source(generator))
        self.drain()
        with mock.patch.object(target, "export_video", side_effect=self.successful_export) as encode:
            command = {"id": "one-export", "action": "export"}
            self.node._command(command)
            self.node._command(command)
            self.drain()
            self.node._command(command)
        generator.process.assert_not_called()
        self.assertEqual(encode.call_count, 1)

    def test_collision_is_reported_without_replacing_existing_file(self):
        self.select()
        self.load()
        output = Path(self.media("existing.mp4"))
        before = output.read_bytes()
        self.apply(output={"codec": "hevc10", "manual_output_enabled": True, "path": str(output)})
        with mock.patch.object(target, "export_video", side_effect=self.successful_export):
            self.export()
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "error")
        self.assertFalse(self.node._hmb_color_lut_state["result"])

    def test_node_deletion_invalidates_queued_source_and_export(self):
        self.select()
        self.node._queue_source(self.source())
        self.node.after_node_deleted()
        self.node.after_node_deleted()
        self.drain()
        self.assertFalse(self.node._hmb_color_lut_state["source"])
        self.assertTrue(self.node._cancel.is_set())
        self.node._command({"id": "deleted", "action": "export"})
        self.assertEqual(ControlledThread.pending, [])
        routing.release_node_lifecycle.assert_called_once()

    def test_cancelled_export_never_publishes_result(self):
        self.select()
        self.load()
        self.node._command({"id": "pending", "action": "export"})
        self.node._command({"id": "cancel", "action": "cancel"})
        with mock.patch.object(target, "export_video", side_effect=self.successful_export):
            self.drain()
        self.assertFalse(self.node._hmb_color_lut_state["result"])
        self.assertEqual(self.node.parameter_output_values.get("video_url", ""), "")
        self.assertIn(self.node._hmb_color_lut_state["status"]["phase"], {"cancelled", "idle"})

    def test_malformed_ui_and_commands_do_not_escape_into_host(self):
        cases = [{"revision": "oops"}, {"revision": []}, {"revision": float("inf")},
                 {"output": []}, {"output": "wrong"}, {"source": ["wrong"]},
                 {"output": {"codec": {}}}, {"shot_states": {"bad": None}}, {"profiles": "bad"}]
        for value in cases:
            with self.subTest(value=value):
                node = target.HMBColorLUTLibrary(name="Malformed LUT")
                node._apply_ui(value)
        for command in (None, [], "not-json", {"id": "bad", "action": "save_profile", "state": {"profiles": 5}},
                        {"id": "bad-shot", "action": "export", "state": {"shot": [1]}}):
            with self.subTest(command=command):
                self.node._command(command)

    def test_hydration_never_exports_source_from_a_different_shot(self):
        saved = copy.deepcopy(self.node._hmb_color_lut_state)
        saved["shot"] = SHOT_A
        saved["source"] = self.source(shot=SHOT_B)
        self.node._apply_ui(saved)
        self.drain()
        with mock.patch.object(target, "export_video", side_effect=self.successful_export) as encode:
            self.export()
        encode.assert_not_called()
        self.assertFalse(self.node._hmb_color_lut_state["source"])

    def test_malformed_saved_history_does_not_break_project_switch(self):
        other = copy.deepcopy(self.node._hmb_color_lut_state)
        other["project_id"] = "project-2"
        saved = copy.deepcopy(self.node._hmb_color_lut_state)
        saved["shot_states"] = {target._selection_key(other): None}
        self.node._apply_ui(saved)
        self.apply(project_id="project-2")
        self.assertEqual(self.node._hmb_color_lut_state["settings"], target.default_settings())


if __name__ == "__main__":
    unittest.main(verbosity=2)
