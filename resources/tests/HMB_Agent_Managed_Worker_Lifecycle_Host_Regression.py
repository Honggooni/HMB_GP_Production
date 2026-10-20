"""Isolated installed SDK managed workers and out-of-order native completions.

The actual facade, protected process, Standard Agent and TestModel runner are
used. Only model transport/account prerequisites and the synthetic Prompt
document source are supplied by this fixture. No live desktop, paid inference,
Broker, user files or policy DAT are accessed.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
import HMB_Seedance_Execution_Mode_Host_Regression as harness


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def subscription(row):
    return dict(schema="hmb-shot-channel-subscription", version=1,
        participant_kind="agent", enabled=True, channel_uuid=harness.CHANNEL,
        shot_uuid=row["shot_uuid"], shot_number=row["number"], shot_name=row["name"])


class PromptDocuments:
    _hmb_node_deleted = False

    def __init__(self, owner):
        self.owner = owner

    def _hmb_prompt_shot_document(self, *, channel_uuid, shot_uuid):
        assert channel_uuid == harness.CHANNEL
        rows = self.owner._hmb_shot_catalog_snapshot["shots"]
        row = next(item for item in rows if item["shot_uuid"] == shot_uuid)
        visible = "Literal approved input " + shot_uuid + " {{KEEP}} 0 OFF"
        machine = "Opaque approved machine input " + shot_uuid + " {{KEEP}} 0 OFF"
        return dict(schema="hmb-prompt-shot-document", version=1,
            subscription={**subscription(row), "participant_kind": "prompt"},
            visible_prompt=visible, machine_prompt=machine,
            paired_snapshot=dict(schema="hmb-prompt-paired-snapshot", version=1,
                generation=1, visible_sha256=sha(visible), machine_sha256=sha(machine), machine_prompt=machine),
            shot_context=dict(schema="hmb-agent-shot-context", version=1,
                channel_uuid=harness.CHANNEL, shot_uuid=shot_uuid,
                shot_number=row["number"], shot_name=row["name"], prompt_generation=1,
                visible_prompt_sha256=sha(visible), image_media_sha256=sha("[]"), video_media_sha256=sha("[]")),
            reference_media=dict(schema="hmb-agent-reference-media", version=1,
                machine_sha256=sha(machine), images=[], videos=[]),
            generation_context={}, project_identity=dict(project_id="katuri8", project_name="까투리8"))


async def exercise(engine, _phase, out):
    agents = importlib.import_module("HMBAgentLibrary")
    seedance = importlib.import_module("HMBSeedanceGeneration")
    routing = importlib.import_module("_hmb_shot_routing")
    base = agents.HMBAgentLibrary.__mro__[1]
    native_module = inspect.getmodule(base)
    from griptape_nodes_library.llm import runner as native_runner
    from pydantic_ai.models.test import TestModel
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest

    schema = harness.register(engine, {"HMBAgentLibrary": agents, "HMBSeedanceGeneration": seedance})
    engine.event_manager.initialize_queue()
    harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="ManagedWorkerLifecycle"))
    local = threading.local()
    gates = {}
    entered = {}
    native_calls = []
    native_agent_inputs = {}
    native_subscriptions = {}
    native_setting_inputs = {}
    failures = []
    original_processor = base._process
    original_run = native_module.run_agent

    def native_process(self, *args, **kwargs):
        local.owner = self
        try:
            return original_processor(self, *args, **kwargs)
        finally:
            local.owner = None

    def test_model(_config):
        worker = local.owner
        key = worker._hmb_shot_subscription["shot_uuid"]
        native_agent_inputs[key] = deepcopy(worker.parameter_values.get("agent"))
        native_subscriptions[key] = deepcopy(worker._hmb_shot_subscription)
        native_setting_inputs[key] = {name: deepcopy(worker.parameter_values.get(name))
            for name in ("agent", "agent_memory", "tools", "rulesets")}
        return TestModel(custom_output_text="Exact native output " + key, call_tools=[])

    def model_run(agent, prompt, **kwargs):
        worker = local.owner
        key = worker._hmb_shot_subscription["shot_uuid"]
        native_calls.append(key)
        entered[key].set()
        assert gates[key].wait(12), "in-memory model gate timed out"
        assert key in str(prompt)
        assert "{{KEEP}}" in str(prompt)
        return original_run(agent, prompt, **kwargs)

    async def wait_enter(key):
        for _ in range(1200):
            if entered[key].is_set():
                return
            await asyncio.sleep(.005)
        raise AssertionError("native model never entered: " + key)

    def new_manager(index):
        created = harness.send(engine, CreateNodeRequest(node_type="HMBAgentLibrary",
            specific_library_name=schema.name, node_name=f"Worker Manager {index}",
            initial_setup=True, create_error_proxy_on_failure=False))
        owner = engine.node_manager.get_node_by_name(created.node_name)
        owner._hmb_shot_catalog_snapshot = harness.catalog(importlib.import_module("HMBSeedanceGeneration"))
        source = PromptDocuments(owner)
        owner._hmb_manager_prompt_owner = lambda **kw: source
        # Synthetic document transport has no retained ImageAsset/Prompt tree.
        # Preview compilation is covered by the exact physical-edge host suite;
        # this fixture retains the native row, slot and worker publication path.
        owner._refresh_routed_prompt_preview = lambda: None
        owner._model_access.raise_if_selection_denied = lambda: None
        owner._hmb_active_slot_key = "__hmb_only__"
        template = owner._hmb_native_slot_snapshot()
        for row in harness.SHOTS:
            key = owner._hmb_slot_key(harness.CHANNEL, row["shot_uuid"])
            owner._hmb_shot_slots[key] = deepcopy(template)
            gates[row["shot_uuid"]] = threading.Event()
            entered[row["shot_uuid"]] = threading.Event()
        owner.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,
            owner._hmb_widget_value({"channel_uuid": harness.CHANNEL, **harness.SHOTS[0]},
                owner._hmb_shot_catalog_snapshot), initial_setup=True)
        return owner, source

    def run(owner, source, row, generator=None):
        return asyncio.create_task(owner._hmb_run_agent_shot(channel_uuid=harness.CHANNEL,
            shot_uuid=row["shot_uuid"], prompt_owner=source, generator=generator))

    def new_generator(owner, row, index):
        created = harness.send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration",
            specific_library_name=schema.name, node_name=f"Worker Wrapper Generator {index}",
            metadata={seedance.SEEDANCE_EXECUTION_MODE_METADATA: harness.intent(seedance, "shot", row)},
            initial_setup=True, create_error_proxy_on_failure=False))
        node = engine.node_manager.get_node_by_name(created.node_name)
        def current():
            found = next((item for item in owner._hmb_shot_catalog_snapshot["shots"]
                if item["shot_uuid"] == row["shot_uuid"]), None)
            return subscription(found) if found is not None else dict(enabled=False)
        # Physical publisher/edge/project discovery is synthetic here. Keep
        # the real retained Generator, current lifecycle, request snapshot,
        # worker await, native result/ticket and pre-submit guards unchanged.
        node._manual_agent_prompt_source = lambda: owner
        node._reconcile_shared_shot_routing = lambda **kw: None
        node._hmb_shot_channel_subscription = current
        node._hmb_seedance_execution_mode = lambda: "shot"
        node._hmb_test_input_changes = {}
        node._resolve_exact_shot_generation_inputs = lambda params: {**params, **node._hmb_test_input_changes,
            "_hmb_imageasset_project_selection": dict(project_id="katuri8", project_name="까투리8")}
        node._assert_imageasset_project_selection = lambda selection: None
        node._capture_generated_video_origin = lambda: {**current(),
            "source_node_instance_id": "isolated-generator-" + str(index)}
        return node

    with ExitStack() as guards:
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            guards.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
        guards.enter_context(mock.patch.object(base, "_process", native_process))
        guards.enter_context(mock.patch.object(native_runner, "build_model", test_model))
        guards.enter_context(mock.patch.object(native_module, "run_agent", model_run))
        guards.enter_context(mock.patch.object(native_module, "resolve_cloud_api_key", lambda: "offline-test-only"))
        guards.enter_context(mock.patch.object(native_module, "require_model_invocation_sync", lambda *a, **k: None))
        guards.enter_context(mock.patch.object(agents.HMBAgentLibrary, "_hmb_web_rerender_policy_status",
            lambda *a, **k: dict(ready=True, reason="project_policy_pending")))
        guards.enter_context(mock.patch.object(seedance._HMBAIBrokerBridge, "_request_json", harness.deny))
        guards.enter_context(mock.patch.object(seedance.HMBSeedanceGeneration, "_process_generation", harness.deny))

        owner, source = new_manager(1)
        targets = [SimpleNamespace(_hmb_node_deleted=False, is_cancellation_requested=False) for _ in harness.SHOTS]
        tasks = [run(owner, source, row, target) for row, target in zip(harness.SHOTS, targets)]
        for row in harness.SHOTS:
            await wait_enter(row["shot_uuid"])
        # One SDK-owned editor can move while all five frozen workers remain
        # independent. These setters execute the actual installed native form.
        for number in (1, 5, 2, 4, 3, 5):
            owner.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,
                owner._hmb_widget_value({"channel_uuid": harness.CHANNEL, **harness.SHOTS[number-1]},
                    owner._hmb_shot_catalog_snapshot))
        completed = []
        for row, task in reversed(list(zip(harness.SHOTS, tasks))):
            gates[row["shot_uuid"]].set()
            record = await asyncio.wait_for(task, 12)
            assert record["text"] == "Exact native output " + row["shot_uuid"], record["result"]
            assert record["result"]["inference_started"] is True
            completed.append(row["number"])
        assert completed == [5, 4, 3, 2, 1]
        for row, target in zip(harness.SHOTS, targets):
            key = owner._hmb_slot_key(harness.CHANNEL, row["shot_uuid"])
            record = owner._hmb_agent_shot_result(channel_uuid=harness.CHANNEL, shot_uuid=row["shot_uuid"])
            assert record["text"] == owner._hmb_shot_slots[key]["outputs"]["output"] == "Exact native output " + row["shot_uuid"]
            ticket = owner._hmb_agent_shot_result(channel_uuid=harness.CHANNEL, shot_uuid=row["shot_uuid"],
                run_id=record["result"]["run_id"], generator=target)
            assert ticket == record
        assert owner.parameter_output_values["output"] == "Exact native output " + harness.SHOTS[4]["shot_uuid"]
        native_saved_agent = deepcopy(owner.parameter_output_values["agent"])
        harness.record("five_actual_protected_workers_finish_reverse_order_while_editor_switches",
            workers=5, native_model_calls=5, exact_individual_results=True, paid_calls=0)

        # A queued worker must derive mutable name/number only once it owns
        # the per-UUID lock, so renaming a queued Shot cannot become a failure.
        for row in harness.SHOTS:
            label = f"queued_worker_refreshes_uuid_metadata_shot_{row['number']}"
            owner, source = new_manager("queued-" + str(row["number"]))
            key = owner._hmb_slot_key(harness.CHANNEL, row["shot_uuid"])
            lock = owner._hmb_shot_execution_locks.setdefault(key, threading.Lock())
            lock.acquire()
            task = run(owner, source, row)
            await asyncio.sleep(.06)
            owner._hmb_shot_catalog_snapshot["shots"][row["number"]-1]["name"] = "Renamed while queued"
            lock.release()
            gates[row["shot_uuid"]].set()
            try:
                record = await asyncio.wait_for(task, 12)
                assert record["shot"]["shot_name"] == "Renamed while queued"
                harness.record(label)
            except Exception as exc:
                failures.append(dict(case=label, error_type=type(exc).__name__, error=str(exc)))

        # Deleting/replacing a Shot while its old model is already running
        # must never create an admissible result or ticket for the old UUID.
        for kind in ("removed_shot", "prompt_replaced", "generator_deleted", "generator_cancelled", "manager_replaced", "renamed_renumbered_shot"):
            for row in harness.SHOTS:
                label = f"{kind}_late_completion_shot_{row['number']}_cannot_publish"
                manager_index = f"late-{kind}-{row['number']}"
                owner, source = new_manager(manager_index)
                target = SimpleNamespace(_hmb_node_deleted=False, is_cancellation_requested=False)
                task = run(owner, source, row, target)
                await wait_enter(row["shot_uuid"])
                held_gate = gates[row["shot_uuid"]]
                replacement = None
                if kind == "removed_shot":
                    owner._hmb_shot_catalog_snapshot["shots"] = [item for item in owner._hmb_shot_catalog_snapshot["shots"]
                        if item["shot_uuid"] != row["shot_uuid"]]
                elif kind == "prompt_replaced":
                    new_source = PromptDocuments(owner)
                    owner._hmb_manager_prompt_owner = lambda **kw: new_source
                elif kind == "generator_deleted":
                    target._hmb_node_deleted = True
                elif kind == "generator_cancelled":
                    target.is_cancellation_requested = True
                elif kind == "manager_replaced":
                    harness.send(engine, DeleteNodeRequest(node_name=owner.name))
                    replacement, _ = new_manager(manager_index)
                    assert replacement.name == owner.name and replacement is not owner
                elif kind == "renamed_renumbered_shot":
                    next_number = row["number"] % 5 + 1
                    for item in owner._hmb_shot_catalog_snapshot["shots"]:
                        if item["shot_uuid"] == row["shot_uuid"]:
                            item.update(number=next_number, name="Renamed after model entry")
                        elif item["number"] == next_number:
                            item["number"] = row["number"]
                held_gate.set()
                result = (await asyncio.gather(task, return_exceptions=True))[0]
                try:
                    if kind == "renamed_renumbered_shot":
                        assert isinstance(result, dict), "harmless name/number change rejected own UUID"
                        assert result["shot"]["shot_name"] == "Renamed after model entry"
                        assert result["shot"]["shot_number"] == next_number
                        assert result["text"] == "Exact native output " + row["shot_uuid"]
                        assert native_subscriptions[row["shot_uuid"]]["shot_name"] == row["name"]
                        assert native_subscriptions[row["shot_uuid"]]["shot_number"] == row["number"]
                        harness.record(label, frozen_model_subscription_preserved=True, latest_record_display_metadata=True)
                        continue
                    assert isinstance(result, BaseException), "lost owner published a new native result"
                    assert not owner._hmb_agent_shot_result(channel_uuid=harness.CHANNEL, shot_uuid=row["shot_uuid"])
                    assert not owner._hmb_shot_request_records
                    if replacement is not None:
                        assert not replacement._hmb_shot_results and not replacement._hmb_shot_request_records
                    harness.record(label)
                except Exception as exc:
                    failures.append(dict(case=label, error_type=type(exc).__name__, error=str(exc)))

        # A legacy durable store can contain only its authored active Shot,
        # without the new manager's neutral settings template. Executing an
        # unvisited Shot must not import another Shot's native conversation.
        owner, source = new_manager(4)
        row = harness.SHOTS[3]
        key = owner._hmb_slot_key(harness.CHANNEL, row["shot_uuid"])
        owner._hmb_shot_slots.pop(key, None)
        owner._hmb_shot_slots.pop("__hmb_default_settings__", None)
        owner.set_parameter_value("agent", native_saved_agent)
        gates[row["shot_uuid"]].set()
        await asyncio.wait_for(run(owner, source, row), 12)
        try:
            assert native_agent_inputs[row["shot_uuid"]] is None, "unvisited Shot inherited another Shot's native conversation"
            harness.record("missing_legacy_template_never_imports_another_shot_native_conversation")
        except Exception as exc:
            failures.append(dict(case="missing_legacy_template_never_imports_another_shot_native_conversation",
                error_type=type(exc).__name__, error=str(exc)))

        # Neutralization applies only to a brand-new fallback. Every authored
        # Shot's explicit conversation, tools, rules and OFF/0 memory survive
        # into its own real native worker and remain in its durable settings.
        for row in harness.SHOTS:
            owner, source = new_manager("authored-" + str(row["number"]))
            other = harness.SHOTS[row["number"] % 5]
            owner.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,
                owner._hmb_widget_value({"channel_uuid": harness.CHANNEL, **other},
                    owner._hmb_shot_catalog_snapshot))
            key = owner._hmb_slot_key(harness.CHANNEL, row["shot_uuid"])
            expected = dict(agent=deepcopy(native_saved_agent),
                tools=[dict(tool_type="Calculator")],
                rulesets=[dict(name="Authored Shot " + str(row["number"]), rules=["Keep this authored literal."])],
                agent_memory=dict(runs=[dict(input="Own history " + str(row["number"]), output="Own answer")],
                    explicit_zero=0, explicit_off=False))
            owner._hmb_shot_slots[key]["values"].update(deepcopy(expected))
            before = deepcopy(owner._hmb_shot_slots[key]["values"])
            gates[row["shot_uuid"]].set()
            result = await asyncio.wait_for(run(owner, source, row), 12)
            assert result["text"] == "Exact native output " + row["shot_uuid"]
            assert native_setting_inputs[row["shot_uuid"]] == expected
            assert owner._hmb_shot_slots[key]["values"] == before
            assert type(native_setting_inputs[row["shot_uuid"]]["agent_memory"]["explicit_zero"]) is int
            assert native_setting_inputs[row["shot_uuid"]]["agent_memory"]["explicit_off"] is False
            harness.record(f"authored_native_tools_rulesets_memory_shot_{row['number']}_preserved")

        # Exercise the Generator wrapper awaiting the actual protected model
        # worker, not a prewritten fake result. No generation method is called.
        for kind in ("queued_rename", "inference_rename", "post_return_rename", "removed_shot", "media_settings_changed"):
            for row in harness.SHOTS:
                index = f"wrapper-{kind}-{row['number']}"
                owner, source = new_manager(index)
                node = new_generator(owner, row, index)
                key = owner._hmb_slot_key(harness.CHANNEL, row["shot_uuid"])
                lock = None
                if kind == "post_return_rename":
                    original_run_api = owner._hmb_run_agent_shot
                    async def run_then_rename(**kwargs):
                        record = await original_run_api(**kwargs)
                        # Inject an editor catalog update after the native
                        # model/ticket is committed, immediately before the
                        # Generator wrapper resumes. The immutable result and
                        # ticket themselves remain byte-for-byte untouched.
                        owner._hmb_shot_catalog_snapshot["shots"][row["number"]-1]["name"] = "Changed after result returned"
                        return record
                    owner._hmb_run_agent_shot = run_then_rename
                if kind == "queued_rename":
                    lock = owner._hmb_shot_execution_locks.setdefault(key, threading.Lock())
                    lock.acquire()
                task = asyncio.create_task(node._prepare_managed_agent_shot())
                if kind == "queued_rename":
                    await asyncio.sleep(.06)
                else:
                    await wait_enter(row["shot_uuid"])
                if kind == "media_settings_changed":
                    # The immutable Shot is unchanged, but input edits while
                    # the native model runs must invalidate its old prompt.
                    changes = (
                        {"reference_images": ["file:///synthetic-new-image.png"]},
                        {"video_references": ["file:///synthetic-new-video.mov"]},
                        {"resolution": "480p"},
                        {"video_reference_slots": [{"video": "first"}, {"video": "second"}]},
                        {"duration": 9, "reference_audio": ["file:///synthetic-new-audio.wav"]},
                    )
                    node._hmb_test_input_changes.update(changes[row["number"]-1])
                elif kind == "removed_shot":
                    owner._hmb_shot_catalog_snapshot["shots"] = [item for item in owner._hmb_shot_catalog_snapshot["shots"]
                        if item["shot_uuid"] != row["shot_uuid"]]
                elif kind != "post_return_rename":
                    owner._hmb_shot_catalog_snapshot["shots"][row["number"]-1]["name"] = "Current wrapper row name"
                if lock is not None:
                    lock.release()
                gates[row["shot_uuid"]].set()
                result = (await asyncio.gather(task, return_exceptions=True))[0]
                if kind == "media_settings_changed":
                    assert isinstance(result, seedance._AgentResultUnavailable), result
                    assert "media or generation settings changed" in str(result), result
                    # The staged old result remains releasable for the real
                    # Generator finally path; none of it is admitted to submit.
                    managed = node._hmb_managed_agent_request
                    assert managed["record"]["text"] == "Exact native output " + row["shot_uuid"]
                    assert not getattr(node,"_hmb_agent_submission_prompt",None)
                    owner._hmb_release_agent_shot_result(channel_uuid=harness.CHANNEL, shot_uuid=row["shot_uuid"],
                        run_id=managed["record"]["result"]["run_id"], generator=node)
                    assert not owner._hmb_agent_shot_result(channel_uuid=harness.CHANNEL, shot_uuid=row["shot_uuid"],
                        run_id=managed["record"]["result"]["run_id"], generator=node)
                    node._hmb_managed_agent_request = None
                elif kind == "removed_shot":
                    assert isinstance(result, BaseException), "Generator accepted removed native Shot"
                    assert not getattr(node, "_hmb_managed_agent_request", None)
                    assert not owner._hmb_shot_request_records
                else:
                    assert result is None, result
                    managed = node._hmb_managed_agent_request
                    assert managed["record"]["text"] == "Exact native output " + row["shot_uuid"]
                    if kind == "post_return_rename":
                        assert managed["record"]["shot"]["shot_name"] == row["name"]
                        assert node._hmb_shot_channel_subscription()["shot_name"] == "Changed after result returned"
                    else:
                        assert managed["record"]["shot"]["shot_name"] == "Current wrapper row name"
                    node._assert_agent_result_available(allow_resume=False)
                    assert node._hmb_agent_submission_prompt == managed["record"]["text"]
                harness.record(f"generator_wrapper_real_native_worker_{kind}_shot_{row['number']}",
                    exact_native_result_and_ticket=True, broker_calls=0)

        owner, source = new_manager("five-wrapper-concurrent")
        nodes = [new_generator(owner, row, "concurrent-" + str(row["number"])) for row in harness.SHOTS]
        tasks = [asyncio.create_task(node._prepare_managed_agent_shot()) for node in nodes]
        for row in harness.SHOTS:
            await wait_enter(row["shot_uuid"])
        for row, node, task in reversed(list(zip(harness.SHOTS, nodes, tasks))):
            gates[row["shot_uuid"]].set()
            await asyncio.wait_for(task, 12)
            node._assert_agent_result_available(allow_resume=False)
            assert node._hmb_agent_submission_prompt == "Exact native output " + row["shot_uuid"]
            assert node._get_parameters()["prompt"] == node._hmb_agent_submission_prompt
            for foreign in nodes:
                if foreign is node:
                    continue
                assert not owner._hmb_agent_shot_result(channel_uuid=harness.CHANNEL,
                    shot_uuid=row["shot_uuid"], run_id=node._hmb_managed_agent_request["record"]["result"]["run_id"],
                    generator=foreign)
        harness.record("five_actual_generator_wrappers_await_native_workers_reverse_order_keep_exact_submission",
            generators=5, mismatched_ticket_admissions=0, broker_calls=0)

        (out / "observations.json").write_text(json.dumps(dict(failures=failures,
            native_calls=len(native_calls), cases=harness.RESULTS), indent=2), encoding="utf-8")
        assert not failures, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports/critical-agent-isolation-20261020/native-worker")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    harness.PRODUCTS = ("HMBAgentLibrary.py", "HMBSeedanceGeneration.py")
    harness.exercise = exercise
    harness.run_phase("worker", args.out.resolve())
    result = json.loads((args.out / "worker-result.json").read_text("utf-8"))
    print(json.dumps(dict(passed=result["passed"], cases=len(result["cases"]), paid_calls=0)))
    assert result["passed"]


if __name__ == "__main__":
    main()
