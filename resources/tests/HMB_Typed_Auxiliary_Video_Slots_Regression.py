from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBPromptLibrary as prompt  # noqa: E402
import HMBVideoPickerLibrary as picker  # noqa: E402


BUNDLE_ID = "typed-auxiliary-slot-regression-bundle"
AUXILIARY_SLOTS = (2, 3, 4, 5)


def primary_video(bundle_id: str = BUNDLE_ID) -> dict:
    return {
        "video_slot": 1,
        "video_uid": f"typed-mask-{bundle_id}",
        "source_uid": f"typed-mask-{bundle_id}",
        "video_path": "C:/typed_auxiliary/color.mp4",
        "camera": "|shotCam",
        "bundle_run_id": bundle_id,
        "pair_run_id": bundle_id,
        "source_fps": 24.0,
        "output_fps": 24.0,
        "fps": 24.0,
        "source_frame_count": 12,
        "output_frame_count": 12,
        "decoded_frame_count": 12,
        "frame_count": 12,
        "source_duration_seconds": 0.5,
        "output_duration_seconds": 0.5,
        "duration_seconds": 0.5,
        "start_frame": 101.0,
        "end_frame": 112.0,
        "output_width": 320,
        "output_height": 180,
        "width": 320,
        "height": 180,
        "has_maya_frame_range": True,
        "markers": [],
        "generation_role": "mask",
        "media_kind": picker.MASK_MEDIA_KIND,
        "video_role": "maya_color_assignment_mask",
    }


def depth_video(slot: int, bundle_id: str = BUNDLE_ID) -> dict:
    return {
        **primary_video(bundle_id),
        "video_slot": slot,
        "video_uid": f"typed-depth-{bundle_id}-{slot}",
        "source_uid": f"typed-depth-{bundle_id}-{slot}",
        "video_path": f"C:/typed_auxiliary/depth_{slot}.mp4",
        "markers": [],
        "media_kind": picker.DEPTH_MEDIA_KIND,
        "generation_role": "depth",
        "video_role": "maya_depth_companion",
        "source_type_hint": picker.DEPTH_SOURCE_TYPE,
        "control_role_hint": picker.DEPTH_CONTROL_ROLE,
        "source_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "companion_of_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "source_video_uid": f"typed-mask-{bundle_id}",
        "companion_video_uid": f"typed-mask-{bundle_id}",
        "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
    }


def motion_video(slot: int, bundle_id: str = BUNDLE_ID) -> dict:
    item = {
        **primary_video(bundle_id),
        "video_slot": slot,
        "video_uid": f"typed-motion-{bundle_id}-{slot}",
        "source_uid": f"typed-motion-{bundle_id}-{slot}",
        "video_path": f"C:/typed_auxiliary/motion_{slot}.mp4",
        "markers": [],
        "media_kind": picker.MOTION_GUIDE_MEDIA_KIND,
        "generation_role": "motion_guide",
        "video_role": "maya_motion_guide_companion",
        "source_type_hint": picker.MOTION_GUIDE_SOURCE_TYPE,
        "control_role_hint": picker.MOTION_GUIDE_CONTROL_ROLE,
        "source_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "companion_of_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "source_video_uid": f"typed-mask-{bundle_id}",
        "companion_video_uid": f"typed-mask-{bundle_id}",
        "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
    }
    item.pop("pair_run_id", None)
    return item


def manual_video(slot: int) -> dict:
    return {
        "video_slot": slot,
        "video_uid": f"typed-manual-{slot}",
        "source_uid": f"typed-manual-{slot}",
        "video_path": f"C:/typed_auxiliary/manual_{slot}.mp4",
        "media_kind": "uploaded_video",
        "video_role": "manual_auxiliary",
    }


def packed_original(slot: int = 1) -> dict:
    item = primary_video()
    item.pop("pair_run_id", None)
    item.pop("bundle_run_id", None)
    item.update({
        "video_slot": slot,
        "video_uid": f"typed-original-{slot}",
        "source_uid": f"typed-original-{slot}",
        "video_path": f"C:/typed_auxiliary/original_{slot}.mp4",
        "media_kind": picker.ORIGINAL_MEDIA_KIND,
        "generation_role": "original",
        "video_role": "maya_original_playblast",
        "source_type_hint": "Original Maya Viewport Reference",
        "control_role_hint": "Original Appearance and Motion Reference",
    })
    return item


def packed_mask(slot: int, bundle_id: str = BUNDLE_ID) -> dict:
    item = primary_video(bundle_id)
    item.update({
        "video_slot": slot,
        "video_uid": f"typed-mask-{bundle_id}",
        "source_uid": f"typed-mask-{bundle_id}",
        "video_path": f"C:/typed_auxiliary/mask_{slot}.mp4",
        "media_kind": picker.MASK_MEDIA_KIND,
        "generation_role": "mask",
        "video_role": "maya_color_assignment_mask",
        "source_type_hint": "Color Assignment Mask / Segmentation Reference",
        "control_role_hint": "Object and Character Region Guidance",
    })
    return item


def with_source(item: dict, source_slot: int) -> dict:
    out = copy.deepcopy(item)
    out["source_video_slot"] = source_slot
    out["companion_of_video_slot"] = source_slot
    return out


def standalone(item: dict) -> dict:
    out = with_source(item, 0)
    out["source_video_uid"] = ""
    out["companion_video_uid"] = ""
    return out


def state_with(*items: dict) -> dict:
    return {
        "active_slot_count": 5,
        "mask_enabled": True,
        "videos": [primary_video(), *items],
        "slot_assignments": [],
        "slot_visibility": [],
        "snapshots": [],
    }


# Generation uses a canonical packed order. Downstream type recognition remains
# metadata-based so a later user reorder does not change semantic authority.
assert picker.PRIMARY_COLOR_VIDEO_SLOT == 1
assert tuple(picker.AUXILIARY_VIDEO_SLOTS) == AUXILIARY_SLOTS
assert "Maya Preview / Playblast" in prompt.PRIMARY_VIDEO_SOURCE_TYPES
assert "Motion Reference" in prompt.PRIMARY_VIDEO_SOURCE_TYPES
assert "Unified Shot-Control Video" in prompt.PRIMARY_VIDEO_SOURCE_TYPES
assert not hasattr(picker, "DEPTH_VIDEO_SLOT")
assert not hasattr(picker, "MOTION_GUIDE_VIDEO_SLOT")
for runtime_path in (ROOT / "HMBVideoPickerLibrary.py", ROOT / "HMBPromptLibrary.py"):
    runtime_source = runtime_path.read_text(encoding="utf-8")
    assert "DEPTH_VIDEO_SLOT" not in runtime_source
    assert "MOTION_GUIDE_VIDEO_SLOT" not in runtime_source


# Depth/Motion use private Maya staging positions only. Catalog occupancy,
# deleted cards, and user reorder never alter that internal render plan.
request_modes = (
    (False, False, (0, 0)),
    (True, False, (2, 0)),
    (False, True, (0, 2)),
    (True, True, (2, 3)),
)
allocator_case_count = 0
for occupied_mask in range(16):
    occupied = [
        manual_video(slot)
        for bit, slot in enumerate(AUXILIARY_SLOTS)
        if occupied_mask & (1 << bit)
    ]
    for depth_requested, motion_requested, expected in request_modes:
        allocator_case_count += 1
        original = state_with(*occupied)
        before = copy.deepcopy(original)
        assert picker._resolve_generated_companion_slots(
            original,
            depth_enabled=depth_requested,
            motion_guide_enabled=motion_requested,
        ) == expected
        assert original == before
assert allocator_case_count == 64


# Generated records append with new stable identities. Existing typed/manual
# rows survive, and only the first ten selected records are exposed in the
# transient Prompt/Generator order.
append_source = picker._parse_state({
    **state_with(*[manual_video(slot) for slot in AUXILIARY_SLOTS]),
    "original_enabled": False,
    "mask_enabled": True,
    "depth_enabled": True,
    "motion_guide_enabled": True,
})
append_before = copy.deepcopy(append_source)
appended = picker._pack_selected_generation_videos(
    append_source,
    {
        "mask": packed_mask(1),
        "depth": depth_video(2),
        "motion_guide": motion_video(3),
    },
)
assert append_source == append_before
assert len(appended["videos"]) == len(append_before["videos"]) + 3
assert [item.get("generation_role") for item in appended["videos"][-3:]] == [
    "mask", "depth", "motion_guide",
]
assert len({item["video_uid"] for item in appended["videos"]}) == len(
    appended["videos"]
)
new_mask_uid = appended["videos"][-3]["video_uid"]
assert appended["videos"][-2]["source_video_uid"] == new_mask_uid
assert appended["videos"][-1]["source_video_uid"] == new_mask_uid
append_payload, append_media = picker._build_synchronized_video_outputs(
    appended
)
assert append_payload["schema_version"] == 5
assert append_payload["selected_video_count"] == len(append_media)
assert append_payload["selected_video_count"] <= 10
assert [item["video_uid"] for item in append_payload["videos"]] == (
    append_payload["ordered_video_uids"]
)

# Every request mode must also freeze the same canonical plan in the operation
# context consumed by the Maya job and publication path.
node = picker.HMBVideoPickerLibrary.__new__(picker.HMBVideoPickerLibrary)
for depth_requested, motion_requested, expected in (
    (False, False, (0, 0)),
    (True, False, (2, 0)),
    (False, True, (0, 2)),
    (True, True, (2, 3)),
):
    context_state = state_with()
    context_state.update({
        "depth_enabled": depth_requested,
        "motion_guide_enabled": motion_requested,
    })
    context = node._create_operation_context(
        "run_video",
        "C:/typed_auxiliary/shot.mb",
        context_state,
        video_slot=5,
    )
    assert context.video_slot == 1
    assert (context.depth_video_slot, context.motion_guide_video_slot) == expected

occupied_context_state = state_with(manual_video(2))
occupied_context_state.update({
    "depth_enabled": True,
    "motion_guide_enabled": True,
})
occupied_context_before = copy.deepcopy(occupied_context_state)
occupied_context = node._create_operation_context(
    "run_video",
    "C:/typed_auxiliary/occupied_shot.mb",
    occupied_context_state,
    video_slot=2,
)
assert (
    occupied_context.depth_video_slot,
    occupied_context.motion_guide_video_slot,
) == (2, 3)
assert occupied_context.input_digest
assert occupied_context_state == occupied_context_before

# Catalog order does not mutate Maya authoring assignments, snapshots, or
# visibility, and the retired clear helper remains non-destructive.
for conflict_key, conflict_value in (
    (
        "slot_assignments",
        [{"video_slot": 2, "bindings": [{"group_name": "Authored"}]}],
    ),
    ("snapshots", [{"video_slot": 2, "path": "C:/typed_auxiliary/still.png"}]),
    ("slot_visibility", [{"video_slot": 2, "hidden_paths": ["|Authored"]}]),
):
    conflict_state = state_with()
    conflict_state[conflict_key] = conflict_value
    before = copy.deepcopy(conflict_state)
    assert picker._resolve_generated_companion_slots(
        conflict_state,
        depth_enabled=False,
        motion_guide_enabled=True,
    ) == (0, 2)
    assert conflict_state == before
    assert picker._clear_slot_ui_state(conflict_state, 2) == before
    assert conflict_state == before

generated_with_stale_ui = state_with(depth_video(2))
generated_with_stale_ui.update({
    "slot_assignments": [
        {"video_slot": 2, "bindings": [{"group_name": "Stale"}]}
    ],
    "snapshots": [{"video_slot": 2, "path": "C:/typed_auxiliary/stale.png"}],
    "slot_visibility": [{"video_slot": 2, "hidden_paths": ["|Stale"]}],
})
assert picker._resolve_generated_companion_slots(
    generated_with_stale_ui,
    depth_enabled=True,
    motion_guide_enabled=False,
) == (2, 0)
generated_before = copy.deepcopy(generated_with_stale_ui)
assert picker._clear_slot_ui_state(generated_with_stale_ui, 2) == generated_before
assert generated_with_stale_ui == generated_before

# Zero Color Pick rows means zero included geometry, not a creative preflight
# failure. Color-only generation may intentionally produce the empty/black
# render scope. Depth/Motion still report their own technical zero-geometry or
# a technical zero-target diagnostic only when the authored-visible fallback is
# genuinely empty, without deleting the prior outputs.
binding_node = picker.HMBVideoPickerLibrary.__new__(picker.HMBVideoPickerLibrary)
assert binding_node._selected_slot_job_bindings(state_with(), 1) == []
disabled_binding_state = state_with()
disabled_binding_state["slot_assignments"] = [{
    "video_slot": 1,
    "bindings": [{
        "group_name": "ExcludedIdea",
        "full_dag_path": "|ExcludedIdea",
        "color": "Red",
        "enabled": False,
    }],
}]
assert binding_node._selected_slot_job_bindings(disabled_binding_state, 1) == []
maya_runner_source = (
    ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
).read_text(encoding="utf-8")
assert (
    "No enabled Group Name + Color Pick assignments found in the "
    "HMBVideoPickerLibrary state."
) not in maya_runner_source
assert "Motion Guide requires at least one valid Color Assignment target." not in maya_runner_source
assert "Motion Guide found no authored-visible, Picker-eye-enabled Maya target." in maya_runner_source
assert "Depth playblast found no visible polygon mesh" in maya_runner_source
assert "_unassigned_motion_bindings" in maya_runner_source
assert "_prepare_unassigned_auxiliary_scope" in maya_runner_source
assert 'require_depth_api = False' in maya_runner_source
picker_source = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
assert "_publish_validated_playblast_artifact" in picker_source
assert '"publish-backup" / "color"' in picker_source
assert '"publish-backup" / "depth"' in picker_source
assert '"publish-backup" / "motion"' in picker_source


class PublishHarness:
    def __init__(self) -> None:
        self.published_state = None

    def _apply_selected_view_fields(self, state: dict) -> dict:
        return state

    def _write_state(self, state: dict) -> None:
        self.published_state = copy.deepcopy(state)

    def _sync_outputs_from_state(self, state: dict) -> str:
        self.published_state = copy.deepcopy(state)
        return "published"


# Color-only publication releases matched-bundle confidence by publishing a new
# identity-free Color row, but it does not delete previous generated media or
# any slot-authored UI. The user decides whether those auxiliary ideas remain.
publish_state = state_with(depth_video(2), motion_video(3))
publish_state.update({
    "active_slot_count": 3,
    "selected_video_slot": 1,
    "depth_enabled": False,
    "motion_guide_enabled": False,
    "video_path": "C:/typed_auxiliary/new_color.mp4",
    "project_video_path": "C:/typed_auxiliary/project_new_color.mp4",
    "video_url": "/static/new_color.mp4",
    "slot_assignments": [
        {"video_slot": 1, "bindings": []},
        {"video_slot": 2, "bindings": [{"group_name": "Depth idea"}]},
        {"video_slot": 3, "bindings": [{"group_name": "Motion idea"}]},
    ],
    "slot_visibility": [
        {"video_slot": 1, "hidden_paths": []},
        {"video_slot": 2, "hidden_paths": ["|DepthHidden"]},
        {"video_slot": 3, "hidden_paths": ["|MotionHidden"]},
    ],
    "snapshots": [
        {
            "video_slot": 2,
            "frame": 106,
            "data_uri": "data:image/png;base64,AA==",
            "path": "C:/typed_auxiliary/depth.png",
        },
        {
            "video_slot": 3,
            "frame": 107,
            "data_uri": "data:image/png;base64,AQ==",
            "path": "C:/typed_auxiliary/motion.png",
        },
    ],
})
publish_state = picker._parse_state(publish_state)
authored_ui_before = copy.deepcopy({
    key: publish_state[key]
    for key in ("slot_assignments", "slot_visibility", "snapshots")
})
publish_harness = PublishHarness()
assert picker.HMBVideoPickerLibrary._publish_outputs(
    publish_harness,
    publish_state,
    picker.PRIMARY_COLOR_VIDEO_SLOT,
) == "published"
published = publish_harness.published_state
assert published is not None
assert [item["video_slot"] for item in published["videos"]] == [1, 2, 3, 4]
assert next(item for item in published["videos"] if item["video_slot"] == 2)[
    "video_path"
] == "C:/typed_auxiliary/depth_2.mp4"
assert next(item for item in published["videos"] if item["video_slot"] == 3)[
    "video_path"
] == "C:/typed_auxiliary/motion_3.mp4"
assert published["videos"][3]["generation_role"] == "mask"
assert published["videos"][3]["video_path"] == (
    "C:/typed_auxiliary/new_color.mp4"
)
assert len({item["video_uid"] for item in published["videos"]}) == 4
assert published["slot_assignments"][:3] == authored_ui_before[
    "slot_assignments"
]
assert published["slot_visibility"][:3] == authored_ui_before[
    "slot_visibility"
]
assert published["snapshots"] == authored_ui_before["snapshots"]

# Concrete artifact names carry a unique token rather than a reusable slot
# suffix, so another generation can never overwrite a previous take.
assert 'f"{scene_path.stem}_playblast_{token}.mp4"' in picker_source
assert 'f"{scene_path.stem}_depth_playblast_{token}.mp4"' in picker_source
assert 'f"{scene_path.stem}_motion_guide_{token}.mp4"' in picker_source


# Reordering selected assets changes only transient @video positions. Typed
# authority follows stable companion/source UIDs and remains exact.
typed_reorder = picker._parse_state({
    "videos": [primary_video(), depth_video(2), motion_video(3)],
})
typed_reorder_source = copy.deepcopy(typed_reorder)
typed_reorder_source["videos"][0]["selection_order"] = 3
typed_reorder_source["videos"][1]["selection_order"] = 1
typed_reorder_source["videos"][2]["selection_order"] = 2
typed_reordered = picker._parse_state(typed_reorder_source)
typed_payload, _typed_media = picker._build_synchronized_video_outputs(
    typed_reordered
)
assert [item["generation_role"] for item in typed_payload["videos"]] == [
    "depth", "motion_guide", "mask",
]
assert typed_payload["videos"][0]["source_video_slot"] == 3
assert typed_payload["videos"][1]["source_video_slot"] == 3
assert typed_payload["videos"][0]["source_video_uid"] == (
    typed_payload["videos"][2]["video_uid"]
)


# Prompt recognition remains type/provenance based in every auxiliary slot.
# Applying PICKER_OUT assigns the self-scoped type and role at the actual slot.
for slot in AUXILIARY_SLOTS:
    depth = depth_video(slot)
    motion = motion_video(slot)
    assert prompt._picker_video_claims_generated_depth(depth, slot)
    assert prompt._picker_video_is_generated_depth(depth, slot, BUNDLE_ID)
    assert not prompt._picker_video_claims_generated_motion_guide(depth, slot)
    assert prompt._picker_video_claims_generated_motion_guide(motion, slot)
    assert prompt._picker_video_is_generated_motion_guide(motion, slot, BUNDLE_ID)
    assert not prompt._picker_video_claims_generated_depth(motion, slot)

    for companion, expected_type, expected_role in (
        (depth, picker.DEPTH_SOURCE_TYPE, picker.DEPTH_CONTROL_ROLE),
        (
            motion,
            picker.MOTION_GUIDE_SOURCE_TYPE,
            picker.MOTION_GUIDE_CONTROL_ROLE,
        ),
    ):
        selected_rows = [primary_video()]
        selected_rows.extend(
            manual_video(filler_slot)
            for filler_slot in range(2, slot)
        )
        selected_rows.append(companion)
        applied = prompt._apply_picker_payload(
            prompt._default_widget_state(),
            {
                "mode": "maya",
                "active_slot_count": slot,
                "scene_path": "C:/typed_auxiliary/shot.mb",
                "videos": selected_rows,
            },
            connected=True,
        )
        actual = applied["videos"][slot - 1]
        assert actual["source_type"] == expected_type
        assert actual["control_role"] == expected_role
        assert not applied["picker"].get("contract_errors"), applied["picker"]


# Prompt does not reserve @video1 for a creative role. If Picker explicitly
# supplies valid typed provenance there, the row keeps that declared type and
# role instead of being rewritten as Color Playblast.
standalone_depth_primary = standalone(depth_video(1))
standalone_motion_primary = standalone(motion_video(1))
assert prompt._picker_video_claims_generated_depth(standalone_depth_primary, 1)
assert prompt._picker_video_is_generated_depth(
    standalone_depth_primary, 1, BUNDLE_ID
)
assert prompt._picker_video_claims_generated_motion_guide(
    standalone_motion_primary, 1
)
assert prompt._picker_video_is_generated_motion_guide(
    standalone_motion_primary,
    1,
    BUNDLE_ID,
)
for typed_primary, expected_type, expected_role in (
    (
        standalone_depth_primary,
        picker.DEPTH_SOURCE_TYPE,
        picker.DEPTH_CONTROL_ROLE,
    ),
    (
        standalone_motion_primary,
        picker.MOTION_GUIDE_SOURCE_TYPE,
        picker.MOTION_GUIDE_CONTROL_ROLE,
    ),
):
    applied = prompt._apply_picker_payload(
        prompt._default_widget_state(),
        {
            "mode": "maya",
            "active_slot_count": 1,
            "scene_path": "C:/typed_auxiliary/typed_primary.mb",
            "videos": [typed_primary],
        },
        connected=True,
    )
    actual = applied["videos"][0]
    assert actual["source_type"] == expected_type
    assert actual["control_role"] == expected_role
    assert not applied["picker"].get("contract_errors"), applied["picker"]


# Packed Generate provenance follows the actual Mask slot instead of assuming
# @video1. Original may precede it, and a checked Depth/Motion output remains a
# validated independent typed source when Mask was unchecked (source slot 0).
packed_full = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 4,
        "scene_path": "C:/typed_auxiliary/packed_full.mb",
        "videos": [
            packed_original(1),
            packed_mask(2),
            with_source(depth_video(3), 2),
            with_source(motion_video(4), 2),
        ],
    },
    connected=True,
)
assert packed_full["videos"][2]["source_type"] == picker.DEPTH_SOURCE_TYPE
assert packed_full["videos"][2]["control_role"] == picker.DEPTH_CONTROL_ROLE
assert packed_full["videos"][3]["source_type"] == picker.MOTION_GUIDE_SOURCE_TYPE
assert packed_full["videos"][3]["control_role"] == picker.MOTION_GUIDE_CONTROL_ROLE
assert not packed_full["picker"].get("contract_errors"), packed_full["picker"]

packed_depth_only = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 2,
        "scene_path": "C:/typed_auxiliary/packed_depth_only.mb",
        "videos": [packed_original(1), standalone(depth_video(2))],
    },
    connected=True,
)
assert packed_depth_only["videos"][1]["source_type"] == picker.DEPTH_SOURCE_TYPE
assert packed_depth_only["videos"][1]["control_role"] == picker.DEPTH_CONTROL_ROLE
assert not packed_depth_only["picker"].get("contract_errors"), packed_depth_only["picker"]

packed_motion_only = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 2,
        "scene_path": "C:/typed_auxiliary/packed_motion_only.mb",
        "videos": [packed_original(1), standalone(motion_video(2))],
    },
    connected=True,
)
assert packed_motion_only["videos"][1]["source_type"] == picker.MOTION_GUIDE_SOURCE_TYPE
assert packed_motion_only["videos"][1]["control_role"] == picker.MOTION_GUIDE_CONTROL_ROLE
assert not packed_motion_only["picker"].get("contract_errors"), packed_motion_only["picker"]

# Standalone authority is fail-closed: zero must be explicit and the row still
# needs its exact typed discriminator/profile plus a non-empty own bundle ID.
for missing_source_item, typed_label in (
    (depth_video(2), "Depth"),
    (motion_video(2), "Motion Guide"),
):
    missing_source_item.pop("source_video_slot", None)
    missing_source_item.pop("companion_of_video_slot", None)
    missing_source = prompt._apply_picker_payload(
        prompt._default_widget_state(),
        {
            "mode": "maya",
            "active_slot_count": 2,
            "scene_path": "C:/typed_auxiliary/missing_standalone_source.mb",
            "videos": [packed_original(1), missing_source_item],
        },
        connected=True,
    )
    assert any(
        f"mismatched generated {typed_label} provenance" in error
        for error in missing_source["picker"].get("contract_errors", [])
    )

blank_identity_depth = with_source(depth_video(2), 0)
blank_identity_depth["bundle_run_id"] = ""
blank_identity_depth["pair_run_id"] = ""
blank_identity_motion = with_source(motion_video(2), 0)
blank_identity_motion["bundle_run_id"] = ""
for blank_item, typed_label in (
    (blank_identity_depth, "Depth"),
    (blank_identity_motion, "Motion Guide"),
):
    blank_identity = prompt._apply_picker_payload(
        prompt._default_widget_state(),
        {
            "mode": "maya",
            "active_slot_count": 2,
            "scene_path": "C:/typed_auxiliary/blank_standalone_identity.mb",
            "videos": [packed_original(1), blank_item],
        },
        connected=True,
    )
    assert any(
        f"mismatched generated {typed_label} provenance" in error
        for error in blank_identity["picker"].get("contract_errors", [])
    )

contradictory_source = with_source(depth_video(2), 0)
contradictory_source["companion_of_video_slot"] = 1
contradictory_result = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 2,
        "scene_path": "C:/typed_auxiliary/contradictory_source.mb",
        "videos": [packed_original(1), contradictory_source],
    },
    connected=True,
)
assert any(
    "mismatched generated Depth provenance" in error
    for error in contradictory_result["picker"].get("contract_errors", [])
)

# A typed Original is never accepted as the companion source solely because it
# occupies @video1. This distinguishes packed output from the untyped legacy
# @video1 Color row, which remains covered by the tests above.
forged_original_source = packed_original(1)
forged_original_source["bundle_run_id"] = BUNDLE_ID
forged_original_source["pair_run_id"] = BUNDLE_ID
rejected_original_source = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 2,
        "scene_path": "C:/typed_auxiliary/rejected_original_source.mb",
        "videos": [
            forged_original_source,
            with_source(depth_video(2), 1),
        ],
    },
    connected=True,
)
assert any(
    "mismatched generated Depth provenance" in error
    for error in rejected_original_source["picker"].get("contract_errors", [])
)


# A claimed companion with mismatched provenance loses only matched-bundle
# authority. Prompt keeps the connected file, its local metadata, and supplied
# type hints as an independently usable source.
unverified_depth = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 2,
        "scene_path": "C:/typed_auxiliary/unverified_depth.mb",
        "videos": [primary_video(), depth_video(2, "wrong-bundle")],
    },
    connected=True,
)
unverified_depth_row = unverified_depth["videos"][1]
assert unverified_depth_row["present"] is True
assert unverified_depth_row["label"] == "depth_2"
assert unverified_depth_row["source_type"] == picker.DEPTH_SOURCE_TYPE
assert unverified_depth_row["control_role"] == picker.DEPTH_CONTROL_ROLE
assert any(
    prompt._video_slot_number(item.get("video_slot"), prompt.MAX_VIDEOS) == 2
    for item in unverified_depth["picker"].get("frame_metadata", [])
)
assert any(
    "mismatched generated Depth provenance" in error
    for error in unverified_depth["picker"].get("contract_errors", [])
)
unverified_depth_prompt = prompt._build_prompt_package(unverified_depth)
assert "SOURCE DATA WARNINGS:" not in unverified_depth_prompt
assert "mismatched generated Depth provenance" not in unverified_depth_prompt
assert "@video2 = depth_2" in unverified_depth_prompt
assert "Final prompt generation is blocked" not in unverified_depth_prompt


# Applying a valid generated typed source is additive: user-authored Color Pick,
# target-slot, and optional Range data remain intact rather than being erased.
binding_state = prompt._default_widget_state()
binding_state["images"][0].update({
    "present": True,
    "label": "Bound idea",
    "source_type": "Character Appearance",
    "color_picks": ["Red"],
    "binding_video_slots": [2],
    "marker_video": 2,
    "frame_range_enabled": True,
    "frame_range_color_index": 0,
    "frame_range_bindings": {
        "@video2::Red": {
            "video_slot": "@video2",
            "color_pick": "Red",
            "origin": "manual",
            "start_frame": 101,
            "end_frame": 112,
            "ranges": [{"start": 103, "end": 108}],
        },
    },
})
bound_depth = prompt._apply_picker_payload(
    binding_state,
    {
        "mode": "maya",
        "active_slot_count": 2,
        "scene_path": "C:/typed_auxiliary/bound_depth.mb",
        "videos": [primary_video(), depth_video(2)],
    },
    connected=True,
)
bound_image = bound_depth["images"][0]
assert bound_image["color_picks"][0] == "Red"
assert bound_image["binding_video_slots"][0] == 2
assert "@video2::Red" in bound_image["frame_range_bindings"]


# Prompt consumes whichever valid Picker media exists. Color-only and
# Color+Depth remain complete additive states; an absent Motion Guide is not a
# downstream preflight failure.
motion_required_text = "requires one validated Motion Guide"
for companions in ([], [depth_video(4)]):
    applied = prompt._apply_picker_payload(
        prompt._default_widget_state(),
        {
            "mode": "maya",
            "active_slot_count": 4 if companions else 1,
            "scene_path": "C:/typed_auxiliary/upstream_only.mb",
            "videos": [primary_video(), *companions],
        },
        connected=True,
    )
    compiled = prompt._build_prompt_package(applied)
    assert motion_required_text not in compiled
    assert "Final prompt generation is blocked" not in compiled

motion_ready = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "active_slot_count": 4,
        "scene_path": "C:/typed_auxiliary/downstream_ready.mb",
        "videos": [primary_video(), motion_video(4)],
    },
    connected=True,
)
assert motion_required_text not in prompt._build_prompt_package(motion_ready)


print(
    "HMB typed auxiliary video slots regression: PASS "
    f"({allocator_case_count} private-staging/catalog-occupancy cases; "
    "UID companion reorder and typed Prompt authority preserved)"
)
