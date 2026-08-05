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
if mayabatch is None:
    print("HMB no-assignment auxiliary live smoke: SKIP (Maya is unavailable)")
    raise SystemExit(0)

mayapy = Path(mayabatch).with_name("mayapy.exe")
builder = ROOT / ".tmp" / "build_motion_guide_smoke_scene.py"
if not mayapy.is_file() or not builder.is_file():
    print("HMB no-assignment auxiliary live smoke: SKIP (fixture builder is unavailable)")
    raise SystemExit(0)

run_folder = (
    ROOT
    / ".tmp"
    / "auxiliary_no_assignment_live_smoke"
    / time.strftime("%Y%m%d_%H%M%S")
)
run_folder.mkdir(parents=True, exist_ok=False)
scene_path = run_folder / "HMB_Auxiliary_No_Assignment.ma"
build_log = run_folder / "build.log"
with build_log.open("w", encoding="utf-8", errors="replace") as handle:
    built = subprocess.run(
        [str(mayapy), str(builder), str(scene_path)],
        stdout=handle,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
assert built.returncode == 0, build_log.read_text(encoding="utf-8", errors="replace")[-8000:]

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

job = {
    "operation": "render",
    "scene_path": str(scene_path),
    "output_folder": str(run_folder),
    "output_name": "No_Assignment_Color",
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
    "bindings": [],
    "hidden_paths": ["|HiddenProp_G"],
    "generate_depth_playblast": True,
    "depth_video_slot": 2,
    "depth_output_name": "No_Assignment_Depth",
    "depth_frames_folder": str(depth_frames),
    "depth_sidecar_path": str(depth_sidecar_path),
    "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
    "generate_motion_guide": True,
    "motion_guide_video_slot": 3,
    "motion_guide_output_name": "No_Assignment_Motion",
    "motion_guide_frames_folder": str(motion_frames),
    "motion_guide_sidecar_path": str(motion_sidecar_path),
    "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
}
job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

scene_hash_before = sha256(scene_path)
environment = picker._maya_subprocess_environment(job_path)
command = [
    str(mayabatch),
    "-command",
    picker._maya_runner_command(),
]
with log_path.open("w", encoding="utf-8", errors="replace") as handle:
    completed = subprocess.run(
        command,
        stdout=handle,
        stderr=subprocess.STDOUT,
        cwd=str(job_path.parent),
        env=environment,
        timeout=900,
        check=False,
    )
assert completed.returncode == 0, log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
assert sha256(scene_path) == scene_hash_before

result = json.loads(result_path.read_text(encoding="utf-8"))
assert result["ok"] is True
assert result["frame_count"] == 3
assert result["artifacts"]["color"]["ok"] is True
assert result["artifacts"]["depth"]["ok"] is True
assert result["artifacts"]["motion_guide"]["ok"] is True

color_sidecar = json.loads(color_sidecar_path.read_text(encoding="utf-8"))
depth_sidecar = json.loads(depth_sidecar_path.read_text(encoding="utf-8"))
motion_sidecar = json.loads(motion_sidecar_path.read_text(encoding="utf-8"))
assert color_sidecar["markers"] == []
assert depth_sidecar["depth_range_report"]["renderable_shape_count"] == 1
motion_report = motion_sidecar["motion_guide_report"]
assert motion_report["target_count"] >= 1
assert all(target["asset_id"] != "HiddenProp" for target in motion_report["targets"])
assert motion_report["hidden_paths"] == ["|HiddenProp_G"]

from PIL import Image


color_image = Image.open(color_frames / "No_Assignment_Color.000000.png").convert("RGB")
assert set(color_image.getdata()) == {(0, 0, 0)}
depth_image = Image.open(depth_frames / "No_Assignment_Depth.000000.png").convert("RGB")
assert any(pixel != (0, 0, 0) for pixel in depth_image.getdata())

print(
    "HMB live no-assignment Color + Depth + Motion smoke: PASS "
    f"({run_folder}, 3 synchronized frames each)"
)
