"""Isolated web Agent policy/lifecycle contracts; never invokes a provider."""
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


def fake_native_process(self):
    facades.append(self)
    assert self.parameter_values["model"] == "native-selected-model"
    assert self.get_parameter_value("output_schema") == {"type": "object"}
    assert self.get_parameter_list_value("tools") == [{"name": "native-tool"}]
    rules = self.get_parameter_list_value("rulesets")
    assert len(rules) == 3 and len(rules[-1]["rules"]) == 4 and len(rules[-2]["rules"]) == 4
    prompt = self._handle_additional_context(self.get_parameter_value("prompt"), self.get_parameter_value("additional_context"))
    self.append_value_to_parameter("logs", "private log")
    yield lambda: self._process(SimpleNamespace(tasks=[]), prompt)
    self.set_parameter_value("output", "New generator instruction.")
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
    assert set(status) == {"ready", "version", "sha256", "reason"}
    with patch.object(module._hmb, "_read_agent_policy_envelope", side_effect=RuntimeError("private policy bytes")):
        unavailable = node._hmb_web_rerender_policy_status()
        assert unavailable == {"ready": False, "version": "", "sha256": "", "reason": "policy_unavailable"}
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
    with patch.object(base, "process", fake_native_process, create=True), patch.object(base, "_process", fake_model, create=True), patch.object(_hmb_agent_media, "augment_prompt", fake_augment):
        result = await node._hmb_run_web_rerender(web_prompt, media, settings, cap)
        assert result["text"] == "New generator instruction."
        assert result["output_sha256"] == hashlib.sha256(result["text"].encode()).hexdigest()
        assert result["policy_identity"]["contract_sha256"]
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
        # Policy file/provenance/signature work runs off the engine loop too.
        # Cancellation must drain that thread before clearing its facade and
        # releasing the shared reservation, and must never reach the model.
        policy_entered = threading.Event()
        policy_release = threading.Event()
        policy_facades = []
        loop_thread = threading.get_ident()
        context = contextvars.ContextVar("web_rerender_policy_test", default="missing")
        token = context.set("engine-context")
        original_loader = module._HMBWebRerenderExecution._load_hmb_rules
        def blocking_policy():
            assert threading.get_ident() != loop_thread
            assert context.get() == "engine-context"
            policy_entered.set()
            assert policy_release.wait(5)
        def observed_load(self):
            assert threading.get_ident() != loop_thread
            assert context.get() == "engine-context"
            policy_facades.append(self)
            return original_loader(self)
        previous = len(captures)
        try:
            with patch.object(module._hmb, "_bootstrap_agent_policy_session", blocking_policy), patch.object(module._HMBWebRerenderExecution, "_load_hmb_rules", observed_load):
                task = asyncio.create_task(node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "cancel-policy")))
                try:
                    assert await asyncio.to_thread(policy_entered.wait, 2)
                    await asyncio.sleep(0.01)  # The engine loop remains responsive.
                    assert node._hmb_web_rerender_busy()
                    task.cancel()
                    await asyncio.sleep(0.01)
                    task.cancel()  # Repeated cancellation cannot release early.
                    await asyncio.sleep(0.01)
                    assert not task.done() and node._hmb_web_rerender_busy()
                finally:
                    policy_release.set()
                try:
                    await task
                    raise AssertionError("cancelled policy load reached execution")
                except asyncio.CancelledError:
                    pass
        finally:
            context.reset(token)
        assert len(captures) == previous and not node._hmb_web_rerender_busy()
        assert len(policy_facades) == 1
        assert not policy_facades[0]._hmb_policy_identity and not policy_facades[0]._hmb_rules_active
        assert policy_facades[0].parameter_values == {} and policy_facades[0].parameter_output_values == {}
        # Provider payloads cannot escape the web-facing error.
        def failed_model(*args):
            raise RuntimeError("secret-api-key and private policy")
        with patch.object(base, "_process", failed_model):
            try:
                await node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "failed"))
                raise AssertionError("provider failure returned success")
            except RuntimeError as exc:
                assert "secret-api-key" not in str(exc) and "private policy" not in str(exc)
        with patch.object(module._hmb, "_bootstrap_agent_policy_session", side_effect=RuntimeError("policy bytes")):
            previous = len(captures)
            try:
                await node._hmb_run_web_rerender(web_prompt, media, settings, authority(node, "policy"))
                raise AssertionError("missing policy admitted")
            except RuntimeError as exc:
                assert str(exc) == module._HMB_POLICY_UNAVAILABLE_MESSAGE
            assert len(captures) == previous
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
    print("HMB_AGENT_WEB_RERENDER_CORE=PASS (authority, signed policy, snapshots, isolation, serialization, cancellation, cleanup)")


asyncio.run(core())

if module._BuiltinAgent is None:
    print("HMB_AGENT_WEB_RERENDER_NATIVE=SKIP (installed Standard Agent unavailable)")
    raise SystemExit(0)

# Use the installed native model/schema/tools lifecycle; replace only the
# billable processor. Model/credential access is mocked in this process only.
native = inspect.getmodule(base)
live = module.HMBAgentLibrary(name="offline_web_native")
live.parameter_values["additional_context"] = {"SIGN": "NO SUBSTITUTION"}
live._model_access.raise_if_denied = lambda *args, **kwargs: None
prior = copy.deepcopy((live.parameter_values, dict(live.parameter_output_values)))
observed = []


def native_model(self, agent, prompt):
    literal = agent.tasks[0]._process_task_input(prompt)
    value = str(getattr(literal, "value", literal))
    assert value.startswith(web_prompt) and "{{SIGN}}" in value and "{% include" in value
    assert len(agent.rulesets) >= 2
    observed.append((self, value))
    agent.tasks[0].output = native.TextArtifact(value="Native web instruction.")
    self._last_raw_output = "Native web instruction."
    return agent


with patch.object(base, "_process", native_model), patch.object(native, "resolve_cloud_api_key", lambda: "offline-non-billable"), patch.object(native, "require_model_invocation_sync", lambda *args, **kwargs: None), patch.object(native, "try_throw_error", lambda *args, **kwargs: None):
    import _hmb_agent_media
    with patch.object(_hmb_agent_media, "augment_prompt", fake_augment):
        native_result = asyncio.run(live._hmb_run_web_rerender(web_prompt, media, settings, authority(live, "native")))
assert native_result["text"] == "Native web instruction." and len(observed) == 1
assert prior == (live.parameter_values, dict(live.parameter_output_values))
print("HMB_AGENT_WEB_RERENDER_NATIVE=PASS (installed Standard Agent; zero provider calls)")
