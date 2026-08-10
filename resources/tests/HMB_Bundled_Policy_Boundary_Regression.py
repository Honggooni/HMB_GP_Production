from __future__ import annotations

import base64
import io
import importlib.util
import json
import sys
from pathlib import Path
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_POLICY_VERSION = "2026-08-11.agent-shot-quality.v4"
EXPECTED_POLICY_CONTRACT = (
    "b9f6a430737ad266022d1b53da99b1afb7defbc0348f88a59ebf6da5b7e1dec5"
)
EXPECTED_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"
LOAD_FAILURE = "HMB_GP_Agent_Library internal rule payload could not be loaded."


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("_hmb_common")
agent = load("HMBAgentLibrary")
bundled_policy_path = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
assert common._BUNDLED_AGENT_POLICY_FILE == bundled_policy_path
assert bundled_policy_path.is_file()
assert not hasattr(common, "_resolve_agent_rule_data_path")
assert not hasattr(common, "_load_agent_rule_payload_from_path")


def assert_current_payload(payload: dict[str, object]) -> None:
    assert payload["final_policy_version"] == EXPECTED_POLICY_VERSION
    assert payload["final_motion_look_policy_sha256"] == EXPECTED_POLICY_CONTRACT
    assert str(payload["policy"]).strip()
    assert str(payload["binding"]).strip()


original_path_open = Path.open
read_calls: list[Path] = []


def recording_open(path: Path, *args, **kwargs):
    read_calls.append(Path(path))
    return original_path_open(path, *args, **kwargs)


Path.open = recording_open
try:
    assert_current_payload(common._load_agent_rule_payload())
finally:
    Path.open = original_path_open

# The loader opens exactly one library-local signed file and exposes no path
# argument or runtime override surface.
assert read_calls == [bundled_policy_path]


with bundled_policy_path.open("rb") as stream:
    bundled_policy_bytes = stream.read(common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 1)
assert bundled_policy_bytes
assert len(bundled_policy_bytes) <= common._AGENT_POLICY_MAX_ENVELOPE_BYTES
signed_envelope = json.loads(bundled_policy_bytes.decode("utf-8"))
assert signed_envelope["schema"] == "hmb-agent-policy-envelope-v3"
assert signed_envelope["key_id"] == EXPECTED_SIGNING_KEY_ID

wrong_signature_envelope = dict(signed_envelope)
wrong_signature = bytearray(base64.b64decode(wrong_signature_envelope["signature"]))
wrong_signature[-1] ^= 1
wrong_signature_envelope["signature"] = base64.b64encode(wrong_signature).decode(
    "ascii"
)
wrong_signature_bytes = json.dumps(
    wrong_signature_envelope,
    ensure_ascii=False,
    separators=(",", ":"),
).encode("utf-8")


def assert_bundle_failure(
    label: str,
    *,
    encoded: bytes | None = None,
    open_error: BaseException | None = None,
) -> None:
    original_path_open = Path.open
    open_calls: list[Path] = []
    read_sizes: list[int] = []

    class ObservedStream(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return super().read(size)

    def fixture_open(path: Path, *args, **kwargs):
        open_calls.append(Path(path))
        if open_error is not None:
            raise open_error
        assert encoded is not None
        return ObservedStream(encoded)

    Path.open = fixture_open
    try:
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == LOAD_FAILURE
            assert exc.__cause__ is not None
        else:
            raise AssertionError(f"{label} bundled policy was accepted.")
    finally:
        Path.open = original_path_open

    assert open_calls == [bundled_policy_path]
    if encoded is None:
        assert read_sizes == []
    else:
        assert read_sizes == [common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 1]


assert_bundle_failure(
    "missing",
    open_error=FileNotFoundError("simulated missing bundled policy"),
)
assert_bundle_failure("corrupt", encoded=b"not-a-signed-policy")
assert_bundle_failure(
    "oversized",
    encoded=b"x" * (common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 2),
)
assert_bundle_failure("wrong-signature", encoded=wrong_signature_bytes)


def exercise_public_route(
    *,
    canonical_hmb_prompt: bool,
    topology_failure: bool = False,
) -> tuple[str, int, dict[str, object], BaseException | None]:
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = False
    node._hmb_structured_rules_active = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_goal_first_rules = []
    node._hmb_native_calls_this_process = 0
    node.parameter_output_values = {"agent": {"stale": True}, "output": "stale"}
    native_calls: list[bool] = []

    def native_once(self):
        native_calls.append(True)
        if False:
            yield None
        return "native-complete"

    node._run_native_agent_once = MethodType(native_once, node)

    def topology(_self):
        if topology_failure:
            raise RuntimeError("private topology detail")
        return canonical_hmb_prompt

    node._has_canonical_hmb_prompt_connection = MethodType(topology, node)
    iterator = node.process()
    try:
        while True:
            next(iterator)
    except RuntimeError as exc:
        return (
            str(exc),
            len(native_calls),
            dict(node.parameter_output_values),
            exc.__cause__,
        )
    except StopIteration as stop:
        return (
            str(stop.value),
            len(native_calls),
            dict(node.parameter_output_values),
            None,
        )


def assert_public_routes() -> None:
    # A canonical HMB route verifies the library-local v4 policy.
    bundled_result, bundled_native_calls, _bundled_outputs, bundled_cause = (
        exercise_public_route(canonical_hmb_prompt=True)
    )
    assert bundled_result == "native-complete"
    assert bundled_native_calls == 1
    assert bundled_cause is None

    # A missing local bundle stops the HMB route before the native Agent runs.
    original_agent_reader = agent._hmb._read_agent_policy_envelope

    def unavailable_bundle_reader() -> bytes:
        raise FileNotFoundError("simulated missing bundled policy")

    agent._hmb._read_agent_policy_envelope = unavailable_bundle_reader
    try:
        public_error, public_native_calls, public_outputs, public_cause = (
            exercise_public_route(canonical_hmb_prompt=True)
        )
    finally:
        agent._hmb._read_agent_policy_envelope = original_agent_reader
    assert public_error == agent._HMB_POLICY_UNAVAILABLE_MESSAGE
    assert public_native_calls == 0
    assert public_outputs == {
        "agent": {},
        "output": agent._HMB_POLICY_UNAVAILABLE_MESSAGE,
    }
    assert public_cause is None

    topology_error, topology_native_calls, topology_outputs, topology_cause = (
        exercise_public_route(
            canonical_hmb_prompt=False,
            topology_failure=True,
        )
    )
    assert topology_error == agent._HMB_TOPOLOGY_UNAVAILABLE_MESSAGE
    assert topology_native_calls == 0
    assert topology_outputs == {
        "agent": {},
        "output": agent._HMB_TOPOLOGY_UNAVAILABLE_MESSAGE,
    }
    assert topology_cause is None

    native_result, native_calls, _native_outputs, _native_cause = (
        exercise_public_route(canonical_hmb_prompt=False)
    )
    assert native_result == "native-complete"
    assert native_calls == 1


assert_public_routes()


common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
assert "_BUNDLED_AGENT_POLICY_FILE" in common_source
assert 'ROOT / "resources" / "agent" / "hmb_agent_core.dat"' in common_source
for forbidden in (
    "_resolve_agent_rule_data_path",
    "_load_agent_rule_payload_from_path",
):
    assert forbidden not in common_source
read_start = common_source.index("def _read_agent_policy_envelope")
read_end = common_source.index("def _decode_signed_agent_policy_envelope")
read_source = common_source[read_start:read_end]
assert "_BUNDLED_AGENT_POLICY_FILE.open(\"rb\")" in read_source
assert "read(_AGENT_POLICY_MAX_ENVELOPE_BYTES + 1)" in read_source
assert ".read_bytes()" not in common_source[
    read_start : common_source.index("def get_internal_policy_rules")
]
assert "zlib.decompress(" not in common_source
assert "continuing with the native Agent" not in agent_source
assert "_HMB_POLICY_UNAVAILABLE_MESSAGE" in agent_source
assert "raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE)" in agent_source

manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert registered_secrets == {
    "GT_CLOUD_API_KEY": "",
    "GT_CLOUD_BUCKET_ID": "",
    "TOS_ACCESS_KEY_ID": "",
    "TOS_SECRET_ACCESS_KEY": "",
    "TOS_BUCKET_NAME": "",
}

print("HMB local bundled Agent policy boundary regression: PASS")
