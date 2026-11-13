from __future__ import annotations

"""Sound confinement, transactional authoring and real retained-SDK hydration.

All audio and SDK settings are disposable; no model, server or user folder write.
"""
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
from uuid import uuid4
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_sound as helper
import HMBSoundLibrary as target
import _hmb_shot_routing as routing
try:
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    NATIVE = True
except ImportError:
    NATIVE = False

CHANNEL = "11111111-1111-4111-8111-111111111111"
SHOTS = [{"shot_uuid": f"33333333-3333-4333-8333-{n:012d}", "number": n, "name": f"Shot {n}", "revision": 1} for n in (1, 2)]
_document = {"channel_uuid": CHANNEL, "generation": 1, "shots": SHOTS}
CATALOG = {"schema": "hmb-shot-routing-catalog", "version": 1,
    "publisher_instance_uuid": "22222222-2222-4222-8222-222222222222", **_document,
    "metadata_sha256": hashlib.sha256(json.dumps(_document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def make_wave(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(48000)
        output.writeframes(struct.pack("<h", 4000) * 12000)


class ControlledThread:
    pending = []
    def __init__(self, target=None, **_kwargs): self.target, self.running = target, False
    def start(self): self.running = True; self.pending.append(self)
    def is_alive(self): return self.running
    def run(self):
        self.pending.remove(self)
        try: self.target()
        finally: self.running = False


class SoundLibraryRegression(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hmb_sound_library_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.audio = self.root / "showA" / "Ai_Ct_audio"
        self.path = self.audio / "Dialogue" / "voice.wav"
        make_wave(self.path)
        self.track = helper.make_sound_track(self.audio, "Dialogue/voice.wav")
        self.snapshot = {"schema": helper.SCHEMA, "version": 1, "project_id": "showA", "project_root": str(self.audio),
            "project_uid": helper.project_uid(self.audio), "channel_uuid": "", "revision": 1, "tracks": [self.track]}

    def test_catalog_preserves_originals_and_does_not_create_missing_project(self):
        before = self.path.read_bytes()
        assets = helper.scan_sound_project(self.audio)
        self.assertEqual(assets[0]["role"], "Dialogue")
        self.assertEqual(assets[0]["relative_path"], "Dialogue/voice.wav")
        missing = self.root / "missing" / "Ai_Ct_audio"
        with self.assertRaises(helper.SoundError): helper.scan_sound_project(missing)
        self.assertFalse(missing.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_escape_absolute_alias_and_unsupported_source_are_rejected(self):
        for relative in ("../voice.wav", "/voice.wav", "C:/voice.wav", "Dialogue/../voice.wav", "./Dialogue/voice.wav", "Dialogue//voice.wav", "Dialogue/voice.json"):
            with self.subTest(relative=relative), self.assertRaises(helper.SoundError): helper._source_path(self.audio, relative)
        forged = copy.deepcopy(self.snapshot); forged["tracks"][0]["path"] = str(self.root / "outside.wav")
        with self.assertRaises(helper.SoundError): helper.normalize_sound_snapshot(forged)

    def test_ancestor_reparse_is_checked_before_resolve_hides_it(self):
        original = Path.lstat
        def fake_lstat(path, *args, **kwargs):
            if path == self.audio.parent:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", autospec=True, side_effect=fake_lstat), self.assertRaises(helper.SoundError):
            helper.resolve_sound_tracks(self.snapshot)

    def test_actual_symlink_escape_if_supported(self):
        outside = self.root / "outside.wav"; outside.write_bytes(self.path.read_bytes())
        linked = self.audio / "linked.wav"
        try: linked.symlink_to(outside)
        except OSError: self.skipTest("Windows symlink privilege unavailable; reparse-component test still runs")
        with self.assertRaises(helper.SoundError): helper._source_path(self.audio, "linked.wav")

    def test_size_and_exact_bytes_are_verified_at_execution(self):
        with mock.patch.object(helper, "MAX_SOURCE_BYTES", 16), self.assertRaises(helper.SoundError): helper.media_signature(self.path)
        self.assertEqual(len(helper.resolve_sound_tracks(self.snapshot)), 1)
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        with self.assertRaises(helper.SoundError) as failure: helper.resolve_sound_tracks(self.snapshot)
        self.assertEqual(failure.exception.code, "SOUND_SOURCE_CHANGED")

    def test_ffmpeg_header_fallback_when_ffprobe_lookup_raises(self):
        import _hmb_video_tools
        with mock.patch.object(_hmb_video_tools, "_find_ffprobe", side_effect=ValueError("probe not bundled")):
            self.assertAlmostEqual(helper.probe_sound(self.path)["duration_seconds"], .25, places=2)

    def test_only_and_numbered_shot_rows_never_cross_scopes(self):
        numbered = copy.deepcopy(self.track)
        numbered.update(instance_id=str(uuid4()), channel_uuid=CHANNEL, shot_uuid=SHOTS[0]["shot_uuid"])
        value = {**self.snapshot, "channel_uuid": CHANNEL, "tracks": [self.track, numbered]}
        self.assertEqual([t["instance_id"] for t in helper.resolve_sound_tracks(value)], [self.track["instance_id"]])
        self.assertEqual(helper.resolve_sound_tracks(value, channel_uuid=CHANNEL, shot_uuid=SHOTS[1]["shot_uuid"]), [])
        self.assertEqual(len(helper.resolve_sound_tracks(value, channel_uuid=CHANNEL, shot_uuid=SHOTS[0]["shot_uuid"], project_id="showA")), 1)
        for context in ({"channel_uuid": "foreign", "shot_uuid": SHOTS[0]["shot_uuid"]}, {"project_id": "other"}):
            with self.assertRaises(helper.SoundError): helper.resolve_sound_tracks(value, **context)

    def test_literal_zero_false_eof_and_public_directions_are_preserved(self):
        value = copy.deepcopy(self.snapshot)
        literal = '  supplied "words"\nNo invented speech.  '
        value["tracks"][0].update(transcript=literal, gain_db=0, start_seconds=0, out_seconds=None, lipsync=False, enabled=False)
        normalized = helper.normalize_sound_snapshot(value)["tracks"][0]
        self.assertEqual(normalized["transcript"], literal)
        self.assertEqual((normalized["gain_db"], normalized["start_seconds"], normalized["out_seconds"], normalized["lipsync"]), (0, 0, None, False))
        self.assertEqual(helper.public_sound_directions(value), [])
        value["tracks"][0]["enabled"] = True
        direction = helper.public_sound_directions(value)[0]
        self.assertEqual(direction["transcript"], literal)
        self.assertFalse({"path", "media_signature", "project_root"} & direction.keys())

    def test_preparing_and_failed_selection_block_before_any_file_hash(self):
        with mock.patch.object(helper,"media_signature",side_effect=AssertionError("preparation must stop before file reads")):
            pending={**self.snapshot,"preparing":True}
            self.assertTrue(helper.normalize_sound_snapshot(pending)["preparing"])
            with self.assertRaises(helper.SoundPreparingError) as failure:helper.resolve_sound_tracks(pending)
            self.assertIs(failure.exception.hmb_sound_preparing,True)
            with self.assertRaises(helper.SoundError) as failure:helper.resolve_sound_tracks({**self.snapshot,"preparation_error":"SOUND_PREPARATION_FAILED"})
            self.assertEqual(failure.exception.code,"SOUND_PREPARATION_FAILED")
            self.assertFalse(getattr(failure.exception,"hmb_sound_preparing",False))

    def test_six_sound_instances_are_preserved_five_limits_shots_only(self):
        value={**self.snapshot,"tracks":[{**copy.deepcopy(self.track),"instance_id":str(uuid4())} for _ in range(6)]}
        self.assertEqual(len(helper.normalize_sound_snapshot(value)["tracks"]),6)
        self.assertEqual(len(helper.resolve_sound_tracks(value)),6)

    def test_authoring_normalization_never_opens_or_resolves_originals(self):
        value={**self.snapshot,"tracks":[{**copy.deepcopy(self.track),"instance_id":str(uuid4())} for _ in range(64)]}
        with mock.patch.object(Path,"resolve",side_effect=AssertionError("authoring must not resolve SMB")), \
             mock.patch.object(Path,"lstat",side_effect=AssertionError("authoring must not stat SMB")), \
             mock.patch.object(helper,"media_signature",side_effect=AssertionError("authoring must not hash media")), \
             mock.patch.object(helper,"probe_sound",side_effect=AssertionError("authoring must not decode media")):
            normalized=helper.normalize_sound_snapshot(value)
        self.assertEqual(len(normalized["tracks"]),64)
        self.assertEqual(normalized["tracks"][0]["source_uid"],self.track["source_uid"])

    def test_public_tokens_match_provider_reference_order_and_only_namespace(self):
        rows=[]
        for purpose in ("mix","both","mix","reference"):
            rows.append({**copy.deepcopy(self.track),"instance_id":str(uuid4()),"purpose":purpose,"channel_uuid":CHANNEL,"shot_uuid":SHOTS[0]["shot_uuid"]})
        value={**self.snapshot,"channel_uuid":CHANNEL,"tracks":rows}
        self.assertEqual([r["audio"] for r in helper.public_sound_directions(value,channel_uuid=CHANNEL,shot_uuid=SHOTS[0]["shot_uuid"])],["@mix1","@audio1","@mix2","@audio2"])
        for row in rows:row.update(channel_uuid="",shot_uuid="")
        self.assertEqual([r["audio"] for r in helper.public_sound_directions({**self.snapshot,"tracks":rows})],["@mix1","@sound1","@mix2","@sound2"])


@unittest.skipUnless(NATIVE, "Installed retained SDK required for authoring lifecycle")
class SoundNodeRegression(SoundLibraryRegression):
    # Keep helper checks separate in discovery; this fixture tests retained state.
    def setUp(self):
        super().setUp()
        self.addCleanup(logging.shutdown)
        environment = {key: str(self.root / key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")}
        patch = mock.patch.dict(os.environ, environment); patch.start(); self.addCleanup(patch.stop)
        if NATIVE:
            scope = engine_scope(); self.engine = scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
            self.engine.event_manager.initialize_queue()
            ensured = self.engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="SoundFixture"))
            self.assertTrue(ensured.succeeded(), str(ensured.result_details))
            self.flow = self.engine.flow_manager.get_flow_by_name(ensured.flow_name)
        ControlledThread.pending = []
        for patch in (mock.patch.object(routing, "schedule_post_registration_reconcile"),
                      mock.patch.object(target.HMBSoundLibrary, "_notify_consumers"),
                      mock.patch.object(target, "threading", types.SimpleNamespace(RLock=threading.RLock,Thread=ControlledThread))):
            patch.start(); self.addCleanup(patch.stop)
        if NATIVE:
            from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
            from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
            schema=LibrarySchema.model_validate_json((ROOT/"griptape-nodes-library.json").read_text("utf-8-sig"))
            library=LibraryRegistry.generate_new_library(schema)
            definition=next((d for d in schema.nodes if d.class_name=="HMBSoundLibrary"),next(d for d in schema.nodes if d.class_name=="HMBImageAssetLibrary"))
            library.register_lazy_node_type("HMBSoundLibrary",definition.metadata,lambda:target.HMBSoundLibrary)
            self.addCleanup(LibraryRegistry.unregister_library,schema.name,event_manager=self.engine.event_manager)
            created=self.engine.handle_request(CreateNodeRequest(node_type="HMBSoundLibrary",node_name="Sound Fixture",specific_library_name=schema.name,initial_setup=True))
            self.assertTrue(created.succeeded(),str(created.result_details))
            self.node=self.engine.node_manager.get_node_by_name(created.node_name)
        else:
            self.node = target.HMBSoundLibrary(name="Sound Fixture")
        self.node.publish_update_to_parameter = mock.Mock()
        state = target.default_state()
        state.update(**{k:self.snapshot[k] for k in ("project_id", "project_root", "project_uid", "channel_uuid", "revision", "tracks")})
        state["projects"] = [{"project_id":"showA","project_root":str(self.audio)}]
        state["assets"] = helper.scan_sound_project(self.audio)
        self.node.set_parameter_value(target.UI, state, initial_setup=True)

    def command(self, action, **changes): self.node._command({"id":str(uuid4()),"action":action,**changes})
    def drain(self):
        while ControlledThread.pending: ControlledThread.pending[0].run()

    def test_native_initial_setup_restores_without_hook_or_command_replay(self):
        state = copy.deepcopy(self.node._state_sound);state["__hmb_sound_command"]={"id":"saved","action":"remove","instance_id":self.track["instance_id"]}
        with mock.patch.object(self.node,"after_value_set",wraps=self.node.after_value_set) as hook, mock.patch.object(self.node,"_command") as command:
            with mock.patch.object(routing,"schedule_post_hydration_reconcile") as schedule:
                self.node.set_parameter_value(target.UI,state,initial_setup=True)
                schedule.assert_called_once_with(self.node)
            hook.assert_not_called();command.assert_not_called()
        self.assertEqual(self.node._state_sound["tracks"], helper.normalize_sound_snapshot(self.snapshot)["tracks"])
        self.assertNotIn("__hmb_sound_command",self.node.get_parameter_value(target.UI))
        self.node.publish_update_to_parameter.assert_not_called()

    def test_malformed_save_and_live_browser_state_cannot_replace_sources(self):
        before=copy.deepcopy(self.node._state_sound)
        forged=copy.deepcopy(before);forged["tracks"][0]["path"]=str(self.root/"outside.wav")
        with mock.patch.object(routing,"schedule_post_hydration_reconcile") as schedule:
            self.node.set_parameter_value(target.UI,forged,initial_setup=True)
            schedule.assert_not_called()
        self.assertEqual(self.node._state_sound,before)
        self.node.after_value_set(types.SimpleNamespace(name=target.UI),forged)
        self.assertEqual(self.node._state_sound,before)
        self.assertEqual(self.node.get_parameter_value(target.UI)["tracks"][0]["path"],before["tracks"][0]["path"])

    def test_invalid_edit_is_atomic_and_duplicate_is_explicit(self):
        before=copy.deepcopy(self.node._state_sound["tracks"])
        with self.assertRaises(helper.SoundError):self.command("edit",instance_id=self.track["instance_id"],changes={"gain_db":999})
        self.assertEqual(self.node._state_sound["tracks"],before)
        self.command("add",relative_path="Dialogue/voice.wav")
        self.assertEqual(ControlledThread.pending,[])
        self.command("duplicate",instance_id=self.track["instance_id"])
        self.assertEqual(len(self.node._state_sound["tracks"]),2)
        self.assertNotEqual(*[t["instance_id"] for t in self.node._state_sound["tracks"]])

    def test_add_limit_and_stale_context_preserve_all_existing_tracks(self):
        self.node._state_sound["tracks"]=[{**copy.deepcopy(self.track),"instance_id":str(uuid4())} for _ in range(64)]
        before=copy.deepcopy(self.node._state_sound["tracks"])
        with self.assertRaises(helper.SoundError):self.command("add",relative_path="Dialogue/voice.wav")
        with self.assertRaises(helper.SoundError):self.command("duplicate",instance_id=before[0]["instance_id"])
        with self.assertRaises(helper.SoundError):self.command("remove",instance_id=before[0]["instance_id"],context={"revision":0})
        self.assertEqual(self.node._state_sound["tracks"],before)

    def test_project_switch_with_tracks_is_rejected_before_scan(self):
        other=self.root/"showB"/"Ai_Ct_audio";other.mkdir(parents=True)
        self.node._state_sound["projects"].append({"project_id":"showB","project_root":str(other)})
        with mock.patch.object(target,"scan_sound_project") as scan, self.assertRaises(helper.SoundError):self.command("project",project_id="showB")
        scan.assert_not_called();self.assertEqual(self.node._state_sound["project_id"],"showA")

    def test_cancel_and_valid_restore_retire_late_worker_commits(self):
        self.command("refresh")
        with self.assertRaises(helper.SoundError):self.command("remove",instance_id=self.track["instance_id"])
        self.command("cancel");self.drain()
        self.assertFalse(self.node._state_sound["busy"])
        self.assertEqual(len(self.node._state_sound["tracks"]),1)
        self.command("refresh")
        saved=copy.deepcopy(self.node._state_sound);saved["tracks"][0]["transcript"]="restored authored words"
        self.node.set_parameter_value(target.UI,saved,initial_setup=True)
        self.drain()
        self.assertEqual(self.node._state_sound["tracks"][0]["transcript"],"restored authored words")
        self.assertFalse(self.node._state_sound["busy"])

    def test_rapid_project_changes_coalesce_and_retire_older_scan(self):
        other=self.root/"showB"/"Ai_Ct_audio";other.mkdir(parents=True)
        self.node._state_sound["tracks"]=[]
        self.node._state_sound["projects"].append({"project_id":"showB","project_root":str(other)})
        self.command("project",project_id="showB")
        self.command("project",project_id="showA")
        self.assertEqual(len(ControlledThread.pending),1,"Only one read worker may be active; the newest project is queued.")
        self.drain()
        self.assertEqual(self.node._state_sound["project_id"],"showA")
        self.assertEqual(len(self.node._state_sound["assets"]),1)
        self.assertFalse(self.node._state_sound["busy"])

    def test_add_commit_limit_is_atomic_even_if_another_author_changes_state(self):
        second=self.audio/"SFX"/"second.wav";make_wave(second)
        self.node._state_sound["assets"]=helper.scan_sound_project(self.audio)
        self.command("add",relative_path="SFX/second.wav")
        self.node._state_sound["tracks"]=[{**copy.deepcopy(self.track),"instance_id":str(uuid4())} for _ in range(64)]
        before=copy.deepcopy(self.node._state_sound["tracks"])
        self.drain()
        self.assertEqual(self.node._state_sound["tracks"],before)
        self.assertEqual(self.node._state_sound["error_code"],"SOUND_TRACK_LIMIT")

    def test_pending_add_is_typed_and_scoped_while_refresh_is_optional(self):
        self.node._hmb_reconcile_shot_routing(CATALOG)
        second=self.audio/"SFX"/"second.wav";make_wave(second)
        self.node._state_sound["assets"]=helper.scan_sound_project(self.audio)
        self.command("refresh")
        self.assertNotIn("preparing",self.node._snapshot())
        self.drain()
        self.command("add",relative_path="SFX/second.wav")
        pending=self.node._hmb_sound_snapshot_for(channel_uuid="",shot_uuid="")
        with self.assertRaises(helper.SoundPreparingError):helper.resolve_sound_tracks(pending)
        other=self.node._hmb_sound_snapshot_for(channel_uuid=CHANNEL,shot_uuid=SHOTS[1]["shot_uuid"])
        self.assertNotIn("preparing",other)
        self.assertEqual(helper.resolve_sound_tracks(other,channel_uuid=CHANNEL,shot_uuid=SHOTS[1]["shot_uuid"]),[])
        self.drain()
        self.assertNotIn("preparing",self.node._snapshot())
        self.assertEqual(len(self.node._state_sound["tracks"]),2)

    def test_failed_pending_add_cannot_silently_revert_to_old_audio(self):
        second=self.audio/"SFX"/"failed.wav";make_wave(second)
        self.node._state_sound["assets"]=helper.scan_sound_project(self.audio)
        before=copy.deepcopy(self.node._state_sound["tracks"])
        with mock.patch.object(target,"make_sound_track",side_effect=helper.SoundError("SOUND_SOURCE_UNAVAILABLE","Synthetic failure")):
            self.command("add",relative_path="SFX/failed.wav");self.drain()
        self.assertEqual(self.node._state_sound["tracks"],before)
        with self.assertRaises(helper.SoundError) as failure:helper.resolve_sound_tracks(self.node._snapshot())
        self.assertEqual(failure.exception.code,"SOUND_PREPARATION_FAILED")
        self.command("cancel")
        self.assertNotIn("preparation_error",self.node._snapshot())

    @unittest.skipUnless(NATIVE,"Installed retained SDK required")
    def test_native_event_hydration_and_serialization_keep_sound_data(self):
        state=copy.deepcopy(self.node._state_sound);state["tracks"][0]["transcript"]="actual SDK saved text"
        result=self.engine.handle_request(SetParameterValueRequest(node_name=self.node.name,parameter_name=target.UI,value=state,initial_setup=True,broadcast_result=False))
        self.assertTrue(result.succeeded(),str(result.result_details))
        self.assertEqual(self.node._state_sound["tracks"][0]["transcript"],"actual SDK saved text")
        serialized=self.engine.handle_request(SerializeFlowToCommandsRequest(flow_name=self.flow.name))
        self.assertTrue(serialized.succeeded(),str(serialized.result_details))
        self.assertIn("actual SDK saved text",str(serialized.serialized_flow_commands))
        self.assertIn("str",self.node.get_parameter_by_name(target.CATALOG_IN).input_types)

    def test_native_initial_geometry_preserves_saved_custom_size(self):
        from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
        self.assertEqual(self.node.metadata["size"],{"width":1470,"height":710})
        widget_options = self.node.get_parameter_by_name(target.UI).ui_options
        self.assertEqual((widget_options["width"], widget_options["height"]), (1430, 620))
        custom={"width":1035,"height":845}
        result=self.engine.handle_request(CreateNodeRequest(node_type="HMBSoundLibrary",node_name="Custom sized sound",
            specific_library_name="HMB_GP_Production",initial_setup=True,metadata={"size":custom}))
        self.assertTrue(result.succeeded(),str(result.result_details))
        node=self.engine.node_manager.get_node_by_name(result.node_name)
        self.assertEqual(node.metadata["size"],custom)
        node.set_parameter_value(target.UI,copy.deepcopy(self.node._state_sound),initial_setup=True)
        self.assertEqual(node.metadata["size"],custom)

    def test_native_saved_sixtyfour_offline_sources_never_probe_on_hydration(self):
        root=Path(r"\\offline.invalid\share\showA\Ai_Ct_audio")
        uid=helper.project_uid(root)
        state=target.default_state()
        state.update(project_id="showA",project_root=str(root),project_uid=uid,revision=10)
        for index in range(64):
            relative=f"voice-{index}.wav"
            state["tracks"].append({**copy.deepcopy(self.track),"instance_id":str(uuid4()),"relative_path":relative,
                "source_uid":helper.source_uid(root,relative),"path":str(root/relative)})
        with mock.patch.object(Path,"resolve",side_effect=AssertionError("native hydrate must not resolve offline media")), \
             mock.patch.object(Path,"lstat",side_effect=AssertionError("native hydrate must not stat offline media")), \
             mock.patch.object(helper,"media_signature",side_effect=AssertionError("native hydrate must not hash offline media")), \
             mock.patch.object(helper,"probe_sound",side_effect=AssertionError("native hydrate must not decode offline media")):
            self.node.set_parameter_value(target.UI,state,initial_setup=True)
        self.assertEqual(len(self.node._state_sound["tracks"]),64)
        self.assertEqual(self.node._state_sound["project_uid"],uid)

    def test_native_module_loading_alias_is_accepted_through_real_sound_lut_wire(self):
        from griptape_nodes.retained_mode.managers.library.module_loading import LibraryModuleLoading
        from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
        import HMBColorLUTLibrary as color
        loader=LibraryModuleLoading(self.engine)
        dynamic=loader.load_module_from_file(ROOT/"HMBSoundLibrary.py","HMB_GP_Production")
        self.assertIsNot(dynamic.HMBSoundLibrary,target.HMBSoundLibrary,"The actual loader must produce the distinct runtime alias class.")
        alias=dynamic.HMBSoundLibrary(name="Dynamic Sound Publisher")
        alias.set_parameter_value(target.UI,copy.deepcopy(self.node._state_sound),initial_setup=True)
        alias._publish(notify=False)
        with mock.patch.object(color,"_profiles_path",return_value=self.root/"profiles.json"):
            lut=color.HMBColorLUTLibrary(name="Dynamic Sound LUT")
        for node in (alias,lut):
            from _hmb_fixture_sdk import register_fixture_node
            register_fixture_node(self.engine, self.flow, node)
        result=self.engine.handle_request(CreateConnectionRequest(source_node_name=alias.name,source_parameter_name="SOUND_OUT",
            target_node_name=lut.name,target_parameter_name=color.SOUND_IN))
        self.assertTrue(result.succeeded(),str(result.result_details))
        captured=lut._capture_sound_snapshot(lut._hmb_color_lut_state)
        self.assertEqual(captured["tracks"][0]["source_uid"],self.track["source_uid"])
        self.assertEqual(captured["project_id"],"showA")

    def test_automatic_context_roundtrip_preserves_six_tracks_and_monotonic_revision(self):
        def catalog(channel,shots,generation):
            document={"channel_uuid":channel,"generation":generation,"shots":shots}
            return {"schema":"hmb-shot-routing-catalog","version":1,"publisher_instance_uuid":"22222222-2222-4222-8222-222222222222",**document,
                "metadata_sha256":hashlib.sha256(json.dumps(document,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
        state=copy.deepcopy(self.node._state_sound)
        state.update(channel_uuid=CHANNEL,shot_catalog=copy.deepcopy(CATALOG),shot={"channel_uuid":CHANNEL,**SHOTS[0]})
        state["tracks"]=[{**copy.deepcopy(self.track),"instance_id":str(uuid4()),"channel_uuid":CHANNEL,
            "shot_uuid":SHOTS[0]["shot_uuid"] if i<5 else "orphan-original-shot"} for i in range(6)]
        self.node.set_parameter_value(target.UI,state,initial_setup=True)
        context_a={"project_id":"showA","project_root":str(self.audio),"catalog":CATALOG,"source":None}
        self.node._activate_sound_context(context_a);self.drain()
        ids=[row["instance_id"] for row in self.node._state_sound["tracks"]]
        old_context={"project_uid":self.node._state_sound["project_uid"],"channel_uuid":CHANNEL,
            "shot_uuid":self.node._state_sound["shot"]["shot_uuid"],"revision":self.node._state_sound["revision"]}
        root_b=self.root/"showB"/"Ai_Ct_audio";make_wave(root_b/"own.wav")
        channel_b="44444444-4444-4444-8444-444444444444"
        shots_b=[{**SHOTS[0],"shot_uuid":"55555555-5555-4555-8555-555555555555","name":"Project B only"}]
        context_b={"project_id":"showB","project_root":str(root_b),"catalog":catalog(channel_b,shots_b,1),"source":None}
        self.node._activate_sound_context(context_b);self.drain()
        self.assertEqual(self.node._state_sound["tracks"],[])
        self.command("shot_add",source_uid=self.node._state_sound["assets"][0]["source_uid"],shot_uuid=shots_b[0]["shot_uuid"])
        self.drain();revision_b=self.node._state_sound["revision"]
        renamed=[{**SHOTS[0],"name":"A renamed exact UUID"}]
        context_a["catalog"]=catalog(CHANNEL,renamed,2)
        self.node._activate_sound_context(context_a);self.drain()
        self.assertEqual([r["instance_id"] for r in self.node._state_sound["tracks"]],ids)
        self.assertEqual(self.node._state_sound["shot_catalog"]["shots"][0]["name"],"A renamed exact UUID")
        self.assertGreater(self.node._state_sound["revision"],revision_b)
        self.assertEqual(self.node._track_total(self.node._state_sound),7)
        with self.assertRaises(helper.SoundError):self.command("remove",instance_id=ids[0],context=old_context)
        # Existing data remains after a source replaces a Shot at the same number.
        replacement=[{**renamed[0],"shot_uuid":"66666666-6666-4666-8666-666666666666"}]
        context_a["catalog"]=catalog(CHANNEL,replacement,3)
        self.node._activate_sound_context(context_a)
        self.assertEqual([r["instance_id"] for r in self.node._state_sound["tracks"]],ids)
        selected=self.node._hmb_sound_snapshot_for(channel_uuid=CHANNEL,shot_uuid=replacement[0]["shot_uuid"])
        self.assertEqual(helper.resolve_sound_tracks(selected,channel_uuid=CHANNEL,shot_uuid=replacement[0]["shot_uuid"]),[])
        saved=copy.deepcopy(self.node._state_sound)
        with mock.patch.object(Path,"resolve",side_effect=AssertionError("hydrate must not resolve media")),mock.patch.object(Path,"lstat",side_effect=AssertionError("hydrate must not stat media")):
            normalized=target.HMBSoundLibrary._normalize_saved_state(saved)
        self.assertEqual(target.HMBSoundLibrary._track_total(normalized),7)

    def test_atomic_shot_add_uses_catalog_uuid_not_current_tab(self):
        self.node._hmb_reconcile_shot_routing(CATALOG)
        state=self.node._state_sound
        context={"project_uid":state["project_uid"],"channel_uuid":CHANNEL,"shot_uuid":"optimistic-ui-tab","revision":state["revision"]}
        self.command("shot_add",source_uid=state["assets"][0]["source_uid"],shot_uuid=SHOTS[1]["shot_uuid"],context=context)
        state["shot"]={"channel_uuid":CHANNEL,**SHOTS[0]}
        self.drain()
        self.assertEqual(state["tracks"][-1]["shot_uuid"],SHOTS[1]["shot_uuid"])
        with self.assertRaises(helper.SoundError):self.command("shot_add",source_uid=state["assets"][0]["source_uid"],shot_uuid="invented-shot")

    def test_standalone_discovery_chooses_one_and_ambiguity_needs_shot_context(self):
        self.node.set_parameter_value(target.UI,target.default_state(),initial_setup=True)
        row={"project_id":"showA","project_root":str(self.audio)}
        with mock.patch.object(target,"discover_sound_projects",return_value=[row]),mock.patch.object(self.node,"_has_image_peer",return_value=False):
            self.node._discover_standalone_context();self.drain()
        self.assertEqual(self.node._state_sound["project_root"],str(self.audio))
        self.assertEqual(len(self.node._state_sound["assets"]),1)
        scans=self.node._scan_requested_root
        with mock.patch.object(target,"scan_sound_project",side_effect=AssertionError("route echo must not rescan")):
            self.node._activate_sound_context({**row,"catalog":{},"source":None})
        self.assertEqual(self.node._scan_requested_root,scans)
        self.node.set_parameter_value(target.UI,target.default_state(),initial_setup=True)
        self.node._standalone_discovery_started=False
        with mock.patch.object(target,"discover_sound_projects",return_value=[row,{"project_id":"other","project_root":str(self.root/"other"/"Ai_Ct_audio")}]),mock.patch.object(self.node,"_has_image_peer",return_value=False):
            self.node._discover_standalone_context();self.drain()
        self.assertEqual(self.node._state_sound["project_root"],"")
        self.assertEqual(self.node._state_sound["error_code"],"SOUND_CONTEXT_REQUIRED")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    # Do not run the base helper test methods twice through fixture inheritance.
    suite=unittest.TestSuite()
    for cls in (SoundLibraryRegression,SoundNodeRegression):
        for name in cls.__dict__:
            if name.startswith("test_"):suite.addTest(cls(name))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
