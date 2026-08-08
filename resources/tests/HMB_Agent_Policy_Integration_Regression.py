from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import types
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.5.27"
EXPECTED_POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
EXPECTED_CONTRACT_SHA256 = "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
EXPECTED_BUNDLED_POLICY_SHA256 = "6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619"
EXPECTED_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"
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


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent = load("HMBAgentLibrary")
prompt = load("HMBPromptLibrary")

policy = agent.get_internal_policy_rules().strip()
binding = agent.get_internal_binding_rules().strip()
identity = agent._hmb.get_internal_policy_identity()

assert f'version = "{EXPECTED_RELEASE_VERSION}"' in (
    ROOT / "pyproject.toml"
).read_text(encoding="utf-8")
assert identity == {
    "version": EXPECTED_POLICY_VERSION,
    "contract_sha256": EXPECTED_CONTRACT_SHA256,
}
assert len(agent._split_behavior_rules(policy, 4)) == 4
assert len(agent._split_behavior_rules(binding, 4)) == 4

for rules in (policy, binding):
    for marker in SHARED_MARKERS:
        assert rules.count(marker) == 1, marker
    for forbidden in FORBIDDEN_GATES:
        assert forbidden.casefold() not in rules.casefold(), forbidden
    normalized_rules = rules.casefold()
    assert "every non-empty subset" in normalized_rules
    assert "final creative authority" in normalized_rules
    assert "not a prerequisite" in normalized_rules
    assert "interpretation hint" in normalized_rules
    assert "current explicit user goal" in normalized_rules
    assert "unreadable or corrupt file" in normalized_rules
    assert "never downgrade supplied content to context-only" in normalized_rules
    assert "explicit scoped exception" in normalized_rules
    assert "named target or clearly scene-wide scope" in normalized_rules
    assert "stable default focus" in normalized_rules
    assert "explicit user goal may use any visible property" not in normalized_rules
    assert "may broaden, narrow, or reframe" not in normalized_rules
    assert "target-property-time" not in normalized_rules
    assert "hidden rules" in normalized_rules

# The signed/compressed v3 envelope is the sole local runtime policy. No
# plaintext policy or private signing key is distributed.
bundled_policy_path = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
assert bundled_policy_path.is_file()
assert hashlib.sha256(bundled_policy_path.read_bytes()).hexdigest() == (
    EXPECTED_BUNDLED_POLICY_SHA256
)
sealed = bundled_policy_path.read_bytes()
assert policy.encode("utf-8") not in sealed
assert binding.encode("utf-8") not in sealed
for marker in SHARED_MARKERS:
    assert marker.encode("utf-8") not in sealed

envelope = json.loads(sealed.decode("utf-8"))
assert envelope["schema"] == agent._hmb._AGENT_POLICY_ENVELOPE_SCHEMA
assert envelope["algorithm"] == agent._hmb._AGENT_POLICY_SIGNATURE_ALGORITHM
assert envelope["key_id"] == agent._hmb._AGENT_POLICY_SIGNING_KEY_ID
assert envelope["key_id"] == EXPECTED_SIGNING_KEY_ID
assert envelope["payload_sha256"]
assert envelope["signature"]
payload = agent._hmb._decode_signed_agent_policy_envelope(sealed)
agent._hmb._validate_agent_policy_payload(payload)
assert payload["schema"] == "hmb-agent-policy-v3"
assert payload["final_policy_version"] == EXPECTED_POLICY_VERSION
assert payload["final_motion_look_policy_sha256"] == EXPECTED_CONTRACT_SHA256
assert hashlib.sha256(policy.encode("utf-8")).hexdigest() == payload["policy_sha256"]
assert hashlib.sha256(binding.encode("utf-8")).hexdigest() == payload["binding_sha256"]
final_clauses = [str(item) for item in payload["final_motion_look_policy_clauses"]]
assert len(final_clauses) == len(SHARED_MARKERS)
assert hashlib.sha256("\n\n".join(final_clauses).encode("utf-8")).hexdigest() == (
    EXPECTED_CONTRACT_SHA256
)
for clause in final_clauses:
    assert policy.count(clause) == 1
    assert binding.count(clause) == 1
assert len(payload["video_appearance_isolation_clauses"]) == 2
assert all(
    clause in final_clauses
    for clause in payload["video_appearance_isolation_clauses"]
)


def assert_policy_rejected(encoded: bytes) -> None:
    try:
        agent._hmb._decode_signed_agent_policy_envelope(encoded)
    except RuntimeError:
        return
    raise AssertionError("Tampered or incomplete signed policy was accepted.")


# Any envelope/payload mutation fails before policy injection. Removing a
# required inner digest is also rejected by the fixed v3 contract validator.
for envelope_field in ("signature", "payload_sha256", "algorithm", "key_id"):
    altered_envelope = dict(envelope)
    altered_envelope.pop(envelope_field)
    assert_policy_rejected(
        json.dumps(altered_envelope, separators=(",", ":")).encode("utf-8")
    )
altered_envelope = dict(envelope)
payload_text = str(altered_envelope["payload"])
altered_envelope["payload"] = ("A" if payload_text[:1] != "A" else "B") + payload_text[1:]
assert_policy_rejected(
    json.dumps(altered_envelope, separators=(",", ":")).encode("utf-8")
)
for required_field in (
    "policy_sha256",
    "binding_sha256",
    "final_motion_look_policy_sha256",
    "final_policy_version",
):
    altered_payload = dict(payload)
    altered_payload.pop(required_field)
    try:
        agent._hmb._validate_agent_policy_payload(altered_payload)
    except RuntimeError:
        continue
    raise AssertionError(f"Signed payload without {required_field} was accepted.")

# Payload shape remains a Prompt-format regression, but text is never activation
# provenance. Only the canonical HMBPromptLibrary.PROMPT_OUT -> Agent.prompt edge
# opts into the structured 4+4 Behaviors. Plain text, copied HMB text, and direct
# Image/Video payloads remain stock native Agent requests.
plain_prompt = "Independent designer request using the currently available inputs."
empty_hmb_prompt = prompt._build_prompt_package(prompt._default_widget_state())
assert not agent._is_hmb_prompt_library_payload(plain_prompt)
assert agent._is_hmb_prompt_library_payload(empty_hmb_prompt)
assert policy not in empty_hmb_prompt
assert binding not in empty_hmb_prompt
goal_first_rule = agent._extract_goal_first_rule(policy, binding)
assert goal_first_rule.startswith(agent._HMB_GOAL_FIRST_RULE_HEADING)
for marker in SHARED_MARKERS:
    assert goal_first_rule.count(marker) == 1
assert "final creative authority" in goal_first_rule
assert "never activates a prerequisite" in goal_first_rule

all_compositions = {
    frozenset(values)
    for size in range(1, 5)
    for values in combinations(("I", "V", "P", "A"), size)
}
agent_compositions = sorted(
    (item for item in all_compositions if "A" in item),
    key=lambda item: (len(item), tuple(sorted(item))),
)
assert len(all_compositions) == 15
assert len(agent_compositions) == 8


def exercise_agent_route(
    prompt_value: str,
    *,
    canonical_prompt_connected: bool = False,
) -> tuple[bool, bool, int, int, int, bool]:
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_goal_first_rules = []
    node._hmb_structured_rules_active = False
    node._hmb_native_calls_this_process = 0
    observations: list[tuple[bool, bool, int, int, int]] = []
    secured: list[bool] = []

    def native_once(self):
        observations.append(
            (
                bool(self._hmb_rules_active),
                bool(self._hmb_structured_rules_active),
                len(self._hmb_goal_first_rules),
                len(self._hmb_policy_rules),
                len(self._hmb_binding_rules),
            )
        )
        if False:
            yield None
        return "native-complete"

    def secure(self):
        secured.append(True)

    node.get_parameter_value = types.MethodType(
        lambda _self, name: prompt_value if name == "prompt" else None,
        node,
    )
    node._run_native_agent_once = types.MethodType(native_once, node)
    node._secure_hmb_outputs = types.MethodType(secure, node)
    node._has_canonical_hmb_prompt_connection = types.MethodType(
        lambda _self: canonical_prompt_connected,
        node,
    )
    iterator = node.process()
    try:
        while True:
            next(iterator)
    except StopIteration as stop:
        assert stop.value == "native-complete"
    assert len(observations) == 1
    active, structured, goal_count, project_count, shot_count = observations[0]
    return active, structured, goal_count, project_count, shot_count, bool(secured)


def exercise_agent_block(
    prompt_value: str,
    *,
    topology_failure: bool = False,
) -> str:
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = False
    node._hmb_policy = "stale-policy"
    node._hmb_binding = "stale-binding"
    node._hmb_policy_rules = ["stale-project-rule"]
    node._hmb_binding_rules = ["stale-shot-rule"]
    node._hmb_goal_first_rules = ["stale-goal-rule"]
    node._hmb_structured_rules_active = False
    node._hmb_native_calls_this_process = 0
    node.parameter_output_values = {
        "agent": {"stale": True},
        "output": "stale visible output",
    }
    native_calls: list[bool] = []

    def forbidden_native(self):
        native_calls.append(True)
        if False:
            yield None
        return "native-must-not-run"

    def topology(self):
        if topology_failure:
            raise RuntimeError("simulated topology lookup failure")
        return True

    node.get_parameter_value = types.MethodType(
        lambda _self, name: prompt_value if name == "prompt" else None,
        node,
    )
    node._run_native_agent_once = types.MethodType(forbidden_native, node)
    node._has_canonical_hmb_prompt_connection = types.MethodType(topology, node)
    iterator = node.process()
    try:
        while True:
            next(iterator)
    except RuntimeError as exc:
        assert exc.__cause__ is None
        error_text = str(exc)
    except StopIteration as stop:
        raise AssertionError(f"Blocked HMB route completed unexpectedly: {stop.value}")

    assert native_calls == []
    assert node._hmb_native_calls_this_process == 0
    assert node._hmb_rules_active is False
    assert node._hmb_structured_rules_active is False
    assert node._hmb_policy == ""
    assert node._hmb_binding == ""
    assert node._hmb_policy_rules == []
    assert node._hmb_binding_rules == []
    assert node._hmb_goal_first_rules == []
    assert node.parameter_output_values["agent"] == {}
    assert node.parameter_output_values["output"] == error_text
    assert "fin-rcomp1" not in error_text.casefold()
    return error_text


for composition in agent_compositions:
    has_prompt = "P" in composition
    route = exercise_agent_route(
        empty_hmb_prompt if has_prompt else plain_prompt,
        canonical_prompt_connected=has_prompt,
    )
    if has_prompt:
        assert route == (True, True, 1, 4, 4, True), composition
    else:
        assert route == (False, False, 0, 0, 0, False), composition

direct_source_payloads = (
    json.dumps(
        {
            "schema": "hmb-image-asset-library-binding",
            "ordered_images": [{"image_name": "Direct image idea"}],
        },
        ensure_ascii=False,
    ),
    json.dumps(
        {
            "schema": "hmb-video-picker-output",
            "videos": [{"video_slot": 3, "path": "direct_motion.mp4"}],
        },
        ensure_ascii=False,
    ),
    "HMB_GP_Production\nTARGET GENERATOR:\nincomplete but readable user intent",
)
for direct_payload in direct_source_payloads:
    assert not agent._is_hmb_prompt_library_payload(direct_payload)
    assert exercise_agent_route(direct_payload) == (False, False, 0, 0, 0, False)

# Empty, image-only, video-described, and mixed HMB payloads all activate the
# same non-gating policy. Agent does not inspect whether their source libraries
# are connected and does not require media completion before the native call.
payload_variants = (
    empty_hmb_prompt,
    empty_hmb_prompt.replace(
        "No image source assigned in HMBPromptLibrary.",
        "@image1 = manually supplied design reference",
    ),
    empty_hmb_prompt.replace(
        "No video source assigned in HMBPromptLibrary.",
        "@video3 = independently supplied timing reference",
    ),
    empty_hmb_prompt.replace(
        "No image source assigned in HMBPromptLibrary.",
        "@image2 = library asset",
    ).replace(
        "No video source assigned in HMBPromptLibrary.",
        "@video4 = optional motion guide",
    ),
)
for variant in payload_variants:
    assert agent._is_hmb_prompt_library_payload(variant)
    assert exercise_agent_route(
        variant,
        canonical_prompt_connected=True,
    ) == (True, True, 1, 4, 4, True)

# Copied or forged HMB-shaped text is still a native request when the canonical
# Prompt edge is absent. Conversely, the canonical edge owns routing even if a
# future Prompt version changes its headings or wording.
assert exercise_agent_route(empty_hmb_prompt) == (False, False, 0, 0, 0, False)
assert exercise_agent_route(
    plain_prompt,
    canonical_prompt_connected=True,
) == (True, True, 1, 4, 4, True)

# A canonical HMB Prompt makes the signed policy mandatory. Load/integrity
# failures publish a safe diagnostic and block before native Agent execution.
original_load_rules = agent.HMBAgentLibrary._load_hmb_rules
try:
    policy_load_attempts: list[str] = []

    def forbidden_plain_policy_load(_self):
        policy_load_attempts.append("plain")
        raise AssertionError("plain native Agent attempted to read HMB policy")

    agent.HMBAgentLibrary._load_hmb_rules = forbidden_plain_policy_load
    assert exercise_agent_route(plain_prompt) == (
        False,
        False,
        0,
        0,
        0,
        False,
    )
    assert policy_load_attempts == []

    agent.HMBAgentLibrary._load_hmb_rules = lambda _self: (_ for _ in ()).throw(
        RuntimeError("simulated sealed policy failure")
    )
    for composition in agent_compositions:
        if "P" not in composition:
            continue
        assert exercise_agent_block(
            f"{empty_hmb_prompt}\nCOMPOSITION={''.join(sorted(composition))}"
        ) == agent._HMB_POLICY_UNAVAILABLE_MESSAGE
    assert exercise_agent_block(
        empty_hmb_prompt,
        topology_failure=True,
    ) == agent._HMB_TOPOLOGY_UNAVAILABLE_MESSAGE
finally:
    agent.HMBAgentLibrary._load_hmb_rules = original_load_rules

tampered_envelope = dict(envelope)
signature_text = str(tampered_envelope["signature"])
tampered_envelope["signature"] = (
    ("A" if signature_text[:1] != "A" else "B") + signature_text[1:]
)
original_policy_path = agent._hmb._BUNDLED_AGENT_POLICY_FILE
with tempfile.TemporaryDirectory() as temporary_directory:
    corrupt_policy_path = Path(temporary_directory) / "hmb_agent_core.dat"
    corrupt_policy_path.write_text(
        json.dumps(tampered_envelope, separators=(",", ":")),
        encoding="utf-8",
    )
    agent._hmb._BUNDLED_AGENT_POLICY_FILE = corrupt_policy_path
    try:
        assert exercise_agent_block(empty_hmb_prompt) == (
            agent._HMB_POLICY_UNAVAILABLE_MESSAGE
        )
    finally:
        agent._hmb._BUNDLED_AGENT_POLICY_FILE = original_policy_path

# Runtime source documents carry the new contract marker check while output
# state and hidden-rule sanitization remain in their established code paths.
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
assert "_HMB_HYBRID_INDEPENDENCE_MARKERS" in agent_source
assert "_HMB_GOAL_FIRST_RULESET_NAME" in agent_source
assert "_extract_goal_first_rule" in agent_source
assert "sealed hybrid-composition policy is stale or incomplete" in agent_source
assert "_secure_hmb_outputs" in agent_source
assert "_contains_public_output_state_leak" in agent_source
assert "_prepend_standard_library_paths_for_agent" not in common_source
assert "pkgutil.walk_packages" not in common_source
assert "Path.home() / \"Documents\" / \"GriptapeNodes\"" not in common_source
assert "_AGENT_POLICY_RSA_MODULUS_B64" in common_source
assert "_verify_agent_policy_signature" in common_source

print(
    "HMB independent hybrid Agent policy integration regression: PASS "
    f"(15 compositions / 8 Agent subsets; contract {EXPECTED_CONTRACT_SHA256[:12]})"
)
