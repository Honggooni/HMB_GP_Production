from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load("_hmb_video_taxonomy_prompt", "HMBPromptLibrary.py")
agent = load("_hmb_video_taxonomy_agent", "HMBAgentLibrary.py")

expected = dict(prompt.VIDEO_TAXONOMY_WIRE_MAP)
assert len(prompt.VIDEO_MAIN_TYPE_CHOICES) == 6  # placeholder + five families
assert sum(len(values) for values in prompt.VIDEO_SUB_TYPE_CHOICES.values()) == 17
assert prompt.VIDEO_SUB_TYPE_CHOICES["FX / Simulation Reference"] == [
    "Explosion", "Dust", "Particle",
]
assert "FX Behavior" not in prompt.VIDEO_SUB_TYPE_CHOICES["FX / Simulation Reference"]
assert "Simulation" not in prompt.VIDEO_SUB_TYPE_CHOICES["FX / Simulation Reference"]
assert "Unified Shot-Control Video" not in prompt.VIDEO_MAIN_TYPE_CHOICES
assert "Timing / Edit Reference" not in prompt.VIDEO_MAIN_TYPE_CHOICES

# Legacy Main/Sub wire selections are deliberately released rather than
# migrated.  Their labels/media remain ordinary durable video state.
legacy = prompt._default_widget_state()
legacy["videos"][0].update({
    "present": True,
    "label": "legacy.mp4",
    "source_type": "Unified Shot-Control Video",
    "control_role": "Primary Unified Shot Control",
})
released = prompt._normalize_state(legacy)["videos"][0]
assert released["video_main_type"] == "Select Video Main Type"
assert released["video_sub_type"] == ""
assert released["source_type"] == "Role Required / Select Video Type"
assert released["control_role"] == ""
assert released["label"] == "legacy.mp4"

# Every new UI pair projects to an already signed/allowed Agent wire pair.
for index, ((main_type, sub_type), wire_pair) in enumerate(expected.items(), start=1):
    state = prompt._default_widget_state()
    state["videos"][0].update({
        "present": True,
        "label": f"taxonomy-{index}.mp4",
        "video_main_type": main_type,
        "video_sub_type": sub_type,
    })
    normalized = prompt._normalize_state(state)
    video = normalized["videos"][0]
    assert (video["source_type"], video["control_role"]) == wire_pair
    assert video["source_type"] in agent._PUBLIC_VIDEO_SOURCE_TYPES
    assert video["control_role"] in agent._PUBLIC_VIDEO_ROLES
    package = prompt._build_data_only_prompt_package(normalized)
    validated = agent._assert_public_job_data_contract(package)
    assert validated["videos"][0]["source_type"] == wire_pair[0]
    assert validated["videos"][0]["control_role"] == wire_pair[1]

print(
    "HMB compact video taxonomy regression: PASS "
    "(legacy release, 17 UI pairs, signed Agent wire compatibility)"
)
