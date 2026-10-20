"""Actual SDK Shot add/delete delivery; private synthetic flow and media only.

Measures retained request and next-turn catalog publication separately.  It
does not establish desktop paint latency or run models/providers/renders.
"""
from __future__ import annotations

import asyncio
import cProfile
from collections import Counter
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("_hmb_shot_add_base", Path(__file__).with_name(
    "HMB_Library_Lifecycle_Order_Host_Regression.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
RESULTS = []


async def exercise(engine, modules, project_state, order, label, replacement=None):
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    import _hmb_shot_routing as routing

    captured = {}
    original_graph, original_unregister = base.assert_graph, LibraryRegistry.unregister_library
    cleanup = []
    def capture(*args, **kwargs):
        result = original_graph(*args, **kwargs)
        captured.update(flow=args[1], nodes=args[2], shots=args[3])
        return result
    with mock.patch.object(base, "assert_graph", capture), mock.patch.object(
            LibraryRegistry, "unregister_library", side_effect=lambda *a, **k: cleanup.append((a, k))):
        await ORIGINAL_SCENARIO(engine, modules, project_state, order, label, replacement)
    nodes = captured["nodes"]
    images, _, prompts, agents, _finishes, _generators = (modules[k] for k in base.KINDS)
    source, picker, prompt, agent, finish = (nodes[k] for k in base.KINDS[:5])
    generators = nodes[base.KINDS[5]]
    full_shots = deepcopy(source._current_state()["shot_routing"]["shots"])
    exact_bindings = {node.name: node._hmb_shot_channel_subscription()["shot_uuid"] for node in generators}
    if os.environ.get("HMB_SHOT_ADD_EXPLICIT_INTENT") == "1":
        for node in generators:
            node._hmb_commit_seedance_mode(exact_bindings[node.name])
    current_agent = agent._hmb_shot_channel_subscription()
    original_outputs = {}
    for shot in full_shots:
        key = agent._hmb_slot_key(base.CHANNEL, shot["shot_uuid"])
        slot = deepcopy(agent._hmb_shot_slots[key])
        slot["outputs"]["output"] = "Exact immutable output " + shot["shot_uuid"]
        agent._hmb_shot_slots[key] = slot
        original_outputs[shot["shot_uuid"]] = slot["outputs"]["output"]
    # Capture current native output before switching away, matching real edit
    # ownership; otherwise its first legitimate capture would replace our seed.
    agent.parameter_output_values["output"] = original_outputs[current_agent["shot_uuid"]]
    agent._hmb_notify_shot_preview()
    catalogs = (picker, prompt, agent, finish, *generators)
    events, passes = Counter(), []
    real_event, real_reconcile = engine.event_manager.put_event, routing.reconcile_shot_routing
    def event(value):
        events[type(value).__name__] += 1
        return real_event(value)
    def reconcile(*args, **kwargs):
        started = time.perf_counter()
        result = real_reconcile(*args, **kwargs)
        passes.append(dict(ms=round((time.perf_counter()-started)*1000, 3), code=result.get("code")))
        return result
    def catalog_rows(node):
        if node is picker:
            value = getattr(node, "_hmb_shot_catalog_snapshot", {}) or {}
        elif node is prompt:
            value = {"shots": node._current_state().get("image_asset", {}).get("shot_catalog", [])}
        elif node is finish:
            value = node._widget_state.get("shot_catalog") or {}
        elif node is agent:
            value = getattr(node, "_hmb_shot_catalog_snapshot", {}) or {}
        else:
            value = getattr(node, "_hmb_shot_catalog_snapshot", {}) or {}
        return [(row["shot_uuid"], row["number"], row["name"]) for row in value.get("shots", [])]
    def edit(rows):
        state = source._current_state()
        route = deepcopy(state["shot_routing"])
        route["shots"] = [dict(deepcopy(row), number=index) for index, row in enumerate(rows, 1)]
        route["generation"] += 1
        if route["active_shot_uuid"] not in {row["shot_uuid"] for row in rows}:
            route["active_shot_uuid"] = rows[0]["shot_uuid"]
        value = dict(schema=images.IMAGE_ASSET_EDIT_SCHEMA, version=1,
            scan_revision=state["scan_revision"], ui_edit_revision=state[images.UI_EDIT_REVISION_KEY]+1,
            catalog_identity={key:state[key] for key in ("catalog_root", "project_root", "project_uid",
                "project_cache_uid", "manifest_signature", "folder_signature", "scan_revision")},
            selected_source_uids=[row["source_uid"] for row in sorted(state["assets"],
                key=lambda row:row["selection_order"]) if row["selected"]],
            edits={"shot_routing":route})
        base.send(engine, SetParameterValueRequest(node_name=source.name,
            parameter_name=images.WIDGET_STATE_PARAMETER, value=json.dumps(value)))
    try:
        with mock.patch.object(engine.event_manager, "put_event", event), mock.patch.object(
                routing, "reconcile_shot_routing", reconcile):
            for seed in (7, 29, 503):
                rng = random.Random(seed)
                # Shrink to one, then restore the exact retained UUIDs in random
                # insertion order. Display numbering remains current catalog
                # order; histories and Generator ownership remain UUID based.
                remaining = [deepcopy(full_shots[0])]
                transitions = [("shrink", deepcopy(remaining))]
                shuffled = deepcopy(full_shots[1:]); rng.shuffle(shuffled)
                for shot in shuffled:
                    remaining.append(shot)
                    remaining.sort(key=lambda row:row["number"])
                    transitions.append(("add", deepcopy(remaining)))
                # Rename all rows, then remove and recreate each 2..5 member.
                for victim in rng.sample(full_shots[1:], 4):
                    rows = [deepcopy(row) for row in remaining if row["shot_uuid"] != victim["shot_uuid"]]
                    transitions.append(("delete", rows))
                    transitions.append(("restore", deepcopy(remaining)))
                victim = rng.choice(full_shots[1:])
                new_uuid = f"44444444-4444-4444-8444-{seed:012d}"
                replacement_rows = [dict(deepcopy(row), shot_uuid=new_uuid)
                    if row["shot_uuid"] == victim["shot_uuid"] else deepcopy(row) for row in remaining]
                transitions.append(("replace_uuid", replacement_rows))
                transitions.append(("restore_uuid", deepcopy(remaining)))
                for operation, rows in transitions:
                    expected = [(row["shot_uuid"], index, row["name"]) for index, row in enumerate(rows, 1)]
                    available_ids = {row["shot_uuid"] for row in rows}
                    # A Generator waiting for a deleted exact UUID deliberately
                    # rejects unrelated catalogs. It must receive the newest
                    # catalog immediately when its own UUID returns.
                    recipients = [node for node in catalogs if node not in generators
                        or not node._hmb_seedance_requested_shot_identity()
                        or exact_bindings[node.name] in available_ids]
                    prior_events, prior_passes = events.copy(), len(passes)
                    profile = cProfile.Profile() if os.environ.get("HMB_SHOT_ADD_PROFILE") == "1" and not RESULTS else None
                    if profile is not None:
                        profile.enable()
                    start = time.perf_counter()
                    edit(rows)
                    request_ms = (time.perf_counter()-start)*1000
                    missing = [node.name for node in recipients if catalog_rows(node) != expected]
                    # No sleep/debounce hidden in the acceptance predicate.
                    # Run only scheduled retained callbacks until all received.
                    turns = 0
                    deadline = time.perf_counter()+4
                    while missing and time.perf_counter()<deadline:
                        await asyncio.sleep(0)
                        turns += 1
                        missing = [node.name for node in recipients if catalog_rows(node) != expected]
                    assert not missing, dict(operation=operation, missing=missing,
                        expected=expected, actual={node.name:catalog_rows(node) for node in catalogs})
                    elapsed_ms = (time.perf_counter()-start)*1000
                    rebound = lambda: all(node._hmb_shot_channel_subscription()["shot_uuid"] == exact_bindings[node.name]
                        for node in generators if exact_bindings[node.name] in {row["shot_uuid"] for row in rows})
                    while not rebound() and time.perf_counter()<deadline:
                        await asyncio.sleep(0)
                        turns += 1
                    for node in generators:
                        sub = node._hmb_shot_channel_subscription()
                        if exact_bindings[node.name] in {row["shot_uuid"] for row in rows}:
                            assert sub["shot_uuid"] == exact_bindings[node.name], ("reassigned", node.name,
                                dict(sub=sub, suspended=getattr(node,"_hmb_suspended_shot_identity",None),
                                    intent=node._hmb_seedance_mode_intent(), status=getattr(node,"_hmb_shot_route_status",{})),
                                {target.name:dict(sub=target._hmb_shot_channel_subscription(),
                                    suspended=getattr(target,"_hmb_suspended_shot_identity",None),
                                    intent=target._hmb_seedance_mode_intent()) for target in generators},passes[prior_passes:])
                    for shot in full_shots:
                        key = agent._hmb_slot_key(base.CHANNEL, shot["shot_uuid"])
                        assert agent._hmb_shot_slots[key]["outputs"]["output"] == original_outputs[shot["shot_uuid"]]
                    if operation == "replace_uuid":
                        replacement_output = agent._hmb_agent_shot_preview(channel_uuid=base.CHANNEL,
                            shot_uuid=new_uuid)
                        assert replacement_output is None or replacement_output["text"] == "", (
                            "output_reused_for_new_UUID", replacement_output)
                        for node in generators:
                            if exact_bindings[node.name] == victim["shot_uuid"]:
                                assert node._hmb_seedance_execution_mode() == "waiting"
                                assert node._hmb_seedance_requested_shot_identity()["shot_uuid"] == victim["shot_uuid"]
                    if len(rows)==5:
                        for node in generators:
                            if exact_bindings[node.name] not in available_ids:
                                continue
                            expected_text = original_outputs[exact_bindings[node.name]]
                            actual_text = node._get_raw_parameter_value("prompt")
                            assert actual_text == expected_text, (node.name, expected_text, actual_text)
                    record=dict(seed=seed, operation=operation, shots=len(rows),
                        native_request_ms=round(request_ms,3), all_catalogs_ms=round(elapsed_ms,3),
                        event_loop_turns=turns, recipients=len(recipients),
                        passes=passes[prior_passes:], events=dict(events-prior_events))
                    RESULTS.append(record)
                    print("SHOT_ADD_DELIVERY_CASE "+json.dumps(record), flush=True)
                    if profile is not None:
                        profile.disable()
                        profile.print_stats(sort="cumulative")
            assert not base.ATTEMPTS
    finally:
        for args, kwargs in cleanup:
            original_unregister(*args, **kwargs)


ORIGINAL_SCENARIO = base.scenario
def main():
    base.scenario = exercise
    with mock.patch.dict(os.environ, {"HMB_LIFECYCLE_CASE":"LifecycleOrder0"}):
        base.main()
    print("HMB_SHOT_ADD_IMMEDIATE_DELIVERY_HOST=PASS "+json.dumps(dict(
        cases=len(RESULTS), maximum_native_request_ms=max(row["native_request_ms"] for row in RESULTS),
        maximum_catalog_delivery_ms=max(row["all_catalogs_ms"] for row in RESULTS),
        maximum_event_loop_turns=max(row["event_loop_turns"] for row in RESULTS),
        independent_outputs=5, paid_calls=0, live_graph_calls=0)))

if __name__ == "__main__":
    main()
