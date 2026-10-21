"""Offline execution-snapshot provenance through the real authenticated bridge.

The 22 mode/model/Task wire combinations are transport fixtures, not new Shot
operations. Bound Shot production still resolves to Reference to Video. All
opener responses, media URLs and projects here are synthetic; no paid calls.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path[:0] = [str(TESTS), str(TESTS.parent.parent)]
spec = importlib.util.spec_from_file_location("generation_mode_only_fixture",
    TESTS / "HMB_Seedance_Only_Project_Selection_Regression.py")
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t, base = fixture.t, fixture.base
transport = fixture.transport_fixture
MODE, TASK = "hmb_generation_mode", "hmb_generation_task"
META = {MODE, TASK}


def metadata_capability():
    return {"schema": "hmb-generation-mode-v1", "field": MODE,
        "choices": ["only", "shot"], "task_field": TASK,
        "tasks": list(t.TASK_STORAGE_CHOICES)}


def advertise(document, draft, occurrence):
    return {**document, "generation_mode_metadata": metadata_capability()}


def parameters(model, task):
    values = fixture.values_for(task)
    values.update(model_id=model, input_mode=t.TASK_INPUT_MODES[task],
                  duration=-1 if task == t.TASK_VIDEO_EDITING else 5)
    if task in (t.TASK_TEXT_ONLY, t.TASK_FIRST_LAST_FRAME):
        values.update(reference_images=[], video_references=[], video_reference_slots=[], reference_audio=[])
    if task == t.TASK_FIRST_LAST_FRAME:
        values["first_frame"] = "https://media.invalid/first.png"
    return values


def wire_payload(model, task, mode="only"):
    node = base.Node()
    node._prepare_media_reference = lambda kind, value: value
    values = parameters(model, task)
    values["_hmb_generation_mode"] = mode
    payload = node._build_broker_payload(values)
    payload["client_request_id"] = "hmb-mode-fixture-request"
    return payload


class GenerationModeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(socket, "create_connection",
            side_effect=AssertionError("External network is forbidden")))
        self.stack.enter_context(mock.patch.object(t.urllib.request.OpenerDirector, "open",
            side_effect=AssertionError("External transport is forbidden")))
        self.stack.enter_context(mock.patch.object(t, "_broker_load_token",
            side_effect=AssertionError("Real credentials are forbidden")))
        for name in ("bind_task_origin", "bind_task_project"):
            self.stack.enter_context(mock.patch.object(t._review, name))
        self.stack.enter_context(mock.patch.object(t, "_broker_log_transport_error"))

    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def bridge(self, transform=advertise):
        opener = transport.RouteOpener()
        opener.transform = transform
        return transport.bridge_for(opener), opener

    def test_only_all_current_model_tasks_reach_wire_with_real_execution_snapshot(self):
        cases = 0
        for model, tasks in t.MODEL_TASK_CHOICES.items():
            for task in tasks:
                with self.subTest(model=model, task=task):
                    values = parameters(model, task)
                    original = deepcopy(values)
                    node = fixture.Node(values)
                    graph = fixture.Graph(node)
                    node.select("katuri8")
                    node.transport.transform = advertise
                    with graph.context(), fixture.run_boundaries():
                        asyncio.run(node._process_generation_impl())
                    self.assertEqual(len(node.transport.posts), 1)
                    body = node.transport.posts[0]["body"]
                    self.assertEqual((body[MODE], body[TASK]), ("only", task))
                    self.assertEqual(body["input_mode"], t.TASK_INPUT_MODES[task])
                    self.assertEqual(body["prompt"], original["prompt"])
                    self.assertNotIn("task", body)
                    self.assertEqual(node.values, original)
                    self.assertEqual(len(node.saved), 1)
                    if model != t.SEEDANCE_2_5_MODEL_ID:
                        self.assertNotIn("omni_reference_task_type", body)
                    cases += 1
        self.assertEqual(cases, sum(map(len, t.MODEL_TASK_CHOICES.values())))

    def test_only_and_shot_wire_contract_matrix_does_not_add_model_tasks(self):
        cases = 0
        for mode in ("only", "shot"):
            for model, tasks in t.MODEL_TASK_CHOICES.items():
                for task in tasks:
                    with self.subTest(mode=mode, model=model, task=task):
                        bridge, opener = self.bridge()
                        payload = wire_payload(model, task, mode)
                        before = deepcopy(payload)
                        bridge.generate_seedance(payload, timeout=2)
                        self.assertEqual(payload, before)
                        body = opener.posts[0]["body"]
                        self.assertEqual((body[MODE], body[TASK]), (mode, task))
                        self.assertNotIn("task", body)
                        self.assertFalse(any(value is None or value == [] for value in body.values()))
                        expected = t.TASK_OMNI_REFERENCE_TYPES.get(task) if model == t.SEEDANCE_2_5_MODEL_ID else None
                        self.assertEqual(body.get("omni_reference_task_type"), expected)
                        cases += 1
        self.assertEqual(cases, 22)

    def test_snapshot_never_rereads_ui_or_guesses_only_from_project_schema(self):
        values = parameters(t.SEEDANCE_2_5_MODEL_ID, t.TASK_VIDEO_EDITING)
        node = fixture.Node(values)
        graph = fixture.Graph(node)
        # Connected ImageAsset provenance is valid even on the actual Only path.
        graph.direct(project="katuri8")
        with graph.context():
            snapshot = node._resolve_exact_shot_generation_inputs(values)
        self.assertEqual(snapshot["_hmb_generation_mode"], "only")
        self.assertEqual(snapshot["_hmb_imageasset_project_selection"]["schema"], t.PROJECT_SELECTION_SCHEMA)
        node.shot()
        node.values["task"] = t.TASK_TEXT_ONLY
        node._prepare_media_reference = lambda kind, value: value
        with mock.patch.object(node, "get_parameter_value", side_effect=AssertionError("Late mutable UI read")):
            payload = node._build_broker_payload(snapshot)
        self.assertEqual((payload[MODE], payload[TASK]), ("only", t.TASK_VIDEO_EDITING))
        unknown = deepcopy(snapshot)
        unknown.pop("_hmb_generation_mode")
        unknown["_hmb_draft_only"] = True
        with mock.patch.object(node, "get_parameter_value", side_effect=AssertionError("Inferred UI read")):
            legacy = node._build_broker_payload(unknown)
        self.assertFalse(META & legacy.keys())

    def test_missing_malformed_nullable_capability_preserves_exact_legacy_post(self):
        variants = [None, {}, [], "only", {**metadata_capability(), "schema": "future"},
            {**metadata_capability(), "field": "wrong"},
            {**metadata_capability(), "task_field": "wrong"},
            {**metadata_capability(), "choices": None},
            {**metadata_capability(), "tasks": [None]}]
        for capability in variants:
            with self.subTest(capability=capability):
                def transform(doc, draft, occurrence):
                    return {**doc, "generation_mode_metadata": deepcopy(capability)}
                bridge, opener = self.bridge(transform)
                payload = wire_payload(t.SEEDANCE_2_0_FAST_MODEL_ID, t.TASK_REFERENCE_TO_VIDEO)
                bridge.generate_seedance(payload, timeout=2)
                legacy_bridge, legacy_opener = self.bridge(transform)
                legacy_bridge.generate_seedance({key: value for key, value in payload.items() if key not in META}, timeout=2)
                self.assertEqual(opener.posts[0], legacy_opener.posts[0])
                self.assertFalse(META & opener.posts[0]["body"].keys())

    def test_optional_discovery_failure_keeps_legacy_render_and_does_not_retry_post(self):
        for failure in (401, 404, 429, 503, TimeoutError("offline timeout")):
            with self.subTest(failure=failure):
                bridge, opener = self.bridge(lambda *args: failure)
                bridge.generate_seedance(wire_payload(t.SEEDANCE_2_0_MODEL_ID, t.TASK_TEXT_ONLY), timeout=2)
                self.assertEqual(len(opener.posts), 1)
                self.assertFalse(META & opener.posts[0]["body"].keys())
                bridge._clear_access_token.assert_not_called()
                self.assertEqual(bridge._load_access_token(), transport.SYNTHETIC_TOKEN)

    def test_nullable_metadata_is_omitted_without_additional_discovery(self):
        bridge, opener = self.bridge()
        payload = wire_payload(t.SEEDANCE_2_0_FAST_MODEL_ID, t.TASK_TEXT_ONLY)
        payload.update({MODE: None, TASK: None, "omni_reference_task_type": None})
        bridge.generate_seedance(payload, timeout=2)
        self.assertFalse(META & opener.posts[0]["body"].keys())
        self.assertEqual(opener.capability_paths, [])
        self.assertNotIn("omni_reference_task_type", opener.posts[0]["body"])

    def test_capability_only_sends_common_literals_and_refreshes_after_upgrade(self):
        bridge, opener = self.bridge(lambda doc, *args: {
            key: value for key, value in doc.items() if key != "generation_mode_metadata"})
        payload = wire_payload(t.SEEDANCE_2_0_FAST_MODEL_ID, t.TASK_REFERENCE_TO_VIDEO)
        bridge.generate_seedance(payload, timeout=2)
        self.assertFalse(META & opener.posts[-1]["body"].keys())
        opener.transform = advertise
        bridge._generation_mode_metadata_checked_at -= 31
        bridge.generate_seedance(payload, timeout=2)
        self.assertEqual(opener.posts[-1]["body"][MODE], "only")
        self.assertEqual(opener.posts[-1]["body"][TASK], t.TASK_REFERENCE_TO_VIDEO)
        self.assertEqual(len(opener.capability_paths), 2)
        self.assertEqual({post["idempotency_key"] for post in opener.posts}, {payload["client_request_id"]})
        self.assertEqual(opener.posts[0]["body"]["client_request_id"], opener.posts[1]["body"]["client_request_id"])
        # Server initial-accept immutability is a server contract, not claimed
        # by these synthetic transport responses. The client never patches it.
        self.assertTrue(all(call["path"] in (transport.CAP_PATH, transport.GENERATE_PATH,
            "/api/v1/maintenance-intake/capabilities") for call in opener.calls))

    def test_partial_capability_never_sends_an_unadvertised_literal(self):
        def partial(doc, *args):
            return {**doc, "generation_mode_metadata": {**metadata_capability(),
                "choices": ["only"], "tasks": [t.TASK_TEXT_ONLY]}}
        bridge, opener = self.bridge(partial)
        bridge.generate_seedance(wire_payload(t.SEEDANCE_2_0_FAST_MODEL_ID, t.TASK_REFERENCE_TO_VIDEO, "shot"), timeout=2)
        self.assertFalse(META & opener.posts[0]["body"].keys())


if __name__ == "__main__":
    t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    transport.t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    unittest.main()
