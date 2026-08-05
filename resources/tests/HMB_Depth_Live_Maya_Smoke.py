from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


mayabatch = picker._find_mayabatch()
ffmpeg = picker._find_ffmpeg(mayabatch)
if mayabatch is None or ffmpeg is None:
    print("HMB live Depth smoke: SKIP (Maya or FFmpeg is unavailable)")
    raise SystemExit(0)

mayapy = Path(mayabatch).with_name("mayapy.exe")
builder = ROOT / ".tmp" / "build_motion_guide_smoke_scene.py"
if not mayapy.is_file() or not builder.is_file():
    print("HMB live Depth smoke: SKIP (fixture builder is unavailable)")
    raise SystemExit(0)

run_folder = (
    ROOT
    / ".tmp"
    / "depth_live_smoke"
    / time.strftime("%Y%m%d_%H%M%S")
)
run_folder.mkdir(parents=True, exist_ok=False)
scene_path = run_folder / "HMB_Depth_Live_Smoke.ma"
build_log = run_folder / "build.log"
with build_log.open("w", encoding="utf-8", errors="replace") as handle:
    built = subprocess.run(
        [str(mayapy), str(builder), str(scene_path)],
        stdout=handle,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
assert built.returncode == 0, build_log.read_text(
    encoding="utf-8",
    errors="replace",
)[-8000:]

color_frames = run_folder / "color_frames"
depth_frames = run_folder / "depth_frames"
job_path = run_folder / "render.job.json"
result_path = run_folder / "render.result.json"
progress_path = run_folder / "render.progress.json"
color_sidecar_path = run_folder / "color.hmb.json"
depth_sidecar_path = run_folder / "depth.hmb.json"
log_path = run_folder / "mayabatch.log"
color_video_path = run_folder / "color.mp4"
depth_video_path = run_folder / "depth.mp4"

color_output_name = "HMB_Depth_Smoke_Color"
depth_output_name = "HMB_Depth_Smoke_Depth"
job = {
    "operation": "render",
    "scene_path": str(scene_path),
    "output_folder": str(run_folder),
    "output_name": color_output_name,
    "frames_folder": str(color_frames),
    "sidecar_path": str(color_sidecar_path),
    "result_path": str(result_path),
    "progress_path": str(progress_path),
    "camera": "|shotCam1",
    "width": 640,
    "height": 360,
    "start_frame": 1,
    "end_frame": 3,
    "fps": 24,
    "apply_marker_shaders": True,
    "character_outline_mode": "native_lambert",
    "force_high_quality_viewport": True,
    "viewport_quality_profile": picker.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
    "require_full_smooth_geometry": True,
    "screen_space_patterns": True,
    "screen_space_pattern_profile": picker.SCREEN_SPACE_PATTERN_PROFILE,
    "expected_maya_major": "2027",
    "marker_catalog_path": str(picker.MARKER_CATALOG_PATH),
    "marker_catalog_version": int(picker.MARKER_CATALOG["version"]),
    "video_slot": 1,
    "bindings": [
        {
            "group_name": "MotionActor_G",
            "full_dag_path": "|MotionActor_G",
            "asset_id": "MotionActor",
            "color": "Red",
            "video_slot": 1,
            "picker_order": 1,
        },
        {
            "group_name": "HiddenProp_G",
            "full_dag_path": "|HiddenProp_G",
            "asset_id": "HiddenProp",
            "color": "Sky Blue",
            "video_slot": 1,
            "picker_order": 2,
        },
    ],
    "hidden_paths": [],
    "generate_depth_playblast": True,
    "depth_video_slot": 2,
    "depth_output_name": depth_output_name,
    "depth_frames_folder": str(depth_frames),
    "depth_sidecar_path": str(depth_sidecar_path),
    "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
}
job_path.write_text(
    json.dumps(job, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

scene_hash_before = sha256(scene_path)
environment = picker._maya_subprocess_environment(job_path)
command = [
    str(mayabatch),
    "-command",
    picker._maya_runner_command(),
]
with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
    completed = subprocess.run(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(job_path.parent),
        env=environment,
        timeout=900,
        check=False,
    )
assert completed.returncode == 0, log_path.read_text(
    encoding="utf-8",
    errors="replace",
)[-8000:]
assert sha256(scene_path) == scene_hash_before

result = json.loads(result_path.read_text(encoding="utf-8"))
color_sidecar = json.loads(color_sidecar_path.read_text(encoding="utf-8"))
depth_sidecar = json.loads(depth_sidecar_path.read_text(encoding="utf-8"))
assert result["ok"] is True
assert result["frame_count"] == result["depth_frame_count"] == 3
assert result["depth_profile"] == picker.DEPTH_PLAYBLAST_PROFILE
assert color_sidecar["camera"] == depth_sidecar["camera"] == "|shotCam1"
assert color_sidecar["resolution"] == depth_sidecar["resolution"] == {
    "width": 640,
    "height": 360,
}
assert color_sidecar["fps"] == depth_sidecar["fps"] == 24.0
assert [item["maya_frame"] for item in color_sidecar["frame_map"]] == [
    item["maya_frame"] for item in depth_sidecar["frame_map"]
]
assert depth_sidecar["depth_range_report"]["background"] == "pure_black"
assert (
    depth_sidecar["depth_range_report"]["direction"]
    == "near_white_far_black"
)
depth_range_report = depth_sidecar["depth_range_report"]
assert depth_range_report["source"] == "object_bbox_camera_depth"
assert (
    depth_range_report["assignment_mode"]
    == "color_picker_style_shared_gray_material_buckets"
)
assert depth_range_report["depth_update_scope"] == (
    "per_shape_path_per_output_frame"
)
assert depth_range_report["representative_depth"] == (
    "median_positive_camera_depth_of_world_bbox_corners"
)
assert depth_range_report["shader_model"] == "surfaceShader"
assert depth_range_report["grayscale_bucket_count"] == 256
assert depth_range_report["standard_nodes"] == ["surfaceShader"]
assert depth_range_report["near_color"] == 0.9
assert depth_range_report["output_value_range"] == [0.0, 0.9]
assert depth_range_report["camera_near_safety_margin"] == 0.1
assert depth_range_report["reserved_output_value_range"] == [0.9, 1.0]
assignment_verification = depth_range_report["assignment_verification"]
assert assignment_verification["rendered_frame_count"] == 3
assert assignment_verification["expected_frame_assignment_count"] == (
    3 * assignment_verification["shape_path_count"]
)
assert assignment_verification["verified_frame_assignment_count"] == (
    assignment_verification["expected_frame_assignment_count"]
)

color_pattern = color_frames / f"{color_output_name}.%06d.png"
depth_pattern = depth_frames / f"{depth_output_name}.%06d.png"
for frame_index in range(3):
    assert Path(str(color_pattern) % frame_index).is_file()
    assert Path(str(depth_pattern) % frame_index).is_file()

try:
    from PIL import Image
except ImportError:
    Image = None
if Image is not None:
    depth_image = Image.open(Path(str(depth_pattern) % 0)).convert("RGB")
    pixels = list(depth_image.getdata())
    assert all(red == green == blue for red, green, blue in pixels)
    grayscale_values = [red for red, _green, _blue in pixels]
    assert min(grayscale_values) == 0
    assert max(grayscale_values) > 0
    assert len(set(grayscale_values)) >= 2

    # v5 intentionally applies one fixed grayscale bucket per full object DAG
    # path, so curved surfaces need not contain a continuous per-pixel ramp.
    # Pixel-content classification remains diagnostic-only; complete per-frame
    # material-assignment evidence above is the blocking coverage contract.
    color_frame_paths = [
        Path(str(color_pattern) % frame_index)
        for frame_index in range(3)
    ]
    depth_frame_paths = [
        Path(str(depth_pattern) % frame_index)
        for frame_index in range(3)
    ]
    depth_validation = picker._validate_depth_companion_inputs(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frame_paths,
        depth_frame_paths=depth_frame_paths,
        expected_frame_count=3,
        expected_fps=24.0,
        expected_start_frame=1.0,
        expected_end_frame=3.0,
        expected_width=640,
        expected_height=360,
    )
    assert depth_validation["validated"] is True
    assert depth_validation["quality_medians"]["foreground_coverage_ratio"] > 0.0
    assert depth_validation["content_heuristics_blocking"] is False

for frame_pattern, output_path in (
    (color_pattern, color_video_path),
    (depth_pattern, depth_video_path),
):
    encode = picker._build_ffmpeg_encode_command(
        ffmpeg=ffmpeg,
        frame_pattern=frame_pattern,
        output_path=output_path,
        source_fps=24.0,
        frame_count=3,
        width=640,
        height=360,
    )
    encoded = subprocess.run(
        encode,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
    assert encoded.returncode == 0, encoded.stdout.decode(
        "utf-8",
        errors="replace",
    )
    assert picker._is_structurally_valid_mp4(output_path)

print(
    "HMB live Color + Depth Maya smoke: PASS "
    f"({run_folder}, {result['frame_count']} frames each)"
)
