"""Sequential checked-video publication without Maya, Blender, graph, or API calls.

Only the validated per-role producers are replaced. The production worker,
catalog append/ownership checks and public VIDEO_OUT/PICKER_OUT builder run.
Tiny local byte fixtures stand in for producer-validated MP4 artifacts; this
test does not assert codec validity or rendered image quality.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
import uuid
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ISOLATED = tempfile.TemporaryDirectory(prefix="hmb-progressive-generation-")
TEMP = Path(ISOLATED.name).resolve()
ENV = mock.patch.dict(os.environ, {name: str(TEMP / name) for name in (
    "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
)})
ENV.start()
spec = importlib.util.spec_from_file_location("hmb_progressive_generation_regression", ROOT / "HMBVideoPickerLibrary.py")
assert spec and spec.loader
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)
try:
    from griptape_nodes.retained_mode.engine import current_engine
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes as SDK
    from griptape_nodes.exe_types.flow import ControlFlow
except ImportError:
    SDK = None
else:
    # Initialize the isolated in-process SDK before the no-render subprocess
    # guard: SDK boot performs a read-only hardware/CUDA capability probe.
    SDK.EventManager().initialize_queue()
ROLES = ("original", "mask", "depth", "motion_guide")
FLAGS = dict(zip(ROLES, ("original_enabled", "mask_enabled", "depth_enabled", "motion_guide_enabled")))


class Scenario:
    def __init__(self, case: str, *, engine="maya", roles=ROLES, failures=(), stop_after="", invalidate_at="", identity="", navigate_at="", duplicate_at="", preview_switch_at=""):
        self.root = TEMP / case
        self.root.mkdir(parents=True)
        self.scene = self.root / ("fixture.blend" if engine == "blender" else "fixture.mb")
        self.scene.write_bytes(b"local-scene-contract-fixture")
        self.engine, self.roles = engine, tuple(roles)
        self.failures, self.stop_after = set(failures), stop_after
        self.invalidate_at, self.identity = invalidate_at, identity
        self.navigate_at, self.duplicate_at = navigate_at, duplicate_at
        self.preview_switch_at = preview_switch_at
        self.expected_preview = None
        self.preview_errors = []
        self.entered, self.completed, self.publications = [], [], []
        self.completed_uids = {}
        self.expected_before = []
        self.stop_sent = False
        self.run_index = 0
        self.node = picker.HMBVideoPickerLibrary(name="Progressive_" + case)
        if SDK is not None:
            flow = ControlFlow(name="ProgressiveFlow_" + case, engine=current_engine())
            flow.add_node(self.node)
            SDK.ObjectManager().add_object_by_name(flow.name, flow)
            SDK.ObjectManager().add_object_by_name(self.node.name, self.node)
            SDK.NodeManager()._name_to_parent_flow_name[self.node.name] = flow.name
        self.node._prepare_run_state = lambda *_a, **_k: None
        state = self.node._picker_state()
        first = copy.deepcopy(state["picker_shots"][0])
        first.update(workspace_uuid=str(uuid.uuid4()), bound_shot_uuid=str(uuid.uuid4()), number=1, name="Shot 1")
        second = copy.deepcopy(first)
        second.update(workspace_uuid=str(uuid.uuid4()), bound_shot_uuid=str(uuid.uuid4()), number=2, name="Shot 2")
        self.owner, self.other = first["workspace_uuid"], second["workspace_uuid"]
        state.update({
            "picker_shots": [first, second], "active_picker_shot_uuid": self.owner,
            "channel_uuid": str(uuid.uuid4()), "scene_path": str(self.scene),
            "scene_request_path": str(self.scene), "scene_draft_path": str(self.scene),
            "native_read_ready": True, "native_metadata": {"scene_path": str(self.scene)},
            "selected_camera": "|shotCam", "camera": "|shotCam", "start_frame": 1.0,
            "end_frame": 2.0, "source_fps": 24.0, "status": "OUTLINER_READY",
            "scene_stage": "OUTLINER_READY", **{flag: role in self.roles for role, flag in FLAGS.items()},
        })
        self.node._store_initial_parameter_value("MAYA_SCENE", str(self.scene))
        self.node._write_state(state)
        # ImageAsset routing is the external owner represented by the captured
        # channel/bound-shot fields above. No real ImageAsset node is attached
        # in this fixture; do not let SDK graph lookup detach those bindings.
        self.node._reconcile_shared_shot_routing = lambda: None
        self.original_cache = self.root / "mutable_original.mp4"
        self.node._render_original_preview_mode = self.original
        self.node._blender_render_original_preview_mode = self.original
        self.node._maya_mode = self.auxiliary
        self.node._blender_mode = self.auxiliary
        self.node._shot_picker_dependency_envelope = lambda *, state_snapshot=None, **_k: {
            "schema": "hmb-picker-shot-routing-catalog", "version": 1,
            "channel_uuid": state_snapshot["channel_uuid"],
            "generation": len(state_snapshot.get("videos", [])) + 1,
            "metadata_sha256": "a" * 64, "media_sha256": "b" * 64,
            "shot_count": len(state_snapshot["picker_shots"]),
        }
        raw_sync = self.node._sync_outputs_from_state

        def sync(state, **kwargs):
            kwargs["propagate_connections"] = False
            result = raw_sync(state, **kwargs)
            payload = json.loads(self.node.parameter_output_values.get("PICKER_OUT", "{}"))
            self.publications.append({"state": copy.deepcopy(state), "payload": payload,
                                      "video_out": copy.deepcopy(self.node.parameter_output_values.get("VIDEO_OUT", []))})
            owner_row = next((row for row in state["picker_shots"] if row["workspace_uuid"] == self.owner), None)
            if state.get("generation_output_roles") and owner_row is not None:
                current_preview = owner_row.get("preview_video_uid")
                if self.expected_preview is None:
                    self.expected_preview = current_preview
                elif current_preview != self.expected_preview:
                    self.preview_errors.append((self.expected_preview, current_preview))
                    raise AssertionError("Later role publication changed the existing/user-selected preview.")
            visible_roles = [item.get("generation_role") for item in state.get("videos", [])]
            if self.stop_after and self.stop_after in visible_roles and not self.stop_sent:
                self.stop_sent = True
                self.node._hmb_cancel_requested.set()
            return result
        self.node._sync_outputs_from_state = sync

    def external_state_write(self, state, *, widget=False):
        """Model the independent UI/routing owner, never a stale worker write."""
        errors = []
        def write():
            try:
                if widget:
                    parameter = picker._get_parameter_obj(self.node, picker.WIDGET_STATE_PARAMETER)
                    value = self.node.before_value_set(parameter, json.dumps(state))
                    self.node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, value)
                    self.node.after_value_set(parameter, value)
                else:
                    self.node._write_state(state)
            except BaseException as exc:
                errors.append(exc)
        owner = threading.Thread(target=write)
        owner.start()
        owner.join(5)
        assert not owner.is_alive(), "External fixture state update deadlocked."
        if errors:
            raise errors[0]

    def begin(self, role, context):
        assert tuple(context.selected_roles) == self.roles, "Freeze click-time choices throughout every producer."
        assert role in self.roles, "Unchecked producer must not run."
        current = self.node._picker_state()
        committed = {item.get("generation_role"): item for item in current.get("videos", [])
                     if item.get("generation_role") in self.completed}
        for done in self.completed:
            if done in self.failures:
                continue
            assert done in committed, f"{done} missing from catalog before {role} starts"
            assert self.publications, f"{done} was never publicly synchronized before {role} starts"
            published = self.publications[-1]
            assert any(item.get("generation_role") == done for item in published["state"].get("videos", [])), f"{done} remains private before {role}"
            if current["active_picker_shot_uuid"] == self.owner:
                assert any(item.get("generation_role") == done for item in published["payload"].get("videos", [])), f"{done} missing in Loader PICKER_OUT before {role}"
                assert committed[done]["video_path"] in published["video_out"], f"{done} missing in Loader VIDEO_OUT before {role}"
            assert Path(committed[done]["video_path"]).is_file()
        self.entered.append(role)
        if self.duplicate_at == role:
            self.duplicate_at = ""
            self.node._start_ui_operation("run_video", self.node._picker_state())
        if self.navigate_at == role:
            state = picker._activate_picker_workspace_projection(self.node._picker_state(), self.other)
            self.external_state_write(state, widget=True)
        if self.preview_switch_at == role:
            state = self.node._picker_state()
            chosen = next(item["video_uid"] for item in state["videos"] if item.get("generation_role") == "mask")
            state.update(preview_video_uid=chosen, selected_video_uid=chosen, selected_video_slot=2, preview_frame=1.0)
            for row in state["picker_shots"]:
                if row["workspace_uuid"] == self.owner:
                    row.update(preview_video_uid=chosen, selected_video_slot=2, preview_frame=1.0,
                               revision=int(row.get("revision", 0)) + 1)
            self.expected_preview = chosen
            self.external_state_write(state, widget=True)
        if self.invalidate_at == role:
            state = self.node._picker_state()
            if self.identity == "channel":
                state["channel_uuid"] = str(uuid.uuid4())
            elif self.identity == "binding":
                for row in state["picker_shots"]:
                    if row["workspace_uuid"] == self.owner:
                        row["bound_shot_uuid"] = str(uuid.uuid4())
            elif self.identity == "removed_shot":
                state["picker_shots"] = [row for row in state["picker_shots"] if row["workspace_uuid"] != self.owner]
                state["active_picker_shot_uuid"] = self.other
            self.external_state_write(state)
        if role in self.failures:
            raise RuntimeError("controlled " + role + " producer failure")

    def original(self, _scene, *, context, publish_public):
        assert publish_public is False
        self.begin("original", context)
        self.original_cache.write_bytes(b"validated-original-" + str(self.run_index).encode())
        metadata = {"schema": "hmb-original-playblast", "camera": "|shotCam", "start_frame": 1,
                    "end_frame": 2, "fps": 24, "frame_count": 2, "resolution": {"width": 1280, "height": 720}}
        self.original_cache.with_suffix(".hmb.json").write_text(json.dumps(metadata), encoding="utf-8")
        state = self.node._picker_state()
        state.update(original_video_path=str(self.original_cache), original_video_url=self.original_cache.as_uri(), original_metadata=metadata)
        self.node._write_state(state)
        self.completed.append("original")
        return {"mode": "original_preview_cache", "cached": False}

    def auxiliary(self, _scene, _slot, *, context, publish_public, selected_role=None):
        assert publish_public is False
        assert selected_role in ("mask", "depth", "motion_guide"), "Each worker invocation must own exactly one checked output."
        self.begin(selected_role, context)
        path = self.root / f"{self.run_index}-{selected_role}.mp4"
        path.write_bytes(("validated-" + selected_role + "-" + str(self.run_index)).encode())
        kinds = {
            "mask": picker.BLENDER_MASK_MEDIA_KIND if self.engine == "blender" else picker.MASK_MEDIA_KIND,
            "depth": picker.BLENDER_DEPTH_MEDIA_KIND if self.engine == "blender" else picker.DEPTH_MEDIA_KIND,
            "motion_guide": picker.BLENDER_MOTION_GUIDE_MEDIA_KIND if self.engine == "blender" else picker.MOTION_GUIDE_MEDIA_KIND,
        }
        run_id = context.operation_id + "-" + selected_role
        item = {"video_path": str(path), "video_url": path.as_uri(), "generation_role": selected_role,
                "media_kind": kinds[selected_role], "source_fps": 24, "source_frame_count": 2,
                "run_id": run_id, "bundle_run_id": run_id, "scene_engine": self.engine}
        self.completed.append(selected_role)
        return {"video": str(path) if selected_role == "mask" else "",
                "depth_video": str(path) if selected_role == "depth" else "",
                "motion_guide_video": str(path) if selected_role == "motion_guide" else "",
                "depth_succeeded": selected_role == "depth", "motion_guide_succeeded": selected_role == "motion_guide",
                "run_id": run_id, "bundle_run_id": run_id, "generated_item": item}

    def run(self):
        self.run_index += 1
        self.entered, self.completed = [], []
        self.expected_preview, self.preview_errors = None, []
        state = self.node._picker_state()
        state["backend_ack_action_id"] = "progressive-" + uuid.uuid4().hex
        self.node._start_ui_operation("run_video", state)
        assert not self.node._hmb_process_lock.locked()
        assert self.node._hmb_active_operation is None
        assert not self.preview_errors, self.preview_errors
        return self.node._picker_state()


class ProgressiveSelectedGenerationRegression(unittest.TestCase):
    def setUp(self):
        self.patches = mock.patch.multiple(picker,
            _request_parameter_value=lambda *_a, **_k: False,
            _video_asset_thumbnail_url=lambda *_a, **_k: ("", ""),
            _external_media_url=lambda path: Path(path).resolve().as_uri(),
            _notify_parameter_update=lambda *_a, **_k: None,
            _propagate_parameter_update_to_connections=lambda *_a, **_k: None,
        )
        self.patches.start()
        self.network = mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.processes = mock.patch.object(picker.subprocess, "Popen", side_effect=AssertionError("DCC/media process forbidden"))
        self.processes.start()

    def tearDown(self):
        self.processes.stop()
        self.network.stop()
        self.patches.stop()

    def test_each_completed_role_is_public_before_next_role_for_both_engines(self):
        for engine in ("maya", "blender"):
            with self.subTest(engine=engine):
                case = Scenario("ordered-" + engine, engine=engine)
                result = case.run()
                self.assertEqual(case.entered, list(ROLES), result.get("message"))
                self.assertEqual([item.get("generation_role") for item in result["videos"]], list(ROLES))
                self.assertEqual(result["generation_output_roles"], list(ROLES))
                self.assertEqual(len({item["video_uid"] for item in result["videos"]}), 4)
                self.assertTrue(all(item["picker_shot_uuid"] == case.owner for item in result["videos"]))

    def test_auxiliary_only_does_not_generate_unchecked_mask(self):
        for engine in ("maya", "blender"):
            case = Scenario("aux-only-" + engine, engine=engine, roles=("depth", "motion_guide"))
            result = case.run()
            self.assertEqual(case.entered, ["depth", "motion_guide"], result.get("message"))
            self.assertEqual([item["generation_role"] for item in result["videos"]], case.entered)

    def test_failure_of_each_role_continues_later_roles_once(self):
        for failed in ROLES:
            case = Scenario("failure-" + failed, failures=(failed,))
            result = case.run()
            self.assertEqual(case.entered, list(ROLES), result.get("message"))
            self.assertEqual([item["generation_role"] for item in result["videos"]], [role for role in ROLES if role != failed])
            self.assertTrue(any(failed.replace("_", " ") in str(value).lower() or failed in str(value).lower()
                                for value in [result.get("message", ""), *result.get("warnings", [])]))
            self.assertTrue(all(Path(item["video_path"]).is_file() for item in result["videos"]))

    def test_stop_keeps_completed_original_and_never_starts_mask(self):
        for index, role in enumerate(ROLES):
            case = Scenario("stop-after-" + role, stop_after=role)
            result = case.run()
            self.assertEqual(case.entered, list(ROLES[:index + 1]), result.get("message"))
            self.assertEqual([item["generation_role"] for item in result["videos"]], list(ROLES[:index + 1]))
            self.assertTrue(all(Path(item["video_path"]).is_file() for item in result["videos"]))

    def test_all_role_failures_do_not_retry_or_publish(self):
        case = Scenario("all-failed", failures=ROLES)
        existing = case.root / "existing-manual.mp4"
        existing.write_bytes(b"untouched-existing-manual")
        case.node._write_state(picker._append_video_asset(case.node._picker_state(), {
            "video_uid": "existing-manual", "video_path": str(existing), "video_url": existing.as_uri(),
            "label": "Existing Manual",
        }, picker_shot_uuid=case.owner, defer_thumbnail=True))
        result = case.run()
        self.assertEqual(case.entered, list(ROLES), result.get("message"))
        self.assertEqual([item["video_uid"] for item in result["videos"]], ["existing-manual"])
        self.assertEqual(existing.read_bytes(), b"untouched-existing-manual")
        self.assertFalse(any(item.get("generation_role") for item in result["videos"]))

    def test_original_immutable_catalog_copy_failure_continues_other_roles(self):
        case = Scenario("original-copy-failed")
        def reject_copy(*_args, **_kwargs):
            case.failures.add("original")
            raise RuntimeError("immutable Original catalog copy failed")
        with mock.patch.object(picker, "_snapshot_original_preview_asset", side_effect=reject_copy):
            result = case.run()
        self.assertEqual(case.entered, list(ROLES), result.get("message"))
        self.assertEqual([item["generation_role"] for item in result["videos"]], list(ROLES[1:]))
        self.assertTrue(case.original_cache.is_file())
        self.assertFalse(any(item["video_path"] == str(case.original_cache) for item in result["videos"]))

    def test_late_identity_change_rejects_new_role(self):
        for identity in ("channel", "binding", "removed_shot"):
            with self.subTest(identity=identity):
                case = Scenario("stale-" + identity, invalidate_at="mask", identity=identity)
                result = case.run()
                self.assertEqual(case.entered, ["original", "mask"], str((result.get("message"), result.get("warnings"))))
                self.assertFalse(any(item.get("generation_role") == "mask" for item in result["videos"]), result.get("message"))

    def test_navigation_keeps_click_time_owner(self):
        case = Scenario("navigation", navigate_at="mask")
        result = case.run()
        self.assertEqual(case.entered, list(ROLES), result.get("message"))
        self.assertEqual(result["active_picker_shot_uuid"], case.other)
        self.assertTrue(all(item["picker_shot_uuid"] == case.owner for item in result["videos"]))

    def test_user_preview_change_is_preserved_by_later_publications(self):
        case = Scenario("user-preview", preview_switch_at="depth")
        result = case.run()
        self.assertEqual(case.entered, list(ROLES), result.get("message"))
        expected = next(item["video_uid"] for item in result["videos"] if item["generation_role"] == "mask")
        self.assertEqual(result["preview_video_uid"], expected)
        self.assertEqual(result["preview_frame"], 1.0)

    def test_duplicate_active_click_does_not_duplicate_generation(self):
        case = Scenario("duplicate", duplicate_at="mask")
        result = case.run()
        self.assertEqual(case.entered, list(ROLES), result.get("message"))
        self.assertEqual(len(result["videos"]), 4)

    def test_explicit_rerun_appends_once_and_keeps_original_media_immutable(self):
        case = Scenario("rerun")
        first = case.run()
        self.assertEqual(len(first["videos"]), 4, first.get("message"))
        old_bytes = {item["video_path"]: Path(item["video_path"]).read_bytes() for item in first["videos"]}
        second = case.run()
        self.assertEqual(len(second["videos"]), 8, second.get("message"))
        self.assertEqual(len({item["video_uid"] for item in second["videos"]}), 8)
        self.assertEqual(len({item["video_path"] for item in second["videos"]}), 8)
        for path, content in old_bytes.items():
            self.assertEqual(Path(path).read_bytes(), content)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        ENV.stop()
        ISOLATED.cleanup()
