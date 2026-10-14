"""Offline native object creation versus real Agent inference completion.

The Standard Agent's process/processor I/O boundaries are fixtures. HMB's real
async result publication, process, native iterator, and processor wrapper run.
No model, Broker, engine graph, policy file, or network operation is performed.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import copy
import unittest
from unittest.mock import Mock, patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("hmb_agent_created_state_target", ROOT / "HMBAgentLibrary.py")
assert spec and spec.loader
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)
Agent = target.HMBAgentLibrary
Base = target._BaseAgent


def forbidden(*_args, **_kwargs):
    raise AssertionError("Offline Agent state regression attempted external I/O")


def native_set(self, name, value, *_args, **_kwargs):
    self.parameter_values[name] = value
    if name in {"output", "logs"}:
        self.parameter_output_values[name] = value


def native_get(self, name):
    return self.parameter_values.get(name)


def native_get_list(self, name):
    return self.parameter_values.get(name, [])


def native_process(self):
    """The installed Standard Agent's nonblank-prompt/empty-prompt contract."""
    self.native_calls += 1
    self.native_rulesets = self.get_parameter_list_value("rulesets")
    prompt = self.get_parameter_value("prompt")
    self.parameter_output_values["agent"] = {"fixture_object_created": True}
    if prompt and not str(prompt).isspace():
        yield lambda: self._process(SimpleNamespace(), prompt)
        self.set_parameter_value("output", self.fixture_output)
    else:
        self.parameter_output_values["output"] = self.fixture_created_output


def native_processor(self, _agent, _prompt):
    self.model_calls += 1
    self.received_prompts.append(_prompt)
    if self.fixture_failure:
        raise self.fixture_failure
    return self.fixture_output


async def native_aprocess(self):
    iterator = self.process()
    response = None
    while True:
        try:
            pending = next(iterator) if response is None else iterator.send(response)
        except StopIteration:
            return
        response = pending() if callable(pending) else pending
        # Let five independently owned Agents interleave through actual HMB
        # gate/iterator/result publication boundaries without model I/O.
        await asyncio.sleep(0)


def make_agent(number, *, prompt="", canonical=False, project="katuri8", pending=False):
    node = object.__new__(Agent)
    node.name = f"Offline Agent {number}"
    node.parameter_values = {"prompt": prompt, "SHOT_PROMPT_IN": prompt}
    node.parameter_output_values = {}
    node._hmb_node_deleted = False
    node._hmb_lifecycle_generation = 1
    node._hmb_execution_result = {}
    node._hmb_native_calls_this_process = 0
    node._hmb_rules_active = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_policy_identity = {}
    node._hmb_publication_buffer = {"output": "", "logs": ""}
    node._hmb_capture_publications = False
    node._hmb_suppress_visible_publication = False
    node._hmb_scheduler_step_failed = False
    node._hmb_last_sanitizer_status = "clean"
    node._hmb_reference_observation = {}
    node._hmb_reference_observation_run_id = ""
    node._hmb_shot_context = {}
    node._hmb_native_failure_code = ""
    node._hmb_verified_prompt_source_node = None
    node._hmb_native_prompt_read_active = False
    node._hmb_runtime_prompt = ""
    node._hmb_prompt_preview_active = False
    node._hmb_lifecycle_is_live = lambda generation: generation == 1 and not node._hmb_node_deleted
    node._refresh_agent_shot_route = Mock(return_value={})
    node._clear_execution_shot_binding = Mock()
    node._assert_exact_prompt_shot_route = Mock(return_value={})
    node._adopt_verified_execution_shot_binding = Mock()
    node._set_agent_execution_phase = Mock()
    node.show_message_by_name = Mock()
    node.hide_message_by_name = Mock()
    node._set_visible_output = lambda value: native_set(node, "output", value)
    source = SimpleNamespace(_hmb_project_identity=lambda: target.resolve_project(project))
    node.fixture_source = source
    def topology():
        node._hmb_verified_prompt_source_node = source if canonical else None
        return canonical
    node._has_canonical_hmb_prompt_connection = topology
    node._hmb_web_rerender_policy_status = Mock(return_value={
        "ready": True, "reason": "project_policy_pending" if pending else "",
        "policy_verified": not pending, "policy_status": "absent" if pending else "available",
    })
    node._load_hmb_rules = Mock(return_value=("fixture-policy", "fixture-binding", [], []))
    node._secure_hmb_outputs = Mock(return_value=False)
    node.fixture_output = "Completed fixture model response"
    node.fixture_created_output = "Agent created."
    node.fixture_failure = None
    node.native_calls = 0
    node.model_calls = 0
    node.native_rulesets = []
    node.received_prompts = []
    return node


class AgentCreatedState(unittest.TestCase):
    def setUp(self):
        self.context = []
        for owner, name, value in (
            (Base, "process", native_process),
            (Base, "aprocess", native_aprocess),
            (Base, "_process", native_processor),
            (Base, "set_parameter_value", native_set),
            (Base, "get_parameter_value", native_get),
            (Base, "get_parameter_list_value", native_get_list),
            (target, "_paired_machine_prompt", lambda node, value: value),
            (target, "_run_native_with_literal_hmb_input", lambda processor, agent, prompt: processor(agent, prompt)),
            (target._hmb, "_bootstrap_agent_policy_session", Mock()),
            (socket, "create_connection", forbidden),
            (urllib.request, "urlopen", forbidden),
        ):
            item = patch.object(owner, name, value, create=True)
            item.start()
            self.context.append(item)

    def tearDown(self):
        for item in reversed(self.context):
            item.stop()

    @staticmethod
    def run_nodes(nodes):
        async def run():
            await asyncio.gather(*(node.aprocess() for node in nodes))
        asyncio.run(run())

    def test_five_missing_project_policies_continue_with_the_verified_source_without_policy(self):
        nodes = [make_agent(i, prompt="Fixture shot prompt", canonical=True, pending=True) for i in range(5)]
        for node in nodes:
            node.parameter_values["prompt"] = "Visible HMB_GP_Production placeholder"
            node.parameter_values["SHOT_PROMPT_IN"] = "Verified source {{SIGN}} {% literal %} " + node.name
            node.parameter_values["rulesets"] = [{"name": "authored rules", "rules": ["Keep authored user rules"]}]
        self.run_nodes(nodes)
        for node in nodes:
            result = node._hmb_execution_result_snapshot()
            self.assertEqual((result["status"], result["code"]), ("succeeded", "NO_PROJECT_POLICY"))
            self.assertEqual((node.native_calls, node.model_calls), (1, 1))
            self.assertTrue(result["inference_started"])
            self.assertFalse(result["policy_applied"])
            self.assertEqual(result["policy_status"], "absent")
            self.assertEqual(result["project_id"], "katuri8")
            self.assertIn(node.parameter_values["SHOT_PROMPT_IN"], node.received_prompts[0])
            self.assertNotIn("Visible HMB_GP_Production placeholder", node.received_prompts[0])
            self.assertEqual(node.native_rulesets, node.parameter_values["rulesets"])
            node._load_hmb_rules.assert_not_called()

    def test_five_ready_hmb_agents_latch_policy_and_inference_independently(self):
        nodes = [make_agent(i, prompt="Fixture shot prompt", canonical=True, project="superwings12") for i in range(5)]
        self.run_nodes(nodes)
        for node in nodes:
            result = node._hmb_execution_result_snapshot()
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual((node.native_calls, node.model_calls), (1, 1))
            self.assertTrue(result["inference_started"])
            self.assertTrue(result["policy_applied"])

    def test_five_empty_native_agents_create_objects_and_never_load_policy(self):
        nodes = [make_agent(i, prompt="" if i % 2 else "  ") for i in range(5)]
        with patch.object(target._hmb, "_bootstrap_agent_policy_session", forbidden):
            self.run_nodes(nodes)
        for node in nodes:
            result = node._hmb_execution_result_snapshot()
            self.assertEqual((result["status"], result["code"]), ("created", "AGENT_CREATED"))
            self.assertEqual((node.native_calls, node.model_calls), (1, 0))
            self.assertFalse(result["inference_started"])
            self.assertFalse(result["policy_applied"])
            self.assertEqual(result["output_sha256"], "")
            self.assertEqual(node.parameter_output_values["output"], "Agent created.")
            self.assertEqual(node.parameter_output_values["agent"], {"fixture_object_created": True})
            node.show_message_by_name.assert_called_with(target._AGENT_CREATED_WARNING)
            node._load_hmb_rules.assert_not_called()

    def test_literal_agent_created_real_model_response_remains_successful(self):
        node = make_agent(1, prompt="Return the requested literal phrase")
        node.fixture_output = "Agent created."
        self.run_nodes([node])
        result = node._hmb_execution_result_snapshot()
        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(result["inference_started"])
        self.assertFalse(result["policy_applied"])
        self.assertEqual(node.model_calls, 1)
        self.assertEqual(result["output_sha256"], hashlib.sha256(node.fixture_output.encode()).hexdigest())

    def test_created_then_generated_then_created_resets_run_facts(self):
        node = make_agent(1)
        self.run_nodes([node])
        first = node._hmb_execution_result_snapshot()
        node.parameter_values["prompt"] = "Fixture inference"
        self.run_nodes([node])
        second = node._hmb_execution_result_snapshot()
        node.parameter_values["prompt"] = ""
        self.run_nodes([node])
        third = node._hmb_execution_result_snapshot()
        self.assertEqual([item["status"] for item in (first, second, third)], ["created", "succeeded", "created"])
        self.assertEqual(len({item["run_id"] for item in (first, second, third)}), 3)
        self.assertEqual(node.model_calls, 1)
        self.assertFalse(third["inference_started"])

    def test_object_creation_does_not_depend_on_literal_native_output(self):
        node = make_agent(1)
        node.fixture_created_output = "Native object initialized with a different display label"
        self.run_nodes([node])
        self.assertEqual(node._hmb_execution_result_snapshot()["status"], "created")
        self.assertEqual(node.parameter_output_values["output"], node.fixture_created_output)

    def test_native_inference_failure_does_not_become_object_creation(self):
        node = make_agent(1, prompt="Fixture inference")
        node.fixture_failure = TimeoutError()
        self.run_nodes([node])
        result = node._hmb_execution_result_snapshot()
        self.assertEqual((result["status"], result["code"]), ("failed", "MODEL_TIMEOUT"))
        self.assertTrue(result["inference_started"])

    def test_canonical_hmb_completion_without_inference_never_reports_created_or_success(self):
        node = make_agent(1, canonical=True, project="superwings12")
        self.run_nodes([node])
        result = node._hmb_execution_result_snapshot()
        self.assertEqual((result["status"], result["code"]), ("failed", "EMPTY_OUTPUT"))
        self.assertFalse(result["inference_started"])
        self.assertFalse(result["policy_applied"])
        self.assertEqual(node.model_calls, 0)

    def test_saved_created_facts_restore_advisory_without_a_model_call(self):
        original = make_agent(1)
        self.run_nodes([original])
        stored = original._hmb_execution_result_snapshot()
        restored = make_agent(2)
        restored.parameter_values[target._AGENT_EXECUTION_RESULT_PARAMETER] = stored
        restored._refresh_hmb_execution_result_messages()
        restored.show_message_by_name.assert_called_once_with(target._AGENT_CREATED_WARNING)
        self.assertEqual((restored.native_calls, restored.model_calls), (0, 0))
        self.assertEqual(restored._hmb_execution_result_snapshot(), stored)

    def test_legacy_success_literal_output_and_unknown_facts_never_claim_creation(self):
        node = make_agent(1)
        node.parameter_output_values["output"] = "Agent created."
        for stored in ({"status": "succeeded"}, {"status": "created", "code": "AGENT_CREATED"},
                       {"status": "created", "code": "AGENT_CREATED", "inference_started": True, "policy_applied": False}):
            node.parameter_values[target._AGENT_EXECUTION_RESULT_PARAMETER] = stored
            node._refresh_hmb_execution_result_messages()
            node.show_message_by_name.assert_not_called()
            self.assertEqual(node._hmb_execution_result_snapshot(), stored)
        self.assertEqual(node.parameter_output_values["output"], "Agent created.")

    def test_present_invalid_policy_keeps_blocking_before_model_inference(self):
        node = make_agent(1, prompt="Fixture shot prompt", canonical=True, project="superwings12")
        with patch.object(target._hmb, "_bootstrap_agent_policy_session", side_effect=RuntimeError("invalid signed artifact")):
            self.run_nodes([node])
        result = node._hmb_execution_result_snapshot()
        self.assertEqual((result["status"], result["code"]), ("failed", "POLICY_UNAVAILABLE"))
        self.assertEqual((node.native_calls, node.model_calls), (0, 0))
        self.assertEqual(result["policy_status"], "not_applied")

    def test_missing_policy_preserves_verified_prompt_settings_and_reference_inputs(self):
        node = make_agent(1, prompt="Authored literal {{SIGN}} {% literal %}", canonical=True, pending=True)
        machine = node.parameter_values["SHOT_PROMPT_IN"]
        node.parameter_values["prompt"] = "Visible HMB_GP_Production placeholder"
        settings = {"resolution": "480p", "duration": 4, "generate_audio": False, "priority": 0}
        media = {"machine_sha256": hashlib.sha256(machine.encode()).hexdigest(),
                 "images": [{"token": "@image2", "source": "unchanged-image-source"}],
                 "videos": [{"token": "@video1", "source": "unchanged-video-source"}]}
        expected = copy.deepcopy(media)
        node.fixture_source._hmb_agent_generation_context = Mock(return_value=settings)
        node.fixture_source._hmb_agent_reference_media = Mock(return_value=media)
        received = []
        def augment(prompt, snapshot, _agent, **_kwargs):
            received.append(copy.deepcopy(snapshot))
            return prompt
        import _hmb_agent_media
        with patch.object(_hmb_agent_media, "augment_prompt", augment):
            self.run_nodes([node])
        self.assertEqual(node._hmb_execution_result_snapshot()["code"], "NO_PROJECT_POLICY")
        self.assertEqual(received, [expected])
        self.assertEqual(media, expected)
        node.fixture_source._hmb_agent_generation_context.assert_called_once_with(machine)
        node.fixture_source._hmb_agent_reference_media.assert_called_once_with(machine)
        self.assertIn(machine, node.received_prompts[0])
        self.assertIn('"generate_audio":false', node.received_prompts[0])
        self.assertIn('"priority":0', node.received_prompts[0])
        self.assertNotIn("Visible HMB_GP_Production placeholder", node.received_prompts[0])
        self.assertEqual(node.parameter_values["prompt"], "Visible HMB_GP_Production placeholder")


if __name__ == "__main__":
    unittest.main(verbosity=2)
