from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_picker():
    module_name = "hmb_video_picker_python_geometry_hydration_regression"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "HMBVideoPickerLibrary.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load HMBVideoPickerLibrary.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


picker = load_picker()

default_expanded = {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_START_HEIGHT,
}
custom_expanded = {"width": 1680, "height": 1320}


def assert_expanded_geometry(node, expected):
    assert node.metadata["size"] == expected
    assert node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == expected
    assert node.metadata["hmb_picker_native_size_version"] == picker.PICKER_NATIVE_SIZE_VERSION
    assert node.width == expected["width"]
    assert node.height == expected["height"]
    state_parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
    assert state_parameter is not None
    assert state_parameter.hide is False
    assert state_parameter.hide_property is False
    assert state_parameter.serializable is True
    assert state_parameter.ui_options["hide"] is False
    assert state_parameter.ui_options["hide_property"] is False
    assert state_parameter.ui_options["expandable"] is True
    assert state_parameter.ui_options["height"] == picker.PICKER_WIDGET_START_HEIGHT
    assert state_parameter.ui_options["min_height"] == picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT
    for hidden_name in ("MAYA_SCENE", picker.WIDGET_COMMAND_PARAMETER):
        hidden_parameter = picker._get_parameter_obj(node, hidden_name)
        assert hidden_parameter is not None
        assert hidden_parameter.hide is True
        assert hidden_parameter.hide_property is True
        assert hidden_parameter.ui_options["hide"] is True
        assert hidden_parameter.ui_options["hide_property"] is True
        assert hidden_parameter.ui_options["expandable"] is False
        assert hidden_parameter.ui_options["height"] == 0
        assert hidden_parameter.ui_options["max_height"] == 0


# A compact session is intentionally not workflow authority. If the host saved
# the temporary compact shell in metadata.size, the separately retained
# expanded geometry is restored before the next React Flow layout pass.
compact_saved_metadata = {
    "size": {
        "width": picker.PICKER_START_WIDTH,
        "height": picker.PICKER_COMPACT_NATIVE_HEIGHT,
    },
    picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(custom_expanded),
    "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
}
initial, expanded, migrated = picker._restored_picker_native_geometry(
    compact_saved_metadata
)
assert initial == custom_expanded
assert expanded == custom_expanded
assert migrated is True


# Invalid, legacy, or partial compact metadata also fails closed to one complete
# expanded authoring surface; it can never advertise a header-only cold mount.
for metadata in (
    None,
    {},
    {"size": {"width": 1400, "height": 158}},
    {"size": {"width": 1400, "height": 360}},
    {"size": {"width": 1400}},
):
    cold_initial, cold_expanded, _ = picker._restored_picker_native_geometry(metadata)
    assert cold_initial == default_expanded
    assert cold_expanded == default_expanded


if picker.DataNode.__module__ == "_hmb_gp_production_common":
    # Keep the source regression deterministic and prevent background routing
    # discovery from changing otherwise unrelated test state.
    picker._find_mayabatch = lambda: None
    picker._shot_routing.schedule_post_registration_reconcile = lambda _node: False
    picker._shot_routing.schedule_post_hydration_reconcile = lambda _node: False

    first = picker.HMBVideoPickerLibrary(name="picker_geometry_first")
    second = picker.HMBVideoPickerLibrary(
        name="picker_geometry_second",
        metadata=copy.deepcopy(compact_saved_metadata),
    )
    assert_expanded_geometry(first, default_expanded)
    assert_expanded_geometry(second, custom_expanded)
    assert first.metadata is not second.metadata

    first_state = first._picker_state()
    second_state = second._picker_state()
    assert first_state["runtime_instance_id"] != second_state["runtime_instance_id"]
    assert first_state["picker_shots"] is not second_state["picker_shots"]

    # All supported workflow hydration hooks must keep the visible state row
    # mounted and must not let one node's geometry or state leak into its peer.
    for hook_name in ("after_deserialize", "after_load", "on_loaded"):
        before_first = copy.deepcopy(first.metadata)
        before_second = copy.deepcopy(second.metadata)
        getattr(first, hook_name)()
        assert_expanded_geometry(first, default_expanded)
        assert_expanded_geometry(second, custom_expanded)
        assert first.metadata == before_first
        assert second.metadata == before_second

    # A saved state reload repairs stale serialized parameter UI flags on each
    # instance independently. These flags are the complete Python-side body
    # visibility contract; compact/expanded subtree attachment remains local to
    # the JavaScript widget and is deliberately absent from durable state.
    first_parameter = picker._get_parameter_obj(first, picker.WIDGET_STATE_PARAMETER)
    first_parameter.hide = True
    first_parameter.hide_property = True
    first_parameter.ui_options.update(
        {"hide": True, "hide_property": True, "expandable": False, "height": 1}
    )
    first.after_load()
    assert_expanded_geometry(first, default_expanded)
    assert_expanded_geometry(second, custom_expanded)
    assert "view_mode" not in first._picker_state()
    assert "picker_view_mode" not in first._picker_state()
    assert "expanded" not in first._picker_state()


print(
    "HMB VideoPicker Python geometry/hydration regression: PASS "
    "(cold/new/reload/two instances/compact-expanded authority)"
)
