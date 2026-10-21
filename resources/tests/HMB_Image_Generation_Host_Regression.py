"""Personal image workspace in the actual SDK, with synthetic Broker results.

Only private fixture configuration/media are written. The SDK CreateNode,
parameter types, output publication and serialize/delete/reopen are real.
No provider, live engine, Broker, user workflow or installed library is changed.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import io
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
ATTEMPTS = []


def deny(*_args, **_kwargs):
    ATTEMPTS.append("unexpected_network")
    raise AssertionError("Personal image fixture attempted a live request")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def identity(path):
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns


async def exercise(engine, directory):
    from PIL import Image
    import HMBImageGeneration as target
    import _hmb_image_generation as protocol
    from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
    from griptape_nodes.exe_types.core_types import ParameterMode
    from griptape_nodes.exe_types.node_types import SuccessFailureNode
    from griptape_nodes.files.file import File
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, ListConnectionsForNodeRequest
    from griptape_nodes.retained_mode.events.flow_events import (
        DeleteFlowRequest, DeserializeFlowFromCommandsRequest, SerializeFlowToCommandsRequest,
    )
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, GetAllNodeInfoRequest
    from griptape_nodes.retained_mode.events.parameter_events import GetNodeElementDetailsRequest

    buffer = io.BytesIO()
    Image.new("RGB", (17, 9), (40, 110, 180)).save(buffer, "PNG")
    raw = buffer.getvalue()
    verified = protocol.validate_image_bytes(raw)
    raw_capabilities = {
        "schema": protocol.CAPABILITIES_SCHEMA, "version": 1, "enabled": True,
        "persistence_scope": "personal_local", "client_request_lookup": True,
        "models": [{"provider": "google", "model_id": "gemini-3-pro-image",
                    "display_name": "Nano Banana Pro", "enabled": True, "credential_ready": True,
                    "tasks": ["text-to-image", "image-to-image"], "aspect_ratios": ["1:1", "16:9", "4:3"],
                    "image_sizes": ["1K", "2K", "4K"], "output_formats": ["png"],
                    "max_reference_images": 4, "max_reference_bytes": 1048576,
                    "defaults": {"task": "text-to-image", "ratio": "1:1", "image_size": "1K", "output_format": "png"},
                    "option_schema": {"schema": "hmb-image-model-options-v1", "revision": "pro-host-v1", "properties": {
                        "temperature": {"type": "number", "default": 1.0, "minimum": 0, "maximum": 2},
                        "top_p": {"type": "number", "default": 0.95, "minimum": 0, "maximum": 1},
                        "use_google_search": {"type": "boolean", "default": False},
                    }}}],
    }
    nb2 = deepcopy(raw_capabilities["models"][0])
    nb2.update(model_id="gemini-3.1-flash-image", display_name="Nano Banana 2",
               image_sizes=["512", "1K", "2K", "4K"], aspect_ratios=["1:1", "16:9", "1:8"])
    nb2["defaults"].update(image_size="512", ratio="16:9")
    nb2["option_schema"]["revision"] = "nb2-host-v1"
    nb2["option_schema"]["properties"]["use_google_image_search"] = {"type": "boolean", "default": False}
    raw_capabilities["models"].append(nb2)
    caps = protocol.parse_capabilities(raw_capabilities)
    records, creates, refreshes, downloads = {}, [], [], []

    class FixtureBroker:
        def __init__(self, node, *, server_url):
            self.node, self.server_url = node, server_url

        def capabilities(self):
            return caps

        def account_snapshot(self, **_kwargs):
            return SimpleNamespace(connected=True)

        def create(self, invocation, *, is_alive):
            assert is_alive()
            checkpoint = self.node._checkpoint()
            assert checkpoint["client_request_id"] == invocation.client_request_id
            assert checkpoint["status"] == "submitting", "Request identity must be saved before create"
            payload = invocation.payload()
            assert payload["persistence_scope"] == "personal_local"
            assert payload["publish_to_reviews"] is False
            assert "project_id" not in payload and "shot_id" not in payload
            creates.append(deepcopy(payload))
            job = {"schema": protocol.JOB_SCHEMA, "version": 1, "status": "succeeded",
                   "job_id": "job-image-fixture-" + str(len(creates)), "provider": invocation.provider,
                   "model": invocation.model_id, "client_request_id": invocation.client_request_id,
                   "persistence_scope": "personal_local", "publish_to_reviews": False,
                   "result": {"url": self.server_url + "/api/assets/" + "A" * 43,
                              "mime_type": "image/png", "sha256": verified.sha256}}
            records[job["job_id"]] = deepcopy(job)
            return deepcopy(job)

        def refresh(self, task_id, **_kwargs):
            refreshes.append(task_id)
            return deepcopy(records[task_id])

        def save_result(self, job, output_path, *, is_alive):
            assert is_alive()
            downloads.append(job["job_id"])
            return protocol.save_image_atomic(verified, output_path, is_alive=is_alive)

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(row for row in schema.nodes if row.class_name == "HMBImageGeneration")
    library.register_lazy_node_type(definition.class_name, definition.metadata, lambda: target.HMBImageGeneration)
    class FixtureImageSink(SuccessFailureNode):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_parameter(ParameterImage(name="image", allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY}))
        async def aprocess(self):
            pass
    library.register_lazy_node_type("FixtureImageSink", definition.metadata, lambda: FixtureImageSink)
    engine.event_manager.initialize_queue()
    expected = {}
    preserved_edges = []

    def assert_preserved_edges():
        for source, source_port, sink in preserved_edges:
            result = send(engine, ListConnectionsForNodeRequest(node_name=source))
            assert any(row.source_parameter_name == source_port and row.target_node_name == sink
                       and row.target_parameter_name == "image" for row in result.outgoing_connections), (source, source_port, sink)

    def attach(node):
        node._broker_factory = lambda **kwargs: FixtureBroker(node, **kwargs)

    def option(node, key, value=None, *, write=False):
        name = node._active_option_parameters[key]
        if write:
            node.set_parameter_value(name, value)
        return node.get_parameter_value(name)

    def assert_output(node, path, task_id):
        assert isinstance(node.get_parameter_by_name("image_url"), ParameterImage)
        assert isinstance(node.get_parameter_by_name("IMAGE_OUT"), ParameterImage)
        for key in ("image_url", "IMAGE_OUT"):
            artifact = node.parameter_output_values[key]
            assert artifact.value == str(path)
            assert File(artifact.value).read().content == raw
        assert node.parameter_output_values["generation_id"] == task_id
        assert node.parameter_output_values.get("was_successful") is True, {
            "native_status_value": node.get_parameter_value("was_successful"),
            "output_status_value": node.parameter_output_values.get("was_successful"),
            "execution_succeeded": node._execution_succeeded,
            "result_details": node.get_parameter_value("result_details"),
        }
        element_id = node.get_parameter_by_name("image_url").element_id
        details = send(engine, GetNodeElementDetailsRequest(node_name=node.name))
        assert details.element_details["element_id_to_value"][element_id].value == str(path)
        snapshot = send(engine, GetAllNodeInfoRequest(node_name=node.name))
        assert snapshot.element_id_to_value[element_id].value == str(path)
        return identity(path)

    try:
        ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="PersonalImageFixture"))
        for slot in range(1, 6):
            created = send(engine, CreateNodeRequest(node_type="HMBImageGeneration",
                node_name=f"Personal Image {slot}", specific_library_name=schema.name, initial_setup=True))
            node = engine.node_manager.get_node_by_name(created.node_name)
            if slot == 1:
                assert not creates and not downloads, "Construction performed an image operation"
            assert not any("project" in name.lower() or "shot" in name.lower()
                           for name in node.parameter_values)
            attach(node)
            await node._execute("connect")
            node.set_parameter_value("prompt", f"개별 이미지 입력 {slot}", initial_setup=True)
            node.set_parameter_value("output_file", str(directory / f"personal-{slot}.png"), initial_setup=True)
            node.set_parameter_value("image_size", "4K")
            node.set_parameter_value("ratio", "4:3")
            option(node, "temperature", slot / 10, write=True)
            option(node, "top_p", 0.0, write=True)
            node.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
            node.set_parameter_value("image_size", "512")
            node.set_parameter_value("ratio", "1:8")
            node.set_parameter_value("auto_image_resize", False)
            option(node, "temperature", 1.0 + slot / 10, write=True)
            option(node, "use_google_image_search", slot % 2 == 0, write=True)
            if slot % 2:
                node.set_parameter_value("model_id", "google/gemini-3-pro-image")
            await node.aprocess()
            assert len(creates) == slot, node.parameter_output_values.get("result_details")
            checkpoint = node._checkpoint()
            path = Path(checkpoint["saved_path"])
            task_id = checkpoint["task_id"]
            before = assert_output(node, path, task_id)
            await node._execute("retrieve")
            assert len(creates) == slot and len(downloads) == slot, "Same Task retrieve duplicated create/save"
            assert assert_output(node, path, task_id) == before
            expected[node.name] = (str(path), task_id, deepcopy(checkpoint), before, node.get_parameter_value("prompt"),
                deepcopy(node.get_parameter_value("image_model_settings")),
                sorted(parameter.name for parameter in node.parameters if parameter.name.startswith("model_option__")),
                node.get_parameter_value("model_id"), slot)

        # The former visible image_url port is now hidden but remains a valid
        # saved-workflow connection. The canonical preview/output stays public.
        first_name = next(iter(expected))
        first_node = engine.node_manager.get_node_by_name(first_name)
        assert first_node.get_parameter_by_name("image_url").hide
        assert not first_node.get_parameter_by_name("IMAGE_OUT").hide
        for port, sink_name in (("image_url", "Legacy image alias consumer"), ("IMAGE_OUT", "Canonical image consumer")):
            created = send(engine, CreateNodeRequest(node_type="FixtureImageSink", node_name=sink_name,
                specific_library_name=schema.name, initial_setup=True))
            send(engine, CreateConnectionRequest(source_node_name=first_name, source_parameter_name=port,
                target_node_name=created.node_name, target_parameter_name="image", initial_setup=True))
            preserved_edges.append((first_name, port, created.node_name))
        assert_preserved_edges()

        assert len({row[1] for row in expected.values()}) == 5
        assert len({item["client_request_id"] for item in creates}) == 5
        assert len(set(item["prompt"] for item in creates)) == 5
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=ensured.flow_name))
        send(engine, DeleteFlowRequest(flow_name=None))
        before_counts = len(creates), len(refreshes), len(downloads)
        restored = send(engine, DeserializeFlowFromCommandsRequest(serialized_flow_commands=serialized.serialized_flow_commands))
        assert before_counts == (len(creates), len(refreshes), len(downloads)), "Reopen invoked a Broker operation"
        flow = engine.flow_manager.get_flow_by_name(restored.flow_name)
        assert_preserved_edges()
        for name, (path, task_id, checkpoint, original, prompt, model_settings, parameter_names, model_id, slot) in expected.items():
            node = flow.nodes[name]
            attach(node)
            assert node._checkpoint() == checkpoint
            assert node.get_parameter_value("prompt") == prompt
            assert node.get_parameter_value("image_model_settings") == model_settings
            restored_names = sorted(parameter.name for parameter in node.parameters
                                    if parameter.name.startswith("model_option__"))
            assert restored_names == parameter_names, {
                "condition": "Flow hydration changed dynamic parameter definitions", "node": name,
                "added": sorted(set(restored_names) - set(parameter_names)),
                "missing": sorted(set(parameter_names) - set(restored_names)),
                "before_count": len(parameter_names), "after_count": len(restored_names),
            }
            assert node.get_parameter_value("model_id") == model_id
            # Check the original completed task immediately after hydration.
            # Later authoring/model edits legitimately invalidate SDK status.
            assert assert_output(node, Path(path), task_id) == original
            node.set_parameter_value("model_id", "google/gemini-3-pro-image")
            assert node.get_parameter_value("image_size") == "4K"
            assert node.get_parameter_value("ratio") == "4:3"
            assert option(node, "temperature") == slot / 10
            assert option(node, "top_p") == 0.0
            node.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
            assert node.get_parameter_value("image_size") == "512"
            assert node.get_parameter_value("ratio") == "1:8"
            assert option(node, "temperature") == 1.0 + slot / 10
            assert option(node, "use_google_image_search") is (slot % 2 == 0)
            assert node.get_parameter_value("auto_image_resize") is False
            node.set_parameter_value("model_id", model_id)
            assert node.get_parameter_value("image_model_settings") == model_settings
            await node._execute("retrieve")
            assert assert_output(node, Path(path), task_id) == original
        assert len(creates) == len(downloads) == 5
        # A locked or deleted node must not perform a create, lookup or save.
        node = next(iter(flow.nodes.values()))
        before_counts = len(creates), len(refreshes), len(downloads)
        node.lock = True
        await node.aprocess()
        node.lock = False
        node.after_node_deleted()
        await node.aprocess()
        assert before_counts == (len(creates), len(refreshes), len(downloads))
        assert not ATTEMPTS
        print(json.dumps({"status": "PASS", "native_image_nodes": 5,
            "synthetic_creates": len(creates), "native_serialize_reopen": True,
            "same_task_retrievals": len(refreshes), "local_saves": len(downloads),
            "legacy_alias_and_canonical_edges_restored": len(preserved_edges),
            "per_model_options_resolution_and_native_structure_restored": True,
            "network_requests": 0, "paid_generation": False, "user_workflow_changes": 0}, sort_keys=True))
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-image-host-sdk-") as folder:
        directory = Path(folder)
        env = {key: str(directory / key) for key in (
            "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
            "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
            "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT")}
        for path in env.values():
            Path(path).mkdir()
        with mock.patch.dict(os.environ, env), ExitStack() as guard:
            os.chdir(directory)
            try:
                import _hmb_broker_config as broker_config
                guard.enter_context(mock.patch.object(broker_config, "load_broker_base_url", return_value="https://image-fixture.invalid/GripTapeServer"))
                for key in ("create_connection", "getaddrinfo"):
                    guard.enter_context(mock.patch.object(socket, key, deny))
                native_connect = socket.socket.connect

                def connect(sock, address):
                    caller = sys._getframe(1)
                    if caller.f_code.co_name == "_fallback_socketpair" and Path(caller.f_code.co_filename).name == "socket.py":
                        assert address[0] in {"127.0.0.1", "::1"}
                        return native_connect(sock, address)
                    return deny(sock, address)

                logging.disable(logging.CRITICAL)
                from griptape_nodes.retained_mode.engine import engine_scope
                with asyncio.Runner() as runner:
                    runner.get_loop()
                    with mock.patch.object(socket.socket, "connect", connect), mock.patch.object(socket.socket, "connect_ex", deny):
                        with engine_scope() as engine:
                            runner.run(exercise(engine, directory))
            finally:
                logging.shutdown()
                os.chdir(previous)


if __name__ == "__main__":
    main()
