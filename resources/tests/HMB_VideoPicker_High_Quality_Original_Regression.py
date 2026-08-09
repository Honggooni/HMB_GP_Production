from __future__ import annotations

import ast
import contextlib
import copy
import importlib.util
import io
import json
import re
import sys
import tempfile
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PICKER_PATH = ROOT / "HMBVideoPickerLibrary.py"
RUNNER_PATH = ROOT / "resources/maya/HMB_Maya_Background_Preview.py"
VIEWPORT_PROFILE_FIELD = "viewport_quality_profile"
MOUTH_PATCH_POLICY_FIELD = "mouth_card_inner_patch_policy"
FORCE_JOB_FIELD = "force_high_quality_viewport"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def function_node(tree: ast.AST, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one function named {name}, got {len(matches)}.")
    return matches[0]


def write_json_dicts(function: ast.FunctionDef) -> list[ast.Dict]:
    result: list[ast.Dict] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        callee = node.func
        if not isinstance(callee, ast.Name) or callee.id != "_write_json":
            continue
        if isinstance(node.args[1], ast.Dict):
            result.append(node.args[1])
    return result


def literal_dict_fields(node: ast.Dict) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        try:
            fields[key_node.value] = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            fields[key_node.value] = value_node
    return fields


def job_dict(function: ast.FunctionDef, required_fields: set[str]) -> dict[str, Any]:
    candidates = []
    for node in write_json_dicts(function):
        fields = literal_dict_fields(node)
        if required_fields.issubset(fields):
            candidates.append(fields)
    if len(candidates) != 1:
        raise AssertionError(
            f"Expected one job dict in {function.name} containing "
            f"{sorted(required_fields)}, got {len(candidates)}."
        )
    return candidates[0]


picker_source = PICKER_PATH.read_text(encoding="utf-8")
runner_source = RUNNER_PATH.read_text(encoding="utf-8")
picker_tree = ast.parse(picker_source, filename=str(PICKER_PATH))
runner_tree = ast.parse(runner_source, filename=str(RUNNER_PATH))

# READ remains metadata-only. Original and Color PLAYBLAST both request the
# same best-effort full-detail Smooth Preview 3 viewport profile.
read_job = job_dict(
    function_node(picker_tree, "_read_scene_mode"),
    {"operation", "scene_path", "result_path", "progress_path"},
)
original_job = job_dict(
    function_node(picker_tree, "_render_original_preview_mode"),
    {"operation", "scene_path", "frames_folder", "sidecar_path", "result_path"},
)
color_job = job_dict(
    function_node(picker_tree, "_maya_mode"),
    {"scene_path", "frames_folder", "sidecar_path", "result_path"},
)
assert read_job["operation"] == "scan"
assert read_job.get("generate_original_video") is False
assert FORCE_JOB_FIELD not in read_job
assert original_job["operation"] == "render"
assert original_job.get("apply_marker_shaders") is False
assert original_job.get(FORCE_JOB_FIELD) is True
assert original_job.get("require_full_smooth_geometry") is True
assert original_job.get(MOUTH_PATCH_POLICY_FIELD) is not None
assert color_job.get("apply_marker_shaders") is True
assert color_job.get(FORCE_JOB_FIELD) is True
assert color_job.get("require_full_smooth_geometry") is True
assert color_job.get("world_space_patterns") is True
assert color_job.get("world_pattern_profile") is not None
assert color_job.get("world_pattern_cell_units") is not None
assert color_job.get("world_pattern_density_multiplier") is not None
assert color_job.get("screen_space_patterns") is False

# The runner must gate the override from the explicit job field and restore it
# in a finally-protected path. These static pins make accidental unconditional
# application to READ/Color visible even if a future mock becomes too lenient.
assert FORCE_JOB_FIELD in runner_source
assert VIEWPORT_PROFILE_FIELD in runner_source
assert "overrideLevelOfDetail" in runner_source
assert "finally:" in runner_source

# Every explicit reference load must suppress scriptNode execution. Proxy
# activation must use proxyActivate(..., false), never proxySwitch or
# proxyActivate(..., true), before the same safe load path is used.
reference_load_calls: list[ast.Call] = []
for candidate in ast.walk(runner_tree):
    if not isinstance(candidate, ast.Call):
        continue
    if not (
        isinstance(candidate.func, ast.Attribute)
        and candidate.func.attr == "file"
        and isinstance(candidate.func.value, ast.Name)
        and candidate.func.value.id == "cmds"
    ):
        continue
    if any(keyword.arg == "loadReference" for keyword in candidate.keywords):
        reference_load_calls.append(candidate)
assert reference_load_calls, "The Maya runner must contain explicit reference loads."
for reference_load_call in reference_load_calls:
    execute_keyword = next(
        (
            keyword
            for keyword in reference_load_call.keywords
            if keyword.arg == "executeScriptNodes"
        ),
        None,
    )
    assert (
        execute_keyword is not None
        and isinstance(execute_keyword.value, ast.Constant)
        and execute_keyword.value.value is False
    ), (
        "Every cmds.file(loadReference=...) call must set "
        f"executeScriptNodes=False (line {reference_load_call.lineno})."
    )

proxy_switch_function = function_node(runner_tree, "_switch_proxy_reference")
proxy_switch_calls = [
    candidate
    for candidate in ast.walk(proxy_switch_function)
    if isinstance(candidate, ast.Call)
    and isinstance(candidate.func, ast.Attribute)
    and candidate.func.attr == "eval"
]
assert len(proxy_switch_calls) == 1
proxy_activation_expression = ast.get_source_segment(
    runner_source, proxy_switch_calls[0]
) or ""
assert "proxyActivate" in proxy_activation_expression
assert "false" in proxy_activation_expression
assert "proxySwitch" not in proxy_activation_expression


picker = load_module("HMBVideoPickerLibrary_HQ_Regression", PICKER_PATH)

# A high-quality viewport behavior change is part of Original cache identity.
# Old sidecars that predate the profile and sidecars from a stale profile must
# be rejected even when scene/camera/range/FPS/resolution/encoding all match.
with tempfile.TemporaryDirectory(prefix="HMB_HQ_Original_Cache_") as cache_dir:
    cache_root = Path(cache_dir)
    scene_path = cache_root / "shot.mb"
    scene_path.write_bytes(b"Maya high-quality Original cache fixture")
    reference_path = cache_root / "prop.ma"
    reference_path.write_bytes(b"reference-v1")
    state = picker._default_widget_state()
    state.update(
        {
            "scene_path": str(scene_path),
            "scene_request_path": str(scene_path),
            "selected_camera": "|shotCam",
            "camera": "|shotCam",
            "start_frame": 1001.0,
            "end_frame": 1010.0,
            "source_fps": 24.0,
            "output_width": 1280,
            "output_height": 720,
            "native_metadata": {
                "scene_path": str(scene_path),
                "start_frame": 1001.0,
                "end_frame": 1010.0,
                "fps": 24.0,
            },
        }
    )
    dependency_manifest_path = picker._scene_dependency_manifest_path(scene_path)
    dependency_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    dependency_manifest_path.write_text(
        json.dumps(
            {
                "schema": picker.ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA,
                "version": picker.ORIGINAL_DEPENDENCY_MANIFEST_VERSION,
                "scene_path": str(scene_path),
                "paths": [str(scene_path), str(reference_path)],
            }
        ),
        encoding="utf-8",
    )
    state["native_metadata"]["dependency_manifest_path"] = str(
        dependency_manifest_path
    )
    cache_fields = picker._original_preview_cache_fields(scene_path, state)
    assert VIEWPORT_PROFILE_FIELD in cache_fields
    assert str(cache_fields[VIEWPORT_PROFILE_FIELD]).strip()
    assert cache_fields[MOUTH_PATCH_POLICY_FIELD] == (
        picker.MOUTH_CARD_INNER_PATCH_POLICY
    )

    video_path, sidecar_path = picker._original_preview_paths(scene_path)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    def mp4_box(box_type: bytes, payload: bytes) -> bytes:
        return (8 + len(payload)).to_bytes(4, "big") + box_type + payload

    video_path.write_bytes(
        mp4_box(b"ftyp", b"isom\x00\x00\x02\x00isom")
        + mp4_box(b"mdat", b"hq")
        + mp4_box(b"moov", b"meta")
    )
    current_sidecar = {
        "schema": "hmb-original-playblast",
        **copy.deepcopy(cache_fields),
        "accepted_read_dependency_fingerprint": cache_fields[
            "scene_dependency_fingerprint"
        ],
        "scene_dependency_paths": [str(scene_path), str(reference_path)],
        "video_size_bytes": video_path.stat().st_size,
    }
    sidecar_path.write_text(
        json.dumps(current_sidecar, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert picker._original_preview_cache_is_valid(
        scene_path, state, video_path, sidecar_path
    )

    reference_path.write_bytes(b"reference-v2")
    assert not picker._original_preview_cache_is_valid(
        scene_path, state, video_path, sidecar_path
    ), "Changing only an external reference must invalidate Original cache."
    cache_fields = picker._original_preview_cache_fields(scene_path, state)
    current_sidecar = {
        "schema": "hmb-original-playblast",
        **copy.deepcopy(cache_fields),
        "accepted_read_dependency_fingerprint": cache_fields[
            "scene_dependency_fingerprint"
        ],
        "scene_dependency_paths": [str(scene_path), str(reference_path)],
        "video_size_bytes": video_path.stat().st_size,
    }

    legacy_sidecar = copy.deepcopy(current_sidecar)
    legacy_sidecar.pop(VIEWPORT_PROFILE_FIELD)
    sidecar_path.write_text(
        json.dumps(legacy_sidecar, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert not picker._original_preview_cache_is_valid(
        scene_path, state, video_path, sidecar_path
    )

    missing_mouth_policy_sidecar = copy.deepcopy(current_sidecar)
    missing_mouth_policy_sidecar.pop(MOUTH_PATCH_POLICY_FIELD)
    sidecar_path.write_text(
        json.dumps(
            missing_mouth_policy_sidecar,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    assert not picker._original_preview_cache_is_valid(
        scene_path, state, video_path, sidecar_path
    )

    stale_mouth_policy_sidecar = copy.deepcopy(current_sidecar)
    stale_mouth_policy_sidecar[MOUTH_PATCH_POLICY_FIELD] = (
        "temporary_mouth_alpha_inner_patch_v0"
    )
    sidecar_path.write_text(
        json.dumps(stale_mouth_policy_sidecar, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert not picker._original_preview_cache_is_valid(
        scene_path, state, video_path, sidecar_path
    )

    stale_sidecar = copy.deepcopy(current_sidecar)
    stale_sidecar[VIEWPORT_PROFILE_FIELD] = "stale_bbox_profile_v0"
    sidecar_path.write_text(
        json.dumps(stale_sidecar, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert not picker._original_preview_cache_is_valid(
        scene_path, state, video_path, sidecar_path
    )


# Selecting Original must replace stale Color-slot camera/range/FPS metadata,
# not only its URL and marker list.
view_node = picker.HMBVideoPickerLibrary(name="high_quality_original_view")
contaminated_view = picker._default_widget_state()
contaminated_view.update(
    {
        "original_preview_enabled": True,
        "original_video_path": "C:/preview/original.mp4",
        "original_video_url": "file:///C:/preview/original.mp4",
        "camera": "|colorCam",
        "source_fps": 60.0,
        "start_frame": 1.0,
        "end_frame": 300.0,
        "source_frame_count": 300,
        "markers": [{"color": "Red"}],
        "original_metadata": {
            "camera": "|originalCam",
            "fps": 24.0,
            "start_frame": 1001.0,
            "end_frame": 1010.0,
            "frame_count": 10,
            "resolution": {"width": 1920, "height": 1080},
        },
    }
)
original_view = view_node._apply_selected_view_fields(contaminated_view)
assert original_view["camera"] == "|originalCam"
assert original_view["source_fps"] == 24.0
assert original_view["start_frame"] == 1001.0
assert original_view["end_frame"] == 1010.0
assert original_view["source_frame_count"] == 10
assert original_view["output_width"] == 1920
assert original_view["output_height"] == 1080
assert original_view["markers"] == []


class FakeMayaCmds(types.ModuleType):
    """Small Maya command model for temporary bbox/LOD override contracts."""

    def __init__(self) -> None:
        super().__init__("maya.cmds")
        self.quality_nodes = ["|BBox_GRP", "|Full_GRP", "|Authored_GRP"]
        self.values: dict[str, Any] = {
            "|BBox_GRP.overrideEnabled": True,
            "|BBox_GRP.overrideLevelOfDetail": 1,
            "|Full_GRP.overrideEnabled": True,
            "|Full_GRP.overrideLevelOfDetail": 0,
            "|Authored_GRP.overrideEnabled": False,
            "|Authored_GRP.overrideLevelOfDetail": 1,
        }
        self.settable = {name: True for name in self.values}
        self.set_calls: list[tuple[str, Any]] = []
        self.smooth_modes = {name: 1 for name in self.quality_nodes}
        self.visible_nurbs = "|Nurbs_GRP|VisibleNurbsShape"
        self.history_nurbs = "|Nurbs_GRP|VisibleNurbsShapeOrig"
        self.nurbs_smoothness = {
            self.visible_nurbs: {
                "divisionsU": 0,
                "divisionsV": 2,
                "pointsWire": 8,
                "pointsShaded": 3,
            },
        }
        self.values[self.visible_nurbs + ".intermediateObject"] = False
        self.values[self.history_nurbs + ".intermediateObject"] = True
        self.nurbs_calls: list[tuple[str, bool, dict[str, Any]]] = []

    def about(self, version: bool = False, **_kwargs):
        return "2027" if version else ""

    def ls(self, *patterns, **kwargs):
        if kwargs.get("type") == "nurbsSurface":
            return [self.visible_nurbs, self.history_nurbs]
        if patterns:
            pattern = str(patterns[0])
            if "overrideLevelOfDetail" in pattern:
                if kwargs.get("objectsOnly"):
                    return list(self.quality_nodes)
                return [node + ".overrideLevelOfDetail" for node in self.quality_nodes]
            if "overrideEnabled" in pattern:
                if kwargs.get("objectsOnly"):
                    return list(self.quality_nodes)
                return [node + ".overrideEnabled" for node in self.quality_nodes]
        if (
            kwargs.get("dag")
            or kwargs.get("dagObjects")
            or kwargs.get("long")
            or kwargs.get("type") in {"transform", "mesh"}
        ):
            return list(self.quality_nodes)
        return list(self.quality_nodes)

    def objExists(self, name: str) -> bool:
        return name in self.values or name in self.quality_nodes

    def attributeQuery(self, attribute: str, node: str, exists: bool = False, **_kwargs):
        if exists:
            return f"{node}.{attribute}" in self.values
        return False

    def getAttr(self, name: str, **kwargs):
        if kwargs.get("settable"):
            return self.settable.get(name, False)
        if kwargs.get("lock"):
            return not self.settable.get(name, False)
        if name not in self.values:
            raise RuntimeError(f"Unknown mocked Maya attribute: {name}")
        return self.values[name]

    def setAttr(self, name: str, value: Any, *_args, **_kwargs):
        # Render-global changes are irrelevant to this contract but remain
        # accepted so the production viewport setup function can run.
        if name in self.values:
            if not self.settable.get(name, False):
                raise RuntimeError(f"Mocked attribute is not settable: {name}")
            self.values[name] = value
            self.set_calls.append((name, value))

    def displayRGBColor(self, *_args, **_kwargs):
        return None

    def displaySmoothness(
        self,
        node,
        query=False,
        polygonObject=None,
        **kwargs,
    ):
        if node in {self.visible_nurbs, self.history_nurbs}:
            if node == self.history_nurbs:
                raise AssertionError("Intermediate NURBS must not be queried or changed.")
            self.nurbs_calls.append((node, bool(query), dict(kwargs)))
            values = self.nurbs_smoothness[node]
            for flag in ("divisionsU", "divisionsV", "pointsWire", "pointsShaded"):
                if query and kwargs.get(flag) is True:
                    return [values[flag]]
                if not query and flag in kwargs:
                    values[flag] = int(kwargs[flag])
            return None
        if query and polygonObject is True:
            return [self.smooth_modes.get(node, 1)]
        if polygonObject is not None:
            self.smooth_modes[node] = int(polygonObject)
        return None

    def listRelatives(self, *_args, **_kwargs):
        return []

    def nodeType(self, _node: str):
        return "transform"

    def referenceQuery(self, *_args, **_kwargs):
        return False

    def listConnections(self, *_args, **_kwargs):
        return []

    def connectionInfo(self, *_args, **_kwargs):
        return False


fake_cmds = FakeMayaCmds()
maya_module = types.ModuleType("maya")
maya_module.cmds = fake_cmds
sys.modules["maya"] = maya_module
sys.modules["maya.cmds"] = fake_cmds
runner = load_module("HMB_Maya_Background_Preview_HQ_Regression", RUNNER_PATH)
production_switch_proxy_reference = runner._switch_proxy_reference


def authored_quality_snapshot() -> dict[str, Any]:
    return {
        name: value
        for name, value in fake_cmds.values.items()
        if name.endswith(".overrideEnabled") or name.endswith(".overrideLevelOfDetail")
    }


def bbox_is_full_quality() -> bool:
    return (
        not bool(fake_cmds.values["|BBox_GRP.overrideEnabled"])
        or int(fake_cmds.values["|BBox_GRP.overrideLevelOfDetail"]) == 0
    )


# A missing procedural plug-in is advisory when the scene still contains saved
# viewport meshes. This restores the production path used by older shots while
# keeping Bounding Box, technical-dummy, missing-mesh, and Smooth Preview checks.
original_unresolved_proxy_plugins = runner._unresolved_proxy_plugins
original_visible_technical_dummy_meshes = runner._visible_technical_dummy_meshes
original_emit_console = runner._emit_console
proxy_pass_messages: list[tuple[str, str]] = []
try:
    runner._unresolved_proxy_plugins = lambda: [
        {
            "node": "SichuanPark:redshiftProxy116",
            "real_class": "",
            "plugin": "redshift4maya",
        }
    ]
    runner._emit_console = lambda level, message: proxy_pass_messages.append(
        (str(level), str(message))
    )
    proxy_restore, proxy_report = runner._apply_full_smooth_viewport(
        {
            "require_full_smooth_geometry": True,
            VIEWPORT_PROFILE_FIELD: runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
        }
    )
    assert proxy_report["unresolved_proxy_plugin_pass_through"] is True
    assert proxy_report["unresolved_proxy_nodes"][0]["node"] == (
        "SichuanPark:redshiftProxy116"
    )
    assert len(proxy_report["warnings"]) == 1
    assert "authored reference, proxy, and visibility state is preserved" in (
        proxy_report["warnings"][0]
    )
    assert "cached proxy recovery is not attempted" in proxy_report["warnings"][0]
    assert proxy_report["smooth_mesh_shape_count"] == len(fake_cmds.quality_nodes)
    assert proxy_pass_messages == [
        ("WARNING", proxy_report["warnings"][0])
    ]
    assert runner._restore_full_smooth_viewport(proxy_restore) == []
    assert authored_quality_snapshot() == {
        "|BBox_GRP.overrideEnabled": True,
        "|BBox_GRP.overrideLevelOfDetail": 1,
        "|Full_GRP.overrideEnabled": True,
        "|Full_GRP.overrideLevelOfDetail": 0,
        "|Authored_GRP.overrideEnabled": False,
        "|Authored_GRP.overrideLevelOfDetail": 1,
    }

    # Visible technical geometry is reported, but a preferred quality profile
    # no longer blocks otherwise valid tool output.
    runner._visible_technical_dummy_meshes = lambda: ["|technical_dummy|meshShape"]
    dummy_restore, dummy_report = runner._apply_full_smooth_viewport(
        {
            "require_full_smooth_geometry": True,
            VIEWPORT_PROFILE_FIELD: runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
        }
    )
    assert any(
        "Visible dummy/check geometry" in warning
        for warning in dummy_report["warnings"]
    )
    assert runner._restore_full_smooth_viewport(dummy_restore) == []
finally:
    runner._unresolved_proxy_plugins = original_unresolved_proxy_plugins
    runner._visible_technical_dummy_meshes = (
        original_visible_technical_dummy_meshes
    )
    runner._emit_console = original_emit_console


runner._open_scene_for_job = lambda _job: "C:/show/shot.mb"
runner._resolve_camera = lambda camera: camera or "|shotCam"
runner._load_marker_catalog = lambda _job: {}
runner._read_job_bindings = lambda _job: []
runner._apply_marker_shaders = lambda _bindings, _job: []
runner._apply_assigned_render_scope = lambda _bindings, _job: (
    [],
    {
        "policy": "maya_authored_visible_and_color_bound_and_picker_visible",
        "allowed_shape_path_count": len(fake_cmds.quality_nodes),
        "excluded_shape_path_count": 0,
    },
)
runner._emit_console = lambda *_args, **_kwargs: None
runner._write_progress = lambda *_args, **_kwargs: None
runner._scan_scene = lambda _job, _result, _version, _scene: {
    "ok": True,
    "operation": "scan",
}


def render_job(
    folder: Path,
    *,
    marker_mode: bool,
    force_high_quality: bool,
) -> tuple[Path, Path, dict[str, Any]]:
    frames_folder = folder / "frames"
    sidecar_path = folder / "preview.hmb.json"
    result_path = folder / "preview.result.json"
    job = {
        "operation": "render",
        "scene_path": "C:/show/shot.mb",
        "frames_folder": str(frames_folder),
        "sidecar_path": str(sidecar_path),
        "result_path": str(result_path),
        "camera": "|shotCam",
        "width": 1280,
        "height": 720,
        "start_frame": 1001.0,
        "end_frame": 1001.0,
        "fps": 24.0,
        "output_name": "preview",
        "apply_marker_shaders": marker_mode,
    }
    if force_high_quality:
        job[FORCE_JOB_FIELD] = True
    job_path = folder / "preview.job.json"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return job_path, sidecar_path, job


with tempfile.TemporaryDirectory(prefix="HMB_HQ_Original_Runner_") as runner_dir:
    runner_root = Path(runner_dir)
    authored = authored_quality_snapshot()
    observations: list[tuple[str, bool]] = []

    def successful_render_frames(**kwargs):
        observations.append((str(kwargs.get("output_name")), bbox_is_full_quality()))
        frames_folder = Path(kwargs["frames_folder"])
        frames_folder.mkdir(parents=True, exist_ok=True)
        frame_path = frames_folder / f"{kwargs['output_name']}.000000.png"
        frame_path.write_bytes(b"fake png")
        return [str(frame_path)], [{"index": 0, "maya_frame": 1001.0}]

    runner._render_frames = successful_render_frames

    # READ returns before any viewport override path.
    read_folder = runner_root / "read"
    read_folder.mkdir()
    read_result_path = read_folder / "read.result.json"
    read_job_path = read_folder / "read.job.json"
    read_job_path.write_text(
        json.dumps(
            {
                "operation": "scan",
                "scene_path": "C:/show/shot.mb",
                "result_path": str(read_result_path),
            }
        ),
        encoding="utf-8",
    )
    assert runner.run(str(read_job_path))["operation"] == "scan"
    assert authored_quality_snapshot() == authored
    assert observations == []

    # Color PLAYBLAST must capture with the same full-detail override and then
    # restore the authored bbox/LOD state exactly.
    color_folder = runner_root / "color"
    color_folder.mkdir()
    color_job_path, color_sidecar_path, _ = render_job(
        color_folder,
        marker_mode=True,
        force_high_quality=True,
    )
    runner.run(str(color_job_path))
    assert observations[-1] == ("preview", True)
    assert authored_quality_snapshot() == authored
    assert fake_cmds.nurbs_smoothness[fake_cmds.visible_nurbs] == {
        "divisionsU": 0,
        "divisionsV": 2,
        "pointsWire": 8,
        "pointsShaded": 3,
    }
    color_sidecar = json.loads(color_sidecar_path.read_text(encoding="utf-8"))
    assert (
        color_sidecar["viewport_quality_report"]["smooth_nurbs_shape_count"]
        == 1
    )
    assert color_sidecar.get(VIEWPORT_PROFILE_FIELD) == (
        picker.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
    )
    assert color_sidecar.get("assignment_mode") == (
        "direct_group_name_plus_color_pick"
    )

    # Original applies full-quality display only during frame capture and then
    # restores every authored bbox/LOD value exactly.
    original_folder = runner_root / "original"
    original_folder.mkdir()
    original_job_path, original_sidecar_path, _ = render_job(
        original_folder,
        marker_mode=False,
        force_high_quality=True,
    )
    runner.run(str(original_job_path))
    assert observations[-1] == ("preview", True)
    assert authored_quality_snapshot() == authored
    original_sidecar = json.loads(original_sidecar_path.read_text(encoding="utf-8"))
    assert (
        original_sidecar.get(VIEWPORT_PROFILE_FIELD)
        == picker._original_preview_cache_fields(
            Path("C:/show/shot.mb"),
            {
                "selected_camera": "|shotCam",
                "start_frame": 1001.0,
                "end_frame": 1001.0,
                "source_fps": 24.0,
                "output_width": 1280,
                "output_height": 720,
            },
        )[VIEWPORT_PROFILE_FIELD]
    )

    # Failure cannot strand the opened Maya scene in a forced display state.
    failure_folder = runner_root / "failure"
    failure_folder.mkdir()
    failure_job_path, _, _ = render_job(
        failure_folder,
        marker_mode=False,
        force_high_quality=True,
    )

    def failing_render_frames(**_kwargs):
        assert bbox_is_full_quality()
        raise RuntimeError("intentional render failure after high-quality override")

    runner._render_frames = failing_render_frames
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            runner.run(str(failure_job_path))
    except RuntimeError as exc:
        assert "intentional render failure" in str(exc)
    else:
        raise AssertionError("The mocked Original render failure was not propagated.")
    assert authored_quality_snapshot() == authored


class FakeProxyReferenceCmds(types.ModuleType):
    """Maya proxyManager/reference model with optional nested references."""

    def __init__(
        self,
        managers: dict[str, dict[str, Any]],
        standard_references: list[dict[str, Any]] | None = None,
        fail_load_nodes: set[str] | None = None,
    ) -> None:
        super().__init__("maya.cmds")
        self.managers = copy.deepcopy(managers)
        self.references: dict[str, dict[str, Any]] = {}
        self.switch_calls: list[str] = []
        self.activation_calls: list[str] = []
        self.load_calls: list[str] = []
        self.unload_calls: list[str] = []
        self.file_calls: list[dict[str, Any]] = []
        self.fail_load_nodes = set(fail_load_nodes or set())
        self.nested_by_parent: dict[str, list[dict[str, Any]]] = {}
        for manager in self.managers.values():
            for member in manager.get("members") or []:
                self.references[member["node"]] = {
                    "loaded": bool(member.get("loaded")),
                    "filename": member.get("filename") or f"P:/proxy/{member['node']}.ma",
                    "proxy_tag": member.get("tag") or "",
                }
        for record in standard_references or []:
            node = record["node"]
            self.references[node] = {
                "loaded": bool(record.get("loaded")),
                "filename": record.get("filename") or f"P:/assets/{node}.ma",
                "proxy_tag": "",
            }
            self.nested_by_parent[node] = [
                copy.deepcopy(item) for item in record.get("nested") or []
            ]

    def ls(self, *_patterns, **kwargs):
        node_type = kwargs.get("type")
        if node_type == "proxyManager":
            return sorted(self.managers)
        if node_type == "reference":
            return sorted(self.references)
        return []

    def getAttr(self, plug: str, **kwargs):
        if kwargs.get("multiIndices") and plug.endswith(".proxyList"):
            manager = plug.rsplit(".", 1)[0]
            return list(range(len(self.managers[manager].get("members") or [])))
        if plug.endswith(".proxyTag"):
            node = plug.rsplit(".", 1)[0]
            return self.references[node]["proxy_tag"]
        raise RuntimeError(f"Unsupported proxy mock getAttr: {plug} {kwargs}")

    def connectionInfo(self, plug: str, **kwargs):
        if not kwargs.get("destinationFromSource"):
            return []
        if plug.endswith(".activeProxy"):
            manager_name = plug.rsplit(".", 1)[0]
            manager = self.managers[manager_name]
            active = manager.get("active") or ""
            for index, member in enumerate(manager.get("members") or []):
                if member["node"] == active:
                    return [f"{manager_name}.proxyList[{index}]"]
            return []
        if ".proxyList[" in plug:
            manager_name = plug.split(".proxyList[", 1)[0]
            index = int(plug.rsplit("[", 1)[1].rstrip("]"))
            member = self.managers[manager_name]["members"][index]
            return [f"{member['node']}.proxyMsg"]
        return []

    def objExists(self, node: str):
        return node in self.references or node in self.managers

    def nodeType(self, node: str):
        if node in self.references:
            return "reference"
        if node in self.managers:
            return "proxyManager"
        return ""

    def attributeQuery(self, attribute: str, node: str, exists: bool = False, **_kwargs):
        return bool(exists and attribute == "proxyTag" and node in self.references)

    def referenceQuery(self, node: str, **kwargs):
        if node not in self.references:
            raise RuntimeError(f"Unknown reference node: {node}")
        if kwargs.get("isLoaded"):
            return bool(self.references[node]["loaded"])
        if kwargs.get("filename"):
            return self.references[node]["filename"]
        raise RuntimeError(f"Unsupported proxy mock referenceQuery: {node} {kwargs}")

    def file(self, *_args, **kwargs):
        if kwargs.get("loadReference"):
            node = kwargs["loadReference"]
            self.file_calls.append(dict(kwargs))
            if node in self.fail_load_nodes:
                raise RuntimeError(f"intentional safe-load failure for {node}")
            self.references[node]["loaded"] = True
            self.load_calls.append(node)
            for nested in self.nested_by_parent.get(node) or []:
                nested_node = nested["node"]
                self.references.setdefault(
                    nested_node,
                    {
                        "loaded": bool(nested.get("loaded")),
                        "filename": nested.get("filename")
                        or f"P:/assets/{nested_node}.ma",
                        "proxy_tag": "",
                    },
                )
            return self.references[node]["filename"]
        if kwargs.get("unloadReference"):
            node = kwargs["unloadReference"]
            self.file_calls.append(dict(kwargs))
            self.references[node]["loaded"] = False
            self.unload_calls.append(node)
            return None
        raise RuntimeError(f"Unsupported proxy mock file call: {kwargs}")

    def activate_proxy(self, reference_node: str):
        """Model proxyActivate(reference, false): select but do not unsafe-load."""
        owner = None
        for manager_name, manager in self.managers.items():
            if any(
                member.get("node") == reference_node
                for member in manager.get("members") or []
            ):
                owner = manager_name
                break
        if owner is None:
            raise RuntimeError(f"Proxy member has no manager: {reference_node}")
        manager = self.managers[owner]
        for member in manager.get("members") or []:
            member_node = member["node"]
            if member_node != reference_node:
                self.references[member_node]["loaded"] = False
        manager["active"] = reference_node
        self.activation_calls.append(reference_node)

    def switch_proxy(self, reference_node: str):
        owner = None
        for manager_name, manager in self.managers.items():
            if any(
                member.get("node") == reference_node
                for member in manager.get("members") or []
            ):
                owner = manager_name
                break
        if owner is None:
            raise RuntimeError(f"Proxy member has no manager: {reference_node}")
        manager = self.managers[owner]
        for member in manager.get("members") or []:
            self.references[member["node"]]["loaded"] = (
                member["node"] == reference_node
            )
        manager["active"] = reference_node
        self.switch_calls.append(reference_node)


def run_reference_loader(
    proxy_cmds: FakeProxyReferenceCmds,
) -> tuple[list[str], dict[str, Any]]:
    runner.cmds = proxy_cmds
    runner._switch_proxy_reference = proxy_cmds.switch_proxy
    reference_job: dict[str, Any] = {"force_high_quality_viewport": True}
    warnings = runner._load_all_references_with_progress(reference_job)
    report = reference_job.get("_reference_report")
    assert isinstance(report, dict)
    return warnings, report


active_proxy_command_model: FakeProxyReferenceCmds | None = None


class FakeMayaMel(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("maya.mel")
        self.commands: list[str] = []

    def eval(self, command: str):
        self.commands.append(command)
        match = re.fullmatch(
            r'proxyActivate\("((?:\\.|[^"])*)",\s*false\)',
            command.strip(),
        )
        if match is None:
            raise RuntimeError(f"Unsafe or unexpected proxy MEL command: {command}")
        if active_proxy_command_model is None:
            raise RuntimeError("No active proxy command model.")
        reference_node = (
            match.group(1).replace('\\"', '"').replace("\\\\", "\\")
        )
        active_proxy_command_model.activate_proxy(reference_node)
        return None


fake_mel = FakeMayaMel()
maya_module.mel = fake_mel
sys.modules["maya.mel"] = fake_mel


def run_safe_reference_loader(
    proxy_cmds: FakeProxyReferenceCmds,
    *,
    force_high_quality: bool,
    job_fields: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    global active_proxy_command_model
    runner.cmds = proxy_cmds
    runner._switch_proxy_reference = production_switch_proxy_reference
    active_proxy_command_model = proxy_cmds
    reference_job: dict[str, Any] = {
        "force_high_quality_viewport": bool(force_high_quality),
        **dict(job_fields or {}),
    }
    warnings = runner._load_all_references_with_progress(reference_job)
    report = reference_job.get("_reference_report")
    assert isinstance(report, dict)
    return warnings, report, reference_job


# One exact high-quality tag owns the proxySwitch. The previously active low
# proxy is unloaded, while unrelated prop/reference nodes and nested references
# discovered after their parent loads continue through the standard path.
exact_proxy_cmds = FakeProxyReferenceCmds(
    {
        "heroProxyManager": {
            "active": "heroLowRN",
            "members": [
                {
                    "node": "heroLowRN",
                    "tag": "low",
                    "loaded": True,
                    "filename": "P:/assets/Hero_low.ma",
                },
                {
                    "node": "heroHighRN",
                    "tag": "HIGH",
                    "loaded": False,
                    "filename": "P:/assets/Hero_high.ma",
                },
            ],
        }
    },
    standard_references=[
        {
            "node": "propRN",
            "loaded": False,
            "filename": "P:/assets/Prop.ma",
            "nested": [
                {
                    "node": "propLookdevRN",
                    "loaded": False,
                    "filename": "P:/assets/Prop_Lookdev.ma",
                }
            ],
        },
        {
            "node": "setDressRN",
            "loaded": False,
            "filename": "P:/assets/SetDress.ma",
        },
    ],
)
exact_warnings, exact_report = run_reference_loader(exact_proxy_cmds)
assert exact_warnings == []
assert exact_proxy_cmds.switch_calls == ["heroHighRN"]
assert exact_proxy_cmds.references["heroHighRN"]["loaded"] is True
assert exact_proxy_cmds.references["heroLowRN"]["loaded"] is False
assert exact_proxy_cmds.unload_calls == ["heroLowRN"]
assert exact_proxy_cmds.references["propRN"]["loaded"] is True
assert exact_proxy_cmds.references["propLookdevRN"]["loaded"] is True
assert exact_proxy_cmds.references["setDressRN"]["loaded"] is True
assert {"propRN", "propLookdevRN", "setDressRN"}.issubset(
    set(exact_proxy_cmds.load_calls)
)
assert exact_report["proxy_set_count"] == 1
assert exact_report["proxy_high_quality_switch_count"] == 1
assert exact_report["proxy_inactive_unload_count"] == 1
assert exact_report["standard_reference_loaded_count"] == 3
assert exact_report["high_quality_unresolved_proxy_sets"] == []
assert exact_report["proxy_sets"] == [
    {
        "proxy_manager": "heroProxyManager",
        "selected_reference": "heroHighRN",
        "selection_reason": "explicit_high_quality_proxy",
        "proxy_tag": "HIGH",
    }
]

# Two equally ranked exact high tags are ambiguous. The authored active member
# is retained for metadata safety, no proxySwitch is attempted, and the set is
# explicitly reported unresolved so Original rendering can fail closed.
ambiguous_proxy_cmds = FakeProxyReferenceCmds(
    {
        "ambiguousProxyManager": {
            "active": "ambiguousLowRN",
            "members": [
                {"node": "ambiguousLowRN", "tag": "low", "loaded": True},
                {"node": "ambiguousHighRN", "tag": "high", "loaded": False},
                {"node": "ambiguousHiresRN", "tag": "hires", "loaded": False},
            ],
        }
    }
)
ambiguous_warnings, ambiguous_report = run_reference_loader(ambiguous_proxy_cmds)
assert ambiguous_proxy_cmds.switch_calls == []
assert ambiguous_proxy_cmds.references["ambiguousLowRN"]["loaded"] is True
assert ambiguous_report["proxy_high_quality_switch_count"] == 0
assert len(ambiguous_report["high_quality_unresolved_proxy_sets"]) == 1
assert ambiguous_report["high_quality_unresolved_proxy_sets"][0] == {
    "proxy_manager": "ambiguousProxyManager",
    "active_reference": "ambiguousLowRN",
    "available_tags": ["low", "high", "hires"],
}
assert any("no unique explicit high-quality tag" in item for item in ambiguous_warnings)
assert ambiguous_report["proxy_sets"][0]["selection_reason"] == (
    "high_quality_proxy_unresolved"
)

# A multi-member proxy set with no recognized high tag follows the same
# unresolved/fail-closed contract; names containing merely "high" as a
# substring are not accepted as exact high-quality tags.
no_high_proxy_cmds = FakeProxyReferenceCmds(
    {
        "noHighProxyManager": {
            "active": "previewRN",
            "members": [
                {"node": "previewRN", "tag": "preview", "loaded": True},
                {
                    "node": "notExactHighRN",
                    "tag": "highest_preview",
                    "loaded": False,
                },
            ],
        }
    }
)
no_high_warnings, no_high_report = run_reference_loader(no_high_proxy_cmds)
assert no_high_proxy_cmds.switch_calls == []
assert no_high_proxy_cmds.references["previewRN"]["loaded"] is True
assert no_high_report["proxy_high_quality_switch_count"] == 0
assert len(no_high_report["high_quality_unresolved_proxy_sets"]) == 1
assert no_high_report["high_quality_unresolved_proxy_sets"][0] == {
    "proxy_manager": "noHighProxyManager",
    "active_reference": "previewRN",
    "available_tags": ["preview", "highest_preview"],
}
assert any("no unique explicit high-quality tag" in item for item in no_high_warnings)
assert no_high_report["proxy_sets"][0]["selection_reason"] == (
    "high_quality_proxy_unresolved"
)


# Exercise the production proxyActivate(..., false) helper itself. It must
# activate without MEL's unsafe auto-load, then perform every selected proxy,
# standard, and nested reference load with executeScriptNodes=False.
safe_exact_cmds = FakeProxyReferenceCmds(
    {
        "safeHeroProxyManager": {
            "active": "safeHeroLowRN",
            "members": [
                {"node": "safeHeroLowRN", "tag": "low", "loaded": True},
                {"node": "safeHeroHighRN", "tag": "high", "loaded": False},
            ],
        }
    },
    standard_references=[
        {
            "node": "safePropRN",
            "loaded": False,
            "nested": [
                {"node": "safeNestedLookRN", "loaded": False},
            ],
        }
    ],
)
safe_exact_warnings, safe_exact_report, _ = run_safe_reference_loader(
    safe_exact_cmds,
    force_high_quality=True,
)
assert safe_exact_warnings == []
assert safe_exact_cmds.activation_calls == ["safeHeroHighRN"]
assert safe_exact_cmds.references["safeHeroHighRN"]["loaded"] is True
assert safe_exact_cmds.references["safeHeroLowRN"]["loaded"] is False
assert safe_exact_cmds.references["safePropRN"]["loaded"] is True
assert safe_exact_cmds.references["safeNestedLookRN"]["loaded"] is True
assert safe_exact_report["failed_references"] == []
safe_load_calls = [
    item for item in safe_exact_cmds.file_calls if item.get("loadReference")
]
assert {
    item["loadReference"] for item in safe_load_calls
} == {"safeHeroHighRN", "safePropRN", "safeNestedLookRN"}
assert all(item.get("executeScriptNodes") is False for item in safe_load_calls)
assert fake_mel.commands[-1] == 'proxyActivate("safeHeroHighRN", false)'

# A damaged scene can have the selected exact-high member already loaded while
# proxyManager.activeProxy still points at low. Loaded state alone is not
# readiness: the loader must activate high and validate exclusive membership.
damaged_cmds = FakeProxyReferenceCmds(
    {
        "damagedProxyManager": {
            "active": "damagedLowRN",
            "members": [
                {"node": "damagedLowRN", "tag": "low", "loaded": True},
                {"node": "damagedHighRN", "tag": "high", "loaded": True},
            ],
        }
    }
)
damaged_warnings, damaged_report, _ = run_safe_reference_loader(
    damaged_cmds,
    force_high_quality=True,
)
assert damaged_warnings == []
assert damaged_cmds.activation_calls == ["damagedHighRN"]
assert damaged_cmds.managers["damagedProxyManager"]["active"] == "damagedHighRN"
assert damaged_cmds.references["damagedHighRN"]["loaded"] is True
assert damaged_cmds.references["damagedLowRN"]["loaded"] is False
assert damaged_cmds.unload_calls == ["damagedLowRN"]
assert damaged_report["failed_references"] == []
assert damaged_report["high_quality_unresolved_proxy_sets"] == []
assert damaged_report["proxy_sets"][0]["selected_reference"] == "damagedHighRN"


def best_effort_original_message(reference_job: dict[str, Any]) -> str:
    restore, report = runner._apply_full_smooth_viewport(reference_job)
    assert runner._restore_full_smooth_viewport(restore) == []
    return " | ".join(report.get("warnings") or [])


# A selected high proxy that cannot complete its safe load remains an explicit
# quality warning, with the exact reference recorded for diagnostics.
failed_high_cmds = FakeProxyReferenceCmds(
    {
        "failedHighProxyManager": {
            "active": "failedLowRN",
            "members": [
                {"node": "failedLowRN", "tag": "low", "loaded": True},
                {
                    "node": "failedHighRN",
                    "tag": "high",
                    "loaded": False,
                    "filename": "P:/assets/Failed_High.ma",
                },
            ],
        }
    },
    fail_load_nodes={"failedHighRN"},
)
failed_high_warnings, failed_high_report, failed_high_job = (
    run_safe_reference_loader(
        failed_high_cmds,
        force_high_quality=True,
    )
)
assert any("Failed_High.ma" in item for item in failed_high_warnings)
assert failed_high_report["failed_references"] == [
    {
        "reference_kind": "proxy",
        "proxy_manager": "failedHighProxyManager",
        "reference_node": "failedHighRN",
        "reference_file": "P:/assets/Failed_High.ma",
        "error": "intentional safe-load failure for failedHighRN",
    }
]
assert failed_high_report["high_quality_unresolved_proxy_sets"]
failed_high_message = best_effort_original_message(failed_high_job)
assert "Failed_High.ma" in failed_high_message
assert "will continue with the loaded authored-visible scene" in failed_high_message
assert all(
    item.get("executeScriptNodes") is False
    for item in failed_high_cmds.file_calls
    if item.get("loadReference")
)

# An unrelated standard prop load failure is also advisory to the capture while
# remaining visible in diagnostics.
failed_prop_cmds = FakeProxyReferenceCmds(
    {},
    standard_references=[
        {
            "node": "failedPropRN",
            "loaded": False,
            "filename": "P:/assets/Failed_Prop.ma",
        }
    ],
    fail_load_nodes={"failedPropRN"},
)
failed_prop_warnings, failed_prop_report, failed_prop_job = (
    run_safe_reference_loader(
        failed_prop_cmds,
        force_high_quality=True,
    )
)
assert any("Failed_Prop.ma" in item for item in failed_prop_warnings)
assert failed_prop_report["failed_references"] == [
    {
        "reference_kind": "standard",
        "proxy_manager": "",
        "reference_node": "failedPropRN",
        "reference_file": "P:/assets/Failed_Prop.ma",
        "error": "intentional safe-load failure for failedPropRN",
    }
]
failed_prop_message = best_effort_original_message(failed_prop_job)
assert "Failed_Prop.ma" in failed_prop_message
assert "will continue with the loaded authored-visible scene" in failed_prop_message

# READ remains metadata-only and reports a failed reference as a warning.
for non_original_fields in ({"operation": "scan"},):
    warning_cmds = FakeProxyReferenceCmds(
        {},
        standard_references=[
            {
                "node": "warningPropRN",
                "loaded": False,
                "filename": "P:/assets/Warning_Prop.ma",
            }
        ],
        fail_load_nodes={"warningPropRN"},
    )
    warning_rows, warning_report, warning_job = run_safe_reference_loader(
        warning_cmds,
        force_high_quality=False,
        job_fields=non_original_fields,
    )
    assert len(warning_rows) == 1
    assert "Warning_Prop.ma" in warning_rows[0]
    assert warning_report["failed_references"][0]["reference_node"] == (
        "warningPropRN"
    )
    assert warning_job["force_high_quality_viewport"] is False
    assert all(
        item.get("executeScriptNodes") is False
        for item in warning_cmds.file_calls
        if item.get("loadReference")
    )

# Color reports the same best-effort quality warning as Original; a missing
# optional reference does not become a tool-execution policy.
color_failed_cmds = FakeProxyReferenceCmds(
    {},
    standard_references=[
        {
            "node": "colorFailedPropRN",
            "loaded": False,
            "filename": "P:/assets/Color_Failed_Prop.ma",
        }
    ],
    fail_load_nodes={"colorFailedPropRN"},
)
_, color_failed_report, color_failed_job = run_safe_reference_loader(
    color_failed_cmds,
    force_high_quality=True,
    job_fields={"operation": "render", "apply_marker_shaders": True},
)
assert color_failed_report["failed_references"]
assert "Color_Failed_Prop.ma" in best_effort_original_message(color_failed_job)

runner.cmds = fake_cmds
runner._switch_proxy_reference = production_switch_proxy_reference
active_proxy_command_model = None

print(
    "HMB VideoPicker best-effort full-smooth viewport, bbox/LOD restore, "
    "safe proxyActivate/reference diagnostics, nonblocking quality warnings, damaged-state "
    "repair, nested-reference loading, cache-profile invalidation, and "
    "metadata-only READ isolation regression: PASS"
)
