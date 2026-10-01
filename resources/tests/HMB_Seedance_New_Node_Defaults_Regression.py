"""Offline contract for the fresh Seedance controls shown in the UI.

Uses test-only Griptape stubs; no engine configuration, Broker request, or
billable render is involved. Grouped parameter construction is recorded
because the lightweight stub does not register ParameterGroup children.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location(
    "hmb_seedance_new_node_defaults", ROOT / "HMBSeedanceGeneration.py"
)
assert spec is not None and spec.loader is not None
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)

active_groups: list[str] = []
grouped_defaults: dict[str, object] = {}


class RecordingGroup(target.ParameterGroup):
    def __enter__(self):
        active_groups.append(self.name)
        return super().__enter__()

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            active_groups.pop()


def recording_parameter(base):
    class RecordingParameter(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if active_groups == ["Generation Settings"]:
                grouped_defaults[self.name] = self.default_value

    return RecordingParameter


with (
    mock.patch.object(target, "ParameterGroup", RecordingGroup),
    mock.patch.object(
        target, "ParameterString", recording_parameter(target.ParameterString)
    ),
    mock.patch.object(target, "ParameterInt", recording_parameter(target.ParameterInt)),
    mock.patch.object(
        target, "ParameterBool", recording_parameter(target.ParameterBool)
    ),
):
    node = target.HMBSeedanceGeneration(name="Fresh Seedance Default Regression")

assert node.get_parameter_value("model_id") == target.MODEL_NAME_SEEDANCE_2_5
assert grouped_defaults == {
    "resolution": "720p",
    "ratio": "16:9",
    "duration": 4,
    "generate_audio": False,
    "output_format": "mov",
}
assert node._output_file._default_filename == "volcengine_seedance_video.mov"

# Materialize the recorded group children as Griptape itself does before a
# user switches models. The 2.0 compatibility route must normalize MOV→MP4.
for name, value in grouped_defaults.items():
    node.set_parameter_value(name, value, initial_setup=True)
node.set_parameter_value(
    "output_file", "volcengine_seedance_video.mov", initial_setup=True
)
node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0)
assert node.get_parameter_value("output_format") == "mp4"
assert node.get_parameter_value("output_file") == "volcengine_seedance_video.mp4"
assert node.get_parameter_value("resolution") == "1080p"

print("HMB Seedance new-node defaults and 2.0 compatibility: PASS")
