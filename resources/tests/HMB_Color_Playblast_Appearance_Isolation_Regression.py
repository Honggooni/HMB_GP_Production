from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

from _hmb_bundled_policy_session import install_bundled_policy_session


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.7.29"


def load_module(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent = load_module("HMBAgentLibrary")
_original_policy_reader, sealed = install_bundled_policy_session(agent._hmb)
policy, binding = agent._hmb._load_verified_behavior_documents()
policy = policy.strip()
binding = binding.strip()
identity = agent._hmb.get_internal_policy_identity()

assert f'version = "{EXPECTED_RELEASE_VERSION}"' in (
    ROOT / "pyproject.toml"
).read_text(encoding="utf-8")
assert identity["version"]
assert identity["contract_sha256"] == hashlib.sha256(
    policy.encode("utf-8") + b"\0" + binding.encode("utf-8")
).hexdigest()
assert identity["envelope_sha256"] == hashlib.sha256(sealed).hexdigest()
assert len(agent._split_behavior_rules(policy, 4)) == 4
assert len(agent._split_behavior_rules(binding, 4)) == 4

payload = agent._hmb._decode_signed_agent_policy_envelope(sealed)
validated = agent._hmb._validate_agent_policy_payload(payload)

assert str(payload["final_policy_version"]).strip()
assert "video_appearance_isolation_clauses" not in validated
legacy_extended = dict(payload)
legacy_extended["video_appearance_isolation_clauses"] = [
    "Legacy metadata must not define runtime appearance authority."
]
assert agent._hmb._validate_agent_policy_payload(legacy_extended) == validated

print(
    "HMB Color Playblast non-dependent appearance-isolation regression: PASS "
    f"({identity['version']}, contract {identity['contract_sha256'][:12]})"
)
