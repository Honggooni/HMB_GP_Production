"""Actual isolated SDK: explicit mode persistence, UUID ownership and pre-run isolation.

This manual regression never processes a model, submits a render, opens a user
workflow or connects to the running desktop engine. Saved files contain only
synthetic values and are reopened by a second, cold SDK process.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
STANDARD = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [dict(shot_uuid=f"33333333-3333-4333-8333-{n:012d}", number=n,
              name=f"Mode authored asset {n}", revision=1)
         for n in range(1, 6)]
PRODUCTS = ("HMBSeedanceGeneration.py", "_hmb_shot_routing.py", "widgets/HMBSeedanceGenerationWidget.js")
ATTEMPTS = []
RESULTS = []
REQUESTS = 0


def deny(*args, **kwargs):
    ATTEMPTS.append("forbidden_model_or_provider_or_live_transport")
    raise AssertionError("Mode SDK fixture must not execute models, renders or live transports")


def record(name, **details):
    RESULTS.append(dict(name=name, passed=True, **details))


def send(engine, request):
    global REQUESTS
    REQUESTS += 1
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


async def asend(engine, request):
    global REQUESTS
    REQUESTS += 1
    request.broadcast_result = False
    result = await engine.ahandle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def catalog(t, *, channel=CHANNEL, shots=None, generation=1):
    document = dict(channel_uuid=channel, generation=generation, shots=deepcopy(SHOTS if shots is None else shots))
    return dict(schema="hmb-shot-routing-catalog", version=1, publisher_instance_uuid=PUBLISHER,
                **document, metadata_sha256=t.HMBSeedanceGeneration._canonical_sha256(document))


def intent(t, mode="only", shot=None, revision=1):
    value = dict(schema=t.SEEDANCE_EXECUTION_MODE_SCHEMA, version=1, mode=mode, revision=revision)
    if mode == "shot":
        value.update(channel_uuid=CHANNEL, shot_uuid=shot["shot_uuid"],
                     shot_number=shot["number"], shot_name=shot["name"])
    return value


def authored(t, node):
    names = ("model_id", "task", "prompt", "resolution", "duration", "output_format", "output_file",
             "generate_audio", "draft_action", "resume_generation_id", "draft_job_id", "only_project")
    return dict(values={key: deepcopy(node.get_parameter_value(key)) for key in names},
                reference_images=deepcopy(node._get_list_input("reference_images")),
                video_references=deepcopy(node._get_list_input(t.VIDEO_REFERENCES_PARAMETER)),
                reference_audio=deepcopy(node._get_list_input("reference_audio")))


def configure(t, node, number):
    values = dict(model_id=t.MODEL_NAME_SEEDANCE_2_5, task=t.TASK_REFERENCE_TO_VIDEO,
                  prompt=f"Literal mode {number} {{RGB(12, 34, 56)}} OFF 0 한국어",
                  resolution="480p", duration=4, output_format="mov", generate_audio=False,
                  output_file=f"mode-{number}-original.mov", only_project="까투리8")
    for key, value in values.items():
        node.set_parameter_value(key, value, initial_setup=True)
    for field, extension in (("reference_images", "png"), (t.VIDEO_REFERENCES_PARAMETER, "mp4"), ("reference_audio", "wav")):
        child = node.get_parameter_by_name(field).add_child_parameter()
        node.set_parameter_value(child.name, f"https://media.invalid/mode-{number}.{extension}", initial_setup=True)
    # A synthetic saved Task is not resumed or submitted by this fixture.
    node.set_parameter_value("resume_generation_id", "job-" + str(number) * 32, initial_setup=True)


def select(engine, t, node, shot=""):
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    fields = node._hmb_seedance_mode_widget_fields()
    value = t._seedance_widget_value(dict(channel_uuid=CHANNEL if shot else "", shot_uuid=shot),
                                      node._hmb_shot_catalog_snapshot)
    value.update(fields)
    value["selection_request"] = dict(schema=t.SEEDANCE_MODE_SELECTION_SCHEMA, version=1,
        mode="shot" if shot else "only", expected_revision=fields["execution_mode_revision"],
        expected_instance=fields["execution_mode_instance"])
    send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=t.SEEDANCE_SHOT_WIDGET_PARAMETER,
                                        value=value, initial_setup=False))
    return value


def register(engine, modules):
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    for definition in schema.nodes:
        if definition.class_name in modules:
            cls = getattr(modules[definition.class_name], definition.class_name)
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    return schema


async def exercise(engine, phase, out):
    t = importlib.import_module("HMBSeedanceGeneration")
    agents = importlib.import_module("HMBAgentLibrary")
    images = importlib.import_module("HMBImageAssetLibrary")
    routing = importlib.import_module("_hmb_shot_routing")
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest, CreateFlowRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest, RunWorkflowWithCurrentStateRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
    schema = register(engine, {"HMBSeedanceGeneration": t, "HMBAgentLibrary": agents,
                               "HMBImageAssetLibrary": images})
    engine.event_manager.initialize_queue()
    saved = out / "synthetic-mode-workflow.py"
    expected_file = out / "expected.json"
    with ExitStack() as guards:
        if phase != "reopen":
            for key in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                guards.enter_context(mock.patch.object(routing, key, lambda *a, **k: False))
        guards.enter_context(mock.patch.object(t._HMBAIBrokerBridge, "_request_json", deny))
        guards.enter_context(mock.patch.object(t.HMBSeedanceGeneration, "_process_generation", deny))
        if phase == "reopen":
            result = await asend(engine, RunWorkflowWithCurrentStateRequest(file_path=str(saved)))
            assert str(getattr(result.status, "name", result.status)) == "GOOD", str(result.status)
            expected = json.loads(expected_file.read_text("utf-8"))
            restored = []
            for name, wanted in expected.items():
                node = engine.node_manager.get_node_by_name(name)
                assert isinstance(node, t.HMBSeedanceGeneration), name
                assert node.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA] == wanted["intent"]
                assert node.metadata["preserved_literal"] == wanted["literal"]
                assert authored(t, node) == wanted["authored"], (name, authored(t, node), wanted["authored"])
                actual = node._hmb_seedance_execution_mode()
                if wanted["intent"]["mode"] == "only":
                    assert actual == "only" and not node._hmb_shot_channel_subscription()["enabled"]
                else:
                    assert actual in {"shot", "waiting"} and node._hmb_seedance_requested_shot_identity()["shot_uuid"] == wanted["intent"]["shot_uuid"]
                # First getter is observed before any manual restore/reconcile.
                first = deepcopy(node.get_parameter_value(t.SEEDANCE_SHOT_WIDGET_PARAMETER))
                observation = dict(node=name, actual_mode=actual,
                    widget_mode=first.get("execution_mode"), widget_requested_mode=first.get("requested_mode"),
                    metadata_intent=node._hmb_seedance_mode_intent())
                with (out / "cold-first-getter-observations.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(observation, ensure_ascii=False) + "\n")
                if wanted["intent"]["mode"] == "only":
                    assert first["execution_mode"] == actual == "only", observation
                else:
                    # Actual native source discovery can advance its private
                    # catalog between two reads. Both first snapshots must keep
                    # the requested Shot, never report independent Only.
                    assert first["execution_mode"] in {"shot", "waiting"}, observation
                    assert first["requested_mode"] == "shot", observation
                    assert first["pending_shot"]["shot_uuid"] == wanted["intent"]["shot_uuid"], observation
                restored.append((node, wanted))
                record("cold_saved_file_first_getter", node=name, mode=actual,
                       widget_mode=first["execution_mode"],
                       requested_uuid=node._hmb_seedance_requested_shot_identity().get("shot_uuid", ""))
            deadline = asyncio.get_running_loop().time() + 3
            while True:
                coherent = all(n._hmb_seedance_execution_mode() == n.get_parameter_value(t.SEEDANCE_SHOT_WIDGET_PARAMETER).get("execution_mode")
                    and n._hmb_seedance_execution_mode() == ("only" if wanted["intent"]["mode"] == "only" else "shot")
                    for n, wanted in restored)
                if coherent:
                    break
                assert asyncio.get_running_loop().time() < deadline, "Natural source restore did not settle"
                await asyncio.sleep(.02)
            for node, wanted in restored:
                assert authored(t, node) == wanted["authored"]
                widget = node.get_parameter_value(t.SEEDANCE_SHOT_WIDGET_PARAMETER)
                if wanted["intent"]["mode"] == "shot":
                    assert node._shot_identity()["shot_uuid"] == wanted["intent"]["shot_uuid"]
                    assert widget["shot"]["shot_uuid"] == wanted["intent"]["shot_uuid"]
                else:
                    assert not node._hmb_shot_channel_subscription()["enabled"]
                record("cold_natural_restore_settled_exact_mode", node=node.name,
                       mode=node._hmb_seedance_execution_mode(), manual_hook_calls=0)
            return

        flow = engine.flow_manager.get_flow_by_name(send(engine, EnsureWorkflowAndFlowRequest(flow_name="ExplicitOnlySDK")).flow_name)
        source_result = send(engine, CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name="Disposable Image publisher", initial_setup=True, create_error_proxy_on_failure=False))
        source = engine.node_manager.get_node_by_name(source_result.node_name)
        state = images._default_state()
        state["shot_routing"].update(channel_uuid=CHANNEL, publisher_instance_uuid=PUBLISHER,
            generation=1, shots=[dict(row, selected_source_uids=[]) for row in SHOTS], active_shot_uuid=SHOTS[0]["shot_uuid"])
        source.set_parameter_value(images.WIDGET_STATE_PARAMETER, json.dumps(state, ensure_ascii=False), initial_setup=True)
        source._hmb_initial_catalog_scan_pending = False
        assert source._hmb_shot_channel_subscription()["channel_uuid"] == CHANNEL
        def create(name, mode="only", shot=None):
            value = {t.SEEDANCE_EXECUTION_MODE_METADATA: intent(t, mode, shot), "preserved_literal": {"OFF": False, "zero": 0, "text": "한글 {literal}"}}
            result = send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration", specific_library_name=schema.name,
                node_name=name, initial_setup=True, metadata=value, create_error_proxy_on_failure=False))
            return engine.node_manager.get_node_by_name(result.node_name)
        only = create("Mode Only")
        configure(t, only, 6)
        # A late serialized quartet must not become authority over explicit Only.
        for key, value in ((t.SHOT_CHANNEL_UUID_PARAMETER, CHANNEL), (t.SHOT_UUID_PARAMETER, SHOTS[0]["shot_uuid"]),
                           (t.SHOT_NUMBER_PARAMETER, 1), (t.SHOT_NAME_PARAMETER, "Late obsolete Shot")):
            only.set_parameter_value(key, value, initial_setup=True)
        assert only._hmb_seedance_execution_mode() == "only" and not only._hmb_shot_channel_subscription()["enabled"]
        record("metadata_before_late_quartet_keeps_only")
        generators = []
        for number, shot in enumerate(SHOTS, 1):
            node = create(f"Mode Shot {number}", "shot", shot)
            configure(t, node, number)
            node._hmb_reconcile_shot_routing(catalog(t))
            assert node._hmb_seedance_execution_mode() == "shot"
            generators.append(node)
        record("five_exact_shot_bindings", UUIDs=[node._shot_identity()["shot_uuid"] for node in generators])
        only._hmb_reconcile_shot_routing(catalog(t))
        before = authored(t, only)
        # Release one claimed Shot only inside this disposable graph.
        target = generators.pop()
        target._hmb_commit_seedance_mode()
        target._apply_seedance_shot_selection("", fallback_to_available=False)
        request = select(engine, t, only, SHOTS[4]["shot_uuid"])
        assert only._hmb_seedance_execution_mode() == "shot"
        select(engine, t, only)
        assert only._hmb_seedance_execution_mode() == "only" and authored(t, only) == before
        # Stale request replays the old instance/revision and cannot bind again.
        from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
        send(engine, SetParameterValueRequest(node_name=only.name, parameter_name=t.SEEDANCE_SHOT_WIDGET_PARAMETER, value=request))
        assert only._hmb_seedance_execution_mode() == "only"
        record("native_only_shot_only_and_stale_request", authored_values_preserved=True)

        node = generators[0]
        preserved = authored(t, node)
        wanted = node._hmb_seedance_requested_shot_identity()["shot_uuid"]
        node._hmb_clear_shot_routing_catalog()
        assert node._hmb_seedance_execution_mode() == "waiting" and not node._draft_only_mode()
        altered = [dict(row, shot_uuid="44444444-4444-4444-8444-444444444444") if row["shot_uuid"] == wanted else row for row in SHOTS]
        node._hmb_reconcile_shot_routing(catalog(t, shots=altered, generation=2))
        assert node._hmb_seedance_execution_mode() == "waiting"
        node._hmb_reconcile_shot_routing(catalog(t, channel=PUBLISHER, generation=3))
        assert node._hmb_seedance_execution_mode() == "waiting" and node._hmb_seedance_requested_shot_identity()["shot_uuid"] == wanted
        node._hmb_reconcile_shot_routing(catalog(t, generation=4, shots=[dict(row, name="Renamed exact UUID") if row["shot_uuid"] == wanted else row for row in SHOTS]))
        assert node._hmb_seedance_execution_mode() == "shot" and node._shot_identity()["shot_uuid"] == wanted
        assert node._shot_identity()["shot_name"] == "Renamed exact UUID" and authored(t, node) == preserved
        record("waiting_new_uuid_and_foreign_channel_rejected_exact_uuid_restored")

        # Legacy auto-bound nodes have no mode intent. A missing single Shot
        # must gain a durable exact pending identity, not claim its replacement.
        legacy = create("Legacy pending Shot 5", "shot", SHOTS[4])
        configure(t, legacy, 7)
        legacy._hmb_reconcile_shot_routing(catalog(t))
        legacy.metadata.pop(t.SEEDANCE_EXECUTION_MODE_METADATA)
        without_five = SHOTS[:4]
        legacy._hmb_reconcile_shot_routing(catalog(t, shots=without_five, generation=2))
        assert legacy._hmb_seedance_execution_mode() == "waiting"
        assert legacy._hmb_seedance_requested_shot_identity()["shot_uuid"] == SHOTS[4]["shot_uuid"]
        assert legacy.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA]["mode"] == "shot"
        replacement = [*without_five, dict(SHOTS[4], shot_uuid="55555555-5555-4555-8555-555555555555")]
        legacy._hmb_reconcile_shot_routing(catalog(t, shots=replacement, generation=3))
        assert legacy._hmb_seedance_execution_mode() == "waiting"
        legacy._hmb_reconcile_shot_routing(catalog(t, generation=4))
        assert legacy._shot_identity()["shot_uuid"] == SHOTS[4]["shot_uuid"]
        legacy._hmb_reconcile_shot_routing(catalog(t, shots=without_five, generation=5))
        record("legacy_missing_shot_keeps_exact_durable_owner_and_rejects_same_number_new_uuid")

        # Preserve waiting bindings across native save; they must not open as Only.
        node._hmb_clear_shot_routing_catalog()
        all_nodes = [only, *generators, target, legacy]
        expected = {n.name: dict(intent=deepcopy(n.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA]),
            literal=deepcopy(n.metadata["preserved_literal"]), authored=authored(t, n)) for n in all_nodes}
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name)).serialized_flow_commands
        await asend(engine, SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
            file_name=saved.stem, file_path=str(saved), display_name="Offline explicit-mode fixture"))
        tree = __import__("ast").parse(saved.read_text("utf-8"))
        calls = {__import__("ast").unparse(n.func).rsplit(".", 1)[-1] for n in __import__("ast").walk(tree) if isinstance(n, __import__("ast").Call)}
        assert not calls & {"StartFlowRequest", "StartFlowFromNodeRequest", "ExecuteNodeRequest", "ResolveNodeRequest"}, calls
        expected_file.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
        record("actual_native_save_seven_generators_including_legacy_pending", path=str(saved), SHA256=hashlib.sha256(saved.read_bytes()).hexdigest(), execute_calls=0)

        # Separate disposable flow: a manually connected HMB manager is a local
        # admission failure. Native StartFlow must finish, without inference.
        blocked_flow = engine.flow_manager.get_flow_by_name(send(engine, CreateFlowRequest(
            parent_flow_name=None, flow_name="OnlyBlockedManagerSDK", set_as_new_context=True)).flow_name)
        # Keep a deliberately invalid pre-existing wire long enough to inspect
        # the native pre-run guard. Normal HMB routing removes this wire earlier.
        guards.enter_context(mock.patch.object(routing, "reconcile_shot_routing",
            lambda *a, **k: dict(ok=True, changed=0, failures=[])))
        gen = create("Blocked Only")
        for key, value in dict(model_id=t.MODEL_NAME_SEEDANCE_2_5, task=t.TASK_TEXT_ONLY, prompt="", only_project="까투리8", resolution="480p").items():
            gen.set_parameter_value(key, value, initial_setup=True)
        manager_result = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name=schema.name,
            node_name="Shared HMB Manager", initial_setup=True, create_error_proxy_on_failure=False))
        manager = engine.node_manager.get_node_by_name(manager_result.node_name)
        assert manager._hmb_shot_manager_enabled()
        manager.parameter_output_values["output"] = "Synthetic cached manager text"
        connection = dict(source_node_name=manager.name, source_parameter_name="output", target_node_name=gen.name, target_parameter_name="prompt")
        send(engine, CreateConnectionRequest(**connection, initial_setup=True))
        assert gen._manual_agent_prompt_source() is manager
        node_errors = gen.validate_before_node_run() or []
        workflow_errors = gen.validate_before_workflow_run() or []
        assert not node_errors and not workflow_errors
        assert "Only mode cannot run" in gen._hmb_local_preflight_failure
        process_calls = []
        with mock.patch.object(manager, "validate_before_workflow_run", return_value=None), mock.patch.object(manager, "validate_before_node_run", return_value=None), mock.patch.object(manager, "process", side_effect=lambda *a, **k: process_calls.append("manager")):
            # The SDK's unqualified start queue includes every top-level flow.
            # Restrict this single-invalid-wire case to its own retained node;
            # the separate five-Shot fixture covers the complete Flow queue.
            result = await engine.ahandle_request(StartFlowRequest(flow_name=blocked_flow.name, flow_node_name=gen.name, broadcast_result=False))
        (out / "start-flow-observation.json").write_text(json.dumps(dict(
            result_type=type(result).__name__, errors=[str(e) for e in getattr(result, "validation_exceptions", [])],
            upstream_process_calls=len(process_calls), Generator_node_hook_errors=[str(e) for e in node_errors],
            Generator_workflow_hook_errors=[str(e) for e in workflow_errors],
            Generator_outputs={key: str(value) for key, value in gen.parameter_output_values.items()},
            Generator_values={key: str(gen.get_parameter_value(key)) for key in ("generation_status", "was_successful", "result_details")}), ensure_ascii=False, indent=2), encoding="utf-8")
        assert result.succeeded(), str(result)
        assert "SKIPPED:" in gen.parameter_output_values.get("result_details", "")
        assert "Only mode cannot run" in gen.parameter_output_values.get("result_details", "")
        assert gen.parameter_output_values.get("was_successful") is False
        assert gen.parameter_output_values.get("generation_status") == "skipped"
        assert not process_calls
        record("native_StartFlow_locally_skips_only_manager_without_inference", upstream_process_calls=0,
               scope="Native invalid-wire validation with automatic route cleanup held; normal routing removes the wire earlier.")
        send(engine, DeleteConnectionRequest(**connection))

        # A true installed Standard Agent and an ordinary SDK text source have
        # no HMB manager authority; validation allows their explicit inputs.
        from griptape_nodes.exe_types.node_types import DataNode
        from griptape_nodes.exe_types.core_types import ParameterMode
        from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
        standard = agents._BaseAgent(name="Native Standard input")
        class OrdinaryText(DataNode):
            def process(self):
                deny()
        plain = OrdinaryText(name="Ordinary literal input")
        plain.add_parameter(ParameterString(name="text", default_value="Ordinary {{literal}}", allowed_modes={ParameterMode.OUTPUT}))
        for source, port in ((standard, "output"), (plain, "text")):
            source.metadata.update(library=schema.name, node_type=type(source).__name__)
            blocked_flow.add_node(source)
            engine.object_manager.add_object_by_name(source.name, source)
            engine.node_manager._name_to_parent_flow_name[source.name] = blocked_flow.name
            source.parameter_output_values[port] = "Native retained input without model execution"
            edge = dict(source_node_name=source.name, source_parameter_name=port, target_node_name=gen.name, target_parameter_name="prompt")
            send(engine, CreateConnectionRequest(**edge, initial_setup=True))
            assert gen._manual_agent_prompt_source() is None
            gen._assert_only_mode_inputs()
            params = gen._get_parameters_for_start_validation()
            assert params["_hmb_generation_mode"] == "only"
            send(engine, DeleteConnectionRequest(**edge))
        record("native_standard_and_ordinary_prompt_inputs_allowed_without_execution")


def run_phase(phase, out):
    private = out / (phase + "-profile")
    for key, leaf in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state"),
                      ("XDG_CACHE_HOME", "cache"), ("LOCALAPPDATA", "local"), ("APPDATA", "app"),
                      ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "projects")):
        folder = private / leaf
        folder.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(folder)
    os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(STANDARD)
    sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests"), str(STANDARD), str(STANDARD / ".venv/Lib/site-packages")]
    sys.dont_write_bytecode = True
    attempts = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection
    original_addrinfo = socket.getaddrinfo
    def allowed(address):
        host = address[0] if isinstance(address, tuple) else address
        port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
        if port in {8124, 8125, 8443, 14823} or host is not None and str(host).lower() not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
            attempts.append("blocked_network")
            raise AssertionError("No live engine, Broker or external network in ModeHost")
    def connect(sock, address, *a, **k):
        allowed(address)
        return original_connect(sock, address, *a, **k)
    def connect_ex(sock, address, *a, **k):
        allowed(address)
        return original_connect_ex(sock, address, *a, **k)
    def create(address, *a, **k):
        allowed(address)
        return original_create(address, *a, **k)
    def addrinfo(host, *a, **k):
        allowed(host)
        return original_addrinfo(host, *a, **k)
    error = None
    try:
        with mock.patch.object(socket.socket, "connect", connect), mock.patch.object(socket.socket, "connect_ex", connect_ex), mock.patch.object(socket, "create_connection", create), mock.patch.object(socket, "getaddrinfo", addrinfo):
            logging.disable(logging.CRITICAL)
            from griptape_nodes.retained_mode.engine import engine_scope
            with engine_scope() as engine:
                asyncio.run(exercise(engine, phase, out))
    except BaseException as exc:
        error = exc
        raise
    finally:
        logging.shutdown()
        result = dict(schema="hmb-seedance-execution-mode-installed-sdk/v1", phase=phase,
            passed=error is None and not attempts and not ATTEMPTS, cases=RESULTS, native_requests=REQUESTS,
            forbidden_execution_attempts=len(ATTEMPTS), external_or_live_socket_attempts=len(attempts),
            provider_or_paid_calls=0, live_graph_actions=0,
            source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PRODUCTS})
        (out / (phase + "-result.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("save", "reopen"))
    parser.add_argument("--out", type=Path, default=ROOT / "reports/only-explicit-mode-local808-20261019/sdk/manual")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.phase:
        run_phase(args.phase, args.out.resolve())
        return
    source = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PRODUCTS}
    results = []
    for phase in ("save", "reopen"):
        child = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--phase", phase, "--out", str(args.out.resolve())],
            cwd=ROOT, env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True, timeout=180)
        (args.out / (phase + "-stdout-stderr.txt")).write_bytes(child.stdout + child.stderr)
        if child.returncode:
            print((child.stdout + child.stderr).decode("utf-8", errors="replace"))
            raise SystemExit(child.returncode)
        results.append(json.loads((args.out / (phase + "-result.json")).read_text("utf-8")))
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PRODUCTS}
    summary = dict(schema="hmb-seedance-execution-mode-host-summary/v1", passed=all(r["passed"] for r in results) and source == after,
        source_stable=source == after, source_before=source, source_after=after, results=results,
        actual_cold_processes=2, scope="Real installed SDK native save and cold file-open; native mode/parameter/connection/StartFlow validation. No provider or current desktop graph.")
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(passed=summary["passed"], cases=sum(len(r["cases"]) for r in results), source_stable=source == after)))
    assert summary["passed"]


if __name__ == "__main__":
    main()
