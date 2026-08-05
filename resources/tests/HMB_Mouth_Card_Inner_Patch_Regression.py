from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"

maya_module = types.ModuleType("maya")
cmds_module = types.ModuleType("maya.cmds")
maya_module.cmds = cmds_module
sys.modules.setdefault("maya", maya_module)
sys.modules.setdefault("maya.cmds", cmds_module)

spec = importlib.util.spec_from_file_location("hmb_mouth_patch_runner", RUNNER_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def regular_grid_faces(columns: int = 6, rows: int = 6):
    stride = columns + 1
    result = []
    for row in range(rows):
        for column in range(columns):
            lower_left = (row * stride) + column
            result.append((
                lower_left,
                lower_left + 1,
                lower_left + stride + 1,
                lower_left + stride,
            ))
    return result


faces = regular_grid_faces()
plan = runner._mouth_grid_inner_patch_plan(49, 84, faces)
assert plan["eligible"] is True
assert len(plan["outer_faces"]) == 20
assert len(plan["inner_faces"]) == 16
assert plan["boundary_edge_count"] == 24

assert not runner._mouth_grid_inner_patch_plan(48, 84, faces)["eligible"]
assert not runner._mouth_grid_inner_patch_plan(49, 83, faces)["eligible"]
assert not runner._mouth_grid_inner_patch_plan(49, 84, faces[:-1])["eligible"]
damaged_faces = list(faces)
damaged_faces[0] = (0, 1, 8, 8)
assert not runner._mouth_grid_inner_patch_plan(49, 84, damaged_faces)["eligible"]

inner_uv_values = []
for v_index in range(1, 6):
    for u_index in range(1, 6):
        inner_uv_values.extend((u_index / 6.0, 2.0 + (v_index / 6.0)))
uv_plan = runner._mouth_inner_uv_plan_from_values(inner_uv_values)
assert uv_plan["eligible"] is True
assert uv_plan["udim"] == 1021
assert runner._alpha_bbox_fits_inner_uv(
    (0.20, 0.31, 0.80, 0.68),
    uv_plan["inner_bbox"],
)
assert not runner._alpha_bbox_fits_inner_uv(
    (0.0, 0.31, 0.80, 0.68),
    uv_plan["inner_bbox"],
)
bad_uv_values = list(inner_uv_values)
bad_uv_values[0] = 0.0
assert not runner._mouth_inner_uv_plan_from_values(bad_uv_values)["eligible"]

mouth_record = {
    "alpha_driven": True,
    "source_material": "Face_2d_mouth_Material",
    "shading_group": "Face_2d_mouth_SG",
}
assert runner._mouth_semantic_cutout_candidate(
    "|Character|FaceCardShape", mouth_record
)
assert not runner._mouth_semantic_cutout_candidate(
    "|Character|EyeCardShape", mouth_record
)
assert not runner._mouth_semantic_cutout_candidate(
    "|Character|BodyShape", {"alpha_driven": True}
)

depth_controller = runner._MouthCardInnerPatchController(
    {"_authored_cutout_snapshot": {"|Character|MouthShape": mouth_record}},
    "depth",
)
assert depth_controller.report["candidate_shape_path_count"] == 1
assert depth_controller.report["eligible_shape_path_count"] == 0
assert depth_controller.report["skipped_shape_path_count"] == 1
assert depth_controller.report["depth_excluded_shape_path_count"] == 1
assert depth_controller.report["skip_reason_counts"] == {
    "depth_policy_excludes_mouth_alpha": 1
}


class RenderCmds:
    def __init__(self, root: Path, fail_render: bool = False):
        self.root = root
        self.images_rule = "images"
        self.capture_folder: Path | None = None
        self.prefix = ""
        self.fail_render = fail_render
        self.events: list[str] = []

    def listRelatives(self, camera, **_kwargs):
        return [camera + "|cameraShape"]

    def workspace(
        self,
        query=False,
        rootDirectory=False,
        fileRuleEntry=None,
        fileRule=None,
    ):
        if query and rootDirectory:
            return str(self.root)
        if fileRuleEntry == "images":
            return self.images_rule
        if fileRule:
            self.images_rule = fileRule[1]
            self.capture_folder = Path(fileRule[1])
        return ""

    def setAttr(self, plug, value, **_kwargs):
        if plug == "defaultRenderGlobals.imageFilePrefix":
            self.prefix = value

    def currentTime(self, _frame, **_kwargs):
        self.events.append("currentTime")

    def ogsRender(self, **_kwargs):
        self.events.append("ogsRender")
        if self.fail_render:
            raise RuntimeError("synthetic OGS failure")
        assert self.capture_folder is not None
        self.capture_folder.mkdir(parents=True, exist_ok=True)
        (self.capture_folder / (self.prefix + ".png")).write_bytes(b"png")
        return True


original_cmds = runner.cmds
original_write_progress = runner._write_progress
runner._write_progress = lambda *_args, **_kwargs: None
try:
    with tempfile.TemporaryDirectory(prefix="hmb_mouth_patch_order_") as folder:
        root = Path(folder)
        render_cmds = RenderCmds(root)
        runner.cmds = render_cmds

        def prepare(*_args):
            render_cmds.events.append("prepare")

        def restore(*_args):
            render_cmds.events.append("restore")

        outputs, _frame_map = runner._render_frames(
            camera="|camera",
            frame_values=[1.0],
            width=64,
            height=64,
            frames_folder=str(root / "frames"),
            output_name="mouth_patch",
            pre_frame_callback=prepare,
            post_frame_callback=restore,
        )
        assert len(outputs) == 1
        assert render_cmds.events == [
            "currentTime", "prepare", "ogsRender", "restore"
        ]

    with tempfile.TemporaryDirectory(prefix="hmb_mouth_patch_failure_") as folder:
        root = Path(folder)
        render_cmds = RenderCmds(root, fail_render=True)
        runner.cmds = render_cmds

        def prepare_failure(*_args):
            render_cmds.events.append("prepare")

        def restore_failure(*_args):
            render_cmds.events.append("restore")

        try:
            runner._render_frames(
                camera="|camera",
                frame_values=[1.0],
                width=64,
                height=64,
                frames_folder=str(root / "frames"),
                output_name="mouth_patch",
                pre_frame_callback=prepare_failure,
                post_frame_callback=restore_failure,
            )
        except RuntimeError as exc:
            assert "synthetic OGS failure" in str(exc)
        else:
            raise AssertionError("Synthetic OGS failure should propagate")
        assert render_cmds.events == [
            "currentTime", "prepare", "ogsRender", "restore"
        ]
finally:
    runner.cmds = original_cmds
    runner._write_progress = original_write_progress


source = RUNNER_PATH.read_text(encoding="utf-8")
assert "cmds.file(save=True" not in source.replace(" ", "")
assert "post_frame_callback=mouth_controller.restore_frame" in source
assert "Depth refused an opaque fallback for a mouth alpha card." in source
assert '"depth_policy_excludes_mouth_alpha"' in source
assert "cmds.createDisplayLayer(" in source
assert "depth_hidden_shape_path_count" in source
assert "def _restore_depth_scope(self):" in source
assert "failed_entries.append(entry)" in source
assert "cmds.nodeType(item, inherited=True)" in source
assert "runtime_exclusion_verified_shape_path_count" in source
assert "def finalize_cutout_report():" in source
assert "scene_path" not in runner._MouthCardInnerPatchController.__init__.__code__.co_consts

print(
    "HMB Original mouth-card strict topology/UV/alpha gate, Depth full mouth-alpha "
    "exclusion, per-frame ordering, restoration, and no-save regression: PASS"
)
