from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    module_name = f"_hmb_semantic_integrity_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


agent = load("HMBAgentLibrary")


def expect_rejected(callback: Any, fragment: str = "") -> None:
    try:
        callback()
    except RuntimeError as exc:
        if fragment:
            assert fragment in str(exc), str(exc)
        return
    raise AssertionError("invalid semantic contract was accepted")


def envelope(job: dict[str, Any]) -> str:
    return "\n".join((
        "HMB_GP_Production",
        "HMB JOB DATA (JSON):",
        json.dumps(job, ensure_ascii=False, separators=(",", ":")),
        "FX/TIMING SOURCE DATA (JSON):",
        "{}",
        "USER DESCRIPTION DATA (JSON):",
        "{}",
        "",
    ))


def image(
    token: str,
    label: str,
    main_type: str,
    sub_type: str,
    target: str,
    *,
    scope_mode: str = "",
    custom_instruction: str = "",
) -> dict[str, Any]:
    source_type, source_scope = agent._hmb.image_taxonomy_wire_pair(
        main_type,
        sub_type,
    )
    record: dict[str, Any] = {
        "image": token,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "source_type": source_type,
        "source_scope": source_scope,
        "custom_source_type": "",
        "target_id": target,
        "relationship_targets": [],
        "bindings": [],
        "identity": {},
    }
    if sub_type in {"Lighting / Atmosphere", "Color / Look / Lighting"}:
        record["target_scope_mode"] = scope_mode
        record["custom_look_instruction"] = custom_instruction
    return record


def video(token: str, source_type: str, role: str) -> dict[str, Any]:
    return {
        "video": token,
        "label": token[1:],
        "source_type": source_type,
        "custom_source_type": "",
        "control_role": role,
        "custom_control_role": "",
        "control_role_explicit": True,
        "keep_out": "",
        "identity": {},
    }


def job(
    *,
    images: list[dict[str, Any]] | None = None,
    videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "hmb-public-job-data",
        "version": 3,
        "images": list(images or []),
        "videos": list(videos or []),
        "control_only_bindings": [],
        "frame_ranges": [],
        "connections": {"image_asset": bool(images), "picker": bool(videos)},
    }


# One primary Original may coexist with every typed auxiliary reference.
valid_videos = [
    video(
        "@video1",
        "Unified Shot-Control Video",
        "Primary Unified Shot Control",
    ),
    video("@video2", "Mask / Control Reference", "Mask / Guide Only"),
    video(
        "@video3",
        "Depth / Spatial Reference",
        "Spatial Alignment Verification Only",
    ),
    video(
        "@video4",
        "Motion Guide / Retargeting Reference",
        "Derived Motion Decoding Only",
    ),
]
assert agent._assert_public_job_data_contract(
    envelope(job(videos=valid_videos))
)["videos"] == valid_videos
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        envelope(job(videos=[valid_videos[0], {**valid_videos[0], "video": "@video2"}]))
    ),
    "multiple Primary Unified",
)


semantic_job = agent._assert_public_job_data_contract(
    envelope(job(
        images=[
            image(
                "@image1",
                "ForestSet",
                "Environment / Background",
                "Main Background",
                "ForestSet",
            ),
            image(
                "@image2",
                "DawnLook",
                "Look Reference",
                "Color / Look / Lighting",
                "Global Look",
                scope_mode="global",
            ),
            image(
                "@image3",
                "Hero",
                "Character",
                "Full Appearance",
                "Hero",
            ),
        ],
        videos=[valid_videos[0]],
    ))
)
manifest = agent._build_final_output_semantic_manifest(semantic_job)
good = """@image1 (ForestSet) is the sole background and scene-content authority.

@image2 (DawnLook) supplies the Global Look scene-wide: transfer its color palette and grade, lighting and exposure, plus render style and shading. Never copy, replace, or import its background location, geometry, objects, or composition.

@image3 is the exact Hero character appearance, identity, design, proportions, silhouette, and material authority.

@video1 is the Primary Unified Shot Control for motion, acting, timing, camera, framing, and layout. Its control visualization is proxy shading only and it has no character appearance authority; character appearance comes solely from @image3."""
agent._assert_final_output_semantic_integrity(good, manifest)
expect_rejected(
    lambda: agent._assert_final_output_semantic_integrity(
        good.replace("@image3", "the character"),
        manifest,
    ),
    "missing:@image3",
)
expect_rejected(
    lambda: agent._assert_final_output_semantic_integrity(
        good.replace("Hero", "Pilot"),
        manifest,
    ),
    "target:@image3",
)
expect_rejected(
    lambda: agent._assert_final_output_semantic_integrity(
        good.replace("camera, framing, and layout", "gesture detail"),
        manifest,
    ),
    "video_authority:@video1",
)
expect_rejected(
    lambda: agent._assert_final_output_semantic_integrity(
        good.replace(
            "Its control visualization is proxy shading only and it has no character appearance authority; character appearance comes solely from @image3.",
            "Use it as a general reference.",
        ),
        manifest,
    ),
    "video_appearance_isolation:@video1",
)

# A single explicit shot-wide exclusion is valid; repeating identical
# appearance-isolation prose in every video paragraph is not required.
global_video_job = agent._assert_public_job_data_contract(
    envelope(job(videos=[valid_videos[0], valid_videos[1]]))
)
global_video_manifest = agent._build_final_output_semantic_manifest(global_video_job)
global_video_final = """@video1 supplies motion, acting, timing, camera, framing, and layout as the Primary Unified Shot Control.

@video2 supplies mask, occupancy, silhouette, and occlusion guidance only.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image references."""
agent._assert_final_output_semantic_integrity(
    global_video_final,
    global_video_manifest,
)


custom_instruction = "Use a cool moonlit key with warm window bounce."
custom_job = agent._assert_public_job_data_contract(
    envelope(job(images=[
        image(
            "@image1",
            "NightLighting",
            "Look Reference",
            "Lighting / Atmosphere",
            "Custom",
            scope_mode="custom",
            custom_instruction=custom_instruction,
        )
    ]))
)
custom_manifest = agent._build_final_output_semantic_manifest(custom_job)
custom_tag = custom_manifest["images"][0]["custom_instruction_evidence_tag"]
custom_final = (
    "@image1 supplies shared scene lighting and atmosphere using a cool moonlit "
    f"key with warm window bounce across all visible subjects. {custom_tag}"
)
agent._assert_final_output_semantic_integrity(custom_final, custom_manifest)
assert custom_tag not in agent._strip_semantic_evidence_tags(custom_final)
expect_rejected(
    lambda: agent._assert_final_output_semantic_integrity(
        custom_final.replace(custom_tag, ""),
        custom_manifest,
    ),
    "custom_look_instruction:@image1",
)

# Custom may instead address one named/local recipient. It retains typed
# lighting authority and exact SHA/tag evidence without being rewritten into
# a Global Look or requiring any shared/scene-wide wording.
local_custom_instruction = (
    "Apply a warm key and reduced exposure to Hero_A only."
)
local_custom_job = agent._assert_public_job_data_contract(
    envelope(job(images=[
        image(
            "@image1",
            "HeroLighting",
            "Look Reference",
            "Lighting / Atmosphere",
            "Custom",
            scope_mode="custom",
            custom_instruction=local_custom_instruction,
        )
    ]))
)
local_custom_manifest = agent._build_final_output_semantic_manifest(
    local_custom_job
)
local_custom_tag = local_custom_manifest["images"][0][
    "custom_instruction_evidence_tag"
]
local_custom_final = (
    "@image1 supplies lighting, exposure, and atmosphere: apply a warm key "
    f"and reduced exposure to Hero_A only. {local_custom_tag}"
)
agent._assert_final_output_semantic_integrity(
    local_custom_final,
    local_custom_manifest,
)

# Custom has its own authored-scope claim key. A Global claim must not absorb
# it, and two different local Custom instructions may coexist; an exact
# duplicate still fails closed for overlapping attribute authority.
global_and_local = job(images=[
    image(
        "@image1",
        "GlobalLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
    image(
        "@image2",
        "HeroLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=local_custom_instruction,
    ),
])
assert len(agent._assert_public_job_data_contract(
    envelope(global_and_local)
)["images"]) == 2

second_local_instruction = "Apply a cool rim to Forest_A only."
distinct_custom_scopes = job(images=[
    image(
        "@image1",
        "HeroLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=local_custom_instruction,
    ),
    image(
        "@image2",
        "ForestLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=second_local_instruction,
    ),
])
assert len(agent._assert_public_job_data_contract(
    envelope(distinct_custom_scopes)
)["images"]) == 2
duplicate_custom_scope = json.loads(json.dumps(distinct_custom_scopes))
duplicate_custom_scope["images"][1]["custom_look_instruction"] = (
    local_custom_instruction
)
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        envelope(duplicate_custom_scope)
    ),
    "Look target attribute authority is ambiguous",
)


# A machine-only Prompt generation change invalidates the old publication even
# when the concise SHOT_PROMPT_IN bytes are unchanged.
visible = "Visible Prompt"
visible_hash = hashlib.sha256(visible.encode("utf-8")).hexdigest()
base_context = {
    "schema": "hmb-agent-shot-context",
    "version": 1,
    "channel_uuid": "11111111-1111-4111-8111-111111111111",
    "shot_uuid": "22222222-2222-4222-8222-222222222222",
    "shot_number": 1,
    "shot_name": "Shot 1",
    "prompt_generation": 4,
    "visible_prompt_sha256": visible_hash,
    "image_media_sha256": "a" * 64,
    "video_media_sha256": "b" * 64,
}
probe = object.__new__(agent.HMBAgentLibrary)
probe._hmb_shot_context = dict(base_context)
probe._hmb_last_generator_snapshot = {
    "schema": "hmb-agent-generator-shot-snapshot",
    "version": 1,
    **{key: base_context[key] for key in (
        "channel_uuid", "shot_uuid", "shot_number", "shot_name",
        "prompt_generation", "visible_prompt_sha256", "image_media_sha256",
        "video_media_sha256",
    )},
    "final_text_sha256": "c" * 64,
}
probe._hmb_remote_prompt_publication = {"published": True}
same_source = SimpleNamespace(
    _hmb_agent_shot_context=lambda _value: dict(base_context)
)
assert probe._invalidate_stale_generator_authority_for_prompt(
    visible,
    source_node=same_source,
) is False
changed_context = {**base_context, "prompt_generation": 5}
changed_source = SimpleNamespace(
    _hmb_agent_shot_context=lambda _value: dict(changed_context)
)
assert probe._invalidate_stale_generator_authority_for_prompt(
    visible,
    source_node=changed_source,
) is True
assert probe._hmb_shot_context == {}
assert probe._hmb_last_generator_snapshot == {}
assert probe._hmb_remote_prompt_publication == {}


print("HMB Agent/Generator semantic integrity regression passed")
