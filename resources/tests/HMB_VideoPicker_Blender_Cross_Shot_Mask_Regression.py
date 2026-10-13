"""Fast regression: Blender companion-only generation must not harvest old Mask."""

from __future__ import annotations

import copy
import inspect
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker


SHOT_UUIDS = [
    f"cccccccc-cccc-4ccc-8ccc-{number:012d}"
    for number in range(1, 6)
]


def shot_row(state: dict, number: int) -> dict:
    return next(row for row in state["picker_shots"] if row["number"] == number)


def registered_node():
    node = picker.HMBVideoPickerLibrary(name="blender_cross_shot_mask_regression")
    try:
        from griptape_nodes.exe_types.flow import ControlFlow
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    except ImportError:
        return node  # Hostless fallback has no retained-mode registry.
    manager = GriptapeNodes.EventManager()
    manager.initialize_queue()
    options = {"name": "BlenderCrossShotMaskFixture"}
    if "engine" in inspect.signature(ControlFlow).parameters:
        options["engine"] = manager.engine
    flow = ControlFlow(**options)
    flow.add_node(node)
    GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name
    return node


def run() -> None:
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hmb-blender-cross-shot-mask-", dir=ROOT / ".tmp") as temp:
        scene = Path(temp) / "placeholder.blend"
        scene.write_bytes(b"This read-only fake scene is never opened by Blender.")
        state = picker._default_widget_state()
        state.update({
            "scene_path": str(scene),
            "scene_request_path": str(scene),
            "scene_draft_path": str(scene),
            "mode": "blender",
            "scene_engine": "blender",
            "mask_enabled": False,
            "original_enabled": False,
            "depth_enabled": True,
            "motion_guide_enabled": True,
            "picker_shots": [
                picker._new_picker_workspace_row(
                    number,
                    bound_shot_uuid=shot_uuid,
                    workspace_uuid=picker._picker_workspace_uuid_for_bound_shot(shot_uuid),
                )
                for number, shot_uuid in enumerate(SHOT_UUIDS, start=1)
            ],
            "shot_selections": [
                {"shot_uuid": shot_uuid, "number": number, "name": f"Shot {number}", "revision": 1}
                for number, shot_uuid in enumerate(SHOT_UUIDS, start=1)
            ],
        })
        shot4 = shot_row(state, 4)["workspace_uuid"]
        shot5 = shot_row(state, 5)["workspace_uuid"]
        state["active_picker_shot_uuid"] = shot5
        state = picker._append_video_asset(state, {
            "video_uid": "existing-shot5-mask",
            "video_url": "https://media.example/old-shot5-mask.mp4",
            "generation_role": "mask",
            "media_kind": picker.BLENDER_MASK_MEDIA_KIND,
            "video_role": "blender_color_assignment_mask",
            "scene_engine": "blender",
        }, picker_shot_uuid=shot5)
        assert shot_row(state, 5)["selected_video_uids"] == ["existing-shot5-mask"]
        state = picker._activate_picker_workspace_projection(state, shot4)
        assert state is not None
        state.update({"mask_enabled": False, "original_enabled": False,
                      "depth_enabled": True, "motion_guide_enabled": True})

        node = registered_node()
        node._write_state(state)

        def generated_companions(_scene_text, _video_slot, context=None, *, publish_public=True, selected_role=None):
            del publish_public
            assert context is not None and context.picker_shot_uuid == shot4
            assert selected_role in ("depth", "motion_guide")
            generated_item = None
            for role, kind, video_role, profile_key, profile in (
                ("depth", picker.BLENDER_DEPTH_MEDIA_KIND, "blender_depth_companion",
                 "depth_profile", picker.BLENDER_DEPTH_PROFILE),
                ("motion_guide", picker.BLENDER_MOTION_GUIDE_MEDIA_KIND,
                 "blender_motion_guide_companion", "motion_guide_profile",
                 picker.BLENDER_MOTION_GUIDE_PROFILE),
            ):
                if role != selected_role:
                    continue
                generated_item = {
                    "video_uid": f"provisional-shot4-{role}",
                    "video_url": f"https://media.example/new-shot4-{role}.mp4",
                    "video_path": f"https://media.example/new-shot4-{role}.mp4",
                    "generation_role": role,
                    "media_kind": kind,
                    "video_role": video_role,
                    "scene_engine": "blender",
                    "bundle_run_id": "blender-new-shot4-bundle",
                    profile_key: profile,
                }
            assert generated_item is not None
            return {
                "mode": "blender", "video": "",
                "depth_video": generated_item["video_path"] if selected_role == "depth" else "",
                "motion_guide_video": generated_item["video_path"] if selected_role == "motion_guide" else "",
                "depth_succeeded": selected_role == "depth",
                "motion_guide_succeeded": selected_role == "motion_guide",
                "bundle_run_id": "blender-new-shot4-bundle",
                "generated_item": generated_item,
            }

        incoming = copy.deepcopy(node._picker_state())
        incoming["backend_ack_action_id"] = "blender-cross-shot-companions"
        node._hmb_cancel_requested.clear()
        with patch.object(node, "_blender_mode", side_effect=generated_companions), patch.object(
            picker, "_video_asset_thumbnail_url", return_value=("", ""),
        ), patch.object(
            picker, "_select_synchronized_video_media",
            side_effect=lambda item, **_kwargs: item.get("video_url", ""),
        ):
            node._start_ui_operation("run_video", incoming)

        result = node._picker_state()
        assert result["scene_stage"] == "VIDEO_READY", result.get("message")
        assert result["generation_output_roles"] == ["depth", "motion_guide"]
        assert shot_row(result, 5)["video_asset_uids"] == ["existing-shot5-mask"]
        assert shot_row(result, 5)["selected_video_uids"] == ["existing-shot5-mask"]
        assert [row["generation_role"] for row in result["videos"]
                if row["picker_shot_uuid"] == shot4] == ["depth", "motion_guide"]
        assert len(shot_row(result, 4)["selected_video_uids"]) == 2
    print("PASS: Blender Mask-off companion generation preserved the older Shot 5 Mask")


if __name__ == "__main__":
    run()
