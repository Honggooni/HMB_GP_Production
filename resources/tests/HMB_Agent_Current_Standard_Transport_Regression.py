"""Installed Standard native processing and PydanticAI serialization, paid-free.

The actual model's HTTP client uses httpx.MockTransport, not a provider. The
Standard process/build/runner/output-schema/tool/cancellation implementations
remain intact. No user workflow or credential is read.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
if importlib.util.find_spec("griptape_nodes") is None:
    print("HMB_AGENT_CURRENT_STANDARD_TRANSPORT=SKIP (installed SDK required)")
    raise SystemExit(0)

import httpx
from openai import AsyncOpenAI
from PIL import Image
from griptape_nodes.drivers.cloud_models import VISION_MODEL_CHOICES
from griptape_nodes.retained_mode.engine import engine_scope
from griptape_nodes_library.llm import models as native_models
from griptape_nodes_library.llm.agent_state import AgentState
from griptape_nodes_library.llm.model_config import ModelConfig, ModelProvider
import HMBAgentLibrary as hmb
import HMBPromptLibrary as prompt_module
import _hmb_agent_media as media
from _hmb_bundled_policy_session import install_bundled_policy_session

assert hmb._BuiltinAgent is not None
native = sys.modules[hmb._BuiltinAgent.__module__]
install_bundled_policy_session(hmb._hmb)
LITERAL = '{{SIGN}} {% include "unavailable" %} {# literal #} 한글😀\r\nC:\\asset\\hero'
FINAL = "Use @image1 for the approved character; retain {{SIGN}} and the assigned motion."
ATTEMPTS = []


def deny(*_args, **_kwargs):
    ATTEMPTS.append("external_or_provider")
    raise AssertionError("External/provider operations are forbidden")


class NativeTransport(unittest.TestCase):
    def setUp(self):
        self.scope = engine_scope()
        self.engine = self.scope.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb-current-native-media-")
        self.image = Path(self.temporary.name) / "local-fixture.png"
        Image.new("RGB", (4, 3), (233, 14, 75)).save(self.image)
        self.values = {"model_provider": "griptape_cloud", "model": VISION_MODEL_CHOICES[0],
            "agent": None, "prompt": "human view", "include_details": False,
            "additional_context": {"zero": 0, "off": False, "unset": "", "literal": LITERAL},
            "agent_memory": {"runs": [{"input": "prior authored input", "output": "prior output"}]},
            "output_schema": None}
        self.node = hmb.HMBAgentLibrary(name="Isolated current Standard Agent")
        self.node._hmb_rules_active = True
        self.node._hmb_policy_omitted = False
        self.node._hmb_native_prompt_read_active = True
        self.node._hmb_ruleset_names = ("private-project-scope", "private-shot-scope")
        _p, _s, self.node._hmb_policy_rules, self.node._hmb_binding_rules = self.node._load_hmb_rules()
        self.node._hmb_runtime_prompt = "VERIFIED MACHINE DATA\n" + LITERAL
        machine_hash = hashlib.sha256(self.node._hmb_runtime_prompt.encode()).hexdigest()
        self.snapshot = {"schema": "hmb-agent-reference-media", "version": 1,
            "machine_sha256": machine_hash,
            "images": [{"source": str(self.image), "media_token": "local-fixture-image",
                "reference_index": 1, "role": "character", "label": "Approved local fixture"}], "videos": []}
        self.source = SimpleNamespace(
            _hmb_agent_generation_context=lambda _expected: {"resolution": "480p", "generate_audio": False, "seed": 0},
            _hmb_agent_reference_media=lambda _expected: deepcopy(self.snapshot))
        setattr(self.node, hmb._VERIFIED_PROMPT_SOURCE_ATTRIBUTE, self.source)
        self.captured = []
        self.clients = []
        self.cancellation = False
        self.slow = False
        self.call_tool = False
        self.final_text = FINAL
        self.structured_field = "instruction"
        self.patchers = ExitStack()
        self.patchers.enter_context(mock.patch.object(hmb._BaseAgent, "get_parameter_value",
            lambda _self, name: self.values.get(name)))
        self.patchers.enter_context(mock.patch.object(hmb._BaseAgent, "get_parameter_list_value",
            lambda _self, name: ([{"name": "caller", "rules": ["Keep caller-owned rule."]}] if name == "rulesets"
                else [{"tool_type": "Calculator"}] if name == "tools" else [])))
        self.patchers.enter_context(mock.patch.object(self.node._model_access, "raise_if_selection_denied", lambda: None))
        self.patchers.enter_context(mock.patch.object(native, "require_model_invocation_sync", lambda *_a, **_k: None))
        self.patchers.enter_context(mock.patch.object(native_models, "resolve_api_key", lambda _config: "offline-never-sent"))
        self.patchers.enter_context(mock.patch.object(hmb.HMBAgentLibrary, "is_cancellation_requested",
            property(lambda _self: self.cancellation)))
        self.patchers.enter_context(mock.patch.object(native_models, "AsyncOpenAI", self.client))
        self.patchers.enter_context(mock.patch.object(socket, "create_connection", deny))

    def tearDown(self):
        self.patchers.close()
        self.temporary.cleanup()
        self.scope.__exit__(None, None, None)

    def client(self, **kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(self.respond))
        client = AsyncOpenAI(**kwargs)
        self.clients.append(client)
        return client

    async def respond(self, request):
        body = json.loads(request.content)
        self.captured.append(body)
        self.assertEqual(request.method, "POST")
        if self.slow:
            self.cancellation = True
            await asyncio.sleep(3)
        tools = body.get("tools") or []
        output_tool = next((tool["function"]["name"] for tool in tools
            if tool["function"]["name"].startswith("final_result")), None)
        tool_round = self.call_tool and not any(item["role"] == "tool" for item in body["messages"])
        delta = ({"tool_calls": [{"index": 0, "id": "offline-calculator", "type": "function",
            "function": {"name": "calculate", "arguments": '{"expression":"0+1"}'}}]} if tool_round else
            {"tool_calls": [{"index": 0, "id": "offline-output", "type": "function",
            "function": {"name": output_tool, "arguments": json.dumps({self.structured_field: self.final_text})}}]}
            if output_tool else {"content": self.final_text})
        payload = {"id": "offline-chat", "object": "chat.completion.chunk", "created": 1,
            "model": body["model"], "choices": [{"index": 0, "delta": delta,
                "finish_reason": "tool_calls" if output_tool or tool_round else "stop"}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            content=("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode())

    def run_native(self):
        iterator = self.node._run_native_agent_once()
        returned, steps = None, 0
        while True:
            try:
                callback = iterator.send(returned)
            except StopIteration:
                break
            self.assertTrue(callable(callback))
            returned = callback()
            steps += 1
        self.assertEqual(steps, 1)
        return returned

    def assert_bound(self, *, pixels=1):
        self.assertEqual(len(self.captured), 1)
        body = self.captured[0]
        self.assertEqual(body["model"], VISION_MODEL_CHOICES[0])
        serialized = json.dumps(body, ensure_ascii=False)
        user_messages = [m for m in body["messages"] if m["role"] == "user"]
        current = user_messages[-1]["content"]
        texts = current if isinstance(current, str) else "\n".join(p["text"] for p in current if p["type"] == "text")
        self.assertIn(self.node._hmb_runtime_prompt, texts)
        self.assertIn(LITERAL, texts)
        self.assertIn('"zero":0,"off":false,"unset":""', texts)
        self.assertEqual(texts.count(hmb._AGENT_ENGLISH_OUTPUT_CONTRACT), 1)
        self.assertIn('"resolution":"480p"', texts)
        self.assertIn('"generate_audio":false', texts)
        self.assertIn("Keep caller-owned rule.", serialized)
        for rule in self.node._hmb_policy_rules + self.node._hmb_binding_rules:
            self.assertEqual(serialized.count(json.dumps(rule, ensure_ascii=False)[1:-1]), 1)
        self.assertIn("prior authored input", serialized)
        images = [] if isinstance(current, str) else [p for p in current if p["type"] == "image_url"]
        self.assertEqual(len(images), pixels)
        if images:
            encoded = images[0]["image_url"]["url"]
            self.assertTrue(encoded.startswith("data:image/png;base64,"))
            with Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))) as frame:
                self.assertEqual(frame.size, (4, 3))
                self.assertEqual(frame.convert("RGB").getpixel((0, 0)), (233, 14, 75))
        self.assertNotIn(str(self.image), serialized)
        self.assertIn("calculate", serialized)
        self.assertEqual(self.values["additional_context"]["zero"], 0)
        self.assertIs(self.values["additional_context"]["off"], False)
        self.assertFalse(ATTEMPTS)

    def test_current_native_text_model_bound_bytes_rules_and_literals(self):
        result = self.run_native()
        self.assertEqual(result.output, FINAL)
        self.assertEqual(self.node.parameter_output_values["output"], FINAL)
        self.assert_bound()
        self.node._secure_hmb_outputs()
        self.assertFalse(any(rule in str(self.node.parameter_output_values)
            for rule in self.node._hmb_policy_rules + self.node._hmb_binding_rules))

    def test_current_structured_output_and_native_tools(self):
        self.values["output_schema"] = {"type": "object", "properties": {"instruction": {"type": "string"}},
            "required": ["instruction"], "additionalProperties": False}
        authored = deepcopy(self.values["output_schema"])
        result = self.run_native()
        self.assertEqual(result.output, {"instruction": FINAL})
        self.assertEqual(json.loads(self.node.parameter_output_values["output"]), result.output)
        # The installed Standard's StructuredDict assigns its default title;
        # all caller-authored schema fields still reach its native output tool.
        self.assertEqual(self.values["output_schema"], {**authored, "title": "output"})
        self.assert_bound()

    def test_current_native_calculator_tool_executes_and_returns_to_same_model(self):
        self.call_tool = True
        result = self.run_native()
        self.assertEqual(result.output, FINAL)
        self.assertEqual(len(self.captured), 2)
        tool_returns = [item for item in self.captured[-1]["messages"] if item["role"] == "tool"]
        self.assertEqual(len(tool_returns), 1)
        self.assertEqual(tool_returns[0]["content"], "1")
        self.assertEqual([body["model"] for body in self.captured], [VISION_MODEL_CHOICES[0]] * 2)

    def test_legacy_two_argument_literal_processor_remains_compatible(self):
        from griptape.artifacts import TextArtifact
        from griptape.structures import Agent
        from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver

        legacy = Agent(prompt_driver=GriptapeCloudPromptDriver(model=VISION_MODEL_CHOICES[0], api_key="offline"))
        calls = []
        def processor(structure, value):
            calls.append(value)
            structure._execution_args = (value,)
            self.assertEqual(structure.tasks[0].input.value, LITERAL)
            self.assertIsInstance(structure.tasks[0].input, TextArtifact)
            return structure
        self.assertIs(hmb._run_native_with_literal_hmb_input(processor, legacy, LITERAL), legacy)
        self.assertEqual(calls, [LITERAL])
        self.assertNotIn("_process_task_input", legacy.tasks[0].__dict__)

    def test_current_native_cancellation_uses_standard_runner(self):
        self.slow = True
        start = time.monotonic()
        self.assertIsNone(self.run_native())
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(len(self.captured), 1)
        self.assertNotIn(FINAL, str(self.node.parameter_output_values))

    def test_unknown_native_endpoint_remains_text_only(self):
        self.values["model"] = ModelConfig(provider=ModelProvider.OPENAI_COMPATIBLE,
            model=VISION_MODEL_CHOICES[0], base_url="https://offline-fixture.invalid/v1", api_key="offline-never-sent")
        result = self.run_native()
        self.assertEqual(result.output, FINAL)
        self.assert_bound(pixels=0)
        self.assertEqual(self.node._hmb_reference_observation["status"], "no_vision_driver")

    def test_untrusted_state_shape_cannot_activate_binary_transport(self):
        state = SimpleNamespace(model=ModelConfig(provider=ModelProvider.GRIPTAPE_CLOUD, model=VISION_MODEL_CHOICES[0]))
        self.assertFalse(media.driver_accepts_images(state))
        actual = AgentState(model=state.model)
        self.assertTrue(media.driver_accepts_images(actual))
        actual.model.base_url = "https://offline-fixture.invalid"
        self.assertFalse(media.driver_accepts_images(actual))


if __name__ == "__main__":
    unittest.main(verbosity=2)
