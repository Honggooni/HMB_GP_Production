from __future__ import annotations

import copy
import importlib.util
import json
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
default_compact = {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_COMPACT_NATIVE_HEIGHT,
}


def assert_compact_geometry(node, expected_expanded):
    assert node.metadata["size"] == default_compact
    assert node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == expected_expanded
    assert node.metadata["hmb_picker_native_size_version"] == picker.PICKER_NATIVE_SIZE_VERSION
    assert node.width == default_compact["width"]
    assert node.height == default_compact["height"]
    assert node._picker_state()["expanded_node_size"] == {
        "width": int(expected_expanded["width"]),
        "height": int(expected_expanded["height"]),
    }
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


# The compact shell is the workflow cold-mount authority, while the separately
# retained expanded geometry remains available for the explicit view toggle.
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
assert initial == default_compact
assert expanded == custom_expanded
assert migrated is False


# Invalid, legacy, or partial metadata fails closed to one complete compact
# Loader and a valid default expanded transition geometry.
for metadata in (
    None,
    {},
    {"size": {"width": 1400, "height": 158}},
    {"size": {"width": 1400, "height": 360}},
    {"size": {"width": 1400}},
):
    cold_initial, cold_expanded, _ = picker._restored_picker_native_geometry(metadata)
    assert cold_initial == default_compact
    assert cold_expanded == default_expanded


# Current widget resize transactions accept only complete bounded geometry and
# cannot replace Python-owned Shot media. Older revisions and malformed sizes
# keep the last authoritative expanded geometry.
authoritative = picker._parse_state(
    {
        "state_revision": 12,
        "expanded_node_size": dict(default_expanded),
        "videos": [
            {
                "video_uid": "expanded-size-media-1",
                "source_uid": "expanded-size-media-1",
                "video_slot": 1,
                "selected": True,
                "selection_order": 1,
                "catalog_order": 1,
                "video_path": "https://media.example.test/shot-1.mp4",
            }
        ],
    }
)
current_resize = copy.deepcopy(authoritative)
current_resize["state_revision"] = 13
current_resize["expanded_node_size"] = {"width": 1777, "height": 1444}
current_resize["videos"] = []
merged_resize = picker.HMBVideoPickerLibrary._merge_widget_state(
    authoritative,
    current_resize,
)
assert merged_resize["expanded_node_size"] == {"width": 1777, "height": 1444}
assert [item["video_uid"] for item in merged_resize["videos"]] == [
    "expanded-size-media-1"
]

stale_resize = copy.deepcopy(current_resize)
stale_resize["state_revision"] = 11
stale_resize["expanded_node_size"] = {"width": 1888, "height": 1555}
assert picker.HMBVideoPickerLibrary._merge_widget_state(
    merged_resize,
    stale_resize,
)["expanded_node_size"] == {"width": 1777, "height": 1444}

invalid_resize = copy.deepcopy(current_resize)
invalid_resize["state_revision"] = 14
invalid_resize["expanded_node_size"] = {"width": True, "height": 1555}
assert picker.HMBVideoPickerLibrary._merge_widget_state(
    merged_resize,
    invalid_resize,
)["expanded_node_size"] == {"width": 1777, "height": 1444}

assert picker._normalized_picker_expanded_size(
    {"width": 9000, "height": 7000}
) == {"width": 6000, "height": 6000}
assert picker._reconciled_picker_expanded_state_size(
    {"expanded_node_size": dict(default_expanded)},
    {picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(custom_expanded)},
) == custom_expanded
assert picker._reconciled_picker_expanded_state_size(
    {"expanded_node_size": {"width": 1777, "height": 1444}},
    {picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(custom_expanded)},
) == {"width": 1777, "height": 1444}
assert picker._reconciled_picker_expanded_state_size(
    json.dumps({"expanded_node_size": {"width": 1777, "height": 1444}}),
    {},
) == {"width": 1777, "height": 1444}


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
    assert_compact_geometry(first, default_expanded)
    assert_compact_geometry(second, custom_expanded)
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
        assert_compact_geometry(first, default_expanded)
        assert_compact_geometry(second, custom_expanded)
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
    assert_compact_geometry(first, default_expanded)
    assert_compact_geometry(second, custom_expanded)
    assert "view_mode" not in first._picker_state()
    assert "picker_view_mode" not in first._picker_state()
    assert "expanded" not in first._picker_state()

    # A failed retained-mode publication rolls back both serialized state and
    # metadata, so SaveWorkflow can never observe a half-committed geometry.
    rollback_node = picker.HMBVideoPickerLibrary(
        name="picker_expanded_size_rollback"
    )
    rollback_state = copy.deepcopy(rollback_node._picker_state())
    rollback_metadata = copy.deepcopy(rollback_node.metadata)
    rejected_state = copy.deepcopy(rollback_state)
    rejected_state["expanded_node_size"] = {"width": 1777, "height": 1444}
    original_request_parameter_value = picker._request_parameter_value

    def reject_expanded_state(*_args, **_kwargs):
        raise RuntimeError("synthetic retained-mode rejection")

    picker._request_parameter_value = reject_expanded_state
    try:
        try:
            rollback_node._write_state(rejected_state)
            raise AssertionError("Rejected geometry publication unexpectedly succeeded")
        except RuntimeError as exc:
            assert "synthetic retained-mode rejection" in str(exc)
    finally:
        picker._request_parameter_value = original_request_parameter_value
    assert rollback_node.metadata == rollback_metadata
    assert picker._parse_state(
        picker._raw_parameter_value(rollback_node, picker.WIDGET_STATE_PARAMETER)
    )["expanded_node_size"] == rollback_state["expanded_node_size"]

    # SaveWorkflow reads parameter_values and metadata independently. A Python
    # publication therefore stages one identical expanded geometry on both
    # surfaces without disturbing the compact cold mount or retained media.
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    durable_state = copy.deepcopy(first._picker_state())
    durable_state["expanded_node_size"] = {"width": 1777, "height": 1444}
    durable_state["videos"] = copy.deepcopy(authoritative["videos"])
    first._write_state(durable_state)
    saved_state = copy.deepcopy(first._picker_state())
    saved_metadata = copy.deepcopy(first.metadata)
    assert saved_state["expanded_node_size"] == {"width": 1777, "height": 1444}
    assert saved_metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == {
        "width": 1777,
        "height": 1444,
    }
    assert saved_metadata["size"] == default_compact
    assert [item["video_uid"] for item in saved_state["videos"]] == [
        "expanded-size-media-1"
    ]

    reloaded = picker.HMBVideoPickerLibrary(
        name="picker_expanded_size_reloaded",
        metadata=saved_metadata,
    )
    reloaded.set_parameter_value(
        picker.WIDGET_STATE_PARAMETER,
        saved_state,
        initial_setup=True,
    )
    assert_compact_geometry(reloaded, {"width": 1777, "height": 1444})
    assert [item["video_uid"] for item in reloaded._picker_state()["videos"]] == [
        "expanded-size-media-1"
    ]

    # Migrate the exact v7 failure case: state contains the finalized widget
    # resize while metadata still contains the old default. Hydration keeps the
    # non-default state value and repairs metadata instead of overwriting state.
    mismatched_metadata = copy.deepcopy(saved_metadata)
    mismatched_metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] = dict(
        default_expanded
    )
    migrated = picker.HMBVideoPickerLibrary(
        name="picker_expanded_size_mismatch",
        metadata=mismatched_metadata,
    )
    migrated.set_parameter_value(
        picker.WIDGET_STATE_PARAMETER,
        saved_state,
        initial_setup=True,
    )
    assert_compact_geometry(migrated, {"width": 1777, "height": 1444})
    assert [item["video_uid"] for item in migrated._picker_state()["videos"]] == [
        "expanded-size-media-1"
    ]


print(
    "HMB VideoPicker Python geometry/hydration regression: PASS "
    "(cold/new/reload/two instances/validated expanded persistence/media)"
)
