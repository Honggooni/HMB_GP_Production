"""Only Shot representatives require verification; history must never block their outputs."""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import nullcontext
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(os.environ.get("HMB_PICKER_TEST_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))


async def verify(folder):
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes as GT
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    engine = GT.get_instance()
    GT.EventManager().initialize_queue()
    flow_result = GT.handle_request(EnsureWorkflowAndFlowRequest(flow_name="SelectedVideoSlowWire"))
    assert flow_result.succeeded(), flow_result.result_details
    view = engine.bind_workflow(engine.open_workflows.get(flow_result.workflow_id)) if hasattr(engine, "bind_workflow") else nullcontext()
    with view:
        await verify_flow(folder, engine, GT.FlowManager().get_flow_by_name(flow_result.flow_name))


async def verify_flow(folder, engine, flow):
    import HMBVideoPickerLibrary as picker

    node = picker.HMBVideoPickerLibrary(name="SelectedVideoPreparation")
    state = node._picker_state()
    count = 8
    for i in range(count):
        path = folder / f"clip-{i}.mp4"
        path.write_bytes(b"local reference readability fixture")
        state = picker._append_video_asset(state, {
            "video_uid": f"clip-{i}", "video_path": str(path), "label": f"clip-{i}.mp4",
        }, defer_thumbnail=True)
    row = state["picker_shots"][0]
    row["video_asset_uids"] = [f"clip-{i}" for i in range(count)]
    row["selected_video_uids"] = ["clip-7"]
    state = picker._parse_state(state)
    assert [v["video_uid"] for v in state["videos"] if v["selected"]] == ["clip-7"]
    owner = threading.get_ident()
    probed = []
    def delayed(reference):
        probed.append((Path(reference).stem, threading.get_ident() == owner))
        time.sleep(.055)
        return real_probe(reference)
    real_probe = picker._probe_readable_video_reference
    with patch.object(picker, "_probe_readable_video_reference", side_effect=delayed):
        start = time.perf_counter()
        _, media, cache = await asyncio.to_thread(node._prepare_execution_media, state)
        envelope = node._shot_picker_dependency_envelope(state_snapshot=state, probe_cache=cache)
        duration = time.perf_counter() - start
        assert envelope["shot_count"] == 1 and envelope["generation"] > 0
        assert [Path(item).stem for item in media] == ["clip-7"]
    counts = Counter(name for name, _ in probed)
    result = {"elapsed_ms": round(duration * 1000, 1), "probes": dict(counts), "owner_thread_probes": sum(is_owner for _, is_owner in probed)}
    print("HMB_SELECTED_VIDEO_PROBES=" + json.dumps(result), flush=True)
    assert counts == {"clip-7": 1} and not result["owner_thread_probes"]

    # Exercise a real direct legacy wire and its regular deferred publisher.
    # Seed the authored selection locally, then hold actual reference probing.
    import HMBPromptLibrary as prompt
    import HMBSeedanceGeneration as seedance
    import HMBAgentLibrary as agents
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes as GT
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    receiver = prompt.HMBPromptLibrary(name="SlowDirectPrompt")
    agent = agents.HMBAgentLibrary(name="SlowMediaAgent")
    generator = seedance.HMBSeedanceGeneration(name="SlowMediaGenerator")
    for entity in (node, receiver, agent, generator):
        flow.add_node(entity)
        workflow = engine.current_workflow()
        engine.object_manager.add_object_by_name_in(workflow, entity.name, entity)
        workflow.nodes.name_to_parent_flow_name[entity.name] = flow.name
    def wire(request_type, source, source_port, target, target_port):
        result = GT.handle_request(request_type(source_node_name=source.name, source_parameter_name=source_port,
                               target_node_name=target.name, target_parameter_name=target_port))
        assert result.succeeded(), result.result_details
    wire(CreateConnectionRequest, node, "PICKER_OUT", receiver, "PICKER_IN")
    wire(CreateConnectionRequest, receiver, "PROMPT_OUT", agent, "prompt")
    wire(CreateConnectionRequest, node, "VIDEO_OUT", generator, seedance.VIDEO_REFERENCES_PARAMETER)
    assert receiver.get_parameter_by_name(prompt.WIDGET_PARAMETER_NAME).ui_options["media_preview_sources"] == {
        "picker": node._hmb_picker_publisher_uuid}
    entered = threading.Event()
    def slow_selected(reference):
        assert Path(reference).stem == "clip-7" and threading.get_ident() != owner
        entered.set()
        time.sleep(1)
        return real_probe(reference)
    with patch.object(picker, "_probe_readable_video_reference", side_effect=slow_selected):
        node._write_state(state)
        start = time.perf_counter()
        node._sync_outputs_from_state(node._picker_state())
        returned = time.perf_counter()
        await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), 3)
        assert entered.is_set()
        assert "clip-7" not in str(receiver.get_parameter_value("PICKER_IN"))
        assert "clip-7" not in str(receiver.parameter_output_values.get("PROMPT_OUT", ""))
        assert "clip-7" not in str(agent.get_parameter_value("prompt"))
        assert not generator._hmb_preflight_parameters(bound=False)["video_references"]
        deadline = start + 8
        while "clip-7" not in str(receiver.get_parameter_value("PICKER_IN")):
            assert time.perf_counter() < deadline, "Verified file reached Picker but did not reach the direct Prompt input"
            await asyncio.sleep(.01)
        assert "clip-7" in str(node.parameter_output_values["VIDEO_OUT"])
        assert generator._hmb_preflight_parameters(bound=False)["video_references"] == [str(folder / "clip-7.mp4")]
        while "clip-7" not in str(agent.get_parameter_value("prompt")):
            assert time.perf_counter() < deadline, "Verified selected video did not reach Standard Agent prompt"
            await asyncio.sleep(.01)
        assert receiver._current_state()["picker"]["ordered_video_uids"] == ["clip-7"]
        elapsed = time.perf_counter() - start
        assert elapsed >= 1
        print("HMB_SLOW_DIRECT_WIRE=" + json.dumps({"callback_ms": round(1000 * (returned - start), 1),
              "verified_wire_ms": round(1000 * elapsed, 1), "premature_prompt_rows": 0,
              "agent_video":"clip-7","generator_reference": "clip-7.mp4"}), flush=True)

    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest
    release_old = threading.Event()
    entered.clear()
    def hold_old(reference):
        entered.set()
        assert release_old.wait(12)
        return real_probe(reference)
    with patch.object(picker, "_probe_readable_video_reference", side_effect=hold_old):
        node._sync_outputs_from_state(state)
        await asyncio.to_thread(entered.wait, 2)
        assert entered.is_set()
        wire(DeleteConnectionRequest, node, "PICKER_OUT", receiver, "PICKER_IN")
        wire(DeleteConnectionRequest, node, "VIDEO_OUT", generator, seedance.VIDEO_REFERENCES_PARAMETER)
        removed = GT.handle_request(DeleteNodeRequest(node_name=node.name))
        assert removed.succeeded(), removed.result_details
        replacement = picker.HMBVideoPickerLibrary(name=node.name)
        flow.add_node(replacement)
        engine.object_manager.add_object_by_name_in(workflow, replacement.name, replacement)
        workflow.nodes.name_to_parent_flow_name[replacement.name] = flow.name
        wire(CreateConnectionRequest, replacement, "PICKER_OUT", receiver, "PICKER_IN")
        wire(CreateConnectionRequest, replacement, "VIDEO_OUT", generator, seedance.VIDEO_REFERENCES_PARAMETER)
        release_old.set()
        deadline = time.perf_counter() + 8
        while node._hmb_video_removal_sync_thread.is_alive():
            assert time.perf_counter() < deadline, "Superseded background worker did not finish"
            await asyncio.sleep(.02)
    assert receiver.get_parameter_by_name(prompt.WIDGET_PARAMETER_NAME).ui_options["media_preview_sources"]["picker"] == replacement._hmb_picker_publisher_uuid
    assert "clip-7" not in str(receiver.get_parameter_value("PICKER_IN"))
    assert not generator._hmb_preflight_parameters(bound=False)["video_references"]
    print("HMB stale Picker background completion after rewiring both Prompt and Generator: PASS",flush=True)


if __name__ == "__main__":
    from griptape_nodes.retained_mode.engine import engine_scope
    with tempfile.TemporaryDirectory(prefix="hmb-selected-probe-") as t:
        folder = Path(t)
        env = {k: str(folder / k) for k in ("LOCALAPPDATA", "APPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        if not os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"):
            env["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(os.environ.get("HMB_STANDARD_LIBRARY_ROOT") or (Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
        with patch.dict(os.environ, env), patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            logging.disable(logging.CRITICAL)
            with engine_scope():
                asyncio.run(verify(folder))
