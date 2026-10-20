"""Gateway review capability and delayed Shot-name publication regression.

Uses unchanged production methods through the existing offline portal fixture.
All accounts, credentials, task records and HTTP responses are synthetic. No
real server, provider, user workflow or original media is accessed.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import Request

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
import HMB_Review_Portal_Client_Regression as fixture

review = fixture.review
GATEWAY = "https://broker.example/GripTapeServer"


def capabilities(*, page="/GripTapeServer/reviews", manual=True):
    result = {**fixture.CAPABILITIES, "page_url": page,
        "captured_title_supported": True,
        "captured_title_schema": "hmb-captured-display-title", "captured_title_version": 1}
    if manual:
        result.update(retention_days=None, media_retention_days=None,
                      automatic_deletion=False, retention_policy="manual_only")
    return result


class MountedPortal(fixture.FakePortal):
    """Keep the real gateway HTTP address while reusing the v1 fake routes."""
    def __init__(self, namespace):
        super().__init__(namespace)
        self.capabilities = capabilities()
        self.public_requests = []

    def open(self, request, *, timeout):
        parsed = urlparse(request.full_url)
        self.public_requests.append({"method": request.method, "url": request.full_url})
        assert parsed.path.startswith("/GripTapeServer/api/v1/reviews/")
        assert parsed.scheme == "https" and parsed.netloc == "broker.example"
        assert request.method in {"GET", "PUT", "POST"}
        assert "/generate/" not in parsed.path and "/refresh" not in parsed.path
        internal = parsed._replace(path=parsed.path.removeprefix("/GripTapeServer")).geturl()
        rewritten = Request(internal, data=request.data, headers=dict(request.header_items()),
                            method=request.method)
        response = super().open(rewritten, timeout=timeout)
        response.url = request.full_url
        return response


class GatewayReviewCapabilities(unittest.TestCase):
    def setUp(self):
        self.queued, self.opened, self.tokens = [], [], []
        self.ns = fixture.production_namespace(self.queued, self.opened, self.tokens)
        self.portal = MountedPortal(self.ns)
        self.bridge = self.ns["Bridge"](opener=self.portal, server_url=GATEWAY)
        for target in ("socket.create_connection", "socket.socket.connect"):
            guard = patch(target, side_effect=AssertionError("Real network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_mounted_manual_retention_contract_is_supported(self):
        expected = deepcopy(self.portal.capabilities)
        self.assertEqual(self.bridge.review_capabilities(), {**expected, "_http_status": 200})
        self.assertEqual(self.portal.capabilities, expected)
        self.assertEqual(self.portal.public_requests, [{"method": "GET",
            "url": GATEWAY + "/api/v1/reviews/capabilities"}])

    def test_legacy_30_day_contract_survives_gateway_migration(self):
        for page in ("/reviews", "/GripTapeServer/reviews"):
            with self.subTest(page=page):
                self.portal.capabilities = capabilities(page=page, manual=False)
                self.assertEqual(self.bridge.review_capabilities()["retention_days"], 30)

    def test_bare_legacy_review_path_with_explicit_manual_retention_is_supported(self):
        self.portal.capabilities = capabilities(page="/reviews")
        self.assertIsNone(self.bridge.review_capabilities()["retention_days"])

    def test_external_sibling_and_ambiguous_page_routes_are_rejected(self):
        for page in ("https://evil.example/reviews", "https://broker.example/GripTapeServer/reviews",
                     "//evil.example/reviews", "/OtherGateway/reviews", "/GripTapeServer2/reviews",
                     "/GripTapeServer/reviews/", "/GripTapeServer/reviews?token=canary",
                     "/GripTapeServer/reviews#fragment", "/GripTapeServer/../reviews",
                     "/GripTapeServer/%2e%2e/reviews", "/GripTapeServer\\reviews", None, 1, [], {}):
            with self.subTest(page=page):
                self.portal.capabilities = capabilities(page=page)
                with self.assertRaises(self.ns["_BrokerProtocolError"]):
                    self.bridge.review_capabilities()

    def test_null_retention_requires_the_explicit_manual_only_contract(self):
        invalid = (
            {"automatic_deletion": True}, {"automatic_deletion": None},
            {"automatic_deletion": 0}, {"retention_policy": "automatic"},
            {"retention_policy": None}, {"retention_days": False},
            {"retention_days": 0}, {"retention_days": 30.0},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                self.portal.capabilities = {**capabilities(), **overrides}
                with self.assertRaises(self.ns["_BrokerProtocolError"]):
                    self.bridge.review_capabilities()
        for missing in ("automatic_deletion", "retention_policy"):
            with self.subTest(missing=missing):
                self.portal.capabilities = capabilities()
                self.portal.capabilities.pop(missing)
                with self.assertRaises(self.ns["_BrokerProtocolError"]):
                    self.bridge.review_capabilities()

    def test_unknown_or_forged_outer_contract_is_rejected(self):
        for overrides in ({"schema": "unknown"}, {"version": True}, {"version": 2},
                          {"review_portal": 1}, {"page_size": 10}, {"page_size": 20.0}):
            with self.subTest(overrides=overrides):
                self.portal.capabilities = {**capabilities(), **overrides}
                with self.assertRaises(self.ns["_BrokerProtocolError"]):
                    self.bridge.review_capabilities()

    def _node(self):
        namespace, portal = self.ns, self.portal
        class Node(namespace["PortalNode"]):
            def __init__(self):
                self.name, self.alive = "SyntheticGatewayPortal", True
                self._hmb_review_sync_epoch = 0
                self._hmb_review_sync_lock = threading.Lock()
                self._hmb_review_sync_jobs = set()
                self.checkpoint, self.values, self.published = {}, {"status_details": "render succeeded"}, []
                self._generation_run_active = threading.Event()
            def _runtime_node_is_live(self, **_kwargs):
                return self.alive
            def _generation_recovery_state(self):
                return self.checkpoint
            def _create_broker_bridge(self, *, server_url):
                return namespace["Bridge"](opener=portal, server_url=server_url)
            def _authoritative_existing_generation_id(self):
                return self.checkpoint.get("task_id", "")
            def get_parameter_value(self, name):
                return self.values.get(name)
            def set_parameter_value(self, name, value):
                self.values[name] = value
            def publish_update_to_parameter(self, name, value):
                self.published.append((name, value))
        return Node()

    def test_five_completed_task_names_publish_late_without_render_or_original_mutation(self):
        with tempfile.TemporaryDirectory(prefix="hmb-gateway-late-casecard-") as directory:
            root = Path(directory)
            original_root = review.review_root
            with patch.dict(os.environ, {"APPDATA": str(root / "app"), "LOCALAPPDATA": str(root / "local")}), \
                    patch.object(review, "review_root", side_effect=lambda value=None: original_root(value or root)):
                node = self._node()
                before, expected = {}, {}
                for number in range(1, 6):
                    task = "job-" + str(number) * 32
                    name = f"e201s120c00{number}__"
                    expected[task] = name
                    case = review.start_case("synthetic-client-" + str(number),
                        {"project_id": "superwings12", "project_name": "슈퍼윙즈12",
                         "settings": {"resolution": "480p", "duration": 4, "generate_audio": False},
                         "generation_origin": {"channel_uuid": "channel-a", "shot_uuid": "shot-" + str(number),
                            "source_node_instance_id": "generator-" + str(number), "number": number, "name": name}},
                        "Original prompt " + str(number), {"library_version": "0.8.16"}, {})
                    review.update_case(task, case_id=case, status="succeeded")
                    review.bind_task_origin(task, GATEWAY)
                    review.mark_server_sync(task, status="failed", reason="portal_failed")
                    before[task] = review.read_case(task)
                for number in (3, 1, 5, 2, 4):
                    task = "job-" + str(number) * 32
                    node._sync_review_task(task, GATEWAY, 0)
                    record = review.read_case(task)
                    self.assertEqual(record["server_sync"]["status"], "synced")
                    self.assertEqual(self.portal.casecards[task]["shot"]["name"], expected[task])
                    self.assertEqual(node._hmb_captured_title_sync_state["status"], "embedded")
                    for field in ("inputs", "submitted_prompt", "prompt_sha256", "input_evidence_sha256",
                                  "case_id", "client_request_id", "task_id", "status", "reviews"):
                        self.assertEqual(record[field], before[task][field])
                writes = [call for call in self.portal.public_requests if call["method"] != "GET"]
                self.assertEqual(len(writes), 5)
                self.assertTrue(all(call["method"] == "PUT" and call["url"].endswith("/casecard") for call in writes))
                for task in expected:
                    node._sync_review_task(task, GATEWAY, 0)
                self.assertEqual([call for call in self.portal.public_requests if call["method"] != "GET"], writes)
                self.assertEqual({task: card["shot"]["name"] for task, card in self.portal.casecards.items()}, expected)
                self.assertEqual(set(self.tokens), {GATEWAY})
                self.assertFalse(self.opened)

    def test_unsupported_gateway_contract_leaves_completed_result_intact(self):
        with tempfile.TemporaryDirectory(prefix="hmb-gateway-invalid-cap-") as directory:
            root = Path(directory)
            original_root = review.review_root
            with patch.object(review, "review_root", side_effect=lambda value=None: original_root(value or root)):
                task = "job-" + "a" * 32
                case = review.start_case("synthetic-invalid-cap", {"generation_origin": {
                    "channel_uuid": "channel-a", "shot_uuid": "shot-a", "number": 1,
                    "name": "Original captured Shot"}}, "original prompt", {}, {})
                review.update_case(task, case_id=case, status="succeeded")
                before = review.read_case(task)
                self.portal.capabilities = capabilities(page="/Sibling/reviews")
                self._node()._sync_review_task(task, GATEWAY, 0)
                after = review.read_case(task)
                self.assertEqual(after["status"], "succeeded")
                self.assertEqual(after["inputs"], before["inputs"])
                self.assertEqual(after["input_evidence_sha256"], before["input_evidence_sha256"])
                self.assertEqual(after["server_sync"]["status"], "failed")
                self.assertTrue(all(call["method"] == "GET" for call in self.portal.public_requests))
                self.assertFalse(self.portal.casecards)


if __name__ == "__main__":
    unittest.main(verbosity=2)
