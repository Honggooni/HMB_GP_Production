"""Real SDK whole-Flow admission isolation with five exact Shot consumers.

Only the model-inference and video-generation boundaries are counted fakes.
Native retained nodes, files, connections, validators, scheduling, manager
preparation, result tickets and Generator aprocess remain real. No provider
request, user workflow, desktop transport or paid operation is permitted.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
import HMB_Library_Lifecycle_Order_Host_Regression as base
import HMB_Seedance_Execution_Mode_Host_Regression as host

PRODUCTS = ("HMBAgentLibrary.py", "HMBPromptLibrary.py", "HMBSeedanceGeneration.py", "_hmb_shot_routing.py")
SELECTED_CASES = "all"


async def exercise(engine, phase, out):
    modules = {name: importlib.import_module(name) for name in base.KINDS}
    images, pickers, prompts, agents, finishes, t = (modules[name] for name in base.KINDS)
    routing = importlib.import_module("_hmb_shot_routing")
    bootstrap = importlib.import_module("_hmb_library_bootstrap")
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
    library, schema = base.register(engine, modules)
    engine.event_manager.initialize_queue()
    counters = {"compile": Counter(), "submit": Counter()}
    observed = []
    overlap = dict(enabled=False, active=0, peak=0, peak_tickets=0)
    overlap_gate = asyncio.Event()
    with ExitStack() as guard:
        guard.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: False))
        guard.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
        guard.enter_context(mock.patch.object(t._HMBAIBrokerBridge, "_request_json", host.deny))
        guard.enter_context(mock.patch.object(agents.HMBAgentLibrary, "_hmb_aprocess_locked", host.deny))
        guard.enter_context(mock.patch.object(agents._HMBAgentShotExecution, "_hmb_aprocess_locked", host.deny))
        # Native Standard validation remains active. Supply a synthetic local
        # credential because no driver/model operation exists in this fixture.
        native_agent_module = importlib.import_module(agents._BaseAgent.__module__)
        guard.enter_context(mock.patch.object(native_agent_module, "resolve_cloud_api_key", return_value="offline-fixture-not-a-credential"))
        state = base.create_project(images, out / "fixture-media")
        flow = engine.flow_manager.get_flow_by_name(host.send(engine, EnsureWorkflowAndFlowRequest(flow_name="FiveShotAdmissionIsolation")).flow_name)
        nodes = {}
        for kind in base.KINDS:
            names = [f"Isolated Generator {i}" for i in range(1, 6)] if kind == base.KINDS[-1] else [f"Isolated {kind}"]
            created = []
            for name in names:
                result = host.send(engine, CreateNodeRequest(node_type=kind, specific_library_name=schema.name,
                    node_name=name, create_error_proxy_on_failure=False))
                node = engine.node_manager.get_node_by_name(result.node_name)
                if kind == base.KINDS[0]:
                    node._hmb_initial_catalog_scan_pending = False
                    node._resolution_cache_for_state(deepcopy(state))
                    node._cache_shot_routing_snapshot(deepcopy(state), force=True)
                    node._publish_state(deepcopy(state))
                created.append(node)
            nodes[kind] = created if kind == base.KINDS[-1] else created[0]
            await asyncio.sleep(.03)
        source, picker, prompt, manager, finish = (nodes[k] for k in base.KINDS[:-1])
        shots = source._hmb_shot_routing_snapshot()["shots"]
        def ready():
            try:
                base.assert_graph(engine, flow, nodes, shots)
                return True
            except (AssertionError, KeyError, ValueError):
                return False
        await base.settle(ready)
        bindings = base.assert_graph(engine, flow, nodes, shots)
        generators = [bindings[shot["shot_uuid"]] for shot in shots]
        text_key = next(iter(prompts.TEXT_FIELD_DEFAULTS))
        prompt_state = prompt._current_state()
        for shot in shots:
            prompt_state = prompts._select_prompt_shot_document(prompt_state, dict(shot, channel_uuid=base.CHANNEL))
            prompt_state = base.prompt_rows_from_state(prompt, prompt_state)[0]
            prompt_state["text"][text_key] = f"Offline authored {shot['shot_uuid']} {{literal}} OFF 0"
            prompt_state = prompts._store_prompt_shot_document(prompt_state)
        host.send(engine, SetParameterValueRequest(node_name=prompt.name, parameter_name=prompts.WIDGET_PARAMETER_NAME,
            value=prompts._json_dumps(prompt_state), initial_setup=True))
        prompt._sync_prompt_output_now()
        for node, shot in zip(generators, shots):
            for key, value in dict(model_id=t.MODEL_NAME_SEEDANCE_2_5, task=t.TASK_REFERENCE_TO_VIDEO,
                    resolution="480p", duration=4, output_format="mov", generate_audio=False,
                    draft_action=t.DRAFT_ACTION_OFF, resume_generation_id="").items():
                node.set_parameter_value(key, value, initial_setup=True)
            node._hmb_commit_seedance_mode(shot["shot_uuid"])
        original_intents = [deepcopy(node.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA]) for node in generators]
        exact_sources = {shot["shot_uuid"]: list(shot["selected_source_uids"]) for shot in shots}
        trace = []
        def traced(name, stage):
            trace.append(dict(node=name, stage=stage, monotonic=time.perf_counter()))
            (out / "native-stage-trace.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
        for node in generators:
            original_aprocess = node.aprocess
            async def traced_aprocess(node=node, original=original_aprocess):
                traced(node.name, "aprocess_enter")
                try:
                    return await original()
                finally:
                    traced(node.name, "aprocess_exit")
            guard.enter_context(mock.patch.object(node, "aprocess", traced_aprocess))

        async def fake_compile(*, channel_uuid, shot_uuid, prompt_owner, generator=None):
            traced(generator.name, "compile_enter")
            assert generator in generators and channel_uuid == base.CHANNEL
            assert manager._hmb_manager_prompt_owner(channel_uuid=channel_uuid, shot_uuid=shot_uuid) is prompt_owner is prompt
            document = prompt_owner._hmb_prompt_shot_document(channel_uuid=channel_uuid, shot_uuid=shot_uuid)
            assert isinstance(document, dict)
            subscription = generator._hmb_shot_channel_subscription()
            assert subscription["enabled"] and subscription["shot_uuid"] == shot_uuid
            counters["compile"][generator.name] += 1
            text = "Offline completed exact Shot " + shot_uuid
            run_id = f"offline-{generator.name}-{counters['compile'][generator.name]}"
            record = dict(text=text, result=dict(status="succeeded", run_id=run_id,
                output_sha256=hashlib.sha256(text.encode()).hexdigest()), observation={}, policy_identity={},
                shot={key: subscription[key] for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name")})
            key = manager._hmb_slot_key(channel_uuid, shot_uuid)
            with manager._hmb_shot_result_lock:
                tickets = getattr(manager, "_hmb_shot_request_records", None)
                if tickets is None:
                    tickets = manager._hmb_shot_request_records = {}
                tickets[run_id] = dict(key=key, generator=generator, record=deepcopy(record))
                if overlap["enabled"]:
                    overlap["peak_tickets"] = max(overlap["peak_tickets"], len(tickets))
            if overlap["enabled"]:
                overlap["active"] += 1
                overlap["peak"] = max(overlap["peak"], overlap["active"])
                if overlap["active"] == 4:
                    overlap_gate.set()
                try:
                    await asyncio.wait_for(overlap_gate.wait(), timeout=45)
                    await asyncio.sleep(.02)
                finally:
                    overlap["active"] -= 1
            return record

        guard.enter_context(mock.patch.object(manager, "_hmb_run_agent_shot", fake_compile))
        for node in generators:
            async def fake_submit(node=node):
                # This is a counted video-generation boundary, not a fake HTTP
                # response. All preceding production admission/tickets are real.
                node._assert_agent_result_available(allow_resume=False)
                params = node._resolve_exact_shot_generation_inputs(node._get_parameters())
                selected = params["_hmb_imageasset_project_selection"]
                assert isinstance(selected, dict) and selected
                sub = node._hmb_shot_channel_subscription()
                assert sub["enabled"] and sub["shot_uuid"] in exact_sources
                counters["submit"][node.name] += 1
                node._set_status_results(was_successful=True, result_details="OFFLINE counted generation boundary; no provider request")
            guard.enter_context(mock.patch.object(node, "_process_generation", fake_submit))

        async def run_case(name, invalid=(), *, concurrent=False):
            before = {kind: counters[kind].copy() for kind in counters}
            started = time.perf_counter()
            async def diagnose_pending():
                await asyncio.sleep(8)
                def await_chain(task):
                    chain, value, seen = [], task.get_coro(), set()
                    while value is not None and id(value) not in seen:
                        seen.add(id(value))
                        frame = getattr(value, "cr_frame", None) or getattr(value, "gi_frame", None)
                        if frame:
                            chain.append(dict(file=frame.f_code.co_filename, function=frame.f_code.co_name, line=frame.f_lineno))
                        value = getattr(value, "cr_await", None) or getattr(value, "gi_yieldfrom", None)
                    return chain
                pending = dict(case=name, states={n.name:str(n.state) for n in flow.nodes.values()},
                    counters={k:dict(v) for k,v in counters.items()},
                    tasks=[dict(name=task.get_name(), await_chain=await_chain(task), frames=[dict(file=f.f_code.co_filename, function=f.f_code.co_name, line=f.f_lineno)
                        for f in task.get_stack()]) for task in asyncio.all_tasks()])
                (out / (name + "-pending.json")).write_text(json.dumps(pending, indent=2), encoding="utf-8")
                import faulthandler
                with (out / (name + "-threads.txt")).open("w", encoding="utf-8") as stream:
                    faulthandler.dump_traceback(file=stream, all_threads=True)
            diagnostic = asyncio.create_task(diagnose_pending())
            try:
                if concurrent:
                    # Invoke the real asynchronous node entrypoints concurrently;
                    # the SDK whole-Flow queue above is independently exercised.
                    await asyncio.wait_for(asyncio.gather(*(node.aprocess() for node in generators)), timeout=120)
                    result = SimpleNamespace(result_details="Five real Generator aprocess entries completed", succeeded=lambda:True)
                    result_type = "ActualGeneratorAprocessGather"
                else:
                    host.REQUESTS += 1
                    result = await asyncio.wait_for(engine.ahandle_request(StartFlowRequest(flow_name=flow.name, broadcast_result=False)), timeout=120)
                    result_type = type(result).__name__
            finally:
                diagnostic.cancel()
            delta = {kind: {node.name: counters[kind][node.name] - before[kind][node.name] for node in generators} for kind in counters}
            values = {node.name: dict(status=str(node.parameter_output_values.get("generation_status", "")),
                successful=node.parameter_output_values.get("was_successful"),
                details=str(node.parameter_output_values.get("result_details", "")),
                mode=node._hmb_seedance_execution_mode(),
                task_id=str(node.parameter_output_values.get("generation_id", ""))) for node in generators}
            observation = dict(name=name, result_type=result_type, result_details=str(result.result_details),
                elapsed_seconds=time.perf_counter()-started,
                errors=[str(e) for e in getattr(result, "validation_exceptions", [])], delta=delta, outputs=values)
            observed.append(observation)
            (out / "flow-observations.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf-8")
            assert result.succeeded(), observation
            for node in generators:
                expected = 0 if node in invalid else 1
                assert delta["compile"][node.name] == delta["submit"][node.name] == expected, observation
                if node in invalid:
                    assert values[node.name]["successful"] is False and values[node.name]["status"] == "skipped", observation
                    assert values[node.name]["details"].startswith("SKIPPED:") and not values[node.name]["task_id"], observation
                else:
                    assert values[node.name]["successful"] is True, observation
            assert not getattr(manager, "_hmb_shot_request_records", {}), "Per-run exact tickets leaked"
            if concurrent:
                assert overlap["peak"] == overlap["peak_tickets"] == 4 and overlap["active"] == 0, overlap
            host.record(name, healthy=len(generators)-len(invalid), invalid=len(invalid),
                exact_compile_counts=delta["compile"], exact_generation_boundary_counts=delta["submit"],
                actual_entrypoint=result_type, peak_concurrent_exact_tickets=overlap["peak_tickets"] if concurrent else None,
                provider_calls=0)
            print("FIVE_SHOT_FLOW_PASS " + name, flush=True)

        first = generators[0]
        waiting = deepcopy(original_intents[0])
        waiting.update(shot_uuid="44444444-4444-4444-8444-444444444444", shot_name="Missing original Shot", revision=waiting["revision"]+1)
        if SELECTED_CASES == "all":
            await run_case("five_healthy_exact_shots")
            first.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA] = waiting
            routing.reconcile_shot_routing(first)
            assert first._hmb_seedance_execution_mode() == "waiting"
            await run_case("one_waiting_shot_four_continue", invalid=(first,))
            first.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA] = deepcopy(original_intents[0])
            routing.reconcile_shot_routing(first)
            await base.settle(lambda: first._hmb_seedance_execution_mode() == "shot")
            await run_case("repaired_original_uuid_revalidates_five")
            first._hmb_commit_seedance_mode()
            first._apply_seedance_shot_selection("", fallback_to_available=False)
            first.set_parameter_value("only_project", "", initial_setup=True)
            first.set_parameter_value("prompt", "Offline direct independent prompt", initial_setup=True)
            routing.reconcile_shot_routing(first)
            assert first._hmb_seedance_execution_mode() == "only"
            await run_case("one_only_project_missing_four_continue", invalid=(first,))
            first.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA] = deepcopy(original_intents[0])
            routing.reconcile_shot_routing(first)
            await base.settle(lambda: first._hmb_seedance_execution_mode() == "shot")
        if SELECTED_CASES in {"all", "tail"}:
            first.set_parameter_value("execution_expires_after", 1, initial_setup=True)
            try:
                first._validate_local_render_preflight()
            except ValueError as exc:
                assert "execution_expires_after" in str(exc), str(exc)
            else:
                raise AssertionError("The invalid fixture option did not reach the real validator")
            await run_case("one_invalid_model_option_four_continue", invalid=(first,))
            first.set_parameter_value("execution_expires_after", 172800, initial_setup=True)
            await run_case("corrected_option_five_continue_without_duplicates")
        first.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA] = waiting
        routing.reconcile_shot_routing(first)
        assert first._hmb_seedance_execution_mode() == "waiting"
        overlap["enabled"] = True
        await run_case("concurrent_one_waiting_four_exact_tickets_continue", invalid=(first,), concurrent=True)
        assert not host.ATTEMPTS
        (out / "native-flow-summary.json").write_text(json.dumps(dict(passed=True, cases=host.RESULTS,
            source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCTS},
            exact_shot_count=5, manager_count=1, native_flow_count=sum(row["result_type"] == "StartFlowResultSuccess" for row in observed),
            actual_aprocess_gather_count=1, selected_cases=SELECTED_CASES, actual_provider_requests=0,
            actual_model_requests=0, counted_fake_model_boundary=True, counted_fake_video_boundary=True,
            scope="Actual SDK whole Flow and HMB admission/manager-ticket execution; model and generation boundaries counted fakes; no video synthesis or HTTP submission."), ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    global SELECTED_CASES
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT/"reports/release809-local810-20261019/flow/five-shot-host")
    parser.add_argument("--cases", choices=("all", "tail", "concurrent"), default="all")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    SELECTED_CASES = args.cases
    before = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCTS}
    os.environ.pop("HMB_AGENT_POLICY_PATH", None)
    host.exercise = exercise
    host.run_phase("five-shot", out)
    after = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCTS}
    (out / "source-preservation.json").write_text(json.dumps(dict(before=before, after=after,
        stable=before == after, test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=2), encoding="utf-8")
    assert before == after, "Runtime source changed during actual SDK execution"
    print("HMB_FIVE_SHOT_LOCAL_FAILURE_HOST=PASS " + json.dumps(dict(cases=len(host.RESULTS), paid_calls=0)))


if __name__ == "__main__":
    main()
