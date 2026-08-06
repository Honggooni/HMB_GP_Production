from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
POLICY_ENV = "HMB_AGENT_POLICY_PATH"


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("_hmb_common")
agent = load("HMBAgentLibrary")
assert common.AGENT_RULE_DATA_PATH_ENV == POLICY_ENV
assert common.AGENT_RULE_DATA_PATH is None
bundled_policy_path = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
assert common._BUNDLED_AGENT_RULE_DATA_PATH == bundled_policy_path
assert bundled_policy_path.is_file()


def assert_v2_payload(payload: dict[str, object]) -> None:
    assert payload["final_policy_version"] == "2026-08-01.goal-final-authority.v2"
    assert payload["final_motion_look_policy_sha256"] == (
        "a17809e4103628c1b0ab0b96081f6325faf9d16703a5fac57ef7d1eaa7d043bf"
    )
    assert str(payload["policy"]).strip()
    assert str(payload["binding"]).strip()


original_reader = common._read_agent_policy_envelope
original_env = os.environ.pop(POLICY_ENV, None)
try:
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        read_calls: list[Path] = []

        def recording_reader(path: Path) -> bytes:
            read_calls.append(Path(path))
            return original_reader(path)

        common._read_agent_policy_envelope = recording_reader

        # No external configuration uses the exact bundled signed v2 policy.
        assert_v2_payload(common._load_agent_rule_payload())
        assert read_calls == [bundled_policy_path]

        # A valid external policy is preferred and the bundle is never opened.
        external_policy = temporary_root / "external-policy.dat"
        external_policy.write_bytes(bundled_policy_path.read_bytes())
        os.environ[POLICY_ENV] = str(external_policy)
        read_calls.clear()
        assert_v2_payload(common._load_agent_rule_payload())
        assert read_calls == [external_policy]

        # Missing external storage falls back to the bundled signed policy.
        missing_policy = temporary_root / "missing-policy.dat"
        os.environ[POLICY_ENV] = str(missing_policy)
        read_calls.clear()
        assert_v2_payload(common._load_agent_rule_payload())
        assert read_calls == [missing_policy, bundled_policy_path]

        # An unreadable external policy follows the same verified fallback.
        unreadable_policy = temporary_root / "unreadable-policy.dat"
        unreadable_policy.write_bytes(bundled_policy_path.read_bytes())

        def unreadable_external_reader(path: Path) -> bytes:
            candidate = Path(path)
            read_calls.append(candidate)
            if candidate == unreadable_policy:
                raise PermissionError("simulated external policy denial")
            return original_reader(candidate)

        common._read_agent_policy_envelope = unreadable_external_reader
        os.environ[POLICY_ENV] = str(unreadable_policy)
        read_calls.clear()
        assert_v2_payload(common._load_agent_rule_payload())
        assert read_calls == [unreadable_policy, bundled_policy_path]

        # Relative production configuration is rejected, then the bundle is used.
        common._read_agent_policy_envelope = recording_reader
        os.environ[POLICY_ENV] = "relative-policy.dat"
        try:
            common._resolve_agent_rule_data_path()
        except RuntimeError as exc:
            assert str(exc) == "external policy path is invalid"
        else:
            raise AssertionError("Relative external policy path was accepted.")
        read_calls.clear()
        assert_v2_payload(common._load_agent_rule_payload())
        assert read_calls == [bundled_policy_path]

        # Invalid external bytes cannot be injected and instead select the bundle.
        invalid_path = Path(temporary_directory) / "invalid-policy.dat"
        invalid_path.write_bytes(b"not-a-signed-policy")
        os.environ[POLICY_ENV] = str(invalid_path)
        read_calls.clear()
        assert_v2_payload(common._load_agent_rule_payload())
        assert read_calls == [invalid_path, bundled_policy_path]

        # The explicit test override is strict: invalid data must not be hidden by
        # the production bundle fallback.
        common.AGENT_RULE_DATA_PATH = invalid_path
        os.environ.pop(POLICY_ENV, None)
        read_calls.clear()
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == (
                "HMB_GP_Agent_Library signed rule payload could not be verified."
            )
        else:
            raise AssertionError("Unsigned external policy data was accepted.")
        assert read_calls == [invalid_path]

        oversized_path = Path(temporary_directory) / "oversized-policy.dat"
        oversized_path.write_bytes(
            b"x" * (common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 1)
        )
        common.AGENT_RULE_DATA_PATH = oversized_path
        read_calls.clear()
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == (
                "HMB_GP_Agent_Library internal rule payload could not be loaded."
            )
        else:
            raise AssertionError("Oversized external policy data was accepted.")
        assert read_calls == [oversized_path]

        # If neither production source can be read, expose only the existing
        # generalized load failure while preserving the attempted access order.
        common.AGENT_RULE_DATA_PATH = None
        unavailable_external = temporary_root / "unavailable-policy.dat"
        os.environ[POLICY_ENV] = str(unavailable_external)

        def unavailable_reader(path: Path) -> bytes:
            read_calls.append(Path(path))
            raise PermissionError("simulated policy storage outage")

        common._read_agent_policy_envelope = unavailable_reader
        read_calls.clear()
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == (
                "HMB_GP_Agent_Library internal rule payload could not be loaded."
            )
        else:
            raise AssertionError("Unavailable external and bundled policies were accepted.")
        assert read_calls == [unavailable_external, bundled_policy_path]
finally:
    common.AGENT_RULE_DATA_PATH = None
    common._read_agent_policy_envelope = original_reader
    if original_env is not None:
        os.environ[POLICY_ENV] = original_env
    else:
        os.environ.pop(POLICY_ENV, None)


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


route_env = os.environ.pop(POLICY_ENV, None)
try:
    # A canonical HMB route now remains usable without workstation-specific
    # configuration because it verifies the bundled v2 policy.
    bundled_result, bundled_native_calls, _bundled_outputs, bundled_cause = exercise_public_route(
        canonical_hmb_prompt=True
    )
    assert bundled_result == "native-complete"
    assert bundled_native_calls == 1
    assert bundled_cause is None

    # An explicit invalid override remains fail-closed and cannot silently use
    # the bundled policy.
    with tempfile.TemporaryDirectory() as temporary_directory:
        invalid_override = Path(temporary_directory) / "invalid-override.dat"
        invalid_override.write_bytes(b"not-a-signed-policy")
        common.AGENT_RULE_DATA_PATH = invalid_override
        agent._hmb.AGENT_RULE_DATA_PATH = invalid_override
        public_error, public_native_calls, public_outputs, public_cause = (
            exercise_public_route(canonical_hmb_prompt=True)
        )
        assert public_error == agent._HMB_POLICY_UNAVAILABLE_MESSAGE
        assert public_native_calls == 0
        assert public_outputs == {
            "agent": {},
            "output": agent._HMB_POLICY_UNAVAILABLE_MESSAGE,
        }
        assert public_cause is None
    common.AGENT_RULE_DATA_PATH = None
    agent._hmb.AGENT_RULE_DATA_PATH = None

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
finally:
    common.AGENT_RULE_DATA_PATH = None
    agent._hmb.AGENT_RULE_DATA_PATH = None
    if route_env is not None:
        os.environ[POLICY_ENV] = route_env
    else:
        os.environ.pop(POLICY_ENV, None)

common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
assert "_BUNDLED_AGENT_RULE_DATA_PATH" in common_source
assert 'ROOT / "resources" / "agent" / "hmb_agent_core.dat"' in common_source
assert ".read_bytes()" not in common_source[
    common_source.index("def _load_agent_rule_payload"):
    common_source.index("def get_internal_policy_rules")
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
    "ARK_API_KEY": "",
    "GT_CLOUD_API_KEY": "",
    "GT_CLOUD_BUCKET_ID": "",
    "TOS_ACCESS_KEY_ID": "",
    "TOS_SECRET_ACCESS_KEY": "",
    "TOS_BUCKET_NAME": "",
}

print("HMB external Agent policy boundary regression: PASS")
