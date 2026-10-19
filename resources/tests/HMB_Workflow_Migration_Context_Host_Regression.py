"""Actual SDK migration: empty/nested caller context and rollback stay isolated."""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("migration_context_fixture",
    ROOT / "resources/tests/HMB_Workflow_Consolidation_Host_Regression.py")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

def context_identity(manager):
    return tuple((id(workflow), workflow._name,
        tuple((id(flow), id(flow._flow), tuple((id(node), id(node.node),
            tuple(id(element) for element in node._element_stack))
            for node in flow._node_stack)) for flow in workflow._flow_stack))
        for workflow in manager._workflow_stack)

async def exercise(engine, directory):
    import _hmb_workflow_migration as migration
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    original = migration.migrate_flow
    original_structure = migration._structural_request
    calls, structures, observer_samples = [], [], []
    caller = {}

    def observed_structure(host, flow, request, expected):
        before = context_identity(host.context_manager)
        result = original_structure(host, flow, request, expected)
        assert not inspect.isawaitable(result)
        assert context_identity(host.context_manager) == before
        structures.append(type(request).__name__)
        return result

    async def isolated_call(host, flow_name, **kwargs):
        manager = host.context_manager
        if not caller:
            created = base.send(host, CreateFlowRequest(flow_name="MigrationContextCaller",
                parent_flow_name=None, set_as_new_context=False))
            caller["flow"] = host.flow_manager.get_flow_by_name(created.flow_name)
            made = base.send(host, CreateNodeRequest(node_type="HMBAgentLibrary",
                specific_library_name="HMB_GP_Production", node_name="Migration context sentinel",
                override_parent_flow_name=created.flow_name, set_as_new_context=False))
            caller["node"] = host.node_manager.get_node_by_name(made.node_name)
            caller["element"] = caller["node"].get_parameter_by_name("prompt")
        before = context_identity(manager)
        mode = "empty_flow" if len(calls) % 2 == 0 else "nested_other_flow_node_element"
        record = {"mode": mode}
        async def run_current_context():
            expected = context_identity(manager)
            done = False
            async def observer():
                while not done:
                    assert context_identity(manager) == expected, "Migration leaked a target context across a task boundary"
                    observer_samples.append(1)
                    await asyncio.sleep(0)
            task = asyncio.create_task(observer())
            await asyncio.sleep(0)
            try:
                result = await original(host, flow_name, **kwargs)
                record.update(code=result["code"], ok=result["ok"], rollback=result.get("rollback"))
                return result
            except asyncio.CancelledError:
                record.update(code="migration_cancelled", ok=False, rollback=migration.last_migration_result(host, flow_name)["rollback"])
                raise
            finally:
                done = True
                await task
                assert context_identity(manager) == expected
                calls.append(record)
        # This official nested Workflow scope has no Flow or Node, while the
        # real caller's entire Workflow/Flow/Node/element stack stays below it.
        with manager.workflow(manager.get_current_workflow_name()):
            if mode == "empty_flow":
                assert not manager.has_current_flow() and not manager.has_current_node()
                try:
                    return await run_current_context()
                finally:
                    assert not manager.has_current_flow() and not manager.has_current_node()
                    assert manager.get_current_workflow_name() == before[-1][1]
                    # Workflow scope itself restores the original stack below.
            else:
                with manager.flow(flow=caller["flow"]), manager.node(node=caller["node"]), manager.element(caller["element"]):
                    assert manager.get_current_flow() is caller["flow"]
                    assert manager.get_current_node() is caller["node"]
                    assert manager.get_current_element() is caller["element"]
                    try:
                        return await run_current_context()
                    finally:
                        assert manager.get_current_flow() is caller["flow"]
                        assert manager.get_current_node() is caller["node"]
                        assert manager.get_current_element() is caller["element"]

    # Outer wrapper checks after the temporary Workflow itself has popped.
    async def checked_call(host, flow_name, **kwargs):
        before = context_identity(host.context_manager)
        try:
            return await isolated_call(host, flow_name, **kwargs)
        finally:
            assert context_identity(host.context_manager) == before

    with mock.patch.object(migration, "migrate_flow", checked_call), \
            mock.patch.object(migration, "_structural_request", observed_structure):
        await base.canonical_case(engine, directory)
    assert observer_samples and len(calls) >= 8
    assert {row["mode"] for row in calls} == {"empty_flow", "nested_other_flow_node_element"}
    assert sum(row.get("rollback") == "verified" for row in calls) >= 3
    assert {"SerializeFlowToCommandsRequest", "SerializeNodeToCommandsRequest", "DeleteNodeRequest",
        "DeserializeNodeFromCommandsRequest", "SetParameterValueRequest"}.issubset(structures)
    print("MIGRATION_CONTEXT_EVIDENCE " + json.dumps({"calls": calls,
        "synchronous_structural_requests": len(structures), "observer_samples": len(observer_samples),
        "context_leaks": 0, "executed_nodes": len(base.EXECUTED), "network_attempts": len(base.NETWORK)}))

def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    import _hmb_shot_routing as routing
    import _hmb_library_bootstrap as bootstrap
    import HMBAgentLibrary as agents
    import HMBSeedanceGeneration as generators
    import HMBImageAssetLibrary as images
    with tempfile.TemporaryDirectory(prefix="hmb-migration-context-") as directory:
        temporary = Path(directory)
        overrides = {key: str(temporary / leaf) for key, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("LOCALAPPDATA", "local"),
            ("APPDATA", "app"), ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "images"))}
        for target in overrides.values():
            Path(target).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", base.no_network))
            base.NATIVE_HYDRATION_SCHEDULER = routing.schedule_post_hydration_reconcile
            stack.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
            stack.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
            stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", base.no_execution))
            stack.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", base.no_execution))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                asyncio.run(exercise(engine, temporary))
            assert not base.NETWORK and not base.EXECUTED
    print("HMB_WORKFLOW_MIGRATION_CONTEXT_HOST=PASS (actual SDK; no provider or live graph calls)")

if __name__ == "__main__":
    main()
