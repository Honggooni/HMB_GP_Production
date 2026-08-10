from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
RELEASE_MANIFEST = DIST / "release-manifest.json"
RELEASE_ARCHIVE = DIST / "HMB_GP_Production.zip"
RELEASE_CHECKSUMS = DIST / "SHA256SUMS"
POLICY_RELATIVE = "resources/agent/hmb_agent_core.dat"
POLICY_SHA256 = "6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619"
POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
POLICY_CONTRACT_SHA256 = (
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
)
POLICY_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"
EXPECTED_SECRET_NAMES = {
    "GT_CLOUD_API_KEY",
    "GT_CLOUD_BUCKET_ID",
    "TOS_ACCESS_KEY_ID",
    "TOS_SECRET_ACCESS_KEY",
    "TOS_BUCKET_NAME",
}
FORBIDDEN_SUFFIXES = {
    ".env",
    ".jwk",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".secret",
    ".token",
}
PRIVATE_KEY_HEADER = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
COMMON_TOKEN_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
)


# GitHub and GitHub Releases are the permanent team distribution channel.
# Visibility must never be used in place of removing secrets from the source.
readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
security_text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
assert "Public team distribution repository" in readme_text
assert "Keep this repository and its GitHub" in readme_text
assert "Releases public" in readme_text
assert "Public 팀 배포 저장소" in security_text
assert "GitHub Release는 Public을" in security_text
for forbidden_visibility_policy in (
    "Private repository only",
    "반드시\n**Private**",
    "릴리스를 Private으로 유지",
):
    assert forbidden_visibility_policy not in readme_text
    assert forbidden_visibility_policy not in security_text


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


common_spec = importlib.util.spec_from_file_location(
    "_hmb_public_release_policy_verifier",
    ROOT / "_hmb_common.py",
)
assert common_spec is not None and common_spec.loader is not None
common = importlib.util.module_from_spec(common_spec)
common_spec.loader.exec_module(common)

manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
assert manifest["metadata"]["library_version"] == "0.5.31"
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert set(registered_secrets) == EXPECTED_SECRET_NAMES
assert all(value == "" for value in registered_secrets.values())
manifest_description = manifest["settings"][0]["description"]
assert "one-time browser authorization" in manifest_description
assert "CGTeamwork" not in manifest_description
seedance_entries = [
    item
    for item in manifest["nodes"]
    if item["metadata"]["display_name"] == "HMB Seedance Generation"
]
assert len(seedance_entries) == 1
seedance_entry = seedance_entries[0]
assert seedance_entry["class_name"] == "HMBSeedance20VideoGeneration"
assert seedance_entry["file_path"] == "HMBSeedanceGeneration.py"
assert not (ROOT / "HMBSeedance20VideoGeneration.py").exists()

# The two full Seedance transport regressions require a live Griptape host. Keep
# their critical output-macro boundary enforced in source-only CI as well:
# normal generation and Refresh must both use the shared preflight, and only the
# engine-assigned {_index} variable may be deferred until the write stage.
seedance_source = (ROOT / "HMBSeedanceGeneration.py").read_text(
    encoding="utf-8"
)
seedance_tree = ast.parse(seedance_source, filename="HMBSeedanceGeneration.py")
seedance_class = next(
    node
    for node in seedance_tree.body
    if isinstance(node, ast.ClassDef)
    and node.name == "HMBSeedanceGeneration"
)
legacy_seedance_class = next(
    node
    for node in seedance_tree.body
    if isinstance(node, ast.ClassDef)
    and node.name == "HMBSeedance20VideoGeneration"
)
assert len(legacy_seedance_class.bases) == 1
assert isinstance(legacy_seedance_class.bases[0], ast.Name)
assert legacy_seedance_class.bases[0].id == "HMBSeedanceGeneration"
assert not any(
    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    for node in legacy_seedance_class.body
), "The saved-workflow compatibility wrapper must not override behavior."
seedance_methods = {
    node.name: node
    for node in seedance_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
preflight_method = seedance_methods["_preflight_output_destination"]
preflight_source = ast.get_source_segment(seedance_source, preflight_method) or ""
assert 'marker = "missing required variables:"' in preflight_source
assert 'if missing != {"_index"}:' in preflight_source
assert sum(
    isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "resolve"
    for node in ast.walk(preflight_method)
) == 1
for execution_method_name in ("_refresh_async", "_process_generation_impl"):
    execution_method = seedance_methods[execution_method_name]
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_preflight_output_destination"
        for node in ast.walk(execution_method)
    ) == 1
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
        for node in ast.walk(execution_method)
    )

# Keep the API SERVER durable-job contract enforced on public CI without
# importing the host-only griptape_nodes runtime.
assert "CGTeamwork" not in seedance_source
module_functions = {
    node.name: node
    for node in seedance_tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
module_assignments = {
    node.targets[0].id: node.value
    for node in seedance_tree.body
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    )
}

# Public CI cannot import the Griptape-hosted generator, so keep the Broker
# transport boundary enforceable from its AST. Broker traffic must bypass
# machine proxy discovery locally; no global opener or environment mutation is
# permitted, and non-Broker internet clients remain untouched.
opener_factory = module_functions["_broker_build_opener"]
opener_factory_source = (
    ast.get_source_segment(seedance_source, opener_factory) or ""
)
assert "os.environ" not in opener_factory_source
assert "getproxies" not in opener_factory_source
build_opener_calls = [
    node
    for node in ast.walk(seedance_tree)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "build_opener"
    )
]
assert len(build_opener_calls) == 1
assert (
    opener_factory.lineno
    <= build_opener_calls[0].lineno
    <= opener_factory.end_lineno
)
proxy_handlers = [
    argument
    for argument in build_opener_calls[0].args
    if (
        isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Attribute)
        and argument.func.attr == "ProxyHandler"
    )
]
assert len(proxy_handlers) == 1
assert len(proxy_handlers[0].args) == 1
assert isinstance(proxy_handlers[0].args[0], ast.Dict)
assert proxy_handlers[0].args[0].keys == []
assert proxy_handlers[0].args[0].values == []
assert any(
    isinstance(argument, ast.Call)
    and isinstance(argument.func, ast.Name)
    and argument.func.id == "_BrokerNoRedirectHandler"
    for argument in build_opener_calls[0].args
)
assert not any(
    isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "install_opener"
    for node in ast.walk(seedance_tree)
)
factory_calls = [
    node
    for node in ast.walk(seedance_tree)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_broker_build_opener"
    )
]
assert len(factory_calls) == 2

assert ast.literal_eval(
    module_assignments["AI_BROKER_DEVICE_START_BACKOFF_SECONDS"]
) == (0.0, 0.5, 1.5)
assert ast.literal_eval(
    module_assignments[
        "AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS"
    ]
) == 3

device_login_source = (
    ast.get_source_segment(seedance_source, module_functions["_broker_device_login"])
    or ""
)
for endpoint in ('"/api/device/start"', '"/api/device/token"'):
    assert endpoint in device_login_source
assert device_login_source.count('server_url + "/api/device/start"') == 1
assert device_login_source.count("webbrowser.open(") == 1
assert device_login_source.count("_broker_build_opener()") == 1
assert "AI_BROKER_DEVICE_START_BACKOFF_SECONDS" in device_login_source
assert "AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS" in (
    device_login_source
)
assert 'stage="device_start"' in device_login_source
assert 'stage="device_token_poll"' in device_login_source
assert "consecutive_transport_errors = 0" in device_login_source
assert "data=token_payload" in device_login_source
assert "_broker_clear_token" not in device_login_source
assert "_broker_same_origin(verification_url, server_url)" in device_login_source
assert "_broker_save_token(access_token)" in device_login_source

start_retry_loop = next(
    node
    for node in module_functions["_broker_device_login"].body
    if isinstance(node, ast.For)
    and "AI_BROKER_DEVICE_START_BACKOFF_SECONDS"
    in (ast.get_source_segment(seedance_source, node) or "")
)
assert any(isinstance(node, ast.Break) for node in ast.walk(start_retry_loop))
browser_open_call = next(
    node
    for node in ast.walk(module_functions["_broker_device_login"])
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "open"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "webbrowser"
    )
)
assert browser_open_call.lineno > start_retry_loop.end_lineno
token_poll_loop = next(
    node
    for node in module_functions["_broker_device_login"].body
    if isinstance(node, ast.While)
)
assert browser_open_call.lineno < token_poll_loop.lineno

token_path_source = (
    ast.get_source_segment(seedance_source, module_functions["_broker_token_path"])
    or ""
)
assert '"FNAIBroker"' in token_path_source
assert '"access_token_v2.dpapi"' in token_path_source

transport_log_source = (
    ast.get_source_segment(
        seedance_source, module_functions["_broker_log_transport_error"]
    )
    or ""
)
for safe_field in (
    "stage=%s",
    "attempt=%d",
    "exception=%s",
    "reason=%s",
    "errno=%s",
    "winerror=%s",
    "host=%s",
    "port=%d",
):
    assert safe_field in transport_log_source
for forbidden_log_value in (
    "Authorization",
    "access_token",
    "device_secret",
    "response_body",
    "proxy_password",
):
    assert forbidden_log_value not in transport_log_source
assert "type(exc).__name__" in transport_log_source
assert "type(reason).__name__" in transport_log_source

broker_class = next(
    node
    for node in seedance_tree.body
    if isinstance(node, ast.ClassDef) and node.name == "_HMBAIBrokerBridge"
)
broker_methods = {
    node.name: node
    for node in broker_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
broker_init_source = (
    ast.get_source_segment(seedance_source, broker_methods["__init__"]) or ""
)
assert broker_init_source.count("_broker_build_opener()") == 1
request_source = ast.get_source_segment(
    seedance_source, broker_methods["_request_json"]
) or ""
assert 'headers["Idempotency-Key"] = idempotency_key' in request_source
assert "exc.code == 410 and not submission" in request_source
assert "BROKER_EXPIRED_STATUSES" in request_source
account_source = ast.get_source_segment(
    seedance_source, broker_methods["account_snapshot"]
) or ""
assert '"GET", "/api/me"' in account_source
assert account_source.index('"GET", "/api/me"') < account_source.index(
    "_broker_device_login()"
)
assert request_source.count("_broker_clear_token()") == 1
assert "if exc.code == 401:" in request_source
transport_handler_source = next(
    ast.get_source_segment(seedance_source, handler) or ""
    for node in ast.walk(broker_methods["_request_json"])
    if isinstance(node, ast.Try)
    for handler in node.handlers
    if "TimeoutError" in (ast.get_source_segment(seedance_source, handler) or "")
)
assert "_broker_clear_token" not in transport_handler_source
generate_source = ast.get_source_segment(
    seedance_source, broker_methods["generate_seedance"]
) or ""
assert '"/api/v1/generate/video"' in generate_source
assert "idempotency_key=client_request_id" in generate_source
assert generate_source.count("self._request_json(") == 1
assert "_broker_device_login" not in generate_source
refresh_job_source = ast.get_source_segment(
    seedance_source, broker_methods["refresh_job"]
) or ""
assert '"/api/v1/jobs/"' in refresh_job_source

process_source = ast.get_source_segment(
    seedance_source, seedance_methods["_process_generation_impl"]
) or ""
assert "_ensure_broker_connected" in process_source
assert "_get_api_key" not in process_source
assert 'payload["client_request_id"] = client_request_id' in process_source
refresh_source = ast.get_source_segment(
    seedance_source, seedance_methods["_refresh_async"]
) or ""
for recovery_marker in (
    "retry_same_request",
    'retry_payload.get("client_request_id") == generation_id',
    "bridge.generate_seedance",
):
    assert recovery_marker in refresh_source
download_source = ast.get_source_segment(
    seedance_source, seedance_methods["_download_broker_video"]
) or ""
assert "bridge.is_trusted_broker_url(url)" in download_source
assert "bridge.download_trusted_result" in download_source
assert "return await self._download_video(url)" in download_source

source_policy_path = ROOT / Path(POLICY_RELATIVE)
source_policy = source_policy_path.read_bytes()
assert digest(source_policy) == POLICY_SHA256
assert common._AGENT_POLICY_VERSION == POLICY_VERSION
assert common._AGENT_POLICY_CONTRACT_SHA256 == POLICY_CONTRACT_SHA256
assert common._AGENT_POLICY_SIGNING_KEY_ID == POLICY_SIGNING_KEY_ID
assert Path(common._BUNDLED_AGENT_POLICY_FILE).resolve() == source_policy_path.resolve()
assert common._read_agent_policy_envelope() == source_policy
source_payload = common._decode_signed_agent_policy_envelope(source_policy)
common._validate_agent_policy_payload(source_payload)
assert source_payload["final_policy_version"] == POLICY_VERSION
assert source_payload["final_motion_look_policy_sha256"] == POLICY_CONTRACT_SHA256

configured_secret_values = tuple(
    value.encode("utf-8")
    for name in EXPECTED_SECRET_NAMES
    if len(value := os.environ.get(name, "")) >= 8
)
source_policy_path_bytes = str(source_policy_path.resolve()).encode("utf-8")

# A clean checkout has no generated dist directory. Validate the immutable
# source boundary in that mode, and additionally validate every release output
# whenever a complete local build is present.
release_outputs = (RELEASE_MANIFEST, RELEASE_ARCHIVE, RELEASE_CHECKSUMS)
output_presence = tuple(path.is_file() for path in release_outputs)
assert not any(output_presence) or all(output_presence), (
    "Release outputs must be either absent or present as a complete set."
)
archive_verified = False
if all(output_presence):
    release_manifest_bytes = RELEASE_MANIFEST.read_bytes()
    release_manifest = json.loads(release_manifest_bytes.decode("utf-8"))
    agent_policy = release_manifest["agent_policy"]
    assert agent_policy == {
        "bundled": True,
        "bundled_path": POLICY_RELATIVE,
        "contract_sha256": POLICY_CONTRACT_SHA256,
        "envelope_schema": "hmb-agent-policy-envelope-v3",
        "envelope_sha256": POLICY_SHA256,
        "maximum_decompressed_bytes": 512 * 1024,
        "maximum_envelope_bytes": 128 * 1024,
        "policy_version": POLICY_VERSION,
        "resolution_order": ["bundled"],
        "signature_algorithm": "RSASSA-PKCS1-v1_5-SHA256",
        "signing_key_id": POLICY_SIGNING_KEY_ID,
        "validated": True,
    }
    assert release_manifest["release_version"] == "0.5.31"
    assert release_manifest["policy_version"] == POLICY_VERSION
    assert release_manifest["contract_sha256"] == POLICY_CONTRACT_SHA256
    source_files = {
        str(item["path"]): item for item in release_manifest["source_files"]
    }
    assert len(source_files) == 25
    assert source_files[POLICY_RELATIVE]["sha256"] == POLICY_SHA256
    assert "CHANGELOG.md" not in source_files
    assert "resources/build_release.py" not in source_files
    assert not any(
        PurePosixPath(path).name.casefold() == "build_release.py"
        for path in source_files
    )
    assert source_policy_path_bytes not in release_manifest_bytes

    archive_names = [str(item["name"]) for item in release_manifest["archives"]]
    assert archive_names == [RELEASE_ARCHIVE.name]
    with zipfile.ZipFile(RELEASE_ARCHIVE, "r") as archive:
        infos = archive.infolist()
        assert len(infos) == 25
        assert not archive.testzip()
        expected_policy_member = f"HMB_GP_Production/{POLICY_RELATIVE}"
        dat_members = [
            info.filename
            for info in infos
            if PurePosixPath(info.filename).suffix.casefold() == ".dat"
        ]
        assert dat_members == [expected_policy_member]
        assert "HMB_GP_Production/CHANGELOG.md" not in {
            info.filename for info in infos
        }
        assert not any(
            PurePosixPath(info.filename).name.casefold() == "build_release.py"
            for info in infos
        )
        for info in infos:
            member = PurePosixPath(info.filename)
            lowered = info.filename.casefold()
            assert member.suffix.casefold() not in FORBIDDEN_SUFFIXES
            if "/resources/agent/" in f"/{lowered}":
                assert info.filename == expected_policy_member
            assert not re.search(
                r"(^|/)(?:credentials|secrets)[^/]*\.json$",
                lowered,
            )
            assert not re.search(r"(^|/)(?:id_rsa|id_ed25519)[^/]*$", lowered)
            content = archive.read(info)
            assert PRIVATE_KEY_HEADER.search(content) is None
            assert not any(pattern.search(content) for pattern in COMMON_TOKEN_PATTERNS)
            assert not any(secret in content for secret in configured_secret_values)
            assert source_policy_path_bytes not in content
        archived_policy = archive.read(expected_policy_member)
        assert archived_policy == source_policy
        assert digest(archived_policy) == POLICY_SHA256
        archived_payload = common._decode_signed_agent_policy_envelope(
            archived_policy
        )
        common._validate_agent_policy_payload(archived_payload)
        assert archived_payload["final_policy_version"] == POLICY_VERSION
        assert (
            archived_payload["final_motion_look_policy_sha256"]
            == POLICY_CONTRACT_SHA256
        )

    checksum_records = {}
    for line in RELEASE_CHECKSUMS.read_text(encoding="utf-8").splitlines():
        expected_hash, filename = line.split("  ", 1)
        checksum_records[filename] = expected_hash
    assert set(checksum_records) == {
        RELEASE_ARCHIVE.name,
        RELEASE_MANIFEST.name,
    }
    for filename, expected_hash in checksum_records.items():
        assert digest((DIST / filename).read_bytes()) == expected_hash
    archive_verified = True

mode = "source and 25-file archive" if archive_verified else "source-only"
print(f"HMB bundled-policy release/credential boundary regression: PASS ({mode})")
