from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_live_output_regression",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


class PublishProbe:
    def __init__(self) -> None:
        self.parameter_output_values: dict[str, object] = {}
        self.published: list[tuple[str, object]] = []
        self.cache_snapshots: list[dict[str, object]] = []
        self._hmb_state_write_lock = threading.RLock()
        self._hmb_node_deleted = False
        self._hmb_lifecycle_generation = 1
        self._hmb_last_public_output_fingerprint = ""
        self._hmb_last_shot_output_fingerprint = ""
        self.shot_envelope = {
            "schema": "hmb-picker-shot-routing-catalog",
            "version": 1,
            "channel_uuid": "11111111-1111-4111-8111-111111111111",
            "generation": 1,
            "metadata_sha256": "a" * 64,
            "media_sha256": "b" * 64,
            "shot_count": 1,
        }

    def publish_update_to_parameter(self, name: str, value: object) -> None:
        self.published.append((name, value))
        self.cache_snapshots.append(copy.deepcopy(self.parameter_output_values))

    def _shot_picker_dependency_envelope(
        self,
        *,
        state_snapshot: object = None,
        probe_cache: object = None,
    ) -> dict[str, object]:
        del state_snapshot, probe_cache
        return copy.deepcopy(self.shot_envelope)


# The common helper must both update the node's output cache and notify the
# connected Griptape parameter. A plain set_output() is insufficient for a
# live Picker -> Prompt edge.
probe = PublishProbe()
picker._publish_parameter_update(probe, "PICKER_OUT", "live-payload")
assert probe.parameter_output_values["PICKER_OUT"] == "live-payload"
assert probe.published == [("PICKER_OUT", "live-payload")]


state = picker._parse_state({
    "videos": [{
        "video_uid": "live-video",
        "source_uid": "live-video",
        "video_path": "C:/shot/live-video.mp4",
        "selected": True,
        "selection_order": 1,
        "generation_role": "mask",
    }],
})
original_retire = picker._retire_legacy_video_slot_outputs
original_reorder = picker._reorder_video_picker_parameters
try:
    picker._retire_legacy_video_slot_outputs = lambda _node: None
    picker._reorder_video_picker_parameters = lambda _node: None
    node = PublishProbe()
    picker_text = picker.HMBVideoPickerLibrary._sync_outputs_from_state(
        node,
        state,
        enforce_media_availability=False,
    )
finally:
    picker._retire_legacy_video_slot_outputs = original_retire
    picker._reorder_video_picker_parameters = original_reorder

assert [name for name, _value in node.published] == [
    "VIDEO_OUT",
    "PICKER_OUT",
    "SHOT_PICKER_OUT",
]
assert node.published[0][1] == ["C:/shot/live-video.mp4"]
assert node.published[1][1] == picker_text
assert node.published[2][1] == node.shot_envelope
assert len(node.cache_snapshots) == 3
for cached in node.cache_snapshots:
    assert cached["VIDEO_OUT"] == ["C:/shot/live-video.mp4"]
    assert cached["PICKER_OUT"] == picker_text
    assert cached["SHOT_PICKER_OUT"] == node.shot_envelope
payload = json.loads(picker_text)
assert payload["videos"][0]["video_uid"] == "live-video"
assert payload["videos"][0]["video_path"] == node.published[0][1][0]


class FirstNotificationFailureProbe(PublishProbe):
    def publish_update_to_parameter(self, name: str, value: object) -> None:
        super().publish_update_to_parameter(name, value)
        if name == "VIDEO_OUT":
            raise LookupError("simulated first notification failure")


# A failed first callback cannot leave mixed caches or prevent the sibling
# notification attempt. The method raises only after both ports were tried.
failure_probe = FirstNotificationFailureProbe()
original_retire = picker._retire_legacy_video_slot_outputs
original_reorder = picker._reorder_video_picker_parameters
try:
    picker._retire_legacy_video_slot_outputs = lambda _node: None
    picker._reorder_video_picker_parameters = lambda _node: None
    try:
        picker.HMBVideoPickerLibrary._sync_outputs_from_state(
            failure_probe,
            state,
            enforce_media_availability=False,
        )
    except RuntimeError as error:
        notification_error = error
    else:
        raise AssertionError("The staged publication must report callback failure.")
finally:
    picker._retire_legacy_video_slot_outputs = original_retire
    picker._reorder_video_picker_parameters = original_reorder

assert [name for name, _value in failure_probe.published] == [
    "VIDEO_OUT",
    "PICKER_OUT",
    "SHOT_PICKER_OUT",
]
assert len(failure_probe.cache_snapshots) == 3
failed_picker_text = failure_probe.parameter_output_values["PICKER_OUT"]
for cached in failure_probe.cache_snapshots:
    assert cached["VIDEO_OUT"] == ["C:/shot/live-video.mp4"]
    assert cached["PICKER_OUT"] == failed_picker_text
    assert cached["SHOT_PICKER_OUT"] == failure_probe.shot_envelope
assert json.loads(str(failed_picker_text))["videos"][0]["video_path"] == "C:/shot/live-video.mp4"
assert "after both output caches were staged" in str(notification_error)
assert "VIDEO_OUT (LookupError)" in str(notification_error)


print(
    "HMB VideoPicker live-output regression: PASS "
    "(atomic cache staging, independent VIDEO_OUT/PICKER_OUT/SHOT_PICKER_OUT notifications)"
)
