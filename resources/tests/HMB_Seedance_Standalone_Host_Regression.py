"""Create, save, reopen and run the HMB Generator without the Standard library."""
from __future__ import annotations

import asyncio
import builtins
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

ROOT = Path(os.environ.get("HMB_MODE_TEST_LIBRARY_ROOT", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT))
UNEXPECTED_ACCESS = []


def offline(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0]).replace("\\", "/").lower()
        if ("/griptape_nodes_library/" in path or "/griptape-nodes-library-standard/" in path
                or path.endswith("/griptape_nodes_library.json")):
            UNEXPECTED_ACCESS.append(path)
            raise AssertionError(f"Unexpected Standard library read: {path}")
    if event not in {"socket.connect", "socket.sendto", "socket.sendmsg", "socket.getaddrinfo"}:
        return
    # Windows asyncio creates its internal socketpair over loopback.
    frame = sys._getframe(1)
    if event == "socket.connect" and isinstance(args[1], tuple) and args[1][0] in {"127.0.0.1", "::1"}:
        while frame:
            if frame.f_code.co_name == "_fallback_socketpair" and Path(frame.f_code.co_filename).name == "socket.py":
                return
            frame = frame.f_back
    UNEXPECTED_ACCESS.append(event)
    raise AssertionError(f"Unexpected external transport: {event}")


async def exercise(engine, work, view):
    from griptape_nodes.exe_types.node_types import SuccessFailureNode
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events import context_events
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
    from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowFromScratchRequest, SaveWorkflowFileFromSerializedFlowRequest

    original_import = builtins.__import__
    def no_optional_driver(name, globals=None, locals=None, fromlist=(), level=0):
        if (name == "griptape_nodes.drivers.storage.griptape_cloud_storage_driver"
                and (globals or {}).get("__name__") == "HMBSeedanceGeneration"):
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    with patch.object(builtins, "__import__", no_optional_driver):
        import HMBSeedanceGeneration as generator
    assert Path(generator.__file__).resolve() == ROOT / "HMBSeedanceGeneration.py"
    assert generator.HMBSeedanceGeneration.__bases__ == (SuccessFailureNode,)
    assert generator.GriptapeCloudStorageDriver is None
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_bytes())
    entry = next(entry for entry in schema.nodes if entry.class_name == "HMBSeedanceGeneration")
    library = LibraryRegistry.generate_new_library(schema)
    library.register_lazy_node_type(entry.class_name, entry.metadata, lambda: generator.HMBSeedanceGeneration)
    engine.event_manager.initialize_queue()
    async def send(request):
        request.broadcast_result = False
        result = await engine.ahandle_request(request)
        assert result.succeeded(), result.result_details
        return result

    async def open_workflow(request):
        view.close()
        opened = await send(request)
        if hasattr(engine, "bind_workflow"):
            view.enter_context(engine.bind_workflow(engine.open_workflows.get(opened.workflow_id)))
        return opened

    opened = await open_workflow(EnsureWorkflowAndFlowRequest(flow_name="Seedance standalone"))
    name = "Saved HMB Generator"
    await send(CreateNodeRequest(node_type=entry.class_name, node_name=name,
        specific_library_name=schema.name, create_error_proxy_on_failure=False))
    original = engine.node_manager.get_node_by_name(name)
    values = dict(model_id=generator.MODEL_NAME_SEEDANCE_2_5, draft_action=generator.DRAFT_ACTION_OFF, task=generator.TASK_TEXT_ONLY,
                  only_project="superwings12", prompt="Standalone Seedance fixture", resolution="720p",
                  duration=4, output_format="mp4", output_file=str(work / "fixture.mp4"))
    original._hmb_commit_seedance_mode()
    for key, value in values.items():
        original.set_parameter_value(key, value, initial_setup=True)
    assert original._try_create_gt_cloud_storage_driver() is None
    serialized = await send(SerializeFlowToCommandsRequest(flow_name=engine.context_manager.get_current_flow().name))
    saved = work / "standalone.py"
    await send(SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized.serialized_flow_commands,
        file_path=str(saved), file_name=saved.stem, display_name="Standalone"))
    if hasattr(context_events, "CloseWorkflowRequest"):
        await send(context_events.CloseWorkflowRequest(workflow_id=opened.workflow_id))
    else:
        await send(ClearAllObjectStateRequest(i_know_what_im_doing=True))
    await open_workflow(RunWorkflowFromScratchRequest(file_path=str(saved)))
    node = engine.node_manager.get_node_by_name(name)
    assert type(node) is generator.HMBSeedanceGeneration and node is not original
    assert {key: node.get_parameter_value(key) for key in values} == values
    for port in ("prompt", "reference_images", "first_frame", "last_frame", "VIDEO_OUT", "generation_id"):
        assert node.get_parameter_by_name(port) is not None, port
    assert node._hmb_seedance_execution_mode() == "only"
    bridge = generator._HMBAIBrokerBridge(server_url="https://broker.example.invalid")
    posts = []
    def request_json(method, path, *, payload, **options):
        assert (method, path) == ("POST", "/api/v1/generate/video"), (method, path)
        assert options["idempotency_key"] == payload["client_request_id"]
        posts.append(payload)
        return {"id": "job-" + "a" * 32, "status": "succeeded", "video_url": "https://media.example.invalid/fixture.mp4"}

    with ExitStack() as external:
        external.enter_context(patch.object(node, "_ensure_broker_connected", AsyncMock(return_value=bridge)))
        external.enter_context(patch.object(node, "_get_broker_bridge", return_value=bridge))
        external.enter_context(patch.object(bridge, "_request_json", side_effect=request_json))
        external.enter_context(patch.object(bridge, "queue_admission", return_value=None))
        external.enter_context(patch.object(bridge, "review_capabilities", return_value={
            "project_routing": {"generation_project_selection_schemas": [generator.ONLY_PROJECT_SELECTION_SCHEMA]}}))
        external.enter_context(patch.object(node, "_force_save_generation_recovery_checkpoint", AsyncMock(return_value=True)))
        completion = external.enter_context(patch.object(node, "_save_completed_task", AsyncMock()))
        await send(ResolveNodeRequest(node_name=name))
        assert len(posts) == 1, (posts, node.parameter_output_values.get("result_details"))
        assert posts[0]["model"] == generator.SEEDANCE_2_5_MODEL_ID
        assert posts[0]["prompt"] == values["prompt"]
        assert posts[0]["project_id"] == values["only_project"]
        completion.assert_awaited_once()
    assert not any(key == "griptape_nodes_library" or key.startswith("griptape_nodes_library.") for key in sys.modules)


def main():
    sys.addaudithook(offline)
    with tempfile.TemporaryDirectory(prefix="hmb-seedance-standalone-") as temp, ExitStack() as patches:
        work = Path(temp)
        paths = {}
        for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                    "XDG_STATE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY", "GTN_ENGINE_CONFIG_DIR",
                    "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR"):
            (work / key).mkdir()
            paths[key] = str(work / key)
        patches.enter_context(patch.dict(os.environ, paths | {"HMB_GRIPTAPE_STANDARD_LIBRARY_PATH": str(work / "absent")}))
        from griptape_nodes.common.log_capture import configure_diagnostic_logging
        from griptape_nodes.retained_mode.engine import engine_scope
        with engine_scope() as engine:
            patches.callback(configure_diagnostic_logging, log_to_file=False, buffer_lines=0)
            async def run():
                with ExitStack() as view:
                    await exercise(engine, work, view)
            asyncio.run(run())
    assert not UNEXPECTED_ACCESS, UNEXPECTED_ACCESS
    print("HMB_SEEDANCE_STANDALONE=PASS saved, reopened, SDK Resolve, 1 simulated submission, no Standard modules")


if __name__ == "__main__":
    main()
