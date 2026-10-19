"""Isolated web revision bypass/lifecycle contracts; never invokes a provider."""
from __future__ import annotations

import asyncio
import copy
import contextvars
import hashlib
import inspect
import json
import os
from pathlib import Path
import pickle
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
standard = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
if standard.is_dir():
    os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(standard))
import HMBAgentLibrary as module
from _hmb_bundled_policy_session import install_bundled_policy_session

install_bundled_policy_session(module._hmb)
base = module.HMBAgentLibrary.__mro__[1]
web_prompt = '웹 수정 {{SIGN}} {% include "secret" %} 한국어\x00 원문'
media = {"schema": "hmb-agent-reference-media", "version": 1,
         "images": [{"token": "@image1", "source": "C:/offline/image.png"}],
         "videos": [{"token": "@video1", "source": "C:/offline/video.mp4"}]}
settings = {"model_id": "seedance-2.5", "duration_seconds": 4, "seed": 0,
            "generate_audio": False, "broker_api_key": "NEVER_MODEL_CONTEXT"}
events = []
facades = []
captures = []
generator = SimpleNamespace(_hmb_node_deleted=False)


def owner():
    node = object.__new__(module.HMBAgentLibrary)
    node.name = "offline_web_agent"
    node.metadata = {"library": "HMB_GP_Production", "node_type": "HMBAgentLibrary"}
    node._hmb_node_deleted = False
    node._hmb_lifecycle_generation = 1
    node._cancellation_requested = threading.Event()
    node._hmb_rules_active = False
    node.parameter_values = {"prompt": "ORIGINAL PROMPT MUST STAY", "SHOT_PROMPT_IN": "OLD AUTHORED PROMPT",
                             "model": "native-selected-model", "model_provider": "native-provider",
                             "output_schema": {"type": "object"}, "tools": [{"name": "native-tool"}],
                             "rulesets": [{"name": "user", "rules": ["user rule"]}],
                             "additional_context": {"SIGN": "MUST NOT SUBSTITUTE"}}
    node.parameter_output_values = {"output": "ORIGINAL ANSWER", "agent": {"original": True}}
    node._hmb_execution_result = {"status": "succeeded", "run_id": "original-run"}
    def read(key):
        assert key not in {"prompt", "SHOT_PROMPT_IN", "output"}, "read original Prompt or output"
        return node.parameter_values.get(key)
    node.get_parameter_value = read
    node.get_parameter_list_value = lambda key: node.parameter_values.get(key, [])
    node.set_parameter_value = lambda *args, **kwargs: events.append((args, kwargs))
    # Bound overrides on the real owner must not be inherited by the facade.
    return node


def authority(node, suffix="one"):
    return node._hmb_issue_web_rerender_authority(request_id="web-" + suffix, generator=generator, owner_key="owner-1")


def reply(text, prompt=web_prompt):
    return json.dumps({"contract": module._WEB_RERENDER_OUTPUT_CONTRACT,
                       "source_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                       "instruction": text}, ensure_ascii=False)


def fake_native_process(self):
    facades.append(self)
    assert self.parameter_values["model"] == "native-selected-model"
    assert self.get_parameter_value("output_schema") == module._web_rerender_output_schema(self._hmb_runtime_prompt)
    assert self.get_parameter_list_value("tools") == [{"name": "native-tool"}]
    rules = self.get_parameter_list_value("rulesets")
    assert rules == [{"name": "user", "rules": ["user rule"]}, module._web_rerender_output_rules(self._hmb_runtime_prompt)]
    assert not self._hmb_rules_active and not self._hmb_policy_identity
    assert not self._hmb_policy and not self._hmb_binding
    prompt = self._handle_additional_context(self.get_parameter_value("prompt"), self.get_parameter_value("additional_context"))
    self.append_value_to_parameter("logs", "private log")
    yield lambda: self._process(SimpleNamespace(tasks=[]), prompt)
    self.set_parameter_value("output", reply("New generator instruction.", self._hmb_runtime_prompt))
    self.parameter_output_values["agent"] = {"tools": "native-private-state"}


def fake_model(self, agent, prompt):
    captures.append(str(prompt))
    self.append_value_to_parameter("output", "not-public-stream")
    return agent


def fake_augment(prompt, snapshot, agent, **kwargs):
    assert snapshot["machine_sha256"] == hashlib.sha256(web_prompt.encode()).hexdigest()
    assert snapshot["images"][0]["source"] == media["images"][0]["source"]
    assert snapshot["videos"][0]["token"] == "@video1"
    kwargs["report_sink"]({"schema": "hmb-agent-reference-observation", "version": 1,
                           "machine_sha256": snapshot["machine_sha256"],
                           "status": "offline-observed", "source_count": 2})
    return prompt


async def core():
    import _hmb_agent_media
    node = owner()
    before = copy.deepcopy((node.parameter_values, node.parameter_output_values, node._hmb_execution_result, media, settings))
    status = node._hmb_web_rerender_policy_status()
    assert status["ready"] and status["version"] and len(status["sha256"]) == 64
    assert set(status) == {"ready", "version", "sha256", "reason", "policy_verified", "policy_status"}
    assert status["policy_verified"] is True and status["policy_status"] == "available"
    with patch.object(module._hmb, "_read_agent_policy_envelope", side_effect=RuntimeError("private policy bytes")):
        unavailable = node._hmb_web_rerender_policy_status()
        assert unavailable == {"ready": False, "version": "", "sha256": "", "reason": "policy_unavailable",
                               "policy_verified": False, "policy_status": "unavailable"}
    cap = authority(node)
    try:
        pickle.dumps(cap)
        raise AssertionError("capability serialized")
    except TypeError:
        pass
    for invalid in ({"request_id": "web-forged"}, "web-forged", object()):
        try:
            await node._hmb_run_web_rerender(web_prompt, media, settings, invalid)
            raise AssertionError("untrusted authority admitted")
        except TypeError:
            pass
    alien = owner()
    try:
        await alien._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "wrong-agent"))
        raise AssertionError("authority accepted for another agent")
    except RuntimeError:
        pass
    with patch.object(base, "process", fake_native_process, create=True), patch.object(base, "_process", fake_model, create=True), patch.object(_hmb_agent_media, "augment_prompt", fake_augment), \
            patch.object(module._hmb, "_bootstrap_agent_policy_session", side_effect=AssertionError("web bootstrapped policy")), \
            patch.object(module._hmb, "_read_agent_policy_envelope", side_effect=AssertionError("web read policy")), \
            patch.object(module._hmb, "_load_agent_rule_payload", side_effect=AssertionError("web loaded policy")), \
            patch.object(module, "_with_english_agent_output_contract", side_effect=AssertionError("web injected English policy")):
        result = await node._hmb_run_web_rerender(web_prompt, media, settings, cap)
        assert result["text"] == "New generator instruction."
        assert result["output_sha256"] == hashlib.sha256(result["text"].encode()).hexdigest()
        assert result["policy_identity"] == {"mode": "preserved_parent", "reinjected": False}
        assert result["observation"]["source_count"] == 2
        assert captures[0].startswith(web_prompt)
        assert "NEVER_MODEL_CONTEXT" not in captures[0] and '"seed":0' in captures[0] and '"generate_audio":false' in captures[0]
        assert "ORIGINAL" not in captures[0] and "OLD AUTHORED" not in captures[0]
        try:
            await node._hmb_run_web_rerender(web_prompt, media, settings, cap)
            raise AssertionError("capability reused")
        except RuntimeError:
            pass
        # Invalid snapshots stop before an LLM step.
        previous = len(captures)
        bad_media = copy.deepcopy(media)
        bad_media["images"][0]["token"] = "@image2"
        try:
            await node._hmb_run_web_rerender(web_prompt, bad_media, settings, authority(node, "bad-source"))
            raise AssertionError("misordered source admitted")
        except ValueError:
            pass
        assert len(captures) == previous
        # A manual host execution waits for the same reservation.
        entered = threading.Event()
        release = threading.Event()
        manual_started = asyncio.Event()
        def blocking_model(self, agent, prompt):
            entered.set()
            assert release.wait(5)
            return fake_model(self, agent, prompt)
        async def manual(self):
            manual_started.set()
        with patch.object(base, "_process", blocking_model), patch.object(module.HMBAgentLibrary, "_hmb_aprocess_locked", manual):
            task = asyncio.create_task(node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "concurrent")))
            assert await asyncio.to_thread(entered.wait, 5)
            manual_task = asyncio.create_task(node.aprocess())
            cancelled_waiter = asyncio.create_task(node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "cancel-waiter")))
            await asyncio.sleep(0.1)
            assert not manual_started.is_set() and node._hmb_web_rerender_busy()
            cancelled_waiter.cancel()
            try:
                await cancelled_waiter
                raise AssertionError("cancelled lock waiter completed")
            except asyncio.CancelledError:
                pass
            assert node._hmb_web_rerender_busy()
            release.set()
            await task
            await manual_task
            assert manual_started.is_set() and not node._hmb_web_rerender_busy()
        # Cancellation does not release the gate while a native call can still
        # stream. A follow-up request cannot overlap that late completion.
        entered.clear(); release.clear()
        with patch.object(base, "_process", blocking_model):
            task = asyncio.create_task(node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "cancel")))
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            await asyncio.sleep(0.05)
            assert not task.done() and node._hmb_web_rerender_busy()
            release.set()
            try:
                await task
                raise AssertionError("cancelled call returned success")
            except asyncio.CancelledError:
                pass
            assert not node._hmb_web_rerender_busy()
        # Native invocation preserves engine context and runs off the event
        # loop even though no policy bootstrap/load precedes it anymore.
        loop_thread = threading.get_ident()
        context = contextvars.ContextVar("web_rerender_revision_test", default="missing")
        token = context.set("engine-context")
        def contextual_model(self, agent, prompt):
            assert threading.get_ident() != loop_thread
            assert context.get() == "engine-context"
            return fake_model(self, agent, prompt)
        try:
            with patch.object(base, "_process", contextual_model):
                revised = await node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "context"))
                assert revised["policy_identity"]["mode"] == "preserved_parent"
        finally:
            context.reset(token)
        # Stale runtime HMB rules from the owner (or a wrapped incoming Agent)
        # never become caller rules in the isolated revision facade.
        stale = owner()
        stale._hmb_rules_active = True
        stale._hmb_ruleset_names = ("transient-project", "transient-shot")
        stale._hmb_policy = "STALE SEALED POLICY"
        stale._hmb_binding = "STALE SEALED BINDING"
        transient = [{"name": name, "rules": ["STALE SEALED POLICY"]} for name in stale._hmb_ruleset_names]
        stale.parameter_values["rulesets"] += copy.deepcopy(transient)
        stale.parameter_values["agent"] = {"agent": {}, "rulesets": copy.deepcopy(stale.parameter_values["rulesets"])}
        stale_before = copy.deepcopy(stale.parameter_values)
        def stale_model(self, agent, prompt):
            assert self.get_parameter_value("agent")["rulesets"] == [{"name": "user", "rules": ["user rule"]}]
            assert "STALE SEALED" not in str(prompt)
            return fake_model(self, agent, prompt)
        with patch.object(base, "_process", stale_model):
            await stale._hmb_run_web_rerender(web_prompt, media, settings, authority(stale, "stale"))
        assert stale.parameter_values == stale_before and stale._hmb_rules_active
        # Provider payloads cannot escape the web-facing error.
        def failed_model(*args):
            raise RuntimeError("secret-api-key and private policy")
        with patch.object(base, "_process", failed_model):
            try:
                await node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "failed"))
                raise AssertionError("provider failure returned success")
            except RuntimeError as exc:
                assert "secret-api-key" not in str(exc) and "private policy" not in str(exc)
        # The web contract combines up to 50k recorded prompt + 4k review;
        # provider-ready Agent output must still fit the 50k Generator limit.
        with patch.object(_hmb_agent_media, "augment_prompt", lambda prompt, *_args, **_kwargs: prompt):
            for length in (50000, 54000):
                await node._hmb_run_web_rerender("x" * length, media, settings, authority(node, f"input-{length}"))
                assert captures[-1].startswith("x" * length)
        previous = len(captures)
        try:
            await node._hmb_run_web_rerender("x" * 54001, media, settings, authority(node, "input-too-long"))
            raise AssertionError("oversized input admitted")
        except ValueError:
            pass
        assert len(captures) == previous
        def oversized_output(self):
            yield from fake_native_process(self)
            self.set_parameter_value("output", "x" * 50001)
        with patch.object(base, "process", oversized_output):
            try:
                await node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "output-too-long"))
                raise AssertionError("oversized generator output admitted")
            except RuntimeError:
                pass
    assert before == (node.parameter_values, node.parameter_output_values, node._hmb_execution_result, media, settings)
    assert not events
    for facade in facades:
        assert facade.parameter_values == {} and facade.parameter_output_values == {}
        assert not facade._hmb_rules_active and facade._hmb_runtime_prompt == ""
    print("HMB_AGENT_WEB_RERENDER_CORE=PASS (authority, parent policy preserved without reinjection, snapshots, isolation, serialization, cancellation, cleanup)")


asyncio.run(core())

if module._BuiltinAgent is None:
    print("HMB_AGENT_WEB_RERENDER_NATIVE=SKIP (installed Standard Agent unavailable)")
    raise SystemExit(0)

# Use the installed native model/schema/tools lifecycle; replace only the
# billable processor. Model/credential access is mocked in this process only.
native = inspect.getmodule(base)
from griptape_nodes_library.llm import runner as native_runner
from pydantic import TypeAdapter
from pydantic_ai.models.test import TestModel

live = module.HMBAgentLibrary(name="offline_web_native")
live.parameter_values["additional_context"] = {"SIGN": "NO SUBSTITUTION"}
live._model_access.raise_if_selection_denied = lambda *args, **kwargs: None
live._hmb_shot_catalog_snapshot = {"channel_uuid": "offline-native-channel", "shots": [
    {"shot_uuid": "offline-native-shot", "number": 1, "name": "Native web revision", "revision": 0}]}
generator._hmb_shot_channel_subscription = lambda: {
    "channel_uuid": "offline-native-channel", "shot_uuid": "offline-native-shot",
    "shot_number": 1, "shot_name": "Native web revision"}
live._hmb_shot_slots["offline-native-channel\x1foffline-native-shot"] = live._hmb_native_slot_snapshot()
prior = copy.deepcopy((dict(live.parameter_values), dict(live.parameter_output_values)))
observed = []
original_native_process = base._process


def native_model(self, state, prompt, output_type):
    assert isinstance(state, native.AgentState)
    value = str(getattr(prompt, "value", prompt))
    assert value.startswith(web_prompt) and "{{SIGN}}" in value and "{% include" in value
    assert [rule["name"] for rule in state.rulesets] == [module._WEB_RERENDER_OUTPUT_RULESET] and not self._hmb_rules_active
    schema = TypeAdapter(output_type).json_schema()
    assert set(schema["properties"]) == {"contract", "source_sha256", "instruction"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["source_sha256"]["enum"] == [hashlib.sha256(web_prompt.encode()).hexdigest()]
    assert '"seed":0' in value and '"generate_audio":false' in value and "NEVER_MODEL_CONTEXT" not in value
    observed.append((self, value))
    # Exercise the real installed Standard build/run/output handling; replace
    # only provider inference with PydanticAI's in-memory structured TestModel.
    result = original_native_process(self, state, prompt, output_type)
    assert isinstance(result, native.AgentRunResult)
    assert result.output == json.loads(reply("Native web instruction."))
    assert result.new_messages()
    return result


with patch.object(base, "_process", native_model), patch.object(native, "resolve_cloud_api_key", lambda: "offline-non-billable"), patch.object(native, "require_model_invocation_sync", lambda *args, **kwargs: None), \
        patch.object(native_runner, "build_model", lambda _config: TestModel(custom_output_args=json.loads(reply("Native web instruction.")))):
    import _hmb_agent_media
    with patch.object(_hmb_agent_media, "augment_prompt", fake_augment), \
            patch.object(module._hmb, "_bootstrap_agent_policy_session", side_effect=AssertionError("native web bootstrapped policy")), \
            patch.object(module._hmb, "_read_agent_policy_envelope", side_effect=AssertionError("native web read policy")), \
            patch.object(module._hmb, "_load_agent_rule_payload", side_effect=AssertionError("native web loaded policy")):
        native_result = asyncio.run(live._hmb_run_web_rerender(web_prompt, media, settings, authority(live, "native")))
assert native_result["text"] == "Native web instruction." and len(observed) == 1
assert prior == (live.parameter_values, dict(live.parameter_output_values))
print("HMB_AGENT_WEB_RERENDER_NATIVE=PASS (installed Standard Agent; zero provider calls)")
