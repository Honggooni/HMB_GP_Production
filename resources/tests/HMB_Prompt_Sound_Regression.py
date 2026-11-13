"""Prompt Sound contract fixtures; no application, provider, media submission or network."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBPromptLibrary as prompt
import HMBImageAssetLibrary as image_node
import HMBSoundLibrary as sound_node
import _hmb_sound as sound
import _hmb_shot_routing as routing

CHANNEL = "11111111-1111-4111-8111-111111111111"
SHOTS = [{"channel_uuid": CHANNEL, "shot_uuid": f"22222222-2222-4222-8222-{i:012d}",
          "number": i, "name": f"Shot {i}", "selected_source_uids": []} for i in range(1, 3)]


class PromptSoundRegression(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="hmb-prompt-sound-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve() / "superwings12" / "Ai_Ct_audio"
        (self.root / "Dialogue").mkdir(parents=True)
        self.audio = self.root / "Dialogue" / "Hero.wav"
        self.audio.write_bytes(b"fixture audio identity only; no listening claim")
        self.snapshot = {"schema": sound.SCHEMA, "version": 1, "project_id": "superwings12", "project_root": str(self.root),
            "project_uid": sound.project_uid(self.root), "channel_uuid": CHANNEL, "revision": 3, "tracks": []}
        for index, shot in enumerate([SHOTS[0], SHOTS[0], SHOTS[1]], 1):
            self.snapshot["tracks"].append({"instance_id": f"track-{index}", "source_uid": sound.source_uid(self.root, "Dialogue/Hero.wav"),
                "relative_path": "Dialogue/Hero.wav", "path": str(self.audio), "media_signature": sound.media_signature(self.audio),
                "name": "Hero", "role": "Dialogue", "purpose": "both", "transcript": "  원본 대사 {0}\nOFF  ",
                "target": "Hero", "in_seconds": 0, "out_seconds": None, "start_seconds": index - 1, "gain_db": 0,
                "enabled": True, "loop": False, "lipsync": False, "duration_seconds": 8,
                "channel_uuid": CHANNEL, "shot_uuid": shot["shot_uuid"]})
        self.snapshot = sound.normalize_sound_snapshot(self.snapshot)
        self.state = prompt._normalize_state({**prompt._default_widget_state(), "multi_shot_enabled": True,
            "shot": SHOTS[0], "image_asset": {"project_id": "superwings12", "shot_catalog": SHOTS,
                "shot_catalog_routing": {"publisher_instance_uuid": CHANNEL, "channel_uuid": CHANNEL,
                    "generation": 1, "metadata_sha256": "a" * 64}}})
        self.node = prompt.HMBPromptLibrary(name="Prompt Sound fixture")
        self.node._current_state = lambda: deepcopy(self.state)
        self.source = SimpleNamespace(_hmb_sound_snapshot_for=lambda **_kwargs: deepcopy(self.snapshot))

    def test_no_sound_output_remains_unchanged_and_authored_fields_stay_five(self):
        state = prompt._default_widget_state()
        original = prompt._build_data_only_prompt_package(state)
        self.assertNotIn('"audios"', original)
        self.assertNotIn('"sound_direction"', original)
        self.assertEqual(prompt.TEXT_FIELD_NAMES,
            ["PROJECT_STYLE_LOOK", "SCENE_CONTEXT", "EMOTION_INTENT", "VIDEO_VFX", "PRESERVED_TEXT"])
        with patch.object(self.node, "_registered_sound_source", return_value=None):
            projected = self.node._apply_sound_source(prompt._normalize_state({**state, "sound_sources": [{"instance_id": "forged", "path": "C:/private.wav"}]}))
        self.assertEqual(prompt._build_data_only_prompt_package(projected), original)

    def test_unconfigured_sound_first_drag_is_optional_until_project_selection(self):
        state = prompt._normalize_state(prompt._default_widget_state())
        for index, field in enumerate(prompt.TEXT_FIELD_NAMES):
            state["text"][field] = f"  exact {index} {{0}} OFF\n  "
        baseline = prompt._build_data_only_prompt_package(state)
        current = {"value": {}}
        source = SimpleNamespace(_hmb_sound_snapshot_for=lambda **_kwargs: deepcopy(current["value"]))
        with patch.object(self.node, "_registered_sound_source", return_value=source):
            empty = self.node._apply_sound_source(deepcopy(state))
            self.assertEqual(prompt._build_data_only_prompt_package(empty), baseline)
            self.assertEqual(empty["text"], state["text"])
            self.assertEqual(empty["sound_sources"], [])
            self.assertEqual(self.node._hmb_current_sound_snapshot, {})
            configured = deepcopy(self.snapshot)
            configured["channel_uuid"] = ""
            configured["tracks"] = [dict(configured["tracks"][0], channel_uuid="", shot_uuid="")]
            current["value"] = configured
            ready = self.node._apply_sound_source(deepcopy(empty))
            self.assertEqual(len(ready["sound_sources"]), 1)
            self.assertEqual(ready["text"], state["text"])
            self.assertIn('"audios"', prompt._build_data_only_prompt_package(ready))
            current["value"] = {}
            cleared = self.node._apply_sound_source(deepcopy(ready))
            self.assertEqual(prompt._build_data_only_prompt_package(cleared), baseline)
            current["value"] = None
            with self.assertRaises(sound.SoundError):
                self.node._apply_sound_source(deepcopy(empty))

    def test_exact_scope_instance_overlays_and_literal_public_directions(self):
        self.state["text"]["EMOTION_INTENT"] = "keep performance 0 OFF"
        self.state["text"]["VIDEO_VFX"] = "keep VFX {unchanged}"
        self.state["sound_direction"] = "  짧게, {정확한 대사}\n0 OFF  "
        self.state["sound_overlays"] = {
            "track-1": {"start_seconds": 0, "gain_db": 0, "loop": False, "lipsync": True, "transcript": "  안녕 {0}\nOFF  "},
            "track-2": {"start_seconds": 2, "enabled": False},
            "track-3": {"transcript": "must not cross the Shot boundary"},
        }
        before = deepcopy(self.snapshot)
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            state = self.node._apply_sound_source(deepcopy(self.state))
            snapshot = self.node._hmb_sound_snapshot_for(CHANNEL, SHOTS[0]["shot_uuid"])
        self.assertEqual(self.snapshot, before)
        self.assertEqual(len(snapshot["tracks"]), 3, "immutable transport keeps the complete source snapshot")
        self.assertEqual(snapshot["tracks"][0]["transcript"], "  안녕 {0}\nOFF  ")
        self.assertEqual(snapshot["tracks"][2]["transcript"], before["tracks"][2]["transcript"])
        self.assertEqual(len(state["sound_sources"]), 2)
        machine = prompt._build_data_only_prompt_package(state)
        lines = machine.splitlines()
        job = json.loads(lines[lines.index(prompt.PUBLIC_JOB_CONTRACT_HEADER) + 1])
        self.assertEqual(len(job["audios"]), 1)
        self.assertEqual(job["audios"][0]["audio"], "@audio1")
        self.assertEqual(job["audios"][0]["transcript"], "  안녕 {0}\nOFF  ")
        self.assertEqual(job["sound_direction"], self.state["sound_direction"])
        self.assertEqual(job["audios"][0]["start_seconds"], 0)
        self.assertEqual(job["audios"][0]["gain_db"], 0)
        self.assertIs(job["audios"][0]["loop"], False)
        self.assertNotIn(str(self.root), machine)
        self.assertNotIn("media_signature", machine)
        self.assertEqual(state["text"], self.state["text"])

    def test_invalid_connected_scope_project_and_timing_are_explicit(self):
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            changed = deepcopy(self.state)
            changed["image_asset"]["project_id"] = "Other"
            with self.assertRaisesRegex(sound.SoundError, "프로젝트"):
                self.node._sound_snapshot_for_state(changed)
            changed = deepcopy(self.state)
            changed["shot"]["channel_uuid"] = "other-channel"
            with self.assertRaisesRegex(sound.SoundError, "채널"):
                self.node._sound_snapshot_for_state(changed)
            changed = deepcopy(self.state)
            changed["sound_overlays"] = {"track-1": {"in_seconds": 3, "out_seconds": 1}}
            with self.assertRaises(sound.SoundError):
                self.node._sound_snapshot_for_state(changed)

    def test_pending_sound_add_is_typed_preparing_and_never_an_empty_ready_snapshot(self):
        preparing = deepcopy(self.snapshot)
        preparing["preparing"] = True
        source = SimpleNamespace(_hmb_sound_snapshot_for=lambda **_kwargs: deepcopy(preparing))
        with patch.object(self.node, "_registered_sound_source", return_value=source):
            with self.assertRaises(sound.SoundPreparingError) as result:
                self.node._sound_snapshot_for_state(deepcopy(self.state))
        self.assertIs(getattr(result.exception, "hmb_sound_preparing", False), True)
        self.assertEqual(result.exception.code, "SOUND_PREPARING")

    def test_mix_first_does_not_consume_dialogue_provider_audio_slot(self):
        self.snapshot["tracks"][0].update(purpose="mix", role="Music", name="BGM")
        self.snapshot["tracks"][1].update(purpose="both", role="Dialogue", name="Dialogue")
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            state = self.node._apply_sound_source(deepcopy(self.state))
        machine = prompt._build_data_only_prompt_package(state)
        lines = machine.splitlines()
        job = json.loads(lines[lines.index(prompt.PUBLIC_JOB_CONTRACT_HEADER) + 1])
        self.assertEqual([(row["name"], row["audio"]) for row in job["audios"]], [("BGM", "@mix1"), ("Dialogue", "@audio1")])
        self.assertNotIn("source_uid", json.dumps(job["audios"]))
        self.assertNotIn("media_signature", machine)
        self.assertNotIn(str(self.root), machine)

    def test_speaker_reference_uses_exact_sources_and_colors_after_reordering(self):
        state = deepcopy(self.state)
        sheet = {"label": "Hero sheet.png", "asset_source_uid": "sheet-id",
                 "asset_managed": True, "image_main_type": "Character", "image_sub_type": "Full Appearance"}
        preview = {"label": "Original preview.mov", "video_uid": "preview-id"}
        mask = {"label": "Color guide.mov", "video_uid": "mask-id", "picker_speaker_mask": True}
        state["images"] = [sheet, dict(sheet, asset_source_uid="other-shot")]
        state["videos"] = [preview, mask]
        state["image_asset"].update(enabled=True, ordered_source_uids=["sheet-id"])
        state["picker"].update(enabled=True, ordered_video_uids=["preview-id", "mask-id"], markers=[
            {"video_uid": "mask-id", "color": "Red", "asset_id": "Hero"},
            {"video_uid": "mask-id", "color": "Green", "asset_id": "Hero"},
            {"video_uid": "mask-id", "color": "Green", "asset_id": "Villain"},
            {"video_uid": "different-mask", "color": "Blue", "asset_id": "Hero"},
        ])
        state["sound_overlays"] = {
            "track-1": {"speaker_binding": {"kind": "image", "source_id": "sheet-id", "color": ""}},
            "track-2": {"speaker_binding": {"kind": "video", "source_id": "mask-id", "color": "Red"}},
        }
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            state = self.node._apply_sound_source(prompt._normalize_state(state))
        self.assertEqual([(r["kind"], r["is_mask"], r["colors"]) for r in state["speaker_sources"]],
                         [("image", False, []), ("video", False, []), ("video", True, ["Red"])])

        def audios(widget):
            machine = prompt._build_data_only_prompt_package(widget).splitlines()
            return json.loads(machine[machine.index(prompt.PUBLIC_JOB_CONTRACT_HEADER) + 1])["audios"]

        self.assertEqual([row["speaker_reference"] for row in audios(state)],
                         [{"source": "@image1"}, {"source": "@video2", "mask_color": "Red"}])
        self.assertIn("Speaker reference: @video2 / Mask color: Red", prompt._build_prompt_package(state))
        self.assertNotIn("speaker_binding", self.node._hmb_current_sound_snapshot["tracks"][0])
        state["videos"] = [mask, preview]
        self.assertEqual(audios(state)[1]["speaker_reference"], {"source": "@video1", "mask_color": "Red"})

        restored = prompt._normalize_state(json.loads(prompt._json_dumps(state)))
        self.assertEqual(audios(restored)[1]["speaker_reference"], {"source": "@video1", "mask_color": "Red"})
        restored["sound_overlays"]["track-2"]["speaker_binding"]["color"] = "Green"
        self.assertNotIn("speaker_reference", audios(restored)[1])
        restored["sound_overlays"]["track-2"]["speaker_binding"] = {"kind": "video", "source_id": "preview-id"}
        self.assertEqual(audios(restored)[1]["speaker_reference"], {"source": "@video2"})
        restored["videos"][1]["video_sub_type"] = "Analysis"
        self.assertNotIn("speaker_reference", audios(restored)[1])
        restored["videos"][1]["video_sub_type"] = ""
        restored["sound_sources"][1]["purpose"] = "mix"
        self.assertNotIn("speaker_reference", audios(restored)[1])

    def test_audio_subtypes_keep_only_apply_in_normal_sound_and_only_analysis_in_picker(self):
        self.snapshot["tracks"].append(dict(self.snapshot["tracks"][0], instance_id="track-4", enabled=False))
        state = deepcopy(self.state)
        state["sound_overlays"] = {
            "track-1": {"audio_sub_type": "Analysis", "enabled": False, "in_seconds": 1, "out_seconds": 4},
            "track-2": {"audio_sub_type": "Ignore", "enabled": True, "purpose": "mix"},
            "track-4": {"audio_sub_type": "Apply", "enabled": False, "start_seconds": 0},
        }
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            state = self.node._apply_sound_source(prompt._normalize_state(state))
            snapshot = self.node._hmb_current_sound_snapshot
        self.assertEqual([(row["instance_id"], row["audio_sub_type"], row["enabled"], row["audio"])
                          for row in state["sound_sources"]],
            [("track-1", "Analysis", False, ""), ("track-2", "Ignore", False, ""),
             ("track-4", "Apply", True, "@audio1")])
        self.assertEqual([(row["instance_id"], row["enabled"]) for row in snapshot["tracks"]],
            [("track-1", False), ("track-2", False), ("track-3", True), ("track-4", True)])
        self.assertTrue(all("audio_sub_type" not in row for row in snapshot["tracks"]))
        self.assertEqual([row["instance_id"] for row in sound.resolve_sound_tracks(snapshot,
            channel_uuid=CHANNEL, shot_uuid=SHOTS[0]["shot_uuid"])], ["track-4"])
        candidates = self.node._hmb_project_analysis_sources(state, [], [], snapshot)
        self.assertEqual([(row["selector"], row["start_seconds"], row["end_seconds"]) for row in candidates],
            [("track-1", 1, 4)])
        machine = prompt._build_data_only_prompt_package(state)
        job = json.loads(machine.splitlines()[machine.splitlines().index(prompt.PUBLIC_JOB_CONTRACT_HEADER) + 1])
        self.assertEqual([row["audio"] for row in job["audios"]], ["@audio1"])
        self.assertTrue(all("audio_sub_type" not in row for row in job["audios"]))

    def test_failed_sound_add_is_explicit_nonretry_error(self):
        failed = deepcopy(self.snapshot)
        failed["preparation_error"] = "SOUND_PREPARATION_FAILED"
        source = SimpleNamespace(_hmb_sound_snapshot_for=lambda **_kwargs: deepcopy(failed))
        with patch.object(self.node, "_registered_sound_source", return_value=source):
            with self.assertRaises(sound.SoundError) as result:
                self.node._sound_snapshot_for_state(deepcopy(self.state))
        self.assertEqual(result.exception.code, "SOUND_PREPARATION_FAILED")
        self.assertFalse(getattr(result.exception, "hmb_sound_preparing", False))

    def test_agent_sound_snapshot_requires_current_machine_pair(self):
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            state = self.node._apply_sound_source(deepcopy(self.state))
            machine = prompt._build_data_only_prompt_package(state)
            with patch.object(self.node, "_compile_current_prompt_pair", return_value=(state, "visible", machine, "fingerprint")):
                self.assertEqual(self.node._hmb_agent_sound_snapshot(machine), self.node._hmb_current_sound_snapshot)
                with self.assertRaisesRegex(sound.SoundError, "Prompt"):
                    self.node._hmb_agent_sound_snapshot(machine + "stale")

    def test_shot_documents_and_crossed_revision_merge_retain_sound_authoring(self):
        state = deepcopy(self.state)
        for index, shot in enumerate(SHOTS):
            state = prompt._select_prompt_shot_document(state, shot)
            state["sound_overlays"] = {"track-1": {"gain_db": 0, "lipsync": index == 0, "transcript": f"exact {index}  ",
                "audio_sub_type": ("Analysis", "Ignore")[index]}}
            state["sound_direction"] = f"direction {index}\n0 OFF  "
            prompt._store_prompt_shot_document(state)
        for index, shot in enumerate(SHOTS):
            restored = prompt._select_prompt_shot_document(deepcopy(state), shot)
            self.assertEqual(restored["sound_direction"], f"direction {index}\n0 OFF  ")
            self.assertEqual(restored["sound_overlays"]["track-1"]["transcript"], f"exact {index}  ")
            self.assertEqual(restored["sound_overlays"]["track-1"]["audio_sub_type"], ("Analysis", "Ignore")[index])
        source = prompt._select_prompt_shot_document(deepcopy(state), SHOTS[0])
        ui = deepcopy(source)
        ui["sound_direction"] = "latest literal"
        ui["sound_overlays"]["track-1"]["lipsync"] = False
        merged = prompt._merge_prompt_revision_axes(source, ui)
        self.assertEqual(merged["sound_direction"], "latest literal")
        self.assertIs(merged["sound_overlays"]["track-1"]["lipsync"], False)

    def test_new_default_height_and_saved_user_geometry(self):
        self.assertEqual(prompt.PROMPT_START_HEIGHT, 1480)
        self.assertEqual(prompt._prompt_start_metadata({})["size"], {"width": 1490, "height": 1480})
        saved = {"size": {"width": 1234, "height": 987}, "position": {"x": 0, "y": 1}}
        self.assertEqual(prompt._prompt_start_metadata(saved), saved)

    def test_immutable_shot_document_contains_full_audio_snapshot_without_ui_mutation(self):
        image_state = image_node._default_state()
        image_state["project_id"] = "superwings12"
        image_state["shot_routing"]["channel_uuid"] = CHANNEL
        image_state["shot_routing"]["shots"] = [{**shot, "revision": 1} for shot in SHOTS]
        image_state["shot_routing"]["active_shot_uuid"] = SHOTS[0]["shot_uuid"]
        image_snapshot = image_node._build_shot_routing_snapshot(image_state, normalized=True)
        catalog = prompt._compact_catalog_from_snapshot(image_snapshot)
        self.state["image_asset"]["shot_catalog_routing"] = prompt._catalog_routing_projection(catalog)
        self.state["sound_overlays"] = {"track-1": {"transcript": "  immutable exact {0}  ", "lipsync": True}}
        self.node._hmb_connected_source_nodes = {prompt.SHOT_ASSET_INPUT_PARAMETER_NAME: SimpleNamespace(
            _hmb_shot_routing_snapshot=lambda **_kwargs: deepcopy(image_snapshot),
            _hmb_project_identity=lambda: {"project_id": "superwings12", "project_name": "슈퍼윙즈12"})}
        before = deepcopy(self.state)
        outputs = deepcopy(dict(self.node.parameter_output_values))
        with patch.object(self.node, "_registered_sound_source", return_value=self.source):
            document = self.node._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=SHOTS[0]["shot_uuid"])
        self.assertEqual(document["audio_sources"]["schema"], sound.SCHEMA)
        self.assertEqual(len(document["audio_sources"]["tracks"]), 3)
        self.assertEqual(document["audio_sources"]["tracks"][0]["transcript"], "  immutable exact {0}  ")
        self.assertNotIn(str(self.root), document["machine_prompt"])
        document["audio_sources"]["tracks"][0]["transcript"] = "mutated consumer copy"
        self.assertEqual(self.state, before)
        self.assertEqual(dict(self.node.parameter_output_values), outputs)
        self.assertNotEqual(self.snapshot["tracks"][0]["transcript"], "mutated consumer copy")

    def test_physical_edge_registration_and_source_file_proof(self):
        source = sound_node.HMBSoundLibrary.__new__(sound_node.HMBSoundLibrary)
        source.name = "Sounds"
        source.metadata = {"library": "HMB_GP_Production", "node_type": "HMBSoundLibrary"}
        source._hmb_node_deleted = False
        self.node._hmb_connected_source_nodes[prompt.SOUND_INPUT_PARAMETER_NAME] = source
        self.node._hmb_sound_connected = True
        edge = SimpleNamespace(target_parameter_name="SOUND_IN", source_parameter_name="SHOT_SOUND_OUT", source_node_name="Sounds")
        class Success:
            incoming_connections = [edge]
        native = ModuleType("griptape_nodes.retained_mode.griptape_nodes")
        manager = SimpleNamespace(get_node_by_name=lambda name: source if name == "Sounds" else self.node)
        native.GriptapeNodes = SimpleNamespace(NodeManager=lambda: manager, handle_request=lambda _request: Success())
        events = ModuleType("griptape_nodes.retained_mode.events.connection_events")
        events.ListConnectionsForNodeResultSuccess = Success
        events.ListConnectionsForNodeRequest = lambda **_kwargs: None
        engine = ModuleType("griptape_nodes.retained_mode.engine")
        engine.has_current_engine = lambda: True
        with patch.dict(sys.modules, {native.__name__: native, events.__name__: events, engine.__name__: engine}), \
             patch.object(routing, "_same_flow_nodes", return_value=("Flow", [self.node, source])):
            self.assertIs(self.node._registered_sound_source(), source)
            Success.incoming_connections = [edge, edge]
            with self.assertRaises(sound.SoundError):
                self.node._registered_sound_source()
            Success.incoming_connections = [edge]
            edge.source_parameter_name = "forged-output"
            with self.assertRaises(sound.SoundError):
                self.node._registered_sound_source()
            edge.source_parameter_name = "SHOT_SOUND_OUT"
            source._hmb_node_deleted = True
            with self.assertRaises(sound.SoundError):
                self.node._registered_sound_source()
            source._hmb_node_deleted = False
            Success.incoming_connections = []
            self.assertIsNone(self.node._registered_sound_source(), "disconnected serialized data has no source authority")


if __name__ == "__main__":
    unittest.main(verbosity=2)
