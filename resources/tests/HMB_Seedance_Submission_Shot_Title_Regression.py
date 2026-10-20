"""Submission-time Shot titles through the real payload/Bridge JSON boundary.

All transport, accounts and task records are synthetic. No user graph, server,
provider, original media, credentials or billable render is touched.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest import mock
import urllib.error
from urllib.parse import urlsplit

TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "submission_shot_title_fixture", TESTS / "HMB_Seedance_Generation_Mode_Regression.py")
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t, base, transport = fixture.t, fixture.base, fixture.transport
FIELD = "hmb_shot"
CHANNEL = "11111111-1111-4111-8111-111111111111"
SOURCE = "22222222-2222-4222-8222-222222222222"


def origin(number=1, name=None):
    return {"channel_uuid": CHANNEL,
        "shot_uuid": f"33333333-3333-4333-8333-{number:012d}",
        "source_node_instance_id": SOURCE, "number": number,
        "name": f"e201s120c00{number}__" if name is None else name}


def capability():
    return {"schema": "hmb-generation-shot-metadata", "version": 1,
            "field": FIELD, "enabled": True}


def advertise(document, *_args):
    return {**document, "generation_mode_metadata": fixture.metadata_capability(),
            "generation_shot_metadata": capability()}


def build(number=1, *, mode="shot", model=None, task=None, name=None):
    node = base.Node()
    node._prepare_media_reference = lambda _kind, value: value
    params = fixture.parameters(model or t.SEEDANCE_2_5_MODEL_ID,
                                task or t.TASK_REFERENCE_TO_VIDEO)
    params.update(_hmb_generation_mode=mode, _hmb_generation_origin=origin(number, name))
    with mock.patch.object(node, "get_parameter_value", side_effect=AssertionError("Mutable UI title read")):
        payload = node._build_broker_payload(params)
    payload["client_request_id"] = "job-" + str(number) * 32
    return payload, params


class TitleOpener(transport.RouteOpener):
    """Record the submitted label before any completion/casecard operation."""
    def __init__(self):
        super().__init__()
        self.transform = advertise
        self.accepted = {}
        self.lock = threading.Lock()
        self.post_barrier = None
        self.failure = None
        self.interval_once = False

    def open(self, request, timeout):
        if request.get_method() != "POST" or urlsplit(request.full_url).path != transport.GENERATE_PATH:
            return super().open(request, timeout)
        assert request.get_header("Authorization") == "Bearer " + transport.SYNTHETIC_TOKEN
        body = json.loads(request.data)
        key = request.get_header("Idempotency-key")
        assert key == body["client_request_id"]
        with self.lock:
            self.calls.append({"method": "POST", "path": transport.GENERATE_PATH,
                "body": deepcopy(body), "idempotency_key": key, "raw": request.data})
            first = len([call for call in self.posts if call["idempotency_key"] == key]) == 1
        if self.interval_once and first:
            raise urllib.error.HTTPError(request.full_url, 429, "Synthetic cooldown", {},
                io.BytesIO(json.dumps({"error_code": "submission_interval_limited", "retryable": True,
                    "provider_create_sent": False, "retry_after_ms": 0}).encode()))
        if self.failure is not None:
            raise self.failure
        # Mirrors the agreed frozen server candidate's first-accept metadata
        # semantics only; this fixture does not claim a deployed server test.
        with self.lock:
            previous = self.accepted.get(key)
            if previous is not None and previous != body:
                raise urllib.error.HTTPError(request.full_url, 409, "Immutable snapshot", {},
                    io.BytesIO(b'{"error":"immutable snapshot"}'))
            self.accepted.setdefault(key, deepcopy(body))
        if self.post_barrier is not None:
            self.post_barrier.wait(timeout=5)
            time.sleep((6 - body[FIELD]["number"]) * .003)
        response = io.BytesIO(json.dumps({"id": key, "status": "queued"}).encode())
        response.status = 202
        response.geturl = lambda: request.full_url
        return response


class SubmissionShotTitleTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(socket, "create_connection",
            side_effect=AssertionError("External network forbidden")))
        stack.enter_context(mock.patch.object(t.urllib.request.OpenerDirector, "open",
            side_effect=AssertionError("External transport forbidden")))
        stack.enter_context(mock.patch.object(t, "_broker_load_token",
            side_effect=AssertionError("Real credentials forbidden")))
        stack.enter_context(mock.patch.object(t, "_broker_log_transport_error"))
        stack.enter_context(mock.patch.object(t, "AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS", 0.0))
        for name in ("bind_task_origin", "bind_task_project"):
            stack.enter_context(mock.patch.object(t._review, name))

    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def bridge(self, opener=None):
        opener = opener or TitleOpener()
        bridge = t._HMBAIBrokerBridge(opener=opener, server_url=base.ORIGIN)
        bridge._load_access_token = mock.Mock(return_value=transport.SYNTHETIC_TOKEN)
        bridge._clear_access_token = mock.Mock()
        return bridge, opener

    def test_all_five_frozen_names_exist_on_initial_queued_task(self):
        for number in range(1, 6):
            with self.subTest(number=number):
                payload, params = build(number)
                params["_hmb_generation_origin"]["name"] = "Late changed shot"
                bridge, opener = self.bridge()
                result = bridge.generate_seedance(payload, timeout=2)
                self.assertEqual(result["status"], "queued")
                self.assertEqual(opener.accepted[result["id"]][FIELD], origin(number))
                self.assertEqual(len(opener.posts), 1)
                self.assertEqual(opener.capability_paths, [transport.CAP_PATH])
                self.assertFalse(any("casecard" in call["path"] for call in opener.calls))

    def test_five_concurrent_out_of_order_responses_keep_exact_shot_and_key(self):
        opener = TitleOpener()
        opener.post_barrier = threading.Barrier(5)
        payloads = [build(number)[0] for number in range(1, 6)]
        def send(payload):
            bridge, _ = self.bridge(opener)
            result = bridge.generate_seedance(payload, timeout=2)
            return result["id"], deepcopy(opener.accepted[result["id"]][FIELD])
        # Disable only the production cadence in this transport identity test;
        # its independently tested pacing would serialize this synthetic barrier.
        with mock.patch.object(t, "_broker_wait_for_http_submission", return_value=True):
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(send, payloads))
        self.assertEqual(len(opener.accepted), 5)
        self.assertEqual({key: shot for key, shot in results},
            {payload["client_request_id"]: payload[FIELD] for payload in payloads})

    def test_all_models_keep_submission_title_without_changing_render_settings(self):
        for model in t.MODEL_TASK_CHOICES:
            with self.subTest(model=model):
                payload, _ = build(model=model)
                before = deepcopy(payload)
                bridge, opener = self.bridge()
                bridge.generate_seedance(payload, timeout=2)
                self.assertEqual(payload, before)
                wire = opener.posts[0]["body"]
                self.assertEqual(wire[FIELD], origin())
                self.assertEqual(wire["model"], model)
                self.assertEqual(wire["prompt"], before["prompt"])

    def test_only_unknown_missing_snapshot_and_legacy_keep_compatible_requests(self):
        for mode in ("only", None, "legacy"):
            payload, _ = build(mode=mode)
            payload[FIELD] = origin()
            payload[t.GENERATION_MODE_METADATA_FIELD] = mode
            bridge, opener = self.bridge()
            bridge.generate_seedance(payload, timeout=2)
            self.assertNotIn(FIELD, opener.posts[0]["body"])
        payload, _ = build()
        payload.pop(FIELD)
        bridge, opener = self.bridge()
        bridge.generate_seedance(payload, timeout=2)
        self.assertNotIn(FIELD, opener.posts[0]["body"])

    def test_missing_disabled_malformed_or_failed_capability_never_blocks_legacy(self):
        variants = [None, {}, {**capability(), "enabled": False},
                    {**capability(), "enabled": 1}, {**capability(), "version": True},
                    {**capability(), "field": "shot_name"}, {**capability(), "schema": "future"}]
        for value in variants:
            with self.subTest(capability=value):
                opener = TitleOpener()
                opener.transform = lambda doc, *args: {**advertise(doc), "generation_shot_metadata": value}
                bridge, _ = self.bridge(opener)
                bridge.generate_seedance(build()[0], timeout=2)
                self.assertEqual(len(opener.posts), 1)
                self.assertNotIn(FIELD, opener.posts[0]["body"])
        # 2.0 Text needs no capability for rendering; optional display discovery
        # can fail without cancelling it or clearing this account's token.
        opener = TitleOpener()
        opener.transform = lambda *args: TimeoutError("Synthetic capability timeout")
        bridge, _ = self.bridge(opener)
        bridge.generate_seedance(build(model=t.SEEDANCE_2_0_FAST_MODEL_ID, task=t.TASK_TEXT_ONLY)[0], timeout=2)
        self.assertNotIn(FIELD, opener.posts[0]["body"])
        bridge._clear_access_token.assert_not_called()

    def test_literal_names_and_excluded_values_keep_existing_public_name_policy(self):
        for name in ("Shot 1", "까투리_8 e201s120c001__", "  생성 이름 🎬__  "):
            snapshot = origin(name=name)
            self.assertEqual(t._generation_submission_shot(snapshot), snapshot)
        for name in ("", "  ", "http://private.invalid/name", "C:\\private\\shot", "a/b", "a\nname",
                     "password=private", "Bearer private", "\ud800", "x" * 129):
            with self.subTest(name=repr(name)):
                self.assertEqual(t._generation_submission_shot(origin(4, name))["name"], "Shot 4")
        for changes in ({"channel_uuid": ""}, {"shot_uuid": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
                        {"number": True}, {"number": 6}, {"name": None}, {"extra": "private"}):
            self.assertEqual(t._generation_submission_shot({**origin(), **changes}), {})

    def test_definitive_cooldown_retry_preserves_exact_body_title_and_idempotency(self):
        bridge, opener = self.bridge()
        opener.interval_once = True
        bridge.generate_seedance(build(3)[0], timeout=2)
        self.assertEqual(len(opener.posts), 2)
        self.assertEqual(opener.posts[0]["raw"], opener.posts[1]["raw"])
        self.assertEqual(opener.posts[0]["idempotency_key"], opener.posts[1]["idempotency_key"])
        self.assertEqual(len(opener.accepted), 1)

    def test_uncertain_create_does_not_repost_or_change_captured_title(self):
        bridge, opener = self.bridge()
        opener.failure = TimeoutError("Synthetic create response lost")
        with self.assertRaises(t._BrokerUnavailableError) as raised:
            bridge.generate_seedance(build(5)[0], timeout=2)
        self.assertTrue(raised.exception.submission_outcome_unknown)
        self.assertEqual(len(opener.posts), 1)
        self.assertEqual(opener.posts[0]["body"][FIELD], origin(5))

    def test_draft_final_and_web_rerender_cannot_override_original_shot(self):
        node = base.Node()
        params = base.params(t.DRAFT_ACTION_FINAL)
        params.update(resolution="1080p", _hmb_generation_mode="shot", _hmb_generation_origin=origin(5))
        self.assertNotIn(FIELD, node._build_broker_payload(params))
        web = object.__new__(t._HMBWebRerenderExecution)
        for name in ("_assert_operation_project_selection", "_validate_parameters", "_validate_broker_model",
                     "_preflight_broker_media_size"):
            setattr(web, name, lambda *args, **kwargs: None)
        web._compose_finish_look_prompt = lambda prompt, *_args: prompt
        web._prepare_media_reference = lambda _kind, value: value
        params = fixture.parameters(t.SEEDANCE_2_5_MODEL_ID, t.TASK_REFERENCE_TO_VIDEO)
        params.update(_hmb_generation_mode="shot", _hmb_generation_origin=origin(5))
        payload = web._build_broker_payload(params)
        self.assertNotIn(FIELD, payload)
        self.assertNotIn(t.GENERATION_MODE_METADATA_FIELD, payload)


if __name__ == "__main__":
    unittest.main()
