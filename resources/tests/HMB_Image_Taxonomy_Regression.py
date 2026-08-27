from __future__ import annotations

import copy
import importlib.util
import json
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


common = load("_hmb_image_taxonomy_common", "_hmb_common.py")
prompt = load("_hmb_image_taxonomy_prompt", "HMBPromptLibrary.py")
image_asset = load("_hmb_image_taxonomy_asset", "HMBImageAssetLibrary.py")
agent = load("_hmb_image_taxonomy_agent", "HMBAgentLibrary.py")


def expect_rejected(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("invalid image taxonomy authority was accepted")


def replace_job(package: str, job: dict) -> str:
    lines = package.splitlines()
    assert lines[1] == prompt.PUBLIC_JOB_CONTRACT_HEADER
    lines[2] = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
    return "\n".join(lines)


def assert_unbound_image(
    package: str,
    *,
    token: str,
    reason: str,
) -> None:
    """Assert v4.5's relation-local failure without weakening wire validation."""

    validated_job = agent._assert_public_job_data_contract(package)
    manifest = agent._build_final_output_semantic_manifest(validated_job)
    row = next(
        image
        for image in manifest["images"]
        if image.get("token") == token
    )
    assert row["unbound_authority"] is True
    assert any(
        relation.get("reason") == reason
        for relation in row["unresolved_relations"]
    )

assert prompt.IMAGE_MAIN_TYPE_CHOICES == [
    "Select Image Main Type",
    "Character",
    "Character Prop",
    "Environment / Background",
    "Background Prop",
    "Look Reference",
    "Custom / Context",
]
assert "Scene / Look Reference" not in prompt.IMAGE_MAIN_TYPE_CHOICES
assert "Character Appearance" not in prompt.IMAGE_MAIN_TYPE_CHOICES
taxonomy_payload = common.image_taxonomy_payload()
assert prompt._image_taxonomy_payload() == taxonomy_payload
assert image_asset._taxonomy_payload() == taxonomy_payload
assert taxonomy_payload["schema"] == "hmb-image-taxonomy"
assert taxonomy_payload["version"] == 2
assert taxonomy_payload["main_type_count"] == 6
assert taxonomy_payload["sub_type_count"] == 26
assert taxonomy_payload["pair_count"] == 26
assert len(common.IMAGE_TAXONOMY_WIRE_MAP) == 26
assert prompt.image_sub_type_choices_for_main_type("Look Reference")[-3:] == [
    "ch_Scale",
    "bg_Scale",
    "ch_Scale / bg_Scale",
]
for retired_subtype in ("Scale", "Composition", "Scale / Composition"):
    released_scale = prompt._default_image_item(1)
    released_scale.update({
        "present": True,
        "label": "retired-scale-sheet.png",
        "image_main_type": "Look Reference",
        "image_sub_type": retired_subtype,
        "owner": "Camera / Composition",
    })
    prompt._normalize_image_binding_fields(released_scale)
    assert released_scale["image_main_type"] == "Select Image Main Type"
    assert released_scale["image_sub_type"] == ""
    assert released_scale["owner"] == ""
    released_asset_taxonomy = image_asset._normalize_image_taxonomy_fields({
        "image_main_type": "Look Reference",
        "image_sub_type": retired_subtype,
    })
    assert released_asset_taxonomy["image_main_type"] == "Select Image Main Type"
    assert released_asset_taxonomy["image_sub_type"] == ""

# Old Main/Sub/Target/Color state is intentionally released, while the image
# identity and media remain available for the user to classify again.
legacy = prompt._default_widget_state()
legacy["images"][0].update({
    "present": True,
    "label": "legacy.png",
    "asset_id": "legacy",
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
    "binding_scopes": ["Full body / full appearance"],
    "owner": "hero",
    "color_picks": ["Red"],
})
released = prompt._normalize_state(legacy)["images"][0]
assert released["image_main_type"] == "Select Image Main Type"
assert released["image_sub_type"] == ""
assert released["source_type"] == "Role Required / Select Source Type"
assert released["scope"] == ""
assert released["owner"] == ""
assert released["color_picks"] == [""]
assert released["label"] == "legacy.png"
assert released["asset_id"] == "legacy"

exact_taxonomy_records: set[tuple[str, str, str, str, str]] = set()
visible_documents: set[str] = set()
semantic_fingerprints: set[str] = set()
packages_by_taxonomy: dict[tuple[str, str], tuple[str, dict]] = {}

for (main_type, sub_type), wire_pair in common.IMAGE_TAXONOMY_WIRE_MAP.items():
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        # Keep every non-taxonomy input identical so uniqueness cannot be
        # accidentally supplied by a changing file name.
        "label": "shared-taxonomy-reference.png",
        "image_main_type": main_type,
        "image_sub_type": sub_type,
    })
    if main_type == "Look Reference":
        if sub_type in common.IMAGE_GENERAL_LOOK_REFERENCE_SUB_TYPES:
            item["owner"] = common.IMAGE_GLOBAL_LOOK_TARGET
        elif sub_type in common.IMAGE_SCALE_REFERENCE_SUB_TYPES:
            item["owner"] = common.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS[sub_type]
    normalized = prompt._normalize_image_binding_fields(item)
    assert (normalized["source_type"], normalized["scope"]) == wire_pair
    state = prompt._default_widget_state()
    state["images"] = [normalized]
    package = prompt._build_data_only_prompt_package(state)
    validated = agent._assert_public_job_data_contract(package)
    record = validated["images"][0]
    assert record["image_main_type"] == main_type
    assert record["image_sub_type"] == sub_type
    assert (record["source_type"], record["source_scope"]) == wire_pair
    exact_taxonomy_records.add((
        record["image_main_type"],
        record["image_sub_type"],
        record["source_type"],
        record["source_scope"],
        record["target_id"],
    ))
    visible_documents.add(prompt._build_prompt_package(state))
    semantic_fingerprints.add(prompt._prompt_semantic_fingerprint(state))
    packages_by_taxonomy[(main_type, sub_type)] = (package, validated)

assert len(exact_taxonomy_records) == len(common.IMAGE_TAXONOMY_WIRE_MAP) == 26
assert len(visible_documents) == 26
assert len(semantic_fingerprints) == 26

# Scale sheets may address only their typed named domain or the canonical all
# target. Camera / Composition and Global Look are no longer valid recipients.
scale_target_state = prompt._default_widget_state()
scale_target_state["images"] = []
for slot, label, main_type, sub_type, owner in (
    (1, "Hero", "Character", "Full Appearance", "Hero"),
    (2, "Forest", "Environment / Background", "Main Background", "Forest"),
    (3, "CharacterScale", "Look Reference", "ch_Scale", "Hero"),
    (4, "BackgroundScale", "Look Reference", "bg_Scale", "Forest"),
    (
        5,
        "CombinedScale",
        "Look Reference",
        "ch_Scale / bg_Scale",
        "ch_all / bg_all",
    ),
):
    scale_item = prompt._default_image_item(slot)
    scale_item.update({
        "present": True,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "owner": owner,
    })
    scale_target_state["images"].append(scale_item)
overlapping_scale_package = prompt._build_data_only_prompt_package(scale_target_state)
expect_rejected(
    lambda: agent._assert_public_job_data_contract(overlapping_scale_package)
)

# Removing the domain-wide combined claim leaves the two disjoint typed claims
# valid. This guards against rejecting independent character/background ratios.
scale_target_state["images"] = scale_target_state["images"][:-1]
scale_target_package = prompt._build_data_only_prompt_package(scale_target_state)
scale_target_job = agent._assert_public_job_data_contract(scale_target_package)
assert [row["target_id"] for row in scale_target_job["images"][2:]] == [
    "Hero",
    "Forest",
]
for invalid_target in ("Camera / Composition", "Global Look", "Forest"):
    invalid_scale_job = copy.deepcopy(scale_target_job)
    invalid_scale_job["images"][2]["target_id"] = invalid_target
    expect_rejected(
        lambda job=invalid_scale_job: agent._assert_public_job_data_contract(
            replace_job(scale_target_package, job)
        )
    )

# A domain-wide scale claim conflicts with a named member of that domain, as do
# two separate sheets claiming the same named target. Disjoint domains remain
# valid as exercised above.
for first_target, second_target in (
    ("Hero", "Hero"),
    ("ch_all", "Hero"),
    ("ch_all / bg_all", "Forest"),
):
    conflicting_job = copy.deepcopy(scale_target_job)
    conflicting_job["images"][2]["target_id"] = first_target
    if first_target == "ch_all / bg_all":
        conflicting_job["images"][2]["image_sub_type"] = "ch_Scale / bg_Scale"
        conflicting_job["images"][2]["source_scope"] = (
            "Character / Background Relative Size / Placement Only"
        )
    duplicate_claim = copy.deepcopy(conflicting_job["images"][2])
    duplicate_claim["image"] = "@image5"
    duplicate_claim["label"] = "SecondScale"
    duplicate_claim["image_sub_type"] = (
        "bg_Scale" if second_target == "Forest" else "ch_Scale"
    )
    duplicate_claim["source_scope"] = (
        "Background Relative Size / Placement Only"
        if second_target == "Forest"
        else "Character Relative Size Only"
    )
    duplicate_claim["target_id"] = second_target
    conflicting_job["images"].append(duplicate_claim)
    expect_rejected(
        lambda job=conflicting_job: agent._assert_public_job_data_contract(
            replace_job(scale_target_package, job)
        )
    )

# Exhaustive Look Target contract: seven Sub Types by eleven persisted Target
# classes. General Look keeps only blank, explicit Global Look, and renderable
# named targets. Scale rows keep their typed named domain or canonical all target.
look_subtypes = prompt.image_sub_type_choices_for_main_type("Look Reference")
general_look_subtypes = list(look_subtypes[:4])
global_scope_look_subtypes = list(
    common.IMAGE_GLOBAL_SCOPE_LOOK_REFERENCE_SUB_TYPES
)
look_target_matrix = [
    "",
    "Global Look",
    "Custom",
    "Camera / Composition",
    "ch_all",
    "bg_all",
    "ch_all / bg_all",
    "None",
    "Hero",
    "Sword",
    "Forest",
    "Tree",
]
named_target_rows = [
    ("Hero", "Character", "Full Appearance"),
    ("Sword", "Character Prop", "Handheld Prop"),
    ("Forest", "Environment / Background", "Main Background"),
    ("Tree", "Background Prop", "Independent Scene Prop"),
]


def expected_look_target(subtype: str, target: str) -> str:
    if subtype in global_scope_look_subtypes:
        return "Custom" if target == "Custom" else "Global Look"
    if subtype in general_look_subtypes:
        return (
            ""
            if target in (
                common.IMAGE_SYSTEM_TARGETS
                | set(common.IMAGE_RESERVED_TARGET_ALIASES)
            ).difference(common.IMAGE_GENERAL_LOOK_ALLOWED_SYSTEM_TARGETS)
            else target
        )
    default = prompt.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS[subtype]
    if subtype == "ch_Scale" and target in {"Hero", "Sword", default}:
        return target
    if subtype == "bg_Scale" and target in {"Forest", "Tree", default}:
        return target
    if (
        subtype == "ch_Scale / bg_Scale"
        and target in {"Hero", "Sword", "Forest", "Tree", default}
    ):
        return target
    return default


def raw_agent_target_is_valid(subtype: str, target: str) -> bool:
    if subtype in global_scope_look_subtypes:
        return target in {"Global Look", "Custom"}
    if subtype in general_look_subtypes:
        return bool(target) and target not in (
            common.IMAGE_SYSTEM_TARGETS
            | set(common.IMAGE_RESERVED_TARGET_ALIASES)
        ).difference(common.IMAGE_GENERAL_LOOK_ALLOWED_SYSTEM_TARGETS)
    if subtype == "ch_Scale":
        return target in {"Hero", "Sword", "ch_all"}
    if subtype == "bg_Scale":
        return target in {"Forest", "Tree", "bg_all"}
    return target in {"Hero", "Sword", "Forest", "Tree", "ch_all / bg_all"}


look_target_matrix_count = 0
for look_subtype in look_subtypes:
    for authored_target in look_target_matrix:
        matrix_state = prompt._default_widget_state()
        matrix_state["images"] = []
        for slot, (label, main_type, sub_type) in enumerate(
            named_target_rows,
            start=1,
        ):
            named_row = prompt._default_image_item(slot)
            named_row.update({
                "present": True,
                "label": label,
                "image_main_type": main_type,
                "image_sub_type": sub_type,
                "owner": label,
            })
            matrix_state["images"].append(named_row)
        look_row = prompt._default_image_item(5)
        look_row.update({
            "present": True,
            "label": "Look Sheet",
            "image_main_type": "Look Reference",
            "image_sub_type": look_subtype,
            "owner": authored_target,
            "look_custom_instruction": (
                "Use the authored custom shared-lighting scope."
                if authored_target == "Custom"
                else ""
            ),
            # A default is source metadata, not another authored Target. It
            # must always be rebuilt for the effective destination subtype.
            "asset_default_target": authored_target,
        })
        matrix_state["images"].append(look_row)
        normalized_matrix_state = prompt._normalize_state(matrix_state)
        normalized_look = normalized_matrix_state["images"][-1]
        expected_target = expected_look_target(look_subtype, authored_target)
        expected_default = (
            "Global Look"
            if look_subtype in global_scope_look_subtypes
            else (
                ""
                if look_subtype in general_look_subtypes
                else prompt.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS[look_subtype]
            )
        )
        assert normalized_look["owner"] == expected_target, (
            look_subtype,
            authored_target,
            normalized_look["owner"],
        )
        assert normalized_look["asset_default_target"] == expected_default

        matrix_package = prompt._build_data_only_prompt_package(
            normalized_matrix_state
        )
        if look_subtype in general_look_subtypes and not expected_target:
            # A missing semantic Target remains valid on the public wire so
            # unrelated shot sources survive. The private v4.5 manifest makes
            # this Look row non-authoritative until its Target is resolved.
            assert_unbound_image(
                matrix_package,
                token="@image5",
                reason="missing_required_target",
            )
            look_target_matrix_count += 1
            continue
        matrix_job = agent._assert_public_job_data_contract(matrix_package)
        assert matrix_job["images"][-1]["target_id"] == expected_target

        forged_job = copy.deepcopy(matrix_job)
        forged_job["images"][-1]["target_id"] = authored_target
        if look_subtype in global_scope_look_subtypes:
            forged_job["images"][-1]["target_scope_mode"] = (
                "custom" if authored_target == "Custom" else "global"
            )
            forged_job["images"][-1]["custom_look_instruction"] = (
                "Use the authored custom shared-lighting scope."
                if authored_target == "Custom"
                else ""
            )
        if raw_agent_target_is_valid(look_subtype, authored_target):
            validated_forged = agent._assert_public_job_data_contract(
                replace_job(matrix_package, forged_job)
            )
            assert validated_forged["images"][-1]["target_id"] == authored_target
        else:
            expect_rejected(
                lambda job=forged_job, package=matrix_package: (
                    agent._assert_public_job_data_contract(
                        replace_job(package, job)
                    )
                )
            )
        look_target_matrix_count += 1

assert look_target_matrix_count == 7 * 12

# Every canonical Sub Type transition is deterministic. General Look defaults
# stay blank; entering any Scale subtype assigns only that subtype's typed all
# target. In particular, no Scale all token may survive a return to general Look.
look_transition_matrix_count = 0
for source_subtype in look_subtypes:
    source_target = prompt.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS.get(
        source_subtype,
        "",
    )
    for destination_subtype in look_subtypes:
        transition = prompt._default_image_item(1)
        transition.update({
            "present": True,
            "label": "Transition Look",
            "image_main_type": "Look Reference",
            "image_sub_type": source_subtype,
            "owner": source_target,
            "asset_default_target": source_target,
        })
        prompt._normalize_image_binding_fields(transition)
        transition["image_sub_type"] = destination_subtype
        prompt._normalize_image_binding_fields(transition)
        destination_target = prompt.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS.get(
            destination_subtype,
            (
                "Global Look"
                if destination_subtype in global_scope_look_subtypes
                else (
                    "Global Look"
                    if source_subtype in global_scope_look_subtypes
                    else ""
                )
            ),
        )
        assert transition["owner"] == destination_target, (
            source_subtype,
            destination_subtype,
            transition["owner"],
        )
        destination_default = prompt.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS.get(
            destination_subtype,
            (
                "Global Look"
                if destination_subtype in global_scope_look_subtypes
                else ""
            ),
        )
        assert transition["asset_default_target"] == destination_default
        assert (transition["source_type"], transition["scope"]) == (
            common.IMAGE_TAXONOMY_WIRE_MAP[
                ("Look Reference", destination_subtype)
            ]
        )
        look_transition_matrix_count += 1

assert look_transition_matrix_count == 7 * 7

# The two authoring choices formerly collapsed to an identical no-video job.
color_mood_package, color_mood_job = packages_by_taxonomy[
    ("Look Reference", "Color Mood")
]
render_look_package, render_look_job = packages_by_taxonomy[
    ("Look Reference", "Render Look")
]
assert color_mood_package != render_look_package
assert color_mood_job["images"][0]["source_scope"] == "Color mood only"
assert render_look_job["images"][0]["source_scope"] == "Render look only"

# Agent fail-closes exact taxonomy and Look-only relationship/binding authority.
# Blank is a safe unassigned authoring state; a non-empty General Look Target
# must be Global Look or the canonical address of an active renderable row.
full_look_package, full_look_job = packages_by_taxonomy[
    ("Look Reference", "Color / Look / Lighting")
]
full_look_record = full_look_job["images"][0]
assert full_look_record["target_id"] == "Global Look"
assert full_look_record["target_scope_mode"] == "global"
assert full_look_record["custom_look_instruction"] == ""
assert full_look_record["bindings"] == []
assert full_look_record["relationship_targets"] == []

custom_look_state = prompt._default_widget_state()
custom_look_state["images"][0].update({
    "present": True,
    "label": "custom-lighting-sheet.png",
    "image_main_type": "Look Reference",
    "image_sub_type": "Lighting / Atmosphere",
    "owner": "Custom",
    "look_custom_instruction": (
        "Apply a warm key and reduced exposure to Hero_A only."
    ),
})
custom_look_roundtrip = prompt._normalize_state(
    json.loads(json.dumps(custom_look_state, ensure_ascii=False))
)
assert custom_look_roundtrip["images"][0]["owner"] == "Custom"
assert custom_look_roundtrip["images"][0]["look_custom_instruction"] == (
    "Apply a warm key and reduced exposure to Hero_A only."
)
custom_visible_prompt = prompt._build_prompt_package(custom_look_roundtrip)
assert "Apply a warm key and reduced exposure to Hero_A only." in custom_visible_prompt
assert "never expand it to an unlisted target or to the whole scene" in (
    custom_visible_prompt
)
assert "relight the actual selected character, prop, and background" not in (
    custom_visible_prompt
)
custom_look_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(custom_look_roundtrip)
)
assert custom_look_job["images"][0]["target_id"] == "Custom"
assert custom_look_job["images"][0]["target_scope_mode"] == "custom"
assert custom_look_job["images"][0]["custom_look_instruction"] == (
    "Apply a warm key and reduced exposure to Hero_A only."
)

wrong_scope_job = copy.deepcopy(full_look_job)
wrong_scope_job["images"][0]["source_scope"] = "Rendering look only"
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(full_look_package, wrong_scope_job)
    )
)

for authored_target in ("Global Look", "Custom"):
    targeted_job = copy.deepcopy(full_look_job)
    targeted_job["images"][0]["target_id"] = authored_target
    targeted_job["images"][0]["target_scope_mode"] = (
        "custom" if authored_target == "Custom" else "global"
    )
    targeted_job["images"][0]["custom_look_instruction"] = (
        "Use the authored custom shared-lighting scope."
        if authored_target == "Custom"
        else ""
    )
    validated_targeted_job = agent._assert_public_job_data_contract(
        replace_job(full_look_package, targeted_job)
    )
    assert validated_targeted_job["images"][0]["target_id"] == authored_target

for invalid_target in ("", "Hero_A", "Camera / Composition"):
    targeted_job = copy.deepcopy(full_look_job)
    targeted_job["images"][0]["target_id"] = invalid_target
    expect_rejected(
        lambda job=targeted_job: agent._assert_public_job_data_contract(
            replace_job(full_look_package, job)
        )
    )

# Renderable recipients use owner first and label only as a fallback.  Look and
# Custom rows are sources/context rather than renderable Target recipients.
target_contract_state = prompt._default_widget_state()
target_contract_state["images"] = []
for slot, label, main_type, sub_type, owner in (
    (1, "hero-file.png", "Character", "Full Appearance", "Hero_A"),
    (2, "forest-file.png", "Environment / Background", "Main Background", ""),
    (
        3,
        "other-look.png",
        "Look Reference",
        "Lighting / Atmosphere",
        "",
    ),
    (4, "context-guide.png", "Custom / Context", "Context", "Context_Target"),
    (5, "hero-color-look.png", "Look Reference", "Color Mood", "Hero_A"),
):
    row = prompt._default_image_item(slot)
    row.update({
        "present": True,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "owner": owner,
    })
    target_contract_state["images"].append(row)
target_contract_package = prompt._build_data_only_prompt_package(
    target_contract_state
)
target_contract_job = agent._assert_public_job_data_contract(
    target_contract_package
)
assert target_contract_job["images"][4]["target_id"] == "Hero_A"

# The same normalized address cannot identify both a character-domain and a
# background-domain recipient. Prompt normalization clears the ambiguous Look
# target. The valid public envelope remains usable but the private manifest
# makes that unresolved Look relation non-authoritative; forging the ambiguous
# address onto the wire must still fail closed in the Agent.
ambiguous_target_state = prompt._default_widget_state()
ambiguous_target_state["images"] = []
for slot, label, main_type, sub_type, owner in (
    (1, "hero-shared.png", "Character", "Full Appearance", "Shared_Target"),
    (
        2,
        "forest-shared.png",
        "Environment / Background",
        "Main Background",
        "Ｓｈａｒｅｄ＿Ｔａｒｇｅｔ",
    ),
    (3, "look-shared.png", "Look Reference", "Color Mood", "shared_target"),
):
    row = prompt._default_image_item(slot)
    row.update({
        "present": True,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "owner": owner,
    })
    ambiguous_target_state["images"].append(row)
normalized_ambiguous_state = prompt._normalize_state(ambiguous_target_state)
assert normalized_ambiguous_state["images"][2]["owner"] == ""
ambiguous_target_package = prompt._build_data_only_prompt_package(
    normalized_ambiguous_state
)
assert_unbound_image(
    ambiguous_target_package,
    token="@image3",
    reason="missing_required_target",
)
ambiguous_target_job = json.loads(ambiguous_target_package.splitlines()[2])
forged_ambiguous_target_job = copy.deepcopy(ambiguous_target_job)
forged_ambiguous_target_job["images"][2]["target_id"] = "Shared_Target"
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(ambiguous_target_package, forged_ambiguous_target_job)
    )
)

# Exact canonical Global Look and both renderable address forms are valid:
# owner wins for Hero_A, while the blank-owner background falls back to label.
for valid_target in ("Global Look", "Hero_A", "forest-file.png"):
    valid_job = copy.deepcopy(target_contract_job)
    valid_job["images"][4]["target_id"] = valid_target
    validated_job = agent._assert_public_job_data_contract(
        replace_job(target_contract_package, valid_job)
    )
    assert validated_job["images"][4]["target_id"] == valid_target

for invalid_target in (
    "hero-file.png",  # owner wins over label for this renderable row
    "other-look.png",
    "context-guide.png",
    "Context_Target",
    "Camera / Composition",
    "ch_all",
    "bg_all",
    "ch_all / bg_all",
    "None",
    "missing-renderable-target",
):
    invalid_job = copy.deepcopy(target_contract_job)
    invalid_job["images"][4]["target_id"] = invalid_target
    expect_rejected(
        lambda job=invalid_job: agent._assert_public_job_data_contract(
            replace_job(target_contract_package, job)
        )
    )

# A renderable row may never claim a reserved system address; otherwise a Look
# Target could be silently redirected from an object to a global/system scope.
for reserved_target in common.IMAGE_SYSTEM_TARGETS:
    reserved_job = copy.deepcopy(target_contract_job)
    reserved_job["images"][0]["target_id"] = reserved_target
    reserved_job["images"][4]["target_id"] = ""
    expect_rejected(
        lambda job=reserved_job: agent._assert_public_job_data_contract(
            replace_job(target_contract_package, job)
        )
    )

# Reserved addresses are identifiers, not case-sensitive display names. A
# renderable row must not turn a differently cased system token into a named
# target and thereby make a General Look claim appear local.
reserved_case_variants = (
    "global look",
    "GLOBAL LOOK",
    " camera / composition ",
    "CAMERA / COMPOSITION",
    "CH_ALL",
    "Bg_All",
    "CH_ALL / BG_ALL",
    "none",
    "Ｇｌｏｂａｌ Ｌｏｏｋ",
    "Ｃａｍｅｒａ ／ Ｃｏｍｐｏｓｉｔｉｏｎ",
    "ｃｈ＿ａｌｌ",
    "Scale",
    "scale",
    "Composition",
    "SCALE / COMPOSITION",
    "Look",
    "custom",
    "SELF",
)
for reserved_target in reserved_case_variants:
    reserved_job = copy.deepcopy(target_contract_job)
    reserved_job["images"][0]["target_id"] = reserved_target
    reserved_job["images"][4]["target_id"] = ""
    expect_rejected(
        lambda job=reserved_job: agent._assert_public_job_data_contract(
            replace_job(target_contract_package, job)
        )
    )

# The same collision rule applies to the label fallback when a renderable row
# has no explicit owner address.
for reserved_label in reserved_case_variants:
    reserved_job = copy.deepcopy(target_contract_job)
    reserved_job["images"][1]["target_id"] = ""
    reserved_job["images"][1]["label"] = reserved_label
    reserved_job["images"][4]["target_id"] = ""
    expect_rejected(
        lambda job=reserved_job: agent._assert_public_job_data_contract(
            replace_job(target_contract_package, job)
        )
    )

# Non-canonical case variants are never aliases on the Agent wire. Only the
# exact `Global Look` enum above grants scene-wide authority.
for invalid_target in reserved_case_variants:
    invalid_job = copy.deepcopy(target_contract_job)
    invalid_job["images"][4]["target_id"] = invalid_target
    expect_rejected(
        lambda job=invalid_job: agent._assert_public_job_data_contract(
            replace_job(target_contract_package, job)
        )
    )

wrong_relationship_job = copy.deepcopy(full_look_job)
wrong_relationship_job["images"][0]["relationship_targets"] = ["Hero_A"]
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(full_look_package, wrong_relationship_job)
    )
)

wrong_binding_job = copy.deepcopy(full_look_job)
wrong_binding_job["images"][0]["bindings"] = [{
    "video": "@video1",
    "marker_color": "",
    "target_scope": "All color + look + lighting functions",
}]
wrong_binding_job["videos"] = [{
    "video": "@video1",
    "label": "valid-motion-reference.mp4",
    "source_type": "Motion Reference",
    "custom_source_type": "",
    "control_role": "Local Motion Detail Only",
    "custom_control_role": "",
    "control_role_explicit": True,
    "keep_out": "",
    "identity": {},
}]
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(full_look_package, wrong_binding_job)
    )
)

character_prop = prompt._default_image_item(1)
character_prop.update({
    "image_main_type": "Character Prop",
    "image_sub_type": "Handheld Prop",
    "color_picks": ["Red", "Sky Blue"],
})
prompt._normalize_image_binding_fields(character_prop)
assert character_prop["color_picks"] == ["Red"]

background_prop = prompt._default_image_item(1)
background_prop.update({
    "image_main_type": "Background Prop",
    "image_sub_type": "Set / Structure",
    "color_picks": ["Mint", "Green"],
})
prompt._normalize_image_binding_fields(background_prop)
assert background_prop["color_picks"] == ["Mint"]

# Empty marker values are pending UI binding slots, not invalid taxonomy.
# They must survive until the user fills all three Video / Color selectors.
pending_three = prompt._default_image_item(1)
pending_three.update({
    "image_main_type": "Character",
    "image_sub_type": "Full Appearance",
    "color_picks": ["", "", ""],
    "binding_video_slots": [1, 2, 3],
})
prompt._normalize_image_binding_fields(pending_three)
assert pending_three["color_picks"] == ["", "", ""]
assert pending_three["binding_video_slots"] == [1, 2, 3]

filled_three = prompt._default_image_item(1)
filled_three.update({
    "image_main_type": "Character",
    "image_sub_type": "Full Appearance",
    "color_picks": ["Red", "Green", "Blue", "Yellow"],
    "binding_video_slots": [1, 2, 3, 4],
})
prompt._normalize_image_binding_fields(filled_three)
assert filled_three["color_picks"] == ["Red", "Green", "Blue"]
assert filled_three["binding_video_slots"] == [1, 2, 3]

# Environment Main/Sub already owns scene authority. Migrate only the former
# generated target; a genuinely authored named target remains intact.
legacy_environment_target = prompt._default_image_item(1)
legacy_environment_target.update({
    "image_main_type": "Environment / Background",
    "image_sub_type": "Main Background",
    "owner": "Scene / Environment",
})
prompt._normalize_image_binding_fields(legacy_environment_target)
assert legacy_environment_target["owner"] == ""
assert prompt._default_image_target_for_main_type("Environment / Background") == ""
assert "Scene / Environment" not in common.IMAGE_SYSTEM_TARGETS

named_environment_target = prompt._default_image_item(1)
named_environment_target.update({
    "image_main_type": "Environment / Background",
    "image_sub_type": "Main Background",
    "owner": "Forest_Set_A",
})
prompt._normalize_image_binding_fields(named_environment_target)
assert named_environment_target["owner"] == "Forest_Set_A"

look = prompt._default_image_item(1)
look.update({
    "present": True,
    "label": "look.png",
    "image_main_type": "Look Reference",
    "image_sub_type": "Render Look",
    "owner": "Former Character Target",
    "color_picks": ["Red", "Sky Blue"],
})
prompt._normalize_image_binding_fields(look)
assert look["color_picks"] == [""]
assert look["owner"] == "Former Character Target"
assert prompt._image_binding_entries(look) == []
assert common.image_color_pick_choices_for_taxonomy("Look Reference", "Render Look") == []

# A named character Target survives Render Look, while lighting-bearing Look
# becomes Global Look and a later scale sheet receives its typed all-target.
transitioning_look = prompt._default_image_item(1)
transitioning_look.update({
    "present": True,
    "label": "jett-look-reference.png",
    "image_main_type": "Look Reference",
    "owner": "Jett_11",
})
for look_subtype, expected_owner in (
    ("Render Look", "Jett_11"),
    ("Lighting / Atmosphere", "Global Look"),
    ("ch_Scale", "ch_all"),
):
    transitioning_look["image_sub_type"] = look_subtype
    prompt._normalize_image_binding_fields(transitioning_look)
    assert transitioning_look["owner"] == expected_owner
    assert (
        transitioning_look["source_type"],
        transitioning_look["scope"],
    ) == common.IMAGE_TAXONOMY_WIRE_MAP[("Look Reference", look_subtype)]

# Multiple Look rows may address real renderable subjects with independent
# color, lighting, render, and relative-size decisions in one Agent job.
targeted_look_state = prompt._default_widget_state()
targeted_look_state["images"] = []
for slot, label, main_type, sub_type, owner in (
    (1, "hero-sheet.png", "Character", "Full Appearance", "Hero_A"),
    (2, "forest-sheet.png", "Environment / Background", "Main Background", "Forest_A"),
):
    target_row = prompt._default_image_item(slot)
    target_row.update({
        "present": True,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "owner": owner,
    })
    targeted_look_state["images"].append(target_row)
targeted_look_subtypes = prompt.image_sub_type_choices_for_main_type(
    "Look Reference"
)
expected_target_ids = []
general_target_by_subtype = {
    "Color Mood": "Hero_A",
    "Lighting / Atmosphere": "Global Look",
    "Render Look": "Hero_A",
}
for index, look_subtype in enumerate(targeted_look_subtypes, start=3):
    # The combined relative-size sheet is validated independently above. It
    # cannot coexist with ch_all and bg_all claims in one job because those
    # measurement domains overlap by design.
    if look_subtype in {"Color / Look / Lighting", "ch_Scale / bg_Scale"}:
        continue
    target_id = prompt.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS.get(
        look_subtype,
        general_target_by_subtype.get(look_subtype, ""),
    )
    targeted_item = prompt._default_image_item(index)
    targeted_item.update({
        "present": True,
        "label": f"targeted-look-{index}.png",
        "image_main_type": "Look Reference",
        "image_sub_type": look_subtype,
        "owner": target_id,
    })
    targeted_look_state["images"].append(
        prompt._normalize_image_binding_fields(targeted_item)
    )
    expected_target_ids.append(target_id)

targeted_look_visible = prompt._build_prompt_package(targeted_look_state)
targeted_look_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(targeted_look_state)
)
assert [record["target_id"] for record in targeted_look_job["images"]] == (
    ["Hero_A", "Forest_A", *expected_target_ids]
)
assert all(
    record["bindings"] == []
    for record in targeted_look_job["images"][2:]
)
assert "across every visible" not in targeted_look_visible
assert "scene-wide" in targeted_look_visible
assert "only on the selected target" in targeted_look_visible
assert "Reference-content exclusion" in targeted_look_visible
assert "never copy, insert, reconstruct, or render" in targeted_look_visible

# With IMAGE_ASSET_IN connected, only asset-managed rows own active @imageN
# tokens. The manual row is excluded, and its Target cannot be forged into the
# active Look contract. This also proves owner-first addressing survives the
# connection-owned path.
asset_owned_state = prompt._default_widget_state()
asset_owned_state["image_asset"].update({
    "enabled": True,
    "order_managed": True,
})
asset_owned_state["images"] = []
for slot, label, owner, asset_managed, main_type, sub_type in (
    (1, "manual-hero.png", "Manual_Hero", False, "Character", "Full Appearance"),
    (2, "asset-hero.png", "Asset_Hero", True, "Character", "Full Appearance"),
    (3, "asset-look.png", "Asset_Hero", True, "Look Reference", "Render Look"),
):
    row = prompt._default_image_item(slot)
    row.update({
        "present": True,
        "label": label,
        "owner": owner,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "asset_managed": asset_managed,
    })
    asset_owned_state["images"].append(row)
asset_owned_package = prompt._build_data_only_prompt_package(asset_owned_state)
asset_owned_job = agent._assert_public_job_data_contract(asset_owned_package)
assert [row["label"] for row in asset_owned_job["images"]] == [
    "asset-hero.png",
    "asset-look.png",
]
assert asset_owned_job["images"][0]["target_id"] == "Asset_Hero"
assert asset_owned_job["images"][1]["target_id"] == "Asset_Hero"
manual_target_job = copy.deepcopy(asset_owned_job)
manual_target_job["images"][1]["target_id"] = "Manual_Hero"
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(asset_owned_package, manual_target_job)
    )
)

# Registration candidates are internal provenance. The public job and Agent
# contract must receive only the effective Prompt Look taxonomy.
verified_look_override = prompt._default_image_item(1)
verified_look_override.update(
    {
        "present": True,
        "label": "registered-master-look.png",
        "asset_managed": True,
        "asset_verified": True,
        "asset_source_kind": "project",
        "asset_source_uid": "verified-look-taxonomy",
        "asset_project_uid": "project-look-taxonomy",
        "asset_library_id": "library-look-taxonomy",
        "asset_id": "MasterLook",
        "asset_image_main_type_candidate": "Look Reference",
        "asset_image_sub_type_candidate": "Color Mood",
        "image_main_type": "Look Reference",
        "image_sub_type": "ch_Scale",
        "owner": "Jett_11",
    }
)
prompt._normalize_image_binding_fields(verified_look_override)
verified_look_state = prompt._default_widget_state()
verified_look_state["images"] = [verified_look_override]
verified_look_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(verified_look_state)
)
verified_look_record = verified_look_job["images"][0]
assert verified_look_record["image_main_type"] == "Look Reference"
assert verified_look_record["image_sub_type"] == "ch_Scale"
assert verified_look_record["source_type"] == "Relative Size Reference"
assert verified_look_record["source_scope"] == "Character Relative Size Only"
assert verified_look_record["target_id"] == "ch_all"
assert verified_look_record["bindings"] == []
assert "asset_image_sub_type_candidate" not in verified_look_record

# Five-image, no-control-video production example. Image 5 owns the shared
# scene lighting/look while the first four sources retain intrinsic identity.
example_state = prompt._default_widget_state()
example_state["images"] = []
for slot, label, main_type, sub_type, owner in (
    (1, "Character_A.png", "Character", "Full Appearance", "Character_A"),
    (2, "Character_B.png", "Character", "Full Appearance", "Character_B"),
    (3, "Main_Background.png", "Environment / Background", "Main Background", "Main Background"),
    (4, "Sky.png", "Environment / Background", "Sky / Exterior", "Sky"),
    (5, "Master_Look.png", "Look Reference", "Color / Look / Lighting", "Global Look"),
):
    example_item = prompt._default_image_item(slot)
    example_item.update({
        "present": True,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "owner": owner,
    })
    example_state["images"].append(
        prompt._normalize_image_binding_fields(example_item)
    )

example_visible = prompt._build_prompt_package(example_state)
example_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(example_state)
)
assert len(example_job["images"]) == 5
assert example_job["images"][4]["image_main_type"] == "Look Reference"
assert example_job["images"][4]["image_sub_type"] == "Color / Look / Lighting"
assert example_job["images"][4]["source_scope"] == (
    "All color + look + lighting functions"
)
assert example_job["images"][4]["target_id"] == "Global Look"
assert "reference time-of-day and illumination state" in example_visible
assert "never copy, insert, reconstruct, or render" in example_visible
assert "actual selected character, prop, and background sources" in example_visible
assert "scene-wide" in example_visible
assert "across every visible" not in example_visible
assert "preserve intrinsic identity, color, pattern, and material" in example_visible

# Server records use only the new authoring fields. Legacy record values are
# never treated as migration input.
server_legacy = image_asset._normalize_image_taxonomy_fields({
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
})
assert server_legacy["image_main_type"] == "Select Image Main Type"
assert server_legacy["image_sub_type"] == ""

server_look = image_asset._normalize_image_taxonomy_fields({
    "image_main_type": "Look Reference",
    "image_sub_type": "Color Mood",
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
})
assert server_look["source_type"] == "Color / Look Reference"
assert server_look["scope_candidate"] == "Color mood only"
assert server_look["color_pick_candidates"] == []

print(
    "HMB image taxonomy regression: PASS "
    "(26 exact Agent projections, editable Look targets, five-image relight)"
)
