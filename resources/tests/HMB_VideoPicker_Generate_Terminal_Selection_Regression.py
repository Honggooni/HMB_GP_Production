"""Fast regression for final Generate selection after provisional card replacement."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from HMBVideoPickerLibrary import (
    _blender_generated_item_for_result,
    _original_video_item_from_state,
    _restore_terminal_only_generated_selection,
    _video_frame_metadata,
)


class GenerateTerminalSelectionRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.generated = {
            "original": "draft-original",
            "mask": "draft-mask",
            "depth": "draft-depth",
            "motion_guide": "draft-motion",
        }
        self.actual = {
            "original": "final-original",
            "mask": "final-mask",
            "depth": "final-depth",
            "motion_guide": "final-motion",
        }
        self.roles = tuple(self.generated)
        self.owned = ["old-video", *self.actual.values()]

    def _restore(self, selected: list[str], terminal: list[str], *, engine: str = "blender") -> list[str]:
        return _restore_terminal_only_generated_selection(
            selected,
            scene_engine=engine,
            owned_uids=self.owned,
            terminal_selected_uids=terminal,
            generated_uid_by_role=self.generated,
            actual_uid_by_role=self.actual,
            provisional_roles={"mask", "depth", "motion_guide"},
            ordered_roles=self.roles,
        )

    def test_original_is_selected_before_mask_depth_and_motion(self) -> None:
        selected = ["old-video", "final-mask", "final-depth", "final-motion"]
        terminal = list(self.generated.values())
        self.assertEqual(
            self._restore(selected, terminal),
            ["old-video", "final-original", "final-mask", "final-depth", "final-motion"],
        )

    def test_provisional_deselection_is_not_undone(self) -> None:
        terminal = list(self.generated.values())
        self.assertEqual(
            self._restore(["final-depth", "final-motion"], terminal),
            ["final-original", "final-depth", "final-motion"],
        )

    def test_unselected_original_remains_unselected(self) -> None:
        self.assertEqual(
            self._restore(["final-mask"], ["draft-mask"]),
            ["final-mask"],
        )

    def test_maya_terminal_selection_is_unchanged(self) -> None:
        selected = ["old-video", "final-mask", "final-depth", "final-motion"]
        self.assertEqual(
            self._restore(selected, list(self.generated.values()), engine="maya"),
            selected,
        )

    def test_maya_video_metadata_has_no_blender_fields(self) -> None:
        frame = _video_frame_metadata({
            "media_kind": "maya_original_playblast",
            "source_fps": 24,
            "output_frame_count": 24,
            "start_frame": 101,
            "end_frame": 124,
            "has_maya_frame_range": True,
        }, 1)
        self.assertNotIn("scene_engine", frame)
        self.assertNotIn("blender_start_frame", frame)
        self.assertNotIn("blender_end_frame", frame)
        original = _original_video_item_from_state({
            "scene_path": "C:/example/scene.mb",
            "original_video_path": "C:/example/original.mp4",
            "original_metadata": {"fps": 24, "frame_count": 24},
        })
        self.assertNotIn("scene_engine", original)

    def test_blender_companions_do_not_capture_another_shots_mask(self) -> None:
        shot4 = str(uuid.uuid4())
        shot5 = str(uuid.uuid4())
        result = {
            "bundle_run_id": "blender-current",
            "video": "C:/renders/current-mask.mp4",
            "depth_video": "C:/renders/current-depth.mp4",
            "motion_guide_video": "C:/renders/current-motion.mp4",
        }
        videos = [
            {"generation_role": "mask", "scene_engine": "blender",
             "picker_shot_uuid": shot5, "bundle_run_id": "blender-previous",
             "video_path": "C:/renders/previous-mask.mp4", "video_uid": "shot5-mask"},
            {"generation_role": "depth", "scene_engine": "blender",
             "picker_shot_uuid": shot4, "bundle_run_id": "blender-current",
             "video_path": result["depth_video"], "video_uid": "shot4-depth"},
            {"generation_role": "motion_guide", "scene_engine": "blender",
             "picker_shot_uuid": shot4, "bundle_run_id": "blender-current",
             "video_path": result["motion_guide_video"], "video_uid": "shot4-motion"},
        ]
        self.assertEqual(
            _blender_generated_item_for_result(videos, "depth", result, shot4)["video_uid"],
            "shot4-depth",
        )
        self.assertEqual(
            _blender_generated_item_for_result(videos, "motion_guide", result, shot4)["video_uid"],
            "shot4-motion",
        )
        with self.assertRaisesRegex(RuntimeError, "captured Shot"):
            _blender_generated_item_for_result(videos, "mask", result, shot4)


if __name__ == "__main__":
    unittest.main()
