from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_picker():
    module_name = "hmb_video_picker_native_size_migration_regression"
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

default_expanded_size = {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_START_HEIGHT,
}

assert picker.PICKER_NATIVE_SIZE_VERSION == 6
assert picker.PICKER_WIDGET_MIN_WIDTH == 760
assert picker.PICKER_COMPACT_NATIVE_HEIGHT == 360
assert picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT == 360
assert picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT == 252
assert picker.PICKER_WIDGET_START_HEIGHT == 1151
assert picker.PICKER_WIDGET_MIN_HEIGHT == 1151

# A new node starts in the inline expanded hybrid view. Compact is entered only
# after the user double-clicks the fixed widget header.
new_initial, new_expanded, new_migrated = picker._restored_picker_native_geometry(None)
assert new_initial == default_expanded_size
assert new_expanded == default_expanded_size
assert new_migrated is True

# The retired v2 158px outer size is repaired to the expanded-first hybrid
# geometry. Compact is derived only after the user changes view mode.
legacy_initial, legacy_expanded, legacy_migrated = picker._restored_picker_native_geometry(
    {
        "size": {"width": 1333, "height": 158},
        "hmb_picker_native_size_version": 2,
    }
)
assert legacy_initial == default_expanded_size
assert legacy_expanded == default_expanded_size
assert legacy_migrated is True

# v3's 1400x1200 cold/reload geometry remains the initial expanded geometry.
v3_initial, v3_expanded, v3_migrated = picker._restored_picker_native_geometry(
    {
        "size": {"width": 1400, "height": 1200},
        "hmb_picker_native_size_version": 3,
    }
)
assert v3_initial == {"width": 1400, "height": 1200}
assert v3_expanded == {"width": 1400, "height": 1200}
assert v3_migrated is True

# A legitimate pre-v5 user resize remains the expanded cold/reload geometry.
user_expanded_size = {"width": 1188.5, "height": 1151}
user_initial, preserved_expanded, user_migrated = picker._restored_picker_native_geometry(
    {
        "size": dict(user_expanded_size),
        "hmb_picker_native_size_version": 3,
        "unrelated": "preserve-me",
    }
)
assert user_initial == user_expanded_size
assert preserved_expanded == user_expanded_size
assert user_migrated is True

# Current v6 expanded metadata is one-shot and does not report another
# migration when both native and saved expanded geometry agree.
canonical_metadata = {
    "size": dict(user_expanded_size),
    picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(user_expanded_size),
    "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
}
canonical_initial, canonical_expanded, canonical_migrated = (
    picker._restored_picker_native_geometry(canonical_metadata)
)
assert canonical_initial == user_expanded_size
assert canonical_expanded == user_expanded_size
assert canonical_migrated is False

# If the host serializes metadata.size while the full dashboard is visible,
# that live expanded resize is newer than the previous expanded snapshot.
latest_expanded = {"width": 1777, "height": 1444}
reload_initial, reload_expanded, reload_migrated = picker._restored_picker_native_geometry(
    {
        "size": dict(latest_expanded),
        picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(user_expanded_size),
        "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
    }
)
assert reload_initial == latest_expanded
assert reload_expanded == latest_expanded
assert reload_migrated is True

# Corrupt active dimensions cannot erase a valid saved expanded resize.
corrupt_initial, corrupt_expanded, corrupt_migrated = picker._restored_picker_native_geometry(
    {
        "size": {"width": True, "height": float("nan")},
        picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(user_expanded_size),
        "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
    }
)
assert corrupt_initial == user_expanded_size
assert corrupt_expanded == user_expanded_size
assert corrupt_migrated is True

# The compatibility helper exposes the expanded cold-mount result.
wrapper_size, wrapper_migrated = picker._restored_picker_native_size(
    {"size": {"width": 1400, "height": 1200}, "hmb_picker_native_size_version": 3}
)
assert wrapper_size == default_expanded_size
assert wrapper_migrated is True

# The constructor prepares expanded metadata before invoking DataNode, so the
# host allocator and first widget paint observe the same geometry.
picker_source = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
prepare_index = picker_source.index('prepared_kwargs["metadata"] = prepared_metadata')
super_index = picker_source.index("super().__init__(**prepared_kwargs)", prepare_index)
assert prepare_index < super_index

# Exercise the local fallback constructor path used by source regressions.
if picker.DataNode.__module__ == "_hmb_gp_production_common":
    new_node = picker.HMBVideoPickerLibrary(name="picker_v6_new")
    assert new_node.metadata["size"] == default_expanded_size
    assert new_node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == default_expanded_size
    assert new_node.metadata["hmb_picker_native_size_version"] == 6
    assert new_node.width == default_expanded_size["width"]
    assert new_node.height == default_expanded_size["height"]

    restored_node = picker.HMBVideoPickerLibrary(
        name="picker_v3_expanded_restore",
        metadata={
            "size": dict(latest_expanded),
            "hmb_picker_native_size_version": 3,
            "unrelated": "preserve-me",
        },
    )
    assert restored_node.metadata["size"] == latest_expanded
    assert restored_node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == latest_expanded
    assert restored_node.metadata["hmb_picker_native_size_version"] == 6
    assert restored_node.metadata["unrelated"] == "preserve-me"
    assert restored_node.width == latest_expanded["width"]
    assert restored_node.height == latest_expanded["height"]
    for key in (
        "height",
        "default_height",
        "preferred_height",
        "initial_height",
    ):
        assert restored_node.ui_options[key] == picker.PICKER_START_HEIGHT
    assert restored_node.ui_options["min_height"] == picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT
    for key in ("node_size", "default_size", "initial_size"):
        assert restored_node.ui_options[key] == default_expanded_size

    state_parameter = picker._get_parameter_obj(restored_node, picker.WIDGET_STATE_PARAMETER)
    assert state_parameter.ui_options["height"] == picker.PICKER_WIDGET_START_HEIGHT
    assert state_parameter.ui_options["min_height"] == picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT
    for key in ("node_size", "default_size", "initial_size"):
        assert state_parameter.ui_options[key] == default_expanded_size

# Manifest defaults must match the Python expanded-first hybrid contract.
manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
picker_manifest = next(
    item for item in manifest["nodes"] if item["class_name"] == "HMBVideoPickerLibrary"
)["metadata"]
for key in ("height", "default_height", "preferred_height", "initial_height"):
    assert picker_manifest[key] == picker.PICKER_START_HEIGHT
assert picker_manifest["min_height"] == picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT
for key in ("height", "default_height", "preferred_height", "initial_height"):
    assert picker_manifest["ui_options"][key] == picker.PICKER_START_HEIGHT
assert picker_manifest["ui_options"]["min_height"] == picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT

print("HMB VideoPicker native size migration regression: PASS")
