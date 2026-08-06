from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.5.15"
EXPECTED_VERSION = "2026-08-01.goal-final-authority.v2"
EXPECTED_CONTRACT_SHA256 = "a17809e4103628c1b0ab0b96081f6325faf9d16703a5fac57ef7d1eaa7d043bf"
OPTIONAL_MARKER = "OPTIONAL VIDEO CONTROL:"
ISOLATION_MARKER = "COLOR PLAYBLAST ISOLATION WITHOUT DEPENDENCY:"
FORBIDDEN_DEPENDENCIES = (
    "[HMB VALIDATION ERROR]",
    "requires the validated Motion Guide",
    "Missing or incomplete approved appearance bindings",
    "must stop generation",
    "@video1 is mandatory",
    "@video1 must be active",
)


def load_module(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent = load_module("HMBAgentLibrary")
policy = agent.get_internal_policy_rules().strip()
binding = agent.get_internal_binding_rules().strip()
identity = agent._hmb.get_internal_policy_identity()

assert f'version = "{EXPECTED_RELEASE_VERSION}"' in (
    ROOT / "pyproject.toml"
).read_text(encoding="utf-8")
assert identity == {
    "version": EXPECTED_VERSION,
    "contract_sha256": EXPECTED_CONTRACT_SHA256,
}
assert len(agent._split_behavior_rules(policy, 4)) == 4
assert len(agent._split_behavior_rules(binding, 4)) == 4

for rules in (policy, binding):
    assert rules.count(OPTIONAL_MARKER) == 1
    assert rules.count(ISOLATION_MARKER) == 1
    assert "@video1 is not a prerequisite" in rules
    assert "Motion Guide, Depth, Color Playblast" in rules
    assert "generated companions are optional evidence" in rules
    assert "proxy colors and temporary materials" in rules
    assert "default interpretation, not a prohibition" in rules
    assert "explicit user goal may use any visible property" in rules
    assert "separate image binding or Motion Guide is optional" in rules
    assert "no source is rejected, narrowed, or omitted" in rules
    for forbidden in FORBIDDEN_DEPENDENCIES:
        assert forbidden.casefold() not in rules.casefold(), forbidden

bundled_policy_path = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
assert bundled_policy_path.is_file()
sealed = bundled_policy_path.read_bytes()
assert OPTIONAL_MARKER.encode("utf-8") not in sealed
assert ISOLATION_MARKER.encode("utf-8") not in sealed
payload = agent._hmb._decode_signed_agent_policy_envelope(sealed)
agent._hmb._validate_agent_policy_payload(payload)

assert payload["final_policy_version"] == EXPECTED_VERSION
assert payload["final_motion_look_policy_sha256"] == EXPECTED_CONTRACT_SHA256
isolation_clauses = [str(item) for item in payload["video_appearance_isolation_clauses"]]
assert len(isolation_clauses) == 2
assert isolation_clauses[0].startswith(OPTIONAL_MARKER)
assert isolation_clauses[1].startswith(ISOLATION_MARKER)
for clause in isolation_clauses:
    assert policy.count(clause) == 1
    assert binding.count(clause) == 1
    assert clause.encode("utf-8") not in sealed

# Proxy appearance has a safe default interpretation, but the user's explicit
# goal remains able to override it without a media dependency or output gate.
isolation = isolation_clauses[1]
assert "proxy colors" in isolation
assert "default interpretation, not a prohibition" in isolation
assert "explicit user goal may use any visible property" in isolation
assert "no source is rejected, narrowed, or omitted" in isolation
assert "zero identity or final-look authority" not in isolation
assert "stop" not in isolation.casefold()
assert "error" not in isolation.casefold()

print(
    "HMB Color Playblast non-dependent appearance-isolation regression: PASS "
    f"({EXPECTED_VERSION}, contract {EXPECTED_CONTRACT_SHA256[:12]})"
)
