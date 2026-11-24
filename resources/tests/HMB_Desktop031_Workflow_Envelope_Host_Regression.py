"""Exercise editor-style request envelopes against the installed multi-workflow SDK."""
import asyncio
from contextlib import ExitStack, nullcontext
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(os.environ.get("HMB_MODE_TEST_LIBRARY_ROOT", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT))
STANDARD = Path(os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",
                               Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))


async def draft_final(engine, owner, other):
    """Use the real Final button callback, SDK idle check and Generator with an offline broker."""
    import HMB_Seedance_Draft_Shot_Regression as fixture
    from _hmb_workflow_migration import _engine_has_running_flow

    assert Path(fixture.t.__file__).resolve() == ROOT / "HMBSeedanceGeneration.py"
    with engine.bind_workflow(other), ExitStack() as normal:
        shot = fixture.Node(shot=True)
        normal.callback(shot.base.cleanup)
        engine.object_manager.add_object_by_name_in(other, shot.name, shot)
        project = {"schema": fixture.t.PROJECT_SELECTION_SCHEMA, "project": fixture.PROJECT}
        origin = shot._capture_generated_video_origin()
        normal.enter_context(patch.object(shot, "_capture_imageasset_project_selection", return_value=project))
        normal.enter_context(patch.object(shot, "_resolve_exact_shot_generation_inputs", side_effect=lambda values: {
            **values, **fixture.PROJECT, "_hmb_imageasset_project_selection": project, "_hmb_generation_origin": origin}))
        normal.enter_context(fixture.run_boundaries(shot))
        await shot._process_generation_impl()
        assert len(shot.bridge.posts) == 1 and shot.saved, shot._set_status_results.call_args_list
        assert shot.bridge.posts[0]["project_id"] == fixture.PROJECT["project_id"]
        assert "draft_job_id" not in shot.bridge.posts[0] and not shot.bridge.posts[0].get("draft")

    with engine.bind_workflow(owner), ExitStack() as boundaries:
        boundaries.enter_context(patch.object(fixture.t._broker_config, "load_broker_base_url", return_value=fixture.base.ORIGIN))
        node = fixture.Node()
        boundaries.callback(node.base.cleanup)
        engine.object_manager.add_object_by_name_in(owner, node.name, node)
        assert node.workflow is owner
        source = fixture.completed_source(node)
        node._store_draft_source(source)
        fixture.forbid_upstream_work(node)
        boundaries.enter_context(fixture.run_boundaries(node))

        def click():
            return node._on_finalize_draft_clicked(None, None, action_id="offline-final",
                expected_draft_job_id=source["draft_job_id"], final_resolution="1080p")

        machine = SimpleNamespace(current_state=object())
        with patch.object(owner.flows, "global_control_flow_machine", machine):
            assert _engine_has_running_flow(engine)
            denied = click()
            assert not denied.success and "Wait for the current workflow" in str(denied.details), denied.details
            assert not node.bridge.posts
        with patch.object(other.flows, "global_control_flow_machine", machine), engine.bind_workflow(other):
            assert _engine_has_running_flow(engine)
            started = click()
            assert started.success, started.details
            completion = node._hmb_draft_finalize_future
            click()
            await asyncio.wrap_future(completion)
            assert len(node.bridge.posts) == 1, node._set_status_results.call_args_list
            posted = node.bridge.posts[0]
            assert posted["draft_job_id"] == source["draft_job_id"] and posted["resolution"] == "1080p"
            assert node.upload_calls == 0 and node.saved
        assert not _engine_has_running_flow(engine)


async def check_basket_envelopes(engine, send):
    from griptape_nodes.retained_mode.events import context_events
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from _hmb_cgt import CatalogPreparation

    if not hasattr(context_events, "OpenWorkflowRequest"):
        return
    request_type = PayloadRegistry.get_type("HMBShotBasketRequest")
    assert str(engine.event_manager.get_scope_for_request_type(request_type)) == "optional_workflow"

    async def basket(action, payload, workflow=None):
        return await send(request_type(action=action, payload=payload), workflow)

    async def open_tab(display_name):
        opened = await send(context_events.OpenWorkflowRequest(display_name=display_name, create_flow=True))
        assert opened.succeeded(), opened.result_details
        runtime = engine.open_workflows.get(opened.open_workflow.workflow_id)
        return runtime, {"workflow_name": opened.open_workflow.name, "flow_name": runtime.context.get_current_flow().name}

    project = "katuri8"
    (Path(os.environ["HMB_IMAGE_PROJECTS_ROOT"]) / project / "Ai_Ct_image").mkdir(parents=True)
    # The only external boundary in prewarm is the CGT lookup.
    with patch.object(CatalogPreparation, "prepare", return_value=None):
        startup = await basket("status", {"prewarm": True})
        assert startup.succeeded() and engine.current_workflow_or_none() is None
        first, first_names = await open_tab("Basket A")
        second, second_names = await open_tab("Basket B")
        assert first_names["flow_name"] == second_names["flow_name"]
        crossed = await basket("prepare", second_names, first.workflow_id)
        assert not crossed.succeeded() and not first.context.get_current_flow().nodes and not second.context.get_current_flow().nodes
        closed = await basket("prepare", first_names, "closed-test-workflow")
        assert type(closed).__name__ == "WorkflowNotOpenResultFailure"
        result = await basket("prepare", first_names, first.workflow_id)
        assert result.succeeded() and result.data["created"] and result.data["prepared"], result.result_details
        retried = await basket("prepare", first_names, first.workflow_id)
        assert retried.succeeded() and retried.data["prepared"] and not retried.data.get("changed")
        for _ in range(100):
            status = await basket("status", first_names, first.workflow_id)
            assert status.succeeded(), status.result_details
            if any(item["project_id"] == project for item in status.data["projects"]):
                break
            await asyncio.sleep(0.05)
        bound = await basket("create", dict(first_names, project_id=project, cgt_setup=True), first.workflow_id)
        assert bound.succeeded() and bound.data.get("bound") and not bound.data["created"], bound.result_details
        for _ in range(100):
            status = await basket("status", first_names, first.workflow_id)
            assert status.succeeded(), status.result_details
            if status.data["status"] == "ready":
                break
            await asyncio.sleep(0.05)
        assert status.data["status"] == "ready" and status.data["cgt_required"] and not status.data["cgt_bound"]
        assert len(first.context.get_current_flow().nodes) == 6 and not second.context.get_current_flow().nodes
        assert engine.current_workflow_or_none() is None


async def exercise(engine, patches):
    import _hmb_library_bootstrap as bootstrap
    import _hmb_connection_management as connections
    import _hmb_shot_routing as routing
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_bytes())
    library = LibraryRegistry.generate_new_library(schema)
    classes = {}
    for definition in schema.nodes:
        module = importlib.import_module(Path(definition.file_path).stem)
        cls = getattr(module, definition.class_name)
        classes[definition.class_name] = cls
        library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    assert len(classes) == 11
    # Local graph and provider boundary only, independent of accounts and desktop patches.
    patches.enter_context(patch.object(bootstrap._Registration, "start_web_worker", return_value=None))
    patches.enter_context(patch.object(bootstrap, "_hmb_coordinate_native_editor_update", return_value=None))
    for action in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
        patches.enter_context(patch.object(routing, action, return_value=False))
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    owner.before_library_nodes_loaded(schema, library)
    engine.event_manager.initialize_queue()
    assert owner._registrations

    async def send(request, workflow=None):
        request.broadcast_result = False
        context = {"open_workflow_id": workflow} if workflow is not None else {}
        return await engine.ahandle_request(request, result_context=context)

    async def create(name, workflow):
        result = await send(CreateNodeRequest(node_type=name, specific_library_name=schema.name,
            node_name=name, create_error_proxy_on_failure=False), workflow)
        assert result.succeeded(), (name, result.result_details)
        node = engine.node_manager.get_node_by_name_in(engine.open_workflows.get(workflow), name)
        assert type(node) is classes[name]
        return node

    await check_basket_envelopes(engine, send)
    patches.enter_context(patch.object(classes["HMBImageAssetLibrary"], "_schedule_catalog_scan", return_value=False))
    first = await send(EnsureWorkflowAndFlowRequest(flow_name="Editor A"))
    second = await send(EnsureWorkflowAndFlowRequest(flow_name="Editor B"))
    assert first.succeeded() and second.succeeded() and first.workflow_id != second.workflow_id
    a, b = first.workflow_id, second.workflow_id
    nodes = {name: await create(name, a) for name in classes}
    await draft_final(engine, engine.open_workflows.get(a), engine.open_workflows.get(b))
    run_names = ("HMBAgentLibrary", "HMBSeedanceGeneration")
    calls = []

    async def run_local_fixture(node):
        # Only the final billable node body is replaced. Resolve, lookup,
        # routing, validation dispatch and execution scheduling belong to the SDK.
        calls.append((node.name, engine.current_workflow().workflow_id))

    for name in run_names:
        other = await create(name, b)
        other.metadata[connections.STATE] = {"version": 1, "detached": True}
        cls = classes[name]
        patches.enter_context(patch.object(cls, "aprocess", run_local_fixture))
        patches.enter_context(patch.object(cls, "validate_before_node_run", return_value=[]))
        patches.enter_context(patch.object(cls, "validate_before_workflow_run", return_value=[]))
        caller = engine.open_workflows.get(b) if name == "HMBSeedanceGeneration" else None
        with engine.bind_workflow(caller) if caller else nullcontext():
            change = await send(SetParameterValueRequest(node_name=name, parameter_name="prompt",
                                                         value="Offline editor input"), a)
            assert change.succeeded(), change.result_details
            assert nodes[name].get_parameter_value("prompt") == "Offline editor input"
            assert other.get_parameter_value("prompt") != "Offline editor input"
            allowed = await send(ResolveNodeRequest(node_name=name), a)
            assert allowed.succeeded(), (name, allowed.result_details)
            assert engine.current_workflow_or_none() is caller
        with engine.bind_workflow(engine.open_workflows.get(a)):
            denied = await send(ResolveNodeRequest(node_name=name), b)
            assert not denied.succeeded() and "HMB_CONNECTION_DETACHED" in str(denied.result_details)
            assert engine.current_workflow().workflow_id == a
    assert calls == [(name, a) for name in run_names], calls
    missing = await send(ResolveNodeRequest(node_name="No such node"), a)
    assert not missing.succeeded() and "does not exist" in str(missing.result_details)
    closed = await send(ResolveNodeRequest(node_name=run_names[0]), "not-an-open-workflow")
    assert type(closed).__name__ == "WorkflowNotOpenResultFailure"
    unnamed = await send(ResolveNodeRequest(node_name=run_names[0]))
    assert type(unnamed).__name__ == "WorkflowNotNamedResultFailure"
    duplicate = await send(CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name=schema.name,
                                            node_name="Second Agent"), a)
    assert not duplicate.succeeded()
    assert engine.current_workflow_or_none() is None
    agent = nodes["HMBAgentLibrary"]
    native_cls = importlib.import_module("HMBAgentLibrary")._BuiltinAgent
    assert native_cls is not None and Path(sys.modules[native_cls.__module__].__file__).resolve().is_relative_to(
        STANDARD.resolve()), "Expected the Agent from the selected Standard Library checkout"
    std_schema = LibrarySchema.model_validate_json((STANDARD / "griptape_nodes_library.json").read_bytes())
    std_library = LibraryRegistry.generate_new_library(std_schema)
    agent_def = next(row for row in std_schema.nodes if row.class_name == "Agent")
    std_library.register_lazy_node_type("Agent", agent_def.metadata, lambda: native_cls)
    native_result = await send(CreateNodeRequest(node_type="Agent", specific_library_name=std_schema.name,
                                                 node_name="Native Agent", create_error_proxy_on_failure=False), a)
    assert native_result.succeeded(), native_result.result_details
    native = engine.node_manager.get_node_by_name_in(engine.open_workflows.get(a), "Native Agent")
    assert type(native) is native_cls
    assert list(agent._model_access.model_choices) == list(native._model_access.model_choices)
    for key in ("model", "model_provider"):
        assert agent.get_parameter_value(key) == native.get_parameter_value(key)
    generator = nodes["HMBSeedanceGeneration"]
    edge = {"source_node_name": native.name, "source_parameter_name": "output",
            "target_node_name": generator.name, "target_parameter_name": "prompt"}
    with engine.bind_workflow(engine.open_workflows.get(b)):
        connected = await send(CreateConnectionRequest(**edge, initial_setup=True), a)
        assert connected.succeeded(), connected.result_details
        view = await send(connections.HMBGetNodeConnectionsRequest(node_name=generator.name), a)
        assert view.succeeded() and view.connections, view.result_details
        deletion = await send(DeleteNodeRequest(node_name=generator.name), a)
        assert not deletion.succeeded() and "HMB_DELETE_CONNECTED" in str(deletion.result_details)
    assert engine.node_manager.get_node_by_name_in(engine.open_workflows.get(a), generator.name) is generator
    print(json.dumps({"created_nodes": list(nodes), "executed_offline": list(run_names),
                      "same_names_isolated": True, "offline_draft_final_posts": 1, "offline_bound_shot_posts": 1,
                      "native_model_choices": list(native._model_access.model_choices),
                      "native_model_provider": native.get_parameter_value("model_provider"),
                      "native_model": native.get_parameter_value("model"), "external_calls": 0}))


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-desktop031-envelope-") as temp, ExitStack() as patches:
        workspace = Path(temp)
        paths = {}
        for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                    "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY", "GTN_ENGINE_CONFIG_DIR",
                    "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "HMB_IMAGE_PROJECTS_ROOT"):
            (workspace / key).mkdir()
            paths[key] = str(workspace / key)
        patches.enter_context(patch.dict(os.environ, paths | {"HMB_GRIPTAPE_STANDARD_LIBRARY_PATH": str(STANDARD)}))
        from griptape_nodes.retained_mode.engine import engine_scope
        from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowResultSuccess
        if "open_workflow" not in EnsureWorkflowAndFlowResultSuccess.__dataclass_fields__:
            print("HMB_DESKTOP031_WORKFLOW_ENVELOPE=SKIP (Desktop 0.31 multi-workflow API required)")
            return
        with engine_scope() as engine:
            from griptape_nodes.common.log_capture import configure_diagnostic_logging
            patches.callback(configure_diagnostic_logging, log_to_file=False, buffer_lines=0)
            asyncio.run(exercise(engine, patches))
    print("HMB_DESKTOP031_WORKFLOW_ENVELOPE=PASS")


if __name__ == "__main__":
    main()
