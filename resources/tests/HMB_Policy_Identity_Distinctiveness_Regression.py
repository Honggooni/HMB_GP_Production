from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]


def load_agent():
    path = ROOT / "HMBAgentLibrary.py"
    module_name = "_hmb_policy_identity_distinctiveness_agent"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


agent = load_agent()


def envelope(job_data: dict[str, Any]) -> str:
    return "\n".join((
        "HMB_GP_Production",
        "HMB JOB DATA (JSON):",
        json.dumps(job_data, ensure_ascii=False, separators=(",", ":")),
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
    wire_pair = agent._hmb.image_taxonomy_wire_pair(main_type, sub_type)
    if wire_pair is None:
        raise AssertionError(f"Unknown image taxonomy: {main_type} / {sub_type}")
    source_type, source_scope = wire_pair
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


def unbound_image(token: str = "@image1") -> dict[str, Any]:
    return {
        "image": token,
        "label": "UnboundReference",
        "image_main_type": agent._hmb.IMAGE_MAIN_TYPE_UNCLASSIFIED,
        "image_sub_type": "",
        "source_type": agent._hmb.IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
        "source_scope": "",
        "custom_source_type": "",
        "target_id": "",
        "relationship_targets": [],
        "bindings": [],
        "identity": {},
    }


def video(
    token: str = "@video1",
    *,
    source_type: str = "Unified Shot-Control Video",
    role: str = "Primary Unified Shot Control",
) -> dict[str, Any]:
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
    image_rows = list(images or [])
    video_rows = list(videos or [])
    return {
        "schema": "hmb-public-job-data",
        "version": 3,
        "images": image_rows,
        "videos": video_rows,
        "control_only_bindings": [],
        "frame_ranges": [],
        "connections": {
            "image_asset": bool(image_rows),
            "picker": bool(video_rows),
        },
    }


def validate_job(job_data: dict[str, Any]) -> dict[str, Any]:
    return agent._assert_public_job_data_contract(envelope(job_data))


def validate_final(job_data: dict[str, Any], final_text: str) -> None:
    validated_job = validate_job(job_data)
    manifest = agent._build_final_output_semantic_manifest(validated_job)
    agent._assert_final_output_semantic_integrity(final_text, manifest)


def manifest_for(job_data: dict[str, Any]) -> dict[str, Any]:
    return agent._build_final_output_semantic_manifest(validate_job(job_data))


def assert_unresolved_images(
    job_data: dict[str, Any],
    *,
    reason: str,
    expected_tokens: set[str],
    require_unbound: bool = True,
) -> None:
    manifest = manifest_for(job_data)
    rows = {
        str(row.get("token") or ""): row
        for row in manifest["images"]
        if str(row.get("token") or "") in expected_tokens
    }
    assert set(rows) == expected_tokens
    for row in rows.values():
        if require_unbound:
            assert row["unbound_authority"] is True
        assert any(
            relation.get("reason") == reason
            for relation in row["unresolved_relations"]
        )


failures: list[str] = []

HARD_DISTINCTIVENESS_BLOCK = (
    "Preserve each character's internal local value hierarchy, signature accents, "
    "and material breaks, and keep every character visually separable from every "
    "other character. Character distinctiveness is a hard priority over every "
    "Look transfer; adapt the Look around those identity cues."
)
PAINTED_HIGHLIGHT_BLOCK = (
    "For every resolved appearance source, preserve every repeated painted or "
    "cel-style highlight as intrinsic authored "
    "graphic treatment. Remove only illumination that is either demonstrably "
    "view-dependent captured studio illumination or explicitly typed and scoped "
    "as captured studio key, fill, or rim evidence; every uncertain highlight or "
    "edge accent remains intrinsic and must be retained."
)
INTRINSIC_EMITTER_BLOCK = (
    "For every Character, every Character Prop, and every Background Prop source, "
    "if a source-defined intrinsic emitter is present, its source image remains "
    "the sole source and authority for its design, shape, placement, color, "
    "material, and steady emissive state."
)
LOOK_TRANSFER_ONLY_BLOCK = (
    "Every resolved Look Reference is transfer-only and contributes only its "
    "declared look attributes. It must never define, supply, copy, replace, "
    "import, or acquire authority over scene/background content, location, "
    "terrain, geometry, objects, layout, composition, material identity, species, "
    "morphology, depicted detail, or vegetation arrangement."
)
SHARED_SHADOW_BLOCK = (
    "If a dark shadow would crush face, eye, or expression readability, adjust "
    "shared low-frequency ambient or reflected bounce across the entire connected "
    "local shadow field, including affected characters, props, and nearby "
    "environment, while preserving direct-light reduction and the continuous "
    "shadow boundary; never apply a selective character-only lift."
)


def check_rejected(
    name: str,
    callback: Callable[[], Any],
    fragment: str = "",
) -> None:
    try:
        callback()
    except RuntimeError as exc:
        if fragment and fragment not in str(exc):
            failures.append(
                f"{name}: rejected for the wrong reason: {exc!s}"
            )
        return
    except Exception as exc:  # pragma: no cover - diagnostic aggregation
        failures.append(
            f"{name}: raised unexpected {type(exc).__name__}: {exc!s}"
        )
        return
    failures.append(f"{name}: invalid authority contract was accepted")


def check_allowed(name: str, callback: Callable[[], Any]) -> None:
    try:
        callback()
    except Exception as exc:  # pragma: no cover - diagnostic aggregation
        failures.append(
            f"{name}: valid authority contract was rejected: "
            f"{type(exc).__name__}: {exc!s}"
        )


# A transferable Look without its required target now fails only that relation;
# the public job remains usable and the private manifest makes it context-only.
for targetless_subtype in ("Color Mood", "Render Look"):
    targetless_job = job(images=[
        image(
            "@image1",
            "TargetlessLook",
            "Look Reference",
            targetless_subtype,
            "",
        )
    ])
    check_allowed(
        f"targetless {targetless_subtype}",
        lambda case=targetless_job: assert_unresolved_images(
            case,
            reason="missing_required_target",
            expected_tokens={"@image1"},
        ),
    )


# Appearance-bearing object rows require their named appearance relation.  A
# targetless Background Prop remains readable context, but it cannot own an
# intrinsic material or emitter until its Target is resolved.
targetless_background_prop = job(images=[
    image(
        "@image1",
        "UnboundLantern",
        "Background Prop",
        "Independent Scene Prop",
        "",
    )
])
check_allowed(
    "targetless Background Prop",
    lambda: assert_unresolved_images(
        targetless_background_prop,
        reason="missing_required_target",
        expected_tokens={"@image1"},
    ),
)


# Two sheets may refine different portions of one character, but two sheets
# claiming the same subtype for the same character have no deterministic winner.
duplicate_full_appearance = job(images=[
    image(
        "@image1",
        "HeroFullA",
        "Character",
        "Full Appearance",
        "Hero_A",
    ),
    image(
        "@image2",
        "HeroFullB",
        "Character",
        "Full Appearance",
        "Hero_A",
    ),
])
check_allowed(
    "duplicate Character subtype for one target",
    lambda: assert_unresolved_images(
        duplicate_full_appearance,
        reason="duplicate_same_target_and_sub_type",
        expected_tokens={"@image1", "@image2"},
    ),
)

full_plus_face = job(images=[
    image(
        "@image1",
        "HeroFull",
        "Character",
        "Full Appearance",
        "Hero_A",
    ),
    image(
        "@image2",
        "HeroFace",
        "Character",
        "Head / Face",
        "Hero_A",
    ),
])
check_allowed(
    "Full Appearance plus Head / Face for one target",
    lambda: validate_job(full_plus_face),
)


hero = image(
    "@image1",
    "Hero",
    "Character",
    "Full Appearance",
    "Hero_A",
)


# Distinct Custom prose is not automatically a distinct target. Conflicting
# lighting directions aimed at the same named recipient must fail closed.
overlapping_custom_look = job(images=[
    hero,
    image(
        "@image2",
        "WarmHeroLight",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "For Hero_A only, apply a warm key and reduced exposure."
        ),
    ),
    image(
        "@image3",
        "CoolHeroLight",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "For Hero_A only, apply a cool key and increased exposure."
        ),
    ),
])
check_allowed(
    "overlapping Custom Look lighting for one target",
    lambda: assert_unresolved_images(
        overlapping_custom_look,
        reason="look_authority_scope_conflict",
        expected_tokens={"@image2", "@image3"},
    ),
)


# Equal attribute domains are not ambiguous when each Custom instruction names
# one different, active recipient.
hero_b = image(
    "@image2",
    "HeroB",
    "Character",
    "Full Appearance",
    "Hero_B",
)
different_target_custom_looks = job(images=[
    hero,
    hero_b,
    image(
        "@image3",
        "HeroAWarmLight",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction="For Hero_A only, apply a warm key.",
    ),
    image(
        "@image4",
        "HeroBCoolLight",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction="For Hero_B only, apply a cool key.",
    ),
])
check_allowed(
    "same-domain Custom lighting for different targets",
    lambda: validate_job(different_target_custom_looks),
)


# One standalone Custom retains the legacy scene-wide/custom instruction path;
# it does not need to invent a named renderable recipient merely to be usable.
standalone_scene_wide_custom = job(images=[
    image(
        "@image1",
        "SceneWideCustomLight",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "Apply a cool moonlit key with warm window bounce across the "
            "whole scene."
        ),
    ),
])
check_allowed(
    "single scene-wide Custom without a known renderable target",
    lambda: validate_job(standalone_scene_wide_custom),
)


# A single local Custom is allowed beside a Global Look when it owns a
# disjoint attribute domain, or when it explicitly declares a local override.
global_plus_disjoint_custom = job(images=[
    hero,
    image(
        "@image2",
        "GlobalColor",
        "Look Reference",
        "Color Mood",
        "Global Look",
    ),
    image(
        "@image3",
        "HeroLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "For Hero_A only, apply a warm key and reduced exposure."
        ),
    ),
])
check_allowed(
    "Global color plus disjoint local Custom lighting",
    lambda: validate_job(global_plus_disjoint_custom),
)

global_plus_implicit_same_domain_custom = job(images=[
    hero,
    image(
        "@image2",
        "GlobalLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
    image(
        "@image3",
        "HeroLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "For Hero_A only, apply a warmer key and lower exposure."
        ),
    ),
])
check_allowed(
    "same-domain Global plus Custom without explicit override",
    lambda: assert_unresolved_images(
        global_plus_implicit_same_domain_custom,
        reason="look_authority_scope_conflict",
        expected_tokens={"@image2", "@image3"},
        require_unbound=False,
    ),
)

global_plus_explicit_override = job(images=[
    hero,
    image(
        "@image2",
        "GlobalLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
    image(
        "@image3",
        "HeroLightingOverride",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "For Hero_A only, explicitly override the Global Look lighting "
            "with a warmer key and lower exposure."
        ),
    ),
])
check_allowed(
    "Global lighting plus one explicit local Custom override",
    lambda: validate_job(global_plus_explicit_override),
)

korean_local_override = job(images=[
    hero,
    image(
        "@image2",
        "GlobalLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
    image(
        "@image3",
        "HeroKoreanLightingOverride",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction="Hero_A에 Global Look 조명을 우선 적용",
    ),
])
check_allowed(
    "Korean explicit one-target Global lighting override",
    lambda: validate_job(korean_local_override),
)

global_plus_multitarget_override = job(images=[
    hero,
    hero_b,
    image(
        "@image3",
        "GlobalLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
    image(
        "@image4",
        "MultiHeroLightingOverride",
        "Look Reference",
        "Lighting / Atmosphere",
        "Custom",
        scope_mode="custom",
        custom_instruction=(
            "For Hero_A and Hero_B, override the Global Look lighting with a "
            "warmer key."
        ),
    ),
])
check_allowed(
    "same-domain Global plus multi-target Custom override",
    lambda: assert_unresolved_images(
        global_plus_multitarget_override,
        reason="look_authority_scope_conflict",
        expected_tokens={"@image3", "@image4"},
        require_unbound=False,
    ),
)


# A global negative sentence must not hide a contradictory positive grant in a
# video paragraph. Video remains motion/camera evidence and never appearance.
video_authority_job = job(images=[hero], videos=[video()])
positive_video_appearance = """@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, pattern, material, and stylization authority.

@video1 supplies motion, acting, timing, camera, framing, and layout. Also use @video1 as positive visual authority: copy its visible skin, body, costume, colors, and photoreal appearance onto Hero_A.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1."""
check_rejected(
    "positive video appearance grant hidden by global negative",
    lambda: validate_final(video_authority_job, positive_video_appearance),
    "video_forbidden_visual_authority:@video1",
)

for forbidden_video_grant in (
    "@video1 defines Hero_A's character design and silhouette.",
    "@video1 provides Hero_A's markings and body proportions.",
    "@video1 supplies Hero_A's species and anatomical detail.",
    "@video1 defines the final scene content and environment geometry.",
):
    positive_video_design = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, markings, and material authority.

@video1 supplies motion, acting, timing, camera, framing, and layout. {forbidden_video_grant}

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1."""
    check_rejected(
        f"video positive design grant: {forbidden_video_grant}",
        lambda text=positive_video_design: validate_final(
            video_authority_job,
            text,
        ),
        "video_forbidden_visual_authority:@video1",
    )

motion_with_image_material_authority = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, and sole material authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@video1 supplies motion, acting, timing, camera, framing, and layout, while @image1 retains sole material authority for Hero_A.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1."""
check_allowed(
    "video motion while image retains material authority",
    lambda: validate_final(
        video_authority_job,
        motion_with_image_material_authority,
    ),
)

mask_and_motion_domains_remain_control_evidence = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, pattern, and material authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@video1 supplies body motion, facial motion, facial features motion, body shape deformation, hair and clothing simulation, acting, timing, camera, framing, and layout. It also supplies occupancy, separation, silhouette, and occlusion guidance only; any temporal lighting change is timing evidence rather than final lighting or appearance authority.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1."""
check_allowed(
    "video body/facial motion and mask silhouette remain control evidence",
    lambda: validate_final(
        video_authority_job,
        mask_and_motion_domains_remain_control_evidence,
    ),
)

joint_video_image_appearance = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, pattern, and material authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@video1 supplies motion, acting, timing, camera, framing, and layout. @video1 and @image1 jointly define Hero_A's character appearance, material, and stylization.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1."""
check_rejected(
    "joint video/image appearance grant cannot evade proxy isolation",
    lambda: validate_final(video_authority_job, joint_video_image_appearance),
    "video_forbidden_visual_authority:@video1",
)

two_image_appearance_job = job(
    images=[
        hero,
        image(
            "@image2",
            "HeroFace",
            "Character",
            "Head / Face",
            "Hero_A",
        ),
    ],
    videos=[video()],
)
image_joint_owner_with_video_context = f"""@image1 (Hero) is the exact Hero_A full character appearance, identity, design, proportions, silhouette, color, pattern, and material authority.

@image2 (HeroFace) is the exact Hero_A head and face appearance, facial identity, design, proportions, color, pattern, and material authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@video1 supplies motion, acting, timing, camera, framing, and layout, while @image1/@image2 together define Hero_A's appearance and material within their declared scopes.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1 and @image2."""
check_allowed(
    "video context is not a joint appearance subject of two images",
    lambda: validate_final(
        two_image_appearance_job,
        image_joint_owner_with_video_context,
    ),
)

unbound_with_bound_video_job = job(videos=[
    video("@video1", source_type="", role=""),
    video("@video2"),
])
unbound_joint_motion = """@video1 is unbound because its type and role are missing; it is context-only and owns no motion, camera, timing, spatial, FX, appearance, lighting, or scene-content authority.

@video2 supplies primary motion, acting, performance, pose, timing, trajectory, camera, framing, layout, and composition.

@video1 and @video2 jointly define the final motion and timing.

All video references provide control information only and have no character appearance authority; appearance and identity may come only from typed image sources."""
check_rejected(
    "unbound and bound videos cannot jointly own motion",
    lambda: validate_final(
        unbound_with_bound_video_job,
        unbound_joint_motion,
    ),
    "unbound_video_authority:@video1",
)


# A valid camera-only/unbound denial cannot conceal a later positive silhouette
# grant from the same unbound image.
unbound_camera_only_job = job(images=[unbound_image()])
unbound_silhouette_grant = """@image1 is an unbound, reference-only image with no appearance, identity, design, material, look, lighting, color, pattern, texture, style, background, environment, geometry, or layout authority. It may inform camera context only. @image1 supplies Hero_A's silhouette."""
check_rejected(
    "unbound camera-only denial followed by silhouette grant",
    lambda: validate_final(unbound_camera_only_job, unbound_silhouette_grant),
    "unbound_image_authority:@image1",
)

unbound_with_bound_image_job = job(images=[
    unbound_image("@image1"),
    image(
        "@image2",
        "BoundHero",
        "Character",
        "Full Appearance",
        "Hero_A",
    ),
])
unbound_joint_appearance = f"""@image1 is an unbound, reference-only image with no appearance, identity, design, material, look, lighting, color, pattern, texture, style, background, environment, geometry, or layout authority.

@image2 (BoundHero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, pattern, and material authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@image1 and @image2 jointly define Hero_A's character appearance and material."""
check_rejected(
    "unbound and bound images cannot jointly own appearance",
    lambda: validate_final(
        unbound_with_bound_image_job,
        unbound_joint_appearance,
    ),
    "unbound_image_authority:@image1",
)


# A Look transfers lighting values and atmosphere. In the absence of a Main
# Background or explicit Shot/FX authority it cannot invent visible light/FX.
look_only_job = job(images=[
    image(
        "@image1",
        "DawnLighting",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    )
])
for visible_light_action in (
    "Create a new visible sun in frame from this Look Reference.",
    "Add new god rays across the scene from this Look Reference.",
    "Add new bloom around an invented luminous orb from this Look Reference.",
):
    unauthorized_visible_light = (
        "@image1 (DawnLighting) supplies the Global Look scene-wide lighting, "
        "illumination, exposure, and atmosphere. "
        + visible_light_action
    )
    check_rejected(
        f"Look invents visible light: {visible_light_action}",
        lambda text=unauthorized_visible_light: validate_final(
            look_only_job,
            text,
        ),
        "look_visible_light_non_creation",
    )

contradictory_look_light = """@image1 (DawnLighting) supplies the Global Look scene-wide lighting, illumination, exposure, and atmosphere. It must not create bloom. It manifests a new light source."""
check_rejected(
    "Look denial followed by manifests-new-light contradiction",
    lambda: validate_final(look_only_job, contradictory_look_light),
    "look_visible_light_non_creation",
)

look_only_transfer_safe = f"""@image1 (DawnLighting) supplies the Global Look scene-wide lighting, illumination, exposure, white balance, and atmosphere only. @image1 must not create, add, or invent any visible light source, sun, moon, god ray, lens flare, or bloom. {LOOK_TRANSFER_ONLY_BLOCK}"""
check_allowed(
    "Look-only job remains transfer-only without Main Background",
    lambda: validate_final(look_only_job, look_only_transfer_safe),
)
check_rejected(
    "Look-only job cannot define background content",
    lambda: validate_final(
        look_only_job,
        look_only_transfer_safe
        + "\n@image1 also defines the final background content, terrain, geometry, "
        "objects, layout, and composition.",
    ),
    "background_look_non_substitution",
)

look_with_authorized_fx_job = job(
    images=[
        image(
            "@image1",
            "NightAtmosphere",
            "Look Reference",
            "Lighting / Atmosphere",
            "Global Look",
            scope_mode="global",
        )
    ],
    videos=[
        video(
            source_type="FX Reference",
            role="FX Effect Only",
        )
    ],
)
look_atmosphere_with_fx_bloom = f"""@image1 (NightAtmosphere) supplies the Global Look scene-wide atmosphere, illumination, and exposure only. @image1 must not create, add, or invent any visible light source, sun, moon, god ray, lens flare, or bloom. {LOOK_TRANSFER_ONLY_BLOCK}

@video1 supplies the authorized FX effect, particle, emitter, and simulation behavior. @video1 owns the bloom activation, timing, spread, and falloff; @image1 supplies atmosphere only.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image references."""
check_allowed(
    "Look atmosphere with FX/video-authorized bloom behavior",
    lambda: validate_final(
        look_with_authorized_fx_job,
        look_atmosphere_with_fx_bloom,
    ),
)
check_rejected(
    "Look and FX cannot jointly create bloom",
    lambda: validate_final(
        look_with_authorized_fx_job,
        look_atmosphere_with_fx_bloom
        + "\n@image1 and @video1 jointly create bloom across the shot.",
    ),
    "look_visible_light_non_creation",
)


# Intrinsic emitter components are character design, not newly invented
# environment lights. Explicitly preserving them must remain a valid contract.
character_and_look_job = job(images=[
    hero,
    image(
        "@image2",
        "NightAtmosphere",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
])
intrinsic_emitter_preservation = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, and material authority. Preserve Hero_A's intrinsic color, pattern, material, stylization, and medium distinctiveness. {HARD_DISTINCTIVENESS_BLOCK} {PAINTED_HIGHLIGHT_BLOCK} @image1 remains the sole source for intrinsic emitter components such as its designed glowing eyes and chest energy core, including their shape, placement, color, material, and steady emissive identity. {INTRINSIC_EMITTER_BLOCK}

@image2 (NightAtmosphere) supplies the Global Look scene-wide lighting, illumination, exposure, and atmosphere only. It may illuminate the existing @image1 emitter components, but it has no authority to invent, remove, or redesign them and must not create a new visible sun, moon, luminous orb, god ray, volumetric beam, lens flare, or bloom. {LOOK_TRANSFER_ONLY_BLOCK} {SHARED_SHADOW_BLOCK}"""
check_allowed(
    "Character intrinsic emitter component preservation",
    lambda: validate_final(
        character_and_look_job,
        intrinsic_emitter_preservation,
    ),
)

check_rejected(
    "positive removal and redesign of image-owned intrinsic emitters",
    lambda: validate_final(
        character_and_look_job,
        intrinsic_emitter_preservation
        + "\nHowever, remove the designed glowing eyes and redesign the intrinsic "
        "chest energy core.",
    ),
    "intrinsic_emitter_source_separation",
)


# Appearance-source highlight and emitter preservation are unconditional: they
# remain mandatory even when no Look or FX source exists.
appearance_only_job = job(images=[hero])
appearance_only_safe = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, pattern, material, and stylization authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}"""
check_allowed(
    "appearance-only source preserves highlights and conditional emitters",
    lambda: validate_final(appearance_only_job, appearance_only_safe),
)
check_rejected(
    "appearance-only source missing highlight preservation",
    lambda: validate_final(
        appearance_only_job,
        "@image1 (Hero) is the exact Hero_A character appearance, identity, "
        "design, proportions, silhouette, color, pattern, and material authority. "
        + INTRINSIC_EMITTER_BLOCK,
    ),
    "painted_cel_highlight_preservation",
)
check_rejected(
    "appearance-only source missing conditional emitter preservation",
    lambda: validate_final(
        appearance_only_job,
        "@image1 (Hero) is the exact Hero_A character appearance, identity, "
        "design, proportions, silhouette, color, pattern, and material authority. "
        + PAINTED_HIGHLIGHT_BLOCK,
    ),
    "intrinsic_emitter_source_separation",
)

two_appearance_sources_job = job(images=[
    hero,
    image(
        "@image2",
        "Lantern",
        "Background Prop",
        "Independent Scene Prop",
        "Lantern_A",
    ),
])
image1_only_highlight_guard = (
    "@image1 preserves every repeated painted or cel-style highlight as intrinsic "
    "authored graphic treatment. Remove only demonstrably view-dependent captured "
    "studio key, fill, or rim illumination from @image1; every uncertain highlight "
    "or edge accent on @image1 remains intrinsic and must be retained."
)
image1_only_emitter_guard = (
    "If a source-defined intrinsic emitter is present on @image1, @image1 remains "
    "the sole source and authority for its design, shape, placement, color, "
    "material, and steady emissive state."
)
two_source_authority = (
    "@image1 (Hero) is the exact Hero_A character appearance, identity, design, "
    "proportions, silhouette, color, pattern, and material authority.\n\n"
    "@image2 (Lantern) is the exact Lantern_A background prop, object design, "
    "appearance, color, and material authority."
)
check_rejected(
    "highlight guard must cover every resolved appearance source",
    lambda: validate_final(
        two_appearance_sources_job,
        two_source_authority
        + "\n\n"
        + image1_only_highlight_guard
        + "\n\n"
        + INTRINSIC_EMITTER_BLOCK,
    ),
    "painted_cel_highlight_preservation",
)
check_rejected(
    "conditional emitter guard must cover every resolved appearance source",
    lambda: validate_final(
        two_appearance_sources_job,
        two_source_authority
        + "\n\n"
        + PAINTED_HIGHLIGHT_BLOCK
        + "\n\n"
        + image1_only_emitter_guard,
    ),
    "intrinsic_emitter_source_separation",
)


# When Character and Look coexist, the final contract must state that Look
# transfer cannot flatten the character's medium-specific distinctiveness.
character_and_render_look_job = job(images=[
    hero,
    image(
        "@image2",
        "PainterlyFinish",
        "Look Reference",
        "Render Look",
        "Global Look",
    ),
])
complete_distinctiveness_guard = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, and silhouette authority. Preserve its intrinsic color, pattern, material, stylization, and medium distinctiveness; @image2 may transfer presentation only and must not overwrite, replace, homogenize, or average those character-specific traits. {HARD_DISTINCTIVENESS_BLOCK} {PAINTED_HIGHLIGHT_BLOCK} If a source-defined intrinsic emitter component is present on @image1, @image1 remains the sole source and authority for its design, shape, placement, color, material, and steady emissive state. {INTRINSIC_EMITTER_BLOCK}

@image2 (PainterlyFinish) supplies the Global Look render style, shading, surface finish, and rendering language only. It must not create a new visible sun, moon, luminous orb, god ray, volumetric beam, lens flare, or bloom. {LOOK_TRANSFER_ONLY_BLOCK}"""
check_allowed(
    "complete Character/Look intrinsic distinctiveness guard",
    lambda: validate_final(
        character_and_render_look_job,
        complete_distinctiveness_guard,
    ),
)

# A resolved appearance source may state sole ownership of its own intrinsic
# material in a Look paragraph. That exemption must not permit joint ownership.
appearance_owner_with_look = (
    complete_distinctiveness_guard
    + "\n\n@image2 transfers presentation-only rendering attributes, and intrinsic "
    "material identity remains solely with @image1."
)
check_allowed(
    "Look paragraph preserves Character sole intrinsic material owner",
    lambda: validate_final(
        character_and_render_look_job,
        appearance_owner_with_look,
    ),
)
appearance_owner_sourced_with_look = (
    complete_distinctiveness_guard
    + "\n\n@image2 supplies Render Look shading and finish only, with intrinsic "
    "material identity sourced solely from @image1."
)
check_allowed(
    "Look paragraph accepts direct sourced solely appearance ownership",
    lambda: validate_final(
        character_and_render_look_job,
        appearance_owner_sourced_with_look,
    ),
)
check_rejected(
    "Look and Character cannot jointly own intrinsic material identity",
    lambda: validate_final(
        character_and_render_look_job,
        complete_distinctiveness_guard
        + "\n\n@image2 and @image1 jointly define and own the intrinsic material "
        "identity used by the final character.",
    ),
    "background_look_non_substitution",
)

# Relighting requires the lighting domain itself to remain resolved. Resolved
# color/render domains cannot stand in for a conflicted lighting claim.
resolved_combined_look_job = job(images=[
    hero,
    image(
        "@image2",
        "ResolvedCombinedLook",
        "Look Reference",
        "Color / Look / Lighting",
        "Global Look",
        scope_mode="global",
    ),
])
resolved_combined_manifest = manifest_for(resolved_combined_look_job)
assert resolved_combined_manifest["relighting_look_tokens"] == ["@image2"]

lighting_conflicted_combined_job = job(images=[
    hero,
    image(
        "@image2",
        "ConflictedCombinedLook",
        "Look Reference",
        "Color / Look / Lighting",
        "Global Look",
        scope_mode="global",
    ),
    image(
        "@image3",
        "CompetingGlobalLight",
        "Look Reference",
        "Lighting / Atmosphere",
        "Global Look",
        scope_mode="global",
    ),
])
lighting_conflicted_manifest = manifest_for(lighting_conflicted_combined_job)
combined_row = next(
    row for row in lighting_conflicted_manifest["images"]
    if row["token"] == "@image2"
)
assert "lighting" in combined_row["unresolved_domains"]
assert "color" not in combined_row["unresolved_domains"]
assert "render" not in combined_row["unresolved_domains"]
assert "@image2" not in lighting_conflicted_manifest["relighting_look_tokens"]
assert "@image3" not in lighting_conflicted_manifest["relighting_look_tokens"]

missing_distinctiveness_guard = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, and silhouette authority. {PAINTED_HIGHLIGHT_BLOCK} If a source-defined intrinsic emitter component is present on @image1, @image1 remains the sole source and authority for its design, shape, placement, color, material, and steady emissive state.

@image2 (PainterlyFinish) supplies the Global Look render style, shading, surface finish, and rendering language only. It must not create a new visible sun, moon, luminous orb, god ray, volumetric beam, lens flare, or bloom."""
check_rejected(
    "missing Character/Look intrinsic distinctiveness guard",
    lambda: validate_final(
        character_and_render_look_job,
        missing_distinctiveness_guard,
    ),
    "character_intrinsic_distinctiveness",
)

contradictory_distinctiveness_guard = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, and silhouette authority. Its intrinsic color, pattern, material, stylization, and native medium must not alter lighting, and overwrite those traits. {HARD_DISTINCTIVENESS_BLOCK} {PAINTED_HIGHLIGHT_BLOCK} If a source-defined intrinsic emitter component is present on @image1, @image1 remains the sole source and authority for its design, shape, placement, color, material, and steady emissive state.

@image2 (PainterlyFinish) supplies the Global Look render style, shading, surface finish, and rendering language only. It must not create a new visible sun, moon, luminous orb, god ray, volumetric beam, lens flare, or bloom."""
check_rejected(
    "distinctiveness denial followed by positive overwrite",
    lambda: validate_final(
        character_and_render_look_job,
        contradictory_distinctiveness_guard,
    ),
    "character_intrinsic_distinctiveness",
)

for destructive_restyle in (
    "However, repaint its intrinsic colors and markings from @image2.",
    "However, retexture its intrinsic materials from @image2.",
):
    disguised_trait_replacement = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, and silhouette authority. Preserve its intrinsic color, pattern, material, stylization, and medium distinctiveness. {HARD_DISTINCTIVENESS_BLOCK} {PAINTED_HIGHLIGHT_BLOCK} {destructive_restyle} If a source-defined intrinsic emitter component is present on @image1, @image1 remains the sole source and authority for its design, shape, placement, color, material, and steady emissive state.

@image2 (PainterlyFinish) supplies the Global Look render style, shading, surface finish, and rendering language only. It must not create a new visible sun, moon, luminous orb, god ray, volumetric beam, lens flare, or bloom."""
    check_rejected(
        f"positive trait replacement: {destructive_restyle}",
        lambda text=disguised_trait_replacement: validate_final(
            character_and_render_look_job,
            text,
        ),
        "character_intrinsic_distinctiveness",
    )

check_rejected(
    "Look homogenizes character material and value structure",
    lambda: validate_final(
        character_and_render_look_job,
        complete_distinctiveness_guard
        + "\nApply the same clay material, identical local value structure, and "
        "uniform accent scheme to all characters.",
    ),
    "character_intrinsic_distinctiveness",
)

for destructive_highlight in (
    "Remove the repeated cel-style painted highlights to match the Look Reference.",
    "Erase every uncertain edge highlight as captured studio glare.",
):
    check_rejected(
        f"protected highlight removal: {destructive_highlight}",
        lambda text=destructive_highlight: validate_final(
            character_and_render_look_job,
            complete_distinctiveness_guard + "\n" + text,
        ),
        "painted_cel_highlight_preservation",
    )


# Background Prop images own the design of their built-in emitters. A generic
# Primary Unified video supplies motion/camera only; merely mentioning an
# intrinsic emitter must not force an FX activation/timing clause.
background_prop_with_primary_job = job(
    images=[
        image(
            "@image1",
            "Lantern",
            "Background Prop",
            "Independent Scene Prop",
            "Lantern_A",
        )
    ],
    videos=[video()],
)
background_prop_emitter_preservation = f"""@image1 (Lantern) is the exact Lantern_A background prop, object design, appearance, and material authority. @image1 remains the sole source for its intrinsic emitter component, including the designed emitter shape, placement, color, material, and identity. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@video1 supplies motion, acting, timing, camera, framing, and layout only.

All video references provide control information only and have no prop or character appearance authority; appearance, identity, and material come solely from @image1."""
check_allowed(
    "Background Prop emitter protection without Primary behavior clause",
    lambda: validate_final(
        background_prop_with_primary_job,
        background_prop_emitter_preservation,
    ),
)


# A non-optical dust FX reference owns ordinary particle simulation behavior,
# not light/emitter behavior. Conditional image ownership remains sufficient
# for any source-defined character emitter that might exist.
character_with_dust_fx_job = job(
    images=[hero],
    videos=[
        video(
            source_type="FX Reference",
            role="FX Effect Only",
        )
    ],
)
character_with_dust_fx = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, and material authority. If a source-defined intrinsic emitter component is present on @image1, @image1 remains the sole source and authority for its design, shape, placement, color, and material. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@video1 supplies the authorized non-optical dust FX effect, particle simulation, timing, and behavior. It controls dust motion, density, dispersion, and falloff only.

All video references provide control information only and have no character appearance authority; appearance, identity, and material come solely from @image1."""
check_allowed(
    "Character plus non-optical dust FX without light behavior clause",
    lambda: validate_final(character_with_dust_fx_job, character_with_dust_fx),
)


# Main Background owns depicted content; Look may transfer attributes only.
background_and_look_job = job(images=[
    image(
        "@image1",
        "ForestSet",
        "Environment / Background",
        "Main Background",
        "",
    ),
    image(
        "@image2",
        "PainterlyForest",
        "Look Reference",
        "Render Look",
        "Global Look",
    ),
])
background_and_look_safe = """@image1 is the sole background and scene-content authority for the location, terrain, geometry, objects, material and vegetation identity, morphology, depicted detail, layout, and composition.

@image2 supplies the Global Look render style, shading character, rendering-detail treatment, and finish only. Never copy, replace, import, or transfer its background location, terrain, geometry, objects, material identity, vegetation species, morphology, micro-density, layout, or composition. @image2 must not create a visible light source, sun, moon, luminous emitter, god ray, volumetric beam, lens flare, or bloom."""
check_allowed(
    "Main Background content and transfer-only Render Look",
    lambda: validate_final(background_and_look_job, background_and_look_safe),
)
check_rejected(
    "Render Look positively acquires scene species and material identity",
    lambda: validate_final(
        background_and_look_job,
        background_and_look_safe
        + "\n@image2 transfers the forest material identity, tree species, leaf "
        "morphology, and vegetation micro-density into the final background.",
    ),
    "background_look_non_substitution",
)
check_rejected(
    "Look and Main Background cannot jointly own scene content",
    lambda: validate_final(
        background_and_look_job,
        background_and_look_safe
        + "\n@image2 and @image1 jointly define the final background content, "
        "terrain geometry, object layout, material identity, tree species, and "
        "vegetation morphology.",
    ),
    "background_look_non_substitution",
)


# Typed FX owns temporal behavior, never a persistent scene light object.
check_rejected(
    "typed FX creates a persistent sun object",
    lambda: validate_final(
        look_with_authorized_fx_job,
        look_atmosphere_with_fx_bloom
        + "\n@video1 creates a new persistent sun and installs a permanent lamp "
        "as scene-visible light objects.",
    ),
    "fx_persistent_light_creation:@video1",
)


# Dark-shadow readability is shared with the connected local lighting field.
shadow_job = job(images=[
    hero,
    image(
        "@image2",
        "ForestSet",
        "Environment / Background",
        "Main Background",
        "",
    ),
])
shadow_safe = f"""@image1 (Hero) is the exact Hero_A character appearance, identity, design, proportions, silhouette, color, pattern, and material authority. {PAINTED_HIGHLIGHT_BLOCK} {INTRINSIC_EMITTER_BLOCK}

@image2 is the sole background and environment scene-content authority for location, terrain, geometry, objects, layout, and spatial shadow boundaries.

{SHARED_SHADOW_BLOCK}"""
check_allowed(
    "shared local shadow-field readability",
    lambda: validate_final(shadow_job, shadow_safe),
)
check_rejected(
    "selective character-only shadow lift",
    lambda: validate_final(
        shadow_job,
        shadow_safe
        + "\nIf the shadow is dark, brighten only the character with a selective "
        "fill while leaving props and environment unchanged.",
    ),
    "shadow_readability_shared_field",
)


# Captured-light cleanup has two narrow alternatives. Explicit type and scope
# evidence is sufficient even when the captured studio light is not proven
# camera/view-dependent; authored and uncertain highlights remain protected.
typed_scoped_highlight_block = (
    "Preserve every repeated painted or cel-style highlight as intrinsic authored "
    "graphic treatment. Neutralize only highlights explicitly typed and scoped "
    "as captured studio key, fill, or rim lighting evidence. Preserve every "
    "uncertain highlight or edge accent as intrinsic treatment."
)
check_allowed(
    "explicitly typed and scoped captured studio light removal",
    lambda: validate_final(
        character_and_render_look_job,
        complete_distinctiveness_guard.replace(
            PAINTED_HIGHLIGHT_BLOCK,
            typed_scoped_highlight_block,
        ),
    ),
)
check_rejected(
    "captured studio light removal missing explicit type and scope",
    lambda: validate_final(
        character_and_render_look_job,
        complete_distinctiveness_guard
        + "\nNeutralize only highlights that resemble captured studio key, fill, "
        "or rim lighting.",
    ),
    "painted_cel_highlight_preservation",
)
check_rejected(
    "uncertain highlight removal despite typed captured-light scope",
    lambda: validate_final(
        character_and_render_look_job,
        complete_distinctiveness_guard
        + "\nNeutralize uncertain highlights explicitly typed and scoped as "
        "captured studio key-light evidence.",
    ),
    "painted_cel_highlight_preservation",
)


# Every Local/Secondary conflict must survive as its exact relation record. A
# generic conflict disclaimer elsewhere in the result is not interchangeable.
conflict_hero = image(
    "@image1",
    "ConflictHero",
    "Character",
    "Full Appearance",
    "Hero_Conflict",
)
conflict_hero["bindings"] = [
    {
        "video": "@video1",
        "marker_color": "Red",
        "target_scope": "Full body / full appearance",
    },
    {
        "video": "@video2",
        "marker_color": "Red",
        "target_scope": "Full body / full appearance",
    },
]
local_motion_conflict_job = job(
    images=[conflict_hero],
    videos=[
        video("@video1", role="Local Motion Detail Only"),
        video("@video2", role="Secondary Motion Only"),
    ],
)
local_motion_conflict_manifest = manifest_for(local_motion_conflict_job)
assert len(local_motion_conflict_manifest["unresolved_motion_relations"]) == 2

motion_conflict_prefix = f"""@image1 (ConflictHero) is the exact Hero_Conflict character appearance, identity, design, proportions, silhouette, color, pattern, and material authority. {PAINTED_HIGHLIGHT_BLOCK} If a source-defined intrinsic emitter component is present on @image1, @image1 remains the sole source and authority for its design, shape, placement, color, material, and steady emissive state.

@video1 supplies local motion, pose, acting, performance, and timing only for its resolved relation.

@video2 supplies secondary motion, pose, acting, performance, and timing only for its resolved relation.

All video references provide control information only and have no character appearance authority; appearance and identity come solely from @image1."""
whole_shot_conflict_record = (
    "The Local/Secondary conflict between @video1 and @video2 for target "
    "Hero_Conflict, function motion, spatial domain Full body / full appearance "
    "| Red, across the whole-shot scope remains unresolved; it must not average, "
    "blend, select, or choose a winner by slot or order."
)
check_allowed(
    "exact whole-shot Local/Secondary conflict record",
    lambda: agent._assert_final_output_semantic_integrity(
        motion_conflict_prefix + "\n\n" + whole_shot_conflict_record,
        local_motion_conflict_manifest,
    ),
)
check_rejected(
    "generic unrelated Local/Secondary conflict disclaimer",
    lambda: agent._assert_final_output_semantic_integrity(
        motion_conflict_prefix
        + "\n\nA Local/Secondary conflict is unresolved somewhere in the shot and "
        "must not average or choose a winner by slot.",
        local_motion_conflict_manifest,
    ),
    "local_motion_conflict_isolation",
)
check_rejected(
    "Local/Secondary conflict record with wrong target",
    lambda: agent._assert_final_output_semantic_integrity(
        motion_conflict_prefix
        + "\n\n"
        + whole_shot_conflict_record.replace("Hero_Conflict", "Other_Hero"),
        local_motion_conflict_manifest,
    ),
    "local_motion_conflict_isolation",
)
check_rejected(
    "Local/Secondary conflict record with wrong peer token",
    lambda: agent._assert_final_output_semantic_integrity(
        motion_conflict_prefix
        + "\n\n"
        + whole_shot_conflict_record.replace("@video2", "@video3"),
        local_motion_conflict_manifest,
    ),
    "local_motion_conflict_isolation",
)

interval_conflict_manifest = copy.deepcopy(local_motion_conflict_manifest)
for relation in interval_conflict_manifest["unresolved_motion_relations"]:
    relation["start_frame"] = 101
    relation["end_frame"] = 162
interval_conflict_record = whole_shot_conflict_record.replace(
    "across the whole-shot scope",
    "during frames 101-162",
)
check_allowed(
    "exact frame-interval Local/Secondary conflict record",
    lambda: agent._assert_final_output_semantic_integrity(
        motion_conflict_prefix + "\n\n" + interval_conflict_record,
        interval_conflict_manifest,
    ),
)
check_rejected(
    "whole-shot prose cannot satisfy an interval conflict record",
    lambda: agent._assert_final_output_semantic_integrity(
        motion_conflict_prefix + "\n\n" + whole_shot_conflict_record,
        interval_conflict_manifest,
    ),
    "local_motion_conflict_isolation",
)


if failures:
    raise AssertionError(
        "HMB policy identity/distinctiveness regression failures:\n- "
        + "\n- ".join(failures)
    )


print("HMB policy identity/distinctiveness regression passed")
