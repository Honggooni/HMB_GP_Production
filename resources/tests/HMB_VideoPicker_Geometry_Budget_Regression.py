"""Smooth-geometry budget and native failure propagation without DCC/render/API calls."""
from __future__ import annotations

import copy
import contextlib
import importlib.util
import json
import io
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


with mock.patch.dict(sys.modules, {"maya": types.ModuleType("maya"), "maya.cmds": types.ModuleType("maya.cmds")}):
    runner = load_module("hmb_geometry_budget_runner", ROOT / "resources/maya/HMB_Maya_Background_Preview.py")
picker = load_module("hmb_geometry_budget_picker", ROOT / "HMBVideoPickerLibrary.py")
LIMIT = 10_000_000
POLICY = "hmb_smooth_preview_geometry_budget_v1"
ERROR = "smooth_preview_geometry_budget_exceeded"


class GeometryScene:
    """Maya metadata only. Any scene-edit/render call is an assertion failure."""
    def __init__(self, shapes, *, attributes=None, driven=()):
        self.shapes = copy.deepcopy(shapes)
        self.attributes = dict(attributes or {})
        self.driven = set(driven)
        self.queried = []
        self.writes = []

    def ls(self, node=None, **kwargs):
        if kwargs.get("type") == "mesh":
            return [path for path, data in self.shapes.items() if data.get("type", "mesh") == "mesh"]
        if isinstance(node, list):
            return list(node)
        return [node] if node else list(self.shapes)

    def nodeType(self, shape):
        return self.shapes.get(shape, {}).get("type", "mesh")

    def objExists(self, plug):
        return True

    def attributeQuery(self, _attribute, **_kwargs):
        return True

    def getAttr(self, plug):
        if plug in self.attributes:
            return self.attributes[plug]
        node, _, attribute = plug.rpartition(".")
        data = self.shapes.get(node, {})
        if attribute == "smoothLevel":
            return data.get("level", 2)
        if attribute == "displaySmoothMesh":
            return data.get("mode", 1)
        if attribute == "intermediateObject":
            return data.get("intermediate", False)
        if attribute in {"visibility", "lodVisibility", "overrideVisibility"}:
            return True
        return False

    def listConnections(self, plug, **_kwargs):
        return ["animatedVisibility.output"] if plug in self.driven else []

    def displaySmoothness(self, shape, **kwargs):
        if kwargs.get("query"):
            return [self.shapes[shape].get("mode", 1)]
        self.writes.append(("displaySmoothness", shape, kwargs))
        raise AssertionError("Budget preflight must not change authored mesh quality.")

    def setAttr(self, *args, **kwargs):
        self.writes.append(("setAttr", args, kwargs))
        raise AssertionError("Budget preflight must not modify Maya attributes.")

    def mesh_api(self, shape):
        self.queried.append(shape)
        data = self.shapes[shape]
        if data.get("query_error"):
            raise RuntimeError("synthetic unavailable topology")
        def visible():
            if "visible" in data:
                return data["visible"]
            parts = [part for part in shape.split("|") if part]
            return all(self.attributes.get("|" + "|".join(parts[:index]) + ".visibility", True)
                       for index in range(1, len(parts) + 1))
        dag_path = types.SimpleNamespace(isVisible=visible,
                                         isTemplated=lambda: data.get("templated", False))
        return None, dag_path, types.SimpleNamespace(
            numPolygons=data.get("faces", 1), numFaceVertices=data.get("face_vertices", 4))


class CaptureHost:
    """Production capture/error methods with an in-memory widget transport."""
    _run_shared_maya_capture = picker.HMBVideoPickerLibrary._run_shared_maya_capture
    _execute_maya_capture_passes = picker.HMBVideoPickerLibrary._execute_maya_capture_passes
    _register_active_process = picker.HMBVideoPickerLibrary._register_active_process
    _clear_active_process = picker.HMBVideoPickerLibrary._clear_active_process
    _set_failed_state = picker.HMBVideoPickerLibrary._set_failed_state
    _mark_operation_finished = picker.HMBVideoPickerLibrary._mark_operation_finished
    _operation_elapsed_seconds = staticmethod(picker.HMBVideoPickerLibrary._operation_elapsed_seconds)

    def __init__(self, kind, log):
        self._hmb_cancel_requested = threading.Event()
        self._hmb_active_process = None
        self.state = {"operation_kind": kind, "native_read_ready": True,
                      "native_metadata": {"quality": "authored high detail"},
                      "snapshots": [{"snapshot_uid": "existing-result"}],
                      "videos": [], "last_log_path": str(log)}

    def _picker_state(self):
        return copy.deepcopy(self.state)

    def _write_state(self, state):
        self.state = copy.deepcopy(state)

    def _assert_operation_current(self, _context, _stage):
        return None

    def _register_cleanup_file(self, _path):
        return None

    def _apply_selected_view_fields(self, state):
        return state

    def _sync_outputs_from_state(self, _state):
        return None

    def _wait_for_process_with_progress(self, process, *_args, **_kwargs):
        process.complete()
        return process.return_code


class GeometryBudgetTests(unittest.TestCase):
    def preflight(self, scene, job=None):
        job = job if job is not None else {}
        job.setdefault("_authored_cutout_snapshot", {
            path: {"alpha_driven": data.get("alpha", False), "ambiguous": data.get("ambiguous", False)}
            for path, data in scene.shapes.items()})
        with mock.patch.object(runner, "cmds", scene), \
                mock.patch.object(runner, "_depth_mesh_api", side_effect=scene.mesh_api), \
                mock.patch.object(runner, "_emit_console"):
            return runner._preflight_smooth_geometry_budget(job)

    def test_exact_limit_allowed_and_excess_rejected_without_quality_changes(self):
        at_limit = GeometryScene({"|Hero|shape": {"faces": 625000, "face_vertices": 2500000, "level": 2}})
        job = {}
        report = self.preflight(at_limit, job)
        self.assertEqual(report["policy"], POLICY)
        self.assertEqual(report["status"], "within_budget")
        self.assertTrue(report["complete"])
        self.assertEqual((report["estimated_faces"], report["budget_faces"]), (LIMIT, LIMIT))
        self.assertEqual(job["_smooth_geometry_budget_report"], report)
        over = GeometryScene({"|Hero|shape": {"faces": 625001, "face_vertices": 2500004, "level": 2}})
        with self.assertRaises(runner._SmoothPreviewGeometryBudgetError) as caught:
            self.preflight(over)
        self.assertEqual(caught.exception.error_code, ERROR)
        self.assertEqual(caught.exception.report["estimated_faces"], LIMIT + 16)
        self.assertEqual(caught.exception.report["status"], "exceeded")
        self.assertEqual(at_limit.writes + over.writes, [])

    def test_polygon_valence_and_authored_cutout_modes_are_counted(self):
        scene = GeometryScene({
            "|Hero|triangleAndPentagon": {"faces": 2, "face_vertices": 8, "level": 2},
            "|Hero|flatAlpha": {"faces": 1, "face_vertices": 4, "level": 6, "mode": 1, "alpha": True},
            "|Hero|smoothAlpha": {"faces": 4, "face_vertices": 16, "level": 2, "mode": 3, "alpha": True},
            "|Hero|mouth_card": {"faces": 1, "face_vertices": 4, "level": 6, "mode": 1, "ambiguous": True},
            "|Hero|zeroLevel": {"faces": 7, "face_vertices": 28, "level": 0},
        })
        report = self.preflight(scene)
        self.assertEqual(report["estimated_faces"], 32 + 1 + 64 + 1 + 7)
        self.assertEqual(report["base_faces"], 15)
        self.assertEqual(report["preserved_cutout_count"], 3)
        self.assertEqual(report["counted_mesh_path_count"], 5)
        self.assertEqual(scene.writes, [])

    def test_capture_scope_visibility_and_instance_paths_control_the_budget(self):
        scene = GeometryScene({
            "|One|sharedShape": {"faces": 10, "face_vertices": 40, "level": 1},
            "|Two|sharedShape": {"faces": 10, "face_vertices": 40, "level": 1},
            "|Hidden|shape": {"faces": LIMIT, "face_vertices": LIMIT * 4},
            "|Unassigned|shape": {"faces": LIMIT, "face_vertices": LIMIT * 4},
            "|Animated|shape": {"faces": 5, "face_vertices": 20, "level": 1},
            "|Construction|shape": {"faces": LIMIT, "face_vertices": LIMIT * 4, "intermediate": True},
        }, attributes={"|Hidden.visibility": False, "|Animated.visibility": False}, driven={"|Animated.visibility"})
        allowed = [path for path in scene.shapes if not path.startswith("|Unassigned|")]
        job = {"_viewport_quality_scope_shapes": allowed + [allowed[0]], "_render_scope_shapes": ["|Unassigned|shape"]}
        report = self.preflight(scene, job)
        self.assertEqual(report["estimated_faces"], 80)
        self.assertEqual(report["counted_mesh_path_count"], 2)
        self.assertEqual(set(scene.queried), {"|One|sharedShape", "|Two|sharedShape", "|Animated|shape"})
        empty = self.preflight(scene, {"_viewport_quality_scope_shapes": []})
        self.assertEqual(empty["estimated_faces"], 0)
        fallback = self.preflight(scene, {"_render_scope_shapes": ["|One|sharedShape"]})
        self.assertEqual(fallback["estimated_faces"], 40)

    def test_unknown_topology_never_claims_verified_budget_and_known_excess_still_stops(self):
        for invalid in (float("nan"), float("inf"), -1):
            with self.subTest(invalid=invalid):
                scene = GeometryScene({"|Invalid|shape": {"faces": invalid, "face_vertices": 4}})
                report = self.preflight(scene)
                self.assertFalse(report["complete"])
                self.assertEqual(report["status"], "incomplete")
                self.assertEqual(report["counted_mesh_path_count"], 0)
                self.assertTrue(report["unknown_mesh_paths"])
        scene = GeometryScene({"|Unavailable|shape": {"query_error": True}})
        report = self.preflight(scene)
        self.assertEqual(report["status"], "incomplete")
        scene.shapes["|TooLarge|shape"] = {"faces": LIMIT, "face_vertices": LIMIT * 4}
        with self.assertRaises(runner._SmoothPreviewGeometryBudgetError) as caught:
            self.preflight(scene)
        self.assertEqual(caught.exception.report["status"], "exceeded")
        self.assertFalse(caught.exception.report["complete"])
        self.assertGreater(caught.exception.report["estimated_faces"], LIMIT)

    def test_runner_writes_typed_error_and_progress_before_any_render_or_quality_edit(self):
        with tempfile.TemporaryDirectory(prefix="hmb-geometry-runner-") as temporary:
            root = Path(temporary)
            for role in ("original", "color", "depth"):
                with self.subTest(role=role):
                    folder = root / role
                    folder.mkdir()
                    source = folder / "scene.mb"
                    source.write_bytes(b"authored high-quality reference scene")
                    scene = GeometryScene({"|Background|shape": {"faces": 625001, "face_vertices": 2500004}})
                    scene.about = lambda **_kwargs: "2027"
                    frame_visits = []
                    scene.currentTime = lambda frame, **_kwargs: frame_visits.append(frame)
                    mode = ["parallel"]
                    def evaluation(query=False, mode=None):
                        if query:
                            return [current_mode[0]]
                        current_mode[0] = mode
                    current_mode = mode
                    scene.evaluationManager = evaluation
                    job = {
                        "operation": "snapshot" if role == "original" else "render",
                        "scene_path": str(source), "result_path": str(folder / "result.json"),
                        "progress_path": str(folder / "progress.json"), "sidecar_path": str(folder / "color.hmb.json"),
                        "frames_folder": str(folder / "frames"), "output_name": "color",
                        "camera": "|camera", "width": 1280, "height": 720,
                        "start_frame": 5, "end_frame": 5, "fps": 25,
                        "force_high_quality_viewport": True, "require_full_smooth_geometry": True,
                        "viewport_quality_profile": runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
                        "apply_marker_shaders": role != "original",
                        "apply_original_lambert_override": role == "original",
                        "original_material_override_profile": runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE if role == "original" else "",
                        "capture_pass": "" if role == "original" else role,
                        "_authored_cutout_snapshot": {"|Background|shape": {"alpha_driven": False}},
                        "depth_frames_folder": str(folder / "depth"), "depth_output_name": "depth",
                        "depth_sidecar_path": str(folder / "depth.hmb.json"),
                        "motion_guide_frames_folder": str(folder / "motion"), "motion_guide_output_name": "motion",
                        "motion_guide_sidecar_path": str(folder / "motion.hmb.json"),
                    }
                    job_path = folder / "job.json"
                    job_path.write_text(json.dumps(job), encoding="utf-8")
                    layer = {"report": {"capture_layer": "defaultRenderLayer", "default_layer_verified": True}}
                    def restore_layer(context):
                        context["report"].update(restored=True, restore_ok=True)
                    def assigned_scope(_bindings, current_job):
                        current_job["_viewport_quality_scope_shapes"] = list(scene.shapes)
                        return [], {"allowed_shape_path_count": 1}
                    with contextlib.ExitStack() as stack:
                        replacements = {
                            "cmds": scene, "_depth_mesh_api": scene.mesh_api,
                            "_open_scene_for_job": lambda value: value["scene_path"],
                            "_resolve_camera": lambda value: value,
                            "_apply_capture_render_layer": lambda: layer,
                            "_restore_capture_render_layer": restore_layer,
                            "_load_marker_catalog": lambda _job: None,
                            "_read_job_bindings": lambda _job: [{"subject_root": "|Background", "color": "Red"}],
                            "_character_outline_mode": lambda _job: "native_lambert",
                            "_apply_assigned_render_scope": assigned_scope,
                            "_authored_cutout_scope_shapes": lambda _job: list(scene.shapes),
                            "_emit_console": lambda *_args: None,
                        }
                        for name, replacement in replacements.items():
                            stack.enter_context(mock.patch.object(runner, name, replacement))
                        renders = [stack.enter_context(mock.patch.object(runner, name, side_effect=AssertionError("Rendering is forbidden after budget failure.")))
                                   for name in ("_render_frames", "_render_depth_pass", "_render_motion_guide_pass")]
                        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                        with self.assertRaises(runner._SmoothPreviewGeometryBudgetError):
                            runner.run(str(job_path))
                        for render in renders:
                            render.assert_not_called()
                    result = json.loads(Path(job["result_path"]).read_text(encoding="utf-8"))
                    progress = json.loads(Path(job["progress_path"]).read_text(encoding="utf-8"))
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["error_code"], ERROR)
                    self.assertEqual(result["smooth_geometry_budget_report"]["estimated_faces"], LIMIT + 16)
                    self.assertIn("10,000,016", result["error"])
                    self.assertIn("10,000,000", result["error"])
                    self.assertEqual(progress["stage"], "error")
                    self.assertEqual(progress["error_code"], ERROR)
                    self.assertEqual(progress["smooth_geometry_budget_report"], result["smooth_geometry_budget_report"])
                    self.assertEqual(scene.writes, [])
                    self.assertEqual(current_mode[0], "parallel")
                    self.assertTrue(layer["report"]["restore_ok"])
                    self.assertEqual(source.read_bytes(), b"authored high-quality reference scene")
                    self.assertEqual(list(folder.rglob("*.png")), [])

    def test_frame_budget_rechecks_animated_visibility_after_callbacks_before_ogs(self):
        with tempfile.TemporaryDirectory(prefix="hmb-geometry-frame-") as temporary:
            root = Path(temporary)
            scene = GeometryScene({
                "|Hero|shape": {"faces": 10, "face_vertices": 40, "level": 1, "mode": 3},
                "|AnimatedBackground|shape": {"faces": 625001, "face_vertices": 2500004, "level": 2, "mode": 3, "visible": False},
                "|Unassigned|shape": {"faces": LIMIT, "face_vertices": LIMIT * 4, "mode": 3},
            })
            current = {"frame": 0, "images": str(root / "images"), "prefix": ""}
            steps = []
            def workspace(**kwargs):
                if kwargs.get("query"):
                    return str(root)
                if "fileRuleEntry" in kwargs:
                    return current["images"]
                if "fileRule" in kwargs:
                    current["images"] = kwargs["fileRule"][1]
            def set_attr(name, value, **_kwargs):
                self.assertEqual(name, "defaultRenderGlobals.imageFilePrefix")
                current["prefix"] = value
            def current_time(frame, **_kwargs):
                current["frame"] = frame
                steps.append(("time", frame))
            def prepare(frame, _index, _total):
                steps.append(("prepare", frame))
                scene.shapes["|AnimatedBackground|shape"]["visible"] = frame == 2
            def ogs(**kwargs):
                frame = kwargs["frame"]
                steps.append(("ogs", frame))
                self.assertEqual(frame, 1)
                output = Path(current["images"]) / (current["prefix"] + ".png")
                output.write_bytes(b"synthetic approved frame")
                return True
            scene.workspace = workspace
            scene.setAttr = set_attr
            scene.currentTime = current_time
            scene.listRelatives = lambda *_args, **_kwargs: ["|camera|cameraShape"]
            scene.ogsRender = ogs
            job = {"force_high_quality_viewport": True, "capture_pass": "depth",
                   "_render_scope_shapes": ["|Hero|shape", "|AnimatedBackground|shape"],
                   "_viewport_quality_scope_shapes": ["|Hero|shape"],
                   "progress_path": str(root / "progress.json")}
            with mock.patch.object(runner, "cmds", scene), \
                    mock.patch.object(runner, "_depth_mesh_api", side_effect=scene.mesh_api), \
                    mock.patch.object(runner, "_ensure_authored_cutout_snapshot", side_effect=AssertionError("Frame checks must not rescan material graphs.")), \
                    mock.patch.object(runner, "_emit_console"):
                with self.assertRaises(runner._SmoothPreviewGeometryBudgetError) as caught:
                    runner._render_frames("|camera", [1, 2], 1280, 720, str(root / "frames"), "depth", job=job,
                                          pre_frame_callback=prepare,
                                          post_frame_callback=lambda frame, *_args: steps.append(("restore", frame)))
            self.assertEqual(steps, [("time", 1), ("prepare", 1), ("ogs", 1.0), ("restore", 1),
                                     ("time", 2), ("prepare", 2), ("restore", 2)])
            self.assertEqual(caught.exception.report["evaluation"], "actual_frame")
            self.assertEqual(caught.exception.report["maya_frame"], 2)
            self.assertEqual(caught.exception.report["estimated_faces"], LIMIT + 16 + 40)
            self.assertNotIn("|Unassigned|shape", scene.queried)
            self.assertEqual(current["images"], str(root / "images"))
            self.assertEqual((root / "frames/depth.000000.png").read_bytes(), b"synthetic approved frame")
            self.assertFalse((root / "frames/depth.000001.png").exists())

    def test_motion_software_raster_has_no_source_mesh_budget_query(self):
        with mock.patch.object(runner, "_depth_mesh_api", side_effect=AssertionError("Motion does not tessellate source meshes.")), \
                mock.patch.object(runner, "_ensure_authored_cutout_snapshot", side_effect=AssertionError("Unnecessary material scan.")):
            for actual in (False, True):
                job = {"capture_pass": "motion_guide"}
                report = runner._preflight_smooth_geometry_budget(job, actual_frame=actual, maya_frame=2)
                self.assertEqual(report["status"], "not_applicable")
                self.assertEqual(report["reason"], "motion_guide_software_raster")
                self.assertEqual(job["_smooth_geometry_budget_report"], report)

    def test_native_exit_one_preserves_typed_reason_through_shared_capture_and_ui_error(self):
        report = {"policy": POLICY, "budget_faces": LIMIT, "estimated_faces": LIMIT + 16,
                  "status": "exceeded", "complete": True}
        error_text = "Smooth Preview geometry budget exceeded: estimated 10,000,016 vs 10,000,000 faces."
        with tempfile.TemporaryDirectory(prefix="hmb-geometry-host-") as temporary:
            root = Path(temporary)
            scene = root / "scene.ma"
            scene.write_text("// isolated capture metadata fixture", encoding="utf-8")
            coordinator = picker._MayaCaptureCoordinator(workers=1)
            for kind in ("render_snapshot", "render_original_preview", "run_video"):
                with self.subTest(kind=kind):
                    private = root / ".hmb_video_picker" / kind
                    private.mkdir(parents=True)
                    job = {"operation": "snapshot" if kind == "render_snapshot" else "render",
                           "scene_path": str(scene), "camera": "|camera", "start_frame": 1,
                           "end_frame": 1, "fps": 25, "width": 1280, "height": 720,
                           "output_name": "mask", "frames_folder": str(private / "frames"),
                           "sidecar_path": str(private / "mask.hmb.json"),
                           "result_path": str(private / "result.json"),
                           "progress_path": str(private / "progress.json")}
                    job_path = private / "job.json"
                    job_path.write_text(json.dumps(job), encoding="utf-8")
                    log = root / (kind + ".txt")
                    log.write_text("capture requested\n", encoding="utf-8")
                    host = CaptureHost(kind, log)
                    launches = []
                    class FailedNativeProcess:
                        def __init__(self, _command, *, env, **_kwargs):
                            self.job = json.loads(Path(env["HMB_VIDEO_PICKER_JOB"]).read_text(encoding="utf-8"))
                            self.pid = 12345
                            self.return_code = None
                            launches.append(self.job)
                        def poll(self):
                            return self.return_code
                        def complete(self):
                            Path(self.job["result_path"]).write_text(json.dumps({
                                "ok": False, "error": error_text, "error_code": ERROR,
                                "smooth_geometry_budget_report": report}), encoding="utf-8")
                            self.return_code = 1
                    with mock.patch.object(picker, "_maya_capture_coordinator", return_value=coordinator), \
                            mock.patch.object(picker.subprocess, "Popen", FailedNativeProcess):
                        with self.assertRaises(picker._MayaNativeCaptureError) as caught:
                            if kind == "run_video":
                                host._execute_maya_capture_passes(job=job, command=["offline-maya"], job_path=job_path,
                                    result_path=Path(job["result_path"]), log_path=log, context=None)
                            else:
                                host._run_shared_maya_capture(job=job, command=["offline-maya"], job_path=job_path,
                                    result_path=Path(job["result_path"]), progress_path=Path(job["progress_path"]),
                                    log_path=log, activity_paths=(Path(job["frames_folder"]),), context=None,
                                    operation_label=kind)
                    self.assertEqual(caught.exception.error_code, ERROR)
                    self.assertEqual(caught.exception.smooth_geometry_budget_report, report)
                    self.assertEqual(str(caught.exception), error_text)
                    self.assertEqual(len(launches), 1, "A known budget error must not start a second Maya attempt.")
                    self.assertIsNone(host._hmb_active_process)
                    host._set_failed_state(caught.exception)
                    self.assertIn(error_text, host.state["message"])
                    self.assertEqual(host.state["native_error_code"], ERROR)
                    self.assertEqual(host.state["native_error_report"], report)
                    self.assertTrue(any(row["level"] == "ERROR" and row["message"] == error_text
                                        for row in host.state["activity_log"]))
                    self.assertTrue(host.state["native_read_ready"])
                    self.assertEqual(host.state["native_metadata"], {"quality": "authored high detail"})
                    self.assertEqual(host.state["snapshots"], [{"snapshot_uid": "existing-result"}])
                    self.assertNotIn("exited with code 1", host.state["message"])
                    self.assertIn(error_text, log.read_text(encoding="utf-8"))
                    self.assertEqual(list(private.rglob("*.png")), [])

    def test_sequential_worker_keeps_completed_mask_and_specific_budget_errors(self):
        # Reuse the isolated real-worker fixture; only per-role media producers
        # are simulated, as in its standalone progressive-generation coverage.
        fixture = load_module("hmb_geometry_progressive_fixture", ROOT / "resources/tests/HMB_VideoPicker_Progressive_Selected_Generation_Regression.py")
        harness = fixture.ProgressiveSelectedGenerationRegression()
        harness.setUp()
        try:
            case = fixture.Scenario("geometry-budget-terminal", roles=("original", "mask", "depth"))
            report = {"policy": POLICY, "status": "exceeded", "budget_faces": LIMIT, "estimated_faces": LIMIT + 16}
            detail = "Smooth Preview geometry budget exceeded: estimated 10,000,016 vs 10,000,000 faces."
            def original(_scene, *, context=None, **_kwargs):
                case.begin("original", context)
                raise fixture.picker._MayaNativeCaptureError(detail, ERROR, report)
            auxiliary = case.node._maya_mode
            def selected(_scene, slot, *, selected_role=None, context=None, **kwargs):
                if selected_role == "depth":
                    case.begin("depth", context)
                    raise fixture.picker._MayaNativeCaptureError(detail, ERROR, report)
                return auxiliary(_scene, slot, selected_role=selected_role, context=context, **kwargs)
            case.node._render_original_preview_mode = original
            case.node._maya_mode = selected
            result = case.run()
            self.assertEqual(case.entered, ["original", "mask", "depth"])
            self.assertEqual(result["generation_output_roles"], ["mask"])
            self.assertEqual(len(result["videos"]), 1)
            self.assertTrue(Path(result["videos"][0]["video_path"]).is_file())
            self.assertEqual(result["native_error_code"], ERROR)
            self.assertEqual(result["native_error_report"], report)
            self.assertIn(detail, result["message"])
            for role in ("Original", "Depth"):
                self.assertIn(role, result["message"])
                self.assertTrue(any(row["level"] == "ERROR" and role in row["message"] and detail in row["message"]
                                    for row in result["activity_log"]))
            self.assertTrue(result["native_read_ready"])
            self.assertEqual(Path(result["scene_path"]), case.scene)
            self.assertFalse(case.node._hmb_process_lock.locked())
            self.assertIsNone(case.node._hmb_active_operation)

            all_failed = fixture.Scenario("geometry-budget-all-failed", roles=("original", "mask", "depth"))
            def failed_original(_scene, *, context=None, **_kwargs):
                all_failed.begin("original", context)
                raise fixture.picker._MayaNativeCaptureError(detail, ERROR, report)
            def failed_auxiliary(_scene, _slot, *, selected_role=None, context=None, **_kwargs):
                all_failed.begin(selected_role, context)
                raise fixture.picker._MayaNativeCaptureError(detail, ERROR, report)
            all_failed.node._render_original_preview_mode = failed_original
            all_failed.node._maya_mode = failed_auxiliary
            before_log_count = len(all_failed.node._picker_state()["activity_log"])
            failed = all_failed.run()
            self.assertEqual(all_failed.entered, ["original", "mask", "depth"])
            self.assertEqual((failed["status"], failed["scene_stage"]), ("FAILED", "FAILED"))
            self.assertEqual(failed["generation_output_roles"], [])
            self.assertEqual(failed["videos"], [])
            self.assertEqual(failed["native_error_code"], ERROR)
            self.assertEqual(failed["native_error_report"], report)
            self.assertTrue(failed["native_read_ready"])
            self.assertIn(detail, failed["message"])
            operation_log = failed["activity_log"][before_log_count:]
            self.assertTrue(operation_log)
            self.assertFalse(any(row["level"] == "SUCCESS" for row in operation_log),
                             "An all-failed render must not append a SUCCESS; prior initialization logs remain intact.")
            self.assertEqual(failed["activity_log"][-1]["level"], "ERROR")
            for role in ("Original", "Mask", "Depth"):
                self.assertIn(role, failed["message"])
                self.assertTrue(any(row["level"] == "ERROR" and role in row["message"] and detail in row["message"]
                                    for row in failed["activity_log"]))
            self.assertFalse(all_failed.node._hmb_process_lock.locked())
            self.assertIsNone(all_failed.node._hmb_active_operation)
        finally:
            harness.tearDown()
            fixture.ENV.stop()
            fixture.ISOLATED.cleanup()


if __name__ == "__main__":
    unittest.main()
