"""Isolated installed-SDK personal image lifecycle; transport/model always mocked.

Exercises native node parameters, output artifacts and saved command hydration.
It does not operate an open workflow or call a provider or production Broker.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import HMBImageGeneration as target
import _hmb_image_generation as protocol
from PIL import Image
from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
from griptape_nodes.retained_mode.engine import engine_scope
from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest, DeleteNodeRequest, DeserializeNodeFromCommandsRequest, SerializeNodeToCommandsRequest,
)
from griptape_nodes.serialization.values import decode_value

buffer = io.BytesIO()
Image.new("RGB", (19, 11), (34, 67, 120)).save(buffer, "PNG")
PNG = buffer.getvalue()
LEGACY_RAW_CAPABILITIES = {
    "schema": protocol.CAPABILITIES_SCHEMA, "version": 1, "enabled": True,
    "persistence_scope": "personal_local", "client_request_lookup": True,
    "models": [dict(provider=provider, model_id=model, display_name=label,
                    enabled=True, credential_ready=True, tasks=["text-to-image", "image-to-image"],
                    aspect_ratios=["1:1", "16:9"], image_sizes=["1K", "2K"], output_formats=["png"],
                    max_reference_images=3, max_reference_bytes=1024 * 1024)
               for provider, model, label in (("google", "gemini-3-pro-image", "Nano Banana Pro"),
                    ("future-provider", "future-model", "Independent future model"))]}
CAPABILITIES = protocol.parse_capabilities(LEGACY_RAW_CAPABILITIES)


def option_capabilities(*, include_future=False):
    """Synthetic advertised profiles, independent of bundled provider defaults."""
    properties = {
        "temperature": {"type": "number", "label": "Temperature", "default": 1.0,
                        "minimum": 0, "maximum": 2, "step": 0.1},
        "top_p": {"type": "number", "label": "Top P", "default": 0.95,
                  "minimum": 0, "maximum": 1, "step": 0.05},
        "use_google_search": {"type": "boolean", "label": "Google Search", "default": False},
        "mode": {"type": "string", "label": "Mode", "default": "fast", "enum": ["fast", "quality"]},
        "seed": {"type": "integer", "label": "Seed", "default": 0, "minimum": 0, "maximum": 100, "step": 1},
        "label": {"type": "string", "label": "Label", "default": "", "max_length": 64},
    }
    pro = deepcopy(LEGACY_RAW_CAPABILITIES["models"][0])
    pro.update(image_sizes=["1K", "2K", "4K"], aspect_ratios=["1:1", "16:9", "4:3"],
        defaults={"task": "text-to-image", "ratio": "1:1", "image_size": "1K", "output_format": "png"},
        option_schema={"schema": "hmb-image-model-options-v1", "revision": "pro-fixture-v1", "properties": properties})
    nb2 = deepcopy(pro)
    nb2.update(model_id="gemini-3.1-flash-image", display_name="Nano Banana 2",
        image_sizes=["512", "1K", "2K", "4K"], aspect_ratios=["1:1", "16:9", "1:8"],
        defaults={"task": "text-to-image", "ratio": "16:9", "image_size": "512", "output_format": "png"})
    nb2["option_schema"]["revision"] = "nb2-fixture-v1"
    nb2["option_schema"]["properties"]["use_google_image_search"] = {
        "type": "boolean", "label": "Google Image Search", "default": False}
    raw = deepcopy(LEGACY_RAW_CAPABILITIES)
    raw["models"] = [pro, nb2]
    if include_future:
        future = deepcopy(pro)
        future.update(provider="synthetic-provider", model_id="synthetic-image-model", display_name="Synthetic typed model")
        future["option_schema"] = {"schema": "hmb-image-model-options-v1", "revision": "future-fixture-v1", "properties": {
            "custom_mode": {"type": "string", "label": "Custom Enum", "default": "draft", "enum": ["draft", "quality"]},
            "custom_budget": {"type": "integer", "label": "Custom Integer", "default": 0, "minimum": 0, "maximum": 8},
            "custom_weight": {"type": "number", "label": "Custom Number", "default": 1.0, "minimum": 0, "maximum": 2},
            "custom_enabled": {"type": "boolean", "label": "Custom Boolean", "default": True},
            "custom_label": {"type": "string", "label": "Custom String", "default": "base", "max_length": 64},
        }}
        raw["models"].append(future)
    return protocol.parse_capabilities(raw)


def forbidden(*_args, **_kwargs):
    raise AssertionError("Real network, provider generation or SDK File upload is forbidden in this test")


original_connect = socket.socket.connect
def local_connect(sock, address):
    # asyncio's native Windows event loop creates its own local socket pair.
    if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
        return original_connect(sock, address)
    return forbidden()


class Backend:
    def __init__(self):
        self.created = []
        self.capabilities = CAPABILITIES
        self.refreshed = []
        self.saved = []
        self.capability_calls = 0
        self.account_calls = 0
        self.error = None
        self.capability_error = None
        self.account_error = None
        self.status = "succeeded"
        self.job_fields = {}
        self.save_error = None
        self.after_save = None
        self.block_capabilities = False
        self.capabilities_started = threading.Event()
        self.capabilities_release = threading.Event()
        self.block_create = False
        self.started = threading.Event()
        self.release = threading.Event()

    def record(self, invocation, status="succeeded"):
        number = self.created.index(invocation) + 1
        record = dict(schema=protocol.JOB_SCHEMA, version=1, status=status, job_id=f"job-personal-{number}",
            provider=invocation.provider, model=invocation.model_id, client_request_id=invocation.client_request_id,
            persistence_scope="personal_local", publish_to_reviews=False,
            result=dict(url="https://broker.invalid/api/assets/" + "a" * 43, mime_type="image/png",
                        sha256=hashlib.sha256(PNG).hexdigest()))
        record.update(deepcopy(self.job_fields))
        return record

    def factory(self, *, server_url):
        backend = self
        class FakeBroker:
            def __init__(self):
                self.server_url = server_url
            def account_snapshot(self, *, connect=False):
                backend.account_calls += 1
                if backend.account_error:
                    raise backend.account_error
                return SimpleNamespace(connected=True, state="connected", account="offline-personal-user")
            def capabilities(self):
                backend.capability_calls += 1
                if backend.capability_error:
                    raise backend.capability_error
                backend.capabilities_started.set()
                if backend.block_capabilities and not backend.capabilities_release.wait(8):
                    raise AssertionError("Fixture did not release the blocked catalogue request")
                return backend.capabilities
            def create(self, invocation, *, is_alive=None, **kwargs):
                backend.created.append(invocation)
                backend.started.set()
                if backend.block_create:
                    if not backend.release.wait(8):
                        raise AssertionError("Fixture did not release the blocked image request")
                if backend.error:
                    raise backend.error
                return backend.record(invocation, backend.status)
            def refresh(self, job_id, *, client_request_id="", **kwargs):
                backend.refreshed.append((job_id, client_request_id))
                invocation = next(value for value in backend.created if value.client_request_id == client_request_id)
                return backend.record(invocation, backend.status)
            def save_result(self, job, output_path, *, is_alive=None):
                backend.saved.append(job["job_id"])
                if backend.save_error:
                    raise backend.save_error
                saved = protocol.save_image_atomic(protocol.validate_image_bytes(PNG), output_path, is_alive=is_alive)
                if backend.after_save:
                    backend.after_save()
                return saved
        return FakeBroker()


class PersonalImageNodeTests(unittest.TestCase):
    def test_queue_headers_survive_native_reopen_and_same_request_recovery(self):
        import _hmb_queue_admission as queue
        raw=json.loads((ROOT/'resources/tests/HMB_Maintenance_Queue_Fixture.json').read_text('utf-8'))
        admission=queue.parse(raw)
        self.authored()
        self.backend.capabilities=replace(protocol.parse_capabilities(raw['image_syntax']),_queue_admission=admission)
        self.backend.error=protocol.ImageGenerationError('Synthetic response loss',submission_outcome_unknown=True)
        self.run_node()
        cp=self.node._checkpoint()
        self.assertEqual(cp['queue_only_headers'],admission.headers)
        self.assertEqual(len(self.backend.created),1)
        self.node=self.reopen_options_node(self.node)
        self.assertEqual(self.node._checkpoint()['queue_only_headers'],admission.headers)
        self.backend.error=None
        self.run_node()
        self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.node._checkpoint()['queue_only_headers'],admission.headers)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb-personal-image-sdk-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        environment = {name: str(self.folder / name) for name in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA")}
        self.patches = [mock.patch.dict(os.environ, environment),
            mock.patch.object(socket, "create_connection", forbidden),
            mock.patch.object(socket.socket, "connect", local_connect),
            mock.patch.object(urllib.request, "urlopen", forbidden),
            mock.patch.object(urllib.request.OpenerDirector, "open", forbidden),
            mock.patch.object(target.broker_config, "load_broker_base_url", return_value="https://broker.invalid")]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.shutdown)
        scope = engine_scope()
        self.engine = scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        self.engine.event_manager.initialize_queue()
        result = self.engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="PersonalImageOffline"))
        self.assertTrue(result.succeeded(), str(result.result_details))
        self.flow = self.engine.flow_manager.get_flow_by_name(result.flow_name)
        self.schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
        self.library = LibraryRegistry.generate_new_library(self.schema)
        self.addCleanup(LibraryRegistry.unregister_library, self.schema.name, event_manager=self.engine.event_manager)
        definition = next(item for item in self.schema.nodes if item.class_name == "HMBImageGeneration")
        self.library.register_lazy_node_type(definition.class_name, definition.metadata, lambda: target.HMBImageGeneration)
        self.backend = Backend()
        self.node = self.create("Personal image")

    def send(self, request):
        request.broadcast_result = False
        result = self.engine.handle_request(request)
        self.assertTrue(result.succeeded(), str(result.result_details))
        return result

    def configure(self, node):
        node._broker_factory = self.backend.factory
        node._output_file.build_file = lambda **kwargs: SimpleNamespace(resolve=lambda: str(self.folder / "image.png"))
        node.publish_update_to_parameter = mock.Mock()
        return node

    def create(self, name):
        result = self.send(CreateNodeRequest(node_type="HMBImageGeneration", specific_library_name=self.schema.name,
            node_name=name, create_error_proxy_on_failure=False))
        return self.configure(self.engine.node_manager.get_node_by_name(result.node_name))

    def run_node(self, node=None, action="run"):
        asyncio.run((node or self.node)._execute(action))

    def authored(self):
        self.node.set_parameter_value("prompt", "Keep the exact authored image prompt {literal} 0 OFF")

    def references(self, values):
        parameter = self.node.get_parameter_by_name("reference_images")
        parameter.ensure_length(len(values))
        for child, value in zip(parameter.get_child_parameters(), values, strict=True):
            self.node.set_parameter_value(child.name, value)

    def option_parameter(self, key, node=None):
        node = node or self.node
        name = node._active_option_parameters[key]
        parameter = node.get_parameter_by_name(name)
        self.assertIsNotNone(parameter, key)
        return parameter

    def set_option(self, key, value, node=None):
        node = node or self.node
        node.set_parameter_value(self.option_parameter(key, node).name, value)

    def option_value(self, key, node=None):
        node = node or self.node
        return node.get_parameter_value(self.option_parameter(key, node).name)

    def model_settings(self, node=None):
        value = deepcopy((node or self.node).get_parameter_value("image_model_settings"))
        self.assertEqual(value["schema"], "hmb-image-model-settings-v1")
        self.assertIsInstance(value["models"], dict)
        return value

    def reopen_options_node(self, node):
        pool = {}
        serialized = self.send(SerializeNodeToCommandsRequest(node_name=node.name,
            unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True))
        name = node.name
        self.send(DeleteNodeRequest(node_name=name))
        commands = deepcopy(serialized.serialized_node_commands)
        commands.create_node_command.node_name = name
        commands.create_node_command.override_parent_flow_name = self.flow.name
        result = self.send(DeserializeNodeFromCommandsRequest(serialized_node_commands=commands))
        reopened = self.configure(self.engine.node_manager.get_node_by_name(result.node_name))
        for indirect in serialized.set_parameter_value_commands:
            request = deepcopy(indirect.set_parameter_value_command)
            request.node_name = reopened.name
            request.value = decode_value(deepcopy(pool[indirect.unique_value_uuid]))
            request.initial_setup = True
            self.send(request)
        return reopened

    def assert_success(self, node=None):
        node = node or self.node
        self.assertTrue(node._execution_succeeded, node.parameter_output_values.get("result_details"))
        self.assertEqual(node.get_parameter_value("image_recovery")["status"], "succeeded")
        artifact = node.parameter_output_values["IMAGE_OUT"]
        self.assertIsInstance(artifact, ImageUrlArtifact)
        self.assertEqual(Path(artifact.value).read_bytes(), PNG)
        self.assertEqual(node.parameter_output_values["image_url"].value, artifact.value)
        self.assertFalse(node._busy)
        return artifact

    def test_construct_edit_and_model_change_are_offline_personal(self):
        names = {parameter.name for parameter in self.node.parameters}
        self.assertFalse({"provider", "project_id", "project_name", "shot", "shot_name", "agent", "api_key"} & names)
        self.assertFalse(self.backend.created)
        self.assertEqual(self.backend.capability_calls, 0)
        self.authored()
        self.run_node(action="connect")
        self.assertEqual(self.backend.account_calls, 1)
        self.assertEqual(self.backend.capability_calls, 1)
        self.node.set_parameter_value("model_id", "future-provider/future-model")
        self.assertEqual(self.backend.capability_calls, 1, "Selecting a cached model repeated network discovery")
        self.assertEqual(self.node._choices["model_id"].choices, ["google/gemini-3-pro-image", "future-provider/future-model"])
        self.run_node()
        self.assert_success()
        payload = self.backend.created[0].payload()
        self.assertEqual(payload["model"], "future-model")
        self.assertEqual(payload["provider"], "future-provider")
        self.assertIs(payload["publish_to_reviews"], False)
        self.assertEqual(payload["persistence_scope"], "personal_local")

    def test_compact_native_ui_keeps_one_visible_image_and_collapsed_status(self):
        header = self.node.get_parameter_by_name("HMB_IMAGE_GENERATION_UI")
        self.assertIsNotNone(header)
        self.assertFalse(header.serializable)
        self.assertEqual(header.allowed_modes, {ParameterMode.PROPERTY})
        self.assertIs(header.ui_options.get("expandable"), False,
            "A widget without expandable=False becomes a weighted grow row in the editor")
        self.assertIs(header.ui_options.get("resizable"), False)
        for key in ("height", "min_height", "max_height", "widget_height"):
            self.assertEqual(header.ui_options.get(key), 64, key)
        status = self.node.status_component.get_parameter_group()
        self.assertEqual(status.name, "Status")
        self.assertIs(status.ui_options.get("collapsed"), True)
        status_names = {child.name for child in status.children}
        self.assertTrue({"was_successful", "result_details", "resume_task_id", "generation_id",
            "generation_status", "broker_status", "broker_connect_refresh", "generation_refresh", "image_notice"} <= status_names)
        for name in ("resume_task_id", "generation_id", "generation_status", "broker_status", "was_successful", "result_details"):
            parameter = self.node.get_parameter_by_name(name)
            self.assertEqual(parameter.allowed_modes, {ParameterMode.PROPERTY}, name)
        visible = [parameter.name for parameter in self.node.parameters if isinstance(parameter, ParameterImage)
            and ParameterMode.OUTPUT in parameter.allowed_modes and not parameter.hide and not parameter.hide_property]
        self.assertEqual(visible, ["IMAGE_OUT"])
        canonical = self.node.get_parameter_by_name("IMAGE_OUT")
        alias = self.node.get_parameter_by_name("image_url")
        self.assertEqual(canonical.allowed_modes, {ParameterMode.PROPERTY, ParameterMode.OUTPUT})
        self.assertEqual(alias.allowed_modes, {ParameterMode.PROPERTY, ParameterMode.OUTPUT})
        self.assertTrue(alias.hide)
        self.assertTrue(alias.ui_options.get("hide_handles"))
        for name in ("model_id", "task", "ratio", "image_size", "output_format"):
            parameter = self.node.get_parameter_by_name(name)
            self.assertIn(ParameterMode.INPUT, parameter.allowed_modes)
            self.assertTrue(parameter.ui_options.get("hide_handles"), name)
        self.assertIn(ParameterMode.INPUT, self.node.get_parameter_by_name("prompt").allowed_modes)
        self.assertIn(ParameterMode.INPUT, self.node.get_parameter_by_name("reference_images").allowed_modes)
        self.assertFalse(self.backend.created)
        self.assertEqual(self.backend.capability_calls, 0)

    def test_model_display_names_keep_exact_saved_and_wire_ids(self):
        self.assertEqual(self.node.get_parameter_value("image_model"), "Nano Banana Pro")
        self.assertEqual(self.node._choices["image_model"].choices, ["Nano Banana Pro", "Nano Banana 2"])
        canonical = self.node.get_parameter_by_name("model_id")
        self.assertTrue(canonical.hide)
        self.assertTrue(canonical.hide_property)
        self.assertTrue(canonical.serializable)
        display = self.node.get_parameter_by_name("image_model")
        self.assertFalse(display.serializable)
        self.assertEqual(display.allowed_modes, {ParameterMode.PROPERTY})
        self.backend.capabilities = option_capabilities()
        self.run_node(action="connect")
        self.authored()
        calls = self.backend.capability_calls
        for label, model in (("Nano Banana 2", "gemini-3.1-flash-image"),
                             ("Nano Banana Pro", "gemini-3-pro-image")):
            self.node.set_parameter_value("image_model", label)
            self.assertEqual(self.node.get_parameter_value("model_id"), "google/" + model)
            self.assertEqual(self.backend.capability_calls, calls)
            self.assertIn("google/" + model, self.node.get_parameter_by_name("image_model").tooltip)
            self.run_node()
            self.assert_success()
            self.assertEqual(self.backend.created[-1].payload()["model"], model)
            self.assertEqual(self.backend.created[-1].payload()["provider"], "google")
            calls = self.backend.capability_calls

    def test_model_labels_preserve_per_model_options_and_saved_reopen(self):
        self.backend.capabilities = option_capabilities()
        self.run_node(action="connect")
        self.node.set_parameter_value("image_model", "Nano Banana Pro")
        self.node.set_parameter_value("image_size", "4K")
        self.set_option("temperature", 0.0)
        self.node.set_parameter_value("image_model", "Nano Banana 2")
        self.node.set_parameter_value("image_size", "512")
        self.set_option("temperature", 2.0)
        before = self.model_settings()
        reopened = self.reopen_options_node(self.node)
        self.assertEqual(reopened.get_parameter_value("image_model"), "Nano Banana 2")
        self.assertEqual(reopened.get_parameter_value("model_id"), "google/gemini-3.1-flash-image")
        self.assertEqual(reopened.get_parameter_value("image_size"), "512")
        self.assertEqual(self.option_value("temperature", reopened), 2.0)
        reopened.set_parameter_value("image_model", "Nano Banana Pro")
        self.assertEqual(reopened.get_parameter_value("image_size"), "4K")
        self.assertEqual(self.option_value("temperature", reopened), 0.0)
        self.assertEqual(self.model_settings(reopened), before)
        self.assertFalse(self.backend.created)

    def test_legacy_canonical_model_hydration_updates_display_without_network(self):
        canonical = self.node.get_parameter_by_name("model_id")
        canonical.update_ui_options({"hide": False, "hide_property": False})
        self.node.set_parameter_value("model_id", "google/gemini-3.1-flash-image", initial_setup=True)
        self.assertTrue(canonical.hide)
        self.assertTrue(canonical.hide_property)
        self.assertEqual(self.node.get_parameter_value("image_model"), "Nano Banana 2")
        self.node.set_parameter_value("model_id", "google/gemini-3-pro-image", initial_setup=True)
        self.assertEqual(self.node.get_parameter_value("image_model"), "Nano Banana Pro")
        self.node.set_parameter_value("model_id", "future-provider/not-advertised", initial_setup=True)
        self.assertEqual(self.node.get_parameter_value("image_model"), "future-provider/not-advertised")
        self.assertFalse(self.backend.created)
        self.assertEqual(self.backend.capability_calls, 0)

    def test_duplicate_or_stale_model_label_never_changes_model_identity(self):
        caps = option_capabilities(include_future=True)
        future = replace(caps.models[-1], display_name="Nano Banana Pro")
        self.backend.capabilities = replace(caps, models=(*caps.models[:-1], future))
        self.run_node(action="connect")
        qualified = "Nano Banana Pro (synthetic-provider/synthetic-image-model)"
        self.assertIn(qualified, self.node._choices["image_model"].choices)
        self.node.set_parameter_value("image_model", qualified)
        self.assertEqual(self.node.get_parameter_value("model_id"), "synthetic-provider/synthetic-image-model")
        self.node.set_parameter_value("image_model", "Nano Banana Pro")
        self.assertEqual(self.node.get_parameter_value("model_id"), "google/gemini-3-pro-image")
        self.node.set_parameter_value("image_model", "stale catalogue entry")
        self.assertEqual(self.node.get_parameter_value("image_model"), "Nano Banana Pro")
        self.assertEqual(self.node.get_parameter_value("model_id"), "google/gemini-3-pro-image")
        self.assertFalse(self.backend.created)

    def test_status_buttons_keep_the_original_native_callback_dispatch(self):
        details = SimpleNamespace(label="fixture")
        sentinel = object()
        for name, action in (("broker_connect_refresh", "connect"), ("generation_refresh", "retrieve")):
            with self.subTest(name=name), mock.patch.object(self.node, "_schedule", return_value=sentinel) as schedule:
                button = self.node.get_parameter_by_name(name)
                self.assertTrue(callable(button.on_click_callback))
                self.assertIs(button.on_click_callback(button, details), sentinel)
                schedule.assert_called_once_with(action, details)
                self.assertFalse(button.serializable)
        self.assertFalse(self.backend.created)

    def test_new_run_preserves_original_and_creates_new_request(self):
        self.authored()
        self.run_node()
        first = self.assert_success()
        original = Path(first.value).read_bytes()
        self.run_node()
        second = self.assert_success()
        self.assertNotEqual(first.value, second.value)
        self.assertEqual(Path(first.value).read_bytes(), original)
        self.assertEqual(len(self.backend.created), 2)
        self.assertNotEqual(self.backend.created[0].client_request_id, self.backend.created[1].client_request_id)

    def test_retrieve_existing_image_does_not_resubmit_or_copy(self):
        self.authored()
        self.run_node()
        first = self.assert_success()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        self.run_node(action="retrieve")
        self.assertEqual(self.assert_success().value, first.value)
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.saved), 1)
        self.assertEqual(self.node.get_parameter_value("image_recovery"), checkpoint)

    def test_model_refresh_success_or_failure_preserves_completed_image_and_status(self):
        self.authored()
        self.run_node()
        self.assert_success()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        preserved = {name: self.node.parameter_output_values.get(name) for name in (
            "IMAGE_OUT", "image_url", "generation_id", "generation_status", "was_successful", "result_details")}
        for failure in (None, "capabilities", "account"):
            with self.subTest(failure=failure):
                self.backend.capability_error = protocol.ImageGenerationError("Test catalogue temporarily unavailable") if failure == "capabilities" else None
                self.backend.account_error = protocol.ImageGenerationError("Test account login unavailable") if failure == "account" else None
                self.run_node(action="connect")
                self.assertTrue(self.node._execution_succeeded)
                self.assertEqual(self.node.get_parameter_value("image_recovery"), checkpoint)
                self.assertEqual({name: self.node.parameter_output_values.get(name) for name in preserved}, preserved)
                self.assertFalse(self.node._busy)
                self.assertEqual(len(self.backend.created), 1)
                self.assertEqual(len(self.backend.saved), 1)
                expected = ("Ready:" if failure is None else
                    "Test catalogue" if failure == "capabilities" else "Test account")
                self.assertIn(expected, self.node.parameter_output_values.get("broker_status", ""))

    def test_save_failure_retries_the_accepted_task_without_another_create(self):
        self.authored()
        self.backend.save_error = protocol.ImageGenerationError("simulated filesystem unavailable", code="IMAGE_SAVE_FAILED")
        self.run_node()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        self.assertEqual(checkpoint["status"], "succeeded")
        self.assertNotIn("saved_path", checkpoint)
        self.assertFalse(self.node._execution_succeeded)
        self.backend.save_error = None
        self.run_node()
        self.assert_success()
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(self.backend.refreshed[-1], (checkpoint["task_id"], checkpoint["client_request_id"]))

    def test_live_edits_during_discovery_change_only_the_next_run(self):
        self.authored()
        self.backend.block_capabilities = True
        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.capabilities_started.wait, 5))
            self.node.set_parameter_value("prompt", "A different later prompt")
            self.node.set_parameter_value("model_id", "future-provider/future-model")
            self.node.set_parameter_value("ratio", "16:9")
            self.backend.capabilities_release.set()
            await running
        asyncio.run(scenario())
        self.assert_success()
        first = self.backend.created[0].payload()
        self.assertEqual(first["prompt"], "Keep the exact authored image prompt {literal} 0 OFF")
        self.assertEqual(first["model"], "gemini-3-pro-image")
        self.assertEqual(first["ratio"], "1:1")
        self.run_node()
        second = self.backend.created[1].payload()
        self.assertEqual(second["prompt"], "A different later prompt")
        self.assertEqual(second["model"], "future-model")
        self.assertEqual(second["ratio"], "16:9")

    def test_unknown_create_is_retrieved_by_the_original_identity(self):
        self.authored()
        self.backend.error = protocol.ImageGenerationError("simulated accepted timeout", submission_outcome_unknown=True)
        self.run_node()
        checkpoint = self.node.get_parameter_value("image_recovery")
        self.assertEqual(checkpoint["status"], "submission_unknown")
        self.assertEqual(checkpoint["task_id"], self.backend.created[0].client_request_id)
        self.backend.error = None
        self.run_node()
        self.assert_success()
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(self.backend.refreshed[0], (checkpoint["task_id"], checkpoint["client_request_id"]))

    def test_running_unknown_create_stops_without_polling_or_replacement(self):
        self.authored()
        self.backend.status = "running"
        self.backend.job_fields = {"submission_outcome_unknown": True,
            "error": {"code": "image_submission_unknown", "message": "provider-raw-body-must-not-be-shown"}}
        with mock.patch.object(target.asyncio, "sleep", side_effect=AssertionError("Unknown submission must not poll")):
            self.run_node()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        self.assertEqual(checkpoint["status"], "submission_unknown")
        self.assertEqual(checkpoint["task_id"], "job-personal-1")
        self.assertEqual(checkpoint["client_request_id"], self.backend.created[0].client_request_id)
        self.assertEqual(checkpoint["output_path"], str(self.folder / "image.png"))
        self.assertFalse(self.node._execution_succeeded)
        self.assertEqual(self.node.parameter_output_values["generation_status"], "submission_unknown")
        details = self.node.get_parameter_value("result_details")
        self.assertIn("outcome is unknown", details)
        self.assertIn("Automatic polling stopped", details)
        self.assertNotIn("provider-raw-body", details)
        self.assertFalse(self.backend.refreshed)
        self.assertFalse(self.backend.saved)
        self.assertFalse(self.node._busy)
        self.run_node()  # An explicit Run while unknown still retrieves the same Task.
        self.run_node(action="retrieve")
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(self.backend.refreshed, [(checkpoint["task_id"], checkpoint["client_request_id"])] * 2)
        self.assertEqual(self.node.get_parameter_value("image_recovery"), checkpoint)

    def test_refresh_unknown_code_stops_after_one_poll_and_keeps_the_original_task(self):
        self.authored()
        self.backend.status = "queued"
        original_record = self.backend.record
        def record(invocation, status="succeeded"):
            result = original_record(invocation, status)
            if self.backend.refreshed:
                result.update(status="running", error={"code": "image_submission_unknown"})
            return result
        async def scenario():
            with mock.patch.object(self.node, "POLL_INTERVAL_SECONDS", 0), mock.patch.object(self.backend, "record", side_effect=record):
                await asyncio.wait_for(self.node.aprocess(), timeout=2)
        asyncio.run(scenario())
        checkpoint = self.node.get_parameter_value("image_recovery")
        self.assertEqual(checkpoint["status"], "submission_unknown")
        self.assertEqual(checkpoint["task_id"], "job-personal-1")
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(self.backend.refreshed, [(checkpoint["task_id"], checkpoint["client_request_id"])])
        self.assertFalse(self.backend.saved)
        self.assertFalse(self.node._busy)

    def test_unknown_task_survives_native_save_reopen_and_recovers_same_result(self):
        self.authored()
        self.backend.status = "running"
        self.backend.job_fields = {"error": {"code": "image_submission_unknown"}}
        self.run_node()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        reopened = self.reopen_options_node(self.node)
        self.assertEqual(reopened.get_parameter_value("image_recovery"), checkpoint)
        self.assertEqual(reopened.get_parameter_value("prompt"), "Keep the exact authored image prompt {literal} 0 OFF")
        self.run_node(reopened, "retrieve")
        self.assertEqual(reopened.get_parameter_value("image_recovery"), checkpoint)
        self.assertEqual(len(self.backend.created), 1)
        self.backend.status = "succeeded"
        self.backend.job_fields = {}
        self.run_node(reopened, "retrieve")
        self.assert_success(reopened)
        self.assertEqual(reopened.get_parameter_value("image_recovery")["task_id"], checkpoint["task_id"])
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.saved), 1)
        payload = self.backend.created[0].payload()
        self.assertEqual(payload["persistence_scope"], "personal_local")
        self.assertIs(payload["publish_to_reviews"], False)
        self.assertFalse({"project_id", "project_name", "shot", "shot_name"} & payload.keys())

    def test_verified_success_is_not_hidden_by_a_stale_unknown_marker(self):
        self.authored()
        self.backend.job_fields = {"submission_outcome_unknown": True,
            "error": {"code": "image_submission_unknown"}}
        self.run_node()
        self.assert_success()
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.saved), 1)

    def test_false_unknown_marker_keeps_normal_pending_poll_and_success(self):
        self.authored()
        original_record = self.backend.record
        def record(invocation, status="succeeded"):
            result = original_record(invocation, status)
            if not self.backend.refreshed:
                result.update(status="running", submission_outcome_unknown=False)
            return result
        async def scenario():
            with mock.patch.object(self.node, "POLL_INTERVAL_SECONDS", 0), mock.patch.object(self.backend, "record", side_effect=record):
                await asyncio.wait_for(self.node.aprocess(), timeout=2)
        asyncio.run(scenario())
        self.assert_success()
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.refreshed), 1)

    def test_unknown_late_response_after_delete_or_native_stop_cannot_publish(self):
        for action in ("delete", "stop"):
            with self.subTest(action=action):
                self.backend = Backend()
                self.backend.status = "running"
                self.backend.job_fields = {"submission_outcome_unknown": True}
                self.backend.block_create = True
                node = self.create("Unknown late " + action)
                node.set_parameter_value("prompt", "A personal test image")
                async def scenario():
                    running = asyncio.create_task(node.aprocess())
                    self.assertTrue(await asyncio.to_thread(self.backend.started.wait, 5))
                    if action == "delete":
                        node.after_node_deleted()
                    else:
                        node.request_cancellation()
                    before = deepcopy(dict(node.parameter_output_values))
                    self.backend.release.set()
                    await running
                    self.assertEqual(dict(node.parameter_output_values), before)
                asyncio.run(scenario())
                checkpoint = node.get_parameter_value("image_recovery")
                self.assertEqual(checkpoint["client_request_id"], self.backend.created[0].client_request_id)
                self.assertEqual(checkpoint["status"], "submitting")
                self.assertEqual(len(self.backend.created), 1)
                self.assertFalse(self.backend.refreshed)
                self.assertFalse(self.backend.saved)
                self.assertFalse(node._busy)

    def test_double_run_is_admitted_only_once(self):
        self.authored()
        self.backend.block_create = True
        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.started.wait, 5))
            await self.node.aprocess()
            self.assertEqual(len(self.backend.created), 1)
            self.backend.release.set()
            await running
        asyncio.run(scenario())
        self.assert_success()

    def test_deleted_late_completion_does_not_publish(self):
        self.authored()
        self.backend.block_create = True
        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.started.wait, 5))
            self.node.after_node_deleted()
            before = deepcopy(dict(self.node.parameter_output_values))
            self.backend.release.set()
            await running
            self.assertEqual(dict(self.node.parameter_output_values), before)
        asyncio.run(scenario())
        self.assertFalse(self.backend.saved)
        self.assertFalse(self.node._busy)

    def test_native_stop_during_catalogue_lookup_prevents_create(self):
        self.authored()
        self.backend.block_capabilities = True
        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.capabilities_started.wait, 5))
            self.node.request_cancellation()
            self.backend.capabilities_release.set()
            await running
        asyncio.run(scenario())
        self.assertFalse(self.backend.created)
        self.assertFalse(self.backend.saved)
        self.assertEqual(self.node.get_parameter_value("image_recovery"), {})
        self.assertFalse(self.node._busy)

    def test_native_stop_after_create_preserves_identity_and_suppresses_late_output(self):
        self.authored()
        self.backend.block_create = True
        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.started.wait, 5))
            self.node.request_cancellation()
            before = deepcopy(dict(self.node.parameter_output_values))
            self.backend.release.set()
            await running
            self.assertEqual(dict(self.node.parameter_output_values), before)
        asyncio.run(scenario())
        self.assertFalse(self.backend.saved)
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        self.assertEqual(checkpoint["client_request_id"], self.backend.created[0].client_request_id)
        self.assertEqual(checkpoint["task_id"], checkpoint["client_request_id"])
        self.assertEqual(checkpoint["status"], "submitting")
        self.node.clear_cancellation()
        self.run_node(action="retrieve")
        self.assert_success()
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(self.backend.refreshed[-1], (checkpoint["task_id"], checkpoint["client_request_id"]))

    def test_native_stop_interrupts_poll_wait_without_another_lookup(self):
        self.authored()
        self.backend.status = "queued"
        self.assertEqual(self.node.POLL_INTERVAL_SECONDS, 30)
        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.started.wait, 5))
            for _ in range(100):
                if self.node.get_parameter_value("image_recovery").get("status") == "queued":
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(self.node.get_parameter_value("image_recovery")["status"], "queued")
            self.node.request_cancellation()
            await asyncio.wait_for(running, timeout=1.5)
        asyncio.run(scenario())
        self.assertFalse(self.backend.refreshed)
        self.assertFalse(self.backend.saved)
        self.assertEqual(len(self.backend.created), 1)
        self.assertFalse(self.node._busy)

    def test_lock_prevents_run_and_model_call(self):
        self.authored()
        self.node.lock = True
        before = deepcopy(dict(self.node.parameter_output_values))
        self.run_node()
        self.assertFalse(self.backend.created)
        self.assertEqual(self.backend.capability_calls, 0)
        self.assertEqual(dict(self.node.parameter_output_values), before)

    def test_failed_run_preserves_previous_original_output(self):
        self.authored()
        self.run_node()
        first = self.assert_success()
        self.node.set_parameter_value("prompt", "")
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertEqual(self.node.parameter_output_values["IMAGE_OUT"].value, first.value)
        self.assertEqual(Path(first.value).read_bytes(), PNG)
        self.assertEqual(len(self.backend.created), 1)

    def test_optional_success_status_hook_failure_cannot_reverse_saved_success(self):
        self.authored()
        original = self.node._set_status_results
        calls = []
        def status(*, was_successful, result_details):
            calls.append(was_successful)
            if was_successful:
                raise ConnectionResetError("test disconnected optional status hook")
            return original(was_successful=was_successful, result_details=result_details)
        with mock.patch.object(self.node, "_set_status_results", side_effect=status):
            self.run_node()
            first = self.assert_success()
            checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
            self.assertIs(self.node.parameter_output_values["was_successful"], True)
            self.run_node(action="retrieve")
            self.assertEqual(self.assert_success().value, first.value)
        self.assertEqual(calls, [True, True], "A completed image was followed by false failure status")
        self.assertEqual(self.node.get_parameter_value("image_recovery"), checkpoint)
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.saved), 1)

    def test_native_output_event_failure_keeps_committed_image_task_and_success(self):
        self.authored()
        outputs = self.node.parameter_output_values
        original = type(outputs)._emit_parameter_change_event
        armed = [False]
        failed_names = []
        self.backend.after_save = lambda: armed.__setitem__(0, True)
        def emit(owner, parameter_name, value, *, deleted=False):
            if owner is outputs and armed[0]:
                failed_names.append(parameter_name)
                raise OSError("test editor event transport unavailable after save")
            return original(owner, parameter_name, value, deleted=deleted)
        with mock.patch.object(type(outputs), "_emit_parameter_change_event", autospec=True, side_effect=emit):
            self.run_node()
            first = self.assert_success()
            checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
            self.assertIs(self.node.parameter_output_values["was_successful"], True)
            self.assertIn("IMAGE_OUT", failed_names)
            self.assertIn("result_details", failed_names)
            self.assertEqual(len(list(self.folder.glob("image*.png"))), 1)
            armed[0] = False  # Native beginning-execution clear remains normal.
            self.run_node(action="retrieve")
            self.assertEqual(self.assert_success().value, first.value)
        self.assertEqual(self.node.get_parameter_value("image_recovery"), checkpoint)
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.saved), 1)

    def test_external_reference_is_rejected_before_create(self):
        self.authored()
        self.node.set_parameter_value("task", "image-to-image")
        self.references(["https://outside.invalid/private.png"])
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertFalse(self.backend.created)
        self.assertFalse(self.node._busy)

    def test_image_edit_submits_original_reference_bytes(self):
        self.authored()
        reference = self.folder / "source.png"
        reference.write_bytes(PNG)
        self.node.set_parameter_value("task", "image-to-image")
        self.references([ImageUrlArtifact(value=str(reference))])
        self.run_node()
        self.assert_success()
        references = self.backend.created[0].payload()["reference_images"]
        import base64
        self.assertEqual(base64.b64decode(references[0].split(",", 1)[1]), PNG)

    def test_custom_saved_model_is_not_replaced_before_server_refresh(self):
        self.node.set_parameter_value("model_id", "new-provider/model-not-yet-advertised", initial_setup=True)
        self.assertEqual(self.node.get_parameter_value("model_id"), "new-provider/model-not-yet-advertised")
        self.authored()
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertFalse(self.backend.created)
        self.assertEqual(self.node.get_parameter_value("model_id"), "new-provider/model-not-yet-advertised")

    def test_unregistered_server_key_blocks_before_create(self):
        self.authored()
        unavailable = replace(CAPABILITIES.models[0], credential_ready=False)
        self.backend.capabilities = replace(CAPABILITIES, models=(unavailable,))
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertFalse(self.backend.created)
        self.assertFalse(self.backend.saved)
        self.assertEqual(self.node.get_parameter_value("image_recovery"), {})
        self.assertIn("API key", self.node.get_parameter_value("result_details") or "")

    def test_model_specific_resolution_ratio_and_authored_options_survive_switches(self):
        self.backend.capabilities = option_capabilities()
        self.run_node(action="connect")
        self.assertEqual(self.node.get_parameter_by_name("image_size").ui_options.get("display_name"), "Resolution / 해상도")
        self.assertEqual(self.node._choices["image_size"].choices, ["1K", "2K", "4K"])
        self.assertEqual(self.node._choices["ratio"].choices, ["1:1", "16:9", "4:3"])
        for key, value in (("image_size", "4K"), ("ratio", "4:3")):
            self.node.set_parameter_value(key, value)
        self.set_option("temperature", 0.4)
        self.set_option("mode", "quality")
        pro_names = dict(self.node._active_option_parameters)
        self.node.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
        self.assertEqual(self.node._choices["image_size"].choices, ["512", "1K", "2K", "4K"])
        self.assertEqual(self.node._choices["ratio"].choices, ["1:1", "16:9", "1:8"])
        self.assertEqual(self.node.get_parameter_value("image_size"), "512")
        self.node.set_parameter_value("ratio", "1:8")
        self.set_option("temperature", 0.8)
        self.set_option("use_google_image_search", True)
        nb2_names = dict(self.node._active_option_parameters)
        calls = self.backend.capability_calls
        for _ in range(5):
            self.node.set_parameter_value("model_id", "google/gemini-3-pro-image")
            self.assertEqual(self.node.get_parameter_value("image_size"), "4K")
            self.assertEqual(self.node.get_parameter_value("ratio"), "4:3")
            self.assertEqual(self.option_value("temperature"), 0.4)
            self.assertEqual(self.option_value("mode"), "quality")
            self.assertEqual(self.node._active_option_parameters, pro_names)
            self.assertNotIn("use_google_image_search", self.node._active_option_parameters)
            self.node.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
            self.assertEqual(self.node.get_parameter_value("image_size"), "512")
            self.assertEqual(self.node.get_parameter_value("ratio"), "1:8")
            self.assertEqual(self.option_value("temperature"), 0.8)
            self.assertIs(self.option_value("use_google_image_search"), True)
            self.assertEqual(self.node._active_option_parameters, nb2_names)
        self.assertEqual(self.backend.capability_calls, calls, "Page/model switching repeated capability discovery")
        self.assertFalse(self.backend.created)

    def test_legacy_hydration_without_new_cache_preserves_authored_model_core(self):
        # A workflow saved before image_model_settings existed replays only its
        # old native fields. Constructor defaults must not masquerade as saved
        # per-model authoring and overwrite the restored NB2 core on Connect.
        self.backend.capabilities = option_capabilities()
        self.node.set_parameter_value("model_id", "google/gemini-3.1-flash-image", initial_setup=True)
        self.node.set_parameter_value("image_size", "4K", initial_setup=True)
        self.node.set_parameter_value("ratio", "16:9", initial_setup=True)
        self.authored()
        self.run_node(action="connect")
        self.assertEqual(self.node.get_parameter_value("model_id"), "google/gemini-3.1-flash-image")
        self.assertEqual(self.node.get_parameter_value("image_size"), "4K")
        self.assertEqual(self.node.get_parameter_value("ratio"), "16:9")
        self.node.set_parameter_value("model_id", "google/gemini-3-pro-image")
        self.node.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
        self.assertEqual(self.node.get_parameter_value("image_size"), "4K")
        self.assertEqual(self.node.get_parameter_value("ratio"), "16:9")
        self.run_node()
        self.assert_success()
        payload = self.backend.created[-1].payload()
        self.assertEqual((payload["model"], payload["image_size"], payload["ratio"]),
                         ("gemini-3.1-flash-image", "4K", "16:9"))

    def test_future_advertised_native_types_preserve_zero_false_and_original_strings(self):
        from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
        from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
        from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
        from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
        self.backend.capabilities = option_capabilities(include_future=True)
        self.run_node(action="connect")
        self.node.set_parameter_value("model_id", "synthetic-provider/synthetic-image-model")
        self.authored()
        overrides = {"custom_mode": "quality", "custom_budget": 0, "custom_weight": 0.0,
                     "custom_enabled": False, "custom_label": "  exact {literal} 0 OFF  "}
        types = {"custom_mode": ParameterString, "custom_budget": ParameterInt, "custom_weight": ParameterFloat,
                 "custom_enabled": ParameterBool, "custom_label": ParameterString}
        for key, value in overrides.items():
            parameter = self.option_parameter(key)
            self.assertIsInstance(parameter, types[key])
            self.assertEqual(parameter.allowed_modes, {ParameterMode.PROPERTY})
            self.assertTrue(parameter.serializable, "Native scalar options must not poison the SDK shared value tracker")
            self.assertTrue(parameter.ui_options.get("hide_handles"))
            self.set_option(key, value)
        self.run_node()
        self.assert_success()
        payload = self.backend.created[-1].payload()
        self.assertEqual(payload["model_options"], overrides)
        self.assertEqual(payload["model_options_schema_revision"], "future-fixture-v1")
        self.assertIs(payload["model_options"]["custom_enabled"], False)
        self.assertIs(type(payload["model_options"]["custom_budget"]), int)
        self.assertNotIn("auto_image_resize", payload)

    def test_core_options_and_client_resize_snapshot_are_frozen_before_discovery(self):
        self.backend.capabilities = option_capabilities()
        self.run_node(action="connect")
        self.authored()
        self.node.set_parameter_value("image_size", "4K")
        self.node.set_parameter_value("ratio", "4:3")
        self.node.set_parameter_value("auto_image_resize", True)
        self.set_option("temperature", 0.0)
        self.set_option("top_p", 0.0)
        self.set_option("use_google_search", False)
        self.set_option("seed", 0)
        self.set_option("label", "before discovery")
        self.backend.capabilities_started.clear()
        self.backend.block_capabilities = True

        async def scenario():
            running = asyncio.create_task(self.node.aprocess())
            self.assertTrue(await asyncio.to_thread(self.backend.capabilities_started.wait, 5))
            self.node.set_parameter_value("image_size", "1K")
            self.node.set_parameter_value("ratio", "16:9")
            self.node.set_parameter_value("auto_image_resize", False)
            self.set_option("temperature", 1.2)
            self.set_option("use_google_search", True)
            self.set_option("label", "next run")
            self.backend.capabilities_release.set()
            await running

        with mock.patch.object(target, "prepare_invocation", wraps=protocol.prepare_invocation) as prepare:
            asyncio.run(scenario())
        self.assert_success()
        payload = self.backend.created[-1].payload()
        self.assertEqual((payload["image_size"], payload["ratio"]), ("4K", "4:3"))
        self.assertEqual(payload["model_options"]["temperature"], 0.0)
        self.assertEqual(payload["model_options"]["top_p"], 0.0)
        self.assertIs(payload["model_options"]["use_google_search"], False)
        self.assertEqual(payload["model_options"]["seed"], 0)
        self.assertEqual(payload["model_options"]["label"], "before discovery")
        self.assertIs(prepare.call_args.kwargs["auto_image_resize"], True)
        self.assertEqual(self.node.get_parameter_value("image_size"), "1K")
        self.assertEqual(self.option_value("label"), "next run")
        self.assertNotIn("auto_image_resize", payload)

    def test_per_model_settings_and_future_controls_survive_native_cold_reopen(self):
        self.backend.capabilities = option_capabilities(include_future=True)
        self.run_node(action="connect")
        self.authored()
        self.node.set_parameter_value("image_size", "4K")
        self.set_option("temperature", 0.2)
        self.node.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
        self.node.set_parameter_value("image_size", "512")
        self.node.set_parameter_value("auto_image_resize", False)
        self.set_option("use_google_image_search", True)
        self.node.set_parameter_value("model_id", "synthetic-provider/synthetic-image-model")
        self.set_option("custom_budget", 0)
        self.set_option("custom_enabled", False)
        self.set_option("custom_label", "cold saved authoring")
        before = self.model_settings()
        names_before = sorted(parameter.name for parameter in self.node.parameters
                              if parameter.name.startswith("model_option__"))
        calls_before = self.backend.capability_calls, len(self.backend.created), len(self.backend.saved)
        reopened = self.reopen_options_node(self.node)
        self.assertEqual(self.model_settings(reopened), before)
        self.assertEqual(sorted(parameter.name for parameter in reopened.parameters
                                if parameter.name.startswith("model_option__")), names_before,
                         "Native parameter hydration duplicated dynamic controls or generated _1 names")
        self.assertEqual(reopened.get_parameter_value("model_id"), "synthetic-provider/synthetic-image-model")
        self.assertEqual(self.option_value("custom_label", reopened), "cold saved authoring")
        self.assertIs(self.option_value("custom_enabled", reopened), False)
        self.assertEqual(self.option_value("custom_budget", reopened), 0)
        reopened.set_parameter_value("model_id", "google/gemini-3-pro-image")
        self.assertEqual(reopened.get_parameter_value("image_size"), "4K")
        self.assertEqual(self.option_value("temperature", reopened), 0.2)
        reopened.set_parameter_value("model_id", "google/gemini-3.1-flash-image")
        self.assertEqual(reopened.get_parameter_value("image_size"), "512")
        self.assertIs(reopened.get_parameter_value("auto_image_resize"), False)
        self.assertIs(self.option_value("use_google_image_search", reopened), True)
        self.assertEqual(calls_before, (self.backend.capability_calls, len(self.backend.created), len(self.backend.saved)),
                         "Cold reopen or cached model switching made a request")

    def test_legacy_catalogue_keeps_eleven_wire_fields_and_rejects_custom_advanced_values(self):
        self.authored()
        self.run_node()
        self.assert_success()
        expected = {"provider", "model", "task", "prompt", "persistence_scope", "publish_to_reviews",
                    "ratio", "image_size", "output_format", "reference_images", "client_request_id"}
        self.assertEqual(set(self.backend.created[-1].payload()), expected)
        self.set_option("temperature", 0.3)
        previous = deepcopy(self.node.get_parameter_value("image_recovery"))
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertEqual(len(self.backend.created), 1, "A legacy Broker silently ignored authored advanced options")
        self.assertEqual(self.option_value("temperature"), 0.3)
        self.assertEqual(self.node.get_parameter_value("image_recovery"), previous)
        self.assertRegex(str(self.node.get_parameter_value("result_details") or ""), "(?i)option|temperature|support|legacy")

    def test_removed_advertised_custom_option_is_preserved_and_rejected_before_create(self):
        self.backend.capabilities = option_capabilities()
        self.run_node(action="connect")
        self.authored()
        self.set_option("mode", "quality")
        original_model = self.backend.capabilities.models[0]
        changed = replace(original_model, option_schema_revision="pro-fixture-v2",
                          options=tuple(option for option in original_model.options if option.name != "mode"))
        self.backend.capabilities = replace(self.backend.capabilities, models=(changed, self.backend.capabilities.models[1]))
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertFalse(self.backend.created, "A disappeared authored option was silently dropped")
        state = self.model_settings()["models"]["google/gemini-3-pro-image"]
        self.assertEqual(state["options"]["mode"], "quality")

    def test_unbounded_advertised_number_builds_native_control_and_submits(self):
        caps = option_capabilities(include_future=True)
        future = caps.models[-1]
        spec = protocol.parse_option_spec("custom_weight", {"type": "number", "default": 0.5})
        future = replace(future, options=tuple(spec if item.name == spec.name else item for item in future.options))
        self.backend.capabilities = replace(caps, models=(*caps.models[:-1], future))
        self.run_node(action="connect")
        self.node.set_parameter_value("model_id", "synthetic-provider/synthetic-image-model")
        self.authored()
        self.set_option("custom_weight", 0.75)
        self.run_node()
        self.assert_success()
        self.assertEqual(self.backend.created[-1].payload()["model_options"]["custom_weight"], 0.75)

    def test_offset_step_number_uses_advertised_origin_without_native_rejection(self):
        caps = option_capabilities(include_future=True)
        future = caps.models[-1]
        spec = protocol.parse_option_spec("custom_weight", {
            "type": "number", "default": 0.05, "minimum": 0.05, "maximum": 1.05, "step": 0.1})
        future = replace(future, options=tuple(spec if item.name == spec.name else item for item in future.options))
        self.backend.capabilities = replace(caps, models=(*caps.models[:-1], future))
        self.run_node(action="connect")
        self.node.set_parameter_value("model_id", "synthetic-provider/synthetic-image-model")
        self.authored()
        self.set_option("custom_weight", 0.15)
        self.assertEqual(self.option_value("custom_weight"), 0.15)
        self.run_node()
        self.assert_success()
        self.assertEqual(self.backend.created[-1].payload()["model_options"]["custom_weight"], 0.15)

    def test_number_to_integer_schema_change_preserves_fraction_and_rejects_before_create(self):
        caps = option_capabilities(include_future=True)
        self.backend.capabilities = caps
        self.run_node(action="connect")
        self.node.set_parameter_value("model_id", "synthetic-provider/synthetic-image-model")
        self.authored()
        self.set_option("custom_weight", 0.5)
        future = caps.models[-1]
        spec = protocol.parse_option_spec("custom_weight", {"type": "integer", "default": 0, "minimum": 0, "maximum": 8})
        future = replace(future, option_schema_revision="future-integer-v2",
            options=tuple(spec if item.name == spec.name else item for item in future.options))
        self.backend.capabilities = replace(caps, models=(*caps.models[:-1], future))
        self.run_node(action="connect")
        self.assertEqual(self.option_value("custom_weight"), 0.5, "New integer converter truncated an authored fraction")
        state = self.model_settings()["models"]["synthetic-provider/synthetic-image-model"]
        self.assertEqual(state["options"]["custom_weight"], 0.5)
        self.run_node()
        self.assertFalse(self.node._execution_succeeded)
        self.assertFalse(self.backend.created)
        self.assertEqual(self.option_value("custom_weight"), 0.5)
        reopened = self.reopen_options_node(self.node)
        self.assertEqual(self.option_value("custom_weight", reopened), 0.5,
                         "Cold hydrate truncated the original invalid-for-integer fraction")
        restored_state = self.model_settings(reopened)["models"]["synthetic-provider/synthetic-image-model"]
        self.assertEqual(restored_state["options"]["custom_weight"], 0.5)
        self.run_node(reopened)
        self.assertFalse(reopened._execution_succeeded)
        self.assertFalse(self.backend.created)
        self.assertEqual(self.option_value("custom_weight", reopened), 0.5)

    def test_schema_label_revision_refresh_keeps_native_structure_bounded(self):
        caps = option_capabilities(include_future=True)
        self.backend.capabilities = caps
        self.run_node(action="connect")
        self.node.set_parameter_value("model_id", "synthetic-provider/synthetic-image-model")
        self.set_option("custom_label", "preserved authored label")
        count = len([parameter for parameter in self.node.parameters if parameter.name.startswith("model_option__")])
        for index in range(12):
            previous = self.backend.capabilities.models[-1]
            future = replace(previous, option_schema_revision=f"future-label-v{index}", options=tuple(
                replace(spec, label=f"Label revision {index}") if spec.name == "custom_label" else spec
                for spec in previous.options))
            self.backend.capabilities = replace(caps, models=(*caps.models[:-1], future))
            self.run_node(action="connect")
            self.assertEqual(len([parameter for parameter in self.node.parameters
                                  if parameter.name.startswith("model_option__")]), count,
                             "Schema labels/revisions leaked stale native controls")
            self.assertEqual(self.option_value("custom_label"), "preserved authored label")
        self.assertFalse(self.backend.created)

    def test_shared_boolean_value_tracker_preserves_completed_status_during_native_reopen(self):
        # The SDK tracker caches serializability by id(value). An opt-out True
        # control before Status poisoned the same singleton used by successful
        # completion. Both scalar controls and completion must serialize.
        self.backend.capabilities = option_capabilities()
        self.run_node(action="connect")
        self.authored()
        self.node.set_parameter_value("auto_image_resize", True)
        self.set_option("use_google_search", True)
        self.assertTrue(self.node.get_parameter_by_name("auto_image_resize").serializable)
        for name in self.node._active_option_parameters.values():
            self.assertTrue(self.node.get_parameter_by_name(name).serializable)
        self.run_node()
        original = self.assert_success()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        reopened = self.reopen_options_node(self.node)
        self.assertIs(reopened.get_parameter_value("was_successful"), True)
        self.assertIs(reopened.parameter_output_values.get("was_successful"), True)
        self.assertEqual(reopened.get_parameter_value("image_recovery"), checkpoint)
        self.assertEqual(Path(reopened.parameter_output_values["IMAGE_OUT"].value).read_bytes(), PNG)
        self.assertEqual(reopened.parameter_output_values["IMAGE_OUT"].value, original.value)
        self.assertIs(reopened.get_parameter_value("auto_image_resize"), True)
        self.assertIs(self.option_value("use_google_search", reopened), True)
        self.assertEqual(len(self.backend.created), 1)

    def test_native_save_restore_keeps_original_checkpoint_and_retrieves(self):
        self.authored()
        # Model an existing workflow made before the fixed header contract.
        legacy_header = self.node.get_parameter_by_name("HMB_IMAGE_GENERATION_UI")
        for key in ("expandable", "resizable", "max_height", "widget_height", "compact"):
            legacy_header.ui_options.pop(key, None)
        legacy_header.ui_options.update(height=72, min_height=72)
        self.run_node()
        first = self.assert_success()
        checkpoint = deepcopy(self.node.get_parameter_value("image_recovery"))
        pool = {}
        serialized = self.send(SerializeNodeToCommandsRequest(node_name=self.node.name,
            unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True))
        old_name = self.node.name
        self.send(DeleteNodeRequest(node_name=old_name))
        commands = deepcopy(serialized.serialized_node_commands)
        commands.create_node_command.node_name = old_name
        commands.create_node_command.override_parent_flow_name = self.flow.name
        result = self.send(DeserializeNodeFromCommandsRequest(serialized_node_commands=commands))
        reopened = self.configure(self.engine.node_manager.get_node_by_name(result.node_name))
        for indirect in serialized.set_parameter_value_commands:
            request = deepcopy(indirect.set_parameter_value_command)
            request.node_name = reopened.name
            request.value = decode_value(deepcopy(pool[indirect.unique_value_uuid]))
            request.initial_setup = True
            self.send(request)
        self.assertEqual(reopened.get_parameter_value("image_recovery"), checkpoint)
        self.assertEqual(reopened.get_parameter_value("prompt"), "Keep the exact authored image prompt {literal} 0 OFF")
        self.assertIs(reopened.status_component.get_parameter_group().ui_options.get("collapsed"), True)
        header = reopened.get_parameter_by_name("HMB_IMAGE_GENERATION_UI")
        self.assertIs(header.ui_options.get("expandable"), False)
        self.assertEqual(header.ui_options.get("height"), 64)
        self.assertTrue(callable(reopened.get_parameter_by_name("broker_connect_refresh").on_click_callback))
        self.assertTrue(callable(reopened.get_parameter_by_name("generation_refresh").on_click_callback))
        self.run_node(reopened, "retrieve")
        self.assertEqual(self.assert_success(reopened).value, first.value)
        self.assertEqual(len(self.backend.created), 1)
        self.assertEqual(len(self.backend.saved), 1)


if __name__ == "__main__":
    result = unittest.main(exit=False)
    print(json.dumps(dict(status="PASS" if result.result.wasSuccessful() else "FAIL",
        tests=result.result.testsRun, transport="mock-only", paid_generation=False)))
    sys.exit(0 if result.result.wasSuccessful() else 1)
