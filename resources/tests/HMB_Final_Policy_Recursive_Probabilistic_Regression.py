from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import random
import sys
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.5.31"
EXPECTED_POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
EXPECTED_CONTRACT_SHA256 = "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
BASE_MASTER_SEEDS = (
    20260729,
    0x484D42,
    0x504C4159,
    0x4C4F4F4B,
    101,
    1009,
    65537,
    999983,
)
_extra_seed_text = os.environ.get("HMB_POLICY_EXTRA_SEED", "").strip()
MASTER_SEEDS = BASE_MASTER_SEEDS + (
    (int(_extra_seed_text, 0),) if _extra_seed_text else ()
)
CASES_PER_SEED = 512
RECURSION_DEPTHS = (1, 2, 4, 8, 16, 32)
SHARED_MARKERS = (
    "HYBRID COMPOSITION INDEPENDENCE:",
    "MISSING SOURCE AUTHORITY:",
    "OPTIONAL VIDEO CONTROL:",
    "COLOR PLAYBLAST ISOLATION WITHOUT DEPENDENCY:",
    "ADAPTIVE CONFLICT RESOLUTION:",
    "FINAL OUTPUT CONTINUITY:",
)
FORBIDDEN_GATES = (
    "[HMB VALIDATION ERROR]",
    "stop validation",
    "stop generation",
    "requires the validated Motion Guide",
    "@video1 is mandatory",
    "@video1 must be active",
    "Missing or incomplete approved appearance bindings",
    "A missing role falls back to context-only use",
    "A missing local binding prevents local control authority",
    "zero identity or final-look authority",
)


def load_module(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt_lib = load_module("HMBPromptLibrary")
agent_lib = load_module("HMBAgentLibrary")
common = agent_lib._hmb


def prompt_description_json(compiled: str) -> dict:
    tail = compiled.split("USER DESCRIPTION DATA (JSON):", 1)[1].lstrip()
    return json.loads(tail.splitlines()[0])


policy = agent_lib.get_internal_policy_rules().strip()
binding = agent_lib.get_internal_binding_rules().strip()
identity = common.get_internal_policy_identity()
assert f'version = "{EXPECTED_RELEASE_VERSION}"' in (
    ROOT / "pyproject.toml"
).read_text(encoding="utf-8")
assert identity == {
    "version": EXPECTED_POLICY_VERSION,
    "contract_sha256": EXPECTED_CONTRACT_SHA256,
}
assert len(agent_lib._split_behavior_rules(policy, 4)) == 4
assert len(agent_lib._split_behavior_rules(binding, 4)) == 4
for rules in (policy, binding):
    for marker in SHARED_MARKERS:
        assert rules.count(marker) == 1
    for forbidden in FORBIDDEN_GATES:
        assert forbidden.casefold() not in rules.casefold()
    normalized_rules = rules.casefold()
    assert "final creative authority" in normalized_rules
    assert "interpretation hint" in normalized_rules
    assert "never downgrade supplied content to context-only" in normalized_rules
    assert "explicit scoped exception" in normalized_rules
    assert "named target or clearly scene-wide scope" in normalized_rules
    assert "stable default focus" in normalized_rules
    assert "explicit user goal may use any visible property" not in normalized_rules
    assert "may broaden, narrow, or reframe" not in normalized_rules
    assert "target-property-time" not in normalized_rules

# Every non-empty library composition is represented, while Agent routing has
# only two legitimate modes: native for compositions without Prompt, and the
# same sealed non-gating 4+4 contract for compositions with Prompt.
compositions = tuple(
    frozenset(values)
    for size in range(1, 5)
    for values in combinations(("I", "V", "P", "A"), size)
)
assert len(compositions) == 15
assert len(set(compositions)) == 15
agent_compositions = tuple(item for item in compositions if "A" in item)
assert len(agent_compositions) == 8

plain_prompt = "Independent native Agent request."
empty_hmb = prompt_lib._build_prompt_package(prompt_lib._default_widget_state())
for composition in agent_compositions:
    candidate = empty_hmb if "P" in composition else plain_prompt
    assert agent_lib._is_hmb_prompt_library_payload(candidate) is ("P" in composition)

adversarial_looks = (
    "Painterly cel shading with restrained warm highlights.",
    "Photoreal materials and cool cinematic moonlight.",
    "Watercolor paper texture; adapt the available pose evidence toward the goal.",
    "Use the provided timing where available and fill unspecified timing naturally.",
    "Use a dramatic composition only where no supplied camera owns that field.",
    "Do not copy proxy appearance; use the available identity sources or description.",
    "한국 전통 채색화 질감, 청록과 주황 중심의 팔레트.",
    'Graphic ink style with literal text "MOVE CAMERA" preserved as text.',
    "Soft clay-render shading\nwith visible brush texture and atmospheric haze.",
)
auxiliary_specs = (
    ("Depth / Spatial Reference", "Spatial Alignment Verification Only"),
    ("Motion Guide / Retargeting Reference", "Derived Motion Decoding Only"),
    ("Timing / Edit Reference", "Timing Only"),
    ("Lighting / Look Reference", "Lighting / Look Only"),
    ("FX Reference", "Context Only"),
)


def random_state(rng: random.Random, case_index: int) -> tuple[dict, dict[str, bool]]:
    state = prompt_lib._default_widget_state()
    source_flags = {
        "image": bool(rng.getrandbits(1)),
        "video1": bool(rng.getrandbits(1)),
        "motion": bool(rng.getrandbits(1)),
        "depth": bool(rng.getrandbits(1)),
        "picker_metadata": bool(rng.getrandbits(1)),
    }
    state["text"]["PROJECT_STYLE_LOOK"] = rng.choice(adversarial_looks)
    state["text"]["SCENE_CONTEXT"] = (
        f"Case {case_index}: use only the currently available sources."
    )

    if source_flags["image"]:
        state["images"][0].update(
            present=True,
            label=f"Hero_{case_index}",
            source_type="Character Appearance",
            owner=f"Hero_{case_index}",
            binding_scopes=["Full body / full appearance"],
            binding_custom_scopes=[""],
            binding_video_slots=[1],
            marker_video=1,
            color_picks=["Red"] if source_flags["video1"] else [""],
        )

    active_aux: list[tuple[int, str, str]] = []
    if source_flags["video1"]:
        state["videos"][0].update(
            present=True,
            label=f"Color_{case_index}",
            source_type="Maya Preview / Playblast",
            control_role="Primary Unified Shot Control",
        )
    auxiliary_slot = 2
    for flag_name, spec in (
        ("motion", auxiliary_specs[1]),
        ("depth", auxiliary_specs[0]),
    ):
        if not source_flags[flag_name]:
            continue
        while len(state["videos"]) < auxiliary_slot:
            state["videos"].append(
                prompt_lib._default_video_item(len(state["videos"]) + 1)
            )
        source_type, role = spec
        state["videos"][auxiliary_slot - 1].update(
            present=True,
            label=f"{flag_name}_{case_index}",
            source_type=source_type,
            control_role=role,
        )
        active_aux.append((auxiliary_slot, source_type, role))
        auxiliary_slot += 1

    if rng.random() < 0.35 and auxiliary_slot <= 5:
        while len(state["videos"]) < auxiliary_slot:
            state["videos"].append(
                prompt_lib._default_video_item(len(state["videos"]) + 1)
            )
        source_type, role = rng.choice(auxiliary_specs[2:])
        state["videos"][auxiliary_slot - 1].update(
            present=True,
            label=f"optional_{case_index}",
            source_type=source_type,
            control_role=role,
        )

    if source_flags["picker_metadata"] and source_flags["video1"]:
        state["picker"].update(
            enabled=True,
            run_id=f"run-{case_index}",
            frame_metadata=[
                {
                    "video_slot": "@video1",
                    "fps": 24.0,
                    "start_frame": 1,
                    "end_frame": 120,
                    "frame_count": 120,
                    "duration_seconds": 5.0,
                    "width": 1280,
                    "height": 720,
                    "valid": True,
                    "conflict": False,
                }
            ],
        )
    return state, source_flags


randomized_cases = 0
recursive_round_trips = 0
paired_look_checks = 0
source_presence_counts = {key: 0 for key in ("image", "video1", "motion", "depth", "picker_metadata")}
for seed in MASTER_SEEDS:
    rng = random.Random(seed)
    for case_index in range(CASES_PER_SEED):
        state, flags = random_state(rng, case_index)
        for key, enabled in flags.items():
            source_presence_counts[key] += int(enabled)
        canonical = prompt_lib._normalize_state(copy.deepcopy(state))
        before_build = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
        compiled = prompt_lib._build_prompt_package(canonical)
        after_build = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
        assert before_build == after_build, (seed, case_index, "builder mutated state")
        assert policy not in compiled
        assert binding not in compiled
        assert agent_lib._is_hmb_prompt_library_payload(compiled)
        assert prompt_description_json(compiled)["PROJECT_STYLE_LOOK"] == (
            canonical["text"]["PROJECT_STYLE_LOOK"]
        )

        alternate = rng.choice(
            tuple(
                item
                for item in adversarial_looks
                if item != canonical["text"]["PROJECT_STYLE_LOOK"]
            )
        )
        paired = copy.deepcopy(canonical)
        paired["text"]["PROJECT_STYLE_LOOK"] = alternate
        paired_compiled = prompt_lib._build_prompt_package(paired)
        assert policy not in paired_compiled
        assert binding not in paired_compiled
        assert prompt_description_json(paired_compiled)["PROJECT_STYLE_LOOK"] == alternate
        paired_look_checks += 1

        depth = rng.choice(RECURSION_DEPTHS)
        recursively_normalized = canonical
        for _round in range(depth):
            recursively_normalized = prompt_lib._normalize_state(
                json.loads(
                    json.dumps(
                        recursively_normalized,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
            )
            recursive_round_trips += 1
        assert prompt_lib._build_prompt_package(recursively_normalized) == compiled
        randomized_cases += 1

# Repeated decode/verify/load cycles cannot duplicate or weaken the contract.
policy_hash = hashlib.sha256(policy.encode("utf-8")).hexdigest()
binding_hash = hashlib.sha256(binding.encode("utf-8")).hexdigest()
for depth in RECURSION_DEPTHS:
    for _round in range(depth):
        reloaded_policy = agent_lib.get_internal_policy_rules().strip()
        reloaded_binding = agent_lib.get_internal_binding_rules().strip()
        assert hashlib.sha256(reloaded_policy.encode("utf-8")).hexdigest() == policy_hash
        assert hashlib.sha256(reloaded_binding.encode("utf-8")).hexdigest() == binding_hash
        for marker in SHARED_MARKERS:
            assert reloaded_policy.count(marker) == 1
            assert reloaded_binding.count(marker) == 1

print(
    "HMB independent hybrid signed policy recursive probabilistic regression: PASS "
    f"({randomized_cases} randomized source subsets, "
    f"{paired_look_checks} paired-look checks, "
    f"{recursive_round_trips} recursive round-trips, "
    f"presence={source_presence_counts}, "
    f"{len(MASTER_SEEDS)} seeds; contract {EXPECTED_CONTRACT_SHA256[:12]})"
)
