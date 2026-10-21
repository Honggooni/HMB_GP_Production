"""Real installed-SDK DAG: one Prompt/Agent manager and five Generator intents.

The exact source snapshot, model call and video generation are deterministic
offline boundaries. Routing, registered ownership, Prompt document compilation,
native Agent processing, Generator entry points and host scheduling stay real.
No user graph, credentials, provider, Broker, DCC or render filesystem is used.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(
    Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
try:
    HOST = importlib.util.find_spec("griptape_nodes.machines.parallel_resolution") is not None
except (ImportError, ModuleNotFoundError):
    HOST = False
if not HOST:
    print("HMB_MULTISHOT_MANAGER_HOST=SKIP (installed SDK required)")
    raise SystemExit(0)

CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [dict(shot_uuid=f"33333333-3333-4333-8333-{i:012d}", number=i,
              name=f"Authored asset {i}", revision=1,
              selected_source_uids=[f"import:manager-image-{i}"]) for i in range(1, 6)]
PROJECT = {"project_id": "katuri8", "project_name": "까투리8"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def no_network(*args, **kwargs):
    raise AssertionError("Offline manager integration must not access transport or authorization.")


async def exercise(engine):
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.machines.dag_builder import DagBuilder
    from griptape_nodes.machines.parallel_resolution import ParallelResolutionMachine
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest, EnsureWorkflowAndFlowResultSuccess
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest, ListConnectionsForNodeResultSuccess
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, CreateConnectionResultSuccess
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    import _hmb_shot_routing as routing
    import HMBImageAssetLibrary as image_module
    import HMBPromptLibrary as prompt_module
    import HMBAgentLibrary as agent_module
    import HMBFinishLookLibrary as finish_module
    import HMBSeedanceGeneration as seedance_module
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema

    # Register the source-under-test classes through the real host library
    # registry. Canonical Prompt topology must not be faked by a lookup stub.
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
    library = LibraryRegistry.generate_new_library(schema)
    classes = {cls.__name__: cls for cls in (image_module.HMBImageAssetLibrary,
        prompt_module.HMBPromptLibrary, agent_module.HMBAgentLibrary, finish_module.HMBFinishLookLibrary, seedance_module.HMBSeedanceGeneration)}
    for definition in schema.nodes:
        cls = classes.get(definition.class_name)
        if cls is not None:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)

    engine.event_manager.initialize_queue()
    ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(
        display_name="Offline manager integration", flow_name="OfflineMultishotManagers"))
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess), ensured
    flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
    events = []
    event_lock = threading.Lock()
    release = threading.Event()
    entered = threading.Event()
    native_mode = {"block": None, "fail": None}
    policy_observations = []
    executions = []
    model_owners = []
    finish_authored = {}
    finish_observations = []
    finish_manager = None
    original_policy_readiness = agent_module.HMBAgentLibrary._hmb_web_rerender_policy_status

    def record(kind, number):
        with event_lock:
            events.append((kind, number, time.monotonic()))

    def register(node):
        node.metadata["library"] = schema.name
        node.metadata["node_type"] = type(node).__name__
        flow.add_node(node)
        engine.object_manager.add_object_by_name(node.name, node)
        engine.node_manager._name_to_parent_flow_name[node.name] = flow.name

    native_context = threading.local()
    native_states = []

    def process_owner(self, state, prompt, output_type):
        assert isinstance(state, native_module.AgentState)
        native_states.append(state)
        native_context.owner = self
        native_context.state = state
        try:
            return original_native_process(self, state, prompt, output_type)
        finally:
            native_context.owner = None
            native_context.state = None

    def test_model(_config):
        from pydantic_ai.models.test import TestModel
        number = native_context.owner._hmb_shot_subscription["shot_number"]
        return TestModel(custom_output_text=f"Exact final instruction for authored asset {number}.")

    def model_fixture(native_agent, prompt, **kwargs):
        self = native_context.owner
        number = self._hmb_shot_subscription["shot_number"]
        model_owners.append((number, self._hmb_shot_owner.name))
        executions.append(self)
        if self._hmb_rules_active and not self._hmb_policy_omitted:
            scopes = self.get_parameter_list_value("rulesets")
            private = [row for row in scopes if row.get("name") in self._hmb_ruleset_names]
            assert len(private) == 2 and all(len(row["rules"]) == 4 for row in private)
            assert self._hmb_ruleset_names[0] != self._hmb_ruleset_names[1]
            assert self._hmb_run_policy_applied is True
            runtime_private = [row for row in native_context.state.rulesets if row.get("name") in self._hmb_ruleset_names]
            assert runtime_private == private
            assert str(prompt).count(self._hmb_shot_source.machine) == 1
            policy_observations.append({"shot": number, "policy_applied": True,
                "identity": deepcopy(self._hmb_policy_identity),
                "rule_hashes": [[hashlib.sha256(value.encode("utf-8")).hexdigest() for value in row["rules"]] for row in private]})
        record("model_started", number)
        if native_mode["block"] == number:
            entered.set()
            assert release.wait(5), "Offline model fixture was not released"
        time.sleep(0.03)
        if native_mode["fail"] == number:
            raise TimeoutError("PRIVATE_MODEL_FIXTURE_DETAILS")
        result = original_run_agent(native_agent, prompt, **kwargs)
        assert isinstance(result, native_module.AgentRunResult)
        assert result.output == f"Exact final instruction for authored asset {number}."
        assert result.new_messages()
        record("model_finished", number)
        return result

    async def generation_fixture(self):
        number = self._hmb_shot_channel_subscription()["shot_number"]
        if self.get_parameter_value("resume_generation_id"):
            record("retrieved", number)
            return
        if self._draft_final_requested():
            record("final", number)
            return
        params = self._get_parameters()
        assert params["prompt"] == f"Exact final instruction for authored asset {number}.", params["prompt"]
        assert params["resolution"] == "480p", params["resolution"]
        assert self.get_parameter_value("resolution") == "480p"
        assert self.get_parameter_value("prompt") != params["prompt"] or self._hmb_managed_agent_request
        self._assert_agent_result_available(params["prompt"], allow_resume=False)
        shot_record = self._hmb_managed_agent_request["record"]
        assert shot_record["shot"]["shot_uuid"] == SHOTS[number - 1]["shot_uuid"]
        prepared = self._resolve_exact_shot_generation_inputs(params)
        assert prepared["reference_images"] == [f"https://fixture.invalid/manager-image-{number}.png"], prepared["reference_images"]
        assert not prepared["video_references"] and not prepared["reference_audio"]
        exact_finish = finish_manager._hmb_finish_look_shot_snapshot_for(
            channel_uuid=CHANNEL, shot_uuid=SHOTS[number - 1]["shot_uuid"])
        finish_observations.append((number, params["prompt"], prepared, exact_finish,
            finish_manager._hmb_shot_channel_subscription()))
        record("generation_finished", number)
        self._set_status_results(was_successful=True, result_details="Offline video boundary completed.")

    native_base = agent_module.HMBAgentLibrary.__mro__[1]
    native_module = inspect.getmodule(native_base)
    assert agent_module._BuiltinAgent is not None and native_module is not None
    from griptape_nodes_library.llm import runner as native_runner
    original_native_process = native_base._process
    original_run_agent = native_module.run_agent
    with ExitStack() as stack:
        # Registration/discovery is driven synchronously below. Only the
        # deferred timer is suppressed, never the router or retained edges.
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
        stack.enter_context(mock.patch.object(native_base, "_process", process_owner))
        stack.enter_context(mock.patch.object(native_runner, "build_model", test_model))
        stack.enter_context(mock.patch.object(native_module, "run_agent", model_fixture))
        stack.enter_context(mock.patch.object(native_module, "resolve_cloud_api_key", lambda: "offline-unused"))
        stack.enter_context(mock.patch.object(native_module, "require_model_invocation_sync", lambda *a, **k: None))
        stack.enter_context(mock.patch.object(agent_module.HMBAgentLibrary, "validate_before_node_run", lambda self: None))
        stack.enter_context(mock.patch.object(seedance_module.HMBSeedanceGeneration, "validate_before_node_run", lambda self: None))
        stack.enter_context(mock.patch.object(agent_module.HMBAgentLibrary, "_hmb_web_rerender_policy_status",
            lambda self, *a, **k: {"ready": True, "reason": "project_policy_pending", "policy_verified": False, "policy_status": "absent"}))
        stack.enter_context(mock.patch.object(agent_module._hmb, "_bootstrap_agent_policy_session", no_network))
        stack.enter_context(mock.patch.object(seedance_module.HMBSeedanceGeneration, "_process_generation", generation_fixture))
        stack.enter_context(mock.patch.object(seedance_module._HMBAIBrokerBridge, "account_snapshot", no_network))

        source = image_module.HMBImageAssetLibrary(name="offline_manager_image")
        source._hmb_initial_catalog_scan_pending = False
        source._hmb_hydration_adopted = True
        # The current Prompt uses the exact scoped ImageAsset API, which reads
        # canonical authored state rather than the broad routing snapshot.
        # Author that real state as well as the media-free discovery fixture;
        # keep the scoped validation/materialization implementation unmocked.
        project_root = Path.cwd() / "synthetic-projects" / "Katuri8"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "hmb_image_assets.json").write_text('{"assets": []}', encoding="utf-8")
        source_state = image_module._select_catalog_project(
            image_module._load_project_catalog(project_root.parent, source._current_state()), project_root)
        # A bound Shot intentionally uses Reference to Video. Supply one
        # distinct synthetic URL record per Shot; no URL is fetched because
        # the existing native model/video boundaries remain offline fixtures.
        source_state["assets"] = [dict(
            asset_library_id=f"import:manager-image-{n}", source_uid=f"import:manager-image-{n}",
            source_kind="user", asset_id=f"manager-actor-{n}", image_name=f"Manager Actor {n}",
            path=f"https://fixture.invalid/manager-image-{n}.png", selected=True,
            selection_order=n, import_index=n, connected=True, registered=False,
            media_ref_kind="url") for n in range(1, 6)]
        source_state["shot_routing"].update(channel_uuid=CHANNEL,
            publisher_instance_uuid=PUBLISHER, generation=1,
            shots=deepcopy(SHOTS), active_shot_uuid=SHOTS[0]["shot_uuid"])
        # Match the real selection publication, including the native root and
        # ASSET_OUT projections. process() is intentionally an offline no-op
        # below, so a widget-only initial_setup write cannot publish them later.
        source._publish_state(source_state)
        snapshot = deepcopy(source._hmb_shot_routing_snapshot(CHANNEL, cached_only=True))
        catalog_document = dict(channel_uuid=CHANNEL, generation=1,
            shots=[{key: row[key] for key in ("shot_uuid", "number", "name", "revision")} for row in SHOTS])
        catalog = dict(schema="hmb-shot-routing-catalog", version=1, publisher_instance_uuid=PUBLISHER,
                       **catalog_document, metadata_sha256=digest(catalog_document))
        source._hmb_shot_routing_snapshot = lambda *a, **k: deepcopy(snapshot)
        source._hmb_shot_routing_catalog = lambda: deepcopy(catalog)
        source._hmb_project_identity = lambda: dict(PROJECT)
        source._hmb_shot_channel_subscription = lambda: dict(schema=routing.SUBSCRIPTION_SCHEMA, version=1,
            participant_kind="image_asset", enabled=True, channel_uuid=CHANNEL,
            shot_uuid=SHOTS[0]["shot_uuid"], shot_number=1, shot_name=SHOTS[0]["name"])
        source.process = lambda: None
        register(source)
        source.set_parameter_value("SHOT_ASSET_OUT", "offline-media-snapshot-token", initial_setup=True)
        source.parameter_output_values["SHOT_ASSET_OUT"] = "offline-media-snapshot-token"
        prompt = prompt_module.HMBPromptLibrary(name="offline_prompt_manager")
        register(prompt)
        prompt_state = prompt._current_state()
        prompt_state["multi_shot_enabled"] = True
        prompt_state["text"]["PRESERVED_TEXT"] = "Animate the authored asset in its own shot."
        prompt.set_parameter_value(prompt_module.WIDGET_PARAMETER_NAME, prompt_module._json_dumps(prompt_state), initial_setup=True)
        manager = agent_module.HMBAgentLibrary(name="offline_agent_manager")
        register(manager)
        assert manager.metadata["size"] == {"width": 720, "height": 1100}
        restored_size = {"width": 641, "height": 853}
        restored_manager = agent_module.HMBAgentLibrary(name="offline_saved_size_fixture", metadata={"size": deepcopy(restored_size)})
        assert restored_manager.metadata["size"] == restored_size
        finish_manager = finish_module.HMBFinishLookLibrary(name="offline_finish_manager")
        register(finish_manager)
        stack.enter_context(mock.patch.object(type(manager._model_access), "raise_if_selection_denied", lambda self: None))
        generators = []
        for number in range(1, 6):
            generator = seedance_module.HMBSeedanceGeneration(name=f"offline_managed_generator_{number}")
            register(generator)
            generator.set_parameter_value("model_id", seedance_module.MODEL_NAME_SEEDANCE_2_5, initial_setup=True)
            generator.set_parameter_value("resolution", "480p", initial_setup=True)
            generator.set_parameter_value("draft_action", seedance_module.DRAFT_ACTION_OFF, initial_setup=True)
            generators.append(generator)

        # Populate real manager catalogs before the explicit Agent opt-in.
        result = routing.reconcile_shot_routing(source, _allow_unready_cleanup=True)
        assert result["ok"], result
        widget = manager._hmb_widget_value(shot_catalog=catalog, shot_manager=True)
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER, widget)
        assert manager._hmb_shot_manager_enabled()
        # Read-only UI response clocks are not authoring commands. Exercise the
        # official native request lifecycle with an acknowledged client lease,
        # then select/edit each exact target using the latest per-target CAS.
        finish_ui_sequence = 0
        finish_ui_epoch = ""
        def set_finish_ui(value):
            result = engine.handle_request(SetParameterValueRequest(
                node_name=finish_manager.name, parameter_name=finish_module.WIDGET_PARAMETER_NAME,
                value=deepcopy(value), initial_setup=False))
            assert result.succeeded(), str(result.result_details)
            return deepcopy(finish_manager.get_parameter_value(finish_module.WIDGET_PARAMETER_NAME))
        def finish_ui_command(operation, value=None):
            nonlocal finish_ui_sequence, finish_ui_epoch
            finish_ui_sequence += 1
            value = deepcopy(finish_manager._widget_state if value is None else value)
            clock = deepcopy(finish_manager.get_parameter_value(finish_module.WIDGET_PARAMETER_NAME)[finish_module.UI_TRANSPORT_KEY])
            key = finish_manager._hmb_finish_key(value["shot"]["channel_uuid"], value["shot"]["shot_uuid"])
            request_id = f"offline-finish-{finish_ui_sequence}"
            value[finish_module.UI_TRANSPORT_KEY] = dict(
                schema=finish_module.UI_TRANSPORT_SCHEMA, version=1, operation=operation,
                session_id=clock["session_id"], base_revision=clock["revision"],
                base_target_revision=clock["target_revisions"][key], client_id="offline-combined-finish-ui",
                client_epoch=finish_ui_epoch, request_id=request_id, sequence=finish_ui_sequence)
            response = set_finish_ui(value)
            acknowledgement = response[finish_module.UI_TRANSPORT_KEY]
            assert acknowledgement["status"] == ("refreshed" if operation == "refresh" else "accepted"), acknowledgement
            assert acknowledgement["request_id"] == request_id and acknowledgement["sequence"] == finish_ui_sequence, acknowledgement
            assert acknowledgement["session_id"] == clock["session_id"], acknowledgement
            finish_ui_epoch = acknowledgement["client_epoch"]
            assert finish_ui_epoch
            return response
        finish_ui_command("refresh")
        for number, shot in enumerate(SHOTS, 1):
            finish_widget = deepcopy(finish_manager._widget_state)
            finish_widget["shot"] = {"channel_uuid": CHANNEL, **shot}
            finish_ui_command("select", finish_widget)
            assert finish_manager._widget_state["shot"]["shot_uuid"] == shot["shot_uuid"]
            finish_widget = deepcopy(finish_manager._widget_state)
            beauty = finish_widget["finish_look"]["beauty"]
            beauty.update(enabled=number % 2 == 1, brightness=1 + number / 10,
                saturation=number / 2, glow_width=number * 7, soften_shadows=number / 10)
            finish_authored[number] = deepcopy(finish_widget["finish_look"])
            finish_ui_command("edit", finish_widget)
        # Transport-free legacy nine-key native API remains compatible. Restore
        # the authored fifth document before the unchanged Generator assertions.
        legacy = deepcopy(finish_manager._widget_state)
        assert len(legacy) == 9 and finish_module.UI_TRANSPORT_KEY not in legacy
        legacy["finish_look"]["beauty"]["brightness"] = 1.4
        set_finish_ui(legacy)
        legacy_snapshot = finish_manager._hmb_finish_look_shot_snapshot_for(
            channel_uuid=CHANNEL, shot_uuid=SHOTS[4]["shot_uuid"])
        assert legacy_snapshot["finish_look_state"] == legacy["finish_look"]
        legacy["finish_look"] = deepcopy(finish_authored[5])
        set_finish_ui(legacy)
        assert finish_manager._hmb_finish_look_shot_snapshot_for(
            channel_uuid=CHANNEL, shot_uuid=SHOTS[4]["shot_uuid"])["finish_look_state"] == finish_authored[5]
        finish_widget = deepcopy(finish_manager._widget_state)
        finish_widget["shot"] = {"channel_uuid": CHANNEL, **SHOTS[0]}
        finish_ui_command("select", finish_widget)
        assert finish_manager._last_valid_state == finish_authored[1]
        print("PASS actual SDK Finish refresh/select/edit lease+CAS authors five exact documents; legacy nine-key native API remains compatible")
        for generator, shot in zip(generators, SHOTS):
            for key, value in ((seedance_module.SHOT_CHANNEL_UUID_PARAMETER, CHANNEL),
                               (seedance_module.SHOT_UUID_PARAMETER, shot["shot_uuid"]),
                               (seedance_module.SHOT_NUMBER_PARAMETER, shot["number"]),
                               (seedance_module.SHOT_NAME_PARAMETER, shot["name"]),
                               (seedance_module.SHOT_SELECTOR_PARAMETER, shot["name"])):
                generator.set_parameter_value(key, value, initial_setup=True)
        result = routing.reconcile_shot_routing(source, _allow_unready_cleanup=True)
        assert result["ok"], result
        for node in [source, prompt, manager, *generators]:
            routing._mark_authoritative(node)
        assert prompt._hmb_shot_manager_enabled()
        assert len(prompt._hmb_prompt_shot_subscriptions()) == 5
        assert len(manager._hmb_agent_shot_subscriptions()) == 5
        result = engine.handle_request(ListConnectionsForNodeRequest(node_name=manager.name))
        assert isinstance(result, ListConnectionsForNodeResultSuccess)
        assert sum(edge.target_parameter_name == "SHOT_PROMPT_IN" for edge in result.incoming_connections) == 1
        for generator in generators:
            assert generator._manual_agent_prompt_source() is manager
        print("PASS new Agent default size reserves header/rows/body; saved size preserved; one Finish manager owns five distinct Beauty documents")

        # The official SDK root holds five lightweight rows and exactly one
        # native Agent body. Selecting row3 moves the same element objects/IDs.
        body = list(manager._hmb_native_editor_elements)
        body_identity = [(id(item), item.element_id) for item in body]
        assert body and len({identity for identity, _ in body_identity}) == len(body)
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER,
            manager._hmb_widget_value(shot={"channel_uuid": CHANNEL, **SHOTS[2]}, shot_catalog=catalog, shot_manager=True))
        root_children = list(manager.root_ui_element.children)
        row3 = manager.get_parameter_by_name(agent_module._AGENT_SHOT_ROW_PREFIX + "3")
        row4 = manager.get_parameter_by_name(agent_module._AGENT_SHOT_ROW_PREFIX + "4")
        start = root_children.index(row3) + 1
        assert root_children[start:start + len(body)] == body and root_children[start + len(body)] is row4
        assert all(sum(item is element for item in root_children) == 1 for element in body)
        visible = {str(item.name): bool(item.ui_options.get("hide", False)) for item in body}
        collapsed = deepcopy(manager.get_parameter_value(agent_module._AGENT_WIDGET_PARAMETER))
        collapsed["shot_editor_expanded"] = False
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER, collapsed)
        assert all(item.ui_options.get("hide") is True for item in body)
        collapsed["shot_editor_expanded"] = True
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER, collapsed)
        assert {str(item.name): bool(item.ui_options.get("hide", False)) for item in body} == visible
        assert [(id(item), item.element_id) for item in manager._hmb_native_editor_elements] == body_identity
        with mock.patch.object(manager, "reorder_elements", wraps=manager.reorder_elements) as reorder:
            for _ in range(100):
                manager._hmb_layout_shot_editor()
            assert reorder.call_count == 0
        # Recovery only republishes a canonical row ACK. Inactive target2
        # must not move the active editor3, overwrite inputs or start a worker.
        before_refresh = deepcopy(manager.get_parameter_value(agent_module._AGENT_WIDGET_PARAMETER))
        before_prompt = manager.get_parameter_value("prompt")
        row2 = manager.get_parameter_by_name(agent_module._AGENT_SHOT_ROW_PREFIX + "2")
        manager._hmb_handle_row_action(row2, {"shot": {"channel_uuid": CHANNEL, **SHOTS[1]},
            "action": {"kind": "refresh", "request_id": "a" * 32}})
        assert manager.get_parameter_value(agent_module._AGENT_WIDGET_PARAMETER) == before_refresh
        assert manager.get_parameter_value("prompt") == before_prompt and not manager._hmb_shot_workers
        refreshed = manager.get_parameter_value(row2.name)
        assert refreshed["request_id"] == "a" * 32 and not refreshed["selected"]
        print("PASS native SDK accordion row3/body/row4 order; original IDs, hide restoration, 100 unchanged layouts reorder zero")

        async def resolve(targets):
            dag = DagBuilder(engine=engine)
            for node in targets:
                node.prepare_to_run_again()
                dag.add_node_with_dependencies(node, node.name)
            participants = [node.node_reference for node in dag.node_to_reference.values()]
            machine = ParallelResolutionMachine(flow.name, max_nodes_in_parallel=5, dag_builder=dag, engine=engine)
            await asyncio.wait_for(machine.resolve_node(), timeout=15)
            assert machine.is_complete() and not machine.is_errored(), machine.get_error_message()
            return participants

        # One selected Generator invokes exactly one model although the shared
        # manager declares five available Shots.
        participants = await resolve([generators[2]])
        assert sum(node is manager for node in participants) == 1, [node.name for node in participants]
        assert [number for kind, number, _ in events if kind == "model_started"] == [3], (events,
            {key: generators[2].parameter_output_values.get(key) for key in ("was_successful", "result_details", "generation_status")},
            manager._hmb_shot_run_status)
        assert [number for kind, number, _ in events if kind == "generation_finished"] == [3], (events,
            {key: generators[2].parameter_output_values.get(key) for key in ("was_successful", "result_details", "generation_status")})
        for number, literal, prepared, exact_finish, visible in finish_observations:
            assert prepared["prompt"] == literal, ("literal_prompt", prepared["prompt"], literal)
            assert exact_finish["finish_look_state"] == finish_authored[number], ("finish_state", number, exact_finish["finish_look_state"], finish_authored[number])
            assert prepared["_hmb_finish_look_out"] == finish_module.compile_finish_look_prompt(finish_authored[number]), ("finish_prose", number, prepared["_hmb_finish_look_out"], finish_module.compile_finish_look_prompt(finish_authored[number]))
            assert visible["shot_uuid"] == SHOTS[0]["shot_uuid"], ("finish_ui", visible)
        events.clear()

        # Source/Prompt/manager are shared SDK dependencies, not five visible
        # model nodes. Each Generator independently pulls its frozen Shot.
        await resolve(generators)
        assert sorted(number for kind, number, _ in events if kind == "model_started") == [1, 2, 3, 4, 5], events
        assert sorted(number for kind, number, _ in events if kind == "generation_finished") == [1, 2, 3, 4, 5], events
        started = sorted(at for kind, _, at in events if kind == "model_started")
        first_finished = min(at for kind, _, at in events if kind == "model_finished")
        assert started[1] < first_finished, "The manager serialized distinct Shot model calls."
        assert all(generator.get_parameter_value("resolution") == "480p" for generator in generators)
        assert all(generator.state == NodeResolutionState.RESOLVED for generator in generators)
        assert all(state.to_wire()["format"] == "pydantic_ai_agent" for state in native_states)
        assert all(state.messages for state in native_states)
        events.clear()

        # One Agent retains native ParameterList/schema settings per Shot.
        # The five row controls move this one native body; there is no Only view.
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER,
            manager._hmb_widget_value(shot={"channel_uuid": CHANNEL, **SHOTS[3]}, shot_catalog=catalog, shot_manager=True))
        fourth_rule = manager.get_parameter_by_name("rulesets").add_child_parameter()
        fourth_tool = manager.get_parameter_by_name("tools").add_child_parameter()
        manager.set_parameter_value(fourth_rule.name, "FOURTH_SHOT_RULE")
        manager.set_parameter_value(fourth_tool.name, {"name": "Fourth fixture tool", "configuration": {"value": 0}})
        fourth_schema = {"type": "object", "properties": {"fourth": {"type": "string"}}}
        manager.set_parameter_value("output_schema", deepcopy(fourth_schema))
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER,
            manager._hmb_widget_value(shot={"channel_uuid": CHANNEL, **SHOTS[4]}, shot_catalog=catalog, shot_manager=True))
        assert manager.get_parameter_list_value("rulesets") == []
        assert manager.get_parameter_list_value("tools") == []
        fifth_rule = manager.get_parameter_by_name("rulesets").add_child_parameter()
        fifth_tool = manager.get_parameter_by_name("tools").add_child_parameter()
        manager.set_parameter_value(fifth_rule.name, "FIFTH_SHOT_RULE")
        manager.set_parameter_value(fifth_tool.name, {"name": "Fifth fixture tool", "configuration": {"value": False}})
        fifth_schema = {"type": "object", "properties": {"fifth": {"type": "number"}}}
        manager.set_parameter_value("output_schema", deepcopy(fifth_schema))
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER,
            manager._hmb_widget_value(shot={"channel_uuid": CHANNEL, **SHOTS[3]}, shot_catalog=catalog, shot_manager=True))
        assert manager.get_parameter_list_value("rulesets") == ["FOURTH_SHOT_RULE"]
        assert manager.get_parameter_list_value("tools") == [{"name": "Fourth fixture tool", "configuration": {"value": 0}}]
        assert manager.get_parameter_value("output_schema") == fourth_schema
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER,
            manager._hmb_widget_value(shot={"channel_uuid": CHANNEL, **SHOTS[4]}, shot_catalog=catalog, shot_manager=True))
        assert manager.get_parameter_list_value("rulesets") == ["FIFTH_SHOT_RULE"]
        assert manager.get_parameter_list_value("tools") == [{"name": "Fifth fixture tool", "configuration": {"value": False}}]
        assert manager.get_parameter_value("output_schema") == fifth_schema
        assert all(generator._manual_agent_prompt_source() is manager for generator in generators)
        events.clear()

        # Reusing the same selected Generator creates one new Agent intent,
        # while Resume and Draft Final each execute zero additional models.
        await resolve([generators[0]])
        assert [n for kind, n, _ in events if kind == "model_started"] == [1], events
        events.clear()
        generators[0].set_parameter_value("resume_generation_id", "job-" + "a" * 32, initial_setup=True)
        await resolve([generators[0]])
        assert [kind for kind, _, _ in events] == ["retrieved"], events
        events.clear()
        generators[0].set_parameter_value("resume_generation_id", "", initial_setup=True)
        with mock.patch.object(generators[0], "_draft_final_requested", return_value=True):
            await resolve([generators[0]])
        assert [kind for kind, _, _ in events] == ["final"], events
        events.clear()

        # A failed one-shot request cannot consume a previous successful text
        # or abort another Generator that shares the manager.
        native_mode["fail"] = 1
        await resolve(generators[:2])
        assert [n for kind, n, _ in events if kind == "generation_finished"] == [2], events
        assert generators[0].parameter_output_values.get("was_successful") is False
        assert "PRIVATE_MODEL_FIXTURE_DETAILS" not in str(generators[0].parameter_output_values)
        assert manager._hmb_agent_shot_result(channel_uuid=CHANNEL, shot_uuid=SHOTS[0]["shot_uuid"]) == {}
        events.clear()
        native_mode["fail"] = None

        # An editor switch while two requests are running cannot change their
        # frozen subscriptions or turn cancel-one into cancel-all.
        native_mode["block"] = 1
        first = asyncio.create_task(generators[0].aprocess())
        second = asyncio.create_task(generators[1].aprocess())
        deadline = time.monotonic() + 5
        while not entered.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        assert entered.is_set(), "Selected worker did not enter its model boundary"
        manager.set_parameter_value(agent_module._AGENT_WIDGET_PARAMETER,
            manager._hmb_widget_value(shot={"channel_uuid": CHANNEL, **SHOTS[3]}, shot_catalog=catalog, shot_manager=True))
        state = prompt._current_state()
        state["shot"] = {"channel_uuid": CHANNEL, **SHOTS[4]}
        state[prompt_module.UI_EDIT_REVISION_KEY] += 1
        prompt.set_parameter_value(prompt_module.WIDGET_PARAMETER_NAME, prompt_module._json_dumps(state))
        worker = manager._hmb_shot_workers[manager._hmb_slot_key(CHANNEL, SHOTS[0]["shot_uuid"])]
        assert worker._hmb_shot_subscription["shot_number"] == 1
        assert prompt._hmb_shot_channel_subscription()["shot_number"] == 5
        assert manager._hmb_shot_channel_subscription()["shot_number"] == 4
        generators[0].request_cancellation()
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), timeout=10)
        assert isinstance(outcomes[0], asyncio.CancelledError), outcomes
        assert outcomes[1] is None, outcomes
        assert [n for kind, n, _ in events if kind == "generation_finished"] == [2], events
        generators[0].clear_cancellation()
        native_mode["block"] = None
        assert not manager._hmb_shot_workers
        events.clear()

        # Verify the new per-Shot facade with the exact signed v7 DAT. Seed an
        # isolated authorized session offline; no auth endpoint is contacted.
        sys.path.insert(0, str(Path(__file__).parent))
        from _hmb_bundled_policy_session import install_bundled_policy_session
        install_bundled_policy_session(agent_module._hmb)
        policy_payload = agent_module._hmb._load_agent_rule_payload()
        assert policy_payload["final_policy_version"].endswith("v7.0")
        PROJECT.update(project_id="superwings12", project_name="슈퍼윙즈12")
        project_root = Path.cwd() / "synthetic-projects" / "superwings12"
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "hmb_image_assets.json").write_text('{"assets": []}', encoding="utf-8")
        authored_routing = deepcopy(source._current_state()["shot_routing"])
        authored_images = deepcopy(source._current_state()["assets"])
        source_state = image_module._select_catalog_project(
            image_module._load_project_catalog(project_root.parent, source._current_state()), project_root)
        source_state["assets"] = authored_images
        source_state["shot_routing"] = dict(authored_routing, generation=2)
        source._publish_state(source_state)
        snapshot.update(project_id=PROJECT["project_id"], generation=2)
        snapshot["metadata_sha256"] = digest({key: snapshot[key] for key in
            ("channel_uuid", "generation", "project_id", "shots", "ordered_assets")})
        catalog_document["generation"] = 2
        catalog.update(generation=2, metadata_sha256=digest(catalog_document))
        result = routing.reconcile_shot_routing(source, _allow_unready_cleanup=True)
        assert result["ok"], result
        with mock.patch.object(agent_module._hmb, "_bootstrap_agent_policy_session", lambda *a, **k: None), \
             mock.patch.object(agent_module.HMBAgentLibrary, "_hmb_web_rerender_policy_status", original_policy_readiness):
            await resolve([generators[2]])
        assert [n for kind, n, _ in events if kind == "model_started"] == [3], events
        assert [n for kind, n, _ in events if kind == "generation_finished"] == [3], events
        assert len(policy_observations) == 1 and policy_observations[0]["policy_applied"]
        ready_record = manager._hmb_agent_shot_result(channel_uuid=CHANNEL, shot_uuid=SHOTS[2]["shot_uuid"])
        assert ready_record["policy_identity"]["version"] == policy_payload["final_policy_version"]
        assert ready_record["result"]["policy_applied"] is True
        assert not manager._hmb_rules_active and not manager._hmb_policy_rules and not manager._hmb_binding_rules
        assert not manager._hmb_shot_workers
        assert all(node.get_parameter_value("resolution") == "480p" for node in generators)
        assert all(not worker._hmb_rules_active and not worker._hmb_policy_rules
                   and not worker._hmb_binding_rules and not worker.parameter_values
                   and not worker.parameter_output_values for worker in executions)
        assert {number for number, *_ in finish_observations} == {1, 2, 3, 4, 5}
        for number, literal, prepared, exact_finish, visible in finish_observations:
            assert prepared["prompt"] == literal
            assert exact_finish["finish_look_state"] == finish_authored[number]
            assert prepared["_hmb_finish_look_out"] == finish_module.compile_finish_look_prompt(finish_authored[number])
            assert visible["shot_uuid"] == SHOTS[0]["shot_uuid"]
        assert manager.metadata["size"] == {"width": 720, "height": 1100}
        manager.metadata["size"] = {"width": 811, "height": 777}
        for _ in range(100):
            manager._hmb_layout_shot_editor()
        assert manager.metadata["size"] == {"width": 811, "height": 777}
        print("PASS real Prompt1/Agent1/Finish1 to five Generators: exact per-Shot Beauty at every mocked render boundary, literal prompt/480p retained; user resize never forced")

    print("HMB_MULTISHOT_MANAGER_HOST=PASS (real DAG; one Prompt; one Agent; five Shot rows; native ParameterList/schema isolation; five concurrent intents; single selection; rerender; Resume/Final Agent zero; failure/cancel isolation; editor switch; signed v7 policy; 480p retained)")


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-multishot-manager-host-") as directory:
        root = Path(directory)
        overrides = {name: str(root / leaf) for name, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("LOCALAPPDATA", "local"),
            ("APPDATA", "app"), ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"))}
        with mock.patch.dict(os.environ, overrides), mock.patch.object(socket, "create_connection", no_network):
            os.chdir(root)
            logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:
                    asyncio.run(exercise(engine))
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    main()
