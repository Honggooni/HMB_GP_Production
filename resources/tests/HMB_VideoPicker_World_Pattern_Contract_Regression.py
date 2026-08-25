from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = _load("HMBVideoPickerLibrary", ROOT / "HMBVideoPickerLibrary.py")

pattern_row = {
    "pattern": "direction_checker",
    "subject_root": "|DomeSkyMountain",
    "projection_type": "TriPlanar",
    "projection_axis": "XYZ",
    "cell_size_world_units": 5.0,
    "projection_node": "HMB_Direction_Checker_Projection",
    "projector_node": "HMB_Direction_Checker_Projector",
    "anchor_node": "HMB_Direction_Checker_RootAnchor",
    "constraint_node": "HMB_Direction_Checker_RootAnchor_parentConstraint",
    "scale_constraint_node": "HMB_Direction_Checker_RootAnchor_scaleConstraint",
    "scale_compensator_node": "HMB_Direction_Checker_WorldScaleCompensator",
    "root_scale_followed": True,
    "world_cell_scale_compensated": True,
    "camera_anchored": False,
    "uv_dependent": False,
    "reference_frame": 101.0,
}
report = {
    "profile": picker.MAYA_WORLD_PATTERN_PROFILE,
    "coordinate_space": "background_root",
    "camera_anchored": False,
    "uv_dependent": False,
    "root_scale_followed": True,
    "world_cell_scale_compensated": True,
    "base_cell_world_units": 15.0,
    "density_multiplier": 3.0,
    "cell_size_world_units": 5.0,
    "reference_frame": 101.0,
    "pattern_binding_count": 1,
    "projection_node_count": 1,
    "projector_node_count": 1,
    "patterns": [pattern_row],
}
options = {
    "output_transform_disabled": True,
    "multisample_disabled": True,
    "line_aa_disabled": True,
    "ssao_disabled": True,
    "motion_blur_disabled": True,
}
confirmation = {
    "world_pattern_profile": picker.MAYA_WORLD_PATTERN_PROFILE,
    "world_pattern_report": report,
    "world_pattern_render_options": options,
}

assert picker._validate_world_pattern_runner_confirmation(confirmation) == report
assert picker._validate_world_pattern_runner_confirmation({}, confirmation) == report


def _assert_rejected(payload: dict, expected: str) -> None:
    try:
        picker._validate_world_pattern_runner_confirmation(payload)
    except RuntimeError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"World-pattern confirmation must reject {expected}.")


bad_profile = copy.deepcopy(confirmation)
bad_profile["world_pattern_profile"] = "legacy"
_assert_rejected(bad_profile, "profile")

missing_node = copy.deepcopy(confirmation)
missing_node["world_pattern_report"]["patterns"][0].pop("projection_node")
_assert_rejected(missing_node, "projection_node")

camera_anchored = copy.deepcopy(confirmation)
camera_anchored["world_pattern_report"]["camera_anchored"] = True
_assert_rejected(camera_anchored, "camera independence")

unverified_options = copy.deepcopy(confirmation)
unverified_options["world_pattern_render_options"]["multisample_disabled"] = False
_assert_rejected(unverified_options, "multisample_disabled")

print(
    "HMB VideoPicker world-pattern producer/consumer confirmation regression: PASS"
)
