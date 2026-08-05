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
assert not (ROOT / "resources" / "agent" / "hmb_agent_core.dat").exists()

original_env = os.environ.pop(POLICY_ENV, None)
try:
    try:
        common._load_agent_rule_payload()
    except RuntimeError as exc:
        assert str(exc) == (
            "HMB_GP_Agent_Library internal rule payload could not be loaded."
        )
    else:
        raise AssertionError("Missing external policy configuration was accepted.")

    os.environ[POLICY_ENV] = "relative-policy.dat"
    try:
        common._resolve_agent_rule_data_path()
    except RuntimeError as exc:
        assert str(exc) == "external policy path is invalid"
    else:
        raise AssertionError("Relative external policy path was accepted.")
    os.environ.pop(POLICY_ENV)

    with tempfile.TemporaryDirectory() as temporary_directory:
        invalid_path = Path(temporary_directory) / "invalid-policy.dat"
        invalid_path.write_bytes(b"not-a-signed-policy")
        common.AGENT_RULE_DATA_PATH = invalid_path
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == (
                "HMB_GP_Agent_Library signed rule payload could not be verified."
            )
        else:
            raise AssertionError("Unsigned external policy data was accepted.")

        oversized_path = Path(temporary_directory) / "oversized-policy.dat"
        oversized_path.write_bytes(
            b"x" * (common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 1)
        )
        common.AGENT_RULE_DATA_PATH = oversized_path
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == (
                "HMB_GP_Agent_Library internal rule payload could not be loaded."
            )
        else:
            raise AssertionError("Oversized external policy data was accepted.")
finally:
    common.AGENT_RULE_DATA_PATH = None
    if original_env is not None:
        os.environ[POLICY_ENV] = original_env


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
    public_error, public_native_calls, public_outputs, public_cause = exercise_public_route(
        canonical_hmb_prompt=True
    )
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
finally:
    if route_env is not None:
        os.environ[POLICY_ENV] = route_env

common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
build_source = (ROOT / "resources" / "build_release.py").read_text(
    encoding="utf-8"
)
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
assert 'ROOT / "resources" / "agent" / "hmb_agent_core.dat"' not in common_source
assert '"resources/agent/hmb_agent_core.dat",' not in build_source
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
