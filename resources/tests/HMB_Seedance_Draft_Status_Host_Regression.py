"""Native SDK completed Draft save/reopen, detached callbacks and GET-only status recovery."""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import HMB_Seedance_Execution_Mode_Host_Regression as host


async def exercise(engine, phase, out):
    import HMBSeedanceGeneration as t
    import _hmb_shot_routing as routing
    from griptape_nodes.retained_mode.engine import NO_WORKFLOW
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowWithCurrentStateRequest, SaveWorkflowFileFromSerializedFlowRequest

    schema = host.register(engine, {"HMBSeedanceGeneration": t})
    engine.event_manager.initialize_queue()
    job = "job-" + "a" * 32
    origin = "https://sdk-fixture.invalid"
    project = t.resolve_project("katuri8", default_legacy=False)
    resolutions = {"1080p": "available", "4k": "available"}
    endpoints = {f"/api/v1/reviews/tasks/{job}/draft-final?resolution={r}": r for r in resolutions}
    calls = []
    offline = False

    def read(method, path, **kwargs):
        if method != "GET" or path not in endpoints:
            host.deny()
        quality = endpoints[path]
        calls.append(quality)
        if offline:
            raise TimeoutError("Simulated status timeout")
        return dict(schema="hmb-review-draft-final-v1", state_schema="hmb-draft-final-state-v1",
                    state="available", is_draft=True, eligible=True, consumed=False, source_task_id=job,
                    resolution=quality, owner_user_id=7, project_id=project["project_id"], project_name=project["project_name"],
                    child_task_id=None, child_status=None, checked_at=int(time.time()), expires_at=int(time.time())+604800,
                    idempotency_key=t._seedance_draft_final_request_id(job, quality, version=1))

    async def require_state(state):
        async with asyncio.timeout(5):
            while True:
                current = node.get_parameter_value(t.SEEDANCE_SHOT_WIDGET_PARAMETER)["draft"]
                if current["final_state"] == state:
                    return current
                await asyncio.sleep(.02)

    async def clear_watch():
        previous = getattr(node, "_hmb_draft_final_status_future", None)
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.gather(asyncio.wrap_future(previous), return_exceptions=True)
            await asyncio.sleep(0)
        node._hmb_draft_final_status_future = None
        node._hmb_draft_final_status_cache = {}
        calls.clear()

    bridge = t._HMBAIBrokerBridge(server_url=origin)
    name = "Completed 480p"
    saved = out / "offline-draft.py"
    with ExitStack() as guards:
        for method in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            guards.enter_context(patch.object(routing, method, return_value=False))
        guards.enter_context(patch.object(t.HMBSeedanceGeneration, "_get_broker_bridge", return_value=bridge))
        guards.enter_context(patch.object(t.HMBSeedanceGeneration, "_selected_broker_server_url", return_value=origin))
        guards.enter_context(patch.object(t.HMBSeedanceGeneration, "_process_generation", host.deny))
        guards.enter_context(patch.object(t._HMBAIBrokerBridge, "_request_json", host.deny))
        guards.enter_context(patch.object(bridge, "_load_access_token", return_value="synthetic-token"))
        guards.enter_context(patch.object(bridge, "_request_json", side_effect=read))
        if phase == "save":
            flow = host.send(engine, EnsureWorkflowAndFlowRequest(flow_name="Offline Draft")).flow_name
            host.send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration", specific_library_name=schema.name,
                      node_name=name, initial_setup=True, metadata={t.SEEDANCE_EXECUTION_MODE_METADATA: host.intent(t)},
                      create_error_proxy_on_failure=False))
        else:
            result = await host.asend(engine, RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
            assert str(getattr(result.status, "name", result.status)) == "GOOD"
        node = engine.node_manager.get_node_by_name(name)
        if phase == "save":
            host.configure(t, node, 6)
            node._hmb_clear_shot_routing_catalog()
            host.select(engine, t, node)
            node.set_parameter_value("draft_action", "Draft 480p", emit_change=False)
            node._store_draft_source(dict(draft_job_id=job, completed=True, created_at_ms=int(time.time()*1000)-1000,
                broker_server_url=origin, project_id=project["project_id"], project_name=project["project_name"],
                generation_origin=node._capture_generated_video_origin(), owner_id=node._draft_owner_id(), source_bindings={}))
            serialized = host.send(engine, SerializeFlowToCommandsRequest(flow_name=flow)).serialized_flow_commands
            await host.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
                               file_name=saved.stem, file_path=str(saved), display_name="Offline Draft"))
        source = node._draft_source_record()
        assert source["draft_job_id"] == job and source["completed"] and node._draft_only_mode()
        await clear_watch()
        with engine.bind_workflow(NO_WORKFLOW):
            node._sync_seedance_shot_widget(emit_change=True)
        available = await require_state("available")
        assert available["final_available"] and available["finals_by_resolution"] == resolutions
        assert calls == list(resolutions), calls
        host.record("detached_callback_queries_each_final_quality", phase=phase, read_only_gets=list(calls))
        await clear_watch()
        offline = True
        with engine.bind_workflow(NO_WORKFLOW):
            node._sync_seedance_shot_widget(emit_change=True)
        assert not (await require_state("unknown"))["final_available"]
        offline = False
        calls.clear()
        command = dict(schema=t.SEEDANCE_REFRESH_COMMAND_SCHEMA, version=t.SEEDANCE_REFRESH_COMMAND_VERSION,
                       action="refresh_draft_final_status", action_id="sdk-retry-final-status",
                       expected_draft_job_id=job, issued_at_ms=int(time.time()*1000))
        host.send(engine, SetParameterValueRequest(node_name=name, parameter_name=t.SEEDANCE_REFRESH_COMMAND_PARAMETER,
                                                   value=command, initial_setup=False))
        available = await require_state("available")
        assert available["final_available"] and calls == list(resolutions), (available, calls)
        assert node._draft_source_record()["draft_job_id"] == job
        host.record("status_retry_wakes_same_draft_without_render", phase=phase, read_only_gets=list(calls))
        await clear_watch()


if __name__ == "__main__":
    if len(sys.argv) == 3:
        phase, out = sys.argv[1], Path(sys.argv[2])
        expected = ("detached_callback_queries_each_final_quality", "status_retry_wakes_same_draft_without_render")
        if phase == "save":
            # Several older SDK probes register their callback after importing the harness.
            with patch.object(host, "exercise", exercise):
                host.run_phase(phase, out, use_standard=False, expected_cases=expected)
        else:
            host.run_phase(phase, out, exercise_flow=exercise, use_standard=False, expected_cases=expected)
    else:
        with tempfile.TemporaryDirectory(prefix="hmb-draft-status-") as tmp:
            for case in ("save", "reopen"):
                subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), case, tmp], check=True, timeout=90)
                result = json.loads((Path(tmp) / (case + "-result.json")).read_bytes())
                assert result["passed"] and not result["external_or_live_socket_attempts"] and not result["forbidden_execution_attempts"]
        print("PASS Native SDK Draft save and cold reopen: detached status, GET-only retry, no paid calls.")
