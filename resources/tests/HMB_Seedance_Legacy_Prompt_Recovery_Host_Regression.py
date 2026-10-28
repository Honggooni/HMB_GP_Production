"""Inert preservation of legacy prompt on a managed Seedance input.

Runs with the installed SDK in a temporary engine. It never invokes a model,
Broker, external network, media operation or a user's live workflow.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
sys.dont_write_bytecode = True

import HMB_Seedance_Execution_Mode_Host_Regression as harness


async def exercise(engine):
    import HMBSeedanceGeneration as seedance
    import _hmb_library_bootstrap as bootstrap
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest

    schema = harness.register(engine, {"HMBSeedanceGeneration": seedance})
    library = LibraryRegistry.get_library(schema.name)
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
        owner.before_library_nodes_loaded(schema, library)
    engine.event_manager.initialize_queue()
    harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="LegacyPromptRecovery"))
    key = seedance._HMB_LEGACY_PROMPT_RECOVERY_METADATA

    def create(name):
        result = harness.send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration",
            specific_library_name=schema.name, node_name=name,
            initial_setup=True, create_error_proxy_on_failure=False))
        return engine.node_manager.get_node_by_name(result.node_name)

    try:
        node = create("bound legacy input")
        with mock.patch.object(node, "_hmb_managed_prompt_projection", return_value="SHOT_AGENT_RESULT"):
            node.set_parameter_value("prompt", "LEGACY_AUTHORED_INPUT", initial_setup=True)
            assert node.parameter_values["prompt"] == "SHOT_AGENT_RESULT"
            assert node.metadata[key] == {"schema": "hmb-legacy-prompt-recovery", "version": 1,
                                          "value": "LEGACY_AUTHORED_INPUT"}
            node.set_parameter_value("prompt", "SHOT_AGENT_RESULT", initial_setup=True)
            assert node.metadata[key]["value"] == "LEGACY_AUTHORED_INPUT"
            node.set_parameter_value("prompt", "ANOTHER_INTERACTIVE_VALUE", initial_setup=False)
            assert node.metadata[key]["value"] == "LEGACY_AUTHORED_INPUT"
            assert node.parameter_values["prompt"] == "SHOT_AGENT_RESULT"

        native = create("unmanaged input")
        with mock.patch.object(native, "_hmb_managed_prompt_projection", return_value=None):
            native.set_parameter_value("prompt", "ORDINARY_INPUT", initial_setup=True)
            assert native.parameter_values["prompt"] == "ORDINARY_INPUT" and key not in native.metadata

        equal = create("matching input")
        with mock.patch.object(equal, "_hmb_managed_prompt_projection", return_value="SAME_INPUT"):
            equal.set_parameter_value("prompt", "SAME_INPUT", initial_setup=True)
            assert equal.parameter_values["prompt"] == "SAME_INPUT" and key not in equal.metadata

        occupied = create("occupied metadata")
        occupied.metadata[key] = {"external": "retain"}
        with mock.patch.object(occupied, "_hmb_managed_prompt_projection", return_value="SHOT"):
            occupied.set_parameter_value("prompt", "LEGACY", initial_setup=True)
        assert occupied.metadata[key] == {"external": "retain"}
        assert not harness.ATTEMPTS
    finally:
        owner.before_library_unregistered(schema, library)


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    native_connect = socket.socket.connect
    def guarded_connect(sock, address, *args, **kwargs):
        if (isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1")
                and any(frame.function == "_fallback_socketpair" and Path(frame.filename).name == "socket.py"
                        for frame in inspect.stack(context=0))):
            return native_connect(sock, address, *args, **kwargs)
        return harness.deny(sock, address)
    with tempfile.TemporaryDirectory(prefix="hmb-legacy-prompt-") as directory:
        root = Path(directory)
        settings = {name: str(root / name) for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        for folder in settings.values():
            Path(folder).mkdir(parents=True, exist_ok=True)
        with (mock.patch.dict(os.environ, settings), mock.patch.object(socket, "create_connection", harness.deny),
              mock.patch.object(socket, "getaddrinfo", harness.deny),
              mock.patch.object(socket.socket, "connect", guarded_connect),
              mock.patch.object(socket.socket, "connect_ex", harness.deny)):
            try:
                with engine_scope() as engine:
                    asyncio.run(exercise(engine))
            finally:
                logging.shutdown()
    print("HMB_LEGACY_PROMPT_RECOVERY_HOST=PASS (inert metadata, managed projection unchanged; no render)")


if __name__ == "__main__":
    main()
