from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load_module("hmb_picker_visibility_recolor", ROOT / "HMBVideoPickerLibrary.py")

# Old catalog/selection transitions could duplicate one editable Mask binding.
# The first row is the live row edited by the widget; a later copy is stale and
# must not survive into the Maya shader job.
normalized = picker._normalize_assignment_bindings(
    [
        {
            "group_name": "Hero",
            "full_dag_path": "|Hero",
            "maya_uuid": "hero-uuid",
            "color": "Pink",
            "picker_order": 1,
        },
        {
            "group_name": "Hero",
            "full_dag_path": "|Hero",
            "maya_uuid": "hero-uuid",
            "color": "Red",
            "picker_order": 4,
        },
    ],
    1,
)
assert len(normalized) == 1
assert normalized[0]["color"] == "Pink"

widget_source = (ROOT / "widgets" / "HMBVideoPickerLibraryWidget_v032.js").read_text(
    encoding="utf-8"
)
assert "function hmbDedupePickerBindings" in widget_source
assert "const withoutSelectedObject = current.filter" in widget_source
assert "hmbPickerBindingIdentity(item) !== selectedIdentity" in widget_source

runner_source = (
    ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
).read_text(encoding="utf-8")
assert (
    "if generate_depth_playblast or (generate_motion_guide and not bindings):"
    in runner_source
)
assert (
    '"policy": "maya_visibility_on_and_picker_visible_independent_of_color_assignment"'
    in runner_source
)

print("HMB VideoPicker visibility-driven Depth and Mask recolor regression: PASS")
