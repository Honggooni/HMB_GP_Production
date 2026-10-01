"""Read-only smoke of a supplied .blend through the private Picker worker.

Run with a scene path; outputs are kept in a unique workspace .tmp folder so
the original scene and its neighboring files are never changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "resources" / "blender" / "HMB_Blender_Background_Preview.py"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_job(scene: Path, output: Path, operation: str, **fields: object) -> dict:
    job_folder = output / operation
    job_folder.mkdir(parents=True, exist_ok=False)
    job = {
        "operation": operation,
        "scene_path": str(scene),
        "result_path": str(job_folder / "result.json"),
        "progress_path": str(job_folder / "progress.json"),
        "frames_folder": str(job_folder / "frames"),
        "sidecar_path": str(job_folder / "sidecar.json"),
        "output_name": operation,
        "start_frame": 1,
        "end_frame": 3,
        "width": 320,
        "height": 180,
    }
    job.update(fields)
    job_path = job_folder / "job.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    command = [
        str(BLENDER), "--background", "--factory-startup", "--disable-autoexec",
        "--python-exit-code", "5", str(scene), "--python", str(WORKER),
        "--", str(job_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=240)
    result_path = Path(job["result_path"])
    if not result_path.is_file():
        raise AssertionError(f"{operation}: no result JSON: {completed.stdout[-3000:]} {completed.stderr[-3000:]}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if completed.returncode != 0 or result.get("ok") is not True:
        raise AssertionError(f"{operation}: exit={completed.returncode}, error={result.get('error')}, stdout={completed.stdout[-3000:]}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene", type=Path)
    args = parser.parse_args()
    scene = args.scene.resolve(strict=True)
    if scene.suffix.casefold() != ".blend":
        raise SystemExit("A .blend scene is required")
    if not BLENDER.is_file() or not WORKER.is_file():
        raise SystemExit("Blender or the HMB Blender worker is missing")
    before = sha256(scene)
    output = Path(tempfile.mkdtemp(prefix="hmb-blender-sample-", dir=ROOT / ".tmp"))
    scan = run_job(scene, output, "scan")
    camera = scan.get("selected_camera") or next(
        (item.get("full_path") for item in scan.get("cameras", [])), ""
    )
    if not camera:
        raise AssertionError("The supplied scene has no usable camera")
    roots = [item for item in scan.get("outliner_nodes", []) if not item.get("parent_path")]
    color_root = next((item for item in roots if item.get("name") == "Scissors_ROOT"), roots[0])
    binding = {"group_name": color_root["name"], "full_dag_path": color_root["full_path"],
               "maya_uuid": color_root.get("maya_uuid", ""), "color": "Red", "enabled": True}
    common = {"camera": camera, "fps": scan["fps"]}
    original = run_job(scene, output, "snapshot", apply_marker_shaders=False,
                       start_frame=1, end_frame=1, **common)
    original_frame = output / "snapshot" / "frames" / "snapshot.000000.png"
    with Image.open(original_frame) as original_image:
        original_contrast = max(ImageStat.Stat(original_image.convert("RGB")).stddev)
    if original_contrast < 5.0:
        raise AssertionError(
            f"Original preview is visually flat (RGB stddev {original_contrast:.2f})"
        )
    render_dir = output / "render"
    render = run_job(
        scene, output, "render", apply_marker_shaders=True, bindings=[binding],
        generate_depth_playblast=True,
        depth_frames_folder=str(render_dir / "depth"),
        depth_sidecar_path=str(render_dir / "depth.json"),
        depth_output_name="depth",
        generate_motion_guide=True,
        motion_guide_frames_folder=str(render_dir / "motion"),
        motion_guide_sidecar_path=str(render_dir / "motion.json"),
        motion_guide_output_name="motion",
        **common,
    )
    if sha256(scene) != before:
        raise AssertionError("Smoke run modified the supplied scene")
    artifacts = render.get("artifacts") or {}
    for kind in ("color", "depth", "motion_guide"):
        if not (artifacts.get(kind) or {}).get("ok"):
            raise AssertionError(f"{kind} output missing: {artifacts.get(kind)}")
    for folder, name in (
        (output / "snapshot" / "frames", "snapshot"),
        (render_dir / "frames", "render"),
        (render_dir / "depth", "depth"),
        (render_dir / "motion", "motion"),
    ):
        if not (folder / f"{name}.000000.png").is_file():
            raise AssertionError(f"Expected frame missing: {folder / name}")
    print(json.dumps({
        "output_folder": str(output),
        "scene_sha256_unchanged": True,
        "camera": camera,
        "fps": scan["fps"],
        "outliner_nodes": len(scan.get("outliner_nodes", [])),
        "original_frames": original["frame_count"],
        "original_contrast_stddev": round(original_contrast, 2),
        "mask_frames": render["frame_count"],
        "depth_frames": render.get("depth_frame_count"),
        "motion_frames": render.get("motion_guide_frame_count"),
        "motion_detected": (render.get("motion_guide_report") or {}).get("motion_detected"),
        "depth_profile": render.get("depth_profile"),
        "motion_profile": render.get("motion_guide_profile"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
