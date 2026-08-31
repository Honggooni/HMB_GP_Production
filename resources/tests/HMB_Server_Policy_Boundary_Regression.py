from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DAT_PATH = ROOT / "resources" / "agent" / "hmb_agent_core.dat"


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load("_hmb_common")
agent = load("HMBAgentLibrary")
packager_path = ROOT / "tools" / "package_runtime_release.py"
packager_spec = importlib.util.spec_from_file_location(
    "_hmb_bundled_policy_packager", packager_path
)
assert packager_spec is not None and packager_spec.loader is not None
packager = importlib.util.module_from_spec(packager_spec)
packager_spec.loader.exec_module(packager)

encoded = common._read_agent_policy_envelope()
validated = common._validate_agent_policy_payload(
    common._decode_signed_agent_policy_envelope(encoded)
)
identity = packager.synchronize_bundled_agent_policy()
assert identity == {
    "envelope_sha256": hashlib.sha256(encoded).hexdigest(),
    "final_policy_version": validated["final_policy_version"],
    "policy_pair_sha256": validated["policy_pair_sha256"],
}
assert DAT_PATH.read_bytes() == encoded
assert packager.BUNDLED_AGENT_POLICY_MEMBER.as_posix() in packager.RUNTIME_INSTALL_FILES
assert "resources/tls/hmb_agent_broker_ca.pem" not in packager.RUNTIME_INSTALL_FILES
assert packager.POLICY_DELIVERY == "bundled-signed-dat"

manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
delivery = manifest["metadata"]["agent_policy_delivery"]
assert delivery["envelope_sha256"] == identity["envelope_sha256"]
assert delivery["policy_version"] == identity["final_policy_version"]
assert delivery["contract_sha256"] == identity["policy_pair_sha256"]
assert "[HMB LOCAL POLICY REQUIRED]" in agent._HMB_POLICY_UNAVAILABLE_MESSAGE
assert "Broker login" not in agent._HMB_POLICY_UNAVAILABLE_MESSAGE

print("HMB bundled Agent policy installation/package boundary regression: PASS")
