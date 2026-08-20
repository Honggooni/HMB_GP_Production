from __future__ import annotations

from pathlib import Path
import importlib.util
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

assert picker.PICKER_NATIVE_SIZE_VERSION == 3
assert picker.PICKER_WIDGET_MIN_WIDTH == 760
assert picker.PICKER_WIDGET_MIN_HEIGHT == 1151

# v2 compact mode incorrectly persisted its 158px widget height as the outer
# React Flow node height. Preserve a valid user width and restore only height.
repaired_size, repaired = picker._restored_picker_native_size(
    {
        "size": {"width": 1333, "height": picker.PICKER_WIDGET_COMPACT_MOUNT_HEIGHT},
        "hmb_picker_native_size_version": 2,
    }
)
assert repaired is True
assert repaired_size == {"width": 1333, "height": picker.PICKER_START_HEIGHT}

precise_width_size, precise_width_repaired = picker._restored_picker_native_size(
    {
        "size": {"width": 1333.5, "height": 158},
        "hmb_picker_native_size_version": 2,
    }
)
assert precise_width_repaired is True
assert precise_width_size["width"] == 1333.5

# A corrupt width cannot be promoted into the new contract. Use the full
# production start frame when both dimensions need repair.
fallback_size, fallback_repaired = picker._restored_picker_native_size(
    {
        "size": {"width": 420, "height": 158},
        "hmb_picker_native_size_version": 2,
    }
)
assert fallback_repaired is True
assert fallback_size == {
    "width": picker.PICKER_START_WIDTH,
    "height": picker.PICKER_START_HEIGHT,
}

# The established 1151px floor is a legitimate user-resized height and must
# remain byte-for-byte stable while the contract marker advances.
valid_user_size = {"width": 1188, "height": picker.PICKER_WIDGET_MIN_HEIGHT}
preserved_size, preserved_repaired = picker._restored_picker_native_size(
    {
        "size": dict(valid_user_size),
        "hmb_picker_native_size_version": 2,
    }
)
assert preserved_repaired is False
assert preserved_size == valid_user_size

# Versioning makes the migration one-shot. Current-contract metadata is never
# rewritten by this legacy repair even if a future host supplies a small size.
current_size = {"width": 1000, "height": 300}
unchanged_size, current_repaired = picker._restored_picker_native_size(
    {
        "size": dict(current_size),
        "hmb_picker_native_size_version": picker.PICKER_NATIVE_SIZE_VERSION,
    }
)
assert current_repaired is False
assert unchanged_size == current_size

# Exercise the constructor path used during workflow reload, not only the pure
# migration helper. A standalone installed Griptape package cannot construct a
# real DataNode without an Engine/EventManager, so that host-specific lifecycle
# remains covered by in-app smoke tests while the local fallback verifies the
# constructor contract here.
if picker.DataNode.__module__ == "_hmb_gp_production_common":
    node = picker.HMBVideoPickerLibrary(
        name="picker_compact_height_recovery",
        metadata={
            "size": {"width": 1333, "height": 158},
            "hmb_picker_native_size_version": 2,
        },
    )
    assert node.metadata["size"] == {
        "width": 1333,
        "height": picker.PICKER_START_HEIGHT,
    }
    assert node.metadata["hmb_picker_native_size_version"] == (
        picker.PICKER_NATIVE_SIZE_VERSION
    )
    assert node.width == 1333
    assert node.height == picker.PICKER_START_HEIGHT

    preserved_node = picker.HMBVideoPickerLibrary(
        name="picker_valid_user_height_preserved",
        metadata={
            "size": dict(valid_user_size),
            "hmb_picker_native_size_version": 2,
        },
    )
    assert preserved_node.metadata["size"] == valid_user_size
    assert preserved_node.metadata["hmb_picker_native_size_version"] == (
        picker.PICKER_NATIVE_SIZE_VERSION
    )
    assert preserved_node.width == valid_user_size["width"]
    assert preserved_node.height == valid_user_size["height"]

print("HMB VideoPicker native size migration regression: PASS")
