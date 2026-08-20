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

compact_size = {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_COMPACT_NATIVE_HEIGHT,
}
default_expanded_size = {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_START_HEIGHT,
}

assert picker.PICKER_NATIVE_SIZE_VERSION == 4
assert picker.PICKER_WIDGET_MIN_WIDTH == 760
assert picker.PICKER_COMPACT_NATIVE_HEIGHT == 360
assert picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT == 360
assert picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT == 158
assert picker.PICKER_WIDGET_START_HEIGHT == 158
assert picker.PICKER_WIDGET_MIN_HEIGHT == 1151

# A new node starts compact; the full-view default is retained independently.
new_compact, new_expanded, new_migrated = picker._restored_picker_native_geometry(None)
assert new_compact == compact_size
assert new_expanded == default_expanded_size
assert new_migrated is True

# The retired v2 158px outer size is repaired directly to the stable compact
# native shell. It is never promoted through the old 1200px cold-mount state.
legacy_compact, legacy_expanded, legacy_migrated = picker._restored_picker_native_geometry(
    {
        "size": {"width": 1333, "height": 158},
        "hmb_picker_native_size_version": 2,
    }
)
assert legacy_compact == compact_size
assert legacy_expanded == default_expanded_size
assert legacy_migrated is True

# v3's 1400x1200 cold/reload geometry becomes exactly one 1400x360 compact
# result, while the former full geometry is preserved for explicit expansion.
v3_compact, v3_expanded, v3_migrated = picker._restored_picker_native_geometry(
    {
        "size": {"width": 1400, "height": 1200},
        "hmb_picker_native_size_version": 3,
    }
)
assert v3_compact == compact_size
assert v3_expanded == {"width": 1400, "height": 1200}
assert v3_migrated is True

# A legitimate pre-v4 user resize is not discarded. It moves to the expanded
# geometry field while the active cold/reload size remains stable compact.
user_expanded_size = {"width": 1188.5, "height": 1151}
user_compact, preserved_expanded, user_migrated = picker._restored_picker_native_geometry(
    {
        "size": dict(user_expanded_size),
        "hmb_picker_native_size_version": 3,
        "unrelated": "preserve-me",
    }
)
assert user_compact == compact_size
assert preserved_expanded == user_expanded_size
assert user_migrated is True

# Current v4 compact metadata is one-shot and keeps its independently saved
# expanded geometry without reporting another migration.
canonical_metadata = {
    "size": dict(compact_size),
    picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(user_expanded_size),
    "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
}
canonical_compact, canonical_expanded, canonical_migrated = (
    picker._restored_picker_native_geometry(canonical_metadata)
)
assert canonical_compact == compact_size
assert canonical_expanded == user_expanded_size
assert canonical_migrated is False

# If the host serializes metadata.size while the full dashboard is visible,
# that live expanded resize is newer than the previous expanded snapshot.
latest_expanded = {"width": 1777, "height": 1444}
reload_compact, reload_expanded, reload_migrated = picker._restored_picker_native_geometry(
    {
        "size": dict(latest_expanded),
        picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(user_expanded_size),
        "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
    }
)
assert reload_compact == compact_size
assert reload_expanded == latest_expanded
assert reload_migrated is True

# Corrupt active dimensions cannot erase a valid saved expanded resize.
corrupt_compact, corrupt_expanded, corrupt_migrated = picker._restored_picker_native_geometry(
    {
        "size": {"width": True, "height": float("nan")},
        picker.PICKER_EXPANDED_SIZE_METADATA_KEY: dict(user_expanded_size),
        "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
    }
)
assert corrupt_compact == compact_size
assert corrupt_expanded == user_expanded_size
assert corrupt_migrated is True

# The compatibility helper also exposes only the compact cold-mount result.
wrapper_size, wrapper_migrated = picker._restored_picker_native_size(
    {"size": {"width": 1400, "height": 1200}, "hmb_picker_native_size_version": 3}
)
assert wrapper_size == compact_size
assert wrapper_migrated is True

# The constructor prepares compact metadata before invoking DataNode, so the
# host allocator never observes an intermediate 1200px compact-path height.
picker_source = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
prepare_index = picker_source.index('prepared_kwargs["metadata"] = prepared_metadata')
super_index = picker_source.index("super().__init__(**prepared_kwargs)", prepare_index)
assert prepare_index < super_index

# Exercise the local fallback constructor path used by source regressions.
if picker.DataNode.__module__ == "_hmb_gp_production_common":
    new_node = picker.HMBVideoPickerLibrary(name="picker_v4_new")
    assert new_node.metadata["size"] == compact_size
    assert new_node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == default_expanded_size
    assert new_node.metadata["hmb_picker_native_size_version"] == 4
    assert new_node.width == compact_size["width"]
    assert new_node.height == compact_size["height"]

    restored_node = picker.HMBVideoPickerLibrary(
        name="picker_v3_expanded_restore",
        metadata={
            "size": dict(latest_expanded),
            "hmb_picker_native_size_version": 3,
            "unrelated": "preserve-me",
        },
    )
    assert restored_node.metadata["size"] == compact_size
    assert restored_node.metadata[picker.PICKER_EXPANDED_SIZE_METADATA_KEY] == latest_expanded
    assert restored_node.metadata["hmb_picker_native_size_version"] == 4
    assert restored_node.metadata["unrelated"] == "preserve-me"
    assert restored_node.width == compact_size["width"]
    assert restored_node.height == compact_size["height"]
    for key in (
        "height",
        "default_height",
        "preferred_height",
        "initial_height",
    ):
        assert restored_node.ui_options[key] == picker.PICKER_COMPACT_NATIVE_HEIGHT
    assert restored_node.ui_options["min_height"] == picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT
    for key in ("node_size", "default_size", "initial_size"):
        assert restored_node.ui_options[key] == compact_size

    state_parameter = picker._get_parameter_obj(restored_node, picker.WIDGET_STATE_PARAMETER)
    assert state_parameter.ui_options["height"] == picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT
    assert state_parameter.ui_options["min_height"] == picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT
    for key in ("node_size", "default_size", "initial_size"):
        assert state_parameter.ui_options[key] == compact_size

# Manifest defaults must match the Python native compact contract; the 158px
# authored row and 1200px expanded canvas are intentionally not advertised as
# the cold React Flow node size.
manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
picker_manifest = next(
    item for item in manifest["nodes"] if item["class_name"] == "HMBVideoPickerLibrary"
)["metadata"]
for key in ("height", "default_height", "preferred_height", "initial_height"):
    assert picker_manifest[key] == picker.PICKER_COMPACT_NATIVE_HEIGHT
assert picker_manifest["min_height"] == picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT
for key in ("height", "default_height", "preferred_height", "initial_height"):
    assert picker_manifest["ui_options"][key] == picker.PICKER_COMPACT_NATIVE_HEIGHT
assert picker_manifest["ui_options"]["min_height"] == picker.PICKER_COMPACT_NATIVE_MIN_HEIGHT

print("HMB VideoPicker native size migration regression: PASS")
