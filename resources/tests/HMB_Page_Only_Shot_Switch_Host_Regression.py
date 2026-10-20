"""Actual SDK: page-only reads never rebuild an Agent execution document.

All nodes, five-Shot media references and saved files are synthetic and live in
a private profile. Model/provider/Broker/desktop transports are forbidden. The
existing native accordion and cold Prompt source fixtures supply independent
input, output, list-child, connection and serialization assertions; this test
adds strict zero-work guards at the new presentation-only boundary.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import statistics
import sys
import time
import types
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
sys.dont_write_bytecode = True
RESULTS = []
ATTEMPTS = []
METRICS = {}


def deny(*args, **kwargs):
    ATTEMPTS.append("forbidden_transport_or_execution")
    raise AssertionError("Page-only host fixture must not execute models, render or access a live service")


def record(name, **details):
    RESULTS.append(dict(name=name, passed=True, **details))


def summary(numbers):
    numbers = sorted(numbers)
    return dict(samples=len(numbers), minimum_ms=round(numbers[0], 4),
        median_ms=round(statistics.median(numbers), 4),
        p95_ms=round(numbers[min(len(numbers) - 1, int(len(numbers) * .95))], 4),
        maximum_ms=round(numbers[-1], 4))


def check_views(prompt, prompts, images, pickers, rows, channel, *, label):
    """Warm first; only repeated presentation reads are inside the guards."""
    expected = {}
    for row in rows:
        view = prompt._hmb_prompt_shot_view(channel_uuid=channel, shot_uuid=row["shot_uuid"])
        assert isinstance(view, dict) and view.get("visible_prompt"), (label, row["number"], view)
        assert view["subscription"]["shot_uuid"] == row["shot_uuid"]
        assert view["subscription"]["channel_uuid"] == channel
        expected[row["shot_uuid"]] = deepcopy(view)
    counts = Counter()
    samples = []
    targets = ((prompts, "_normalize_state"),
        (prompts.HMBPromptLibrary, "_compiled_prompt_pair_for_state"),
        (prompts.HMBPromptLibrary, "_apply_exact_shot_routes"),
        (prompts.HMBPromptLibrary, "_hmb_prompt_shot_document"),
        (prompts.HMBPromptLibrary, "_hmb_agent_reference_media"),
        (prompts.HMBPromptLibrary, "_hmb_agent_generation_context"),
        (images.HMBImageAssetLibrary, "_hmb_shot_routing_snapshot_for"),
        (pickers.HMBVideoPickerLibrary, "_hmb_shot_routing_snapshot_for"))
    with ExitStack() as guards:
        for owner, name in targets:
            def expensive(*args, _name=name, **kwargs):
                counts[_name] += 1
                raise AssertionError("Presentation view performed execution work: " + _name)
            guards.enter_context(mock.patch.object(owner, name, expensive))
        for number in ([1, 2, 3, 4, 5, 4, 3, 2, 1, 5, 3, 2] * 10):
            row = rows[number - 1]
            started = time.perf_counter_ns()
            view = prompt._hmb_prompt_shot_view(channel_uuid=channel, shot_uuid=row["shot_uuid"])
            samples.append((time.perf_counter_ns() - started) / 1e6)
            assert view == expected[row["shot_uuid"]], (label, number)
        # The caller cannot poison the reusable owner-owned presentation data.
        row = rows[2]
        view = prompt._hmb_prompt_shot_view(channel_uuid=channel, shot_uuid=row["shot_uuid"])
        view["visible_prompt"] = "Synthetic caller mutation must remain private"
        view["subscription"]["shot_uuid"] = "wrong-caller-uuid"
        assert prompt._hmb_prompt_shot_view(channel_uuid=channel,
            shot_uuid=row["shot_uuid"]) == expected[row["shot_uuid"]]
        assert not prompt._hmb_prompt_shot_view(channel_uuid="unrelated-channel", shot_uuid=row["shot_uuid"])
        assert not prompt._hmb_prompt_shot_view(channel_uuid=channel, shot_uuid="deleted-or-replaced-uuid")
    assert not counts, counts
    METRICS[label] = {**summary(samples), "execution_or_source_build_calls": dict(counts)}
    record(label, repeated_views=len(samples), expensive_calls=0, shots=5,
        own_UUID_and_literal_preserved=True, returned_view_isolated=True)
    return expected


def prompt_native_pages(engine, prompt, prompts, images, pickers, cold):
    """Send the same full-state page selections the existing widget emits."""
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    counts = Counter()
    samples = []
    observations = []
    before_outputs = deepcopy(dict(prompt.parameter_output_values))
    for number in (2, 1, 5, 4, 3, 2, 5, 1, 3, 4, 2, 1):
        row = cold.ROWS[number - 1]
        # Browser serialization and normalizing its received authoritative
        # state happen before this native request measurement/zero-work guard.
        selected = prompts._select_prompt_shot_document(prompt._current_state(),
            {**row, "channel_uuid": cold.CHANNEL})
        selected["ui"]["shot_editor_expanded"] = True
        selected[prompts.UI_EDIT_REVISION_KEY] = int(selected.get(prompts.UI_EDIT_REVISION_KEY) or 0) + 1
        selected = prompts._store_prompt_shot_document(prompts._normalize_state(selected))
        serialized = prompts._json_dumps(selected)
        before_count = Counter(counts)
        observation = {"shot": number, "predicate": []}
        with ExitStack() as guards:
            targets = ((prompts.HMBPromptLibrary, "_compiled_prompt_pair_for_state"),
                (prompts.HMBPromptLibrary, "_apply_exact_shot_routes"),
                (prompts.HMBPromptLibrary, "_sync_prompt_output_now"),
                (prompts.HMBPromptLibrary, "_sync_prompt_output_from_state"),
                (prompts.HMBPromptLibrary, "_schedule_prompt_sync"),
                (images.HMBImageAssetLibrary, "_hmb_shot_routing_snapshot_for"),
                (pickers.HMBVideoPickerLibrary, "_hmb_shot_routing_snapshot_for"))
            for owner, name in targets:
                def expensive(*args, _name=name, **kwargs):
                    counts[_name] += 1
                    raise AssertionError("Page-only native write performed execution work: " + _name)
                guards.enter_context(mock.patch.object(owner, name, expensive))
            original_normalize = prompts._normalize_state
            def normalize(*args, **kwargs):
                counts["normalization_calls"] += 1
                return original_normalize(*args, **kwargs)
            guards.enter_context(mock.patch.object(prompts, "_normalize_state", normalize))
            original_predicate = prompts._prompt_page_only_write
            def predicate(previous, incoming):
                answer = original_predicate(previous, incoming)
                before = prompts._parse_state(previous) if not isinstance(previous, dict) else previous
                after = prompts._parse_state(incoming) if not isinstance(incoming, dict) else incoming
                observation["predicate"].append({"answer": answer,
                    "before_shot": before.get("shot", {}).get("number"),
                    "after_shot": after.get("shot", {}).get("number")})
                return answer
            guards.enter_context(mock.patch.object(prompts, "_prompt_page_only_write", predicate))
            started = time.perf_counter_ns()
            cold.send(engine, SetParameterValueRequest(node_name=prompt.name,
                parameter_name=prompts.WIDGET_PARAMETER_NAME, value=serialized))
            samples.append((time.perf_counter_ns() - started) / 1e6)
        observation["calls"] = dict(counts - before_count)
        observations.append(observation)
        assert prompt._current_state()["shot"]["shot_uuid"] == row["shot_uuid"]
        assert prompt.parameter_output_values == before_outputs, (number, "A page flip published a different execution result")
    METRICS["prompt_native_page_writes"] = {**summary(samples), "calls": dict(counts), "observations": observations}
    assert not {key: value for key, value in counts.items() if key != "normalization_calls"}, counts
    record("prompt_native_widget_page_writes_do_not_recompile_query_or_publish", native_requests=len(samples),
        execution_build_calls=0, source_queries=0, output_publication=0,
        normalization_calls=counts["normalization_calls"])


def missing_display_callback_does_not_requeue_itself(prompt, row, channel):
    """An unready source notification may re-enter its own display getter."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    queued = []
    notifications = []
    class PrivateLoop:
        def is_running(self):
            return True
        def call_soon_threadsafe(self, callback):
            queued.append(callback)
    def refresh(source, parameter_name):
        assert source is prompt and parameter_name == "PROMPT_OUT"
        notifications.append(True)
        assert not prompt._hmb_prompt_shot_view(channel_uuid=channel, shot_uuid=row["shot_uuid"])
    consumer = types.SimpleNamespace(lock=False, _hmb_hydrate_shot_prompt_from_source=refresh)
    edge = types.SimpleNamespace(source_node=prompt, target_node=consumer)
    connections = types.SimpleNamespace(get_outgoing_connections_from_parameter=lambda *a: [edge])
    event_manager = types.SimpleNamespace(event_loop=PrivateLoop())
    flow_manager = types.SimpleNamespace(get_connections=lambda: connections)
    cache = prompt._hmb_prompt_shot_views
    old_pending = getattr(prompt, "_hmb_prompt_view_warmup_pending", False)
    prompt._hmb_prompt_shot_views = {}
    prompt._hmb_prompt_view_warmup_pending = False
    try:
        with (mock.patch.object(GriptapeNodes, "EventManager", return_value=event_manager),
              mock.patch.object(GriptapeNodes, "FlowManager", return_value=flow_manager),
              mock.patch.object(prompt, "_hmb_prepare_prompt_shot_views", return_value=None) as prepare):
            assert not prompt._hmb_prompt_shot_view(channel_uuid=channel, shot_uuid=row["shot_uuid"])
            assert len(queued) == 1 and prompt._hmb_prompt_view_warmup_pending is True
            queued.pop(0)()
            prepare.assert_called_once_with()
            assert notifications == [True]
            assert not queued, "An unready display callback scheduled itself forever"
            assert prompt._hmb_prompt_view_warmup_pending is False
    finally:
        prompt._hmb_prompt_shot_views = cache
        prompt._hmb_prompt_view_warmup_pending = old_pending
    record("unready_display_notification_reentry_does_not_requeue_forever",
        initial_callbacks=1, reentrant_callbacks_queued=0, pending_flag_released=True)


async def prompt_views(engine):
    import HMBImageAssetLibrary as images
    import HMBVideoPickerLibrary as pickers
    import HMBPromptLibrary as prompts
    import HMB_Prompt_Scoped_Snapshot_Cold_Reload_Host_Regression as cold

    # This fixture uses the actual native serializer, deletes the entire graph
    # and opens the saved commands again. The ten final execution-document
    # reads validate all five original image/video bindings after fresh clocks.
    await cold.exercise(engine)
    prompt = engine.node_manager.get_node_by_name("Real scoped Prompt")
    image = engine.node_manager.get_node_by_name("Real scoped Image")
    picker = engine.node_manager.get_node_by_name("Real scoped Picker")
    owner_flow = engine.flow_manager.get_flow_by_name(
        engine.node_manager._name_to_parent_flow_name[prompt.name])
    if not engine.context_manager.has_current_flow():
        engine.context_manager.push_flow(owner_flow)
    assert callable(getattr(prompt, "_hmb_prompt_shot_view", None)), "Presentation-only Prompt API is required"
    record("native_five_shot_source_bindings_and_literal_cold_reopen", shots=5,
        actual_SDK_serialize_delete_deserialize=True, image_and_video_per_Shot=True)
    baseline = deepcopy(prompt._current_state())
    before_outputs = deepcopy(dict(prompt.parameter_output_values))
    expected = check_views(prompt, prompts, images, pickers, cold.ROWS, cold.CHANNEL,
        label="prompt_120_cached_page_views_after_cold_reopen")
    assert prompt._current_state() == baseline
    assert prompt.parameter_output_values == before_outputs
    text_field = next(iter(prompts.TEXT_FIELD_DEFAULTS))
    for n, row in enumerate(cold.ROWS, 1):
        stored = json.loads(baseline["shot_documents"][prompts._prompt_document_key(
            {**row, "channel_uuid": cold.CHANNEL})])
        assert stored["text"][text_field] == f"Cold-reload exact literal {n} {{SIGN}} OFF 0"
    record("page_reads_leave_all_five_inputs_bindings_and_outputs_unchanged", shots=5)
    prompt_native_pages(engine, prompt, prompts, images, pickers, cold)
    before_edit = prompt._current_state()
    next_row = cold.ROWS[1]
    page_only = prompts._select_prompt_shot_document(deepcopy(before_edit),
        {**next_row, "channel_uuid": cold.CHANNEL})
    page_only[prompts.UI_EDIT_REVISION_KEY] = int(page_only.get(prompts.UI_EDIT_REVISION_KEY) or 0) + 1
    page_only = prompts._store_prompt_shot_document(page_only)
    assert prompts._prompt_page_only_write(before_edit, page_only)
    combined_edit = deepcopy(page_only)
    combined_edit["text"][text_field] = "A real authoring change together with navigation"
    combined_edit = prompts._store_prompt_shot_document(combined_edit)
    assert not prompts._prompt_page_only_write(before_edit, combined_edit)
    record("combined_authoring_edit_and_navigation_not_misclassified_as_page_only", changed_text_preserved=True)

    # A real authoring change is allowed to prepare its changed page. Preparing
    # one document must not destroy the already ready sibling display pages.
    changed = cold.ROWS[2]
    state = prompts._select_prompt_shot_document(prompt._current_state(),
        {**changed, "channel_uuid": cold.CHANNEL})
    literal = "Edited exact Shot 3 literal {SIGN} OFF 0"
    state["text"][text_field] = literal
    state[prompts.UI_EDIT_REVISION_KEY] = int(state.get(prompts.UI_EDIT_REVISION_KEY) or 0) + 1
    state = prompts._store_prompt_shot_document(state)
    prompt._hmb_write_merged_prompt_state(prompts._json_dumps(state))
    execution = prompt._hmb_prompt_shot_document(channel_uuid=cold.CHANNEL, shot_uuid=changed["shot_uuid"])
    assert literal in execution["machine_prompt"]
    refreshed = check_views(prompt, prompts, images, pickers, cold.ROWS, cold.CHANNEL,
        label="prompt_120_cached_views_after_one_real_edit")
    for row in cold.ROWS:
        if row["shot_uuid"] == changed["shot_uuid"]:
            assert refreshed[row["shot_uuid"]]["visible_prompt"] == execution["visible_prompt"]
            assert refreshed[row["shot_uuid"]]["revision"] != expected[row["shot_uuid"]]["revision"]
        else:
            assert refreshed[row["shot_uuid"]] == expected[row["shot_uuid"]], "An unchanged sibling page was invalidated or rebuilt"
    record("changed_shot_only_refresh_preserves_other_four_ready_pages", changed_Shot=3, other_ready_views=4)
    missing_display_callback_does_not_requeue_itself(prompt, changed, cold.CHANNEL)

    # Execution must continue to verify current ownership; a cached display is
    # deliberately not an inference authority when its publisher has vanished.
    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest
    cold.send(engine, DeleteNodeRequest(node_name=image.name))
    try:
        prompt._hmb_prompt_shot_document(channel_uuid=cold.CHANNEL, shot_uuid=changed["shot_uuid"])
    except Exception:
        pass
    else:
        raise AssertionError("A display cache bypassed missing execution owner validation")
    retained = prompt._current_state()["shot_documents"]
    assert set(baseline["shot_documents"]).issubset(retained)
    for number, row in enumerate(cold.ROWS, 1):
        stored = json.loads(retained[prompts._prompt_document_key({**row, "channel_uuid": cold.CHANNEL})])
        assert stored["text"][text_field] == (literal if number == 3 else
            f"Cold-reload exact literal {number} {{SIGN}} OFF 0")
    assert len(picker._picker_state()["picker_shots"]) == 5
    record("retained_presentation_is_not_missing_publisher_execution_authority", input_documents_retained=5)


def agent_pages(engine):
    import HMBAgentLibrary as agents
    import HMB_Agent_Atomic_Accordion_Order_Host_Regression as atomic

    # Adapt only the old fixture's synthetic source boundary. The actual SDK
    # native widgets, exact row SetParameter requests, stable children/edges,
    # values and serializer assertions still run unchanged.
    document_calls = Counter()
    display_calls = Counter()
    original_simple = atomic.SimpleNamespace
    def synthetic_source(**kwargs):
        reader = kwargs.get("_hmb_prompt_shot_view") or kwargs.get("_hmb_prompt_shot_document")
        if reader is None:
            return original_simple(**kwargs)
        def view(**identity):
            display_calls[identity["shot_uuid"]] += 1
            return dict(reader(**identity), subscription=identity, revision=1)
        def document(**identity):
            document_calls[identity["shot_uuid"]] += 1
            raise AssertionError("Agent page selection requested an execution document")
        return original_simple(_hmb_shot_manager_enabled=lambda: True, _hmb_node_deleted=False,
            _hmb_prompt_shot_view=view, _hmb_prompt_shot_document=document)

    original = agents.HMBAgentLibrary._hmb_handle_row_action
    samples = []
    expensive_events = Counter()
    selecting = False
    original_put = engine.event_manager.put_event
    def put(event):
        if selecting:
            payload = atomic.payload(event)
            details = getattr(payload, "element_details", {})
            if (type(payload).__name__ == "AlterElementEvent" and isinstance(details, dict)
                    and details.get("parameter_name") == agents._AGENT_SHOT_STORE_PARAMETER
                    and "value" in details):
                expensive_events["full_durable_shot_store_value"] += 1
        return original_put(event)
    def action(self, parameter, value):
        nonlocal selecting
        selected = isinstance(value, dict) and value.get("action", {}).get("kind") == "select"
        started = time.perf_counter_ns()
        selecting = selected
        try:
            return original(self, parameter, value)
        finally:
            selecting = False
            if selected:
                samples.append((time.perf_counter_ns() - started) / 1e6)
    with (mock.patch.object(atomic, "SimpleNamespace", synthetic_source),
          mock.patch.object(agents.HMBAgentLibrary, "_hmb_handle_row_action", action),
          mock.patch.object(engine.event_manager, "put_event", put)):
        atomic.exercise(engine)
    assert not document_calls, document_calls
    assert not expensive_events, expensive_events
    assert len(display_calls) == 5, display_calls
    METRICS["agent_native_page_requests"] = {**summary(samples),
        "execution_document_builds": sum(document_calls.values()),
        "presentation_reads": sum(display_calls.values()), "full_shot_store_events": dict(expensive_events)}
    record("agent_five_native_pages_use_display_only_no_execution_document", shots=5,
        native_select_requests=len(samples), execution_document_builds=0,
        full_shot_store_value_publications=0,
        own_outputs_context_zero_off_tools_rulesets_preserved=True,
        native_child_and_edge_identity_preserved=True, actual_SDK_serialization=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
        default=ROOT / "reports/page-switch-optimization-20261020/page-only-host")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    private = args.out.resolve() / "private-profile"
    for key, leaf in (("APPDATA", "app"), ("LOCALAPPDATA", "local"), ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
        ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "projects"),
        ("TEMP", "temp"), ("TMP", "temp")):
        folder = private / leaf
        folder.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(folder)
    standard = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
    os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(standard)
    for key in tuple(os.environ):
        if any(token in key.upper() for token in ("API_KEY", "ACCESS_TOKEN", "SECRET", "PASSWORD")):
            os.environ.pop(key, None)
    sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests"), str(standard), str(standard / ".venv/Lib/site-packages")]
    if importlib.util.find_spec("griptape_nodes") is None:
        print("HMB_PAGE_ONLY_SHOT_SWITCH_HOST=SKIP (installed SDK required)")
        return
    # Windows asyncio's fallback socketpair is local implementation machinery,
    # never a service connection. Every other TCP/DNS request remains denied.
    original_connect = socket.socket.connect
    import inspect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1") and any(
            frame.function == "_fallback_socketpair" and Path(frame.filename).name == "socket.py"
            for frame in inspect.stack(context=0)):
            return original_connect(sock, address)
        return deny(sock, address)
    original_handler = logging.FileHandler
    class TextHandler(original_handler):
        def __init__(self, filename, *a, **kw):
            file = Path(filename)
            super().__init__(str(file.with_suffix(".txt")) if file.suffix.lower() == ".log" else filename, *a, **kw)
    files = ("HMBAgentLibrary.py", "HMBPromptLibrary.py", "_hmb_shot_routing.py")
    before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    passed = False
    with ExitStack() as guards:
        guards.enter_context(mock.patch.object(logging, "FileHandler", TextHandler))
        for owner, name in ((socket, "create_connection"), (socket.socket, "connect"),
            (socket.socket, "connect_ex"), (socket, "getaddrinfo")):
            guards.enter_context(mock.patch.object(owner, name, connect if name == "connect" else deny))
        from griptape_nodes.retained_mode.engine import engine_scope
        import HMBAgentLibrary as agents
        import HMBPromptLibrary as prompts
        import HMBImageAssetLibrary as images
        import _hmb_shot_routing as routing
        guards.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
        guards.enter_context(mock.patch.object(prompts.HMBPromptLibrary, "_schedule_prompt_sync", lambda *a, **k: None))
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            guards.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
        guards.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", deny))
        guards.enter_context(mock.patch.object(agents.HMBAgentLibrary, "_run_native_agent_once", deny))
        logging.disable(logging.CRITICAL)
        try:
            with engine_scope() as engine:
                asyncio.run(prompt_views(engine))
            with engine_scope() as engine:
                engine.event_manager.initialize_queue()
                agent_pages(engine)
            assert not ATTEMPTS
            assert before == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}, "Product code changed during the SDK regression"
            passed = True
        finally:
            result = dict(schema="hmb-page-only-shot-switch-host/v1", passed=passed,
                cases=RESULTS, metrics=METRICS, source_sha256=before,
                source_unchanged=before == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
                forbidden_attempts=len(ATTEMPTS), paid_calls=0, live_graph_actions=0,
                scope="Private installed SDK graph; page-native request timings exclude desktop transport and paint")
            (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("HMB_PAGE_ONLY_SHOT_SWITCH_HOST=PASS " + json.dumps(dict(cases=len(RESULTS), metrics=METRICS)))


if __name__ == "__main__":
    main()
