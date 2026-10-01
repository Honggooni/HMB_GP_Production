"""Exercise the real Picker-to-Blender route on the user's read-only scene.

The source .blend is never copied or saved. All Picker products, temporary jobs,
logs, and generated media are redirected into a disposable workspace folder.
Run directly with Python; an unavailable sample or Blender install skips cleanly.
"""

from __future__ import annotations

import copy
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker


DEFAULT_SCENE = Path(
    r"C:\Users\jh_ahn\Documents\Codex\2026-09-15\qm\outputs\scissors.blend"
)
EXPECTED_ROLES = ("original", "mask", "depth", "motion_guide")
EXPECTED_KINDS = {
    "original": "blender_original_render",
    "mask": "blender_color_assignment_mask",
    "depth": "blender_depth_render",
    "motion_guide": "blender_motion_guide",
}
EXPECTED_VIDEO_ROLES = {
    "original": "blender_original_render",
    "mask": "blender_color_assignment_mask",
    "depth": "blender_depth_companion",
    "motion_guide": "blender_motion_guide_companion",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace(state: dict, number: int) -> dict:
    return next(
        row for row in state["picker_shots"]
        if isinstance(row, dict) and int(row.get("number") or 0) == number
    )


def _rows_for_shot(state: dict, number: int) -> list[dict]:
    workspace_uuid = _workspace(state, number)["workspace_uuid"]
    return [
        row for row in state["videos"]
        if isinstance(row, dict) and row.get("picker_shot_uuid") == workspace_uuid
    ]


def _catalog() -> dict:
    publisher = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    channel = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    shots = [
        {
            "shot_uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"hmb-blender-qa-shot-{number}")),
            "number": number,
            "name": f"Shot {number}",
            "revision": number,
        }
        for number in range(1, 6)
    ]
    document = {"channel_uuid": channel, "generation": 1, "shots": shots}
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": publisher,
        **document,
        "metadata_sha256": picker._sha256_canonical(document),
    }


class BlenderScissorsPickerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = Path(os.environ.get("HMB_BLEND_TEST_SCENE", str(DEFAULT_SCENE))).resolve()
        if not cls.scene.is_file() or cls.scene.suffix.casefold() != ".blend":
            raise unittest.SkipTest("The provided scissors.blend sample is not available.")
        if picker._find_blender() is None:
            raise unittest.SkipTest("Blender is not installed or discoverable.")
        if picker._find_ffmpeg() is None:
            raise unittest.SkipTest("FFmpeg is not installed or discoverable.")

    def _call(self, node: picker.HMBVideoPickerLibrary, action: str) -> dict:
        state = node._picker_state()
        state.update({
            "scene_path": str(self.scene),
            "scene_request_path": str(self.scene),
            "scene_draft_path": str(self.scene),
            "backend_ack_action_id": f"blender-qa-{action}-{uuid.uuid4().hex}",
            "pending_action": "",
            "pending_action_id": "",
        })
        node._hmb_cancel_requested.clear()
        node._start_ui_operation(action, state)
        final = node._picker_state()
        detail = f"{final.get('message')} (QA artifacts: {getattr(self, '_qa_output_root', '')})"
        self.assertNotEqual(final.get("status"), "FAILED", detail)
        self.assertNotEqual(final.get("status"), "STALE_RESULT_DISCARD", final.get("message"))
        return final

    def _select_shot(self, node: picker.HMBVideoPickerLibrary, number: int) -> dict:
        state = node._picker_state()
        expected_orders = {
            row["workspace_uuid"]: list(row["selected_video_uids"])
            for row in state["picker_shots"] if isinstance(row, dict)
        }
        shot_uuid = _workspace(state, number)["workspace_uuid"]
        projected = picker._activate_picker_workspace_projection(state, shot_uuid)
        self.assertIsNotNone(projected)
        for row in projected["picker_shots"]:
            self.assertEqual(
                row["selected_video_uids"], expected_orders[row["workspace_uuid"]],
                f"Shot {number} projection changed saved order for Shot {row['number']}: "
                f"before={expected_orders[row['workspace_uuid']]}, after={row['selected_video_uids']}",
            )
        node._write_state(projected)
        selected = node._picker_state()
        for row in selected["picker_shots"]:
            self.assertEqual(
                row["selected_video_uids"], expected_orders[row["workspace_uuid"]],
                f"Shot {number} commit changed saved order for Shot {row['number']}: "
                f"before={expected_orders[row['workspace_uuid']]}, after={row['selected_video_uids']}",
            )
        self.assertEqual(selected["active_picker_shot_uuid"], shot_uuid)
        return selected

    def _assert_selected_output(self, state: dict, number: int, roles: tuple[str, ...]) -> None:
        workspace = _workspace(state, number)
        selected_uids = list(workspace["selected_video_uids"])
        self.assertEqual(
            len(selected_uids), len(roles),
            f"Shot {number}: selected={selected_uids}, owned={workspace['video_asset_uids']}, "
            f"catalog={[row.get('generation_role') for row in _rows_for_shot(state, number)]}",
        )
        selected_items = [next(row for row in state["videos"] if row["video_uid"] == uid)
                          for uid in selected_uids]
        self.assertEqual(tuple(row["generation_role"] for row in selected_items), roles)
        self.assertTrue(all(row["picker_shot_uuid"] == workspace["workspace_uuid"]
                            for row in selected_items))

        selected_state = picker._activate_picker_workspace_projection(state, workspace["workspace_uuid"])
        self.assertIsNotNone(selected_state)
        payload, media = picker._build_synchronized_video_outputs(
            selected_state, enforce_media_availability=True,
        )
        self.assertEqual(payload["mode"], "blender")
        self.assertEqual(payload["scene_engine"], "blender")
        self.assertEqual(selected_state["shot_number"], number)
        self.assertEqual(len(payload["videos"]), len(roles))
        self.assertEqual(len(media), len(roles))
        self.assertEqual(payload["ordered_video_uids"], selected_uids)
        for index, (row, video) in enumerate(zip(selected_items, payload["videos"]), start=1):
            role = roles[index - 1]
            self.assertEqual(video["video_uid"], row["video_uid"])
            self.assertEqual(video["generation_role"], role)
            self.assertEqual(video["media_kind"], EXPECTED_KINDS[role])
            self.assertEqual(video["video_role"], EXPECTED_VIDEO_ROLES[role])
            self.assertEqual(video["scene_engine"], "blender")
            self.assertEqual(video["selection_order"], index)
            self.assertEqual(video["video_slot"], index)
            self.assertEqual(video["video_path"], media[index - 1])
            self.assertTrue(Path(media[index - 1]).is_file())
            frame = video["frame_metadata"]
            self.assertEqual(frame["scene_engine"], "blender")
            self.assertEqual(frame["origin"], "decoded_video+blender")
            self.assertEqual(frame["frame_count"], 2)
            self.assertEqual(frame["width"], 320)
            self.assertEqual(frame["height"], 180)
            if role == "depth":
                self.assertEqual(video["depth_profile"], picker.BLENDER_DEPTH_PROFILE)
            elif role == "motion_guide":
                self.assertEqual(video["motion_guide_profile"], picker.BLENDER_MOTION_GUIDE_PROFILE)
            elif role == "mask":
                self.assertTrue(any(marker["asset_id"] == "Scissors_ROOT"
                                    for marker in video["markers"]))
        if "mask" in roles:
            mask_uid = selected_items[roles.index("mask")]["video_uid"]
            mask_slot = roles.index("mask") + 1
            for role in ("depth", "motion_guide"):
                if role in roles:
                    companion = payload["videos"][roles.index(role)]
                    self.assertEqual(companion["companion_video_uid"], mask_uid)
                    self.assertEqual(companion["source_video_slot"], mask_slot)
                    self.assertEqual(companion["companion_of_video_slot"], mask_slot)
        else:
            for role in ("depth", "motion_guide"):
                if role in roles:
                    companion = payload["videos"][roles.index(role)]
                    self.assertEqual(companion.get("companion_video_uid"), "")
                    self.assertEqual(companion.get("source_video_uid"), "")
                    self.assertEqual(companion["source_video_slot"], 0)
                    self.assertEqual(companion["companion_of_video_slot"], 0)

    def test_read_snapshot_original_all_outputs_and_five_shots(self) -> None:
        source_sha256 = _sha256(self.scene)
        source_mtime_ns = self.scene.stat().st_mtime_ns
        (ROOT / ".tmp").mkdir(exist_ok=True)
        keep_outputs = os.environ.get("HMB_BLEND_KEEP_QA", "").strip().lower() in {"1", "true", "yes"}
        output_context = (
            nullcontext(tempfile.mkdtemp(prefix="hmb-picker-blender-scissors-", dir=ROOT / ".tmp"))
            if keep_outputs else
            tempfile.TemporaryDirectory(prefix="hmb-picker-blender-scissors-", dir=ROOT / ".tmp")
        )
        with output_context as temp:
            output_root = Path(temp) / "picker-output"
            output_root.mkdir()
            self._qa_output_root = output_root
            # The production preset is HD. This accepted 16:9 QA preset keeps
            # the real process/encoder route quick and does not edit the source.
            qa_resolutions = (*picker.PLAYBLAST_RESOLUTIONS, (320, 180))
            with patch.object(picker, "_scene_output_folder", return_value=output_root), patch.object(
                picker, "PLAYBLAST_RESOLUTIONS", qa_resolutions,
            ), patch.object(picker, "_video_asset_thumbnail_url", return_value=("", "")):
                catalog = _catalog()
                state = picker._default_widget_state()
                state.update({
                    "scene_path": str(self.scene),
                    "scene_request_path": str(self.scene),
                    "scene_draft_path": str(self.scene),
                    "shot_publisher_instance_uuid": catalog["publisher_instance_uuid"],
                    "channel_uuid": catalog["channel_uuid"],
                    "shot_selections": copy.deepcopy(catalog["shots"]),
                    "accepted_shot_catalog_publisher_instance_uuid": catalog["publisher_instance_uuid"],
                    "accepted_shot_catalog_channel_uuid": catalog["channel_uuid"],
                    "accepted_shot_catalog_generation": catalog["generation"],
                    "accepted_shot_catalog_metadata_sha256": catalog["metadata_sha256"],
                    "picker_shots": [
                        picker._new_picker_workspace_row(
                            number,
                            bound_shot_uuid=shot["shot_uuid"],
                            workspace_uuid=picker._picker_workspace_uuid_for_bound_shot(shot["shot_uuid"]),
                        )
                        for number, shot in enumerate(catalog["shots"], start=1)
                    ],
                    "output_width": 320,
                    "output_height": 180,
                })
                state["active_picker_shot_uuid"] = state["picker_shots"][0]["workspace_uuid"]
                state.update({
                    "shot_uuid": catalog["shots"][0]["shot_uuid"],
                    "shot_number": 1,
                    "shot_name": "Shot 1",
                })
                node = picker.HMBVideoPickerLibrary(name="BlenderScissorsPickerIntegration")
                node._hmb_shot_catalog_snapshot = copy.deepcopy(catalog)
                node._hmb_shot_route_status = {"ok": True, "code": "ready"}
                node._write_state(state)

                read = self._call(node, "read_scene")
                self.assertTrue(read["native_read_ready"])
                self.assertEqual(read["native_read_mode"], "blender-background-atomic")
                self.assertEqual(read["scene_engine"], "blender")
                self.assertEqual(read["selected_camera"], "|Product_camera")
                root = next(row for row in read["outliner_nodes"]
                            if row["full_path"] == "|Scissors_ROOT")
                self.assertEqual(len(read["picker_shots"]), 5)

                read.update({
                    "start_frame": 1,
                    "end_frame": 2,
                    "current_frame": 1,
                    "snapshot_frame": 1,
                    "output_width": 320,
                    "output_height": 180,
                    "original_enabled": True,
                    "mask_enabled": True,
                    "depth_enabled": True,
                    "motion_guide_enabled": True,
                    "slot_assignments": [{"video_slot": 1, "bindings": [{
                        "group_name": "Scissors_ROOT",
                        "full_dag_path": root["full_path"],
                        "maya_uuid": root["maya_uuid"],
                        "color": "Red",
                        "enabled": True,
                        "picker_order": 1,
                    }]}],
                })
                node._write_state(read)

                snapshot = self._call(node, "render_snapshot")
                self.assertTrue(snapshot["snapshots"])
                snapshot_item = snapshot["snapshots"][-1]
                snapshot_path = Path(snapshot_item["path"])
                self.assertTrue(snapshot_path.is_file())
                self.assertTrue(snapshot_path.is_relative_to(output_root))
                self.assertEqual(snapshot_item["sha256"], _sha256(snapshot_path))
                self.assertEqual(_workspace(snapshot, 1)["active_snapshot_uid"], snapshot_item["snapshot_uid"])

                original = self._call(node, "render_original_preview")
                original_path = Path(original["original_video_path"])
                self.assertTrue(original_path.is_file())
                self.assertTrue(original_path.is_relative_to(output_root))
                self.assertEqual(original["original_metadata"]["scene_engine"], "blender")

                focused_choices = os.environ.get("HMB_BLEND_QA_FOCUSED", "").strip().lower() in {"1", "true", "yes"}
                main_shots = (5,) if focused_choices else tuple(range(1, 6))
                completed_main: list[int] = []
                for number in main_shots:
                    shot_state = self._select_shot(node, number)
                    shot_state.update({
                        "original_enabled": True,
                        "mask_enabled": True,
                        "depth_enabled": True,
                        "motion_guide_enabled": True,
                        "slot_assignments": [{"video_slot": 1, "bindings": [{
                            "group_name": "Scissors_ROOT",
                            "full_dag_path": root["full_path"],
                            "maya_uuid": root["maya_uuid"],
                            "color": "Red",
                            "enabled": True,
                            "picker_order": 1,
                        }]}],
                    })
                    node._write_state(shot_state)
                    generation = self._call(node, "run_video")
                    self.assertEqual(generation["scene_stage"], "VIDEO_READY", generation.get("message"))
                    self.assertEqual(tuple(generation["generation_output_roles"]), EXPECTED_ROLES)
                    self._assert_selected_output(generation, number, EXPECTED_ROLES)
                    self.assertEqual(len(_rows_for_shot(generation, number)), 4)
                    for other in completed_main:
                        self.assertEqual(len(_rows_for_shot(generation, other)), 4)
                    completed_main.append(number)
                    self.assertEqual(len(generation["videos"]), len(completed_main) * 4)

                # The optional Mask-only path must add just one selected card.
                state = self._select_shot(node, 5)
                state.update({"original_enabled": False, "mask_enabled": True,
                              "depth_enabled": False, "motion_guide_enabled": False})
                node._write_state(state)
                mask_commit: dict = {}
                original_commit = node._commit_generate_terminal_state

                def observe_mask_commit(terminal_state, context, records, provisional):
                    mask_commit.update({
                        "latest_selected": list(_workspace(node._picker_state(), 5)["selected_video_uids"]),
                        "terminal_selected": list(_workspace(terminal_state, 5)["selected_video_uids"]),
                        "provisional_uids": list(provisional),
                        "generation_records": [
                            (row.get("generation_role"), row.get("video_uid")) for row in records
                        ],
                    })
                    return original_commit(terminal_state, context, records, provisional)

                with patch.object(node, "_commit_generate_terminal_state", side_effect=observe_mask_commit):
                    mask_only = self._call(node, "run_video")
                self.assertEqual(mask_only["generation_output_roles"], ["mask"])
                self.assertEqual(len(_rows_for_shot(mask_only, 5)), 5)
                self.assertEqual(
                    len(_workspace(mask_only, 5)["selected_video_uids"]), 5,
                    f"Mask-only Shot 5 selection: "
                    f"{_workspace(mask_only, 5)['selected_video_uids']}; "
                    f"catalog={[row.get('generation_role') for row in _rows_for_shot(mask_only, 5)]}; "
                    f"commit={mask_commit}",
                )
                self.assertEqual(_rows_for_shot(mask_only, 5)[-1]["media_kind"], EXPECTED_KINDS["mask"])

                # With Mask off, both companions are still valid standalone
                # references and must not claim the hidden mask as a selected
                # source UID or slot.
                state = self._select_shot(node, 4)
                self.assertEqual(
                    len(_workspace(state, 5)["selected_video_uids"]), 5,
                    f"Shot 5 selection changed when switching to Shot 4: "
                    f"{_workspace(state, 5)['selected_video_uids']}",
                )
                state.update({"original_enabled": False, "mask_enabled": False,
                              "depth_enabled": True, "motion_guide_enabled": True,
                              "slot_assignments": [{"video_slot": 1, "bindings": [{
                                  "group_name": "Scissors_ROOT",
                                  "full_dag_path": root["full_path"],
                                  "maya_uuid": root["maya_uuid"],
                                  "color": "Red", "enabled": True, "picker_order": 1,
                              }]}]})
                node._write_state(state)
                self.assertEqual(
                    len(_workspace(node._picker_state(), 5)["selected_video_uids"]), 5,
                    "Shot 5 selection changed while authoring Shot 4 companion-only settings.",
                )
                companion_trace: list[dict] = []
                original_write_state = node._write_state
                original_companion_commit = node._commit_generate_terminal_state

                def trace_companion_write(incoming):
                    before = list(_workspace(node._picker_state(), 5)["selected_video_uids"])
                    proposed = list(_workspace(incoming, 5)["selected_video_uids"])
                    original_write_state(incoming)
                    after = list(_workspace(node._picker_state(), 5)["selected_video_uids"])
                    if before != after or proposed != after:
                        companion_trace.append({
                            "stage": "write_state",
                            "status": incoming.get("status"),
                            "operation_kind": incoming.get("operation_kind"),
                            "message": str(incoming.get("message") or "")[:150],
                            "before": before,
                            "proposed": proposed,
                            "after": after,
                            "video_count": len(node._picker_state()["videos"]),
                        })

                def trace_companion_commit(terminal_state, context, records, provisional):
                    companion_trace.append({
                        "stage": "commit_before",
                        "latest": list(_workspace(node._picker_state(), 5)["selected_video_uids"]),
                        "terminal": list(_workspace(terminal_state, 5)["selected_video_uids"]),
                        "provisional": list(provisional),
                        "record_roles": [row.get("generation_role") for row in records],
                    })
                    result = original_companion_commit(terminal_state, context, records, provisional)
                    companion_trace.append({
                        "stage": "commit_after",
                        "selected": list(_workspace(result, 5)["selected_video_uids"]),
                    })
                    return result

                with patch.object(node, "_write_state", side_effect=trace_companion_write), patch.object(
                    node, "_commit_generate_terminal_state", side_effect=trace_companion_commit,
                ):
                    companions_only = self._call(node, "run_video")
                self.assertEqual(companions_only["generation_output_roles"], ["depth", "motion_guide"])
                expected_shot4_count = (4 if 4 in completed_main else 0) + 2
                self.assertEqual(len(_rows_for_shot(companions_only, 4)), expected_shot4_count)
                self.assertEqual(
                    len(_workspace(companions_only, 4)["selected_video_uids"]), expected_shot4_count,
                    f"Companion-only Shot 4 selection: "
                    f"{_workspace(companions_only, 4)['selected_video_uids']}; "
                    f"catalog={[row.get('generation_role') for row in _rows_for_shot(companions_only, 4)]}",
                )
                new_companions = _rows_for_shot(companions_only, 4)[-2:]
                for row in new_companions:
                    self.assertFalse(row.get("companion_video_uid"))
                    self.assertFalse(row.get("source_video_uid"))
                self.assertEqual(
                    len(_workspace(companions_only, 5)["selected_video_uids"]), 5,
                    f"Shot 4 companion-only generation changed Shot 5 selection: "
                    f"{_workspace(companions_only, 5)['selected_video_uids']}; trace={companion_trace}",
                )

                # Revisit every workspace after all publications. A Shot
                # switch must never expose media from a different Shot.
                expected_counts = {number: (4 if number in completed_main else 0)
                                   for number in range(1, 6)}
                expected_counts[4] += 2
                expected_counts[5] += 1
                for number in range(5, 0, -1):
                    selected = self._select_shot(node, number)
                    row = _workspace(selected, number)
                    self.assertEqual(len(row["selected_video_uids"]), expected_counts[number])
                    self.assertEqual(len(row["video_asset_uids"]), expected_counts[number])
                    selected_uids = set(row["selected_video_uids"])
                    self.assertEqual(selected_uids, {
                        item["video_uid"] for item in _rows_for_shot(selected, number)
                    })
                    payload, media = picker._build_synchronized_video_outputs(
                        selected, enforce_media_availability=True,
                    )
                    self.assertEqual(selected["shot_number"], number)
                    self.assertEqual(len(media), expected_counts[number])
                    self.assertEqual(set(payload["ordered_video_uids"]), selected_uids)

                self.assertTrue(all(path.is_relative_to(output_root)
                                    for path in output_root.rglob("*.mp4")))

        self.assertEqual(_sha256(self.scene), source_sha256, "The source .blend changed")
        self.assertEqual(self.scene.stat().st_mtime_ns, source_mtime_ns)


if __name__ == "__main__":
    unittest.main()
