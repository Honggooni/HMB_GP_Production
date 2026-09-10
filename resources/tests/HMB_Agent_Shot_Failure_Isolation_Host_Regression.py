"""Offline failure isolation through the installed Griptape DAG scheduler.

Uses actual HMB async entry points, the host node executor, graph dependencies,
and parameter propagation. Native model work and Seedance's external generation
boundary are replaced with deterministic local results. No policy DAT, login,
Broker, provider, or application UI is accessed. Hostless CI reports SKIP.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
import importlib.util
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STANDARD_ROOT = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(STANDARD_ROOT))


def host_available() -> bool:
    try:
        return importlib.util.find_spec("griptape_nodes.machines.parallel_resolution") is not None
    except (ImportError, ModuleNotFoundError):
        return False


if not host_available():
    print("HMB_AGENT_SHOT_FAILURE_ISOLATION_HOST=SKIP (installed host required)")
    raise SystemExit(0)


def no_network(*_args, **_kwargs):
    raise AssertionError("The offline host regression attempted a network operation.")


async def exercise_host(engine, agent_module, seedance_module) -> None:
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.machines.dag_builder import DagBuilder
    from griptape_nodes.machines.parallel_resolution import ParallelResolutionMachine
    from griptape_nodes.retained_mode.events.context_events import (
        EnsureWorkflowAndFlowRequest, EnsureWorkflowAndFlowResultSuccess,
    )
    import _hmb_shot_routing as shot_routing

    engine.event_manager.initialize_queue()
    events: list[tuple[str, int, float]] = []
    event_lock = threading.Lock()
    sibling_generation_started = threading.Event()

    def record(kind: str, number: int) -> None:
        with event_lock:
            events.append((kind, number, time.monotonic()))

    def native_model_fixture(self):
        number = self._regression_shot_number

        def model_step():
            record("agent_started", number)
            if number == 1:
                # Fail only after another branch entered generation, proving
                # its active async polling survives as well as queued work.
                assert sibling_generation_started.wait(timeout=5.0)
                time.sleep(0.02)
                record("agent_failed", number)
                raise TimeoutError("Read timed out: PRIVATE_PROVIDER_PAYLOAD")
            time.sleep(0.06)
            return f"Valid generator instruction for shot {number}."

        result = yield model_step
        self.set_parameter_value("output", result)
        self.parameter_output_values["output"] = result
        record("agent_finished", number)

    async def generation_fixture(self):
        number = self._regression_shot_number
        if self.get_parameter_value("resume_generation_id"):
            record("existing_task_retrieved", number)
            self._set_status_results(was_successful=True, result_details="Existing offline result retrieved.")
            return
        prompt = str(self.get_parameter_value("prompt") or "")
        assert number != 1, "The failed Agent branch reached generation."
        assert prompt == f"Valid generator instruction for shot {number}.", prompt
        record("generation_started", number)
        sibling_generation_started.set()
        await asyncio.sleep(0.08)
        self._set_status_results(was_successful=True, result_details="Offline result.")
        self._set_generation_status("succeeded", generation_id=f"offline-task-{number}")
        record("generation_finished", number)

    ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(
        display_name="Offline Shot Isolation", flow_name="OfflineShotIsolation",
    ))
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess), ensured
    flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
    agents = []
    generators = []
    native_base = agent_module.HMBAgentLibrary.__mro__[1]

    with ExitStack() as stack:
        # Hold the five supplied edges fixed; selector ownership/reconciliation
        # is covered by the routing regressions and otherwise removes Only
        # mode managed edges while these deliberately minimal fixtures load.
        stack.enter_context(mock.patch.object(
            shot_routing, "reconcile_shot_routing",
            lambda *_args, **_kwargs: {"ok": True, "code": "ready", "changed": 0},
        ))
        stack.enter_context(mock.patch.object(native_base, "process", native_model_fixture))
        stack.enter_context(mock.patch.object(
            seedance_module.HMBSeedanceGeneration, "_process_generation", generation_fixture,
        ))
        # Model entitlement and destination/media prerequisites belong to the
        # replaced external boundaries. Keep host dispatch and error handling
        # untouched, while excluding credentials and disk render preparation.
        stack.enter_context(mock.patch.object(
            agent_module.HMBAgentLibrary, "validate_before_node_run", lambda _self: None,
        ))
        stack.enter_context(mock.patch.object(
            seedance_module.HMBSeedanceGeneration, "validate_before_node_run", lambda _self: None,
        ))
        for number in range(1, 6):
            agent = agent_module.HMBAgentLibrary(name=f"offline_shot_{number}_agent")
            generator = seedance_module.HMBSeedanceGeneration(name=f"offline_shot_{number}_generator")
            for node in (agent, generator):
                node._regression_shot_number = number
                flow.add_node(node)
                engine.object_manager.add_object_by_name(node.name, node)
                engine.node_manager._name_to_parent_flow_name[node.name] = flow.name
            agent.set_parameter_value("prompt", f"Author shot {number}.")
            # Prove a previous good value cannot leak from the failed branch.
            agent.set_parameter_value("output", "STALE_SUCCESS_MUST_NOT_RENDER")
            agent.parameter_output_values["output"] = "STALE_SUCCESS_MUST_NOT_RENDER"
            generator.set_parameter_value("prompt", "STALE_SUCCESS_MUST_NOT_RENDER")
            assert flow.add_connection(
                agent, agent.get_parameter_by_name("output"),
                generator, generator.get_parameter_by_name("prompt"),
            ) is not None
            agents.append(agent)
            generators.append(generator)

        dag = DagBuilder(engine=engine)
        for generator in generators:
            dag.add_node_with_dependencies(generator, generator.name)
        assert len(dag.node_to_reference) == 10, sorted(dag.node_to_reference)
        machine = ParallelResolutionMachine(
            flow.name, max_nodes_in_parallel=2, dag_builder=dag, engine=engine,
        )
        await asyncio.wait_for(machine.resolve_node(), timeout=15.0)

        assert machine.is_complete(), machine.current_state
        assert not machine.is_errored(), machine.get_error_message()
        assert all(node.state == NodeResolutionState.RESOLVED for node in agents + generators)
        assert sorted(n for kind, n, _ in events if kind == "generation_finished") == [2, 3, 4, 5]
        assert not any(kind == "generation_started" and n == 1 for kind, n, _ in events)
        failed_at = next(at for kind, _, at in events if kind == "agent_failed")
        assert any(kind == "agent_started" and at > failed_at for kind, _, at in events), events
        assert any(
            kind == "generation_started" and at < failed_at
            and any(k == "generation_finished" and n == number and finished > failed_at
                    for k, n, finished in events)
            for kind, number, at in events
        ), events
        snapshot = agents[0]._hmb_execution_result_snapshot()
        assert snapshot["status"] == "failed", snapshot
        assert snapshot["code"] == "MODEL_TIMEOUT", snapshot
        assert "PRIVATE_PROVIDER_PAYLOAD" not in str(snapshot)
        assert generators[0].parameter_output_values.get("was_successful") is False
        details = str(generators[0].parameter_output_values.get("result_details") or "")
        assert "skip" in details.casefold(), details
        assert "PRIVATE_PROVIDER_PAYLOAD" not in details
        assert all(g.parameter_output_values.get("was_successful") is True for g in generators[1:])

        # Single-node resolution ignores control branching in this host. The
        # actual runtime prompt guard must still reject the known failed source.
        events.clear()
        generators[0].prepare_to_run_again()
        single_dag = engine.flow_manager.global_dag_builder
        single_dag.clear()
        single_dag.add_node_with_dependencies(generators[0], generators[0].name)
        assert len(single_dag.node_to_reference) == 1
        engine.flow_manager._global_single_node_resolution = True
        single_machine = ParallelResolutionMachine(
            flow.name, max_nodes_in_parallel=2, dag_builder=single_dag, engine=engine,
        )
        await asyncio.wait_for(single_machine.resolve_node(), timeout=10.0)
        assert single_machine.is_complete() and not single_machine.is_errored()
        assert not events, events
        assert generators[0].parameter_output_values.get("was_successful") is False

        async def resolve_only(node):
            node.prepare_to_run_again()
            single_dag.clear()
            single_dag.add_node_with_dependencies(node, node.name)
            current = ParallelResolutionMachine(
                flow.name, max_nodes_in_parallel=2, dag_builder=single_dag, engine=engine,
            )
            await asyncio.wait_for(current.resolve_node(), timeout=10.0)
            assert current.is_complete() and not current.is_errored()

        # The real host clears output maps before execution. A failed input
        # must therefore preserve an existing task through its durable record.
        existing = generators[0]
        checkpoint = existing._set_generation_recovery_checkpoint(
            stage="polling", task_id="offline-existing-task",
            task_identity="broker_task", status="running",
        )
        await resolve_only(existing)
        assert not events, events
        assert existing._generation_recovery_state() == checkpoint
        assert existing.parameter_output_values["generation_id"] == "offline-existing-task"
        assert existing.parameter_output_values["generation_status"] == "running"
        existing.set_parameter_value("resume_generation_id", "offline-existing-task")
        await resolve_only(existing)
        assert [(kind, n) for kind, n, _ in events] == [("existing_task_retrieved", 1)]
        assert existing._generation_recovery_state() == checkpoint

        # A valid saved/locked Agent result remains usable even when it predates
        # the new execution metadata. No additional fresh-success gate applies.
        events.clear()
        frozen = agents[1]
        frozen.lock = True
        frozen._hmb_execution_result = {}
        frozen.parameter_values[agent_module._AGENT_EXECUTION_RESULT_PARAMETER] = {}
        await resolve_only(generators[1])
        assert [(kind, n) for kind, n, _ in events] == [
            ("generation_started", 2), ("generation_finished", 2),
        ]
        assert "MODEL_TIMEOUT" in details, details

    print("HMB_AGENT_SHOT_FAILURE_ISOLATION_HOST=PASS (real DAG, five branches, queued siblings, timeout metadata, stale prompt blocked, single-node skip, existing-task recovery, locked legacy output)")


def main() -> None:
    previous_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-shot-isolation-host-") as directory:
        root = Path(directory)
        overrides = {
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "LOCALAPPDATA": str(root / "local-app-data"),
            "APPDATA": str(root / "app-data"),
            "GTN_CONFIG_WORKSPACE_DIRECTORY": str(root),
        }
        with mock.patch.dict(os.environ, overrides), mock.patch.object(socket, "create_connection", no_network):
            os.chdir(root)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope

                # Assertions retain failure evidence without flooding the test
                # console with unregistered-model/unsaved-workflow fixture logs.
                logging.disable(logging.CRITICAL)
                with engine_scope() as engine:
                    import HMBAgentLibrary as agent_module
                    import HMBSeedanceGeneration as seedance_module

                    assert agent_module._BuiltinAgent is not None, "Run with the installed host and Standard Agent."
                    with mock.patch.object(agent_module._hmb, "_bootstrap_agent_policy_session", no_network), \
                         mock.patch.object(agent_module._hmb, "_load_agent_rule_payload", no_network), \
                         mock.patch.object(seedance_module._HMBAIBrokerBridge, "account_snapshot", no_network):
                        asyncio.run(exercise_host(engine, agent_module, seedance_module))
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    main()
