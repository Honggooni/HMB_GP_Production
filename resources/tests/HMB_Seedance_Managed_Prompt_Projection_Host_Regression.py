"""Installed SDK, real Agent output edges, exact per-Generator saved prompts.

Only disposable synthetic nodes are authored. No Agent/model/Generator Run is
called. The existing isolated host harness blocks external and live sockets.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
import HMB_Seedance_Execution_Mode_Host_Regression as harness


def saved_prompt_values(path):
    tree = ast.parse(path.read_text("utf-8"))
    pool = ast.literal_eval(next(node.value for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
            and target.id == "top_level_unique_values_dict" for target in node.targets)))
    names = {}
    values = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Await)):
            outer = node.value.value.value
            call = outer.args[0] if isinstance(outer, ast.Call) and outer.args else None
            if isinstance(call, ast.Call) and ast.unparse(call.func).rsplit(".", 1)[-1] == "CreateNodeRequest":
                keywords = {item.arg: item.value for item in call.keywords}
                if isinstance(keywords.get("node_name"), ast.Constant):
                    names[node.targets[0].id] = keywords["node_name"].value
        if isinstance(node, ast.Call) and ast.unparse(node.func).rsplit(".", 1)[-1] == "SetParameterValueRequest":
            keywords = {item.arg: item.value for item in node.keywords}
            if not isinstance(keywords.get("parameter_name"), ast.Constant) or keywords["parameter_name"].value != "prompt":
                continue
            name = keywords.get("node_name")
            value = keywords.get("value")
            if isinstance(name, ast.Name) and isinstance(value, ast.Call) and value.args and isinstance(value.args[0], ast.Subscript):
                values[names[name.id]] = pool[ast.literal_eval(value.args[0].slice)]
    return values


async def exercise(engine, _phase, out):
    t = importlib.import_module("HMBSeedanceGeneration")
    agents = importlib.import_module("HMBAgentLibrary")
    images = importlib.import_module("HMBImageAssetLibrary")
    prompts = importlib.import_module("HMBPromptLibrary")
    routing = importlib.import_module("_hmb_shot_routing")
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
    from griptape_nodes.retained_mode.events.workflow_events import (
        SaveWorkflowFileFromSerializedFlowRequest, RunWorkflowWithCurrentStateRequest,
    )
    schema = harness.register(engine, {"HMBSeedanceGeneration": t, "HMBAgentLibrary": agents,
        "HMBImageAssetLibrary": images, "HMBPromptLibrary": prompts})
    engine.event_manager.initialize_queue()
    schedulers = {key: getattr(routing, key) for key in (
        "schedule_post_registration_reconcile", "schedule_post_hydration_reconcile")}
    with ExitStack() as guards:
        for key in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            guards.enter_context(mock.patch.object(routing, key, lambda *a, **k: False))
        guards.enter_context(mock.patch.object(t._HMBAIBrokerBridge, "_request_json", harness.deny))
        guards.enter_context(mock.patch.object(t.HMBSeedanceGeneration, "_process_generation", harness.deny))
        guards.enter_context(mock.patch.object(agents.HMBAgentLibrary, "_hmb_run_agent_shot", harness.deny))
        guards.enter_context(mock.patch.object(agents.HMBAgentLibrary, "_run_native_agent_once", harness.deny))
        flow_name = harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="ManagedPromptProjectionSDK")).flow_name
        source_created = harness.send(engine, CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name="Projection Image publisher", initial_setup=True, create_error_proxy_on_failure=False))
        publisher = engine.node_manager.get_node_by_name(source_created.node_name)
        state = images._default_state()
        state["shot_routing"].update(channel_uuid=harness.CHANNEL, publisher_instance_uuid=harness.PUBLISHER,
            generation=1, shots=[dict(row, selected_source_uids=[]) for row in harness.SHOTS],
            active_shot_uuid=harness.SHOTS[0]["shot_uuid"])
        publisher.set_parameter_value(images.WIDGET_STATE_PARAMETER, json.dumps(state), initial_setup=True)
        publisher._hmb_initial_catalog_scan_pending = False
        prompt_created = harness.send(engine, CreateNodeRequest(node_type="HMBPromptLibrary", specific_library_name=schema.name,
            node_name="Projection Prompt manager", initial_setup=True, create_error_proxy_on_failure=False))
        prompt_manager = engine.node_manager.get_node_by_name(prompt_created.node_name)
        prompt_state = prompt_manager._current_state()
        prompt_state["multi_shot_enabled"] = True
        prompt_state["text"]["PRESERVED_TEXT"] = "Synthetic exact Shot direction."
        prompt_manager.set_parameter_value(prompts.WIDGET_PARAMETER_NAME, prompts._json_dumps(prompt_state), initial_setup=True)
        created = harness.send(engine, CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name=schema.name,
            node_name="Projection Agent", initial_setup=True, create_error_proxy_on_failure=False))
        manager = engine.node_manager.get_node_by_name(created.node_name)
        catalog = publisher._hmb_shot_routing_catalog()
        manager._hmb_reconcile_shot_routing(catalog)
        template = manager._hmb_native_slot_snapshot()
        expected = {}
        for shot in harness.SHOTS:
            number = shot["number"]
            text = "" if number == 2 else f"Exact saved final instruction {number}"
            key = manager._hmb_slot_key(harness.CHANNEL, shot["shot_uuid"])
            slot = deepcopy(template)
            slot["outputs"] = {"output": text, "logs": "", "agent": None}
            slot["result"] = {}
            manager._hmb_shot_slots[key] = slot
            expected[number] = text
        manager.set_parameter_value("output", expected[1], initial_setup=True)
        manager.parameter_output_values["output"] = expected[1]
        manager._hmb_persist_shot_store()
        generators = []
        for shot in harness.SHOTS:
            number = shot["number"]
            created = harness.send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration", specific_library_name=schema.name,
                node_name=f"Projection Generator {number}", initial_setup=True,
                metadata={t.SEEDANCE_EXECUTION_MODE_METADATA: harness.intent(t, "shot", shot)}, create_error_proxy_on_failure=False))
            node = engine.node_manager.get_node_by_name(created.node_name)
            node._hmb_reconcile_shot_routing(catalog)
            harness.send(engine, CreateConnectionRequest(source_node_name=manager.name, source_parameter_name="output",
                target_node_name=node.name, target_parameter_name="prompt", initial_setup=True))
            generators.append(node)

        def verify(label):
            for number, node in enumerate(generators, 1):
                assert node._shot_identity()["shot_uuid"] == harness.SHOTS[number - 1]["shot_uuid"], (label, number, node._shot_identity(), node.metadata.get(t.SEEDANCE_EXECUTION_MODE_METADATA))
                assert node.get_parameter_value("prompt") == expected[number], (label, number, "native")
                assert node._get_raw_parameter_value("prompt") == expected[number], (label, number, "save")
                assert node.parameter_values["prompt"] == expected[number], (label, number, "stored")
            harness.record(label, Generators=5, exact_UUID=True, native_raw_and_stored_prompt_equal=True)

        verify("real_output_edges_project_five_distinct_results_including_unrun_empty_slot")
        for sequence, number in enumerate((1, 2, 3, 4, 5, 4, 3, 2, 1, 5, 3, 5, 1), 1):
            row = manager.get_parameter_by_name(agents._AGENT_SHOT_ROW_PREFIX + str(number))
            with ExitStack() as events:
                changes = [events.enter_context(mock.patch.object(node, "_emit_parameter_lifecycle_event",
                    wraps=node._emit_parameter_lifecycle_event)) for node in generators]
                command = deepcopy(manager.get_parameter_value(row.name))
                command["action"] = {"kind": "select", "request_id": f"{sequence:032x}", "expanded": True}
                harness.send(engine, SetParameterValueRequest(node_name=manager.name,
                    parameter_name=row.name, value=command))
                assert all(change.call_count == 0 for change in changes), [change.call_count for change in changes]
            verify(f"actual_native_agent_row_selection_{sequence}_to_{number}_keeps_all_generator_results")

        # Simulate only the public result publication of a completed inactive
        # worker. The native Run, model and render methods above remain denied.
        inactive = harness.SHOTS[1]
        key = manager._hmb_slot_key(harness.CHANNEL, inactive["shot_uuid"])
        expected[2] = "New inactive Shot 2 exact final instruction"
        manager._hmb_shot_slots[key]["outputs"]["output"] = expected[2]
        with (mock.patch.object(generators[0], "_emit_parameter_lifecycle_event", wraps=generators[0]._emit_parameter_lifecycle_event) as first,
              mock.patch.object(generators[1], "_emit_parameter_lifecycle_event", wraps=generators[1]._emit_parameter_lifecycle_event) as second):
            manager._hmb_notify_shot_preview(channel_uuid=harness.CHANNEL, shot_uuid=inactive["shot_uuid"])
            assert first.call_count == 0 and second.call_count == 1, (first.call_count, second.call_count)
        verify("inactive_shot_result_notifies_only_exact_generator_with_native_ui_event")

        # Every Shot receives a different completed public result. Updating an
        # inactive result must publish to exactly its own physical receiver;
        # the currently displayed Agent output is never a broadcast authority.
        for number in (5, 3, 4, 2, 1):
            shot = harness.SHOTS[number - 1]
            key = manager._hmb_slot_key(harness.CHANNEL, shot["shot_uuid"])
            expected[number] = f"Individually completed Shot {number} final instruction"
            manager._hmb_shot_slots[key]["outputs"]["output"] = expected[number]
            with ExitStack() as events:
                changes = [events.enter_context(mock.patch.object(node, "_emit_parameter_lifecycle_event",
                    wraps=node._emit_parameter_lifecycle_event)) for node in generators]
                manager._hmb_notify_shot_preview(channel_uuid=harness.CHANNEL, shot_uuid=shot["shot_uuid"])
                assert [change.call_count for change in changes] == [int(index == number)
                    for index in range(1, 6)], (number, [change.call_count for change in changes])
            verify(f"completed_shot_{number}_updates_only_its_own_generator")
        assert len(set(expected.values())) == 5 and all(expected.values())
        manager.set_parameter_value("output", expected[1], initial_setup=True)
        manager.parameter_output_values["output"] = expected[1]
        for sequence, number in enumerate((1, 2, 3, 4, 5, 4, 3, 2, 1, 3, 5, 1), 100):
            row = manager.get_parameter_by_name(agents._AGENT_SHOT_ROW_PREFIX + str(number))
            command = deepcopy(manager.get_parameter_value(row.name))
            command["action"] = {"kind": "select", "request_id": f"{sequence:032x}", "expanded": True}
            with ExitStack() as events:
                changes = [events.enter_context(mock.patch.object(node, "_emit_parameter_lifecycle_event",
                    wraps=node._emit_parameter_lifecycle_event)) for node in generators]
                harness.send(engine, SetParameterValueRequest(node_name=manager.name,
                    parameter_name=row.name, value=command))
                assert all(change.call_count == 0 for change in changes)
            verify(f"all_five_completed_outputs_survive_native_selection_{sequence}_to_{number}")
        manager._hmb_persist_shot_store()

        # The real SDK serializer must write per-target text, even while the
        # shared Agent is displaying a different Shot's public output.
        serialized = harness.send(engine, SerializeFlowToCommandsRequest(flow_name=flow_name)).serialized_flow_commands
        saved = out / "synthetic-exact-generator-prompts.py"
        await harness.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
            file_name=saved.stem, file_path=str(saved), display_name="Offline exact Generator prompts"))
        values = saved_prompt_values(saved)
        for number, node in enumerate(generators, 1):
            assert values[node.name] == expected[number], (number, values.get(node.name), expected[number])
        harness.record("actual_sdk_workflow_save_writes_exact_per_generator_prompt", Generators=5,
            path=str(saved), Agent_and_model_and_render_Run_calls=0)

        # Catalog notifications may reach the Agent before its Generators.
        # Name/number changes never change the immutable ownership of text.
        renamed = deepcopy(harness.SHOTS)
        renamed[1].update(number=5, name="Renamed original Shot 2")
        renamed[4].update(number=2, name="Renumbered original Shot 5")
        next_catalog = harness.catalog(t, shots=renamed, generation=2)
        manager._hmb_shot_catalog_snapshot = deepcopy(next_catalog)
        manager._hmb_notify_shot_preview(channel_uuid=harness.CHANNEL, shot_uuid=inactive["shot_uuid"])
        assert generators[1]._shot_identity()["shot_number"] == 2
        assert generators[1].get_parameter_value("prompt") == expected[2]
        assert generators[1].parameter_values["prompt"] == expected[2]
        harness.record("agent_rename_notification_before_generator_metadata_preserves_own_uuid_text")
        for node in generators:
            node._hmb_reconcile_shot_routing(next_catalog)
        assert generators[1]._shot_identity()["shot_number"] == 5
        assert generators[1]._shot_identity()["shot_name"] == "Renamed original Shot 2"
        assert generators[4]._shot_identity()["shot_number"] == 2
        verify("generator_metadata_catches_up_after_rename_renumber_without_blank_or_foreign_text")

        # Re-open the real generated workflow into the same disposable engine.
        # No original workflow or live desktop graph is read or replaced.
        names = [node.name for node in generators]
        await harness.asend(engine, ClearAllObjectStateRequest(i_know_what_im_doing=True))
        with ExitStack() as hydration:
            for key, callback in schedulers.items():
                hydration.enter_context(mock.patch.object(routing, key, callback))
            await harness.asend(engine, RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
            reopened_publisher = engine.node_manager.get_node_by_name(publisher.name)
            reopened_publisher._hmb_initial_catalog_scan_pending = False
            for _ in range(250):
                await asyncio.sleep(.02)
                reconciled = routing.reconcile_shot_routing(reopened_publisher)
                if reconciled.get("code") != "hydration_pending":
                    break
            assert reconciled.get("ok") is True and reconciled.get("code") != "hydration_pending", reconciled
        reopened = [engine.node_manager.get_node_by_name(name) for name in names]
        reopened_manager = engine.node_manager.get_node_by_name(manager.name)
        for number, node in enumerate(reopened, 1):
            assert node.get_parameter_value("prompt") == expected[number], (
                "reopen", number, "stored", node.parameter_values.get("prompt"),
                "visible", node.get_parameter_value("prompt"), "route", reconciled,
                "catalog_size", len(reopened_manager._hmb_shot_catalog_snapshot.get("shots", [])),
                "slot_count", len(reopened_manager._hmb_shot_slots))
            assert node._shot_identity()["shot_uuid"] == harness.SHOTS[number - 1]["shot_uuid"]
        for shot in harness.SHOTS:
            key = reopened_manager._hmb_slot_key(harness.CHANNEL, shot["shot_uuid"])
            assert reopened_manager._hmb_shot_slots[key]["outputs"]["output"] == expected[shot["number"]]
        harness.record("actual_sdk_cold_reopen_preserves_all_five_individual_agent_outputs_and_generator_prompts",
            Generators=5, distinct_nonempty_outputs=5, Agent_and_model_and_render_Run_calls=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports/agent-selection-responsiveness-20261020/managed-prompt-sdk")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    harness.PRODUCTS = ("HMBSeedanceGeneration.py", "HMBAgentLibrary.py")
    harness.exercise = exercise
    harness.run_phase("projection", args.out.resolve())
    result = json.loads((args.out / "projection-result.json").read_text("utf-8"))
    print(json.dumps({"passed": result["passed"], "cases": len(result["cases"]), "paid_calls": 0}))
    assert result["passed"]


if __name__ == "__main__":
    main()
