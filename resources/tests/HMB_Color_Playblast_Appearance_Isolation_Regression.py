from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RELEASE_VERSION = "0.5.18"
EXPECTED_VERSION = "2026-08-06.animation-look-continuity.v3"
EXPECTED_CONTRACT_SHA256 = "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
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
    assert "proxy colors" in rules
    assert "temporary materials" in rules
    assert "default production authority" in rules
    assert "explicit scoped instruction" in rules
    assert "named target or clearly scene-wide scope" in rules
    assert "scoped exception never converts control visualization" in rules
    assert "separate image binding or Motion Guide is optional" in rules
    assert "no source is rejected, narrowed, or omitted solely" in rules
    assert "explicit user goal may use any visible property" not in rules
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

# Proxy appearance remains control visualization. Only an explicit property,
# target, and temporal scope may create a local exception without a dependency
# or output gate.
isolation = isolation_clauses[1]
assert "proxy colors" in isolation
assert "default production authority" in isolation
assert "named visible property" in isolation
assert "named target or clearly scene-wide scope" in isolation
assert "scoped exception never converts control visualization" in isolation
assert "no source is rejected, narrowed, or omitted solely" in isolation
assert "explicit user goal may use any visible property" not in isolation
assert "zero identity or final-look authority" not in isolation
assert "stop" not in isolation.casefold()
assert "error" not in isolation.casefold()

print(
    "HMB Color Playblast non-dependent appearance-isolation regression: PASS "
    f"({EXPECTED_VERSION}, contract {EXPECTED_CONTRACT_SHA256[:12]})"
)
