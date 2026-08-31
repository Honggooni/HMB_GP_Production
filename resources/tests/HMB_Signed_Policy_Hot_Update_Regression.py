from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sys
import zlib
from pathlib import Path

from _hmb_bundled_policy_session import read_bundled_policy_artifact


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def self_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


common = load("_hmb_common")
agent = load("HMBAgentLibrary")
real_signature_verifier = common._verify_agent_policy_signature

# The production public key must validate the exact DAT included in the runtime.
bundled_encoded = read_bundled_policy_artifact()
bundled_payload = common._decode_signed_agent_policy_envelope(bundled_encoded)
bundled_validated = common._validate_agent_policy_payload(bundled_payload)
assert bundled_validated["policy_sha256"] == self_hash(
    bundled_validated["policy"]
)
assert bundled_validated["binding_sha256"] == self_hash(
    bundled_validated["binding"]
)

synthetic_policy = "\n\n".join(
    (
        "Behavior 1",
        "1. PROJECT_SYNTHETIC_ONE\n\nSynthetic project authority alpha.",
        "2. PROJECT_SYNTHETIC_TWO\n\nSynthetic project authority beta.",
        "3. PROJECT_SYNTHETIC_THREE\n\nSynthetic project authority gamma.",
        "4. PROJECT_SYNTHETIC_FOUR\n\nSynthetic project authority delta.",
    )
)
synthetic_binding = "\n\n".join(
    (
        "Behavior 2",
        "1. SHOT_SYNTHETIC_ONE\n\nSynthetic shot control north.",
        "2. SHOT_SYNTHETIC_TWO\n\nSynthetic shot control east.",
        "3. SHOT_SYNTHETIC_THREE\n\nSynthetic shot control south.",
        "4. SHOT_SYNTHETIC_FOUR\n\nSynthetic shot control west.",
    )
)
baseline_payload = {
    "schema": common._AGENT_POLICY_SCHEMA,
    "policy": synthetic_policy,
    "policy_sha256": self_hash(synthetic_policy),
    "binding": synthetic_binding,
    "binding_sha256": self_hash(synthetic_binding),
    "final_policy_version": "2026-08-11.synthetic-policy.v4.1",
}


def make_revision(
    version: str,
    *,
    note: str,
    payload_overrides: dict | None = None,
    envelope_overrides: dict | None = None,
) -> tuple[bytes, bytes, bytes]:
    payload = copy.deepcopy(baseline_payload)
    payload["final_policy_version"] = version
    payload["policy"] += f"\n\n{note} Project."
    payload["binding"] += f"\n\n{note} Shot."
    payload["policy_sha256"] = self_hash(payload["policy"])
    payload["binding_sha256"] = self_hash(payload["binding"])
    if payload_overrides:
        payload.update(payload_overrides)
    payload_bytes = zlib.compress(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        level=9,
    )
    test_signature = hashlib.sha384(payload_bytes).digest() * 8
    envelope = {
        "schema": common._AGENT_POLICY_ENVELOPE_SCHEMA,
        "algorithm": common._AGENT_POLICY_SIGNATURE_ALGORITHM,
        "key_id": common._AGENT_POLICY_SIGNING_KEY_ID,
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "payload": base64.b64encode(payload_bytes).decode("ascii"),
        "signature": base64.b64encode(test_signature).decode("ascii"),
    }
    if envelope_overrides:
        envelope.update(envelope_overrides)
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        payload_bytes,
        test_signature,
    )


revision_a, revision_a_payload, revision_a_signature = make_revision(
    "2026-08-12.synthetic-policy.v4.1.1",
    note="Signed Master revision A",
)
revision_b, revision_b_payload, revision_b_signature = make_revision(
    "2026-09-03.synthetic-policy.v7.2",
    note="Signed Master revision B",
)
trusted_test_pairs = {
    (revision_a_payload, revision_a_signature),
    (revision_b_payload, revision_b_signature),
}
common._verify_agent_policy_signature = (
    lambda payload_bytes, signature: (payload_bytes, signature) in trusted_test_pairs
)


def rejected(label: str, operation) -> None:
    try:
        operation()
    except RuntimeError:
        return
    raise AssertionError(f"Rejected hot-update case was accepted: {label}")


try:
    # A trusted signer may revise both 4-rule documents and signed version
    # metadata in a new package. Only envelope schema and self-hashes remain
    # stable client-side.
    decoded_a = common._decode_signed_agent_policy_envelope(revision_a)
    validated_a = common._validate_agent_policy_payload(decoded_a)
    decoded_b = common._decode_signed_agent_policy_envelope(revision_b)
    validated_b = common._validate_agent_policy_payload(decoded_b)
    assert validated_a["final_policy_version"].endswith(".v4.1.1")
    assert validated_b["final_policy_version"].endswith(".v7.2")
    assert validated_a["policy_sha256"] != baseline_payload["policy_sha256"]
    assert validated_a["binding_sha256"] != baseline_payload["binding_sha256"]
    assert validated_a["policy_pair_sha256"] == hashlib.sha256(
        validated_a["policy"].encode("utf-8")
        + b"\0"
        + validated_a["binding"].encode("utf-8")
    ).hexdigest()
    assert validated_b["policy_pair_sha256"] == hashlib.sha256(
        validated_b["policy"].encode("utf-8")
        + b"\0"
        + validated_b["binding"].encode("utf-8")
    ).hexdigest()
    assert (
        validated_a["policy_pair_sha256"]
        != validated_b["policy_pair_sha256"]
    )

    # A package may atomically install either trusted revision before a newly
    # launched process. Verify each candidate at the local read boundary; an
    # already bootstrapped process deliberately remains on its one snapshot.
    reads = iter((revision_a, revision_b))
    real_envelope_reader = common._read_agent_policy_envelope
    common._read_agent_policy_envelope = lambda: next(reads)
    try:
        loaded_a = common._load_verified_agent_rule_payload()
        loaded_b = common._load_verified_agent_rule_payload()
    finally:
        common._read_agent_policy_envelope = real_envelope_reader
    assert loaded_a["final_policy_version"].endswith(".v4.1.1")
    assert loaded_b["final_policy_version"].endswith(".v7.2")
    assert loaded_a["envelope_sha256"] == hashlib.sha256(revision_a).hexdigest()
    assert loaded_b["envelope_sha256"] == hashlib.sha256(revision_b).hexdigest()

    # One verified bootstrap owns an immutable process snapshot. Reads are
    # defensive copies and never read the DAT a second time.
    common._agent_process_session.bootstrap_once(
        True,
        lambda: True,
        lambda: dict(loaded_a),
    )
    common._read_agent_policy_envelope = lambda: (_ for _ in ()).throw(
        AssertionError("READY session performed another bundled DAT read")
    )
    try:
        session_a = common._load_agent_rule_payload()
        session_b = common._load_agent_rule_payload()
    finally:
        common._read_agent_policy_envelope = real_envelope_reader
    assert session_a == session_b == loaded_a
    assert session_a is not session_b

    # One Agent execution consumes documents and audit identity from one
    # already-verified payload snapshot, never from multiple server reads.
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_policy_identity = {}
    calls: list[bool] = []
    real_payload_loader = agent._hmb._load_agent_rule_payload

    def one_snapshot():
        calls.append(True)
        return dict(loaded_a)

    agent._hmb._load_agent_rule_payload = one_snapshot
    try:
        policy, binding, policy_rules, binding_rules = node._load_hmb_rules()
    finally:
        agent._hmb._load_agent_rule_payload = real_payload_loader
    assert calls == [True]
    assert len(policy_rules) == len(binding_rules) == 4
    assert policy == loaded_a["policy"] and binding == loaded_a["binding"]
    assert node._hmb_policy_identity == {
        "version": loaded_a["final_policy_version"],
        "contract_sha256": loaded_a["policy_pair_sha256"],
        "envelope_sha256": hashlib.sha256(revision_a).hexdigest(),
    }

    # Trusted signatures do not bypass transport schema or document
    # self-integrity. Policy version and wording are signed-DAT-owned.
    stale_hash_payload = copy.deepcopy(decoded_a)
    stale_hash_payload["policy"] += " raw edit"
    rejected(
        "raw edit with stale self-hash",
        lambda: common._validate_agent_policy_payload(stale_hash_payload),
    )
    legacy_identity_payload = copy.deepcopy(decoded_a)
    legacy_identity_payload["final_motion_look_policy_sha256"] = "0" * 64
    legacy_identity_validated = common._validate_agent_policy_payload(
        legacy_identity_payload
    )
    assert legacy_identity_validated["policy_pair_sha256"] != "0" * 64
    assert "final_motion_look_policy_sha256" not in legacy_identity_validated

    arbitrary_version_payload = copy.deepcopy(decoded_a)
    arbitrary_version_payload["final_policy_version"] = "vNext/server-approved"
    assert common._validate_agent_policy_payload(arbitrary_version_payload)[
        "final_policy_version"
    ] == "vNext/server-approved"
    wrong_shape_payload = copy.deepcopy(decoded_a)
    wrong_shape_payload["policy"] = wrong_shape_payload["policy"].replace(
        "\n4. PROJECT_SYNTHETIC_FOUR",
        "\n5. PROJECT_SYNTHETIC_FOUR",
        1,
    )
    wrong_shape_payload["policy_sha256"] = self_hash(wrong_shape_payload["policy"])
    wrong_shape_validated = common._validate_agent_policy_payload(wrong_shape_payload)
    rejected(
        "non-4-rule Agent delivery structure",
        lambda: agent._split_behavior_rules(wrong_shape_validated["policy"], 4),
    )
    extra_payload_field = copy.deepcopy(decoded_a)
    extra_payload_field["policy_revision_bypass"] = True
    assert common._validate_agent_policy_payload(extra_payload_field)[
        "policy_sha256"
    ] == decoded_a["policy_sha256"]
    wrong_key, _, _ = make_revision(
        "2026-08-12.synthetic-policy.v4.1.2",
        note="Wrong key",
        envelope_overrides={"key_id": "untrusted-policy-key"},
    )
    rejected(
        "different signer key id",
        lambda: common._decode_signed_agent_policy_envelope(wrong_key),
    )
    extra_envelope, _, _ = make_revision(
        "2026-08-12.synthetic-policy.v4.1.3",
        note="Extra envelope",
        envelope_overrides={"unsigned_hint": "ignore-signature"},
    )
    rejected(
        "extra unsigned envelope field",
        lambda: common._decode_signed_agent_policy_envelope(extra_envelope),
    )
finally:
    common._verify_agent_policy_signature = real_signature_verifier

# The synthetic candidate is never trusted by the production public key.
rejected(
    "untrusted synthetic signature",
    lambda: common._decode_signed_agent_policy_envelope(revision_a),
)

common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
for removed_pin in (
    "_AGENT_POLICY_ENVELOPE_SHA256",
    "_AGENT_POLICY_PROJECT_SHA256",
    "_AGENT_POLICY_BINDING_SHA256",
):
    assert removed_pin not in common_source
assert "lru_cache" not in common_source

print(
    "HMB signed policy hot-update regression: PASS "
    "(allow=trusted key+v3 schema+self-hashes+dynamic version/wording; "
    "deny=unsigned/tamper/wrong key/schema/digest/non-4-rule delivery)"
)
