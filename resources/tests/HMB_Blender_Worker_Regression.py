"""Small real-Blender regression for the Picker's private .blend worker."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "resources" / "blender" / "HMB_Blender_Background_Preview.py"
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def blender_binary():
    override = os.environ.get("HMB_BLENDER_EXE", "")
    return Path(override) if override else DEFAULT_BLENDER


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BlenderWorkerRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = blender_binary()
        if not cls.binary.is_file():
            raise unittest.SkipTest("Installed Blender 5.2 executable was not found.")

    def _make_scene(self, directory, unsafe_driver=False):
        scene = directory / "animated.blend"
        expression = (
            "import bpy;"
            "s=bpy.context.scene;"
            "s.frame_start=1;s.frame_end=3;s.render.fps=24;"
            "o=bpy.data.objects['Cube'];"
            "o.location.x=-0.3;o.location.z=0;o.keyframe_insert(data_path='location',frame=1);"
            "o.location.x=0.3;o.location.z=2;o.keyframe_insert(data_path='location',frame=3);"
            "a=o.copy();a.data=o.data.copy();a.animation_data_clear();a.name='PatternSky';s.collection.objects.link(a);a.location.x=-1.5;"
            "b=o.copy();b.data=o.data.copy();b.animation_data_clear();b.name='PatternFloor';s.collection.objects.link(b);b.location.x=1.5;"
            "c=o.copy();c.data=o.data.copy();c.animation_data_clear();c.name='PatternPosition';s.collection.objects.link(c);c.location.y=1.5;"
            "d=o.copy();d.data=o.data.copy();d.animation_data_clear();d.name='HiddenRenderCube';"
            "hc=bpy.data.collections.new('HiddenRender');hc.hide_render=True;s.collection.children.link(hc);hc.objects.link(d);"
            + ("o.driver_add('scale',0).driver.expression='sin(frame)';" if unsafe_driver else "") +
            "s.camera=bpy.data.objects['Camera'];"
            "bpy.ops.wm.save_as_mainfile(filepath=" + repr(str(scene)) + ")"
        )
        command = [
            str(self.binary), "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "5", "--python-expr", expression,
        ]
        run = subprocess.run(command, capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue(scene.is_file())
        return scene

    def _run_job(self, directory, scene, operation, **fields):
        root = directory / operation
        root.mkdir()
        job = {
            "operation": operation,
            "scene_path": str(scene),
            "result_path": str(root / "result.json"),
            "progress_path": str(root / "progress.json"),
            "frames_folder": str(root / "frames"),
            "sidecar_path": str(root / "sidecar.json"),
            "output_name": "preview",
            "camera": "|Camera",
            "start_frame": 1,
            "end_frame": 2,
            "width": 96,
            "height": 64,
            "fps": 24,
        }
        job.update(fields)
        job_path = root / "job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        before = digest(scene)
        command = [
            str(self.binary), "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "5", str(scene), "--python", str(WORKER),
            "--", str(job_path),
        ]
        run = subprocess.run(command, capture_output=True, text=True, timeout=180)
        self.assertEqual(digest(scene), before, "Worker modified the saved Blender scene")
        self.assertTrue(Path(job["result_path"]).is_file(), run.stdout + run.stderr)
        return job, json.loads(Path(job["result_path"]).read_text(encoding="utf-8")), run

    def test_scan_render_snapshot_and_auxiliary_profiles(self):
        with tempfile.TemporaryDirectory(prefix="hmb-blender-worker-") as temporary:
            directory = Path(temporary)
            scene = self._make_scene(directory)
            job, scan, process = self._run_job(directory, scene, "scan")
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(scan["ok"])
            self.assertEqual(scan["fps"], 24)
            self.assertEqual(scan["selected_camera"], "|Camera")
            self.assertTrue(scan["outliner_nodes"])
            root = next(item for item in scan["outliner_nodes"] if item["name"] == "Cube")
            self.assertTrue(root["maya_uuid"].startswith("blender-"))
            self.assertEqual(root["full_path"], "|Cube")
            hidden = next(item for item in scan["outliner_nodes"] if item["name"] == "HiddenRenderCube")
            self.assertFalse(hidden["scene_visible"])

            markers = [{"group_name": "Cube", "full_dag_path": "|Cube", "asset_id": "Cube", "color": "Red", "enabled": True}]
            fields = {
                "apply_marker_shaders": True,
                "bindings": markers,
                "generate_depth_playblast": True,
                "depth_frames_folder": str(directory / "render" / "depth"),
                "depth_sidecar_path": str(directory / "render" / "depth.json"),
                "depth_output_name": "depth",
                "generate_motion_guide": True,
                "motion_guide_frames_folder": str(directory / "render" / "motion"),
                "motion_guide_sidecar_path": str(directory / "render" / "motion.json"),
                "motion_guide_output_name": "motion",
            }
            job, render, process = self._run_job(directory, scene, "render", **fields)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(render["ok"], render.get("error"))
            self.assertEqual(render["frame_count"], 2)
            self.assertTrue(render["artifacts"]["color"]["ok"])
            self.assertTrue(render["artifacts"]["depth"]["ok"])
            self.assertTrue(render["artifacts"]["motion_guide"]["ok"])
            self.assertEqual(render["depth_profile"], "hmb_blender_camera_depth_v1")
            self.assertEqual(render["motion_guide_profile"], "hmb_blender_motion_guide_v1")
            self.assertTrue(render["motion_guide_report"]["motion_detected"])
            self.assertEqual(render["depth_range_report"]["sampled_frame_count"], 2)
            for folder, name in (("frames", "preview"), ("depth", "depth"), ("motion", "motion")):
                self.assertTrue((directory / "render" / folder / (name + ".000000.png")).is_file())
                self.assertTrue((directory / "render" / folder / (name + ".000001.png")).is_file())

            job, original, process = self._run_job(directory, scene, "snapshot", apply_marker_shaders=False, start_frame=1, end_frame=1)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(original["ok"], original.get("error"))
            self.assertEqual(original["frame_count"], 1)
            self.assertEqual(original["render_profile"], "hmb_blender_workbench_midgray_v1")
            with Image.open(directory / "snapshot" / "frames" / "preview.000000.png") as image:
                self.assertGreater(ImageStat.Stat(image.convert("L")).stddev[0], 10)

    def test_all_pattern_markers_render_without_changing_source(self):
        with tempfile.TemporaryDirectory(prefix="hmb-blender-worker-") as temporary:
            directory = Path(temporary)
            scene = self._make_scene(directory)
            job, result, process = self._run_job(
                directory, scene, "render",
                apply_marker_shaders=True,
                width=512, height=320,
                start_frame=1, end_frame=1,
                bindings=[
                    {"group_name": "Cube", "full_dag_path": "|Cube", "color": "Direction Checker", "enabled": True},
                    {"group_name": "PatternSky", "full_dag_path": "|PatternSky", "color": "Sky Grid", "enabled": True},
                    {"group_name": "PatternFloor", "full_dag_path": "|PatternFloor", "color": "Floor Grid", "enabled": True},
                    {"group_name": "PatternPosition", "full_dag_path": "|PatternPosition", "color": "Position Pattern", "enabled": True},
                ],
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(result["ok"], result.get("error"))
            self.assertEqual(result["render_profile"], "hmb_blender_eevee_world_patterns_v1")
            pattern_frame = Path(job["frames_folder"]) / "preview.000000.png"
            self.assertTrue(pattern_frame.is_file())
            retained = os.environ.get("HMB_BLEND_KEEP_PATTERN_QA", "")
            if retained:
                destination = Path(retained)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pattern_frame, destination)
            with Image.open(pattern_frame) as image:
                rgb = image.convert("RGB")
                self.assertGreater(len(rgb.getcolors(maxcolors=100000) or []), 20)
                pixels = list(rgb.get_flattened_data())
                self.assertGreater(sum(r > 180 and b > 180 and g < 100 for r, g, b in pixels), 100)
                self.assertGreater(sum(r < 100 and g > 180 and b > 180 for r, g, b in pixels), 100)
                self.assertGreater(sum(r > 180 and g > 110 and b < 100 for r, g, b in pixels), 100)
                self.assertGreater(sum(r < 170 and g > 110 and b < 170 for r, g, b in pixels), 100)
            self.assertEqual(
                json.loads(Path(job["sidecar_path"]).read_text(encoding="utf-8"))["assignment_mode"],
                "blender_object_world_pattern_marker",
            )

    def test_extended_actor_and_ghost_render_all_auxiliary_outputs(self):
        with tempfile.TemporaryDirectory(prefix="hmb-blender-palette-") as temporary:
            directory = Path(temporary)
            scene = self._make_scene(directory)
            job, result, process = self._run_job(
                directory, scene, "render", width=384, height=240,
                apply_marker_shaders=True,
                marker_catalog_path=str(ROOT / "resources" / "picker" / "HMB_Marker_Catalog.json"),
                bindings=[
                    {"full_dag_path": "|Cube", "color": "Cyan", "enabled": True},
                    {"full_dag_path": "|PatternSky", "color": "Lavender", "enabled": True},
                ],
                generate_depth_playblast=True,
                depth_frames_folder=str(directory / "render" / "depth"),
                depth_sidecar_path=str(directory / "render" / "depth.json"),
                depth_output_name="depth",
                generate_motion_guide=True,
                motion_guide_frames_folder=str(directory / "render" / "motion"),
                motion_guide_sidecar_path=str(directory / "render" / "motion.json"),
                motion_guide_output_name="motion",
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(result["ok"], result.get("error"))
            self.assertEqual(result["render_profile"], "hmb_blender_workbench_flat_markers_v1")
            for kind in ("color", "depth", "motion_guide"):
                self.assertTrue(result["artifacts"][kind]["ok"], result["artifacts"][kind])
            sidecar = json.loads(Path(job["sidecar_path"]).read_text(encoding="utf-8"))
            markers = {row["color"]: row for row in sidecar["markers"]}
            self.assertEqual(markers["Cyan"]["rgb"], [0.0, 217 / 255, 217 / 255])
            self.assertEqual(markers["Lavender"]["rgb"], [184 / 255, 166 / 255, 217 / 255])
            self.assertEqual(sidecar["marker_catalog_version"], 5)
            for folder, name in (("frames", "preview"), ("depth", "depth"), ("motion", "motion")):
                for index in (0, 1):
                    frame = directory / "render" / folder / (name + ".{:06d}.png".format(index))
                    self.assertTrue(frame.is_file(), str(frame))
                    with Image.open(frame) as image:
                        self.assertEqual(image.size, (384, 240))
                        self.assertGreater(max(ImageStat.Stat(image.convert("RGB")).stddev), 5)
            retained = os.environ.get("HMB_BLEND_KEEP_PALETTE_QA", "")
            if retained:
                destination = Path(retained)
                destination.mkdir(parents=True, exist_ok=True)
                shutil.copytree(directory / "render", destination / "render", dirs_exist_ok=True)
            with Image.open(directory / "render" / "frames" / "preview.000000.png") as image:
                pixels = list(image.convert("RGB").get_flattened_data())
                self.assertGreater(sum(g - r > 35 and b - r > 35 and abs(g - b) < 15 for r, g, b in pixels), 100)
                # Workbench keeps the scene's authored display transform; AgX
                # compresses this pastel's hue while the sidecar stays exact.
                self.assertGreater(sum(b - r > 2 and r - g > 2 and g > 100 for r, g, b in pixels), 100)
            _, original, process = self._run_job(
                directory, scene, "snapshot", width=384, height=240,
                start_frame=1, end_frame=2, apply_marker_shaders=False,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(original["ok"], original.get("error"))
            self.assertEqual(original["frame_count"], 2)
            self.assertEqual(original["render_profile"], "hmb_blender_workbench_midgray_v1")
            for index in (0, 1):
                frame = directory / "snapshot" / "frames" / ("preview.{:06d}.png".format(index))
                with Image.open(frame) as image:
                    self.assertGreater(ImageStat.Stat(image.convert("L")).stddev[0], 10)
            if retained:
                shutil.copytree(directory / "snapshot", destination / "snapshot", dirs_exist_ok=True)

    def test_extended_solid_colors_survive_pattern_render_path(self):
        with tempfile.TemporaryDirectory(prefix="hmb-blender-palette-pattern-") as temporary:
            directory = Path(temporary)
            scene = self._make_scene(directory)
            job, result, process = self._run_job(
                directory, scene, "render", width=320, height=200,
                start_frame=1, end_frame=1, apply_marker_shaders=True,
                bindings=[
                    {"full_dag_path": "|Cube", "color": "Cyan", "enabled": True},
                    {"full_dag_path": "|PatternSky", "color": "Lavender", "enabled": True},
                    {"full_dag_path": "|PatternFloor", "color": "Sky Grid", "enabled": True},
                ],
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(result["ok"], result.get("error"))
            self.assertEqual(result["render_profile"], "hmb_blender_eevee_world_patterns_v1")
            with Image.open(Path(job["frames_folder"]) / "preview.000000.png") as image:
                pixels = list(image.convert("RGB").get_flattened_data())
                # Raw emission keeps the new solids distinct from the pure
                # cyan Pattern ID and from one another in the mixed pass.
                self.assertGreater(sum(max(abs(channel - expected) for channel, expected in zip(pixel, (0, 217, 217))) <= 2 for pixel in pixels), 100)
                self.assertGreater(sum(max(abs(channel - expected) for channel, expected in zip(pixel, (184, 166, 217))) <= 2 for pixel in pixels), 100)

    def test_scripted_driver_is_reported_and_render_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="hmb-blender-driver-") as temporary:
            directory = Path(temporary)
            scene = self._make_scene(directory, unsafe_driver=True)
            _, scan, process = self._run_job(directory, scene, "scan")
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertGreater(scan["script_node_report"]["scripted_driver_count"], 0)
            _, render, process = self._run_job(
                directory, scene, "render", apply_marker_shaders=False,
                start_frame=1, end_frame=1,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(render["ok"])
            self.assertIn("scripted driver", render["error"])

    def test_user_scissors_sample_remains_unchanged(self):
        sample = Path(os.environ.get(
            "HMB_BLEND_TEST_SCENE",
            r"C:\Users\jh_ahn\Documents\Codex\2026-09-15\qm\outputs\scissors.blend",
        ))
        if not sample.is_file():
            self.skipTest("User's read-only scissors.blend sample is not available.")
        with tempfile.TemporaryDirectory(prefix="hmb-blender-sample-") as temporary:
            directory = Path(temporary)
            before = digest(sample)
            _, scan, process = self._run_job(directory, sample, "scan")
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(scan["ok"])
            self.assertEqual(scan["selected_camera"], "|Product_camera")
            self.assertEqual(scan["fps"], 24)
            self.assertEqual(scan["end_frame"], 250)
            self.assertIn("|Scissors_ROOT", {item["full_path"] for item in scan["outliner_nodes"]})

            _, original, process = self._run_job(
                directory, sample, "snapshot",
                camera="|Product_camera", width=160, height=96,
                start_frame=1, end_frame=1,
                apply_marker_shaders=False,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(original["ok"])
            self.assertEqual(original["frame_count"], 1)
            retained = os.environ.get("HMB_BLEND_KEEP_QA", "")
            if retained:
                destination = Path(retained)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(directory / "snapshot" / "frames" / "preview.000000.png", destination)
            with Image.open(directory / "snapshot" / "frames" / "preview.000000.png") as image:
                self.assertGreater(
                    ImageStat.Stat(image.convert("L")).stddev[0], 10,
                    "Original Blender preview must show neutral geometry against a distinct background",
                )

            marker = [{
                "group_name": "Scissors_ROOT", "full_dag_path": "|Scissors_ROOT",
                "asset_id": "Scissors_ROOT", "color": "Red", "enabled": True,
            }]
            _, render, process = self._run_job(
                directory, sample, "render",
                camera="|Product_camera", width=160, height=96,
                start_frame=1, end_frame=1,
                apply_marker_shaders=True, bindings=marker,
                generate_depth_playblast=True,
                depth_frames_folder=str(directory / "render" / "depth"),
                depth_sidecar_path=str(directory / "render" / "depth.json"),
                depth_output_name="depth",
                generate_motion_guide=True,
                motion_guide_frames_folder=str(directory / "render" / "motion"),
                motion_guide_sidecar_path=str(directory / "render" / "motion.json"),
                motion_guide_output_name="motion",
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(render["ok"], render.get("error"))
            self.assertTrue(render["artifacts"]["depth"]["ok"])
            self.assertTrue(render["artifacts"]["motion_guide"]["ok"])
            self.assertEqual(digest(sample), before)


if __name__ == "__main__":
    unittest.main()
