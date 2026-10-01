"""Exercise process isolation, native-crash retry, and existing result guards.

The production orchestration runs against simulated external Maya processes;
actual Maya rendering, image semantics, and encoding have separate regressions.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("HMBVideoPickerLibrary", ROOT / "HMBVideoPickerLibrary.py")
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)

NATIVE_CRASH = 3221225477 if picker.os.name == "nt" else -11
PASS = picker.HMBVideoPickerLibrary._execute_maya_capture_passes


class Controller:
    def __init__(self):
        self._hmb_cancel_requested = threading.Event()
        self.state = {"language": "en"}
        self.stale = False
        self.active = None
        self.registered_pids = []
        self.cleaned_pids = []
        self.cleanup_paths = []

    def _assert_operation_current(self, _context, _stage):
        if self.stale:
            raise picker._StaleOperationError("Simulated accepted-input change")

    def _register_cleanup_file(self, path):
        self.cleanup_paths.append(path)

    def _picker_state(self):
        return dict(self.state)

    def _write_state(self, state):
        self.state = dict(state)

    def _register_active_process(self, process, _kind):
        assert self.active is None, "Capture processes must run sequentially."
        self.active = process
        self.registered_pids.append(process.pid)

    def _clear_active_process(self, process):
        assert self.active is process
        self.active = None
        self.cleaned_pids.append(process.pid)

    def _wait_for_process_with_progress(self, process, _progress, _overall, _stall, _label, *, activity_paths):
        assert tuple(activity_paths) == (process.frames_folder,)
        process.complete()
        return process.return_code


def fixture(root: Path):
    private = root / ".hmb_video_picker" / "isolated"
    private.mkdir(parents=True)
    scene = root / "scene.ma"
    scene.write_text("// isolated capture fixture", encoding="utf-8")
    job = {
        "operation": "render", "scene_path": str(scene), "output_folder": str(root),
        "output_name": "mask", "frames_folder": str(private / "frames"),
        "sidecar_path": str(private / "mask.hmb.json"),
        "result_path": str(private / "render.result.json"),
        "progress_path": str(private / "render.progress.json"),
        "camera": "|authoredCamera", "start_frame": None, "end_frame": None, "fps": None,
        "generate_depth_playblast": True, "generate_motion_guide": True,
        "depth_output_name": "depth", "depth_frames_folder": str(private / "depth_frames"),
        "depth_sidecar_path": str(private / "depth.hmb.json"),
        "motion_guide_output_name": "motion", "motion_guide_frames_folder": str(private / "motion_frames"),
        "motion_guide_sidecar_path": str(private / "motion.hmb.json"),
    }
    job_path = private / "render.job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    return job, job_path, private / "render.result.json", root / "capture.log"


def exercise(root: Path, outcomes=None, *, stop_role="", stale_role="", bad_path_role="", primary_bad_path=False, depth_selected=True):
    job, job_path, result_path, log_path = fixture(root)
    job["generate_depth_playblast"] = depth_selected
    job_path.write_text(json.dumps(job), encoding="utf-8")
    node = Controller()
    calls = []
    outcomes = outcomes or {}

    class Process:
        def __init__(self, _command, *, env, **_kwargs):
            self.job_path = Path(env["HMB_VIDEO_PICKER_JOB"])
            self.job = json.loads(self.job_path.read_text(encoding="utf-8"))
            self.role = self.job["capture_pass"]
            self.evaluation = self.job["maya_evaluation_mode"]
            self.pid = 1000 + len(calls)
            prefix = "" if self.role == "color" else self.role + "_"
            self.frames_folder = Path(self.job[prefix + "frames_folder"])
            self.sidecar_path = Path(self.job[prefix + "sidecar_path"])
            self.output_name = self.job[prefix + "output_name"]
            self.return_code = outcomes.get((self.role, self.evaluation), 0)
            calls.append((self.role, self.evaluation, self.pid, self.job))
            assert self.job["generate_depth_playblast"] is (self.role == "depth")
            assert self.job["generate_motion_guide"] is (self.role == "motion_guide")
            assert self.job["motion_guide_full_scene_scope"] is (
                self.role == "motion_guide" and depth_selected
            ), "Isolation changed legacy Motion visibility for the selected output set."

        def complete(self):
            if self.evaluation == "off":
                assert not (self.frames_folder / "partial-from-crash.png").exists(), "Retry reused crashed partial frames."
            self.frames_folder.mkdir(parents=True, exist_ok=True)
            if self.return_code:
                (self.frames_folder / "partial-from-crash.png").write_bytes(b"partial")
            else:
                for index in range(3):
                    (self.frames_folder / f"{self.output_name}.{index:06d}.png").write_bytes(b"complete frame")
                sidecar = {"camera": "|authoredCamera", "start_frame": 101, "end_frame": 103,
                           "fps": 24, "frame_count": 3, "resolution": {"width": 1920, "height": 1080},
                           "frame_map": [{"sequence_index": index, "maya_frame": 101 + index} for index in range(3)]}
                self.sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
                result = {"ok": True, "capture_pass": self.role, "scene_path": self.job["scene_path"],
                          "frames_folder": str(self.frames_folder), "sidecar_path": str(self.sidecar_path),
                          "fps": 24, "frame_count": 3, "frame_map": sidecar["frame_map"],
                          "artifacts": {self.role: {"ok": True}}}
                if self.role != "color":
                    result.update({self.role + "_frames_folder": str(self.frames_folder),
                                   self.role + "_sidecar_path": str(self.sidecar_path),
                                   self.role + "_frame_count": 3, self.role + "_frame_map": sidecar["frame_map"]})
                if bad_path_role == self.role:
                    result[self.role + "_sidecar_path"] = str(root / "unrelated.json")
                if primary_bad_path and self.role == "color":
                    result["sidecar_path"] = str(root / "unrelated.json")
                Path(self.job["result_path"]).write_text(json.dumps(result), encoding="utf-8")
            if self.role == stop_role:
                node._hmb_cancel_requested.set()
            if self.role == stale_role:
                node.stale = True

    original_popen = picker.subprocess.Popen
    picker.subprocess.Popen = Process
    result = None
    error = None
    try:
        result = PASS(node, job=job, command=["simulated-mayabatch"], job_path=job_path,
                      result_path=result_path, log_path=log_path, context=None)
    except Exception as exc:
        error = exc
    finally:
        picker.subprocess.Popen = original_popen
    assert node.active is None
    assert node.registered_pids == node.cleaned_pids
    assert len({call[2] for call in calls}) == len(calls)
    assert len({call[3]["result_path"] for call in calls}) == len(calls)
    assert len({call[3]["progress_path"] for call in calls}) == len(calls)
    return result, error, calls, job, node


with tempfile.TemporaryDirectory(prefix="hmb_isolated_capture_") as temp:
    root = Path(temp)
    result, error, calls, job, _node = exercise(root / "success")
    assert error is None, error
    assert [(role, mode) for role, mode, _pid, _job in calls] == [("color", "serial"), ("depth", "serial"), ("motion_guide", "serial")]
    assert all(result["artifacts"][role]["ok"] for role in ("color", "depth", "motion_guide"))
    for _role, _mode, _pid, pass_job in calls[1:]:
        assert (pass_job["camera"], pass_job["start_frame"], pass_job["end_frame"], pass_job["fps"]) == ("|authoredCamera", 101, 103, 24)

    result, error, calls, _job, _node = exercise(root / "motion_without_depth", depth_selected=False)
    assert error is None and result["artifacts"]["motion_guide"]["ok"], error
    assert [role for role, _mode, _pid, _job in calls] == ["color", "motion_guide"]
    assert calls[-1][3]["motion_guide_full_scene_scope"] is False

    result, error, calls, job, _node = exercise(root / "depth_native_failure", {("depth", "serial"): NATIVE_CRASH, ("depth", "off"): NATIVE_CRASH})
    assert error is None, error
    assert [(role, mode) for role, mode, _pid, _job in calls] == [("color", "serial"), ("depth", "serial"), ("depth", "off"), ("motion_guide", "serial")]
    assert result["artifacts"]["color"]["ok"] and result["artifacts"]["motion_guide"]["ok"]
    assert result["artifacts"]["depth"]["ok"] is False
    assert str(NATIVE_CRASH) in result["artifacts"]["depth"]["error"]
    assert (Path(job["frames_folder"]) / "mask.000002.png").is_file()
    assert Path(job["sidecar_path"]).is_file()
    assert Path(job["motion_guide_sidecar_path"]).is_file()

    result, error, calls, _job, _node = exercise(root / "depth_dg_recovery", {("depth", "serial"): NATIVE_CRASH})
    assert error is None and result["artifacts"]["depth"]["ok"], error
    assert any("DG evaluation" in warning for warning in result["capture_warnings"])
    assert [(role, mode) for role, mode, _pid, _job in calls].count(("color", "serial")) == 1

    result, error, calls, _job, _node = exercise(root / "ordinary_error", {("depth", "serial"): 1})
    assert error is None and result["artifacts"]["motion_guide"]["ok"], error
    assert ("depth", "off") not in [(role, mode) for role, mode, _pid, _job in calls]

    result, error, calls, _job, _node = exercise(root / "primary_failed", {("color", "serial"): NATIVE_CRASH, ("color", "off"): NATIVE_CRASH})
    assert result is None and isinstance(error, RuntimeError)
    assert [role for role, _mode, _pid, _job in calls] == ["color", "color"], "Companions need a complete primary Mask authority."

    result, error, calls, _job, _node = exercise(root / "stop_transition", {("depth", "serial"): NATIVE_CRASH}, stop_role="depth")
    assert result is None and "cancelled" in str(error)
    assert [role for role, _mode, _pid, _job in calls] == ["color", "depth"]

    result, error, calls, _job, _node = exercise(root / "stale_transition", stale_role="depth")
    assert result is None and isinstance(error, picker._StaleOperationError)
    assert [role for role, _mode, _pid, _job in calls] == ["color", "depth"]

    result, error, calls, _job, _node = exercise(root / "bad_aux_path", bad_path_role="depth")
    assert error is None and result["artifacts"]["depth"]["ok"] is False, error
    assert result["artifacts"]["motion_guide"]["ok"]
    assert "unexpected staged path" in result["artifacts"]["depth"]["error"]
    assert "depth_sidecar_path" not in result

    result, error, calls, _job, _node = exercise(root / "bad_primary_path", primary_bad_path=True)
    assert result is None and "unexpected staged path" in str(error)
    assert [role for role, _mode, _pid, _job in calls] == ["color"]

    controller = Controller()
    unsafe_job, unsafe_job_path, unsafe_result_path, unsafe_log_path = fixture(root / "unsafe_requested_path")
    unsafe_job["frames_folder"] = str(root / "unrelated-output")
    try:
        PASS(controller, job=unsafe_job, command=["must-not-launch"], job_path=unsafe_job_path,
             result_path=unsafe_result_path, log_path=unsafe_log_path, context=None)
    except RuntimeError as exc:
        assert "Refusing cleanup outside .hmb_video_picker" in str(exc), exc
    else:
        raise AssertionError("Capture accepted an unsafe requested frame root.")
    assert not controller.registered_pids

print("HMB VideoPicker isolated Maya capture regression: PASS (separate roles, native DG retry, retained primary, optional failure continuation, STOP/stale barriers, exact private paths)")
