"""Mask exact-M SET material preservation; no Maya process or user scene."""
from __future__ import annotations
import ast
import copy
import fnmatch
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "resources/maya/HMB_Maya_Background_Preview.py"
FIXTURES = ROOT / "resources/tests/HMB_VideoPicker_Original_Lambert_Override_Regression.py"
maya = types.ModuleType("maya")
maya.cmds = types.ModuleType("maya.cmds")
sys.modules.update({"maya": maya, "maya.cmds": maya.cmds})
spec = importlib.util.spec_from_file_location("mask_material_pass_worker", WORKER)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

# Reuse the existing SG/texture/unknown-plugin model without executing the
# Original test's Host imports or duplicating its 600-line Maya fixture.
tree = ast.parse(FIXTURES.read_text(encoding="utf-8"))
wanted = {"FakeMaterialCmds", "MidgrayCmds", "EyeMidgrayCmds", "configure_pass_sets", "add_surface"}
namespace = dict(types=types, copy=copy, fnmatch=fnmatch, Any=Any, BASE_SCOPE_SHAPES=["meshA", "meshB", "meshC", "meshD", "meshE"])
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in wanted], type_ignores=[]), str(FIXTURES), "exec"), namespace)
Eye = namespace["EyeMidgrayCmds"]
configure = namespace["configure_pass_sets"]


class MaskCmds(Eye):
    def __init__(self, folder):
        super().__init__(folder)
        self.node_types["MaskMarkerSG"] = "shadingEngine"
        self.members["MaskMarkerSG"] = []
        self.fail_mask_split_after_move = False

    def delete(self, node):
        if str(node).startswith("HMB_Mask_Authored_RemainderSG"):
            self.members.pop(node, None)
            return namespace["FakeMaterialCmds"].delete(self, node)
        return super().delete(node)

    def sets(self, group=None, query=False, **kwargs):
        if not query and kwargs.get("forceElement"):
            members = group if isinstance(group, (list, tuple)) else [group]
            # Maya whole-shape forceElement removes that shape's old face
            # assignments; keep the fake faithful for shared/per-face SGs.
            for member in members:
                if "." in str(member):
                    continue
                path = str(member)
                owner = path.rsplit("|", 1)[0] if self.node_types.get(path) in ("mesh", "nurbsSurface") else path
                for current in self.members.values():
                    current[:] = [x for x in current if str(x).split(".", 1)[0] not in (path, owner)]
            result = super().sets(group, query=query, **kwargs)
            if self.fail_mask_split_after_move and kwargs["forceElement"].startswith("HMB_Mask_"):
                self.fail_mask_split_after_move = False
                raise RuntimeError("intentional partial Mask remainder assignment")
            return result
        return super().sets(group, query=query, **kwargs)


def job_for(fake, shapes):
    return {"_viewport_quality_scope_shapes": list(shapes), "_render_scope_shapes": list(shapes),
        "_render_scope_binding_shapes": {"|hero:ROOT": list(shapes)}, "character_outline_mode": "native_lambert"}


def mark(fake, job, shapes):
    runner.cmds = fake
    # This test owns pass filtering/SG boundaries; independent cutout tests own
    # alpha transfer. The marker still uses the real forceElement assignment.
    def assign(shapes, shared_group, *args):
        return runner._assign(shapes, shared_group), list(shapes), []
    with mock.patch.object(runner, "_descendant_shapes", return_value=list(shapes)), \
         mock.patch.object(runner, "_marker_renderable_shapes", side_effect=list), \
         mock.patch.object(runner, "_lambert_shader", return_value="MaskMarkerSG"), \
         mock.patch.object(runner, "_assign_marker_group_preserving_cutouts", side_effect=assign), \
         mock.patch.object(runner, "MARKER_COLORS", {"Red": (1.0, 0.0, 0.0)}), \
         mock.patch.object(runner, "MARKER_PATTERNS", {}):
        return runner._apply_marker_shaders([{"color": "Red", "subject_root": "|hero:ROOT"}], job)


with tempfile.TemporaryDirectory(prefix="hmb-mask-material-pass-") as temporary:
    folder = Path(temporary)
    # Exact names, namespace leaves, group descendants/nested sets and component
    # owners share Original's resolution rules, but Mask selects only M.
    for prefix in ("", "studio:hero:"):
        fake = MaskCmds(folder)
        configure(fake, {prefix + "AIPicker_SET": [fake.EYE_LEFT_OWNER],
            prefix + "AIPickerM_SET": ["Nested_SET"],
            "Nested_SET": [fake.EYE_RIGHT_OWNER + ".f[0:2]"],
            prefix + "AIPickerM_SET_extra": [fake.BODY_OWNER],
            prefix + "aipickerm_set": [fake.BROW_OWNER]})
        runner.cmds = fake
        assert runner._original_pass_set_shapes() == {fake.EYE_LEFT, fake.EYE_RIGHT}
        assert runner._mask_pass_set_shapes() == {fake.EYE_RIGHT}
        shapes = [fake.EYE_LEFT, fake.EYE_RIGHT, fake.BODY, fake.BROW]
        job = job_for(fake, shapes)
        pass_members = list(fake.members["sharedEyeBodySG"][:1])
        pass_graph = fake.authored_eye_snapshot()
        assert not mark(fake, job, shapes)
        assert job["_mask_material_pass_shapes"] == [fake.EYE_RIGHT]
        assert job["_mask_marker_assignment_eligible_shape_count"] == 3
        assert fake.members["sharedEyeBodySG"] == pass_members
        assert set(fake.members["MaskMarkerSG"]) == {fake.EYE_LEFT, fake.BODY, fake.BROW}
        assert all(fake.EYE_RIGHT not in members for _group, members in fake.assignment_calls)
        before_controller = fake.snapshot()
        controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
        report = controller.apply()
        assert report["profile"] == runner.MASK_MATERIAL_PASS_PROFILE
        assert report["material_pass_source"] == "AIPickerM_SET"
        assert report["material_pass_sources"] == ["AIPickerM_SET"]
        assert report["material_pass_shape_count"] == report["preserved_eye_shape_count"] == 1
        assert report["temporary_lambert_count"] == 0
        assert report["authored_materials_ignored"] is False and report["opaque_surface_verified"] is False
        assert not any(key in report for key in ("base_color", "diffuse", "fill_color"))
        assert fake.snapshot() == before_controller
        assert controller.finish()["restore_ok"] and fake.snapshot() == before_controller
        assert fake.authored_eye_snapshot() == pass_graph
    # AIPicker_SET alone never grants a Mask exception, nor do legacy names.
    fake = MaskCmds(folder)
    runner.cmds = fake
    assert not runner._mask_pass_set_shapes()
    job = job_for(fake, [fake.EYE_LEFT, fake.EYE_RIGHT])
    mark(fake, job, [fake.EYE_LEFT, fake.EYE_RIGHT])
    assert not job["_mask_material_pass_shapes"] and job["_mask_marker_assignment_eligible_shape_count"] == 2
    controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
    assert controller.apply()["material_pass_shape_count"] == 0
    assert controller.finish()["restore_ok"]
    # All-pass bindings are valid, with zero fake semantic marker assignments.
    fake = MaskCmds(folder)
    configure(fake, {"AIPickerM_SET": [fake.EYE_RIGHT_OWNER]})
    job = job_for(fake, [fake.EYE_RIGHT])
    before = fake.snapshot()
    assert not mark(fake, job, [fake.EYE_RIGHT])
    assert fake.snapshot() == before and not fake.assignment_calls
    assert job["_mask_marker_assignment_eligible_shape_count"] == 0
    all_pass_binding = {"color": "Red", "asset_id": "all-pass-fixture", "subject_root": "|hero:ROOT"}
    with mock.patch.object(runner, "MARKER_COLORS", {"Red": (1.0, 0.0, 0.0)}):
        metadata = runner._marker_payload([all_pass_binding])
    assert len(metadata) == 1 and metadata[0]["color"] == all_pass_binding["color"]
    assert metadata[0]["asset_id"] == all_pass_binding["asset_id"]
    assert metadata[0]["subject_root"] == all_pass_binding["subject_root"]
    controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
    assert controller.apply()["material_pass_shape_count"] == 1
    assert controller.finish()["restore_ok"] and fake.snapshot() == before
    # Missing provider fallback uses Original's native input/cache transfer,
    # while unselected non-pass members of a shared SG keep the authored graph.
    for fail in (False, True):
        fake = MaskCmds(folder)
        configure(fake, {"AIPickerM_SET": [fake.EYE_RIGHT_OWNER]})
        fake.node_types["EyeMat"] = "unknown"
        job = job_for(fake, [fake.EYE_RIGHT])
        mark(fake, job, [fake.EYE_RIGHT])
        before = fake.snapshot()
        fake.fail_mask_split_after_move = fail
        controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
        if fail:
            try:
                controller.apply()
            except RuntimeError as exc:
                assert "partial Mask remainder" in str(exc)
            else:
                raise AssertionError("Partial Mask SG assignment must fail")
            assert controller.report["restore_ok"] and fake.snapshot() == before
            continue
        report = controller.apply()
        assert report["eye_fallback_applied"] and report["eye_fallback_verified"]
        assert report["split_body_member_count"] == len(fake.BODY_MEMBERS)
        remainder = next(group for group in fake.members if group.startswith("HMB_Mask_"))
        assert fake.connections[remainder + ".surfaceShader"] == "EyeMat.outColor"
        assert fake.connections[remainder + ".displacementShader"] == "EyeDisplacement.outAlpha"
        assert fake.members["sharedEyeBodySG"] == fake.EYE_MEMBERS
        assert fake.connections["sharedEyeBodySG.surfaceShader"].startswith("HMB_Original_EyeFallback_")
        assert controller.finish()["restore_ok"] and fake.snapshot() == before
        assert controller.finish()["restore_ok"] and fake.snapshot() == before
    # Missing native inputs fail as Mask (and use the Mask report key), before
    # a compatibility gray result can be published as authored material.
    fake = MaskCmds(folder)
    configure(fake, {"AIPickerM_SET": [fake.EYE_RIGHT_OWNER]})
    fake.values["EyeNormal.fileTextureName"] = str(folder / "missing-mask-pass-normal.png")
    job = job_for(fake, [fake.EYE_RIGHT])
    mark(fake, job, [fake.EYE_RIGHT])
    before = fake.snapshot()
    controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
    try:
        controller.apply()
    except RuntimeError as exc:
        assert str(exc).startswith("Mask material pass failed:")
    else:
        raise AssertionError("Missing authored pass texture was accepted")
    assert fake.snapshot() == before and job["_mask_material_pass_report"]["restore_ok"]
    assert "_original_material_override_report" not in job
    # A failed native restore keeps its usable fallback attached and temporary
    # nodes retained, then raises; it must never report successful publication.
    fake = MaskCmds(folder)
    configure(fake, {"AIPickerM_SET": [fake.EYE_RIGHT_OWNER]})
    fake.node_types["EyeMat"] = "unknown"
    job = job_for(fake, [fake.EYE_RIGHT])
    mark(fake, job, [fake.EYE_RIGHT])
    controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
    assert controller.apply()["eye_fallback_applied"]
    fake.fail_restore_target = "sharedEyeBodySG.surfaceShader"
    try:
        controller.finish()
    except RuntimeError as exc:
        assert str(exc).startswith("Mask material pass could not restore")
    else:
        raise AssertionError("Failed Mask shader restoration was accepted")
    assert controller.report["restore_ok"] is False
    assert controller.report["temporary_nodes_retained_on_restore_failure"] is True
    assert fake.connections["sharedEyeBodySG.surfaceShader"].startswith("HMB_Original_EyeFallback_")
    assert any(node.startswith("HMB_Original_EyeFallback_") for node in fake.node_types)

source = WORKER.read_text(encoding="utf-8")
main_node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name == "run")
main_source = ast.get_source_segment(source, main_node)
capture = main_source.index("output_paths, frame_map = _render_frames(")
restore = main_source.index("mask_material_controller.finish()", capture)
depth = main_source.index(") = _render_depth_pass(", capture)
assert capture < restore < depth
assert main_source.count('payload["mask_material_pass_report"]') == 1
assert main_source.count('result["mask_material_pass_report"]') == 1
for name in ("_render_depth_pass", "_render_motion_guide_pass"):
    part = ast.get_source_segment(source, next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name == name))
    assert "material_pass" not in part and "AIPicker" not in part

# Cross the real Worker -> Host proof boundary with actual controller reports.
# Lighting/texture evidence comes from the real marker viewport setup function,
# rather than making an Original neutral-body proof pretend to describe Mask.
host_spec = importlib.util.spec_from_file_location("mask_material_pass_host", ROOT / "HMBVideoPickerLibrary.py")
host = importlib.util.module_from_spec(host_spec)
sys.modules[host_spec.name] = host
host_spec.loader.exec_module(host)
with tempfile.TemporaryDirectory(prefix="hmb-mask-host-proof-") as temporary:
    for kind in ("empty", "native", "fallback"):
        fake = MaskCmds(Path(temporary))
        configure(fake, {} if kind == "empty" else {"AIPickerM_SET": [fake.EYE_RIGHT_OWNER]})
        if kind == "fallback":
            fake.node_types["EyeMat"] = "unknown"
        job = job_for(fake, [fake.EYE_RIGHT])
        mark(fake, job, [fake.EYE_RIGHT])
        options = runner._set_viewport_render_options(marker_mode=True)
        assert options["default_lighting_verified"] and options["textured_render_mode_verified"]
        controller = runner._OriginalLambertOverrideController(job, material_pass_only=True)
        controller.apply()
        controller.report.update({key: options[key] for key in ("default_lighting_verified", "textured_render_mode_verified")})
        proof = controller.finish()
        assert host._mask_material_report_is_valid(proof), kind
        accepted = host._validate_mask_material_pass_confirmation(
            {"mask_material_pass_report": proof}, {"mask_material_pass_report": copy.deepcopy(proof)})
        assert accepted == proof and accepted is not proof
print("HMB_MASK_MATERIAL_PASS=PASS (Original exact2/Mask exact1; namespaces/nested/component; marker exclusion; all/zero pass; shared-SG native fallback+partial failure exact restore; color-finally before Depth/Motion; no scene/render/Maya process)")
