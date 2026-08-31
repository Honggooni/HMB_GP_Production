from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DAT_PATH = ROOT / "resources" / "agent" / "hmb_agent_core.dat"


def load_common():
    path = ROOT / "_hmb_common.py"
    spec = importlib.util.spec_from_file_location("_hmb_bundled_policy_common", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load_common()
common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
seedance_source = (ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8")
manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
delivery = manifest["metadata"]["agent_policy_delivery"]

assert "_AGENT_POLICY_BROKER" not in common_source
assert "_fetch_agent_policy" not in common_source
assert "http.client" not in common_source
assert "import ssl" not in common_source
assert "_broker_load_bearer_token_readonly" in common_source
assert "_broker_load_bearer_token_readonly" in seedance_source

assert delivery["mode"] == "bundled_signed_dat"
assert delivery["runtime_path"] == "resources/agent/hmb_agent_core.dat"
assert delivery["archive_source_count"] == 26
assert delivery["verification"] == "rsa3072_sha256_v3_contract_once_per_process"

encoded = common._read_agent_policy_envelope()
assert DAT_PATH.is_file() and not DAT_PATH.is_symlink()
assert encoded == DAT_PATH.read_bytes()
payload = common._validate_agent_policy_payload(
    common._decode_signed_agent_policy_envelope(encoded)
)
assert hashlib.sha256(encoded).hexdigest() == delivery["envelope_sha256"]
assert payload["final_policy_version"] == delivery["policy_version"]
assert payload["policy_pair_sha256"] == delivery["contract_sha256"]

print("HMB bundled signed Agent policy / Seedance Broker separation regression: PASS")
