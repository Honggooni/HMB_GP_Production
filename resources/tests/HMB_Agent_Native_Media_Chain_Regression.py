"""Actual installed Standard Agent streaming + HMB media + final payload, offline.

Requires HMB_GRIPTAPE_STANDARD_LIBRARY_PATH. Provider streaming and upload
boundaries are stubbed; socket connections are forbidden for the whole test.
No policy plaintext is copied into this test or emitted in successful output.
"""
from __future__ import annotations

import copy
import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import logging
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from _hmb_bundled_policy_session import install_bundled_policy_session
from griptape.common import DeltaMessage, TextDeltaMessageContent
from griptape.artifacts import ListArtifact, TextArtifact
from griptape.events import EventListener, FinishStructureRunEvent
from griptape.structures import Agent as GtAgent
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape_nodes.drivers.cloud_models import VISION_MODEL_CHOICES
from PIL import Image
import _hmb_shot_routing as routing


def load(name):
    spec = importlib.util.spec_from_file_location("_native_chain_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


agent = load("HMBAgentLibrary")
prompt = load("HMBPromptLibrary")
generator = load("HMBSeedanceGeneration")
finish = load("HMBFinishLookLibrary")
assert agent._BuiltinAgent is not None, "Point HMB_GRIPTAPE_STANDARD_LIBRARY_PATH at the installed Standard Library"
native_module = sys.modules[agent._BuiltinAgent.__module__]
install_bundled_policy_session(agent._hmb)
LITERAL = '{{SIGN}} {{KEEP_ME}} {% include "unavailable" %} {% endraw %} {# literal #} 한글😀\r\n\tC:\\asset\\hero'
_socket_connect = socket.socket.connect


def local_socket_connect(sock, address, *args, **kwargs):
    # Windows asyncio creates a loopback self-pipe. It is not provider I/O.
    if not isinstance(address, tuple) or str(address[0]).casefold() not in {"localhost", "127.0.0.1", "::1"}:
        raise AssertionError("external network forbidden")
    return _socket_connect(sock, address, *args, **kwargs)


def subscription(number):
    return {
        "schema": "hmb-shot-channel-subscription", "version": 1,
        "participant_kind": "seedance", "enabled": True,
        "channel_uuid": "test-channel", "shot_uuid": f"test-shot-{number}",
        "shot_number": number, "shot_name": f"Shot {number}",
    }


def source_fixture(number, image_path):
    state = prompt._default_widget_state()
    state["shot"].update(channel_uuid="test-channel", shot_uuid=f"test-shot-{number}",
                         number=number, name=f"Shot {number}")
    state["images"][0].update(present=True, image_main_type="Character",
                              image_sub_type="Full Appearance", owner=f"hero-{number}",
                              label=f"Approved hero {number}", surface_2d=False)
    state["text"]["PRESERVED_TEXT"] = LITERAL
    state = prompt._normalize_state(state)
    source = SimpleNamespace(name=f"Prompt {number}", _hmb_sync_lock=threading.RLock(),
                             _hmb_current_shot_images=[str(image_path)],
                             _hmb_current_shot_videos=[])
    source._compile_current_prompt_pair = lambda **kw: (
        state, prompt._build_prompt_package(state), prompt._build_data_only_prompt_package(state), "fixture")
    source._hmb_agent_reference_media = lambda expected: prompt.HMBPromptLibrary._hmb_agent_reference_media(source, expected)
    source._hmb_agent_generation_context = lambda expected: prompt.HMBPromptLibrary._hmb_agent_generation_context(source, expected)
    settings = {
        "model_id": generator.MODEL_NAME_SEEDANCE_2_5,
        generator.TASK_PARAMETER: generator.TASK_REFERENCE_TO_VIDEO,
        "duration": 8 if number == 1 else 12,
        "ratio": "16:9" if number == 1 else "9:16", "resolution": "1080p",
    }
    render = SimpleNamespace(name=f"Render {number}", get_parameter_value=lambda name: settings.get(name),
                             _hmb_shot_channel_subscription=lambda: subscription(number))
    render._hmb_agent_generation_settings = lambda: generator.HMBSeedanceGeneration._hmb_agent_generation_settings(render)
    return source, render, source._compile_current_prompt_pair()[2]


def run_native(source, renders, machine, structured=False, expected_pixels=1, custom_input=None):
    if hasattr(native_module, "AgentState"):
        return run_current_native(source, renders, machine, structured=structured,
            expected_pixels=expected_pixels, custom_input=custom_input)
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = True
    node._hmb_native_prompt_read_active = True
    node._hmb_runtime_prompt = machine
    node._hmb_lifecycle_generation = 1
    node._hmb_lifecycle_is_live = lambda generation: True
    node._hmb_ruleset_names = ("project-private", "shot-private")
    _project, _shot, node._hmb_policy_rules, node._hmb_binding_rules = node._load_hmb_rules()
    setattr(node, agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, source)
    node.parameter_output_values = {}
    node.append_value_to_parameter = lambda name, value: node.parameter_output_values.__setitem__(name, node.parameter_output_values.get(name, "") + str(value))
    node.set_parameter_value = lambda name, value, **kw: node.parameter_output_values.__setitem__(name, value)
    node._model_access = SimpleNamespace(raise_if_selection_denied=lambda: None,
                                         model_choices=list(VISION_MODEL_CHOICES))
    selected_driver = GriptapeCloudPromptDriver(model=VISION_MODEL_CHOICES[0], api_key="offline-never-sent")
    schema = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]} if structured else None
    final_text = "Use @image1 for the approved hero; preserve {{SIGN}}; retain the assigned motion."
    expected = json.dumps({"prompt": final_text}) if structured else final_text
    context = {"zero": 0, "disabled": False, "unset": "", "literal": LITERAL}
    values = {"model": selected_driver, "model_provider": "griptape_cloud", "agent": None,
              "include_details": False, "output_schema": schema, "prompt": "public view",
              "additional_context": context, "agent_memory": None}
    captured = []
    def stream(driver, stack):
        captured.append((driver, stack))
        yield DeltaMessage(role="assistant", content=TextDeltaMessageContent(expected))
    with patch.object(agent._BaseAgent, "get_parameter_value", lambda _self, name: values.get(name)), \
         patch.object(agent._BaseAgent, "get_parameter_list_value", lambda _self, name: [{"name": "caller", "rules": ["Keep caller-owned instruction."]}] if name == "rulesets" else []), \
         patch.object(agent.HMBAgentLibrary, "is_cancellation_requested", False), \
         patch.object(native_module, "cloud_driver_auth", return_value={"api_key": "offline-never-sent"}), \
         patch.object(native_module, "require_model_invocation_sync", return_value=None), \
         patch.object(GriptapeCloudPromptDriver, "try_stream", stream), \
         patch.object(routing, "_same_flow_nodes", return_value=("fixture-flow", renders)), \
         patch.object(native_module, "GtAgent", lambda **kwargs: GtAgent(**kwargs) if custom_input is None else GtAgent(input=custom_input, **kwargs)):
        iterator = agent._BaseAgent.process(node)
        next_value = None
        yields = 0
        while True:
            try:
                pending = iterator.send(next_value)
            except StopIteration:
                break
            assert callable(pending)
            yields += 1
            next_value = pending()
    assert yields == len(captured) == 1
    assert captured[0][0] is selected_driver
    assert selected_driver.model == VISION_MODEL_CHOICES[0]
    stack = captured[0][1]
    body = selected_driver._base_params(stack)
    system = "\n".join(message.to_text() for message in stack.system_messages)
    user = "\n".join(message.to_text() for message in stack.user_messages)
    assert "Keep caller-owned instruction." in system
    for rule in node._hmb_policy_rules + node._hmb_binding_rules:
        assert rule in system
    assert "Super Wings theatrical render look" in system
    assert machine in user
    assert '"zero":0' in user and '"disabled":false' in user and '"unset":""' in user
    assert "{{KEEP_ME}}" in user
    serialized_context = user.split("HMB ADDITIONAL CONTEXT DATA (JSON):\n", 1)[1].splitlines()[0]
    assert json.loads(serialized_context) == context
    assert "HMB CURRENT GENERATOR SETTINGS" in user
    images = [content for message in stack.user_messages for content in message.content
              if content.__class__.__name__ == "ImageMessageContent"]
    assert len(images) == expected_pixels
    assert str(source._hmb_current_shot_images[0]) not in user
    assert values["output_schema"] == schema
    if structured:
        assert next_value.tasks[0].output_schema is not None
        assert "prompt" in next_value.tasks[0].output_schema.model_json_schema()["properties"]
        assert json.loads(node.parameter_output_values["output"])["prompt"] == final_text
    else:
        assert node.parameter_output_values["output"] == final_text
    assert "_process_task_input" not in next_value.tasks[0].__dict__
    return final_text, user, images[0] if images else None


def run_current_native(source, renders, machine, structured=False, expected_pixels=1, custom_input=None):
    """Use current native process/runner/serialization, never obsolete symbols."""
    from HMB_Agent_Current_Standard_Transport_Regression import NativeTransport
    fixture = NativeTransport(methodName="test_current_native_text_model_bound_bytes_rules_and_literals")
    fixture.setUp()
    try:
        fixture.node._hmb_runtime_prompt = machine
        setattr(fixture.node, agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, source)
        fixture.values["additional_context"] = {"zero": 0, "disabled": False, "unset": "", "literal": LITERAL}
        fixture.final_text = "Use @image1 for the approved hero; preserve {{SIGN}}; retain the assigned motion."
        fixture.structured_field = "prompt"
        if structured:
            fixture.values["output_schema"] = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}
        with patch.object(routing, "_same_flow_nodes", return_value=("fixture-flow", renders)):
            result = fixture.run_native()
        assert len(fixture.captured) == 1
        body = fixture.captured[0]
        assert body["model"] == VISION_MODEL_CHOICES[0]
        messages = [message for message in body["messages"] if message["role"] == "user"]
        content = messages[-1]["content"]
        user = content if isinstance(content, str) else "\n".join(item["text"] for item in content if item["type"] == "text")
        system = json.dumps([m for m in body["messages"] if m["role"] in {"system", "developer"}], ensure_ascii=False)
        assert "Keep caller-owned rule." in system
        for rule in fixture.node._hmb_policy_rules + fixture.node._hmb_binding_rules:
            assert json.dumps(rule, ensure_ascii=False)[1:-1] in system
        assert machine in user and "{{KEEP_ME}}" in user
        assert '"zero":0' in user and '"disabled":false' in user and '"unset":""' in user
        assert "HMB CURRENT GENERATOR SETTINGS" in user
        images = [] if isinstance(content, str) else [item for item in content if item["type"] == "image_url"]
        assert len(images) == expected_pixels
        assert str(source._hmb_current_shot_images[0]) not in user
        if structured:
            assert result.output == {"prompt": fixture.final_text}
            assert json.loads(fixture.node.parameter_output_values["output"]) == result.output
        else:
            assert result.output == fixture.final_text
        if custom_input is not None:
            # Current Standard has no PromptTask.input template. Exercise the
            # genuine legacy Task contract explicitly rather than pretending
            # the current PydanticAI state exposes a legacy task.
            legacy = GtAgent(input=custom_input, prompt_driver=GriptapeCloudPromptDriver(model=VISION_MODEL_CHOICES[0], api_key="offline"))
            def legacy_template(structure, value):
                structure._execution_args = (value,)
                return structure.tasks[0].input.value
            user = agent._run_native_with_literal_hmb_input(legacy_template, legacy, user)
        return fixture.final_text, user, images[0] if images else None
    finally:
        fixture.tearDown()


class NativeChainTests(unittest.TestCase):
    def test_text_fallback_and_custom_native_template_preserve_literals(self):
        source, render, machine = source_fixture(1, Path("C:/unavailable-fixture/hero.png"))
        with patch.object(socket.socket, "connect", new=local_socket_connect):
            for template in (None, "PREFIX {{ args[0] }} SUFFIX"):
                _final, user, pixels = run_native(source, [render], machine, expected_pixels=0, custom_input=template)
                self.assertIsNone(pixels)
                self.assertIn(machine, user)
                if template:
                    self.assertIn("PREFIX ", user)
                    self.assertIn(" SUFFIX", user)

    def test_exact_identity_delegation_existing_hook_and_failure_restoration(self):
        for fail in (None, RuntimeError("offline failure"), asyncio.CancelledError()):
            native = GtAgent(prompt_driver=GriptapeCloudPromptDriver(model=VISION_MODEL_CHOICES[0], api_key="offline"))
            task = native.tasks[0]
            original = task._process_task_input
            delegated = []
            task._process_task_input = lambda value: delegated.append(value) or original(value)
            previous = task._process_task_input
            payload = ListArtifact([TextArtifact(LITERAL)])
            calls = []
            def process(structure, value):
                calls.append(value)
                structure._execution_args = (value,)
                self.assertIs(task.input, payload)
                self.assertEqual(task._process_task_input("{{ 2 + 2 }}").value, "4")
                if fail is not None:
                    raise fail
                return structure
            if fail is None:
                self.assertIs(agent._run_native_with_literal_hmb_input(process, native, payload), native)
            else:
                with self.assertRaises(type(fail)):
                    agent._run_native_with_literal_hmb_input(process, native, payload)
            self.assertEqual(len(calls), 1)
            self.assertIs(task._process_task_input, previous)
            self.assertIn("{{ 2 + 2 }}", delegated)
        calls = []
        def failing_unknown(structure, value):
            calls.append(value)
            raise AttributeError("native failure must not retry")
        with self.assertRaises(AttributeError):
            agent._run_native_with_literal_hmb_input(failing_unknown, SimpleNamespace(tasks=[object()]), "text")
        self.assertEqual(len(calls), 1)

    def test_separate_native_tasks_are_concurrent_and_isolated(self):
        barrier = threading.Barrier(2)
        def execute(number):
            native = GtAgent(prompt_driver=GriptapeCloudPromptDriver(model=VISION_MODEL_CHOICES[0], api_key="offline"))
            text = LITERAL + str(number)
            def process(structure, value):
                structure._execution_args = (value,)
                barrier.wait(timeout=3)
                self.assertEqual(structure.tasks[0].input.value, text)
                return text
            result = agent._run_native_with_literal_hmb_input(process, native, text)
            self.assertNotIn("_process_task_input", native.tasks[0].__dict__)
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(set(pool.map(execute, (1, 2))), {LITERAL + "1", LITERAL + "2"})

    def test_cancelled_native_worker_keeps_literal_until_finish_then_restores(self):
        native = GtAgent(prompt_driver=GriptapeCloudPromptDriver(model=VISION_MODEL_CHOICES[0], api_key="offline", stream=True))
        cancelled = [False]
        release = threading.Event()
        finished = threading.Event()
        def stream(driver, stack):
            cancelled[0] = True
            yield DeltaMessage(role="assistant", content=TextDeltaMessageContent("first"))
            release.wait(timeout=3)
            yield DeltaMessage(role="assistant", content=TextDeltaMessageContent(" final"))
        def on_event(event):
            if event.structure_id == native.id:
                finished.set()
            return event
        workers = ThreadPoolExecutor(max_workers=1)
        def cancelled_ui_processor(structure, value):
            workers.submit(contextvars.copy_context().run, structure.run, value)
            deadline = __import__("time").monotonic() + 2
            while not cancelled[0] and __import__("time").monotonic() < deadline:
                __import__("time").sleep(.005)
            self.assertTrue(cancelled[0])
            return structure
        with patch.object(socket.socket, "connect", new=local_socket_connect), \
             patch.object(GriptapeCloudPromptDriver, "try_stream", stream), \
             EventListener(on_event, event_types=[FinishStructureRunEvent]):
            self.assertIs(agent._run_native_with_literal_hmb_input(cancelled_ui_processor, native, LITERAL), native)
            self.assertTrue(cancelled[0])
            # The UI returned while the real native worker still owns input.
            self.assertIn("_process_task_input", native.tasks[0].__dict__)
            release.set()
            self.assertTrue(finished.wait(timeout=3))
        workers.shutdown(wait=True)
        self.assertNotIn("_process_task_input", native.tasks[0].__dict__)
        self.assertIn(LITERAL, native.conversation_memory.runs[-1].input.to_text())

    def test_cancellation_or_deletion_during_optional_preparation_starts_no_model(self):
        import hashlib
        for mode in ("cancel", "delete", "generation", "delete_clear_policy"):
            node = object.__new__(agent.HMBAgentLibrary)
            node._hmb_rules_active = True
            node._hmb_runtime_prompt = "machine"
            node._hmb_lifecycle_generation = 1
            cancelled = [False]
            def getter(expected):
                if mode == "cancel":
                    cancelled[0] = True
                elif mode in {"delete", "delete_clear_policy"}:
                    node._hmb_node_deleted = True
                    if mode == "delete_clear_policy":
                        node._hmb_rules_active = False
                else:
                    node._hmb_lifecycle_generation = 2
                return {"schema": "hmb-agent-reference-media", "version": 1,
                        "machine_sha256": hashlib.sha256(b"machine").hexdigest(), "images": [], "videos": []}
            setattr(node, agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, SimpleNamespace(_hmb_agent_reference_media=getter))
            sentinel = object()
            with patch.object(agent.HMBAgentLibrary, "is_cancellation_requested", property(lambda self: cancelled[0])), \
                 patch.object(agent._BaseAgent, "_process", side_effect=AssertionError("native must not start")) as native_call:
                self.assertIs(node._process(sentinel, "machine"), sentinel)
                self.assertEqual(native_call.call_count, 0)

    def test_actual_native_streaming_shot_isolation_and_final_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            red, blue = directory / "hero-a.png", directory / "hero-b.png"
            Image.new("RGB", (32, 16), "red").save(red)
            Image.new("RGB", (32, 16), "blue").save(blue)
            source_a, render_a, machine_a = source_fixture(1, red)
            source_b, render_b, machine_b = source_fixture(2, blue)
            with patch.object(socket.socket, "connect", new=local_socket_connect):
                final_a, user_a, pixels_a = run_native(source_a, [render_a, render_b], machine_a)
                final_b, user_b, pixels_b = run_native(source_b, [render_a, render_b], machine_b, structured=True)
                self.assertIn('"duration_seconds":8', user_a)
                self.assertNotIn('"duration_seconds":12', user_a)
                self.assertIn('"target_id":"hero-1"', user_a)
                self.assertNotIn('"target_id":"hero-2"', user_a)
                self.assertIn('"duration_seconds":12', user_b)
                self.assertNotIn('"duration_seconds":8', user_b)
                self.assertNotEqual(pixels_a, pixels_b)
                node = object.__new__(generator.HMBSeedanceGeneration)
                prepared = []
                node._preflight_broker_media_size = lambda payload, fields: None
                node._prepare_media_reference = lambda kind, value: prepared.append((kind, value)) or "https://offline.invalid/" + Path(value).name
                params = {
                    "model_id": generator.SEEDANCE_2_5_MODEL_ID,
                    generator.TASK_PARAMETER: generator.TASK_REFERENCE_TO_VIDEO,
                    "prompt": final_a, "duration": 8, "resolution": "1080p", "ratio": "16:9",
                    "input_mode": generator.INPUT_MODE_MULTIMODAL_REFERENCES,
                    "first_frame": None, "last_frame": None,
                    "reference_images": [str(red), str(blue)],
                    "video_references": ["C:/selected/original.mp4", "C:/selected/mask.mp4"],
                    "reference_audio": [], "generate_audio": False, "watermark": False,
                    "output_format": "mp4", "return_last_frame": False,
                    "execution_expires_after": 3600, "priority": 0,
                    "poll_interval_seconds": 1, "generation_timeout_seconds": 30,
                }
                beauty = finish.default_finish_look_state()
                off = node._build_broker_payload(copy.deepcopy(params))
                self.assertEqual(off["prompt"], final_a)
                self.assertEqual(finish.compile_finish_look_prompt(beauty), "")
                beauty["beauty"].update(enabled=True, brightness=0, saturation=0,
                                         glow_brightness=0, soft_focus=0, blur_amount=0)
                normalized = finish.validate_finish_look_state(beauty)
                self.assertEqual(normalized["beauty"]["brightness"], 0)
                self.assertEqual(normalized["beauty"]["saturation"], 0)
                beauty_text = finish.compile_finish_look_prompt(beauty)
                params["_hmb_finish_look_out"] = beauty_text
                on = node._build_broker_payload(copy.deepcopy(params))
                self.assertIn(final_a, on["prompt"])
                self.assertEqual(on["prompt"].count(beauty_text), 1)
                self.assertIn("monochrome character-surface color response", on["prompt"])
                self.assertIn("feature placement", on["prompt"])
                self.assertEqual(on["image_urls"], ["https://offline.invalid/hero-a.png", "https://offline.invalid/hero-b.png"])
                self.assertEqual(on["video_urls"], ["https://offline.invalid/original.mp4", "https://offline.invalid/mask.mp4"])
                self.assertIs(on["generate_audio"], False)
                self.assertIs(on["watermark"], False)
                self.assertIs(on["return_last_frame"], False)
                self.assertEqual((on["duration_seconds"], on["aspect_ratio"], on["resolution"]), (8, "16:9", "1080p"))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main(verbosity=2)
