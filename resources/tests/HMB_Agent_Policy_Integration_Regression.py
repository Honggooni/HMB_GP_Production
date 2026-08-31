from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from itertools import combinations
from pathlib import Path

from _hmb_private_policy_fixture import (
    install_private_policy_reader,
    read_private_policy_fixture_if_available,
)


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.7.19"
EXPECTED_SIGNING_KEY_ID = "hmb-policy-local-2026-08-r1"
PRIVATE_SIGNED_POLICY_FIXTURE = (
    ROOT
    / "resources"
    / "policy"
    / "HMB_GP_Production_Rule"
    / "artifact"
    / "hmb_agent_core.dat"
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

sealed = read_private_policy_fixture_if_available()
assert sealed is not None
original_policy_reader = agent._hmb._read_agent_policy_envelope
_fixture_reader, installed_sealed = install_private_policy_reader(agent._hmb)
assert _fixture_reader is original_policy_reader
assert installed_sealed == sealed

policy, binding = agent._hmb._load_verified_behavior_documents()
policy = policy.strip()
binding = binding.strip()
identity = agent._hmb.get_internal_policy_identity()

assert f'version = "{EXPECTED_RELEASE_VERSION}"' in (
    ROOT / "pyproject.toml"
).read_text(encoding="utf-8")
assert isinstance(identity["version"], str) and identity["version"]
assert identity["contract_sha256"] == hashlib.sha256(
    policy.encode("utf-8") + b"\0" + binding.encode("utf-8")
).hexdigest()
assert identity["envelope_sha256"] == hashlib.sha256(sealed).hexdigest()
policy_rule_list = agent._split_behavior_rules(policy, 4)
binding_rule_list = agent._split_behavior_rules(binding, 4)
assert len(policy_rule_list) == 4
assert len(binding_rule_list) == 4
assert all(rule.strip() for rule in policy_rule_list + binding_rule_list)
assert policy_rule_list != binding_rule_list

# The signed/compressed server envelope is read from the private test fixture only.
# Runtime and public packages never use this path or carry a local fallback.
assert policy.encode("utf-8") not in sealed
assert binding.encode("utf-8") not in sealed

envelope = json.loads(sealed.decode("utf-8"))
assert envelope["schema"] == agent._hmb._AGENT_POLICY_ENVELOPE_SCHEMA
assert envelope["algorithm"] == agent._hmb._AGENT_POLICY_SIGNATURE_ALGORITHM
assert envelope["key_id"] == agent._hmb._AGENT_POLICY_SIGNING_KEY_ID
assert envelope["key_id"] == EXPECTED_SIGNING_KEY_ID
assert envelope["payload_sha256"]
assert envelope["signature"]
payload = agent._hmb._decode_signed_agent_policy_envelope(sealed)
validated_payload = agent._hmb._validate_agent_policy_payload(payload)
assert payload["schema"] == "hmb-agent-policy-v3"
assert payload["final_policy_version"] == identity["version"]
assert hashlib.sha256(policy.encode("utf-8")).hexdigest() == payload["policy_sha256"]
assert hashlib.sha256(binding.encode("utf-8")).hexdigest() == payload["binding_sha256"]
assert validated_payload["policy_sha256"] == payload["policy_sha256"]
assert validated_payload["binding_sha256"] == payload["binding_sha256"]


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
empty_prompt_state = prompt._default_widget_state()
empty_hmb_prompt = prompt._build_prompt_package(empty_prompt_state)
empty_hmb_machine_prompt = prompt._build_data_only_prompt_package(
    empty_prompt_state
)
assert policy not in empty_hmb_prompt
assert binding not in empty_hmb_prompt

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
    paired_machine_prompt: str = "",
) -> tuple[bool, bool, int, int, int, bool]:
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_ruleset_names = ("", "")
    node._hmb_native_calls_this_process = 0
    node.parameter_output_values = {"agent": {}, "output": ""}
    paired_source = None
    if canonical_prompt_connected:
        assert paired_machine_prompt

        class PairedPromptSource:
            @staticmethod
            def _hmb_agent_prompt_snapshot(expected_visible):
                visible = str(expected_visible or "")
                return {
                    "schema": agent._PAIRED_PROMPT_SNAPSHOT_SCHEMA,
                    "version": agent._PAIRED_PROMPT_SNAPSHOT_VERSION,
                    "generation": 1,
                    "visible_sha256": hashlib.sha256(
                        visible.encode("utf-8")
                    ).hexdigest(),
                    "machine_sha256": hashlib.sha256(
                        paired_machine_prompt.encode("utf-8")
                    ).hexdigest(),
                    "machine_prompt": paired_machine_prompt,
                }

        paired_source = PairedPromptSource()
    observations: list[tuple[bool, bool, int, int, int]] = []
    secured: list[bool] = []

    def native_once(self):
        names = tuple(self._hmb_ruleset_names)
        observations.append(
            (
                bool(self._hmb_rules_active),
                len(set(names)) == 2
                and all(
                    len(name) == 32
                    and all(character in "0123456789abcdef" for character in name)
                    for name in names
                ),
                sum(bool(name) for name in names),
                len(self._hmb_policy_rules),
                len(self._hmb_binding_rules),
            )
        )
        self.parameter_output_values["output"] = "native-complete"
        if False:
            yield None
        return "native-complete"

    def secure(self):
        secured.append(True)

    node.get_parameter_value = types.MethodType(
        lambda _self, name: (
            prompt_value
            if name in {"prompt", agent._AGENT_SHOT_PROMPT_INPUT_PARAMETER}
            else None
        ),
        node,
    )
    node._run_native_agent_once = types.MethodType(native_once, node)
    node._secure_hmb_outputs = types.MethodType(secure, node)
    node._hmb_shot_channel_subscription = types.MethodType(
        lambda _self: {"enabled": False},
        node,
    )

    def canonical_prompt_topology(self):
        # The production topology verifier clears any retained predecessor and
        # installs the exact live Prompt instance during this call. Mirror that
        # paired-source side effect instead of returning a provenance-free bool.
        setattr(
            self,
            agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,
            paired_source if canonical_prompt_connected else None,
        )
        return canonical_prompt_connected

    node._has_canonical_hmb_prompt_connection = types.MethodType(
        canonical_prompt_topology,
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
    node._hmb_ruleset_names = ("stale-a", "stale-b")
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
    assert node._hmb_policy == ""
    assert node._hmb_binding == ""
    assert node._hmb_policy_rules == []
    assert node._hmb_binding_rules == []
    assert node._hmb_ruleset_names == ("", "")
    assert node.parameter_output_values["agent"] == {}
    assert node.parameter_output_values["output"] == error_text
    assert "fin-rcomp1" not in error_text.casefold()
    return error_text


for composition in agent_compositions:
    has_prompt = "P" in composition
    route = exercise_agent_route(
        empty_hmb_prompt if has_prompt else plain_prompt,
        canonical_prompt_connected=has_prompt,
        paired_machine_prompt=empty_hmb_machine_prompt if has_prompt else "",
    )
    if has_prompt:
        assert route == (True, True, 2, 4, 4, True), composition
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
    assert exercise_agent_route(direct_payload) == (False, False, 0, 0, 0, False)

# Empty, image-only, video-described, and mixed typed Prompt packages all
# activate the same non-gating policy. Media completion is not a prerequisite.
image_state = prompt._default_widget_state()
image_state["images"][0].update({
    "present": True,
    "label": "manually supplied design reference",
    "source_type": "Character Appearance",
    "owner": "Design target",
})
video_state = prompt._default_widget_state()
video_state["videos"] = [prompt._default_video_item(3)]
video_state["videos"][0].update({
    "present": True,
    "label": "independently supplied timing reference",
    "source_type": "Motion Reference",
    "control_role": "Context Only",
})
mixed_state = prompt._default_widget_state()
mixed_state["images"] = [prompt._default_image_item(2)]
mixed_state["images"][0].update({
    "present": True,
    "label": "library asset",
    "source_type": "Environment / Background",
    "owner": "Scene / Environment",
})
mixed_state["videos"] = [prompt._default_video_item(4)]
mixed_state["videos"][0].update({
    "present": True,
    "label": "optional motion guide",
    "source_type": "Motion Guide / Retargeting Reference",
    "control_role": "Derived Motion Decoding Only",
})
payload_variant_states = (
    empty_prompt_state,
    image_state,
    video_state,
    mixed_state,
)
for variant_state in payload_variant_states:
    variant = prompt._build_prompt_package(variant_state)
    machine_variant = prompt._build_data_only_prompt_package(variant_state)
    assert exercise_agent_route(
        variant,
        canonical_prompt_connected=True,
        paired_machine_prompt=machine_variant,
    ) == (True, True, 2, 4, 4, True)

# Copied or forged HMB-shaped text is still a native request when the canonical
# Prompt edge is absent. A canonical edge with a stale/plain payload fails
# closed because the current typed FX/Timing envelope is mandatory.
assert exercise_agent_route(empty_hmb_prompt) == (False, False, 0, 0, 0, False)
assert exercise_agent_block(plain_prompt) == agent._HMB_SOURCE_CONTRACT_INVALID_MESSAGE

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
            empty_hmb_prompt
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
tampered_policy_bytes = json.dumps(
    tampered_envelope,
    separators=(",", ":"),
).encode("utf-8")
assert_policy_rejected(tampered_policy_bytes)
assert agent._hmb.get_internal_policy_identity() == identity

# Runtime source contains no stable ruleset labels or legacy synthesized-policy
# fallback. Trusted signing and document self-hashes are the transport gate;
# signed server version and wording are not byte-pinned.
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
assert "secrets.token_hex(16)" in agent_source
assert "_secure_hmb_outputs" in agent_source
assert "_contains_public_output_state_leak" in agent_source
assert "_prepend_standard_library_paths_for_agent" not in common_source
assert "pkgutil.walk_packages" not in common_source
assert "Path.home() / \"Documents\" / \"GriptapeNodes\"" not in common_source
assert "_AGENT_POLICY_RSA_MODULUS_B64" in common_source
assert "_verify_agent_policy_signature" in common_source
assert "_BUNDLED_AGENT_POLICY_FILE" not in common_source
assert r"\\FIN-RCOMP7\D$\agent" not in common_source

agent._hmb._read_agent_policy_envelope = original_policy_reader

print(
    "HMB independent hybrid Agent policy integration regression: PASS "
    f"(15 compositions / 8 Agent subsets; contract {identity['contract_sha256'][:12]})"
)
