from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

from _hmb_private_policy_fixture import install_private_policy_reader


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.7.15"
EXPECTED_VERSION = "2026-08-27.agent-shot-quality.v4.5"
EXPECTED_CONTRACT_SHA256 = "86852214d3e1a29eab12a2b0cff0302f6920d5d3ce3b00947d96ef1eb952c872"


def load_module(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent = load_module("HMBAgentLibrary")
_original_policy_reader, sealed = install_private_policy_reader(agent._hmb)
policy, binding = agent._hmb._load_verified_behavior_documents()
policy = policy.strip()
binding = binding.strip()
identity = agent._hmb.get_internal_policy_identity()

assert f'version = "{EXPECTED_RELEASE_VERSION}"' in (
    ROOT / "pyproject.toml"
).read_text(encoding="utf-8")
assert identity == {
    "version": EXPECTED_VERSION,
    "contract_sha256": EXPECTED_CONTRACT_SHA256,
    "envelope_sha256": hashlib.sha256(sealed).hexdigest(),
}
assert len(agent._split_behavior_rules(policy, 4)) == 4
assert len(agent._split_behavior_rules(binding, 4)) == 4

payload = agent._hmb._decode_signed_agent_policy_envelope(sealed)
agent._hmb._validate_agent_policy_payload(payload)

assert payload["final_policy_version"] == EXPECTED_VERSION
assert payload["final_motion_look_policy_sha256"] == EXPECTED_CONTRACT_SHA256
isolation_clauses = [str(item) for item in payload["video_appearance_isolation_clauses"]]
assert len(isolation_clauses) == 2
for clause in isolation_clauses:
    assert clause.strip()
    assert policy.count(clause) == 1
    assert binding.count(clause) == 1
    assert clause.encode("utf-8") not in sealed

print(
    "HMB Color Playblast non-dependent appearance-isolation regression: PASS "
    f"({EXPECTED_VERSION}, contract {EXPECTED_CONTRACT_SHA256[:12]})"
)
