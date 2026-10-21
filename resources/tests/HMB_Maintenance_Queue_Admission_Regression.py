"""Offline R11 admission using actual Bridge bodies and synthetic urllib I/O.

Fixture: server R11-ADMISSION-SYNTHETIC-RESPONSE.json, 2026-10-22.
No server import, SDK, credentials, sockets, provider, install or user DB access.
"""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import time
import urllib.error
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_queue_admission as queue
import _hmb_image_generation as images
import _hmb_my_box as box

spec = importlib.util.spec_from_file_location("queue_actual_auth_fixture", Path(__file__).with_name("HMB_Seedance_Reference_Lease_Regression.py"))
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
RAW = json.loads(Path(__file__).with_name("HMB_Maintenance_Queue_Fixture.json").read_text("utf-8"))
SOURCE = "job-mybox-" + "a" * 32
CID = "synthetic-queue-client"


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.ns = fixture.isolated_bridge_methods()
        self.auth = "synthetic-token-A"
        self.calls = []
        self.raw = deepcopy(RAW)
        self.rejection = None
        self.lost = False
        self.source_status = "completed"
        self.final = None
        self.video_final = {"schema": "hmb-review-draft-final-v1", "source_task_id": "job-" + "d" * 32,
            "owner_user_id": 7, "state": "available", "eligible": True, "child_task_id": None, "expires_at": int(time.time()) + 500}
        self.ns["_broker_load_token"] = lambda **_: self.auth
        self.ns["_broker_clear_token"] = lambda **_: None
        self.bridge = self.ns["ActualAuthBridge"](server_url=fixture.ORIGIN, opener=SimpleNamespace(open=self.open))
        self.bridge._open_create_request = self.open

    def open(self, request, timeout):
        path = urlsplit(request.full_url).path.removeprefix("/gateway")
        body = json.loads(request.data) if request.data is not None else None
        self.calls.append((request.get_method(), path, deepcopy(body), dict(request.header_items())))
        if path == "/api/me":
            data = {"id": 7 if self.auth == "synthetic-token-A" else 8, "username": "fixture-member"}
        elif path == queue.PATH:
            if self.rejection is not None:
                raise urllib.error.HTTPError(request.full_url, self.rejection, "synthetic rejection", {}, io.BytesIO(b'{}'))
            data = deepcopy(self.raw)
        elif request.get_method() == "GET" and path.startswith(box.API + "/items/"):
            data = self.private_job(CID, SOURCE, self.source_status)
            if self.final is not None:
                data["draft_final"] = deepcopy(self.final)
        elif request.get_method() == "GET" and path.endswith("/draft-final"):
            data = deepcopy(self.video_final)
        elif request.get_method() == "POST" and path == "/api/v1/generate/image":
            if self.lost:
                raise TimeoutError("synthetic response lost after durable acceptance")
            data = {"schema": images.JOB_SCHEMA, "version": 1, "job_id": "job-image-" + "b" * 32,
                "client_request_id": body["client_request_id"], "provider": body["provider"], "model": body["model"],
                "status": "queued", "persistence_scope": "personal_local", "publish_to_reviews": False}
        elif request.get_method() == "POST" and path == "/api/v1/generate/video":
            data = self.private_job(body["client_request_id"], "job-mybox-" + "b" * 32, "pending") if body.get("my_box_selection") else {
                "id": "job-" + "b" * 32, "client_request_id": body["client_request_id"], "status": "pending"}
        elif request.get_method() == "POST" and path.endswith("/refresh"):
            data = {"schema": images.JOB_SCHEMA, "version": 1, "job_id": "job-image-" + "b" * 32,
                "client_request_id": CID, "provider": "google", "model": "gemini-3-pro-image",
                "status": "queued", "persistence_scope": "personal_local", "publish_to_reviews": False}
        else:
            raise AssertionError("Native generation/readiness or workspace/source grant route was called: " + path)
        response = io.BytesIO(json.dumps(data).encode())
        response.status = 202 if request.get_method() == "POST" and "/generate/" in path else 200
        response.geturl = lambda: request.full_url
        return response

    def private_job(self, cid, task, status):
        return {"schema": box.JOB_SCHEMA, "version": 1, "task_id": task, "job_id": task,
            "workspace_id": self.selection()["workspace_id"], "scope": box.SCOPE, "publish_to_reviews": False,
            "generation_mode": "only", "resubmit_allowed": False, "client_request_id": cid,
            "provider": "volcengine_ark", "model": "doubao-seedance-2-5-260628", "status": status}

    def selection(self):
        return deepcopy((self.raw["only_syntax"]["workspace"] or self.raw["workspace_intent"])["selection"])

    def image(self):
        broker = images.ImageGenerationBroker(self.bridge)
        caps = broker.capabilities()
        invocation = images.prepare_invocation(caps, provider="google", model_id="gemini-3-pro-image", task="text-to-image",
            prompt="Keep authored literal text", ratio="16:9", image_size="1K", output_format="png", client_request_id=CID)
        return broker, caps, invocation

    def private(self, **changes):
        broker = box.MyBoxBroker(self.bridge)
        caps = broker.capabilities()
        base = {"provider": "volcengine_ark", "model": "doubao-seedance-2-5-260628", "prompt": "literal",
            "resolution": "480p", "output_format": "mov", "seed": 0, "generate_audio": False, **changes}
        return broker, caps, box.prepare_invocation(base, selection=self.selection(), title="Private", client_request_id=CID,
            queue_admission=caps._queue_admission)

    def posts(self):
        return [c for c in self.calls if c[0] == "POST" and "/generate/" in c[1]]

    def test_three_headers_and_native_image_body_flags_unchanged(self):
        broker, caps, invocation = self.image()
        self.assertFalse(caps.enabled)
        self.assertTrue(all(not m.enabled and not m.credential_ready for m in caps.models))
        before = invocation.payload()
        checkpoints = []
        result = broker.create(invocation, on_submission_prepared=lambda value: checkpoints.append(value.payload()))
        self.assertEqual(result["status"], "queued")
        self.assertEqual(checkpoints, [before])
        self.assertEqual(self.posts()[0][2], before)
        actual_headers = {k.lower(): v for k, v in self.posts()[0][3].items()}
        for key, value in caps._queue_admission.headers.items():
            self.assertEqual(actual_headers[key.lower()], value)
        self.assertEqual(actual_headers["idempotency-key"], CID)
        self.assertNotIn("queue_only", before)
        self.assertEqual(json.loads(json.dumps(caps._queue_admission.headers)), caps._queue_admission.headers)

    def test_plain_disabled_capability_cannot_prepare(self):
        broker, caps, invocation = self.image()
        with self.assertRaises(images.ImageGenerationError):
            images.prepare_invocation(replace(caps, _queue_admission=None), provider="google", model_id="gemini-3-pro-image",
                task="text-to-image", prompt="literal", ratio="16:9", image_size="1K", output_format="png")
        self.assertEqual(self.posts(), [])

    def test_auth_rotation_copied_or_foreign_admission_blocks_post(self):
        for changed in ("token", "copy", "bridge"):
            with self.subTest(changed=changed):
                self.setUp()
                broker, caps, invocation = self.image()
                if changed == "token":
                    self.auth = "synthetic-token-B"
                elif changed == "copy":
                    broker._capabilities = replace(caps, _queue_admission=copy(caps._queue_admission))
                else:
                    broker._bridge = copy(self.bridge)
                with self.assertRaises((queue.QueueAdmissionError, images.ImageGenerationError)): broker.create(invocation)
                self.assertEqual(self.posts(), [])

    def test_principal_mismatch_never_binds(self):
        self.raw["principal"]["id"] = 99
        with self.assertRaises(queue.QueueAdmissionError): self.bridge.queue_admission()
        self.assertIsNone(self.bridge._queue_admission_binding)

    def test_native_absence_only_404_405_501_is_optional(self):
        for code in (404, 405, 501, 503, 401):
            self.rejection = code
            if code in (404, 405, 501): self.assertIsNone(self.bridge.queue_admission(refresh=True))
            else:
                with self.assertRaises(self.ns["_BrokerError"]): self.bridge.queue_admission(refresh=True)
        self.assertEqual(self.posts(), [])

    def test_non_capture_has_no_authority_or_profiles(self):
        raw = {k: deepcopy(v) for k, v in RAW.items() if k not in {"video_syntax", "image_syntax", "only_syntax", "workspace_intent", "operations", "video_models", "project_routing"}}
        raw.update(mode="draining", queue_only=False)
        self.assertIsNone(queue.parse(raw))
        with self.assertRaises(queue.QueueAdmissionError): queue.parse({**raw, "queue_only": True})
        with self.assertRaises(queue.QueueAdmissionError): queue.parse({**raw, "image_syntax": RAW["image_syntax"]})

    def test_generation_source_and_false_readiness_strict(self):
        for field, bad in (("admission_generation", True), ("admission_generation", -1), ("admission_generation", 2**53),
                ("source_instance", "bad\nheader"), ("generation_ready", True), ("native_readiness_verified", True),
                ("execution_revalidation_required", False), ("operations", ["image", "image"])):
            with self.subTest(field=field, bad=bad):
                with self.assertRaises(queue.QueueAdmissionError): queue.parse({**RAW, field: bad})
        for value in (0, queue.MAX_GENERATION):
            self.assertEqual(queue.parse({**RAW, "admission_generation": value}).headers["X-HMB-Intake-Generation"], str(value))
        for value in ("01", "-1", "+1", "1.0", str(2**53), 1):
            with self.assertRaises(queue.QueueAdmissionError): queue.identity({**queue.parse(RAW).headers, "X-HMB-Intake-Generation": value})

    def test_workspace_intent_read_never_creates(self):
        broker, caps, invocation = self.private()
        self.assertIsNone(caps.workspace)
        self.assertIsNone(broker.workspace())
        target = broker.workspace(create=True, explicit_selection=True)
        self.assertEqual(target, RAW["workspace_intent"])
        self.assertIsNone(caps.workspace)
        self.assertFalse(caps.enabled or caps.generation_enabled)
        with self.assertRaises(box.MyBoxError): caps.require_generation()
        self.assertEqual(broker.create(invocation)["status"], "pending")
        self.assertFalse(any(c[1].endswith("/workspace") for c in self.calls))

    def test_existing_workspace_and_foreign_workspace_rejected(self):
        self.raw["only_syntax"]["workspace"] = deepcopy(RAW["workspace_intent"])
        self.raw["only_syntax"]["workspace"]["created_at"] = 100
        self.raw["workspace_intent"] = None
        broker, caps, invocation = self.private()
        self.assertEqual(broker.workspace(), caps.workspace)
        bad_selection = {**invocation.selection, "workspace_id": "mbx_" + "f" * 32}
        bad = box.prepare_invocation(invocation.payload() | {"my_box_selection": bad_selection}, selection=bad_selection, title="Private", client_request_id=CID)
        with self.assertRaises(box.MyBoxError): broker.create(bad)
        self.assertEqual(self.posts(), [])

    def test_source_detail_then_marker_no_grant_post(self):
        broker, caps, invocation = self.private()
        grant = broker.source_reference(SOURCE, CID, "Video Editing", selection=invocation.selection)
        self.assertEqual(grant, {"url": queue.source_marker(SOURCE), "queue_only": True})
        self.assertTrue(any(c[0:2] == ("GET", box.API + "/items/" + SOURCE) for c in self.calls))
        self.assertFalse(any(c[0] == "POST" for c in self.calls))
        self.source_status = "running"
        with self.assertRaises(box.MyBoxError): broker.source_reference(SOURCE, CID, "Video Editing", selection=invocation.selection)

    def test_markers_only_explicit_private_video_urls(self):
        marker = queue.source_marker(SOURCE)
        payload = {"video_urls": [marker], "my_box_selection": self.selection()}
        queue.validate_create(payload, "/api/v1/generate/video", "only", queue_only=True)
        for field in ("image_urls", "audio_urls", "reference_images", "first_frame", "last_frame"):
            with self.assertRaises(queue.QueueAdmissionError):
                queue.validate_create({field: [marker], "my_box_selection": self.selection()}, "/api/v1/generate/video", "only", queue_only=True)
        with self.assertRaises(queue.QueueAdmissionError): queue.validate_create(payload, "/api/v1/generate/video", "only", queue_only=False)
        with self.assertRaises(queue.QueueAdmissionError): queue.validate_create(payload, "/api/v1/generate/image", "only", queue_only=True)

    def test_stale409_or_response_loss_never_auto_reposts(self):
        for outcome in ("lost", "409"):
            with self.subTest(outcome=outcome):
                self.setUp()
                broker, caps, invocation = self.image()
                if outcome == "lost": self.lost = True
                else:
                    original = self.bridge._open_create_request
                    original_open = self.bridge._opener.open
                    def reject(request, timeout):
                        if request.get_method() == "POST" and "/generate/" in request.full_url:
                            self.calls.append(("POST", "/api/v1/generate/image", json.loads(request.data), {}))
                            raise urllib.error.HTTPError(request.full_url, 409, "generation changed", {}, io.BytesIO(b'{"request_captured":false}'))
                        return original_open(request, timeout)
                    self.bridge._opener.open = reject
                with self.assertRaises(images.ImageGenerationError) as raised: broker.create(invocation)
                self.assertEqual(raised.exception.submission_outcome_unknown, outcome == "lost")
                self.assertEqual(len(self.posts()), 1)
                if outcome == "lost":
                    job = broker.refresh(CID, client_request_id=CID)
                    self.assertEqual(job["client_request_id"], CID)
                    self.assertEqual(len(self.posts()), 1)

    def test_cancel_or_invalid_immutable_snapshot_has_no_post(self):
        broker, caps, invocation = self.image()
        with self.assertRaises(images.ImageGenerationError): broker.create(invocation, is_alive=lambda: False)
        body = invocation.payload() | {"image_size": "unsupported"}
        forged = replace(invocation, _payload_json=json.dumps(body))
        with self.assertRaises(images.ImageGenerationError): broker.create(forged)
        self.assertEqual(self.posts(), [])

    def test_header_identity_is_frozen_with_both_invocations(self):
        for kind in ("image", "only"):
            with self.subTest(kind=kind):
                self.setUp()
                broker, caps, invocation = self.image() if kind == "image" else self.private()
                headers = json.loads(invocation._queue_headers_json)
                self.assertEqual(headers, caps._queue_admission.headers)
                self.raw["admission_generation"] += 1
                broker.capabilities()
                with self.assertRaises((images.ImageGenerationError, box.MyBoxError)):
                    broker.create(invocation)
                self.assertEqual(self.posts(), [])

    def test_private_final_fresh_owner_eligibility_and_child_fence(self):
        broker, caps, invocation = self.private(draft_job_id=SOURCE, resolution="1080p", quality="1080p")
        self.final = {"schema": box.DRAFT_FINAL_SCHEMA, "version": 1, "state": "available", "eligible": True,
            "source_task_id": SOURCE, "child_task_id": None, "child_status": None, "expires_at": int(time.time()) + 500,
            "expiry_basis": "source_creation_provider_limit", "workspace_id": self.selection()["workspace_id"],
            "selection": self.selection(), "final_client_request_id": "mbx-final-v1-" + "a" * 32,
            "eligibility_scope": "source_only", "resubmit_allowed": False, "reason_code": None}
        broker.create(invocation)
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.posts()[0][2]["draft_job_id"], SOURCE)
        self.assertFalse(caps.generation_enabled)
        self.final["expires_at"] = int(time.time()) - 1
        with self.assertRaises(box.MyBoxError): broker.create(invocation)
        self.assertEqual(len(self.posts()), 1)

    def video_bridge(self):
        path = Path(__file__).with_name("HMB_Seedance_Capability_Routing_Regression.py")
        key = "queue_full_video_fixture"
        if key not in sys.modules:
            spec = importlib.util.spec_from_file_location(key, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            spec.loader.exec_module(module)
        target = sys.modules[key].t
        patch = mock.patch.object(target, "_broker_load_token", side_effect=lambda **_: self.auth)
        patch.start(); self.addCleanup(patch.stop)
        target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0
        self.bridge = target._HMBAIBrokerBridge(server_url=fixture.ORIGIN, opener=SimpleNamespace(open=self.open))
        return target, self.bridge

    def test_all_three_video_models_use_pure_queue_syntax_and_keep_options(self):
        target, bridge = self.video_bridge()
        for row in self.raw["video_models"]:
            body = {**row, "prompt": "literal", "quality": "720p", "resolution": "720p", "aspect_ratio": "16:9",
                "task": "Reference to Video", "input_mode": "multimodal_references", "image_urls": ["data:image/png;base64,fixture"],
                "generate_audio": False, "client_request_id": CID, "output_format": "mov"}
            bridge.generate_seedance(body, timeout=5)
            posted = self.posts()[-1][2]
            self.assertEqual(posted["model"], row["model"])
            self.assertIs(posted["generate_audio"], False)
            self.assertEqual(posted["client_request_id"], CID)
            self.assertNotIn("queue_only", posted)
            self.assertEqual(posted.get("output_format"), "mov" if row["model"] == target.SEEDANCE_2_5_MODEL_ID else None)
        self.assertEqual(len(self.posts()), 3)

    def test_video_final_keeps_source_and_1080_target_and_blocks_expiry(self):
        target, bridge = self.video_bridge()
        body = {"model": target.SEEDANCE_2_5_MODEL_ID, "draft_job_id": self.video_final["source_task_id"],
            "resolution": "1080p", "quality": "1080p", "output_format": "mov", "client_request_id": CID}
        frozen = deepcopy(body)
        bridge.generate_seedance(body, timeout=5)
        self.assertEqual(body, frozen)
        self.assertEqual(self.posts()[0][2], {"provider": "volcengine_ark", **frozen})
        for change in ({"expires_at": int(time.time()) - 1}, {"owner_user_id": 8}, {"child_task_id": "job-" + "e" * 32}):
            prior = deepcopy(self.video_final)
            self.video_final.update(change)
            with self.assertRaises(target._BrokerProtocolError): bridge.generate_seedance(body, timeout=5)
            self.video_final = prior
        self.assertEqual(len(self.posts()), 1)

    def test_checkpoint_generation_change_never_posts_under_new_identity(self):
        target, bridge = self.video_bridge()
        admission = bridge.queue_admission()
        headers = admission.headers
        self.raw["admission_generation"] += 1
        bridge.queue_admission(refresh=True)
        with self.assertRaises(queue.QueueAdmissionError):
            bridge.generate_seedance({"model": target.SEEDANCE_2_0_MODEL_ID, "prompt": "literal", "client_request_id": CID},
                timeout=5, queue_only_headers=headers)
        self.assertEqual(self.posts(), [])

    def test_native_local_admission_rejection_discards_only_unsubmitted_checkpoint(self):
        import asyncio
        self.video_bridge()
        module=sys.modules['queue_full_video_fixture']
        node=module.RoutingNode()
        node.bridge.generate_seedance=mock.Mock(side_effect=queue.QueueAdmissionError('Synthetic local admission rotation'))
        with self.assertRaises(queue.QueueAdmissionError): asyncio.run(node._process_generation_impl())
        self.assertEqual(node.transport.posts,[])
        self.assertFalse(node._generation_recovery_state().get('task_id'))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AdmissionTests))
    print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL", "tests": result.testsRun,
        "actual_bridge_method_bodies": True, "native_readiness_forged": False, "network": "synthetic-opener-only",
        "paid_calls": 0, "credential_store_reads": 0, "installed_files_changed": 0}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
