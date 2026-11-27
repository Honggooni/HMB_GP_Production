"""Offline advanced option boundaries and exact request/recovery semantics.

Uses the real Generator validator and payload builder with the existing
clean-CI node fixture. No provider, Broker, upload or active workflow is used.
"""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))
spec = importlib.util.spec_from_file_location(
    "advanced_transport_option_fixture", TESTS / "HMB_Seedance_Draft_Regression.py",
)
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t
from _hmb_cloud_proof_fixtures import CloudInputFixture


class AdvancedTransportOptionsRegression(unittest.TestCase):
    def test_cloud_proof_requires_the_designated_broker_and_an_empty_authenticated_probe(self):
        target = "https://test.example/GripTapeTest"
        bridge = Mock(server_url=target)
        ref = {"reference_images": ["image.png"]}
        bridge._request_json.return_value = {"_http_status": 200, "files": [], "provider_submitted": False}
        probe = t._negotiate_cloud_reference_proof
        with patch.dict(os.environ, {"HMB_CLOUD_PREFLIGHT_V1_BROKER_URL": target}):
            self.assertFalse(asyncio.run(probe(bridge, "https://other.example", ref)))
            self.assertFalse(asyncio.run(probe(bridge, target, {"video_reference_slots": [None, ""]})))
            bridge._request_json.assert_not_called()
            self.assertTrue(asyncio.run(probe(bridge, target, ref)))
            bridge._request_json.assert_called_once_with("POST", "/api/v1/preflight/griptape-cloud", payload={}, timeout=10.0)
            for changed in ({"_http_status": 204}, {"files": [{}]}, {"provider_submitted": 0}):
                bridge._request_json.return_value = {"_http_status": 200, "files": [], "provider_submitted": False, **changed}
                with self.assertRaises(t._BrokerProtocolError):
                    asyncio.run(probe(bridge, target, ref))
            bridge._request_json.side_effect = t._BrokerError("Unknown route", status_code=404)
            with self.assertRaises(t._BrokerError):
                asyncio.run(probe(bridge, target, ref))

    def tearDown(self):
        while fixture.TEMPORARIES:
            fixture.TEMPORARIES.pop().cleanup()

    def values(self, **changes):
        values = fixture.params()
        values.update(changes)
        return values

    def validate(self, values):
        node = fixture.Node(values)
        node._validate_parameters(values)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.bridge.refresh_ids, [])
        self.assertEqual(node.upload_calls, 0)
        return node

    def invalid(self, **changes):
        values = self.values(**changes)
        node = fixture.Node(values)
        with self.assertRaises(ValueError):
            node._build_broker_payload(values)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.bridge.refresh_ids, [])
        self.assertEqual(node.upload_calls, 0)

    def test_poll_interval_and_local_timeout_exact_positive_integer_boundaries(self):
        for interval, timeout in ((1, 1), (1, 3600), (30, 3600), (3600, 3600)):
            with self.subTest(interval=interval, timeout=timeout):
                values = self.values(poll_interval_seconds=interval,
                                     generation_timeout_seconds=timeout)
                node = self.validate(values)
                body = node._build_broker_payload(values)
                self.assertEqual(values["poll_interval_seconds"], interval)
                self.assertEqual(values["generation_timeout_seconds"], timeout)
                self.assertNotIn("poll_interval_seconds", body)
                self.assertNotIn("generation_timeout_seconds", body)

    def test_invalid_polling_controls_fail_before_payload_or_upload(self):
        for name in ("poll_interval_seconds", "generation_timeout_seconds"):
            for value in (0, -1, True, False, 1.5, "30", None):
                with self.subTest(name=name, value=value):
                    self.invalid(**{name: value})
        self.invalid(poll_interval_seconds=61, generation_timeout_seconds=60)

    def test_provider_expiry_both_limits_and_default_survive_into_wire(self):
        for expiry in (3600, 172800, 259200):
            with self.subTest(expiry=expiry):
                values = self.values(execution_expires_after=expiry)
                node = self.validate(values)
                self.assertEqual(node._build_broker_payload(values)["execution_expires_after"], expiry)

    def test_invalid_expiry_is_never_clamped_or_posted(self):
        for value in (3599, 259201, 0, -1, True, False, 3600.0, "3600", None):
            with self.subTest(value=value):
                self.invalid(execution_expires_after=value)

    def test_full_seedance20_priorities_zero_through_nine_survive_wire(self):
        for priority in range(10):
            with self.subTest(priority=priority):
                values = self.values(model_id=t.SEEDANCE_2_0_MODEL_ID, priority=priority)
                node = self.validate(values)
                self.assertEqual(node._build_broker_payload(values)["priority"], priority)

    def test_invalid_priorities_fail_before_payload_or_upload(self):
        for value in (-1, 10, True, False, 1.0, "0", None):
            with self.subTest(value=value):
                self.invalid(model_id=t.SEEDANCE_2_0_MODEL_ID, priority=value)

    def test_fast_and_seedance25_allow_zero_and_omit_unsupported_priority(self):
        for model in (t.SEEDANCE_2_0_FAST_MODEL_ID, t.SEEDANCE_2_5_MODEL_ID):
            with self.subTest(model=model):
                values = self.values(model_id=model, priority=0)
                node = self.validate(values)
                self.assertNotIn("priority", node._build_broker_payload(values))
                self.assertEqual(values["priority"], 0)
                for unsupported in (1, 9):
                    self.invalid(model_id=model, priority=unsupported)

    def test_false_audio_watermark_and_last_frame_are_not_replaced_by_defaults(self):
        values = self.values(generate_audio=False, watermark=False, return_last_frame=False,
                             output_format="mov", priority=0)
        original = deepcopy(values)
        node = self.validate(values)
        body = node._build_broker_payload(values)
        for key in ("generate_audio", "watermark", "return_last_frame"):
            self.assertIs(body[key], False)
        self.assertEqual(body["output_format"], "mov")
        self.assertEqual(values, original)

    def test_legacy_transport_settings_survive_reopen_and_stay_out_of_render_requests(self):
        for service in (*t.LOCAL_VIDEO_UPLOAD_SERVICES, "unsupported saved uploader"):
            for auto_publish in (False, True):
                with self.subTest(service=service, auto_publish=auto_publish):
                    values = self.values(local_video_upload_service=service,
                        auto_publish_local_videos=auto_publish, tos_url_validity_seconds=86400,
                        tos_region=t.DEFAULT_TOS_REGION, tos_endpoint=t.DEFAULT_TOS_ENDPOINT)
                    original = deepcopy(values)
                    node = self.validate(values)
                    body = node._build_broker_payload(values)
                    for field in ("local_video_upload_service", "auto_publish_local_videos", "tos_region",
                                  "tos_endpoint", "tos_url_validity_seconds"):
                        self.assertNotIn(field, body)
                    self.assertEqual(values, original)

    def test_retired_tos_ttl_does_not_block_cloud_requests(self):
        for ttl in (3600, 86400, 2592000, 3599, 2592001, 0, True, False, 3600.0, "3600", None):
            with self.subTest(ttl=ttl):
                values = self.values(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_TOS,
                    tos_url_validity_seconds=ttl, tos_region=t.DEFAULT_TOS_REGION,
                    tos_endpoint=t.DEFAULT_TOS_ENDPOINT)
                self.validate(values)
                self.assertEqual(values["tos_url_validity_seconds"], ttl)

    def test_stale_tos_endpoint_from_workflow_is_never_forwarded(self):
        for endpoint in ("http://tos-cn-beijing.volces.com", "https://attacker.example",
                         "https://tos-cn-beijing.volces.com/path",
                         "https://secret@tos-cn-beijing.volces.com",
                         "https://tos-cn-beijing.volces.com?token=fixture",
                         "https://tos-cn-beijing.volces.com:444"):
            with self.subTest(endpoint=endpoint):
                values = self.values(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_TOS,
                    tos_url_validity_seconds=86400, tos_region=t.DEFAULT_TOS_REGION,
                    tos_endpoint=endpoint)
                payload = self.validate(values)._build_broker_payload(values)
                self.assertNotIn(endpoint, json.dumps(payload))

    def test_cloud_selection_is_not_blocked_by_unused_stale_tos_options(self):
        values = self.values(local_video_upload_service=t.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
                             tos_url_validity_seconds=0, tos_region="", tos_endpoint="invalid")
        self.validate(values)

    def test_resume_validates_only_existing_identity_and_polling_not_new_render_controls(self):
        values = self.values(resume_generation_id=fixture.JOB, model_id="old-model",
            execution_expires_after=-1, priority=99, local_video_upload_service="old-uploader",
            tos_url_validity_seconds=0, output_format="old-format", reference_images=["missing"])
        original = deepcopy(values)
        self.validate(values)
        self.assertEqual(values, original)
        for name in ("poll_interval_seconds", "generation_timeout_seconds"):
            invalid = deepcopy(values)
            invalid[name] = 0
            node = fixture.Node(invalid)
            with self.assertRaises(ValueError):
                node._validate_parameters(invalid)
            self.assertEqual(node.bridge.posts, [])

    def test_final_sparse_request_ignores_new_prompt_media_tos_expiry_and_priority(self):
        values = self.values(draft_action=t.DRAFT_ACTION_FINAL, resolution="1080p", output_format="mov",
            prompt="must not be resent", reference_images=["unavailable-image"],
            video_references=["unavailable-picker"], execution_expires_after=-1, priority=99,
            local_video_upload_service="old-uploader", tos_url_validity_seconds=0)
        node = self.validate(values)
        body = node._build_broker_payload(values)
        self.assertEqual(set(body), {"provider", "model", "draft_job_id", "resolution", "output_format",
                                     "project_id", "project_name"})
        self.assertEqual((body["draft_job_id"], body["resolution"], body["output_format"]),
                         (fixture.JOB, "1080p", "mov"))
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.upload_calls, 0)

    def test_designated_project_posts_proven_media_once_and_retrieves_existing_id(self):
        origin = 'https://project-fixture.invalid/GripTapeTest'
        for kind in ('references', 'frames', 'text'):
            with self.subTest(kind=kind):
                node = fixture.Node(self.values())
                node.bridge.server_url = origin
                node._selected_broker_server_url = lambda: origin
                cloud = CloudInputFixture(node.base.name)
                node._create_gt_cloud_storage_driver = Mock(return_value=cloud)
                node._reference_video_upload_path = lambda path, model: nullcontext(path)
                node._prepare_video_references_for_run = t.HMBSeedanceGeneration._prepare_video_references_for_run.__get__(node)
                node.bridge._request_json = Mock(return_value={'_http_status': 200, 'provider_submitted': False, 'files': []})
                if kind == 'frames':
                    node.values.update(task=t.TASK_FIRST_LAST_FRAME, input_mode=t.INPUT_MODE_FIRST_LAST_FRAME,
                                       ratio='adaptive', first_frame=str(cloud.images[1]), last_frame=str(cloud.images[0]))
                elif kind == 'references':
                    node.values.update(task=t.TASK_REFERENCE_TO_VIDEO, input_mode=t.INPUT_MODE_MULTIMODAL_REFERENCES,
                                       reference_images=[str(path) for path in (*cloud.images, cloud.images[0])],
                                       video_reference_slots=[str(cloud.video)] * 2, reference_audio=[str(cloud.audio)] * 2)
                selection = {'schema': t.PROJECT_SELECTION_SCHEMA, 'project': deepcopy(fixture.PROJECT)}
                node._resolve_exact_shot_generation_inputs = lambda values: dict(values, _hmb_imageasset_project_selection=deepcopy(selection))
                with (
                    patch.dict(os.environ, {'HMB_CLOUD_PREFLIGHT_V1_BROKER_URL': origin, 'APPDATA': node.base.name}),
                    patch.object(t._broker_config, 'load_broker_base_url', return_value=origin),
                    patch.object(t, '_resolve_mp4_decode_verifier', return_value=SimpleNamespace(executable='fixture', backend='test')),
                    patch.object(node, '_capture_imageasset_project_selection', return_value=selection),
                    patch.object(t._review, 'capture_inputs', return_value={}),
                ):
                    asyncio.run(node._process_generation())
                    self.assertEqual(len(node.bridge.posts), 1)
                    payload = node.bridge.posts[0]
                    if kind == 'text':
                        node.bridge._request_json.assert_not_called()
                        self.assertFalse(cloud.uploads)
                    else:
                        node.bridge._request_json.assert_called_once_with('POST', '/api/v1/preflight/griptape-cloud', payload={}, timeout=10.0)
                        cloud.assert_payload(self, payload, frames=kind == 'frames')
                    job_id = node.saved[-1][0]
                    node.values['resume_generation_id'] = job_id
                    node.parameter_values['resume_generation_id'] = job_id
                    before = len(cloud.uploads), node.bridge._request_json.call_count
                    asyncio.run(node._process_generation())
                    self.assertEqual(node.bridge.refresh_ids, [job_id])
                    self.assertEqual(len(node.bridge.posts), 1)
                    self.assertEqual((len(cloud.uploads), node.bridge._request_json.call_count), before)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL", "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "provider_calls": 0, "mode": "clean_ci_actual_validator_and_payload"}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
