from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
EXPECTED_ENVELOPE_SHA256 = (
    "e46328be5f3bf9d0bc05d52b12cc6b14cc71b3125297d01efc2100e47276c914"
)
EXPECTED_PAYLOAD_SHA256 = (
    "c5d9e518c21c65ea10460343afcc485c8b595a46feb5047fca0300af2b7cc228"
)
EXPECTED_POLICY_SHA256 = (
    "a88b0404ce1628d4ab93480960d75e73e94b751d248f4921ae6df1c329606058"
)
EXPECTED_BINDING_SHA256 = (
    "36871668bae849974b3c95e09ccd1bfaa9bae848550200e8d27f294ff294dce5"
)
EXPECTED_VERSION = "2026-08-11.agent-shot-quality.v4"
EXPECTED_CONTRACT_SHA256 = (
    "b9f6a430737ad266022d1b53da99b1afb7defbc0348f88a59ebf6da5b7e1dec5"
)
EXPECTED_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"


def load_common():
    spec = importlib.util.spec_from_file_location(
        "_hmb_v4_semantic_policy_verifier",
        ROOT / "_hmb_common.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def paragraph_containing(document: str, marker: str) -> str:
    marker_folded = marker.casefold()
    matches = [
        paragraph.strip()
        for paragraph in document.split("\n\n")
        if marker_folded in paragraph.casefold()
    ]
    assert len(matches) == 1, (marker, len(matches))
    return matches[0]


common = load_common()
encoded = POLICY_PATH.read_bytes()
assert hashlib.sha256(encoded).hexdigest() == EXPECTED_ENVELOPE_SHA256
envelope = json.loads(encoded.decode("utf-8"))
assert envelope == {
    "schema": "hmb-agent-policy-envelope-v3",
    "algorithm": "RSASSA-PKCS1-v1_5-SHA256",
    "key_id": EXPECTED_SIGNING_KEY_ID,
    "payload_sha256": EXPECTED_PAYLOAD_SHA256,
    "payload": envelope["payload"],
    "signature": envelope["signature"],
}
payload = common._decode_signed_agent_policy_envelope(encoded)
common._validate_agent_policy_payload(payload)
assert payload["schema"] == "hmb-agent-policy-v3"
assert payload["final_policy_version"] == EXPECTED_VERSION
assert payload["final_motion_look_policy_sha256"] == EXPECTED_CONTRACT_SHA256
assert payload["policy_sha256"] == EXPECTED_POLICY_SHA256
assert payload["binding_sha256"] == EXPECTED_BINDING_SHA256

policy = str(payload["policy"]).strip()
binding = str(payload["binding"]).strip()
assert hashlib.sha256(policy.encode("utf-8")).hexdigest() == EXPECTED_POLICY_SHA256
assert hashlib.sha256(binding.encode("utf-8")).hexdigest() == EXPECTED_BINDING_SHA256

# The v4 policy is a pre-generation instruction contract. It never claims
# generated-video inspection, severity grading, approval, rejection, or
# regeneration capabilities.
instruction_boundary = (
    "Semantic validation examines only the proposed pre-generation instruction "
    "and never asserts a downstream result state or action."
)
knowledge_boundary = (
    "never state or imply that a downstream result is known or guaranteed"
)
for document in (policy, binding):
    folded = document.casefold()
    assert instruction_boundary.casefold() in folded
    assert knowledge_boundary.casefold() in folded
    for unsupported_claim in (
        "the agent inspects generated frames",
        "the agent measures final pixels",
        "automatic visual qc",
        "blocker/major/minor",
        "automatic defect severity classification",
        "automatic policy rejection",
        "automatic regeneration",
        "automatic visual qc is performed",
        "automatically rejects generated video",
        "automatically regenerates generated video",
        "output is automatically approved",
        "generated frames were inspected and approved",
    ):
        assert unsupported_claim not in folded

project_boundary = paragraph_containing(policy, "PRE-GENERATION POLICY BOUNDARY:")
for boundary in (
    "receives only that serialized string",
    "does not open source media",
    "inspect a Maya scene",
    "measure geometry or pixels",
    "observe downstream results",
    "not a claim that the downstream generator deterministically guarantees",
):
    assert boundary.casefold() in project_boundary.casefold()

# Actor/Ghost/Pattern values are routing addresses with exact membership and
# temporary shader scope; they never become final appearance authority.
actor_names = ("Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink")
ghost_names = ("Sky Blue", "Mint", "Beige")
pattern_names = ("Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern")
for document in (policy, binding):
    marker_contract = paragraph_containing(document, "Actor 7")
    marker_folded = marker_contract.casefold()
    for marker_name in actor_names + ghost_names + pattern_names:
        assert marker_name.casefold() in marker_folded
    for required in (
        "Actor Shader",
        "Surface Shader",
        "lighting-independent",
        "final material",
        "Pattern 4",
    ):
        assert required.casefold() in marker_folded

# Playblast/Mask/Depth remain relative evidence; only an explicitly scoped
# Official Scale Sheet or validated numeric contract can carry absolute scale.
project_scale = paragraph_containing(policy, "SCALE AUTHORITY:")
binding_scale = paragraph_containing(binding, "For scale interpretation")
for scale_contract in (project_scale, binding_scale):
    folded = scale_contract.casefold()
    for required in (
        "Official Scale Sheet",
        "validated numeric contract",
        "Depth",
        "Ghost",
        "Pattern",
        "non-uniform",
        "frame-to-frame scale pulsation",
    ):
        assert required.casefold() in folded
assert "none supplies absolute dimensions" in project_scale.casefold()
assert "not absolute-dimension authority" in binding_scale.casefold()

# Character hue-family continuity and restrained child-TV illumination are
# required in both project and shot instructions.
project_color = paragraph_containing(
    policy,
    "CHARACTER COLOR AND CHILDREN'S TV ANIMATION READABILITY:",
)
binding_color = paragraph_containing(
    binding,
    "Preserve approved character color families",
)
assert "intrinsic color" in project_color.casefold()
assert "color families" in binding_color.casefold()
for color_contract in (project_color, binding_color):
    color_folded = color_contract.casefold()
    for required in (
        "children's TV animation readability",
        "strong glow",
        "bloom",
        "excessive backlight",
        "high-frequency luminance flicker",
    ):
        assert required.casefold() in color_folded

# Temporal stability protects identity while retaining approved acting,
# transformations, camera, contact, FX timing, and secondary motion.
project_temporal = paragraph_containing(policy, "TEMPORAL IDENTITY STABILITY:")
binding_temporal = paragraph_containing(binding, "Require temporal stability")
for temporal_contract in (project_temporal, binding_temporal):
    folded = temporal_contract.casefold()
    for required in (
        "texture crawling or boiling",
        "marking slippage",
        "pop-in/pop-out",
        "intended physical scale",
        "acting",
        "secondary motion",
    ):
        assert required.casefold() in folded

# Motion-reference appearance is isolated from final look in both documents.
for document in (policy, binding):
    motion_contract = paragraph_containing(document, "reference-video color")
    folded = motion_contract.casefold()
    assert "external motion reference" in folded
    assert "not final-look authority" in folded
    for appearance_attribute in (
        "material",
        "texture",
        "shading",
        "shadow",
        "highlight",
        "glow",
        "lighting",
        "grade",
    ):
        assert appearance_attribute in folded

print(
    "HMB v4 signed policy semantic regression: PASS "
    f"({EXPECTED_VERSION}, contract {EXPECTED_CONTRACT_SHA256[:12]})"
)
