# -*- coding: utf-8 -*-
"""Maya-free checks for temporary evaluation and isolated capture roles."""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "resources/maya/HMB_Maya_Background_Preview.py"
maya_package = types.ModuleType("maya")
maya_cmds = types.ModuleType("maya.cmds")
maya_package.cmds = maya_cmds
sys.modules.setdefault("maya", maya_package)
sys.modules.setdefault("maya.cmds", maya_cmds)
spec = importlib.util.spec_from_file_location("hmb_isolated_capture_runner", RUNNER_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class EvaluationCmds:
    def __init__(self, prior="parallel", *, fail_set=(), ignore_set=(), fail_read=False):
        self.mode = prior
        self.fail_set = set(fail_set)
        self.ignore_set = set(ignore_set)
        self.fail_read = fail_read
        self.set_calls = []

    def about(self, version=False):
        return "2027" if version else ""

    def evaluationManager(self, query=False, mode=None):
        if query:
            if self.fail_read:
                raise RuntimeError("synthetic evaluation query failure")
            # Actual Maya 2027 includes this non-mode status item even for
            # queries after set/scene load/restoration.
            return [self.mode, "Evaluation graph is ready."]
        self.set_calls.append(mode)
        if mode in self.fail_set:
            raise RuntimeError("synthetic evaluation set failure")
        if mode not in self.ignore_set:
            self.mode = mode


@contextlib.contextmanager
def mocked_capture(cmds, calls, *, open_mode=None, fail_role="", wrong_role="", bindings=True):
    def open_scene(job):
        assert cmds.mode == job.get("maya_evaluation_mode", "serial")
        calls.append("open")
        if fail_role == "open":
            raise RuntimeError("synthetic scene open failure")
        if open_mode:
            cmds.mode = open_mode
        return job["scene_path"]

    def snapshot(job, shapes):
        calls.append("authored_alpha")
        job["_authored_cutout_report"] = {"policy": "authored_alpha", "shape_count": len(shapes)}

    def assigned_scope(_bindings, _job):
        calls.append("assigned_scope")
        return ["|EyeOff"], {"policy": "assigned_and_eye_visible", "allowed_shape_path_count": 1}

    def auxiliary_scope(job, hidden_paths, scope):
        assert hidden_paths == ["|EyeOff"]
        assert scope["policy"] == "assigned_and_eye_visible"
        calls.append("auxiliary_scope")
        job["_auxiliary_render_scope_report"] = {"policy": "authored_visible_and_eye_visible"}

    def marker_shaders(_bindings, job):
        calls.append("marker_shaders")
        job["_marker_cutout_transparency"] = {"policy": "authored_alpha"}
        return []

    def capture(role, **kwargs):
        calls.append(role)
        assert cmds.mode == kwargs["job"].get("maya_evaluation_mode", "serial")
        assert kwargs["camera"] == "|shotCamera"
        assert (kwargs["width"], kwargs["height"]) == (1280, 720)
        assert kwargs["frame_values"] == [101.25, 102.25, 103.25, 103.75]
        if fail_role == role:
            raise RuntimeError("synthetic {0} failure".format(role))
        folder = Path(kwargs["frames_folder"])
        folder.mkdir()
        frames = kwargs["frame_values"]
        if wrong_role == role:
            frames = frames[:-1]
        paths, mapping = [], []
        for index, frame in enumerate(frames):
            path = folder / "{0}.{1:06d}.png".format(kwargs["output_name"], index)
            path.write_bytes(b"synthetic png; no Maya render")
            paths.append(str(path))
            mapping.append({"sequence_index": index, "maya_frame": frame, "file": path.name})
        if role == "color":
            return paths, mapping
        return paths, mapping, {"profile": role, "cutout_transparency": {"policy": "authored_alpha"}}

    replacements = {
        "cmds": cmds,
        "_open_scene_for_job": open_scene,
        "_scan_scene": lambda *_args: {"ok": True, "operation": "scan"},
        "_load_marker_catalog": lambda _job: {},
        "_read_job_bindings": lambda _job: [{"color": "Red", "subject_root": "|Hero"}] if bindings else [],
        "_resolve_camera": lambda _camera: "|shotCamera",
        "_character_outline_mode": lambda _job: "approved_outline",
        "_apply_assigned_render_scope": assigned_scope,
        "_authored_cutout_scope_shapes": lambda _job: ["|Hero|meshShape"],
        "_ensure_authored_cutout_snapshot": snapshot,
        "_apply_marker_shaders": marker_shaders,
        "_apply_full_smooth_viewport": lambda _job: (calls.append("quality") or {}, {"profile": "full_smooth"}),
        "_restore_full_smooth_viewport": lambda _state: calls.append("restore_quality") or [],
        "_set_viewport_render_options": lambda **_kwargs: {},
        "_prepare_unassigned_auxiliary_scope": auxiliary_scope,
        "_unassigned_motion_bindings": lambda **_kwargs: [{"subject_root": "|Fallback"}],
        "_render_frames": lambda **kwargs: capture("color", **kwargs),
        "_render_depth_pass": lambda **kwargs: capture("depth", **kwargs),
        "_render_motion_guide_pass": lambda **kwargs: capture("motion_guide", **kwargs),
        "_marker_payload": lambda _bindings, **_kwargs: [{"subject_root": "|Hero", "color": "Red"}] if _bindings else [],
        "_write_progress": lambda *_args, **_kwargs: None,
        "_emit_console": lambda *_args, **_kwargs: None,
    }
    originals = {name: getattr(runner, name) for name in replacements}
    for name, value in replacements.items():
        setattr(runner, name, value)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(runner, name, value)


def make_job(folder, **fields):
    scene = folder / "source.mb"
    scene.write_bytes(b"untouched authored Maya scene")
    job = {
        "operation": "render", "scene_path": str(scene),
        "result_path": str(folder / "result.json"),
        "sidecar_path": str(folder / "color.hmb.json"),
        "frames_folder": str(folder / "color"), "output_name": "shot_color",
        "camera": "|shotCamera", "width": 1280, "height": 720,
        "start_frame": 101.25, "end_frame": 103.75, "fps": 25.0,
        "apply_marker_shaders": True, "force_high_quality_viewport": True,
        "generate_depth_playblast": True, "generate_motion_guide": True,
        "depth_frames_folder": str(folder / "depth"), "depth_output_name": "shot_depth",
        "depth_sidecar_path": str(folder / "depth.hmb.json"),
        "motion_guide_frames_folder": str(folder / "motion"), "motion_guide_output_name": "shot_motion",
        "motion_guide_sidecar_path": str(folder / "motion.hmb.json"),
    }
    job.update(fields)
    path = folder / "job.json"
    runner._write_json(str(path), job)
    return path, job


# Query parsing tolerates Maya status messages but not missing/conflicting modes.
original_cmds = runner.cmds
try:
    for values, expected in (
        (["parallel", "Evaluation graph is ready."], "parallel"),
        (["Evaluation graph is ready.", "serial"], "serial"),
        (["off"], "off"),
        ("serial", "serial"),
        (["Evaluation graph is ready."], None),
        (["parallel", "serial", "Evaluation graph is ready."], None),
        (["serial", "serial"], None),
        ([], None),
    ):
        runner.cmds = types.SimpleNamespace(evaluationManager=lambda **_kwargs: values)
        if expected is not None:
            assert runner._query_capture_evaluation_mode() == expected
        else:
            try:
                runner._query_capture_evaluation_mode()
            except RuntimeError as exc:
                assert "ambiguous evaluation mode" in str(exc)
            else:
                raise AssertionError("Invalid evaluation query accepted: {0!r}".format(values))
finally:
    runner.cmds = original_cmds


# Every role captures the exact fractional timing and only its requested pass.
# Both serial and explicit DG retries restore each possible previous mode.
for prior in ("parallel", "serial", "off"):
    for selected in ("serial", "off"):
        for role in ("color", "depth", "motion_guide"):
            with tempfile.TemporaryDirectory(prefix="hmb_capture_isolation_") as directory:
                folder = Path(directory)
                path, job = make_job(folder, capture_pass=role, maya_evaluation_mode=selected)
                source_hash = hashlib.sha256(Path(job["scene_path"]).read_bytes()).hexdigest()
                primary_sidecar = Path(job["sidecar_path"])
                if role != "color":
                    primary_sidecar.write_bytes(b"existing validated Mask authority")
                cmds, calls = EvaluationCmds(prior), []
                with mocked_capture(cmds, calls, open_mode="parallel"):
                    result = runner.run(str(path))
                assert cmds.mode == prior
                assert result["ok"] and result["capture_pass"] == role
                assert result["frame_count"] == 4 and result["fps"] == 25.0
                assert [value for value in calls if value in ("color", "depth", "motion_guide")] == [role]
                assert calls.index("authored_alpha") < calls.index(role) < calls.index("restore_quality")
                assert result["artifacts"][role]["ok"] is True
                assert result["artifacts"]["color"]["requested"] is (role == "color")
                if role == "color":
                    assert calls.count("marker_shaders") == 1
                else:
                    assert "marker_shaders" not in calls
                    assert not Path(job["frames_folder"]).exists()
                    assert primary_sidecar.read_bytes() == b"existing validated Mask authority"
                    assert result["frames_folder"] == job[role + "_frames_folder"]
                    assert result["sidecar_path"] == job[role + "_sidecar_path"]
                    assert [item["maya_frame"] for item in result["frame_map"]] == [101.25, 102.25, 103.25, 103.75]
                payload = runner._read_json(result["sidecar_path"])
                assert (payload["camera"], payload["fps"], payload["start_frame"], payload["end_frame"]) == ("|shotCamera", 25.0, 101.25, 103.75)
                assert payload["markers"] == [{"subject_root": "|Hero", "color": "Red"}]
                assert payload["render_scope"]["policy"] == "assigned_and_eye_visible"
                assert payload["viewport_quality_report"]["profile"] == "full_smooth"
                assert hashlib.sha256(Path(job["scene_path"]).read_bytes()).hexdigest() == source_hash
                if role == "depth":
                    assert calls.index("auxiliary_scope") < calls.index("depth")
                elif role == "motion_guide":
                    assert "auxiliary_scope" not in calls  # Assigned motion keeps its original scope.


# Missing bindings retain the authored-visible fallback for isolated Motion.
with tempfile.TemporaryDirectory(prefix="hmb_motion_fallback_") as directory:
    path, _job = make_job(Path(directory), capture_pass="motion_guide")
    cmds, calls = EvaluationCmds(), []
    with mocked_capture(cmds, calls, bindings=False):
        assert runner.run(str(path))["ok"]
    assert "auxiliary_scope" in calls and cmds.mode == "parallel"


# Legacy Depth+Motion released Mask's exclusion scope before both auxiliaries.
# The node's explicit flag preserves that order-dependent scope in a fresh
# Motion process, while a Motion-only selection keeps its assigned scope.
for full_scene_scope in (False, True):
    with tempfile.TemporaryDirectory(prefix="hmb_motion_depth_scope_") as directory:
        path, _job = make_job(
            Path(directory), capture_pass="motion_guide",
            motion_guide_full_scene_scope=full_scene_scope,
        )
        cmds, calls = EvaluationCmds(), []
        with mocked_capture(cmds, calls):
            result = runner.run(str(path))
        assert ("auxiliary_scope" in calls) is full_scene_scope
        assert [value for value in calls if value in ("color", "depth", "motion_guide")] == ["motion_guide"]
        assert cmds.mode == "parallel" and result["ok"]
        if full_scene_scope:
            assert calls.index("auxiliary_scope") < calls.index("motion_guide")
            payload = runner._read_json(result["sidecar_path"])
            assert payload["auxiliary_render_scope"]["policy"] == "authored_visible_and_eye_visible"


# Legacy jobs still capture all roles and preserve optional-failure behavior.
with tempfile.TemporaryDirectory(prefix="hmb_capture_legacy_") as directory:
    path, job = make_job(Path(directory))
    cmds, calls = EvaluationCmds(), []
    with mocked_capture(cmds, calls, fail_role="depth"):
        result = runner.run(str(path))
    assert result["ok"] and cmds.mode == "parallel"
    assert [value for value in calls if value in ("color", "depth", "motion_guide")] == ["color", "depth", "motion_guide"]
    assert result["artifacts"]["depth"]["ok"] is False
    assert result["artifacts"]["motion_guide"]["ok"] is True
    assert Path(job["sidecar_path"]).is_file()


# Python exceptions and invalid/incomplete captures must restore the mode and
# report a failure; no partial auxiliary sidecar may claim successful output.
failure_cases = [
    ({"capture_pass": "color"}, {"fail_role": "open"}, {}, "scene open failure"),
    ({"capture_pass": "color"}, {"fail_role": "color"}, {}, "color failure"),
    ({"capture_pass": "depth"}, {"fail_role": "depth"}, {}, "Requested depth capture failed"),
    ({"capture_pass": "motion_guide"}, {"wrong_role": "motion_guide"}, {}, "frame count"),
    ({"maya_evaluation_mode": "parallel"}, {}, {}, "Unsupported Maya capture evaluation mode"),
    ({"capture_pass": "unknown"}, {}, {}, "Unsupported Maya capture pass"),
    ({}, {}, {"fail_set": ("serial",)}, "could not be applied"),
    ({}, {}, {"ignore_set": ("serial",)}, "could not be applied"),
    ({}, {}, {"fail_read": True}, "could not be read"),
    ({"capture_pass": "color"}, {}, {"fail_set": ("parallel",)}, "could not be restored"),
]
for fields, capture_options, evaluation_options, message in failure_cases:
    with tempfile.TemporaryDirectory(prefix="hmb_capture_failure_") as directory:
        path, job = make_job(Path(directory), **fields)
        cmds, calls = EvaluationCmds(**evaluation_options), []
        with mocked_capture(cmds, calls, **capture_options), contextlib.redirect_stderr(io.StringIO()):
            try:
                runner.run(str(path))
            except RuntimeError as exc:
                assert message in str(exc), (message, str(exc))
            else:
                raise AssertionError("Expected failure: " + message)
        result = runner._read_json(job["result_path"])
        assert result["ok"] is False and message in result["error"]
        if message != "could not be restored":
            assert cmds.mode == "parallel"
        if fields.get("capture_pass") == "depth":
            assert not Path(job["depth_sidecar_path"]).exists()
        if fields.get("capture_pass") == "motion_guide":
            assert not Path(job["motion_guide_sidecar_path"]).exists()


# Metadata READ does not query or mutate evaluation modes. Source save, user
# preferences and preference persistence must not be introduced anywhere.
with tempfile.TemporaryDirectory(prefix="hmb_capture_scan_") as directory:
    path, _job = make_job(Path(directory), operation="scan")
    cmds, calls = EvaluationCmds(prior="serial", fail_read=True), []
    with mocked_capture(cmds, calls):
        assert runner.run(str(path))["operation"] == "scan"
    assert cmds.set_calls == []

tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        continue
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "cmds":
        continue
    assert node.func.attr not in ("savePrefs", "saveToolSettings")
    if node.func.attr == "file":
        assert not {"save", "saveAs", "rename"}.intersection(keyword.arg for keyword in node.keywords)

print("PASS: isolated Color/Depth/Motion capture, exact timing, temporary serial/DG modes, failure restoration and unchanged source scenes.")
