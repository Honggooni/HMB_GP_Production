from pathlib import Path
import copy
import hashlib
import importlib.util
import io
import json
import queue
import random
import sys
import tempfile
import threading
import time
import types

from _hmb_private_policy_fixture import install_private_policy_reader


ROOT = Path(__file__).resolve().parents[2]


def load(name, path=None):
    module_path = Path(path or (ROOT / f"{name}.py"))
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def wait_for(predicate, timeout=2.0, message="condition was not met"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def install_engine_hooks(node):
    """Model Griptape's before/store/after parameter transaction locally."""
    raw_set = node.set_parameter_value
    raw_write_state = node._write_state

    def local_write_state(state):
        request_parameter_value = picker._request_parameter_value
        picker._request_parameter_value = lambda *_args, **_kwargs: False
        try:
            return raw_write_state(state)
        finally:
            picker._request_parameter_value = request_parameter_value

    node._write_state = local_write_state

    def engine_set(
        name,
        value,
        *,
        initial_setup=False,
        emit_change=True,
        skip_before_value_set=False,
    ):
        if initial_setup:
            return raw_set(
                name,
                value,
                initial_setup=True,
                emit_change=emit_change,
                skip_before_value_set=skip_before_value_set,
            )
        parameter = picker._get_parameter_obj(node, name)
        assert parameter is not None, name
        final_value = value if skip_before_value_set else node.before_value_set(parameter, value)
        raw_set(name, final_value)
        node.after_value_set(parameter, final_value)
        return final_value

    node.set_parameter_value = engine_set
    return node


def send_command(node, action, action_id, payload=None, runtime_id=None):
    command = picker._default_picker_command(
        node._hmb_runtime_instance_id if runtime_id is None else runtime_id
    )
    command.update({
        "action": action,
        "action_id": action_id,
        "issued_at_ms": int(time.time() * 1000),
        "payload": dict(payload or {}),
    })
    return node.set_parameter_value(picker.WIDGET_COMMAND_PARAMETER, command)


common = load("_hmb_common")
picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")
agent = load("HMBAgentLibrary")
_original_policy_reader, signed_policy_fixture = install_private_policy_reader(common)
if agent._hmb is not common:
    install_private_policy_reader(agent._hmb)

assert prompt.PICKER_DEPTH_PROFILE == picker.DEPTH_PLAYBLAST_PROFILE
assert picker.DEPTH_PLAYBLAST_PROFILE == "hmb_camera_space_depth_v7"

# Generate Playblast owns the only execution trigger. Four inert choices pack
# their validated results in Original -> Mask -> Depth -> Motion Guide order.
legacy_generation_state = picker._parse_state({"schema": "maya-video-picker-state"})
assert legacy_generation_state["original_enabled"] is False
assert legacy_generation_state["mask_enabled"] is True
assert picker._generation_choice_roles(legacy_generation_state) == ["mask"]

four_choice_state = picker._default_widget_state()
four_choice_state.update({
    "original_enabled": True,
    "mask_enabled": True,
    "depth_enabled": True,
    "motion_guide_enabled": True,
    "original_video_path": "C:/show/shot/shot_Original.mp4",
    "original_video_url": "file:///shot_Original.mp4",
    "original_metadata": {
        "camera": "|cam",
        "start_frame": 1,
        "end_frame": 24,
        "fps": 24,
        "frame_count": 24,
        "resolution": {"width": 1280, "height": 720},
    },
})
original_item = picker._original_video_item_from_state(four_choice_state)
mask_item = {
    "video_slot": 1,
    "video_path": "C:/show/shot/shot_playblast_1.mp4",
    "run_id": "mask-run",
    "source_fps": 24,
    "source_frame_count": 24,
}
four_choice_state["run_id"] = "mask-run"
four_choice_state["video_path"] = mask_item["video_path"]
assert picker._is_generated_mask_video_item(mask_item) is False
assert picker._is_generated_mask_video_item(mask_item, four_choice_state) is True
depth_item = {
    "video_slot": 2,
    "video_path": "C:/show/shot/shot_depth_playblast_2.mp4",
    "media_kind": picker.DEPTH_MEDIA_KIND,
    "video_role": "maya_depth_companion",
    "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
    "source_video_slot": 1,
}
motion_item = {
    "video_slot": 3,
    "video_path": "C:/show/shot/shot_motion_guide_3.mp4",
    "media_kind": picker.MOTION_GUIDE_MEDIA_KIND,
    "video_role": "maya_motion_guide_companion",
    "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
    "source_video_slot": 1,
}
manual_item = {
    "video_slot": 4,
    "video_path": "C:/show/shot/manual.mp4",
    "label": "Manual",
}
four_choice_state["videos"] = [mask_item, depth_item, motion_item, manual_item]
four_choice_state["slot_assignments"] = [
    {
        "video_slot": 1,
        "bindings": [{"full_dag_path": "|mask", "color": "Blue"}],
    },
    {
        "video_slot": 4,
        "bindings": [{"full_dag_path": "|manual", "color": "Red"}],
    },
]
packed = picker._pack_selected_generation_videos(
    four_choice_state,
    {
        "original": original_item,
        "mask": mask_item,
        "depth": depth_item,
        "motion_guide": motion_item,
    },
)
assert [item["video_path"] for item in packed["videos"][:4]] == [
    mask_item["video_path"],
    depth_item["video_path"],
    motion_item["video_path"],
    manual_item["video_path"],
]
assert [item.get("generation_role") for item in packed["videos"][4:]] == [
    "original", "mask", "depth", "motion_guide",
]
assert [item["video_slot"] for item in packed["videos"]] == list(range(1, 9))
assert len({item["video_uid"] for item in packed["videos"]}) == 8
assert packed["videos"][3]["label"] == "Manual"
assert [
    row["video_slot"]
    for row in packed["slot_assignments"]
    if row["bindings"]
] == [1, 4]
assert packed["mask_authoring_slot"] == 1
assert picker._slot_assignment_bindings(packed, picker._mask_authoring_slot(packed))[0][
    "full_dag_path"
] == "|mask"
new_mask_uid = packed["videos"][5]["video_uid"]
assert packed["videos"][6]["source_video_uid"] == new_mask_uid
assert packed["videos"][7]["source_video_uid"] == new_mask_uid
packed_payload, packed_media = picker._build_synchronized_video_outputs(packed)
assert packed_payload["schema_version"] == 5
assert len(packed_payload["videos"]) == len(packed_media) == 8
assert packed_payload["videos"][6]["source_video_slot"] == 6
assert packed_payload["videos"][7]["source_video_slot"] == 6
packed_view_state = copy.deepcopy(packed)
packed_view_state["original_preview_enabled"] = False
packed_view_state["selected_video_slot"] = 6
picker_view_probe = object.__new__(picker.HMBVideoPickerLibrary)
packed_mask_view = picker_view_probe._apply_selected_view_fields(packed_view_state)
assert packed_mask_view["video_path"] == mask_item["video_path"]
assert packed_mask_view["video_path"] != original_item["video_path"]

# The generator now receives one synchronized list. There are no per-slot
# public media outputs to reconnect or drift out of order.
assert picker.VIDEO_OUTPUT_PARAMETER == "VIDEO_OUT"
assert not hasattr(picker.HMBVideoPickerLibrary, "_connect_generated_display_videos")

depth_only_state = copy.deepcopy(four_choice_state)
depth_only_state.update({
    "original_enabled": False,
    "mask_enabled": False,
    "depth_enabled": True,
    "motion_guide_enabled": False,
})
depth_only = picker._pack_selected_generation_videos(
    depth_only_state,
    {"depth": depth_item},
)
assert len(depth_only["videos"]) == 5
assert depth_only["videos"][-1]["generation_role"] == "depth"
assert depth_only["videos"][-1]["video_slot"] == 5
assert depth_only["videos"][-1]["source_video_uid"] == ""
assert depth_only["videos"][-1]["companion_video_uid"] == ""

# PICKER_OUT must retain explicit no-Mask provenance.  Omitting zero would let
# PromptLibrary mistake a Depth/Motion slot for a legacy Mask companion.
picker_payload_probe = object.__new__(picker.HMBVideoPickerLibrary)
depth_only_payload = picker_payload_probe._build_picker_payload(depth_only)
packed_depth_payload = depth_only_payload["videos"][-1]
assert packed_depth_payload["source_video_slot"] == 0
assert packed_depth_payload["companion_of_video_slot"] == 0

# A manual video that merely resembles a legacy renderer filename is not
# disposable.  Legacy ownership requires both the same run and an exact match
# to the containing state's top-level current video path.
manual_lookalike = {
    "video_slot": 1,
    "video_path": "C:/manual/editorial_playblast_1.mp4",
    "run_id": "manual-run",
    "label": "Manual Lookalike",
}
manual_lookalike_state = picker._default_widget_state()
manual_lookalike_state.update({
    "original_enabled": True,
    "mask_enabled": False,
    "depth_enabled": False,
    "motion_guide_enabled": False,
    "run_id": "manual-run",
    "video_path": "C:/manual/different_selected_video.mp4",
    "videos": [manual_lookalike],
})
assert picker._is_generated_mask_video_item(
    manual_lookalike,
    manual_lookalike_state,
) is False
lookalike_pack = picker._pack_selected_generation_videos(
    manual_lookalike_state,
    {"original": original_item},
)
assert [item.get("label") for item in lookalike_pack["videos"]] == [
    "Manual Lookalike", "Original Playblast",
]

# Internal legacy Mask staging may temporarily overwrite a manual @video1.
# The pre-generation snapshot remains the manual authority and is appended
# after successful generated outputs without data loss.
staging_state = copy.deepcopy(manual_lookalike_state)
staging_state.update({
    "original_enabled": False,
    "mask_enabled": True,
    "video_path": mask_item["video_path"],
    "run_id": "mask-run",
    "videos": [mask_item],
})
manual_source_pack = picker._pack_selected_generation_videos(
    staging_state,
    {"mask": mask_item},
    manual_source_state=manual_lookalike_state,
)
assert [item.get("generation_role") for item in manual_source_pack["videos"]] == [
    None, "mask",
]
assert manual_source_pack["videos"][0]["label"] == "Manual Lookalike"

# Mask authoring controls stay on slot 1 regardless of catalog presentation
# order; unrelated transient video positions do not perturb render identity.
digest_scene = "C:/show/shot/scene.mb"
mask_digest = picker._operation_input_digest("run_video", digest_scene, packed, 1)
changed_mask_controls = copy.deepcopy(packed)
next(
    row for row in changed_mask_controls["slot_assignments"]
    if int(row.get("video_slot") or 0) == 1
)["bindings"][0]["color"] = "Red"
assert picker._operation_input_digest(
    "run_video", digest_scene, changed_mask_controls, 1,
) != mask_digest
changed_original_controls = copy.deepcopy(packed)
next(
    row for row in changed_original_controls["slot_assignments"]
    if int(row.get("video_slot") or 0) == 2
)["bindings"] = [{
    "full_dag_path": "|presentation-only", "color": "Green",
}]
assert picker._operation_input_digest(
    "run_video", digest_scene, changed_original_controls, 1,
) == mask_digest
operation_probe = object.__new__(picker.HMBVideoPickerLibrary)
packed_context = operation_probe._create_operation_context(
    # Context creation starts *before* the four generated outputs are appended.
    # Refeeding the already-packed eight-item terminal state would correctly
    # reserve another four outputs and exceed the Shot's ten-asset capacity.
    "run_video", digest_scene, four_choice_state, 1,
)
assert packed_context.mask_authoring_slot == 1
no_output_state = picker._default_widget_state()
no_output_state.update({
    "original_enabled": False,
    "mask_enabled": False,
    "depth_enabled": False,
    "motion_guide_enabled": False,
})
try:
    operation_probe._create_operation_context(
        "run_video", digest_scene, no_output_state, 1,
    )
except ValueError as exc:
    assert "at least one checked output" in str(exc)
else:
    raise AssertionError("Backend accepted Generate with no selected output.")

# The real multi-stage Generate path freezes the four accepted choices. A
# successful Original snapshot and the shared Mask/Depth/Motion stage must
# reach one final four-role commit even if a private stage mutates its working
# copy of a choice flag.
def install_direct_picker_state_writes(node):
    raw_write_state = node._write_state

    def direct_write_state(state):
        request_parameter_value = picker._request_parameter_value
        picker._request_parameter_value = lambda *_args, **_kwargs: False
        try:
            return raw_write_state(state)
        finally:
            picker._request_parameter_value = request_parameter_value

    node._write_state = direct_write_state
    return node


with tempfile.TemporaryDirectory() as orchestration_temp_text:
    orchestration_temp = Path(orchestration_temp_text)
    orchestration_scene = orchestration_temp / "four_outputs.mb"
    orchestration_scene.write_bytes(b"maya-scene-probe")
    original_cache = orchestration_temp / "validated_original.mp4"
    original_cache.write_bytes(b"validated-original")
    original_cache.with_suffix(".hmb.json").write_text(
        json.dumps({
            "schema": "hmb-original-playblast",
            "camera": "|shotCam",
            "start_frame": 1,
            "end_frame": 2,
            "fps": 24,
            "frame_count": 2,
            "resolution": {"width": 1280, "height": 720},
        }),
        encoding="utf-8",
    )
    orchestration_node = install_direct_picker_state_writes(
        picker.HMBVideoPickerLibrary(name="four_role_orchestration")
    )
    orchestration_syncs = []
    orchestration_node._sync_outputs_from_state = (
        lambda state: orchestration_syncs.append(copy.deepcopy(state)) or ""
    )
    orchestration_state = orchestration_node._picker_state()
    orchestration_state.update({
        "scene_path": str(orchestration_scene),
        "scene_request_path": str(orchestration_scene),
        "scene_draft_path": str(orchestration_scene),
        "native_read_ready": True,
        "selected_camera": "|shotCam",
        "camera": "|shotCam",
        "start_frame": 1.0,
        "end_frame": 2.0,
        "source_fps": 24.0,
        "original_enabled": True,
        "mask_enabled": True,
        "depth_enabled": True,
        "motion_guide_enabled": True,
        "backend_ack_action_id": "four-role-success",
    })
    orchestration_node._write_state(orchestration_state)

    def successful_original_stage(*_args, **_kwargs):
        stage_state = orchestration_node._picker_state()
        stage_state.update({
            "original_video_path": str(original_cache),
            "original_video_url": original_cache.as_uri(),
            "original_metadata": {
                "camera": "|shotCam",
                "start_frame": 1,
                "end_frame": 2,
                "fps": 24,
                "frame_count": 2,
                "resolution": {"width": 1280, "height": 720},
            },
            # A private stage must not redefine the accepted Generate choices.
            "original_enabled": False,
        })
        orchestration_node._write_state(stage_state)
        return {"mode": "original_preview_cache", "cached": True}

    orchestration_node._render_original_preview_mode = successful_original_stage
    orchestration_node._prepare_run_state = lambda *_args, **_kwargs: None

    def successful_core_stage(*_args, **_kwargs):
        stage_state = orchestration_node._picker_state()
        for role, path, media_kind in (
            ("mask", orchestration_temp / "mask.mp4", picker.MASK_MEDIA_KIND),
            ("depth", orchestration_temp / "depth.mp4", picker.DEPTH_MEDIA_KIND),
            (
                "motion_guide",
                orchestration_temp / "motion.mp4",
                picker.MOTION_GUIDE_MEDIA_KIND,
            ),
        ):
            item = {
                "video_path": str(path),
                "video_url": path.as_uri(),
                "generation_role": role,
                "media_kind": media_kind,
                "source_fps": 24,
                "source_frame_count": 2,
            }
            stage_state = picker._append_video_asset(stage_state, item)
        orchestration_node._write_state(stage_state)
        return {"depth_succeeded": True, "motion_guide_succeeded": True}

    orchestration_node._maya_mode = successful_core_stage
    orchestration_node._start_ui_operation(
        "run_video",
        orchestration_node._picker_state(),
    )
    orchestration_result = orchestration_node._picker_state()
    assert [
        item.get("generation_role")
        for item in orchestration_result["videos"]
    ] == ["original", "mask", "depth", "motion_guide"]
    assert picker._generation_choice_roles(orchestration_result) == [
        "original", "mask", "depth", "motion_guide",
    ]
    assert orchestration_result["generation_output_roles"] == [
        "original", "mask", "depth", "motion_guide",
    ]
    assert len(orchestration_syncs) == 1

    # A selected Original failure is terminal. The shared core stage must not
    # run and no subset of the remaining three checked roles may be published.
    failure_node = install_direct_picker_state_writes(
        picker.HMBVideoPickerLibrary(name="original_failure_no_partial")
    )
    failure_syncs = []
    failure_node._sync_outputs_from_state = (
        lambda state: failure_syncs.append(copy.deepcopy(state)) or ""
    )
    failure_state = failure_node._picker_state()
    failure_state.update({
        "scene_path": str(orchestration_scene),
        "scene_request_path": str(orchestration_scene),
        "scene_draft_path": str(orchestration_scene),
        "native_read_ready": True,
        "selected_camera": "|shotCam",
        "camera": "|shotCam",
        "start_frame": 1.0,
        "end_frame": 2.0,
        "source_fps": 24.0,
        "original_enabled": True,
        "mask_enabled": True,
        "depth_enabled": True,
        "motion_guide_enabled": True,
        "backend_ack_action_id": "four-role-original-failure",
        "videos": [{
            "video_path": str(orchestration_temp / "existing_manual.mp4"),
            "video_url": (orchestration_temp / "existing_manual.mp4").as_uri(),
            "label": "Existing Manual",
        }],
    })
    failure_node._write_state(failure_state)
    core_calls = []

    def failed_original_stage(*_args, **_kwargs):
        raise RuntimeError("simulated Original renderer failure")

    failure_node._render_original_preview_mode = failed_original_stage
    failure_node._prepare_run_state = lambda *_args, **_kwargs: core_calls.append(
        "prepare"
    )
    failure_node._maya_mode = lambda *_args, **_kwargs: core_calls.append(
        "maya"
    )
    failure_node._start_ui_operation("run_video", failure_node._picker_state())
    failure_result = failure_node._picker_state()
    assert failure_result["status"] == "FAILED"
    assert core_calls == []
    assert [item.get("label") for item in failure_result["videos"]] == [
        "Existing Manual"
    ]
    assert not any(
        item.get("generation_role")
        for item in failure_result["videos"]
    )
    assert "did not publish a partial Mask/Depth/Motion result" in failure_result[
        "message"
    ]
    assert failure_syncs == []

    # Snapshotting is part of the same mandatory Original stage. A renderer
    # success followed by an immutable-snapshot failure must be just as
    # terminal as a renderer failure, with no core work or partial publish.
    snapshot_failure_node = install_direct_picker_state_writes(
        picker.HMBVideoPickerLibrary(name="original_snapshot_failure_no_partial")
    )
    snapshot_failure_syncs = []
    snapshot_failure_node._sync_outputs_from_state = (
        lambda state: snapshot_failure_syncs.append(copy.deepcopy(state)) or ""
    )
    snapshot_failure_state = snapshot_failure_node._picker_state()
    snapshot_failure_state.update({
        "scene_path": str(orchestration_scene),
        "scene_request_path": str(orchestration_scene),
        "scene_draft_path": str(orchestration_scene),
        "native_read_ready": True,
        "selected_camera": "|shotCam",
        "camera": "|shotCam",
        "start_frame": 1.0,
        "end_frame": 2.0,
        "source_fps": 24.0,
        "original_enabled": True,
        "mask_enabled": True,
        "depth_enabled": True,
        "motion_guide_enabled": True,
        "backend_ack_action_id": "four-role-original-snapshot-failure",
        "videos": [{
            "video_path": str(orchestration_temp / "existing_snapshot_manual.mp4"),
            "video_url": (
                orchestration_temp / "existing_snapshot_manual.mp4"
            ).as_uri(),
            "label": "Existing Snapshot Manual",
        }],
    })
    snapshot_failure_node._write_state(snapshot_failure_state)
    snapshot_core_calls = []
    snapshot_failure_node._render_original_preview_mode = (
        lambda *_args, **_kwargs: {"mode": "original_preview_cache"}
    )
    snapshot_failure_node._prepare_run_state = (
        lambda *_args, **_kwargs: snapshot_core_calls.append("prepare")
    )
    snapshot_failure_node._maya_mode = (
        lambda *_args, **_kwargs: snapshot_core_calls.append("maya")
    )
    original_snapshot_helper = picker._snapshot_original_preview_asset

    def failed_original_snapshot(*_args, **_kwargs):
        raise RuntimeError("simulated Original snapshot failure")

    picker._snapshot_original_preview_asset = failed_original_snapshot
    try:
        snapshot_failure_node._start_ui_operation(
            "run_video",
            snapshot_failure_node._picker_state(),
        )
    finally:
        picker._snapshot_original_preview_asset = original_snapshot_helper
    snapshot_failure_result = snapshot_failure_node._picker_state()
    assert snapshot_failure_result["status"] == "FAILED"
    assert snapshot_core_calls == []
    assert [
        item.get("label") for item in snapshot_failure_result["videos"]
    ] == ["Existing Snapshot Manual"]
    assert not any(
        item.get("generation_role")
        for item in snapshot_failure_result["videos"]
    )
    assert "did not publish a partial Mask/Depth/Motion result" in (
        snapshot_failure_result["message"]
    )
    assert "simulated Original snapshot failure" in snapshot_failure_result[
        "message"
    ]
    assert snapshot_failure_syncs == []

# Private multi-stage generation may write its staging state, but it must not
# publish VIDEO/PICKER outputs until the final packed commit.
atomic_probe = object.__new__(picker.HMBVideoPickerLibrary)
atomic_writes = []
atomic_sync_calls = []
atomic_probe._apply_selected_view_fields = lambda state: state
atomic_probe._write_state = lambda state: atomic_writes.append(copy.deepcopy(state))
atomic_probe._sync_outputs_from_state = lambda state: atomic_sync_calls.append(state)
atomic_result = atomic_probe._publish_outputs({
    "active_slot_count": 1,
    "selected_video_slot": 1,
    "operation_kind": "run_video",
    "markers": [],
    "videos": [],
    "video_path": "C:/private/staging_mask.mp4",
    "video_url": "file:///private/staging_mask.mp4",
    "warnings": [],
}, 1, publish_public=False)
assert atomic_result == ""
assert len(atomic_writes) == 1
assert atomic_writes[0]["operation_kind"] == "run_video"
assert atomic_sync_calls == []

# Stable VIDEO_OUT parameters must be published above the custom dashboard.
# Griptape only mirrors ordering changes to the desktop when its official
# reorder_elements() API is used; directly rearranging root._children is local.
class _OrderChild:
    def __init__(self, name):
        self.name = name


class _OrderRoot:
    def __init__(self, names):
        self.children = [_OrderChild(name) for name in names]


class _OrderNode:
    def __init__(self):
        self.root_ui_element = _OrderRoot([
            "PICKER_OUT",
            "MAYA_SCENE",
            picker.WIDGET_COMMAND_PARAMETER,
            picker.WIDGET_STATE_PARAMETER,
            "VIDEO_OUT",
        ])
        self.parameters = {}
        self.reorder_calls = []

    def reorder_elements(self, names):
        self.reorder_calls.append(list(names))
        by_name = {child.name: child for child in self.root_ui_element.children}
        self.root_ui_element.children[:] = [by_name[name] for name in names]


order_node = _OrderNode()
picker._reorder_video_picker_parameters(order_node, 2)
assert order_node.reorder_calls == [[
    "PICKER_OUT",
    "VIDEO_OUT",
    "MAYA_SCENE",
    picker.WIDGET_COMMAND_PARAMETER,
    picker.WIDGET_STATE_PARAMETER,
]]
assert [child.name for child in order_node.root_ui_element.children] == [
    "PICKER_OUT",
    "VIDEO_OUT",
    "MAYA_SCENE",
    picker.WIDGET_COMMAND_PARAMETER,
    picker.WIDGET_STATE_PARAMETER,
]

# ---------------------------------------------------------------------------
# Package, Agent freeze, policy, and custom-widget lifecycle contracts.
# ---------------------------------------------------------------------------
manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
assert manifest["metadata"]["library_version"] == "0.7.11"
assert "TypedAuxiliaryVideoAssets" in manifest["metadata"]["tags"]
assert "Pillow==12.3.0" in manifest["metadata"]["dependencies"]["pip_dependencies"]
registered_widgets = {item["name"] for item in manifest.get("widgets", [])}
assert registered_widgets == {
    "HMBAgentLibraryWidget",
    "HMBImageAssetLibraryWidget",
    "HMBImageAssetThumbnailPatchBridgeWidget",
    "HMBPromptLibraryScopedBindingWidget",
    "HMBSeedanceGenerationWidget",
    "HMBVideoPickerCommandBridgeWidget",
    "HMBVideoPickerLibraryWidget",
}
assert (ROOT / "widgets/HMBImageAssetThumbnailPatchBridgeWidget.js").is_file()
assert (ROOT / "widgets/HMBVideoPickerCommandBridgeWidget_v032.js").is_file()
assert (ROOT / "widgets/HMBSeedanceGenerationWidget.js").is_file()
obsolete_picker_widgets = (
    "HMBVideoPickerLibraryWidget.js",
    "HMBVideoPickerLibraryWidget_v028.js",
    "HMBVideoPickerLibraryWidget_v029.js",
    "HMBVideoPickerCommandBridgeWidget_v028.js",
    "HMBVideoPickerCommandBridgeWidget_v029.js",
    "HMBVideoPickerLibraryWidget_v030.js",
    "HMBVideoPickerCommandBridgeWidget_v030.js",
    "HMBVideoPickerLibraryWidget_v031.js",
    "HMBVideoPickerCommandBridgeWidget_v031.js",
)
assert not [
    name for name in obsolete_picker_widgets
    if (ROOT / "widgets" / name).exists()
], "Release source must contain only the active v032 Picker widgets."
assert next(
    item for item in manifest["widgets"]
    if item["name"] == "HMBVideoPickerCommandBridgeWidget"
)["path"] == "widgets/HMBVideoPickerCommandBridgeWidget_v032.js"

picker_manifest = next(item for item in manifest["nodes"] if item["class_name"] == "HMBVideoPickerLibrary")
prompt_manifest = next(item for item in manifest["nodes"] if item["class_name"] == "HMBPromptLibrary")
assert picker_manifest["metadata"]["width"] == 1400
assert prompt_manifest["metadata"]["width"] == 1800
assert picker_manifest["metadata"]["height"] == 360
assert prompt_manifest["metadata"]["height"] == 1193
for prompt_height_key in (
    "height", "default_height", "initial_height", "min_height",
):
    assert prompt_manifest["metadata"][prompt_height_key] == 1193
for prompt_height_key in (
    "height", "default_height", "preferred_height", "initial_height", "min_height",
):
    assert prompt_manifest["metadata"]["ui_options"][prompt_height_key] == 1193
assert prompt.PROMPT_NATIVE_ASSET_INPUT_ROW_HEIGHT == 0
assert prompt.PROMPT_START_HEIGHT == prompt.PROMPT_MIN_HEIGHT == 1193
assert picker_manifest["metadata"]["ui_options"]["initial_width"] == 1400
assert picker_manifest["metadata"]["ui_options"]["initial_height"] == 360
assert picker_manifest["metadata"]["ui_options"]["min_height"] == 360
agent_manifest = next(item for item in manifest["nodes"] if item["class_name"] == "HMBAgentLibrary")
for native_size_key in (
    "width", "height", "default_width", "default_height",
    "preferred_width", "preferred_height", "initial_width", "initial_height",
):
    assert native_size_key not in agent_manifest["metadata"]

# The active runtime is the server-hosted signed v4.5 policy. This internal
# regression injects the private signed artifact without creating a local
# runtime fallback or copying it into the public package.
assert hashlib.sha256(signed_policy_fixture).hexdigest() == (
    "228b54e55dd4167f4cb58f8bdbdb8762818a636018180fe1ae97f7a023ac2144"
)
policy_payload = common._load_agent_rule_payload()
assert policy_payload["final_policy_version"] == (
    "2026-08-27.agent-shot-quality.v4.5"
)
assert policy_payload["final_motion_look_policy_sha256"] == (
    "86852214d3e1a29eab12a2b0cff0302f6920d5d3ce3b00947d96ef1eb952c872"
)
assert agent._assert_prompt_policy_identity_matches_signed_runtime() == (
    policy_payload["final_policy_version"],
    policy_payload["final_motion_look_policy_sha256"],
)

widget_source = (ROOT / "widgets/HMBVideoPickerLibraryWidget_v032.js").read_text(encoding="utf-8")
command_widget_source = (ROOT / "widgets/HMBVideoPickerCommandBridgeWidget_v032.js").read_text(encoding="utf-8")
prompt_widget_source = (ROOT / "widgets/HMBPromptLibraryScopedBindingWidget.js").read_text(encoding="utf-8")
picker_source = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")

assert picker.DEPTH_PLAYBLAST_PROFILE == "hmb_camera_space_depth_v7"
assert picker.LEGACY_DEPTH_PLAYBLAST_PROFILES == frozenset({
    "hmb_camera_space_depth_v1",
    "hmb_camera_space_depth_v2",
    "hmb_camera_space_depth_v3",
    "hmb_camera_space_depth_v4",
    "hmb_camera_space_depth_v5",
    "hmb_camera_space_depth_v6",
})
assert "hmb_camera_space_depth_v7" not in widget_source
assert "HMB_PICKER_COMMAND" in widget_source
assert "HMB_VIDEO_PICKER_COMMAND_REGISTRY_KEY" in widget_source
assert "return latestProps.onChange(command)" in command_widget_source
assert "hmbDeliverPickerStateIfMounted(" in widget_source
assert "JSON.parse(JSON.stringify(normalized))" in widget_source
assert "def _apply_widget_action(" not in picker_source
assert "commitAndRemount" not in widget_source
assert "HMBVideoPickerLibraryWidget(container, {" not in widget_source
assert "emit(props, state);\n          remount();" not in prompt_widget_source
assert "emit(props, state, container);\n        remount();" not in prompt_widget_source
assert 'state.ui.language = uiLanguage(state) === "ko" ? "en" : "ko";' in prompt_widget_source
assert prompt_widget_source.count("remount();") == 2
assert "hmbCommitLocalPromptStructure(container, props, state, remount)" in prompt_widget_source
assert "if (currentValue === nextValue && !disabledChanged) {" in prompt_widget_source
assert "if (dirtyText.length || shouldRepublishRevisionMerge) {" in prompt_widget_source
assert 'pending_action: "read_scene"' not in widget_source
assert 'pending_action: "run_video"' not in widget_source
assert 'pending_action: "render_snapshot"' not in widget_source
assert 'pending_action: "stop_read"' not in widget_source
assert 'const action = processPid > 0 ? "stop_read" : "cancel_pending";' in widget_source
assert "Pending operation cancelled before an external process PID existed." in widget_source
assert "READ request submitted through HMB_PICKER_COMMAND. Waiting for Python acknowledgement." in widget_source
assert "READ transport timed out before Python acknowledgement (20 seconds)." in widget_source
assert "export function pickerButtonAvailability" in widget_source
assert "const mayaAvailable = Boolean(state.maya_available && clean(state.maya_executable));" in widget_source
assert "stopEnabled: (operationBusy || !!localReadPending || !!localOriginalPending) && !stopping" in widget_source
assert "const HMB_PICKER_CONTENT_FALLBACK_HEIGHT = 960;" in widget_source
assert ".hmbvp-clip{width:100%;height:100%;" in widget_source
assert ".hmbvp{--safe-x:16px;position:relative;width:100%;height:100%;" in widget_source
assert "border-radius:11px" in widget_source
assert 'class="statusbar"' not in widget_source
assert ".statusbar{" not in widget_source
assert 'class="warnings"' not in widget_source
assert ".warnings{" not in widget_source
assert 'id="activity-log-view" class="activity-log-view" role="log" aria-live="polite"' in widget_source
assert '.activity-log-row[data-level="ERROR"]{color:#fb7185}' in widget_source
# v0.6.46 leaves broad host/adaptive ancestors untouched. Compact and expanded
# modes may size only the exact recognized HMB_PICKER_STATE row and its spacer,
# restoring their snapshots on transition; broad overflow overrides stay banned.
assert 'container.style.overflow = "visible"' not in widget_source
assert "export function hmbApplyVideoPickerCompactTailReclaim(" in widget_source
assert "export function hmbRestoreVideoPickerCompactTailReclaim(container)" in widget_source
assert 'container.closest?.(\'[data-parameter-name="HMB_PICKER_STATE"]\')' in widget_source
assert 'clean(element.getAttribute?.("aria-hidden")).toLowerCase() === "true"' in widget_source
assert "hmbEnsurePickerBootstrapNode" not in command_widget_source
assert "export function hmbCollapseCommandBridgeLayoutRow(container)" in command_widget_source
assert "parentElement" not in command_widget_source
assert "react-flow" not in command_widget_source.casefold()
assert "hmbApplyPickerCommandRowReclaim(container)" in widget_source
assert "const HMB_DEFAULT_NODE_WIDTH = 1400;" in widget_source
assert "const HMB_DEFAULT_NODE_HEIGHT = 1200;" in widget_source
assert "const HMB_MIN_NODE_HEIGHT = 1151;" in widget_source
assert "function hmbApplyPickerInitialNodeSizeOnce(container)" in widget_source
assert "hmbApplyPickerInitialNodeSizeOnce(container);\n  concealNativeMayaPicker(container);" in widget_source
assert "currentWidth < HMB_DEFAULT_NODE_WIDTH - 1" not in widget_source
assert "currentHeight < HMB_DEFAULT_NODE_HEIGHT - 1" not in widget_source
assert "const HMB_RIGHT_SECTION_DEFAULT_HEIGHTS = { settings: 217, color: 628, log: 208 };" in widget_source
assert '{ value: "1920x1080", width: 1920, height: 1080' in widget_source
assert 'id="playblast-resolution"' in widget_source
assert "(1920, 1080)" in picker_source
assert '"width": output_width' in picker_source
assert '"height": output_height' in picker_source
assert "hmbAdjustPickerNodeHeightForVideoSlots" not in widget_source
assert 'hmbScopeWidgetStyleMarkup(pickerMarkup, ".hmbvp")' in widget_source
assert "hmbPreparePickerSlotTransition(" not in widget_source
assert 'data-video-asset-uid="${escapeHtml(uid)}"' in widget_source
assert 'data-selected-video-order="${Number(order || 0)}"' in widget_source
assert 'draggable="true"' in widget_source
assert 'data-hmb-picker-slot-transition="true"' not in widget_source
assert "hmb-picker-native-row-in" not in widget_source
assert "transition:height 180ms" not in widget_source
assert "_stage_video_slot_native_size" not in picker_source
assert "PICKER_VIDEO_OUTPUT_ROW_DELTA" not in picker_source
assert "def _retire_legacy_video_slot_outputs(" in picker_source
assert "Legacy node deletion race ignored" not in picker_source
assert 'prepared_kwargs["metadata"] = prepared_metadata' in picker_source
assert "super().__init__(**prepared_kwargs)" in picker_source
assert "initial_size_setter(width=PICKER_START_WIDTH, height=PICKER_START_HEIGHT)" not in picker_source
assert "_add_picker_command_bridge(self)" in picker_source
assert "if name == WIDGET_COMMAND_PARAMETER:" in picker_source
assert "if action in {\"cancel_pending\", \"stop_read\", \"cancel_operation\"}:" in picker_source
assert "event_loop.call_soon_threadsafe(launch)" in picker_source
assert widget_source.index('id="original-preview-toggle"') < widget_source.index(
    'id="mask-playblast-toggle"'
) < widget_source.index('id="depth-playblast-toggle"') < widget_source.index(
    'id="motion-guide-toggle"'
)
original_toggle_source = widget_source[
    widget_source.index('on(container.querySelector("#original-preview-toggle")'):
    widget_source.index('on(container.querySelector("#mask-playblast-toggle")')
]
assert "dispatchCommand(" not in original_toggle_source
assert '"original_enabled"' in original_toggle_source
output_choice_source = widget_source[
    widget_source.index("const queueOutputChoice ="):
    widget_source.index('on(container.querySelector("#original-preview-toggle")')
]
assert "[field]: enabled" in output_choice_source
assert "hmbApplyPickerOutputChoicesToDom(" in output_choice_source
assert "schedulePickerStatePublicationAfterPaint(next" in output_choice_source
assert "commitOptions: { suppressMatchingEcho: true }" in output_choice_source
assert "include_original: originalEnabled" in widget_source
assert "include_mask: maskEnabled" in widget_source
assert "Select at least one output: Original, Mask, Depth, or Motion Guide." in widget_source


# ---------------------------------------------------------------------------
# Marker vocabulary and executable discovery.
# ---------------------------------------------------------------------------
catalog_path = ROOT / "resources/picker/HMB_Marker_Catalog.json"
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
assert catalog["version"] == 4
character = [item["name"] for item in catalog["character"]]
background = [item["name"] for item in catalog["background"]]
expected_actor = ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink"]
expected_ghost = ["Sky Blue", "Mint", "Beige"]
expected_object = [
    *expected_ghost,
    "Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern",
]
assert character == expected_actor
assert background == expected_object
assert picker.MARKER_ORDER == expected_actor + expected_object
assert prompt._hmb.ACTOR_COLOR_PICK_CHOICES == expected_actor
assert prompt._hmb.OBJECT_COLOR_PICK_CHOICES == expected_object
assert prompt._hmb.COLOR_PICK_CHOICES == picker.MARKER_ORDER
assert prompt.image_color_pick_choices_for_taxonomy(
    "Character", "Full Appearance"
) == expected_actor
assert prompt.image_color_pick_choices_for_taxonomy(
    "Character Prop", "Handheld Prop"
) == expected_actor
assert prompt.image_color_pick_choices_for_taxonomy(
    "Environment / Background", "Main Background"
) == expected_object
assert prompt.image_color_pick_choices_for_taxonomy(
    "Background Prop", "Independent Scene Prop"
) == expected_object

original_mayabatch_candidates = picker._mayabatch_candidates
try:
    maya_2024 = Path("/Program Files/Autodesk/Maya2024/bin/mayabatch.exe")
    maya_2027 = Path("/Program Files/Autodesk/Maya2027/bin/mayabatch.exe")
    picker._mayabatch_candidates = lambda: [maya_2024, maya_2027]
    assert picker._find_mayabatch() == maya_2027
    assert picker._maya_display_version(picker._find_mayabatch()) == "2027"
finally:
    picker._mayabatch_candidates = original_mayabatch_candidates

with tempfile.TemporaryDirectory() as bundled_ffmpeg_dir:
    bundled_ffmpeg_path = Path(bundled_ffmpeg_dir) / "ffmpeg.exe"
    bundled_ffmpeg_path.write_bytes(b"test ffmpeg executable")
    original_imageio_ffmpeg = sys.modules.get("imageio_ffmpeg")
    original_which = picker.shutil.which
    original_ffmpeg_path = picker.os.environ.pop("FFMPEG_PATH", None)
    fake_imageio_ffmpeg = types.ModuleType("imageio_ffmpeg")
    fake_imageio_ffmpeg.get_ffmpeg_exe = lambda: str(bundled_ffmpeg_path)
    sys.modules["imageio_ffmpeg"] = fake_imageio_ffmpeg
    try:
        picker.shutil.which = lambda _name: None
        assert picker._find_ffmpeg(None) == bundled_ffmpeg_path.resolve()
    finally:
        picker.shutil.which = original_which
        if original_ffmpeg_path is not None:
            picker.os.environ["FFMPEG_PATH"] = original_ffmpeg_path
        if original_imageio_ffmpeg is None:
            sys.modules.pop("imageio_ffmpeg", None)
        else:
            sys.modules["imageio_ffmpeg"] = original_imageio_ffmpeg

with tempfile.TemporaryDirectory() as maya_env_dir:
    maya_env_job = Path(maya_env_dir) / "maya.job.json"
    maya_env_job.write_text('{"operation":"scan"}', encoding="utf-8")
    original_hmb_vp2 = picker.os.environ.pop("HMB_MAYA_VP2_DEVICE_OVERRIDE", None)
    original_maya_vp2 = picker.os.environ.pop("MAYA_VP2_DEVICE_OVERRIDE", None)
    try:
        maya_env = picker._maya_subprocess_environment(maya_env_job)
        assert maya_env["HMB_VIDEO_PICKER_JOB"] == str(maya_env_job.resolve())
        assert maya_env["HMB_VIDEO_PICKER_RUNNER"] == str(
            picker.MAYA_RUNNER.resolve()
        )
        assert len(maya_env["HMB_VIDEO_PICKER_JOB_SHA256"]) == 64
        assert len(maya_env["HMB_VIDEO_PICKER_RUNNER_SHA256"]) == 64
        assert maya_env["PYTHONUTF8"] == "1"
        assert maya_env["MAYA_DISABLE_CIP"] == "1"
        assert maya_env["MAYA_DISABLE_CER"] == "1"
        assert maya_env["MAYA_DISABLE_ADP"] == "1"
        assert "import HMB_Maya_Background_Preview" not in picker._maya_runner_command()
        assert "spec_from_file_location" in picker._maya_runner_command()
        if picker.os.name == "nt":
            assert maya_env["MAYA_VP2_DEVICE_OVERRIDE"] == "VirtualDeviceDx11"

        picker.os.environ["HMB_MAYA_VP2_DEVICE_OVERRIDE"] = "VirtualDeviceGLCore"
        explicit_maya_env = picker._maya_subprocess_environment(maya_env_job)
        assert explicit_maya_env["MAYA_VP2_DEVICE_OVERRIDE"] == "VirtualDeviceGLCore"
    finally:
        picker.os.environ.pop("HMB_MAYA_VP2_DEVICE_OVERRIDE", None)
        picker.os.environ.pop("MAYA_VP2_DEVICE_OVERRIDE", None)
        if original_hmb_vp2 is not None:
            picker.os.environ["HMB_MAYA_VP2_DEVICE_OVERRIDE"] = original_hmb_vp2
        if original_maya_vp2 is not None:
            picker.os.environ["MAYA_VP2_DEVICE_OVERRIDE"] = original_maya_vp2

# ---------------------------------------------------------------------------
# State/command separation, normalization, replay protection, and STOP meaning.
# ---------------------------------------------------------------------------
node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_primary"))
assert picker.parameter_exists(node, picker.WIDGET_STATE_PARAMETER)
assert picker.parameter_exists(node, picker.WIDGET_COMMAND_PARAMETER)
assert picker.parameter_exists(node, "PICKER_OUT")
assert picker.parameter_exists(node, "VIDEO_OUT")
for slot in range(1, picker.MAX_VIDEO_SLOTS + 1):
    assert not picker.parameter_exists(node, f"VIDEO{slot}_OUT")
video_parameter = picker._get_parameter_obj(node, "VIDEO_OUT")
assert video_parameter is not None
assert video_parameter.output_type == "list[str]"
assert video_parameter.default_value == []
assert video_parameter.ui_options["display_name"] == ""
assert video_parameter.ui_options["hide"] is True
assert video_parameter.ui_options["height"] == 1

# Generated workflows hydrate HMB_PICKER_STATE with initial_setup=True. The
# saved UID/catalog selection must restore one synchronized media list.
initial_restore_node = install_engine_hooks(
    picker.HMBVideoPickerLibrary(name="initial_three_slot_restore")
)
initial_restore_state = initial_restore_node._picker_state()
initial_restore_state.update({
    "runtime_instance_id": "serialized-previous-runtime",
    "state_writer": "python",
    "state_revision": 17,
    "active_slot_count": 3,
    "selected_video_slot": 2,
    "videos": [
        {
            "video_slot": slot,
            "video_url": f"https://cdn.example/saved/project/video_{slot}.mp4",
            "camera": f"camera{slot}",
        }
        for slot in range(1, 4)
    ],
})
initial_state_parameter = picker._get_parameter_obj(
    initial_restore_node,
    picker.WIDGET_STATE_PARAMETER,
)
initial_restore_candidate = initial_restore_node.before_value_set(
    initial_state_parameter,
    initial_restore_state,
)
# NodeManager calls before_value_set without exposing its initial_setup flag.
# The hook must preserve the previous-runtime serialized snapshot verbatim;
# the setter below owns the real saved-workflow versus stale-worker decision.
assert initial_restore_candidate["runtime_instance_id"] == (
    "serialized-previous-runtime"
)
assert getattr(
    initial_restore_node,
    "_hmb_restored_state_pending_revision",
    -1,
) == -1
initial_restore_node.set_parameter_value(
    picker.WIDGET_STATE_PARAMETER,
    initial_restore_candidate,
    initial_setup=True,
    skip_before_value_set=True,
)
restored_three_slot_state = initial_restore_node._picker_state()
assert restored_three_slot_state["active_slot_count"] == 3
assert restored_three_slot_state["selected_video_slot"] == 1
assert restored_three_slot_state["selected_video_uid"] == (
    restored_three_slot_state["videos"][0]["video_uid"]
)
assert restored_three_slot_state["runtime_instance_id"] == initial_restore_node._hmb_runtime_instance_id
assert initial_restore_node._hmb_restored_state_pending_revision == -1
assert initial_restore_node.parameter_output_values["VIDEO_OUT"] == [
    "https://cdn.example/saved/project/video_1.mp4",
    "https://cdn.example/saved/project/video_2.mp4",
    "https://cdn.example/saved/project/video_3.mp4",
]
restored_picker_payload = json.loads(
    initial_restore_node.parameter_output_values["PICKER_OUT"]
)
assert [
    item["video_path"] for item in restored_picker_payload["videos"]
] == initial_restore_node.parameter_output_values["VIDEO_OUT"]

# A later authoritative empty catalog clears the one list atomically; no stale
# per-slot cache or hidden auxiliary output remains.
empty_reload_state = picker._default_widget_state()
node._sync_outputs_from_state(empty_reload_state)
assert node.parameter_output_values["VIDEO_OUT"] == []
assert json.loads(node.parameter_output_values["PICKER_OUT"])["videos"] == []
picker_output_parameter = picker._get_parameter_obj(node, "PICKER_OUT")
assert picker_output_parameter.name == "PICKER_OUT"
assert picker_output_parameter.type == "str"
assert picker_output_parameter.output_type == "str"
if hasattr(picker_output_parameter, "allowed_modes"):
    assert picker_output_parameter.allowed_modes == {picker.ParameterMode.OUTPUT}
else:
    assert picker_output_parameter.allow_output is True
    assert picker_output_parameter.allow_input is False
assert picker_output_parameter.input_types in ([], ["str"])
assert picker_output_parameter.hide_property is True
assert picker_output_parameter.ui_options["display_name"] == ""
assert picker_output_parameter.ui_options["hide_property"] is True
assert picker_output_parameter.ui_options["is_full_width"] is True
assert picker_output_parameter.ui_options["hide"] is True
assert picker_output_parameter.ui_options["hide_handles"] is True
picker.set_output(node, "PICKER_OUT", "picker-contract-preserved")
picker_output_parameter.hide_property = False
picker_output_parameter.ui_options.update({
    "display_name": "PICKER_OUT",
    "hide_property": False,
    "hide_handles": True,
})
node._ensure_parameters()
assert picker_output_parameter.hide_property is True
assert picker_output_parameter.ui_options["display_name"] == ""
assert picker_output_parameter.ui_options["hide_property"] is True
assert picker_output_parameter.ui_options["hide_handles"] is True
assert node.parameter_output_values["PICKER_OUT"] == "picker-contract-preserved"
prompt_port_node = prompt.HMBPromptLibrary(name="prompt_output_port_contract")
prompt_output_parameter = prompt._get_parameter_obj(prompt_port_node, "PROMPT_OUT")
assert prompt_output_parameter.name == "PROMPT_OUT"
assert prompt_output_parameter.type == "str"
assert prompt_output_parameter.output_type == "str"
if hasattr(prompt_output_parameter, "allowed_modes"):
    assert prompt_output_parameter.allowed_modes == {prompt.ParameterMode.OUTPUT}
else:
    assert prompt_output_parameter.allow_output is True
    assert prompt_output_parameter.allow_input is False
assert prompt_output_parameter.input_types in ([], ["str"])
assert prompt_output_parameter.hide_property is True
assert prompt_output_parameter.ui_options["display_name"] == ""
assert prompt_output_parameter.ui_options["hide_property"] is True
assert prompt_output_parameter.ui_options["is_full_width"] is True
assert prompt_output_parameter.ui_options["hide"] is True
assert prompt_output_parameter.ui_options["hide_handles"] is True
prompt.set_output(prompt_port_node, "PROMPT_OUT", "prompt-contract-preserved")
prompt_output_parameter.hide_property = False
prompt_output_parameter.ui_options.update({
    "display_name": "PROMPT_OUT",
    "hide_property": False,
    "hide_handles": True,
})
prompt_port_node._ensure_prompt_output()
assert prompt_output_parameter.hide_property is True
assert prompt_output_parameter.ui_options["display_name"] == ""
assert prompt_output_parameter.ui_options["hide_property"] is True
assert prompt_output_parameter.ui_options["hide_handles"] is True
assert prompt_port_node.parameter_output_values["PROMPT_OUT"] == "prompt-contract-preserved"
state_parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
command_parameter = picker._get_parameter_obj(node, picker.WIDGET_COMMAND_PARAMETER)
assert picker.PICKER_START_WIDTH == 1400
assert picker.PICKER_START_HEIGHT == 1200
assert picker.PICKER_WIDGET_START_HEIGHT == picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT == 252
assert picker.PICKER_WIDGET_MIN_HEIGHT == 1151
assert picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT == 252
assert picker.PICKER_COMPACT_NATIVE_HEIGHT == 360
assert picker.PICKER_NATIVE_SIZE_VERSION == 7
assert node.metadata["size"] == {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_COMPACT_NATIVE_HEIGHT,
}
assert node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_START_HEIGHT,
}
assert node.metadata["hmb_picker_native_size_version"] == picker.PICKER_NATIVE_SIZE_VERSION
assert state_parameter.ui_options["height"] == picker.PICKER_WIDGET_START_HEIGHT
assert state_parameter.ui_options["min_height"] == picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT
assert state_parameter.ui_options["node_size"] == node.metadata["size"]
assert state_parameter.type == "dict"
assert state_parameter.input_types == ["dict"]
assert command_parameter.type == "dict"
assert command_parameter.input_types == ["dict"]
assert command_parameter.ui_options["expandable"] is False
assert command_parameter.ui_options["hide_label"] is True
assert command_parameter.ui_options["hide_handles"] is True
assert state_parameter.ui_options["expandable"] is True
assert picker._playblast_resolution({}) == (1280, 720)
assert picker._playblast_resolution({"output_width": 1920, "output_height": 1080}) == (1920, 1080)
assert picker._playblast_resolution({"output_width": 1600, "output_height": 900}) == (1280, 720)
assert picker._parse_state({"output_width": 1920, "output_height": 1080})["output_width"] == 1920
assert picker._parse_state({"output_width": 1920, "output_height": 1080})["output_height"] == 1080
assert isinstance(node.get_parameter_value(picker.WIDGET_STATE_PARAMETER), dict)
assert isinstance(node.get_parameter_value(picker.WIDGET_COMMAND_PARAMETER), dict)
boot_command = picker._parse_picker_command(node.get_parameter_value(picker.WIDGET_COMMAND_PARAMETER))
assert boot_command["runtime_instance_id"] == node._hmb_runtime_instance_id
assert boot_command["action"] == ""
boot_log = "\n".join(item.get("message", "") for item in node._picker_state().get("activity_log", []))
assert "type=dict" in boot_log
assert "independent HMB_PICKER_COMMAND minimal JSON path" in boot_log
assert "HMB_PICKER_STATE carries dashboard state only" in boot_log
assert node._picker_state()["state_writer"] == "python"
assert node._picker_state()["runtime_instance_id"] == node._hmb_runtime_instance_id

legacy_state = picker._default_widget_state()
legacy_state.pop("ui_layout_version", None)
legacy_state["viewport_panel_height"] = 900
legacy_state["right_section_heights"] = {"settings": 190, "color": 412, "log": 208}
normalized_legacy = picker._parse_state(legacy_state)
assert normalized_legacy["viewport_panel_height"] == 684
assert normalized_legacy["right_section_heights"]["color"] == 628
assert picker._parse_state(normalized_legacy) == normalized_legacy

for malformed in (None, [], {}, "bad", float("nan"), float("inf"), -99, 999):
    parsed = picker._parse_state({
        "active_slot_count": malformed,
        "selected_video_slot": malformed,
        "active_process_pid": malformed,
        "viewport_panel_height": malformed,
    })
    assert 1 <= parsed["active_slot_count"] <= 5
    assert 1 <= parsed["selected_video_slot"] <= parsed["active_slot_count"]
    assert parsed["active_process_pid"] >= 0

random.seed(2201)
malformed_values = [None, [], {}, "", "x", -100, 0, 1, 6, 999, float("nan"), float("inf")]
for _index in range(500):
    candidate = {
        "active_slot_count": random.choice(malformed_values),
        "selected_video_slot": random.choice(malformed_values),
        "active_process_pid": random.choice(malformed_values),
        "right_section_heights": random.choice(malformed_values),
        "videos": random.choice(malformed_values),
        "slot_assignments": random.choice(malformed_values),
        "slot_visibility": random.choice(malformed_values),
    }
    parsed = picker._parse_state(candidate)
    assert picker._parse_state(parsed) == parsed

assert picker._parse_picker_command(None) == picker._default_picker_command("")
malformed_command = picker._parse_picker_command({
    "runtime_instance_id": ["bad"],
    "action": {"bad": True},
    "action_id": None,
    "issued_at_ms": "not-a-number",
    "payload": [1, 2, 3],
})
assert malformed_command["schema"] == picker.COMMAND_SCHEMA
assert malformed_command["version"] == picker.COMMAND_VERSION
assert malformed_command["issued_at_ms"] == 0
assert malformed_command["payload"] == {}

# Legacy action fields in the large state are always inert and stripped.
state_only_node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_state_only"))
state_action_called = threading.Event()
state_only_node._start_ui_operation = lambda *_args, **_kwargs: state_action_called.set()
legacy_widget_state = state_only_node._picker_state()
legacy_widget_state.update({
    "pending_action": "read_scene",
    "pending_action_id": "legacy-state-command",
    "scene_path": "C:/shots/legacy.mb",
})
final_state_value = state_only_node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, legacy_widget_state)
assert final_state_value["pending_action"] == ""
assert final_state_value["pending_action_id"] == ""
time.sleep(0.05)
assert not state_action_called.is_set()

# The independent command parameter acknowledges and dispatches READ only once.
command_node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_command"))
captured_actions = []
command_event = threading.Event()

def capture_start(action, incoming):
    captured_actions.append((action, copy.deepcopy(incoming)))
    command_node._write_state(incoming)
    command_event.set()

command_node._start_ui_operation = capture_start
send_command(
    command_node,
    "read_scene",
    "read-command-1",
    {"scene_path": "C:/shots/shot.mb", "selected_video_slot": 1},
)
assert command_event.wait(timeout=2.0)
assert captured_actions[0][0] == "read_scene"
assert captured_actions[0][1]["backend_ack_action_id"] == "read-command-1"
assert captured_actions[0][1]["pending_action"] == ""
assert command_node._picker_state()["backend_ack_action_id"] == "read-command-1"

# A stale command from a saved workflow is ignored because its runtime ID is old.
stale_node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_stale"))
original_language = stale_node._picker_state()["language"]
send_command(
    stale_node,
    "set_language",
    "stale-command-1",
    {"language": "ko"},
    runtime_id="previous-python-runtime",
)
time.sleep(0.1)
assert stale_node._picker_state()["language"] == original_language
assert stale_node._picker_state()["backend_ack_action_id"] != "stale-command-1"

# A valid command is applied, and replaying the same action ID is idempotent.
language_node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_language"))
send_command(language_node, "set_language", "language-command-1", {"language": "ko"})
wait_for(
    lambda: language_node._picker_state().get("backend_ack_action_id") == "language-command-1",
    message="language command was not acknowledged",
)
assert language_node._picker_state()["language"] == "ko"
log_count = len(language_node._picker_state().get("activity_log", []))
send_command(language_node, "set_language", "language-command-1", {"language": "en"})
wait_for(
    lambda: language_node._picker_state().get("backend_ack_action_id") == "language-command-1",
    message="duplicate command acknowledgement was not retained",
)
assert language_node._picker_state()["language"] == "ko"
assert len(language_node._picker_state().get("activity_log", [])) == log_count

# Before an external PID exists, STOP cancels only the pending worker and does
# not claim to terminate a running Maya process.
pending_node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_pending"))
pending_node._hmb_pending_operation_id = "pending-read-command"
send_command(
    pending_node,
    "cancel_pending",
    "cancel-pending-1",
    {"target_action_id": "pending-read-command", "active_process_pid": 0},
)
wait_for(
    lambda: pending_node._picker_state().get("backend_ack_action_id") == "cancel-pending-1",
    message="pending cancellation was not acknowledged",
)
pending_state = pending_node._picker_state()
assert pending_state["active_process_pid"] == 0
assert pending_state["active_process_kind"] == ""
assert "before an external process started" in pending_state["message"]
pending_log = "\n".join(item.get("message", "") for item in pending_state.get("activity_log", []))
assert "termination of the active" not in pending_log
assert "PID " not in pending_state["message"]

class FakeActiveProcess:
    def __init__(self, pid=9876):
        self.pid = pid
        self.killed = threading.Event()

    def poll(self):
        return 0 if self.killed.is_set() else None

    def kill(self):
        self.killed.set()

    def wait(self, timeout=None):
        self.killed.set()
        return 0

active_node = install_engine_hooks(picker.HMBVideoPickerLibrary(name="reliability_active"))
fake_process = FakeActiveProcess()
active_node._register_active_process(fake_process, "Maya")
assert active_node._picker_state()["active_process_pid"] == 9876
send_command(
    active_node,
    "stop_read",
    "active-stop-1",
    {"target_action_id": "read-command", "active_process_pid": 9876},
)
assert fake_process.killed.wait(timeout=2.0)
active_state = active_node._picker_state()
assert active_state["backend_ack_action_id"] == "active-stop-1"
assert "PID 9876" in active_state["message"]
active_node._clear_active_process(fake_process)
assert active_node._picker_state()["active_process_pid"] == 0

# Backend failures remain diagnosable in the operation log.
with tempfile.TemporaryDirectory() as failure_log_dir:
    failure_log_path = Path(failure_log_dir) / "Read_failure.log"
    failed_state = node._picker_state()
    failed_state["last_log_path"] = str(failure_log_path)
    node._write_state(failed_state)
    node._set_failed_state(RuntimeError("persistent read diagnostic"))
    assert "HMB OPERATION ERROR: persistent read diagnostic" in failure_log_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Retained-mode request and post-transaction worker scheduling simulation.
# ---------------------------------------------------------------------------
engine_module_names = [
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.events",
    "griptape_nodes.retained_mode.events.parameter_events",
    "griptape_nodes.retained_mode.griptape_nodes",
]
saved_engine_modules = {name: sys.modules.get(name) for name in engine_module_names}
bus_requests = []
scheduled_callbacks = []

class FakeSetParameterValueRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class FakeSetParameterValueResultSuccess:
    pass

class FakeEventLoop:
    @staticmethod
    def is_running():
        return True

    @staticmethod
    def call_soon_threadsafe(callback):
        scheduled_callbacks.append(callback)

class FakeEventManager:
    event_loop = FakeEventLoop()

class FakeGriptapeNodes:
    @staticmethod
    def handle_request(request):
        bus_requests.append(request)
        return FakeSetParameterValueResultSuccess()

    @staticmethod
    def EventManager():
        return FakeEventManager()

bus_node = picker.HMBVideoPickerLibrary(name="reliability_bus")

try:
    for package_name in engine_module_names[:3]:
        package = types.ModuleType(package_name)
        package.__path__ = []
        sys.modules[package_name] = package
    parameter_events_module = types.ModuleType(engine_module_names[3])
    parameter_events_module.SetParameterValueRequest = FakeSetParameterValueRequest
    parameter_events_module.SetParameterValueResultSuccess = FakeSetParameterValueResultSuccess
    sys.modules[engine_module_names[3]] = parameter_events_module
    griptape_nodes_module = types.ModuleType(engine_module_names[4])
    griptape_nodes_module.GriptapeNodes = FakeGriptapeNodes
    sys.modules[engine_module_names[4]] = griptape_nodes_module

    bus_state = bus_node._picker_state()
    bus_state["scene_stage"] = "BUS_TEST"
    bus_node._write_state(bus_state)
    assert len(bus_requests) == 1
    assert bus_requests[0].node_name == bus_node.name
    assert bus_requests[0].parameter_name == picker.WIDGET_STATE_PARAMETER
    assert bus_requests[0].data_type == "dict"
    assert bus_requests[0].value["scene_stage"] == "BUS_TEST"

    worker_started = threading.Event()
    bus_node._schedule_action_worker("read_scene", "scheduled-read-1", worker_started.set)
    assert len(scheduled_callbacks) == 1
    assert not worker_started.is_set()
    scheduled_callbacks.pop()()
    assert worker_started.wait(timeout=1.0)

    # Cancellation must bypass the queue so a pending worker can be stopped.
    stop_worker_started = threading.Event()
    bus_node._schedule_action_worker("cancel_pending", "scheduled-stop-1", stop_worker_started.set)
    assert stop_worker_started.wait(timeout=1.0)
    assert scheduled_callbacks == []
finally:
    for module_name, original_module in saved_engine_modules.items():
        if original_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_module

# Static controls retained from the production picker.
assert 'id="maya-scene-path"' in widget_source
assert 'id="browse-maya-scene"' in widget_source
assert 'id="load-maya-scene"' not in widget_source
assert widget_source.count('id="read-scene"') == 1
assert "openNativeMayaPicker(container)" in widget_source
assert "window.setInterval(checkSelectionResult, 200)" not in widget_source
assert "const HMB_PICKER_BROWSE_POLL_DELAYS_MS" in widget_source
assert "+ HMB_PICKER_BROWSE_POLL_DELAYS_MS.reduce((total, delay) => total + delay, 0)" in widget_source
assert "hmbNativeMayaBrowseSessionOwnedBy(container, ownerActionId)" in widget_source
assert 'id="open-video"' not in widget_source
assert 'id="open-video-file"' not in widget_source
assert "__hmbOpenedVideoUrl" not in widget_source
assert "__hmbOpenedVideoName" not in widget_source
assert "URL.createObjectURL" not in widget_source
assert "URL.revokeObjectURL" not in widget_source
assert 'data-visibility-path=' in widget_source
assert "slot_visibility" in widget_source
assert "const actorOptions = paletteGroups.actor;" in widget_source
assert "const ghostOptions = paletteGroups.ghost;" in widget_source
assert "const objectOptions = paletteGroups.object;" in widget_source
assert 'id="create-snapshot"' in widget_source
assert 'id="delete-snapshot"' in widget_source
assert 'id="snapshot-prev"' in widget_source
assert 'id="video-play-toggle"' in widget_source
assert 'id="snapshot-next"' in widget_source
assert 'id="video-prev-frame"' not in widget_source
assert 'id="video-next-frame"' not in widget_source
assert 'id="video-seek"' in widget_source
assert "viewportVideo.loop = true" not in widget_source
assert "media.loop = false;" in widget_source
assert widget_source.count("ownerDocument?.defaultView?.MutationObserver") == 3
assert "READ_PREVIEW_WIDTH" not in picker_source
assert "READ_PREVIEW_HEIGHT" not in picker_source
assert 'f"{scene_path.stem}_Orignal.mp4"' in picker_source
assert 'f"{scene_path.stem}_playblast_{token}.mp4"' in picker_source
assert "time.time_ns()}|{uuid.uuid4().hex" in picker_source
assert picker_source.count('"character_outline_mode": "native_lambert"') == 2
for retired_field in (
    "preview_frames", "preview_data_uri", "preview_frame_index",
    "slot_output_settings", "output_scope", "output_visibility",
):
    assert retired_field not in picker_source
    assert retired_field not in widget_source

maya_runner_source = (ROOT / "resources/maya/HMB_Maya_Background_Preview.py").read_text(encoding="utf-8")
assert "def _apply_assigned_render_scope" in maya_runner_source
assert "def _validated_picker_hidden_paths" in maya_runner_source
assert "def _apply_hidden_paths" not in maya_runner_source
assert "HMB_Unassigned_Black" not in maya_runner_source
assert 'loadReferenceDepth="none"' not in maya_runner_source
assert 'job["_reference_warnings"] = _audit_authored_reference_state(job)' in maya_runner_source
assert '"preview_frames"' not in maya_runner_source
assert '"generate_original_video"' in maya_runner_source
assert '"original_frame_count": original_frame_count' in maya_runner_source
assert "Legacy generate_original_video was ignored: scan/READ is metadata-only." in maya_runner_source
assert "os.replace(temp_path, progress_path)" in maya_runner_source
assert "cmds.file(save" not in maya_runner_source
assert "def _lambert_shader(" in maya_runner_source
assert "def _assign_marker_group_preserving_cutouts(" in maya_runner_source
assert 'cmds.createNode("pfxToon"' in maya_runner_source
assert maya_runner_source.count("_character_out_rim(") == 2
assert "character_outline_shapes.extend(opaque_shapes)" in maya_runner_source
assert "outline_mode == CHARACTER_OUTLINE_PFX" in maya_runner_source
assert "character_outline_mode=CHARACTER_OUTLINE_NATIVE" in maya_runner_source
assert '"markers": _marker_payload(' in maya_runner_source
assert '("localOcclusion", CHARACTER_OUT_RIM_LOCAL_OCCLUSION)' in maya_runner_source
assert '("lineOffset", CHARACTER_OUT_RIM_LINE_OFFSET)' in maya_runner_source
assert '("hardwareRenderingGlobals.multiSampleEnable", 0)' in maya_runner_source
assert '("hardwareRenderingGlobals.lineAAEnable", 0)' in maya_runner_source
assert '"hardwareRenderingGlobals.lightingMode", 0' in maya_runner_source
assert '"hardwareRenderingGlobals.renderMode", 4' in maya_runner_source
assert "marker_group = _screen_space_pattern_shader(" in maya_runner_source
assert "MARKER_PATTERN_IDS.get(color)" in maya_runner_source
assert "enableMultisample" in maya_runner_source
assert "force_high_quality_viewport and not apply_marker_shaders" in maya_runner_source
assert "cmds.displaySmoothness(" in maya_runner_source
assert picker_source.count("activity_paths=(frames_folder,)") == 2
assert "[depth_frames_folder]" in picker_source
assert "[motion_guide_frames_folder]" in picker_source
assert "if motion_guide_enabled" in picker_source
assert "if depth_enabled" in picker_source
assert "activity_paths=(original_frames_folder,)" not in picker_source
assert '"generate_original_video": False' in picker_source
assert '"original_video": ""' in picker_source
assert 'if action == "render_original_preview":' in picker_source
assert 'if action == "hide_original_preview":' in picker_source

class FakeCompletedProcess:
    @staticmethod
    def poll():
        return 0


progress_probe_node = install_engine_hooks(
    picker.HMBVideoPickerLibrary(name="reliability_progress_probe")
)
original_read_json = picker._read_json
progress_read_calls = []


def locked_progress_reader(path):
    progress_read_calls.append(path)
    raise PermissionError(13, "simulated Windows progress-file lock", str(path))


try:
    picker._read_json = locked_progress_reader
    read_return_code = progress_probe_node._wait_for_process_with_progress(
        FakeCompletedProcess(),
        Path("read.progress.json"),
        1.0,
        1.0,
        "READ progress transport regression",
        output_queue=queue.Queue(),
    )
    assert read_return_code == 0
    assert progress_read_calls == [Path("read.progress.json")]

    playblast_return_code = progress_probe_node._wait_for_process_with_progress(
        FakeCompletedProcess(),
        Path("render.progress.json"),
        1.0,
        1.0,
        "PLAYBLAST progress lock regression",
    )
    assert playblast_return_code == 0
    assert progress_read_calls == [Path("read.progress.json"), Path("render.progress.json")]
finally:
    picker._read_json = original_read_json

# Maya's progress JSON may be unavailable or locked. Completed top-level frame
# files must then reset the stall clock, while a genuinely inactive process
# must still be terminated.
class DeterministicClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += float(seconds)


original_monotonic = picker.time.monotonic
original_sleep = picker.time.sleep
original_activity_scan_interval = picker.PROCESS_OUTPUT_ACTIVITY_SCAN_INTERVAL_SECONDS
original_terminate_process = picker._terminate_process
original_activity_snapshot = picker._filesystem_activity_snapshot
original_watchdog_read_json = picker._read_json
terminated_processes = []

try:
    picker.PROCESS_OUTPUT_ACTIVITY_SCAN_INTERVAL_SECONDS = 0.05
    picker._terminate_process = lambda process: terminated_processes.append(process)

    # Repeat past the requested 10-run threshold. Unique child names/counts make
    # this independent of unreliable Windows parent-directory mtime behavior.
    for activity_iteration in range(12):
        with tempfile.TemporaryDirectory() as frame_activity_dir:
            frame_root = Path(frame_activity_dir) / "frames"
            activity_clock = DeterministicClock()
            picker.time.monotonic = activity_clock.monotonic
            picker.time.sleep = activity_clock.sleep

            class FrameProducingProcess:
                pid = 501

                def __init__(self):
                    self.created = set()

                def poll(self):
                    for threshold, name in (
                        (0.15, "frame.000000.png"),
                        (0.40, "frame.000001.png"),
                        (0.65, "frame.000002.png"),
                    ):
                        if activity_clock.value >= threshold and name not in self.created:
                            # The Maya runner atomically moves each completed
                            # frame into the top level of frames_folder.
                            frame_root.mkdir(parents=True, exist_ok=True)
                            (frame_root / name).write_bytes(
                                f"{activity_iteration}:{name}".encode("utf-8")
                            )
                            self.created.add(name)
                    return 0 if activity_clock.value >= 0.85 else None

            activity_node = install_engine_hooks(
                picker.HMBVideoPickerLibrary(name="reliability_activity")
            )
            activity_process = FrameProducingProcess()
            activity_return_code = activity_node._wait_for_process_with_progress(
                activity_process,
                Path(frame_activity_dir) / "render.progress.json",
                2.0,
                0.35,
                "PLAYBLAST frame output activity regression",
                activity_paths=(frame_root,),
            )
            assert activity_return_code == 0
            assert len(activity_process.created) == 3
            assert terminated_processes == []

    # Healthy structured progress is primary and must not trigger repeated
    # direct-child scans of a growing sequence.
    json_clock = DeterministicClock()
    picker.time.monotonic = json_clock.monotonic
    picker.time.sleep = json_clock.sleep
    activity_snapshot_calls = []

    def counted_activity_snapshot(paths):
        activity_snapshot_calls.append(tuple(paths))
        return original_activity_snapshot(paths)

    class HealthyJsonProcess:
        pid = 504

        @staticmethod
        def poll():
            return 0 if json_clock.value >= 0.85 else None

    picker._filesystem_activity_snapshot = counted_activity_snapshot
    picker._read_json = lambda _path: {
        "stage": "rendering_frames",
        "frame_index": int(json_clock.value * 1000),
    }
    with tempfile.TemporaryDirectory() as json_activity_dir:
        json_frame_root = Path(json_activity_dir) / "frames"
        json_return_code = install_engine_hooks(
            picker.HMBVideoPickerLibrary(name="reliability_json_progress")
        )._wait_for_process_with_progress(
            HealthyJsonProcess(),
            Path(json_activity_dir) / "render.progress.json",
            2.0,
            0.35,
            "PLAYBLAST primary JSON progress regression",
            activity_paths=(json_frame_root,),
        )
    assert json_return_code == 0
    assert len(activity_snapshot_calls) == 1
    picker._filesystem_activity_snapshot = original_activity_snapshot
    picker._read_json = original_watchdog_read_json

    hang_clock = DeterministicClock()
    picker.time.monotonic = hang_clock.monotonic
    picker.time.sleep = hang_clock.sleep

    class InactiveProcess:
        pid = 502

        @staticmethod
        def poll():
            return None

    inactive_process = InactiveProcess()
    try:
        install_engine_hooks(
            picker.HMBVideoPickerLibrary(name="reliability_invalid_progress")
        )._wait_for_process_with_progress(
            inactive_process,
            Path("inactive.progress.json"),
            2.0,
            0.25,
            "PLAYBLAST genuine hang regression",
        )
        raise AssertionError("An inactive Maya process must still hit the stall timeout.")
    except TimeoutError as exc:
        assert "made no progress" in str(exc)
    assert terminated_processes == [inactive_process]

    # If Maya exits at the timeout boundary, its real return code wins. This
    # prevents a completed process from being misreported as a timeout.
    race_clock = DeterministicClock()
    picker.time.monotonic = race_clock.monotonic
    picker.time.sleep = race_clock.sleep
    terminated_processes.clear()

    class ExitAtTimeoutProcess:
        pid = 503

        def __init__(self):
            self.boundary_polls = 0

        def poll(self):
            if race_clock.value < 0.1:
                return None
            self.boundary_polls += 1
            return 0 if self.boundary_polls >= 2 else None

    exit_process = ExitAtTimeoutProcess()
    exit_return_code = install_engine_hooks(
        picker.HMBVideoPickerLibrary(name="reliability_exit_progress")
    )._wait_for_process_with_progress(
        exit_process,
        Path("exit.progress.json"),
        0.05,
        10.0,
        "PLAYBLAST exit-before-timeout regression",
    )
    assert exit_return_code == 0
    assert exit_process.boundary_polls == 2
    assert terminated_processes == []
finally:
    picker.time.monotonic = original_monotonic
    picker.time.sleep = original_sleep
    picker.PROCESS_OUTPUT_ACTIVITY_SCAN_INTERVAL_SECONDS = original_activity_scan_interval
    picker._terminate_process = original_terminate_process
    picker._filesystem_activity_snapshot = original_activity_snapshot
    picker._read_json = original_watchdog_read_json

# One metadata-only full-scene READ must publish exact Maya values into
# Playblast Settings and move the UI from step 1 to the Outliner-ready step
# without rendering, encoding, or publishing an Original preview.
with tempfile.TemporaryDirectory() as temp_dir:
    temp_root = Path(temp_dir)
    scene_path = temp_root / "shot.mb"
    scene_path.write_bytes(b"Maya full-read process placeholder")
    mayabatch_path = temp_root / "Autodesk" / "Maya2027" / "bin" / "mayabatch.exe"
    mayabatch_path.parent.mkdir(parents=True)
    mayabatch_path.write_bytes(b"")
    ffmpeg_path = temp_root / "ffmpeg.exe"
    ffmpeg_path.write_bytes(b"")
    original_find_mayabatch = picker._find_mayabatch
    original_find_ffmpeg = picker._find_ffmpeg
    original_popen = picker.subprocess.Popen
    captured_maya_jobs = []
    captured_ffmpeg_commands = []

    class FakeFullReadPopen:
        def __init__(self, command, **kwargs):
            self.returncode = 0
            self.pid = 4242
            env = kwargs.get("env") or {}
            if "HMB_VIDEO_PICKER_JOB" in env:
                job_path = Path(env["HMB_VIDEO_PICKER_JOB"])
                job = json.loads(job_path.read_text(encoding="utf-8"))
                captured_maya_jobs.append(job)
                if job.get("operation") == "scan":
                    Path(job["result_path"]).write_text(json.dumps({
                        "ok": True,
                        "operation": "scan",
                        "maya_version": "2027",
                        "scene_path": str(scene_path),
                        "cameras": [{"name": "shotCam", "full_path": "|shotCam", "default_camera": False}],
                        "selected_camera": "|shotCam",
                        "warnings": [
                            "Reference skipped because it could not be loaded: P:/assets/Missing/Missing.ma (Maya command error)"
                        ],
                        "start_frame": 1001.0,
                        "current_frame": 1024.0,
                        "end_frame": 1048.0,
                        "fps": 23.976,
                        "outliner_nodes": [{
                            "name": "Actor_GRP",
                            "full_path": "|Actor_GRP",
                            "parent_path": "",
                            "maya_uuid": "actor-uuid",
                        }],
                        "original_frames_folder": "",
                         "original_output_name": "",
                         "original_frame_count": 0,
                         "scene_dependency_paths": [str(scene_path)],
                         "script_node_report": {
                             "script_node_count": 0,
                             "disabled_count": 0,
                             "disabled_nodes": [],
                         },
                     }), encoding="utf-8")
                    self.stdout = io.StringIO("[HMBVideoPicker][SUCCESS] metadata-only scene read complete\n")
                elif job.get("operation") == "render":
                    frames_folder = Path(job["frames_folder"])
                    frames_folder.mkdir(parents=True, exist_ok=True)
                    (frames_folder / f"{job['output_name']}.000000.png").write_bytes(b"fake png")
                    Path(job["sidecar_path"]).write_text(json.dumps({
                         "warnings": [],
                         "render_method": "Viewport 2.0 OGS",
                         "scene_path": str(scene_path),
                         "camera": job["camera"],
                         "start_frame": job["start_frame"],
                         "end_frame": job["end_frame"],
                         "fps": job["fps"],
                         "frame_count": 48,
                         "resolution": {
                             "width": job["width"],
                             "height": job["height"],
                         },
                         "assignment_mode": picker.ORIGINAL_LAMBERT_ASSIGNMENT_MODE,
                         "original_material_override_profile": (
                             picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
                         ),
                         "original_material_override_report": {
                             "profile": picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
                             "requested": True,
                             "status": "restored",
                             "restore_ok": True,
                             "shading_group_membership_preserved": True,
                             "one_lambert_per_source_material": True,
                             "default_lighting_verified": True,
                             "textured_render_mode_verified": True,
                             "inspected_shading_engine_count": 2,
                             "source_material_count": 2,
                             "temporary_lambert_count": 2,
                             "existing_lambert_count": 0,
                             "texture_connection_count": 2,
                             "numeric_color_count": 0,
                             "loaded_plugin_passthrough_count": 0,
                             "loaded_plugin_nodes": [],
                             "plugin_fallback_count": 0,
                             "plugin_fallback_material_count": 0,
                             "plugin_fallback_node_count": 0,
                             "plugin_fallback_records": [],
                             "texture_identity_preserved": True,
                             "warnings": [],
                             "swapped_shading_engine_count": 2,
                         },
                         "markers": [],
                         "scene_dependency_paths": [str(scene_path)],
                         "script_node_report": {
                             "script_node_count": 0,
                             "disabled_count": 0,
                             "disabled_nodes": [],
                         },
                         "viewport_quality_profile": picker.ORIGINAL_VIEWPORT_QUALITY_PROFILE,
                        "viewport_quality_report": {
                            "profile": picker.ORIGINAL_VIEWPORT_QUALITY_PROFILE,
                            "smooth_mesh_preview_mode": 3,
                            "smooth_mesh_shape_count": 8,
                            "remaining_bounding_box_count": 0,
                            "unsupported_proxy_shapes": [],
                            "technical_dummy_shapes": [],
                            "reference_loading": {
                                "proxy_set_count": 1,
                                "standard_reference_loaded_count": 2,
                            },
                        },
                    }), encoding="utf-8")
                    Path(job["result_path"]).write_text(json.dumps({
                        "ok": True,
                        "operation": "render",
                        "maya_version": "2027",
                        "scene_path": str(scene_path),
                        "frames_folder": job["frames_folder"],
                        "sidecar_path": job["sidecar_path"],
                        "fps": job["fps"],
                        "frame_count": 48,
                        "viewport_quality_profile": picker.ORIGINAL_VIEWPORT_QUALITY_PROFILE,
                    }), encoding="utf-8")
                    self.stdout = None
                else:
                    raise AssertionError(f"Unexpected Maya test job: {job.get('operation')}")
            else:
                captured_ffmpeg_commands.append(list(command))

                def mp4_box(box_type, payload):
                    return (
                        (8 + len(payload)).to_bytes(4, "big")
                        + box_type
                        + payload
                    )

                Path(command[-1]).write_bytes(
                    mp4_box(b"ftyp", b"isom\x00\x00\x02\x00isom")
                    + mp4_box(b"mdat", b"video")
                    + mp4_box(b"moov", b"meta")
                )
                self.stdout = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    try:
        picker._find_mayabatch = lambda: mayabatch_path
        picker._find_ffmpeg = lambda _mayabatch=None: ffmpeg_path
        picker.subprocess.Popen = FakeFullReadPopen
        full_read_node = install_engine_hooks(
            picker.HMBVideoPickerLibrary(name="reliability_full_read")
        )
        configured_state = full_read_node._picker_state()
        configured_state.update({"output_width": 1920, "output_height": 1080})
        full_read_node._write_state(configured_state)
        full_read_node._read_scene_mode(str(scene_path))
        full_read_state = full_read_node._picker_state()
        assert full_read_state["status"] == "OUTLINER_READY"
        assert full_read_state["scene_stage"] == "OUTLINER_READY"
        assert full_read_state["scene_request_status"] == "COMPLETE"
        assert full_read_state["native_read_ready"] is True
        assert full_read_state["native_read_mode"] == "maya-batch-atomic"
        assert full_read_state["start_frame"] == 1001.0
        assert full_read_state["current_frame"] == 1024.0
        assert full_read_state["end_frame"] == 1048.0
        assert full_read_state["source_fps"] == 23.976
        assert full_read_state["output_fps"] == 23.976
        assert full_read_state["output_width"] == 1920
        assert full_read_state["output_height"] == 1080
        assert len(captured_maya_jobs) == 1
        assert captured_maya_jobs[0]["operation"] == "scan"
        assert captured_maya_jobs[0]["generate_original_video"] is False
        assert "width" not in captured_maya_jobs[0]
        assert "height" not in captured_maya_jobs[0]
        assert captured_ffmpeg_commands == []
        assert full_read_state["maya_version"] == "2027"
        assert full_read_state["native_source_version"] == "2027"
        assert full_read_state["selected_camera"] == "|shotCam"
        assert full_read_state["outliner_nodes"][0]["full_path"] == "|Actor_GRP"
        assert full_read_state["warnings"] == [
            "Reference skipped because it could not be loaded: P:/assets/Missing/Missing.ma (Maya command error)"
        ]
        assert full_read_state["native_metadata"]["outliner_group_count"] == 1
        assert full_read_state["native_metadata"]["original_video_path"] == ""
        assert full_read_state["native_metadata"]["preview_frame_count"] == 0
        assert full_read_state["original_video_path"] == ""
        assert full_read_state["original_video_url"] == ""
        assert full_read_state["original_preview_enabled"] is False
        assert full_read_state["video_path"] == ""
        assert full_read_state["video_url"] == ""
        expected_original = temp_root / "shot" / "shot_Orignal.mp4"
        expected_sidecar = temp_root / "shot" / "shot_Orignal.hmb.json"
        assert not expected_original.exists()
        assert not expected_sidecar.exists()

        # The first explicit Original request is a cache miss: one Maya render
        # and one FFmpeg encode publish the exact original pair atomically.
        first_original = full_read_node._render_original_preview_mode(str(scene_path))
        first_original_state = full_read_node._picker_state()
        assert first_original["mode"] == "original_preview"
        assert first_original["cached"] is False
        assert len(captured_maya_jobs) == 2
        assert captured_maya_jobs[1]["operation"] == "render"
        assert captured_maya_jobs[1]["apply_marker_shaders"] is False
        assert captured_maya_jobs[1]["apply_original_lambert_override"] is True
        assert (
            captured_maya_jobs[1]["original_material_override_profile"]
            == picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        )
        assert captured_maya_jobs[1]["force_high_quality_viewport"] is True
        assert (
            captured_maya_jobs[1]["viewport_quality_profile"]
            == picker.ORIGINAL_VIEWPORT_QUALITY_PROFILE
        )
        assert captured_maya_jobs[1]["width"] == 1920
        assert captured_maya_jobs[1]["height"] == 1080
        assert len(captured_ffmpeg_commands) == 1
        assert any("scale=1920:1080:flags=lanczos" in part for part in captured_ffmpeg_commands[0])
        assert first_original_state["original_preview_enabled"] is True
        assert (
            Path(first_original_state["original_video_path"]).resolve()
            == expected_original.resolve()
        )
        assert expected_original.is_file()
        assert expected_sidecar.is_file()
        assert first_original_state["original_video_url"]
        assert (
            Path(first_original_state["video_path"]).resolve()
            == expected_original.resolve()
        )
        assert first_original_state["video_url"]

        # The same explicit request is a validated cache hit. It must not launch
        # Maya or FFmpeg again, and it must keep the exact published pair active.
        maya_job_count = len(captured_maya_jobs)
        ffmpeg_count = len(captured_ffmpeg_commands)
        second_original = full_read_node._render_original_preview_mode(str(scene_path))
        second_original_state = full_read_node._picker_state()
        assert second_original["mode"] == "original_preview_cache"
        assert second_original["cached"] is True
        assert len(captured_maya_jobs) == maya_job_count
        assert len(captured_ffmpeg_commands) == ffmpeg_count
        assert second_original_state["original_preview_enabled"] is True
        assert (
            Path(second_original_state["original_video_path"]).resolve()
            == expected_original.resolve()
        )
        assert (
            Path(second_original_state["video_path"]).resolve()
            == expected_original.resolve()
        )
        full_read_node._cleanup_transient_paths()
    finally:
        picker._find_mayabatch = original_find_mayabatch
        picker._find_ffmpeg = original_find_ffmpeg
        picker.subprocess.Popen = original_popen

# Every packaged marker survives normalization; legacy choices are rejected.
raw_markers = [
    {
        "color": name,
        "asset_id": f"Asset_{index}",
        "subject_root": f"|Asset_{index}",
        "video_slot": 1,
        "picker_order": index,
    }
    for index, name in enumerate(picker.MARKER_ORDER, start=1)
]
normalized_markers = picker._normalize_markers(raw_markers, 1)
assert [item["color"] for item in normalized_markers] == picker.MARKER_ORDER
assert picker._normalize_markers([
    {"color": "Cyan", "asset_id": "Legacy", "subject_root": "|Legacy"}
]) == []
shared_background_markers = picker._normalize_markers([
    {"color": "Sky Blue", "asset_id": "BackgroundA", "subject_root": "|BackgroundA"},
    {"color": "Sky Blue", "asset_id": "BackgroundB", "subject_root": "|BackgroundB"},
    {"color": "Direction Checker", "asset_id": "CheckerA", "subject_root": "|CheckerA"},
    {"color": "Direction Checker", "asset_id": "CheckerB", "subject_root": "|CheckerB"},
], 1)
assert [item["asset_id"] for item in shared_background_markers] == [
    "BackgroundA", "BackgroundB", "CheckerA", "CheckerB",
]
assert len(picker._normalize_markers([
    {"color": "Red", "asset_id": "ActorA", "subject_root": "|ActorA"},
    {"color": "Red", "asset_id": "ActorB", "subject_root": "|ActorB"},
], 1)) == 1

shared_background_state = picker._default_widget_state()
shared_background_state["slot_assignments"] = [{
    "video_slot": 1,
    "bindings": [
        {
            "group_name": "BackgroundA",
            "full_dag_path": "|BackgroundA",
            "maya_uuid": "bg-a",
            "color": "Sky Blue",
            "enabled": True,
            "video_slot": 1,
            "picker_order": 1,
        },
        {
            "group_name": "BackgroundB",
            "full_dag_path": "|BackgroundB",
            "maya_uuid": "bg-b",
            "color": "Sky Blue",
            "enabled": True,
            "video_slot": 1,
            "picker_order": 2,
        },
    ],
}]
assert len(node._selected_slot_job_bindings(shared_background_state, 1)) == 2
duplicate_actor_state = copy.deepcopy(shared_background_state)
for binding in duplicate_actor_state["slot_assignments"][0]["bindings"]:
    binding["color"] = "Red"
try:
    node._selected_slot_job_bindings(duplicate_actor_state, 1)
except RuntimeError as exc:
    assert "Duplicate Color Pick" in str(exc)
else:
    raise AssertionError("Actor Color Picks must remain unique.")
duplicate_root_state = copy.deepcopy(shared_background_state)
duplicate_root_state["slot_assignments"][0]["bindings"][1]["full_dag_path"] = "|BackgroundA"
try:
    node._selected_slot_job_bindings(duplicate_root_state, 1)
except RuntimeError as exc:
    assert "Duplicate Maya group" in str(exc)
else:
    raise AssertionError("Repeated background colors must not permit duplicate Maya roots.")
ffmpeg_command = picker._build_ffmpeg_encode_command(
    Path("ffmpeg"),
    Path("frames/shot.%06d.png"),
    Path("video.partial.mp4"),
    25.0,
    100,
)
assert ffmpeg_command[ffmpeg_command.index("-framerate") + 1] == "25/1"
assert "-r" not in ffmpeg_command
assert ffmpeg_command[ffmpeg_command.index("-frames:v") + 1] == "100"
assert ffmpeg_command[ffmpeg_command.index("-fps_mode") + 1] == "passthrough"
assert ffmpeg_command[ffmpeg_command.index("-preset") + 1] == "slow"
assert ffmpeg_command[ffmpeg_command.index("-crf") + 1] == "6"
assert ffmpeg_command[ffmpeg_command.index("-profile:v") + 1] == "high"
assert ffmpeg_command[ffmpeg_command.index("-level:v") + 1] == "4.2"
assert ffmpeg_command[ffmpeg_command.index("-g") + 1] == "25"
assert ffmpeg_command[ffmpeg_command.index("-keyint_min") + 1] == "25"
assert ffmpeg_command[ffmpeg_command.index("-bf") + 1] == "1"
assert ffmpeg_command[ffmpeg_command.index("-refs") + 1] == "2"
assert (
    ffmpeg_command[ffmpeg_command.index("-x264-params") + 1]
    == "colorprim=bt709:transfer=bt709:colormatrix=bt709:fullrange=off"
)
assert ffmpeg_command[ffmpeg_command.index("-color_range") + 1] == "tv"
assert ffmpeg_command[ffmpeg_command.index("-colorspace") + 1] == "bt709"
assert ffmpeg_command[ffmpeg_command.index("-color_primaries") + 1] == "bt709"
assert ffmpeg_command[ffmpeg_command.index("-color_trc") + 1] == "bt709"
assert ffmpeg_command[ffmpeg_command.index("-video_track_timescale") + 1] == "10000"
assert "-an" in ffmpeg_command
scale_filter = ffmpeg_command[ffmpeg_command.index("-vf") + 1]
assert "lanczos+accurate_rnd+full_chroma_int" in scale_filter
assert "in_range=full:out_range=tv:out_color_matrix=bt709" in scale_filter
assert scale_filter.endswith("setsar=1,format=yuv420p")
assert "fps=" not in " ".join(ffmpeg_command)
assert picker._fps_timebase(24.0) == "24/1"
assert picker._fps_timebase(23.976) == "24000/1001"
assert picker._video_track_timescale(24.0) == 10008
assert picker._video_track_timescale(25.0) == 10000
assert picker._video_track_timescale(23.976) == 24000

# Operation digests ignore cosmetic UI changes and invalidate relevant inputs.
with tempfile.TemporaryDirectory() as temp_dir:
    scene = Path(temp_dir) / "shot.mb"
    scene.write_bytes(b"Maya test placeholder")
    state = picker._default_widget_state()
    state.update({
        "scene_path": str(scene),
        "scene_request_path": str(scene),
        "selected_camera": "|shotCam",
        "active_slot_count": 1,
        "selected_video_slot": 1,
        "slot_assignments": [{
            "video_slot": 1,
            "bindings": [{
                "group_name": "Hero",
                "full_dag_path": "|Hero",
                "maya_uuid": "uuid-hero",
                "color": "Red",
                "enabled": True,
                "video_slot": 1,
                "picker_order": 1,
            }],
        }],
    })
    publish_lock = (
        picker._scene_output_folder(scene)
        / ".hmb_video_picker"
        / "shot.playblast.publish.lock"
    )
    with picker._playblast_publish_guard(scene):
        assert publish_lock.is_file()
    assert publish_lock.is_file()
    assert publish_lock.parent.is_dir()

    try:
        with picker._playblast_publish_guard(scene):
            assert publish_lock.is_file()
            raise RuntimeError("intentional publication failure")
    except RuntimeError as exc:
        assert str(exc) == "intentional publication failure"
    else:
        raise AssertionError("The guard must propagate publication failures.")
    assert publish_lock.is_file()
    assert publish_lock.parent.is_dir()

    publish_lock.parent.mkdir(parents=True, exist_ok=True)
    sibling_artifact = publish_lock.parent / "keep.partial"
    sibling_artifact.write_bytes(b"in progress")
    with picker._playblast_publish_guard(scene):
        assert publish_lock.is_file()
    assert publish_lock.is_file()
    assert publish_lock.parent.is_dir()
    assert sibling_artifact.is_file()

    read_digest = picker._operation_input_digest("read_scene", scene, state, 1)
    cosmetic = copy.deepcopy(state)
    cosmetic["language"] = "ko"
    cosmetic["activity_log_text"] = "display only"
    assert picker._operation_input_digest("read_scene", scene, cosmetic, 1) == read_digest

    original_digest = picker._operation_input_digest(
        "render_original_preview", scene, state, 1
    )
    marker_only_change = copy.deepcopy(state)
    marker_only_change["slot_assignments"][0]["bindings"][0]["color"] = "Green"
    assert (
        picker._operation_input_digest(
            "render_original_preview", scene, marker_only_change, 1
        )
        == original_digest
    )
    original_camera_change = copy.deepcopy(state)
    original_camera_change["selected_camera"] = "|otherCam"
    assert (
        picker._operation_input_digest(
            "render_original_preview", scene, original_camera_change, 1
        )
        != original_digest
    )
    original_resolution_change = copy.deepcopy(state)
    original_resolution_change.update({"output_width": 1920, "output_height": 1080})
    assert (
        picker._operation_input_digest(
            "render_original_preview", scene, original_resolution_change, 1
        )
        != original_digest
    )

    run_digest = picker._operation_input_digest("run_video", scene, state, 1)
    cosmetic["language"] = "en"
    assert picker._operation_input_digest("run_video", scene, cosmetic, 1) == run_digest
    changed = copy.deepcopy(state)
    changed["slot_assignments"][0]["bindings"][0]["color"] = "Green"
    assert picker._operation_input_digest("run_video", scene, changed, 1) != run_digest
    changed = copy.deepcopy(state)
    changed["selected_camera"] = "|otherCam"
    assert picker._operation_input_digest("run_video", scene, changed, 1) != run_digest
    visibility_changed = copy.deepcopy(state)
    visibility_changed["slot_visibility"] = [{
        "video_slot": 1,
        "hidden_paths": ["|SetB", "|SetA", "|SetA"],
    }]
    visibility_digest = picker._operation_input_digest(
        "run_video", scene, visibility_changed, 1
    )
    assert visibility_digest != run_digest
    reordered_visibility = copy.deepcopy(visibility_changed)
    reordered_visibility["slot_visibility"][0]["hidden_paths"] = ["|SetA", "|SetB"]
    assert (
        picker._operation_input_digest(
            "run_video", scene, reordered_visibility, 1
        )
        == visibility_digest
    )
    assert (
        picker._operation_input_digest(
            "render_snapshot", scene, visibility_changed, 1
        )
        != picker._operation_input_digest("render_snapshot", scene, state, 1)
    )
    assert (
        picker._operation_input_digest(
            "render_original_preview", scene, visibility_changed, 1
        )
        == original_digest
    )
    assert (
        picker._operation_input_digest("read_scene", scene, visibility_changed, 1)
        == read_digest
    )

# PICKER_OUT uses the same 14-choice vocabulary and Prompt binds exact Asset IDs.
picker_state = picker._default_widget_state()
picker_state.update({
    "scene_path": "C:/show/shot.mb",
    "active_slot_count": 2,
    "selected_video_slot": 2,
    "videos": [
        {
            "video_slot": 1,
            "video_uid": "reliability-hero-mask",
            "source_uid": "reliability-hero-mask",
            "video_path": "C:/show/shot/shot_playblast_1.mp4",
            "camera": "|shotCam",
            "markers": [{
                "color": "Red",
                "asset_id": "Hero",
                "subject_root": "|Hero",
                "video_slot": 1,
                "picker_order": 1,
            }],
        },
        {
            "video_slot": 2,
            "video_uid": "reliability-ground-mask",
            "source_uid": "reliability-ground-mask",
            "video_path": "C:/show/shot/shot_playblast_2.mp4",
            "camera": "|shotCam",
            "markers": [
                {
                    "color": "Floor Grid",
                    "asset_id": "Ground",
                    "subject_root": "|Ground",
                    "video_slot": 2,
                    "picker_order": 1,
                },
                {
                    "color": "Floor Grid",
                    "asset_id": "Trees",
                    "subject_root": "|Trees",
                    "video_slot": 2,
                    "picker_order": 2,
                },
            ],
        },
    ],
})
payload = node._build_picker_payload(picker_state)
assert payload["schema"] == "hmb-prompt-library-picker-binding"
assert payload["schema_version"] == 5
assert payload["marker_catalog_version"] == catalog["version"]
assert [item["video_slot"] for item in payload["videos"]] == [1, 2]
assert payload["ordered_video_uids"] == [
    "reliability-hero-mask",
    "reliability-ground-mask",
]
assert [item["color"] for item in payload["markers"]] == ["Red", "Floor Grid", "Floor Grid"]

prompt_state = prompt._default_widget_state()
prompt_state["images"][0].update(
    present=True,
    label="Hero",
    image_main_type="Character",
    image_sub_type="Full Appearance",
)
prompt_state["images"].append(prompt._default_image_item(2))
prompt_state["images"][1].update(
    present=True,
    label="Ground",
    image_main_type="Environment / Background",
    image_sub_type="Ground / Floor",
)
prompt_state["images"].append(prompt._default_image_item(3))
prompt_state["images"][2].update(
    present=True,
    label="Trees",
    image_main_type="Environment / Background",
    image_sub_type="Main Background",
)
applied = prompt._apply_picker_payload(prompt_state, payload, connected=True)
assert applied["images"][0]["color_picks"] == ["Red"]
assert applied["images"][0]["marker_video"] == 1
assert applied["images"][1]["color_picks"] == ["Floor Grid"]
assert applied["images"][1]["marker_video"] == 2
assert applied["images"][2]["color_picks"] == [""]
assert [item["asset_id"] for item in applied["picker"]["markers"] if item["color"] == "Floor Grid"] == [
    "Ground", "Trees",
]
assert applied["videos"][0]["label"] == "shot_playblast_1"
assert applied["videos"][1]["label"] == "shot_playblast_2"
assert applied["videos"][0]["video_main_type"] == "Maya Preview / Playblast"
assert applied["videos"][0]["video_sub_type"] == "Original Preview"
assert applied["videos"][0]["source_type"] == "Unified Shot-Control Video"
assert applied["videos"][0]["control_role"] == "Primary Unified Shot Control"
compiled_picker_prompt = prompt._build_prompt_package(applied)
assert agent._is_hmb_prompt_library_payload(compiled_picker_prompt)

# The four patterns use reserved categorical Surface Shader IDs. A host-side
# frame-global compositor replaces them without reading UVs or object bounds.
maya_package = types.ModuleType("maya")
maya_cmds = types.ModuleType("maya.cmds")
maya_package.cmds = maya_cmds
sys.modules.setdefault("maya", maya_package)
sys.modules.setdefault("maya.cmds", maya_cmds)
maya_runner = load(
    "HMB_Maya_Background_Preview_regression",
    ROOT / "resources/maya/HMB_Maya_Background_Preview.py",
)
reference_parent_map = {
    "|CH|AnimalKidLion:All_G|AnimalKidLion:geo_GRP|AnimalKidLion:Body": "|CH|AnimalKidLion:All_G|AnimalKidLion:geo_GRP",
    "|CH|AnimalKidLion:All_G|AnimalKidLion:geo_GRP": "|CH|AnimalKidLion:All_G",
    "|CH|AnimalKidLion:All_G": "|CH",
    "|CH": "",
}
reference_nodes = {
    "|CH|AnimalKidLion:All_G|AnimalKidLion:geo_GRP|AnimalKidLion:Body": "AnimalKidLionRN",
    "|CH|AnimalKidLion:All_G|AnimalKidLion:geo_GRP": "AnimalKidLionRN",
    "|CH|AnimalKidLion:All_G": "AnimalKidLionRN",
}
root, reference_node = maya_runner._asset_root_from_transform(
    "|CH|AnimalKidLion:All_G|AnimalKidLion:geo_GRP|AnimalKidLion:Body",
    lambda node: reference_parent_map.get(node, ""),
    lambda node: reference_nodes.get(node, ""),
)
assert root == "|CH|AnimalKidLion:All_G"
assert reference_node == "AnimalKidLionRN"
assert maya_runner._reference_asset_label(
    root,
    reference_node,
    "P:/projects/assets/AnimalKidLion/AnimalKidLion.mb",
) == "AnimalKidLion"

local_parent_map = {
    "|HMB_Test_Objects_GRP|HMB_Test_Cube": "|HMB_Test_Objects_GRP",
    "|HMB_Test_Objects_GRP": "",
    "|DUMMY|DUMMY_Mesh": "|DUMMY",
    "|DUMMY": "",
    "|CheckBox:CheckpCube": "",
}
local_root, local_reference = maya_runner._asset_root_from_transform(
    "|HMB_Test_Objects_GRP|HMB_Test_Cube",
    lambda node: local_parent_map.get(node, ""),
    lambda _node: "",
)
assert local_root == "|HMB_Test_Objects_GRP|HMB_Test_Cube"
assert local_reference == ""
assert maya_runner._asset_root_from_transform(
    "|DUMMY|DUMMY_Mesh",
    lambda node: local_parent_map.get(node, ""),
    lambda _node: "",
) == ("", "")
assert maya_runner._asset_root_from_transform(
    "|CheckBox:CheckpCube",
    lambda node: local_parent_map.get(node, ""),
    lambda _node: "",
) == ("", "")
fractional_frames = maya_runner._frame_values(1.0416666666666667, 125.0)
assert fractional_frames[0] == 1.0416666666666667
assert fractional_frames[-1] == 125.0
assert len(fractional_frames) == 125
assert maya_runner._frame_values(101.0, 103.0) == [101.0, 102.0, 103.0]
maya_runner._load_marker_catalog({
    "marker_catalog_path": str(catalog_path),
    "marker_catalog_version": catalog["version"],
})
assert maya_runner.CHARACTER_MARKERS == set(expected_actor)
assert maya_runner.BACKGROUND_MARKERS == set(expected_object)
assert maya_runner.REPEATABLE_MARKERS == set(expected_object)
assert maya_runner.CHARACTER_LAMBERT_DIFFUSE == 0.55
assert maya_runner.CHARACTER_LAMBERT_AMBIENT_GAIN == 0.0
assert maya_runner.CHARACTER_LAMBERT_INCANDESCENCE_GAIN == 0.25
assert maya_runner.CHARACTER_OUT_RIM_OPACITY == 0.08
assert maya_runner.CHARACTER_OUT_RIM_MIN_PIXEL_WIDTH == 0.35
assert maya_runner.CHARACTER_OUT_RIM_MAX_PIXEL_WIDTH == 0.6
assert maya_runner.CHARACTER_OUT_RIM_LINE_OFFSET == 0.0
assert maya_runner.CHARACTER_OUT_RIM_SCREENSPACE_RESAMPLING == 0.0
assert maya_runner.CHARACTER_OUT_RIM_LOCAL_OCCLUSION == 2
marker_payload_records = [{
    "color": "Red",
    "asset_id": "Hero",
    "subject_root": "|Hero",
    "group_name": "Hero",
    "full_dag_path": "|Hero",
    "maya_uuid": "hero-uuid",
}]
for index, color in enumerate(("Sky Blue", "Mint", "Beige"), start=1):
    marker_payload_records.append({
        "color": color,
        "asset_id": "SolidBackground{0}".format(index),
        "subject_root": "|SolidBackground{0}".format(index),
        "group_name": "SolidBackground{0}".format(index),
        "full_dag_path": "|SolidBackground{0}".format(index),
        "maya_uuid": "solid-background-{0}".format(index),
    })
for index, color in enumerate(("Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"), start=1):
    marker_payload_records.append({
        "color": color,
        "asset_id": "PatternBackground{0}".format(index),
        "subject_root": "|PatternBackground{0}".format(index),
        "group_name": "PatternBackground{0}".format(index),
        "full_dag_path": "|PatternBackground{0}".format(index),
        "maya_uuid": "pattern-background-{0}".format(index),
    })
marker_payload_probe = maya_runner._marker_payload(marker_payload_records)
assert marker_payload_probe[0]["shader_model"] == "lambert"
assert marker_payload_probe[0]["visual_profile"] == "color_stable_lambert_profile"
assert marker_payload_probe[0]["out_rim"] == ""
assert marker_payload_probe[0]["shading_profile"] == {
    "profile": "color_stable_lambert_profile",
    "diffuse": 0.55,
    "ambient_gain": 0.0,
    "incandescence_gain": 0.25,
    "viewport_lighting": "maya_default_lighting",
    "viewport_render_mode": "smooth_shaded_textured",
    "out_rim": "none",
}
for solid_background_payload in marker_payload_probe[1:4]:
    assert solid_background_payload["shader_model"] == "lambert"
    assert solid_background_payload["visual_profile"] == "color_stable_lambert_profile"
    assert solid_background_payload["out_rim"] == ""
    assert solid_background_payload["shading_profile"] == marker_payload_probe[0]["shading_profile"]
for pattern_payload in marker_payload_probe[4:]:
    assert pattern_payload["shader_model"] == "surfaceShader"
    assert pattern_payload["visual_profile"] == "hmb_maya_world_root_projection_v1"
    assert pattern_payload["out_rim"] == ""
    assert pattern_payload["shading_profile"]["pattern_space"] == "background_root"
    assert pattern_payload["shading_profile"]["base_cell_world_units"] == 15.0
    assert pattern_payload["shading_profile"]["density_multiplier"] == 3.0
    assert pattern_payload["shading_profile"]["cell_size_world_units"] == 5.0
    assert pattern_payload["shading_profile"]["camera_anchored"] is False
    assert pattern_payload["shading_profile"]["uv_dependent"] is False
    assert pattern_payload["shading_profile"]["projection_type"] in {
        "Planar",
        "TriPlanar",
    }
    assert pattern_payload["shading_profile"]["projection_axis"] in {"XZ", "XYZ"}

legacy_marker_payload_probe = maya_runner._marker_payload(
    marker_payload_records,
    pattern_profile=maya_runner.SCREEN_SPACE_PATTERN_PROFILE,
)
for pattern_payload in legacy_marker_payload_probe[4:]:
    assert pattern_payload["visual_profile"] == "hmb_screen_space_pattern_post_v2"
    assert pattern_payload["shading_profile"]["pattern_space"] == "screen"
    assert pattern_payload["shading_profile"]["phase_origin"] == "frame_top_left"
    assert pattern_payload["shading_profile"]["linear_scale_divisor"] == 3
    assert len(pattern_payload["shading_profile"]["categorical_id_rgb"]) == 3
assert maya_runner._pattern_pixel("direction_checker", 0, 0, 512) == (0, 0, 0)
assert maya_runner._pattern_pixel("direction_checker", 20, 0, 512) == (0, 0, 0)
assert maya_runner._pattern_pixel("direction_checker", 21, 0, 512) == (255, 255, 255)
assert maya_runner._pattern_pixel("position_pattern", 0, 0, 512) == (239, 65, 65)
assert maya_runner._pattern_pixel("position_pattern", 511, 0, 512) == (62, 205, 119)
assert maya_runner._pattern_pixel("position_pattern", 0, 511, 512) == (57, 104, 232)
assert maya_runner._pattern_pixel("position_pattern", 511, 511, 512) == (246, 210, 49)
assert maya_runner._pattern_pixel("position_pattern", 256, 256, 512) == (255, 255, 255)
assert maya_runner._pattern_pixel("position_pattern", 100, 10, 512) == (62, 205, 119)
assert maya_runner._pattern_pixel("position_pattern", 100, 100, 512) == (246, 210, 49)
assert maya_runner._pattern_pixel("position_pattern", 180, 10, 512) == (239, 65, 65)

original_resolve_group_root = maya_runner._resolve_group_root
try:
    maya_runner._resolve_group_root = lambda name: "|" + str(name).lstrip("|")
    repeated_runner_bindings = maya_runner._read_job_bindings({
        "bindings": [
            {"group_name": "BackgroundA", "color": "Sky Blue", "asset_id": "BackgroundA"},
            {"group_name": "BackgroundB", "color": "Sky Blue", "asset_id": "BackgroundB"},
            {"group_name": "CheckerA", "color": "Direction Checker", "asset_id": "CheckerA"},
            {"group_name": "CheckerB", "color": "Direction Checker", "asset_id": "CheckerB"},
        ],
    })
    assert len(repeated_runner_bindings) == 4
    try:
        maya_runner._read_job_bindings({
            "bindings": [
                {"group_name": "ActorA", "color": "Red", "asset_id": "ActorA"},
                {"group_name": "ActorB", "color": "Red", "asset_id": "ActorB"},
            ],
        })
    except RuntimeError as exc:
        assert "Duplicate marker color" in str(exc)
    else:
        raise AssertionError("Maya runner must reject duplicate Actor colors.")
finally:
    maya_runner._resolve_group_root = original_resolve_group_root
legacy_outline_probe = maya_runner._marker_payload(
    [{
        "color": "Red",
        "asset_id": "Hero",
        "subject_root": "|Hero",
        "group_name": "Hero",
        "full_dag_path": "|Hero",
        "maya_uuid": "hero-uuid",
    }],
    character_outline_mode="pfx_toon",
)[0]
assert legacy_outline_probe["visual_profile"] == "lambert_with_pfxToon_profile"
assert legacy_outline_probe["out_rim"] == "pfxToon_profile"
assert legacy_outline_probe["shading_profile"]["profile"] == "pfxToon_profile"
assert legacy_outline_probe["shading_profile"]["out_rim_opacity"] == 0.08
original_reference_ls = getattr(maya_cmds, "ls", None)
try:
    maya_cmds.ls = lambda type=None: [
        "sharedReferenceNode",
        "_UNKNOWN_REF_NODE_",
        "SavannaLt_Set_sharedReferenceNode",
        "GoodRN",
    ] if type == "reference" else []
    assert maya_runner._reference_nodes() == ["GoodRN"]
finally:
    if original_reference_ls is None:
        delattr(maya_cmds, "ls")
    else:
        maya_cmds.ls = original_reference_ls

with tempfile.TemporaryDirectory() as temp_dir:
    progress_path = Path(temp_dir) / "read.progress.json"
    maya_runner._write_progress(
        {"progress_path": str(progress_path)},
        "regression",
        "Atomic Windows progress publication.",
    )
    assert json.loads(progress_path.read_text(encoding="utf-8"))["stage"] == "regression"

    reference_progress_path = Path(temp_dir) / "references.progress.json"
    original_reference_nodes = maya_runner._reference_nodes
    original_reference_query = getattr(maya_cmds, "referenceQuery", None)
    original_maya_file = getattr(maya_cmds, "file", None)
    reference_loaded = {"GoodRN": False, "MissingRN": False, "LateRN": False}
    reference_files = {
        "GoodRN": "P:/assets/Good/Good.mb",
        "MissingRN": "P:/assets/Missing/Missing.ma",
        "LateRN": "P:/assets/Late/Late.mb",
    }

    def reference_query(node, isLoaded=False, filename=False, withoutCopyNumber=False):
        if isLoaded:
            return reference_loaded[node]
        if filename:
            return reference_files[node]
        raise AssertionError("Unexpected referenceQuery call")

    def maya_file(loadReference=None, **_kwargs):
        if loadReference == "MissingRN":
            raise RuntimeError("Maya command error")
        reference_loaded[loadReference] = True

    try:
        maya_runner._reference_nodes = lambda: ["GoodRN", "MissingRN", "LateRN"]
        maya_cmds.referenceQuery = reference_query
        maya_cmds.file = maya_file
        reference_warnings = maya_runner._load_all_references_with_progress({
            "progress_path": str(reference_progress_path),
        })
        assert reference_loaded["GoodRN"] is True
        assert reference_loaded["MissingRN"] is False
        assert reference_loaded["LateRN"] is True
        assert len(reference_warnings) == 1
        assert "P:/assets/Missing/Missing.ma" in reference_warnings[0]
        reference_progress = json.loads(reference_progress_path.read_text(encoding="utf-8"))
        assert reference_progress["stage"] == "references_loaded"
        assert reference_progress["reference_count"] == 2
        assert reference_progress["skipped_reference_count"] == 1
    finally:
        maya_runner._reference_nodes = original_reference_nodes
        if original_reference_query is None:
            delattr(maya_cmds, "referenceQuery")
        else:
            maya_cmds.referenceQuery = original_reference_query
        if original_maya_file is None:
            delattr(maya_cmds, "file")
        else:
            maya_cmds.file = original_maya_file

    scan_result_path = Path(temp_dir) / "scan.result.json"
    original_scan_outliner_nodes = maya_runner._scan_outliner_nodes
    original_scan_cameras = maya_runner._scan_cameras
    original_scene_fps = maya_runner._scene_fps
    original_playback_options = getattr(maya_cmds, "playbackOptions", None)
    original_current_time = getattr(maya_cmds, "currentTime", None)
    try:
        maya_runner._scan_outliner_nodes = lambda progress: [{
            "name": "Actor_GRP",
            "full_path": "|Actor_GRP",
            "parent_path": "",
            "maya_uuid": "actor-uuid",
        }]
        maya_runner._scan_cameras = lambda: (
            [{"name": "shotCam", "full_path": "|shotCam", "default_camera": False}],
            "|shotCam",
        )
        maya_runner._scene_fps = lambda: 24.0
        maya_cmds.playbackOptions = lambda query=False, minTime=False, maxTime=False: 101.0 if minTime else 173.0
        maya_cmds.currentTime = lambda query=False: 125.0
        scan_result = maya_runner._scan_scene(
            {"_reference_warnings": reference_warnings},
            str(scan_result_path),
            "2024",
            str(Path(temp_dir) / "shot.mb"),
        )
        assert scan_result["ok"] is True
        assert scan_result["operation"] == "scan"
        assert scan_result["selected_camera"] == "|shotCam"
        assert scan_result["start_frame"] == 101.0
        assert scan_result["current_frame"] == 125.0
        assert scan_result["end_frame"] == 173.0
        assert scan_result["fps"] == 24.0
        assert scan_result["outliner_nodes"][0]["full_path"] == "|Actor_GRP"
        assert scan_result["warnings"] == reference_warnings
        assert json.loads(scan_result_path.read_text(encoding="utf-8"))["operation"] == "scan"
    finally:
        maya_runner._scan_outliner_nodes = original_scan_outliner_nodes
        maya_runner._scan_cameras = original_scan_cameras
        maya_runner._scene_fps = original_scene_fps
        if original_playback_options is None:
            delattr(maya_cmds, "playbackOptions")
        else:
            maya_cmds.playbackOptions = original_playback_options
        if original_current_time is None:
            delattr(maya_cmds, "currentTime")
        else:
            maya_cmds.currentTime = original_current_time

    hashes = []
    for name in expected_object[-4:]:
        pattern = maya_runner.MARKER_PATTERNS[name]
        path = Path(temp_dir) / f"{pattern}.png"
        maya_runner._write_pattern_png(str(path), pattern, 128)
        data = path.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(data) > 256
        hashes.append(hashlib.sha256(data).hexdigest())
    assert len(set(hashes)) == 4

assert "polyProjection" not in (ROOT / "resources/maya/HMB_Maya_Background_Preview.py").read_text(encoding="utf-8")
assert "cmds.file(save" not in (ROOT / "resources/maya/HMB_Maya_Background_Preview.py").read_text(encoding="utf-8")

print("HMB VideoPicker independent command transport, lifecycle, Maya/FFmpeg simulation, and Prompt integration regression: PASS")
