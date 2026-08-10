from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load_module("HMBPromptLibrary")
agent = load_module("HMBAgentLibrary")
source = (ROOT / "HMBPromptLibrary.py").read_text(encoding="utf-8")
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
guide = (ROOT / "resources" / "maya" / "HMBVideoPicker_Maya_Guide.txt").read_text(
    encoding="utf-8-sig"
)

legacy_scope_phrases = (
    "explicit user goal may use any visible property",
    "explicit current user goal may use any visible or supplied property",
    "may broaden, narrow, or reframe",
    "broader, narrower, or different use",
    "user's explicit goal may use any readable property",
)
for legacy in legacy_scope_phrases:
    assert legacy.casefold() not in source.casefold(), legacy
    assert legacy.casefold() not in guide.casefold(), legacy

assert prompt.PROMPT_POLICY_SOURCE_VERSION == "2026-08-06.animation-look-continuity.v3"
assert prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256 == (
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
)
assert prompt.PROMPT_POLICY_SOURCE_VERSION == prompt._hmb._AGENT_POLICY_VERSION
assert (
    prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256
    == prompt._hmb._AGENT_POLICY_CONTRACT_SHA256
)
assert agent._prompt_policy_source_identity() == (
    prompt.PROMPT_POLICY_SOURCE_VERSION,
    prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256,
)
assert agent._assert_prompt_policy_identity_matches_signed_runtime() == (
    prompt.PROMPT_POLICY_SOURCE_VERSION,
    prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256,
)
assert "내부 정책 공유폴더" not in agent_source
assert "사용자 로컬에 동봉된 hmb_agent_core.dat" in agent_source
assert "_assert_prompt_policy_identity_matches_signed_runtime()" in agent_source
# The public Prompt package identifies only its downstream target. Detailed
# production defaults belong exclusively to the signed Agent policy and must
# not be exposed or duplicated in user-visible Prompt text.
prompt_only = prompt._build_prompt_package(prompt._default_widget_state())
assert (
    "TARGET GENERATOR:\n"
    "This prompt is written for the active downstream target generator or execution system.\n"
) in prompt_only
for hidden_policy_detail in (
    "Interpret all source bindings",
    "PRODUCTION INTEGRATION DEFAULTS:",
    "Unless an explicit scoped instruction changes it, stable deep focus uses camera-relative scene depth",
    "Characters and environment within the same focus range receive the same optical response",
    "Do not selectively focus or blur only characters or only environment by semantic object class",
    "do not invent focus pumping or rack focus",
    "environment map or IBL is explicitly approved as lighting authority",
    "If supplied but not approved, treat it only as implementation evidence",
    "If none is usable, infer only low-frequency sky and ground illumination, broad light direction, color temperature, contrast, and weather cues",
    "do not invent an HDRI or dramatic light source",
    "Environment dummies carry macro layout, volume, distribution, height, path, depth, occlusion, and structural density",
    "approved background owns micro-density, surface appearance, palette, and atmosphere",
    "Relight characters under shared scene lighting, exposure, atmosphere, white balance, and grade",
    "no unstated character-only lift, fill, saturation, contrast boost, or beautification",
    "Scene-space effects require bidirectional contact, occlusion, shadow, reflected light, atmospheric scattering",
    "Camera, lens, and post effects have no world contact and cast no world shadow",
    "Direct optical illumination and shadow follow onset, peak, and falloff",
    "secondary physical response may use causal inertia, diffusion, delay, damping, dissipation, and recovery",
):
    assert hidden_policy_detail not in prompt_only, hidden_policy_detail
assert "subject-only blur" not in prompt_only.casefold()

# The bundled signed v3 policy remains the authority for the removed public
# defaults; the Prompt compiler must not become their second policy store.
signed_policy = "\n".join(str(document) for document in prompt._hmb.get_internal_policy_documents())
for policy_anchor in (
    "camera-relative scene depth",
    "semantic object class",
    "environment map",
    "macro layout",
    "structural density",
    "shared scene lighting",
    "beautification",
    "bidirectional contact",
    "onset, peak, and falloff",
    "inertia",
    "diffusion",
    "delay",
    "damping",
    "dissipation",
    "recovery",
):
    assert policy_anchor.casefold() in signed_policy.casefold(), policy_anchor

# A narrow optional role label cannot silently discard the animator-authored
# full-shot state. It remains an emphasis unless the user supplies a scoped
# property assignment.
state = prompt._default_widget_state()
state["videos"][0].update(
    {
        "present": True,
        "label": "animator_color_playblast.mp4",
        "source_type": "Maya Preview / Playblast",
        "control_role": "Timing Only",
    }
)
compiled = prompt._build_prompt_package(state)
for anchor in (
    "protected animator-authored acting, motion, pose, timing, trajectory, contact",
    "camera, framing, visibility, occlusion, relative depth, and spatial arrangement",
    "selected role emphasizes timing verification without narrowing that shot state",
    "a role label alone does not narrow them",
    "Proxy marker colors, Color Pick markers, temporary Maya materials, dummy shading",
    "not final identity, material, lighting, or look authority",
    "explicit scoped instruction may change only its named property",
    "named Target or clearly scene-wide scope",
    "if no temporal subset is stated or clearly implied, it applies to the whole shot",
    "otherwise only to that subset",
):
    assert anchor in compiled, anchor

# Structured control-only instructions stay usable, but their override cannot
# spill from one target/boundary into unrelated appearance or motion fields.
control_line = prompt._format_control_only_binding(
    {
        "video": 1,
        "target": "Hero_A",
        "function": "Focus",
        "marker": "Red",
        "boundary": "Frames 48-72",
    }
)
for anchor in (
    "named visible or supplied property",
    "named Target and declared Control Boundary",
    "if no separate temporal subset is stated or clearly implied, it applies to the whole shot",
    "otherwise only to that subset",
    "does not expand into unrelated identity, material, lighting, motion, camera",
):
    assert anchor in control_line, anchor

# Every self-scoped auxiliary role uses the same bounded override vocabulary;
# a missing role or binding remains non-gating without becoming unlimited use.
for spec in prompt.SELF_SCOPED_AUXILIARY_REFERENCE_SPECS.values():
    authority = str(spec["authority"])
    assert "explicit scoped instruction" in authority
    assert "named property" in authority
    assert "named target or clearly scene-wide scope" in authority
    assert "if no temporal subset is stated or clearly implied, it applies to the whole shot" in authority
    assert "otherwise only to that subset" in authority
context = prompt._self_scoped_auxiliary_reference(
    {
        "source_type": "FX Reference",
        "control_role": "Context Only",
    },
    2,
)
assert context is not None
assert "default context interpretation" in context["authority"]
assert "explicit scoped instruction" in context["authority"]

# Image-role output exposes the same appearance/lighting boundary even before
# the sealed Agent policy is injected. Color Pick remains an address.
image_state = prompt._default_widget_state()
image_state["images"][0].update(
    {
        "present": True,
        "label": "hero_character_sheet.png",
        "source_type": "Character Appearance",
        "owner": "Hero_A",
        "color_picks": ["Red"],
    }
)
image_compiled = prompt._build_prompt_package(image_state)
for anchor in (
    "Color Pick values = target, mask, and reference-routing addresses",
    "not final intrinsic color, material, lighting, or background appearance authority",
    "intrinsic identity, color, pattern, and material character",
    "studio lighting, baked highlight/shadow, matte spill, and halo are not scene-light authority",
):
    assert anchor in image_compiled, anchor

environment_role = prompt._image_role_line(
    {"source_type": "Environment / Background", "owner": "Scene / Environment"}, 2
)
assert "continuous environment appearance and target lighting context" in environment_role
assert "including dummy regions" in environment_role
lighting_role = prompt._image_role_line(
    {"source_type": "Lighting / Atmosphere Reference", "owner": "Global Look"}, 3
)
assert "implementation evidence for the approved background or sequence look" in lighting_role
assert "explicitly approved as lighting authority" in lighting_role

# Multi-video output must carry the bounded scope rule and preserve source
# independence without promoting optional metadata into an authority gate.
multi = prompt._default_widget_state()
multi["videos"][0].update(
    {
        "present": True,
        "label": "animator_color_playblast.mp4",
        "source_type": "Maya Preview / Playblast",
        "control_role": "Spatial Alignment Verification Only",
    }
)
second = prompt._default_video_item(2)
second.update(
    {
        "present": True,
        "label": "lighting_reference.mp4",
        "source_type": "Lighting / Look Reference",
        "control_role": "Lighting / Look Only",
    }
)
multi["videos"].append(second)
multi_compiled = prompt._build_prompt_package(multi)
assert "ADDITIVE MULTI-VIDEO BINDING SCHEMA:" in multi_compiled
assert "default attribute interpretation" in multi_compiled
assert "explicit scoped instruction may change only its named property" in multi_compiled
assert "Missing optional metadata or bindings never invents data" in multi_compiled

print(
    "HMB look attribute-scope compiler regression: PASS "
    "(Playblast authority / proxy isolation / scoped overrides / multi-video)"
)
