from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
POLICY_ENV = "HMB_AGENT_POLICY_PATH"
EXPECTED_BUNDLED_POLICY = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
EXPECTED_VERSION = "2026-08-12.agent-shot-quality.v4.2"
EXPECTED_ENVELOPE_SHA256 = (
    "7171bef7169df8894ed24ae7a9b4d9d145957c5110c963b7435372b2695fd251"
)
EXPECTED_PROJECT_SHA256 = (
    "ee06fac0bc8825e29c3c49b755de3770bbe6241f7b4a7c41eba22f97f41c72c2"
)
EXPECTED_BINDING_SHA256 = (
    "5cba8f59f6332c4ff881b27991bc724ff8dbba470bd59046ac2b96b6dbe66e64"
)
EXPECTED_CONTRACT_SHA256 = (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
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

assert not hasattr(common, "AGENT_RULE_DATA_PATH_ENV")
assert common._BUNDLED_AGENT_POLICY_FILE == EXPECTED_BUNDLED_POLICY
assert EXPECTED_BUNDLED_POLICY.is_file()
assert not hasattr(common, "_resolve_agent_rule_data_path")
assert common._AGENT_POLICY_VERSION == EXPECTED_VERSION
assert common._AGENT_POLICY_CONTRACT_SHA256 == EXPECTED_CONTRACT_SHA256
assert not hasattr(common, "_AGENT_POLICY_ENVELOPE_SHA256")
assert not hasattr(common, "_AGENT_POLICY_PROJECT_SHA256")
assert not hasattr(common, "_AGENT_POLICY_BINDING_SHA256")


original_env = os.environ.get(POLICY_ENV)
try:
    # Machine/process environment cannot redirect the fixed bundled loader.
    for hostile_path in (
        "",
        r"D:\agent\hmb_agent_core.dat",
        r"Z:\hmb_agent_core.dat",
        r"\\FIN-RCOMP7\D$\agent\hmb_agent_core.dat",
        r"\\FIN-RCOMP1\HMB_AgentPolicy$\hmb_agent_core.dat",
        r"\\192.168.203.245\HMB_AgentPolicy$\hmb_agent_core.dat",
        r"\\?\UNC\FIN-RCOMP7\HMB_AgentPolicy$\hmb_agent_core.dat",
        r"\\.\UNC\FIN-RCOMP7\HMB_AgentPolicy$\hmb_agent_core.dat",
    ):
        os.environ[POLICY_ENV] = hostile_path
        assert common._BUNDLED_AGENT_POLICY_FILE == EXPECTED_BUNDLED_POLICY
    os.environ.pop(POLICY_ENV, None)
    assert common._BUNDLED_AGENT_POLICY_FILE == EXPECTED_BUNDLED_POLICY

    original_path_open = Path.open
    synthetic_bytes = b'{"bundled_reader_fixture":true}'
    signed_bytes = synthetic_bytes

    # Exercise bounded, fresh bundled reads with inert changing bytes. Trust is
    # decided after each read by signature,
    # schema, self-hashes, 4+4 shape, and the stable contract rather than a
    # package-pinned whole-file digest.
    with tempfile.TemporaryDirectory() as temporary_directory:
        synthetic_fixture = Path(temporary_directory) / "reader-fixture.bin"
        synthetic_fixture.write_bytes(synthetic_bytes)
        bundle_open_calls: list[str] = []

        def synthetic_fixture_open(path: Path, *args, **kwargs):
            bundle_open_calls.append(str(path))
            assert Path(path) == EXPECTED_BUNDLED_POLICY
            return original_path_open(synthetic_fixture, *args, **kwargs)

        Path.open = synthetic_fixture_open
        try:
            assert common._read_agent_policy_envelope() == synthetic_bytes
            with original_path_open(synthetic_fixture, "wb") as stream:
                stream.write(synthetic_bytes + b"\n")
            assert common._read_agent_policy_envelope() == synthetic_bytes + b"\n"
        finally:
            Path.open = original_path_open

        # No process-global payload cache: every protected execution takes a
        # fresh bundled snapshot.
        assert bundle_open_calls == [
            str(EXPECTED_BUNDLED_POLICY),
            str(EXPECTED_BUNDLED_POLICY),
        ]

    # Verify the shipped v4.2 RSA signature and signed 4+4 self-hashes.
    signed_bytes = EXPECTED_BUNDLED_POLICY.read_bytes()
    assert hashlib.sha256(signed_bytes).hexdigest() == EXPECTED_ENVELOPE_SHA256
    payload = common._load_agent_rule_payload()
    assert payload["final_policy_version"] == EXPECTED_VERSION
    assert payload["final_motion_look_policy_sha256"] == EXPECTED_CONTRACT_SHA256
    assert payload["envelope_sha256"] == EXPECTED_ENVELOPE_SHA256
    assert hashlib.sha256(str(payload["policy"]).encode("utf-8")).hexdigest() == (
        EXPECTED_PROJECT_SHA256
    )
    assert hashlib.sha256(str(payload["binding"]).encode("utf-8")).hexdigest() == (
        EXPECTED_BINDING_SHA256
    )

    def assert_open_failure(error: BaseException) -> None:
        def failing_open(_path: Path, *_args, **_kwargs):
            raise error

        Path.open = failing_open
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == LOAD_FAILURE
        else:
            raise AssertionError(f"bundled read failure was accepted: {error!r}")
        finally:
            Path.open = original_path_open

    for simulated_error in (
        FileNotFoundError("simulated missing bundled policy"),
        PermissionError("simulated bundled policy read denial"),
        OSError(5, "simulated bundled policy I/O failure"),
    ):
        assert_open_failure(simulated_error)

    def assert_file_bytes_rejected(label: str, data: bytes) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory) / "fixture.bin"
            fixture.write_bytes(data)

            def fixture_open(_path: Path, *args, **kwargs):
                return original_path_open(fixture, *args, **kwargs)

            Path.open = fixture_open
            try:
                common._load_agent_rule_payload()
            except RuntimeError as exc:
                assert str(exc) == LOAD_FAILURE
            else:
                raise AssertionError(f"{label} bundled policy was accepted")
            finally:
                Path.open = original_path_open

    assert_file_bytes_rejected("empty", b"")
    assert_file_bytes_rejected(
        "oversized",
        b"x" * (common._AGENT_POLICY_MAX_ENVELOPE_BYTES + 1),
    )
    tampered = bytearray(signed_bytes)
    tampered[len(tampered) // 2] ^= 1
    assert_file_bytes_rejected("tampered signed envelope", bytes(tampered))

    # Simulate a namespace/content race by returning a different file identity
    # for the post-read fstat. The loader must reject before decode/injection.
    with tempfile.TemporaryDirectory() as temporary_directory:
        first_file = Path(temporary_directory) / "first.bin"
        second_file = Path(temporary_directory) / "second.bin"
        first_file.write_bytes(signed_bytes)
        second_file.write_bytes(signed_bytes)

        class RacingStream:
            def __init__(self) -> None:
                self._first = original_path_open(first_file, "rb")
                self._second = original_path_open(second_file, "rb")
                self._fileno_calls = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self._first.close()
                self._second.close()

            def fileno(self) -> int:
                self._fileno_calls += 1
                return (
                    self._first.fileno()
                    if self._fileno_calls == 1
                    else self._second.fileno()
                )

            def read(self, size: int = -1) -> bytes:
                return self._first.read(size)

        Path.open = lambda _path, *_args, **_kwargs: RacingStream()
        try:
            common._load_agent_rule_payload()
        except RuntimeError as exc:
            assert str(exc) == LOAD_FAILURE
        else:
            raise AssertionError("bundled policy identity race was accepted")
        finally:
            Path.open = original_path_open

    canonical_empty_prompt = "\n".join(
        (
            "HMB_GP_Production",
            agent._PUBLIC_JOB_CONTRACT_HEADER,
            json.dumps(
                {
                    "schema": agent._PUBLIC_JOB_CONTRACT_SCHEMA,
                    "version": agent._PUBLIC_JOB_CONTRACT_VERSION,
                    "images": [],
                    "videos": [],
                    "control_only_bindings": [],
                    "frame_ranges": [],
                    "connections": {"image_asset": False, "picker": False},
                },
                separators=(",", ":"),
            ),
            agent._FX_TIMING_CONTRACT_HEADER,
            json.dumps(
                {
                    "schema": agent._FX_TIMING_CONTRACT_SCHEMA,
                    "version": agent._FX_TIMING_CONTRACT_VERSION,
                    "valid": True,
                    "errors": [],
                    "sources": [],
                },
                separators=(",", ":"),
            ),
            agent._USER_DESCRIPTION_DATA_HEADER,
            "{}",
        )
    )

    def exercise_route(*, canonical: bool, bundle_failure: bool) -> tuple[str, int, dict]:
        node = object.__new__(agent.HMBAgentLibrary)
        node._hmb_rules_active = False
        node._hmb_policy = ""
        node._hmb_binding = ""
        node._hmb_policy_rules = []
        node._hmb_binding_rules = []
        node._hmb_ruleset_names = ("", "")
        node._hmb_native_calls_this_process = 0
        node.parameter_output_values = {"agent": {"stale": True}, "output": "stale"}
        native_calls: list[bool] = []

        def get_parameter_value(_self, name: str):
            assert name == "prompt"
            return canonical_empty_prompt

        def native_once(_self):
            native_calls.append(True)
            if False:
                yield None
            return "native-complete"

        node.get_parameter_value = MethodType(get_parameter_value, node)
        node._run_native_agent_once = MethodType(native_once, node)
        node._has_canonical_hmb_prompt_connection = MethodType(
            lambda _self: canonical,
            node,
        )

        original_identity_reader = agent._prompt_policy_source_identity
        original_envelope_reader = agent._hmb._read_agent_policy_envelope
        agent._prompt_policy_source_identity = lambda _source_path=None: (
            EXPECTED_VERSION,
            EXPECTED_CONTRACT_SHA256,
        )
        if bundle_failure:
            agent._hmb._read_agent_policy_envelope = lambda: (_ for _ in ()).throw(
                FileNotFoundError("private bundled policy detail")
            )
        else:
            agent._hmb._read_agent_policy_envelope = lambda: (_ for _ in ()).throw(
                AssertionError("plain Agent read the bundled HMB policy")
            )
        try:
            iterator = node.process()
            while True:
                next(iterator)
        except RuntimeError as exc:
            return str(exc), len(native_calls), dict(node.parameter_output_values)
        except StopIteration as stop:
            return str(stop.value), len(native_calls), dict(node.parameter_output_values)
        finally:
            agent._prompt_policy_source_identity = original_identity_reader
            agent._hmb._read_agent_policy_envelope = original_envelope_reader

    public_error, native_calls, public_outputs = exercise_route(
        canonical=True,
        bundle_failure=True,
    )
    assert public_error == agent._HMB_POLICY_UNAVAILABLE_MESSAGE
    assert native_calls == 0
    assert public_outputs == {
        "agent": {},
        "output": agent._HMB_POLICY_UNAVAILABLE_MESSAGE,
    }

    native_result, native_calls, _native_outputs = exercise_route(
        canonical=False,
        bundle_failure=False,
    )
    assert native_result == "native-complete"
    assert native_calls == 1
finally:
    if original_env is None:
        os.environ.pop(POLICY_ENV, None)
    else:
        os.environ[POLICY_ENV] = original_env


common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
assert "_BUNDLED_AGENT_POLICY_FILE" in common_source
assert 'ROOT / "resources" / "agent" / "hmb_agent_core.dat"' in common_source
assert "_resolve_agent_rule_data_path" not in common_source
assert r"\\FIN-RCOMP7\D$\agent" not in common_source
assert "192.168.203.245" not in common_source
assert "FIN-RCOMP7.funnyflux.local" not in common_source
assert "HMB_AgentPolicy$" not in common_source
assert POLICY_ENV not in common_source
assert re.search(r"(?m)^AGENT_RULE_DATA_PATH\s*=", common_source) is None
assert "lru_cache" not in common_source
assert "_AGENT_POLICY_ENVELOPE_SHA256" not in common_source
assert "_AGENT_POLICY_PROJECT_SHA256" not in common_source
assert "_AGENT_POLICY_BINDING_SHA256" not in common_source
assert "HMB LOCAL POLICY REQUIRED" not in agent_source
assert "_BUNDLED_AGENT_POLICY_FILE" not in agent_source
assert "resources/agent/hmb_agent_core.dat" not in agent_source

print("HMB fixed bundled Agent policy boundary regression: PASS")
