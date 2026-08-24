from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import types
import uuid


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import _hmb_shot_routing as routing
import HMBImageAssetLibrary as image
import HMBVideoPickerLibrary as picker


def uuid_text() -> str:
    return str(uuid.uuid4())


original_same_flow_nodes = routing._same_flow_nodes
original_schedule_deletion = routing.schedule_post_deletion_reconcile
try:
    routing.schedule_post_deletion_reconcile = lambda _node: False

    # ImageAsset Reset: catalog rows, ordered selection, imported media and
    # per-Shot membership survive. Runtime/publisher and all transient UI,
    # scan/request/error fields belong to the new object.
    old_image = image.HMBImageAssetLibrary(name="ImageAsset")
    image_channel = uuid_text()
    old_image_publisher = uuid_text()
    image_shot_1 = uuid_text()
    image_shot_2 = uuid_text()
    project_uid = uuid_text()
    project_asset = {
        "asset_library_id": "project-hero",
        "source_uid": "project:project-hero",
        "source_kind": "project",
        "asset_project_uid": project_uid,
        "asset_id": "Hero",
        "image_name": "hero.png",
        "path": "https://media.example.invalid/hero.png",
        "relative_path": "characters/hero.png",
        "extension": ".png",
        "registered": True,
        "selected": True,
        "selection_order": 1,
        "connected": True,
    }
    import_uid = "import:reset-prop"
    imported_asset = {
        "asset_library_id": "user-reset-prop",
        "source_uid": import_uid,
        "source_kind": "user",
        "asset_id": "ResetProp",
        "image_name": "reset_prop.png",
        "path": "",
        "extension": ".png",
        "registered": False,
        "selected": True,
        "selection_order": 2,
        "import_index": 1,
        "connected": True,
    }
    old_image_state = image._default_state()
    old_image_state.update(
        {
            "catalog_root": "P:/HMB/Projects",
            "projects": [
                {
                    "project_uid": project_uid,
                    "project_id": "RESET_PROJECT",
                    "name": "RESET_PROJECT",
                    "path": "P:/HMB/Projects/RESET_PROJECT",
                }
            ],
            "project_root": "P:/HMB/Projects/RESET_PROJECT",
            "project_id": "RESET_PROJECT",
            "project_uid": project_uid,
            "manifest_signature": "reset-manifest",
            "folders": ["characters"],
            "assets": [project_asset, imported_asset],
            "shot_routing": {
                "publisher_instance_uuid": old_image_publisher,
                "channel_uuid": image_channel,
                "generation": 9,
                "active_shot_uuid": image_shot_2,
                "expanded": True,
                "shots": [
                    {
                        "shot_uuid": image_shot_1,
                        "number": 1,
                        "name": "Opening",
                        "name_is_custom": True,
                        "revision": 4,
                        "selected_source_uids": [
                            "project:project-hero",
                            import_uid,
                        ],
                    },
                    {
                        "shot_uuid": image_shot_2,
                        "number": 2,
                        "name": "Close Up",
                        "name_is_custom": True,
                        "revision": 7,
                        "selected_source_uids": [import_uid],
                    },
                ],
            },
            "selected_folder_path": "characters",
            "search": "retired-filter",
            "scan_busy": True,
            "scan_request_id": "retired-scan",
            "asset_registration_request": {
                "request_id": "retired-registration",
                "asset_library_id": "project-hero",
                "source_kind": "project",
                "relative_path": "characters/hero.png",
            },
            "error": "retired scan failed",
            "warnings": ["retired warning"],
            "scan_revision": 12,
            image.UI_EDIT_REVISION_KEY: 19,
        }
    )
    old_image_state = image._normalize_state(old_image_state)
    image._get_parameter_obj(
        old_image,
        image.WIDGET_STATE_PARAMETER,
    ).default_value = image._json_text(old_image_state)
    image._get_parameter_obj(
        old_image,
        image.PROJECT_ROOT_PARAMETER,
    ).default_value = old_image_state["catalog_root"]
    imported_media = "data:image/png;base64,iVBORw0KGgo="
    import_aggregate = {
        "source_uid": import_uid,
        "name": "reset_prop.png",
        "base64": imported_media,
    }
    image._get_parameter_obj(
        old_image,
        image.IMAGE_IMPORT_PARAMETER,
    ).default_value = import_aggregate
    old_image._replace_import_media({import_uid: imported_media})
    old_image._accept_widget_state_baseline(old_image_state)

    new_image = image.HMBImageAssetLibrary(name="ImageAsset_temp")
    new_image_default_publisher = new_image._current_state()["shot_routing"][
        "publisher_instance_uuid"
    ]
    routing._same_flow_nodes = lambda _node: (
        "ResetFlow",
        [old_image, new_image],
    )
    old_image.after_node_deleted()
    assert old_image._hmb_node_deleted is True
    adopted_image = new_image._current_state()
    assert [asset["source_uid"] for asset in adopted_image["assets"]] == [
        "project:project-hero",
        import_uid,
    ]
    assert [asset["selection_order"] for asset in adopted_image["assets"]] == [
        1,
        2,
    ]
    adopted_image_routing = adopted_image["shot_routing"]
    assert adopted_image_routing["channel_uuid"] == image_channel
    assert [shot["shot_uuid"] for shot in adopted_image_routing["shots"]] == [
        image_shot_1,
        image_shot_2,
    ]
    assert adopted_image_routing["active_shot_uuid"] == image_shot_2
    assert [
        shot["selected_source_uids"]
        for shot in adopted_image_routing["shots"]
    ] == [
        ["project:project-hero", import_uid],
        [import_uid],
    ]
    assert adopted_image_routing["publisher_instance_uuid"] not in {
        old_image_publisher,
        new_image_default_publisher,
    }
    assert adopted_image["scan_busy"] is False
    assert adopted_image["scan_request_id"] == ""
    assert adopted_image["asset_registration_request"] == {}
    assert adopted_image["error"] == ""
    assert adopted_image["warnings"] == []
    assert adopted_image["search"] == ""
    assert new_image._hmb_import_media_by_uid == {import_uid: imported_media}
    # The actual host rebuilds ParameterList aggregates while reconnecting the
    # temp node, so the exact container shape is not stable at this midpoint.
    # The durable user row and its resolved media map above are the no-loss
    # reset contract; the connection aggregate is restored by host rewiring.
    invalid_image = copy.deepcopy(new_image._hmb_export_reset_handoff())
    invalid_image["identity_contract"] = "forged"
    assert new_image._hmb_adopt_reset_handoff(invalid_image) is False

    # VideoPicker Reset: every Loader record and each Shot's ownership,
    # selection order and preview cursor survive, while Maya authoring,
    # snapshots, operation/error state and runtime identity reset.
    old_picker = picker.HMBVideoPickerLibrary(name="VideoPicker")
    picker_channel = image_channel
    picker_publisher = old_image_publisher
    workspace_1 = uuid_text()
    workspace_2 = uuid_text()
    video_a = "reset-video-a"
    video_b = "reset-video-b"
    video_c = "reset-video-c"
    remote_rows = [
        {
            "shot_uuid": image_shot_1,
            "number": 1,
            "name": "Opening",
            "revision": 4,
            "selected_video_uids": [video_b, video_a],
        },
        {
            "shot_uuid": image_shot_2,
            "number": 2,
            "name": "Close Up",
            "revision": 7,
            "selected_video_uids": [video_c],
        },
    ]
    catalog_generation = 9
    metadata_hash = picker._sha256_canonical(
        {
            "channel_uuid": picker_channel,
            "generation": catalog_generation,
            "shots": [
                {
                    "shot_uuid": row["shot_uuid"],
                    "number": row["number"],
                    "name": row["name"],
                    "revision": row["revision"],
                }
                for row in remote_rows
            ],
        }
    )
    authored_context = picker._empty_picker_authoring_context()
    authored_context.update(
        {
            "scene_stage": "OUTLINER_READY",
            "scene_path": "C:/shots/retired.mb",
            "scene_draft_path": "C:/shots/retired.mb",
            "scene_request_path": "C:/shots/retired.mb",
            "native_read_ready": True,
            "selected_camera": "|shotCam",
            "cameras": [{"name": "shotCam", "full_path": "|shotCam"}],
            "selected_outliner_path": "|SET|Hero",
            "selected_outliner_name": "Hero",
            "selected_outliner_uuid": uuid_text(),
            "selected_color": "Red",
            "outliner_nodes": [
                {"name": "Hero", "full_path": "|SET|Hero"}
            ],
            "slot_assignments": [
                {
                    "video_slot": 1,
                    "bindings": [
                        {
                            "group_name": "Hero",
                            "full_dag_path": "|SET|Hero",
                            "color": "Red",
                            "enabled": True,
                        }
                    ],
                }
            ],
            "status": "OUTLINER_READY",
            "message": "Retired authoring state",
        }
    )
    picker_state = picker._default_widget_state()
    picker_state.update(
        {
            "state_revision": 41,
            "status": "FAILED",
            "scene_stage": "FAILED",
            "message": "retired Maya error",
            "warnings": ["retired Maya error"],
            "activity_log": [
                {
                    "timestamp": "12:00:00",
                    "level": "ERROR",
                    "message": "retired Maya error",
                }
            ],
            "scene_path": "C:/shots/retired.mb",
            "scene_draft_path": "C:/shots/retired.mb",
            "scene_request_path": "C:/shots/retired.mb",
            "native_read_ready": True,
            "selected_camera": "|shotCam",
            "outliner_nodes": [{"name": "Hero", "full_path": "|SET|Hero"}],
            "selected_outliner_path": "|SET|Hero",
            "selected_outliner_name": "Hero",
            "selected_color": "Red",
            "snapshots": [
                {
                    "snapshot_uid": "retired-snapshot",
                    "video_uid": video_b,
                    "video_slot": 1,
                    "path": "C:/shots/retired_snapshot.png",
                }
            ],
            "operation_kind": "run_video",
            "operation_id": "retired-operation",
            "active_process_pid": 12345,
            "videos": [
                {
                    "video_uid": video_a,
                    "source_uid": video_a,
                    "picker_shot_uuid": workspace_1,
                    "catalog_order": 1,
                    "selected": True,
                    "selection_order": 2,
                    "video_slot": 2,
                    "video_path": "https://media.example.invalid/a.mp4",
                    "video_url": "https://media.example.invalid/a.mp4",
                },
                {
                    "video_uid": video_b,
                    "source_uid": video_b,
                    "picker_shot_uuid": workspace_1,
                    "catalog_order": 2,
                    "selected": True,
                    "selection_order": 1,
                    "video_slot": 1,
                    "video_path": "https://media.example.invalid/b.mp4",
                    "video_url": "https://media.example.invalid/b.mp4",
                },
                {
                    "video_uid": video_c,
                    "source_uid": video_c,
                    "picker_shot_uuid": workspace_2,
                    "catalog_order": 3,
                    "selected": False,
                    "selection_order": 0,
                    "video_slot": 0,
                    "video_path": "https://media.example.invalid/c.mp4",
                    "video_url": "https://media.example.invalid/c.mp4",
                },
            ],
            "picker_shots": [
                {
                    "workspace_uuid": workspace_1,
                    "number": 1,
                    "name": "Opening",
                    "custom_name": True,
                    "revision": 11,
                    "bound_shot_uuid": image_shot_1,
                    "video_asset_uids": [video_a, video_b],
                    "selected_video_uids": [video_b, video_a],
                    "preview_video_uid": video_b,
                    "scene_draft_path": "C:/shots/retired.mb",
                    "current_frame": 120.0,
                    "viewport_mode": "snapshot",
                    "active_snapshot_uid": "retired-snapshot",
                    "selected_video_slot": 1,
                    "authoring_context": authored_context,
                },
                {
                    "workspace_uuid": workspace_2,
                    "number": 2,
                    "name": "Close Up",
                    "custom_name": True,
                    "revision": 13,
                    "bound_shot_uuid": image_shot_2,
                    "video_asset_uids": [video_c],
                    "selected_video_uids": [video_c],
                    "preview_video_uid": video_c,
                    "scene_draft_path": "C:/shots/second.mb",
                    "current_frame": 44.0,
                    "viewport_mode": "video",
                    "active_snapshot_uid": "",
                    "selected_video_slot": 1,
                    "authoring_context": authored_context,
                },
            ],
            "active_picker_shot_uuid": workspace_1,
            "preview_video_uid": video_b,
            "selected_video_uid": video_b,
            "selected_video_slot": 1,
            "active_slot_count": 2,
            "shot_publisher_instance_uuid": picker_publisher,
            "channel_uuid": picker_channel,
            "shot_uuid": image_shot_1,
            "shot_number": 1,
            "shot_name": "Opening",
            "shot_selections": remote_rows,
            "accepted_shot_catalog_publisher_instance_uuid": picker_publisher,
            "accepted_shot_catalog_channel_uuid": picker_channel,
            "accepted_shot_catalog_generation": catalog_generation,
            "accepted_shot_catalog_metadata_sha256": metadata_hash,
        }
    )
    picker_state = picker._parse_state(picker_state)
    assert [
        row["preview_video_uid"] for row in picker_state["picker_shots"]
    ] == [video_b, video_c]
    reset_probe = picker._reset_picker_state_preserving_loader_media(
        picker_state
    )
    assert [
        row["preview_video_uid"] for row in reset_probe["picker_shots"]
    ] == [video_b, video_c]
    old_picker._store_initial_parameter_value(
        picker.WIDGET_STATE_PARAMETER,
        picker_state,
    )
    old_picker._hmb_authoritative_state = copy.deepcopy(picker_state)
    old_picker._hmb_latest_widget_state = copy.deepcopy(picker_state)
    old_picker._hmb_state_revision = picker_state["state_revision"]

    new_picker = picker.HMBVideoPickerLibrary(name="VideoPicker_temp")
    new_picker_runtime = new_picker._hmb_runtime_instance_id
    new_picker_publisher = new_picker._hmb_picker_publisher_uuid

    # A real Reset registers ``VideoPicker_temp`` with NodeManager before the
    # old node's deletion callback runs.  This standalone regression has no
    # FlowManager, so emulate only the successful retained-state commit that
    # `_write_state` performs after NodeManager accepts the request.  Keeping
    # this double instance-local ensures the product adoption path itself is
    # still exercised and no global writer behavior is hidden.
    def commit_registered_temp_state(self, value):
        normalized = picker._parse_state(value)
        normalized["state_revision"] = max(
            int(getattr(self, "_hmb_state_revision", 0) or 0),
            int(normalized.get("state_revision") or 0),
        ) + 1
        normalized["state_writer"] = "python"
        normalized["writer_runtime_instance_id"] = (
            self._hmb_runtime_instance_id
        )
        normalized["writer_lifecycle_generation"] = int(
            getattr(self, "_hmb_lifecycle_generation", 0) or 0
        )
        self._store_initial_parameter_value(
            picker.WIDGET_STATE_PARAMETER,
            normalized,
        )
        self._hmb_state_revision = normalized["state_revision"]
        self._hmb_authoritative_state = copy.deepcopy(normalized)
        self._hmb_latest_widget_state = copy.deepcopy(normalized)

    new_picker._write_state = types.MethodType(
        commit_registered_temp_state,
        new_picker,
    )
    routing._same_flow_nodes = lambda _node: (
        "ResetFlow",
        [old_picker, new_picker],
    )
    old_picker.after_node_deleted()
    assert old_picker._hmb_node_deleted is True
    adopted_picker = new_picker._picker_state()
    assert [
        item["video_uid"] for item in adopted_picker["videos"]
    ] == [video_a, video_b, video_c]
    assert [
        row["video_asset_uids"] for row in adopted_picker["picker_shots"]
    ] == [[video_a, video_b], [video_c]]
    assert [
        row["selected_video_uids"]
        for row in adopted_picker["picker_shots"]
    ] == [[video_b, video_a], [video_c]]
    adopted_previews = [
        row["preview_video_uid"] for row in adopted_picker["picker_shots"]
    ]
    assert adopted_previews == [video_b, video_c], adopted_previews
    assert adopted_picker["active_picker_shot_uuid"] == workspace_1
    assert adopted_picker["channel_uuid"] == picker_channel
    assert adopted_picker["shot_uuid"] == image_shot_1
    assert adopted_picker["runtime_instance_id"] == new_picker_runtime
    assert new_picker._hmb_picker_publisher_uuid == new_picker_publisher
    assert adopted_picker["scene_path"] == ""
    assert adopted_picker["scene_draft_path"] == ""
    assert adopted_picker["native_read_ready"] is False
    assert adopted_picker["outliner_nodes"] == []
    assert adopted_picker["snapshots"] == []
    assert adopted_picker["operation_kind"] == ""
    assert adopted_picker["active_process_pid"] == 0
    assert adopted_picker["status"] == "READY"
    assert adopted_picker["warnings"] == []
    for row in adopted_picker["picker_shots"]:
        context = row["authoring_context"]
        assert context["scene_path"] == ""
        assert context["outliner_nodes"] == []
        # The active row may expose one empty control slot per retained Loader
        # selection.  Reset's authoring guarantee is that no retired Maya
        # binding survives, not that the compatibility list has length one.
        assert context["slot_assignments"]
        assert all(
            assignment.get("bindings") == []
            for assignment in context["slot_assignments"]
            if isinstance(assignment, dict)
        )
    invalid_picker = copy.deepcopy(new_picker._hmb_export_reset_handoff())
    invalid_picker["participant_kind"] = "image_asset"
    assert new_picker._hmb_adopt_reset_handoff(invalid_picker) is False
finally:
    routing._same_flow_nodes = original_same_flow_nodes
    routing.schedule_post_deletion_reconcile = original_schedule_deletion


print("HMB singleton Reset Shot image/Loader media preservation regression: PASS")
