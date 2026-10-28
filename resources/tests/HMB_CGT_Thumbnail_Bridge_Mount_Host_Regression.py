"""Actual SDK bridge mount metadata and legacy cold restore; no CGT/network.

The editor excludes ui_options.hide=True before it can create a Widget carrier.
Exercise the serialized native contract, not only the Python constructor.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def exercise(engine):
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, SerializeNodeToCommandsRequest, DeserializeNodeFromCommandsRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.serialization.values import decode_value, encode_value
    import HMBImageAssetLibrary as source
    import _hmb_shot_routing as routing
    import _hmb_cgt as cgt

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(row for row in schema.nodes if row.class_name == "HMBImageAssetLibrary")
    library.register_lazy_node_type("HMBImageAssetLibrary", definition.metadata, lambda: source.HMBImageAssetLibrary)
    engine.event_manager.initialize_queue()
    created_flow = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="SyntheticBridgeMount"))
    assert created_flow.succeeded(), created_flow.result_details
    with ExitStack() as patches:
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile", "reconcile_shot_routing"):
            patches.enter_context(mock.patch.object(routing, name))
        patches.enter_context(mock.patch.object(source.HMBImageAssetLibrary, "_schedule_catalog_root_change"))
        patches.enter_context(mock.patch.object(source.HMBImageAssetLibrary, "_schedule_catalog_scan"))
        created = engine.handle_request(CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name="SyntheticCGTBridgeMount", override_parent_flow_name=created_flow.flow_name,
            create_error_proxy_on_failure=False))
        assert created.succeeded(), created.result_details
        node = engine.node_manager.get_node_by_name(created.node_name)

        def bridge_contract(owner):
            parameter = owner.get_parameter_by_name(source.THUMBNAIL_PATCH_PARAMETER)
            options = parameter.ui_options
            assert options["hide"] is False and parameter.hide is False
            assert options["hide_property"] is False and parameter.hide_property is False
            assert options["hide_handles"] is True and options["hide_label"] is True
            assert options["height"] == options["min_height"] == options["max_height"] == 0
            assert options["expandable"] is False and options["resizable"] is False
            assert parameter.allowed_modes == source._mode_set("PROPERTY")
            traits = list(parameter.find_elements_by_type(source.Widget, find_recursively=True))
            assert len(traits) == 1 and traits[0].name == source.THUMBNAIL_BRIDGE_WIDGET_NAME
            return parameter

        parameter = bridge_contract(node)
        state = node._current_state()
        template = state["shot_routing"]["shots"][0]
        state["shot_routing"]["shots"] = [dict(template, shot_uuid=str(uuid4()), number=number,
            name=f"Authored Shot {number}", name_is_custom=True) for number in range(1, 6)]
        state["shot_routing"]["active_shot_uuid"] = state["shot_routing"]["shots"][3]["shot_uuid"]
        accepted = engine.handle_request(SetParameterValueRequest(node_name=node.name,
            parameter_name=source.WIDGET_STATE_PARAMETER, value=source._json_text(state), initial_setup=True))
        assert accepted.succeeded(), accepted.result_details
        state_before = deepcopy(node._current_state()["shot_routing"])
        bridge_before = deepcopy(node.get_parameter_value(source.THUMBNAIL_PATCH_PARAMETER))
        # Model an old native save's hidden transport, including the authored
        # detail overrides that execute after a new constructor on reopening.
        parameter.hide = True
        parameter.hide_property = True
        parameter.ui_options.update(hide=True, hide_property=True)
        pool = {}
        serialized = engine.handle_request(SerializeNodeToCommandsRequest(node_name=node.name,
            unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True))
        assert serialized.succeeded(), serialized.result_details
        legacy_commands = deepcopy(serialized.serialized_node_commands)
        assert any(getattr(command, "parameter_name", None) == source.THUMBNAIL_PATCH_PARAMETER
            and (getattr(command, "ui_options", None) or {}).get("hide") is True
            for command in legacy_commands.element_modification_commands), "Legacy hide=True must actually enter native saved commands"
        cold_flow = engine.handle_request(CreateFlowRequest(parent_flow_name=None,
            flow_name="SyntheticBridgeColdRestore", set_as_new_context=False))
        assert cold_flow.succeeded(), cold_flow.result_details
        with engine.context_manager.flow(cold_flow.flow_name):
            cold = engine.handle_request(DeserializeNodeFromCommandsRequest(serialized_node_commands=legacy_commands))
            assert cold.succeeded(), cold.result_details
            restored = engine.node_manager.get_node_by_name(cold.node_name)
            assert restored.get_parameter_by_name(source.THUMBNAIL_PATCH_PARAMETER).ui_options["hide"] is True
            for indirect in serialized.set_parameter_value_commands:
                request = deepcopy(indirect.set_parameter_value_command)
                if request.parameter_name not in {source.WIDGET_STATE_PARAMETER, source.THUMBNAIL_PATCH_PARAMETER}:
                    continue
                request.node_name = restored.name
                request.value = decode_value(deepcopy(pool[indirect.unique_value_uuid]))
                request.initial_setup = True
                applied = engine.handle_request(request)
                assert applied.succeeded(), applied.result_details
            bridge_contract(restored)
            assert restored._current_state()["shot_routing"] == state_before
            assert restored.get_parameter_value(source.THUMBNAIL_PATCH_PARAMETER) == bridge_before
            restored.after_deserialize()
            bridge_contract(restored)
            assert restored._current_state()["shot_routing"] == state_before
            # A serialized pending dialog request is data, never a fresh user
            # action. Drive the actual SDK initial-setup request path and
            # prohibit every CGT read/write helper and process/network escape.
            with ExitStack() as inert:
                cgt_read = inert.enter_context(mock.patch.object(cgt, "catalog", side_effect=AssertionError("CGT read forbidden")))
                cgt_write = inert.enter_context(mock.patch.object(cgt, "start_own_wait_after_commit", side_effect=AssertionError("CGT write forbidden")))
                dispatch = inert.enter_context(mock.patch.object(restored, "_request_cgt_read", side_effect=AssertionError("CGT request dispatched")))
                inert.enter_context(mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")))
                inert.enter_context(mock.patch.object(subprocess, "run", side_effect=AssertionError("subprocess forbidden")))
                inert.enter_context(mock.patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess forbidden")))
                bridge_command = next(indirect for indirect in serialized.set_parameter_value_commands
                    if indirect.set_parameter_value_command.parameter_name == source.THUMBNAIL_PATCH_PARAMETER)
                def restore_saved_bridge(saved):
                    # Model a serialized old workflow's value pool and replay
                    # the SDK's own saved command through initial_setup.
                    saved_pool = deepcopy(pool)
                    saved_pool[bridge_command.unique_value_uuid] = encode_value(saved)
                    request = deepcopy(bridge_command.set_parameter_value_command)
                    request.node_name = restored.name
                    request.value = decode_value(saved_pool[bridge_command.unique_value_uuid])
                    request.initial_setup = True
                    return engine.handle_request(request)
                for operation in ("cgt_catalog", "cgt_confirm", "cgt_cancel"):
                    saved = {**source._default_thumbnail_bridge("fixture-runtime"), "operation": operation,
                        "phase": "request", "request_id": "saved-request", "session_id": "saved-session",
                        "project_identity": "fixture-project", "hierarchy_request": {"fixture": True}}
                    hydrated = restore_saved_bridge(saved)
                    assert hydrated.succeeded(), hydrated.result_details
                    actual = restored.get_parameter_value(source.THUMBNAIL_PATCH_PARAMETER)
                    assert actual["operation"] == actual["phase"] == "idle", actual
                for operation in ("cgt_confirm", "catalog_page"):
                    saved = {**source._default_thumbnail_bridge("fixture-runtime"), "operation": operation,
                        "phase": "result", "request_id": "saved-result", "session_id": "saved-session",
                        "outcome": "ready", "state": {"fixture": True}}
                    expected = source._normalize_thumbnail_bridge(saved)
                    hydrated = restore_saved_bridge(saved)
                    assert hydrated.succeeded(), hydrated.result_details
                    assert restored.get_parameter_value(source.THUMBNAIL_PATCH_PARAMETER) == expected
                assert not cgt_read.called and not cgt_write.called and not dispatch.called
                assert restored._current_state()["shot_routing"] == state_before
            resaved = engine.handle_request(SerializeNodeToCommandsRequest(node_name=restored.name,
                unique_parameter_uuid_to_values={}, serialize_all_parameter_values=True))
            assert resaved.succeeded(), resaved.result_details
            assert not any(getattr(command, "parameter_name", None) == source.THUMBNAIL_PATCH_PARAMETER
                and (getattr(command, "ui_options", None) or {}).get("hide") is True
                for command in resaved.serialized_node_commands.element_modification_commands)
            assert len(engine.flow_manager.get_flow_by_name(cold_flow.flow_name).nodes) == 1
    print(json.dumps({"test": "HMB_CGT_Thumbnail_Bridge_Mount_Host_Regression", "status": "PASS",
        "actual_sdk": True, "fresh_bridge_property_mountable": True, "legacy_native_hide_override_repaired": True,
        "five_shots_preserved": True, "bridge_identity_preserved": True,
        "saved_cgt_requests_inert": True, "saved_results_preserved": True, "cgt_calls": 0, "paid_calls": 0}))


def main():
    if importlib.util.find_spec("griptape_nodes") is None:
        raise RuntimeError("Installed SDK runtime required")
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-cgt-bridge-mount-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        environment = {key: str(directory / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
            "LOCALAPPDATA", "APPDATA", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT")}
        for value in environment.values():
            Path(value).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, environment), mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            logging.disable(logging.CRITICAL)
            os.chdir(directory)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:
                    asyncio.run(exercise(engine))
            finally:
                os.chdir(previous)
                logging.shutdown()


if __name__ == "__main__":
    main()
