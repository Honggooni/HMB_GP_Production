from __future__ import annotations

import hashlib
import importlib.util
import json
import ssl
import sys
from email.message import Message
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_URL = "https://192.168.203.245:8443/api/v1/agent-core/dat"
EXPECTED_HOST = "192.168.203.245"
EXPECTED_PORT = 8443
EXPECTED_PATH = "/api/v1/agent-core/dat"
EXPECTED_VERSION = "2026-08-12.agent-shot-quality.v4.2"
EXPECTED_CONTRACT_SHA256 = (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
LOAD_FAILURE = "HMB_GP_Agent_Library internal rule payload could not be loaded."


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("_hmb_server_policy_boundary_common", ROOT / "_hmb_common.py")
agent = load("_hmb_server_policy_boundary_agent", ROOT / "HMBAgentLibrary.py")
manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)

assert common._AGENT_POLICY_BROKER_URL == EXPECTED_URL
assert common._AGENT_POLICY_BROKER_HOST == EXPECTED_HOST
assert common._AGENT_POLICY_BROKER_PORT == EXPECTED_PORT
assert common._AGENT_POLICY_BROKER_PATH == EXPECTED_PATH
assert common._AGENT_POLICY_VERSION == EXPECTED_VERSION
assert common._AGENT_POLICY_CONTRACT_SHA256 == EXPECTED_CONTRACT_SHA256
assert common._AGENT_POLICY_ENVELOPE_SCHEMA == "hmb-agent-policy-envelope-v3"
assert common._AGENT_POLICY_SCHEMA == "hmb-agent-policy-v3"
assert not hasattr(common, "AGENT_RULE_DATA_PATH_ENV")
assert not hasattr(common, "_AGENT_POLICY_SERVER_UNC")
assert not hasattr(common, "_resolve_agent_rule_data_path")

delivery = manifest["metadata"]["agent_policy_delivery"]
assert delivery["mode"] == "authenticated_broker_session"
assert delivery["broker_endpoint"] == EXPECTED_URL
assert delivery["public_ca_path"] == "resources/tls/hmb_agent_broker_ca.pem"
assert "bootstrap_marker" not in delivery
assert "launcher_path" not in delivery
assert not hasattr(common, "_AGENT_POLICY_BOOTSTRAP_MARKER")
assert delivery["verification"] == (
    "pinned_tls_dpapi_bearer_rsa3072_sha256_v3_contract_once_per_process"
)

# The sole packaged PEM is a public Broker trust anchor and its DER identity is
# pinned independently.  It is not a policy artifact or a client credential.
ca_path = ROOT / delivery["public_ca_path"]
ca_text = ca_path.read_text(encoding="ascii")
ca_der = ssl.PEM_cert_to_DER_cert(ca_text)
assert hashlib.sha256(ca_der).hexdigest() == (
    common._AGENT_POLICY_BROKER_CA_DER_SHA256
)


class FakeSocket:
    def __init__(self, peer_der: bytes) -> None:
        self.peer_der = peer_der

    def getpeercert(self, *, binary_form: bool = False):
        assert binary_form is True
        return self.peer_der


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.body = body
        self.closed = False
        self.headers = Message()
        for name, value in (
            ("Content-Type", "application/octet-stream"),
            ("Content-Disposition", 'attachment; filename="hmb_agent_core.dat"'),
            ("Cache-Control", "private, no-store, no-transform"),
            ("Content-Length", str(len(body))),
            ("Accept-Ranges", "none"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Request-Id", "0123456789abcdef01234567"),
            ("Vary", "Authorization"),
        ):
            self.headers.add_header(name, value)

    def read(self, limit: int = -1) -> bytes:
        assert limit == common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 1
        return self.body

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    instances: list["FakeConnection"] = []
    peer_der = ca_der
    body = b"authenticated-broker-envelope"

    def __init__(self, host: str, port: int, *, timeout: float, context) -> None:
        self.constructor = (host, port, timeout, context)
        self.sock = FakeSocket(self.peer_der)
        self.response = FakeResponse(self.body)
        self.request: tuple[str, str, bool, bool] | None = None
        self.headers: list[tuple[str, str]] = []
        self._buffer: list[bytes] = []
        self.closed = False
        self.__class__.instances.append(self)

    def connect(self) -> None:
        return None

    def putrequest(
        self,
        method: str,
        path: str,
        *,
        skip_host: bool,
        skip_accept_encoding: bool,
    ) -> None:
        self.request = (method, path, skip_host, skip_accept_encoding)

    def putheader(self, name: str, value: str) -> None:
        self.headers.append((name, value))

    def endheaders(self) -> None:
        return None

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


# Exercise the exact authenticated GET without touching the network.  TLS peer
# pinning, a bounded DPAPI-derived bearer value, and strict response headers are
# all mandatory before any DAT bytes cross the transport boundary.
real_https_connection = common.http.client.HTTPSConnection
real_tls_context = common._agent_policy_tls_context
real_token_loader = common._load_agent_policy_bearer_token
fake_context = object()
token_buffer = bytearray(b"broker-session-token")
common.http.client.HTTPSConnection = FakeConnection
common._agent_policy_tls_context = lambda: fake_context
common._load_agent_policy_bearer_token = lambda: token_buffer
try:
    assert common._fetch_agent_policy_envelope() == FakeConnection.body
finally:
    common.http.client.HTTPSConnection = real_https_connection
    common._agent_policy_tls_context = real_tls_context
    common._load_agent_policy_bearer_token = real_token_loader

connection = FakeConnection.instances[-1]
assert connection.constructor == (
    EXPECTED_HOST,
    EXPECTED_PORT,
    common._AGENT_POLICY_REQUEST_TIMEOUT_SECONDS,
    fake_context,
)
assert connection.request == ("GET", EXPECTED_PATH, True, True)
assert dict(connection.headers) == {
    "Host": "192.168.203.245:8443",
    "Accept": "application/octet-stream",
    "Accept-Encoding": "identity",
    "Authorization": "Bearer broker-session-token",
    "Cache-Control": "no-store",
}
assert connection.response.closed is True
assert connection.closed is True
assert token_buffer == bytearray(len(token_buffer))

# A certificate at the correct address with the wrong DER identity is rejected
# before the bearer-token loader is called.
class WrongPeerConnection(FakeConnection):
    peer_der = b"wrong-peer-certificate"


common.http.client.HTTPSConnection = WrongPeerConnection
common._agent_policy_tls_context = lambda: fake_context
common._load_agent_policy_bearer_token = lambda: (_ for _ in ()).throw(
    AssertionError("bearer token loaded before TLS peer pin validation")
)
try:
    try:
        common._fetch_agent_policy_envelope()
    except RuntimeError as exc:
        assert "certificate pin mismatch" in str(exc)
    else:
        raise AssertionError("wrong Broker peer certificate was accepted")
finally:
    common.http.client.HTTPSConnection = real_https_connection
    common._agent_policy_tls_context = real_tls_context
    common._load_agent_policy_bearer_token = real_token_loader

# The compatibility reader has exactly one transport implementation.  It does
# not resolve environment paths, UNC shares, or a bundled/local DAT.
transport_calls: list[bool] = []
real_fetch = common._fetch_agent_policy_envelope
common._fetch_agent_policy_envelope = lambda: (
    transport_calls.append(True) or b"fresh-envelope"
)
try:
    assert common._read_agent_policy_envelope() == b"fresh-envelope"
    assert common._read_agent_policy_envelope() == b"fresh-envelope"
finally:
    common._fetch_agent_policy_envelope = real_fetch
assert transport_calls == [True, True]

# Agent executions are read-only consumers of one authenticated process
# snapshot.  An uninitialized session fails closed and never lazily fetches.
try:
    common._load_agent_rule_payload()
except RuntimeError as exc:
    assert str(exc) == LOAD_FAILURE
else:
    raise AssertionError("uninitialized policy session was accepted")

verified_snapshot = {
    "policy": "verified project rules",
    "binding": "verified shot rules",
    "final_policy_version": EXPECTED_VERSION,
    "final_motion_look_policy_sha256": EXPECTED_CONTRACT_SHA256,
}
bootstrap_fetches: list[bool] = []
real_provenance = common._agent_policy_process_provenance_valid
real_verified_loader = common._fetch_verified_agent_rule_payload
common._agent_policy_process_provenance_valid = lambda: True
common._fetch_verified_agent_rule_payload = lambda: (
    bootstrap_fetches.append(True) or dict(verified_snapshot)
)
try:
    common._bootstrap_agent_policy_session()
    common._bootstrap_agent_policy_session()
finally:
    common._agent_policy_process_provenance_valid = real_provenance
    common._fetch_verified_agent_rule_payload = real_verified_loader
assert common._agent_policy_session_state() == "READY"
first = common._load_agent_rule_payload()
second = common._load_agent_rule_payload()
assert first == second == verified_snapshot
assert first is not second
assert bootstrap_fetches == [True]

common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
for retired_marker in (
    "_BUNDLED_AGENT_POLICY_FILE",
    "_AGENT_POLICY_SERVER_UNC",
    "_resolve_agent_rule_data_path",
    "HMB_AGENT_POLICY_PATH",
    r"\\FIN-RCOMP7\D$\agent",
    "lru_cache",
):
    assert retired_marker not in common_source
assert "_bootstrap_agent_policy_session()" in agent_source
assert "[HMB SERVER POLICY REQUIRED]" in agent._HMB_POLICY_UNAVAILABLE_MESSAGE
assert "HMB LOCAL POLICY REQUIRED" not in agent_source
assert "resources/agent/hmb_agent_core.dat" not in agent_source

print(
    "HMB authenticated Broker Agent policy boundary regression: PASS "
    "(public CA pin / DPAPI bearer / strict HTTPS / one process snapshot)"
)
