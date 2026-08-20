from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_image_asset_resolved_selection_regression",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
asset_library = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = asset_library
SPEC.loader.exec_module(asset_library)


def external_asset(name: str, order: int, path: str = "") -> dict:
    source_uid = f"import:{name.casefold()}"
    return {
        "asset_library_id": source_uid,
        "source_uid": source_uid,
        "source_kind": "user",
        "asset_project_uid": "",
        "asset_id": name,
        "image_name": name,
        "path": path,
        "thumbnail_url": "",
        "relative_path": "",
        "extension": ".png",
        "width": 1,
        "height": 1,
        "source_type": "Custom",
        "custom_source_type": "",
        "scope_candidate": "",
        "color_pick_candidates": [],
        "registered": False,
        "selected": True,
        "selection_order": order,
        "import_index": order,
        "media_ref_kind": "url" if path else "bytes",
        "connected": True,
    }


state = asset_library._default_state()
state["assets"] = [
    external_asset("First", 1, "https://example.com/first.png"),
    external_asset("Missing", 2),
    external_asset("Third", 3),
]
state = asset_library._normalize_state(state)
media_by_uid = {"import:third": b"third-image-bytes"}

# One resolution snapshot drives both public outputs.  A missing middle image
# cannot leave its metadata in @image2 while Third silently becomes fan-out #2.
payload, media = asset_library._build_synchronized_outputs(state, media_by_uid)
assert [item["image_name"] for item in payload["ordered_images"]] == [
    "First",
    "Third",
]
assert [item["selection_order"] for item in payload["ordered_images"]] == [1, 2]
assert media[0] == "https://example.com/first.png"
assert media[1].startswith("data:image/png;base64,")
assert len(media) == len(payload["ordered_images"]) == 2

resolution = payload["media_resolution"]
assert resolution["status"] == "partial"
assert resolution["selected_count"] == 3
assert resolution["resolved_count"] == 2
assert resolution["unresolved_count"] == 1
assert resolution["resolved"] == [
    {
        "source_uid": "import:first",
        "requested_selection_order": 1,
        "selection_order": 1,
    },
    {
        "source_uid": "import:third",
        "requested_selection_order": 3,
        "selection_order": 2,
    },
]
assert resolution["unresolved"] == [
    {
        "source_uid": "import:missing",
        "image_name": "Missing",
        "requested_selection_order": 2,
        "reason": "external_media_unavailable",
    }
]
assert len(payload["warnings"]) == 1
assert "Selected image #2" in payload["warnings"][0]
assert "import:missing" in payload["warnings"][0]
assert "both ASSET_OUT and Video Generation Out" in payload["warnings"][0]

# The compatibility helpers use the same fail-closed resolution contract even
# when each output is requested independently of Prompt or a generator node.
assert asset_library._selected_media_values(state, media_by_uid) == media
independent_payload = asset_library._build_output_payload(state, media_by_uid)
assert independent_payload["ordered_images"] == payload["ordered_images"]
assert independent_payload["selection_id"] == payload["selection_id"]

# Once the missing source resolves, it re-enters its requested slot and both
# outputs expand together.  The selection identity reflects that new snapshot.
complete_media = {
    **media_by_uid,
    "import:missing": "https://example.com/missing.png",
}
complete_payload, complete_fan_out = asset_library._build_synchronized_outputs(
    state,
    complete_media,
)
assert [item["image_name"] for item in complete_payload["ordered_images"]] == [
    "First",
    "Missing",
    "Third",
]
assert complete_fan_out[1] == "https://example.com/missing.png"
assert complete_payload["media_resolution"]["status"] == "complete"
assert complete_payload["warnings"] == []
assert complete_payload["selection_id"] != payload["selection_id"]

# Reordering remains compact and identical on both branches while the missing
# row's source_uid and original requested order stay explicit in diagnostics.
reordered = asset_library._normalize_state(state)
orders = {"Third": 1, "Missing": 2, "First": 3}
for item in reordered["assets"]:
    item["selection_order"] = orders[item["image_name"]]
reordered = asset_library._normalize_state(reordered)
reordered_payload, reordered_media = asset_library._build_synchronized_outputs(
    reordered,
    media_by_uid,
)
assert [item["image_name"] for item in reordered_payload["ordered_images"]] == [
    "Third",
    "First",
]
assert reordered_media[0].startswith("data:image/png;base64,")
assert reordered_media[1] == "https://example.com/first.png"
assert reordered_payload["media_resolution"]["unresolved"][0][
    "requested_selection_order"
] == 2

print("HMB Image Asset resolved-selection regression passed.")
