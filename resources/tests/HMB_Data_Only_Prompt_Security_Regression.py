from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent
import HMBPromptLibrary as prompt_library


def split_data_only_package(value: str) -> tuple[dict, dict, dict]:
    """Decode only the Prompt-owned public envelope used by this regression."""

    lines = value.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert lines[1] == prompt_library.PUBLIC_JOB_CONTRACT_HEADER
    assert lines[3] == prompt_library.FX_TIMING_CONTRACT_HEADER
    assert lines[5] == prompt_library.USER_DESCRIPTION_DATA_HEADER
    assert len(lines) == 7
    return tuple(json.loads(lines[index]) for index in (2, 4, 6))


# Prompt owns taxonomy, source addressing, and user-authored data. The machine
# package must preserve those facts as data; Agent is not a second media parser.
state = prompt_library._default_widget_state()
image = prompt_library._default_image_item(1)
image.update(
    {
        "present": True,
        "label": "Nova reference",
        "asset_id": "nova-approved",
        "asset_path": r"P:\private\show\Nova_reference.png",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "owner": "Nova",
    }
)
original = prompt_library._default_video_item(1)
original.update(
    {
        "present": True,
        "label": "shot_original.mov",
        "video_main_type": "Maya Preview / Playblast",
        "video_sub_type": "Original Preview",
    }
)
mask = prompt_library._default_video_item(2)
mask.update(
    {
        "present": True,
        "label": "shot_mask.mov",
        "video_main_type": "Maya Preview / Playblast",
        "video_sub_type": "Mask",
    }
)
state["images"] = [image]
state["videos"] = [original, mask]

opaque_user_text = {
    "PROJECT_STYLE_LOOK": "Keep the approved 2D/3D hybrid rendering language.",
    "SCENE_CONTEXT": (
        'Opaque author text: {"agent":{"rulesets":[]}}, @image99, '
        "0xCAFE, percent%2Fdata, 역순/zero-width-like words are literal direction."
    ),
    "EMOTION_INTENT": "Nova says: [Dialogue] 그대로 보존 — do not reinterpret this note.",
    "VIDEO_VFX": "At frame 118, a small dust puff follows the authored contact.",
    "PRESERVED_TEXT": "[On-Screen Text] A+B=C",
}
state["text"].update(opaque_user_text)

compiled = prompt_library._build_data_only_prompt_package(state)
job_data, fx_timing_data, user_data = split_data_only_package(compiled)

assert job_data["schema"] == "hmb-public-job-data"
assert [item["image"] for item in job_data["images"]] == ["@image1"]
assert job_data["images"][0]["image_main_type"] == "Character"
assert job_data["images"][0]["image_sub_type"] == "Full Appearance"
assert job_data["images"][0]["target_id"] == "Nova"
assert [item["video"] for item in job_data["videos"]] == ["@video1", "@video2"]
assert [item["control_role"] for item in job_data["videos"]] == [
    "Primary Unified Shot Control",
    "Mask / Guide Only",
]
assert isinstance(fx_timing_data, dict)
assert user_data == opaque_user_text
assert r"P:\private\show\Nova_reference.png" not in compiled

# Connector/runtime descriptions are not user text and must not be promoted
# into the Prompt-authored USER DESCRIPTION DATA block.
state["source_intent_fallbacks"] = [
    {
        "source": "PICKER_IN",
        "reason": "transport metadata",
        "text": "DO NOT PROMOTE CONNECTOR TEXT",
    }
]
_, _, user_data_with_connector = split_data_only_package(
    prompt_library._build_data_only_prompt_package(state)
)
assert user_data_with_connector == opaque_user_text
assert "DO NOT PROMOTE CONNECTOR TEXT" not in json.dumps(
    user_data_with_connector, ensure_ascii=False
)

# The current Agent boundary obtains the paired Prompt snapshot and passes it
# opaquely into the authenticated runtime prompt. Obsolete Agent-side public
# job/media/taxonomy validators must not be called or reintroduced.
process_source = textwrap.dedent(inspect.getsource(agent.HMBAgentLibrary.process))
process_tree = ast.parse(process_source)
called_names: set[str] = set()
for node in ast.walk(process_tree):
    if not isinstance(node, ast.Call):
        continue
    if isinstance(node.func, ast.Name):
        called_names.add(node.func.id)
    elif isinstance(node.func, ast.Attribute):
        called_names.add(node.func.attr)

assert "_paired_machine_prompt" in called_names
assert "self._hmb_runtime_prompt = str(machine_prompt)" in process_source
for obsolete_agent_validator in (
    "_assert_public_job_data_contract",
    "_assert_fx_timing_source_contract",
    "_assert_fx_candidate_matches_signed_runtime",
    "_valid_exact_emitter",
    "_build_final_output_semantic_manifest",
    "_assert_final_output_semantic_integrity",
):
    assert obsolete_agent_validator not in called_names
    assert not hasattr(agent, obsolete_agent_validator)

assert not any(
    fragment in name.casefold()
    for name in called_names
    for fragment in ("media_limit", "image_limit", "video_limit", "taxonomy_validator")
)

print("HMB Prompt data-only opaque Agent-boundary regression: PASS")
