from __future__ import annotations

import hashlib
import importlib.util
import json
import ssl
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMON_PATH = ROOT / "_hmb_common.py"
AGENT_PATH = ROOT / "HMBAgentLibrary.py"
MANIFEST_PATH = ROOT / "griptape-nodes-library.json"
CA_PATH = ROOT / "resources" / "tls" / "hmb_agent_broker_ca.pem"
SESSION_PATH = ROOT / "_hmb_agent_session.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common_source = COMMON_PATH.read_text(encoding="utf-8")
agent_source = AGENT_PATH.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

assert "\\D$\\" not in common_source
assert "\\D$\\" not in agent_source
assert "server_dat_path" not in json.dumps(manifest)
assert "direct_server_dat" not in json.dumps(manifest)
assert "_read_agent_policy_server_dat" not in common_source
assert "_legacy_fetch_agent_policy_envelope" not in common_source
assert not (ROOT / "HMB_Agent_Griptape.bat").exists()
assert "HMB_AGENT_POLICY_PROCESS_BOOTSTRAP" not in common_source
assert "HMB_Agent_Griptape.bat" not in agent_source
assert "_hmb._bootstrap_agent_policy_session()" in agent_source
assert "bootstrap_once_authorized(" in common_source
assert "with _agent_process_session._condition" not in common_source

delivery = manifest["metadata"]["agent_policy_delivery"]
assert delivery == {
    "archive_source_count": 26,
    "mode": "authenticated_broker_session",
    "broker_endpoint": "https://192.168.203.245:8443/api/v1/agent-core/dat",
    "public_ca_path": "resources/tls/hmb_agent_broker_ca.pem",
    "verification": (
        "pinned_tls_dpapi_bearer_rsa3072_sha256_v3_contract_once_per_process"
    ),
}

assert SESSION_PATH.is_file()
assert CA_PATH.is_file()
common = load("_hmb_authenticated_broker_regression_common", COMMON_PATH)
assert common._AGENT_POLICY_BROKER_URL == delivery["broker_endpoint"]
assert not hasattr(common, "_AGENT_POLICY_BOOTSTRAP_MARKER")
der = ssl.PEM_cert_to_DER_cert(CA_PATH.read_text(encoding="ascii"))
assert hashlib.sha256(der).hexdigest() == common._AGENT_POLICY_BROKER_CA_DER_SHA256

# The compatibility reader must stay wired to the authenticated Broker GET.
sentinel = b"authenticated-broker-envelope"
original_fetch = common._fetch_agent_policy_envelope
common._fetch_agent_policy_envelope = lambda: sentinel
try:
    assert common._read_agent_policy_envelope() == sentinel
finally:
    common._fetch_agent_policy_envelope = original_fetch

# Packaged-process provenance alone owns one verified process snapshot; no
# launcher marker is required. Agent executions read defensive copies and never
# issue a second transport request.
fetches: list[bool] = []
common._agent_policy_process_provenance_valid = lambda: True
common._fetch_verified_agent_rule_payload = lambda: (
    fetches.append(True) or {"policy": "verified", "binding": "verified"}
)
common._bootstrap_agent_policy_session()
assert common._agent_policy_session_state() == "READY"
first = common._load_agent_rule_payload()
second = common._load_agent_rule_payload()
assert first == second == {"policy": "verified", "binding": "verified"}
assert first is not second
assert fetches == [True]

# An arbitrary process cannot turn a launcher/environment signal into
# authority. Failed provenance is terminal for that process and performs zero
# authenticated Broker fetches.
denied_session = load("_hmb_agent_denied_bootstrap_regression", SESSION_PATH)
denied_fetches: list[bool] = []
common._agent_process_session = denied_session
common._agent_policy_process_provenance_valid = lambda: False
common._fetch_verified_agent_rule_payload = lambda: (
    denied_fetches.append(True) or {"policy": "forbidden", "binding": "forbidden"}
)
try:
    common._bootstrap_agent_policy_session()
except RuntimeError:
    pass
else:
    raise AssertionError("non-packaged process initialized the Agent policy session")
assert denied_session._status_for_regression()[0] == "failed"
assert denied_fetches == []

# The first authenticated Broker request may legitimately take several
# seconds, but it must not retain the process-cell condition for that entire
# wait.  Status and READY-only readers need to fail/return immediately while a
# single owner performs transport outside the lock.
session = load("_hmb_agent_nonblocking_bootstrap_regression", SESSION_PATH)
loader_started = threading.Event()
loader_release = threading.Event()


def slow_verified_loader():
    loader_started.set()
    assert loader_release.wait(2.0)
    return {"policy": "verified", "binding": "verified"}


bootstrap_thread = threading.Thread(
    target=lambda: session.bootstrap_once_authorized(
        lambda: True,
        slow_verified_loader,
    ),
    daemon=True,
)
bootstrap_thread.start()
assert loader_started.wait(1.0)
started_at = time.perf_counter()
assert session._status_for_regression()[0] == "loading"
try:
    session.read_ready()
except RuntimeError:
    pass
else:
    raise AssertionError("LOADING Agent policy session was exposed as READY")
assert time.perf_counter() - started_at < 0.25
loader_release.set()
bootstrap_thread.join(2.0)
assert not bootstrap_thread.is_alive()
assert session._status_for_regression()[0] == "ready"

print("HMB authenticated Agent Broker delivery regression: PASS")
