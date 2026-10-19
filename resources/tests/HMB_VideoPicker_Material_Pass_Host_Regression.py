"""Exact set contracts, proof admission and cache isolation; no Maya process."""
from __future__ import annotations
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


def empty_mask_material_report():
    """A worker's empty-set report still proves capture and exact restoration."""
    counts = (
        "inspected_shading_engine_count", "contributing_shading_engine_count", "temporary_lambert_count",
        "texture_connection_count", "transparency_transfer_count", "emission_transfer_count", "normal_transfer_count",
        "swapped_shading_engine_count", "preserved_eye_shape_count", "preserved_eye_component_count",
        "preserved_eye_shading_engine_count", "split_shading_engine_count", "split_body_member_count",
        "eye_texture_dependency_count", "eye_missing_texture_dependency_count", "eye_unavailable_plugin_dependency_count",
        "eye_fallback_shading_engine_count", "eye_fallback_shape_count", "eye_fallback_material_count",
        "eye_fallback_texture_connection_count", "material_pass_shape_count", "material_pass_scoped_shape_count",
        "marker_assignment_eligible_shape_count",
    )
    return dict.fromkeys(counts, 0) | {
        "profile": picker.MASK_MATERIAL_PASS_PROFILE, "material_pass_source": "AIPickerM_SET",
        "material_pass_sources": ["AIPickerM_SET"], "requested": True, "status": "restored", "restore_ok": True,
        "shading_group_membership_preserved": True, "default_lighting_verified": True,
        "solid_render_mode_verified": False, "textured_render_mode_verified": True,
        "eye_textures_enabled": False, "eye_materials_preserved": True, "eye_assignments_preserved": True,
        "eye_dependency_preflight_passed": True, "soft_shading_verified": False,
        "authored_materials_ignored": False, "textures_ignored": False, "authored_material_ignore_scope": "none",
        "opaque_surface_verified": False, "temporary_nodes_retained_on_restore_failure": False,
        "eye_fallback_policy": picker.ORIGINAL_EYE_FALLBACK_POLICY, "eye_fallback_applied": False,
        "eye_fallback_verified": False, "eye_fallback_records": [], "eye_unavailable_plugin_nodes": [],
    }


def main():
    empty = empty_mask_material_report()
    assert picker._mask_material_report_is_valid(empty)
    nonempty = empty | {"preserved_eye_shape_count": 2, "material_pass_shape_count": 2,
        "material_pass_scoped_shape_count": 1, "preserved_eye_shading_engine_count": 1,
        "contributing_shading_engine_count": 1, "inspected_shading_engine_count": 1,
        "eye_textures_enabled": True, "marker_assignment_eligible_shape_count": 128}
    assert picker._mask_material_report_is_valid(nonempty)
    assert not picker._original_material_report_is_valid(nonempty)
    for key, value in (
        ("material_pass_source", "AIPicker_SET"), ("material_pass_source", "AIPickerM_SET_extra"),
        ("material_pass_sources", ["AIPicker_SET", "AIPickerM_SET"]),
        ("material_pass_sources", ["studio:AIPickerM_SET"]), ("profile", picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE),
        ("restore_ok", False), ("eye_materials_preserved", False), ("eye_assignments_preserved", False),
        ("shading_group_membership_preserved", False), ("eye_dependency_preflight_passed", False),
        ("eye_missing_texture_dependency_count", 1), ("eye_unavailable_plugin_dependency_count", 1),
        ("material_pass_shape_count", 3), ("material_pass_shape_count", True),
        ("material_pass_scoped_shape_count", 3), ("marker_assignment_eligible_shape_count", -1),
        ("authored_materials_ignored", True), ("textures_ignored", True), ("opaque_surface_verified", True),
        ("solid_render_mode_verified", True), ("soft_shading_verified", True), ("textured_render_mode_verified", False),
        ("default_lighting_verified", False), ("temporary_lambert_count", 1), ("base_color", [.5] * 3),
    ):
        assert not picker._mask_material_report_is_valid(nonempty | {key: value}), (key, value)
    for key in ("material_pass_shape_count", "material_pass_scoped_shape_count", "marker_assignment_eligible_shape_count"):
        broken = copy.deepcopy(nonempty); broken.pop(key)
        assert not picker._mask_material_report_is_valid(broken), key
    source = {"mask_material_pass_report": nonempty}
    before = copy.deepcopy(source)
    admitted = picker._validate_mask_material_pass_confirmation(source, copy.deepcopy(source))
    admitted["material_pass_sources"].append("foreign")
    assert source == before
    for result, sidecar in (({}, source), (source, {}), (source, {"mask_material_pass_report": empty})):
        try:
            picker._validate_mask_material_pass_confirmation(result, sidecar)
        except RuntimeError:
            pass
        else:
            raise AssertionError("A missing or mismatched Mask restoration proof was admitted")
    original = empty | {"profile": picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
        "material_pass_source": "AIPicker_SET|AIPickerM_SET", "material_pass_sources": ["AIPicker_SET", "AIPickerM_SET"],
        "base_color": [.5] * 3, "diffuse": .45, "fill_color": [.22] * 3,
        "solid_render_mode_verified": True, "textured_render_mode_verified": False, "soft_shading_verified": True,
        "authored_materials_ignored": True, "textures_ignored": True,
        "authored_material_ignore_scope": "non_eye_surfaces", "opaque_surface_verified": True}
    assert picker._original_material_report_is_valid(original, allow_legacy=False)
    legacy = copy.deepcopy(original); legacy["material_pass_source"] = "AIPicker_SET"; legacy.pop("material_pass_sources")
    assert picker._original_material_report_is_valid(legacy)
    assert not picker._original_material_report_is_valid(legacy, allow_legacy=False)
    for text, names in (("AIPicker_SET_extra|AIPickerM_SET", ["AIPicker_SET_extra", "AIPickerM_SET"]),
                        ("AIPickerM_SET", ["AIPickerM_SET"]),
                        ("AIPicker_SET|AIPickerM_SET|eye_GRP", ["AIPicker_SET", "AIPickerM_SET", "eye_GRP"])):
        assert not picker._original_material_report_is_valid(original | {"material_pass_source": text, "material_pass_sources": names})
    with tempfile.TemporaryDirectory(prefix="hmb-material-host-") as temporary:
        scene = Path(temporary) / "scene.ma"; scene.write_text("// synthetic fixture")
        for kind in ("render_snapshot", "run_video"):
            for role in ("mask", "original", "depth", "motion_guide"):
                state = picker._parse_state({"selected_camera": "|camera", "start_frame": 1, "end_frame": 2,
                    "source_fps": 24, "native_read_ready": True,
                    **{name + "_enabled": name == role for name in ("mask", "original", "depth", "motion_guide")}})
                baseline = picker._operation_input_digest(kind, scene, state)
                with mock.patch.object(picker, "MASK_MATERIAL_PASS_PROFILE", "historical-no-material-pass"):
                    changed = picker._operation_input_digest(kind, scene, state)
                assert (changed != baseline) is (role == "mask"), (kind, role, "Mask cache isolation")
                with mock.patch.object(picker, "ORIGINAL_MATERIAL_PASS_SOURCES", ("AIPicker_SET",)):
                    changed = picker._operation_input_digest(kind, scene, state)
                assert (changed != baseline) is (role == "original"), (kind, role, "Original cache isolation")
        state = picker._parse_state({"original_enabled": True, "mask_enabled": False, "depth_enabled": False,
                                    "motion_guide_enabled": False})
        current = picker._operation_input_digest("render_original_preview", scene, state)
        with mock.patch.object(picker, "ORIGINAL_MATERIAL_PASS_SOURCES", ("AIPicker_SET",)):
            assert picker._operation_input_digest("render_original_preview", scene, state) != current
    # All three capture entrances retain role-specific confirmation and fixed cache inputs.
    tree = ast.parse((ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8"))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HMBVideoPickerLibrary")
    for name in ("_capture_maya_snapshot_role", "_maya_selected_role_artifact", "_maya_mode"):
        method = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "_validate_mask_material_pass_confirmation" for n in ast.walk(method)), name
    print("HMB_MATERIAL_PASS_HOST=PASS (Original exact2+legacy reader; Mask exact1+independent visuals/restore; mismatched proof rejected; per-role cache isolation)")


if __name__ == "__main__":
    main()
