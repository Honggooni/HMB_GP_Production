"""Bounded real Maya/FFmpeg palette verification on disposable .ma/.mb scenes.

This creates two tiny animated meshes in a private workspace directory, renders
Original/Mask/Depth/Motion Guide, and keeps the artifacts for visual review.
The optional --mixed-pattern mode adds a Sky Grid backdrop to exercise the
production world-projection path alongside the two new solid markers.
No existing user scene or provider API is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


BUILD_SCENE = """
import os, sys
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
cmds.file(new=True, force=True)
cmds.currentUnit(time='film')
cmds.playbackOptions(minTime=1, maxTime=2, animationStartTime=1, animationEndTime=2)
for name, x, z in [('ActorCyan', -1.2, 0.0), ('GhostLavender', 1.2, -0.5)]:
    mesh = cmds.polyCube(name=name+'Mesh', width=1.6, height=1.6, depth=1.6)[0]
    root = cmds.group(mesh, name=name)
    cmds.setAttr(root+'.translateX', x)
    cmds.setAttr(root+'.translateZ', z)
    cmds.setKeyframe(root, attribute='translateY', time=1, value=0.0)
    cmds.setKeyframe(root, attribute='translateY', time=2, value=0.25)
if sys.argv[2] == '1':
    mesh = cmds.polyPlane(name='SkyGridMesh', width=12.0, height=8.0,
                         subdivisionsX=2, subdivisionsY=2, axis=(0.0, 0.0, 1.0))[0]
    root = cmds.group(mesh, name='PatternSkyGrid')
    cmds.setAttr(root+'.translateZ', -3.0)
camera, shape = cmds.camera(name='PaletteCamera', focalLength=35)
camera = cmds.rename(camera, 'PaletteCamera')
shape = cmds.listRelatives(camera, shapes=True, fullPath=True)[0]
cmds.setAttr(camera+'.translateZ', 10.0)
cmds.setAttr(shape+'.renderable', True)
cmds.currentTime(1)
for extension, file_type in [('ma', 'mayaAscii'), ('mb', 'mayaBinary')]:
    target = os.path.join(sys.argv[1], 'PaletteFixture.'+extension)
    cmds.file(rename=target)
    cmds.file(save=True, type=file_type, force=True)
maya.standalone.uninitialize()
"""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(command, log_path, **kwargs):
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        completed = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT,
            creationflags=picker._creation_flags(), timeout=300, check=False, **kwargs,
        )
    assert completed.returncode == 0, "Subprocess exited {}: {}\n{}".format(
        completed.returncode, command[0],
        log_path.read_text(encoding="utf-8", errors="replace")[-10000:],
    )


def run_job(mayabatch, scene, folder, *, original=False, mixed_pattern=False):
    folder.mkdir()
    job = {
        "operation": "render", "scene_path": str(scene),
        "result_path": str(folder / "result.json"),
        "progress_path": str(folder / "progress.json"),
        "frames_folder": str(folder / "frames"),
        "sidecar_path": str(folder / "color.hmb.json"),
        "output_name": "original" if original else "mask",
        "camera": "|PaletteCamera", "start_frame": 1, "end_frame": 2,
        "fps": 24, "width": 256, "height": 160,
        "expected_maya_major": picker._maya_display_version(mayabatch),
        "maya_evaluation_mode": "serial",
        "apply_marker_shaders": not original,
        "force_high_quality_viewport": True,
        "viewport_quality_profile": picker.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
        "require_full_smooth_geometry": True,
        "marker_catalog_path": str(picker.MARKER_CATALOG_PATH),
        "marker_catalog_version": picker.MARKER_CATALOG["version"],
        "bindings": [
            {"color": "Cyan", "asset_id": "ActorCyan", "subject_root": "|ActorCyan", "full_dag_path": "|ActorCyan", "enabled": True},
            {"color": "Lavender", "asset_id": "GhostLavender", "subject_root": "|GhostLavender", "full_dag_path": "|GhostLavender", "enabled": True},
        ] if not original else [],
        "hidden_paths": [],
        "character_outline_mode": "native_lambert",
        "generate_depth_playblast": not original,
        "generate_motion_guide": not original,
    }
    if original:
        job.update({
            "apply_original_lambert_override": True,
            "original_material_override_profile": picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
        })
    else:
        if mixed_pattern:
            job["bindings"].append({
                "color": "Sky Grid", "asset_id": "PatternSkyGrid",
                "subject_root": "|PatternSkyGrid", "full_dag_path": "|PatternSkyGrid", "enabled": True,
            })
            job.update({
                "world_space_patterns": True,
                "screen_space_patterns": False,
                "world_pattern_profile": picker.MAYA_WORLD_PATTERN_PROFILE,
                "world_pattern_cell_units": picker.WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS,
                "world_pattern_density_multiplier": picker.WORLD_PATTERN_DENSITY_MULTIPLIER,
            })
        for kind in ("depth", "motion_guide"):
            job.update({
                kind + "_frames_folder": str(folder / kind),
                kind + "_sidecar_path": str(folder / (kind + ".hmb.json")),
                kind + "_output_name": kind,
            })
        job["depth_profile"] = picker.DEPTH_PLAYBLAST_PROFILE
        job["motion_guide_profile"] = picker.MOTION_GUIDE_PROFILE
    job_path = folder / "job.json"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    before = digest(scene)
    execute(
        [str(mayabatch), "-command", picker._maya_runner_command()],
        folder / "mayabatch.log", cwd=str(folder),
        env=picker._maya_subprocess_environment(job_path),
    )
    assert digest(scene) == before, "Worker modified a saved source scene"
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert result["ok"] is True, result.get("error")
    assert result["frame_count"] == 2
    for kind in ("color",) if original else ("color", "depth", "motion_guide"):
        assert result["artifacts"][kind]["ok"] is True, result["artifacts"][kind]
    return job, result


def encode_and_check(ffmpeg, folder, name):
    for index in (0, 1):
        image_path = folder / (name + ".{:06d}.png".format(index))
        assert image_path.is_file(), str(image_path)
        with Image.open(image_path) as image:
            assert image.size == (256, 160)
            assert max(ImageStat.Stat(image.convert("RGB")).stddev) > 5
    video = folder.parent / (name + ".mp4")
    execute([
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", "24", "-i", str(folder / (name + ".%06d.png")),
        "-frames:v", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an", str(video),
    ], folder.parent / (name + ".encode.log"))
    assert video.is_file() and video.stat().st_size > 1000
    return str(video)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", nargs="+", choices=("ma", "mb"), default=["ma", "mb"])
    parser.add_argument("--mixed-pattern", action="store_true", help="Add Sky Grid and use native Maya world patterns.")
    args = parser.parse_args()
    mayabatch = picker._find_mayabatch()
    assert mayabatch is not None, "Installed Maya mayabatch was not found"
    mayapy = mayabatch.with_name("mayapy.exe")
    ffmpeg = picker._find_ffmpeg(mayabatch)
    assert mayapy.is_file() and ffmpeg is not None
    assert picker.MARKER_CATALOG["version"] == 5
    output = Path(tempfile.mkdtemp(prefix="hmb-palette-maya-", dir=ROOT / ".tmp"))
    execute([str(mayapy), "-c", BUILD_SCENE, str(output), "1" if args.mixed_pattern else "0"], output / "build.log")
    report = {"ok": True, "output_folder": str(output), "maya_binary": str(mayabatch), "mixed_pattern": args.mixed_pattern, "scenes": []}
    for extension in args.formats:
        scene = output / ("PaletteFixture." + extension)
        before = digest(scene)
        original_job, original = run_job(mayabatch, scene, output / (extension + "_original"), original=True)
        mask_job, mask = run_job(mayabatch, scene, output / (extension + "_render"), mixed_pattern=args.mixed_pattern)
        sidecar = json.loads(Path(mask_job["sidecar_path"]).read_text(encoding="utf-8"))
        markers = {row["color"]: row for row in sidecar["markers"]}
        assert set(markers) == ({"Cyan", "Lavender", "Sky Grid"} if args.mixed_pattern else {"Cyan", "Lavender"})
        assert markers["Cyan"]["shader_model"] == "lambert"
        assert markers["Lavender"]["shader_model"] == "surfaceShader"
        assert markers["Lavender"]["shading_profile"]["palette_rgb"] == [184 / 255, 166 / 255, 217 / 255]
        world_report = {}
        if args.mixed_pattern:
            assert markers["Sky Grid"]["shader_model"] == "surfaceShader"
            assert markers["Sky Grid"]["visual_profile"] == picker.MAYA_WORLD_PATTERN_PROFILE
            assert markers["Sky Grid"]["shading_profile"]["projection_type"] == "TriPlanar"
            assert sidecar["world_pattern_profile"] == picker.MAYA_WORLD_PATTERN_PROFILE
            assert sidecar.get("screen_space_postprocess_pending") is not True
            world_report = sidecar["world_pattern_report"]
            assert world_report["pattern_binding_count"] == 1
            assert world_report["projection_node_count"] == 1
            assert world_report["coordinate_space"] == "background_root"
            assert world_report["camera_anchored"] is False
            assert world_report["uv_dependent"] is False
            projection = world_report["patterns"][0]
            assert projection["subject_root"] == "|PatternSkyGrid"
            assert projection["pattern"] == "sky_grid"
            assert projection["projection_type"] == "TriPlanar"
            assert projection["projection_axis"] == "XYZ"
        with Image.open(Path(mask_job["frames_folder"]) / "mask.000000.png") as image:
            pixels = list(image.convert("RGB").get_flattened_data())
            cyan_count = sum(r < 60 and g > 70 and b > 70 and abs(g - b) < 30 for r, g, b in pixels)
            lavender_count = sum(b - r > 8 and r - g > 5 and g > 100 for r, g, b in pixels)
            assert cyan_count > 100, "Actor Cyan disappeared or lost its hue"
            assert lavender_count > 100, "Ghost Lavender disappeared or lost its hue"
            left = [pixel for index, pixel in enumerate(pixels) if index % image.width < image.width // 2]
            right = [pixel for index, pixel in enumerate(pixels) if index % image.width >= image.width // 2]
            assert sum(r < 60 and g > 70 and b > 70 and abs(g - b) < 30 for r, g, b in left) > 100
            assert sum(b - r > 8 and r - g > 5 and g > 100 for r, g, b in right) > 100
            actor_saturated_cyan_count = sum(pixel == (0, 255, 255) for pixel in pixels)
            sky_grid_filler_count = sum(
                max(abs(channel - expected) for channel, expected in zip(pixel, (67, 155, 231))) <= 2
                for pixel in pixels
            )
            if args.mixed_pattern:
                # The unchanged lit Actor profile saturates this fixture's
                # Cyan center to the legacy Sky Grid ID. World projection
                # must nevertheless retain the solid Actor silhouette.
                assert actor_saturated_cyan_count > 100, "Actor Cyan was replaced by the Sky Grid appearance"
                assert sky_grid_filler_count > 100, "The Sky Grid backdrop was not rendered"
        videos = {
            "original": encode_and_check(ffmpeg, Path(original_job["frames_folder"]), "original"),
            "mask": encode_and_check(ffmpeg, Path(mask_job["frames_folder"]), "mask"),
            "depth": encode_and_check(ffmpeg, Path(mask_job["depth_frames_folder"]), "depth"),
            "motion_guide": encode_and_check(ffmpeg, Path(mask_job["motion_guide_frames_folder"]), "motion_guide"),
        }
        assert digest(scene) == before
        record = {
            "scene_path": str(scene), "source_sha256": before, "source_unchanged": True,
            "frames_per_output": 2, "cyan_pixel_count": cyan_count,
            "lavender_pixel_count": lavender_count,
            "actor_saturated_cyan_pixel_count": actor_saturated_cyan_count,
            "sky_grid_filler_pixel_count": sky_grid_filler_count,
            "world_pattern_report": world_report, "videos": videos,
        }
        report["scenes"].append(record)
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
