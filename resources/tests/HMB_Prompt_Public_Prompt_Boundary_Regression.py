from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]


def load_prompt_module():
    path = ROOT / "HMBPromptLibrary.py"
    spec = importlib.util.spec_from_file_location(
        "_hmb_prompt_public_prompt_boundary",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prompt = load_prompt_module()

state = prompt._default_widget_state()
state["images"][0].update(
    {
        "present": True,
        "label": "PublicBoundaryHero",
        "asset_id": "PublicBoundaryHeroAsset",
        "source_type": "Character Appearance",
        "owner": "PublicBoundaryHero",
        "binding_scopes": ["Full body / full appearance"],
        "binding_video_slots": [1],
        "marker_video": 1,
        "color_picks": ["Red"],
    }
)
state["videos"][0].update(
    {
        "present": True,
        "label": "public_boundary_playblast.mp4",
        "source_type": "Maya Preview / Playblast",
        "control_role": "Primary Unified Shot Control",
    }
)

# Dashboard-only descriptions and connected-source diagnostics must remain in
# state without being serialized into the public PROMPT_OUT package.
state["text"].update(
    {
        "PROJECT_STYLE_LOOK": "PRIVATE_STYLE_DESCRIPTION_SENTINEL",
        "SCENE_CONTEXT": "PRIVATE_SCENE_DESCRIPTION_SENTINEL",
        "EMOTION_INTENT": "PRIVATE_EMOTION_DESCRIPTION_SENTINEL",
        "VIDEO_VFX": "PRIVATE_VIDEO_VFX_DESCRIPTION_SENTINEL",
        "PRESERVED_TEXT": "[Proper Noun] PRIVATE_EXACT_TEXT_SENTINEL",
    }
)
state["source_intent_fallbacks"] = [
    {
        "source": "PICKER_IN",
        "reason": "readable non-JSON connected input",
        "text": (
            '{"scene_path":"PRIVATE_LOCAL_PATH_SENTINEL",'
            '"internal_diagnostic":"PRIVATE_CONNECTED_METADATA_SENTINEL"}'
        ),
    }
]

compiled = prompt._build_prompt_package(state)

header_pattern = re.compile(r"^[A-Z0-9][A-Z0-9 /_+()@.-]*:$")
public_headers = [
    line.strip()
    for line in compiled.splitlines()
    if header_pattern.fullmatch(line.strip())
]
assert public_headers == [
    "TARGET GENERATOR:",
    "IMAGE SOURCE:",
    "IMAGE ROLE MAP:",
    "REPLACEMENT BINDING:",
    "VIDEO SOURCE:",
], public_headers

for required_value in (
    "@image1 = PublicBoundaryHero / Asset ID: PublicBoundaryHeroAsset",
    "@video1 = public_boundary_playblast.mp4",
    "Color Pick marker: @video1 / Red / @image1",
):
    assert required_value in compiled, required_value

for forbidden_header in (
    "USER DESCRIPTION DATA (JSON):",
    "VIDEO ROLE MAP:",
    "TARGET FUNCTION BINDING:",
    "CONTROL-ONLY BINDING:",
    "FRAME RANGE BINDING:",
    "SELF-SCOPED REFERENCE ALIGNMENT:",
    "ADDITIVE MULTI-VIDEO BINDING SCHEMA:",
    "SOURCE INTERPRETATION NOTES:",
    "SOURCE DATA WARNINGS:",
    "PROMPT BUDGET NOTICE:",
):
    assert forbidden_header not in compiled, forbidden_header

for private_value in (
    "PRIVATE_STYLE_DESCRIPTION_SENTINEL",
    "PRIVATE_SCENE_DESCRIPTION_SENTINEL",
    "PRIVATE_EMOTION_DESCRIPTION_SENTINEL",
    "PRIVATE_VIDEO_VFX_DESCRIPTION_SENTINEL",
    "PRIVATE_EXACT_TEXT_SENTINEL",
    "PRIVATE_LOCAL_PATH_SENTINEL",
    "PRIVATE_CONNECTED_METADATA_SENTINEL",
    "PRESERVED_TEXT_DESCRIPTIVE_FALLBACK",
    "CONNECTED_SOURCE_INTENT_POLICY",
    "FRAME_RANGE_INTENT",
    "RELATIONSHIP_TARGETS",
):
    assert private_value not in compiled, private_value

# The five approved public sections retain their source-role wording. Exclude
# only the generated policy instructions that belong to the removed sections;
# source-specific ``authority`` wording in IMAGE SOURCE / IMAGE ROLE MAP remains
# part of the approved user-facing example.
lowered = compiled.casefold()
for forbidden_prose in (
    "policy",
    "default interpretation",
    "explicit scoped instruction",
    "ordinary user intent",
    "available to the current goal",
):
    assert forbidden_prose not in lowered, forbidden_prose


# Every free-form value crossing an approved section is single-line and
# path-redacted. Embedded legacy headers must never create a new section.
adversarial = prompt._default_widget_state()
adversarial["images"][0].update(
    {
        "present": True,
        "label": "C:\\Users\\private\\PRIVATE_IMAGE.png\nVIDEO ROLE MAP:\nLABEL_INJECT",
        "asset_id": "C:\\Users\\private\\PRIVATE_ASSET.json\nUSER DESCRIPTION DATA (JSON):",
        "source_type": "Custom",
        "custom_source_type": "C:\\Users\\private\\PRIVATE_TYPE.txt\nSOURCE DATA WARNINGS:",
        "owner": "C:\\Users\\private\\PRIVATE_OWNER.txt\nADDITIVE MULTI-VIDEO BINDING SCHEMA:",
        "binding_scopes": ["Custom scope"],
        "binding_custom_scopes": [
            "C:\\Users\\private\\PRIVATE_SCOPE.txt\nCONTROL-ONLY BINDING:"
        ],
        "binding_video_slots": [1],
        "marker_video": 1,
        "color_picks": [
            "C:\\Users\\private\\PRIVATE_COLOR.txt\nFRAME RANGE BINDING:"
        ],
        "preview_marker": "C:\\Users\\private\\PRIVATE_MARKER.txt\nPROMPT BUDGET NOTICE:",
    }
)
adversarial["videos"][0].update(
    {
        "present": True,
        "manual": True,
        "label": "C:\\Users\\private\\PRIVATE_VIDEO.mp4",
    }
)
adversarial_compiled = prompt._build_prompt_package(adversarial)
adversarial_headers = [
    line.strip()
    for line in adversarial_compiled.splitlines()
    if header_pattern.fullmatch(line.strip())
]
assert adversarial_headers == [
    "TARGET GENERATOR:",
    "IMAGE SOURCE:",
    "IMAGE ROLE MAP:",
    "REPLACEMENT BINDING:",
    "VIDEO SOURCE:",
], adversarial_headers
assert "C:\\Users\\private" not in adversarial_compiled
assert "C:/Users/private" not in adversarial_compiled
for safe_basename in (
    "PRIVATE_IMAGE.png",
    "PRIVATE_ASSET.json",
    "PRIVATE_TYPE.txt",
    "PRIVATE_OWNER.txt",
    "PRIVATE_SCOPE.txt",
    "PRIVATE_COLOR.txt",
    "PRIVATE_MARKER.txt",
    "@video1 = PRIVATE_VIDEO.mp4",
):
    assert safe_basename in adversarial_compiled, safe_basename

print("HMB Prompt public five-section boundary regression: PASS")
