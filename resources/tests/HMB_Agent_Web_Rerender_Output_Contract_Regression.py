"""Web-only final-instruction contract and real worker no-submit boundary.

Installed Standard Agent schema support is checked without a provider call.
All journals and SDK configuration belong to offline fixtures.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
standard = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
if standard.is_dir():
    os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(standard))
import HMBAgentLibrary as agent_module
import _hmb_web_rerender as web

base = agent_module.HMBAgentLibrary.__mro__[1]
prompt = '원본 {{SIGN}} {% include "secret" %} @video1\x00\n\nReview:\n움직임 부드럽게'
instruction = '  @video1 유지. 자막 "Review Assessment"와 {{SIGN}} 보존. 사운드 OFF, seed 0.\x00\n'
media = {"schema": "hmb-agent-reference-media", "version": 1, "images": [],
         "videos": [{"token": "@video1", "source": "C:/offline/literal.mp4"}]}
settings = {"seed": 0, "generate_audio": False, "resolution": "720p"}
project = {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}


def envelope(text=instruction, **changes):
    document = {"contract": agent_module._WEB_RERENDER_OUTPUT_CONTRACT,
                "source_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "instruction": text}
    document.update(changes)
    return json.dumps(document, ensure_ascii=False)


def rejected(value):
    try:
        agent_module._web_rerender_instruction(value, prompt)
    except agent_module._HMBWebRerenderOutputContractError:
        return
    raise AssertionError("Malformed or mismatched response admitted")


valid = envelope()
assert agent_module._web_rerender_instruction(valid, prompt) == instruction
assert agent_module._web_rerender_instruction(envelope("한" * 50000), prompt) == "한" * 50000
assert agent_module._web_rerender_instruction(json.dumps(json.loads(valid), ensure_ascii=True), prompt) == instruction
emoji = "\U0001f680" * 50000
assert agent_module._web_rerender_instruction(json.dumps(json.loads(envelope(emoji)), ensure_ascii=True), prompt) == emoji
bad = ["# Review Assessment: provide a recommendation", "검토 결과: 움직임을 부드럽게 하세요.",
       "```json\n" + valid + "\n```", valid + " trailing explanation", "[]", "null", "{}", None,
       envelope(contract="wrong"), envelope(source_sha256="0" * 64), envelope(""), envelope(" \n\t"),
       envelope(0), envelope(False), envelope({"instruction": "nested"}), envelope("한" * 50001),
       envelope(analysis="extra commentary"), valid[:-1] + ',"instruction":"second answer"}',
       valid.replace('"instruction":', '"instruction": NaN, "unused":')]
for value in bad:
    rejected(value)
schema = agent_module._web_rerender_output_schema(prompt)
assert schema["additionalProperties"] is False and len(schema["required"]) == 3
assert schema["properties"]["source_sha256"]["enum"] == [hashlib.sha256(prompt.encode()).hexdigest()]
assert "do not calculate a hash" in agent_module._web_rerender_output_rules(prompt)["rules"][0]
print(f"HMB_WEB_OUTPUT_ENVELOPE=PASS (4 literal successes including 50k escaped emoji, {len(bad)} malformed/prose/mismatched failures)")

wire_settings = {"model": "doubao-seedance-2-5-260628", "input_mode": "multimodal",
                 "quality": "720p", "resolution": "720p", "aspect_ratio": "16:9", "ratio": "16:9",
                 "duration_seconds": 4, "duration": 4, "generate_audio": False, "output_format": "mp4",
                 "watermark": False, "return_last_frame": False, "execution_expires_after": 172800,
                 "priority": 0, "omni_reference_task_type": "reference_to_video"}
assert agent_module._web_rerender_snapshots(media, wire_settings, prompt)[1] == wire_settings
sparse = {key: wire_settings[key] for key in ("model", "quality", "duration_seconds", "generate_audio")}
assert agent_module._web_rerender_snapshots(media, sparse, prompt)[1] == sparse
assert agent_module._web_rerender_snapshots(media, {"duration_seconds": 6.25, "seed": 0}, prompt)[1] == {"duration_seconds": 6.25, "seed": 0}
for invalid in ({"model": {}}, {"model": "x" * 257}, {"priority": True}, {"priority": 10**1000},
                {"generate_audio": "OFF"}, {"duration": float("nan")}, {"duration": float("inf")},
                {"duration": []}, {"output_format": None}):
    try:
        agent_module._web_rerender_snapshots(media, invalid, prompt)
        raise AssertionError("Unsafe settings scalar admitted")
    except ValueError:
        pass
print("HMB_WEB_OUTPUT_SETTINGS=PASS (all 15 frozen wire fields, sparse absence, false/0, 9 invalid scalar failures)")


def owner():
    node = object.__new__(agent_module.HMBAgentLibrary)
    node.name = "web_output_contract_offline"
    node.metadata = {}
    node._hmb_node_deleted = False
    node._hmb_lifecycle_generation = 1
    node._cancellation_requested = threading.Event()
    node._hmb_rules_active = False
    node.parameter_values = {"prompt": "AUTHORED PROMPT", "SHOT_PROMPT_IN": "AUTHORED INPUT",
                             "model": "native-model", "model_provider": "native-provider",
                             "output_schema": {"type": "object", "properties": {"analysis": {"type": "string"}}},
                             "rulesets": [{"name": "caller", "rules": ["caller rule"]}], "tools": []}
    node.parameter_output_values = {"output": "OLD RESULT"}
    node.get_parameter_value = lambda key: node.parameter_values.get(key)
    node.get_parameter_list_value = lambda key: node.parameter_values.get(key, [])
    return node


class Engine:
    pass


class Generator:
    _hmb_node_deleted = False
    def __init__(self):
        self.executions = 0
    @asynccontextmanager
    async def _hmb_web_rerender_claim(self, snapshot):
        yield SimpleNamespace()
    def _hmb_web_rerender_bind_parent_settings(self, claim, frozen_settings):
        assert frozen_settings["generate_audio"] is False and frozen_settings["priority"] == 0
        claim.parent_generation_context = deepcopy(settings)
    async def _hmb_web_rerender_prepare_media(self, claim):
        return deepcopy(media)
    async def _hmb_web_rerender_execute(self, *args, **kwargs):
        self.executions += 1
        raise AssertionError("Invalid Agent output crossed the Generator boundary")


class Protocol:
    owner_key = "17"
    def __init__(self):
        self.events = []
        self.bridge = SimpleNamespace(server_url="https://broker.example")
    def result(self, command, event, **fields):
        self.events.append(event)
        return {"operation_id": command["operation_id"], "state": "prepared"}


async def worker_rejects(value, *, provider_unsupported=False):
    node, generator, protocol, engine = owner(), Generator(), Protocol(), Engine()
    before = deepcopy((node.parameter_values, node.parameter_output_values))
    steps = []
    def process(self):
        assert self.get_parameter_value("prompt") == prompt
        assert self.get_parameter_value("output_schema") == schema
        assert self.get_parameter_list_value("rulesets")[-1] == agent_module._web_rerender_output_rules(prompt)
        def step():
            steps.append(1)
            if provider_unsupported:
                raise ValueError("private-provider unsupported structured output")
        yield step
        self.set_parameter_value("output", value)
    with tempfile.TemporaryDirectory(prefix="hmb-web-output-contract-") as folder:
        journal = web.OperationJournal(folder)
        worker = web.EngineWorker(engine, journal)
        operation = str(uuid4())
        command = {"operation_id": operation, "render_key": "hmb-web-rerender-" + operation,
                   "target_id": str(uuid4()), "snapshot_sha256": "a" * 64, "web_prompt": prompt,
                   "parent_task_id": "job-parent", "review_id": str(uuid4()), "state": "claimed", **project}
        frozen = {"model": "doubao-seedance-2-5-260628", "input_mode": "Multimodal References",
                  "resolution": "720p", "duration_seconds": 4, "generate_audio": False, "priority": 0}
        digest = web._digest(frozen)
        command.update(frozen_generation_settings_schema=web.PARENT_SETTINGS_SCHEMA,
                       frozen_generation_settings=frozen, frozen_generation_settings_sha256=digest,
                       frozen_generation_settings_binding_sha256=web._digest({"schema": web.PARENT_SETTINGS_SCHEMA,
                           "parent_task_id": "job-parent", **project, "frozen_generation_settings_sha256": digest}))
        snapshot = {"params": {}, "generation_settings": settings, "project": project}
        with patch.object(base, "process", process, create=True), \
             patch.object(agent_module._hmb, "_bootstrap_agent_policy_session", side_effect=AssertionError("policy reinjection")):
            await worker.execute(generator, node, snapshot, protocol, command)
            # A malformed result remains consumed; duplicate dispatch cannot
            # retry the LLM or reach a billable video request.
            await worker.execute(generator, node, snapshot, protocol, command)
        record = journal.read(journal.key(protocol.bridge.server_url, protocol.owner_key, operation))
        assert record["state"] == ("uncertain" if provider_unsupported else "failed")
        assert record["document"]["error_code"] == (
            "execution_uncertain" if provider_unsupported else "web_rerender_output_contract_invalid")
        assert not record["document"].get("agent_result")
    assert steps == [1] and generator.executions == 0, (steps, generator.executions, protocol.events, record["document"].get("error_code"))
    assert protocol.events == ["agent_started", "failed"] and "prepared" not in protocol.events
    assert before == (node.parameter_values, node.parameter_output_values)
    assert not node._hmb_web_rerender_busy()


async def worker_checks():
    for value in (bad[0], bad[1], bad[2], envelope(source_sha256="0" * 64), envelope(analysis="extra")):
        await worker_rejects(value)
    await worker_rejects(valid, provider_unsupported=True)


asyncio.run(worker_checks())
print("HMB_WEB_OUTPUT_WORKER=PASS (6 failures: no Generator call/prepared/create, no replay, owner unchanged)")

if agent_module._BuiltinAgent is None:
    print("HMB_WEB_OUTPUT_NATIVE=SKIP (installed Standard Agent unavailable)")
    raise SystemExit(0)

native = inspect.getmodule(base)
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from pydantic import TypeAdapter

# Current Standard publishes JSON Schema through PydanticAI StructuredDict.
# Its native TypeAdapter preserves dictionaries; it is not the removed
# JSONSchema-to-Pydantic field validator. Check the actual schema supplied to
# the provider and retain HMB's mandatory post-inference rejection boundary.
native_output_type = native.output_type_from_schema(deepcopy(schema))
native_adapter = TypeAdapter(native_output_type)
native_schema = native_adapter.json_schema()
assert {key: value for key, value in native_schema.items() if key != "title"} == schema
assert native_adapter.validate_python(json.loads(valid))["instruction"] == instruction
native_validator = Draft202012Validator(native_schema)
native_validator.validate(json.loads(valid))
for value in (envelope(source_sha256="0" * 64), envelope(""), envelope("한" * 50001)):
    preserved = native_adapter.validate_python(json.loads(value))
    assert preserved == json.loads(value)
    rejected(json.dumps(preserved, ensure_ascii=False))
    try:
        native_validator.validate(preserved)
        raise AssertionError("Installed SDK schema accepted invalid contract")
    except ValidationError:
        pass
print("HMB_WEB_OUTPUT_NATIVE=PASS (installed StructuredDict schema exact; enum/min/max provider constraints and HMB post-inference rejection)")
