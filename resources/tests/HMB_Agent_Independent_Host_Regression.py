"""Exercise HMB's own Agent type and wire with Standard absent, without a provider request."""
import asyncio
from contextlib import ExitStack
import importlib.abc
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

ROOT = Path(os.environ.get("HMB_MODE_TEST_LIBRARY_ROOT", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(Path(__file__).resolve().parent))
from HMB_Seedance_Standalone_Host_Regression import offline, UNEXPECTED_ACCESS


class AbsentStandard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".", 1)[0] == "griptape_nodes_library":
            raise AssertionError("HMB Agent tried to import Standard: " + fullname)
        return None


async def exercise(engine, work):
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events import context_events
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
    from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowFromScratchRequest, SaveWorkflowFileFromSerializedFlowRequest
    import HMBAgentLibrary as hmb
    from _hmb_native_agent.agents.agent import Agent
    from _hmb_native_agent.llm.agent_state import AgentState
    from _hmb_native_agent.llm.model_config import cloud_model_config
    from _hmb_agent_media import _uses_native_user_content

    assert hmb.HMBAgentLibrary.__mro__[1] is Agent
    assert Path(sys.modules[Agent.__module__].__file__).resolve().is_relative_to(ROOT / "_hmb_native_agent")
    state = AgentState(model=cloud_model_config("test-model"))
    assert _uses_native_user_content(state) and AgentState.from_wire(json.dumps(state.to_wire())).to_wire() == state.to_wire()
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_bytes())
    entry = next(node for node in schema.nodes if node.class_name == "HMBAgentLibrary")
    library = LibraryRegistry.generate_new_library(schema)
    library.register_lazy_node_type(entry.class_name, entry.metadata, lambda: hmb.HMBAgentLibrary)
    engine.event_manager.initialize_queue()
    async def send(request):
        request.broadcast_result = False
        result = await engine.ahandle_request(request)
        assert result.succeeded(), result.result_details
        return result

    with ExitStack() as view:
        async def open_view(request):
            view.close()
            result = await send(request)
            if hasattr(engine, "bind_workflow"):
                view.enter_context(engine.bind_workflow(engine.open_workflows.get(result.workflow_id)))
            return result
        opened = await open_view(context_events.EnsureWorkflowAndFlowRequest(flow_name="HMB Independent Agent"))
        name = "Saved Agent"
        await send(CreateNodeRequest(node_type=entry.class_name, specific_library_name=schema.name, node_name=name))
        original = engine.node_manager.get_node_by_name(name)
        original.set_parameter_value("prompt", "보존할 Agent 입력")
        options = {key: original.get_parameter_value(key) for key in ("model", "model_provider", "prompt")}
        serialized = await send(SerializeFlowToCommandsRequest(flow_name=engine.context_manager.get_current_flow().name))
        saved = work / "agent.py"
        await send(SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized.serialized_flow_commands,
            file_path=str(saved), file_name=saved.stem, display_name=name))
        if hasattr(context_events, "CloseWorkflowRequest"):
            await send(context_events.CloseWorkflowRequest(workflow_id=opened.workflow_id))
        else:
            await send(ClearAllObjectStateRequest(i_know_what_im_doing=True))
        await open_view(RunWorkflowFromScratchRequest(file_path=str(saved)))
        restored = engine.node_manager.get_node_by_name(name)
        assert type(restored) is hmb.HMBAgentLibrary and restored is not original
        assert {key: restored.get_parameter_value(key) for key in options} == options
        if "--require-tools" in sys.argv:
            import _hmb_native_agent
            import dateparser
            assert Path(dateparser.__file__).resolve().is_relative_to(ROOT/".hmb-agent-deps")
            from _hmb_native_agent.llm.tools import _date_time, _calculator
            from datetime import datetime
            assert datetime.fromisoformat(_date_time().tools["get_relative_datetime"].function("tomorrow"))
            assert str(_calculator().tools["calculate"].function("6 * 7")) == "42"
            external = ModuleType("dateparser")
            external.__file__ = str(work/".venv/Lib/site-packages/dateparser/__init__.py")
            with patch.dict(sys.modules, {"dateparser":external}):
                try:
                    _hmb_native_agent.check_tool_dependency("dateparser","dateparser")
                except RuntimeError as error:
                    assert "dateparser 1.4.1" in str(error)
                else:
                    raise AssertionError("An incompatible preloaded date parser was accepted")
                assert str(_calculator().tools["calculate"].function("6 * 7")) == "42"
    print("HMB_PINNED_AGENT=PASS native create/save/reopen, preserved model and wire, Standard absent")


def main():
    sys.meta_path.insert(0, AbsentStandard())
    sys.addaudithook(offline)
    with tempfile.TemporaryDirectory(prefix="hmb-agent-independent-") as temp, ExitStack() as env:
        work = Path(temp)
        paths = {key: str(work/key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
            "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        for value in paths.values(): Path(value).mkdir()
        env.enter_context(patch.dict(os.environ, paths | {"HMB_GRIPTAPE_STANDARD_LIBRARY_PATH": str(work / "absent")}))
        from griptape_nodes.retained_mode.engine import engine_scope
        from griptape_nodes.common.log_capture import configure_diagnostic_logging
        try:
            with engine_scope() as engine:
                asyncio.run(exercise(engine, work))
        finally:
            configure_diagnostic_logging(log_to_file=False,buffer_lines=0)
    assert not UNEXPECTED_ACCESS and not any(name.startswith("griptape_nodes_library") for name in sys.modules)


if __name__ == "__main__":
    main()
