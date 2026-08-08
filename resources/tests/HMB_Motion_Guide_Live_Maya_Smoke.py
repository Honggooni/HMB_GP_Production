from __future__ import annotations

import hashlib
import json
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
    print("HMB live Motion Guide smoke: SKIP (Maya or FFmpeg is unavailable)")
    raise SystemExit(0)

mayapy = Path(mayabatch).with_name("mayapy.exe")
builder = ROOT / ".tmp" / "build_motion_guide_smoke_scene.py"
if not mayapy.is_file() or not builder.is_file():
    print("HMB live Motion Guide smoke: SKIP (fixture builder is unavailable)")
    raise SystemExit(0)

run_folder = (
    ROOT
    / ".tmp"
    / "motion_guide_live_smoke"
    / time.strftime("%Y%m%d_%H%M%S")
)
run_folder.mkdir(parents=True, exist_ok=False)
scene_path = run_folder / "HMB_Motion_Guide_Smoke.ma"
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
assert scene_path.is_file()

color_frames = run_folder / "color_frames"
depth_frames = run_folder / "depth_frames"
motion_frames = run_folder / "motion_frames"
job_path = run_folder / "render.job.json"
result_path = run_folder / "render.result.json"
progress_path = run_folder / "render.progress.json"
color_sidecar_path = run_folder / "color.hmb.json"
depth_sidecar_path = run_folder / "depth.hmb.json"
motion_sidecar_path = run_folder / "motion.hmb.json"
log_path = run_folder / "mayabatch.log"

color_output_name = "HMB_Motion_Smoke_Color"
depth_output_name = "HMB_Motion_Smoke_Depth"
motion_output_name = "HMB_Motion_Smoke_Guide"
hidden_paths = ["|HiddenProp_G"]
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
    "hidden_paths": hidden_paths,
    "generate_depth_playblast": True,
    "depth_video_slot": 2,
    "depth_output_name": depth_output_name,
    "depth_frames_folder": str(depth_frames),
    "depth_sidecar_path": str(depth_sidecar_path),
    "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
    "generate_motion_guide": True,
    "motion_guide_video_slot": 3,
    "motion_guide_output_name": motion_output_name,
    "motion_guide_frames_folder": str(motion_frames),
    "motion_guide_sidecar_path": str(motion_sidecar_path),
    "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
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
)[-12000:]
assert sha256(scene_path) == scene_hash_before

result = json.loads(result_path.read_text(encoding="utf-8"))
color_sidecar = json.loads(color_sidecar_path.read_text(encoding="utf-8"))
depth_sidecar = json.loads(depth_sidecar_path.read_text(encoding="utf-8"))
motion_sidecar = json.loads(motion_sidecar_path.read_text(encoding="utf-8"))
assert result["ok"] is True
assert result["frame_count"] == 3
assert result["depth_frame_count"] == 3
assert result["motion_guide_frame_count"] == 3
assert result["depth_profile"] == picker.DEPTH_PLAYBLAST_PROFILE
assert result["motion_guide_profile"] == picker.MOTION_GUIDE_PROFILE
assert motion_sidecar["schema"] == "hmb-maya-motion-guide"
assert (
    motion_sidecar["schema_version"]
    == picker.MOTION_GUIDE_RUNNER_SCHEMA_VERSION
)
assert color_sidecar["camera"] == depth_sidecar["camera"] == "|shotCam1"
assert motion_sidecar["camera"] == "|shotCam1"
assert color_sidecar["resolution"] == depth_sidecar["resolution"]
assert motion_sidecar["resolution"] == {"width": 640, "height": 360}
assert color_sidecar["fps"] == depth_sidecar["fps"] == 24.0
assert motion_sidecar["fps"] == 24.0
assert color_sidecar["hidden_paths"] == hidden_paths
assert depth_sidecar["hidden_paths"] == hidden_paths
assert motion_sidecar["hidden_paths"] == hidden_paths

color_timing = [item["maya_frame"] for item in color_sidecar["frame_map"]]
assert color_timing == [
    item["maya_frame"] for item in depth_sidecar["frame_map"]
]
assert color_timing == [
    item["maya_frame"] for item in motion_sidecar["frame_map"]
]
report = motion_sidecar["motion_guide_report"]
assert report["profile"] == picker.MOTION_GUIDE_PROFILE
face_semantics = report["face_semantics"]
assert face_semantics["schema"] == "hmb-maya-face-semantics"
assert face_semantics["schema_version"] == 2
assert face_semantics["curve_geometry_rendered"] is False
assert face_semantics["target_count"] == 0
assert face_semantics["channel_count"] == 0
assert face_semantics["driver_count"] == 0
assert face_semantics["landmark_count"] == 0
assert report["target_count"] == 1
assert report["joint_target_count"] >= 1
assert report["total_point_samples"] > 0
assert report["visible_target_samples"] == 3
assert report["appearance_authority"] == "zero"
assert report["camera_authority"] == "zero_independent_authority"
assert report["motion_authority"] == "derived_decoder_of_video1_only"
assert report["hidden_paths"] == hidden_paths
actor_frames = [
    next(
        target
        for target in frame["targets"]
        if target["asset_id"] == "MotionActor"
    )
    for frame in report["motion_frames"]
]
assert all(item["visible"] for item in actor_frames)
assert all(item["points"] for item in actor_frames)
assert all(item["face"]["available"] is False for item in actor_frames)
assert all(item["face"]["rasterized"] is False for item in actor_frames)
assert all(
    target["asset_id"] != "HiddenProp"
    for frame in report["motion_frames"]
    for target in frame["targets"]
)
root_x = [
    next(
        point["x"]
        for point in frame["points"]
        if point["label"].lower().endswith("root_jnt")
    )
    for frame in actor_frames
]
assert root_x[0] < root_x[1] < root_x[2]

patterns = (
    (color_frames, color_output_name),
    (depth_frames, depth_output_name),
    (motion_frames, motion_output_name),
)
for folder, name in patterns:
    for index in range(3):
        assert (folder / f"{name}.{index:06d}.png").is_file()

from PIL import Image

motion_image = Image.open(
    motion_frames / f"{motion_output_name}.000001.png"
).convert("RGB")
colors = set(motion_image.getdata())
assert (0, 0, 0) in colors
assert any(color != (0, 0, 0) for color in colors)

for folder, name in patterns:
    frame_pattern = folder / f"{name}.%06d.png"
    output_path = run_folder / f"{name}.mp4"
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
    "HMB live Color + Depth + Motion Guide Maya smoke: PASS "
    f"({run_folder}, 3 synchronized frames each)"
)
