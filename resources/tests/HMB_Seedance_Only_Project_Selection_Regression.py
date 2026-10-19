"""Offline explicit Only-project selection; actual graph/project host methods.

Reuses the registered synthetic graph and a route-sensitive synthetic opener.
The real Broker JSON/authentication transport runs. No live graph, server,
credentials, media upload, model call or billable request is used.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
from urllib.parse import urlsplit


TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "only_project_graph_fixture", TESTS / "HMB_Seedance_Project_Source_Routing_Regression.py")
assert spec and spec.loader
project = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = project
spec.loader.exec_module(project)
base = project.base
t = base.t
Graph = project.Graph
transport_spec = importlib.util.spec_from_file_location(
    "only_project_authenticated_transport_fixture", TESTS / "HMB_Seedance_Capability_Routing_Regression.py")
assert transport_spec and transport_spec.loader
transport_fixture = importlib.util.module_from_spec(transport_spec)
sys.modules[transport_spec.name] = transport_fixture
transport_spec.loader.exec_module(transport_fixture)

ONLY_PROJECT_PARAMETER = "only_project"
ONLY_PROJECT_UNSELECTED = "Select Project"
ONLY_PROJECT_SELECTION_SCHEMA = "hmb-only-project-selection-v1"
CANONICAL_PROJECTS = {
    "dinoster5": "다이노스터",
    "katuri8": "까투리8",
    "superwings12": "슈퍼윙즈12",
}
SHOT_CHANNEL = "10000000-0000-4000-8000-000000000001"
SHOT_UUID = "10000000-0000-4000-8000-000000000002"
REVIEW_CAPABILITIES_PATH = "/api/v1/reviews/capabilities"


def project_capability():
    # Stable portal envelope plus the additive Only support advertisement.
    # The old single-value ImageAsset schema remains unchanged.
    return {"schema": "hmb-review-portal", "version": 1, "review_portal": True,
        "page_url": "/reviews", "page_size": 20, "retention_days": 30,
        "project_routing": {"schema": "hmb-project-routing-v1",
            "generation_project_selection_schema": t.PROJECT_SELECTION_SCHEMA,
            "generation_project_selection_schemas": [t.PROJECT_SELECTION_SCHEMA, ONLY_PROJECT_SELECTION_SCHEMA],
            "project_ids": list(CANONICAL_PROJECTS),
            "projects": [{"project_id": identifier, "project_name": name}
                         for identifier, name in CANONICAL_PROJECTS.items()]}}


class OnlyProjectOpener(transport_fixture.RouteOpener):
    def __init__(self):
        super().__init__()
        self.project_transform = lambda document, occurrence: document
        self.project_capability_calls = 0
        self.published_payloads = []

    def open(self, request, timeout):
        parsed = urlsplit(request.full_url)
        if (request.get_method() == "GET" and parsed.path.startswith("/api/v1/reviews/tasks/")
                and parsed.path.endswith("/draft-final")):
            assert not parsed.query
            assert request.data is None
            assert request.get_header("Authorization") == "Bearer " + transport_fixture.SYNTHETIC_TOKEN
            source_id = parsed.path.split("/")[-2]
            self.calls.append({"method": "GET", "path": parsed.path,
                               "body": None, "idempotency_key": ""})
            now = int(time.time())
            state = {"schema": "hmb-review-draft-final-v1", "state_schema": "hmb-draft-final-state-v1",
                "source_task_id": source_id, "state": "available", "is_draft": True, "eligible": True,
                "consumed": False, "checked_at": now, "expires_at": now + 604800,
                "owner_user_id": 1, "idempotency_key": t._seedance_draft_final_request_id(source_id),
                "child_task_id": None, "child_status": None, **base.PROJECT}
            response = io.BytesIO(json.dumps(state).encode())
            response.status = 200
            response.geturl = lambda: request.full_url
            return response
        if request.get_method() == "GET" and parsed.path == REVIEW_CAPABILITIES_PATH:
            assert not parsed.query
            assert request.data is None
            assert request.get_header("Authorization") == "Bearer " + transport_fixture.SYNTHETIC_TOKEN
            self.calls.append({"method": "GET", "path": REVIEW_CAPABILITIES_PATH,
                               "body": None, "idempotency_key": ""})
            self.project_capability_calls += 1
            document = self.project_transform(project_capability(), self.project_capability_calls)
            if isinstance(document, BaseException):
                raise document
            if isinstance(document, int):
                raise urllib.error.HTTPError(request.full_url, document,
                    "Synthetic project capability rejection", {}, io.BytesIO(b'{"error":"offline rejection"}'))
            self.responses.append((REVIEW_CAPABILITIES_PATH, deepcopy(document)))
            response = io.BytesIO(json.dumps(document).encode())
            response.status = 200
            response.geturl = lambda: request.full_url
            return response
        response = super().open(request, timeout)
        if request.get_method() == "POST" and parsed.path == transport_fixture.GENERATE_PATH:
            self.published_payloads.append(deepcopy(self.calls[-1]["body"]))
        return response


def authenticated_bridge(opener):
    bridge = t._HMBAIBrokerBridge(opener=opener, server_url=base.ORIGIN)
    bridge._load_access_token = mock.Mock(return_value=transport_fixture.SYNTHETIC_TOKEN)
    bridge._clear_access_token = mock.Mock()
    bridge.posts = opener.published_payloads
    return bridge


class Node(project.Node):
    # Retain the real Only/Shot distinction instead of the older Draft
    # fixture's convenient unconditional Only flag.
    _draft_only_mode = t.HMBSeedanceGeneration._draft_only_mode

    def __init__(self, values=None):
        super().__init__(values)
        self.transport = OnlyProjectOpener()
        self.bridge = authenticated_bridge(self.transport)
        self.only()

    def only(self):
        self.parameter_values.update({t.SHOT_SELECTOR_PARAMETER: t.SHOT_ONLY_LABEL,
            t.SHOT_CHANNEL_UUID_PARAMETER: "", t.SHOT_UUID_PARAMETER: "",
            t.SHOT_NUMBER_PARAMETER: 0, t.SHOT_NAME_PARAMETER: t.SHOT_ONLY_LABEL})

    def shot(self):
        self.parameter_values.update({t.SHOT_SELECTOR_PARAMETER: "Shot 1",
            t.SHOT_CHANNEL_UUID_PARAMETER: SHOT_CHANNEL, t.SHOT_UUID_PARAMETER: SHOT_UUID,
            t.SHOT_NUMBER_PARAMETER: 1, t.SHOT_NAME_PARAMETER: "Shot 1"})

    def select(self, value):
        self.parameter_values[ONLY_PROJECT_PARAMETER] = value

    def _create_broker_bridge(self, *, server_url=None):
        if server_url is not None:
            assert server_url == base.ORIGIN
        return self.bridge


def values_for(task):
    values = base.params()
    values.update(task=task, input_mode=t.INPUT_MODE_MULTIMODAL_REFERENCES,
        prompt="카메라 이동만 수정 {{SIGN}} {% raw %} 🎬", resolution="720p",
        ratio="adaptive", duration=-1 if task == t.TASK_VIDEO_EDITING else 4,
        output_format="mp4", reference_images=["https://media.invalid/manual-image.png"],
        video_references=["https://media.invalid/manual-source.mp4"], video_reference_slots=[],
        reference_audio=[], generate_audio=False, watermark=False, priority=0)
    return values


def run_boundaries():
    stack = project.ExitStack()
    stack.enter_context(mock.patch.object(t, "_resolve_mp4_decode_verifier",
        return_value=SimpleNamespace(executable="offline-fixture", backend="test")))
    stack.enter_context(mock.patch.object(t._review, "capture_inputs", return_value={}))
    return stack


class OnlyProjectSelectionTests(unittest.TestCase):
    def setUp(self):
        # Recovery checkpoints remain real, but optional review bookkeeping
        # must never read or alter the user's local task-origin/project records.
        stack = project.ExitStack()
        stack.enter_context(mock.patch.object(t._review, "bind_task_origin"))
        stack.enter_context(mock.patch.object(t._review, "bind_task_project"))
        stack.enter_context(mock.patch.object(t, "_broker_log_transport_error"))
        stack.enter_context(mock.patch.object(t, "_broker_load_token",
            side_effect=AssertionError("Offline regression attempted to load a real credential")))
        stack.enter_context(mock.patch.object(t.urllib.request.OpenerDirector, "open",
            side_effect=AssertionError("Offline regression attempted an external request")))
        self.addCleanup(stack.close)

    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def test_parameter_contract_has_no_implicit_project(self):
        self.assertEqual(t.ONLY_PROJECT_PARAMETER, ONLY_PROJECT_PARAMETER)
        self.assertEqual(t.ONLY_PROJECT_UNSELECTED, ONLY_PROJECT_UNSELECTED)
        self.assertEqual(t.ONLY_PROJECT_SELECTION_SCHEMA, ONLY_PROJECT_SELECTION_SCHEMA)
        node = t.HMBSeedanceGeneration(name="Only project default fixture")
        self.assertEqual(node.get_parameter_value(ONLY_PROJECT_PARAMETER), ONLY_PROJECT_UNSELECTED)

    def test_three_explicit_ids_and_display_names_capture_registered_only_context(self):
        for project_id, name in CANONICAL_PROJECTS.items():
            for authored in (project_id, name):
                with self.subTest(project=project_id, authored=authored):
                    node = Node(); graph = Graph(node); node.select(authored)
                    before = deepcopy(node.parameter_values)
                    with graph.context():
                        selected = node._capture_imageasset_project_selection()
                        self.assertEqual(node._hmb_generation_project(),
                            {"project_id": project_id, "project_name": name})
                    self.assertEqual(selected["schema"], ONLY_PROJECT_SELECTION_SCHEMA)
                    self.assertEqual(selected["selection_source"], "only_explicit")
                    self.assertEqual(selected["project"], {"project_id": project_id, "project_name": name})
                    self.assertEqual(selected["flow"], "fixture-flow")
                    self.assertEqual(selected["owner"], id(node))
                    self.assertEqual(selected["sources"], [])
                    self.assertEqual(selected["edges"], [])
                    self.assertEqual(node.parameter_values, before)

    def test_three_projects_editing_extension_keep_manual_inputs_and_submit_once(self):
        for project_id, name in CANONICAL_PROJECTS.items():
            for task in (t.TASK_VIDEO_EDITING, t.TASK_VIDEO_EXTENSION):
                with self.subTest(project=project_id, task=task):
                    authored = values_for(task)
                    before = deepcopy(authored)
                    node = Node(authored); graph = Graph(node); node.select(project_id)
                    with graph.context(), run_boundaries():
                        resolved = node._resolve_exact_shot_generation_inputs(authored)
                        asyncio.run(node._process_generation_impl())
                    self.assertEqual(len(node.bridge.posts), 1)
                    wire = node.bridge.posts[0]
                    self.assertEqual((wire["project_id"], wire["project_name"]), (project_id, name))
                    self.assertEqual(wire["project_selection_schema"], ONLY_PROJECT_SELECTION_SCHEMA)
                    self.assertEqual(wire["prompt"], before["prompt"])
                    self.assertEqual(wire["duration_seconds"], before["duration"])
                    self.assertEqual(wire["aspect_ratio"], before["ratio"])
                    self.assertIs(wire["generate_audio"], False)
                    for field in ("task", "reference_images", "video_references", "video_reference_slots", "reference_audio"):
                        self.assertEqual(resolved[field], before[field])
                    self.assertEqual(authored, before)
                    self.assertEqual(node.upload_calls, 1)
                    self.assertEqual(len(node.saved), 1)
                    self.assertEqual(node.transport.project_capability_calls, 2)
                    self.assertGreaterEqual(node.bridge._load_access_token.call_count, 3)

    def test_invalid_manual_editing_extension_is_rejected_before_broker_or_upload(self):
        for task in (t.TASK_VIDEO_EDITING, t.TASK_VIDEO_EXTENSION):
            for problem in ("missing-video", "wrong-ratio", "model-2.0", "model-2.0-fast"):
                with self.subTest(task=task, problem=problem):
                    values = values_for(task)
                    if problem == "missing-video":
                        values.update(video_references=[], video_reference_slots=[])
                        expected = "requires at least one reference video"
                    elif problem == "wrong-ratio":
                        values["ratio"] = "16:9"
                        expected = "requires adaptive ratio"
                    else:
                        values["model_id"] = (t.SEEDANCE_2_0_MODEL_ID if problem == "model-2.0"
                                              else t.SEEDANCE_2_0_FAST_MODEL_ID)
                        expected = "does not support task"
                    before = deepcopy(values)
                    node = Node(values); graph = Graph(node); node.select("katuri8")
                    node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError("Invalid inputs accessed Broker"))
                    with graph.context(), run_boundaries(), self.assertRaisesRegex(ValueError, expected):
                        asyncio.run(node._process_generation_impl())
                    node._ensure_broker_connected.assert_not_awaited()
                    self.assertEqual(node.transport.calls, [])
                    self.assertEqual(node.upload_calls, 0)
                    self.assertEqual(node.bridge.posts, [])
                    self.assertEqual(node.saved, [])
                    self.assertEqual(values, before)

    def test_explicit_only_project_draft480_text_and_reference_submit_once(self):
        for task in (t.TASK_TEXT_ONLY, t.TASK_REFERENCE_TO_VIDEO):
            with self.subTest(task=task):
                values = base.params(t.DRAFT_ACTION_PREVIEW)
                values.update(task=task, input_mode=t.TASK_INPUT_MODES[task], resolution="480p",
                    duration=4, ratio="adaptive", output_format="mov", prompt="Draft 원문 {{SIGN}} 🎬",
                    reference_images=["https://media.invalid/draft-image.png"],
                    video_references=["https://media.invalid/draft-source.mp4"], video_reference_slots=[])
                node = Node(values); graph = Graph(node); node.select("katuri8")
                with graph.context(), run_boundaries():
                    asyncio.run(node._process_generation_impl())
                self.assertEqual(len(node.bridge.posts), 1)
                wire = node.bridge.posts[0]
                self.assertEqual((wire["project_id"], wire["project_name"]), ("katuri8", CANONICAL_PROJECTS["katuri8"]))
                self.assertEqual(wire["project_selection_schema"], ONLY_PROJECT_SELECTION_SCHEMA)
                self.assertIs(wire["draft"], True)
                self.assertEqual((wire["quality"], wire["resolution"], wire["output_format"]),
                                 ("480p", "480p", "mov"))
                self.assertEqual(wire["prompt"], values["prompt"])
                self.assertNotIn("draft_job_id", wire)
                self.assertEqual(node.transport.project_capability_calls, 2)
                self.assertEqual(len(node.saved), 1)
                self.assertEqual(node.saved[0][2]["output_format"], "mov")
                self.assertIn("draft480p", node.saved[0][1])

    def test_blank_unknown_and_spoofed_selector_stop_before_broker_or_upload(self):
        invalid = (None, "", ONLY_PROJECT_UNSELECTED, "unknown", "unassigned", "미분류",
            {"project_id": "unassigned", "project_name": "미분류"}, True, False, {},
            {"project_id": "katuri8", "project_name": "슈퍼윙즈12"},
            "C:/projects/Katuri8", "//server/projects/SuperWings12", "../katuri8")
        for authored in invalid:
            with self.subTest(authored=authored):
                node = Node(values_for(t.TASK_VIDEO_EDITING)); graph = Graph(node); node.select(authored)
                before = deepcopy(node.parameter_values)
                node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError("Broker accessed"))
                with graph.context(), self.assertRaises(ValueError):
                    asyncio.run(node._process_generation_impl())
                node._ensure_broker_connected.assert_not_awaited()
                self.assertEqual(node.upload_calls, 0)
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(node.saved, [])
                self.assertEqual(node.parameter_values, before)

    def test_five_unconnected_shots_cannot_classify_six_manual_only_generators(self):
        # Same-flow publication alone does not grant a disconnected Only node
        # another node's project, even after the five production slots exist.
        for project_id in CANONICAL_PROJECTS:
            with self.subTest(project=project_id):
                nodes = [Node(values_for(t.TASK_VIDEO_EDITING)) for _ in range(6)]
                for number, node in enumerate(nodes, 1):
                    node.name = "Disconnected Only " + str(number)
                graph = Graph(nodes[0])
                for node in nodes[1:]:
                    graph.add(node)
                image = graph.add(project.HMBImageAssetLibrary("Unconnected ImageAsset", project_id))
                image.shots = [dict(number=n, name="Published Shot " + str(n)) for n in range(1, 6)]
                for node in nodes:
                    before = deepcopy(node.parameter_values)
                    node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError("Broker accessed"))
                    with graph.context(), self.assertRaises(t._ProjectSelectionRequired):
                        asyncio.run(node._process_generation_impl())
                    node._ensure_broker_connected.assert_not_awaited()
                    self.assertEqual(node.parameter_values, before)
                    self.assertEqual(node.upload_calls, 0)
                    self.assertEqual(node.bridge.posts, [])
                    self.assertEqual(node.saved, [])
                image._hmb_shot_routing_snapshot.assert_not_called()
                image.process.assert_not_called()

    def test_connected_imageasset_remains_authority_and_only_conflict_fails(self):
        for graph_project in CANONICAL_PROJECTS:
            node = Node(); graph = Graph(node); graph.direct(project=graph_project)
            node.select(graph_project)
            with graph.context():
                captured = node._capture_imageasset_project_selection()
                self.assertEqual(captured["schema"], t.PROJECT_SELECTION_SCHEMA)
                self.assertEqual(captured["project"]["project_id"], graph_project)
                self.assertTrue(captured["sources"])
                node.select(next(value for value in CANONICAL_PROJECTS if value != graph_project))
                with self.assertRaises(ValueError):
                    node._capture_imageasset_project_selection()

    def test_explicit_selector_cannot_hide_invalid_imageasset_source_or_graph(self):
        for problem in ("crossflow", "deleted", "replaced", "wrongport", "impostor", "missing", "bad-project"):
            with self.subTest(problem=problem):
                node = Node(); graph = Graph(node); image = graph.direct(hidden=True, project="katuri8")
                node.select("katuri8")
                if problem == "crossflow": graph.flows[image.name] = "other-flow"
                elif problem == "deleted": image._hmb_node_deleted = True
                elif problem == "replaced": graph.nodes[image.name] = SimpleNamespace(name=image.name, metadata=image.metadata)
                elif problem == "wrongport": graph.edges[node.name][0].source_parameter_name = "wrong-port"
                elif problem == "impostor": graph.classes["HMBImageAssetLibrary"] = type("Other", (), {})
                elif problem == "missing": del graph.nodes[image.name]
                else: image.project = "unknown"
                with graph.context(), self.assertRaises(ValueError):
                    node._capture_imageasset_project_selection()

    def test_hidden_only_selection_is_dormant_in_shot_and_restored_in_only(self):
        for hidden_value in ("superwings12", "unknown", True, {"project_id": "superwings12"}):
            with self.subTest(authored=hidden_value):
                node = Node(); graph = Graph(node); graph.direct(project="katuri8")
                node.select(hidden_value); node.shot()
                before = deepcopy(node.parameter_values)
                with graph.context():
                    selected = node._capture_imageasset_project_selection()
                self.assertEqual(selected["project"]["project_id"], "katuri8")
                self.assertEqual(selected["schema"], t.PROJECT_SELECTION_SCHEMA)
                self.assertEqual(node.parameter_values, before)
                node.only()
                self.assertEqual(node.get_parameter_value(ONLY_PROJECT_PARAMETER), hidden_value)
                with graph.context(), self.assertRaises(ValueError):
                    node._capture_imageasset_project_selection()

    def test_shot_cannot_use_a_disconnected_hidden_only_project(self):
        node = Node(); graph = Graph(node); node.select("katuri8"); node.shot()
        with graph.context(), self.assertRaises(ValueError):
            node._capture_imageasset_project_selection()

    def test_registered_owner_and_flow_are_required_even_for_explicit_only(self):
        for problem in ("owner-replaced", "owner-deleted", "flow-missing"):
            with self.subTest(problem=problem):
                node = Node(); graph = Graph(node); node.select("katuri8")
                if problem == "owner-replaced": graph.nodes[node.name] = object()
                elif problem == "owner-deleted": node._hmb_node_deleted = True
                else: graph.flows[node.name] = ""
                with graph.context(), self.assertRaises(ValueError):
                    node._capture_imageasset_project_selection()

    def test_snapshot_detects_selector_mode_flow_and_added_imageasset_changes(self):
        for change in ("selector", "only-to-shot", "owner-flow", "added-imageasset"):
            with self.subTest(change=change):
                node = Node(); graph = Graph(node); node.select("katuri8")
                with graph.context():
                    selected = node._capture_imageasset_project_selection()
                    if change == "selector": node.select("superwings12")
                    elif change == "only-to-shot": node.shot()
                    elif change == "owner-flow": graph.flows[node.name] = "changed-flow"
                    else: graph.direct(project="katuri8")
                    with self.assertRaises(t._ProjectSelectionChanged):
                        node._assert_imageasset_project_selection(selected)

    def test_selector_change_after_media_preparation_prevents_generation_post(self):
        node = Node(values_for(t.TASK_VIDEO_EDITING)); graph = Graph(node); node.select("katuri8")
        prepare = node._prepare_video_references_for_run
        def changed(values):
            result = prepare(values)
            node.select("superwings12")
            return result
        node._prepare_video_references_for_run = changed
        with graph.context(), run_boundaries(), self.assertRaises(t._ProjectSelectionChanged):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.upload_calls, 1)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.saved, [])

    def test_owner_loop_and_paced_post_guard_recheck_only_selector(self):
        async def scenario():
            node = Node(); graph = Graph(node); node.select("katuri8")
            owner_thread = threading.get_ident()
            original_read = graph.read
            def read(request):
                self.assertEqual(threading.get_ident(), owner_thread)
                return original_read(request)
            graph.read = read
            with graph.context():
                node._hmb_project_selection_guard = {"selection": node._capture_imageasset_project_selection(),
                    "loop": asyncio.get_running_loop(), "thread": owner_thread}
                await asyncio.to_thread(node._assert_operation_project_selection)
                post = mock.Mock(side_effect=AssertionError("Generation submitted after project change"))
                with mock.patch.object(t, "_broker_wait_for_submission_slot", side_effect=lambda: node.select("superwings12")), \
                     self.assertRaises(t._ProjectSelectionChanged):
                    await node._await_submission_result(post, {})
                post.assert_not_called()
        asyncio.run(scenario())

    def test_only_capability_is_authenticated_and_legacy_schema_does_not_add_a_get(self):
        opener = OnlyProjectOpener(); bridge = authenticated_bridge(opener)
        bridge.require_generation_project_selection(t.PROJECT_SELECTION_SCHEMA)
        self.assertEqual(opener.calls, [])
        bridge.require_generation_project_selection(ONLY_PROJECT_SELECTION_SCHEMA)
        self.assertEqual([call["path"] for call in opener.calls], [REVIEW_CAPABILITIES_PATH])
        bridge._load_access_token.assert_called_once_with()
        bridge._clear_access_token.assert_not_called()
        with self.assertRaises(t._BrokerProtocolError):
            bridge.require_generation_project_selection("arbitrary-project-schema")
        self.assertEqual(len(opener.calls), 1)

    def test_missing_malformed_or_failed_only_support_never_uploads_or_submits(self):
        def support(document, value, *, missing=False):
            routing = document["project_routing"]
            if missing:
                routing.pop("generation_project_selection_schemas")
            else:
                routing["generation_project_selection_schemas"] = value
            return document
        cases = [lambda *_: None, lambda *_: {}, lambda *_: 401, lambda *_: 503,
                 lambda *_: TimeoutError("offline project capability timeout"),
                 lambda doc, count: support(doc, None, missing=True)]
        for value in (None, [], ONLY_PROJECT_SELECTION_SCHEMA, [t.PROJECT_SELECTION_SCHEMA],
                      [ONLY_PROJECT_SELECTION_SCHEMA, False]):
            cases.append(lambda doc, count, value=value: support(doc, value))
        for index, transform in enumerate(cases):
            with self.subTest(fixture=index):
                node = Node(values_for(t.TASK_VIDEO_EDITING)); graph = Graph(node); node.select("katuri8")
                node.transport.project_transform = transform
                with graph.context(), run_boundaries(), self.assertRaises(t._BrokerError):
                    asyncio.run(node._process_generation_impl())
                self.assertEqual(node.upload_calls, 0)
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(node.saved, [])
                self.assertEqual([call["path"] for call in node.transport.calls], [REVIEW_CAPABILITIES_PATH])
                if index == 2:
                    node.bridge._clear_access_token.assert_called_once_with()

    def test_late_only_support_loss_blocks_the_frozen_request_without_reclassification(self):
        node = Node(values_for(t.TASK_VIDEO_EDITING)); graph = Graph(node); node.select("katuri8")
        def changed(document, occurrence):
            if occurrence > 1:
                document["project_routing"]["generation_project_selection_schemas"] = [t.PROJECT_SELECTION_SCHEMA]
            return document
        node.transport.project_transform = changed
        with graph.context(), run_boundaries(), self.assertRaises(t._BrokerProtocolError):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.upload_calls, 1)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.saved, [])
        self.assertEqual(node.transport.project_capability_calls, 2)
        self.assertEqual(node.get_parameter_value(ONLY_PROJECT_PARAMETER), "katuri8")

    def test_existing_imageasset_selection_keeps_its_wire_and_never_needs_only_support(self):
        node = Node(values_for(t.TASK_VIDEO_EXTENSION)); graph = Graph(node)
        graph.direct(project="katuri8")
        node.transport.project_transform = lambda *_: AssertionError("ImageAsset required new Only capability")
        with graph.context(), run_boundaries():
            asyncio.run(node._process_generation_impl())
        self.assertEqual(len(node.bridge.posts), 1)
        self.assertEqual(node.bridge.posts[0]["project_selection_schema"], t.PROJECT_SELECTION_SCHEMA)
        self.assertEqual(node.bridge.posts[0]["project_id"], "katuri8")
        self.assertEqual(node.transport.project_capability_calls, 0)
        self.assertGreater(node.bridge._load_access_token.call_count, 0)

    def test_final_and_resume_keep_original_task_project_without_new_only_selection(self):
        # The new selector must not reclassify an existing immutable Draft or
        # require today's project-capability advertisement to retrieve it.
        for operation in ("final", "resume"):
            with self.subTest(operation=operation):
                values = base.params(t.DRAFT_ACTION_FINAL if operation == "final" else t.DRAFT_ACTION_OFF)
                values.update(resolution="1080p", output_format="mov")
                node = Node(values); graph = Graph(node)
                # Only Final with no current selection is a genuine legacy
                # source. Resume remains independent of today's selector.
                node.select(ONLY_PROJECT_UNSELECTED if operation == "final" else "katuri8")
                node.transport.project_transform = lambda *_: AssertionError("Inherited task checked Only selection")
                if operation == "final":
                    node._store_draft_source(deepcopy(values["_hmb_draft_source"]))
                    with graph.context():
                        self.assertEqual(node._validated_draft_final_source(values["_hmb_draft_source"]),
                                         values["_hmb_draft_source"])
                if operation == "resume":
                    checkpoint = base.params(t.DRAFT_ACTION_PREVIEW)
                    checkpoint.update(resolution="480p", output_format="mov",
                        _hmb_output_file=str(Path(node.base.name, "original-draft.mov")),
                        _hmb_broker_server_url=base.ORIGIN, _hmb_draft_project=deepcopy(base.PROJECT))
                    node._set_generation_recovery_checkpoint(stage="pre_submit", task_id="hmb-previous",
                        task_identity="client_request", status="submitting", params=checkpoint)
                    node._set_generation_recovery_checkpoint(stage="accepted", task_id=base.JOB,
                        task_identity="broker_task", status="pending", params=checkpoint)
                    node.values["resume_generation_id"] = base.JOB
                    node.parameter_values["resume_generation_id"] = base.JOB
                with graph.context(), run_boundaries():
                    asyncio.run(node._process_generation_impl())
                self.assertEqual(node.transport.project_capability_calls, 0)
                self.assertEqual(len(node.saved), 1)
                if operation == "final":
                    self.assertEqual(len(node.bridge.posts), 1)
                    self.assertEqual({key: node.bridge.posts[0][key] for key in base.PROJECT}, base.PROJECT)
                    self.assertNotIn("project_selection_schema", node.bridge.posts[0])
                else:
                    self.assertEqual(node.bridge.posts, [])
                    self.assertTrue(node.saved[0][1].endswith("original-draft.mov"))

    def test_only_final_project_validator_only_allows_a_true_missing_legacy_selection(self):
        for context in ("same", "other", "legacy-missing", "unknown", "wrong-edge", "lookup-failure"):
            with self.subTest(context=context):
                node = Node(); graph = Graph(node)
                node.parameter_values["model_id"] = t.MODEL_NAME_SEEDANCE_2_5
                source = deepcopy(base.SOURCE)
                node.select(source["project_id"] if context == "same" else
                            "katuri8" if context == "other" else
                            "unknown" if context == "unknown" else ONLY_PROJECT_UNSELECTED)
                if context == "wrong-edge":
                    graph.direct(hidden=True, project=source["project_id"])
                    graph.edges[node.name][0].source_parameter_name = "wrong-port"
                with graph.context():
                    if context == "lookup-failure":
                        with mock.patch.object(t.GriptapeNodes, "handle_request", return_value=None), self.assertRaises(ValueError):
                            node._validated_draft_final_source(source)
                    elif context in {"same", "legacy-missing"}:
                        self.assertEqual(node._validated_draft_final_source(source), source)
                    else:
                        with self.assertRaises(ValueError):
                            node._validated_draft_final_source(source)
                self.assertEqual(node.transport.calls, [])
                self.assertEqual(node.upload_calls, 0)
                self.assertEqual(node.bridge.posts, [])


if __name__ == "__main__":
    t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    unittest.main()
