"""Portable, authenticated-I/O-free regression for ordinary versus Draft routes.

The real Generator, Broker feature checks and JSON/authentication transport run.
Only the opener is synthetic; no server import, engine, credential, network or
provider is used. Temporary destinations never contain user media. The frozen
pure server fixture keeps clean CI independent of a local API SERVER checkout.
"""
from __future__ import annotations

import ast
import asyncio
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
from urllib.parse import urlsplit


TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "capability_routing_shot_fixture", TESTS / "HMB_Seedance_Draft_Shot_Regression.py")
assert spec and spec.loader
shot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shot
spec.loader.exec_module(shot)
base = shot.base
t = base.t

# Exact pure function from C:\API SERVER\app.py, inspected 2026-10-16 (V27).
# Hash covers semantic AST fields, excluding locations and Python 3.12's empty
# type_params addition. Nonempty generic parameters remain part of the hash.
# No server globals are imported: the documented TTL and additive provenance
# literals are supplied below; the live server's isolated contract suite checks
# the actual global literals as well as first-accept record immutability.
SERVER_FIXTURE_AST_SHA256 = "63413b947e7e5f19d075c2c1fc6d1b1f5cc8bfef3b0565f9931291b7edc64525"
# Local server candidate inspected 2026-10-20 adds only the optional captured
# Shot metadata capability. It has not been deployed. Preserve the published
# frozen contract above, and recognize this exact additive candidate separately
# when auditing a developer's optional API SERVER checkout. Arbitrary server
# drift, including a changed existing profile or route, must still fail.
SERVER_SHOT_METADATA_CANDIDATE_AST_SHA256 = "b9c18f5e60bb1e8a22d16f676301f997b9eec4c91db55bb7a1551d419b53ffe9"
SEEDANCE_DRAFT_SOURCE_TTL_SECONDS = 7 * 24 * 60 * 60
GENERATION_MODE_METADATA_SCHEMA = "hmb-generation-mode-v1"
GENERATION_MODE_METADATA_FIELD = "hmb_generation_mode"
GENERATION_MODE_METADATA_CHOICES = ("only", "shot")
GENERATION_TASK_METADATA_FIELD = "hmb_generation_task"
GENERATION_TASK_METADATA_CHOICES = ("Text Only", "First/Last Frame", "Reference to Video", "Video Editing", "Video Extension")


def seedance_generation_capabilities(*, draft=False):
    """Keep the installed v2 contract stable; opt in to Draft capabilities."""
    profile={
        "tasks":["text_to_video","first_last_frame","reference_to_video","video_editing","video_extension"],
        "output_formats":["mp4","mov"],
        "return_last_frame":True,
    }
    if draft:
        profile.update({
            "draft_generation":True,
            "draft_preview_resolution":"480p",
            "draft_final_resolution":"1080p",
            "draft_output_formats":["mp4","mov"],
            "draft_source_ttl_seconds":SEEDANCE_DRAFT_SOURCE_TTL_SECONDS,
            "draft_source_reference":"broker_job_id",
            "draft":{"preview_resolution":"480p","final_resolution":"1080p",
                     "source_reference":"broker_job_id",
                     "source_ttl_seconds":SEEDANCE_DRAFT_SOURCE_TTL_SECONDS},
        })
    return {
        "schema":"hmb-seedance-generation-capabilities",
        "version":3 if draft else 2,
        "generation_mode_metadata":{"schema":GENERATION_MODE_METADATA_SCHEMA,
                                    "field":GENERATION_MODE_METADATA_FIELD,
                                    "choices":list(GENERATION_MODE_METADATA_CHOICES),
                                    "task_field":GENERATION_TASK_METADATA_FIELD,
                                    "tasks":list(GENERATION_TASK_METADATA_CHOICES)},
        "models":{"doubao-seedance-2-5-260628":profile},
    }


CAP_PATH = t.BROKER_SEEDANCE_CAPABILITIES_PATH
DRAFT_PATH = CAP_PATH + "?draft=1"
GENERATE_PATH = "/api/v1/generate/video"
SYNTHETIC_TOKEN = "offline-capability-routing-token"
METRICS = Counter()


def function_node(source):
    return next(node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef)
                and node.name == "seedance_generation_capabilities")


def function_hash(node):
    normalized = deepcopy(node)
    for item in ast.walk(normalized):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and getattr(item, "type_params", None) == []:
            # ast.dump omits an absent optional field in both Python 3.11/3.12.
            # Remove only this known version-added, semantically empty field.
            del item.type_params
    return hashlib.sha256(ast.dump(normalized, include_attributes=False).encode()).hexdigest()


class RouteOpener:
    """Honor the server query boundary rather than return v3 for every GET."""
    def __init__(self):
        self.calls = []
        self.responses = []
        self.transform = lambda document, draft, occurrence: document
        self.get_count = Counter()
        self.job_id = "job-" + "c" * 32

    @property
    def posts(self):
        return [call for call in self.calls
                if call["method"] == "POST" and call["path"] == GENERATE_PATH]

    @property
    def capability_paths(self):
        return [call["path"] for call in self.calls
                if call["method"] == "GET" and call["path"] in (CAP_PATH, DRAFT_PATH)]

    @property
    def state_paths(self):
        return [call["path"] for call in self.calls
                if call["method"] == "GET"
                and call["path"].startswith("/api/v1/reviews/tasks/")
                and call["path"].endswith("/draft-final")]

    def open(self, request, timeout):
        assert request.get_header("Authorization") == "Bearer " + SYNTHETIC_TOKEN
        assert 0 < timeout <= 60
        parsed = urlsplit(request.full_url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        method = request.get_method()
        body = json.loads(request.data) if request.data is not None else None
        self.calls.append({"method": method, "path": path, "body": deepcopy(body),
                           "idempotency_key": request.get_header("Idempotency-key", "")})
        METRICS["synthetic_authenticated_requests"] += 1
        if (method == "GET" and parsed.path.startswith("/api/v1/reviews/tasks/")
                and parsed.path.endswith("/draft-final")):
            assert not parsed.query
            assert request.data is None
            source_id = parsed.path.split("/")[-2]
            assert source_id == base.JOB
            now = int(time.time())
            result = {"schema": "hmb-review-draft-final-v1", "state_schema": "hmb-draft-final-state-v1",
                "source_task_id": source_id, "state": "available", "is_draft": True,
                "eligible": True, "consumed": False, "checked_at": now, "expires_at": now + 604800,
                "owner_user_id": 1, "idempotency_key": t._seedance_draft_final_request_id(source_id),
                "child_task_id": None, "child_status": None, **base.PROJECT}
            METRICS["synthetic_draft_final_state_gets"] += 1
        elif method == "GET":
            assert path in (CAP_PATH, DRAFT_PATH), path
            assert request.data is None
            draft = path == DRAFT_PATH
            self.get_count[draft] += 1
            document = self.transform(seedance_generation_capabilities(draft=draft),
                                      draft, self.get_count[draft])
            if isinstance(document, BaseException):
                raise document
            if isinstance(document, int):
                raise urllib.error.HTTPError(request.full_url, document,
                    "Synthetic capability rejection", {}, io.BytesIO(b'{"error":"offline rejection"}'))
            self.responses.append((path, deepcopy(document)))
            result = document
        elif method == "POST" and path == GENERATE_PATH:
            assert request.get_header("Idempotency-key") == body["client_request_id"]
            METRICS["synthetic_generation_posts"] += 1
            result = {"id": self.job_id, "status": "succeeded", "video_url": "offline-fixture"}
        elif method == "POST" and path.startswith("/api/v1/jobs/") and path.endswith("/refresh"):
            assert body is None
            METRICS["synthetic_refresh_posts"] += 1
            result = {"id": path.split("/")[-2], "status": "succeeded", "video_url": "offline-fixture"}
        else:
            raise AssertionError(f"Unexpected synthetic transport: {method} {path}")
        response = io.BytesIO(json.dumps(result).encode())
        response.status = 200
        response.geturl = lambda: request.full_url
        return response


def bridge_for(opener):
    # The real JSON transport supplies and validates the synthetic auth header.
    # Replacing these two methods prevents any reading/clearing of user tokens.
    bridge = t._HMBAIBrokerBridge(opener=opener, server_url=base.ORIGIN)
    bridge._load_access_token = mock.Mock(return_value=SYNTHETIC_TOKEN)
    bridge._clear_access_token = mock.Mock()
    return bridge


class RoutingNode(base.Node):
    def __init__(self, action=t.DRAFT_ACTION_OFF, *, output_format="mov"):
        values = base.params(action)
        values.update(resolution="1080p" if action == t.DRAFT_ACTION_FINAL else "480p",
                      output_format=output_format)
        super().__init__(values)
        self.transport = RouteOpener()
        self.bridge = bridge_for(self.transport)
        self.media_snapshots = []
        authored_path = str(Path(self.base.name, "authored." + output_format))
        self.parameter_values.update(output_format=output_format, output_file=authored_path)
        self.destination = SimpleNamespace(resolve=lambda: authored_path)
        self.build = mock.Mock(return_value=self.destination)
        self._output_file = SimpleNamespace(build_file=self.build,
                                            _default_filename=Path(authored_path).name)
        self.selection = {"schema": t.PROJECT_SELECTION_SCHEMA, "project": deepcopy(base.PROJECT)}
        self._capture_imageasset_project_selection = mock.Mock(return_value=self.selection)
        if action == t.DRAFT_ACTION_FINAL:
            # Final now validates a fresh authenticated state against the
            # locally retained source, not merely an execution-copy parameter.
            self._store_draft_source(deepcopy(values["_hmb_draft_source"]))

    def _resolve_exact_shot_generation_inputs(self, values):
        return {**values, "_hmb_imageasset_project_selection": deepcopy(self.selection)}

    def _prepare_video_references_for_run(self, values):
        self.upload_calls += 1
        self.media_snapshots.append(deepcopy(values))
        return values


def route_formats(document, *, ordinary=None, draft=None):
    profile = document["models"][t.SEEDANCE_2_5_MODEL_ID]
    if ordinary is not None:
        profile["output_formats"] = deepcopy(ordinary)
    if draft is not None and "draft_output_formats" in profile:
        profile["draft_output_formats"] = deepcopy(draft)
    return document


class CapabilityRoutingTests(unittest.TestCase):
    def setUp(self):
        selected = mock.patch.object(t._broker_config, "load_broker_base_url", return_value=base.ORIGIN)
        selected.start()
        self.addCleanup(selected.stop)
        self.boundaries = mock.patch.object(t, "_resolve_mp4_decode_verifier",
            return_value=SimpleNamespace(executable="offline-fixture", backend="test"))
        self.boundaries.start()
        self.review = mock.patch.object(t._review, "capture_inputs", return_value={})
        self.review.start()
        self.diagnostics = mock.patch.object(t, "_broker_log_transport_error")
        self.diagnostics.start()
        self.token_fence = mock.patch.object(t, "_broker_load_token",
            side_effect=AssertionError("Offline regression attempted to load a real credential"))
        self.token_fence.start()
        self.network_fence = mock.patch.object(t.urllib.request.OpenerDirector, "open",
            side_effect=AssertionError("Offline regression attempted an external request"))
        self.network_fence.start()
        self.origin_fence = mock.patch.object(t._review, "bind_task_origin")
        self.origin_fence.start()
        self.project_fence = mock.patch.object(t._review, "bind_task_project")
        self.project_fence.start()
        self.addCleanup(self.boundaries.stop)
        self.addCleanup(self.review.stop)
        self.addCleanup(self.diagnostics.stop)
        self.addCleanup(self.token_fence.stop)
        self.addCleanup(self.network_fence.stop)
        self.addCleanup(self.origin_fence.stop)
        self.addCleanup(self.project_fence.stop)

    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def test_frozen_actual_server_contract_is_portable_and_route_sensitive(self):
        fixture = function_node(Path(__file__).read_text(encoding="utf-8"))
        self.assertEqual(function_hash(fixture), SERVER_FIXTURE_AST_SHA256)
        changed = deepcopy(fixture)
        version = next(value for key, value in zip(changed.body[-1].value.keys, changed.body[-1].value.values)
                       if isinstance(key, ast.Constant) and key.value == "version")
        version.body.value = 99
        self.assertNotEqual(function_hash(changed), SERVER_FIXTURE_AST_SHA256)
        for field in ("argument", "return", "docstring"):
            with self.subTest(changed_semantic_field=field):
                changed = deepcopy(fixture)
                if field == "argument":
                    changed.args.kw_defaults[0].value = True
                elif field == "return":
                    changed.returns = ast.Name(id="dict", ctx=ast.Load())
                else:
                    changed.body[0].value.value += " changed"
                self.assertNotEqual(function_hash(changed), SERVER_FIXTURE_AST_SHA256)
        if hasattr(ast, "TypeVar"):
            generic = deepcopy(fixture)
            generic.type_params = [ast.TypeVar(name="T", bound=None)]
            self.assertNotEqual(function_hash(generic), SERVER_FIXTURE_AST_SHA256)
        ordinary = seedance_generation_capabilities()
        draft = seedance_generation_capabilities(draft=True)
        self.assertEqual((ordinary["version"], draft["version"]), (2, 3))
        profile = ordinary["models"][t.SEEDANCE_2_5_MODEL_ID]
        self.assertEqual(set(profile), {"tasks", "output_formats", "return_last_frame"})
        self.assertEqual(profile["output_formats"], ["mp4", "mov"])
        self.assertEqual(draft["models"][t.SEEDANCE_2_5_MODEL_ID]["draft_output_formats"], ["mp4", "mov"])
        # Portable CI always runs the frozen contract above. When the local
        # server source exists, extract only its pure function (never import it).
        local_server = Path("C:/API SERVER/app.py")
        if local_server.is_file():
            actual = function_node(local_server.read_text(encoding="utf-8-sig"))
            actual_hash = function_hash(actual)
            self.assertIn(actual_hash, {SERVER_FIXTURE_AST_SHA256,
                                      SERVER_SHOT_METADATA_CANDIDATE_AST_SHA256})
            namespace = {name: globals()[name] for name in (
                "SEEDANCE_DRAFT_SOURCE_TTL_SECONDS", "GENERATION_MODE_METADATA_SCHEMA",
                "GENERATION_MODE_METADATA_FIELD", "GENERATION_MODE_METADATA_CHOICES",
                "GENERATION_TASK_METADATA_FIELD", "GENERATION_TASK_METADATA_CHOICES")}
            candidate = actual_hash == SERVER_SHOT_METADATA_CANDIDATE_AST_SHA256
            shot_capability = {"schema": "hmb-generation-shot-metadata", "version": 1,
                               "field": "hmb_shot", "enabled": True}
            if candidate:
                namespace["review_submission_shots"] = SimpleNamespace(
                    capability=lambda: deepcopy(shot_capability))
            exec(compile(ast.Module(body=[actual], type_ignores=[]), "<pure-server-fixture>", "exec"), namespace)
            for selected in (False, True):
                expected = seedance_generation_capabilities(draft=selected)
                if candidate:
                    expected["generation_shot_metadata"] = deepcopy(shot_capability)
                self.assertEqual(namespace[actual.name](draft=selected), expected)

    def test_actual_bridge_ordinary_v2_route_and_wire_never_opt_into_draft(self):
        node = RoutingNode()
        asyncio.run(node._process_generation_impl())
        self.assertEqual(node.transport.capability_paths, [CAP_PATH, CAP_PATH])
        self.assertEqual(node.transport.state_paths, [])
        self.assertEqual(len(node.transport.posts), 1)
        for _, document in node.transport.responses:
            self.assertEqual(document["version"], 2)
            self.assertNotIn("draft_output_formats", document["models"][t.SEEDANCE_2_5_MODEL_ID])
        body = node.transport.posts[0]["body"]
        self.assertNotIn("draft", body)
        self.assertNotIn("draft_job_id", body)
        self.assertEqual(body["output_format"], "mov")
        self.assertEqual(node.saved[0][2]["output_format"], "mov")
        self.assertTrue(node.saved[0][1].endswith(".mov"))

    def test_five_same_draft480_mov_generators_each_submit_once_and_never_auto_final(self):
        nodes = []
        for index in range(5):
            node = RoutingNode(t.DRAFT_ACTION_PREVIEW)
            node.transport.job_id = "job-" + str(index + 1) * 32
            # Exercise the real completed-Agent fence with five independent
            # synthetic results; no Agent/model execution is part of this test.
            snapshot = mock.Mock(return_value={"status": "succeeded", "run_id": str(index),
                "output_sha256": hashlib.sha256(node.values["prompt"].encode()).hexdigest()})
            node._manual_agent_prompt_source = mock.Mock(return_value=SimpleNamespace(
                _hmb_execution_result_snapshot=snapshot))
            node._assert_agent_result_available = t.HMBSeedanceGeneration._assert_agent_result_available.__get__(node)
            asyncio.run(node._process_generation_impl())
            nodes.append(node)
            self.assertEqual(len(node.transport.posts), 1)
            body = node.transport.posts[0]["body"]
            self.assertIs(body["draft"], True)
            self.assertEqual((body["resolution"], body["quality"], body["output_format"]),
                             ("480p", "480p", "mov"))
            self.assertNotIn("draft_job_id", body)
            self.assertGreaterEqual(len(node.transport.capability_paths), 2)
            self.assertEqual(set(node.transport.capability_paths), {DRAFT_PATH})
            self.assertEqual(node.transport.state_paths, [])
            self.assertEqual(node.upload_calls, 1)
            self.assertEqual(len(node.saved), 1)
            self.assertTrue(node.saved[0][1].endswith(".mov"))
            self.assertEqual(node.saved[0][2]["output_format"], "mov")
            self.assertTrue(snapshot.called)
        self.assertEqual(len({node.transport.posts[0]["body"]["client_request_id"] for node in nodes}), 5)
        METRICS["same_draft480_mov_generators"] += len(nodes)
        METRICS["completed_agent_result_fences"] += len(nodes)

    def test_only_and_shot_direct_final_query_draft_once_no_agent_or_upstream(self):
        async def scenario(bound):
            node = shot.Node(shot=bound)
            opener = RouteOpener()
            node.bridge = bridge_for(opener)
            source = shot.completed_source(node)
            node._store_draft_source(source)
            state_gets_before_click = len(opener.state_paths)
            node.parameter_values.update(prompt="preserve authored prompt {{SIGN}}", duration=29,
                                         output_format="mov", ratio="9:16")
            shot.forbid_upstream_work(node)
            with shot.run_boundaries(node), shot.engine_loop_patch(asyncio.get_running_loop()), \
                 mock.patch.object(t.GriptapeNodes, "handle_request",
                    side_effect=AssertionError("Final executed upstream graph"), create=True), \
                 mock.patch.object(t.GriptapeNodes, "ahandle_request",
                    side_effect=AssertionError("Final executed async upstream graph"), create=True):
                first = node._on_finalize_draft_clicked(None, None,
                    action_id="route-final-first", expected_draft_job_id=base.JOB)
                future = node._hmb_draft_finalize_future
                duplicate = node._on_finalize_draft_clicked(None, None,
                    action_id="route-final-duplicate", expected_draft_job_id=base.JOB)
                self.assertTrue(first.success)
                self.assertTrue(duplicate.success)
                self.assertIs(node._hmb_draft_finalize_future, future)
                await asyncio.wrap_future(future)
                later = node._on_finalize_draft_clicked(None, None,
                    action_id="route-final-later", expected_draft_job_id=base.JOB)
                self.assertFalse(later.success)
            self.assertEqual(len(opener.posts), 1, node._set_status_results.call_args_list)
            self.assertEqual(set(opener.capability_paths), {DRAFT_PATH})
            self.assertGreater(len(opener.state_paths), state_gets_before_click)
            self.assertEqual(set(opener.state_paths), {
                "/api/v1/reviews/tasks/" + base.JOB + "/draft-final"})
            self.assertEqual(opener.posts[0]["body"], {"provider": "volcengine_ark",
                "model": t.SEEDANCE_2_5_MODEL_ID, "draft_job_id": base.JOB,
                "resolution": "1080p", "output_format": "mov", **base.PROJECT,
                "client_request_id": t._seedance_draft_final_request_id(base.JOB)})
            self.assertEqual(node.upload_calls, 0)
            node._manual_agent_prompt_source.assert_not_called()
            node._prepare_video_references_for_run.assert_not_called()
            node._resolve_exact_shot_generation_inputs.assert_not_called()
            self.assertEqual(node.get_parameter_value("prompt"), "preserve authored prompt {{SIGN}}")
            self.assertEqual(len(node.saved), 1)
            self.assertTrue(node.saved[0][1].endswith(".mov"))
            METRICS["direct_final_agent_or_upstream_calls"] += 0
            METRICS["direct_final_one_shot_cases"] += 1
        for bound in (False, True):
            with self.subTest(shot=bound):
                asyncio.run(scenario(bound))

    def test_mp4_only_fallback_is_proven_before_media_and_freezes_request_path_and_save(self):
        for action in (t.DRAFT_ACTION_OFF, t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
            with self.subTest(action=action):
                node = RoutingNode(action)
                node.transport.transform = lambda document, draft, count: route_formats(
                    document, ordinary=["mp4"], draft=["mp4"])
                asyncio.run(node._process_generation_impl())
                self.assertEqual(len(node.transport.posts), 1)
                self.assertEqual(node.transport.posts[0]["body"].get("output_format", "mp4"), "mp4")
                self.assertEqual(node.get_parameter_value("output_format"), "mov")
                self.assertTrue(node.get_parameter_value("output_file").endswith(".mov"))
                self.assertTrue(node.saved[0][1].endswith(".mp4"))
                self.assertEqual(node.saved[0][2]["output_format"], "mp4")
                recovery = node._generation_recovery_state()
                self.assertEqual((recovery["output_format"], recovery["output_file"]),
                                 ("mp4", node.saved[0][1]))
                if action != t.DRAFT_ACTION_FINAL:
                    self.assertEqual(len(node.media_snapshots), 1)
                    self.assertEqual(node.media_snapshots[0]["output_format"], "mp4")
                    self.assertTrue(node.media_snapshots[0]["_hmb_output_file"].endswith(".mp4"))
                METRICS["preupload_format_fallback_cases"] += 1

    def test_draft_and_ordinary_support_lists_are_independent_on_real_routes(self):
        for ordinary, draft, expected in ((["mp4"], ["mp4", "mov"], "mov"),
                                          (["mp4", "mov"], ["mp4"], "mp4")):
            for action in (t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
                with self.subTest(ordinary=ordinary, draft=draft, action=action):
                    node = RoutingNode(action)
                    node.transport.transform = lambda document, selected, count: route_formats(
                        document, ordinary=ordinary, draft=draft)
                    asyncio.run(node._process_generation_impl())
                    self.assertEqual(len(node.transport.posts), 1)
                    self.assertEqual(set(node.transport.capability_paths), {DRAFT_PATH})
                    self.assertEqual(node.transport.posts[0]["body"].get("output_format", "mp4"), expected)
                    self.assertTrue(node.saved[0][1].endswith("." + expected))

    def test_invalid_missing_null_and_http_failures_stop_before_output_upload_or_post(self):
        def changed_formats(document, draft, count, value, missing=False):
            profile = document["models"][t.SEEDANCE_2_5_MODEL_ID]
            field = "draft_output_formats" if draft else "output_formats"
            if missing:
                profile.pop(field)
            else:
                profile[field] = value
            return document
        cases = [lambda *_: None, lambda *_: {}, lambda *_: 401, lambda *_: 503,
                 lambda *_: TimeoutError("offline timeout"),
                 lambda doc, selected, count: changed_formats(doc, selected, count, None, missing=True)]
        for malformed in (None, [], "mp4", ["mp4", False]):
            cases.append(lambda doc, selected, count, value=malformed:
                         changed_formats(doc, selected, count, value))
        for action in (t.DRAFT_ACTION_OFF, t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
            for index, transform in enumerate(cases):
                with self.subTest(action=action, fixture=index):
                    node = RoutingNode(action)
                    node.transport.transform = transform
                    with self.assertRaises(t._BrokerError):
                        asyncio.run(node._process_generation_impl())
                    self.assertEqual(node.transport.posts, [])
                    self.assertEqual(node.upload_calls, 0)
                    self.assertEqual(node.saved, [])
                    node.build.assert_not_called()
                    self.assertEqual(node.get_parameter_value("output_format"), "mov")
                    if index == 2:
                        node.bridge._clear_access_token.assert_called_once_with()
                    METRICS["invalid_capability_no_submit_cases"] += 1

    def test_late_capability_loss_never_rewrites_frozen_body_or_submits(self):
        for action, early_formats in ((t.DRAFT_ACTION_OFF, ["mp4", "mov"]),
                                      (t.DRAFT_ACTION_PREVIEW, ["mp4", "mov"]),
                                      (t.DRAFT_ACTION_PREVIEW, ["mp4"])):
            with self.subTest(action=action, early_formats=early_formats):
                node = RoutingNode(action)
                def transform(document, draft, count):
                    document = route_formats(document, ordinary=early_formats, draft=early_formats)
                    if node.upload_calls:
                        profile = document["models"][t.SEEDANCE_2_5_MODEL_ID]
                        if draft:
                            profile.pop("draft_output_formats")
                        else:
                            profile["output_formats"] = ["mp4"]
                    return document
                node.transport.transform = transform
                expected = "mp4" if early_formats == ["mp4"] else "mov"
                with self.assertRaises(t._BrokerProtocolError):
                    asyncio.run(node._process_generation_impl())
                self.assertEqual(node.transport.posts, [])
                self.assertEqual(node.upload_calls, 1)
                self.assertEqual(node.saved, [])
                self.assertEqual(node.media_snapshots[0]["output_format"], expected)
                self.assertEqual(node._generation_recovery_state()["output_format"], expected)
                self.assertEqual(node.get_parameter_value("output_format"), "mov")
                METRICS["late_loss_no_submit_cases"] += 1

    def test_legacy_mp4_contract_does_not_imply_mov_unsupported(self):
        for requested, succeeds in (("mp4", True), ("mov", False)):
            with self.subTest(requested=requested):
                node = RoutingNode(t.DRAFT_ACTION_PREVIEW, output_format=requested)
                def legacy(document, draft, count):
                    if draft:
                        document["models"][t.SEEDANCE_2_5_MODEL_ID].pop("draft_output_formats")
                    return document
                # An authenticated accepted Draft contract lacking only its
                # format list permits old MP4 callers but cannot prove a MOV
                # limitation or authorize MOV-to-MP4 fallback.
                node.transport.transform = legacy
                if succeeds:
                    asyncio.run(node._process_generation_impl())
                    self.assertEqual(len(node.transport.posts), 1)
                    self.assertEqual(node.saved[0][2]["output_format"], "mp4")
                else:
                    with self.assertRaises(t._BrokerProtocolError):
                        asyncio.run(node._process_generation_impl())
                    self.assertEqual(node.transport.posts, [])
                    node.build.assert_not_called()

    def test_frozen_mp4_and_mov_resume_uses_no_capability_or_generation_post(self):
        for action in (t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_FINAL):
            for frozen_format in ("mp4", "mov"):
                with self.subTest(action=action, frozen_format=frozen_format):
                    node = RoutingNode()
                    original = base.params(action)
                    saved_path = str(Path(node.base.name, "original-stage." + frozen_format))
                    original.update(resolution="480p" if action == t.DRAFT_ACTION_PREVIEW else "1080p",
                        output_format=frozen_format, _hmb_output_file=saved_path,
                        _hmb_broker_server_url=base.ORIGIN, _hmb_draft_project=deepcopy(base.PROJECT))
                    node._set_generation_recovery_checkpoint(stage="pre_submit", task_id="hmb-previous",
                        task_identity="client_request", status="submitting", params=original)
                    node._set_generation_recovery_checkpoint(stage="accepted", task_id=base.JOB,
                        task_identity="broker_task", status="pending", params=original)
                    node.values.update(resume_generation_id=base.JOB, draft_action=t.DRAFT_ACTION_OFF,
                                       output_format="mov" if frozen_format == "mp4" else "mp4")
                    node.parameter_values["resume_generation_id"] = base.JOB
                    node.transport.transform = lambda *_: AssertionError("Resume checked capabilities")
                    asyncio.run(node._process_generation_impl())
                    self.assertEqual(node.transport.posts, [])
                    self.assertEqual(node.transport.capability_paths, [])
                    self.assertEqual(len(node.transport.calls), 1)
                    self.assertEqual(node.transport.calls[0]["path"], "/api/v1/jobs/" + base.JOB + "/refresh")
                    self.assertEqual((node.saved[0][1], node.saved[0][2]["output_format"]),
                                     (saved_path, frozen_format))
                    METRICS["frozen_resume_no_generation_post_cases"] += 1

    def test_missing_authentication_cannot_reach_opener_or_submit(self):
        node = RoutingNode(t.DRAFT_ACTION_PREVIEW)
        node.bridge._load_access_token.side_effect = t._BrokerAuthenticationError("offline missing login")
        with self.assertRaises(t._BrokerAuthenticationError):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.transport.calls, [])
        self.assertEqual(node.saved, [])
        node.build.assert_not_called()

    def test_failed_pending_or_changed_agent_still_blocks_generation_post(self):
        for snapshot in ({"status": "created", "code": "AGENT_CREATED"},
                         {"status": "running"}, {"status": "failed"},
                         {"status": "succeeded", "output_sha256": "a" * 64}):
            with self.subTest(snapshot=snapshot):
                node = RoutingNode(t.DRAFT_ACTION_PREVIEW)
                node._manual_agent_prompt_source = mock.Mock(return_value=SimpleNamespace(
                    _hmb_execution_result_snapshot=lambda: deepcopy(snapshot)))
                node._assert_agent_result_available = t.HMBSeedanceGeneration._assert_agent_result_available.__get__(node)
                with self.assertRaises(t._AgentResultUnavailable):
                    asyncio.run(node._process_generation_impl())
                self.assertEqual(node.transport.posts, [])
                self.assertEqual(node.saved, [])
                METRICS["failed_agent_no_generation_post_cases"] += 1


if __name__ == "__main__":
    t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    runner = unittest.main(exit=False)
    print(json.dumps({"suite": "seedance-capability-routing", "tests_run": runner.result.testsRun,
        "failures": len(runner.result.failures), "errors": len(runner.result.errors),
        "fixture_ast_sha256": SERVER_FIXTURE_AST_SHA256, "metrics": dict(sorted(METRICS.items()))}, sort_keys=True))
    raise SystemExit(0 if runner.result.wasSuccessful() else 1)
