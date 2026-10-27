"""Actual SDK model identity preservation and paid-free native execution gate.

Uses a private engine, synthetic nodes, native Save, literal-only saved setters,
and a fake driver boundary. No user workflow, live engine, credential, provider
request, or paid generation is used.
"""
from __future__ import annotations

import ast
from contextlib import ExitStack
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(
    Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
ATTEMPTS = []
CHECKS = []


def deny(*args, **kwargs):
    ATTEMPTS.append(True)
    raise AssertionError("Model identity regression forbids external requests")


def check(value, label):
    assert value, label
    CHECKS.append(label)


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def exercise(engine, folder):
    import HMBAgentLibrary as hmb
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowRequest
    from griptape_nodes.traits.options import Options

    native = sys.modules[hmb._BuiltinAgent.__module__]
    legacy_table = deepcopy(native.CLOUD_LEGACY_MODEL_VALUES)
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(x for x in schema.nodes if x.class_name == "HMBAgentLibrary")
    library.register_new_node_type(hmb.HMBAgentLibrary, definition.metadata)

    def create(name):
        result = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary",
            specific_library_name="HMB_GP_Production", node_name=name, initial_setup=True))
        return engine.node_manager.get_node_by_name(result.node_name)

    def set_value(node, name, value, initial=True):
        return send(engine, SetParameterValueRequest(node_name=node.name,
            parameter_name=name, value=value, initial_setup=initial))

    def selection(node):
        return {name: node.parameter_values[name] for name in ("model_provider", "model")}

    def rejected(node, token, provider="griptape_cloud"):
        try:
            node._resolve_model_config(token, provider)
        except hmb._HMBModelSelectionRequired as exc:
            check(token in str(exc), "rejection names original model " + token)
            check(hmb._hmb_native_failure_code(exc) == "MODEL_SELECTION_REQUIRED", "specific model selection failure code")
        else:
            raise AssertionError("Unsupported model silently resolved")

    try:
        send(engine, EnsureWorkflowAndFlowRequest(flow_name="SyntheticModelIdentity"))
        node = create("Synthetic Agent")
        supported = node._model_access.model_choices[0]
        old = "claude-sonnet-4-6"
        check(node.get_parameter_value("model") in node._model_access.model_choices, "new Agent retains native supported default")
        set_value(node, "model_provider", "griptape_cloud")
        set_value(node, "model", old)
        check(selection(node) == {"model_provider": "griptape_cloud", "model": old}, "initial saved model preserved exactly")
        check(old not in node._model_access.model_choices, "preserved model is not admitted to supported models")
        check(native.CLOUD_LEGACY_MODEL_VALUES == legacy_table and legacy_table[old] != old, "native global retirement table untouched")
        node._model_access.reinstall_options()
        node._provider.update_model_choices_for_provider("griptape_cloud")
        check(node.parameter_values["model"] == old, "native model refresh retains original selection")
        rejected(node, old)
        set_value(node, "model", "unknown-saved-model")
        check(node.parameter_values["model"] == "unknown-saved-model", "unknown saved model never falls back to first option")
        rejected(node, "unknown-saved-model")
        set_value(node, "model", old)

        # Genuine SDK save then a new node restored only from its generated
        # literal model/provider setters. No workflow code or pickle is run.
        saved = send(engine, SaveWorkflowRequest(file_name=str(folder / "model-identity.py"),
            display_name="Synthetic model identity preservation"))
        tree = ast.parse(Path(saved.file_path).read_text("utf-8"))
        tables = {}
        for assignment in ast.walk(tree):
            if isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Dict):
                for target in assignment.targets:
                    if isinstance(target, ast.Name) and "unique_values" in target.id:
                        tables[target.id] = {ast.literal_eval(k): v for k, v in zip(assignment.value.keys, assignment.value.values)}
        saved_values = {}
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "SetParameterValueRequest"):
                continue
            keywords = {k.arg: k.value for k in call.keywords}
            name_ast = keywords.get("parameter_name")
            if not isinstance(name_ast, ast.Constant) or name_ast.value not in {"model", "model_provider"}:
                continue
            value_ast = keywords["value"]
            if isinstance(value_ast, ast.Call):
                assert isinstance(value_ast.func, ast.Name) and value_ast.func.id == "decode_value"
                assert len(value_ast.args) == 1 and not value_ast.keywords
                reference = value_ast.args[0]
                assert isinstance(reference, ast.Subscript) and isinstance(reference.value, ast.Name)
                value_ast = tables[reference.value.id][ast.literal_eval(reference.slice)]
            saved_values[name_ast.value] = ast.literal_eval(value_ast)
        check(saved_values == selection(node), "native SDK Save contains exact model and provider literals")
        reopened = create("Reopened Synthetic Agent")
        for name, value in saved_values.items():
            set_value(reopened, name, value)
        reopened.after_deserialize()
        check(selection(reopened) == saved_values, "new node replay and after_deserialize preserve selection")

        # Slot switches call the native setter directly; cover that separate
        # restore route with five distinct original model strings.
        template = deepcopy(node._hmb_native_slot_snapshot())
        for number in range(1, 6):
            key = node._hmb_slot_key("synthetic-channel", f"shot-{number}")
            slot = deepcopy(template)
            slot["values"]["model"] = old if number == 1 else f"saved-shot-model-{number}"
            slot["values"]["prompt"] = f"Retained prompt {number}"
            node._hmb_shot_slots[key] = slot
        for number in [1, 2, 3, 4, 5, 4, 3, 2, 1]:
            node._hmb_restore_native_slot("synthetic-channel", f"shot-{number}")
            expected = old if number == 1 else f"saved-shot-model-{number}"
            check(node.parameter_values["model"] == expected, f"shot {number} model survives native restore")
        check(len([k for k in node._hmb_shot_slots if k.startswith("synthetic-channel")]) == 5, "all five independent model settings retained")

        # Provider refresh is not an explicit provider change. An actual user
        # provider change still uses native lists/defaults for the new provider.
        set_value(reopened, "model_provider", "saved-unavailable-provider")
        check(reopened.parameter_values["model_provider"] == "saved-unavailable-provider", "unknown saved provider is not replaced by Cloud")
        reopened._update_option_choices("model_provider", ["griptape_cloud"], "griptape_cloud")
        check(reopened.parameter_values["model_provider"] == "saved-unavailable-provider", "provider list refresh preserves unavailable saved provider")
        with mock.patch.object(reopened._provider, "fetch_models_for_provider", return_value=["provider-a", "provider-b"]):
            set_value(reopened, "model_provider", "synthetic-provider", initial=False)
        check(reopened.parameter_values["model"] == "provider-a", "explicit provider change keeps native new-provider default")
        set_value(reopened, "model", "provider-b", initial=False)
        with mock.patch.object(reopened._provider, "model_config_for", return_value=SimpleNamespace(model="provider-b")):
            check(reopened._resolve_model_config("provider-b", "synthetic-provider").model == "provider-b", "custom provider model resolution unchanged")
        with mock.patch.object(reopened._provider, "model_config_for", return_value=SimpleNamespace(model="different-paid-model")):
            rejected(reopened, "provider-b", "synthetic-provider")

        config = native.cloud_model_config(supported)
        check(reopened._resolve_model_config(config.to_wire(), "saved-unavailable-provider").model == supported,
            "connected ModelConfig keeps its exact model and native precedence")
        connected = native.AgentState(model=config).to_wire()
        state = reopened._build_state(old, "saved-unavailable-provider", connected)
        check(state.model.model == supported, "connected Agent state ignores stale dropdown without replacement")

        # A native process reaches a fake driver only for the exact supported
        # model. Unsupported dropdown values fail before declaration/driver.
        set_value(reopened, "model_provider", "griptape_cloud")
        set_value(reopened, "model", old)
        set_value(reopened, "prompt", "Synthetic prompt")
        calls = []
        with mock.patch.object(reopened, "_process", side_effect=lambda state, *_: calls.append(state.model.model)), \
                mock.patch.object(native, "require_model_invocation_sync", side_effect=lambda *_: None), \
                mock.patch.object(reopened._model_access, "raise_if_selection_denied", return_value=None):
            iterator = hmb._BuiltinAgent.process(reopened)
            try:
                next(iterator)
            except hmb._HMBModelSelectionRequired:
                pass
            else:
                raise AssertionError("Unsupported model reached native driver yield")
            check(calls == [], "unsupported native process invokes no model")
            set_value(reopened, "model", supported, initial=False)
            iterator = hmb._BuiltinAgent.process(reopened)
            pending = next(iterator)
            pending()
            try:
                iterator.send(None)
            except StopIteration:
                pass
            check(calls == [supported], "explicit supported selection reaches exact fake driver once")
        check(native.CLOUD_LEGACY_MODEL_VALUES == legacy_table, "other native Agents retain untouched model configuration")
        for cls in (hmb._HMBAgentShotExecution, hmb._HMBWebRerenderExecution):
            facade = object.__new__(cls)
            facade.__dict__.update(reopened.__dict__)
            rejected(facade, old)
        check("Choose a supported model explicitly" in hmb._hmb_execution_failure_message("MODEL_SELECTION_REQUIRED"), "published failure asks for explicit model selection")
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-agent-model-identity-") as temporary:
        base = Path(temporary)
        overrides = {key: str(base / leaf) for key, leaf in (
            ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
            ("LOCALAPPDATA", "local"), ("APPDATA", "app"), ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"))}
        for directory in overrides.values():
            Path(directory).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", deny))
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
            except ImportError:
                print("HMB_AGENT_MODEL_IDENTITY_HOST=SKIP (installed SDK required)")
                return
            import _hmb_shot_routing as routing
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, lambda *args, **kwargs: False))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                exercise(engine, base)
        check(ATTEMPTS == [], "external model requests zero")
    print(json.dumps({"test": "HMB_AGENT_MODEL_IDENTITY_HOST", "passed": True,
        "checks": CHECKS, "count": len(CHECKS), "external_calls": len(ATTEMPTS)}))


if __name__ == "__main__":
    main()
