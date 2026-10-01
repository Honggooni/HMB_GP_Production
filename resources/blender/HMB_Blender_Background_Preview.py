"""Background Blender worker for HMBVideoPickerLibrary.

The Picker owns UI, Shot assignment, FFmpeg encoding, and publication.  This
worker only reads one .blend file and writes transient PNG frames plus JSON to
the Picker's private job directory.  It never saves the source .blend file.

Invoke with automatic .blend scripts disabled *before* loading the scene::

    blender --background --factory-startup --disable-autoexec --python-exit-code 5 \
        scene.blend --python HMB_Blender_Background_Preview.py -- job.json
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import traceback

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


DEPTH_PROFILE = "hmb_blender_camera_depth_v1"
MOTION_PROFILE = "hmb_blender_motion_guide_v1"
COLOR_PROFILE = "hmb_blender_workbench_flat_markers_v1"
PATTERN_PROFILE = "hmb_blender_eevee_world_patterns_v1"
ORIGINAL_PROFILE = "hmb_blender_workbench_midgray_v1"
RENDER_TYPES = frozenset({"MESH", "CURVE", "SURFACE", "META", "FONT"})
MAX_DIMENSION = 8192
MAX_FRAMES = 1000001


def _clean(value):
    return str(value or "").strip()


def _write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        # Windows may deny a replace while the Picker momentarily has the
        # progress/result JSON open for polling.  Retry the same staged file.
        for attempt in range(40):
            try:
                os.replace(staged, target)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.025)
    finally:
        staged.unlink(missing_ok=True)


def _progress(job, stage, message, **extra):
    print("[HMBVideoPicker][BLENDER][{}] {}".format(stage, message), flush=True)
    path = _clean(job.get("progress_path"))
    if path:
        payload = {"stage": stage, "message": message, "time": time.time()}
        payload.update(extra)
        try:
            _write_json(path, payload)
        except OSError as exc:
            # A locked status file must not invalidate completed render files.
            print("[HMBVideoPicker][BLENDER][progress_warning] {}".format(exc), flush=True)


def _read_job(job_path):
    raw = Path(job_path).read_bytes()
    expected = _clean(os.environ.get("HMB_VIDEO_PICKER_JOB_SHA256")).lower()
    if expected and hashlib.sha256(raw).hexdigest().lower() != expected:
        raise RuntimeError("Blender job integrity check failed.")
    job = json.loads(raw.decode("utf-8"))
    if not isinstance(job, dict):
        raise ValueError("Blender job must be a JSON object.")
    root = Path(job_path).resolve(strict=True).parent
    for field in (
        "result_path", "progress_path", "frames_folder", "sidecar_path",
        "depth_frames_folder", "depth_sidecar_path",
        "motion_guide_frames_folder", "motion_guide_sidecar_path",
    ):
        value = _clean(job.get(field))
        if not value:
            continue
        target = Path(value).resolve(strict=False)
        if target != root and root not in target.parents:
            raise ValueError("Blender {} must remain in the private job folder.".format(field))
        for parent in (target, *target.parents):
            if parent == root.parent:
                break
            if parent.is_symlink():
                raise ValueError("Linked Blender job output path is not allowed: {}".format(field))
    if not _clean(job.get("result_path")):
        raise ValueError("Blender job has no result_path.")
    return job


def _validate_scene(job):
    requested = Path(_clean(job.get("scene_path"))).resolve(strict=True)
    opened = Path(bpy.data.filepath).resolve(strict=True) if bpy.data.filepath else None
    if requested.suffix.lower() != ".blend":
        raise ValueError("Blender worker accepts only .blend scene files.")
    if opened != requested:
        raise RuntimeError("The scene loaded by Blender differs from the Picker job scene.")
    return requested


def _object_path(obj):
    names = []
    current = obj
    while current is not None:
        names.append(current.name)
        current = current.parent
    return "|" + "|".join(reversed(names))


def _stable_identity(obj):
    """Use a reproducible scene-qualified key in the Picker's legacy UUID slot."""
    scene_key = str(Path(bpy.data.filepath).resolve(strict=False)).casefold()
    library_key = (
        str(Path(bpy.path.abspath(obj.library.filepath)).resolve(strict=False)).casefold()
        if obj.library else ""
    )
    raw = "blender\0{}\0{}\0{}".format(scene_key, library_key, _object_path(obj))
    return "blender-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _object_index():
    return {_object_path(obj): obj for obj in bpy.context.scene.objects}


@lru_cache(maxsize=1)
def _render_collection_membership():
    """Collections accepted by the active render view layer, including parents."""
    allowed = set()

    def visit(layer, enabled):
        collection = layer.collection
        enabled = enabled and not layer.exclude and not collection.hide_render
        if enabled:
            allowed.add(collection.as_pointer())
        for child in layer.children:
            visit(child, enabled)

    visit(bpy.context.view_layer.layer_collection, True)
    return allowed


def _visible(obj):
    current = obj
    while current is not None:
        if current.hide_render or current.hide_viewport:
            return False
        current = current.parent
    allowed = _render_collection_membership()
    if not any(collection.as_pointer() in allowed for collection in obj.users_collection):
        return False
    try:
        return bool(obj.visible_get())
    except Exception:
        return True


def _scene_cameras():
    scene = bpy.context.scene
    records = []
    for obj in sorted(scene.objects, key=_object_path):
        if obj.type != "CAMERA":
            continue
        records.append({
            "name": obj.name,
            "full_path": _object_path(obj),
            "maya_uuid": _stable_identity(obj),
            "renderable": _visible(obj),
            "registered": obj == scene.camera,
            "default_camera": False,
        })
    records.sort(key=lambda row: (not row["registered"], not row["renderable"], row["full_path"]))
    return records


def _resolve_camera(job):
    requested = _clean(job.get("camera"))
    cameras = [obj for obj in bpy.context.scene.objects if obj.type == "CAMERA"]
    if requested:
        found = [obj for obj in cameras if _object_path(obj) == requested]
        if not found:
            found = [obj for obj in cameras if obj.name == requested]
        if len(found) != 1:
            raise RuntimeError("Selected Blender camera is missing or ambiguous: {}".format(requested))
        return found[0]
    if bpy.context.scene.camera in cameras:
        return bpy.context.scene.camera
    if len(cameras) == 1:
        return cameras[0]
    if not cameras:
        raise RuntimeError("Blender scene has no camera. Set a scene camera before rendering.")
    raise RuntimeError("Blender scene has multiple cameras. Select one in the Picker.")


def _dependencies():
    paths = set()
    warnings = []
    for library in bpy.data.libraries:
        if library.filepath:
            paths.add(bpy.path.abspath(library.filepath))
    for image in bpy.data.images:
        if image.source == "FILE" and image.filepath:
            paths.add(bpy.path.abspath(image.filepath, library=image.library))
    for path in sorted(paths):
        if not Path(path).exists():
            warnings.append("Missing external Blender dependency: {}".format(path))
    return [str(Path(path).resolve(strict=False)).replace("\\", "/") for path in sorted(paths)], warnings


def _script_safety_report():
    """Refuse previews that could silently omit unsafe .blend animation code."""
    scripted = []
    seen = set()
    for family in (
        "objects", "meshes", "curves", "cameras", "lights", "armatures",
        "shape_keys", "materials", "node_groups", "worlds", "scenes",
        "collections", "textures", "images", "grease_pencils_v3",
    ):
        datablocks = getattr(bpy.data, family, ())
        for datablock in datablocks:
            pointer = datablock.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            animation = getattr(datablock, "animation_data", None)
            for curve in getattr(animation, "drivers", ()) if animation else ():
                if curve.driver.type == "SCRIPTED":
                    scripted.append("{}:{}:{}".format(family, datablock.name, curve.data_path))
    return {
        "autoexec_disabled": True,
        "autoexec_blocked": bool(getattr(bpy.app, "autoexec_fail", False)),
        "autoexec_message": _clean(getattr(bpy.app, "autoexec_fail_message", "")),
        "scripted_driver_count": len(scripted),
        "scripted_driver_examples": scripted[:10],
    }


def _scan(job, scene_path):
    scene = bpy.context.scene
    _progress(job, "collecting_meshes", "Collecting Blender renderable objects.")
    geometry = [obj for obj in scene.objects if obj.type in RENDER_TYPES]
    roots = {}
    for obj in geometry:
        root = obj
        while root.parent is not None:
            root = root.parent
        roots.setdefault(root, []).append(obj)
    outliner = []
    for root, meshes in sorted(roots.items(), key=lambda row: _object_path(row[0])):
        root_path = _object_path(root)
        visible = [obj for obj in meshes if _visible(obj)]
        children = []
        for obj in sorted(meshes, key=_object_path):
            if obj == root:
                continue
            children.append({
                "name": obj.name,
                "full_path": _object_path(obj),
                "parent_path": root_path,
                "node_kind": "mesh",
                "maya_uuid": _stable_identity(obj),
            })
        outliner.append({
            "name": root.name,
            "dag_name": root.name,
            "full_path": root_path,
            "parent_path": "",
            "depth": 0,
            "source_depth": root_path.count("|"),
            "maya_uuid": _stable_identity(root),
            "namespace": "",
            "child_count": len(children),
            "direct_shape_count": int(root.type in RENDER_TYPES),
            "descendant_shape_count": len(meshes),
            "mesh_count": len(meshes),
            "has_renderable_shapes": bool(meshes),
            "referenced": bool(root.library),
            "reference_node": "",
            "reference_file": bpy.path.abspath(root.library.filepath) if root.library else "",
            "proxy_manager": "",
            "proxy_tag": "",
            "node_kind": "asset_root",
            "asset_root": True,
            "depth_meshes": children,
            "outliner_filter": "asset_roots_v1",
            "scene_visible": bool(visible),
            "visible_shape_count": len(visible),
            "visibility_status": "visible" if visible else "self_hidden",
            "visibility_driven": False,
        })
    cameras = _scene_cameras()
    selected = _object_path(scene.camera) if scene.camera and scene.camera.type == "CAMERA" else ""
    requested = _clean(job.get("camera"))
    if requested and requested in {row["full_path"] for row in cameras}:
        selected = requested
    if not selected and len(cameras) == 1:
        selected = cameras[0]["full_path"]
    dependencies, warnings = _dependencies()
    script_report = _script_safety_report()
    if script_report["autoexec_blocked"]:
        warnings.append("Blender blocked automatic script execution; render output may be incomplete.")
    if script_report["scripted_driver_count"]:
        warnings.append("Blender scene contains scripted drivers; background preview refuses to execute them.")
    if not selected:
        warnings.append("No unambiguous active Blender camera; choose a camera before rendering.")
    if job.get("generate_original_video"):
        warnings.append("READ is metadata-only; create Original separately.")
    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    result = {
        "ok": True,
        "operation": "scan",
        "blender_version": bpy.app.version_string,
        "scene_path": str(scene_path).replace("\\", "/"),
        "scene": scene_path.name,
        "outliner_nodes": outliner,
        "cameras": cameras,
        "selected_camera": selected,
        "original_frames_folder": "",
        "original_output_name": "",
        "original_frame_map": [],
        "original_frame_count": 0,
        "warnings": warnings,
        "group_count": len(outliner),
        "start_frame": float(scene.frame_start),
        "end_frame": float(scene.frame_end),
        "current_frame": float(scene.frame_current) + float(scene.frame_subframe),
        "fps": fps,
        "scene_dependency_paths": dependencies,
        "script_node_report": script_report,
    }
    _write_json(job["result_path"], result)
    _progress(job, "scan_complete", "Blender READ completed without rendering.", group_count=len(outliner), camera_count=len(cameras))
    return result


def _catalog(job):
    path = Path(_clean(job.get("marker_catalog_path"))) if job.get("marker_catalog_path") else Path(__file__).resolve().parents[1] / "picker" / "HMB_Marker_Catalog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    markers = {}
    for row in list(payload.get("character", [])) + list(payload.get("background", [])):
        if isinstance(row, dict) and row.get("name"):
            markers[row["name"]] = row
    return payload, markers


def _bindings(job, objects, markers):
    rows = job.get("bindings") or []
    if not isinstance(rows, list):
        raise ValueError("Blender marker bindings must be a list.")
    resolved = []
    used = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not row.get("enabled", True):
            continue
        color = _clean(row.get("color"))
        path = _clean(row.get("full_dag_path") or row.get("subject_root"))
        if not path and not color:
            continue
        if color not in markers:
            raise ValueError("Unsupported Blender marker color on row {}: {}".format(index, color))
        kind = markers[color].get("kind")
        if kind not in {"solid", "pattern"}:
            raise RuntimeError("Unsupported Blender marker kind for '{}'.".format(color))
        obj = objects.get(path)
        if obj is None:
            candidates = [item for item in objects.values() if item.name == path or item.name == _clean(row.get("group_name"))]
            if len(candidates) == 1:
                obj = candidates[0]
        if obj is None:
            raise RuntimeError("Blender marker target is missing: {}".format(path or row.get("group_name")))
        full_path = _object_path(obj)
        if full_path in used:
            raise RuntimeError("Blender marker target is assigned more than once: {}".format(full_path))
        used.add(full_path)
        resolved.append({
            "group_name": _clean(row.get("group_name")) or obj.name,
            "asset_id": _clean(row.get("asset_id")) or obj.name,
            "full_dag_path": full_path,
            "subject_root": full_path,
            "color": color,
            "kind": kind,
            "rgb": [float(value) for value in markers[color].get("rgb", (0.0, 0.0, 0.0))],
            "pattern": _clean(markers[color].get("pattern")),
            "picker_order": int(row.get("picker_order") or index),
        })
    if not resolved:
        raise RuntimeError("Assign at least one Blender object a solid marker before generating Mask.")
    return resolved


def _frame_values(job, scene):
    first = float(scene.frame_start if job.get("start_frame") is None else job["start_frame"])
    last = float(scene.frame_end if job.get("end_frame") is None else job["end_frame"])
    if not math.isfinite(first) or not math.isfinite(last) or last < first:
        raise ValueError("Invalid Blender frame range.")
    whole_steps = int(last - first + 1e-9)
    frames = [first + index for index in range(whole_steps + 1)]
    if not frames or abs(frames[-1] - last) > 1e-6:
        frames.append(last)
    max_frames = max(1, int(os.environ.get("HMB_MAX_PLAYBLAST_FRAMES", str(MAX_FRAMES))))
    if len(frames) > max_frames:
        raise ValueError("Blender render exceeds the {} frame safety budget.".format(max_frames))
    return frames


def _set_frame(scene, value):
    integer = math.floor(value)
    scene.frame_set(integer, subframe=value - integer)


def _visible_scope(job, bindings, objects):
    hidden = set(_clean(path) for path in job.get("hidden_paths", []) if _clean(path))
    marker_by_path = {row["full_dag_path"]: row for row in bindings}
    active = {}
    for path, obj in objects.items():
        if obj.type not in RENDER_TYPES:
            continue
        if not _visible(obj):
            continue
        if any(path == off or path.startswith(off + "|") for off in hidden):
            continue
        choice = ""
        for root_path in marker_by_path:
            if path == root_path or path.startswith(root_path + "|"):
                if len(root_path) > len(choice):
                    choice = root_path
        if choice:
            active[path] = marker_by_path[choice]
    if not active:
        raise RuntimeError("No visible Blender geometry belongs to the selected solid marker bindings.")
    for path, obj in objects.items():
        if obj.type in RENDER_TYPES:
            obj.hide_render = path not in active
    return active, sorted(hidden)


def _configure_workbench(scene, marker_mode, active):
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT" if marker_mode else "STUDIO"
    shading.color_type = "OBJECT"
    shading.single_color = (0.72, 0.72, 0.72)
    shading.background_type = "WORLD"
    if not marker_mode:
        # The Original preview must show neutral geometry, not a uniform gray
        # frame when the authored world background is itself midgray.
        shading.background_color = (0.015, 0.020, 0.030)
        if scene.world is not None:
            scene.world.color = (0.015, 0.020, 0.030)
    shading.show_shadows = False
    shading.show_cavity = not marker_mode
    shading.show_specular_highlight = False
    shading.show_object_outline = False
    scene.render.film_transparent = False
    objects = _object_index()
    for path, row in active.items():
        obj = objects[path]
        if marker_mode:
            obj.color = (*row["rgb"], 1.0)
        else:
            # Unlike Maya VP2's shaded Lambert override, Workbench's uniform
            # single gray erases a product on an equally gray studio floor.
            # Retain texture-free, neutral grayscale separation from authored
            # material luminance while changing only this unsaved process.
            materials = getattr(obj.data, "materials", ())
            authored = next((item for item in materials if item is not None), None)
            if authored is None:
                gray = 0.55
            else:
                red, green, blue = authored.diffuse_color[:3]
                luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                gray = min(0.88, max(0.16, 0.12 + 0.95 * luminance))
            obj.color = (gray, gray, gray, 1.0)


def _pattern_material(marker):
    """Blender-native, world-space marker appearance; never claims Maya parity."""
    material = bpy.data.materials.new("HMB_Blender_Temporary_{}".format(marker["color"].replace(" ", "_")))
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    links = material.node_tree.links
    emission = nodes.new("ShaderNodeEmission")
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    if marker["kind"] == "solid":
        emission.inputs["Color"].default_value = (*marker["rgb"], 1.0)
        return material

    position = nodes.new("ShaderNodeNewGeometry")
    pattern = marker["pattern"]
    if pattern == "direction_checker":
        checker = nodes.new("ShaderNodeTexChecker")
        checker.inputs["Color1"].default_value = (1.0, 0.0, 1.0, 1.0)
        checker.inputs["Color2"].default_value = (0.0, 1.0, 0.9, 1.0)
        checker.inputs["Scale"].default_value = 4.0
        links.new(position.outputs["Position"], checker.inputs["Vector"])
        links.new(checker.outputs["Color"], emission.inputs["Color"])
        return material
    if pattern in {"sky_grid", "floor_grid"}:
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        scale.inputs[3].default_value = 3.0
        links.new(position.outputs["Position"], scale.inputs[0])
        split = nodes.new("ShaderNodeSeparateXYZ")
        links.new(scale.outputs["Vector"], split.inputs["Vector"])
        axes = ("X", "Z") if pattern == "sky_grid" else ("X", "Y")
        grid_lines = []
        for axis in axes:
            repeat = nodes.new("ShaderNodeMath")
            repeat.operation = "PINGPONG"
            repeat.inputs[1].default_value = 0.5
            links.new(split.outputs[axis], repeat.inputs[0])
            line = nodes.new("ShaderNodeMath")
            line.operation = "LESS_THAN"
            line.inputs[1].default_value = 0.035
            links.new(repeat.outputs[0], line.inputs[0])
            grid_lines.append(line)
        either = nodes.new("ShaderNodeMath")
        either.operation = "MAXIMUM"
        links.new(grid_lines[0].outputs[0], either.inputs[0])
        links.new(grid_lines[1].outputs[0], either.inputs[1])
        blend = nodes.new("ShaderNodeMixRGB")
        blend.inputs[1].default_value = (
            (0.04, 0.12, 0.36, 1.0) if pattern == "sky_grid"
            else (0.31, 0.23, 0.10, 1.0)
        )
        blend.inputs[2].default_value = (
            (0.1, 0.87, 1.0, 1.0) if pattern == "sky_grid"
            else (1.0, 0.83, 0.3, 1.0)
        )
        links.new(either.outputs[0], blend.inputs[0])
        links.new(blend.outputs[0], emission.inputs["Color"])
        return material
    if pattern == "position_pattern":
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 3.0
        links.new(position.outputs["Position"], noise.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.1, 0.3, 1.0, 1.0)
        ramp.color_ramp.elements[1].color = (1.0, 0.85, 0.1, 1.0)
        middle = ramp.color_ramp.elements.new(0.5)
        middle.color = (0.1, 0.95, 0.6, 1.0)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], emission.inputs["Color"])
        return material
    raise RuntimeError("Unknown Blender marker pattern: {}".format(pattern))


def _configure_pattern_eevee(scene, active, objects):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Raw"
    scene.use_nodes = False
    cache = {}
    for path, marker in active.items():
        key = marker["color"]
        material = cache.get(key)
        if material is None:
            material = _pattern_material(marker)
            cache[key] = material
        obj = objects[path]
        if not hasattr(obj.data, "materials"):
            raise RuntimeError("Blender object cannot receive the selected pattern material: {}".format(path))
        # Mesh data can be shared across instances.  Copy only in this unsaved
        # background process so each assigned object retains its own marker.
        obj.data = obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(material)
    world = scene.world
    if world and world.use_nodes:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                node.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                node.inputs["Strength"].default_value = 0.0


def _depth_range(scene, camera, active, frames, objects):
    """Use every requested evaluated frame, not only the last camera pose."""
    minimum = math.inf
    maximum = -math.inf
    for frame in frames:
        _set_frame(scene, frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        inverse = camera.evaluated_get(depsgraph).matrix_world.inverted()
        for path in active:
            evaluated = objects[path].evaluated_get(depsgraph)
            for corner in evaluated.bound_box:
                world = evaluated.matrix_world @ Vector(corner)
                distance = -(inverse @ world).z
                if math.isfinite(distance) and distance > 0:
                    minimum = min(minimum, distance)
                    maximum = max(maximum, distance)
    if not math.isfinite(minimum):
        raise RuntimeError("Visible Blender geometry is not in front of the selected camera; Depth cannot be generated.")
    near = max(float(camera.data.clip_start), minimum)
    far = min(float(camera.data.clip_end), maximum)
    if far <= near + 1e-4:
        far = near + max(0.01, near * 0.05)
    return near, far


def _configure_depth(scene, near, far):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "Raw"
    material = bpy.data.materials.new("HMB_Blender_Temporary_Camera_Depth")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    camera_data = nodes.new("ShaderNodeCameraData")
    mapping = nodes.new("ShaderNodeMapRange")
    mapping.inputs["From Min"].default_value = near
    mapping.inputs["From Max"].default_value = far
    mapping.inputs["To Min"].default_value = 1.0
    mapping.inputs["To Max"].default_value = 0.0
    mapping.clamp = True
    emission = nodes.new("ShaderNodeEmission")
    output = nodes.new("ShaderNodeOutputMaterial")
    links = material.node_tree.links
    links.new(camera_data.outputs["View Z Depth"], mapping.inputs["Value"])
    links.new(mapping.outputs["Result"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    for layer in scene.view_layers:
        layer.material_override = material
    world = scene.world
    if world is not None:
        world.color = (0.0, 0.0, 0.0)
        if world.use_nodes:
            for node in world.node_tree.nodes:
                if node.type == "BACKGROUND":
                    node.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                    node.inputs["Strength"].default_value = 0.0


def _render_png(scene, path):
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    bpy.ops.render.render(write_still=True)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Blender did not write PNG frame: {}".format(path))


def _render_sequence(job, scene, frames, folder, name, stage):
    output = Path(folder)
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Blender refuses to replace a nonempty frame directory: {}".format(output))
    output.mkdir(parents=True, exist_ok=True)
    mapping = []
    for index, frame in enumerate(frames):
        _set_frame(scene, frame)
        target = output / "{}.{:06d}.png".format(name, index)
        _progress(job, stage, "Rendering Blender frame {} of {}.".format(index + 1, len(frames)), completed_frames=index, frame_count=len(frames), blender_frame=frame)
        _render_png(scene, target)
        mapping.append({"sequence_index": index, "blender_frame": frame, "maya_frame": frame, "file": target.name})
        _progress(job, stage, "Rendered Blender frame {} of {}.".format(index + 1, len(frames)), completed_frames=index + 1, frame_count=len(frames), blender_frame=frame, output_file=target.name)
    return mapping


def _motion_points(scene, camera, objects, active):
    points = []
    segments = []
    for root_path in sorted(set(row["full_dag_path"] for row in active.values())):
        root = objects.get(root_path)
        if root is None:
            continue
        local_points = []
        if root.type == "ARMATURE":
            armatures = [root]
        else:
            armatures = [obj for obj in root.children_recursive if obj.type == "ARMATURE"]
        for armature in armatures:
            for bone in armature.pose.bones:
                start = armature.matrix_world @ bone.head
                end = armature.matrix_world @ bone.tail
                local_points.extend((start, end))
                segments.append((start, end, len(points) % 7))
        if not local_points:
            local_points.append(root.matrix_world.translation.copy())
        points.extend(local_points)
    projected = []
    for point in points:
        ndc = world_to_camera_view(scene, camera, point)
        if ndc.z > 0:
            projected.append((ndc.x, ndc.y))
    line_points = []
    for start, end, color_index in segments:
        a = world_to_camera_view(scene, camera, start)
        b = world_to_camera_view(scene, camera, end)
        if a.z > 0 and b.z > 0:
            line_points.append(((a.x, a.y), (b.x, b.y), color_index))
    return projected, line_points, len(segments)


def _draw_line(array, a, b, rgb):
    height, width = array.shape[:2]
    x0, y0 = int(a[0] * (width - 1)), int(a[1] * (height - 1))
    x1, y1 = int(b[0] * (width - 1)), int(b[1] * (height - 1))
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for index in range(steps + 1):
        x = round(x0 + (x1 - x0) * index / steps)
        y = round(y0 + (y1 - y0) * index / steps)
        if 0 <= x < width and 0 <= y < height:
            array[max(0, y - 1):min(height, y + 2), max(0, x - 1):min(width, x + 2), :3] = rgb


def _render_motion(job, scene, camera, objects, active, frames, width, height):
    import numpy as np

    folder = Path(job["motion_guide_frames_folder"])
    if folder.exists() and any(folder.iterdir()):
        raise RuntimeError("Blender refuses to replace nonempty Motion Guide frame directory.")
    folder.mkdir(parents=True, exist_ok=True)
    name = _clean(job.get("motion_guide_output_name")) or "motion_guide"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("Unsafe Blender Motion Guide output name.")
    palette = ((0.0, 1.0, 0.3), (0.1, 0.8, 1.0), (1.0, 0.8, 0.1), (1.0, 0.2, 0.5), (0.7, 0.4, 1.0))
    mapping = []
    rendered_bones = 0
    last_point_positions = None
    motion_detected = False
    for index, frame in enumerate(frames):
        _set_frame(scene, frame)
        points, segments, bone_count = _motion_points(scene, camera, objects, active)
        rendered_bones = max(rendered_bones, bone_count)
        if not points and not segments:
            raise RuntimeError("Blender Motion Guide has no projected rig or object anchors in the camera frame.")
        if last_point_positions is not None and points != last_point_positions:
            motion_detected = True
        last_point_positions = points
        pixels = np.zeros((height, width, 4), dtype=np.float32)
        pixels[:, :, 3] = 1.0
        for start, end, color_index in segments:
            _draw_line(pixels, start, end, palette[color_index % len(palette)])
        for number, point in enumerate(points):
            x = round(point[0] * (width - 1))
            y = round(point[1] * (height - 1))
            if 0 <= x < width and 0 <= y < height:
                pixels[max(0, y - 3):min(height, y + 4), max(0, x - 3):min(width, x + 4), :3] = palette[number % len(palette)]
        image = bpy.data.images.new("HMB_Motion_{:06d}".format(index), width=width, height=height, alpha=True, float_buffer=False)
        try:
            image.pixels.foreach_set(pixels.ravel())
            target = folder / "{}.{:06d}.png".format(name, index)
            image.filepath_raw = str(target)
            image.file_format = "PNG"
            image.save()
        finally:
            bpy.data.images.remove(image)
        if not target.is_file() or target.stat().st_size <= 0:
            raise RuntimeError("Blender Motion Guide PNG was not produced.")
        mapping.append({"sequence_index": index, "blender_frame": frame, "maya_frame": frame, "file": target.name})
        _progress(job, "rendering_motion_guide", "Rendered Blender Motion Guide frame {} of {}.".format(index + 1, len(frames)), completed_frames=index + 1, frame_count=len(frames), blender_frame=frame)
    return mapping, {"armature_bone_count": rendered_bones, "motion_detected": motion_detected, "guide_semantics": "camera_projected_armature_bones_and_rigid_object_anchors", "face_semantics": "not_supported"}


def _render(job, scene_path):
    scene = bpy.context.scene
    script_report = _script_safety_report()
    if script_report["autoexec_blocked"]:
        raise RuntimeError("Blender blocked automatic scene script execution; preview cannot verify complete animation with --disable-autoexec.")
    if script_report["scripted_driver_count"]:
        raise RuntimeError("Blender scene has {} scripted driver(s); preview cannot safely verify their animation with --disable-autoexec.".format(script_report["scripted_driver_count"]))
    camera = _resolve_camera(job)
    scene.camera = camera
    width = int(job.get("width") or 1280)
    height = int(job.get("height") or 720)
    if min(width, height) <= 0 or max(width, height) > MAX_DIMENSION:
        raise ValueError("Invalid Blender render dimensions.")
    frames = _frame_values(job, scene)
    fps = float(job.get("fps") or scene.render.fps / (scene.render.fps_base or 1.0))
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("Invalid Blender FPS.")
    name = _clean(job.get("output_name")) or "hmb_preview"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("Unsafe Blender output name.")
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    objects = _object_index()
    marker_mode = bool(job.get("apply_marker_shaders", True))
    depth_requested = bool(job.get("generate_depth_playblast"))
    motion_requested = bool(job.get("generate_motion_guide"))
    if job.get("screen_space_patterns"):
        raise RuntimeError("Maya screen-space patterns are not supported for Blender input.")
    catalog, markers = _catalog(job)
    bindings = _bindings(job, objects, markers) if marker_mode else []
    uses_patterns = False
    if marker_mode:
        active, hidden = _visible_scope(job, bindings, objects)
        uses_patterns = any(row["kind"] == "pattern" for row in active.values())
        if uses_patterns:
            _configure_pattern_eevee(scene, active, objects)
        else:
            _configure_workbench(scene, True, active)
    else:
        hidden = []
        active = {path: {"rgb": (0.5, 0.5, 0.5)} for path, obj in objects.items() if obj.type in RENDER_TYPES and _visible(obj)}
        if not active:
            raise RuntimeError("Blender scene has no visible renderable geometry.")
        _configure_workbench(scene, False, active)
    if depth_requested and not marker_mode:
        raise RuntimeError("Blender Depth must accompany an assigned Mask render.")
    if motion_requested and not marker_mode:
        raise RuntimeError("Blender Motion Guide must accompany an assigned Mask render.")
    _progress(job, "rendering_frames", "Rendering Blender {} frames.".format("Mask" if marker_mode else "Original"), frame_count=len(frames), completed_frames=0)
    frame_map = _render_sequence(job, scene, frames, job["frames_folder"], name, "rendering_frames")
    dependencies, dependency_warnings = _dependencies()
    warnings = list(dependency_warnings)
    profile = (PATTERN_PROFILE if uses_patterns else COLOR_PROFILE) if marker_mode else ORIGINAL_PROFILE
    result = {
        "ok": True,
        "operation": _clean(job.get("operation")) or "render",
        "blender_version": bpy.app.version_string,
        "camera": _object_path(camera),
        "fps": fps,
        "frame_count": len(frame_map),
        "frames_folder": str(Path(job["frames_folder"]).resolve()).replace("\\", "/"),
        "sidecar_path": str(Path(job["sidecar_path"]).resolve()).replace("\\", "/"),
        "frame_map": frame_map,
        "warnings": warnings,
        "render_profile": profile,
        "artifacts": {
            "color": {"requested": True, "ok": True, "error": ""},
            "depth": {"requested": depth_requested, "ok": False, "error": ""},
            "motion_guide": {"requested": motion_requested, "ok": False, "error": ""},
        },
    }
    sidecar = {
        "schema": "hmb-blender-picker-render",
        "schema_version": 1,
        "video": "", "video_path": "",
        "scene": scene_path.name,
        "scene_path": str(scene_path).replace("\\", "/"),
        "camera": _object_path(camera),
        "blender_version": bpy.app.version_string,
        "render_method": "Blender Eevee emission-marker camera render" if uses_patterns else "Blender Workbench camera render",
        "assignment_mode": (
            "blender_object_world_pattern_marker" if uses_patterns else
            "blender_object_solid_marker" if marker_mode else
            "blender_original_neutral_grayscale"
        ),
        "render_profile": profile,
        "marker_catalog_version": int(catalog.get("version") or 0),
        "fps": fps,
        "start_frame": frames[0], "end_frame": frames[-1],
        "frame_count": len(frame_map),
        "resolution": {"width": width, "height": height},
        "video_format": {"container": "MPEG-4", "codec": "H.264", "encoder": "libx264"},
        "frame_pattern": str(Path(job["frames_folder"]) / (name + ".%06d.png")).replace("\\", "/"),
        "frame_map": frame_map,
        "markers": bindings,
        "hidden_paths": hidden,
        "warnings": warnings,
        "scene_dependency_paths": dependencies,
        "script_node_report": script_report,
    }
    _write_json(job["sidecar_path"], sidecar)

    if depth_requested:
        near, far = _depth_range(scene, camera, active, frames, objects)
        _configure_depth(scene, near, far)
        depth_name = _clean(job.get("depth_output_name")) or "depth"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", depth_name):
            raise ValueError("Unsafe Blender Depth output name.")
        depth_map = _render_sequence(job, scene, frames, job["depth_frames_folder"], depth_name, "rendering_depth")
        depth_report = {"near": near, "far": far, "units": "Blender camera-space scene units", "white": "near", "black": "far", "normalization": "linear_clamped", "sampled_frame_count": len(frames)}
        depth_sidecar = dict(sidecar)
        depth_sidecar.update({
            "schema": "hmb-blender-depth-playblast",
            "profile": DEPTH_PROFILE,
            "render_method": "Blender Eevee camera-space Z emission",
            "assignment_mode": "temporary_camera_depth_material_override",
            "frame_pattern": str(Path(job["depth_frames_folder"]) / (depth_name + ".%06d.png")).replace("\\", "/"),
            "frame_map": depth_map,
            "depth_range_report": depth_report,
        })
        _write_json(job["depth_sidecar_path"], depth_sidecar)
        result.update({
            "depth_frames_folder": str(Path(job["depth_frames_folder"]).resolve()).replace("\\", "/"),
            "depth_output_name": depth_name,
            "depth_sidecar_path": str(Path(job["depth_sidecar_path"]).resolve()).replace("\\", "/"),
            "depth_frame_count": len(depth_map),
            "depth_profile": DEPTH_PROFILE,
            "depth_range_report": depth_report,
            "depth_frame_map": depth_map,
        })
        result["artifacts"]["depth"]["ok"] = True

    if motion_requested:
        motion_map, motion_report = _render_motion(job, scene, camera, objects, active, frames, width, height)
        if not motion_report["motion_detected"]:
            warnings.append("Blender Motion Guide has no detected movement in this frame range.")
        if motion_report["armature_bone_count"] == 0:
            warnings.append("Blender Motion Guide contains rigid-object anchors only; no armature bones or face landmarks were found.")
        motion_name = _clean(job.get("motion_guide_output_name")) or "motion_guide"
        motion_sidecar = dict(sidecar)
        motion_sidecar.update({
            "schema": "hmb-blender-motion-guide",
            "profile": MOTION_PROFILE,
            "render_method": "Blender camera-projected armature bones and rigid-object anchors",
            "assignment_mode": "blender_spatial_guide_no_face_semantics",
            "frame_pattern": str(Path(job["motion_guide_frames_folder"]) / (motion_name + ".%06d.png")).replace("\\", "/"),
            "frame_map": motion_map,
            "motion_guide_report": motion_report,
            "warnings": warnings,
        })
        _write_json(job["motion_guide_sidecar_path"], motion_sidecar)
        result.update({
            "motion_guide_frames_folder": str(Path(job["motion_guide_frames_folder"]).resolve()).replace("\\", "/"),
            "motion_guide_output_name": motion_name,
            "motion_guide_sidecar_path": str(Path(job["motion_guide_sidecar_path"]).resolve()).replace("\\", "/"),
            "motion_guide_frame_count": len(motion_map),
            "motion_guide_profile": MOTION_PROFILE,
            "motion_guide_report": motion_report,
            "motion_guide_frame_map": motion_map,
        })
        result["artifacts"]["motion_guide"]["ok"] = True

    _write_json(job["result_path"], result)
    _progress(job, "render_complete", "Blender frame generation completed.", frame_count=len(frame_map), depth_frame_count=result.get("depth_frame_count", 0), motion_guide_frame_count=result.get("motion_guide_frame_count", 0))
    return result


def run(job_path):
    path = str(Path(job_path).resolve(strict=True))
    job = _read_job(path)
    result = {"ok": False, "job_path": path, "blender_version": bpy.app.version_string}
    try:
        scene_path = _validate_scene(job)
        _progress(job, "blender_ready", "Blender scene loaded with automatic script execution disabled.")
        operation = _clean(job.get("operation")) or "render"
        if operation == "scan":
            return _scan(job, scene_path)
        if operation not in {"snapshot", "render"}:
            raise ValueError("Unsupported Blender Picker operation: {}".format(operation))
        return _render(job, scene_path)
    except Exception as exc:
        result.update({"error": str(exc), "traceback": traceback.format_exc()})
        _write_json(job["result_path"], result)
        _progress(job, "failed", str(exc))
        raise


if __name__ == "__main__":
    try:
        marker = sys.argv.index("--")
        job_file = sys.argv[marker + 1]
    except (ValueError, IndexError):
        job_file = os.environ.get("HMB_VIDEO_PICKER_JOB", "")
    if not job_file:
        raise SystemExit("A private Blender Picker job JSON path is required after --.")
    run(job_file)
