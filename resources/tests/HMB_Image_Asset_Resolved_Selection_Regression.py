from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile


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
assert asset_library._project_output_fingerprint(state) is None, (
    "Dynamic IMAGE_IMPORT_IN artifacts must never enter the project-file cache."
)

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

# UI-only state changes must not re-read/re-encode an unchanged verified project
# selection or republish its two output ports. Selected metadata still invalidates
# the fingerprint and rebuilds both outputs.
temp_root = ROOT / ".tmp"
temp_root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="hmb_asset_output_cache_", dir=temp_root) as temporary:
    project_root = Path(temporary)
    image_path = project_root / "Hero.png"
    image_path.write_bytes(b"stable-project-image")
    metadata_root = project_root / asset_library.ASSET_METADATA_DIRECTORY_NAME
    metadata_root.mkdir()
    manifest_path = metadata_root / asset_library.MANIFEST_NAMES[0]
    manifest_path.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "path": "Hero.png",
                        "asset_id": "Hero",
                        "image_name": "Hero",
                        "source_type": "Character Appearance",
                        "custom_source_type": "",
                        "scope": "Head / face only",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    project_id = project_root.name
    project_uid = asset_library._project_uid(project_root)
    project_state = asset_library._normalize_state(
        {
            "project_root": str(project_root),
            "project_id": project_id,
            "project_uid": project_uid,
            "manifest_signature": asset_library._asset_manifest_signature(project_root),
            "scan_revision": 1,
            "assets": [
                {
                    "asset_library_id": asset_library._asset_library_id(
                        project_id,
                        "Hero.png",
                    ),
                    "source_uid": "project:hero",
                    "source_kind": "project",
                    "asset_project_uid": project_uid,
                    "asset_id": "Hero",
                    "image_name": "Hero",
                    "path": str(image_path),
                    "relative_path": "Hero.png",
                    "extension": ".png",
                    "width": 1,
                    "height": 1,
                    "source_type": "Character Appearance",
                    "scope_candidate": "Head / face only",
                    "registered": True,
                    "selected": True,
                    "selection_order": 1,
                }
            ],
        }
    )
    cache_node = object.__new__(asset_library.HMBImageAssetLibrary)
    cache_node._hmb_import_media_by_uid = {}
    cache_node._hmb_last_resolution_warning = ""
    cache_node._hmb_last_output_fingerprint = ""
    cache_node._hmb_last_output_pair = None
    cache_node.parameter_output_values = {}
    build_calls = []
    published_outputs = []
    notifications = []
    original_build = asset_library._build_synchronized_outputs
    original_set_output = asset_library.set_output

    def counted_build(state_value, media_value):
        build_calls.append(1)
        return original_build(state_value, media_value)

    asset_library._build_synchronized_outputs = counted_build
    def recorded_set_output(node, name, value):
        published_outputs.append((name, value))
        node.parameter_output_values[name] = value

    def assert_pair_staged_before_notification(node):
        cached_pair = node._hmb_last_output_pair
        assert isinstance(cached_pair, tuple) and len(cached_pair) == 2
        assert node.parameter_output_values[asset_library.OUTPUT_PARAMETER] == (
            cached_pair[0]
        )
        assert node.parameter_output_values[
            asset_library.MEDIA_OUTPUT_PARAMETER
        ] == cached_pair[1]

    def recorded_publish(name, value):
        assert_pair_staged_before_notification(cache_node)
        notifications.append((name, value))

    asset_library.set_output = recorded_set_output
    cache_node.publish_update_to_parameter = recorded_publish
    try:
        cache_node._sync_output(project_state)
        ui_only_state = dict(project_state)
        ui_only_state["search"] = "Hero"
        ui_only_state["language"] = "ko"
        cache_node._sync_output(ui_only_state)
        assert len(build_calls) == 1
        assert len(published_outputs) == 2
        assert [name for name, _value in notifications] == [
            asset_library.OUTPUT_PARAMETER,
            asset_library.MEDIA_OUTPUT_PARAMETER,
        ]

        # Host-side port clearing must repair the last-good synchronized pair
        # without re-reading or re-encoding the selected project file.
        expected_asset_output = cache_node.parameter_output_values[
            asset_library.OUTPUT_PARAMETER
        ]
        expected_media_output = list(
            cache_node.parameter_output_values[asset_library.MEDIA_OUTPUT_PARAMETER]
        )
        cache_node.parameter_output_values.clear()
        cache_node._sync_output(ui_only_state)
        assert len(build_calls) == 1
        assert len(published_outputs) == 4
        assert len(notifications) == 4
        assert cache_node.parameter_output_values[asset_library.OUTPUT_PARAMETER] == (
            expected_asset_output
        )
        assert cache_node.parameter_output_values[
            asset_library.MEDIA_OUTPUT_PARAMETER
        ] == expected_media_output

        # A one-port mutation is also a pair consistency failure: both cached
        # branches are restored together so metadata and media cannot diverge.
        cache_node.parameter_output_values[
            asset_library.MEDIA_OUTPUT_PARAMETER
        ] = ["tampered-media"]
        cache_node._sync_output(ui_only_state)
        assert len(build_calls) == 1
        assert len(published_outputs) == 6
        assert len(notifications) == 6
        assert [name for name, _value in published_outputs[-2:]] == [
            asset_library.OUTPUT_PARAMETER,
            asset_library.MEDIA_OUTPUT_PARAMETER,
        ]
        assert cache_node.parameter_output_values[asset_library.OUTPUT_PARAMETER] == (
            expected_asset_output
        )
        assert cache_node.parameter_output_values[
            asset_library.MEDIA_OUTPUT_PARAMETER
        ] == expected_media_output

        # Once both live ports match the cached pair, another UI-only sync is a
        # true no-op.
        cache_node._sync_output(ui_only_state)
        assert len(build_calls) == 1
        assert len(published_outputs) == 6
        assert len(notifications) == 6

        # Notification failures are reported only after both ports have been
        # attempted. The first callback must already see both latest caches and
        # the internal last-good pair must remain coherent for later repair.
        failed_notification_attempts = []

        def fail_first_notification(name, value):
            assert_pair_staged_before_notification(cache_node)
            failed_notification_attempts.append((name, value))
            if name == asset_library.OUTPUT_PARAMETER:
                raise ValueError("simulated first-port notification failure")

        cache_node.publish_update_to_parameter = fail_first_notification
        cache_node.parameter_output_values[asset_library.OUTPUT_PARAMETER] = (
            "tampered-asset-output"
        )
        try:
            cache_node._sync_output(ui_only_state)
        except RuntimeError as error:
            assert "both output caches were staged" in str(error)
        else:
            raise AssertionError("A connection notification failure must propagate.")
        assert [name for name, _value in failed_notification_attempts] == [
            asset_library.OUTPUT_PARAMETER,
            asset_library.MEDIA_OUTPUT_PARAMETER,
        ]
        assert len(build_calls) == 1
        assert len(published_outputs) == 8
        assert cache_node._hmb_last_output_pair == (
            expected_asset_output,
            expected_media_output,
        )
        assert_pair_staged_before_notification(cache_node)
        cache_node.publish_update_to_parameter = recorded_publish

        notifications_before_retry = len(notifications)
        cache_node._sync_output(ui_only_state)
        assert len(build_calls) == 1
        assert len(published_outputs) == 8, (
            "A failed notification retry must not rebuild or restage either port."
        )
        assert [name for name, _value in notifications[notifications_before_retry:]] == [
            asset_library.OUTPUT_PARAMETER
        ], "Only the failed Image output port may be retried."
        assert cache_node._hmb_pending_output_notifications == {}

        # Explicit execution must bypass the UI cache and revalidate the actual
        # selected files even when only UI state changed since the last build.
        cache_node._sync_output(ui_only_state, force=True)
        assert len(build_calls) == 2
        assert len(published_outputs) == 10
        assert len(notifications) == 9

        changed_selection_state = asset_library._normalize_state(project_state)
        changed_selection_state["assets"][0]["width"] = 42
        cache_node._sync_output(changed_selection_state)
        assert len(build_calls) == 3
        assert len(published_outputs) == 12
        assert len(notifications) == 11

        # A synchronous Image subscriber can re-enter this node while G1's
        # first port is publishing.  G2 supersedes the complete pair: outer G1
        # must neither publish stale media nor surface G1's now-stale error.
        class ReentrantImageNode:
            def __init__(self):
                self.parameter_output_values = {}
                self._hmb_output_notification_generation = 0
                self._hmb_pending_output_notifications = {}

        reentrant_node = ReentrantImageNode()
        reentrant_events = []

        def publish_g2(name, value):
            reentrant_events.append(("g2", name, value))

        def publish_g1(name, value):
            reentrant_events.append(("g1", name, value))
            if name == asset_library.OUTPUT_PARAMETER:
                reentrant_node.publish_update_to_parameter = publish_g2
                asset_library._stage_and_notify_image_output_pair(
                    reentrant_node,
                    "g2-asset",
                    ["g2-media"],
                )
                raise ValueError("superseded g1 callback failure")

        reentrant_node.publish_update_to_parameter = publish_g1
        asset_library._stage_and_notify_image_output_pair(
            reentrant_node,
            "g1-asset",
            ["g1-media"],
        )
        assert reentrant_node.parameter_output_values == {
            asset_library.OUTPUT_PARAMETER: "g2-asset",
            asset_library.MEDIA_OUTPUT_PARAMETER: ["g2-media"],
        }
        assert [(owner, name) for owner, name, _value in reentrant_events] == [
            ("g1", asset_library.OUTPUT_PARAMETER),
            ("g2", asset_library.OUTPUT_PARAMETER),
            ("g2", asset_library.MEDIA_OUTPUT_PARAMETER),
        ]
        assert reentrant_node._hmb_pending_output_notifications == {}
    finally:
        asset_library._build_synchronized_outputs = original_build
        asset_library.set_output = original_set_output

print("HMB Image Asset resolved-selection regression passed.")
